from __future__ import annotations

import copy
import itertools
import shutil
from collections.abc import Callable, Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,
    Literal,
    Self,
    TypeVar,
    get_args,
    get_origin,
)
from uuid import UUID

from pydantic import (
    BaseModel,
    Discriminator,
    Field,
    SecretStr,
    SerializationInfo,
    Tag,
    TypeAdapter,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic.fields import FieldInfo

from openhands.sdk.agent.base import AgentBase
from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.conversation.message_request import SendMessageRequest
from openhands.sdk.conversation.types import (
    ConversationObservabilityMetadata,
    ConversationObservabilitySpanName,
    ConversationObservabilityTags,
)
from openhands.sdk.hooks import HookConfig
from openhands.sdk.llm import LLM
from openhands.sdk.llm.meta_profile_store import MetaProfile
from openhands.sdk.llm.utils.openhands_provider import (
    canonicalize_openhands_llm_payload,
)
from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.config import (
    MCPOAuthState,
    MCPServer,
)
from openhands.sdk.plugin import PluginSource
from openhands.sdk.subagent.schema import AgentDefinition
from openhands.sdk.tool import Tool
from openhands.sdk.tool.builtins import BUILT_IN_TOOLS, ClassifyAndSwitchLLMTool
from openhands.sdk.tool.defaults import (
    drop_retired_tool_switches,
    effective_builtin_class,
    fold_retired_tool_switches,
    merge_duplicate_tools,
    resolve_tool_specs,
)
from openhands.sdk.utils.pydantic_secrets import (
    serialize_secret,
    validate_secret,
)
from openhands.sdk.workspace import LocalWorkspace

from .acp_providers import (
    ACPFileSecretSpec,
    ACPProviderInfo,
    default_acp_file_secrets,
    get_acp_provider,
)
from .metadata import (
    SETTINGS_METADATA_KEY,
    SETTINGS_SECTION_METADATA_KEY,
    SettingProminence,
    SettingsFieldMetadata,
    SettingsSectionMetadata,
)


if TYPE_CHECKING:
    from openhands.sdk.agent import ACPAgent, Agent
    from openhands.sdk.context.condenser import CondenserBase, LLMSummarizingCondenser
    from openhands.sdk.critic.base import CriticBase


logger = get_logger(__name__)


SettingsValueType = Literal[
    "string",
    "integer",
    "number",
    "boolean",
    "array",
    "object",
]
SettingsChoiceValue = bool | int | float | str


class SettingsChoice(BaseModel):
    value: SettingsChoiceValue
    label: str


class SettingsFieldSchema(BaseModel):
    key: str
    label: str
    description: str | None = None
    section: str
    section_label: str
    value_type: SettingsValueType
    default: Any = None
    prominence: SettingProminence = SettingProminence.MINOR
    depends_on: list[str] = Field(default_factory=list)
    secret: bool = False
    choices: list[SettingsChoice] = Field(default_factory=list)
    variant: str | None = Field(
        default=None,
        description=(
            "When set, the field only applies to the named ``AgentSettings`` "
            "variant (``'openhands'`` or ``'acp'``). The GUI filters fields by the "
            "user's current variant; fields with ``variant=None`` are shown "
            "regardless."
        ),
    )


class SettingsSectionSchema(BaseModel):
    key: str
    label: str
    fields: list[SettingsFieldSchema]
    variant: str | None = Field(
        default=None,
        description=(
            "When set, this section only applies to the named ``AgentSettings`` "
            "variant (e.g. ``'openhands'`` or ``'acp'``). The GUI filters sections by "
            "the current ``agent_kind`` value; sections with ``variant=None`` "
            "are always shown."
        ),
    )


class SettingsSchema(BaseModel):
    model_name: str
    sections: list[SettingsSectionSchema]


CriticMode = Literal["finish_and_message", "all_actions"]
SecurityAnalyzerType = Literal["llm", "none"]
WorktreeBase = Literal["default_branch", "head", "ref"]
"""工作树从以下分支之一开始：仓库的默认分支（当存在时从 ``origin`` 获取），当前的
``HEAD`` 分支，或给定的引用。
"""
DEFAULT_WORKTREE_BRANCH_PREFIX = "openhands/"
"""工作树分支被命名为 ``<prefix><conversation id>``。"""
GIT_REF_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"
"""分支、标签或提交名称。 它永远不会以 ``-`` 开头，因此 git 无法将其读取为选项。
"""
GIT_BRANCH_PREFIX_PATTERN = r"^([A-Za-z0-9][A-Za-z0-9._/-]*)?$"
"""在同一规则下，分支名称前缀，可能为空。"""
ConversationRuntime = Literal["local", "docker"]
"""对话运行的位置：在智能体-服务器的主机上或其自己的容器中。"""
DefaultRuntime = Literal["local", "worktree", "docker"]
"""默认情况下运行新对话的位置：主机上的工作区、主机上的新 git 工作树或它们自己的容器
。
"""
DOCKER_MEMORY_PATTERN = r"^\d+(\.\d+)? ?[kKmMgGtTpP]?[iI]?[bB]?$"
"""`docker run --memory` 接受什么（Docker 的 `RAMInBytes`），e.g。 `512m`, `4g`."""
MIN_CONTAINER_CPUS = 0.01
"""接受的最小 `docker run --cpus` 值 Docker。"""


type CondenserKind = Literal["llm_summarizing", "no_op"]


class CondenserSettings(BaseModel):
    """上下文压缩器-设置变体的共享基础。

    使用：data:`CondenserSettingsConfig` 作为可能包含任何受支持的上下文压缩器设置变体
    的字段。
    """

    condenser_kind: CondenserKind = Field(
        default="llm_summarizing",
        description="Discriminator for the condenser settings union.",
        json_schema_extra={SETTINGS_METADATA_KEY: SettingsFieldMetadata().model_dump()},
    )
    enabled: bool = Field(
        default=True,
        description="Enable conversation memory condensation.",
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Enable memory condensation",
                prominence=SettingProminence.CRITICAL,
            ).model_dump()
        },
    )
    max_size: int = Field(
        default=240,
        ge=20,
        description=(
            "Maximum number of events kept before the condenser runs. "
            "Kept on the base settings class for compatibility; concrete "
            "condenser-settings variants may opt out when this does not apply."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Max size",
                prominence=SettingProminence.MINOR,
                depends_on=("enabled",),
            ).model_dump()
        },
    )

    def build_condenser(self, llm: LLM) -> CondenserBase | None:
        """根据这些设置创建上下文压缩器，如果禁用，则创建 ``None``。"""
        raise NotImplementedError(
            f"{type(self).__name__} must implement build_condenser()"
        )


class LLMSummarizingCondenserSettings(CondenserSettings):
    """设置为默认LLM总结上下文压缩器。"""

    condenser_kind: Literal["llm_summarizing"] = Field(  # type: ignore[reportIncompatibleVariableOverride]
        default="llm_summarizing",
        description=(
            "Discriminator for the condenser settings union. ``'llm_summarizing'`` "
            "selects the default LLM summarizing condenser."
        ),
        json_schema_extra={SETTINGS_METADATA_KEY: SettingsFieldMetadata().model_dump()},
    )
    max_tokens: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Maximum number of tokens allowed before the condenser runs. "
            "When unset, condensation is only based on event count."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Max tokens",
                prominence=SettingProminence.MINOR,
                depends_on=("enabled",),
            ).model_dump()
        },
    )
    keep_first: int = Field(
        default=2,
        ge=0,
        description="Minimum number of initial events to preserve before condensation.",
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Keep first",
                prominence=SettingProminence.MINOR,
                depends_on=("enabled",),
            ).model_dump()
        },
    )
    minimum_progress: float = Field(
        default=0.1,
        gt=0.0,
        lt=1.0,
        description=(
            "Minimum fraction of events that must be condensed for condensation "
            "to be considered successful."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Minimum progress",
                prominence=SettingProminence.MINOR,
                depends_on=("enabled",),
            ).model_dump()
        },
    )
    hard_context_reset_max_retries: int = Field(
        default=5,
        gt=0,
        description="Number of hard context reset attempts before raising an error.",
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Hard reset retries",
                prominence=SettingProminence.MINOR,
                depends_on=("enabled",),
            ).model_dump()
        },
    )
    hard_context_reset_context_scaling: float = Field(
        default=0.8,
        gt=0.0,
        lt=1.0,
        description=(
            "Factor used to reduce event string size after a hard context reset "
            "summarization failure."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Hard reset scaling",
                prominence=SettingProminence.MINOR,
                depends_on=("enabled",),
            ).model_dump()
        },
    )

    def build_condenser(self, llm: LLM) -> LLMSummarizingCondenser | None:
        """根据这些设置创建上下文压缩器，如果禁用，则创建 ``None``。"""
        if not self.enabled:
            return None

        from openhands.sdk.context.condenser import LLMSummarizingCondenser

        condenser_llm = llm.model_copy(update={"usage_id": "condenser"})
        condenser_llm.reset_metrics()
        condenser_kwargs = self.model_dump(
            exclude={"enabled", "condenser_kind"},
            exclude_none=True,
        )
        # 如果用户没有显式配置上下文压缩器 token 限制，应继承智能体 LLM 的有效最大输入
        # token，而不是仅通过上下文压缩触发词元数量。
        #
        if "max_tokens" not in self.model_fields_set:
            effective_max_input_tokens = llm.effective_max_input_tokens
            if effective_max_input_tokens is not None:
                condenser_kwargs["max_tokens"] = effective_max_input_tokens
        return LLMSummarizingCondenser(llm=condenser_llm, **condenser_kwargs)


class NoOpCondenserSettings(CondenserSettings):
    """上下文压缩器的设置使对话视图保持不变。"""

    max_size: ClassVar[int] = 240  # type: ignore[reportIncompatibleVariableOverride]
    condenser_kind: Literal["no_op"] = Field(  # type: ignore[reportIncompatibleVariableOverride]
        default="no_op",
        description=(
            "Discriminator for the condenser settings union. ``'no_op'`` selects "
            "a condenser that leaves conversation views unchanged."
        ),
        json_schema_extra={SETTINGS_METADATA_KEY: SettingsFieldMetadata().model_dump()},
    )

    def build_condenser(self, llm: LLM) -> CondenserBase | None:  # noqa: ARG002
        """根据这些设置创建上下文压缩器，如果禁用，则创建 ``None``。"""
        if not self.enabled:
            return None

        from openhands.sdk.context.condenser import NoOpCondenser

        return NoOpCondenser()


def _condenser_settings_discriminator(value: Any) -> str:
    """:data:`CondenserSettingsConfig` 的鉴别器。

    现有的载荷早于 ``condenser_kind``，并且仅包含默认的 LLM 总结上下文压缩器字段。 将
    缺失的鉴别器视为
    ``'llm_summarizing'`` 因此那些载荷继续验证。
    """
    if isinstance(value, CondenserSettings):
        return value.condenser_kind
    if isinstance(value, dict):
        return value.get("condenser_kind", "llm_summarizing")
    return "llm_summarizing"


CondenserSettingsConfig = Annotated[
    Annotated[LLMSummarizingCondenserSettings, Tag("llm_summarizing")]
    | Annotated[NoOpCondenserSettings, Tag("no_op")],
    Discriminator(_condenser_settings_discriminator),
]
"""上下文压缩器设置变体的可区分联合。"""


class VerificationSettings(BaseModel):
    """智能体的批评和迭代细化设置。"""

    # ——评论家——
    critic_enabled: bool = Field(
        default=False,
        description="Enable critic evaluation for the agent.",
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Enable critic",
                prominence=SettingProminence.CRITICAL,
            ).model_dump()
        },
    )
    critic_mode: CriticMode = Field(
        default="finish_and_message",
        description="When critic evaluation should run.",
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Critic mode",
                prominence=SettingProminence.MINOR,
                depends_on=("critic_enabled",),
            ).model_dump()
        },
    )
    enable_iterative_refinement: bool = Field(
        default=False,
        description=(
            "Automatically retry tasks when critic scores fall below the threshold."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Enable iterative refinement",
                prominence=SettingProminence.CRITICAL,
                depends_on=("critic_enabled",),
            ).model_dump()
        },
    )
    critic_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Critic success threshold used for iterative refinement.",
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Critic threshold",
                prominence=SettingProminence.MINOR,
                depends_on=("critic_enabled", "enable_iterative_refinement"),
            ).model_dump()
        },
    )
    max_refinement_iterations: int = Field(
        default=3,
        ge=1,
        description="Maximum number of refinement attempts after critic feedback.",
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Max refinement iterations",
                prominence=SettingProminence.MINOR,
                depends_on=("critic_enabled", "enable_iterative_refinement"),
            ).model_dump()
        },
    )

    # ——批评部署——
    critic_server_url: str | None = Field(
        default=None,
        description=(
            "Override the critic service URL. "
            "When None, the APIBasedCritic default is used."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Critic server URL",
                prominence=SettingProminence.MINOR,
                depends_on=("critic_enabled",),
            ).model_dump()
        },
    )
    critic_model_name: str | None = Field(
        default=None,
        description=(
            "Override the critic model name. "
            "When None, the APIBasedCritic default is used."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Critic model name",
                prominence=SettingProminence.MINOR,
                depends_on=("critic_enabled",),
            ).model_dump()
        },
    )
    critic_api_key: str | SecretStr | None = Field(
        default=None,
        description=(
            "API key used to authenticate with the critic service. "
            "When None, the LLM's ``api_key`` is reused, which preserves "
            "the auto-configuration path for the All-Hands LLM proxy."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Critic API Key",
                prominence=SettingProminence.CRITICAL,
                depends_on=("critic_enabled",),
            ).model_dump()
        },
    )

    @field_validator("critic_api_key")
    @classmethod
    def _validate_critic_api_key(
        cls, v: str | SecretStr | None, info: ValidationInfo
    ) -> SecretStr | None:
        return validate_secret(v, info)

    @field_serializer("critic_api_key", when_used="always")
    def _serialize_critic_api_key(
        self, v: SecretStr | None, info: SerializationInfo
    ) -> Any:
        return serialize_secret(v, info)


def _default_llm_settings() -> LLM:
    model = LLM.model_fields["model"].get_default()
    assert isinstance(model, str)
    return LLM(model=model)


_RequestT = TypeVar("_RequestT")

type AgentKind = Literal["openhands", "llm", "acp"]
AGENT_SETTINGS_SCHEMA_VERSION = 9
CONVERSATION_SETTINGS_SCHEMA_VERSION = 1

_RUNTIME_SECTION_METADATA = SettingsSectionMetadata(
    key="runtime", label="Runtime"
).model_dump()


class AgentSettingsBase(BaseModel):
    """所有智能体设置变体的共享基础。

    提供每个变体通用的部件：

    - :attr:`schema_version` — 用于已持久化-载荷迁移。
    - :meth:`export_schema` — UI 的结构化字段描述。
    - :meth:`from_persisted` — 通过迁移加载已持久化设置。
    - :meth:`create_agent` — 规范构建路径； 具体的子类必须重写它。

    ``llm`` 字段故意 * 而非 * 在这里提升：仅
    :class:`OpenHandsAgentSettings` 调用 LLM。

    使用：data:`AgentSettingsConfig` 作为可能包含：class:`OpenHandsAgentSettings` 或
    ：class:
    `ACPAgentSettings` 变体的字段的类型。 使用：func:`validate_agent_settings` 验证原
    始载荷。
    """

    schema_version: int = Field(default=AGENT_SETTINGS_SCHEMA_VERSION, ge=1)
    agent_kind: AgentKind = Field(
        default="openhands",
        description="Discriminator for the agent settings union.",
    )

    @classmethod
    def export_schema(cls) -> SettingsSchema:
        """导出描述可配置设置的结构化模式。"""
        return export_settings_schema(cls)

    @classmethod
    def from_persisted(
        cls,
        data: Any,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Self:
        """将已持久化智能体设置加载到该具体变体中。

        应用注册的模式迁移，然后直接针对 ``cls`` 验证迁移的载荷。 该方法适用于具体子
        类； 想要在设置变体之间进行联合调用的调用者应使用：func:
        `validate_agent_settings`。 当前-模式载荷
        with the deprecated ``agent_kind='llm'`` discriminator are rejected by
        ：方法：`OpenHandsAgentSettings.from_persisted`。

        加载加密的已持久化映射时，传递用于写入它的相同验证上下文（例如
        ``{"cipher": cipher}``），以便可以解密包含机密的字段。 该具体变体的已
        验证实例将原封不动地返回，保留其机密，而无需有损序列化往返。

        Returns:
            ``cls`` 的一个实例。

        Raises:
            TypeError: 如果 *data* 不是映射/BaseModel 或具有
                非整数 ``schema_version``。
            ValueError: 如果 ``schema_version`` 为负数，则更新于
                支持，否则无法迁移。
            pydantic.ValidationError：如果迁移的载荷无效
                ``cls``.
        """
        if isinstance(data, cls):
            return data
        if isinstance(data, BaseModel):
            data = data.model_dump(mode="json", context={"expose_secrets": "plaintext"})
        payload = _migrate_agent_settings_payload(data, persisted=True)
        return cls.model_validate(payload, context=context)

    def create_agent(self) -> AgentBase:
        """根据这些设置构建智能体。

        子类（:class:`OpenHandsAgentSettings`, :class:`ACPAgentSettings`）覆盖它以返
        回适当的
        :class:`~openhands.sdk.agent.base.AgentBase` 子类。
        在基类上调用它会直接引发：exc:`NotImplementedError`。
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement create_agent()"
        )


PersistedSettingsMigrator = Callable[[dict[str, Any]], dict[str, Any]]


def _copy_persisted_payload(data: Any) -> dict[str, Any]:
    if isinstance(data, BaseModel):
        payload = data.model_dump(mode="json")
        if not isinstance(payload, dict):
            raise TypeError("Persisted settings payload must serialize to a mapping.")
        return payload
    if isinstance(data, Mapping):
        return dict(data)
    raise TypeError("Persisted settings payload must be a mapping or BaseModel.")


def _apply_persisted_migrations(
    data: Any,
    *,
    current_version: int,
    migrations: dict[int, PersistedSettingsMigrator],
    payload_name: str,
) -> dict[str, Any]:
    payload = _copy_persisted_payload(data)
    version_raw = payload.get("schema_version", 0)
    if version_raw is None:
        version = 0
    elif isinstance(version_raw, int) and not isinstance(version_raw, bool):
        version = version_raw
    else:
        raise TypeError(
            f"{payload_name} schema_version must be an integer, got "
            f"{type(version_raw).__name__}."
        )

    if version < 0:
        raise ValueError(f"{payload_name} schema_version must be non-negative.")
    if version > current_version:
        raise ValueError(
            f"{payload_name} schema_version {version} is newer than supported "
            f"version {current_version}."
        )

    while version < current_version:
        migrate = migrations.get(version)
        if migrate is None:
            raise ValueError(
                f"No migration registered for {payload_name} schema_version {version}."
            )
        payload = migrate(dict(payload))
        next_version = payload.get("schema_version")
        if not isinstance(next_version, int) or isinstance(next_version, bool):
            raise ValueError(
                f"Migration for {payload_name} schema_version {version} did not "
                "produce a valid integer schema_version."
            )
        if next_version <= version:
            raise ValueError(
                f"Migration for {payload_name} schema_version {version} did not "
                "advance the schema_version."
            )
        version = next_version

    return payload


def _migrate_agent_settings_v0_to_v1(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(payload)
    migrated["schema_version"] = 1
    migrated.setdefault("agent_kind", _agent_settings_discriminator(migrated))
    return migrated


def _migrate_agent_settings_v1_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    """将已弃用 ``agent_kind: 'llm'`` 鉴别器规范化为
    ``'openhands'``.

    在v1.19.0``LLMAgentSettings``→``OpenHandsAgentSettings``重命名之前，已持久化载荷
    携带
    ``agent_kind: 'llm'``。 这两个类是字段兼容的（``LLMAgentSettings`` 是
    ``OpenHandsAgentSettings`` 只缩小了鉴别器文字的范围），``LLMAgentSettings`` 的导
    入别名在 v1.24.0 中被删除。
     在读取时重写鉴别器可以让调用者显式验证为
    ``OpenHandsAgentSettings``（规范类）接受遗留数据而不丢失任何字段。
    """
    migrated = dict(payload)
    migrated["schema_version"] = 2
    if migrated.get("agent_kind") == "llm":
        migrated["agent_kind"] = "openhands"
    return migrated


def _migrate_agent_settings_v2_to_v3(payload: dict[str, Any]) -> dict[str, Any]:
    """将已弃用验证字段移至 ``ConversationSettings``。"""
    migrated = dict(payload)
    verification = migrated.get("verification")
    if isinstance(verification, Mapping):
        verification = dict(verification)
        verification.pop("confirmation_mode", None)
        verification.pop("security_analyzer", None)
        migrated["verification"] = verification
    migrated["schema_version"] = 3
    return migrated


def _migrate_agent_settings_v3_to_v4(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(payload)
    llm = migrated.get("llm")
    if isinstance(llm, dict):
        migrated["llm"] = canonicalize_openhands_llm_payload(llm)
    migrated["schema_version"] = 4
    return migrated


def _migrate_agent_settings_v4_to_v5(payload: dict[str, Any]) -> dict[str, Any]:
    """SDK-本机服务器映射/身份验证形状中的持久化 MCP 设置。"""

    migrated = dict(payload)
    mcp_config = migrated.get("mcp_config")
    if isinstance(mcp_config, Mapping):
        migrated["mcp_config"] = _migrate_mcp_config_to_server_map(mcp_config)
    migrated["schema_version"] = 5
    return migrated


def _migrate_agent_settings_v5_to_v6(payload: dict[str, Any]) -> dict[str, Any]:
    """删除已弃用 ``llm.modify_params`` 兼容性字段。

    ``LLM.modify_params`` 在 v1.42.0 中为已弃用，在 v1.47.0 中被删除（LiteLLM 参数修
    改在进程范围内启用）。 已持久化载荷
    由旧版本编写的仍然带有 ``llm.modify_params``； 将其放在此处，以便迁移的载荷是干净
    的当前模式形状。 (``LLM``本身使用
    ``extra="ignore"``，因此未迁移的字段也会在加载时被删除，但迁移仍应发出规范的载荷
    ，而不是依赖宽松的验证。）
    """
    migrated = dict(payload)
    llm = migrated.get("llm")
    if isinstance(llm, Mapping):
        llm = dict(llm)
        llm.pop("modify_params", None)
        migrated["llm"] = llm
    migrated["schema_version"] = 6
    return migrated


def _migrate_agent_settings_v6_to_v7(payload: dict[str, Any]) -> dict[str, Any]:
    """将已弃用 ``llm`` 从 ACP 设置中删除。"""
    migrated = dict(payload)
    if migrated.get("agent_kind") == "acp":
        migrated.pop("llm", None)
    migrated["schema_version"] = 7
    return migrated


def _migrate_agent_settings_v7_to_v8(payload: dict[str, Any]) -> dict[str, Any]:
    """将退役的工具开关折叠到 ``tools`` 中。"""
    if payload.get("agent_kind", "openhands") == "acp":
        migrated = drop_retired_tool_switches(payload)
    else:
        migrated = fold_retired_tool_switches(payload)
    migrated["schema_version"] = 8
    return migrated


def _migrate_agent_settings_v8_to_v9(payload: dict[str, Any]) -> dict[str, Any]:
    """丢弃废弃的输入字段而不恢复其以前的行为。"""
    migrated = drop_retired_tool_switches(payload)
    if payload.get("agent_kind", "openhands") == "acp":
        migrated.pop("llm", None)
    migrated["schema_version"] = 9
    return migrated


def _migrate_agent_settings_payload(
    data: Any, *, persisted: bool = False
) -> dict[str, Any]:
    payload = _copy_persisted_payload(data)
    is_request = not persisted and payload.get("schema_version") is None
    if is_request:
        _reject_removed_settings_input(payload)
    return _apply_persisted_migrations(
        payload,
        current_version=AGENT_SETTINGS_SCHEMA_VERSION,
        migrations=(
            _REQUEST_AGENT_SETTINGS_MIGRATIONS
            if is_request
            else _AGENT_SETTINGS_MIGRATIONS
        ),
        payload_name="AgentSettings",
    )


def _reject_removed_settings_input(data: Any) -> Any:
    if isinstance(data, Mapping):
        removed = {"enable_sub_agents", "enable_switch_llm_tool"}.intersection(data)
        if data.get("agent_kind") == "acp" and "llm" in data:
            removed.add("llm")
        if removed:
            raise ValueError(f"Removed agent settings: {', '.join(sorted(removed))}")
    return data


_MCP_OAUTH_TOKEN_COLLECTION = "mcp-oauth-token"
_MCP_OAUTH_CLIENT_INFO_COLLECTION = "mcp-oauth-client-info"
_MCP_OAUTH_TOKEN_EXPIRY_COLLECTION = "mcp-oauth-token-expiry"
_LINEAR_DEPRECATED_SSE_URL = "https://mcp.linear.app/sse"
_LINEAR_SHTTP_URL = "https://mcp.linear.app/mcp"
_MCP_SERVER_KNOWN_FIELDS = frozenset(MCPServer.model_fields)


def _migrate_legacy_transport_field(server: Mapping[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(dict(server))
    typed_transport = migrated.pop("type", None)
    if "transport" not in migrated and typed_transport is not None:
        migrated["transport"] = (
            "http" if typed_transport == "shttp" else typed_transport
        )
    return migrated


def _is_deprecated_linear_sse(url: Any, transport: Any) -> bool:
    if not isinstance(url, str) or transport != "sse":
        return False
    return url.split("?", 1)[0].rstrip("/") == _LINEAR_DEPRECATED_SSE_URL


def _is_auto_mcp_server_key(name: Any, base: str) -> bool:
    if not isinstance(name, str):
        return False
    if name == base:
        return True
    prefix = f"{base}_"
    return name.startswith(prefix) and name[len(prefix) :].isdigit()


def _reserve_mcp_server_key(name: str, servers: Mapping[str, Any]) -> str:
    if name not in servers:
        return name
    index = 1
    while f"{name}_{index}" in servers:
        index += 1
    return f"{name}_{index}"


def _legacy_cache_entry_value(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, Mapping):
        return None
    value = entry.get("value")
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    return copy.deepcopy(dict(entry))


def _legacy_oauth_bucket_value(
    credentials: Mapping[str, Any],
    collection: str,
    key_suffix: str,
) -> dict[str, Any] | None:
    bucket = credentials.get(collection)
    if not isinstance(bucket, Mapping):
        return None
    fallback: dict[str, Any] | None = None
    for key, entry in bucket.items():
        value = _legacy_cache_entry_value(entry)
        if value is None:
            continue
        if isinstance(key, str) and key.endswith(key_suffix):
            return value
        if fallback is None:
            fallback = value
    return fallback


def _migrate_legacy_oauth_credentials(
    credentials: Any,
) -> dict[str, Any]:
    if not isinstance(credentials, Mapping):
        return {}

    state = MCPOAuthState()
    tokens = _legacy_oauth_bucket_value(
        credentials, _MCP_OAUTH_TOKEN_COLLECTION, "/tokens"
    )
    if tokens:
        state = state.with_token_storage_value("tokens", tokens)

    client_info = _legacy_oauth_bucket_value(
        credentials, _MCP_OAUTH_CLIENT_INFO_COLLECTION, "/client_info"
    )
    if client_info:
        state = state.with_token_storage_value("client_info", client_info)

    token_expiry = _legacy_oauth_bucket_value(
        credentials, _MCP_OAUTH_TOKEN_EXPIRY_COLLECTION, "/token_expiry"
    )
    if token_expiry:
        state = state.with_token_storage_value("token_expires_at", token_expiry)

    return state.to_plain_dict()


def _merge_oauth_state(
    existing_state: Any,
    legacy_credentials: Any,
) -> dict[str, Any] | None:
    state = (
        copy.deepcopy(dict(existing_state))
        if isinstance(existing_state, Mapping)
        else {}
    )
    for key, value in _migrate_legacy_oauth_credentials(legacy_credentials).items():
        state.setdefault(key, value)
    return state or None


def _migrate_authorization_header(headers: dict[str, Any]) -> dict[str, Any] | None:
    for key, value in list(headers.items()):
        if key.lower() != "authorization" or not isinstance(value, str) or not value:
            continue
        headers.pop(key, None)
        parts = value.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return {"strategy": "bearer", "value": parts[1]}
        return {"strategy": "header", "headers": {key: value}}
    return None


def _migrate_oauth_authentication(authentication: Any) -> Any:
    if not isinstance(authentication, Mapping):
        return authentication
    migrated = copy.deepcopy(dict(authentication))
    migrated.setdefault("type", "oauth")
    return migrated


def _finish_mcp_server_auth_migration(
    server: dict[str, Any], *, drop_unknown_fields: bool
) -> dict[str, Any]:
    server = _migrate_legacy_transport_field(server)
    if drop_unknown_fields:
        return {
            key: value
            for key, value in server.items()
            if key in _MCP_SERVER_KNOWN_FIELDS
        }
    return server


def _migrate_mcp_server_auth(server: Any, *, drop_unknown_fields: bool = True) -> Any:
    if not isinstance(server, Mapping):
        return server

    migrated = copy.deepcopy(dict(server))
    authentication = migrated.pop("authentication", None)
    oauth_credentials = migrated.pop("oauth_credentials", None)
    api_key = migrated.pop("api_key", None)
    auth = migrated.get("auth")

    if isinstance(auth, Mapping):
        auth = copy.deepcopy(dict(auth))
        if auth.get("strategy") == "oauth2":
            if authentication is not None and "authentication" not in auth:
                auth["authentication"] = _migrate_oauth_authentication(authentication)
            elif "authentication" in auth:
                auth["authentication"] = _migrate_oauth_authentication(
                    auth["authentication"]
                )
            state = _merge_oauth_state(
                auth.get("state"),
                auth.pop("credentials", None) or oauth_credentials,
            )
            if state is not None:
                auth["state"] = state
        migrated["auth"] = auth
        return _finish_mcp_server_auth_migration(
            migrated, drop_unknown_fields=drop_unknown_fields
        )

    if auth == "oauth":
        oauth_auth: dict[str, Any] = {"strategy": "oauth2"}
        if authentication is not None:
            oauth_auth["authentication"] = _migrate_oauth_authentication(authentication)
        state = _merge_oauth_state(None, oauth_credentials)
        if state is not None:
            oauth_auth["state"] = state
        migrated["auth"] = oauth_auth
        return _finish_mcp_server_auth_migration(
            migrated, drop_unknown_fields=drop_unknown_fields
        )

    if isinstance(auth, str) and auth:
        migrated["auth"] = {"strategy": "bearer", "value": auth}
        return _finish_mcp_server_auth_migration(
            migrated, drop_unknown_fields=drop_unknown_fields
        )

    if isinstance(api_key, str) and api_key:
        migrated["auth"] = {"strategy": "api_key", "value": api_key}
        return _finish_mcp_server_auth_migration(
            migrated, drop_unknown_fields=drop_unknown_fields
        )

    headers = migrated.get("headers")
    if isinstance(headers, Mapping):
        headers = copy.deepcopy(dict(headers))
        header_auth = _migrate_authorization_header(headers)
        if header_auth is not None:
            migrated["auth"] = header_auth
            if headers:
                migrated["headers"] = headers
            else:
                migrated.pop("headers", None)

    return _finish_mcp_server_auth_migration(
        migrated, drop_unknown_fields=drop_unknown_fields
    )


def _migrate_mcp_auth_shape(mcp_config: Any) -> Any:
    if not isinstance(mcp_config, Mapping):
        return mcp_config
    servers = mcp_config.get("mcpServers")
    if not isinstance(servers, Mapping):
        return mcp_config

    migrated = copy.deepcopy(dict(mcp_config))
    migrated_servers: dict[str, Any] = {}
    deferred_linear_servers: dict[str, Any] = {}
    linear_shttp_exists = any(
        isinstance(server, Mapping)
        and isinstance(server.get("url"), str)
        and server["url"].rstrip("/") == _LINEAR_SHTTP_URL
        for server in servers.values()
    )

    for name, server in servers.items():
        server = _migrate_mcp_server_auth(server)
        if isinstance(server, Mapping) and _is_deprecated_linear_sse(
            server.get("url"), server.get("transport")
        ):
            migrated_linear = copy.deepcopy(dict(server))
            migrated_linear["url"] = _LINEAR_SHTTP_URL
            migrated_linear.pop("transport", None)
            if not linear_shttp_exists:
                target_name = (
                    "shttp" if _is_auto_mcp_server_key(name, "sse") else str(name)
                )
                deferred_linear_servers[
                    _reserve_mcp_server_key(
                        target_name,
                        {**migrated_servers, **deferred_linear_servers},
                    )
                ] = migrated_linear
                linear_shttp_exists = True
            continue
        migrated_servers[name] = server

    migrated_servers.update(deferred_linear_servers)
    migrated["mcpServers"] = migrated_servers
    return migrated


def _migrate_mcp_config_to_server_map(
    mcp_config: Mapping[str, Any],
) -> dict[str, Any]:
    migrated = _migrate_mcp_auth_shape(mcp_config)
    if not isinstance(migrated, Mapping):
        return copy.deepcopy(dict(mcp_config))
    server_map = migrated.get("mcpServers")
    drop_unknown_fields = isinstance(server_map, Mapping)
    if not drop_unknown_fields:
        server_map = migrated

    return {
        str(name): _migrate_mcp_server_auth(
            server, drop_unknown_fields=drop_unknown_fields
        )
        if isinstance(server, Mapping)
        else server
        for name, server in server_map.items()
    }


def _migrate_conversation_settings_v0_to_v1(
    payload: dict[str, Any],
) -> dict[str, Any]:
    migrated = dict(payload)
    migrated["schema_version"] = 1
    return migrated


_AGENT_SETTINGS_MIGRATIONS: dict[int, PersistedSettingsMigrator] = {
    0: _migrate_agent_settings_v0_to_v1,
    1: _migrate_agent_settings_v1_to_v2,
    2: _migrate_agent_settings_v2_to_v3,
    3: _migrate_agent_settings_v3_to_v4,
    4: _migrate_agent_settings_v4_to_v5,
    5: _migrate_agent_settings_v5_to_v6,
    6: _migrate_agent_settings_v6_to_v7,
    7: _migrate_agent_settings_v7_to_v8,
    8: _migrate_agent_settings_v8_to_v9,
}
_REQUEST_AGENT_SETTINGS_MIGRATIONS: dict[int, PersistedSettingsMigrator] = {
    **_AGENT_SETTINGS_MIGRATIONS,
    7: lambda payload: {**payload, "schema_version": 8},
    8: lambda payload: {**payload, "schema_version": 9},
}
_CONVERSATION_SETTINGS_MIGRATIONS: dict[int, PersistedSettingsMigrator] = {
    0: _migrate_conversation_settings_v0_to_v1,
}


class ConversationSettings(BaseModel):
    schema_version: int = Field(default=CONVERSATION_SETTINGS_SCHEMA_VERSION, ge=1)

    # --- 运行时字段（即时填充，而不是已持久化） --------------
    agent_settings: AgentSettingsConfig | None = Field(
        default=None,
        exclude=True,
        description=(
            "Agent settings used to build the Agent for the conversation. "
            "When set, create_request() will automatically build the agent "
            "and populate secrets from agent_context. Accepts either the "
            "``OpenHandsAgentSettings`` or ``ACPAgentSettings`` variant."
        ),
    )
    workspace: LocalWorkspace | None = Field(
        default=None,
        exclude=True,
        description="Working directory for the conversation.",
    )
    conversation_id: UUID | None = Field(
        default=None,
        exclude=True,
        description="Conversation UUID. Auto-generated if not set.",
    )
    initial_message: SendMessageRequest | None = Field(
        default=None,
        exclude=True,
        description="Initial message to send to the agent.",
    )
    tool_module_qualnames: dict[str, str] = Field(
        default_factory=dict,
        exclude=True,
        description="Mapping of tool names to module qualnames.",
    )
    agent_definitions: list[AgentDefinition] = Field(
        default_factory=list,
        exclude=True,
        description="Agent definitions for task tools.",
    )
    plugins: list[PluginSource] | None = Field(
        default=None,
        exclude=True,
        description="Plugin sources to load for this conversation.",
    )
    hook_config: HookConfig | None = Field(
        default=None,
        exclude=True,
        description="Hook configuration for lifecycle events.",
    )
    selected_repository: str | None = Field(
        default=None,
        exclude=True,
        description="Repository selected for the conversation.",
    )
    observability_metadata: ConversationObservabilityMetadata | None = Field(
        default=None,
        exclude=True,
        description="Trace-level metadata for observability backends.",
    )
    observability_tags: ConversationObservabilityTags | None = Field(
        default=None,
        exclude=True,
        description="Tags for the conversation root observability span.",
    )
    observability_span_name: ConversationObservabilitySpanName | None = Field(
        default=None,
        exclude=True,
        description="Optional named child span to emit under the conversation root.",
    )

    # --- 已持久化字段 --------------------------------------------------
    max_iterations: int = Field(
        default=500,
        ge=1,
        description=(
            "Maximum number of iterations the conversation will run before stopping."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Max iterations",
                prominence=SettingProminence.MAJOR,
            ).model_dump()
        },
    )
    confirmation_mode: bool = Field(
        default=False,
        description="Require user confirmation before executing risky actions.",
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Confirmation mode",
                prominence=SettingProminence.CRITICAL,
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: SettingsSectionMetadata(
                key="verification",
                label="Verification",
            ).model_dump(),
        },
    )
    security_analyzer: SecurityAnalyzerType | None = Field(
        default="llm",
        description="Security analyzer that evaluates actions before execution.",
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Security analyzer",
                prominence=SettingProminence.MAJOR,
                depends_on=("confirmation_mode",),
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: SettingsSectionMetadata(
                key="verification",
                label="Verification",
            ).model_dump(),
        },
    )
    default_runtime: DefaultRuntime = Field(
        default="local",
        description=(
            "Where new conversations run: in the workspace on the host, in a "
            "new git worktree of it, or in their own Docker container (which "
            "needs a server that offers it)."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Default runtime",
                prominence=SettingProminence.MAJOR,
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: _RUNTIME_SECTION_METADATA,
        },
    )
    worktree_base: WorktreeBase = Field(
        default="default_branch",
        description=(
            "What a new conversation worktree branches from: the repository's "
            "default branch, the checkout's current HEAD, or `worktree_base_ref`."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Create worktrees from",
                prominence=SettingProminence.MAJOR,
                depends_on=("default_runtime=worktree",),
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: _RUNTIME_SECTION_METADATA,
        },
    )
    worktree_base_ref: str | None = Field(
        default=None,
        pattern=GIT_REF_PATTERN,
        description=(
            "Branch, tag or commit new worktrees branch from when "
            "`worktree_base` is `ref`, e.g. `develop` or `origin/release`."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Ref",
                prominence=SettingProminence.MAJOR,
                depends_on=("default_runtime=worktree", "worktree_base=ref"),
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: _RUNTIME_SECTION_METADATA,
        },
    )
    worktree_branch_prefix: str = Field(
        default=DEFAULT_WORKTREE_BRANCH_PREFIX,
        pattern=GIT_BRANCH_PREFIX_PATTERN,
        description=(
            "Start of each worktree's branch name, which ends in the "
            "conversation id, e.g. `openhands/` or `me/`."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Branch name prefix",
                prominence=SettingProminence.MAJOR,
                depends_on=("default_runtime=worktree",),
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: _RUNTIME_SECTION_METADATA,
        },
    )
    container_memory: str | None = Field(
        default=None,
        pattern=DOCKER_MEMORY_PATTERN,
        description=(
            "Memory limit for each new Docker conversation's container, in "
            "`docker run --memory` syntax such as `512m` or `4g`. Unset keeps "
            "the server default."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Container memory limit",
                prominence=SettingProminence.MAJOR,
                depends_on=("default_runtime=docker",),
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: _RUNTIME_SECTION_METADATA,
        },
    )
    container_cpus: float | None = Field(
        default=None,
        ge=MIN_CONTAINER_CPUS,
        description=(
            "CPUs each new Docker conversation's container may use, from 0.01 "
            "up to the machine's CPU count. Unset keeps the server default."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Container CPU limit",
                prominence=SettingProminence.MAJOR,
                depends_on=("default_runtime=docker",),
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: _RUNTIME_SECTION_METADATA,
        },
    )
    container_browser: bool = Field(
        default=True,
        description=(
            "Run a browser in new Docker conversations' containers. Has no "
            "effect when the server's image ships without one."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Browser in containers",
                prominence=SettingProminence.MAJOR,
                depends_on=("default_runtime=docker",),
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: _RUNTIME_SECTION_METADATA,
        },
    )

    @model_validator(mode="after")
    def _ref_for_ref_base(self) -> ConversationSettings:
        if self.worktree_base == "ref" and self.worktree_base_ref is None:
            raise ValueError("Branching worktrees from a ref needs worktree_base_ref")
        return self

    @classmethod
    def export_schema(cls) -> SettingsSchema:
        """导出描述可配置对话设置的结构化模式。"""
        return export_settings_schema(cls)

    @classmethod
    def from_persisted(cls, data: Any) -> ConversationSettings:
        """加载已持久化对话设置，应用任何模式迁移。"""
        payload = _apply_persisted_migrations(
            data,
            current_version=CONVERSATION_SETTINGS_SCHEMA_VERSION,
            migrations=_CONVERSATION_SETTINGS_MIGRATIONS,
            payload_name="ConversationSettings",
        )
        return cls.model_validate(payload)

    def _build_confirmation_policy(self):
        from openhands.sdk.security.confirmation_policy import (
            AlwaysConfirm,
            ConfirmRisky,
            NeverConfirm,
        )

        if not self.confirmation_mode:
            return NeverConfirm()
        if (self.security_analyzer or "").lower() == "llm":
            return ConfirmRisky()
        return AlwaysConfirm()

    def _build_security_analyzer(self):
        analyzer_kind = (self.security_analyzer or "").lower()
        if not analyzer_kind or analyzer_kind == "none":
            return None
        if analyzer_kind == "llm":
            from openhands.sdk.security.llm_analyzer import LLMSecurityAnalyzer

            return LLMSecurityAnalyzer()
        return None

    def _start_request_kwargs(self, **kwargs: Any) -> dict[str, Any]:
        payload = dict(kwargs)

        # --- 智能体 (来自 agent_settings) ---------------------------------------------
        # ---
        # 两种设置变体都公开了 .create_agent() 方法； LLM 变体返回 ``Agent``，ACP 变体返
        # 回
        # ``ACPAgent``. 想要缩小类型的调用者应该访问
        # ``self.agent_settings.create_agent()`` 直接。
        has_agent_source = any(
            payload.get(name) is not None
            for name in ("agent", "agent_settings", "agent_profile_id")
        )
        if not has_agent_source and self.agent_settings is not None:
            payload["agent"] = self.agent_settings.create_agent()

        # --- 机密（来自智能体的上下文）--------------------------------
        # ACPAgent 可以携带提示词-只上下文，但其执行上下文由子进程所有。
        # ``getattr(..., None)`` 保留了这个无操作行为智能体和 AgentContext。
        #
        agent = payload.get("agent")
        if "secrets" not in payload and agent is not None:
            if isinstance(agent, AgentBase) and agent.agent_context is not None:
                secrets = agent.agent_context.secrets
                if secrets:
                    payload["secrets"] = secrets

        # --- 运行时字段------------------------------------------------
        if self.workspace is not None:
            payload.setdefault("workspace", self.workspace)
        if self.conversation_id is not None:
            payload.setdefault("conversation_id", self.conversation_id)
        if self.initial_message is not None:
            payload.setdefault("initial_message", self.initial_message)
        if self.tool_module_qualnames:
            payload.setdefault("tool_module_qualnames", self.tool_module_qualnames)
        if self.agent_definitions:
            payload.setdefault("agent_definitions", self.agent_definitions)
        if self.plugins is not None:
            payload.setdefault("plugins", self.plugins)
        if self.hook_config is not None:
            payload.setdefault("hook_config", self.hook_config)
        if self.observability_metadata is not None:
            payload.setdefault("observability_metadata", self.observability_metadata)
        if self.observability_tags is not None:
            payload.setdefault("observability_tags", self.observability_tags)
        if self.observability_span_name is not None:
            payload.setdefault("observability_span_name", self.observability_span_name)

        # --- 已持久化默认值 ------------------------------------------------------
        payload.setdefault("confirmation_policy", self._build_confirmation_policy())
        payload.setdefault("security_analyzer", self._build_security_analyzer())
        payload.setdefault("max_iterations", self.max_iterations)
        return payload

    def create_request(
        self,
        request_type: Callable[..., _RequestT],
        /,
        **kwargs: Any,
    ) -> _RequestT:
        """根据这些设置构建请求。

        ``ConversationSettings`` 上的每个字段都用作默认值。 显式 *kwargs* 覆盖任何设
        置。
        """
        return request_type(**self._start_request_kwargs(**kwargs))


ACPServerKind = Literal[
    "claude-code", "codex", "gemini-cli", "kimi-code", "pi", "opencode", "custom"
]
"""GUI 可以从中选择已知的 ACP 个后端服务器。

``custom``表示用户自己提供原始``acp_command``； 其他选项映射到存储在的默认 npx 命令
：数据：`~openhands.sdk.settings.acp_providers.ACP_PROVIDERS`。
"""


class OpenHandsAgentSettings(AgentSettingsBase):
    """标准 LLM 支持的：class:`Agent` 的设置。

    这是长期存在的``AgentSettings``形状； 这里的字段构建默认的 ``Agent``（LLM + 工具
    + MCP + 上下文压缩器 + 评论家）。
    """

    agent_kind: Literal["openhands"] = Field(  # type: ignore[reportIncompatibleVariableOverride]
        default="openhands",
        description=(
            "Discriminator for the ``AgentSettings`` union. ``'openhands'`` selects "
            "the standard built-in OpenHands agent."
        ),
    )
    agent: str = Field(
        default="CodeActAgent",
        description="Agent class to use.",
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Agent",
                prominence=SettingProminence.MAJOR,
                variant="openhands",
            ).model_dump()
        },
    )
    llm: LLM = Field(
        default_factory=_default_llm_settings,
        description="LLM settings for the agent.",
        json_schema_extra={
            SETTINGS_SECTION_METADATA_KEY: SettingsSectionMetadata(
                key="llm",
                label="LLM",
                variant="openhands",
            ).model_dump()
        },
    )
    tools: list[Tool] | None = Field(
        default=None,
        description=(
            "Tools available to the agent. None (the default) resolves to the "
            "standard exec set plus switch_llm (see openhands.sdk.tool.defaults); "
            "[] is an explicitly bare agent; a non-empty list is used exactly as "
            "given. Environment-dependent tools (browser) are injected by the "
            "serving layer, not the default."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Tools",
                prominence=SettingProminence.MAJOR,
                variant="openhands",
            ).model_dump()
        },
    )
    enable_classify_and_switch_llm_tool: bool = Field(
        default=False,
        description=(
            "Enable the built-in route_task_to_model tool, which routes the "
            "task to the best LLM profile using the active meta-profile. When no "
            "active_meta_profile is set, the first available meta-profile is used."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Enable intelligent model routing tool",
                prominence=SettingProminence.MINOR,
                variant="openhands",
            ).model_dump()
        },
    )
    active_meta_profile: str | None = Field(
        default=None,
        description=(
            "Name of the active meta-profile (in ~/.openhands/meta-profiles) used "
            "by the route_task_to_model tool to route tasks to LLM profiles."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Active meta-profile",
                prominence=SettingProminence.MINOR,
                variant="openhands",
            ).model_dump()
        },
    )
    meta_profile: MetaProfile | None = Field(
        default=None,
        description=(
            "Inline configuration for the active meta-profile. Cloud runtimes "
            "use this field because their ephemeral filesystem does not contain "
            "the control plane's meta-profile store."
        ),
    )
    meta_profile_llms: dict[str, LLM] = Field(
        default_factory=dict,
        description=(
            "Resolved LLM configurations referenced by the active meta-profile. "
            "Cloud control planes hydrate this map for ephemeral runtimes."
        ),
    )
    tool_concurrency_limit: int = Field(
        default=1,
        ge=1,
        description=(
            "Maximum number of tool calls to execute concurrently per agent step. "
            "1 = sequential (default). Values > 1 enable parallel tool calls; "
            "concurrent tools share the conversation object, filesystem, and "
            "working directory, so mutations to shared state may race."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="Parallel tool calls",
                prominence=SettingProminence.MAJOR,
                variant="openhands",
            ).model_dump()
        },
    )

    mcp_config: dict[str, MCPServer] = Field(
        default_factory=dict,
        description="MCP servers available to the agent.",
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="MCP servers",
                prominence=SettingProminence.MINOR,
                variant="openhands",
            ).model_dump()
        },
    )
    persona: str | None = Field(
        default=None,
        min_length=1,
        max_length=65536,
        description=(
            "Persona text that replaces OpenHands' built-in persona and "
            "coding-workflow guidance. Capability and policy guidance (memory, "
            "security policy, risk assessment, browser, external services, process "
            "management, model-specific notes) and the dynamic context are still "
            "included. None keeps the built-in persona."
        ),
    )
    agent_context: AgentContext = Field(
        default_factory=AgentContext,
        description="Context for the agent (skills, secrets, message suffixes).",
        json_schema_extra={
            SETTINGS_SECTION_METADATA_KEY: SettingsSectionMetadata(
                key="agent_context",
                label="Memory",
                variant="openhands",
            ).model_dump()
        },
    )
    condenser: CondenserSettingsConfig = Field(
        default_factory=LLMSummarizingCondenserSettings,
        description="Condenser settings for the agent.",
        json_schema_extra={
            SETTINGS_SECTION_METADATA_KEY: SettingsSectionMetadata(
                key="condenser",
                label="Condenser",
                variant="openhands",
            ).model_dump()
        },
    )
    verification: VerificationSettings = Field(
        default_factory=VerificationSettings,
        description="Verification settings for the agent critic.",
        json_schema_extra={
            SETTINGS_SECTION_METADATA_KEY: SettingsSectionMetadata(
                key="verification",
                label="Verification",
                variant="openhands",
            ).model_dump()
        },
    )

    @model_validator(mode="before")
    @classmethod
    def _reject_removed_tool_switches(cls, data: Any) -> Any:
        return _reject_removed_settings_input(data)

    @field_validator("condenser", mode="before")
    @classmethod
    def _upgrade_base_condenser_settings(cls, value: Any) -> Any:
        if type(value) is CondenserSettings:
            return LLMSummarizingCondenserSettings.model_validate(value.model_dump())
        return value

    def create_agent(self) -> Agent:
        """纯粹从这些设置构建一个：class:`Agent` 。

        示例：:

            settings = OpenHandsAgentSettings(
                llm=LLM(model="m", api_key="k"),
                tools=[Tool(name="TerminalTool")],
            )
            agent = settings.create_agent()
        """
        from openhands.sdk.agent import Agent
        from openhands.sdk.llm.auth.openai import create_subscription_llm_from_config

        specs = merge_duplicate_tools(resolve_tool_specs(self.tools))
        include_default_tools = [tool.__name__ for tool in BUILT_IN_TOOLS]
        tools: list[Tool] = []
        for spec in specs:
            builtin = effective_builtin_class(spec.name)
            if builtin is None:
                tools.append(spec)
            elif spec.params:
                tools.append(Tool(name=builtin.__name__, params=spec.params))
                if builtin.__name__ in include_default_tools:
                    include_default_tools.remove(builtin.__name__)
            elif builtin.__name__ not in include_default_tools:
                include_default_tools.append(builtin.__name__)

        # 路由工具需要活动元配置文件名称，仅名称 ``include_default_tools`` 路径无法通过
        # 该名称，因此将其添加为
        # ``Tool`` 携带参数的spec。 当没有元配置文件处于活动状态时，该工具将回退到第一个
        # 可用的元配置文件，因此我们仍然连接它。
        #
        if self.enable_classify_and_switch_llm_tool:
            params: dict[str, Any] = {}
            if self.active_meta_profile:
                params["active_meta_profile"] = self.active_meta_profile
            if self.meta_profile:
                params["meta_profile"] = self.meta_profile.model_dump(mode="json")
            if self.meta_profile_llms:
                params["meta_profile_llms"] = self.meta_profile_llms
            if ClassifyAndSwitchLLMTool.__name__ in include_default_tools:
                include_default_tools.remove(ClassifyAndSwitchLLMTool.__name__)
            tools = [
                spec for spec in tools if spec.name != ClassifyAndSwitchLLMTool.__name__
            ]
            tools.append(Tool(name=ClassifyAndSwitchLLMTool.__name__, params=params))

        llm = create_subscription_llm_from_config(self.llm)
        condenser = self.build_condenser(llm)
        return Agent(
            llm=llm,
            tools=tools,
            mcp_config=self.mcp_config,
            include_default_tools=include_default_tools,
            agent_context=self.agent_context,
            persona=self.persona,
            condenser=condenser,
            critic=self.build_critic(),
            tool_concurrency_limit=self.tool_concurrency_limit,
        )

    def build_condenser(self, llm: LLM) -> CondenserBase | None:
        """根据这些设置创建上下文压缩器，如果禁用，则创建 ``None``。"""
        return self.condenser.build_condenser(llm)

    def build_critic(self) -> CriticBase | None:
        """从这些设置创建一个：class:`APIBasedCritic`。

        当批评家被禁用或没有可用的 API 键时返回 ``None``（批评家服务需要身份验证）。

        如果设置了``verification.critic_api_key``，则用于通过批评家服务进行身份验证；
         否则 LLM 的
        ``api_key`` 被重复使用。 这保留了所有手会议代理（LLM）的现有自动配置路径，同
        时允许部署将关键流量路由到不同的提供商（e.g）。 具有自己的凭
        据的 LLM 代理）。

        如果 ``verification.critic_server_url`` 或
        ``verification.critic_model_name`` 被设置，它们会覆盖
        ``APIBasedCritic`` 默认值，允许部署通过自定义端点 (e.g. 一个LLM代理）。
        """
        if not self.verification.critic_enabled:
            return None

        api_key = self.verification.critic_api_key or self.llm.api_key
        if api_key is None:
            return None

        from openhands.sdk.critic.base import IterativeRefinementConfig
        from openhands.sdk.critic.impl.api import APIBasedCritic

        iterative_refinement = None
        if self.verification.enable_iterative_refinement:
            iterative_refinement = IterativeRefinementConfig(
                success_threshold=self.verification.critic_threshold,
                max_iterations=self.verification.max_refinement_iterations,
            )

        overrides: dict[str, Any] = {}
        if self.verification.critic_server_url is not None:
            overrides["server_url"] = self.verification.critic_server_url
        if self.verification.critic_model_name is not None:
            overrides["model_name"] = self.verification.critic_model_name

        return APIBasedCritic(
            api_key=api_key,
            mode=self.verification.critic_mode,
            iterative_refinement=iterative_refinement,
            **overrides,
        )


class ACPAgentSettings(AgentSettingsBase):
    """ACP（智能体客户端协议）智能体的设置。

    ``create_agent()`` 返回一个委托给子进程 ACP 服务器的：class:`ACPAgent`。 ACP 服务
    器管理其自己的系统提示词、工具、MCP
     和（主要）LLM 调用； 这些字段来自
    :class:`OpenHandsAgentSettings` 不适用于此处。

    :attr:`acp_model` 是模型标识。 创建的``ACPAgent``保持其
    自己的指标LLM，因此标题生成可以告诉它永远不可调用。 提供者凭据乘坐对话机密通道 (
    ``request.secrets`` /
    ``agent_context.secrets`` → ``state.secret_registry``)，由提供者的环境变量名称 (:
    attr:
    `api_key_env_var`) 键入。
    """

    agent_kind: Literal["acp"] = Field(  # type: ignore[reportIncompatibleVariableOverride]
        default="acp",
        description=(
            "Discriminator for the ``AgentSettings`` union. ``'acp'`` selects "
            "an ACP-delegating agent."
        ),
    )
    acp_server: ACPServerKind = Field(
        default="claude-code",
        description=(
            "Which ACP-compatible backend to launch. Each choice maps to a "
            "default subprocess command (see ``acp_command`` to override)."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="ACP server",
                prominence=SettingProminence.CRITICAL,
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: SettingsSectionMetadata(
                key="acp",
                label="ACP (Agent Client Protocol)",
                variant="acp",
            ).model_dump(),
        },
    )
    acp_command: list[str] = Field(
        default_factory=list,
        description=(
            "Optional explicit command to launch the ACP subprocess. Leave "
            "empty to use the default for :attr:`acp_server` (e.g. ``npx -y "
            "@agentclientprotocol/claude-agent-acp`` for ``claude-code``). "
            "Must be set when :attr:`acp_server` is ``'custom'``."
        ),
        json_schema_extra={
            # 故意不``depends_on=("acp_server",)``：前端的
            # ``depends_on`` 过滤器执行布尔检查，对于字符串值 ``acp_server``，其计算结果
            # 为 False，并完全隐藏该字段。 如果用户需要提供自定义命令，则可以在 ACP 服务
            # 器页面的“全部”视图中看到 ``acp_command``。
            #
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="ACP command (custom override)",
                prominence=SettingProminence.MINOR,
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: SettingsSectionMetadata(
                key="acp",
                label="ACP (Agent Client Protocol)",
                variant="acp",
            ).model_dump(),
        },
    )
    acp_args: list[str] = Field(
        default_factory=list,
        description="Additional arguments appended to the ACP server command.",
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="ACP extra args",
                prominence=SettingProminence.MINOR,
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: SettingsSectionMetadata(
                key="acp",
                label="ACP (Agent Client Protocol)",
                variant="acp",
            ).model_dump(),
        },
    )
    acp_model: str | None = Field(
        default=None,
        description=(
            "Model identifier for the ACP server to use (e.g. ``'sonnet'`` or "
            "``'gpt-5.5'``). Applied via the protocol — set_config_option(model) "
            "for configOptions-based servers (codex, claude), else "
            "set_session_model. Leave blank to let the server pick its default."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="ACP model",
                prominence=SettingProminence.CRITICAL,
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: SettingsSectionMetadata(
                key="acp",
                label="ACP (Agent Client Protocol)",
                variant="acp",
            ).model_dump(),
        },
    )
    acp_session_mode: str | None = Field(
        default=None,
        description=(
            "Session mode ID (e.g. ``bypassPermissions``). Leave blank to "
            "auto-detect from the ACP server type."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="ACP session mode",
                prominence=SettingProminence.MINOR,
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: SettingsSectionMetadata(
                key="acp",
                label="ACP (Agent Client Protocol)",
                variant="acp",
            ).model_dump(),
        },
    )
    acp_prompt_timeout: float = Field(
        default=1800.0,
        gt=0,
        description=(
            "Inactivity timeout (seconds) for a single ACP prompt() round-trip. "
            "The deadline resets on every update from the ACP server, so a "
            "steadily-progressing agent keeps running; the prompt is only "
            "aborted after this many seconds with no activity at all."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="ACP prompt inactivity timeout (seconds)",
                prominence=SettingProminence.MINOR,
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: SettingsSectionMetadata(
                key="acp",
                label="ACP (Agent Client Protocol)",
                variant="acp",
            ).model_dump(),
        },
    )
    acp_startup_timeout: float = Field(
        default=90.0,
        gt=0,
        description=(
            "Timeout (seconds) for ACP server startup: spawning the "
            "subprocess, the initialize/authenticate handshake, and "
            "new_session()/load_session(). A hard deadline, unlike "
            "acp_prompt_timeout, since startup has no intermediate progress "
            "signal to reset it against."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="ACP startup timeout (seconds)",
                prominence=SettingProminence.MINOR,
            ).model_dump(),
            SETTINGS_SECTION_METADATA_KEY: SettingsSectionMetadata(
                key="acp",
                label="ACP (Agent Client Protocol)",
                variant="acp",
            ).model_dump(),
        },
    )
    mcp_config: dict[str, MCPServer] = Field(
        default_factory=dict,
        description=(
            "MCP servers to make available to the ACP subprocess. Unlike the "
            "OpenHands agent — where these become in-process MCP tools — the "
            "servers are forwarded to the ACP server at session creation and it "
            "owns the connection. Remote (http/sse) servers are only forwarded "
            "when the ACP server advertises support for that transport; stdio "
            "servers (which run inside the runtime) are always forwarded."
        ),
        json_schema_extra={
            SETTINGS_METADATA_KEY: SettingsFieldMetadata(
                label="MCP servers",
                prominence=SettingProminence.MINOR,
                variant="acp",
            ).model_dump(),
        },
    )

    # 编程/面向下游的旋钮，故意在设置表单 UI 中出现不（无 SETTINGS_METADATA_KEY）：部署
    # 应用程序设置它（e.g. 当对话在分组下共享沙箱时），而不是最终用户。 请参阅
    # ``ACPAgent.acp_isolate_data_dir``以获取完整理由。
    #
    acp_isolate_data_dir: bool = Field(
        default=False,
        description=(
            "Give the ACP subprocess a per-conversation CLI data/config root "
            "instead of the shared user HOME. Forwarded to "
            ":attr:`~openhands.sdk.agent.ACPAgent.acp_isolate_data_dir`; off by "
            "default. Enable from the deploying application when several "
            "conversations share one sandbox (see #1019)."
        ),
    )
    # 程序化/下游面向的开关，故意不在设置表单UI（没有SETTINGS_METADATA_KEY）：它是一个下
    # 游应用程序在代码中提供的结构化规格列表，以支持其他ACP CLIs，而不是一个用户字段。
    # 内置提供程序通过默认方式工作。
    #
    acp_file_secrets: list[ACPFileSecretSpec] = Field(
        default_factory=lambda: list(default_acp_file_secrets()),
        description=(
            "Reserved 'file-content' credential secrets the SDK materialises to "
            "disk before launching the ACP subprocess (e.g. Codex auth.json, "
            "Gemini Vertex SA JSON). Defaults to the built-in supported "
            "providers; override to support other ACP servers with different "
            "file-auth schemes."
        ),
    )
    agent_context: AgentContext | None = Field(
        default=None,
        description=(
            "Prompt-only context for the ACP server. ``secrets`` here are "
            "advertised to the agent (names/descriptions) and reach the "
            "subprocess env through ``state.secret_registry``: "
            "``LocalConversation`` seeds ``agent_context.secrets`` into the "
            "registry at conversation init (below ``request.secrets``), so "
            "callers that build the request outside Python (e.g. canvas-local) "
            "are covered too, not just the ``create_request`` path. Provider "
            "credentials belong here (or in ``request.secrets``) keyed by the "
            "provider's env var name."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _reject_removed_llm(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and "llm" in data:
            raise ValueError("ACPAgentSettings.llm was removed; use acp_model instead.")
        return _reject_removed_settings_input(data)

    @property
    def provider_info(self) -> ACPProviderInfo | None:
        """注册表条目用于：attr:`acp_server`，或 ``None`` 条目用于 ``'custom'``。"""
        return get_acp_provider(self.acp_server)

    @property
    def api_key_env_var(self) -> str | None:
        """ACP 子进程期望其 API 键的环境变量名称。

        委托给：data:`~openhands.sdk.settings.acp_providers.ACP_PROVIDERS` 注册表。
        对于
        ``'custom'`` 服务器返回 ``None`` — 在这种情况下，用户完全通过对话机密通道管理
        凭据。
        """
        info = self.provider_info
        return info.api_key_env_var if info is not None else None

    @property
    def base_url_env_var(self) -> str | None:
        """proxy/base-URL 路由的环境变量，如果不支持则为 ``None``。

        委托给：data:`~openhands.sdk.settings.acp_providers.ACP_PROVIDERS` 注册表。
        """
        info = self.provider_info
        return info.base_url_env_var if info is not None else None

    def resolve_acp_command(self) -> list[str]:
        """返回此设置块的有效子进程命令。

        非空时逐字使用：attr:`acp_command`； 否则从：data:
        `~openhands.sdk.settings.acp_providers.ACP_PROVIDERS` 查找默认值。 当：attr:
        `acp_server` 为 ``'custom'`` 但未设置显式命令时引发 ``ValueError``（没有可回
        退的合理默认值）。

        结果通过：meth:`_prefer_pinned_binary` 路由，当固定二进制文件位于 ``PATH`` 时
        ，它会将 ``npx`` 命令交换为固定
        二进制文件（否则为无操作）。
        """
        if self.acp_command:
            command = list(self.acp_command)
        elif self.acp_server == "custom":
            raise ValueError(
                "ACPAgentSettings.acp_command must be set when "
                "acp_server='custom' — there is no default to fall back to"
            )
        else:
            info = get_acp_provider(self.acp_server)
            if info is None:
                raise ValueError(
                    f"No default ACP command for acp_server={self.acp_server!r}"
                )
            command = list(info.default_command)
        return self._prefer_pinned_binary(command)

    @staticmethod
    def _parse_npx_invocation(command: Sequence[str]) -> tuple[str, list[str]] | None:
        """将 ``npx`` 样式的启动命令解析为 ``(package, extra_args)``。

        ``["npx", "-y", "@scope/pkg", "--flag"]`` → ``("@scope/pkg", ["--flag"])``，
        跳过任
        何前导 ``npx`` 标志，例如 ``-y`` / ``--yes``。 退货
        ``None`` 当 * 命令 * 不是 ``npx`` 调用时 (e.g. 已经解析的二进制路径），因此调
        用者保持不变。
        """
        if not command or command[0] != "npx":
            return None
        # 删除前导 npx 标志（-y、--yes、...）以查找包名称。
        rest = list(itertools.dropwhile(lambda arg: arg.startswith("-"), command[1:]))
        if not rest:
            return None
        package, *extra_args = rest
        return package, extra_args

    @staticmethod
    def _npm_package_name(package: str) -> str:
        """从 npm 包规范中删除任何 ``@version`` 说明符。

        ``@scope/pkg@1.2.3`` → ``@scope/pkg``; ``pkg@1.2.3`` → ``pkg``; 未版本化的规
        范将原样返回。
        版本分隔符是
        ``@`` *after* 名称 — 对于范围规范，它是第二个 ``@``（第一个引入范围），因此会
        跳过前导 ``@``。
        """
        start = 1 if package.startswith("@") else 0
        at = package.find("@", start)
        return package[:at] if at != -1 else package

    def _prefer_pinned_binary(self, command: list[str]) -> list[str]:
        """将 ``npx -y <pkg>`` 命令替换为提供商的固定二进制文件。

        当 *command* 是此提供程序包的 ``npx`` 调用并且提供程序的 ``binary_name`` 通过
        ：func:`shutil.which`
        解析时，返回
        ``[binary_name, *extra]``（保留像 Gemini 一样的尾随参数
        ``--acp``) — 运行智能体-服务器镜像的固定包装器，而不是下载 npm-latest。 否则
        返回不变：没有固定的二进制文件（自定义服务器）、不匹配
        /非 npx 命令或二进制文件不存在
        ``PATH``（本地开发）。

        包匹配忽略任何 ``@version`` suffix: the 注册表默认版本锁定（因此，native） 回
        退方案不能向 npm 驱动
        ``latest``但是，客户端仍然可以发送裸包名或不同的包名。 在图像中，无论请求的版
        本如何，固定的二进制文件都代表提供者的包，因此重写仅比较名称。
        """
        info = get_acp_provider(self.acp_server)
        if info is None or info.binary_name is None:
            return command

        default_parsed = self._parse_npx_invocation(info.default_command)
        actual_parsed = self._parse_npx_invocation(command)
        if default_parsed is None or actual_parsed is None:
            return command

        default_pkg, _ = default_parsed
        actual_pkg, extra = actual_parsed
        same_package = self._npm_package_name(actual_pkg) == self._npm_package_name(
            default_pkg
        )
        if not same_package or shutil.which(info.binary_name) is None:
            return command

        return [info.binary_name, *extra]

    def create_agent(self) -> ACPAgent:
        """根据这些设置构建：class:`ACPAgent`。

        子进程命令通过：meth:`resolve_acp_command` 解析，当没有明确指定时，它将：attr
        :`acp_server` 映射到默认值
        `acp_command` 属性已设置。

        :attr:`llm` 未读取：智能体保持默认值 ``acp-managed``
        指标 LLM，设置时用：attr:`acp_model` 重新标记。 凭据供应商机密驱动对话子进程
        端口 (``agent_context.secrets``
         / ``StartConversationRequest.secrets``，通过 ``state.secret_registry``) 根据
         供应商的环境
        变量名称 (:attr:`api_key_env_var`)，并到达注册表。
        """
        from openhands.sdk.agent import ACPAgent

        return ACPAgent(
            acp_command=self.resolve_acp_command(),
            # 将权威提供者密钥携带到智能体：acp_command 本身并不能可靠地反向映射到提供者
            # ，因此消费者 (e.g. 对话 UI 解析品牌标签/型号列表）从
            # ConversationInfo.agent.acp_server 中读取。
            #
            acp_server=self.acp_server,
            acp_args=list(self.acp_args),
            acp_model=self.acp_model,
            acp_session_mode=self.acp_session_mode,
            acp_prompt_timeout=self.acp_prompt_timeout,
            acp_startup_timeout=self.acp_startup_timeout,
            acp_isolate_data_dir=self.acp_isolate_data_dir,
            acp_file_secrets=list(self.acp_file_secrets),
            agent_context=self.agent_context,
            mcp_config=self.mcp_config,
        )


class LLMAgentSettings(OpenHandsAgentSettings):
    """:class:`OpenHandsAgentSettings` 的旧版 ``agent_kind='llm'`` 变体。

    ``LLMAgentSettings`` 是 v1.19.0 重命名之前的公共类名。 公共导入别名（
    ``from openhands.sdk import LLMAgentSettings`` 和
    ``from openhands.sdk.settings import LLMAgentSettings``) 在 v1.24.0 中被删除 — 对
    所有新代码使用
    ：class:`OpenHandsAgentSettings`。

    类本身被保留（可通过
    ``openhands.sdk.settings.model.LLMAgentSettings``），因为它仍然是设置歧视联盟的成
    员：它保留
    ``agent_kind='llm'``，因此已持久化遗留载荷仍然是反序列化，并且 API 损坏检查器与已
    发布的版本相比没有看到任何字段值更改。
    """

    # Keep agent_kind as Literal[LLM] 所以 API-断路器检查器与之前的字段值没有变化 PyPI
    # 发行版（该类作为主要类 agent_kind="llm"). 歧异联合路由 "llm" 载荷这里；
    # validate_agent_settings（）仍然默认为 OpenHandsAgentSettings ("OpenHands").
    #
    agent_kind: Literal["llm"] = Field(  # type: ignore[assignment]
        default="llm",
        description=(
            "Discriminator for the ``AgentSettings`` union. ``'llm'`` selects "
            "the standard LLM-backed agent. Deprecated; use ``'openhands'``."
        ),
    )


def _agent_settings_discriminator(value: Any) -> str:
    """:data:`AgentSettingsConfig` 的鉴别器 — 默认为 ``'openhands'``。

    现有的已持久化载荷早于 ``agent_kind`` 并且仅包含 OpenHands-智能体字段。 将缺失的
    鉴别器视为 ``'openhands'``，可以让载荷无
    需迁移即可进行验证。

    ``'llm'`` 仍然是有效标签，路由到已弃用
    :class:`LLMAgentSettings` 子类。
    """
    if isinstance(value, AgentSettingsBase):
        return value.agent_kind
    if isinstance(value, dict):
        return value.get("agent_kind", "openhands")
    return "openhands"


AgentSettingsConfig = Annotated[
    Annotated[OpenHandsAgentSettings, Tag("openhands")]
    | Annotated[LLMAgentSettings, Tag("llm")]
    | Annotated[ACPAgentSettings, Tag("acp")],
    Discriminator(_agent_settings_discriminator),
]
"""智能体设置变体的可区分联合。

使用：func:`validate_agent_settings` 或：class:`~pydantic.TypeAdapter` 从原始载荷验证
/构造实例。 使用
:func:`default_agent_settings` 用于默认 (LLM-智能体) 形状。

命名为 ``AgentSettingsConfig`` 而不是 ``AgentSettings``，因为旧的具体
``AgentSettings`` 类在其弃用截止日期后被
删除。 将此联合用于接受任何支持的设置变体的字段。
"""


_AGENT_SETTINGS_ADAPTER: TypeAdapter[
    OpenHandsAgentSettings | LLMAgentSettings | ACPAgentSettings
] = TypeAdapter(AgentSettingsConfig)


def validate_agent_settings(
    data: Any,
    *,
    context: Mapping[str, Any] | None = None,
    persisted: bool = False,
) -> OpenHandsAgentSettings | LLMAgentSettings | ACPAgentSettings:
    """加载并验证智能体设置载荷。

    已持久化载荷迁移到验证之前的当前模式版本，包括之前的遗留 ``agent_kind: "llm"`` 载
    荷
    ``OpenHandsAgentSettings`` 重命名。 为存储的数据传递 ``persisted=True``，因此不带
    ``schema_version`` 的载荷将作为旧行迁移，而不是作为请求进行验证。
    """
    if isinstance(data, OpenHandsAgentSettings | ACPAgentSettings):
        return data
    payload = _migrate_agent_settings_payload(data, persisted=persisted)
    # v1->v2 迁移会重命名已弃用 ``agent_kind: 'llm'`` 标记，但仅在推进
    # ``schema_version`` 时进行。 当前版本中已有的载荷保留 ``llm`` 标签并将分派到已弃用
    # ``LLMAgentSettings`` 子类； 无条件规范化，因此加载程序始终返回
    # ``{openhands, acp}`` 变体。
    #
    if payload.get("agent_kind") == "llm":
        payload["agent_kind"] = "openhands"
    return _AGENT_SETTINGS_ADAPTER.validate_python(payload, context=context)


def _merge_patch(base: dict[str, Any], diff: Mapping[str, Any]) -> dict[str, Any]:
    """应用 RFC 7386 JSON 合并补丁。

    嵌套映射递归合并； ``None`` 删除一个键； 所有其他值都会被覆盖。 匹配设置存储使用
    的合并语义，以便调用站点可以在不更改行为的情况下进行委托。
    """
    result = dict(base)
    for key, value in diff.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _merge_patch(result[key], value)
        else:
            result[key] = value
    return result


def apply_agent_settings_diff(
    base: Any,
    diff: Mapping[str, Any] | None,
    *,
    context: Mapping[str, Any] | None = None,
) -> OpenHandsAgentSettings | ACPAgentSettings:
    """将稀疏的智能体设置差异应用于基础，在 ``agent_kind`` 上缩小。

    ``agent_kind`` 是单向窄门，不是转换旋钮：

    * 当 ``diff`` changes ``agent_kind``从  *新鲜* 目标变体的基础。 在交集边界处合并
    得太深，要么失败验证 (ACP'的可选性
    ``agent_context`` 无效 OpenHands或者无声地丢弃传出变体的字段（变体忽略未知键），
    生成一个mongrel行。
    * 当 ``agent_kind`` 未更改或省略时，深度合并变体中的差异（``None`` 根据：func:
    `_merge_patch` 取消设置键）。

    ``base`` 可以是原始已持久化映射或设置实例； 首先对其进行迁移和验证。 合并结果重新
    验证
    :data:`AgentSettingsConfig`，因此返回始终是规范变体。
    这是智能体-settings diff 应用程序的单一所有者； 设置存储应该在此处委托，而不是手
    动进行转储/合并/验证舞蹈。
    """
    base_settings = validate_agent_settings(base, context=context, persisted=True)
    if not diff:
        return base_settings
    new_kind = diff.get("agent_kind")
    if new_kind and new_kind != base_settings.agent_kind:
        merged = _merge_patch({"agent_kind": new_kind}, diff)
    else:
        merged = _merge_patch(
            base_settings.model_dump(mode="json", context={"expose_secrets": True}),
            diff,
        )
    return validate_agent_settings(merged, context=context)


def default_agent_settings() -> OpenHandsAgentSettings:
    """返回默认的：class:`OpenHandsAgentSettings` 实例。

    这是旧的裸 ``AgentSettings()`` 构造函数调用的直接替代 - 自此以来的默认变体是 LLM
    智能体。
    """
    return OpenHandsAgentSettings()


def create_agent_from_settings(
    settings: OpenHandsAgentSettings | ACPAgentSettings,
) -> AgentBase:
    """分派到变体的 ``create_agent()`` 方法。

    返回：class:`~openhands.sdk.agent.Agent` （LLM 变体）或
    :class:`~openhands.sdk.agent.ACPAgent` （ACP 变体）。
    """
    return settings.create_agent()


def export_agent_settings_schema() -> SettingsSchema:
    """导出：data:`AgentSettingsConfig` 联合的组合模式。

    遍历两个变体，用其变体标记每个非共享部分，并返回单个：class:`SettingsSchema`。
    ``agent_kind``判别器故意不作为模式字段**生成
    **——每个变体都有自己的设置页面在GUI，页面在保存时会注入正确的``agent_kind``值。
    部分带有 ``variant`` 标签（
    ``'openhands'``、``'acp'`` 或 ``None`` 表示共享），因此前端可以按页面的变体进行过
    滤。
    """
    llm_schema = OpenHandsAgentSettings.export_schema()
    acp_schema = ACPAgentSettings.export_schema()

    merged_sections: list[SettingsSectionSchema] = []
    merged_by_key: dict[tuple[str, str | None], SettingsSectionSchema] = {}

    def _merge(schema: SettingsSchema, default_variant: str) -> None:
        for section in schema.sections:
            # “一般”是跨变体共享的； 为非共享键打上变体标签，以便 GUI 可以按变体过滤部分
            # 。
            #
            if section.key == _GENERAL_SECTION_KEY and section.variant is None:
                effective_variant: str | None = None
            else:
                effective_variant = section.variant or default_variant

            existing = merged_by_key.get((section.key, effective_variant))
            if existing is None:
                merged = section.model_copy(update={"variant": effective_variant})
                merged_by_key[(section.key, effective_variant)] = merged
                merged_sections.append(merged)
            else:
                # 跨调用相同（键、变体）——按键联合字段。
                seen_keys = {f.key for f in existing.fields}
                for field in section.fields:
                    if field.key not in seen_keys:
                        existing.fields.append(field)

    _merge(llm_schema, default_variant="openhands")
    _merge(acp_schema, default_variant="acp")

    return SettingsSchema(model_name="AgentSettings", sections=merged_sections)


def settings_section_metadata(field: FieldInfo) -> SettingsSectionMetadata | None:
    extra = field.json_schema_extra
    if not isinstance(extra, dict):
        return None

    metadata = extra.get(SETTINGS_SECTION_METADATA_KEY)
    if metadata is None:
        return None
    return SettingsSectionMetadata.model_validate(metadata)


def settings_metadata(field: FieldInfo) -> SettingsFieldMetadata | None:
    extra = field.json_schema_extra
    if not isinstance(extra, dict):
        return None

    metadata = extra.get(SETTINGS_METADATA_KEY)
    if metadata is None:
        return None
    return SettingsFieldMetadata.model_validate(metadata)


_GENERAL_SECTION_KEY = "general"
_GENERAL_SECTION_LABEL = "General"
_GENERAL_SECTION_METADATA = SettingsSectionMetadata(
    key=_GENERAL_SECTION_KEY,
    label=_GENERAL_SECTION_LABEL,
)


def export_settings_schema(model: type[BaseModel]) -> SettingsSchema:
    """导出 Pydantic 设置模型的结构化设置模式。

    返回的模式组合了嵌套模型，并描述了每个导出字段的标签、类型、默认值、依赖项、选择
    项和值是否应被视为机密输入。
    """
    sections: list[SettingsSectionSchema] = []
    sections_by_key: dict[str, SettingsSectionSchema] = {}

    def ensure_section(metadata: SettingsSectionMetadata) -> SettingsSectionSchema:
        section = sections_by_key.get(metadata.key)
        if section is not None:
            return section
        section = SettingsSectionSchema(
            key=metadata.key,
            label=metadata.label or _humanize_name(metadata.key),
            fields=[],
            variant=metadata.variant,
        )
        sections_by_key[metadata.key] = section
        sections.append(section)
        return section

    for field_name, field in model.model_fields.items():
        explicit_section_metadata = settings_section_metadata(field)
        section_metadata = explicit_section_metadata or _GENERAL_SECTION_METADATA
        nested_models = _nested_model_types(field.annotation)

        # 嵌套部分（e.g.、llm、上下文压缩器、critic）
        if explicit_section_metadata is not None and nested_models:
            section_default = field.get_default(call_default_factory=True)
            section = ensure_section(explicit_section_metadata)
            seen_nested_fields: dict[str, SettingsFieldSchema] = {}
            for nested_model in nested_models:
                for nested_key, nested_field in nested_model.model_fields.items():
                    if nested_field.exclude:
                        continue
                    metadata = settings_metadata(nested_field)
                    if metadata is None:
                        continue
                    existing_field = seen_nested_fields.get(nested_key)
                    if existing_field is not None:
                        existing_choice_values = {
                            choice.value for choice in existing_field.choices
                        }
                        for choice in _extract_choices(nested_field.annotation):
                            if choice.value not in existing_choice_values:
                                existing_field.choices.append(choice)
                                existing_choice_values.add(choice.value)
                        continue
                    default_value = None
                    if (
                        isinstance(section_default, BaseModel)
                        and nested_key in type(section_default).model_fields
                    ):
                        default_value = dict(section_default).get(nested_key)
                    field_schema = SettingsFieldSchema(
                        key=f"{explicit_section_metadata.key}.{nested_key}",
                        label=(
                            metadata.label
                            if metadata.label is not None
                            else _humanize_name(nested_key)
                        ),
                        description=nested_field.description,
                        section=section.key,
                        section_label=section.label,
                        value_type=_infer_value_type(nested_field.annotation),
                        default=_normalize_default(default_value),
                        prominence=metadata.prominence,
                        depends_on=[
                            f"{explicit_section_metadata.key}.{dependency}"
                            for dependency in metadata.depends_on
                        ],
                        secret=_contains_secret(nested_field.annotation),
                        choices=_extract_choices(nested_field.annotation),
                        # 字段级变体回退到封闭部分的变体 - 默认情况下，嵌套字段继承其父
                        # 部分的变体。
                        #
                        variant=metadata.variant or section.variant,
                    )
                    seen_nested_fields[nested_key] = field_schema
                    section.fields.append(field_schema)
            continue

        metadata = settings_metadata(field)
        if metadata is None:
            continue

        default_value = field.get_default(call_default_factory=True)
        section = ensure_section(section_metadata)
        section.fields.append(
            SettingsFieldSchema(
                key=field_name,
                label=(
                    metadata.label
                    if metadata.label is not None
                    else _humanize_name(field_name)
                ),
                description=field.description,
                section=section.key,
                section_label=section.label,
                value_type=_infer_value_type(field.annotation),
                default=_normalize_default(default_value),
                prominence=metadata.prominence,
                depends_on=list(metadata.depends_on),
                secret=_contains_secret(field.annotation),
                choices=_extract_choices(field.annotation),
                # 顶级字段：如果设置，则使用其自己的变体，否则回退到封闭部分的变体。
                #
                variant=metadata.variant or section.variant,
            )
        )

    return SettingsSchema(model_name=model.__name__, sections=sections)


def _nested_model_type(annotation: Any) -> type[BaseModel] | None:
    candidates = _nested_model_types(annotation)
    if len(candidates) != 1:
        return None

    return candidates[0]


def _nested_model_types(annotation: Any) -> tuple[type[BaseModel], ...]:
    seen: set[type[BaseModel]] = set()
    models: list[type[BaseModel]] = []
    for candidate in _annotation_options(annotation):
        if (
            isinstance(candidate, type)
            and issubclass(candidate, BaseModel)
            and candidate not in seen
        ):
            seen.add(candidate)
            models.append(candidate)
    return tuple(models)


def _annotation_options(annotation: Any) -> tuple[Any, ...]:
    origin = get_origin(annotation)
    if origin is None or origin is Literal:
        return (annotation,)
    if origin in (list, tuple, set, frozenset, dict):
        return (annotation,)

    options: list[Any] = []
    for arg in get_args(annotation):
        if arg is type(None):
            continue
        options.extend(_annotation_options(arg))
    return tuple(options) or (annotation,)


def _contains_secret(annotation: Any) -> bool:
    return any(option is SecretStr for option in _annotation_options(annotation))


def _infer_value_type(annotation: Any) -> SettingsValueType:
    choices = _choice_values(annotation)
    if choices:
        return _value_type_for_values(choices)

    options = _annotation_options(annotation)
    if all(_is_stringish(option) for option in options):
        return "string"
    if all(option is bool for option in options):
        return "boolean"
    if all(option is int for option in options):
        return "integer"
    if all(option in (int, float) for option in options):
        return "number"
    if all(_is_array_annotation(option) for option in options):
        return "array"
    if all(_is_object_annotation(option) for option in options):
        return "object"
    return "string"


def _is_stringish(annotation: Any) -> bool:
    return annotation in (str, SecretStr, Path)


def _is_array_annotation(annotation: Any) -> bool:
    return get_origin(annotation) in (list, tuple, set, frozenset)


def _is_object_annotation(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is dict:
        return True
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _choice_values(annotation: Any) -> list[SettingsChoiceValue]:
    inner = _annotation_options(annotation)
    if len(inner) != 1:
        return []

    candidate = inner[0]
    origin = get_origin(candidate)
    if origin is Literal:
        return [
            value
            for value in get_args(candidate)
            if isinstance(value, (bool, int, float, str))
        ]
    if isinstance(candidate, type) and issubclass(candidate, Enum):
        return [
            member.value
            for member in candidate
            if isinstance(member.value, (bool, int, float, str))
        ]
    return []


def _value_type_for_values(values: list[SettingsChoiceValue]) -> SettingsValueType:
    if all(isinstance(value, bool) for value in values):
        return "boolean"
    if all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        return "integer"
    if all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in values
    ):
        return "number"
    return "string"


def _extract_choices(annotation: Any) -> list[SettingsChoice]:
    inner = _annotation_options(annotation)
    if len(inner) != 1:
        return []

    candidate = inner[0]
    origin = get_origin(candidate)
    if origin is Literal:
        return [
            SettingsChoice(value=value, label=str(value))
            for value in get_args(candidate)
            if isinstance(value, (bool, int, float, str))
        ]
    if isinstance(candidate, type) and issubclass(candidate, Enum):
        return [
            SettingsChoice(
                value=member.value,
                label=_humanize_name(member.name),
            )
            for member in candidate
            if isinstance(member.value, (bool, int, float, str))
        ]
    return []


def _normalize_default(value: Any) -> Any:
    if isinstance(value, SecretStr):
        return None
    if isinstance(value, Enum):
        return _normalize_default(value.value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _normalize_default(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_normalize_default(item) for item in value]
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    return None


def _humanize_name(name: str) -> str:
    acronyms = {"api", "aws", "id", "llm", "url"}
    words = []
    for part in name.split("_"):
        words.append(part.upper() if part in acronyms else part.capitalize())
    return " ".join(words)
