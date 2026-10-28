from collections import defaultdict
from collections.abc import Sequence
from itertools import pairwise

from openhands.sdk.context.view.manipulation_indices import ManipulationIndices
from openhands.sdk.context.view.properties.base import ViewPropertyBase
from openhands.sdk.event import ActionEvent, Event, EventID, LLMConvertibleEvent


class BatchAtomicityProperty(ViewPropertyBase):
    """确保同一批次的所有事件（共享相同的 llm_response_id）形成一个
    原子单位。

    当 LLM 做出包含多个工具调用的单个响应时，这些调用被视为语义相关。 但是，我们将每
    个工具调用拆分为一个单独的事件，因此要重现原始消息，我们必须维护同一批次中的所
    有事件。 如果我们忘记了其中任何一个事件（例如通过上下文压缩），那么我们必须忘记所
    有这些事件以保持一致性。
    """

    def enforce(
        self,
        current_view_events: list[LLMConvertibleEvent],
        all_events: Sequence[Event],
    ) -> set[EventID]:
        """通过从部分删除的事件中删除所有事件来强制执行批处理原子性
        批次。

        如果批次中缺少任何 ActionEvent，此方法将标记该批次中的所有其他 ActionEvent 对
        象以进行删除。 依靠all_events来检测和识别批
        次。
        """
        all_batches = self._build_batches(all_events)
        events_to_remove: set[EventID] = set()

        for llm_response_id, view_batch_ids in self._build_batches(
            current_view_events
        ).items():
            # 我们假设当前视图事件是一个 all_events 序列元素的严格子集 -- 如果视图中的批
            # 次 ID 不与 all_events 序列生成的批次 ID 一一对应，那么只能说明有些东西被遗
            # 忘，我们需要丢弃整个批次。
            #
            if view_batch_ids != all_batches[llm_response_id]:
                events_to_remove.update(view_batch_ids)

        return events_to_remove

    def manipulation_indices(
        self,
        current_view_events: list[LLMConvertibleEvent],
    ) -> ManipulationIndices:
        """计算尊重批次原子性的操作索引。

        在一个批次内（从开始索引到结束），不允许进行任何操作，因此操作索引位于批次边
        界上。
        """
        # 我们将从一组完整的操作索引开始，并删除批次间索引。
        #
        manipulation_indices: ManipulationIndices = ManipulationIndices.complete(
            current_view_events
        )

        for index, (left, right) in enumerate(pairwise(current_view_events)):
            # 如果左侧事件和右侧事件对应于具有相同 LLM 响应 ID 的操作事件，则它们属于同
            # 一批次。 我们需要删除它们之间的索引——枚举索引对应于 `left` 的索引，因此我
            # 们删除 `index + 1`。
            #
            if (
                isinstance(left, ActionEvent)
                and isinstance(right, ActionEvent)
                and left.llm_response_id == right.llm_response_id
            ):
                manipulation_indices.remove(index + 1)

        return manipulation_indices

    def _build_batches(self, events: Sequence[Event]) -> dict[EventID, set[EventID]]:
        """构建从 LLM 个响应 ID 到事件 ID 的映射的实用函数
        该批次中的操作。
        """
        batches: dict[EventID, set[EventID]] = defaultdict(set)

        for event in events:
            if isinstance(event, ActionEvent):
                batches[event.llm_response_id].add(event.id)

        return batches
