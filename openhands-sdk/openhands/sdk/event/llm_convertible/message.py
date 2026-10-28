import copy
from collections.abc import Sequence
from typing import ClassVar

from pydantic import ConfigDict, Field
from rich.text import Text

from openhands.sdk.critic.result import CriticResult
from openhands.sdk.event.base import N_CHAR_PREVIEW, EventID, LLMConvertibleEvent
from openhands.sdk.event.llm_convertible.reasoning_utils import (
    append_visible_responses_reasoning,
    has_visible_responses_reasoning,
)
from openhands.sdk.event.types import SourceType
from openhands.sdk.llm import (
    ImageContent,
    Message,
    RedactedThinkingBlock,
    TextContent,
    ThinkingBlock,
    content_to_str,
)


class MessageEvent(LLMConvertibleEvent):
    """来自智能体或用户的消息。

    这原本是“MessageAction”，但它假设不是工具调用。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    source: SourceType
    llm_message: Message = Field(
        ..., description="The exact LLM message for this message event"
    )
    llm_response_id: EventID | None = Field(
        default=None,
        description=(
            "Completion or Response ID of the LLM response that generated this event"
            "If the source != 'agent', this field is None"
        ),
    )

    # 上下文扩展内容/技能可以移至此处
    activated_skills: list[str] = Field(
        default_factory=list, description="List of activated skill name"
    )
    extended_content: list[TextContent] = Field(
        default_factory=list, description="List of content added by agent context"
    )
    sender: str | None = Field(
        default=None,
        description=(
            "Optional identifier of the sender. "
            "Can be used to track message origin in multi-agent scenarios."
        ),
    )

    critic_result: CriticResult | None = Field(
        default=None,
        description="Optional critic evaluation of this message and preceding history.",
    )

    @property
    def reasoning_content(self) -> str:
        return self.llm_message.reasoning_content or ""

    @property
    def thinking_blocks(self) -> Sequence[ThinkingBlock | RedactedThinkingBlock]:
        """返回 LLM 消息中的 Anthropic 思维块。"""
        return self.llm_message.thinking_blocks

    @property
    def visualize(self) -> Text:
        """返回此消息事件的富文本表示形式。"""
        content = Text()

        # 消息文本内容
        text_parts = content_to_str(self.llm_message.content)
        if text_parts:
            full_content = "".join(text_parts)
            content.append(full_content)
        else:
            content.append("[no text content]")

        # 响应 API 推理（仅限明文； 从不渲染 encrypted_content)
        if has_visible_responses_reasoning(self.llm_message.responses_reasoning_item):
            content.append("\n\n")
        append_visible_responses_reasoning(
            content, self.llm_message.responses_reasoning_item
        )

        # 添加技能信息（如果存在）
        if self.activated_skills:
            content.append(
                f"\n\nActivated Skills: {', '.join(self.activated_skills)}",
            )

        # 添加扩展内容（如果有）
        if self.extended_content:
            assert not any(
                isinstance(c, ImageContent) for c in self.extended_content
            ), "Extended content should not contain images"
            text_parts = content_to_str(self.extended_content)
            content.append(
                "\n\nPrompt Extension based on Agent Context:\n", style="bold"
            )
            content.append(" ".join(text_parts))

        # 显示评论家结果（如果有）
        if self.critic_result is not None:
            content.append(self.critic_result.visualize)

        return content

    def to_llm_message(self) -> Message:
        msg = copy.deepcopy(self.llm_message)
        msg.content = list(msg.content) + list(self.extended_content)
        return msg

    def __str__(self) -> str:
        """MessageEvent 的纯文本字符串表示形式。"""
        base_str = f"{self.__class__.__name__} ({self.source})"
        # 从消息中提取文本内容
        text_parts = []
        message = self.to_llm_message()
        for content in message.content:
            if isinstance(content, TextContent):
                text_parts.append(content.text)
            elif isinstance(content, ImageContent):
                text_parts.append(f"[Image: {len(content.image_urls)} URLs]")

        if text_parts:
            content_preview = " ".join(text_parts)
            if len(content_preview) > N_CHAR_PREVIEW:
                content_preview = content_preview[: N_CHAR_PREVIEW - 3] + "..."
            skill_info = (
                f" [Skills: {', '.join(self.activated_skills)}]"
                if self.activated_skills
                else ""
            )
            thinking_info = (
                f" [Thinking blocks: {len(self.thinking_blocks)}]"
                if self.thinking_blocks
                else ""
            )
            return (
                f"{base_str}\n  {message.role}: "
                f"{content_preview}{skill_info}{thinking_info}"
            )
        else:
            return f"{base_str}\n  {message.role}: [no text content]"
