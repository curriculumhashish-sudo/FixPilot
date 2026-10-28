from collections.abc import Sequence
from logging import getLogger

from openhands.sdk.context.view.manipulation_indices import ManipulationIndices
from openhands.sdk.context.view.properties.base import ViewPropertyBase
from openhands.sdk.event import (
    Event,
    EventID,
    LLMConvertibleEvent,
    ObservationBaseEvent,
    ToolCallID,
)


logger = getLogger(__name__)


class ObservationUniquenessProperty(ViewPropertyBase):
    """每个 tool_call_id 最多有一个类似观测结果的事件。

    在飞行中发生崩溃时，可以合成一个 ``AgentErrorEvent`` 来补救，然后原始
    ``ObservationEvent`` 可能会晚些到达，因此最终的视图
    会包含两个观测结果-类似事件共享一个工具调用
    ``tool_call_id``. 下游端点 LLM APIs （例如 Anthropic 工具使用）需要一个
    ``tool_result``，而
    ``ToolCallMatchingProperty`` 假定的严格配对会 ``tool_use``
    上下文压缩期间的 ``KeyError``。

    此属性在 ``ToolCallMatchingProperty`` 之前注册，因此在配对逻辑运行之前会删除重复
    项。
    """

    def enforce(
        self,
        current_view_events: list[LLMConvertibleEvent],
        all_events: Sequence[Event],  # noqa: ARG002
    ) -> set[EventID]:
        """删除任何 ``tool_call_id`` 已发生的类似观测结果的事件
        之前已在视图中观察到。 第一次出现获胜，因为智能体可能已经看到了它。
        """
        events_to_remove: set[EventID] = set()
        seen_tool_call_ids: set[ToolCallID] = set()

        for event in current_view_events:
            if isinstance(event, ObservationBaseEvent):
                if event.tool_call_id in seen_tool_call_ids:
                    events_to_remove.add(event.id)
                else:
                    seen_tool_call_ids.add(event.tool_call_id)

        return events_to_remove

    def manipulation_indices(
        self,
        current_view_events: list[LLMConvertibleEvent],
    ) -> ManipulationIndices:
        """该属性不限制操纵指数。 如果重复
        观测结果类似事件滑过 ``enforce``，记录警告，以便回归可见而不会崩溃上下文压缩
        。
        """
        seen_tool_call_ids: set[ToolCallID] = set()

        for event in current_view_events:
            if isinstance(event, ObservationBaseEvent):
                if event.tool_call_id in seen_tool_call_ids:
                    logger.warning(
                        "Duplicate observation-like event for tool_call_id=%s",
                        event.tool_call_id,
                    )
                else:
                    seen_tool_call_ids.add(event.tool_call_id)

        return ManipulationIndices.complete(current_view_events)
