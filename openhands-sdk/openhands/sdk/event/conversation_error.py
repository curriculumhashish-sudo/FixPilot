from pydantic import Field, model_validator
from rich.text import Text

from openhands.sdk.event.base import Event
from openhands.sdk.event.error_classification import (
    ErrorClassification,
    classify_error,
)


class ConversationErrorEvent(Event):
    """
    会话级失败即被不发送回LLM。

    当出现意外异常并阻止运行循环继续时，对话运行时会发出此事件。 它旨在供客户端应用程
    序（e.g.、UI）呈现顶级错误状态，并供编排做出反应。 它不是观测结果，也不是
    LLM 可转换的。

    与AgentErrorEvent的区别：
    - 不依赖于任何 tool_name/tool_call_id（AgentErrorEvent 是工具观测结果）。
    - 通常 source='environment' 并且运行循环移动到 ERROR 状态，
      while AgentErrorEvent has source='agent' and the conversation can
      continue.
    """

    code: str = Field(description="Code for the error - typically a type")
    detail: str = Field(description="Details about the error")
    classification: ErrorClassification | None = Field(
        default=None,
        description="Safe structured error semantics for API consumers.",
    )

    @model_validator(mode="after")
    def classify(self) -> "ConversationErrorEvent":
        if self.classification is None:
            object.__setattr__(
                self, "classification", classify_error(self.code, self.detail)
            )
        return self

    @property
    def visualize(self) -> Text:
        """返回此对话错误事件的富文本表示形式。"""
        content = Text()
        content.append("Conversation Error\n", style="bold")
        content.append("Code: ", style="bold")
        content.append(self.code)
        content.append("\n\nDetail:\n", style="bold")
        content.append(self.detail)
        return content
