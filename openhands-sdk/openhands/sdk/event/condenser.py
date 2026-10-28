from __future__ import annotations

from pydantic import Field
from rich.text import Text

from openhands.sdk.event.base import Event, LLMConvertibleEvent
from openhands.sdk.event.types import EventID, SourceType
from openhands.sdk.llm import Message, TextContent


class Condensation(Event):
    """此操作表示对话历史记录的上下文压缩正在发生。"""

    forgotten_event_ids: set[EventID] = Field(
        default_factory=set,
        description="The IDs of the events that are being forgotten "
        "(removed from the `View` given to the LLM).",
    )

    summary: str | None = Field(
        default=None, description="An optional summary of the events being forgotten."
    )

    summary_offset: int | None = Field(
        default=None,
        ge=0,
        description="An optional offset to the start of the resulting view (after"
        " forgotten events have been removed) indicating where the summary should be"
        " inserted. If not provided, the summary will not be inserted into the view.",
    )
    llm_response_id: EventID = Field(
        description=(
            "Completion or Response ID of the LLM response that generated this event"
        ),
    )

    source: SourceType = "environment"

    @property
    def visualize(self) -> Text:
        text = Text()

        text.append("Auto Conversation Condensation Triggered.\n", style="bold")

        text.append(f"Forgetting {len(self.forgotten_event_ids)} events\n")
        if self.summary:
            text.append("\n[Summary of Events Being Forgotten]\n", style="bold")
            text.append(f"{self.summary}\n")
        return text

    @property
    def summary_event(self) -> CondensationSummaryEvent:
        """生成一个CondensationSummaryEvent。

        由于总结事件不是主事件存储的一部分，并且是动态生成的，因此这个属性确保创建的
        事件基于上下文压缩事件的ID具有唯一且一致的ID。

        Raises:
            ValueError: 如果没有摘要。
        """
        if self.summary is None:
            raise ValueError("No summary present to generate CondensationSummaryEvent.")

        # 为摘要事件创建确定性 ID。 该 ID 在所有自动生成的 ID 中是唯一的（凭借“-summary”
        # 后缀）。 这些事件不打算与常规事件一起存储，但 ID 仍然与基于文件的事件存储兼容
        # 。
        #
        summary_id = f"{self.id}-summary"

        return CondensationSummaryEvent(
            id=summary_id,
            summary=self.summary,
            source=self.source,
        )

    @property
    def has_summary_metadata(self) -> bool:
        """检查摘要和 summary_offset 是否都存在。"""
        return self.summary is not None and self.summary_offset is not None

    def apply(self, events: list[LLMConvertibleEvent]) -> list[LLMConvertibleEvent]:
        """将上下文压缩应用到事件列表。

        此方法删除标记为要忘记的事件并返回新的事件列表。 如果摘要元数据存在（包括摘要
        和偏移），则将对应 CondensationSummaryEvent 插入到指
        定偏移量处，之后将忘记的事件去除。
        """
        output = [event for event in events if event.id not in self.forgotten_event_ids]
        if self.has_summary_metadata:
            assert self.summary_offset is not None
            summary_event = self.summary_event
            output.insert(self.summary_offset, summary_event)
        return output


class CondensationRequest(Event):
    """此操作用于请求对话历史记录的上下文压缩。

    Attributes:
        action (str): 动作类型，即ActionType.CONDENSATION_REQUEST。
    """

    source: SourceType = "environment"

    @property
    def visualize(self) -> Text:
        text = Text()
        text.append("Conversation Condensation Requested\n", style="bold")
        message = (
            "A condensation of the conversation history has been requested to "
            "manage context window usage.\n"
        )
        text.append(message)
        return text


class CondensationSummaryEvent(LLMConvertibleEvent):
    """该事件代表上下文压缩器生成的摘要。"""

    summary: str
    """摘要文本。"""

    source: SourceType = "environment"

    def to_llm_message(self) -> Message:
        return Message(
            role="user",
            content=[TextContent(text=self.summary)],
        )
