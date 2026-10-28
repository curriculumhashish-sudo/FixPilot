"""JSON-元配置文件的文件存储。

不变量键：元架构中的每个模型引用（``classifier_model``，每个类的``model``，以及直接路
由的提示词输出）都是一个保存的LLM架构*的*名称
:class:`~openhands.sdk.llm.llm_profile_store.LLMProfileStore`，不是原始模型
字符串 — 凭据/提供程序设置通过该存储解析。
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final

from filelock import FileLock, Timeout
from pydantic import BaseModel, Field, model_validator

from openhands.sdk.llm.llm_profile_store import PROFILE_NAME_REGEX
from openhands.sdk.logger import get_logger
from openhands.sdk.utils.path import get_user_persistence_dir


_LOCK_TIMEOUT_SECONDS: Final[float] = 30.0

logger = get_logger(__name__)


def default_meta_profile_dir() -> Path:
    """返回元配置文件存储的默认目录。

    智能体-服务器实例可以设置``OH_PERSISTENCE_DIR``以隔离所有已持久化状态。 对于裸
    ``MetaProfileStore()`` 实例，请遵守这
    一点，以便运行时工具读取 HTTP API 公开的相同元配置文件。 如果没有该环境变量，请将
    独立的 SDK 默认值保留在 ``~/.openhands`` 下。 在
    调用时通过 ``get_user_persistence_dir`` 解决，因此 ``~`` 和相对值落在其他商店放置
    文件的位置。
    """
    return get_user_persistence_dir() / "meta-profiles"


class MetaProfileLimitExceeded(Exception):
    """当保存超出配置的元配置文件限制时引发。"""


class MetaProfileClass(BaseModel):
    """单个任务类别和应处理该任务的 LLM 配置文件。"""

    description: str = Field(
        description="Natural-language description of the kind of task this "
        "class covers (e.g. 'task is UI oriented or requires looking at images')."
    )
    model: str = Field(
        description="Name of the saved LLM profile to switch to for tasks "
        "matching this class."
    )


class MetaProfile(BaseModel):
    """声明性模型路由配置。"""

    classifier_model: str = Field(
        description="Name of the saved LLM profile used to classify the task."
    )
    classes: list[MetaProfileClass] = Field(
        default_factory=list,
        description="Ordered list of task classes and their target profiles.",
    )
    prompt_template: str | None = Field(
        default=None,
        description=(
            "Optional direct-routing prompt template. When set, the classifier "
            "receives this rendered prompt and should return JSON with a "
            "`model` field instead of a class number."
        ),
    )
    model_table: str | None = Field(
        default=None,
        description=(
            "Optional text inserted into `{{ model_table }}` for direct-routing "
            "prompts."
        ),
    )

    @model_validator(mode="after")
    def validate_routing_mode(self) -> MetaProfile:
        """验证直接提示词模式：模板需要``{{ instance_text }}``
        并排除类。

        这里接受既没有类也没有模板的元配置文件，因此已持久化仍然会加载；
        ``POST /api/meta-profiles/{name}`` 拒绝。
        """
        if self.prompt_template is None:
            return self
        if re.search(r"{{\s*instance_text\s*}}", self.prompt_template) is None:
            raise ValueError(
                "Direct-routing meta-profiles must include {{ instance_text }} "
                "in prompt_template."
            )
        if self.classes:
            raise ValueError("Direct-routing meta-profiles cannot also define classes.")
        return self


class MetaProfileStore:
    """从默认元配置文件目录读取元配置文件。"""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        """初始化元配置文件存储。

        Args:
            base_dir: 存储元配置文件的目录。 默认为
                设置时为 ``$OH_PERSISTENCE_DIR/meta-profiles``，否则
                ``~/.openhands/meta-profiles``.
        """
        self.base_dir = (
            Path(base_dir) if base_dir is not None else default_meta_profile_dir()
        )
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._file_lock = FileLock(self.base_dir / ".meta-profiles.lock")

    @contextmanager
    def _acquire_lock(self, timeout: float = _LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
        """获取文件锁以进行安全并发访问。

        锁是进程内的可重入，因此持有它的方法可能会调用其他锁定的方法 (e.g. ``save``
        调用 ``list``）。

        Raises:
            TimeoutError: 如果在``timeout``内无法获取锁。
        """
        try:
            with self._file_lock.acquire(timeout=timeout):
                yield
        except Timeout:
            logger.error(
                f"[Meta-profile Store] Failed to acquire lock within {timeout}s"
            )
            raise TimeoutError(
                f"Meta-profile store lock acquisition timed out after {timeout}s"
            )

    def list(self) -> list[str]:
        """返回存储的元配置文件名称（不带 ``.json``），已排序。

        顺序是按字母顺序排列，而不是按时间顺序排列。 当时，调用者会 fallback 到第一个
        可用的元配置 None 如果明确激活，则获取字母顺序最小的姓名，该姓
        名是稳定的，但不是“最近的”。
        """
        return sorted(
            p.stem
            for p in self.base_dir.glob("*.json")
            if PROFILE_NAME_REGEX.match(p.stem)
        )

    def _get_path(self, name: str) -> Path:
        clean_name = name.removesuffix(".json")
        if not PROFILE_NAME_REGEX.match(clean_name):
            raise ValueError(
                f"Invalid meta-profile name: {name!r}. "
                "Names must be 1-64 characters, start with a letter or digit, "
                "and contain only letters, digits, '.', '_', or '-'."
            )
        return self.base_dir / f"{clean_name}.json"

    def load(self, name: str) -> MetaProfile:
        """按名称加载元配置文件。

        Raises:
            FileNotFoundError: 如果元配置文件不存在。
            ValueError: 如果文件损坏或失败验证。
        """
        path = self._get_path(name)
        if not path.exists():
            existing = self.list()
            raise FileNotFoundError(
                f"Meta-profile `{name}` not found. "
                f"Available meta-profiles: {', '.join(existing) or 'none'}"
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return MetaProfile.model_validate(data)
        except Exception as e:
            raise ValueError(f"Failed to load meta-profile `{name}`: {e}") from e

    def save(
        self,
        name: str,
        meta_profile: MetaProfile,
        *,
        max_profiles: int | None = None,
    ) -> None:
        """持久化 ``name`` 下的元配置文件（原子写入、覆盖）。

        Args:
            name: 要保存的元配置文件的名称。
            meta_profile: 元配置文件为持久化。
            max_profiles: 元配置文件数量的可选上限。 设置后，
                如果创建 *new* 元配置文件超出限制，则会引发：class:
                `MetaProfileLimitExceeded`。

        Raises:
            MetaProfileLimitExceeded: 如果超过``max_profiles``。
            ValueError: 如果 ``name`` 不是有效的元配置文件名称。
        """
        path = self._get_path(name)

        # 在前提条件检查和原子替换中保持锁，这样并发创建者就不能同时通过限制检查和超调
        # ``max_profiles`` (TOCTOU)，镜像 ``LLMProfileStore``。
        with self._acquire_lock():
            if max_profiles is not None and not path.exists():
                if len(self.list()) >= max_profiles:
                    raise MetaProfileLimitExceeded(
                        f"Meta-profile limit reached ({max_profiles})."
                    )

            profile_json = json.dumps(meta_profile.model_dump(mode="json"), indent=2)
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=self.base_dir,
                suffix=".tmp",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                tmp.write(profile_json)
                tmp_path = Path(tmp.name)

            try:
                Path.replace(tmp_path, path)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
        logger.info(f"Saved meta-profile `{name}` at {path}")

    def delete(self, name: str) -> None:
        """删除元配置文件（幂等 - 缺少名称是不可操作的）。

        Raises:
            ValueError: 如果 ``name`` 不是有效的元配置文件名称。
        """
        path = self._get_path(name)
        with self._acquire_lock():
            if not path.exists():
                logger.info(f"Meta-profile `{name}` not found. Skipping delete.")
                return
            path.unlink()
        logger.info(f"Deleted meta-profile `{name}`")

    def list_summaries(self) -> list[dict[str, Any]]:
        """列出不完整的元配置文件元数据模式验证。

        具有损坏的 JSON 或非字典顶级值的文件将被跳过并发出警告，因此单个错误文件永远
        不会破坏列表。
        """
        summaries: list[dict[str, Any]] = []
        for name in self.list():
            try:
                data = json.loads(self._get_path(name).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Skipping corrupted meta-profile {name!r}: {e}")
                continue
            if not isinstance(data, dict):
                logger.warning(f"Skipping non-dict meta-profile {name!r}")
                continue
            classes = data.get("classes") or []
            summaries.append(
                {
                    "name": name,
                    "classifier_model": data.get("classifier_model"),
                    "num_classes": len(classes) if isinstance(classes, list) else 0,
                }
            )
        return summaries
