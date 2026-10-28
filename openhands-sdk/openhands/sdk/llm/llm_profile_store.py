# 必需：``LLMProfileStore.list()`` 隐藏类主体中的内置函数，
# 因此像 ``list[dict[str, Any]]`` 这样的注释将在没有延迟的情况下失败。
from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable

from filelock import FileLock, Timeout

from openhands.sdk.llm.utils.openhands_provider import (
    canonicalize_openhands_llm_payload,
)
from openhands.sdk.logger import get_logger
from openhands.sdk.utils.path import get_user_persistence_dir
from openhands.sdk.utils.pydantic_secrets import REDACTED_SECRET_VALUE


if TYPE_CHECKING:
    from openhands.sdk.llm.llm import LLM
    from openhands.sdk.llm.provider_connection_store import ProviderConnectionStore
    from openhands.sdk.utils.cipher import Cipher

_DEFAULT_PROFILE_DIR: Final[Path] = get_user_persistence_dir() / "profiles"
_LOCK_TIMEOUT_SECONDS: Final[float] = 30.0

# 配置文件名称：1-64 个字符，必须以字母数字开头，然后是字母数字或“.”、“_”、“-”。 阻止空
# 名称、路径分隔符、前导点（隐藏文件/路径遍历）和 shell 特殊字符。
#
PROFILE_NAME_PATTERN: Final[str] = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
PROFILE_NAME_REGEX: Final[re.Pattern[str]] = re.compile(PROFILE_NAME_PATTERN)


def canonical_profile_name(name: str) -> str:
    """返回存储密钥 ``name`` 地址：``foo.json`` 是配置文件 ``foo``。"""
    return name.removesuffix(".json")


logger = get_logger(__name__)


class ProfileLimitExceeded(Exception):
    """当保存超出配置的配置文件限制时引发。"""


def _api_key_present(llm: LLM) -> bool:
    """True 当 ``llm`` 携带非空、非已脱敏 API 键时。"""
    from pydantic import SecretStr

    api_key = llm.api_key
    if api_key is None:
        return False
    value = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
    return bool(value.strip()) and value != REDACTED_SECRET_VALUE


@runtime_checkable
class LLMProfileLoader(Protocol):
    """``resolve_agent_profile`` 消耗的最小仅加载合约。

    解析器仅通过 ``load`` 按名称读取 LLM 配置文件，因此有一个备用后端 - e.g。
    ``org.llm_profiles`` 列上的云适配器 — 需要实
    现这个，而不是完整的文件支持：class:`LLMProfileStore`。
    """

    def load(self, name: str, *, cipher: Cipher | None = ...) -> LLM: ...


@runtime_checkable
class LLMProfileMutator(Protocol):
    """删除/重命名跨商店 FK 助手使用的合约。

    ``profile_refs.delete_llm_profile``
    /``rename_llm_profile``仅通过``delete``/``rename``触摸LLM存储，因此云适配器结束
    ``org.llm_profiles`` 可以驱动相同的受保护的 FK 生命周期，而无需成为完整的：class:
    `LLMProfileStore`。
    """

    def delete(self, name: str) -> None: ...

    def rename(self, old_name: str, new_name: str) -> None: ...


class LLMProfileStore:
    """用于持久保存 LLM 配置的独立实用程序。"""

    def __init__(
        self,
        base_dir: Path | str | None = None,
        *,
        provider_store: ProviderConnectionStore | None = None,
    ) -> None:
        """初始化配置文件存储。

        Args:
            base_dir: 存储配置文件的目录的路径。
                如果提供 `None`，则使用默认目录 i.e。，
                `~/.openhands/profiles`.
            provider_store: 共享提供者连接的存储用于
                在加载时解析配置文件的 ``provider_connection_id``。 当 `None`（默认）
                时，会在
                ``provider-connections`` 目录 * 的同级目录 * 中创建：class:
                `ProviderConnectionStore`
                ``base_dir`` 以便于每个 ``LLMProfileStore`` 包括自定义目录和裸机独立
                SDK 实例 — 从读取配置文件的同
                一位置解析连接。 传递一个明确的存储来使用一个无关的目录e.g. 的智能体
                服务器的配置范围目录，或者测试双。
        """
        self.base_dir = Path(base_dir) if base_dir is not None else _DEFAULT_PROFILE_DIR
        # 确保目录存在
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._file_lock = FileLock(self.base_dir / ".profiles.lock")
        if provider_store is None:
            from openhands.sdk.llm.provider_connection_store import (
                ProviderConnectionStore,
            )

            # 从 base_dir 而不是 $HOME 派生连接目录，因此自定义目录配置文件存储读取其链
            # 接的凭据
            #
            # from the same location it reads profiles from. For the default
            # ~/.openhands/profiles 这解析为 ~/.openhands/provider- 连接，匹配
            # ProviderConnectionStore 自己的默认值。
            #
            self._provider_store: ProviderConnectionStore | None = (
                ProviderConnectionStore(
                    base_dir=self.base_dir.parent / "provider-connections"
                )
            )
        else:
            self._provider_store = provider_store

    @contextmanager
    def _acquire_lock(self, timeout: float = _LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
        """获取文件锁以进行安全并发访问。

        Args:
            timeout: 等待锁采集的最长时间（以秒为单位）。

        Raises:
            TimeoutError: 如果在超时内无法获取锁。
        """
        try:
            with self._file_lock.acquire(timeout=timeout):
                yield
        except Timeout:
            logger.error(f"[Profile Store] Failed to acquire lock within {timeout}s")
            raise TimeoutError(
                f"Profile store lock acquisition timed out after {timeout}s"
            )

    def list(self) -> list[str]:
        """返回存储的所有配置文件的列表。

        Returns:
            配置文件名列表（e.g.、[“default.json”、“gpt4.json”]）。
        """
        with self._acquire_lock():
            return [p.name for p in self.base_dir.glob("*.json")]

    def _get_profile_path(self, name: str) -> Path:
        """获取配置文件名称的完整路径。

        Args:
            name: 配置文件名称（必须匹配 ``PROFILE_NAME_PATTERN``）。

        Raises:
            ValueError: 如果名称与允许的模式不匹配。
        """
        clean_name = canonical_profile_name(name)
        if not PROFILE_NAME_REGEX.match(clean_name):
            raise ValueError(
                f"Invalid profile name: {name!r}. "
                "Profile names must be 1-64 characters, start with a letter "
                "or digit, and contain only letters, digits, '.', '_', or '-'."
            )
        return self.base_dir / f"{clean_name}.json"

    def save(
        self,
        name: str,
        llm: LLM,
        include_secrets: bool = False,
        *,
        cipher: Cipher | None = None,
        max_profiles: int | None = None,
    ) -> None:
        """将配置文件保存到配置文件目录。

        覆盖同名的现有配置文件。 设置 ``max_profiles`` 后，如果创建 * 新 * 配置文件会
        超出限制，则引发
        ``ProfileLimitExceeded``。 检查发生在与保存相同的锁下，因此在此过程中与其他
        ``save`` 调用不存在竞争。

        Args:
            name: 要保存的配置文件的名称。
            llm: LLM 要保存的实例
            include_secrets: 是否包含配置文件机密。 默认为 False。
            cipher: 用于机密的 at-REST 加密的可选密码。
                如果提供，机密在写入磁盘之前会被加密。
            max_profiles: 配置文件数量的可选上限。

        Raises:
            ProfileLimitExceeded: 如果超过``max_profiles``。
            TimeoutError: 如果无法获取锁。
        """
        profile_path = self._get_profile_path(name)

        with self._acquire_lock():
            if max_profiles is not None and not profile_path.exists():
                # 仅计算通过 list_summaries（有效名称）可见的文件，因此杂散的无效文件不
                # 会占用插槽。
                #
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
                    f"[Profile Store] Profile `{name}` already exists. Overwriting."
                )

            # 规则5c：引用提供商连接的配置文件没有凭据 — 连接是唯一的真实来源，因此在持
            # 久化之前清除 api_key / base_url 以避免一个可能后来与连接不一致的过时副本。
            #
            if llm.provider_connection_id:
                llm = llm.model_copy(update={"api_key": None, "base_url": None})

            context: dict[str, Any] = {}
            if include_secrets:
                if cipher:
                    context["cipher"] = cipher
                    context["expose_secrets"] = "encrypted"
                else:
                    context["expose_secrets"] = True

            profile_json = json.dumps(llm.to_persisted(context=context), indent=2)
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.base_dir, suffix=".tmp", delete=False
            ) as tmp:
                tmp.write(profile_json)
                tmp_path = Path(tmp.name)

            try:
                Path.replace(tmp_path, profile_path)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
            logger.info(f"[Profile Store] Saved profile `{name}` at {profile_path}")

    def load(
        self,
        name: str,
        *,
        cipher: Cipher | None = None,
        resolve_provider: bool = True,
    ) -> LLM:
        """从给定的配置文件名称加载 LLM 实例。

        Args:
            name: 要加载的配置文件的名称。
            cipher: 用于解密存储在 REST 中的机密的可选密码。
                如果提供，加密的机密将在加载期间解密。
            resolve_provider: 当 True（默认）且配置文件引用
                提供者连接，其共享的 ``api_key`` / ``base_url`` 应用于返回的 LLM （使
                用时读取）。 设置 False 以检查
                存储的配置文件，而无需触摸提供程序存储 - 由显示路径使用，因此悬空引用
                永远不会失败读取。

        Returns:
            根据配置文件配置构造的 LLM 实例，在 ``resolve_provider`` 时应用提供者连接
            凭据。

        Raises:
            FileNotFoundError: 如果配置文件名称不存在。
            ValueError: 如果配置文件已损坏或无效。
            ProviderConnectionNotFound: 如果配置文件引用了提供商
                连接不再存在并且不带有内联键。
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
                from openhands.sdk.llm.llm import LLM

                context: dict[str, Any] | None = {"cipher": cipher} if cipher else None

                llm_instance = LLM.load_from_json(str(profile_path), context=context)
            except Exception as e:
                # 重新加注为 ValueError 以进行更清晰的错误处理
                raise ValueError(f"Failed to load profile `{name}`: {e}") from e

            logger.info(f"[Profile Store] Loaded profile `{name}` from {profile_path}")

        if resolve_provider:
            llm_instance = self._resolve_provider_connection(
                name, llm_instance, cipher=cipher
            )
        return llm_instance

    def resolve_provider_connection(
        self, llm: LLM, *, cipher: Cipher | None = None
    ) -> LLM:
        """应用引用的提供者连接的凭据到 ``llm``。

        共享入口用于读取时的解决方法：[方法名]`load` 在用户加载时适用。 安装了用户提
        供的的呼叫方 LLM (e.g. 的 ``/switch_llm``
         端点，接收前端转发的配置，使用这个，以便关联到提供商连接的配置运行于连接上
         ``api_key`` / ``base_url`` 而不是一个无密钥的配置。
         ``profile_name`` 这里未知，因此错误消息直接引用连接标识。

        解析规则请参见：meth:`_resolve_provider_connection`。
        """
        return self._resolve_provider_connection(None, llm, cipher=cipher)

    def _resolve_provider_connection(
        self, profile_name: str | None, llm: LLM, *, cipher: Cipher | None
    ) -> LLM:
        """应用引用的提供者连接的凭据到 ``llm``。

        规则：
        - no ``provider_connection_id`` -> 不变（字节相同的旧路径）。
        - 未配置提供程序存储 -> 未更改（惰性字段）。
        - 找到连接 -> 其 ``api_key`` / ``base_url`` 获胜（``base_url`` 按原样应用，包
        括 ``None``）。
        - 连接丢失 -> raise :class:`ProviderConnectionNotFound`。

        以下的嵌入密钥回退方案并不是常规“关联的凭据，稍后删除”的恢复路径：：meth:
        `save` 会从任何关联的凭据中剥离嵌入密钥，因此在磁盘上没有嵌入密钥可以
        回退，这会引发。 它仅适用于 LLM，其
        ``provider_connection_id`` 是在没有经过：meth:`save` (e.g. 在内存中构建）。
        """
        connection_id = llm.provider_connection_id
        if not connection_id or self._provider_store is None:
            return llm

        from openhands.sdk.llm.provider_connection_store import (
            ProviderConnectionNotFound,
        )

        connection = self._provider_store.get(connection_id, cipher=cipher)
        if connection is None:
            if _api_key_present(llm):
                logger.warning(
                    "[Profile Store] Profile %r references missing provider "
                    "connection %r; falling back to the profile's inline key.",
                    profile_name,
                    connection_id,
                )
                return llm
            owner = (
                f"Profile {profile_name!r}"
                if profile_name is not None
                else "LLM config"
            )
            raise ProviderConnectionNotFound(
                f"{owner} references provider connection "
                f"{connection_id!r}, which does not exist. Update the profile or "
                "recreate the connection."
            )

        updates: dict[str, Any] = {"base_url": connection.base_url}
        api_key = connection.api_key_value()
        if api_key is not None:
            from pydantic import SecretStr

            updates["api_key"] = SecretStr(api_key)
        return llm.model_copy(update=updates)

    def delete(self, name: str) -> None:
        """删除现有的配置文件。

        如果配置文件不存在于配置文件目录中，则它不会执行任何操作。

        Args:
            name: 要删除的配置文件的名称。

        Raises:
            TimeoutError: 如果无法获取锁。
        """
        profile_path = self._get_profile_path(name)

        with self._acquire_lock():
            if not profile_path.exists():
                logger.info(f"[Profile Store] Profile `{name}` not found. Skipping.")
                return

            profile_path.unlink()
            logger.info(f"[Profile Store] Deleted profile `{name}`")

    def rename(self, old_name: str, new_name: str) -> None:
        """原子地重命名配置文件。

        如果缺少 ``old_name``，则提高 FileNotFoundError；如果采用 ``new_name``，则提
        高 FileExistsError。
         当名称解析为相同路径时，调用是无操作，但仍验证配置文件是否存在。
        """
        old_path = self._get_profile_path(old_name)
        new_path = self._get_profile_path(new_name)

        with self._acquire_lock():
            if not old_path.exists():
                raise FileNotFoundError(f"Profile `{old_name}` not found")
            if old_path == new_path:
                return
            if new_path.exists():
                raise FileExistsError(f"Profile `{new_name}` already exists")
            old_path.rename(new_path)
            logger.info(f"[Profile Store] Renamed profile `{old_name}` to `{new_name}`")

    def list_summaries(self) -> list[dict[str, Any]]:
        """列出配置文件元数据而不实例化 LLM 对象。

        直接读取JSON以避免``LLM._set_env_side_effects``变异
        ``os.environ``. 具有无效名称、损坏的 JSON 或非字典顶级值的文件将被跳过并显示
        警告。

        在读取一个链接的提供者连接的密钥存在时，没有使用密码：此方法只报告密钥是否设
        置，而从未报告其明文，因此，一个加密在REST的密钥仍然显示为存在。
        """
        summaries: list[dict[str, Any]] = []
        with self._acquire_lock():
            for path in sorted(self.base_dir.glob("*.json")):
                name = path.stem
                if not PROFILE_NAME_REGEX.match(name):
                    logger.warning(
                        f"[Profile Store] Skipping profile with invalid name {name!r}"
                    )
                    continue
                try:
                    data = json.loads(path.read_text())
                except (OSError, json.JSONDecodeError) as e:
                    logger.warning(
                        f"[Profile Store] Skipping corrupted profile {name!r}: {e}"
                    )
                    continue
                if not isinstance(data, dict):
                    logger.warning(
                        f"[Profile Store] Skipping non-dict profile {name!r}"
                    )
                    continue
                data = canonicalize_openhands_llm_payload(data)
                api_key = data.get("api_key")
                api_key_set = (
                    isinstance(api_key, str)
                    and bool(api_key.strip())
                    and api_key != REDACTED_SECRET_VALUE
                )
                connection_id = data.get("provider_connection_id")
                # 链接到提供商连接的配置文件不携带内联密钥（保存时清除），因此其有效密钥
                # 存在于连接上。
                #
                provider_connection_broken = False
                if isinstance(connection_id, str) and self._provider_store is not None:
                    connection = self._provider_store.get(connection_id)
                    if connection is None:
                        provider_connection_broken = True
                    elif not api_key_set:
                        api_key_set = connection.api_key_value() is not None
                summaries.append(
                    {
                        "name": name,
                        "model": data.get("model"),
                        "base_url": data.get("base_url"),
                        "provider_connection_id": connection_id,
                        "provider_connection_broken": provider_connection_broken,
                        "api_key_set": api_key_set,
                    }
                )
        return summaries
