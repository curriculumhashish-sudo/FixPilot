"""测试 BatchAtomicityProperty。

该模块测试 BatchAtomicityProperty 正确确保所有事件
from the same batch (sharing the same llm_response_id) form an atomic unit.
"""

from collections.abc import Sequence

from openhands.sdk.context.view.manipulation_indices import ManipulationIndices
from openhands.sdk.context.view.properties.batch_atomicity import BatchAtomicityProperty
from openhands.sdk.event import LLMConvertibleEvent
from tests.sdk.context.view.properties.conftest import create_action_event


class TestBatchAtomicityPropertyBase:
    """BatchAtomicityProperty 测试套件的基类。"""

    def setup_method(self) -> None:
        """设置测试测试夹具。"""
        self.property = BatchAtomicityProperty()


class TestBatchAtomicityPropertyEnforcement(TestBatchAtomicityPropertyBase):
    """测试 BatchAtomicityProperty 执行情况。"""

    def test_partial_batch_forgotten(self) -> None:
        """测试如果批次中的一个事件被遗忘，则该批次中的所有事件
        被遗忘了。

        这模拟了上下文压缩忘记批次中的一些但不是全部操作的场景。 批处理原子性逻辑应确
        保删除批处理中的所有操作。
        """
        # 根据同一 LLM 响应创建一批 4 个操作
        llm_response_id = "response_1"

        action1 = create_action_event("action_1", llm_response_id, "tool_call_1")
        action2 = create_action_event("action_2", llm_response_id, "tool_call_2")
        action3 = create_action_event("action_3", llm_response_id, "tool_call_3")
        action4 = create_action_event("action_4", llm_response_id, "tool_call_4")

        # 对话中的所有事件
        all_events: Sequence[LLMConvertibleEvent] = [action1, action2, action3, action4]

        # 当前视图保留了action1、action2和action3，但action4被遗忘。这模拟了上下文压缩器
        # 在不考虑批次边界的情况下使用事件索引会发生的情况
        #
        current_view_events: list[LLMConvertibleEvent] = [action4]

        # 强制批处理原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 由于批处理原子性，action4 应该被忘记
        assert action4.id in events_to_remove

    def test_complete_batch_forgotten(self) -> None:
        """测试当批次中的所有事件都被遗忘时，它们都会被删除。"""
        llm_response_id = "response_1"

        action1 = create_action_event("action_1", llm_response_id, "tool_call_1")
        action2 = create_action_event("action_2", llm_response_id, "tool_call_2")

        # 对话中的所有事件
        all_events: Sequence[LLMConvertibleEvent] = [action1, action2]

        # 当前视图没有任何操作（全部忘记）
        current_view_events: Sequence[LLMConvertibleEvent] = []

        # 强制批处理原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 由于该批次已经消失，因此无需再删除
        assert len(events_to_remove) == 0

    def test_no_forgetting_preserves_batch(self) -> None:
        """测试当批次中没有事件被遗忘时，所有事件都会被保留。"""
        llm_response_id = "response_1"

        action1 = create_action_event("action_1", llm_response_id, "tool_call_1")
        action2 = create_action_event("action_2", llm_response_id, "tool_call_2")
        action3 = create_action_event("action_3", llm_response_id, "tool_call_3")

        # 对话中的所有事件
        all_events: Sequence[LLMConvertibleEvent] = [action1, action2, action3]

        # 当前视图包含所有操作
        current_view_events: list[LLMConvertibleEvent] = [action1, action2, action3]

        # 强制批处理原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 任何东西都不应该被删除
        assert len(events_to_remove) == 0

    def test_multiple_batches(self) -> None:
        """测试批处理原子性是否可以在多个单独的批处理中正常工作。

        当一批中只有一个动作被忘记时，该批中的所有动作都应该被忘记。 但不同批次应该是
        独立的。
        """
        # 第一批
        batch1_id = "response_1"
        action1_1 = create_action_event("action_1_1", batch1_id, "tool_call_1")
        action1_2 = create_action_event("action_1_2", batch1_id, "tool_call_2")

        # 第二批
        batch2_id = "response_2"
        action2_1 = create_action_event("action_2_1", batch2_id, "tool_call_3")
        action2_2 = create_action_event("action_2_2", batch2_id, "tool_call_4")

        # 对话中的所有事件
        all_events: Sequence[LLMConvertibleEvent] = [
            action1_1,
            action1_2,
            action2_1,
            action2_2,
        ]

        # 当前视图已忘记 action1_2，但保留了 action1_1（部分批次 1）和 action2_1、
        # action2_2 保留（完整批次 2）
        #
        current_view_events: list[LLMConvertibleEvent] = [
            action1_1,
            action2_1,
            action2_2,
        ]

        # 强制批处理原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 由于我们错过了第二个操作，因此第一批应该被删除
        assert action1_1.id in events_to_remove

        # 第二批应完整保存
        assert action2_1.id not in events_to_remove
        assert action2_2.id not in events_to_remove

    def test_first_action_of_batch_forgotten(self) -> None:
        """测试仅忘记批次的第一个操作会导致整个批次
        被遗忘。
        """
        llm_response_id = "response_1"

        action1 = create_action_event("action_1", llm_response_id, "tool_call_1")
        action2 = create_action_event("action_2", llm_response_id, "tool_call_2")
        action3 = create_action_event("action_3", llm_response_id, "tool_call_3")

        # 对话中的所有事件
        all_events: Sequence[LLMConvertibleEvent] = [action1, action2, action3]

        # 当前视图有action2和action3（action1忘记了）
        current_view_events: list[LLMConvertibleEvent] = [action2, action3]

        # 强制批处理原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # action2和action3都应该被忘记
        assert action2.id in events_to_remove
        assert action3.id in events_to_remove

    def test_middle_action_of_batch_forgotten(self) -> None:
        """测试忘记中间操作是否会导致整个批次被忘记。"""
        llm_response_id = "response_1"

        action1 = create_action_event("action_1", llm_response_id, "tool_call_1")
        action2 = create_action_event("action_2", llm_response_id, "tool_call_2")
        action3 = create_action_event("action_3", llm_response_id, "tool_call_3")

        # 对话中的所有事件
        all_events: Sequence[LLMConvertibleEvent] = [action1, action2, action3]

        # 当前视图有action1和action3（action2忘记了）
        current_view_events: list[LLMConvertibleEvent] = [action1, action3]

        # 强制批处理原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # action1和action3都应该被忘记
        assert action1.id in events_to_remove
        assert action3.id in events_to_remove

    def test_different_batches_independent(self) -> None:
        """测试批次原子性仅影响同一批次中的事件。"""
        batch1_id = "response_1"
        batch2_id = "response_2"

        # 第一批
        action1_1 = create_action_event("action_1_1", batch1_id, "tool_call_1")
        action1_2 = create_action_event("action_1_2", batch1_id, "tool_call_2")

        # 第二批
        action2_1 = create_action_event("action_2_1", batch2_id, "tool_call_3")
        action2_2 = create_action_event("action_2_2", batch2_id, "tool_call_4")

        # 对话中的所有事件
        all_events: Sequence[LLMConvertibleEvent] = [
            action1_1,
            action1_2,
            action2_1,
            action2_2,
        ]

        # 当前视图包含两个批次的所有事件
        current_view_events: list[LLMConvertibleEvent] = [
            action1_1,
            action1_2,
            action2_1,
            action2_2,
        ]

        # 强制批处理原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 任何东西都不应该被删除
        assert len(events_to_remove) == 0

    def test_single_action_batch(self) -> None:
        """测试单个操作的批次是否正常工作。"""
        llm_response_id = "response_1"

        action = create_action_event("action_1", llm_response_id, "tool_call_1")

        # 对话中的所有事件
        all_events: Sequence[LLMConvertibleEvent] = [action]

        # 当前视图有操作
        current_view_events: list[LLMConvertibleEvent] = [action]

        # 强制批处理原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 任何东西都不应该被删除
        assert len(events_to_remove) == 0

    def test_single_action_forgotten(self) -> None:
        """测试是否正确处理了被遗忘的单操作批次。"""
        llm_response_id = "response_1"

        action = create_action_event("action_1", llm_response_id, "tool_call_1")

        # 对话中的所有事件
        all_events: Sequence[LLMConvertibleEvent] = [action]

        # 当前视图没有任何操作（已忘记）
        current_view_events: Sequence[LLMConvertibleEvent] = []

        # 强制批处理原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 没有更多可删除的了
        assert len(events_to_remove) == 0

    def test_partial_batch_across_batches(self) -> None:
        """测试是否处理不同 LLM 响应的部分批次
        独立。
        """
        # 第一批-部分
        batch1_id = "response_1"
        action1_1 = create_action_event("action_1_1", batch1_id, "tool_call_1")
        action1_2 = create_action_event("action_1_2", batch1_id, "tool_call_2")

        # 第二批-完成
        batch2_id = "response_2"
        action2_1 = create_action_event("action_2_1", batch2_id, "tool_call_3")

        # 对话中的所有事件
        all_events: Sequence[LLMConvertibleEvent] = [action1_1, action1_2, action2_1]

        # 当前视图有 action1_2 和 action2_1（action1_1 忘记了）
        current_view_events: list[LLMConvertibleEvent] = [action1_2, action2_1]

        # 强制批处理原子性
        events_to_remove = self.property.enforce(current_view_events, all_events)

        # 由于批次原子性，应删除 action1_2
        assert action1_2.id in events_to_remove

        # action2_1 应将不删除（其批次已完成）
        assert action2_1.id not in events_to_remove


class TestBatchAtomicityPropertyManipulationIndices(TestBatchAtomicityPropertyBase):
    """测试 BatchAtomicityProperty 操纵指数。"""

    def test_same_batch_no_manipulation_index(self) -> None:
        """测试同一批次中的事件不能通过操作进行拆分。"""
        llm_response_id = "response_1"

        action1 = create_action_event("action_1", llm_response_id, "tool_call_1")
        action2 = create_action_event("action_2", llm_response_id, "tool_call_2")
        action3 = create_action_event("action_3", llm_response_id, "tool_call_3")

        current_view_events: list[LLMConvertibleEvent] = [action1, action2, action3]

        indices = self.property.manipulation_indices(current_view_events)

        # 索引 1（action1 和 action2 之间）不应被操纵
        assert 1 not in indices
        # 索引 2（action2 和 action3 之间）不应被操纵
        assert 2 not in indices

    def test_different_batches_allow_manipulation(self) -> None:
        """测试不同批次中的事件可以通过操作进行拆分。"""
        batch1_id = "response_1"
        batch2_id = "response_2"

        action1 = create_action_event("action_1", batch1_id, "tool_call_1")
        action2 = create_action_event("action_2", batch2_id, "tool_call_2")

        current_view_events: list[LLMConvertibleEvent] = [action1, action2]

        indices = self.property.manipulation_indices(current_view_events)

        # 索引 1（action1 和 action2 之间）应该是可操作的，因为它们位于不同的批次中
        #
        assert 1 in indices

    def test_single_event_complete_indices(self) -> None:
        """测试单个事件是否具有完整的操纵索引。"""
        current_view_events: list[LLMConvertibleEvent] = [
            create_action_event("action_1", "response_1", "tool_call_1")
        ]

        indices = self.property.manipulation_indices(current_view_events)
        assert indices == ManipulationIndices.complete(current_view_events)

    def test_empty_events_complete_indices(self) -> None:
        """测试空事件列表是否具有完整的操作索引。"""
        current_view_events: list[LLMConvertibleEvent] = []

        indices = self.property.manipulation_indices(current_view_events)
        assert indices == ManipulationIndices.complete(current_view_events)
