import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from pydantic import ConfigDict, Field, field_validator
from rich.text import Text

from openhands.sdk.event.types import ROOT_PARENT_ID, EventID, SourceType
from openhands.sdk.llm import ImageContent, Message, TextContent
from openhands.sdk.utils.models import DiscriminatedUnionMixin


if TYPE_CHECKING:
    from openhands.sdk.event.llm_convertible import ActionEvent

N_CHAR_PREVIEW = 500


class Event(DiscriminatedUnionMixin, ABC):
    """所有事件的基类。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)
    id: EventID = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique event id (ULID/UUID)",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Event timestamp",
    )  # 与V1一致
    source: SourceType = Field(..., description="The source of this event")
    parent_id: EventID | None = Field(
        default=None,
        description=(
            "Parent event id in the conversation tree. None for the root, or for "
            "legacy events predating the tree (see EventLog's effective-parent "
            "rule). Events sharing a parent_id are sibling branches."
        ),
    )

    @field_validator("id")
    @classmethod
    def _reject_reserved_id(cls, v: EventID) -> EventID:
        # ROOT_PARENT_ID是保留的parent_id哨兵值； id 等于它的事件会使其子级在树中看起来
        # 没有父级。
        #
        if v == ROOT_PARENT_ID:
            raise ValueError(f"Event id may not equal reserved sentinel {v!r}")
        return v

    @property
    def visualize(self) -> Text:
        """返回此事件的富文本表示形式。

        这是未知事件类型的回退方案实现。 子类应该重写此方法以提供特定的可视化。
        """
        content = Text()
        content.append(f"Unknown event type: {self.__class__.__name__}")
        content.append(f"\n{self.model_dump()}")
        return content

    def __str__(self) -> str:
        """用于显示的纯文本字符串表示形式。"""
        return f"{self.__class__.__name__} ({self.source})"

    def __repr__(self) -> str:
        """开发人员友好的表示。"""
        return (
            f"{self.__class__.__name__}(id='{self.id[:8]}...', "
            f"source='{self.source}', timestamp='{self.timestamp}')"
        )


class LLMConvertibleEvent(Event, ABC):
    """可转换为 LLM 消息的事件的基类。"""

    @abstractmethod
    def to_llm_message(self) -> Message:
        raise NotImplementedError()

    def __str__(self) -> str:
        """显示 LLM 消息内容的纯文本字符串表示形式。"""
        base_str = super().__str__()
        try:
            llm_message = self.to_llm_message()
            # 从消息中提取文本内容
            text_parts = []
            for content in llm_message.content:
                if isinstance(content, TextContent):
                    text_parts.append(content.text)
                elif isinstance(content, ImageContent):
                    text_parts.append(f"[Image: {len(content.image_urls)} URLs]")

            if text_parts:
                content_preview = " ".join(text_parts)
                # 截断长内容以供显示
                if len(content_preview) > N_CHAR_PREVIEW:
                    content_preview = content_preview[: N_CHAR_PREVIEW - 3] + "..."
                return f"{base_str}\n  {llm_message.role}: {content_preview}"
            else:
                return f"{base_str}\n  {llm_message.role}: [no text content]"
        except Exception:
            # 如果 LLM 消息转换失败，则回退方案转换为基本表示
            return base_str

    @staticmethod
    def events_to_messages(events: list["LLMConvertibleEvent"]) -> list[Message]:
        """将事件流转换为 LLM 消息流，处理多操作批次。

        这是一个只读的事件日志投影：事件一旦创建并添加，就不可变，合并会构建新的内容
        列表，而不是修改事件本身的消息。
        """
        from openhands.sdk.event.llm_convertible import ActionEvent

        messages = []
        i = 0

        while i < len(events):
            event = events[i]

            if isinstance(event, ActionEvent):
                # 从相同的 LLM 响应中收集所有 ActionEvents 这在函数调用发生时发生
                #
                batch_events: list[ActionEvent] = [event]
                response_id = event.llm_response_id

                # 敬请期待相关活动
                j = i + 1
                while j < len(events) and isinstance(events[j], ActionEvent):
                    event = events[j]
                    assert isinstance(event, ActionEvent)  # for type checker
                    if event.llm_response_id != response_id:
                        break
                    batch_events.append(event)
                    j += 1

                # 为响应创建组合消息
                msg = _combine_action_events(batch_events)
                if messages and _can_merge_user_messages(messages[-1], msg):
                    messages[-1].content = list(messages[-1].content) + list(
                        msg.content
                    )
                else:
                    messages.append(msg)
                i = j
            else:
                # 常规活动-直接转化
                msg = event.to_llm_message()
                if messages and _can_merge_user_messages(messages[-1], msg):
                    messages[-1].content = list(messages[-1].content) + list(
                        msg.content
                    )
                else:
                    messages.append(msg)
                i += 1

        return messages


def _is_plain_user_message(message: Message) -> bool:
    """没有工具调用元数据的普通用户轮流——可以安全地合并。"""
    return (
        message.role == "user"
        and message.tool_calls is None
        and message.tool_call_id is None
        and message.name is None
    )


def _can_merge_user_messages(previous: Message, current: Message) -> bool:
    """返回两条用户消息是否可以安全地以 LLM 轮的形式发送。"""
    return _is_plain_user_message(previous) and _is_plain_user_message(current)


def _combine_action_events(events: list["ActionEvent"]) -> Message:
    """将多个 ActionEvents 合并为单个 LLM 消息。

    我们收到多个 ActionEvents 每 LLM 消息 WHEN LLM 通过并行函数调用返回多个工具调用。
    """
    if len(events) == 1:
        return events[0].to_llm_message()
    # 多操作案例 - 重建原始 LLM 响应
    for e in events[1:]:
        assert len(e.thought) == 0, (
            "Expected empty thought for multi-action events after the first one"
        )

    return Message(
        role="assistant",
        content=events[0].thought,  # 仅在第一个事件中共享思想内容
        tool_calls=[event.tool_call for event in events],
        reasoning_content=events[0].reasoning_content,  # 分享推理内容
        thinking_blocks=events[0].thinking_blocks,  # 共享思维块
        # 共享答案推理项目
        responses_reasoning_item=events[0].responses_reasoning_item,
    )
