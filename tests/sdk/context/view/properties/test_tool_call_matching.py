"""测试 ToolCallMatchingProperty。

该模块测试操作和观测结果是否与 tool_call_id 正确配对。 该属性可确保过滤掉不匹配的操作
和观测结果。
"""

from unittest.mock import create_autospec

from openhands.sdk.context.view import View
from openhands.sdk.context.view.manipulation_indices import ManipulationIndices
from openhands.sdk.context.view.properties.tool_call_matching import (
    ToolCallMatchingProperty,
)
from openhands.sdk.event.base import LLMConvertibleEvent
from openhands.sdk.event.llm_convertible import (
    ActionEvent,
    AgentErrorEvent,
    ObservationEvent,
    UserRejectObservation,
)
from tests.sdk.context.view.conftest import (
    create_action_event,
    create_observation_event,
)
from tests.sdk.context.view.properties.conftest import (
    create_action_event_with_none_action,
    message_event,
)


class TestToolCallMatchingBase:
    """ToolCallMatchingProperty 测试套件的基类。"""

    def setup_method(self) -> None:
        """设置测试测试夹具。"""
        self.property = ToolCallMatchingProperty()


class TestToolCallMatchingPropertyEnforcement(TestToolCallMatchingBase):
    """测试 ToolCallMatchingProperty 的强制方法。"""

    def test_empty_list(self) -> None:
        """使用空事件列表测试强制执行。"""
        result = self.property.enforce([], [])
        assert result == set()

    def test_no_tool_events(self) -> None:
        """在没有工具事件的情况下测试强制执行。"""
        message1 = message_event("First message")
        message2 = message_event("Second message")

        events: list[LLMConvertibleEvent] = [message1, message2]
        result = self.property.enforce(events, events)

        # 没有工具事件，没有要删除的内容
        assert result == set()

    def test_matched_pairs(self) -> None:
        """使用匹配的工具调用对测试强制执行。"""
        message = message_event("Test message")

        # 配对1
        action_event_1 = create_autospec(ActionEvent, instance=True)
        action_event_1.tool_call_id = "call_1"
        action_event_1.id = "action_1"
        action_event_1.llm_response_id = "response_1"

        observation_event_1 = create_autospec(ObservationEvent, instance=True)
        observation_event_1.tool_call_id = "call_1"
        observation_event_1.id = "obs_1"

        # 配对2
        action_event_2 = create_autospec(ActionEvent, instance=True)
        action_event_2.tool_call_id = "call_2"
        action_event_2.id = "action_2"
        action_event_2.llm_response_id = "response_2"

        observation_event_2 = create_autospec(ObservationEvent, instance=True)
        observation_event_2.tool_call_id = "call_2"
        observation_event_2.id = "obs_2"

        events: list[LLMConvertibleEvent] = [
            message,
            action_event_1,
            observation_event_1,
            action_event_2,
            observation_event_2,
        ]

        result = self.property.enforce(events, events)

        # 应保留所有事件（所有工具调用均匹配）
        assert result == set()
        assert action_event_1.id not in result
        assert observation_event_1.id not in result

    def test_unmatched_action(self) -> None:
        """使用不匹配的 ActionEvent 测试强制执行。"""
        message = message_event("Test message")

        # 配对
        action_event_matched = create_autospec(ActionEvent, instance=True)
        action_event_matched.tool_call_id = "call_1"
        action_event_matched.id = "action_1"
        action_event_matched.llm_response_id = "response_1"

        observation_event_matched = create_autospec(ObservationEvent, instance=True)
        observation_event_matched.tool_call_id = "call_1"
        observation_event_matched.id = "obs_1"

        # 无与伦比的ActionEvent
        action_event_unmatched = create_autospec(ActionEvent, instance=True)
        action_event_unmatched.tool_call_id = "call_2"
        action_event_unmatched.id = "action_2"
        action_event_unmatched.llm_response_id = "response_2"

        events: list[LLMConvertibleEvent] = [
            message,
            action_event_matched,
            observation_event_matched,
            action_event_unmatched,
        ]

        result = self.property.enforce(events, events)

        # 应保留：消息、匹配对应删除：不匹配的 ActionEvent
        #
        assert result == {action_event_unmatched.id}

    def test_unmatched_observation(self) -> None:
        """使用不匹配的 ObservationEvent 测试强制执行。"""
        message = message_event("Test message")

        # 配对
        action_event_matched = create_autospec(ActionEvent, instance=True)
        action_event_matched.tool_call_id = "call_1"
        action_event_matched.id = "action_1"
        action_event_matched.llm_response_id = "response_1"

        observation_event_matched = create_autospec(ObservationEvent, instance=True)
        observation_event_matched.tool_call_id = "call_1"
        observation_event_matched.id = "obs_1"

        # 无与伦比的ObservationEvent
        observation_event_unmatched = create_autospec(ObservationEvent, instance=True)
        observation_event_unmatched.tool_call_id = "call_2"
        observation_event_unmatched.id = "obs_2"

        events: list[LLMConvertibleEvent] = [
            message,
            action_event_matched,
            observation_event_matched,
            observation_event_unmatched,
        ]

        result = self.property.enforce(events, events)

        # 应保留：消息、匹配对应删除：不匹配的 ObservationEvent
        #
        assert result == {observation_event_unmatched.id}

    def test_mixed_scenario(self) -> None:
        """使用复杂的混合场景进行测试。"""
        message_event_1 = message_event("Message 1")
        message_event_2 = message_event("Message 2")

        # 配对1
        action_event_1 = create_autospec(ActionEvent, instance=True)
        action_event_1.tool_call_id = "call_1"
        action_event_1.id = "action_1"
        action_event_1.llm_response_id = "response_1"

        observation_event_1 = create_autospec(ObservationEvent, instance=True)
        observation_event_1.tool_call_id = "call_1"
        observation_event_1.id = "obs_1"

        # 无与伦比的ActionEvent
        action_event_unmatched = create_autospec(ActionEvent, instance=True)
        action_event_unmatched.tool_call_id = "call_2"
        action_event_unmatched.id = "action_unmatched"
        action_event_unmatched.llm_response_id = "response_2"

        # 无与伦比的ObservationEvent
        observation_event_unmatched = create_autospec(ObservationEvent, instance=True)
        observation_event_unmatched.tool_call_id = "call_3"
        observation_event_unmatched.id = "obs_unmatched"

        # 配对2
        action_event_2 = create_autospec(ActionEvent, instance=True)
        action_event_2.tool_call_id = "call_4"
        action_event_2.id = "action_2"
        action_event_2.llm_response_id = "response_3"

        observation_event_2 = create_autospec(ObservationEvent, instance=True)
        observation_event_2.tool_call_id = "call_4"
        observation_event_2.id = "obs_2"

        events: list[LLMConvertibleEvent] = [
            message_event_1,
            action_event_1,
            observation_event_1,
            action_event_unmatched,
            observation_event_unmatched,
            message_event_2,
            action_event_2,
            observation_event_2,
        ]

        result = self.property.enforce(events, events)

        # 应删除：不匹配的操作和观测结果事件
        assert action_event_unmatched.id in result
        assert observation_event_unmatched.id in result
        assert action_event_1.id not in result
        assert observation_event_1.id not in result
        assert action_event_2.id not in result
        assert observation_event_2.id not in result

    def test_with_user_reject_observation(self) -> None:
        """测试ActionEvent和UserRejectObservation没有被过滤掉。"""
        action_event = create_autospec(ActionEvent, instance=True)
        action_event.tool_call_id = "call_1"
        action_event.id = "action_1"
        action_event.llm_response_id = "response_1"

        user_reject_obs = UserRejectObservation(
            action_id="action_1",
            tool_name="TerminalTool",
            tool_call_id="call_1",
            rejection_reason="User rejected the action",
        )

        message1 = message_event("First message")
        message2 = message_event("Second message")

        events: list[LLMConvertibleEvent] = [
            message1,
            action_event,
            user_reject_obs,
            message2,
        ]

        result = self.property.enforce(events, events)

        # ActionEvent和UserRejectObservation都应该保留
        assert len(result) == 0

    def test_with_agent_error_event(self) -> None:
        """测试与AgentErrorEvent配对的ActionEvent没有被过滤掉。"""
        action_event = create_autospec(ActionEvent, instance=True)
        action_event.tool_call_id = "call_1"
        action_event.id = "action_1"
        action_event.llm_response_id = "response_1"

        agent_error = AgentErrorEvent(
            error="Tool execution failed",
            tool_name="TerminalTool",
            tool_call_id="call_1",
        )

        message1 = message_event("First message")
        message2 = message_event("Second message")

        events: list[LLMConvertibleEvent] = [
            message1,
            action_event,
            agent_error,
            message2,
        ]

        result = self.property.enforce(events, events)

        # ActionEvent和AgentErrorEvent都应该保留
        assert len(result) == 0

    def test_mixed_observation_types(self) -> None:
        """使用混合观测结果类型测试过滤。"""
        # ActionEvents
        action_event_1 = create_autospec(ActionEvent, instance=True)
        action_event_1.tool_call_id = "call_1"
        action_event_1.id = "action_1"
        action_event_1.llm_response_id = "response_1"

        action_event_2 = create_autospec(ActionEvent, instance=True)
        action_event_2.tool_call_id = "call_2"
        action_event_2.id = "action_2"
        action_event_2.llm_response_id = "response_2"

        action_event_3 = create_autospec(ActionEvent, instance=True)
        action_event_3.tool_call_id = "call_3"
        action_event_3.id = "action_3"
        action_event_3.llm_response_id = "response_3"

        # 正常观测结果
        observation_event = create_autospec(ObservationEvent, instance=True)
        observation_event.tool_call_id = "call_1"
        observation_event.id = "obs_1"

        # 用户拒绝
        user_reject_obs = UserRejectObservation(
            action_id="action_2",
            tool_name="TerminalTool",
            tool_call_id="call_2",
            rejection_reason="User rejected the action",
        )

        # 智能体错误
        agent_error = AgentErrorEvent(
            error="Tool execution failed",
            tool_name="TerminalTool",
            tool_call_id="call_3",
        )

        events: list[LLMConvertibleEvent] = [
            message_event("Start"),
            action_event_1,
            observation_event,
            action_event_2,
            user_reject_obs,
            action_event_3,
            agent_error,
            message_event("End"),
        ]

        result = self.property.enforce(events, events)

        # 应保留所有匹配对
        assert len(result) == 0

    def test_action_with_none_action_matched_by_agent_error(self) -> None:
        """测试 ActionEvent 与 action=None 匹配时是否被保留
        AgentErrorEvent.

        这测试了操作未执行（e.g.，工具丢失）但仍有匹配的 AgentErrorEvent 的情况 - 两
        者都应保留。
        """
        # ActionEvent with action=None（操作未执行）
        action_event = create_action_event_with_none_action(
            "action_1", "resp_1", "call_keep_me"
        )

        # 匹配AgentErrorEvent（观测结果路径）
        agent_error = AgentErrorEvent(
            source="agent",
            error="not found",
            tool_name="missing_tool",
            tool_call_id="call_keep_me",
        )

        # 噪音消息事件
        m1 = message_event("hi")
        m2 = message_event("bye")

        events: list[LLMConvertibleEvent] = [m1, action_event, agent_error, m2]

        result = self.property.enforce(events, events)

        # ActionEvent(action=None) 和匹配的 AgentErrorEvent 都必须保留
        assert len(result) == 0
        assert action_event.id not in result
        assert agent_error.id not in result


class TestToolCallMatchingPropertyManipulationIndices(TestToolCallMatchingBase):
    """测试 ToolCallMatchingProperty 的 manipulation_indices 方法。"""

    def test_single_event_complete_indices(self) -> None:
        """单个不可配对事件的测试操作索引已完成。"""
        message = message_event("Test")
        events: list[LLMConvertibleEvent] = [message]

        result = self.property.manipulation_indices(events)

        assert result == ManipulationIndices.complete(events)

    def test_matched_pair_no_index_between(self) -> None:
        """测试匹配动作和观测结果之间没有操纵索引。"""
        action = create_autospec(ActionEvent, instance=True)
        action.tool_call_id = "call_1"
        action.id = "action_1"
        action.llm_response_id = "response_1"

        observation = create_autospec(ObservationEvent, instance=True)
        observation.tool_call_id = "call_1"
        observation.id = "obs_1"

        events: list[LLMConvertibleEvent] = [action, observation]

        result = self.property.manipulation_indices(events)

        # 不允许使用索引 1（在操作和观测结果之间）
        assert 1 not in result

    def test_allow_index_between_pairs(self) -> None:
        """测试单独的匹配对之间是否允许进行操作。"""
        # 第一对
        action1 = create_autospec(ActionEvent, instance=True)
        action1.tool_call_id = "call_1"
        action1.id = "action_1"
        action1.llm_response_id = "response_1"

        observation1 = create_autospec(ObservationEvent, instance=True)
        observation1.tool_call_id = "call_1"
        observation1.id = "obs_1"

        # 第二对
        action2 = create_autospec(ActionEvent, instance=True)
        action2.tool_call_id = "call_2"
        action2.id = "action_2"
        action2.llm_response_id = "response_2"

        observation2 = create_autospec(ObservationEvent, instance=True)
        observation2.tool_call_id = "call_2"
        observation2.id = "obs_2"

        events: list[LLMConvertibleEvent] = [
            action1,
            observation1,
            action2,
            observation2,
        ]

        result = self.property.manipulation_indices(events)

        # 应允许使用索引 2（两对之间）
        assert 2 in result
        # 不允许使用索引 1（操作 1 和观察 1 之间）
        assert 1 not in result

    def test_empty_events(self) -> None:
        """空事件的测试操作索引已完成。"""
        events: list[LLMConvertibleEvent] = []

        result = self.property.manipulation_indices(events)
        assert result == ManipulationIndices.complete(events)

    def test_view_tolerates_orphaned_agent_error(self) -> None:
        """没有相应操作的恢复错误无法阻止 View 消费者。"""
        orphan = AgentErrorEvent(
            error="Tool execution was interrupted by a restart",
            tool_name="TerminalTool",
            tool_call_id="orphaned_call",
        )
        message = message_event("Continue")
        events: list[LLMConvertibleEvent] = [orphan, message]

        assert View(events=events).manipulation_indices == ManipulationIndices.complete(
            events
        )

    def test_orphan_does_not_resolve_another_pending_action(self) -> None:
        """不相关的孤儿留下了受保护的有效操作间隔。"""
        action = create_action_event("response", "pending_call")
        orphan = AgentErrorEvent(
            error="Tool execution was interrupted by a restart",
            tool_name="TerminalTool",
            tool_call_id="orphaned_call",
        )
        observation = create_observation_event("pending_call")
        events: list[LLMConvertibleEvent] = [action, orphan, observation]

        result = View(events=events).manipulation_indices

        assert result == {0, 3}

    def test_duplicate_observation_does_not_crash_manipulation_indices(self) -> None:
        """重复清理属于属性执行，而不是边界查找。"""
        action = create_action_event("response", "call")
        first = create_observation_event("call")
        duplicate = create_observation_event("call")
        events: list[LLMConvertibleEvent] = [action, first, duplicate]

        assert View(events=events).manipulation_indices == {0, 2, 3}
        assert [event.id for event in View.from_events(events).events] == [
            action.id,
            first.id,
        ]
