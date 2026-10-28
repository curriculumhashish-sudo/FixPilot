"""用于迭代分页搜索结果的分页实用程序。"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, Protocol


class PageProtocol[T](Protocol):
    """搜索函数返回的页面对象的协议。

    所有页面对象应具有：
    - items: T 类型的项目列表
    - next_page_id: 分页所需的可选字符串
    """

    items: list[T]
    next_page_id: str | None


async def page_iterator[T](
    search_func: Callable[..., Awaitable[PageProtocol[T]]],
    *args: Any,
    **kwargs: Any,
) -> AsyncGenerator[T]:
    """
    迭代分页搜索结果中的项目。

    这个实用函数通过反复调用搜索函数并更新 page_id 参数来自动处理分页。

    Args:
        search_func: 返回 PageProtocol[T] 对象的异步函数
                    具有“items”和“next_page_id”属性
        *args: 传递给搜索函数的位置参数
        **kwargs: 要传递给搜索函数的关键字参数

    Yields:
        每页中 T 类型的单独项目

    Example:
        异步对于 page_iterator(event_service.search_events, limit=50) 中的事件：
            等待send_event（事件，WebSocket）

        异步用于 page_iterator( 中的对话
            conversation_service.search_conversations,
            execution_status=ConversationExecutionStatus.RUNNING
        ):
            print(conversation.title)
    """
    page_id = kwargs.pop("page_id", None)

    while True:
        # 以当前page_id调用搜索函数
        page = await search_func(*args, page_id=page_id, **kwargs)

        # 生成当前页面中的每个项目
        for item in page.items:
            yield item

        # 检查是否还有更多页面
        page_id = page.next_page_id
        if not page_id:
            break
