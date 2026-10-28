from collections.abc import Sequence

from openhands.sdk.context.view.manipulation_indices import ManipulationIndices
from openhands.sdk.context.view.properties.base import ViewPropertyBase
from openhands.sdk.event import (
    ActionEvent,
    Event,
    EventID,
    LLMConvertibleEvent,
    ObservationBaseEvent,
    ToolCallID,
)


class ToolCallMatchingProperty(ViewPropertyBase):
    """操作和观测结果必须配对。

    最终获得 LLM 的已序列化的视图应该为每个操作 ``tool_call_id`` 恰好包含一个类似观测
    结果的事件。 一些提供商（例如Anthropic工具使用）要
    求每个``tool_use``在立即后续的用户消息中必须有一个对应的``tool_result``，因此重复
    观测结果-类似事件是无法安全忽略的。
    """

    def enforce(
        self,
        current_view_events: list[LLMConvertibleEvent],
        all_events: Sequence[Event],  # noqa: ARG002
    ) -> set[EventID]:
        """通过删除不匹配的操作来强制工具调用匹配观测结果，
        反之亦然。
        """
        # 首先分别收集与操作关联的所有工具调用 ID 和观测结果。
        #
        action_tool_call_ids: set[ToolCallID] = set()
        observation_tool_call_ids: set[ToolCallID] = set()

        for event in current_view_events:
            match event:
                case ActionEvent():
                    action_tool_call_ids.add(event.tool_call_id)
                case ObservationBaseEvent():
                    observation_tool_call_ids.add(event.tool_call_id)

        # 如果某个操作事件的工具调用 ID 未出现在任何观测结果中，我们需要将其删除。 同样
        # ，如果观测结果具有不在任何操作事件中的工具调用 ID，我们需要将其删除。
        #
        events_to_remove: set[EventID] = set()

        for event in current_view_events:
            match event:
                case ActionEvent():
                    if event.tool_call_id not in observation_tool_call_ids:
                        events_to_remove.add(event.id)
                case ObservationBaseEvent():
                    if event.tool_call_id not in action_tool_call_ids:
                        events_to_remove.add(event.id)

        return events_to_remove

    def manipulation_indices(
        self,
        current_view_events: list[LLMConvertibleEvent],
    ) -> ManipulationIndices:
        """计算工具调用匹配的操作索引。

        操作与其匹配的观测结果之间的索引受到保护。 观测结果没有待处理操作的类似事件不
        会影响边界； 财产执行分别删除孤立和重复的观测结果。
        """
        # 从一组完整的操作索引开始，然后我们将删除操作及其配对的观测结果之间的索引。
        #
        manipulation_indices: ManipulationIndices = ManipulationIndices.complete(
            current_view_events
        )

        # 行动总是在前观测结果所以我们可以维护一个待处理的集合工具调用 -- 这些都是工具调
        # 用已经被一个动作引入，但尚未由一个动作解决的观测结果。 如果有任何待处理的工具
        # 调用我们知道我们处于一个动作/观察对之间。
        #
        pending_tool_call_ids: set[ToolCallID] = set()

        for index, event in enumerate(current_view_events):
            match event:
                case ActionEvent():
                    pending_tool_call_ids.add(event.tool_call_id)
                case ObservationBaseEvent():
                    pending_tool_call_ids.discard(event.tool_call_id)

            if pending_tool_call_ids:
                # 枚举索引对应于事件的位置，但我们希望索引紧随其后。
                #
                manipulation_indices.remove(index + 1)

        return manipulation_indices
