"""该功能必须演示的三个场景的端到端验证。

1. 选择加入的本地会话会产生经过净化的生命周期和错误事件。
2. 选择退出的会话会生成 None。
3. 总是失败的导出器不会影响对话的执行。

它们驱动真正的接收器和订阅者接线，而不是模拟对象，并在 *已序列化载荷* 上断言 - 实际离
开进程的字节。
"""

import asyncio
import json
import uuid

import pytest

from openhands.agent_server.telemetry import models as m
from openhands.agent_server.telemetry.factory import (
    DiagnosticEventFactory,
    build_runtime_properties,
)
from openhands.agent_server.telemetry.policy import (
    TelemetryConsent,
    TelemetryDecision,
)
from openhands.agent_server.telemetry.sink import BufferedTelemetrySink
from openhands.agent_server.telemetry.subscriber import (
    ConversationTelemetryContext,
    TelemetrySubscriber,
)
from openhands.sdk.event import AgentErrorEvent, ConversationStateUpdateEvent


# 任何发出的载荷中必须不存在的值。
PROMPT = "Refactor the billing module in /Users/alice/acme/billing.py"
SECRET = "sk-ant-api03-DO-NOT-LEAK-THIS"
WORKSPACE_PATH = "/Users/alice/acme"
FORBIDDEN = [PROMPT, SECRET, WORKSPACE_PATH, "Traceback", "billing.py"]


class CapturingExporter:
    def __init__(self):
        self.payloads: list[dict] = []

    async def send(self, events):
        for event in events:
            self.payloads.append(
                {
                    "event": event.event_name,
                    "distinct_id": event.distinct_id,
                    "properties": event.to_payload(),
                }
            )

    async def aclose(self):
        pass


class AlwaysFailingExporter:
    def __init__(self):
        self.attempts = 0

    async def send(self, events):
        self.attempts += 1
        raise ConnectionError("posthog is unreachable")

    async def aclose(self):
        raise ConnectionError("still unreachable")


def build_subscriber(sink, user_id: str | None = "canvas-user-7"):
    factory = DiagnosticEventFactory(
        runtime=build_runtime_properties(deferred_init=False),
        salt="deployment-salt",
    )
    conversation_id = uuid.uuid4()
    return conversation_id, TelemetrySubscriber(
        conversation_id=conversation_id,
        sink=sink,
        factory=factory,
        context=ConversationTelemetryContext(
            conversation_ref=factory.conversation_ref(conversation_id),
            user_id=user_id,
            llm_model_family="anthropic",
            agent_kind="agent",
            tool_count=4,
            is_fork=False,
            has_agent_profile=False,
            workspace_kind="localworkspace",
            confirmation_policy="neverconfirm",
        ),
    )


async def run_session(subscriber: TelemetrySubscriber) -> None:
    """模拟进行一些工作、出错、然后结束的对话。"""
    subscriber.emit_started()
    # subscribe_to_events 在附加时推送当前状态； 对于新的对话，基线是非终端的。
    #
    await subscriber(ConversationStateUpdateEvent(key="execution_status", value="idle"))
    await subscriber(
        AgentErrorEvent(
            error=f"Command failed while running: {PROMPT} (key={SECRET})",
            tool_name="bash",
            tool_call_id="call-1",
        )
    )
    await subscriber(
        ConversationStateUpdateEvent(key="execution_status", value="finished")
    )
    await subscriber.close()


# ── 1. 选择了────────────────────────────────────────────────────────────


async def test_opted_in_session_emits_sanitized_lifecycle_and_error_events():
    exporter = CapturingExporter()
    sink = BufferedTelemetrySink(
        exporter,
        decision=TelemetryDecision(
            consent=TelemetryConsent.GRANTED, enabled=True, reason="settings"
        ),
        flush_delay=0.05,
        shutdown_flush_timeout=1.0,
    )
    sink.start()

    conversation_id, subscriber = build_subscriber(sink)
    await run_session(subscriber)
    await asyncio.wait_for(sink.aclose(), timeout=10)

    names = [p["event"] for p in exporter.payloads]
    assert m.EventName.CONVERSATION_CREATED in names
    assert m.EventName.CONVERSATION_ERROR in names
    assert m.EventName.CONVERSATION_FINISHED in names

    serialized = json.dumps(exporter.payloads)

    # 没有任何敏感的东西幸存下来。
    for forbidden in FORBIDDEN:
        assert forbidden not in serialized, f"leaked {forbidden!r}"

    # 原始对话 ID 永远不会被发送。
    assert str(conversation_id) not in serialized
    assert conversation_id.hex not in serialized

    # 相关标识是主机的逐字标识。
    assert all(p["distinct_id"] == "canvas-user-7" for p in exporter.payloads)

    # 仅允许列入许可名单的属性，并且每个事件都带有模式版本。
    for payload in exporter.payloads:
        assert set(payload["properties"]) <= set(m.EXPECTED_PROPERTY_NAMES)
        assert payload["properties"]["schema_version"] == m.TELEMETRY_SCHEMA_VERSION
        assert payload["properties"]["source"] == "openhands-agent-server"


async def test_opted_in_session_reports_useful_diagnostics():
    """清理工作不得使活动变得毫无用处。"""
    exporter = CapturingExporter()
    sink = BufferedTelemetrySink(
        exporter,
        decision=TelemetryDecision(
            consent=TelemetryConsent.GRANTED, enabled=True, reason="settings"
        ),
        flush_delay=0.05,
        shutdown_flush_timeout=1.0,
    )
    sink.start()
    _, subscriber = build_subscriber(sink)
    await run_session(subscriber)
    await asyncio.wait_for(sink.aclose(), timeout=10)

    by_name = {p["event"]: p["properties"] for p in exporter.payloads}

    started = by_name[m.EventName.CONVERSATION_CREATED]
    assert (
        started["$insert_id"] == f"conversation_created:{started['conversation_ref']}"
    )
    assert started["llm_model_family"] == "anthropic"
    assert started["tool_count"] == 4

    error = by_name[m.EventName.CONVERSATION_ERROR]
    assert error["error_category"] == "tool_execution"
    assert error["tool_name"] == "bash"
    assert len(error["error_fingerprint"]) >= 16

    finished = by_name[m.EventName.CONVERSATION_FINISHED]
    assert finished["terminal_status"] == "finished"
    # 桶装的，不准确。
    assert "-" in finished["duration_bucket"] or finished["duration_bucket"].startswith(
        ("lt-", "unknown")
    )


# ── 2. 选择退出──────────────────────────────────────────────────────────


@pytest.mark.parametrize("consent", ["denied", "unset"])
async def test_opted_out_session_emits_nothing(consent):
    exporter = CapturingExporter()
    sink = BufferedTelemetrySink(
        exporter,
        decision=TelemetryDecision(
            consent=consent, enabled=consent == "granted", reason="settings"
        ),
        flush_delay=0.05,
        shutdown_flush_timeout=1.0,
    )
    sink.start()

    _, subscriber = build_subscriber(sink)
    await run_session(subscriber)
    await asyncio.sleep(0.2)
    await asyncio.wait_for(sink.aclose(), timeout=10)

    assert exporter.payloads == []


async def test_revocation_mid_session_stops_delivery_and_drops_the_backlog():
    exporter = CapturingExporter()
    sink = BufferedTelemetrySink(
        exporter,
        decision=TelemetryDecision(
            consent=TelemetryConsent.GRANTED, enabled=True, reason="settings"
        ),
        flush_delay=3600,  # 没有任何东西会自行冲洗
        shutdown_flush_timeout=1.0,
    )
    sink.start()

    _, subscriber = build_subscriber(sink)
    subscriber.emit_started()
    await subscriber(ConversationStateUpdateEvent(key="execution_status", value="idle"))
    await subscriber(AgentErrorEvent(error=SECRET, tool_name="bash", tool_call_id="c1"))

    sink.on_decision_changed(
        TelemetryDecision(
            consent=TelemetryConsent.DENIED, enabled=False, reason="settings"
        )
    )

    await subscriber(
        ConversationStateUpdateEvent(key="execution_status", value="finished")
    )
    await subscriber.close()
    await asyncio.wait_for(sink.aclose(), timeout=10)

    assert exporter.payloads == [], "events survived a revocation"


# ── 3. 出口商失败────────────────────────────────────────────────────


async def test_exporter_failure_leaves_conversation_execution_unaffected():
    """损坏的分析后端必须对对话不可见。"""
    exporter = AlwaysFailingExporter()
    sink = BufferedTelemetrySink(
        exporter,
        decision=TelemetryDecision(
            consent=TelemetryConsent.GRANTED, enabled=True, reason="settings"
        ),
        flush_delay=0.02,
        num_retries=1,
        retry_delay=0.01,
        shutdown_flush_timeout=0.5,
    )
    sink.start()

    _, subscriber = build_subscriber(sink)

    # 尽管每次发送都会增加，但会话仍会运行完成。
    await asyncio.wait_for(run_session(subscriber), timeout=5)
    await asyncio.sleep(0.3)

    assert exporter.attempts >= 1, "exporter was never exercised"
    assert sink._drain_task is not None
    assert not sink._drain_task.done(), "drain task died"

    # 即使 aclose()（其 exporter.aclose() 也引发）也不得传播。
    await asyncio.wait_for(sink.aclose(), timeout=10)


async def test_a_hanging_exporter_does_not_delay_the_conversation():
    class HangingExporter:
        async def send(self, events):
            await asyncio.sleep(3600)

        async def aclose(self):
            pass

    sink = BufferedTelemetrySink(
        HangingExporter(),
        decision=TelemetryDecision(
            consent=TelemetryConsent.GRANTED, enabled=True, reason="settings"
        ),
        flush_delay=0.01,
        shutdown_flush_timeout=0.5,
    )
    sink.start()
    _, subscriber = build_subscriber(sink)

    # 如果交付时排放量为同步，则会挂起一个小时。
    await asyncio.wait_for(run_session(subscriber), timeout=2)
    await asyncio.wait_for(sink.aclose(), timeout=10)
