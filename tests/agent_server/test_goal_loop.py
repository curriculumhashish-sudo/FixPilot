"""测试 EventService 中的 /goal 驱动程序循环（智能体服务器端）。

这些驱动一个真正的 EventService + LocalConversation 和一个脚本化的 TestLLM 智能体（每
次运行仅在内容回复上完成）和一个单独的脚本化
判断。
"""

import asyncio
from threading import Event
from typing import cast
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import PrivateAttr, SecretStr

from openhands.agent_server.event_service import EventService
from openhands.agent_server.models import StoredConversation
from openhands.sdk.agent import Agent
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.testing import TestLLM
from openhands.sdk.workspace import LocalWorkspace


def _scripted(*texts: str, usage_id: str) -> TestLLM:
    return TestLLM.from_messages(
        [Message(role="assistant", content=[TextContent(text=t)]) for t in texts],
        usage_id=usage_id,
    )


class _GatedLLM(TestLLM):
    """判断LLM阻塞直到被释放，当它进入时发出信号。

    让测试确定性地捕获审计中的目标循环（没有飞行中的运行）并停止它。
    """

    _gate: Event = PrivateAttr(default_factory=Event)
    _entered: Event = PrivateAttr(default_factory=Event)

    def completion(
        self,
        messages,
        tools=None,
        add_security_risk_prediction=False,
        on_token=None,
        call_context=None,
        **kwargs,
    ):
        self._entered.set()
        self._gate.wait(timeout=10)
        return super().completion(
            messages,
            tools,
            add_security_risk_prediction,
            on_token,
            call_context,
            **kwargs,
        )


class _GatedJudge(TestLLM):
    """判断LLM在第一次调用时会阻塞，以捕捉轮间间隙。

    在回合之间，目标循环在等待裁判时没有运行，这正是一个竞争请求可以声称一个刚释放的
    许可的地方，如果循环没有为自己的整个生命周期保留自己的。
    """

    _gate: Event = PrivateAttr(default_factory=Event)
    _entered: Event = PrivateAttr(default_factory=Event)
    _calls: int = PrivateAttr(default=0)

    def completion(
        self,
        messages,
        tools=None,
        add_security_risk_prediction=False,
        on_token=None,
        call_context=None,
        **kwargs,
    ):
        self._calls += 1
        if self._calls == 1:
            self._entered.set()
            self._gate.wait(timeout=10)
        return super().completion(
            messages,
            tools,
            add_security_risk_prediction,
            on_token,
            call_context,
            **kwargs,
        )


def _goal_status_updates(event_service: EventService) -> list:
    return [
        e.value
        for e in event_service.get_conversation()._state.events
        if isinstance(e, ConversationStateUpdateEvent) and e.key == "goal"
    ]


@pytest.fixture
def event_service(tmp_path):
    with patch("openhands.sdk.llm.utils.model_info.httpx.get") as mock_get:
        mock_get.return_value = MagicMock(json=lambda: {"data": []})
        service = EventService(
            stored=StoredConversation(
                id=uuid4(),
                workspace=LocalWorkspace(working_dir=str(tmp_path / "workspace")),
            ),
            agent=Agent(
                llm=LLM(usage_id="agent", model="test-model", api_key=SecretStr("x")),
                tools=[],
            ),
            conversations_dir=tmp_path / "conversations",
        )
        yield service


async def _start(service: EventService, tmp_path, *agent_turns: str) -> None:
    """启动服务并安装脚本化的智能体 LLM（每次运行一个回复）。"""
    (tmp_path / "workspace").mkdir(exist_ok=True)
    await service.start()
    service.get_conversation().switch_llm(_scripted(*agent_turns, usage_id="agent"))


_DONE = '{"score": 1.0, "complete": true, "missing": ""}'
_NOT_DONE = '{"score": 0.2, "complete": false, "missing": "tests"}'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_turns", "verdicts", "max_iterations", "status", "iterations"),
    [
        (("turn 1", "turn 2"), (_NOT_DONE, _DONE), 5, "complete", 2),
        (("turn 1", "turn 2"), (_NOT_DONE, _NOT_DONE), 2, "capped", 2),
    ],
    ids=["completes-after-two-rounds", "caps-at-max"],
)
async def test_goal_loop_outcomes(
    event_service, tmp_path, agent_turns, verdicts, max_iterations, status, iterations
):
    await _start(event_service, tmp_path, *agent_turns)
    judge = _scripted(*verdicts, usage_id="judge")
    try:
        await event_service.start_goal_loop(
            "build x", judge_llm=judge, max_iterations=max_iterations
        )
        await asyncio.wait_for(event_service._goal_loop_task, timeout=15)

        outcome = event_service._goal_loop_outcome
        assert outcome is not None
        assert outcome.status == status
        assert outcome.iterations == iterations
    finally:
        await event_service.close()


@pytest.mark.asyncio
async def test_goal_loop_emits_status_events(event_service, tmp_path):
    # 循环在每个生命周期点发布 ConversationStateUpdateEvent(key="goal")； 它们已持久化到
    # 共享事件日志（并流式传输给订阅者），因此 UI 可以呈现进度条。
    #
    await _start(event_service, tmp_path, "did the work")
    judge = _scripted(
        '{"score": 1.0, "complete": true, "missing": ""}', usage_id="judge"
    )
    try:
        await event_service.start_goal_loop(
            "build x", judge_llm=judge, max_iterations=3
        )
        await asyncio.wait_for(event_service._goal_loop_task, timeout=15)

        updates = [
            e.value
            for e in event_service.get_conversation()._state.events
            if isinstance(e, ConversationStateUpdateEvent) and e.key == "goal"
        ]
        assert updates, "expected goal-status events"
        # 第一次更新：运行+活动。 最后：完成+不活动。
        assert updates[0]["active"] is True
        assert updates[0]["status"] == "running"
        assert updates[-1]["active"] is False
        assert updates[-1]["status"] == "complete"
        assert updates[-1]["iteration"] == 1
        assert updates[-1]["objective"] == "build x"
    finally:
        await event_service.close()


@pytest.mark.asyncio
async def test_goal_loop_emits_per_round_verdicts(event_service, tmp_path):
    # 每个继续的回合都会发布其评委判决（得分 + 缺席），因此UI可以显示每回合的反馈，而不
    # 是仅显示最终判决。
    #
    await _start(event_service, tmp_path, "turn 1", "turn 2")
    judge = _scripted(_NOT_DONE, _DONE, usage_id="judge")
    try:
        await event_service.start_goal_loop(
            "build x", judge_llm=judge, max_iterations=5
        )
        await asyncio.wait_for(event_service._goal_loop_task, timeout=15)

        updates = _goal_status_updates(event_service)
        # 启动更新（迭代 0）尚未得出结论。
        kickoff = next(u for u in updates if u["iteration"] == 0)
        assert kickoff["verdict"] is None
        # 第 1 轮的中循环“运行”更新承载了该轮的判决。
        round_one = next(
            u for u in updates if u["status"] == "running" and u["iteration"] == 1
        )
        assert round_one["verdict"] is not None
        assert round_one["verdict"]["score"] == 0.2
        assert round_one["verdict"]["missing"] == "tests"
    finally:
        await event_service.close()


@pytest.mark.asyncio
async def test_goal_loop_defaults_judge_to_agent_llm(event_service, tmp_path):
    # 没有 judge_llm 通过 -> 智能体自己的 LLM 被用作法官，因此它的脚本队列同时服务于智能
    # 体轮和判决。 这是 POST /goal 端点始终采用的路径。
    #
    await _start(
        event_service,
        tmp_path,
        "did the work",
        '{"score": 1.0, "complete": true, "missing": ""}',
    )
    try:
        await event_service.start_goal_loop("build x", max_iterations=3)
        await asyncio.wait_for(event_service._goal_loop_task, timeout=15)

        outcome = event_service._goal_loop_outcome
        assert outcome is not None
        assert outcome.status == "complete"
        assert outcome.iterations == 1
    finally:
        await event_service.close()


@pytest.mark.asyncio
async def test_start_goal_loop_rejects_empty_objective(event_service, tmp_path):
    await _start(event_service, tmp_path, "noop")
    judge = _scripted("{}", usage_id="judge")
    try:
        with pytest.raises(ValueError):
            await event_service.start_goal_loop("   ", judge_llm=judge)
    finally:
        await event_service.close()


@pytest.mark.asyncio
async def test_start_goal_loop_rejects_concurrent_goal_loop(event_service, tmp_path):
    await _start(event_service, tmp_path, "noop")
    judge = _scripted("{}", usage_id="judge")
    try:
        # 用无法自行完成的任务占据目标循环槽。
        event_service._goal_loop_task = asyncio.create_task(asyncio.sleep(10))
        with pytest.raises(ValueError, match="goal_already_running"):
            await event_service.start_goal_loop("build x", judge_llm=judge)
    finally:
        event_service._goal_loop_task.cancel()
        event_service._goal_loop_task = None
        await event_service.close()


@pytest.mark.asyncio
async def test_stop_goal_loop_when_idle_returns_false(event_service, tmp_path):
    await _start(event_service, tmp_path, "noop")
    try:
        assert await event_service.stop_goal_loop() is False
    finally:
        await event_service.close()


@pytest.mark.asyncio
async def test_user_message_stops_running_goal_loop(event_service, tmp_path):
    # 正常聊天路径上的用户消息在处理之前会取消正在运行的目标循环。
    #
    await _start(event_service, tmp_path, "noop")
    try:
        event_service._goal_loop_task = asyncio.create_task(asyncio.sleep(30))
        await event_service.send_message(
            Message(role="user", content=[TextContent(text="hello")]), run=False
        )
        assert event_service._goal_loop_task.done()
    finally:
        await event_service.close()


@pytest.mark.asyncio
async def test_stop_running_goal_loop_emits_interrupted(event_service, tmp_path):
    await _start(event_service, tmp_path, "did the work")
    judge = cast(
        _GatedLLM,
        _GatedLLM.from_messages(
            [
                Message(
                    role="assistant",
                    content=[TextContent(text='{"score": 0.2, "complete": false}')],
                )
            ],
            usage_id="judge",
        ),
    )
    try:
        await event_service.start_goal_loop(
            "build x", judge_llm=judge, max_iterations=5
        )
        # 等到裁判被挡：目标是中审，没有跑动。
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, judge._entered.wait, 5.0)

        assert await event_service.stop_goal_loop() is True
        updates = _goal_status_updates(event_service)
        assert updates[-1]["status"] == "interrupted"
        assert updates[-1]["active"] is False
        # 审核已被放弃，因此该轮不计为已完成。
        assert updates[-1]["iteration"] == 0
    finally:
        judge._gate.set()  # 释放孤儿法官线程进行清理
        await event_service.close()


@pytest.mark.asyncio
async def test_resume_from_interrupted_status(event_service, tmp_path):
    await _start(event_service, tmp_path, "resumed and finished")
    # 模拟在 5 轮中的第 1 轮中断的进球循环。
    conversation = event_service.get_conversation()
    with conversation._state:
        conversation._on_event(
            ConversationStateUpdateEvent(
                key="goal",
                value={
                    "active": False,
                    "status": "interrupted",
                    "iteration": 1,
                    "max_iterations": 5,
                    "objective": "build x",
                    "verdict": None,
                },
            )
        )
    judge = _scripted(
        '{"score": 1.0, "complete": true, "missing": ""}', usage_id="judge"
    )
    try:
        await event_service.resume_goal_loop(judge_llm=judge)
        await asyncio.wait_for(event_service._goal_loop_task, timeout=15)

        outcome = event_service._goal_loop_outcome
        assert outcome is not None
        assert outcome.status == "complete"
        assert outcome.iterations == 2  # 从第 1 轮恢复 -> 在第 2 轮完成
    finally:
        await event_service.close()


@pytest.mark.asyncio
async def test_resume_after_failed_audit_never_exceeds_cap(event_service, tmp_path):
    # 唯一一轮的判断调用失败 -> 在 0 of 1 处中断（失败的审核不是完整的一轮）； 简历会重
    # 新运行该轮，上限为 1 中的 1，永远不会高于 max_iterations。
    #
    await _start(event_service, tmp_path, "did the work", "tried again")
    failing_judge = TestLLM.from_messages(
        [RuntimeError("judge network error")], usage_id="judge"
    )
    try:
        await event_service.start_goal_loop(
            "build x", judge_llm=failing_judge, max_iterations=1
        )
        await asyncio.wait_for(event_service._goal_loop_task, timeout=15)
        updates = _goal_status_updates(event_service)
        assert updates[-1]["status"] == "interrupted"
        assert updates[-1]["iteration"] == 0

        await event_service.resume_goal_loop(
            judge_llm=_scripted(_NOT_DONE, usage_id="judge")
        )
        await asyncio.wait_for(event_service._goal_loop_task, timeout=15)

        updates = _goal_status_updates(event_service)
        assert updates[-1]["status"] == "capped"
        assert updates[-1]["iteration"] == 1
        assert all(u["iteration"] <= u["max_iterations"] for u in updates)
    finally:
        await event_service.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_iteration", "stored_max", "override_max", "final_iteration"),
    [(1, 1, None, 1), (3, 5, 2, 2)],
    ids=["stored-at-cap", "lower-max-override"],
)
async def test_resume_from_status_at_cap_never_exceeds_cap(
    event_service,
    tmp_path,
    stored_iteration,
    stored_max,
    override_max,
    final_iteration,
):
    # 中断状态已经达到了（或超过了）上限已持久化由一个旧服务器计数失败的审计，或者继续运
    # 行一个较低的版本 max_iterations -- 结束为一轮，而不是超过限额。
    #
    await _start(event_service, tmp_path, "resumed")
    conversation = event_service.get_conversation()
    with conversation._state:
        conversation._on_event(
            ConversationStateUpdateEvent(
                key="goal",
                value={
                    "active": False,
                    "status": "interrupted",
                    "iteration": stored_iteration,
                    "max_iterations": stored_max,
                    "objective": "build x",
                    "verdict": None,
                },
            )
        )
    try:
        await event_service.resume_goal_loop(
            judge_llm=_scripted(_NOT_DONE, usage_id="judge"),
            max_iterations=override_max,
        )
        await asyncio.wait_for(event_service._goal_loop_task, timeout=15)

        updates = _goal_status_updates(event_service)[1:]  # 跳过已存储的
        assert updates[-1]["status"] == "capped"
        assert updates[-1]["iteration"] == final_iteration
        assert all(u["iteration"] <= u["max_iterations"] for u in updates)
    finally:
        await event_service.close()


@pytest.mark.asyncio
async def test_resume_without_resumable_goal_loop_raises(event_service, tmp_path):
    await _start(event_service, tmp_path, "noop")
    judge = _scripted("{}", usage_id="judge")
    try:
        with pytest.raises(ValueError, match="no_resumable_goal"):
            await event_service.resume_goal_loop(judge_llm=judge)
    finally:
        await event_service.close()


@pytest.mark.asyncio
async def test_resume_after_completed_goal_loop_raises(event_service, tmp_path):
    # 已完成（或上限​​）的目标循环不可恢复。
    await _start(event_service, tmp_path, "noop")
    conversation = event_service.get_conversation()
    with conversation._state:
        conversation._on_event(
            ConversationStateUpdateEvent(
                key="goal",
                value={
                    "active": False,
                    "status": "complete",
                    "iteration": 2,
                    "max_iterations": 5,
                    "objective": "build x",
                    "verdict": None,
                },
            )
        )
    judge = _scripted("{}", usage_id="judge")
    try:
        with pytest.raises(ValueError, match="no_resumable_goal"):
            await event_service.resume_goal_loop(judge_llm=judge)
    finally:
        await event_service.close()


@pytest.mark.asyncio
async def test_goal_loop_halts_on_run_error_as_interrupted(event_service, tmp_path):
    # 模拟“积分不足”：智能体的运行加注。 目标循环必须记录中断（可恢复）状态，而不是默默
    # 地死掉而没有结果。
    #
    (tmp_path / "workspace").mkdir(exist_ok=True)
    await event_service.start()
    event_service.get_conversation().switch_llm(
        TestLLM.from_messages([RuntimeError("out of credits")], usage_id="agent")
    )
    judge = _scripted(
        '{"score": 0.1, "complete": false, "missing": "x"}', usage_id="judge"
    )
    try:
        await event_service.start_goal_loop(
            "build x", judge_llm=judge, max_iterations=5
        )
        await asyncio.wait_for(event_service._goal_loop_task, timeout=15)

        updates = _goal_status_updates(event_service)
        assert updates[-1]["status"] == "interrupted"
        assert updates[-1]["active"] is False
        assert event_service._goal_loop_outcome is None
    finally:
        await event_service.close()


@pytest.mark.asyncio
async def test_goal_loop_continues_past_stuck_run(event_service, tmp_path):
    # 以 STUCK 结束的运行（合法迭代期间卡住检测器启发式触发）必须不将目标循环停止为“中断
    # ”。 裁判是权威的完成信号； 循环应进行审核并重新提示词，保持“工作直到完成”合同。 与
    # 上面的ERROR/PAUSED对比，它们是真实的停止信号。
    #
    await _start(event_service, tmp_path, "turn 1", "turn 2")
    conversation = event_service.get_conversation()

    original_arun = conversation.arun

    async def _arun_first_stuck():
        # 第一次运行结束 STUCK（模拟卡住检测器在运行中跳闸）。
        if not getattr(conversation, "_test_stuck_fired", False):
            conversation._test_stuck_fired = True
            with conversation._state:
                conversation._state.execution_status = ConversationExecutionStatus.STUCK
            return
        await original_arun()

    conversation.arun = _arun_first_stuck

    judge = _scripted(_NOT_DONE, _DONE, usage_id="judge")
    try:
        await event_service.start_goal_loop(
            "build x", judge_llm=judge, max_iterations=5
        )
        await asyncio.wait_for(event_service._goal_loop_task, timeout=15)

        updates = _goal_status_updates(event_service)
        # 循环必须不记录了终端“中断”； STUCK回合被视为正常继续，裁判随后完成。
        #
        assert updates[-1]["status"] == "complete"
        assert updates[-1]["active"] is False
        outcome = event_service._goal_loop_outcome
        assert outcome is not None
        assert outcome.status == "complete"
        assert outcome.iterations == 2
    finally:
        await event_service.close()


@pytest.mark.asyncio
async def test_goal_loop_emits_interrupted_on_unexpected_error(event_service, tmp_path):
    # * 提出 * 的法官 LLM (e.g. 网络错误）通过通用 `except Exception` 路径使循环崩溃——与
    #  ConversationExecutionStatus.ERROR 所示的运行错误（上面的测试）不同。 循环仍必须记
    # 录终端中断（可恢复）状态； 否则最后一个已持久化事件保持活动 = True/running 并且 UI
    #  将死目标显示为正在运行。
    #
    await _start(event_service, tmp_path, "did the work")
    judge = TestLLM.from_messages(
        [RuntimeError("judge network error")], usage_id="judge"
    )
    try:
        await event_service.start_goal_loop(
            "build x", judge_llm=judge, max_iterations=5
        )
        await asyncio.wait_for(event_service._goal_loop_task, timeout=15)

        updates = _goal_status_updates(event_service)
        assert updates[-1]["status"] == "interrupted"
        assert updates[-1]["active"] is False
        assert event_service._goal_loop_outcome is None
    finally:
        await event_service.close()


@pytest.mark.asyncio
async def test_start_goal_loop_rejected_while_run_active(event_service, tmp_path):
    # /goal 必须拒绝 conversation_already_running (-> 409) 当正常运行已经进行时，而不是
    # 滑行并判断该运行无关的转录。 一个占位符 _run_task 充当活跃运行（与相同模式）
    # test_start_goal_loop_rejects_concurrent_goal_loop).
    #
    await _start(event_service, tmp_path, "noop")
    judge = _scripted("{}", usage_id="judge")
    try:
        event_service._run_task = asyncio.create_task(asyncio.sleep(10))
        with pytest.raises(ValueError, match="conversation_already_running"):
            await event_service.start_goal_loop("build x", judge_llm=judge)
        assert event_service._goal_loop_task is None
    finally:
        event_service._run_task.cancel()
        event_service._run_task = None
        await event_service.close()


@pytest.mark.asyncio
async def test_resume_goal_loop_rejected_while_run_active(event_service, tmp_path):
    # 恢复使用相同的忙碌守卫； 重用占位符 _run_task 方法。
    await _start(event_service, tmp_path, "noop")
    conversation = event_service.get_conversation()
    with conversation._state:
        conversation._on_event(
            ConversationStateUpdateEvent(
                key="goal",
                value={
                    "active": False,
                    "status": "interrupted",
                    "iteration": 1,
                    "max_iterations": 5,
                    "objective": "build x",
                    "verdict": None,
                },
            )
        )
    judge = _scripted("{}", usage_id="judge")
    try:
        event_service._run_task = asyncio.create_task(asyncio.sleep(10))
        with pytest.raises(ValueError, match="conversation_already_running"):
            await event_service.resume_goal_loop(judge_llm=judge)
    finally:
        event_service._run_task.cancel()
        event_service._run_task = None
        await event_service.close()


@pytest.mark.asyncio
async def test_goal_loop_holds_capacity_across_rounds(event_service, tmp_path):
    """每个球门回合必须在预先保留的循环许可上运行。

    只有第一轮比赛是在保留的许可证上进行的； 后面的回合称为平原
    ``run()``并且需要一个新的，并且在回合之间许可证是免费的
    while the judge LLM call ran. A competing request could take it there, and
    下一轮的 ``run()`` 那么就会引发 ``ConversationRunLimitExceeded`` (a
    ``RuntimeError``不是
    ``ValueError``), 逃到外部处理器，结束目标 ``interrupted`` 工作仍需完成。 相反，循
    环在其整个生命周期中保留一个许可证。
    """
    await _start(event_service, tmp_path, "turn 1", "turn 2")
    event_service._run_semaphore = asyncio.Semaphore(1)
    judge = cast(
        _GatedJudge,
        _GatedJudge.from_messages(
            [
                Message(role="assistant", content=[TextContent(text=_NOT_DONE)]),
                Message(role="assistant", content=[TextContent(text=_DONE)]),
            ],
            usage_id="judge",
        ),
    )
    try:
        await event_service.start_goal_loop(
            "build x", judge_llm=judge, max_iterations=5
        )
        loop = asyncio.get_running_loop()
        # 中期审核：第一轮结束，没有运行正在进行，但循环必须仍能容纳即将开始的一轮的容量
        # 。
        #
        await loop.run_in_executor(None, judge._entered.wait, 5.0)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(event_service._run_semaphore.acquire(), timeout=0.25)

        judge._gate.set()
        await asyncio.wait_for(event_service._goal_loop_task, timeout=15)

        outcome = event_service._goal_loop_outcome
        assert outcome is not None
        assert outcome.status == "complete"
        assert outcome.iterations == 2

        # 循环完成后，许可证将返回到共享池。
        await asyncio.wait_for(event_service._run_semaphore.acquire(), timeout=5)
        event_service._run_semaphore.release()
    finally:
        judge._gate.set()  # 如果仍被阻止，则释放法官线程
        await event_service.close()


@pytest.mark.asyncio
async def test_goal_loop_release_returns_capacity(event_service, tmp_path):
    """完成的目标循环不得泄漏其保留的许可。"""
    await _start(event_service, tmp_path, "done")
    event_service._run_semaphore = asyncio.Semaphore(1)
    judge = _scripted(_DONE, usage_id="judge")
    try:
        await event_service.start_goal_loop(
            "build x", judge_llm=judge, max_iterations=3
        )
        await asyncio.wait_for(event_service._goal_loop_task, timeout=15)
        assert event_service._run_session_slot is None
        assert event_service._run_session_pins == 0
        await asyncio.wait_for(event_service._run_semaphore.acquire(), timeout=5)
        event_service._run_semaphore.release()
    finally:
        await event_service.close()


def _reopen(service: EventService, tmp_path) -> EventService:
    """同一已持久化对话上的新 EventService（重新启动）。"""
    return EventService(
        stored=service.stored,
        conversations_dir=tmp_path / "conversations",
    )


def _persist_goal_status(service: EventService, **value) -> None:
    conversation = service.get_conversation()
    with conversation._state:
        conversation._on_event(
            ConversationStateUpdateEvent(
                key="goal",
                value={
                    "iteration": 1,
                    "max_iterations": 5,
                    "objective": "build x",
                    "verdict": None,
                    **value,
                },
            )
        )


@pytest.mark.asyncio
async def test_graceful_restart_marks_active_goal_interrupted(event_service, tmp_path):
    await _start(event_service, tmp_path, "did the work")
    judge = cast(
        _GatedLLM,
        _GatedLLM.from_messages(
            [
                Message(
                    role="assistant",
                    content=[TextContent(text='{"score": 0.2, "complete": false}')],
                )
            ],
            usage_id="judge",
        ),
    )
    try:
        await event_service.start_goal_loop(
            "build x", judge_llm=judge, max_iterations=5
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, judge._entered.wait, 5.0)
        assert _goal_status_updates(event_service)[-1]["status"] == "running"
        # 循环处于活动状态时正常关闭：close() 不记录任何内容。
        await event_service.close()
    finally:
        judge._gate.set()

    restarted = _reopen(event_service, tmp_path)
    await restarted.start()
    try:
        last = _goal_status_updates(restarted)[-1]
        assert last["active"] is False
        assert last["status"] == "interrupted"
        assert last["objective"] == "build x"
        assert last["iteration"] == 0
        assert last["max_iterations"] == 5
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_hard_kill_restart_marks_active_goal_interrupted_and_resumable(
    event_service, tmp_path
):
    await _start(event_service, tmp_path, "noop")
    # 被杀死的进程留下的最后状态：仍然活动。
    _persist_goal_status(event_service, active=True, status="running")
    await event_service.close()

    restarted = _reopen(event_service, tmp_path)
    await restarted.start()
    try:
        updates = _goal_status_updates(restarted)
        assert updates[-1] == {
            "active": False,
            "status": "interrupted",
            "iteration": 1,
            "max_iterations": 5,
            "objective": "build x",
            "verdict": None,
        }
        restarted.get_conversation().switch_llm(
            _scripted("resumed and finished", usage_id="agent")
        )
        await restarted.resume_goal_loop(judge_llm=_scripted(_DONE, usage_id="judge"))
        task = restarted._goal_loop_task
        assert task is not None
        await asyncio.wait_for(task, timeout=15)
        outcome = restarted._goal_loop_outcome
        assert outcome is not None
        assert outcome.status == "complete"
        assert outcome.iterations == 2
    finally:
        await restarted.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["complete", "capped", "interrupted"])
async def test_restart_leaves_inactive_goal_status_alone(
    event_service, tmp_path, status
):
    await _start(event_service, tmp_path, "noop")
    _persist_goal_status(event_service, active=False, status=status)
    before = _goal_status_updates(event_service)
    await event_service.close()

    restarted = _reopen(event_service, tmp_path)
    await restarted.start()
    try:
        assert _goal_status_updates(restarted) == before
    finally:
        await restarted.close()
