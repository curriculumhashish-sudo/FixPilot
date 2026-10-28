"""``AgentProfile`` — 命名的、带有参考的智能体启动规范。

一个单独的 ``Discriminator("agent_kind")`` + ``Tag`` 并集
:data:`~openhands.sdk.settings.model.AgentSettingsConfig`: 配置文件携带
*参考文献* (``llm_profile_ref`` / ``mcp_server_refs``) 并且在机密处是免费的
REST，而设置联合嵌入已解析的 ``llm`` / ``mcp_config``。 有关分辨率模型，请参阅史诗#
3713。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from openhands.sdk.settings.model import (
    ACPServerKind,
    AgentKind,
    CondenserSettingsConfig,
    CriticMode,
    LLMSummarizingCondenserSettings,
    VerificationSettings,
)
from openhands.sdk.tool import Tool
from openhands.sdk.tool.defaults import (
    drop_retired_tool_switches,
    fold_retired_tool_switches,
    merge_duplicate_tools,
    reject_builtin_params,
)


AGENT_PROFILE_SCHEMA_VERSION = 4


class ProfileVerificationSettings(BaseModel):
    """机密-个人资料的免费评论家/细化政策。

    的非凭据子集
    ：类：`~openhands.sdk.settings.model.VerificationSettings`：``critic_api_key``
    被省略，因此配置文件不包含机密。 批评者重用已解决的 LLM 配置文件的密钥（现有的
    ``critic_api_key=None`` 行为）。
    """

    critic_enabled: bool = False
    critic_mode: CriticMode = "finish_and_message"
    enable_iterative_refinement: bool = False
    critic_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    max_refinement_iterations: int = Field(default=3, ge=1)
    critic_server_url: str | None = None
    critic_model_name: str | None = None


def build_profile_verification(
    v: VerificationSettings,
) -> ProfileVerificationSettings:
    """将 ``VerificationSettings`` 的无机密子集投影到轮廓上。

    掉落 ``critic_api_key`` — 该配置文件不受机密限制； 批评者重用已解决的 LLM 配置文
    件的密钥。 从智能体服务器路由器提升，因此本地种子和云种
    子构建相同的验证。
    """
    return ProfileVerificationSettings(
        critic_enabled=v.critic_enabled,
        critic_mode=v.critic_mode,
        enable_iterative_refinement=v.enable_iterative_refinement,
        critic_threshold=v.critic_threshold,
        max_refinement_iterations=v.max_refinement_iterations,
        critic_server_url=v.critic_server_url,
        critic_model_name=v.critic_model_name,
    )


class AgentProfileInfo(BaseModel):
    """已存储配置文件的摘要投影（无机密实例化）。"""

    id: str | None = None
    name: str
    agent_kind: str = "openhands"
    revision: int | None = None
    llm_profile_ref: str | None = None
    mcp_server_refs: list[str] | None = None


class AgentProfileListResponse(BaseModel):
    """``GET /api/agent-profiles`` 返回的响应正文。"""

    profiles: list[AgentProfileInfo]
    active_agent_profile_id: str | None = None


class AgentProfileBase(BaseModel):
    """每个 ``AgentProfile`` 变体的共享身份 + 出处字段。

    ``extra="forbid"`` 是使联盟具有跨变体安全性的原因：一个带有载荷标记的
    ``agent_kind="acp"``，它还携带
    ``llm_profile_ref``（或一个 OpenHands 载荷携带 ``acp_*``）会被拒绝，而不是无声地
    将外键字段插入到 mongrel 角色中。
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=AGENT_PROFILE_SCHEMA_VERSION, ge=1)
    agent_kind: AgentKind = Field(
        default="openhands",
        description="Discriminator for the agent profile union.",
    )
    id: UUID = Field(
        default_factory=uuid4,
        description=(
            "Stable provenance handle for this profile. Conversations record "
            "this UUID; it never changes, even when the profile is renamed."
        ),
    )
    name: str = Field(
        min_length=1,
        description="Human-facing, renameable key shown in the profile picker.",
    )
    revision: int = Field(
        default=0,
        ge=0,
        description="Monotonic revision counter, bumped on each saved edit.",
    )
    # null = all of the user's MCP servers; [] = none; a non-null list filters
    # 到指定的键。 null 和 [] 它们是故意区别的。 MCP 服务器是用户配置的已持久化因此，这
    # 个引用是安全的：可以引用的所有名称都在这里 ``mcp_config``. 技能是不按照这种方式 ——
    #  它们来自许多懒惰/不完整的来源，因此一个模式选择它们 *排除* (
    # ``OpenHandsAgentProfile.disabled_skills``而是通过一个拒绝列表，而不是一个允许列表
    # ，其中包含可以悬空的名称。 请参阅
    # #4017架构讨论。
    mcp_server_refs: list[str] | None = Field(
        default=None,
        description=(
            "Which of the user's globally configured MCP servers to expose. "
            "null = all; [] = none; a non-null list = filter to the named keys."
        ),
    )
    # 仅名称 - 值存在于用户的机密存储中，并在生成时解析 ``LookupSecret`` 时到达对话，因
    # 此这使配置文件机密保持自由。 与``mcp_server_refs``不同，这里的引用永远不能
    # 悬挂：这是一个适用于任何对话的允许列表
    # 给定，因此没有匹配机密的名称根本不会匹配。
    secret_refs: list[str] | None = Field(
        default=None,
        description=(
            "Which of the user's saved secrets to expose to this agent. "
            "null = all; [] = none; a non-null list = filter to the named keys. "
            "Strict: nothing is added back. An ACP profile must list its own "
            "provider credential to receive it."
        ),
    )


class OpenHandsAgentProfile(AgentProfileBase):
    """``agent_kind="openhands"`` 配置文件 — 按名称引用 LLM 配置文件。

    镜像可配置表面
    :class:`~openhands.sdk.settings.model.OpenHandsAgentSettings`，除了
    具体 ``llm`` 被：attr:`llm_profile_ref` 替换（根据 LLM 配置文件存储解析），
    ``mcp_config`` 被继承的
    ：属性：`~AgentProfileBase.mcp_server_refs`。
    """

    agent_kind: Literal["openhands"] = Field(  # type: ignore[reportIncompatibleVariableOverride]
        default="openhands",
        description=(
            "Discriminator for the ``AgentProfile`` union. ``'openhands'`` "
            "selects the standard built-in OpenHands agent."
        ),
    )
    llm_profile_ref: str = Field(
        min_length=1,
        description=(
            "Name of the saved LLM profile to resolve for this agent. The "
            "profile itself stores no LLM credential — it lives on the "
            "referenced LLM profile."
        ),
    )
    agent: str = Field(
        default="CodeActAgent",
        description="Agent class to build.",
    )
    # 机密-通过构造自由（名称+参数）。
    tools: list[Tool] | None = Field(
        default=None,
        description=(
            "Tool selection for the resolved agent. None (the default) = the "
            "server's standard tool set; [] = an explicitly bare agent; a "
            "non-empty list is used exactly as given."
        ),
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
    system_message_suffix: str | None = Field(
        default=None,
        description="Optional suffix appended to the system prompt.",
    )
    disabled_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Names of server-discovered skills to EXCLUDE from this agent's "
            "prompt — a deny-list over the discovered catalog. [] (the default) "
            "= all discovered skills; a listed name that is absent from the "
            "catalog is simply a no-op, so the field never fails a launch when "
            "the catalog drifts. Replaces the former allow-list ``skill_refs`` "
            "(#4017): skills are discovered from many incomplete sources, so "
            "exclusion is the only selection model that can't dangle."
        ),
    )
    public_skills: list[str] | None = Field(
        default=None,
        description=(
            "Which public-catalog skills to load. null = all; [] = none; a list "
            "= only the named skills, ignoring names the catalog lacks. User and "
            "project skills are not affected, and `disabled_skills` still "
            "applies to every skill."
        ),
    )
    condenser: CondenserSettingsConfig = Field(
        default_factory=LLMSummarizingCondenserSettings,
        description="Condenser settings for the agent.",
    )
    verification: ProfileVerificationSettings = Field(
        default_factory=ProfileVerificationSettings,
        description="Critic/verification policy (secret-free; no critic_api_key).",
    )
    enable_classify_and_switch_llm_tool: bool = Field(
        default=False,
        description=(
            "Enable the built-in route_task_to_model tool, which routes the "
            "task to an LLM profile using the meta-profile named by "
            "`meta_profile_ref`."
        ),
    )
    meta_profile_ref: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Name of the saved meta-profile the routing tool uses. The launch "
            "copies it and the LLM profiles it routes to into the agent, so a "
            "runtime without the stores can still route. null lets the tool "
            "fall back to the first meta-profile in the runtime's store."
        ),
    )
    tool_concurrency_limit: int = Field(
        default=1,
        ge=1,
        description=(
            "Maximum number of tool calls to execute concurrently per agent "
            "step. 1 = sequential (default)."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _reject_removed_tool_switches(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and (
            "enable_sub_agents" in data or "enable_switch_llm_tool" in data
        ):
            raise ValueError(
                "Retired tool switches were removed; select tools instead."
            )
        return data

    @field_validator("tools")
    @classmethod
    def _canonicalize_tools(cls, tools: list[Tool] | None) -> list[Tool] | None:
        if tools is None:
            return None
        reject_builtin_params(tools)
        return merge_duplicate_tools(tools)


class ACPAgentProfile(AgentProfileBase):
    """``agent_kind="acp"`` 配置文件 — 命名 ACP 后端，不存储凭据。

    没有 ``llm_profile_ref`` 也没有嵌入的凭据：ACP 子进程进行自己的模型调用，并且提供
    者的凭据（环境变量名称）是通过以下方式从：attr:
    `acp_server` 派生的
    ：数据：`~openhands.sdk.settings.acp_providers.ACP_PROVIDERS` 注册表。 的
    价值取决于对话机密渠道，而不是个人资料。
    """

    agent_kind: Literal["acp"] = Field(  # type: ignore[reportIncompatibleVariableOverride]
        default="acp",
        description=(
            "Discriminator for the ``AgentProfile`` union. ``'acp'`` selects an "
            "ACP-delegating agent."
        ),
    )
    # 无技能选择领域：ACP智能体拥有自己的工具和提示词构造。 项目技能永远不会达到 1（CLI
    # 读取存储库本身，#4019）； 任何托管技能是否执行都是调用者通过
    # ``resolve_agent_profile`` 的 ``available_skills`` 表达的部署选择。
    #
    acp_server: ACPServerKind = Field(
        default="claude-code",
        description=(
            "Which ACP-compatible backend to launch. The provider's credential "
            "env-var name is derived from this via the ACP_PROVIDERS registry."
        ),
    )
    acp_model: str | None = Field(
        default=None,
        description=(
            "Model identifier for the ACP server (e.g. 'claude-opus-4-8'). "
            "Leave blank to let the server pick its default."
        ),
    )
    acp_session_mode: str | None = Field(
        default=None,
        description=(
            "Session mode ID (e.g. 'bypassPermissions'). Leave blank to "
            "auto-detect from the ACP server type."
        ),
    )
    acp_prompt_timeout: float = Field(
        default=1800.0,
        gt=0,
        description=(
            "Inactivity timeout (seconds) for a single ACP prompt() round-trip; "
            "resets on every update from the server."
        ),
    )
    acp_startup_timeout: float = Field(
        default=90.0,
        gt=0,
        description=(
            "Timeout (seconds) for ACP server startup: spawn, "
            "initialize/authenticate, and new_session()/load_session()."
        ),
    )
    acp_command: str | None = Field(
        default=None,
        description=(
            "Optional explicit command to launch the ACP subprocess. Leave "
            "blank to use the default for ``acp_server``."
        ),
    )
    acp_args: list[str] | None = Field(
        default=None,
        description="Additional arguments appended to the ACP server command.",
    )


class LaunchedAgentProfile(BaseModel):
    """智能体配置文件启动对话时记录的来源快照。

    存储在 ``StoredConversation`` 上并投影到 ``ConversationInfo`` 上，因此 ts-client
    ``deriveSwitchPlan`` 可以识别哪个智能体配置文件是当前的，而无需进行脆弱的设置比较
    。 参见#3720。
    """

    agent_profile_id: UUID = Field(
        description="Stable id of the agent profile that launched the conversation.",
    )
    revision: int = Field(
        ge=0,
        description="Revision of the agent profile at launch time.",
    )
    secret_refs: list[str] | None = Field(
        default=None,
        description=(
            "Secret allow-list captured at launch, also enforced on resume. "
            "null preserves unrestricted behavior for older conversations."
        ),
    )
    llm_profile_ref: str | None = Field(
        default=None,
        description=(
            "Per-launch LLM profile override from `agent_launch_additions`. "
            "null means the profile's own `llm_profile_ref` was used."
        ),
    )

    def allows_secret(self, name: str) -> bool:
        return self.secret_refs is None or name in self.secret_refs


def _agent_profile_discriminator(value: Any) -> str:
    """:data:`AgentProfile` 的鉴别器 — 默认为 ``'openhands'``。

    没有显式 ``agent_kind`` 的载荷被视为标准 OpenHands 变体，镜像
    :func:`~openhands.sdk.settings.model._agent_settings_discriminator`。
    """
    if isinstance(value, AgentProfileBase):
        return value.agent_kind
    if isinstance(value, Mapping):
        return value.get("agent_kind", "openhands")
    return "openhands"


AgentProfile = Annotated[
    Annotated[OpenHandsAgentProfile, Tag("openhands")]
    | Annotated[ACPAgentProfile, Tag("acp")],
    Discriminator(_agent_profile_discriminator),
]
"""智能体-配置文件变体的歧视联合。

使用：func:`validate_agent_profile` （或：class:`~pydantic.TypeAdapter`）从原始载荷验
证/构造实例。
"""


PersistedProfileMigrator = Callable[[dict[str, Any]], dict[str, Any]]


def _migrate_v1_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    """从 v1 配置文件中删除已停用的嵌入式技能配置。"""
    migrated = dict(payload)
    # ``skills`` 已从 v2 中的已持久化轮廓形状中删除。 在严格模型验证之前，必须在此处将其
    # 丢弃，以便可以打开 v1 配置文件并将其保存为其规范的 v2 表示形式。
    #
    migrated.pop("skills", None)
    if (
        migrated.get("agent_kind", "openhands") == "openhands"
        and migrated.get("name") == "default"
        and migrated.get("revision", 0) == 0
        and migrated.get("tools") == []
    ):
        migrated["tools"] = None
    migrated["schema_version"] = 2
    return migrated


def _migrate_v2_to_v3(payload: dict[str, Any]) -> dict[str, Any]:
    """将退役的工具开关折叠到 ``tools`` 中。"""
    if payload.get("agent_kind", "openhands") == "openhands":
        migrated = fold_retired_tool_switches(payload)
    else:
        migrated = drop_retired_tool_switches(payload)
    migrated["schema_version"] = 3
    return migrated


def _migrate_v3_to_v4(payload: dict[str, Any]) -> dict[str, Any]:
    """丢弃 v3 保存的已停用的开关输入。"""
    migrated = drop_retired_tool_switches(payload)
    migrated["schema_version"] = 4
    return migrated


_AGENT_PROFILE_MIGRATIONS: dict[int, PersistedProfileMigrator] = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
}


def _apply_persisted_migrations(payload: dict[str, Any]) -> dict[str, Any]:
    """将 ``AgentProfile`` 载荷增加到当前模式。"""
    migrated = dict(payload)
    version_raw = migrated.get("schema_version")
    if version_raw is None:
        migrated["schema_version"] = AGENT_PROFILE_SCHEMA_VERSION
        version = AGENT_PROFILE_SCHEMA_VERSION
    elif isinstance(version_raw, int) and not isinstance(version_raw, bool):
        version = version_raw
    else:
        raise TypeError(
            "AgentProfile schema_version must be an integer, got "
            f"{type(version_raw).__name__}."
        )

    if version < 0:
        raise ValueError("AgentProfile schema_version must be non-negative.")
    if version > AGENT_PROFILE_SCHEMA_VERSION:
        raise ValueError(
            f"AgentProfile schema_version {version} is newer than supported "
            f"version {AGENT_PROFILE_SCHEMA_VERSION}."
        )

    while version < AGENT_PROFILE_SCHEMA_VERSION:
        migrate = _AGENT_PROFILE_MIGRATIONS.get(version)
        if migrate is None:
            raise ValueError(
                f"No migration registered for AgentProfile schema_version {version}."
            )
        migrated = migrate(dict(migrated))
        next_version = migrated.get("schema_version")
        if not isinstance(next_version, int) or isinstance(next_version, bool):
            raise ValueError(
                f"Migration for AgentProfile schema_version {version} did not "
                "produce a valid integer schema_version."
            )
        if next_version <= version:
            raise ValueError(
                f"Migration for AgentProfile schema_version {version} did not "
                "advance the schema_version."
            )
        version = next_version

    return migrated


_AGENT_PROFILE_ADAPTER: TypeAdapter[OpenHandsAgentProfile | ACPAgentProfile] = (
    TypeAdapter(AgentProfile)
)


def validate_agent_profile(
    data: Any,
    *,
    context: Mapping[str, Any] | None = None,
) -> OpenHandsAgentProfile | ACPAgentProfile:
    """加载并验证 ``AgentProfile`` 载荷，缩小范围 ``agent_kind``。

    已经验证的实例不变地通过。 原始映射会迁移到当前模式版本，然后进行验证
    :data:`AgentProfile`，因此返回始终是规范变体。
    """
    if isinstance(data, OpenHandsAgentProfile | ACPAgentProfile):
        return data
    if isinstance(data, BaseModel):
        payload = data.model_dump(mode="json")
    elif isinstance(data, Mapping):
        payload = dict(data)
    else:
        raise TypeError("AgentProfile payload must be a mapping or BaseModel.")
    payload = _apply_persisted_migrations(payload)
    return _AGENT_PROFILE_ADAPTER.validate_python(payload, context=context)


def safe_validation_error_detail(exc: ValidationError) -> list[dict[str, Any]]:
    """来自失败配置文件验证的 422 的 FastAPI 形 ``detail``。

    每个错误的表面 ``loc``/``type``/``msg``。 该配置文件没有机密标记字段 ——
    ``skills[].mcp_tools`` 在 #4017
    中被移除，而 ``disabled_skills`` 拒绝列表仅包含 * 名 * —— 因此，完整的验证消息是
    安全返回的，客户端需要它来了解 * 为什么 * 保存失
    败 (e.g。 无效的 ``acp_server`` 值）。 ``input`` 仍然
    dropped: 它与整个被拒绝的载荷相呼应，这是有噪音的并且不需要
    来解释错误。 形状类似于 FastAPI 的请求-验证 ``detail``（错误对象列表），因此路由
    器可以将其直接传递给 ``HTTPException``。 从
    智能体服务器路由器提升，因此本地路由器和云路由器的行为相同。
    """
    return [
        {"loc": list(err["loc"]), "type": str(err["type"]), "msg": str(err["msg"])}
        for err in exc.errors()
    ]
