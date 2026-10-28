"""ask_oracle 工具的操作、观测结果和工具定义。"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar, Final, Self

from pydantic import Field
from rich.text import Text

from openhands.sdk.tool.registry import register_tool
from openhands.sdk.tool.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
)


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState


# Oracle 模型是一个已保存的 LLM 配置文件，按惯例以该名称解析。 保存名为“oracle”的配置文
# 件 (e.g. 通过 LLMProfileStore.save("oracle", llm)) 并且该工具将查阅它。 无需智能体设置
# 或接线。
#
ORACLE_PROFILE_NAME: Final[str] = "oracle"


class AskOracleAction(Action):
    """向 Oracle 寻求建议的行动。"""

    question: str = Field(
        description=(
            "The specific question or dilemma to ask the Oracle about. Use this "
            "when you are stuck, uncertain, or need a second opinion."
        )
    )
    context: str | None = Field(
        default=None,
        description=(
            "Optional extra context, such as approaches already tried, constraints, "
            "or the recommendation you are considering."
        ),
    )

    @property
    def visualize(self) -> Text:
        content = Text()
        content.append("Ask Oracle: ", style="bold cyan")
        content.append(self.question)
        if self.context:
            content.append("\nContext: ", style="bold")
            content.append(self.context)
        return content


class AskOracleObservation(Observation):
    """观测结果由Oracle协商返回。"""

    @property
    def visualize(self) -> Text:
        content = Text()
        if self.is_error:
            content.append("Oracle consultation failed", style="bold red")
        else:
            content.append("Oracle recommendation", style="bold green")
        if self.text:
            content.append("\n")
            content.append(self.text)
        return content


_DESCRIPTION = (
    "Ask the Oracle for a second opinion. The Oracle is a smart model intended "
    "to help with difficult reasoning.\n\n"
    "Use this when you are stuck, uncertain, comparing approaches, or need a "
    "higher-quality recommendation before proceeding.\n\n"
    "Treat the Oracle's response as strong guidance and follow its recommendation "
    "unless you have a clear reason not to."
)


class AskOracleTool(ToolDefinition[AskOracleAction, AskOracleObservation]):
    """用于咨询 Oracle 的工具（名为“oracle”的已保存 LLM 配置文件）。"""

    user_selectable: ClassVar[bool] = False

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,  # noqa: ARG003
        **params,
    ) -> Sequence[Self]:
        if params:
            raise ValueError("AskOracleTool does not accept parameters")

        # 在此导入以保持模块导入轻量并避免任何导入周期。
        from openhands.tools.ask_oracle.impl import AskOracleExecutor

        return [
            cls(
                description=_DESCRIPTION,
                action_type=AskOracleAction,
                observation_type=AskOracleObservation,
                executor=AskOracleExecutor(),
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            )
        ]


# 导入该模块时自动注册。
register_tool(AskOracleTool.name, AskOracleTool)
