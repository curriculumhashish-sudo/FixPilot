"""测试 /goal 驱动程序循环和命令解析。"""

import pytest

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.base import BaseConversation
from openhands.sdk.conversation.goal import GoalOutcome, run_goal
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.testing import TestLLM


def _text_llm(*texts: str) -> TestLLM:
    """一个 LLM 脚本用于返回仅内容回复（每个回复完成一个回合）。"""
    return TestLLM.from_messages(
        [Message(role="assistant", content=[TextContent(text=t)]) for t in texts]
    )


def _conversation(*agent_turns: str) -> BaseConversation:
    """智能体在每个 run() 上完成的对话（仅内容）。"""
    agent = Agent(llm=_text_llm(*agent_turns), tools=[])
    return Conversation(agent=agent)


_DONE = '{"score": 1.0, "complete": true, "missing": ""}'
_NOT_DONE = '{"score": 0.2, "complete": false, "missing": "tests"}'


@pytest.mark.parametrize(
    ("agent_turns", "verdicts", "max_iterations", "status", "iterations"),
    [
        # 法官在第一次审计中表示“完成”
        (("done",), (_DONE,), 5, "complete", 1),
        # “未完成”然后“完成”-> 再次循环，然后完成
        (("turn 1", "turn 2"), (_NOT_DONE, _DONE), 5, "complete", 2),
        # 从未完成 -> 上限为 max_iterations
        (("turn 1", "turn 2"), (_NOT_DONE, _NOT_DONE), 2, "capped", 2),
    ],
    ids=["complete-first-audit", "loops-until-complete", "caps-at-max"],
)
def test_run_goal_outcomes(agent_turns, verdicts, max_iterations, status, iterations):
    conversation = _conversation(*agent_turns)
    outcome = run_goal(
        conversation, "build x", _text_llm(*verdicts), max_iterations=max_iterations
    )
    assert isinstance(outcome, GoalOutcome)
    assert outcome.status == status
    assert outcome.iterations == iterations
    assert outcome.verdict.complete is (status == "complete")


@pytest.mark.parametrize(
    ("objective", "max_iterations"),
    [("   ", 5), ("build x", 0)],
    ids=["empty-objective", "bad-max-iterations"],
)
def test_run_goal_rejects_invalid_input(objective, max_iterations):
    with pytest.raises(ValueError):
        run_goal(
            _conversation("noop"),
            objective,
            _text_llm("{}"),
            max_iterations=max_iterations,
        )
