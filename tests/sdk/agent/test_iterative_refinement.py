"""测试CriticMixin中的迭代细化功能。"""

import json
from unittest.mock import MagicMock

import pytest

from openhands.sdk.agent.critic_mixin import (
    ITERATIVE_REFINEMENT_ITERATION_KEY,
    CriticMixin,
)
from openhands.sdk.critic.base import (
    CriticBase,
    CriticResult,
    IterativeRefinementConfig,
)
from openhands.sdk.critic.impl.api import APIBasedCritic
from openhands.sdk.event import ActionEvent
from openhands.sdk.llm import MessageToolCall, TextContent
from openhands.sdk.tool.builtins.finish import FinishAction


class MockCritic(CriticBase):
    """模拟对象测试评论家。"""

    def evaluate(self, events, git_patch=None):
        return CriticResult(score=0.5, message="Mock evaluation")


class MockCriticMixin(CriticMixin):
    """具体实现CriticMixin进行测试。"""

    def __init__(self, critic=None):
        self.critic = critic


def create_mock_conversation(iteration: int = 0):
    """使用 agent_state 字典创建模拟对象对话。"""
    mock_state = MagicMock()
    mock_state.agent_state = {}
    if iteration > 0:
        mock_state.agent_state = {ITERATIVE_REFINEMENT_ITERATION_KEY: iteration}

    mock_conversation = MagicMock()
    mock_conversation.state = mock_state
    return mock_conversation


def create_finish_action_event(critic_result: CriticResult | None = None):
    """创建一个具有可选评论结果的 FinishAction 事件。"""
    finish_action = FinishAction(message="Task completed")
    event = ActionEvent(
        thought=[TextContent(text="Finishing task")],
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
    # 设置评论家结果（如果提供）
    if critic_result is not None:
        # 使用 object.__setattr__ 绕过冻结模型
        object.__setattr__(event, "critic_result", critic_result)
    return event


class TestIterativeRefinementConfig:
    """测试 IterativeRefinementConfig。"""

    def test_default_values(self):
        """测试默认配置值。"""
        config = IterativeRefinementConfig()
        assert config.success_threshold == 0.6
        assert config.max_iterations == 3

    def test_custom_values(self):
        """测试自定义配置值。"""
        config = IterativeRefinementConfig(
            success_threshold=0.8,
            max_iterations=5,
        )
        assert config.success_threshold == 0.8
        assert config.max_iterations == 5

    def test_threshold_validation_bounds(self):
        """测试阈值必须介于 0 和 1 之间。"""
        # 有效范围
        IterativeRefinementConfig(success_threshold=0.0)
        IterativeRefinementConfig(success_threshold=1.0)

        # 无效边界
        with pytest.raises(Exception):  # Pydantic ValidationError
            IterativeRefinementConfig(success_threshold=-0.1)
        with pytest.raises(Exception):
            IterativeRefinementConfig(success_threshold=1.1)

    def test_max_iterations_validation(self):
        """测试 max_iterations 必须至少为 1。"""
        IterativeRefinementConfig(max_iterations=1)

        with pytest.raises(Exception):  # Pydantic ValidationError
            IterativeRefinementConfig(max_iterations=0)


class TestCheckIterativeRefinement:
    """测试 _check_iterative_refinement 方法。"""

    def test_no_critic_returns_false(self):
        """测试一下，没有批评就意味着没有改进。"""
        mixin = MockCriticMixin(critic=None)
        conversation = create_mock_conversation()
        event = create_finish_action_event()

        should_continue, followup = mixin._check_iterative_refinement(
            conversation, event
        )

        assert should_continue is False
        assert followup is None

    def test_no_iterative_config_returns_false(self):
        """测试没有迭代配置的批评者意味着没有细化。"""
        critic = MockCritic()
        critic.iterative_refinement = None
        mixin = MockCriticMixin(critic=critic)
        conversation = create_mock_conversation()
        event = create_finish_action_event()

        should_continue, followup = mixin._check_iterative_refinement(
            conversation, event
        )

        assert should_continue is False
        assert followup is None

    def test_max_iterations_reached(self):
        """测试最大迭代次数是否会停止细化。"""
        critic = MockCritic()
        critic.iterative_refinement = IterativeRefinementConfig(max_iterations=3)
        mixin = MockCriticMixin(critic=critic)

        # 将迭代设置为最大
        conversation = create_mock_conversation(iteration=3)
        event = create_finish_action_event(CriticResult(score=0.3, message="Low"))

        should_continue, followup = mixin._check_iterative_refinement(
            conversation, event
        )

        assert should_continue is False
        assert followup is None
        # 迭代应该增加不
        assert (
            conversation.state.agent_state.get(ITERATIVE_REFINEMENT_ITERATION_KEY) == 3
        )

    def test_no_critic_result_returns_false(self):
        """测试缺失的批评家结果会停止细化。"""
        critic = MockCritic()
        critic.iterative_refinement = IterativeRefinementConfig()
        mixin = MockCriticMixin(critic=critic)
        conversation = create_mock_conversation()
        event = create_finish_action_event(critic_result=None)

        should_continue, followup = mixin._check_iterative_refinement(
            conversation, event
        )

        assert should_continue is False
        assert followup is None

    def test_score_meets_threshold(self):
        """测试达到阈值是否会停止细化。"""
        critic = MockCritic()
        critic.iterative_refinement = IterativeRefinementConfig(success_threshold=0.6)
        mixin = MockCriticMixin(critic=critic)
        conversation = create_mock_conversation()
        event = create_finish_action_event(CriticResult(score=0.7, message="Good"))

        should_continue, followup = mixin._check_iterative_refinement(
            conversation, event
        )

        assert should_continue is False
        assert followup is None
        # 迭代应该增加不
        assert (
            conversation.state.agent_state.get(ITERATIVE_REFINEMENT_ITERATION_KEY, 0)
            == 0
        )

    def test_score_exactly_at_threshold(self):
        """测试分数恰好达到阈值即视为成功。"""
        critic = MockCritic()
        critic.iterative_refinement = IterativeRefinementConfig(success_threshold=0.6)
        mixin = MockCriticMixin(critic=critic)
        conversation = create_mock_conversation()
        event = create_finish_action_event(
            CriticResult(score=0.6, message="At threshold")
        )

        should_continue, followup = mixin._check_iterative_refinement(
            conversation, event
        )

        assert should_continue is False
        assert followup is None

    def test_high_probability_issue_continues_even_when_score_meets_threshold(self):
        """高概率智能体问题也应该触发细化。"""
        critic = APIBasedCritic(
            api_key="test-key",
            iterative_refinement=IterativeRefinementConfig(success_threshold=0.6),
        )
        mixin = MockCriticMixin(critic=critic)
        conversation = create_mock_conversation()
        event = create_finish_action_event(
            CriticResult(
                score=0.8,
                message="High score but issue detected",
                metadata={
                    "categorized_features": {
                        "agent_behavioral_issues": [
                            {
                                "name": "insufficient_testing",
                                "display_name": "Insufficient Testing",
                                "probability": 0.8,
                            }
                        ]
                    }
                },
            )
        )

        should_continue, followup = mixin._check_iterative_refinement(
            conversation, event
        )

        assert should_continue is True
        assert critic.issue_threshold == 0.75
        assert followup is not None
        assert "Insufficient Testing (80%)" in followup
        assert (
            conversation.state.agent_state.get(ITERATIVE_REFINEMENT_ITERATION_KEY) == 1
        )

    def test_score_below_threshold_continues(self):
        """测试分数低于阈值会触发继续。"""
        critic = MockCritic()
        critic.iterative_refinement = IterativeRefinementConfig(
            success_threshold=0.6, max_iterations=3
        )
        mixin = MockCriticMixin(critic=critic)
        conversation = create_mock_conversation()
        event = create_finish_action_event(CriticResult(score=0.4, message="Low"))

        should_continue, followup = mixin._check_iterative_refinement(
            conversation, event
        )

        assert should_continue is True
        assert followup is not None
        assert "40.0%" in followup  # 后续得分百分比
        # 迭代应该增加
        assert (
            conversation.state.agent_state.get(ITERATIVE_REFINEMENT_ITERATION_KEY) == 1
        )

    def test_iteration_only_increments_on_continue(self):
        """测试迭代计数器仅在继续时递增。"""
        critic = MockCritic()
        critic.iterative_refinement = IterativeRefinementConfig(
            success_threshold=0.6, max_iterations=3
        )
        mixin = MockCriticMixin(critic=critic)

        # 第一次通话 - 分数低于阈值，应继续
        conversation = create_mock_conversation()
        event = create_finish_action_event(CriticResult(score=0.4, message="Low"))
        should_continue, _ = mixin._check_iterative_refinement(conversation, event)
        assert should_continue is True
        assert (
            conversation.state.agent_state.get(ITERATIVE_REFINEMENT_ITERATION_KEY) == 1
        )

        # 第二次通话 - 分数达到阈值，应该不继续
        event2 = create_finish_action_event(CriticResult(score=0.7, message="Good"))
        should_continue, _ = mixin._check_iterative_refinement(conversation, event2)
        assert should_continue is False
        # 迭代仍应为 1（不递增）
        assert (
            conversation.state.agent_state.get(ITERATIVE_REFINEMENT_ITERATION_KEY) == 1
        )

    def test_multiple_iterations(self):
        """测试多次细化迭代。"""
        critic = MockCritic()
        critic.iterative_refinement = IterativeRefinementConfig(
            success_threshold=0.8, max_iterations=5
        )
        mixin = MockCriticMixin(critic=critic)
        conversation = create_mock_conversation()

        # 模拟多次迭代以提高分数
        scores = [0.3, 0.5, 0.6, 0.75, 0.85]
        for i, score in enumerate(scores):
            event = create_finish_action_event(
                CriticResult(score=score, message=f"Score {score}")
            )
            should_continue, _ = mixin._check_iterative_refinement(conversation, event)

            if score < 0.8:
                assert should_continue is True
                assert (
                    conversation.state.agent_state.get(
                        ITERATIVE_REFINEMENT_ITERATION_KEY
                    )
                    == i + 1
                )
            else:
                assert should_continue is False


class TestShouldEvaluateWithCritic:
    """测试 _should_evaluate_with_critic 方法。"""

    def test_no_critic_returns_false(self):
        """测试没有批评者就意味着没有评价。"""
        mixin = MockCriticMixin(critic=None)
        assert mixin._should_evaluate_with_critic(None) is False
        assert mixin._should_evaluate_with_critic(FinishAction(message="done")) is False

    def test_all_actions_mode(self):
        """测试 all_actions 模式评估所有内容。"""
        critic = MockCritic()
        critic.mode = "all_actions"
        mixin = MockCriticMixin(critic=critic)

        assert mixin._should_evaluate_with_critic(None) is True
        assert mixin._should_evaluate_with_critic(FinishAction(message="done")) is True

    def test_finish_and_message_mode(self):
        """测试 finish_and_message 模式仅评估 FinishAction。"""
        critic = MockCritic()
        critic.mode = "finish_and_message"
        mixin = MockCriticMixin(critic=critic)

        assert mixin._should_evaluate_with_critic(None) is False
        assert mixin._should_evaluate_with_critic(FinishAction(message="done")) is True
