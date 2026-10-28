"""system-提示词部分注册表的类型化核心。

纯数据类型——没有 I/O——所以它们单独进行单元测试。
"""

import sys
from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import NamedTuple, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator


__all__ = [
    "CacheTier",
    "Platform",
    "PromptBlocks",
    "PromptContext",
    "PromptSection",
]


class CacheTier(StrEnum):
    """块渲染到的部分； 将 1:1 映射到 ``SystemPromptEvent`` 的两个
    内容块。 ``STATIC`` 在对话之间缓存稳定，``DYNAMIC`` 是每个对话。
    """

    STATIC = "static"
    DYNAMIC = "dynamic"


class Platform(StrEnum):
    """主机平台，源自：data:`sys.platform`。"""

    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    OTHER = "other"

    @classmethod
    def current(cls) -> "Platform":
        if sys.platform == "win32":
            return cls.WINDOWS
        if sys.platform == "darwin":
            return cls.MACOS
        if sys.platform.startswith("linux"):
            return cls.LINUX
        return cls.OTHER


class PromptContext(BaseModel):
    """塑造系统的一切事物的冻结快照提示词。

    ``template_kwargs`` 是静态、缓存稳定块的解析 kwarg 字典； 其他字段快照每个对话信
    号。 ``model_family`` /
    ``cli_mode`` 是 ``template_kwargs`` 上的类型化视图。
    """

    model_config = ConfigDict(frozen=True)

    template_kwargs: Mapping[str, object] = Field(
        default_factory=dict, validate_default=True
    )
    tool_names: tuple[str, ...] = Field(default_factory=tuple)
    tool_guidance: tuple[str, ...] = Field(default_factory=tuple)
    platform: Platform = Field(default_factory=Platform.current)
    working_dir: str | None = None
    now: str | None = None
    skill_names: tuple[str, ...] = Field(default_factory=tuple)
    secret_names: tuple[str, ...] = Field(default_factory=tuple)
    # 已解决的动态层数据（技能门控 + 机密在组装前合并），由动态部分消耗。
    # ``repo_skills`` 是（名称，内容）对；
    # ``secret_infos`` 是（名称，描述）对。
    repo_skills: tuple[tuple[str, str], ...] = Field(default_factory=tuple)
    available_skills_prompt: str | None = None
    custom_suffix: str | None = None
    memory_context: str | None = None
    secret_infos: tuple[tuple[str, str | None], ...] = Field(default_factory=tuple)

    @field_validator("template_kwargs", mode="after")
    @classmethod
    def _freeze_template_kwargs(
        cls, value: Mapping[str, object]
    ) -> Mapping[str, object]:
        # frozen=True blocks attribute reassignment but not nested mutation;
        # 存储只读副本，以便快照及其视图不会漂移。
        return MappingProxyType(dict(value))

    @property
    def model_family(self) -> str | None:
        value = self.template_kwargs.get("model_family")
        return value if isinstance(value, str) else None

    @property
    def cli_mode(self) -> bool:
        return bool(self.template_kwargs.get("cli_mode", False))

    @property
    def persona(self) -> str | None:
        value = self.template_kwargs.get("persona")
        return value if isinstance(value, str) and value.strip() else None


@runtime_checkable
class PromptSection(Protocol):
    """system-提示词文本的一个纯单元——一个贡献的受保护块
    仅在适用时才显示文本。

    针对冻结的：class:`PromptContext` 分两步组装：
    :meth:`guard` 决定该部分是否适用（如果 ``False`` 是
    跳过并且：meth:`render` 永远不会运行），然后：meth:`render` 生成文本。 拆分是有意
    的 - ``guard`` 返回 ``False``
    意味着“此处不适用”（e.g. 安全策略已禁用），同时 ``render`` 返回
    ``None`` 表示“适用，但现在无需添加”（e.g. 没有技能）。

    两者都必须是纯的——只读在``ctx``上，没有I/O——所以部分可以单独测试。 ``name`` 是注
    册表用于重复数据删除/覆盖的唯一键；
    ``cache_tier`` 选择静态或动态块。
    """

    @property
    def name(self) -> str: ...

    @property
    def cache_tier(self) -> CacheTier: ...

    def guard(self, ctx: PromptContext) -> bool:
        """如果本节适用于 ``ctx``，则返回 ``True``。"""
        ...

    def render(self, ctx: PromptContext) -> str | None:
        """返回该部分的文本，或 ``None``/blank 不提供任何内容。"""
        ...


class PromptBlocks(NamedTuple):
    """两个内容块注册表组成。

    将 1:1 映射到 ``SystemPromptEvent``：``static`` 成为缓存稳定的
    ``system_prompt`` 块和 ``dynamic`` 可选的 ``dynamic_context``（``None`` 当没有动
    态部分产生输出时）。 它
    是一个元组，所以它仍然解压为 ``static, dynamic = registry.build(ctx)``。
    """

    static: str
    dynamic: str | None = None
