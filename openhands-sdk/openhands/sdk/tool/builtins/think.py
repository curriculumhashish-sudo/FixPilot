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


class ThinkAction(Action):
    """用于记录想法而不进行任何更改的操作。"""

    thought: str = Field(description="The thought to log.")

    @property
    def visualize(self) -> Text:
        """返回带有思考样式的富文本表示。"""
        content = Text()

        # 添加思考图标和标题
        content.append("🤔 ", style="yellow")
        content.append("Thinking: ", style="bold yellow")

        # 添加正确格式的思想内容
        if self.thought:
            # 分成几行以便更好地格式化
            lines = self.thought.split("\n")
            for i, line in enumerate(lines):
                if i > 0:
                    content.append("\n")
                content.append(line.strip(), style="italic white")

        return content


class ThinkObservation(Observation):
    """
    观测结果记录想法后返回。 ThinkAction 本身包含记录的想法，因此这里不需要额外的字段
    。
    """

    @property
    def visualize(self) -> Text:
        """返回一个空的文本表示，因为思想在行动中。"""
        return Text()


THINK_DESCRIPTION = """Use the tool to think about something. It will not obtain new information or make any changes to the repository, but just log the thought. Use it when complex reasoning or brainstorming is needed.

Common use cases:
1. When exploring a repository and discovering the source of a bug, call this tool to brainstorm several unique ways of fixing the bug, and assess which change(s) are likely to be simplest and most effective.
2. After receiving test results, use this tool to brainstorm ways to fix failing tests.
3. When planning a complex refactoring, use this tool to outline different approaches and their tradeoffs.
4. When designing a new feature, use this tool to think through architecture decisions and implementation details.
5. When debugging a complex issue, use this tool to organize your thoughts and hypotheses.

The tool simply logs your thought process for better transparency and does not execute any code or make changes."""  # noqa: E501


class ThinkExecutor(ToolExecutor):
    def __call__(
        self,
        _: ThinkAction,
        conversation: "BaseConversation | None" = None,  # noqa: ARG002
    ) -> ThinkObservation:
        return ThinkObservation.from_text(text="Your thought has been logged.")


class ThinkTool(ToolDefinition[ThinkAction, ThinkObservation]):
    """用于记录想法而不进行更改的工具。"""

    user_selectable: ClassVar[bool] = False

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,  # noqa: ARG003
        **params,
    ) -> Sequence[Self]:
        """创建 ThinkTool 实例。

        Args:
            conv_state: 可选的对话状态（ThinkTool未使用）。
            **params: 附加参数（支持 None）。

        Returns:
            包含单个 ThinkTool 实例的序列。

        Raises:
            ValueError: 如果提供任何参数。
        """
        if params:
            raise ValueError("ThinkTool doesn't accept parameters")
        return [
            cls(
                description=THINK_DESCRIPTION,
                action_type=ThinkAction,
                observation_type=ThinkObservation,
                executor=ThinkExecutor(),
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
        ]
