from rich.text import Text

from openhands.sdk.event.base import Event
from openhands.sdk.event.types import SourceType


class PauseEvent(Event):
    """指示智能体执行已根据用户请求暂停的事件。"""

    source: SourceType = "user"

    @property
    def visualize(self) -> Text:
        """返回此暂停事件的富文本表示形式。"""
        content = Text()
        content.append("Conversation Paused", style="bold")
        return content

    def __str__(self) -> str:
        """PauseEvent 的纯文本字符串表示形式。"""
        return f"{self.__class__.__name__} ({self.source}): Agent execution paused"


class InterruptEvent(Event):
    """指示智能体在操作过程中中断的事件。

    与在智能体个步骤之间生效的：class:`PauseEvent` 不同，中断会立即取消正在进行的 LLM
     调用。 对话状态设置为 PAUSED，以便稍后可以恢复。
    """

    source: SourceType = "user"

    @property
    def visualize(self) -> Text:
        content = Text()
        content.append("Conversation Interrupted", style="bold red")
        return content

    def __str__(self) -> str:
        return f"{self.__class__.__name__} ({self.source}): Agent execution interrupted"
