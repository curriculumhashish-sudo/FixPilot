from __future__ import annotations

from collections.abc import Sequence
from logging import getLogger
from typing import overload

from pydantic import BaseModel, Field

from openhands.sdk.context.view.manipulation_indices import ManipulationIndices
from openhands.sdk.context.view.properties import ALL_PROPERTIES
from openhands.sdk.event import (
    Condensation,
    CondensationRequest,
    LLMConvertibleEvent,
)
from openhands.sdk.event.base import Event


logger = getLogger(__name__)


class View(BaseModel):
    """事件的线性有序视图。

    由上下文压缩器生成，指示包含的事件已准备好作为 LLM 输入进行处理。 还包含带有来自
    上下文压缩流程的信息的字段，以帮助决定是否需要进一步的上下文压缩。
    """

    events: list[LLMConvertibleEvent] = Field(default_factory=list)

    unhandled_condensation_request: bool = False
    """视图中是否存在未处理的上下文压缩请求。"""

    def __len__(self) -> int:
        return len(self.events)

    @property
    def manipulation_indices(self) -> ManipulationIndices:
        """可以在不违反规则的情况下操纵视图事件的索引
        LLM APIs 所期望的属性。

        每个属性都会生成一组独立的操纵索引。 如果索引存在于_所有_属性派生索引集中，则
        该索引位于返回的操作索引集中。
        """
        results: ManipulationIndices = ManipulationIndices.complete(self.events)
        for property in ALL_PROPERTIES:
            results &= property.manipulation_indices(self.events)
        return results

    # 为了保留类似列表的索引，我们最好支持切片和基于位置的索引。 然而，最大的挑战在于根
    # 据输入类型切换返回类型 MyPy 与 `@overload` 装饰器。
    #

    @overload
    def __getitem__(self, key: slice) -> list[LLMConvertibleEvent]: ...

    @overload
    def __getitem__(self, key: int) -> LLMConvertibleEvent: ...

    def __getitem__(
        self, key: int | slice
    ) -> LLMConvertibleEvent | list[LLMConvertibleEvent]:
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            return [self[i] for i in range(start, stop, step)]
        elif isinstance(key, int):
            return self.events[key]
        else:
            raise ValueError(f"Invalid key type: {type(key)}")

    def enforce_properties(
        self,
        all_events: Sequence[Event],
    ) -> None:
        """强制执行当前视图事件列表上的所有属性。

        重复应用每个属性的强制机制，直到视图事件列表达到稳定状态。

        自执行旨在为回退方案通过关联的操纵索引来通过递归维护属性的性质，一旦必须强制
        执行一个属性，就会记录警告。

        就地修改视图。
        """
        for property in ALL_PROPERTIES:
            events_to_forget = property.enforce(self.events, all_events)
            if events_to_forget:
                logger.warning(
                    f"Property {property.__class__} enforced, "
                    f"{len(events_to_forget)} events dropped."
                )

                self.events = [
                    event for event in self.events if event.id not in events_to_forget
                ]
                break

        # 如果我们一路完成循环而没有中断，则意味着不需要强制执行任何属性，并且我们可以保
        # 持视图不变。
        #
        else:
            return

        # 如果我们确实在循环中遇到了中断，则会应用一个属性，现在我们需要再次检查所有属性
        # 以查看是否有任何属性被解锁。
        #
        self.enforce_properties(all_events)

    def append_event(self, event: Event) -> None:
        """将事件附加到视图末尾，应用任何上下文压缩语义
        就像我们一样。

        就地修改视图。
        """
        match event:
            # 当我们遇到上下文压缩事件时，事件列表应该已经反映了智能体迄今为止看到的事件
            # 。 因此，我们可以将上下文压缩语义直接应用于存储的事件。
            #
            case Condensation():
                self.events = event.apply(self.events)
                self.unhandled_condensation_request = False

            case CondensationRequest():
                self.unhandled_condensation_request = True

            case LLMConvertibleEvent():
                self.events.append(event)

            # 如果事件不相关于上下文压缩和不是 LLMConvertible它不应该出现在结果视图中。
            # 包括用于状态跟踪的某些内部事件 LLM 不需要查看 -- 例如，
            # ConversationStateUpdateEvent, PauseEvent, and (relevant here)
            # CondensationRequest.
            #
            case _:
                logger.debug(
                    f"Skipping non-LLMConvertibleEvent of type {type(event)} "
                    "in View.append_event"
                )

    @staticmethod
    def from_events(events: Sequence[Event]) -> View:
        """从事件列表创建视图，尊重任何事件的语义
        上下文压缩事件。
        """
        result: View = View()

        # 生成  LLMConvertibleEvent 对象的智能体可以发送到 LLM 通过逐个添加到结果视图中
        # 。 这确保了浓缩物按生成的顺序应用上下文压缩请求被适当跟踪。
        #
        for event in events:
            result.append_event(event)

        # 加载所有事件后，强制执行相关属性以确保构建正确完成。
        #
        result.enforce_properties(events)

        return result
