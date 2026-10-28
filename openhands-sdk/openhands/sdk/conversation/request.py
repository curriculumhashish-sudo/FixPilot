"""对话请求模型。

这些类型定义了用于启动对话并与对话交互的载荷。 它们位于 SDK 中，以便
``ConversationSettings`` 可以引用它们，而无需跨包依赖于智能体服务器。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, cast
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    field_serializer,
    model_validator,
)

from openhands.sdk.agent.acp_agent import ACPAgent as ACPAgent
from openhands.sdk.agent.agent import Agent as Agent
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.conversation.message_request import (
    SendMessageRequest as SendMessageRequest,
)
from openhands.sdk.conversation.types import (
    ConversationObservabilityMetadata,
    ConversationObservabilitySpanName,
    ConversationObservabilityTags,
    ConversationTags,
)
from openhands.sdk.hooks import HookConfig
from openhands.sdk.plugin import PluginSource
from openhands.sdk.secret import SecretSource
from openhands.sdk.security.analyzer import SecurityAnalyzerBase
from openhands.sdk.security.confirmation_policy import (
    ConfirmationPolicyBase,
    NeverConfirm,
)
from openhands.sdk.settings.model import (
    DEFAULT_WORKTREE_BRANCH_PREFIX,
    DOCKER_MEMORY_PATTERN,
    GIT_BRANCH_PREFIX_PATTERN,
    GIT_REF_PATTERN,
    MIN_CONTAINER_CPUS,
    ConversationRuntime,
    WorktreeBase,
    validate_agent_settings,
)
from openhands.sdk.skills import Skill
from openhands.sdk.subagent.schema import AgentDefinition
from openhands.sdk.tool.client_tool import ClientToolSpec
from openhands.sdk.utils.models import kind_of
from openhands.sdk.workspace import LocalWorkspace


# ---------------------------------------------------------------------------
# 帮助程序类型别名
# ---------------------------------------------------------------------------

ACPEnabledAgent = Annotated[
    Annotated[Agent, Tag("Agent")] | Annotated[ACPAgent, Tag("ACPAgent")],
    Discriminator(kind_of),
]
"""受歧视联合：常规智能体或 ACP 功能智能体。"""


# ---------------------------------------------------------------------------
# 请求型号
# ---------------------------------------------------------------------------


class StartChildConversationRequest(BaseModel):
    """载荷在与其父级相同的后端启动子级对话。

    由 ``start_child_conversation`` 工具发送到一个子启动端点：默认情况下，智能体-服务
    器通过
    ``POST /api/conversations/{id}/children``，或者由托管父级的后端提供的等效启动器。
    """

    task: str = Field(
        min_length=1,
        description=(
            "Self-contained brief delivered to the child as its first user message."
        ),
    )
    title: str | None = Field(
        default=None, description="Optional title for the child conversation."
    )
    isolation: Literal["worktree", "shared"] = Field(
        default="worktree",
        description=(
            "Workspace isolation for the child. 'worktree' runs it in a git "
            "worktree carved from the parent's workspace when that workspace is a "
            "git repository with a usable base commit; otherwise it shares the "
            "parent's directory. 'shared' always uses the parent's directory. "
            "Backends that manage workspaces themselves may ignore this."
        ),
    )


class StartChildConversationResponse(BaseModel):
    """子对话启动的结果，返回给父级智能体。"""

    conversation_id: UUID
    parent_conversation_id: UUID
    status: str = Field(description="Initial launch status reported by the backend.")
    title: str | None = None
    url: str | None = Field(
        default=None,
        description="Link to the child conversation, when the backend knows it.",
    )
    workspace: str | None = Field(
        default=None, description="Working directory of the child, when known."
    )
    isolation: Literal["worktree", "shared"] | None = Field(
        default=None, description="Workspace isolation actually applied, when known."
    )


class AgentLaunchAdditions(BaseModel):
    """在智能体解析后添加部署上下文。"""

    model_config = ConfigDict(extra="forbid")

    system_message_suffix_append: str | None = Field(
        default=None,
        max_length=32768,
        description=(
            "Deployment-controlled text appended to the resolved agent's "
            "system-message suffix."
        ),
    )
    skills: list[Skill] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description=(
            "Deployment-supplied skills merged into the resolved agent's "
            "context. For a client that ships its own skill catalog and so "
            "cannot rely on the server's: an ``agent_profile_id`` launch sends "
            "no ``agent_settings``, leaving it no other way to supply them. "
            "Merged by name — a skill the resolved agent already carries wins, "
            "and the profile's ``disabled_skills`` deny-list still applies, so "
            "this cannot reintroduce something the profile turned off. None "
            "(the default) adds nothing."
        ),
    )
    llm_profile_ref: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "LLM profile to launch an OpenHands Agent Profile with instead of "
            "its own `llm_profile_ref`. Recorded in `launched_agent_profile`; "
            "the stored profile is not modified. Only valid with "
            "`agent_profile_id`."
        ),
    )


class ConversationContainerOptions(BaseModel):
    """对话容器的资源。

    只有 Docker 运行时在创建会话容器时应用它们； 本地对话会忽略它们。 未设置的字段保
    留服务器配置的限制； 一套取代它并且不受它限制。
    """

    model_config = ConfigDict(extra="forbid")

    memory: str | None = Field(
        default=None,
        pattern=DOCKER_MEMORY_PATTERN,
        description=(
            "Container memory limit in `docker run --memory` syntax; replaces "
            "the server's limit and is not capped by it."
        ),
    )
    cpus: float | None = Field(
        default=None,
        ge=MIN_CONTAINER_CPUS,
        description=(
            "Number of CPUs the container may use (`docker run --cpus`); "
            "replaces the server's limit and is not capped by it."
        ),
    )
    browser: bool = Field(
        default=True,
        description=(
            "False turns the browser off. True cannot turn it on for an image "
            "without one."
        ),
    )


class ConversationWorktreeOptions(BaseModel):
    """服务器如何创建对话的工作树 (``worktree=True``)。"""

    model_config = ConfigDict(extra="forbid")

    base: WorktreeBase = Field(
        default="default_branch",
        description="What the worktree branches from; `ref` uses `ref`.",
    )
    ref: str | None = Field(
        default=None,
        pattern=GIT_REF_PATTERN,
        description="Branch, tag or commit to branch from when `base` is `ref`.",
    )
    branch_prefix: str = Field(
        default=DEFAULT_WORKTREE_BRANCH_PREFIX,
        pattern=GIT_BRANCH_PREFIX_PATTERN,
        description="Start of the worktree's branch name; the conversation id ends it.",
    )

    @model_validator(mode="after")
    def _ref_for_ref_base(self) -> ConversationWorktreeOptions:
        if self.base == "ref" and self.ref is None:
            raise ValueError("A `ref` base needs a `ref`")
        return self


class ConversationConfig(BaseModel):
    """共享对话配置 — 除智能体之外的所有内容。

    这是：class:`StartConversationRequest` 的共同基础（它添加了
    ``agent``/``agent_settings``/``agent_profile_id`` 系列）和智能体-服务器的
    ``StoredConversation`` （它执行不持久化智能体 - 智能体的单一事实来源是
    ``ConversationState`` /
    ``base_state.json``). 智能体不在这一基底上保持，这是让重复结构变得不可能，而不是
    一个审查者需要记住排除的东西。
    """

    workspace: LocalWorkspace = Field(
        ...,
        description="Working directory for agent operations and tool execution.",
    )
    worktree: bool = Field(
        default=False,
        description=(
            "If true and the workspace is already inside a git repository, create "
            "a dedicated git worktree for this conversation under "
            "`/tmp/conversation-worktrees/<conversation_id>/<project_name>`."
        ),
    )
    worktree_options: ConversationWorktreeOptions | None = Field(
        default=None,
        description="How the worktree is created (`worktree=True`); unset: defaults.",
    )
    conversation_id: UUID | None = Field(
        default=None,
        description=(
            "Optional conversation ID. If not provided, a random UUID will be "
            "generated."
        ),
    )
    parent_conversation_id: UUID | None = Field(
        default=None,
        description=(
            "Optional ID of an existing conversation that owns this one. The "
            "parent must already exist and share this conversation's workspace."
        ),
    )
    confirmation_policy: ConfirmationPolicyBase = Field(
        default=NeverConfirm(),
        description="Controls when the conversation will prompt the user before "
        "continuing. Defaults to never.",
    )
    security_analyzer: SecurityAnalyzerBase | None = Field(
        default=None,
        description="Optional security analyzer to evaluate action risks.",
    )
    initial_message: SendMessageRequest | None = Field(
        default=None, description="Initial message to pass to the LLM"
    )
    max_iterations: int = Field(
        default=500,
        ge=1,
        description="If set, the max number of iterations the agent will run "
        "before stopping. This is useful to prevent infinite loops.",
    )
    stuck_detection: bool = Field(
        default=True,
        description="If true, the conversation will use stuck detection to "
        "prevent infinite loops.",
    )
    secrets: dict[str, SecretSource] = Field(
        default_factory=dict,
        description="Secrets available in the conversation",
    )
    secrets_encrypted: bool = Field(
        default=False,
        description=(
            "If true, indicates that secret values in the agent configuration "
            "are cipher-encrypted and should be decrypted by the server before "
            "use. This enables secure round-tripping of settings through "
            "untrusted clients (e.g., frontend) that received encrypted values "
            "via the X-Expose-Secrets header. "
            "Flow: client calls GET /api/settings with X-Expose-Secrets: encrypted "
            "to receive cipher-encrypted secrets, then passes them in the agent "
            "config with secrets_encrypted=True so the server can decrypt them."
        ),
    )
    tool_module_qualnames: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Mapping of tool names to their module qualnames from the client's "
            "registry. These modules will be dynamically imported on the server "
            "to register the tools for this conversation."
        ),
    )
    client_tools: list[ClientToolSpec] = Field(
        default_factory=list,
        description=(
            "Tools defined by the client via JSON spec. These tools have "
            "no server-side executor — when the agent calls them, an "
            "ActionEvent is emitted over the WebSocket and the client "
            "handles execution. The SDK returns an acknowledgment "
            "observation immediately."
        ),
    )
    agent_launch_additions: AgentLaunchAdditions | None = Field(
        default=None,
        description=(
            "Deployment context applied after agent or Agent Profile "
            "resolution. The stored Agent Profile is not modified."
        ),
    )
    agent_definitions: list[AgentDefinition] = Field(
        default_factory=list,
        description=(
            "Agent definitions from the client's registry. These are "
            "registered on the server so that task tools "
            "can see user-registered subagents."
        ),
    )
    plugins: list[PluginSource] | None = Field(
        default=None,
        description=(
            "List of plugins to load for this conversation. Plugins are loaded "
            "and their skills/MCP config are merged into the agent. "
            "Hooks are extracted and stored for runtime execution."
        ),
    )
    hook_config: HookConfig | None = Field(
        default=None,
        description=(
            "Optional hook configuration for this conversation. Hooks are shell "
            "scripts that run at key lifecycle events (PreToolUse, PostToolUse, "
            "UserPromptSubmit, Stop, etc.). If both hook_config and plugins are "
            "provided, they are merged with explicit hooks running before plugin "
            "hooks."
        ),
    )
    tags: ConversationTags = Field(
        default_factory=dict,
        description=(
            "Key-value tags for the conversation. Keys must be lowercase "
            "alphanumeric. Values are arbitrary strings up to 256 characters."
        ),
    )
    user_id: str | None = Field(
        default=None,
        description=(
            "Optional user ID supplied by the hosting deployment, used to "
            "correlate this conversation with the identity that deployment "
            "already established. When set it is passed to "
            "Laminar.set_trace_user_id() so traces can be queried by user, "
            "and — where a host has enabled product analytics — it is reused "
            "verbatim as the analytics correlation id so events attach to the "
            "existing person rather than creating a duplicate identity. It is "
            "never generated by the SDK, and is omitted entirely when unset."
        ),
    )
    observability_metadata: ConversationObservabilityMetadata = Field(
        default_factory=dict,
        description=(
            "Trace-level metadata to attach to observability backends. Values must "
            "be scalars or homogeneous scalar lists supported by OpenTelemetry."
        ),
    )
    observability_tags: ConversationObservabilityTags = Field(
        default_factory=list,
        description="Tags to attach to the conversation root observability span.",
    )
    observability_span_name: ConversationObservabilitySpanName = Field(
        default="conversation",
        description=(
            "Optional named child span to emit under the conversation root. Use "
            "stable, low-cardinality names because observability backends may use "
            "span names for grouping or signal routing."
        ),
    )
    observability_parent_span_context: str | None = Field(
        default=None,
        description=(
            "Serialized parent span context used to attach this conversation to "
            "an upstream automation or integration trace."
        ),
    )

    autotitle: bool = Field(
        default=True,
        description=(
            "If true, automatically generate a title for the conversation from "
            "the first user message. Precedence: title_llm_profile (if set and "
            "loads) → agent.llm → message truncation."
        ),
    )
    title_llm_profile: str | None = Field(
        default=None,
        description=(
            "Optional LLM profile name for title generation. If set, the LLM "
            "is loaded from LLMProfileStore (~/.openhands/profiles/) and used "
            "for LLM-based title generation. This enables using a fast/cheap "
            "model for titles regardless of the agent's main model. If not "
            "set (or profile loading fails), title generation falls back to "
            "the agent's LLM."
        ),
    )
    prompt: str | None = Field(
        default=None,
        max_length=2000,
        description=(
            "Optional prompt that replaces the default title-generation user "
            "message. Use {conversation_content} to place the first user "
            "message and {max_length} to place the title length limit. If the "
            "conversation placeholder is omitted, the message is appended "
            "automatically. Empty or unset values use the default prompt."
        ),
    )


class StartConversationRequest(ConversationConfig):
    """载荷创建一个新对话。

    使用智能体源扩展：class:`ConversationConfig`：存储的智能体配置文件 (
    ``agent_profile_id``)、解析的智能体设置 (
    ``agent_settings``) 或 ``agent`` 内置代码。 服务器在启动时将源转换为对话的智能体
    ； 该模型仅检查是否给出了一个来源。

    Note: 智能体根据 * 请求 * 存在于此，故意不存在
    ``ConversationConfig``. 已持久化记录 (``StoredConversation``) 不包含智能体 — 它的
    唯一事实来源是
    ``ConversationState`` /
    ``base_state.json``.
    """

    agent_settings: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Reference-free agent settings, validated with the AgentSettingsBase "
            "`agent_kind` discriminator. The server builds the agent from them "
            "at launch. Ignored when `agent` is set."
        ),
    )
    agent_profile_id: UUID | None = Field(
        default=None,
        description=(
            "Stored Agent Profile to launch. The server resolves it with its own "
            "stores. Mutually exclusive with the other agent sources."
        ),
    )
    agent: AgentBase = Field(default=cast(AgentBase, None))
    conversation_runtime: ConversationRuntime | None = Field(
        default=None,
        description=(
            "Runtime that executes this conversation. Unset uses the server's "
            "configured `conversation_runtime`; another value is only accepted "
            "when the server lists it in `available_conversation_runtimes`."
        ),
    )
    container: ConversationContainerOptions | None = Field(
        default=None,
        description="Resources for the conversation's container (Docker runtime).",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_agent_source(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # 明确的 null 意味着“不是这个来源”； ``agent`` 不可为空
        # type of its own.
        payload = {
            name: value
            for name, value in data.items()
            if value is not None or name not in ("agent", "agent_settings")
        }
        other_sources = [
            name
            for name in ("agent", "agent_settings")
            if payload.get(name) is not None
        ]
        if payload.get("agent_profile_id") is not None and other_sources:
            raise ValueError(
                "`agent_profile_id` is mutually exclusive with "
                + ", ".join(f"`{name}`" for name in other_sources)
            )
        if payload.get("agent") is not None:
            payload["agent_settings"] = None
        if payload.get("agent") is None and payload.get("agent_settings") is not None:
            try:
                validate_agent_settings(payload["agent_settings"])
            except (TypeError, ValueError) as exc:
                raise ValueError(str(exc)) from exc
        elif isinstance(payload.get("agent"), dict):
            agent_payload = dict(payload["agent"])
            if "kind" not in agent_payload and "llm" in agent_payload:
                agent_payload["kind"] = "Agent"
            payload["agent"] = agent_payload
        return payload

    @model_validator(mode="after")
    def _require_agent(self) -> StartConversationRequest:
        has_profile = self.agent_profile_id is not None
        if not has_profile and self.agent is None and self.agent_settings is None:
            raise ValueError(
                "One of `agent`, `agent_settings`, or `agent_profile_id` must be"
                " provided"
            )
        additions = self.agent_launch_additions
        if additions is not None and additions.llm_profile_ref and not has_profile:
            raise ValueError(
                "`agent_launch_additions.llm_profile_ref` requires `agent_profile_id`"
            )
        return self

    @field_serializer("agent", mode="wrap")
    def _serialize_agent(self, value: AgentBase | None, handler: Any) -> Any:
        if value is None:
            return None
        return handler(value)
