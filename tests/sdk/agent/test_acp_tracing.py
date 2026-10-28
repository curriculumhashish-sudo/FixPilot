"""ACP 回合必须发出 LLM/TOOL 跨度，形状与原生智能体的跨度相似。

跟踪消费者根据``span_type``加上LLM跨度的``output``（辅助消息列表）和每个TOOL跨度的轨
迹重建轨迹
``output``. 他们断言合同而不是跨度仅仅存在。
"""

import json
from typing import Any
from unittest.mock import patch

import pytest

from openhands.sdk.agent.acp_tracing import (
    ACP_SERVER_METADATA_KEY,
    AGENT_KIND_METADATA_KEY,
    TURN_SPAN_NAME,
    ACPTurnTrace,
)


METADATA_PREFIX = "lmnr.association.properties.metadata."


@pytest.fixture
def exported():
    """无论环境 lmnr 状态如何，捕获此测试发出的跨度。

    两条路径，因为这些测试必须永远不跳过——跳过的跟踪测试与通过的测试是无法区分的，
    ``LMNR_*`` 环境变量在CI 中设置。 当 lmnr 已经启动（环境变量或早
    期测试）时，其跨度处理器将被借用并恢复； 这也使测试范围远离其配置的任何实际端点。
     否则，这里就会构建一个，内存导出器已安装 * 在 *
    ``initialize`` 之前，这样就不会创建任何 OTLP 端点 —— 一个不可达的端点会在稍后测试
    中重试导出，带有回退。
    """
    import threading

    from lmnr import Laminar
    from lmnr.opentelemetry_lib.opentelemetry.instrumentation.threading import (
        ThreadingInstrumentor,
    )
    from lmnr.opentelemetry_lib.tracing import TracerWrapper
    from lmnr.opentelemetry_lib.tracing.processor import LaminarSpanProcessor
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    borrowed = TracerWrapper.verify_initialized()
    original_thread_init = threading.Thread.__init__

    if not borrowed:
        TracerWrapper(
            exporter=exporter,
            disable_batch=True,
            instruments=set(),
            set_global_tracer_provider=False,
        )
    if not Laminar.is_initialized():
        # 尊重现有的 TracerWrapper，而不是构建第二个。
        Laminar.initialize(
            project_api_key="test-key",
            disable_batch=True,
            instruments=set(),
            set_global_tracer_provider=False,
        )

    processor = TracerWrapper.instance._span_processor
    assert isinstance(processor, LaminarSpanProcessor)
    previous = processor.instance
    processor.instance = SimpleSpanProcessor(exporter)
    try:
        yield exporter.get_finished_spans
    finally:
        processor.instance = previous
        if not borrowed:
            Laminar.shutdown()
            ThreadingInstrumentor().uninstrument()
            threading.Thread.__init__ = original_thread_init  # type: ignore[method-assign]
            TracerWrapper._original_thread_init = None
            if hasattr(TracerWrapper, "instance"):
                del TracerWrapper.instance


def _tool_entry(call_id: str, **over: Any) -> dict[str, Any]:
    entry = {
        "tool_call_id": call_id,
        "title": f"Read {call_id}.py",
        "tool_kind": "read",
        "status": "completed",
        "raw_input": {"path": f"{call_id}.py"},
        "raw_output": f"contents of {call_id}",
        "content": None,
    }
    entry.update(over)
    return entry


def _by_type(spans, span_type: str):
    return [s for s in spans if (s.attributes or {}).get("lmnr.span.type") == span_type]


def _meta(span, key: str):
    return (span.attributes or {}).get(METADATA_PREFIX + key)


def _tool_text(span) -> str:
    """以消费者内容扁平化器的方式拉出结果文本。"""
    payload = json.loads((span.attributes or {})["lmnr.span.output"])
    return payload["content"][0]["text"]


def test_turn_emits_an_llm_span_whose_output_is_an_assistant_message(exported):
    trace = ACPTurnTrace(acp_server="claude-code", model_id="claude-sonnet-4-5")
    trace.start_turn("read the file")
    entry = _tool_entry("call_1")
    trace.tool_started(entry)
    trace.tool_finished(entry)
    trace.finish_turn("Read it.", "thinking...", [entry])

    llm = _by_type(exported(), "LLM")
    assert len(llm) == 1
    assert llm[0].name == TURN_SPAN_NAME

    output = json.loads((llm[0].attributes or {})["lmnr.span.output"])
    assert isinstance(output, list) and len(output) == 1
    message = output[0]
    assert message["role"] == "assistant"
    assert message["content"] == "Read it."
    assert message["reasoning_content"] == "thinking..."

    # 导出器读取每个工具调用的 id + function.name/参数。
    (call,) = message["tool_calls"]
    assert call["id"] == "call_1"
    assert call["function"]["name"] == "read"
    assert json.loads(call["function"]["arguments"]) == {"path": "call_1.py"}


def test_tool_span_carries_output_and_correlating_call_id(exported):
    trace = ACPTurnTrace(acp_server="codex", model_id=None)
    trace.start_turn("go")
    entry = _tool_entry("call_9")
    trace.tool_started(entry)
    trace.tool_finished(entry)
    trace.finish_turn("done", "", [entry])

    (tool,) = _by_type(exported(), "TOOL")
    assert tool.name == "Read call_9.py"
    assert _tool_text(tool) == "contents of call_9"
    assert _meta(tool, "tool_call_id") == "call_9"


def test_tool_spans_are_children_of_the_turn_span(exported):
    trace = ACPTurnTrace(acp_server="codex", model_id=None)
    trace.start_turn("go")
    entry = _tool_entry("call_1")
    trace.tool_started(entry)
    trace.tool_finished(entry)
    trace.finish_turn("done", "", [entry])

    spans = exported()
    (llm,) = _by_type(spans, "LLM")
    (tool,) = _by_type(spans, "TOOL")
    assert tool.parent is not None
    assert tool.parent.span_id == llm.context.span_id
    assert tool.context.trace_id == llm.context.trace_id


def test_every_span_is_marked_acp_and_names_the_server(exported):
    trace = ACPTurnTrace(acp_server="gemini-cli", model_id="gemini-2.5-pro")
    trace.start_turn("go")
    entry = _tool_entry("call_1")
    trace.tool_started(entry)
    trace.tool_finished(entry)
    trace.finish_turn("done", "", [entry])

    spans = _by_type(exported(), "LLM") + _by_type(exported(), "TOOL")
    assert len(spans) == 2
    for span in spans:
        assert _meta(span, AGENT_KIND_METADATA_KEY) == "acp"
        assert _meta(span, ACP_SERVER_METADATA_KEY) == "gemini-cli"
        assert _meta(span, "acp_model") == "gemini-2.5-pro"


def test_tool_call_ids_survive_out_of_order_completion(exported):
    """两个调用在其中一个调用关闭之前打开 - 每个结果必须保留自己的 id。"""
    trace = ACPTurnTrace(acp_server="codex", model_id=None)
    trace.start_turn("go")
    first, second = _tool_entry("call_a"), _tool_entry("call_b")
    trace.tool_started(first)
    trace.tool_started(second)
    trace.tool_finished(second)
    trace.tool_finished(first)
    trace.finish_turn("done", "", [first, second])

    tools = _by_type(exported(), "TOOL")
    pairs = {_meta(t, "tool_call_id"): _tool_text(t) for t in tools}
    assert pairs == {
        "call_a": "contents of call_a",
        "call_b": "contents of call_b",
    }


def test_abandon_closes_a_tool_span_left_open_by_a_failed_turn(exported):
    trace = ACPTurnTrace(acp_server="codex", model_id=None)
    trace.start_turn("go")
    trace.tool_started(_tool_entry("call_1", status="in_progress"))
    trace.abandon()

    # 未结束的跨度根本不会被导出——结果将会消失。
    assert len(_by_type(exported(), "TOOL")) == 1
    assert len(_by_type(exported(), "LLM")) == 1


def test_finish_turn_closes_a_tool_call_the_server_never_terminated(exported):
    trace = ACPTurnTrace(acp_server="codex", model_id=None)
    trace.start_turn("go")
    entry = _tool_entry("call_1", status="in_progress")
    trace.tool_started(entry)
    trace.finish_turn("done", "", [entry])

    (tool,) = _by_type(exported(), "TOOL")
    assert _tool_text(tool) == "contents of call_1"


def test_tracing_is_inert_when_observability_is_disabled(monkeypatch, exported):
    monkeypatch.setattr(
        "openhands.sdk.agent.acp_tracing.should_enable_observability",
        lambda: False,
    )
    trace = ACPTurnTrace(acp_server="codex", model_id=None)
    trace.start_turn("go")
    entry = _tool_entry("call_1")
    trace.tool_started(entry)
    trace.tool_finished(entry)
    trace.finish_turn("done", "", [entry])

    assert exported() == ()


def test_a_broken_span_backend_never_breaks_the_turn(monkeypatch, exported):
    """可观察性失败必须对智能体保持不可见。"""
    import lmnr

    monkeypatch.setattr(
        lmnr.Laminar, "start_span", lambda **kw: (_ for _ in ()).throw(RuntimeError())
    )
    trace = ACPTurnTrace(acp_server="codex", model_id=None)
    trace.start_turn("go")
    entry = _tool_entry("call_1")
    trace.tool_started(entry)
    trace.tool_finished(entry)
    trace.finish_turn("done", "", [entry])
    trace.abandon()


def test_a_server_that_omits_raw_input_still_records_what_it_could(exported):
    """Codex 未发送 ``raw_input``； 标题是通话的唯一信号。"""
    trace = ACPTurnTrace(acp_server="codex", model_id=None)
    trace.start_turn("go")
    entry = _tool_entry("call_1", raw_input=None, title="Read file '/a/b.py'")
    trace.tool_started(entry)
    trace.tool_finished(entry)
    trace.finish_turn("done", "", [entry])

    (llm,) = _by_type(exported(), "LLM")
    (call,) = json.loads((llm.attributes or {})["lmnr.span.output"])[0]["tool_calls"]
    assert json.loads(call["function"]["arguments"]) == {"title": "Read file '/a/b.py'"}


def test_a_tool_starting_during_teardown_does_not_break_it(exported):
    """超时转向会导致呼叫者线程崩溃，而 ACP 门户
    线程仍然可以传递 ToolCallStart，因此开放跨度表在拆卸过程中发生了变化。 这里是确定
    性的：赛车插入发生在近距离回调内部，而不是真实的线程中。
    """
    trace = ACPTurnTrace(acp_server="codex", model_id=None)
    trace.start_turn("go")
    trace.tool_started(_tool_entry("call_1", status="in_progress"))

    original_close = ACPTurnTrace._close_tool_span
    raced: list[str] = []

    def racing_close(span, entry):
        if not raced:
            raced.append("x")
            trace.tool_started(_tool_entry("call_racer", status="in_progress"))
        original_close(span, entry)

    with patch.object(ACPTurnTrace, "_close_tool_span", staticmethod(racing_close)):
        trace.abandon()  # 不得引发“字典在迭代期间更改大小”

    trace.abandon()  # 幂等，并关闭竞赛留下的任何内容
    assert len(_by_type(exported(), "LLM")) == 1


@pytest.mark.asyncio
async def test_a_call_that_starts_terminal_closes_at_that_notification(exported):
    """有些服务器在第一个通知时报告终端状态，所以没有
    稍后过渡到来。 仅在 ``finish_turn`` 处平仓会将本回合的 REST 记入该工具调用的帐单
    。 通过 ``session_update`` 驱动，因此接
    线
    ``acp_agent`` 是正在测试的内容，而不仅仅是 ``ACPTurnTrace``。
    """
    from unittest.mock import MagicMock

    from acp.schema import ToolCallStart

    from openhands.sdk.agent.acp_agent import _OpenHandsACPBridge

    start = MagicMock(spec=ToolCallStart)
    start.tool_call_id = "tc-terminal"
    start.title = "git status"
    start.kind = "execute"
    start.status = "completed"  # 第一个通知时的终端
    start.raw_input = {"command": "git status"}
    start.raw_output = "nothing to commit"
    start.content = None

    client = _OpenHandsACPBridge()
    client.on_event = lambda _event: None
    client.trace = ACPTurnTrace(acp_server="codex", model_id=None)
    client.trace.start_turn("go")

    await client.session_update("s1", start)

    # 已导出，i.e。 结束——在回合结束之前。
    (tool,) = _by_type(exported(), "TOOL")
    assert _meta(tool, "tool_call_id") == "tc-terminal"
    assert tool.end_time is not None
    closed_at = tool.end_time

    client.trace.finish_turn("done", "", client.accumulated_tool_calls)

    (llm,) = _by_type(exported(), "LLM")
    assert tool.end_time == closed_at, "finish_turn must not re-close the span"
    assert llm.end_time is not None and closed_at <= llm.end_time


def test_an_oversized_block_prompt_is_capped(exported):
    """生产通道 ``prompt_blocks`` — ACP 内容块的列表，而不是
    字符串 - 因此仅理解字符串的上限永远不会应用于真实的提示词，并且一个 Base64 图像块
    可以是兆字节。
    """
    from acp.schema import TextContentBlock

    blocks = [
        TextContentBlock(text="describe this", type="text"),
        TextContentBlock(text="A" * 400_000, type="text"),  # 代表base64图像数据
    ]
    trace = ACPTurnTrace(acp_server="claude-code", model_id=None)
    trace.start_turn(blocks)
    trace.finish_turn("done", "", [])

    (llm,) = _by_type(exported(), "LLM")
    recorded = (llm.attributes or {})["lmnr.span.input"]
    assert len(recorded) < 200_000, "oversized prompt reached the backend uncapped"
    assert "[truncated]" in recorded
    assert "describe this" in recorded  # 提示词的头幸存下来


def test_a_normal_block_prompt_is_recorded_unchanged(exported):
    from acp.schema import TextContentBlock

    trace = ACPTurnTrace(acp_server="claude-code", model_id=None)
    trace.start_turn([TextContentBlock(text="read the file", type="text")])
    trace.finish_turn("done", "", [])

    (llm,) = _by_type(exported(), "LLM")
    recorded = (llm.attributes or {})["lmnr.span.input"]
    assert "read the file" in recorded
    assert "[truncated]" not in recorded


def test_a_secret_in_the_prompt_is_masked_before_it_is_recorded(exported):
    """提示词是用户自己的文本，因此它可以携带粘贴的凭据。"""
    from acp.schema import TextContentBlock

    secret = "ghp_averyrealisticlookingtoken0123456789"

    def mask(text: str) -> str:
        return text.replace(secret, "<secret-hidden>")

    trace = ACPTurnTrace(acp_server="claude-code", model_id=None, mask=mask)
    trace.start_turn(
        [TextContentBlock(text=f"deploy using {secret} please", type="text")]
    )
    trace.finish_turn("done", "", [])

    (llm,) = _by_type(exported(), "LLM")
    recorded = (llm.attributes or {})["lmnr.span.input"]
    assert secret not in recorded
    assert "<secret-hidden>" in recorded
    assert "deploy using" in recorded


def test_the_prompt_is_dropped_rather_than_recorded_raw_if_masking_fails(exported):
    def broken_mask(text: str) -> str:
        raise RuntimeError("masker unavailable")

    trace = ACPTurnTrace(acp_server="claude-code", model_id=None, mask=broken_mask)
    trace.start_turn("deploy using ghp_secret please")
    trace.finish_turn("done", "", [])

    (llm,) = _by_type(exported(), "LLM")
    assert "ghp_secret" not in str((llm.attributes or {}).get("lmnr.span.input"))
