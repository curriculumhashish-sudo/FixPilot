"""测试 conversation.interrupt() — arun() 的即时取消。

涵盖：
- 异步路径验证（实际上调用的是完成，而不是同步回退方案）
- CancelledError 未从 arun() 重新提出
- interrupt() 自然完成后（无操作）
- 多次快速 interrupt() 呼叫
- 取消 token 生命周期（每次运行创建，退出时清除）
- ParallelToolExecutor 跳过取消的工具
"""

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest
from litellm.types.utils import ModelResponse
from pydantic import PrivateAttr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.cancellation import CancellationToken
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event import AgentErrorEvent, InterruptEvent
from openhands.sdk.llm import LLM, LLMResponse, Message, MessageToolCall, TextContent
from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage


def _make_response(model_name: str = "test-slow") -> LLMResponse:
    return LLMResponse(
        message=Message(
            role="assistant",
            content=[TextContent(text="done")],
        ),
        metrics=MetricsSnapshot(
            model_name=model_name,
            accumulated_cost=0.0,
            max_budget_per_task=0.0,
            accumulated_token_usage=TokenUsage(model=model_name),
        ),
        raw_response=MagicMock(spec=ModelResponse, id="s1"),
    )


class SlowLLM(LLM):
    """LLM 阻止完成以模拟长时间运行的调用。"""

    _sleep_seconds: float = PrivateAttr(default=10.0)

    def __init__(self, *, sleep_seconds: float = 10.0):
        super().__init__(model="test-slow", usage_id="test-slow")
        self._sleep_seconds = sleep_seconds

    def completion(  # type: ignore[override]
        self, messages, tools=None, **kw
    ) -> LLMResponse:
        import time

        time.sleep(self._sleep_seconds)
        return _make_response()

    async def acompletion(  # type: ignore[override]
        self, messages, tools=None, **kw
    ) -> LLMResponse:
        await asyncio.sleep(self._sleep_seconds)
        return _make_response()


def _make_conversation(llm: LLM, tmp_path) -> LocalConversation:
    agent = Agent(llm=llm, tools=[])
    conv = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        visualizer=None,
    )
    conv.send_message("hello")
    return conv


@pytest.mark.asyncio
async def test_interrupt_cancels_arun_immediately(tmp_path):
    """interrupt() 应在 LLM 通话中取消 arun() 并设置 PAUSED。"""
    conv = _make_conversation(SlowLLM(sleep_seconds=60.0), tmp_path)

    task = asyncio.create_task(conv.arun())

    # 让事件循环启动arun()并进入LLM睡眠
    await asyncio.sleep(0.05)

    # 中断应取消正在进行的 LLM 调用
    conv.interrupt()

    # arun() should return quickly (it catches CancelledError)
    await asyncio.wait_for(task, timeout=2.0)

    assert conv.state.execution_status == ConversationExecutionStatus.PAUSED

    # 应该已发出 InterruptEvent
    events = list(conv.state.events)
    interrupt_events = [e for e in events if isinstance(e, InterruptEvent)]
    assert len(interrupt_events) == 1


@pytest.mark.asyncio
async def test_interrupt_without_arun_falls_back_to_pause(tmp_path):
    """interrupt() 没有活动的 arun() 应该回退到 pause()。"""
    conv = _make_conversation(SlowLLM(sleep_seconds=60.0), tmp_path)

    # 手动设置为 RUNNING 以验证暂停回退方案
    conv._state.execution_status = ConversationExecutionStatus.RUNNING

    conv.interrupt()

    assert conv.state.execution_status == ConversationExecutionStatus.PAUSED


@pytest.mark.asyncio
async def test_arun_task_cleared_after_interrupt(tmp_path):
    """arun() 完成后（通过中断），_arun_task 应为 None。"""
    conv = _make_conversation(SlowLLM(sleep_seconds=60.0), tmp_path)

    task = asyncio.create_task(conv.arun())
    await asyncio.sleep(0.05)
    conv.interrupt()
    await asyncio.wait_for(task, timeout=2.0)

    assert conv._arun_task is None


@pytest.mark.asyncio
async def test_interrupt_is_resumable(tmp_path):
    """中断后，可以使用新的 arun() 恢复通话。"""

    class CountingLLM(LLM):
        """LLM 立即完成，对调用进行计数。"""

        _call_count: int = PrivateAttr(default=0)

        def __init__(self):
            super().__init__(model="test-counting", usage_id="test-c")

        def completion(  # type: ignore[override]
            self, messages, tools=None, **kw
        ) -> LLMResponse:
            self._call_count += 1
            return _make_response("test-counting")

        async def acompletion(  # type: ignore[override]
            self, messages, tools=None, **kw
        ) -> LLMResponse:
            self._call_count += 1
            return _make_response("test-counting")

    llm = CountingLLM()
    conv = _make_conversation(llm, tmp_path)

    # 第一次运行应该正常完成（智能体表示“完成”→ FINISHED）
    await conv.arun()
    assert conv.state.execution_status == ConversationExecutionStatus.FINISHED
    assert llm._call_count == 1

    # 发送另一条消息并再次运行 — 应该可以工作
    conv.send_message("continue")
    await conv.arun()
    assert llm._call_count == 2


@pytest.mark.asyncio
async def test_arun_calls_acompletion_not_completion(tmp_path):
    """验证 arun() 执行异步路径（完成）。"""

    class TrackingLLM(LLM):
        _sync_calls: int = PrivateAttr(default=0)
        _async_calls: int = PrivateAttr(default=0)

        def __init__(self):
            super().__init__(model="test-track", usage_id="test-t")

        def completion(self, messages, tools=None, **kw) -> LLMResponse:  # type: ignore[override]
            self._sync_calls += 1
            return _make_response("test-track")

        async def acompletion(self, messages, tools=None, **kw) -> LLMResponse:  # type: ignore[override]
            self._async_calls += 1
            return _make_response("test-track")

    llm = TrackingLLM()
    conv = _make_conversation(llm, tmp_path)
    await conv.arun()

    assert llm._async_calls == 1, "arun() should call acompletion"
    assert llm._sync_calls == 0, "arun() should NOT call sync completion"


@pytest.mark.asyncio
async def test_arun_does_not_raise_cancelled_error(tmp_path):
    """CancelledError 必须从 arun() 传播出不。"""
    conv = _make_conversation(SlowLLM(sleep_seconds=60.0), tmp_path)

    task = asyncio.create_task(conv.arun())
    await asyncio.sleep(0.05)
    conv.interrupt()

    # 如果 CancelledError 传播，wait_for 就会提高它。 arun() 应该毫无例外地干净地返回。
    #
    await asyncio.wait_for(task, timeout=2.0)
    # 如果我们到达这里，则不会提出 CancelledError — 测试通过。


@pytest.mark.asyncio
async def test_interrupt_after_natural_completion_is_noop(tmp_path):
    """arun() 自然完成后的 interrupt() 应该是安全的无操作。"""

    class InstantLLM(LLM):
        def __init__(self):
            super().__init__(model="test-instant", usage_id="test-i")

        def completion(self, messages, tools=None, **kw) -> LLMResponse:  # type: ignore[override]
            return _make_response("test-instant")

        async def acompletion(self, messages, tools=None, **kw) -> LLMResponse:  # type: ignore[override]
            return _make_response("test-instant")

    conv = _make_conversation(InstantLLM(), tmp_path)
    await conv.arun()
    assert conv.state.execution_status == ConversationExecutionStatus.FINISHED

    # interrupt() 完成后 — 不应崩溃或更改状态
    conv.interrupt()
    assert conv.state.execution_status == ConversationExecutionStatus.FINISHED


@pytest.mark.asyncio
async def test_multiple_rapid_interrupts(tmp_path):
    """多个快速 interrupt() 调用不应崩溃。"""
    conv = _make_conversation(SlowLLM(sleep_seconds=60.0), tmp_path)

    task = asyncio.create_task(conv.arun())
    await asyncio.sleep(0.05)

    # 快速触发多个中断
    conv.interrupt()
    conv.interrupt()
    conv.interrupt()

    await asyncio.wait_for(task, timeout=2.0)
    assert conv.state.execution_status == ConversationExecutionStatus.PAUSED


# ── CancellationToken 单元测试 ──────────────────────────────────────


def test_cancellation_token_basic():
    """CancellationToken 开始时未取消，在 cancel() 之后取消。"""
    token = CancellationToken()
    assert not token.is_cancelled
    token.cancel()
    assert token.is_cancelled
    # 幂等
    token.cancel()
    assert token.is_cancelled


# ── token 生命周期测试 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_token_created_and_cleared_during_arun(tmp_path):
    """在 arun() 中创建一个新的 CancellationToken，并在最后清除。"""

    class InstantLLM(LLM):
        def __init__(self):
            super().__init__(model="test-instant", usage_id="test-i")

        def completion(self, messages, tools=None, **kw) -> LLMResponse:  # type: ignore[override]
            return _make_response("test-instant")

        async def acompletion(self, messages, tools=None, **kw) -> LLMResponse:  # type: ignore[override]
            return _make_response("test-instant")

    conv = _make_conversation(InstantLLM(), tmp_path)
    assert conv._cancel_token is None  # 在任何跑步之前

    await conv.arun()

    # arun()完成后，token应该被清除
    assert conv._cancel_token is None


@pytest.mark.asyncio
async def test_interrupt_sets_cancel_token(tmp_path):
    """interrupt() 应在取消任务之前设置取消 token。"""
    conv = _make_conversation(SlowLLM(sleep_seconds=60.0), tmp_path)

    task = asyncio.create_task(conv.arun())
    await asyncio.sleep(0.05)

    # 当 arun 处于活动状态时，token 应该存在
    assert conv._cancel_token is not None
    assert not conv._cancel_token.is_cancelled

    conv.interrupt()
    await asyncio.wait_for(task, timeout=2.0)

    # 中断后，取消的 token 被保留（未清除），因此比 arun() 寿命更长的工具线程仍然可以观
    # 察它。
    #
    assert conv._cancel_token is not None
    assert conv._cancel_token.is_cancelled


@pytest.mark.asyncio
async def test_cancel_token_stays_observable_after_interrupt(tmp_path):
    """一个从工作人员线程轮询 conversation.cancel_token 的工具
    outlives arun() 必须仍然看到取消，而不是最后用来清除的 None。 下一次运行时会更换
    新的 token。
    """
    conv = _make_conversation(SlowLLM(sleep_seconds=60.0), tmp_path)

    task = asyncio.create_task(conv.arun())
    await asyncio.sleep(0.05)
    conv.interrupt()
    await asyncio.wait_for(task, timeout=2.0)

    # arun() 终于运行了； 通过公共财产进行的后期民意调查（使用什么工具）仍然必须遵守取消
    # 。
    #
    assert conv.cancel_token is not None
    assert conv.cancel_token.is_cancelled

    # 下一次运行会将其替换为新的、未取消的 token。
    conv.send_message("again")
    resumed = asyncio.create_task(conv.arun())
    await asyncio.sleep(0.05)
    assert conv.cancel_token is not None
    assert not conv.cancel_token.is_cancelled
    conv.interrupt()
    await asyncio.wait_for(resumed, timeout=2.0)


# ── ParallelToolExecutor 取消测试 ────────────────────────────


def _make_action_event(tool_name: str, call_id: str):
    """构建一个最小化的 ActionEvent 用于执行器测试。"""
    from openhands.sdk.event import ActionEvent

    return ActionEvent(
        thought=[TextContent(text="test")],
        tool_call=MessageToolCall(
            id=call_id,
            name=tool_name,
            arguments="{}",
            origin="completion",
        ),
        tool_name=tool_name,
        tool_call_id=call_id,
        llm_response_id="resp-1",
    )


def test_run_safe_skips_cancelled_tool():
    """当 token 已取消时，_run_safe 应跳过执行。"""
    from openhands.sdk.agent.parallel_executor import ParallelToolExecutor

    executor = ParallelToolExecutor(max_workers=1)
    token = CancellationToken()
    token.cancel()

    action = _make_action_event("my_tool", "tc1")
    runner_called = False

    def tool_runner(ae):
        nonlocal runner_called
        runner_called = True
        return []

    result = executor._run_safe(action, tool_runner, cancel_token=token)

    assert not runner_called, "Tool should not have been executed"
    assert len(result) == 1
    assert isinstance(result[0], AgentErrorEvent)
    assert "cancelled" in result[0].error.lower()


def test_run_safe_runs_without_token():
    """当未提供 token 时，_run_safe 应该正常执行。"""
    from openhands.sdk.agent.parallel_executor import ParallelToolExecutor

    executor = ParallelToolExecutor(max_workers=1)
    action = _make_action_event("my_tool", "tc2")
    runner_called = False

    def tool_runner(ae):
        nonlocal runner_called
        runner_called = True
        return []

    executor._run_safe(action, tool_runner, cancel_token=None)
    assert runner_called


@pytest.mark.asyncio
async def test_execute_batch_skips_all_on_pre_cancelled_token():
    """预先取消的 token 的 execute_batch 会跳过所有工具调用。"""
    from openhands.sdk.agent.parallel_executor import ParallelToolExecutor

    executor = ParallelToolExecutor(max_workers=2)
    token = CancellationToken()
    token.cancel()

    actions = [_make_action_event(f"tool_{i}", f"tc-{i}") for i in range(3)]

    runner_calls: list[str] = []

    def tool_runner(ae):
        runner_calls.append(ae.tool_name)
        return []

    results = executor.execute_batch(actions, tool_runner, cancel_token=token)

    assert len(runner_calls) == 0, "No tools should have been called"
    assert len(results) == 3
    for r in results:
        assert len(r) == 1
        assert isinstance(r[0], AgentErrorEvent)
        assert "cancelled" in r[0].error.lower()


@pytest.mark.asyncio
async def test_arun_runs_init_off_the_event_loop(tmp_path):
    """arun() 将 _ensure_agent_ready() 卸载给工作人员线程。

    回归对于智能体-canvas#1072：ACP 智能体通过 *blocking* LookupSecret.get_value()（
    同步 httpx.get）解析
    init_state 中的凭据。 如果arun()在事件循环上运行，并且查找指回同一个单进程服务器
    ，它会冻结负责它的循环——一个自死锁。 验证 init 运行在与驱
    动循环不同的线程上。
    """
    conv = _make_conversation(SlowLLM(sleep_seconds=0.0), tmp_path)

    loop_thread_id = threading.get_ident()
    captured: dict[str, int] = {}
    real_ensure = conv._ensure_agent_ready

    def spy_ensure() -> None:
        captured["thread_id"] = threading.get_ident()
        real_ensure()

    with patch.object(conv, "_ensure_agent_ready", spy_ensure):
        await asyncio.wait_for(conv.arun(), timeout=5.0)

    assert captured["thread_id"] != loop_thread_id
    assert conv.state.execution_status == ConversationExecutionStatus.FINISHED
