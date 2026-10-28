"""汤姆咨询工具定义。

该模块提供用于咨询 Tom 的工具智能体基于用户建模的个性化指导，以及为用户建模进行会话索
引。
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, override

from pydantic import Field

from openhands.sdk.io import LocalFileStore
from openhands.sdk.llm import ImageContent, TextContent
from openhands.sdk.tool import (
    Action,
    DeclaredResources,
    Observation,
    ToolDefinition,
    register_tool,
)
from openhands.sdk.utils.path import get_user_persistence_dir


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState


# ==================== 动作模式 ====================


class ConsultTomAction(Action):
    """行动请咨询 Tom 智能体以获得指导。"""

    reason: str = Field(
        description="Brief explanation of why you need Tom agent consultation"
    )
    use_user_message: bool = Field(
        default=True,
        description=(
            "Whether to consult about the user message (True) "
            "or provide custom query (False)"
        ),
    )
    custom_query: str | None = Field(
        default=None,
        description=(
            "Custom query to ask Tom agent (only used when use_user_message is False)"
        ),
    )


class SleeptimeComputeAction(Action):
    """为 Tom 的用户建模索引现有对话的操作。

    这会触发 Tom 智能体的 sleeptime_compute 函数，该函数处理对话历史记录以构建和更新
    用户模型。
    """

    pass


# ==================== 观测结果模式 ====================


class ConsultTomObservation(Observation):
    """观测结果来自 Tom 智能体咨询。"""

    suggestions: str = Field(
        default="", description="Tom agent's suggestions or guidance"
    )
    confidence: float | None = Field(
        default=None, description="Confidence score from Tom agent (0-1)"
    )
    reasoning: str | None = Field(
        default=None, description="Tom agent's reasoning for the suggestions"
    )

    @property
    @override
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        """将观测结果转换为 LLM 可读内容。"""
        if not self.suggestions:
            return [TextContent(text="Tom agent did not provide suggestions.")]

        content_parts = [f"Tom agent's guidance:\n{self.suggestions}"]

        if self.reasoning:
            content_parts.append(f"\nReasoning: {self.reasoning}")

        if self.confidence is not None:
            content_parts.append(f"\nConfidence: {self.confidence:.0%}")

        return [TextContent(text="\n".join(content_parts))]


class SleeptimeComputeObservation(Observation):
    """观测结果来自睡眠时间计算操作。"""

    message: str = Field(
        default="", description="Result message from sleeptime compute"
    )
    sessions_processed: int = Field(
        default=0, description="Number of conversation sessions indexed"
    )

    @property
    @override
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        """将观测结果转换为 LLM 可读内容。"""
        if self.sessions_processed > 0:
            text = (
                f"Successfully indexed {self.sessions_processed} "
                f"conversation(s) for user modeling.\n{self.message}"
            )
        else:
            text = f"Sleeptime compute completed.\n{self.message}"

        return [TextContent(text=text)]


# ==================== 工具说明====================

_CONSULT_DESCRIPTION = """Consult Tom agent for guidance when you need help \
understanding user intent or task requirements.

This tool allows you to consult Tom agent for personalized guidance \
based on user modeling. Use this when:
- User instructions are vague or unclear
- You need help understanding what the user actually wants
- You want guidance on the best approach for the current task
- You have your own question for Tom agent about the task or user's needs

By default, Tom agent will analyze the user's message. \
Optionally, you can ask a custom question."""

_SLEEPTIME_DESCRIPTION = """Index the current conversation for Tom's user modeling.

This tool processes conversation history to build and update the user model. \
Use this to:
- Index conversations for future personalization
- Build user preferences and patterns from conversation history
- Update Tom's understanding of the user

This is typically used at the end of a conversation or when explicitly requested."""


# ==================== 工具定义 ====================


class TomConsultTool(ToolDefinition[ConsultTomAction, ConsultTomObservation]):
    """咨询 Tom 的工具智能体。"""

    def declared_resources(self, action: Action) -> DeclaredResources:  # noqa: ARG002
        """声明并行执行的资源。

        Consulting Tom 是一个没有共享可变状态的只读 LLM 调用，因此并行运行始终是安全
        的。
        """
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    @override
    def create(
        cls,
        conv_state: "ConversationState",
        enable_rag: bool = True,
        llm_model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> Sequence[ToolDefinition[Any, Any]]:
        """使用执行器参数初始化 Tom Consult 工具。

        Args:
            conv_state: 对话状态（需要
            注册表，运行时传递的状态）
            enable_rag: 是否在Tom智能体中启用RAG
            llm_model: LLM 用于汤姆的模型智能体
            api_key: API 汤姆智能体的 LLM 的钥匙
            api_base: 汤姆智能体的 LLM 的底座 URL

        Returns:
            包含 TomConsultTool 实例的序列
        """
        # conv_state 需要注册表但未使用 - 执行时传递的状态
        _ = conv_state

        # 在此导入以避免循环导入并使 tom-swe 成为可选
        from openhands.tools.tom_consult.executor import TomConsultExecutor

        file_store = LocalFileStore(root=str(get_user_persistence_dir()))

        # 初始化执行器
        executor = TomConsultExecutor(
            file_store=file_store,
            enable_rag=enable_rag,
            llm_model=llm_model,
            api_key=api_key,
            api_base=api_base,
        )

        return [
            cls(
                description=_CONSULT_DESCRIPTION,
                action_type=ConsultTomAction,
                observation_type=ConsultTomObservation,
                executor=executor,
            )
        ]


class SleeptimeComputeTool(
    ToolDefinition[SleeptimeComputeAction, SleeptimeComputeObservation]
):
    """用于为 Tom 的用户建模建立对话索引的工具。"""

    @classmethod
    @override
    def create(
        cls,
        conv_state: "ConversationState",
        enable_rag: bool = True,
        llm_model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> Sequence[ToolDefinition[Any, Any]]:
        """使用执行器参数初始化睡眠时间计算工具。

        Args:
            conv_state: 对话状态（需要
            注册表，运行时传递的状态）
            enable_rag: 是否在Tom智能体中启用RAG
            llm_model: LLM 用于汤姆的模型智能体
            api_key: API 汤姆智能体的 LLM 的钥匙
            api_base: 汤姆智能体的 LLM 的底座 URL

        Returns:
            包含 SleeptimeComputeTool 实例的序列
        """
        # conv_state 需要注册表但未使用 - 执行时传递的状态
        _ = conv_state

        # 在此导入以避免循环导入并使 tom-swe 成为可选
        from openhands.tools.tom_consult.executor import TomConsultExecutor

        file_store = LocalFileStore(root=str(get_user_persistence_dir()))

        # 初始化执行器
        executor = TomConsultExecutor(
            file_store=file_store,
            enable_rag=enable_rag,
            llm_model=llm_model,
            api_key=api_key,
            api_base=api_base,
        )

        return [
            cls(
                description=_SLEEPTIME_DESCRIPTION,
                action_type=SleeptimeComputeAction,
                observation_type=SleeptimeComputeObservation,
                executor=executor,
            )
        ]


# 导入此模块时自动注册工具
register_tool(TomConsultTool.name, TomConsultTool)
register_tool(SleeptimeComputeTool.name, SleeptimeComputeTool)
