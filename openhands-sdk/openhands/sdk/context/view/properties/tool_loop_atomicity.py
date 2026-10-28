from collections.abc import Sequence

from openhands.sdk.context.view.manipulation_indices import ManipulationIndices
from openhands.sdk.context.view.properties.base import ViewPropertyBase
from openhands.sdk.event import (
    ActionEvent,
    Event,
    EventID,
    LLMConvertibleEvent,
    ObservationBaseEvent,
)


class ToolLoopAtomicityProperty(ViewPropertyBase):
    """工具循环是一系列动作/观察对，中间没有任何内容，
    有些智能体认为是单轮。

    对于启用思维的 Anthropic 模型来说，此属性非常重要。 他们期望此类工具循环的第一个
    元素有一个思考块，并使用一些校验和来确保它正确放置。 在这样的设置中，如
    果我们删除工具循环的任何元素，我们就必须删除整个元素。
    """

    def _tool_loops(self, events: Sequence[Event]) -> list[set[EventID]]:
        """计算事件中的所有工具循环。

        Args:
            events: 一系列事件。 一定要井然有序。

        Returns:
            工具循环列表，每个工具循环由一组与循环中的事件相对应的 ID 表示。
        """
        tool_loops: list[set[EventID]] = []
        current_tool_loop: set[EventID] | None = None

        for event in events:
            match event:
                # 如果我们发现带有思维块的动作事件，我们就会启动工具循环。 如果工具循环
                # 已存在，则结束它并开始新的工具循环。
                #
                case ActionEvent() if event.thinking_blocks:
                    if current_tool_loop is not None:
                        tool_loops.append(current_tool_loop)
                    current_tool_loop = {event.id}

                # 如果看到动作或观测结果，当前工具循环状态保持不变——如果在工具循环中，事
                # 件是其中的一部分，如果不在工具循环中，我们不会开始一个新的。
                #
                case ActionEvent() | ObservationBaseEvent():
                    if current_tool_loop is not None:
                        current_tool_loop.add(event.id)

                # 在所有其他情况下，我们都会退出工具循环。
                case _:
                    if current_tool_loop is not None:
                        tool_loops.append(current_tool_loop)
                        current_tool_loop = None

        # 如果事件在我们仍处于工具循环中时结束，请将其附加到输出中。
        if current_tool_loop is not None:
            tool_loops.append(current_tool_loop)

        return tool_loops

    def enforce(
        self,
        current_view_events: list[LLMConvertibleEvent],
        all_events: Sequence[Event],
    ) -> set[EventID]:
        """通过删除部分存在的工具循环来强制工具循环原子性。

        要求我们迭代所有事件以确定工具循环的完整范围。
        """
        all_tool_loops: list[set[EventID]] = self._tool_loops(all_events)
        view_event_ids: set[EventID] = {event.id for event in current_view_events}
        events_to_remove: set[EventID] = set()

        for event in current_view_events:
            # 如果事件已经被标记为删除，我们可以跳过后续检查。
            #
            if event.id in events_to_remove:
                continue

            # 检查该事件是否是工具循环的一部分。 如果是，则该工具循环中的所有事件都必须
            # 是视图的一部分，否则我们必须删除剩余的事件。
            #
            for tool_loop in all_tool_loops:
                if event.id in tool_loop:
                    if not tool_loop.issubset(view_event_ids):
                        events_to_remove.update(view_event_ids & tool_loop)
                    break

        return events_to_remove

    def manipulation_indices(
        self,
        current_view_events: list[LLMConvertibleEvent],
    ) -> ManipulationIndices:
        """计算尊重工具循环原子性的操作索引。

        工具循环内的所有索引都将被删除。
        """
        manipulation_indices: ManipulationIndices = ManipulationIndices.complete(
            current_view_events
        )

        # 为了识别工具循环的边界，我们必须按顺序单步执行所有事件并跟踪我们是否处于工具循
        # 环中。 根据我们进入和退出工具循环时的时间，我们可以从操作索引中移除事件（或不
        # 移除），以确保所有操作索引都处于工具循环的边界。
        #
        in_tool_loop: bool = False

        for index, event in enumerate(current_view_events):
            match event:
                case ActionEvent() if event.thinking_blocks:
                    in_tool_loop = True

                case ActionEvent() | ObservationBaseEvent():
                    if in_tool_loop:
                        manipulation_indices.remove(index)

                case _:
                    in_tool_loop = False

        return manipulation_indices
