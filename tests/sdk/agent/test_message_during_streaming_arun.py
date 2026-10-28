"""在智能体传输其最终响应时发送的用户消息必须可见。

回归对于智能体-canvas#1900：``astep`` 释放 LLM 调用的状态锁，因此消息可以在状态仍为
RUNNING 的情况下到达中间； ``arun()``用于
在FINISHED上断开而无需重新扫描，将其搁浅。 同步 ``run()`` 使锁跨过台阶，并且从未有间
隙，并在此处用作对照。
"""

import asyncio
import threading
import time
from typing import ClassVar
from unittest.mock import MagicMock

import pytest
from litellm.types.utils import ModelResponse
from pydantic import PrivateAttr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event import MessageEvent
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.event.llm_convertible import UserRejectObservation
from openhands.sdk.llm import LLM, LLMResponse, Message, MessageToolCall, TextContent
from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage
from openhands.sdk.security.confirmation_policy import AlwaysConfirm
from openhands.sdk.tool import Tool, ToolDefinition, ToolExecutor, register_tool
from openhands.sdk.tool.schema import Action, Observation


MODEL = "test-model"


def _finishing_response(text: str = "done") -> LLMResponse:
    """带有 NO 工具调用 -> 智能体的纯文本响应变为 FINISHED。"""
    return LLMResponse(
        message=Message(role="assistant", content=[TextContent(text=text)]),
        metrics=MetricsSnapshot(
            model_name=MODEL,
            accumulated_cost=0.0,
            max_budget_per_task=0.0,
            accumulated_token_usage=TokenUsage(model=MODEL),
        ),
        raw_response=MagicMock(spec=ModelResponse, id="resp-1"),
    )


def _make_conversation(llm: LLM, tmp_path) -> LocalConversation:
    return LocalConversation(
        agent=Agent(llm=llm, tools=[]), workspace=str(tmp_path), visualizer=None
    )


def _saw(calls: list[str], marker: str) -> list[int]:
    """提示词包含 `marker` 的 LLM 个调用的索引。"""
    return [i for i, prompt in enumerate(calls) if marker in prompt]


class _InjectingAsyncLLM(LLM):
    """在 (异步) LLM 呼叫期间从另一个线程发送用户消息。"""

    _convo_box: list = PrivateAttr(default_factory=list)
    _calls: list = PrivateAttr(default_factory=list)
    _probe: dict = PrivateAttr(default_factory=dict)

    def __init__(self):
        super().__init__(model=MODEL, usage_id="test-llm")

    def uses_responses_api(self) -> bool:  # 完成后保持生成
        return False

    async def acompletion(self, *, messages, tools=None, **kwargs):  # type: ignore[override]
        self._calls.append(" ".join(str(m) for m in messages))
        convo: LocalConversation = self._convo_box[0]

        if len(self._calls) == 1:
            lock = convo._state._lock
            self._probe["locked_during_call"] = lock.locked()
            self._probe["status_during_call"] = convo._state.execution_status

            # 一条消息从另一个线程（模仿 run_in_executor）到达中流。
            def _send():
                convo.send_message("second message")

            t = threading.Thread(target=_send)
            t.start()
            await asyncio.to_thread(t.join)

            self._probe["status_after_inject"] = convo._state.execution_status

        return _finishing_response()


class _InjectingSyncLLM(LLM):
    """Control: 在 *同步* 步骤期间注入，锁在此步骤中保持。"""

    _convo_box: list = PrivateAttr(default_factory=list)
    _calls: list = PrivateAttr(default_factory=list)
    _probe: dict = PrivateAttr(default_factory=dict)

    def __init__(self):
        super().__init__(model=MODEL, usage_id="test-llm-sync")

    def uses_responses_api(self) -> bool:
        return False

    def completion(self, messages, tools=None, **kwargs):  # type: ignore[override]
        self._calls.append(" ".join(str(m) for m in messages))
        convo: LocalConversation = self._convo_box[0]

        if len(self._calls) == 1:
            lock = convo._state._lock
            # 同步运行循环在整个步骤中保持状态锁。
            self._probe["locked_during_call"] = lock.locked()

            threading.Thread(
                target=lambda: convo.send_message("second message")
            ).start()

            # 等到发送者在 FIFO 锁上排队，因此运行循环可能无法超越它 - 确定性的，没有睡
            # 眠和希望。
            #
            deadline = time.monotonic() + 5.0
            while not lock._waiters:
                assert time.monotonic() < deadline, "send_message never queued"
                time.sleep(0.001)
            self._probe["sender_enqueued"] = True

        return _finishing_response()


@pytest.mark.asyncio
async def test_message_during_streaming_is_acted_upon(tmp_path):
    """arun() 重新扫描锁释放时到达的消息。"""
    llm = _InjectingAsyncLLM()
    convo = _make_conversation(llm, tmp_path)
    llm._convo_box.append(convo)
    convo.send_message("first message")

    await convo.arun()

    # 比赛发生：锁通话中免费，状态仍为 RUNNING。
    assert llm._probe["locked_during_call"] is False
    assert llm._probe["status_during_call"] == ConversationExecutionStatus.RUNNING
    assert llm._probe["status_after_inject"] == ConversationExecutionStatus.RUNNING

    user_texts = [
        str(e.llm_message)
        for e in convo.state.events
        if isinstance(e, MessageEvent) and e.source == "user"
    ]
    assert any("second message" in t for t in user_texts)

    # 智能体对其进行操作：第二次往返运行并将其传送给模型。
    assert len(llm._calls) == 2, (
        f"expected the message to be picked up (2 LLM calls), got {len(llm._calls)}"
    )
    assert _saw(llm._calls, "second message") == [1]
    assert _saw(llm._calls, "first message") == [0, 1]
    assert convo.state.execution_status == ConversationExecutionStatus.FINISHED


def test_sync_run_absorbs_message_sent_during_step(tmp_path):
    """CONTROL: 同步 run() 路径确实不丢弃消息。"""
    llm = _InjectingSyncLLM()
    convo = _make_conversation(llm, tmp_path)
    llm._convo_box.append(convo)
    convo.send_message("first message")

    convo.run()

    # 锁跨过同步步骤，因此 send_message() 必须等待。
    assert llm._probe["locked_during_call"] is True
    assert llm._probe["sender_enqueued"] is True

    # 它观察到 FINISHED，后退到 IDLE，然后再次运行该消息。
    assert len(llm._calls) == 2, (
        f"sync path should absorb the message (2 LLM calls), got {len(llm._calls)}"
    )
    assert _saw(llm._calls, "second message") == [1]
    assert convo.state.execution_status == ConversationExecutionStatus.FINISHED


class _ConfirmAction(Action):
    command: str


class _ConfirmObservation(Observation):
    result: str

    @property
    def to_llm_content(self):
        return [TextContent(text=self.result)]


class _ConfirmExecutor(ToolExecutor[_ConfirmAction, _ConfirmObservation]):
    def __call__(self, action: _ConfirmAction, conversation=None):
        return _ConfirmObservation(result=f"ran {action.command}")


class _ConfirmTool(ToolDefinition[_ConfirmAction, _ConfirmObservation]):
    name: ClassVar[str] = "async_confirm_tool"

    @classmethod
    def create(cls, conv_state=None, **params):
        return [
            cls(
                description="Tool requiring confirmation",
                action_type=_ConfirmAction,
                observation_type=_ConfirmObservation,
                executor=_ConfirmExecutor(),
            )
        ]


register_tool("async_confirm_tool", _ConfirmTool)


def _tool_call_response(command: str = "run-once") -> LLMResponse:
    """工具调用响应 -> 智能体变为 WAITING_FOR_CONFIRMATION。"""
    return LLMResponse(
        message=Message(
            role="assistant",
            content=[TextContent(text=f"I'll {command}")],
            tool_calls=[
                MessageToolCall(
                    id="call_1",
                    name="async_confirm_tool",
                    arguments=f'{{"command": "{command}"}}',
                    origin="completion",
                )
            ],
        ),
        metrics=MetricsSnapshot(
            model_name=MODEL,
            accumulated_cost=0.0,
            max_budget_per_task=0.0,
            accumulated_token_usage=TokenUsage(model=MODEL),
        ),
        raw_response=MagicMock(spec=ModelResponse, id="resp-confirm"),
    )


class _InjectingAsyncConfirmLLM(LLM):
    """第一次通话提出需要确认的操作，同时显示一条消息
    通话中降落； 第二次调用（待处理操作被取代后）正常完成。
    """

    _convo_box: list = PrivateAttr(default_factory=list)
    _calls: list = PrivateAttr(default_factory=list)

    def __init__(self):
        super().__init__(model=MODEL, usage_id="test-llm-confirm")

    def uses_responses_api(self) -> bool:
        return False

    async def acompletion(self, *, messages, tools=None, **kwargs):  # type: ignore[override]
        self._calls.append(" ".join(str(m) for m in messages))
        convo: LocalConversation = self._convo_box[0]

        if len(self._calls) == 1:

            def _send():
                convo.send_message("second message")

            t = threading.Thread(target=_send)
            t.start()
            await asyncio.to_thread(t.join)
            return _tool_call_response()

        return _finishing_response()


@pytest.mark.asyncio
async def test_message_during_confirmation_wait_supersedes_pending_action(tmp_path):
    """astep() 结束 WAITING_FOR_CONFIRMATION 时登陆的消息必须拒绝
    过时的挂起操作，而不是让运行循环默默地执行它作为下一次迭代的隐式确认。
    """
    llm = _InjectingAsyncConfirmLLM()
    convo = LocalConversation(
        agent=Agent(llm=llm, tools=[Tool(name="async_confirm_tool")]),
        workspace=str(tmp_path),
        visualizer=None,
    )
    llm._convo_box.append(convo)
    convo.set_confirmation_policy(AlwaysConfirm())
    convo.send_message("first message")

    await convo.arun()

    assert len(llm._calls) == 2, (
        f"expected the new message to be picked up (2 LLM calls), got {len(llm._calls)}"
    )
    assert _saw(llm._calls, "second message") == [1]
    assert convo.state.execution_status == ConversationExecutionStatus.FINISHED

    reject_events = [
        e for e in convo.state.events if isinstance(e, UserRejectObservation)
    ]
    assert len(reject_events) == 1, "the stale pending action must be rejected"


@pytest.mark.asyncio
async def test_message_during_confirmation_wait_on_final_iteration_still_rejects(
    tmp_path,
):
    """与上面相同的种族，但落在 WAITING_FOR_CONFIRMATION 的步数
    也是运行的最后一次迭代。 循环仍需在继续之前拒绝待处理的动作 IDLE -- 除此之外
    astep() 立即执行作为隐式确认 run() 调用，同样的错误
    FINISHED/ WAITING_FOR_CONFIRMATION 重新扫描是为了防止。
    """
    llm = _InjectingAsyncConfirmLLM()
    convo = LocalConversation(
        agent=Agent(llm=llm, tools=[Tool(name="async_confirm_tool")]),
        workspace=str(tmp_path),
        visualizer=None,
        max_iteration_per_run=1,
    )
    llm._convo_box.append(convo)
    convo.set_confirmation_policy(AlwaysConfirm())
    convo.send_message("first message")

    await convo.arun()

    assert len(llm._calls) == 1, (
        f"final iteration must not auto-continue, got {len(llm._calls)} calls"
    )
    assert convo.state.execution_status == ConversationExecutionStatus.IDLE

    reject_events = [
        e for e in convo.state.events if isinstance(e, UserRejectObservation)
    ]
    assert len(reject_events) == 1, (
        "the pending action must be rejected even when going IDLE on the "
        "final iteration, or the next run() call will silently execute it"
    )


class _InjectingAsyncBudgetLLM(LLM):
    """通过在呼叫中着陆的消息来完成响应，而跑步的
    累计成本已经超出预算。"""

    _convo_box: list = PrivateAttr(default_factory=list)
    _calls: list = PrivateAttr(default_factory=list)

    def __init__(self):
        super().__init__(model=MODEL, usage_id="test-llm-budget")

    def uses_responses_api(self) -> bool:
        return False

    async def acompletion(self, *, messages, tools=None, **kwargs):  # type: ignore[override]
        self._calls.append(" ".join(str(m) for m in messages))
        convo: LocalConversation = self._convo_box[0]

        if len(self._calls) == 1:

            def _send():
                convo.send_message("second message")

            t = threading.Thread(target=_send)
            t.start()
            await asyncio.to_thread(t.join)

        return _finishing_response()


@pytest.mark.asyncio
async def test_message_during_final_step_does_not_trigger_spurious_budget_error(
    tmp_path,
):
    """在其自身预算内完成的步骤期间到达的消息必须
    不会仅仅因为中间步骤重新扫描将状态翻转回 RUNNING 为了拾取消息而变成
    MaxBudgetReached 错误。
    """
    llm = _InjectingAsyncBudgetLLM()
    convo = LocalConversation(
        agent=Agent(llm=llm, tools=[]),
        workspace=str(tmp_path),
        visualizer=None,
        max_budget_per_run=0.01,
    )
    llm._convo_box.append(convo)
    # 测试双胞胎 LLMs 都是子类 get_all_llms() 只会返回类型完全一致的对象 LLM所以这个不会
    # 被正常注册 _ensure_agent_ready() path; 直接将其连接起来，以便预算检查有可供读取的
    # 指标。
    #
    convo.conversation_stats.usage_to_metrics[llm.usage_id] = llm.metrics
    # 模拟在完成此（否则是优雅的）完成步骤时已经超出预算的累计支出。
    #
    llm.metrics.add_cost(1.0)
    convo.send_message("first message")

    await convo.arun()

    assert len(llm._calls) == 2, (
        f"expected the new message to be picked up (2 LLM calls), got {len(llm._calls)}"
    )
    assert convo.state.execution_status == ConversationExecutionStatus.FINISHED
    assert not any(
        isinstance(e, ConversationErrorEvent) and e.code == "MaxBudgetReached"
        for e in convo.state.events
    ), "a graceful finish must not be overridden by the budget check"


class _NavigateAwayDuringStepLLM(LLM):
    """通过 navigate_to() 对活动分支进行变基，而不发送
    任何新消息——证明重新扫描不会被单独的变基愚弄。"""

    _convo_box: list = PrivateAttr(default_factory=list)
    _calls: list = PrivateAttr(default_factory=list)
    _rebase_to: list = PrivateAttr(default_factory=list)

    def __init__(self):
        super().__init__(model=MODEL, usage_id="test-llm-navigate")

    def uses_responses_api(self) -> bool:
        return False

    async def acompletion(self, *, messages, tools=None, **kwargs):  # type: ignore[override]
        self._calls.append(" ".join(str(m) for m in messages))
        convo: LocalConversation = self._convo_box[0]

        if len(self._calls) == 1:
            rebase_to = self._rebase_to[0]

            def _navigate():
                convo.navigate_to(rebase_to)

            t = threading.Thread(target=_navigate)
            t.start()
            await asyncio.to_thread(t.join)

        return _finishing_response()


@pytest.mark.asyncio
async def test_navigate_to_during_step_does_not_spuriously_continue(tmp_path):
    """并发 navigate_to() 变基中间步骤不得被误认为是
    新用户消息。 重新合并活跃分支的更改，即使没有发送任何新内容，该用户消息仍然是“最
    新”的，这正是旧的active_branch()-扫描检查无法区分的，它看起来像一
    个真正的新消息。
    """
    llm = _NavigateAwayDuringStepLLM()
    convo = _make_conversation(llm, tmp_path)
    llm._convo_box.append(convo)

    convo.send_message("first message")
    first_message_id = next(
        e.id
        for e in convo.state.events
        if isinstance(e, MessageEvent) and e.source == "user"
    )
    convo.send_message("second message")

    # 中间步骤，将 HEAD 变基回到第一条消息。 这将从活动分支中删除第二条消息，而不发送任
    # 何新消息。
    #
    llm._rebase_to.append(first_message_id)

    await convo.arun()

    assert len(llm._calls) == 1, (
        f"a navigate_to() rebase alone must not trigger the mid-step rescan, "
        f"got {len(llm._calls)} calls"
    )
    assert convo.state.execution_status == ConversationExecutionStatus.FINISHED
