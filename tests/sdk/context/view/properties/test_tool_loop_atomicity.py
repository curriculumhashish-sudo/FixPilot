"""测试 ToolLoopAtomicityProperty。

该模块测试 ToolLoopAtomicityProperty 是否正确确保工具循环（动作/观察对的序列）形成原
子单元。

工具循环始于一个包含思考块的动作事件，然后继续通过所有后续的动作/观察事件，直到遇到非
工具循环事件。 没有思维块的动作事件不会启动工具循环。
"""

from collections.abc import Sequence

from openhands.sdk.context.view.manipulation_indices import ManipulationIndices
from openhands.sdk.context.view.properties.tool_loop_atomicity import (
    ToolLoopAtomicityProperty,
)
from openhands.sdk.event import LLMConvertibleEvent
from tests.sdk.context.view.properties.conftest import (
    create_action_event,
    create_message_event,
    create_observation_event,
)


THINKING = "Extended thinking..."


class TestToolLoopAtomicityPropertyBase:
    """ToolLoopAtomicityProperty 测试套件的基类。"""

    def setup_method(self) -> None:
        """设置测试测试夹具。"""
        self.property = ToolLoopAtomicityProperty()


class TestToolLoopAtomicityPropertyEnforcement(TestToolLoopAtomicityPropertyBase):
    """测试 ToolLoopAtomicityProperty 执行情况。"""

    def test_partial_tool_loop_forgotten(self) -> None:
        """测试如果工具循环中的一个事件被遗忘，则该循环中的所有事件
        被遗忘了。

        这模拟了上下文压缩忘记工具循环中的一些但不是全部事件的场景。 工具循环原子性逻
        辑应确保删除循环中的所有事件。
        """
        # 创建工具循环：action（思考）->obs->action->obs
        all_events: Sequence[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_observation_event("obs_1", "call_1"),
            create_action_event("action_2", "resp_2", "call_2"),
            create_observation_event("obs_2", "call_2"),
        ]

        # 当前视图已忘记 action_1、observation_1，但保留了 action_2、obs_2
        current_view_events: list[LLMConvertibleEvent] = [
            create_action_event("action_2", "resp_2", "call_2"),
            create_observation_event("obs_2", "call_2"),
        ]

        # 强制工具循环原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 由于工具循环原子性，action_2 和 obs_2 应该被忘记
        assert "action_2" in events_to_remove
        assert "obs_2" in events_to_remove

    def test_complete_tool_loop_forgotten(self) -> None:
        """测试当工具循环中的所有事件都被遗忘时，它们将被删除。"""
        all_events: Sequence[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_observation_event("obs_1", "call_1"),
        ]

        # 当前视图没有事件（全部忘记）
        current_view_events: list[LLMConvertibleEvent] = []

        # 强制工具循环原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 由于工具循环已经消失，无需再删除任何内容
        assert len(events_to_remove) == 0

    def test_no_forgetting_preserves_tool_loop(self) -> None:
        """测试当工具循环中没有事件被遗忘时，所有事件都会被保留。"""
        all_events: Sequence[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_observation_event("obs_1", "call_1"),
            create_action_event("action_2", "resp_2", "call_2"),
            create_observation_event("obs_2", "call_2"),
        ]

        # 当前视图包含所有事件
        current_view_events: list[LLMConvertibleEvent] = list(all_events)

        # 强制工具循环原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 任何东西都不应该被删除
        assert len(events_to_remove) == 0

    def test_tool_loop_between_non_tool_loop_events(self) -> None:
        """测试工具循环是否受非工具循环事件限制。"""
        all_events: Sequence[LLMConvertibleEvent] = [
            create_message_event("msg_1", "User message"),
            # 工具循环开始（第一个动作的思维阻塞）
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_observation_event("obs_1", "call_1"),
            create_action_event("action_2", "resp_2", "call_2"),
            create_observation_event("obs_2", "call_2"),
            # 工具循环结束
            create_message_event("msg_2", "Another user message"),
        ]

        # 当前视图：第一个操作被遗忘，但 REST 保留
        current_view_events: list[LLMConvertibleEvent] = [
            create_observation_event("obs_1", "call_1"),
            create_action_event("action_2", "resp_2", "call_2"),
            create_observation_event("obs_2", "call_2"),
            create_message_event("msg_2", "Another user message"),
        ]

        # 强制工具循环原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 应删除所有剩余的工具循环事件
        assert "obs_1" in events_to_remove
        assert "action_2" in events_to_remove
        assert "obs_2" in events_to_remove
        # 消息应保留
        assert "msg_2" not in events_to_remove

    def test_first_event_of_tool_loop_forgotten(self) -> None:
        """测试忘记第一个事件是否会导致整个工具循环被忘记。"""
        all_events: Sequence[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_observation_event("obs_1", "call_1"),
            create_action_event("action_2", "resp_2", "call_2"),
            create_observation_event("obs_2", "call_2"),
        ]

        # 当前视图已忘记 action_1
        current_view_events: list[LLMConvertibleEvent] = [
            create_observation_event("obs_1", "call_1"),
            create_action_event("action_2", "resp_2", "call_2"),
            create_observation_event("obs_2", "call_2"),
        ]

        # 强制工具循环原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 所有工具循环事件都应该被忘记
        assert "obs_1" in events_to_remove
        assert "action_2" in events_to_remove
        assert "obs_2" in events_to_remove

    def test_middle_event_of_tool_loop_forgotten(self) -> None:
        """测试忘记中间事件是否会导致整个工具循环被忘记。"""
        all_events: Sequence[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_observation_event("obs_1", "call_1"),
            create_action_event("action_2", "resp_2", "call_2"),
            create_observation_event("obs_2", "call_2"),
        ]

        # 当前视图已忘记 observation_1
        current_view_events: list[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_action_event("action_2", "resp_2", "call_2"),
            create_observation_event("obs_2", "call_2"),
        ]

        # 强制工具循环原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 视图中的所有工具循环事件都应该被忘记
        assert "action_1" in events_to_remove
        assert "action_2" in events_to_remove
        assert "obs_2" in events_to_remove

    def test_multiple_separate_tool_loops(self) -> None:
        """测试多个单独的工具循环是否独立处理。"""
        all_events: Sequence[LLMConvertibleEvent] = [
            # 第一个工具循环（思维块启动它）
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_observation_event("obs_1", "call_1"),
            # 间隙（非工具循环事件）
            create_message_event("msg_1", "User message"),
            # 第二个工具循环（思维块启动它）
            create_action_event("action_2", "resp_2", "call_2", thinking=THINKING),
            create_observation_event("obs_2", "call_2"),
        ]

        # 当前视图：第一个工具循环完成，第二个部分（仅观察，无操作）
        current_view_events: list[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_observation_event("obs_1", "call_1"),
            create_message_event("msg_1", "User message"),
            create_observation_event("obs_2", "call_2"),
        ]

        # 强制工具循环原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 应删除第二个工具循环的观测结果（该操作甚至不在视图中）
        #
        assert "obs_2" in events_to_remove
        # 应保留第一个工具循环
        assert "action_1" not in events_to_remove
        assert "obs_1" not in events_to_remove
        # 消息应保留
        assert "msg_1" not in events_to_remove

    def test_single_action_observation_pair(self) -> None:
        """测试单个操作/观察对是否正常工作。"""
        all_events: Sequence[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_observation_event("obs_1", "call_1"),
        ]

        # 当前视图有两个事件
        current_view_events: list[LLMConvertibleEvent] = list(all_events)

        # 强制工具循环原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 任何东西都不应该被删除
        assert len(events_to_remove) == 0

    def test_single_action_forgotten(self) -> None:
        """测试是否正确处理了被遗忘的单对工具循环。"""
        all_events: Sequence[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_observation_event("obs_1", "call_1"),
        ]

        # 当前视图没有事件（忘记）
        current_view_events: list[LLMConvertibleEvent] = []

        # 强制工具循环原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 没有更多可删除的了
        assert len(events_to_remove) == 0

    def test_actions_without_thinking_are_not_tool_loops(self) -> None:
        """测试没有思维块的行动/观察对不是工具
        循环，因此不受工具循环原子性强制的约束。
        """
        all_events: Sequence[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1"),
            create_observation_event("obs_1", "call_1"),
            create_action_event("action_2", "resp_2", "call_2"),
            create_observation_event("obs_2", "call_2"),
        ]

        # 当前视图已忘记 action_1 和 obs_1
        current_view_events: list[LLMConvertibleEvent] = [
            create_action_event("action_2", "resp_2", "call_2"),
            create_observation_event("obs_2", "call_2"),
        ]

        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 如果没有思维块，就没有工具循环，因此无需强制执行
        assert len(events_to_remove) == 0


class TestToolLoopAtomicityPropertyManipulationIndices(
    TestToolLoopAtomicityPropertyBase
):
    """测试 ToolLoopAtomicityProperty 操纵指数。"""

    def test_no_manipulation_within_tool_loop(self) -> None:
        """测试工具循环中的事件是否无法通过操作进行拆分。"""
        current_view_events: list[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_observation_event("obs_1", "call_1"),
            create_action_event("action_2", "resp_2", "call_2"),
            create_observation_event("obs_2", "call_2"),
        ]

        indices = self.property.manipulation_indices(current_view_events)

        # 整个事件集是一个工具循环，因此唯一的索引位于开始和结束处。
        #
        assert indices == {0, 4}

    def test_manipulation_allowed_between_tool_loops(self) -> None:
        """测试单独的工具循环之间是否允许进行操作。"""
        current_view_events: list[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_observation_event("obs_1", "call_1"),
            create_message_event("msg_1", "User message"),
            create_action_event("action_2", "resp_2", "call_2", thinking=THINKING),
            create_observation_event("obs_2", "call_2"),
        ]

        indices = self.property.manipulation_indices(current_view_events)

        # 用户消息开始、结束和包装处的索引。 工具循环内没有索引。
        #
        assert indices == {0, 2, 3, 5}

    def test_manipulation_allowed_before_first_tool_loop(self) -> None:
        """测试在第一个工具循环之前是否允许进行操作。"""
        current_view_events: list[LLMConvertibleEvent] = [
            create_message_event("msg_1", "User message"),
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_observation_event("obs_1", "call_1"),
        ]

        indices = self.property.manipulation_indices(current_view_events)

        # 操作和观测结果之间不应有索引。
        assert indices == {0, 1, 3}

    def test_single_event_complete_indices(self) -> None:
        """测试单个事件是否具有完整的操纵索引。"""
        current_view_events: list[LLMConvertibleEvent] = [
            create_message_event("msg_1", "User message"),
        ]

        indices = self.property.manipulation_indices(current_view_events)
        assert indices == ManipulationIndices.complete(current_view_events)

    def test_empty_events_complete_indices(self) -> None:
        """测试空事件列表是否具有完整的操作索引。"""
        current_view_events: list[LLMConvertibleEvent] = []

        indices = self.property.manipulation_indices(current_view_events)
        assert indices == ManipulationIndices.complete(current_view_events)

    def test_tool_loop_with_message_breaks_at_boundary(self) -> None:
        """测试消息事件是否会中断工具循环。"""
        current_view_events: list[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1", thinking=THINKING),
            create_observation_event("obs_1", "call_1"),
            create_message_event("msg_1", "User message"),
            create_action_event("action_2", "resp_2", "call_2", thinking=THINKING),
            create_observation_event("obs_2", "call_2"),
        ]

        indices = self.property.manipulation_indices(current_view_events)

        # 除 1 和 4 之外的所有索引，因为这些索引位于操作和观测结果之间。
        assert indices == {0, 2, 3, 5}

    def test_parallel_actions_in_tool_loop(self) -> None:
        """测试并行操作（相同的响应）是否位于同一工具循环中。"""
        # 来自相同响应（并行）的两个操作，后跟观测结果。 第一个动作有思维块，启动工具循
        # 环。
        #
        current_view_events: list[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1a", thinking=THINKING),
            create_action_event("action_1b", "resp_1", "call_1b"),
            create_observation_event("obs_1a", "call_1a"),
            create_observation_event("obs_1b", "call_1b"),
        ]

        indices = self.property.manipulation_indices(current_view_events)

        # 这是一个大的工具循环，因此只有开始和结束是可操作的。
        assert indices == {0, 4}

    def test_no_tool_loop_without_thinking_blocks(self) -> None:
        """测试没有思考块的行动不会形成工具循环。"""
        current_view_events: list[LLMConvertibleEvent] = [
            create_action_event("action_1", "resp_1", "call_1"),
            create_observation_event("obs_1", "call_1"),
            create_action_event("action_2", "resp_2", "call_2"),
            create_observation_event("obs_2", "call_2"),
        ]

        indices = self.property.manipulation_indices(current_view_events)

        # 没有思考块，就没有工具循环。 所有指数均可用。
        assert indices == ManipulationIndices.complete(current_view_events)
