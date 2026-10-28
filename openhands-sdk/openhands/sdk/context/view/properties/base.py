from abc import ABC, abstractmethod
from collections.abc import Sequence

from openhands.sdk.context.view.manipulation_indices import ManipulationIndices
from openhands.sdk.event import Event, EventID, LLMConvertibleEvent


class ViewPropertyBase(ABC):
    """视图属性的抽象基类。

    属性定义有助于维护视图中事件的完整性和连贯性的规则。 这些属性由两种策略维护：

    1. 通过删除违反该属性的事件来强制执行该属性。
    2. 定义限制视图修改位置的操作索引。

    主要的视图操作方式（除了在对话过程中添加新事件之外）是在上下文压缩器中进行的，这
    些视图设计是为了尊重操作索引。 这意味着属性应该是归纳性的，并且操纵指数应该可以纯
    粹
    根据当前视图中的事件来计算。

    强制执行旨在作为一种回退方案机制来处理边缘情况、不良数据或不可预见的情况。 因为执
    行假设视图处于不良状态，因此通常需要对事件有更全面的理解，因此依赖于对话中的所有
    事
    件的序列。
    """

    @abstractmethod
    def enforce(
        self,
        current_view_events: list[LLMConvertibleEvent],
        all_events: Sequence[Event],
    ) -> set[EventID]:
        """在事件列表上强制执行该属性。

        Args:
            current_view_events: 当前视图中的事件顺序。
            all_events: 对话中所有事件对象的列表。 有用于
                需要引用当前视图之外的事件的属性。

        Returns:
            一组 EventID 对象，对应于应从当前视图中删除以强制执行该属性的事件。
        """

    @abstractmethod
    def manipulation_indices(
        self,
        current_view_events: list[LLMConvertibleEvent],
    ) -> ManipulationIndices:
        """获取事件列表上属性的操作索引。

        Args:
            current_view_events: 当前视图中的事件顺序。

        Returns:
            一个 ManipulationIndices 对象，定义在维护属性的同时可以修改视图的位置。
        """
