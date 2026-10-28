# 必需：``AgentProfileStore.list()`` 隐藏类主体中的内置函数，
# 因此像 ``list[dict[str, Any]]`` 这样的注释将在没有延迟的情况下失败。
from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable
from uuid import UUID, uuid4

from filelock import FileLock, Timeout

from openhands.sdk.logger import get_logger
from openhands.sdk.profiles.agent_profile import validate_agent_profile
from openhands.sdk.utils.path import get_user_persistence_dir


if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from openhands.sdk.profiles.agent_profile import (
        ACPAgentProfile,
        OpenHandsAgentProfile,
    )

_DEFAULT_PROFILE_DIR: Final[Path] = get_user_persistence_dir() / "agent-profiles"
_LOCK_TIMEOUT_SECONDS: Final[float] = 30.0

# 配置文件名称：1-64 个字符，必须以字母数字开头，然后是字母数字或“.”、“_”、“-”。 阻止空
# 名称、路径分隔符、前导点（隐藏文件/路径遍历）和 shell 特殊字符。 等同于
# ``LLMProfileStore.PROFILE_NAME_PATTERN``，因此两个存储共享命名合同（
# ``llm_profile_ref`` 是 LLM 存储密钥）。
#
PROFILE_NAME_PATTERN: Final[str] = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
PROFILE_NAME_REGEX: Final[re.Pattern[str]] = re.compile(PROFILE_NAME_PATTERN)

logger = get_logger(__name__)


def canonical_profile_name(name: str) -> str:
    """返回 ``name`` 的存储密钥：删除尾随的 ``.json``。

    文件存储通过其文件主干来键入配置文件，因此 ``x.json`` 和 ``x`` 命名相同的配置文件
    。
    """
    return name.removesuffix(".json")


class ProfileLimitExceeded(Exception):
    """当保存超出配置的配置文件限制时引发。"""


class AgentProfileStore:
    """用于持久保存 ``AgentProfile`` 启动规范的独立实用程序。

    `~openhands.sdk.llm.llm_profile_store.LLMProfileStore`：镜像：JSON个文件，每个文
    件位于
    ``~/.openhands/agent-profiles``，文件名是（可重命名的）``name``，稳定``id``（uuid
    ）位于文件中。 REST，该配置项
    机密无冗余，每个字段都是引用（``llm_profile_ref``、``mcp_server_refs``），黑名单
    （``disabled_skills``），或
    纯值，因此无需对持久化或加载它（#4017）。
    """

    def __init__(self, base_dir: Path | str | None = None) -> None:
        """初始化配置文件存储。

        Args:
            base_dir: 存储配置文件的目录。 ``None`` 使用
                默认 ``~/.openhands/agent-profiles``。
        """
        self.base_dir = Path(base_dir) if base_dir is not None else _DEFAULT_PROFILE_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._file_lock = FileLock(self.base_dir / ".agent-profiles.lock")

    @contextmanager
    def _acquire_lock(self, timeout: float = _LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
        """获取存储文件锁以进行安全并发访问。

        ``filelock.FileLock`` 在线程内是可重入的，因此 FK 助手可以将其嵌套在每个方法
        调用周围，而不会出现死锁。
        """
        try:
            with self._file_lock.acquire(timeout=timeout):
                yield
        except Timeout:
            logger.error(f"[AgentProfile Store] Failed to acquire lock in {timeout}s")
            raise TimeoutError(
                f"Agent profile store lock acquisition timed out after {timeout}s"
            )

    def lock(
        self, timeout: float = _LOCK_TIMEOUT_SECONDS
    ) -> AbstractContextManager[None]:
        """FK 助手 (``profile_refs``) 的公共可重入存储锁。

        可重入，因为 ``filelock.FileLock`` 计算每个线程的获取，因此持有者可以嵌套它 (
        e.g.
        ``save_profile_preserving_identity`` 结束
        ``save``). :class:`AgentProfileStoreProtocol` 的一部分，因此是一个非文件存储
        (e.g. 由数据库支持的云存储
        ）可以以相同的名称提供自己的可重入事务保护。 代表：meth:`_acquire_lock`。
        """
        return self._acquire_lock(timeout)

    def list(self) -> list[str]:
        """返回所有存储的配置文件的文件名 (e.g. ``["a.json"]``)."""
        with self._acquire_lock():
            return [p.name for p in self.base_dir.glob("*.json")]

    def _get_profile_path(self, name: str) -> Path:
        """将配置文件名称解析为其文件路径，并验证该名称。

        Raises:
            ValueError: 如果 ``name`` 与 ``PROFILE_NAME_PATTERN`` 不匹配。
        """
        clean_name = canonical_profile_name(name)
        if not PROFILE_NAME_REGEX.match(clean_name):
            raise ValueError(
                f"Invalid profile name: {name!r}. "
                "Profile names must be 1-64 characters, start with a letter "
                "or digit, and contain only letters, digits, '.', '_', or '-'."
            )
        return self.base_dir / f"{clean_name}.json"

    def _atomic_write(self, path: Path, text: str) -> None:
        """通过临时文件 + 原子 ``Path.replace`` 将 ``text`` 写入 ``path``。

        呼叫者必须按住：meth:`_acquire_lock`。 与 ``profile_refs`` 共享，因此级联重写
        重用相同的崩溃安全写入。
        """
        with tempfile.NamedTemporaryFile(
            mode="w", dir=self.base_dir, suffix=".tmp", delete=False
        ) as tmp:
            tmp.write(text)
            tmp_path = Path(tmp.name)
        try:
            Path.replace(tmp_path, path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def save(
        self,
        profile: OpenHandsAgentProfile | ACPAgentProfile,
        *,
        max_profiles: int | None = None,
    ) -> None:
        """将配置文件保存在其自己的 ``name`` 下，覆盖任何同名配置文件。

        该配置文件在 REST 处是机密自由的，因此它以明文形式转储，无需密码/加密。 当设
        置``max_profiles``时，创建一个
        *超出上限的新*配置文件在上限下提高了``ProfileLimitExceeded``
        与写入相同的锁。

        Raises:
            ValueError: 如果 ``profile.name`` 不是有效的配置文件名称。
            ProfileLimitExceeded: 如果超过``max_profiles``。
            TimeoutError: 如果无法获取锁。
        """
        profile_path = self._get_profile_path(profile.name)
        payload = profile.model_dump(mode="json")
        # 保持存储的名称等于文件主干（如 ``rename`` 所做的那样），因此
        # ``x.json`` 和 ``x`` 是一个具有同一个名称的配置文件。
        payload["name"] = profile_path.stem

        with self._acquire_lock():
            if max_profiles is not None and not profile_path.exists():
                count = sum(
                    1
                    for p in self.base_dir.glob("*.json")
                    if PROFILE_NAME_REGEX.match(p.stem)
                )
                if count >= max_profiles:
                    raise ProfileLimitExceeded(
                        f"Profile limit reached ({max_profiles})."
                    )

            if profile_path.exists():
                logger.info(
                    f"[AgentProfile Store] Overwriting profile `{profile.name}`."
                )

            self._atomic_write(profile_path, json.dumps(payload, indent=2))
            logger.info(
                f"[AgentProfile Store] Saved profile `{profile.name}` at {profile_path}"
            )

    def load(
        self,
        name: str,
    ) -> OpenHandsAgentProfile | ACPAgentProfile:
        """加载并验证存储在 ``name`` 下的配置文件。

        所有字段都是引用或纯值，因此加载字段不需要密码。

        Raises:
            FileNotFoundError: 如果``name``不存在。
            ValueError: 如果文件损坏或失败验证。
            TimeoutError: 如果无法获取锁。
        """
        profile_path = self._get_profile_path(name)

        with self._acquire_lock():
            if not profile_path.exists():
                existing = [p.name for p in self.base_dir.glob("*.json")]
                raise FileNotFoundError(
                    f"Profile `{name}` not found. "
                    f"Available profiles: {', '.join(existing) or 'none'}"
                )

            try:
                data = json.loads(profile_path.read_text())
                profile = validate_agent_profile(data)
            except Exception as e:
                raise ValueError(f"Failed to load profile `{name}`: {e}") from e

            logger.info(
                f"[AgentProfile Store] Loaded profile `{name}` from {profile_path}"
            )
            return profile

    def delete(self, name: str) -> None:
        """删除配置文件，如果不存在则不执行任何操作。

        Raises:
            TimeoutError: 如果无法获取锁。
        """
        profile_path = self._get_profile_path(name)

        with self._acquire_lock():
            if not profile_path.exists():
                logger.info(
                    f"[AgentProfile Store] Profile `{name}` not found. Skipping."
                )
                return
            profile_path.unlink()
            logger.info(f"[AgentProfile Store] Deleted profile `{name}`")

    def rename(self, old_name: str, new_name: str) -> None:
        """以原子方式重命名配置文件，将文件内 ``name`` 保留在同步中。

        与裸文件移动不同，这还会重写已持久化 ``name`` 字段（外科手术原始 JSON 编辑）
        。 稳定的``id``被保留。

        Raises:
            FileNotFoundError: 如果缺少 ``old_name``。
            FileExistsError: 如果取``new_name``。
            ValueError: 如果其中一个名称无效。
        """
        old_path = self._get_profile_path(old_name)
        new_path = self._get_profile_path(new_name)
        new_stem = new_path.stem

        with self._acquire_lock():
            if not old_path.exists():
                raise FileNotFoundError(f"Profile `{old_name}` not found")
            if old_path == new_path:
                return
            if new_path.exists():
                raise FileExistsError(f"Profile `{new_name}` already exists")

            data = json.loads(old_path.read_text())
            if isinstance(data, dict):
                data["name"] = new_stem
            self._atomic_write(new_path, json.dumps(data, indent=2))
            old_path.unlink()
            logger.info(
                f"[AgentProfile Store] Renamed profile `{old_name}` to `{new_name}`"
            )

    def set_llm_profile_ref(self, name: str, new_ref: str) -> None:
        """通过手术重新指向一个 OpenHands 轮廓的 ``llm_profile_ref``。

        ``profile_refs.cascade_rename``后面的单配置文件写入原语。 自锁（可重入），因
        此无论是独立调用还是嵌套在 FK 助手的：met
        h:`lock` 下，读取-修改-写入都是原子的。 原始 JSON 编辑（仅 ref 字段发生变化）
        ，因此稳定的 ``id`` 未受影响。 当配置文件丢失、
        非字典或 ACP 配置文件（不携带引用）时，无操作。
        """
        path = self._get_profile_path(name)
        with self._acquire_lock():
            if not path.exists():
                return
            try:
                data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                return
            if not isinstance(data, dict):
                return
            if data.get("agent_kind", "openhands") != "openhands":
                return
            data["llm_profile_ref"] = new_ref
            self._atomic_write(path, json.dumps(data, indent=2))

    def list_summaries(self) -> list[dict[str, Any]]:
        """无需实例化的项目配置文件元数据机密。

        直接读取JSON并返回
        每个配置文件
        ``{id, name, agent_kind, revision, llm_profile_ref, mcp_server_refs}``（
        对于 ACP 个配置文件，``llm_profile_ref`` 是 ``None``）。 具有无效名称、损坏的
         JSON 或非字典顶级值的文件将被跳过并显
        示警告。
        """
        summaries: list[dict[str, Any]] = []
        with self._acquire_lock():
            for path in sorted(self.base_dir.glob("*.json")):
                name = path.stem
                if not PROFILE_NAME_REGEX.match(name):
                    logger.warning(
                        f"[AgentProfile Store] Skipping invalid name {name!r}"
                    )
                    continue
                try:
                    data = json.loads(path.read_text())
                except (OSError, json.JSONDecodeError) as e:
                    logger.warning(
                        f"[AgentProfile Store] Skipping corrupted profile {name!r}: {e}"
                    )
                    continue
                if not isinstance(data, dict):
                    logger.warning(
                        f"[AgentProfile Store] Skipping non-dict profile {name!r}"
                    )
                    continue
                agent_kind = data.get("agent_kind", "openhands")
                summaries.append(
                    {
                        "id": data.get("id"),
                        "name": name,
                        "agent_kind": agent_kind,
                        "revision": data.get("revision"),
                        "llm_profile_ref": (
                            data.get("llm_profile_ref")
                            if agent_kind == "openhands"
                            else None
                        ),
                        "mcp_server_refs": data.get("mcp_server_refs"),
                    }
                )
        return summaries

    def name_for_id(self, profile_id: str | UUID) -> str | None:
        """返回稳定配置文件 ID 的存储名称，如果未找到，则返回 ``None``。

        扫描锁下的 ``list_summaries()``，以便查找与调用时的磁盘状态一致。 镜像过去由
        每个调用者开放编码的 id→name 解析。
        """
        target = str(profile_id)
        for summary in self.list_summaries():
            if str(summary.get("id")) == target:
                return str(summary["name"])
        return None


@runtime_checkable
class AgentProfileStoreProtocol(Protocol):
    """:class:`AgentProfileStore` 和任何替代方案共享的结构契约
    后端（e.g. 多租户云数据库存储）。

    与商店无关的助手（``profile_refs``，
    :func:`save_profile_preserving_identity`) 是根据此协议键入的。
    :meth:`lock` 必须是 ** 可重入 **：FK 助手将其嵌套在周围
    ：甲基：`list_summaries` / ：甲基：`set_llm_profile_ref`。
    """

    def lock(self, timeout: float = ...) -> AbstractContextManager[None]: ...

    def list(self) -> list[str]: ...

    def list_summaries(self) -> list[dict[str, Any]]: ...

    def save(
        self,
        profile: OpenHandsAgentProfile | ACPAgentProfile,
        *,
        max_profiles: int | None = ...,
    ) -> None: ...

    def load(self, name: str) -> OpenHandsAgentProfile | ACPAgentProfile: ...

    def delete(self, name: str) -> None: ...

    def rename(self, old_name: str, new_name: str) -> None: ...

    def set_llm_profile_ref(self, name: str, new_ref: str) -> None: ...

    def name_for_id(self, profile_id: str | UUID) -> str | None: ...


def _existing_identity(
    store: AgentProfileStoreProtocol, name: str
) -> tuple[UUID | None, int | None]:
    """返回 ``name`` 下配置文件的存储 ``(id, revision)``。

    读取：meth:`~AgentProfileStoreProtocol.list_summaries` （无机密实例化）。 格式错
    误的存储 ID 将被视为“无先前身
    份”。
    """
    for summary in store.list_summaries():
        if summary.get("name") != name:
            continue
        sid = summary.get("id")
        rev = summary.get("revision")
        try:
            parsed = UUID(str(sid)) if sid is not None else None
        except (ValueError, TypeError):
            parsed = None
        return parsed, rev if isinstance(rev, int) else None
    return None, None


def save_profile_preserving_identity(
    store: AgentProfileStoreProtocol,
    profile: OpenHandsAgentProfile | ACPAgentProfile,
    *,
    max_profiles: int | None = None,
) -> OpenHandsAgentProfile | ACPAgentProfile:
    """使用服务器管理的 ID/修订策略保存 ``profile``。

    * **覆盖**同名→保持其稳定``id``，``revision = prev + 1``；
    * **创建**→创建一个新的``uuid4``（忽略任何客户端提供的ID）。

    在：meth:`~AgentProfileStoreProtocol.lock` 下运行，因此并发创建的同名不能既创建
    id 又互相破坏。 返回保存的配置文件。

    Raises:
        ProfileLimitExceeded: 如果超过``max_profiles``。
    """
    name = canonical_profile_name(profile.name)
    if name != profile.name:
        profile = profile.model_copy(update={"name": name})
    with store.lock():
        existing_id, existing_rev = _existing_identity(store, profile.name)
        if existing_id is not None:
            profile = profile.model_copy(
                update={"id": existing_id, "revision": (existing_rev or 0) + 1}
            )
        else:
            profile = profile.model_copy(update={"id": uuid4()})
        store.save(profile, max_profiles=max_profiles)
    return profile
