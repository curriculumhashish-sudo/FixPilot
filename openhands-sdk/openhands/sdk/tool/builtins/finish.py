from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar, Self

from pydantic import Field
from rich.text import Text

from openhands.sdk.tool.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)


if TYPE_CHECKING:
    from openhands.sdk.conversation.base import BaseConversation
    from openhands.sdk.conversation.state import ConversationState


class FinishAction(Action):
    message: str = Field(description="Final message to send to the user.")

    @property
    def visualize(self) -> Text:
        """返回此操作的富文本表示形式。"""
        content = Text()
        content.append("Finish with message:\n", style="bold blue")
        content.append(self.message)
        return content


class FinishObservation(Observation):
    """
    观测结果完成任务后返回。 FinishAction 本身包含发送给用户的消息，因此这里不需要额
    外的字段。
    """

    @property
    def visualize(self) -> Text:
        """由于消息位于操作中，因此返回空文本表示形式。"""
        return Text()


TOOL_DESCRIPTION = """Signals the completion of the current task or conversation.

Use this tool when:
- You have successfully completed the user's requested task
- You cannot proceed further due to technical limitations or missing information

The message should include:
- A clear summary of actions taken and their results
- Any next steps for the user
- Explanation if you're unable to complete the task
- Any follow-up questions if more information is needed
"""


class FinishExecutor(ToolExecutor):
    def __call__(
        self,
        action: FinishAction,
        conversation: "BaseConversation | None" = None,  # noqa: ARG002
    ) -> FinishObservation:
        return FinishObservation.from_text(text=action.message)


class FinishTool(ToolDefinition[FinishAction, FinishObservation]):
    """用于发出任务或对话完成信号的工具。"""

    user_selectable: ClassVar[bool] = False

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,  # noqa: ARG003
        **params,
    ) -> Sequence[Self]:
        """创建 FinishTool 实例。

        Args:
            conv_state: 可选的对话状态（FinishTool未使用）。
            **params: 附加参数（支持 None）。

        Returns:
            包含单个 FinishTool 实例的序列。

        Raises:
            ValueError: 如果提供任何参数。
        """
        if params:
            raise ValueError("FinishTool doesn't accept parameters")
        return [
            cls(
                action_type=FinishAction,
                observation_type=FinishObservation,
                description=TOOL_DESCRIPTION,
                executor=FinishExecutor(),
                annotations=ToolAnnotations(
                    title="finish",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
        ]
