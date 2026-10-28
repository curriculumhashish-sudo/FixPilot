"""测试 GoalController（与传输层无关的 /goal 决策逻辑）。"""

import pytest

from openhands.sdk.conversation.goal import (
    GoalContinue,
    GoalController,
    GoalDone,
)
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.testing import TestLLM


def _judge(*texts: str) -> TestLLM:
    """法官 LLM 编写脚本，每次 on_run_finished() 调用返回一个判决。"""
    return TestLLM.from_messages(
        [Message(role="assistant", content=[TextContent(text=t)]) for t in texts]
    )


def test_start_returns_objective():
    controller = GoalController("build x", _judge("{}"))
    assert controller.start() == "build x"
    assert controller.iteration == 0


def test_continue_when_incomplete():
    controller = GoalController(
        "build x",
        _judge('{"score": 0.2, "complete": false, "missing": "tests"}'),
        max_iterations=3,
    )
    step = controller.on_run_finished([])
    assert isinstance(step, GoalContinue)
    assert "tests" in step.followup
    assert controller.iteration == 1
    # 刚刚结束的这一轮比赛的裁决会一直进行，因此车手可以发布每轮裁判的反馈，而不仅仅是终
    # 点的反馈。
    #
    assert step.verdict.score == 0.2
    assert step.verdict.complete is False
    assert step.verdict.missing == "tests"


def test_done_when_complete():
    controller = GoalController(
        "build x", _judge('{"score": 1.0, "complete": true, "missing": ""}')
    )
    step = controller.on_run_finished([])
    assert isinstance(step, GoalDone)
    assert step.outcome.status == "complete"
    assert step.outcome.iterations == 1
    assert step.outcome.verdict.complete


def test_caps_at_max_iterations():
    incomplete = '{"score": 0.1, "complete": false, "missing": "still broken"}'
    controller = GoalController(
        "build x", _judge(incomplete, incomplete), max_iterations=2
    )

    assert isinstance(controller.on_run_finished([]), GoalContinue)  # 第一轮
    step = controller.on_run_finished([])  # 第 2 轮 -> 封顶
    assert isinstance(step, GoalDone)
    assert step.outcome.status == "capped"
    assert step.outcome.iterations == 2
    assert not step.outcome.verdict.complete


def test_failed_judge_call_does_not_count_a_round():
    # 法官提出的要求并不是已完成的审核：计数不得前进，否则恢复的目标将超出max_iterations
    # 。
    #
    controller = GoalController(
        "build x",
        TestLLM.from_messages([RuntimeError("judge network error")]),
        max_iterations=1,
    )

    with pytest.raises(RuntimeError):
        controller.on_run_finished([])
    assert controller.iteration == 0


@pytest.mark.parametrize(
    ("objective", "max_iterations"),
    [("   ", 10), ("build x", 0)],
    ids=["empty-objective", "bad-max-iterations"],
)
def test_validates_inputs(objective, max_iterations):
    with pytest.raises(ValueError):
        GoalController(objective, _judge("{}"), max_iterations=max_iterations)
