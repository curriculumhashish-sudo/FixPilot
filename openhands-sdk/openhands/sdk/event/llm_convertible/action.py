from collections.abc import Sequence
from typing import Protocol, cast

from pydantic import Field
from rich.text import Text

from openhands.sdk.critic.result import CriticResult
from openhands.sdk.event.base import N_CHAR_PREVIEW, EventID, LLMConvertibleEvent
from openhands.sdk.event.llm_convertible.reasoning_utils import (
    append_visible_responses_reasoning,
)
from openhands.sdk.event.types import SourceType, ToolCallID
from openhands.sdk.llm import (
    Message,
    MessageToolCall,
    ReasoningItemModel,
    RedactedThinkingBlock,
    TextContent,
    ThinkingBlock,
)
from openhands.sdk.security import risk
from openhands.sdk.tool.builtins.finish import FinishAction
from openhands.sdk.tool.schema import Action


class _MessageAction(Protocol):
    @property
    def message(self) -> str: ...


def _action_declares_message(action: Action) -> bool:
    # 字段值存在于实例上，但 ``message`` 属性或类属性存在于类上。 实例 ``__dict__`` 错过
    # 了这些。
    #
    if "message" in type(action).model_fields:
        return True
    return any("message" in cls.__dict__ for cls in type(action).__mro__)


class ActionEvent(LLMConvertibleEvent):
    source: SourceType = "agent"
    thought: Sequence[TextContent] = Field(
        ..., description="The thought process of the agent before taking this action"
    )
    reasoning_content: str | None = Field(
        default=None,
        description="Intermediate reasoning/thinking content from reasoning models",
    )
    thinking_blocks: list[ThinkingBlock | RedactedThinkingBlock] = Field(
        default_factory=list,
        description="Anthropic thinking blocks from the LLM response",
    )
    responses_reasoning_item: ReasoningItemModel | None = Field(
        default=None, description="OpenAI Responses reasoning item from model output"
    )
    action: Action | None = Field(
        default=None,
        description="Single tool call returned by LLM (None when non-executable)",
    )
    tool_name: str = Field(..., description="The name of the tool being called")
    tool_call_id: ToolCallID = Field(
        ..., description="The unique id returned by LLM API for this tool call"
    )
    tool_call: MessageToolCall = Field(
        ...,
        description=(
            "The tool call received from the LLM response. We keep a copy of it "
            "so it is easier to construct it into LLM message"
            "This could be different from `action`: e.g., `tool_call` may contain "
            "`security_risk` field predicted by LLM when LLM risk analyzer is enabled"
            ", while `action` does not."
        ),
    )
    llm_response_id: EventID = Field(
        description=(
            "Completion or Response ID of the LLM response that generated this event"
            "E.g., Can be used to group related actions from same LLM response. "
            "This helps in tracking and managing results of parallel function calling "
            "from the same LLM response."
        ),
    )

    security_risk: risk.SecurityRisk = Field(
        default=risk.SecurityRisk.UNKNOWN,
        description="The LLM's assessment of the safety risk of this action.",
    )

    critic_result: CriticResult | None = Field(
        default=None,
        description="Optional critic evaluation of this action and preceding history.",
    )

    summary: str | None = Field(
        default=None,
        description=(
            "A concise summary (approximately 10 words) of what this action does, "
            "provided by the LLM for explainability and debugging. "
            "Examples of good summaries: "
            "'editing configuration file for deployment settings' | "
            "'searching codebase for authentication function definitions' | "
            "'installing required dependencies from package manifest' | "
            "'running tests to verify bug fix' | "
            "'viewing directory structure to locate source files'"
        ),
    )

    @property
    def message(self) -> str | None:
        """面向用户的消息或操作摘要（如果有）。"""
        action = self.action
        if action is None:
            return None
        if isinstance(action, FinishAction):
            return action.message
        if not _action_declares_message(action):
            return None
        message = cast(_MessageAction, action).message
        if isinstance(message, str) and message.strip():
            return message
        return None

    @property
    def visualize(self) -> Text:
        """返回此操作事件的富文本表示形式。"""
        content = Text()

        if self.security_risk != risk.SecurityRisk.UNKNOWN:
            content.append(self.security_risk.visualize)

        # 显示摘要（如果有）
        if self.summary:
            content.append("Summary: ", style="bold cyan")
            content.append(self.summary)
            content.append("\n\n")

        # 首先显示推理内容（如果有）
        if self.reasoning_content:
            content.append("Reasoning:\n", style="bold")
            content.append(self.reasoning_content)
            content.append("\n\n")

        # 显示完整的思维内容
        thought_text = " ".join([t.text for t in self.thought])
        if thought_text:
            content.append("Thought:\n", style="bold")
            content.append(thought_text)
            content.append("\n\n")

        # 响应 API 推理（仅限明文； 从不渲染 encrypted_content)
        append_visible_responses_reasoning(content, self.responses_reasoning_item)

        # 使用action的visible方法显示action信息
        if self.action:
            content.append(self.action.visualize)
        else:
            # 当action为None（不可执行）时，显示函数调用
            content.append("Function call:\n", style="bold")
            content.append(f"- {self.tool_call.name} ({self.tool_call.id})\n")

        # 显示评论家结果（如果有）
        if self.critic_result is not None:
            content.append(self.critic_result.visualize)

        return content

    def to_llm_message(self) -> Message:
        """单个消息 - 对于多操作批次可能不完整"""
        return Message(
            role="assistant",
            content=self.thought,
            tool_calls=[self.tool_call],
            reasoning_content=self.reasoning_content,
            thinking_blocks=self.thinking_blocks,
            responses_reasoning_item=self.responses_reasoning_item,
        )

    def __str__(self) -> str:
        """ActionEvent 的纯文本字符串表示形式。"""
        base_str = f"{self.__class__.__name__} ({self.source})"
        thought_text = " ".join([t.text for t in self.thought])
        thought_preview = (
            thought_text[:N_CHAR_PREVIEW] + "..."
            if len(thought_text) > N_CHAR_PREVIEW
            else thought_text
        )
        if self.action:
            action_name = self.action.__class__.__name__
            return f"{base_str}\n  Thought: {thought_preview}\n  Action: {action_name}"
        else:
            # 当action为None（不可执行）时，显示工具调用
            call = f"{self.tool_call.name}:{self.tool_call.id}"
            return (
                f"{base_str}\n  Thought: {thought_preview}\n  Action: (not executed)"
                f"\n  Call: {call}"
            )
