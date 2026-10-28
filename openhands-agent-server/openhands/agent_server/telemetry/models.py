"""用于产品分析的版本化、允许的诊断事件合同。

Pydantic模型在这里被声明为冻结模型，其中每个字段都是*约束*的标量。 这是故意的：普通的
 ``str`` 字段可以保存提示词、回溯或 API 键，因此不会键入属性字
段 ``str``、``Any``、``dict`` 或 ``list``。 因此，泄漏变成了构建时：class:
`ValidationError` 而不是审阅者必须注意到
的事情。

唯一的 intentional exception 是：attr:`DiagnosticEvent.distinct_id`，它保留了调用者提
供的 ``user_id``，
因此事件与托管部署已拥有的身份相关联。 它被记录为
pass-through and excluded from the "no bare str" rule by design, not by
监督。

该模块不得导入任何分析供应商 SDK。
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from openhands.agent_server.telemetry_types import DeploymentKind


TELEMETRY_SCHEMA_VERSION: Final[int] = 1

SafeToken = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_.:\-]{0,63}$")]
"""小写枚举-ish token：``finished``、``anthropic``、``0-5s``。"""

SafeIdentifier = Annotated[
    str,
    StringConstraints(
        max_length=96,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*([.:][A-Za-z_][A-Za-z0-9_]*)*$",
    ),
]
"""点线 Python 标识符：``ValueError``、``litellm:RateLimitError``。

刻意 * 比一般 token 更严格 * — 没有破折号、空格、斜线或
``@``. 这就排除了形状机密和路径：一个API键（``sk-ant-api03-…``）和一个文件系统路径都
失败了这个模式，因此即使未来的调用者传递一个，也无法占用
``error_class``字段。
"""

VersionToken = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.+\-/]{0,63}$")
]
"""版本标识符：``1.36.1``、``refs/heads/main``、``unknown``。

与：data:`SafeIdentifier` 分开，因为版本合法地以数字开头并包含点、破折号和斜杠。 这些
值来自
``importlib.metadata`` 和构建时环境变量，绝不来自用户输入。
"""

Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{16,64}$")]
"""由：mod:`.sanitizer` 生成的小写十六进制摘要。"""

Bucket = SafeToken
"""分桶大小，例如 ``11-50``。 从未计数。"""


class EventName(StrEnum):
    """稳定的事件名称。 连线值是成员值。"""

    SERVER_STARTED = "agent_server.server_started"
    SERVER_STOPPED = "agent_server.server_stopped"
    CONVERSATION_STARTED = "agent_server.conversation_started"
    CONVERSATION_CREATED = "agent_server.conversation_created"
    CONVERSATION_FINISHED = "agent_server.conversation_finished"
    CONVERSATION_FAILED = "agent_server.conversation_failed"
    CONVERSATION_ERROR = "agent_server.conversation_error"
    REQUEST_FAILED = "agent_server.request_failed"


ErrorCategory = Literal[
    "llm_auth",
    "llm_rate_limit",
    "llm_timeout",
    "llm_context_window",
    "llm_bad_request",
    "tool_execution",
    "mcp",
    "workspace_io",
    "git",
    "network",
    "config",
    "cancelled",
    "internal",
    "unknown",
]

ERROR_CATEGORY_BY_CLASS_NAME: Final[dict[str, ErrorCategory]] = {
    "AuthenticationError": "llm_auth",
    "PermissionDeniedError": "llm_auth",
    "RateLimitError": "llm_rate_limit",
    "APITimeoutError": "llm_timeout",
    "Timeout": "llm_timeout",
    "TimeoutError": "llm_timeout",
    "ContextWindowExceededError": "llm_context_window",
    "BadRequestError": "llm_bad_request",
    "UnprocessableEntityError": "llm_bad_request",
    "APIError": "network",
    "APIConnectionError": "network",
    "ServiceUnavailableError": "network",
    "InternalServerError": "network",
    "ToolExecutionError": "tool_execution",
    "ToolNotFoundError": "tool_execution",
    "MCPError": "mcp",
    "McpError": "mcp",
    "FileNotFoundError": "workspace_io",
    "PermissionError": "workspace_io",
    "IsADirectoryError": "workspace_io",
    "NotADirectoryError": "workspace_io",
    "OSError": "workspace_io",
    "IOError": "workspace_io",
    "GitCommandError": "git",
    "InvalidGitRepositoryError": "git",
    "ConnectionError": "network",
    "ConnectError": "network",
    "ReadTimeout": "network",
    "HTTPStatusError": "network",
    "ClientConnectorError": "network",
    "ValidationError": "config",
    "ValueError": "config",
    "KeyError": "config",
    "TypeError": "internal",
    "CancelledError": "cancelled",
    "KeyboardInterrupt": "cancelled",
}


class RuntimeProperties(BaseModel):
    """有关发出事件的进程的粗略的、非识别性的事实。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    server_version: VersionToken
    sdk_version: VersionToken
    tools_version: VersionToken
    build_git_sha: VersionToken
    build_git_ref: VersionToken
    python_version: SafeToken
    platform: SafeToken
    deferred_init: bool
    deployment_kind: DeploymentKind = "local"
    source: Literal["openhands-agent-server"] = "openhands-agent-server"


class _BaseProperties(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ServerLifecycleProperties(_BaseProperties):
    kind: Literal["server_lifecycle"] = "server_lifecycle"


class ConversationStartedProperties(_BaseProperties):
    kind: Literal["conversation_started"] = "conversation_started"

    conversation_ref: Digest
    llm_model_family: SafeToken
    agent_kind: SafeToken
    tool_count: int = Field(ge=0)
    is_fork: bool
    has_agent_profile: bool
    workspace_kind: SafeToken
    confirmation_policy: SafeToken
    is_automation: bool = False


class ConversationOutcomeProperties(_BaseProperties):
    """最终结果。 数量级是桶装的，而不是原始的。

    与时间戳连接的原始计数是一个重新识别向量，因此持续时间/迭代/令牌/成本都被报告为粗
    桶。
    """

    kind: Literal["conversation_outcome"] = "conversation_outcome"

    conversation_ref: Digest
    terminal_status: SafeToken
    duration_bucket: Bucket
    event_count_bucket: Bucket
    total_tokens_bucket: Bucket
    cost_bucket: Bucket
    llm_model_family: SafeToken


class ErrorProperties(_BaseProperties):
    """失败，沦为可分组的形状。

    值得注意的是，不存在：异常消息、回溯和任何路径。 参见
    :func:`openhands.agent_server.telemetry.sanitizer.normalize_exception`。
    """

    kind: Literal["error"] = "error"

    conversation_ref: Digest | None = None
    error_class: SafeIdentifier
    error_category: ErrorCategory
    error_fingerprint: Digest
    error_origin_module: SafeIdentifier | None = None
    error_origin_lineno: int | None = Field(default=None, ge=0)
    is_first_party: bool
    is_terminal: bool
    error_telemetry: Literal["outcome", "diagnostic"] = "diagnostic"
    tool_name: SafeToken | None = None
    error_id: SafeToken | None = None


class RequestFailedProperties(_BaseProperties):
    """未处理的 5xx。

    ``route_template`` 是参数化路径 (``/api/conversations/{id}``)，而不是嵌入标识符的
    具体路径。
    """

    kind: Literal["request_failed"] = "request_failed"

    route_template: Annotated[
        str, StringConstraints(pattern=r"^/[A-Za-z0-9_/{}.\-]{0,127}$")
    ]
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
    status_code: int = Field(ge=100, le=599)
    error_class: SafeIdentifier
    error_category: ErrorCategory
    error_fingerprint: Digest
    error_id: SafeToken | None = None


DiagnosticProperties = Annotated[
    ServerLifecycleProperties
    | ConversationStartedProperties
    | ConversationOutcomeProperties
    | ErrorProperties
    | RequestFailedProperties,
    Field(discriminator="kind"),
]


class DiagnosticEvent(BaseModel):
    """一项经过净化的分析事件。 水槽唯一接受的东西。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_name: EventName
    schema_version: int = TELEMETRY_SCHEMA_VERSION
    occurred_at: datetime
    insert_id: SafeToken | None = None

    distinct_id: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    """相关恒等式，逐字传递。

    这是部署提供的 ``user_id``，如果存在的话，事件会落在已经识别的托管部署所标识的人
    身上，或者 ``anon:<hex>`` 对于一个未标识的本地会话。 这
    是有意豁免的一个领域
    from the constrained-token rule — correlation requires the value to match
    主机的 id 字节为字节。 它绝不会用于*创建*身份； 看到
    ``posthog_exporter``.
    """

    runtime: RuntimeProperties
    properties: DiagnosticProperties

    def to_payload(self) -> dict[str, object]:
        """压平至出口商发送的财产袋。

        ``distinct_id`` 被排除——它是传输层的寻址字段，而不是事件属性。
        """
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            **self.runtime.model_dump(mode="json"),
            **self.properties.model_dump(mode="json", exclude={"kind"}),
        }
        if self.insert_id is not None:
            payload["$insert_id"] = self.insert_id
        return payload


# ：拒绝测试断言模型准确地生成了该组。
EXPECTED_PROPERTY_NAMES: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "server_version",
        "sdk_version",
        "tools_version",
        "build_git_sha",
        "build_git_ref",
        "python_version",
        "platform",
        "deferred_init",
        "deployment_kind",
        "source",
        "$insert_id",
        "conversation_ref",
        "llm_model_family",
        "agent_kind",
        "tool_count",
        "is_fork",
        "has_agent_profile",
        "workspace_kind",
        "confirmation_policy",
        "is_automation",
        "terminal_status",
        "duration_bucket",
        "event_count_bucket",
        "total_tokens_bucket",
        "cost_bucket",
        "error_class",
        "error_category",
        "error_fingerprint",
        "error_origin_module",
        "error_origin_lineno",
        "is_first_party",
        "is_terminal",
        "error_telemetry",
        "tool_name",
        "error_id",
        "route_template",
        "method",
        "status_code",
    }
)
