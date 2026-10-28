"""批评者实现的测试和注册表。"""

import json

import pytest

from openhands.sdk.critic import (
    AgentFinishedCritic,
    CriticBase,
    CriticResult,
    EmptyPatchCritic,
    PassCritic,
)
from openhands.sdk.event import ActionEvent
from openhands.sdk.llm import MessageToolCall, TextContent
from openhands.sdk.tool.builtins.finish import FinishAction
from openhands.sdk.tool.schema import Action


# 定义一次虚拟操作类以避免重复的类型错误
class DummyAction(Action):
    """用于测试目的的简单虚拟动作。"""

    pass


def test_critic_result_success_threshold():
    """测试 CriticResult 根据阈值确定成功。"""
    # 分数高于阈值就应该成功
    result_success = CriticResult(score=0.8, message="Success")
    assert result_success.success is True

    # 达到阈值的分数应该是成功的
    result_at_threshold = CriticResult(score=0.5, message="At threshold")
    assert result_at_threshold.success is True

    # 低于阈值的分数不应视为成功
    result_fail = CriticResult(score=0.3, message="Fail")
    assert result_fail.success is False


def test_critic_result_validation():
    """测试 CriticResult 是否验证分数范围。"""
    # 有效分数
    CriticResult(score=0.0, message="Min")
    CriticResult(score=1.0, message="Max")

    # 无效分数应引发验证错误
    with pytest.raises(Exception):  # Pydantic ValidationError
        CriticResult(score=-0.1, message="Below min")

    with pytest.raises(Exception):  # Pydantic ValidationError
        CriticResult(score=1.1, message="Above max")


def test_pass_critic_always_succeeds():
    """测试 PassCritic 是否始终返回成功。"""
    critic = PassCritic()

    # 空事件且无补丁
    result = critic.evaluate([], None)
    assert result.score == 1.0
    assert result.success is True

    # 有事件但没有补丁
    events = [
        ActionEvent(
            thought=[TextContent(text="thinking")],
            tool_name="test",
            tool_call_id="test_id",
            tool_call=MessageToolCall(
                id="test_id",
                name="test",
                arguments=json.dumps({}),
                origin="completion",
            ),
            llm_response_id="resp_123",
        )
    ]
    result = critic.evaluate(events, None)
    assert result.score == 1.0
    assert result.success is True

    # 有事件和补丁
    result = critic.evaluate(events, "some patch")
    assert result.score == 1.0
    assert result.success is True


def test_empty_patch_critic_with_empty_patch():
    """测试 EmptyPatchCritic 返回空补丁失败。"""
    critic = EmptyPatchCritic()

    # None 补丁
    result = critic.evaluate([], None)
    assert result.score == 0.0
    assert result.success is False
    assert result.message is not None
    assert "empty" in result.message.lower()

    # 空字符串补丁
    result = critic.evaluate([], "")
    assert result.score == 0.0
    assert result.success is False

    # 仅空白补丁
    result = critic.evaluate([], "   \n\t  ")
    assert result.score == 0.0
    assert result.success is False


def test_empty_patch_critic_with_non_empty_patch():
    """测试 EmptyPatchCritic 返回非空补丁的成功。"""
    critic = EmptyPatchCritic()

    patch = """
    diff --git a/file.py b/file.py
    index abc123..def456 100644
    --- a/file.py
    +++ b/file.py
    @@ -1,3 +1,4 @@
    +# New line
     print("hello")
    """

    result = critic.evaluate([], patch)
    assert result.score == 1.0
    assert result.success is True
    assert result.message is not None
    assert "non-empty" in result.message.lower()


def test_agent_finished_critic_with_empty_patch():
    """当补丁为空时，测试 AgentFinishedCritic 失败。"""
    critic = AgentFinishedCritic()

    # 使用 FinishAction 创建事件
    finish_action = FinishAction(message="Task completed")
    events = [
        ActionEvent(
            thought=[TextContent(text="I finished the task")],
            action=finish_action,
            tool_name="finish",
            tool_call_id="finish_id",
            tool_call=MessageToolCall(
                id="finish_id",
                name="finish",
                arguments=json.dumps({"message": "Task completed"}),
                origin="completion",
            ),
            llm_response_id="resp_finish",
        )
    ]

    # 即使智能体已完成，也应该因空补丁而失败
    result = critic.evaluate(events, None)
    assert result.score == 0.0
    assert result.success is False
    assert result.message is not None
    assert "empty" in result.message.lower()


def test_agent_finished_critic_without_finish_action():
    """当不存在 FinishAction 时，测试 AgentFinishedCritic 失败。"""
    critic = AgentFinishedCritic()

    patch = "diff --git a/file.py"

    # 空事件
    result = critic.evaluate([], patch)
    assert result.score == 0.0
    assert result.success is False

    # 没有 FinishAction 的活动
    other_action = DummyAction()
    events = [
        ActionEvent(
            thought=[TextContent(text="doing something")],
            action=other_action,
            tool_name="other",
            tool_call_id="other_id",
            tool_call=MessageToolCall(
                id="other_id",
                name="other",
                arguments=json.dumps({}),
                origin="completion",
            ),
            llm_response_id="resp_other",
        )
    ]

    result = critic.evaluate(events, patch)
    assert result.score == 0.0
    assert result.success is False
    assert result.message is not None
    assert "finish" in result.message.lower()


def test_agent_finished_critic_success():
    """测试 AgentFinishedCritic 成功，且 FinishAction 和非空补丁。"""
    critic = AgentFinishedCritic()

    patch = """
    diff --git a/file.py b/file.py
    --- a/file.py
    +++ b/file.py
    @@ -1 +1,2 @@
     original line
    +new line
    """

    finish_action = FinishAction(message="Task completed successfully")
    events = [
        ActionEvent(
            thought=[TextContent(text="Starting task")],
            action=None,
            tool_name="read",
            tool_call_id="read_id",
            tool_call=MessageToolCall(
                id="read_id",
                name="read",
                arguments=json.dumps({}),
                origin="completion",
            ),
            llm_response_id="resp_read",
        ),
        ActionEvent(
            thought=[TextContent(text="Finishing task")],
            action=finish_action,
            tool_name="finish",
            tool_call_id="finish_id",
            tool_call=MessageToolCall(
                id="finish_id",
                name="finish",
                arguments=json.dumps({"message": "Task completed successfully"}),
                origin="completion",
            ),
            llm_response_id="resp_finish_success",
        ),
    ]

    result = critic.evaluate(events, patch)
    assert result.score == 1.0
    assert result.success is True


def test_agent_finished_critic_last_action_not_finish():
    """当最后一个操作不是 FinishAction 时，测试 AgentFinishedCritic 失败。"""
    critic = AgentFinishedCritic()

    patch = "diff --git a/file.py"

    finish_action = FinishAction(message="Task completed")
    other_action = DummyAction()

    # FinishAction 不是最后一个操作
    events = [
        ActionEvent(
            thought=[TextContent(text="Finishing")],
            action=finish_action,
            tool_name="finish",
            tool_call_id="finish_id",
            tool_call=MessageToolCall(
                id="finish_id",
                name="finish",
                arguments=json.dumps({"message": "Task completed"}),
                origin="completion",
            ),
            llm_response_id="resp_finish_mid",
        ),
        ActionEvent(
            thought=[TextContent(text="Doing more")],
            action=other_action,
            tool_name="other",
            tool_call_id="other_id",
            tool_call=MessageToolCall(
                id="other_id",
                name="other",
                arguments=json.dumps({}),
                origin="completion",
            ),
            llm_response_id="resp_other_last",
        ),
    ]

    result = critic.evaluate(events, patch)
    assert result.score == 0.0
    assert result.success is False


def test_critic_base_is_abstract():
    """测试CriticBase不能直接实例化。"""
    with pytest.raises(TypeError):
        CriticBase()  # type: ignore
