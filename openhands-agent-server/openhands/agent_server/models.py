from __future__ import annotations

from abc import ABC
from datetime import datetime
from enum import Enum, StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from openhands.sdk.agent.acp_models import ACPModelInfo
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.conversation.conversation_stats import ConversationStats
from openhands.sdk.conversation.request import (  # 重新导出以实现向后兼容
    ACPEnabledAgent as ACPEnabledAgent,
    ConversationConfig as ConversationConfig,
    SendMessageRequest as SendMessageRequest,
    StartChildConversationRequest as StartChildConversationRequest,
    StartChildConversationResponse as StartChildConversationResponse,
    StartConversationRequest as StartConversationRequest,
)
from openhands.sdk.conversation.secret_registry import SecretRegistry
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.conversation.types import ConversationTags
from openhands.sdk.event.base import Event
from openhands.sdk.hooks import HookConfig
from openhands.sdk.llm.message import (  # 再出口
    ImageContent as ImageContent,
    TextContent as TextContent,
)
from openhands.sdk.llm.utils.metrics import MetricsSnapshot
from openhands.sdk.profiles.agent_profile import (
    LaunchedAgentProfile as LaunchedAgentProfile,
)
from openhands.sdk.secret import SecretSource
from openhands.sdk.security.analyzer import SecurityAnalyzerBase
from openhands.sdk.security.confirmation_policy import (
    ConfirmationPolicyBase,
    NeverConfirm,
)
from openhands.sdk.tool.client_tool import ClientToolSpec
from openhands.sdk.utils import OpenHandsUUID, utc_now
from openhands.sdk.utils.models import (
    DiscriminatedUnionMixin,
    OpenHandsModel,
)
from openhands.sdk.workspace.base import BaseWorkspace


class ConversationRuntimeStatus(StrEnum):
    """执行对话的运行时的可用性。"""

    AVAILABLE = "available"
    STARTING = "starting"
    MISSING = "missing"
    OWNERSHIP_LOST = "ownership_lost"
    ERROR = "error"


class ConversationRuntimeError(BaseModel):
    """最新运行时生命周期故障的结构化详细信息。"""

    code: str
    message: str


class ConversationRuntimeInfo(BaseModel):
    """对话的运行时可用性和恢复信息。"""

    runtime_status: ConversationRuntimeStatus
    can_resume: bool
    runtime_error: ConversationRuntimeError | None = None


class ServerErrorEvent(Event):
    """发生服务器级错误时由 Agent Server 发出的事件。

    此事件用于源自 Agent Server 本身的错误，例如 MCP 连接失败、WebSocket 错误或其他基
    础设施问题。 与针对会话级故障的Conversatio
    nErrorEvent不同，此事件表明服务器环境存在问题。
    """

    code: str = Field(description="Code for the error - typically an error type")
    detail: str = Field(description="Details about the error")


class ConversationSortOrder(StrEnum):
    """枚举用于对话排序选项。"""

    CREATED_AT = "CREATED_AT"
    UPDATED_AT = "UPDATED_AT"
    CREATED_AT_DESC = "CREATED_AT_DESC"
    UPDATED_AT_DESC = "UPDATED_AT_DESC"


class EventSortOrder(StrEnum):
    """枚举用于事件排序选项。"""

    TIMESTAMP = "TIMESTAMP"
    TIMESTAMP_DESC = "TIMESTAMP_DESC"


class StoredConversation(ConversationConfig):
    """存储有关对话的详细信息。

    使用服务器分配的字段扩展：class:`ConversationConfig` （智能体-less 共享配置）。
    它故意让不携带``agent``：智能体/运行时状
    态的单一事实来源是
    ``ConversationState`` 已持久化至 ``base_state.json``。 因为
    ``StoredConversation``不是``StartConversationRequest``，智能体不能默默地重新出现
    在``meta.json``中。
    """

    required_runtime_credential_bindings: set[str] = Field(default_factory=set)

    id: OpenHandsUUID
    title: str | None = Field(
        default=None, description="User-defined title for the conversation"
    )
    metrics: MetricsSnapshot | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    forked_from_conversation_id: OpenHandsUUID | None = Field(
        default=None,
        description=(
            "ID of the conversation this one was forked from. ``None`` for "
            "conversations created directly (not via fork)."
        ),
    )
    forked_from_event_id: str | None = Field(
        default=None,
        description=(
            "The ``from_event_id`` branch point this conversation was forked at. "
            "``None`` for conversations not created via fork, or for "
            "whole-conversation forks (no branch slice)."
        ),
    )
    launched_agent_profile: LaunchedAgentProfile | None = Field(
        default=None,
        description=(
            "Provenance snapshot of the agent profile that launched this "
            "conversation. Set at creation when `agent_profile_id` is supplied; "
            "``None`` for conversations started directly with `agent` or "
            "`agent_settings`."
        ),
    )


class _ConversationInfoBase(BaseModel):
    """对话合约共享的公共对话信息字段。"""

    id: UUID = Field(description="Unique conversation ID")
    workspace: BaseWorkspace = Field(
        ...,
        description=(
            "Workspace used by the agent to execute commands and read/write files. "
            "Not the process working directory."
        ),
    )
    persistence_dir: str | None = Field(
        default="workspace/conversations",
        description="Directory for persisting conversation state and events. "
        "If None, conversation will not be persisted.",
    )
    max_iterations: int = Field(
        default=500,
        gt=0,
        description=(
            "Maximum number of iterations the agent can perform in a single run."
        ),
    )
    stuck_detection: bool = Field(
        default=True,
        description="Whether to enable stuck detection for the agent.",
    )
    execution_status: ConversationExecutionStatus = Field(
        default=ConversationExecutionStatus.IDLE
    )
    confirmation_policy: ConfirmationPolicyBase = Field(default=NeverConfirm())
    security_analyzer: SecurityAnalyzerBase | None = Field(
        default=None,
        description="Optional security analyzer to evaluate action risks.",
    )
    activated_knowledge_skills: list[str] = Field(
        default_factory=list,
        description="List of activated knowledge skills name",
    )
    invoked_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Names of progressive-disclosure skills explicitly invoked via the "
            "`invoke_skill` tool."
        ),
    )
    blocked_actions: dict[str, str] = Field(
        default_factory=dict,
        description="Actions blocked by PreToolUse hooks, keyed by action ID",
    )
    blocked_messages: dict[str, str] = Field(
        default_factory=dict,
        description="Messages blocked by UserPromptSubmit hooks, keyed by message ID",
    )
    last_user_message_id: str | None = Field(
        default=None,
        description=(
            "Most recent user MessageEvent id for hook block checks. "
            "Updated when user messages are emitted so Agent.step can pop "
            "blocked_messages without scanning the event log. If None, "
            "hook-blocked checks are skipped (legacy conversations)."
        ),
    )
    leaf_event_id: str | None = Field(
        default=None,
        description=(
            "HEAD of the conversation tree: the parent of the next appended "
            "event. ``None`` means an empty tree (or, for pre-feature "
            "conversations, the linear tail). Moving it via ``navigate`` "
            "re-roots the active branch the agent runs on."
        ),
    )
    stats: ConversationStats = Field(
        default_factory=ConversationStats,
        description="Conversation statistics for tracking LLM metrics",
    )
    secret_registry: SecretRegistry = Field(
        default_factory=SecretRegistry,
        description="Registry for handling secrets and sensitive data",
    )
    agent_state: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary for agent-specific runtime state that persists across "
        "iterations.",
    )
    hook_config: HookConfig | None = Field(
        default=None,
        description=(
            "Hook configuration for this conversation. Includes definitions for "
            "PreToolUse, PostToolUse, UserPromptSubmit, SessionStart, SessionEnd, "
            "and Stop hooks."
        ),
    )

    title: str | None = Field(
        default=None, description="User-defined title for the conversation"
    )
    metrics: MetricsSnapshot | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    # 普通 ``UUID`` （不是 ``OpenHandsUUID``），因此它 JSON 序列化虚线，与上面的 ``id``
    # 字段完全相同 - 客户端必须能够将两者关联起来。
    #
    forked_from_conversation_id: UUID | None = Field(
        default=None,
        description=(
            "ID of the conversation this one was forked from. ``None`` for "
            "conversations created directly (not via fork)."
        ),
    )
    forked_from_event_id: str | None = Field(
        default=None,
        description=(
            "Event ID this conversation was forked at. ``None`` for non-forked "
            "conversations or whole-conversation forks."
        ),
    )
    parent_conversation_id: UUID | None = Field(
        default=None,
        description=(
            "ID of the conversation that owns this one. ``None`` for top-level "
            "conversations."
        ),
    )
    sub_conversation_ids: list[UUID] = Field(
        default_factory=list,
        description=(
            "IDs of conversations naming this one as their parent. Derived from "
            "the server catalog; empty on webhook payloads. Name mirrors the "
            "Cloud API field."
        ),
    )

    tags: ConversationTags = Field(
        default_factory=dict,
        description=(
            "Key-value tags for the conversation. Keys must be lowercase "
            "alphanumeric. Values are arbitrary strings up to 256 characters."
        ),
    )
    current_model_id: str | None = Field(
        default=None,
        description=(
            "Model the agent is actually using for this session. For ACP "
            "agents, this is lifted off ``ACPAgent.current_model_id`` "
            "(populated from the ``models.currentModelId`` field on the "
            "ACP session response, or from ``acp_model`` when the caller "
            "forced an override). May be an opaque alias (e.g. "
            'claude-agent-acp\'s ``"default"``); match it against '
            "``available_models`` to get a display label. ``None`` for older "
            "ACP servers that don't surface the field, or while the agent is "
            "still initializing. Native OpenHands agents leave this ``None`` — "
            "consumers should read ``agent.llm.model`` for those."
        ),
    )
    available_models: list[ACPModelInfo] = Field(
        default_factory=list,
        description=(
            "Models the ACP server offers for this session, lifted off "
            "``ACPAgent.available_models`` (the ``models.availableModels`` "
            "field on the ACP session response). Each entry carries a "
            "``model_id`` plus an optional ``name``/``description``. Surfaced "
            "verbatim so clients can render a model picker and resolve "
            "``current_model_id`` to a display label themselves — the server "
            "does no name curation. Empty for ACP servers that don't surface "
            "the (UNSTABLE) capability and for native OpenHands agents. "
            "Client contract: ``current_model_id`` is NOT guaranteed to be a "
            "member — a forced ``acp_model`` override may name a model absent "
            "from the list — so treat a miss as 'show the raw id'. Some "
            "entries are opaque aliases whose human identity lives in "
            '``description`` (e.g. claude-agent-acp\'s ``"default"`` -> '
            '``"Opus 4.7 with 1M context · ..."``).'
        ),
    )
    supports_runtime_model_switch: bool = Field(
        default=False,
        description=(
            "Whether a live, mid-conversation model switch will be attempted "
            "for this conversation — "
            "tells the inline picker whether to offer a live-switch control. "
            "Mirrors the SDK's switch gate: ``True`` for known switch-capable "
            "providers; ``False`` for unknown/custom ACP servers because their "
            "generic config writes are not guaranteed live-switch primitives. "
            "``False`` for native "
            "OpenHands agents, for a known provider that declares no support, "
            "and before the conversation has started a session."
        ),
    )
    launched_agent_profile: LaunchedAgentProfile | None = Field(
        default=None,
        description=(
            "Provenance snapshot of the agent profile that launched this "
            "conversation. Set at creation when the conversation was started via "
            "``agent_profile_id``; ``None`` for conversations started directly "
            "with ``agent`` or ``agent_settings``. Clients use this to identify "
            "which agent profile is current without fragile settings-comparison."
        ),
    )


class ConversationInfo(_ConversationInfoBase):
    """有关在没有运行时沙箱的情况下本地运行的对话的信息。"""

    agent: AgentBase = Field(
        ...,
        description="The agent running in the conversation.",
    )
    client_tools: list[ClientToolSpec] = Field(
        default_factory=list,
        description=(
            "Client-defined tool specs registered for this conversation. "
            "Surfaced so that a client re-attaching by conversation id can "
            "register the dynamic ClientAction_* action types before syncing "
            "persisted events, avoiding 'Unknown kind' deserialization errors."
        ),
    )
    tool_module_qualnames: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Tool names mapped to importable module qualnames. SDK clients use "
            "this metadata to restore the registrations needed to deserialize "
            "the conversation's tool events when attaching."
        ),
    )
    runtime_info: ConversationRuntimeInfo | None = Field(
        default=None,
        description=(
            "Availability of the execution runtime. Catalog responses populate "
            "this when the hosting server manages runtime lifecycle."
        ),
    )


class ConversationPage(BaseModel):
    items: list[ConversationInfo]
    next_page_id: str | None = None


INCLUDE_SKILLS_PARAM_TITLE = (
    "Whether to include ``agent.agent_context.skills`` in the response. "
    "Default ``false`` (breaking change as of this release): skills are "
    "trimmed to ``[]`` on the wire because no known consumer reads them "
    "from HTTP responses, and a stock agent inlines ~260 KB of skill "
    "content per fetch. Pass ``true`` to opt back into the legacy "
    "full-payload shape — useful only for callers that still rely on "
    "``RemoteConversation.agent.agent_context.skills`` round-tripping "
    "over the wire. The persisted conversation state on disk and the "
    "in-memory runtime copy are untouched either way."
)


def trim_conversation_response_skills(info: ConversationInfo) -> ConversationInfo:
    """返回 ``info``，并将 ``agent.agent_context.skills`` 设置为 ``[]``。

    默认情况下 ** 应用 ** 到发出 ``ConversationInfo`` 的每个路由（搜索、获取、批量获
    取、开始、fork 和已弃用 ACP 等效项）。 仍需
    要旧形状的呼叫者可以选择加入
    with ``?include_skills=true``.

    修剪存在是因为当构造 ``AgentContext`` 时
    with ``load_user_skills=True`` / ``load_public_skills=True``, its
    model_validator 解析整个技能目录（库存设置中约 40 个条目）并内联保留它们。 每条对
    话都会携带 ~260 KB 的技能内容，但实际被 HTTP 响
    应中的智能体-canvas、OpenHands 应用服务器、SDK 示例都忽略掉了
    ``ConversationInfo`` — 他们要么使用进程内
    ``LocalConversation`` 直接或读取其他字段，例如
    ``agent.llm.model``).

    磁盘上的已持久化 ``ConversationState`` 和智能体运行时保存的内存中副本保持不变。

    ``model_copy`` 链就足够了，因为 ``BaseModel.model_copy`` 默认情况下是浅的 - 我们
    用空列表替换叶 ``skills`` 列
    表，而不触及任何其他字段。 返回的对象是一个新鲜的``ConversationInfo``实例； 持有
    输入引用的调用者没有观察到任何突变。
    """
    agent_ctx = getattr(info.agent, "agent_context", None)
    if agent_ctx is None or not agent_ctx.skills:
        return info
    trimmed_agent_context = agent_ctx.model_copy(update={"skills": []})
    trimmed_agent = info.agent.model_copy(
        update={"agent_context": trimmed_agent_context}
    )
    return info.model_copy(update={"agent": trimmed_agent})


class ConfirmationResponseRequest(BaseModel):
    """载荷接受或拒绝待处理的操作。"""

    accept: bool
    reason: str = "User rejected the action."


class Success(BaseModel):
    success: bool = True


class FileUploadResult(Success):
    file_size: int = Field(description="Number of bytes written to the destination")


class EventPage(OpenHandsModel):
    items: list[Event]
    next_page_id: str | None = None


class UpdateSecretsRequest(BaseModel):
    """载荷更新对话中的机密。"""

    secrets: dict[str, SecretSource] = Field(
        description="Dictionary mapping secret keys to values"
    )

    @field_validator("secrets", mode="before")
    @classmethod
    def convert_string_secrets(cls, v: dict[str, Any]) -> dict[str, Any]:
        """将纯字符串机密转换为 StaticSecret 对象。

        此验证器通过自动转换启用向后兼容性：
        - 普通字符串：“机密-值”→StaticSecret(值=SecretStr(“机密-值”))
        - 带值字段的字典：{"value": "机密-value"} → StaticSecret 字典格式
        - 正确的SecretSource对象：不变地通过
        """
        if not isinstance(v, dict):
            return v

        converted = {}
        for key, value in v.items():
            if isinstance(value, str):
                # 将纯字符串转换为 StaticSecret dict 格式
                converted[key] = {
                    "kind": "StaticSecret",
                    "value": value,
                }
            elif isinstance(value, dict):
                if "value" in value and "kind" not in value:
                    # 将带有 value 字段的 dict 转换为 StaticSecret dict 格式
                    converted[key] = {
                        "kind": "StaticSecret",
                        "value": value["value"],
                    }
                else:
                    # 保留现有的 SecretSource 对象或格式正确的字典
                    converted[key] = value
            else:
                # 保持其他类型不变（稍后可能会失败验证）
                converted[key] = value

        return converted


class SetConfirmationPolicyRequest(BaseModel):
    """载荷设置对话的确认策略。"""

    policy: ConfirmationPolicyBase = Field(description="The confirmation policy to set")


class SetSecurityAnalyzerRequest(BaseModel):
    "载荷为对话设置安全分析器"

    security_analyzer: SecurityAnalyzerBase | None = Field(
        description="The security analyzer to set"
    )


class UpdateConversationRequest(BaseModel):
    """载荷更新对话元数据。"""

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="New conversation title",
    )
    tags: ConversationTags | None = Field(
        default=None,
        description=(
            "Key-value tags to set on the conversation. Keys must be lowercase "
            "alphanumeric. Values are arbitrary strings up to 256 characters. "
            "Replaces all existing tags when provided."
        ),
    )

    @field_validator("title")
    @classmethod
    def _reject_blank_title(cls, v: str | None) -> str | None:
        # 服务存储title.strip()； 仅空白标题会将存储的标题删除为“”，而不是像“”那样失败。
        #
        if v is not None and not v.strip():
            raise ValueError("title must not be blank")
        return v


class ForkConversationRequest(BaseModel):
    """载荷分叉对话。"""

    id: UUID | None = Field(
        default=None,
        description="ID for the forked conversation (auto-generated if null)",
    )
    title: str | None = Field(
        default=None,
        max_length=200,
        description="Optional title for the forked conversation",
    )
    tags: ConversationTags | None = Field(
        default=None,
        description=(
            "Optional tags for the forked conversation. Keys must be "
            "lowercase alphanumeric."
        ),
    )
    reset_metrics: bool = Field(
        default=True,
        description=(
            "If true, cost/token stats start fresh on the fork. "
            "If false, metrics are copied from the source."
        ),
    )
    from_event_id: str | None = Field(
        default=None,
        description=(
            "If set, fork only the branch up to and including this event and "
            "set the fork's HEAD there. If null (default), copy the whole "
            "conversation."
        ),
    )


class NavigateConversationRequest(BaseModel):
    """载荷将对话的 HEAD 移至现有事件。"""

    event_id: str | None = Field(
        default=None,
        description=(
            "Event to make the new HEAD, re-rooting the active branch the agent "
            "runs on. All branches stay on disk; this creates no new "
            "conversation. ``None`` selects the empty tree."
        ),
    )


class AskAgentRequest(BaseModel):
    """载荷问智能体一个简单的问题。"""

    question: str = Field(description="The question to ask the agent")


class AskAgentResponse(BaseModel):
    """包含智能体的答案的响应。"""

    response: str = Field(description="The agent's response to the question")


class StartGoalRequest(BaseModel):
    """载荷在对话中启动 ``/goal`` 循环。"""

    objective: str = Field(description="The goal objective to pursue and audit.")
    max_iterations: int = Field(
        default=10, ge=1, description="Maximum audit rounds before giving up."
    )


class AgentResponseResult(BaseModel):
    """智能体对对话的最终响应。

    包含最后一个智能体完成消息或文本响应的文本。 如果智能体尚未产生最终响应，则为空字
    符串。
    """

    response: str = Field(
        description=(
            "The agent's final response text. Extracted from either a "
            "FinishAction message or the last agent MessageEvent. "
            "Empty string if no final response is available."
        )
    )


class BashEventBase(DiscriminatedUnionMixin, ABC):
    """所有 bash 事件类型的基类"""

    id: OpenHandsUUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=utc_now)


class ExecuteBashRequest(BaseModel):
    command: str = Field(description="The bash command to execute")
    cwd: str | None = Field(default=None, description="The current working directory")
    timeout: int = Field(
        default=300,
        description="The max number of seconds a command may be permitted to run.",
    )


class BashCommand(BashEventBase, ExecuteBashRequest):
    pass


class BashOutput(BashEventBase):
    """
    bash 命令的输出。 单个命令可能有多个输出，具体取决于输出的大小。
    """

    command_id: OpenHandsUUID
    order: int = Field(
        default=0, description="The order for this output, sequentially starting with 0"
    )
    exit_code: int | None = Field(
        default=None, description="Exit code None implies the command is still running."
    )
    stdout: str | None = Field(
        default=None, description="The standard output from the command"
    )
    stderr: str | None = Field(
        default=None, description="The error output from the command"
    )


class BashError(BashEventBase):
    code: str = Field(description="Code for the error - typically an error type")
    detail: str = Field(description="Details about the error")


class BashEventSortOrder(Enum):
    TIMESTAMP = "TIMESTAMP"
    TIMESTAMP_DESC = "TIMESTAMP_DESC"


class BashEventPage(OpenHandsModel):
    items: list[BashEventBase]
    next_page_id: str | None = None
