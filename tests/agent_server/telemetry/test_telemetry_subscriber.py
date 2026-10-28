"""订阅者行为：正确的生命周期事件和完全故障隔离。"""

import asyncio
import json
import uuid

import pytest

from openhands.agent_server.pub_sub import PubSub, Subscriber
from openhands.agent_server.telemetry import models as m
from openhands.agent_server.telemetry.factory import DiagnosticEventFactory
from openhands.agent_server.telemetry.subscriber import (
    ConversationTelemetryContext,
    TelemetrySubscriber,
)
from openhands.sdk.event import (
    AgentErrorEvent,
    ConversationStateUpdateEvent,
    StreamingDeltaEvent,
)
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.event.error_classification import ErrorClassification, FailureKind


class CollectingSink:
    def __init__(self, enabled: bool = True):
        self._enabled = enabled
        self.events: list[m.DiagnosticEvent] = []
        self.closed = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def emit(self, event):
        self.events.append(event)

    async def aclose(self):
        self.closed = True

    @property
    def names(self) -> list[str]:
        return [e.event_name for e in self.events]


@pytest.fixture
def factory() -> DiagnosticEventFactory:
    return DiagnosticEventFactory(
        runtime=m.RuntimeProperties(
            server_version="1.36.1",
            sdk_version="1.36.1",
            tools_version="1.36.1",
            build_git_sha="unknown",
            build_git_ref="unknown",
            python_version="3.13",
            platform="darwin",
            deferred_init=False,
        ),
        salt="test-salt",
    )


def make_subscriber(
    sink,
    factory,
    user_id: str | None = "user-1",
    *,
    is_automation: bool = False,
):
    conversation_id = uuid.uuid4()
    return TelemetrySubscriber(
        conversation_id=conversation_id,
        sink=sink,
        factory=factory,
        context=ConversationTelemetryContext(
            conversation_ref=factory.conversation_ref(conversation_id),
            user_id=user_id,
            llm_model_family="anthropic",
            agent_kind="agent",
            tool_count=3,
            is_fork=False,
            has_agent_profile=False,
            workspace_kind="localworkspace",
            confirmation_policy="neverconfirm",
            is_automation=is_automation,
        ),
    )


# ── 生命周期 ──────────────────────────────────────────────────────────────


async def test_emits_exactly_one_created_event(factory):
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    sub.emit_started()
    assert sink.names == [m.EventName.CONVERSATION_CREATED]


async def test_created_event_identifies_automation_conversations(factory):
    sink = CollectingSink()
    sub = make_subscriber(sink, factory, is_automation=True)

    sub.emit_started()

    assert sink.events[0].to_payload()["is_automation"] is True


def test_started_is_only_emitted_for_genuinely_new_conversations():
    """Regression: ``_start_event_service`` 也需要补液。

    当延迟重新加载空闲会话以及重新启动后恢复 RUNNING 个会话时，会调用它。 发射
    所有这些中的 ``conversation_created`` 都会使每次服务器反弹时的指标膨胀，因此该标
    志必须默认为 *not* 发出。
    """
    import inspect

    from openhands.agent_server.conversation_service import ConversationService

    sig = inspect.signature(ConversationService._start_event_service)
    param = sig.parameters["is_new_conversation"]

    assert param.default is False, (
        "_start_event_service must default to NOT emitting conversation_created; "
        "the hydration path relies on that default"
    )
    assert param.kind is inspect.Parameter.KEYWORD_ONLY

    subscribe_sig = inspect.signature(ConversationService._maybe_subscribe_telemetry)
    assert "is_new_conversation" in subscribe_sig.parameters


async def test_terminal_status_emits_finished_once(factory):
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    # subscribe_to_events 在附加时执行的基线推送。
    await sub(ConversationStateUpdateEvent(key="execution_status", value="idle"))
    await sub(ConversationStateUpdateEvent(key="execution_status", value="finished"))
    await sub(ConversationStateUpdateEvent(key="execution_status", value="finished"))
    await sub.close()

    assert sink.names == [m.EventName.CONVERSATION_FINISHED]


@pytest.mark.parametrize("status", ["error", "stuck"])
async def test_failure_statuses_emit_conversation_failed(factory, status):
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    # subscribe_to_events 在附加时执行的基线推送。
    await sub(ConversationStateUpdateEvent(key="execution_status", value="idle"))
    await sub(ConversationStateUpdateEvent(key="execution_status", value=status))
    assert sink.names == [m.EventName.CONVERSATION_FAILED]
    assert sink.events[0].to_payload()["terminal_status"] == status


async def test_terminal_status_is_read_from_a_full_state_snapshot(factory):
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    # subscribe_to_events 在附加时执行的基线推送。
    await sub(ConversationStateUpdateEvent(key="execution_status", value="idle"))
    await sub(
        ConversationStateUpdateEvent(
            key="full_state", value={"execution_status": "finished"}
        )
    )
    assert sink.names == [m.EventName.CONVERSATION_FINISHED]


async def test_close_is_silent_when_no_run_was_observed(factory):
    """Regression: 打开现有的对话不是对话。

    订阅者在每个 _start_event_service 路径上附加，包括用户仅查看旧对话时的惰性附加。
    关闭时发出会产生一个没有匹配的
    conversation_created 的 conversation_finished，并在每个视图然后重新启动循环中重复
    相同的 conversation_ref
    。
    """
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    await sub.close()
    assert sink.names == []


@pytest.mark.parametrize("baseline", ["idle", "paused", "finished", "error"])
async def test_view_only_rehydration_emits_nothing(factory, baseline):
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    # 附加时基线推送，然后会话结束而不运行。
    await sub(ConversationStateUpdateEvent(key="execution_status", value=baseline))
    await sub.close()

    assert sink.names == [], (
        f"view-only rehydration at {baseline!r} emitted {sink.names}"
    )


async def test_a_run_interrupted_before_a_terminal_state_is_still_reported(factory):
    """运行中碰撞安全网必须能够经受住噪音修复的考验。"""
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    await sub(ConversationStateUpdateEvent(key="execution_status", value="idle"))
    await sub(ConversationStateUpdateEvent(key="execution_status", value="running"))
    await sub.close()

    assert sink.names == [m.EventName.CONVERSATION_FAILED]
    payload = sink.events[0].to_payload()
    # 名为 terminal_status 的字段中绝不会出现原始非终止状态。
    assert payload["terminal_status"] == "interrupted"


async def test_an_observed_terminal_state_wins_over_the_interrupted_fallback(factory):
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    await sub(ConversationStateUpdateEvent(key="execution_status", value="idle"))
    await sub(ConversationStateUpdateEvent(key="execution_status", value="running"))
    await sub(ConversationStateUpdateEvent(key="execution_status", value="finished"))
    await sub.close()

    assert sink.names == [m.EventName.CONVERSATION_FINISHED]
    assert sink.events[0].to_payload()["terminal_status"] == "finished"


async def test_close_does_not_close_the_shared_sink(factory):
    """接收器是进程范围内的，并且比每次对话都存在。"""
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    await sub.close()
    assert sink.closed is False


# ── 错误────────────────────────────────────────────────────────────────


async def test_agent_error_event_reports_only_the_tool_name(factory):
    """AgentErrorEvent.error携带模型文本和工具输出； 永远不要发送它。"""
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    secret = "sk-ant-api03-LEAKED /Users/alice/private.py failed"
    await sub(
        AgentErrorEvent(
            error=secret,
            tool_name="bash",
            tool_call_id="call-1",
        )
    )

    assert sink.names == [m.EventName.CONVERSATION_ERROR]
    serialized = json.dumps(sink.events[0].to_payload())
    assert secret not in serialized
    assert "sk-ant" not in serialized
    assert "/Users/alice" not in serialized
    payload = sink.events[0].to_payload()
    assert payload["tool_name"] == "bash"
    assert payload["error_category"] == "tool_execution"


async def test_conversation_error_event_reports_only_the_code(factory):
    """ConversationErrorEvent.detail 是自由散文； 永远不要发送它。"""
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    detail = "Failed reading /home/bob/.ssh/id_rsa while running the user's prompt"
    await sub(
        ConversationErrorEvent(source="environment", code="LLMAuthError", detail=detail)
    )

    serialized = json.dumps(sink.events[0].to_payload())
    assert detail not in serialized
    assert "/home/bob" not in serialized
    assert sink.events[0].to_payload()["error_class"] == "LLMAuthError"
    assert sink.events[0].to_payload()["error_telemetry"] == "diagnostic"


async def test_known_error_outcomes_are_not_diagnostics(factory):
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    await sub(
        ConversationErrorEvent(
            source="environment",
            code="OpenAIError",
            detail="Incorrect API key provided",
        )
    )

    assert sink.events[0].to_payload()["error_telemetry"] == "outcome"


async def test_agent_error_with_agent_action_classification_is_outcome(factory):
    """工具验证错误 (agent_action) 是结果，而不是诊断。"""
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    await sub(
        AgentErrorEvent(
            error="Error executing tool 'bash': invalid argument",
            tool_name="bash",
            tool_call_id="call-1",
            classification=ErrorClassification(
                kind=FailureKind.AGENT_ACTION, retryable=True, user_action="retry"
            ),
        )
    )

    assert sink.events[0].to_payload()["error_telemetry"] == "outcome"


async def test_agent_error_with_internal_classification_is_diagnostic(factory):
    """意外崩溃（内部）是一种诊断，而不是结果。"""
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    await sub(
        AgentErrorEvent(
            error="A restart occurred while this tool was in progress.",
            tool_name="bash",
            tool_call_id="call-1",
            classification=ErrorClassification(
                kind=FailureKind.INTERNAL, retryable=False
            ),
        )
    )

    assert sink.events[0].to_payload()["error_telemetry"] == "diagnostic"


async def test_agent_error_without_classification_is_diagnostic(factory):
    """裸露的 AgentErrorEvent（未知）默认用于诊断。"""
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    await sub(
        AgentErrorEvent(
            error="something unexpected",
            tool_name="bash",
            tool_call_id="call-1",
        )
    )

    assert sink.events[0].to_payload()["error_telemetry"] == "diagnostic"


# ── 隔离──────────────────────────────────────────────────────────────


async def test_subscriber_never_raises_on_a_malformed_event(factory):
    class Broken:
        @property
        def key(self):
            raise RuntimeError("boom")

    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    await sub(Broken())  # type: ignore[arg-type]


async def test_a_raising_sink_cannot_break_the_subscriber(factory):
    class ExplodingSink:
        enabled = True

        def emit(self, event):
            raise RuntimeError("sink is broken")

        async def aclose(self):
            pass

    sub = make_subscriber(ExplodingSink(), factory)
    await sub(ConversationStateUpdateEvent(key="execution_status", value="finished"))
    await sub.close()


async def test_subscriber_does_not_stall_pubsub_fanout(factory):
    """遥测订阅者不得延迟向其兄弟姐妹传送。"""

    class SlowSibling(Subscriber):
        def __init__(self):
            self.received = 0

        async def __call__(self, event):
            self.received += 1

        async def close(self):
            pass

    sink = CollectingSink()
    pub_sub: PubSub = PubSub()
    sibling = SlowSibling()
    telemetry_sub = make_subscriber(sink, factory)
    # 播种基线，镜像 subscribe_to_events' 初始推送。
    await telemetry_sub(
        ConversationStateUpdateEvent(key="execution_status", value="idle")
    )
    pub_sub.subscribe(telemetry_sub)
    pub_sub.subscribe(sibling)

    event = ConversationStateUpdateEvent(key="execution_status", value="finished")
    await asyncio.wait_for(pub_sub(event), timeout=1.0)

    assert sibling.received == 1
    assert sink.names == [m.EventName.CONVERSATION_FINISHED]


async def test_disabled_sink_short_circuits_before_building_events(factory):
    sink = CollectingSink(enabled=False)
    sub = make_subscriber(sink, factory)

    sub.emit_started()
    # emit() 本身是对禁用接收器的无操作； 没有记录任何内容。
    assert sink.events == [] or sink.names == [m.EventName.CONVERSATION_CREATED]


# ── 身份──────────────────────────────────────────────────────────────


async def test_identified_conversations_pass_user_id_through_verbatim(factory):
    sink = CollectingSink()
    sub = make_subscriber(sink, factory, user_id="canvas-user-42")

    sub.emit_started()
    assert sink.events[0].distinct_id == "canvas-user-42"


async def test_unidentified_conversations_get_an_anonymous_id(factory):
    sink = CollectingSink()
    sub = make_subscriber(sink, factory, user_id=None)

    sub.emit_started()
    assert sink.events[0].distinct_id.startswith("anon:")


async def test_conversation_ref_is_never_the_raw_uuid(factory):
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    sub.emit_started()
    payload = json.dumps(sink.events[0].to_payload())
    assert str(sub.conversation_id) not in payload
    assert sub.conversation_id.hex not in payload


async def test_initial_state_push_is_a_baseline_not_a_transition(factory):
    """Regression: 补充已完成的对话不得重新发出。

    ``subscribe_to_events``同步将当前状态推送给新订阅者。 对于已经结束的对话——懒加载
    、重启后恢复的RUNNING->ERROR记录——推送原本
    看起来像是一个全新的终端过渡，产生了一个重复项
    ``conversation_finished`` 具有无意义的亚秒持续时间。
    """
    for persisted_status in ("finished", "error", "stuck"):
        sink = CollectingSink()
        sub = make_subscriber(sink, factory)

        # subscribe_to_events 推动附加的内容。
        await sub(
            ConversationStateUpdateEvent(key="execution_status", value=persisted_status)
        )
        assert sink.names == [], (
            f"attaching to an already-{persisted_status} conversation emitted "
            f"{sink.names}"
        )

        # 并且 close() 也不能发明一个。
        await sub.close()
        assert sink.names == [], f"close() emitted {sink.names} after rehydration"


async def test_a_live_transition_after_the_baseline_still_emits(factory):
    """播种保护不得抑制真正的终端转换。"""
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)

    # 基线：新的对话是闲置的。
    await sub(ConversationStateUpdateEvent(key="execution_status", value="idle"))
    assert sink.names == []

    await sub(ConversationStateUpdateEvent(key="execution_status", value="finished"))
    assert sink.names == [m.EventName.CONVERSATION_FINISHED]


# ── 生产事件形状────────────────────────────────────────────── 上述测试手动构造
# ConversationStateUpdateEvent
#
# key="execution_status". Production never does that: EventService always
# 通过 ConversationStateUpdateEvent.from_conversation_state() 发布，发出 key="full_state
# "。 这些测试驱动真正的构造函数，因此 full_state 分支中的错误无法隐藏在合成形状后面。
#


def _real_state(status=None):
    import uuid as _uuid

    from openhands.sdk.agent import Agent
    from openhands.sdk.conversation.state import ConversationState
    from openhands.sdk.llm import LLM
    from openhands.sdk.workspace import LocalWorkspace

    state = ConversationState(
        id=_uuid.uuid4(),
        agent=Agent(llm=LLM(model="anthropic/claude-sonnet-5", usage_id="t"), tools=[]),
        workspace=LocalWorkspace(working_dir="workspace/project"),
    )
    if status is not None:
        state.execution_status = status
    return state


async def test_lifecycle_fires_on_the_real_from_conversation_state_event(factory):
    """端到端的构造函数EventService实际使用。"""
    from openhands.sdk.conversation.state import ConversationExecutionStatus
    from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent

    sink = CollectingSink()
    sub = make_subscriber(sink, factory)
    state = _real_state()

    baseline = ConversationStateUpdateEvent.from_conversation_state(state)
    assert baseline.key == "full_state", (
        "production shape changed; the subscriber's full_state branch may be dead"
    )
    await sub(baseline)
    assert sink.names == []

    state.execution_status = ConversationExecutionStatus.FINISHED
    await sub(ConversationStateUpdateEvent.from_conversation_state(state))
    assert sink.names == [m.EventName.CONVERSATION_FINISHED]


async def test_outcome_reports_real_bucketed_usage(factory):
    """Regression: 令牌/成本被硬编码为“未知”并且从未填充。"""
    from openhands.sdk.conversation.state import ConversationExecutionStatus
    from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
    from openhands.sdk.llm.utils.metrics import Metrics

    sink = CollectingSink()
    sub = make_subscriber(sink, factory)
    state = _real_state()
    await sub(ConversationStateUpdateEvent.from_conversation_state(state))

    metrics = Metrics(model_name="anthropic/claude-sonnet-5")
    metrics.add_cost(0.42)
    metrics.add_token_usage(
        prompt_tokens=12000,
        completion_tokens=3000,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        context_window=200000,
        response_id="r",
    )
    # usage_to_metrics 保存指标（不是 MetricsSnapshot）； 两者都是序列化
    # accumulated_cost / accumulated_token_usage，这就是我们读到的内容。
    #
    state.stats.usage_to_metrics["t"] = metrics
    state.execution_status = ConversationExecutionStatus.FINISHED

    await sub(ConversationStateUpdateEvent.from_conversation_state(state))
    payload = sink.events[0].to_payload()

    assert payload["total_tokens_bucket"] == "10000-50000"
    assert payload["cost_bucket"] == "0p1-1"
    # 桶装的，绝不是生的。
    assert "15000" not in str(payload)
    assert "0.42" not in str(payload)


def _stats_update_with_usage():
    """``stats`` 更新 EventService 在每次 LLM 调用后发布。"""
    from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
    from openhands.sdk.llm.utils.metrics import Metrics

    state = _real_state()
    metrics = Metrics(model_name="deepseek/deepseek-chat")
    metrics.add_cost(0.42)
    metrics.add_token_usage(
        prompt_tokens=12000,
        completion_tokens=3000,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        context_window=200000,
        response_id="r",
    )
    state.stats.usage_to_metrics["default"] = metrics
    return ConversationStateUpdateEvent(key="stats", value=state.stats)


async def test_outcome_reports_usage_from_the_live_event_order(factory):
    """Regression: 实时运行的终端状态是裸字符串更新。

    服务器在每次 LLM 调用后发布 ``stats`` 密钥更新，然后
    ``execution_status`` 更新（裸字符串），然后才更新 ``full_state`` 快照。 使用必须
    来自终端状态之前看到的``stats``更新，
    而不仅仅是来自终端``full_state``。
    """
    from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent

    sink = CollectingSink()
    sub = make_subscriber(sink, factory)
    await sub(ConversationStateUpdateEvent.from_conversation_state(_real_state()))
    await sub(ConversationStateUpdateEvent(key="execution_status", value="running"))
    await sub(_stats_update_with_usage())
    await sub(ConversationStateUpdateEvent(key="execution_status", value="finished"))

    assert sink.names == [m.EventName.CONVERSATION_FINISHED]
    payload = sink.events[0].to_payload()
    assert payload["total_tokens_bucket"] == "10000-50000"
    assert payload["cost_bucket"] == "0p1-1"


async def test_interrupted_fallback_reports_usage_seen_before_close(factory):
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)
    await sub(ConversationStateUpdateEvent(key="execution_status", value="idle"))
    await sub(ConversationStateUpdateEvent(key="execution_status", value="running"))
    await sub(_stats_update_with_usage())
    await sub.close()

    assert sink.names == [m.EventName.CONVERSATION_FAILED]
    payload = sink.events[0].to_payload()
    assert payload["terminal_status"] == "interrupted"
    assert payload["total_tokens_bucket"] == "10000-50000"
    assert payload["cost_bucket"] == "0p1-1"


def test_confirmation_policy_is_read_from_the_field_that_exists():
    """Regression: 该字段是 confirmation_policy，而不是 confirmation_mode。

    通过 getattr 读取不存在的 ``confirmation_mode`` 会为每个对话默默地报告 False，并
    且 bool 无论如何都会将
    ConfirmRisky 折叠为 NeverConfirm。
    """
    import uuid as _uuid

    from openhands.agent_server.conversation_service import _build_telemetry_context
    from openhands.agent_server.models import StoredConversation
    from openhands.agent_server.telemetry.factory import (
        DiagnosticEventFactory,
        build_runtime_properties,
    )
    from openhands.sdk.agent import Agent
    from openhands.sdk.llm import LLM
    from openhands.sdk.security.confirmation_policy import AlwaysConfirm
    from openhands.sdk.workspace import LocalWorkspace

    assert "confirmation_mode" not in StoredConversation.model_fields
    assert "confirmation_policy" in StoredConversation.model_fields

    agent = Agent(llm=LLM(model="anthropic/claude-sonnet-5", usage_id="t"), tools=[])
    stored = StoredConversation(
        id=_uuid.uuid4(),
        workspace=LocalWorkspace(working_dir="/Users/alice/secret-project"),
        confirmation_policy=AlwaysConfirm(),
        user_id="canvas-user-42",
    )
    ctx = _build_telemetry_context(
        stored,
        DiagnosticEventFactory(
            runtime=build_runtime_properties(deferred_init=False),
            salt="s",
        ),
        agent=agent,
    )

    from dataclasses import asdict

    assert ctx.confirmation_policy == "alwaysconfirm"
    assert ctx.llm_model_family == "anthropic"
    assert ctx.user_id == "canvas-user-42"
    # 没有字段默默降级，工作区路径也没有泄漏。
    fields = asdict(ctx)
    assert "unknown" not in fields.values()
    assert "secret-project" not in repr(fields)


@pytest.mark.parametrize(
    ("tags", "is_automation"),
    [
        ({"automationtrigger": "cron"}, True),
        ({"automationid": "auto-1"}, True),
        ({"automationrunid": "run-1"}, True),
        ({"automationtrigger": ""}, False),
        ({"automationname": "Nightly Audit"}, False),
        ({"source": "automation"}, False),
        ({}, False),
    ],
)
def test_is_automation_is_derived_from_allowlisted_tags(tags, is_automation):
    from openhands.agent_server.conversation_service import _build_telemetry_context
    from openhands.agent_server.models import StoredConversation
    from openhands.agent_server.telemetry.factory import (
        DiagnosticEventFactory,
        build_runtime_properties,
    )
    from openhands.sdk.agent import Agent
    from openhands.sdk.llm import LLM
    from openhands.sdk.workspace import LocalWorkspace

    agent = Agent(llm=LLM(model="anthropic/claude-sonnet-5", usage_id="t"), tools=[])
    stored = StoredConversation(
        id=uuid.uuid4(),
        workspace=LocalWorkspace(working_dir="/tmp"),
        user_id="canvas-user-42",
        tags=tags,
    )

    context = _build_telemetry_context(
        stored,
        DiagnosticEventFactory(
            runtime=build_runtime_properties(deferred_init=False),
            salt="s",
        ),
        agent=agent,
    )

    assert context.is_automation is is_automation


async def test_event_count_ignores_streaming_deltas(factory):
    """Delta 不得膨胀 event_count_bucket（#4673 为回归）。"""
    sink = CollectingSink()
    sub = make_subscriber(sink, factory)
    pub_sub: PubSub = PubSub()
    pub_sub.subscribe(sub)

    for _ in range(50):
        await pub_sub(StreamingDeltaEvent(content="tok"))

    assert sub._event_count == 0
