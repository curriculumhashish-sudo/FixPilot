"""Agent Server 的净化产品分析遥测。

这是**产品分析**，与此存储库中容易混淆的其他两个内容不同：

* **LLM 完成日志记录** (``LLM.log_completions``) 将完整的提示词和响应写入磁盘以进行调
试。 它在设计上具有高保真度和隐私敏感性，并且它产
生的任何内容都不会转发到这里。
* **层流/OpenTelemetry跟踪** (``openhands.sdk.observability``) 生成用于延迟和跨度分析
的分布式跟踪。 单独的管道，单独
的目的地。

该包发出的是一个小型、版本化的生命周期和失败事件集合，其属性都是约束的标量值——从不提
示词，messages, paths, 机密请求/响应体或堆栈跟踪。

``posthog_exporter`` 是故意在此处导入的 ** 而非 **：导入此包不得引入可选的供应商依赖
项。
"""

from openhands.agent_server.telemetry.factory import (
    DISTINCT_ID_HEADER,
    DiagnosticEventFactory,
    build_runtime_properties,
    distinct_id_from_header,
)
from openhands.agent_server.telemetry.models import (
    TELEMETRY_SCHEMA_VERSION,
    DeploymentKind,
    DiagnosticEvent,
    RuntimeProperties,
)
from openhands.agent_server.telemetry.policy import (
    TelemetryConsent,
    TelemetryDecision,
    kill_switch_engaged,
    read_consent,
    resolve,
)
from openhands.agent_server.telemetry.service import (
    build_telemetry_sink,
    emit_server_started,
    emit_server_stopped,
    get_event_factory,
    get_telemetry_sink,
    notify_misc_settings_changed,
    reset_telemetry_sink,
    shutdown_telemetry_sink,
)
from openhands.agent_server.telemetry.sink import (
    BufferedTelemetrySink,
    NoOpTelemetrySink,
    TelemetryExporter,
    TelemetrySink,
)
from openhands.agent_server.telemetry.subscriber import (
    ConversationTelemetryContext,
    TelemetrySubscriber,
)


__all__ = [
    "TELEMETRY_SCHEMA_VERSION",
    "BufferedTelemetrySink",
    "ConversationTelemetryContext",
    "DeploymentKind",
    "DiagnosticEvent",
    "DISTINCT_ID_HEADER",
    "DiagnosticEventFactory",
    "NoOpTelemetrySink",
    "RuntimeProperties",
    "TelemetryConsent",
    "TelemetryDecision",
    "TelemetryExporter",
    "read_consent",
    "TelemetrySink",
    "TelemetrySubscriber",
    "build_runtime_properties",
    "distinct_id_from_header",
    "build_telemetry_sink",
    "emit_server_started",
    "emit_server_stopped",
    "get_event_factory",
    "get_telemetry_sink",
    "kill_switch_engaged",
    "notify_misc_settings_changed",
    "reset_telemetry_sink",
    "resolve",
    "shutdown_telemetry_sink",
]
