"""Trace-上下文传播到 ``ParallelToolExecutor`` 工作人员线程。

``ThreadPoolExecutor.submit`` 和 ``loop.run_in_executor`` 均不复制
``contextvars`` 本身，因此调度的工具调用不会从调度线程继承任何内容，除非执行器显式复
制它。

两种配置的行为不同，此处分别介绍：

* **lmnr 未初始化** — 根本没有任何内容跨越线程边界，因此在工作线程中打开的跨度会启动
自己的跟踪。
* **lmnr 已初始化**（``lmnr_initialized``测试夹具） — lmnr 的供应商
  ``ThreadingInstrumentor`` 修补 ``ThreadPoolExecutor.submit`` 以携带其自己的 * 隔离
  的 * 上下文跨越，这是
  ``@observe`` 父母所反对的，因此 TOOL 跨度已经嵌套在那里，而没有我们的副本。 **not**
  携带的lmnr是OpenTelemetry*global*
  上下文或者普通的``ContextVar``； 这些差距是副本所弥补的，并且 ``with_lmnr`` 测试将
  其固定。
"""

import asyncio
import contextvars
import inspect
import threading
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Self
from unittest.mock import MagicMock, patch

import pytest
from litellm import ChatCompletionMessageToolCall
from litellm.types.utils import (
    Choices,
    Function,
    Message as LiteLLMMessage,
    ModelResponse,
)
from opentelemetry.context import Context, create_key, get_value, set_value
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanContext, Tracer
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.agent.parallel_executor import ParallelToolExecutor
from openhands.sdk.conversation import Conversation
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.tool import Action, Observation, Tool, ToolExecutor, register_tool
from openhands.sdk.tool.tool import ToolDefinition


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState


_PROBE: contextvars.ContextVar[str] = contextvars.ContextVar("probe", default="unset")

_BARRIER_TIMEOUT = 10.0


@pytest.fixture
def probe() -> Iterator[contextvars.ContextVar[str]]:
    token = _PROBE.set("set-by-dispatcher")
    try:
        yield _PROBE
    finally:
        _PROBE.reset(token)


@pytest.fixture
def tracing() -> Iterator[tuple[Tracer, InMemorySpanExporter]]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    try:
        yield provider.get_tracer("test"), exporter
    finally:
        provider.shutdown()


@pytest.fixture
def lmnr_initialized() -> Iterator[None]:
    """像 ``maybe_init_laminar()`` 一样调出 lmnr 的真实 ``TracerWrapper``。

    它的副作用是进程范围内的猴子补丁，因此请再次将其拆除。
    """
    from lmnr.opentelemetry_lib.opentelemetry.instrumentation.threading import (
        ThreadingInstrumentor,
    )
    from lmnr.opentelemetry_lib.tracing import TracerWrapper

    if TracerWrapper.verify_initialized():
        yield
        return

    original_thread_init = threading.Thread.__init__
    TracerWrapper(
        exporter=InMemorySpanExporter(),
        disable_batch=True,
        instruments=set(),
        set_global_tracer_provider=False,
    )
    try:
        yield
    finally:
        ThreadingInstrumentor().uninstrument()
        threading.Thread.__init__ = original_thread_init  # type: ignore[method-assign]
        TracerWrapper._original_thread_init = None
        del TracerWrapper.instance


def _assert_lmnr_wraps_submit() -> None:
    """Guard: 如果 lmnr 的提交补丁没有上线，这些测试就毫无意义。"""
    assert hasattr(ThreadPoolExecutor.submit, "__wrapped__"), (
        "lmnr's ThreadingInstrumentor did not patch ThreadPoolExecutor.submit; "
        "the with_lmnr tests would silently degrade to the without_lmnr case"
    )


def _make_action(tool_call_id: str, tool_name: str = "my_tool") -> Any:
    ae = MagicMock()
    ae.tool_name = tool_name
    ae.tool_call_id = tool_call_id
    return ae


def _finished(exporter: InMemorySpanExporter, name: str) -> ReadableSpan:
    matches = [s for s in exporter.get_finished_spans() if s.name == name]
    assert len(matches) == 1, f"expected exactly one {name!r} span, got {matches}"
    return matches[0]


# ── contextvars到达worker 线程 ────────────────────────────


def test_execute_batch_propagates_contextvars(probe) -> None:
    executor = ParallelToolExecutor(max_workers=2)
    seen: list[str] = []
    threads: set[str] = set()

    def tool_runner(action: Any) -> list[Any]:
        seen.append(probe.get())
        threads.add(threading.current_thread().name)
        return [MagicMock()]

    executor.execute_batch([_make_action("c0"), _make_action("c1")], tool_runner)

    assert threading.current_thread().name not in threads
    assert seen == ["set-by-dispatcher", "set-by-dispatcher"]


def test_aexecute_batch_propagates_contextvars(probe) -> None:
    executor = ParallelToolExecutor(max_workers=2)
    seen: list[str] = []
    threads: set[str] = set()

    def tool_runner(action: Any) -> list[Any]:
        seen.append(probe.get())
        threads.add(threading.current_thread().name)
        return [MagicMock()]

    asyncio.run(
        executor.aexecute_batch([_make_action("c0"), _make_action("c1")], tool_runner)
    )

    assert threading.current_thread().name not in threads
    assert seen == ["set-by-dispatcher", "set-by-dispatcher"]


# ── 每个任务都需要自己的上下文对象 ──────────────────────── 一个 contextvars.Context 不
# 能同时被两个线程输入 (``RuntimeError: cannot enter context: ... is already entered``),
#  因此这些迫使真正的重叠通过一个屏障。
#


def test_execute_batch_overlapping_tasks_each_get_a_fresh_context(probe) -> None:
    executor = ParallelToolExecutor(max_workers=3)
    barrier = threading.Barrier(3)
    seen: list[str] = []
    lock = threading.Lock()

    def tool_runner(action: Any) -> list[Any]:
        barrier.wait(timeout=_BARRIER_TIMEOUT)
        with lock:
            seen.append(probe.get())
        return ["ok"]

    results = executor.execute_batch(
        [_make_action(f"c{i}", f"tool_{i}") for i in range(3)], tool_runner
    )

    assert results == [["ok"], ["ok"], ["ok"]]
    assert seen == ["set-by-dispatcher"] * 3


def test_aexecute_batch_overlapping_tasks_each_get_a_fresh_context(probe) -> None:
    executor = ParallelToolExecutor(max_workers=3)
    barrier = threading.Barrier(3)
    seen: list[str] = []
    lock = threading.Lock()

    def tool_runner(action: Any) -> list[Any]:
        barrier.wait(timeout=_BARRIER_TIMEOUT)
        with lock:
            seen.append(probe.get())
        return ["ok"]

    results = asyncio.run(
        executor.aexecute_batch(
            [_make_action(f"c{i}", f"tool_{i}") for i in range(3)], tool_runner
        )
    )

    assert results == [["ok"], ["ok"], ["ok"]]
    assert seen == ["set-by-dispatcher"] * 3


# ── 在调度程序下的工作嵌套中创建的 OTel 跨度──── lmnr 未初始化：没有副本，任何内容都不
# 会跨越线程边界。
#


def _span_nesting_runner(
    tracer: Tracer, recorded: list[SpanContext], lock: threading.Lock
) -> Any:
    def tool_runner(action: Any) -> list[Any]:
        with tracer.start_as_current_span(f"tool-{action.tool_call_id}") as span:
            with lock:
                recorded.append(span.get_span_context())
        return [MagicMock()]

    return tool_runner


def test_execute_batch_worker_spans_nest_under_dispatcher_without_lmnr(
    tracing,
) -> None:
    tracer, exporter = tracing
    executor = ParallelToolExecutor(max_workers=2)
    recorded: list[SpanContext] = []
    tool_runner = _span_nesting_runner(tracer, recorded, threading.Lock())

    with tracer.start_as_current_span("agent.step") as parent:
        parent_ctx = parent.get_span_context()
        executor.execute_batch(
            [_make_action("c0", "tool_0"), _make_action("c1", "tool_1")], tool_runner
        )

    assert {c.trace_id for c in recorded} == {parent_ctx.trace_id}
    for tool_call_id in ("c0", "c1"):
        span = _finished(exporter, f"tool-{tool_call_id}")
        assert span.parent is not None
        assert span.parent.span_id == parent_ctx.span_id


def test_aexecute_batch_worker_spans_nest_under_dispatcher_without_lmnr(
    tracing,
) -> None:
    tracer, exporter = tracing
    executor = ParallelToolExecutor(max_workers=2)
    recorded: list[SpanContext] = []
    tool_runner = _span_nesting_runner(tracer, recorded, threading.Lock())

    async def main() -> SpanContext:
        with tracer.start_as_current_span("agent.astep") as parent:
            await executor.aexecute_batch(
                [_make_action("c0", "tool_0"), _make_action("c1", "tool_1")],
                tool_runner,
            )
            return parent.get_span_context()

    parent_ctx = asyncio.run(main())

    assert {c.trace_id for c in recorded} == {parent_ctx.trace_id}
    for tool_call_id in ("c0", "c1"):
        span = _finished(exporter, f"tool-{tool_call_id}")
        assert span.parent is not None
        assert span.parent.span_id == parent_ctx.span_id


# ── lmnr 自己的仪器未发现的东西────────────── lmnr 补丁 ThreadPoolExecutor.submit 来携
# 带其隔离的上下文，所以
#
# @observe spans nest across the boundary with or without this executor's
# 复制。 不携带OTel global上下文和plainContextVars； 这些引脚表明副本弥补了 lmnr 自己的
# 配置中的这两个差距。
#


def test_execute_batch_worker_spans_nest_under_dispatcher_with_lmnr(
    tracing, lmnr_initialized
) -> None:
    _assert_lmnr_wraps_submit()
    tracer, exporter = tracing
    executor = ParallelToolExecutor(max_workers=2)
    recorded: list[SpanContext] = []
    tool_runner = _span_nesting_runner(tracer, recorded, threading.Lock())

    with tracer.start_as_current_span("agent.step") as parent:
        parent_ctx = parent.get_span_context()
        executor.execute_batch(
            [_make_action("c0", "tool_0"), _make_action("c1", "tool_1")], tool_runner
        )

    assert {c.trace_id for c in recorded} == {parent_ctx.trace_id}
    for tool_call_id in ("c0", "c1"):
        span = _finished(exporter, f"tool-{tool_call_id}")
        assert span.parent is not None
        assert span.parent.span_id == parent_ctx.span_id


def test_aexecute_batch_worker_spans_nest_under_dispatcher_with_lmnr(
    tracing, lmnr_initialized
) -> None:
    _assert_lmnr_wraps_submit()
    tracer, exporter = tracing
    executor = ParallelToolExecutor(max_workers=2)
    recorded: list[SpanContext] = []
    tool_runner = _span_nesting_runner(tracer, recorded, threading.Lock())

    async def main() -> SpanContext:
        with tracer.start_as_current_span("agent.astep") as parent:
            await executor.aexecute_batch(
                [_make_action("c0", "tool_0"), _make_action("c1", "tool_1")],
                tool_runner,
            )
            return parent.get_span_context()

    parent_ctx = asyncio.run(main())

    assert {c.trace_id for c in recorded} == {parent_ctx.trace_id}
    for tool_call_id in ("c0", "c1"):
        span = _finished(exporter, f"tool-{tool_call_id}")
        assert span.parent is not None
        assert span.parent.span_id == parent_ctx.span_id


def test_execute_batch_propagates_contextvars_with_lmnr(
    probe, lmnr_initialized
) -> None:
    _assert_lmnr_wraps_submit()
    executor = ParallelToolExecutor(max_workers=2)
    seen: list[str] = []
    lock = threading.Lock()

    def tool_runner(action: Any) -> list[Any]:
        with lock:
            seen.append(probe.get())
        return [MagicMock()]

    executor.execute_batch([_make_action("c0"), _make_action("c1")], tool_runner)

    assert seen == ["set-by-dispatcher", "set-by-dispatcher"]


def test_lmnr_isolated_context_survives_the_context_copy(lmnr_initialized) -> None:
    """该副本不得破坏 lmnr 已为其自身传播的内容。"""
    from lmnr.opentelemetry_lib.tracing.context import (
        attach_context,
        detach_context,
        get_current_context,
    )

    key = create_key("openhands.test.isolated")
    executor = ParallelToolExecutor(max_workers=2)
    seen: list[Any] = []
    lock = threading.Lock()

    def tool_runner(action: Any) -> list[Any]:
        with lock:
            seen.append(get_value(key, get_current_context()))
        return [MagicMock()]

    token = attach_context(set_value(key, "isolated-parent", Context()))
    try:
        executor.execute_batch([_make_action("c0"), _make_action("c1")], tool_runner)
    finally:
        detach_context(token)

    assert seen == ["isolated-parent", "isolated-parent"]


# ── 端到端通过真实的智能体且 tool_concurrency_limit=2 ──
# ``observe`` 被原始 OTel 替代品取代，因此这会端到端地执行 no-lmnr 路径。 与 lmnr 一起生
# 活的是真正的``observe``父母，反对 lmnr 的孤立上下文，而 lmnr 则跨越了边界本身。
#


class _SpanCtxAction(Action):
    value: str = ""


class _SpanCtxObservation(Observation):
    result: str = ""


class _SpanCtxExecutor(ToolExecutor[_SpanCtxAction, _SpanCtxObservation]):
    def __call__(
        self, action: _SpanCtxAction, conversation=None
    ) -> _SpanCtxObservation:
        return _SpanCtxObservation(result=action.value)


class _SpanCtxToolA(ToolDefinition[_SpanCtxAction, _SpanCtxObservation]):
    name = "echo_a"

    @classmethod
    def create(cls, conv_state: "ConversationState | None" = None) -> Sequence[Self]:
        return [
            cls(
                description="Echoes its input",
                action_type=_SpanCtxAction,
                observation_type=_SpanCtxObservation,
                executor=_SpanCtxExecutor(),
            )
        ]


class _SpanCtxToolB(_SpanCtxToolA):
    name = "echo_b"


register_tool("SpanCtxEchoToolA", _SpanCtxToolA)
register_tool("SpanCtxEchoToolB", _SpanCtxToolB)


def _response_with_two_tool_calls() -> ModelResponse:
    return ModelResponse(
        id="mock-response-1",
        choices=[
            Choices(
                index=0,
                message=LiteLLMMessage(
                    role="assistant",
                    content="calling both tools",
                    tool_calls=[
                        ChatCompletionMessageToolCall(
                            id=f"call_{name}",
                            type="function",
                            function=Function(name=name, arguments='{"value": "hi"}'),
                        )
                        for name in ("echo_a", "echo_b")
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
        created=0,
        model="test-model",
        object="chat.completion",
    )


def test_agent_step_tool_spans_nest_under_dispatcher_without_lmnr(tracing) -> None:
    tracer, exporter = tracing
    llm = LLM(
        usage_id="test-llm",
        model="test-model",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )
    agent = Agent(
        llm=llm,
        tools=[Tool(name="SpanCtxEchoToolA"), Tool(name="SpanCtxEchoToolB")],
        tool_concurrency_limit=2,
    )
    conversation = Conversation(agent=agent, callbacks=[])
    worker_threads: set[str] = set()

    def fake_observe(**kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            def wrapper(*args: Any, **fkwargs: Any) -> Any:
                worker_threads.add(threading.current_thread().name)
                with tracer.start_as_current_span("tool.execute"):
                    return fn(*args, **fkwargs)

            return wrapper

        return decorator

    with (
        patch(
            "openhands.sdk.llm.llm.litellm_completion",
            side_effect=lambda messages, **kw: _response_with_two_tool_calls(),
        ),
        patch(
            "openhands.sdk.agent.agent.should_enable_observability", return_value=True
        ),
        # 运行未修饰的 ``step``。 它的``@observe``包装器在任何过程中observability开启时
        # ，构建一个真实的lmnr范围，并缓存它——它会介于这个测试的父范围和工具范围之间。
        # 如果没有这个，环境 ``LMNR_*`` 环境变量将决定测试是否测量其名称所声称的内容。
        #
        patch.object(Agent, "step", inspect.unwrap(Agent.step)),
        patch("openhands.sdk.agent.agent.observe", side_effect=fake_observe),
    ):
        conversation.send_message(
            Message(role="user", content=[TextContent(text="please echo hi")])
        )
        with tracer.start_as_current_span("agent.step") as parent:
            parent_ctx = parent.get_span_context()
            agent.step(conversation, on_event=lambda e: None)

    assert threading.current_thread().name not in worker_threads, (
        "tool calls did not run off the dispatching thread; "
        "the test is not exercising the parallel path"
    )
    tool_spans = [s for s in exporter.get_finished_spans() if s.name == "tool.execute"]
    assert len(tool_spans) == 2
    for span in tool_spans:
        assert span.context is not None
        assert span.context.trace_id == parent_ctx.trace_id
        assert span.parent is not None
        assert span.parent.span_id == parent_ctx.span_id
