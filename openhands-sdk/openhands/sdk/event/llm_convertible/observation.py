from typing import Literal

from pydantic import Field, model_validator
from rich.text import Text

from openhands.sdk.event.base import N_CHAR_PREVIEW, LLMConvertibleEvent
from openhands.sdk.event.error_classification import ErrorClassification, FailureKind
from openhands.sdk.event.types import EventID, SourceType, ToolCallID
from openhands.sdk.llm import Message, TextContent, content_to_str
from openhands.sdk.tool.schema import Observation


# 动作拒绝的来源 - 用于区分用户拒绝和钩子块
RejectionSource = Literal["user", "hook"]


class ObservationBaseEvent(LLMConvertibleEvent):
    """作为对工具调用响应的任何内容的基类。

    示例包括工具执行、错误、用户拒绝。
    """

    source: SourceType = "environment"
    tool_name: str = Field(
        ..., description="The tool name that this observation is responding to"
    )
    tool_call_id: ToolCallID = Field(
        ..., description="The tool call id that this observation is responding to"
    )


class ObservationEvent(ObservationBaseEvent):
    observation: Observation = Field(
        ..., description="The observation (tool call) sent to LLM"
    )
    action_id: EventID = Field(
        ..., description="The action id that this observation is responding to"
    )
    extended_content: list[TextContent] = Field(
        default_factory=list,
        description=(
            "Content added by agent context (e.g. path-scoped rules triggered "
            "by the touched file), appended after the tool result in to_llm_message."
        ),
    )

    @property
    def visualize(self) -> Text:
        """返回此观测结果事件的富文本表示。"""
        to_viz = self.observation.visualize
        content = Text()
        if to_viz.plain.strip():
            content.append("Tool: ", style="bold")
            content.append(self.tool_name)
            content.append("\nResult:\n", style="bold")
            content.append(to_viz)
        # 表面智能体-上下文注射 (e.g. 路径范围的规则）与 MessageEvent 奇偶校验，因此在调
        # 试时触发的规则是可见的。
        #
        if self.extended_content:
            content.append(
                "\n\nPrompt Extension based on Agent Context:\n", style="bold"
            )
            content.append(" ".join(content_to_str(self.extended_content)))
        return content

    def to_llm_message(self) -> Message:
        return Message(
            role="tool",
            content=list(self.observation.to_llm_content) + list(self.extended_content),
            name=self.tool_name,
            tool_call_id=self.tool_call_id,
        )

    def __str__(self) -> str:
        """ObservationEvent 的纯文本字符串表示形式。"""
        base_str = f"{self.__class__.__name__} ({self.source})"
        content_str = "".join(content_to_str(self.observation.to_llm_content))
        obs_preview = (
            content_str[:N_CHAR_PREVIEW] + "..."
            if len(content_str) > N_CHAR_PREVIEW
            else content_str
        )
        return f"{base_str}\n  Tool: {self.tool_name}\n  Result: {obs_preview}"


class UserRejectObservation(ObservationBaseEvent):
    """观测结果当操作被用户或挂钩拒绝时。

    该事件在以下情况下发出：
    - 用户在确认模式期间拒绝操作 (rejection_source="user")
    - PreToolUse 钩子阻止操作 (rejection_source="hook")
    """

    rejection_reason: str = Field(
        default="User rejected the action",
        description="Reason for rejecting the action",
    )
    rejection_source: RejectionSource = Field(
        default="user",
        description=(
            "Source of the rejection: 'user' for confirmation mode rejections, "
            "'hook' for PreToolUse hook blocks"
        ),
    )
    action_id: EventID = Field(
        ..., description="The action id that this observation is responding to"
    )

    @property
    def visualize(self) -> Text:
        """返回此用户拒绝事件的富文本表示形式。"""
        content = Text()
        content.append("Tool: ", style="bold")
        content.append(self.tool_name)
        content.append("\n\nRejection Reason:\n", style="bold")
        content.append(self.rejection_reason)
        return content

    def to_llm_message(self) -> Message:
        return Message(
            role="tool",
            content=[TextContent(text=f"Action rejected: {self.rejection_reason}")],
            name=self.tool_name,
            tool_call_id=self.tool_call_id,
        )

    def __str__(self) -> str:
        """UserRejectObservation 的纯文本字符串表示形式。"""
        base_str = f"{self.__class__.__name__} ({self.source})"
        reason_preview = (
            self.rejection_reason[:N_CHAR_PREVIEW] + "..."
            if len(self.rejection_reason) > N_CHAR_PREVIEW
            else self.rejection_reason
        )
        return f"{base_str}\n  Tool: {self.tool_name}\n  Reason: {reason_preview}"


class AgentErrorEvent(ObservationBaseEvent):
    """由智能体触发的错误。

    Note: 此事件不应包含模型“想法”或“reasoning_content”。 它
    表示由代理/支架产生的错误，而不是模型输出。
    """

    source: SourceType = "agent"
    error: str = Field(..., description="The error message from the scaffold")
    classification: ErrorClassification | None = Field(
        default=None,
        description="Safe structured error semantics for API consumers.",
    )

    @model_validator(mode="after")
    def classify(self) -> "AgentErrorEvent":
        """当生产者未提供分类时默认为 UNKNOWN。

        ``AgentErrorEvent``描述*哪里*出现错误（智能体脚手架），而不是*为什么*发生错误
        。 知道错误是预期的、智能体-可纠正的验证失败的生产者显
        式地通过``AGENT_ACTION``； 意外异常和崩溃恢复路径保留默认值，因此遥测将它们视
        为诊断。
        """
        if self.classification is None:
            object.__setattr__(
                self,
                "classification",
                ErrorClassification(kind=FailureKind.UNKNOWN, retryable=False),
            )
        return self

    @property
    def visualize(self) -> Text:
        """返回此智能体错误事件的富文本表示形式。"""
        content = Text()
        content.append("Error Details:\n", style="bold")
        content.append(self.error)
        return content

    def to_llm_message(self) -> Message:
        # 提供纯字符串错误内容； 序列化器处理聊天与响应。 对于ResponsesAPI，输出是一个字
        # 符串； JSON 不是必需的。
        #
        return Message(
            role="tool",
            content=[TextContent(text=self.error)],
            name=self.tool_name,
            tool_call_id=self.tool_call_id,
        )

    def __str__(self) -> str:
        """AgentErrorEvent 的纯文本字符串表示形式。"""
        base_str = f"{self.__class__.__name__} ({self.source})"
        error_preview = (
            self.error[:N_CHAR_PREVIEW] + "..."
            if len(self.error) > N_CHAR_PREVIEW
            else self.error
        )
        return f"{base_str}\n  Error: {error_preview}"
