"""ask_oracle 工具的执行器。"""

from typing import TYPE_CHECKING

from openhands.sdk.llm import Message, TextContent
from openhands.sdk.tool.tool import ToolExecutor
from openhands.tools.ask_oracle.definition import (
    ORACLE_PROFILE_NAME,
    AskOracleAction,
    AskOracleObservation,
)


if TYPE_CHECKING:
    from openhands.sdk.conversation.impl.local_conversation import LocalConversation


ORACLE_USAGE_PREFIX = "oracle"


_ORACLE_SYSTEM_PROMPT = """\
You are the Oracle: a highly capable reviewer giving a second opinion to an \
OpenHands agent.

Answer the agent's question directly. Do not call tools. Do not perform work \
directly. Give a concrete recommendation the agent can follow, including important \
risks or caveats."""

_ORACLE_USER_PROMPT_TEMPLATE = """\
Question:
{question}
{context_section}"""


class AskOracleExecutor(ToolExecutor[AskOracleAction, AskOracleObservation]):
    """咨询 Oracle：名为 ``oracle`` 的已保存 LLM 配置。

    按照惯例，Oracle 是从会话的 LLM 配置文件存储中以名称 ``oracle`` (
    ``ORACLE_PROFILE_NAME``) 解析的。 通话内容是
    stateless: 它仅发送 Oracle 系统提示词以及智能体的问题
    和可选的上下文，没有对话历史记录和工具，并返回 Oracle 的文本。 活动对话 LLM 永远
    不会切换。
    """

    def __call__(
        self,
        action: AskOracleAction,
        conversation: "LocalConversation | None" = None,
    ) -> AskOracleObservation:
        if conversation is None:
            return AskOracleObservation.from_text(
                text="Cannot ask the Oracle without an active conversation.",
                is_error=True,
            )

        try:
            oracle_llm = conversation.get_or_create_profile_llm(
                profile_name=ORACLE_PROFILE_NAME,
                usage_id=f"{ORACLE_USAGE_PREFIX}:{ORACLE_PROFILE_NAME}",
            )
        except FileNotFoundError:
            return AskOracleObservation.from_text(
                text=(
                    "The Oracle is not available because no profile named "
                    f"'{ORACLE_PROFILE_NAME}' was found. Save one to enable it."
                ),
                is_error=True,
            )
        except ValueError as exc:
            return AskOracleObservation.from_text(
                text=f"The Oracle is not available: {exc}",
                is_error=True,
            )
        except Exception as exc:
            return AskOracleObservation.from_text(
                text=f"The Oracle is not available: {type(exc).__name__}: {exc}",
                is_error=True,
            )

        context_section = (
            f"\nAdditional context from the agent:\n{action.context}\n"
            if action.context
            else ""
        )
        user_prompt = _ORACLE_USER_PROMPT_TEMPLATE.format(
            question=action.question,
            context_section=context_section,
        )
        messages = [
            Message(
                role="system",
                content=[TextContent(text=_ORACLE_SYSTEM_PROMPT)],
            ),
            Message(role="user", content=[TextContent(text=user_prompt)]),
        ]

        try:
            llm_response = oracle_llm.generate(messages=messages, store=False)
        except Exception as exc:
            return AskOracleObservation.from_text(
                text=(
                    "The Oracle encountered an error and did not return a "
                    f"response: {type(exc).__name__}: {exc}"
                ),
                is_error=True,
            )

        oracle_text = "".join(
            content.text
            for content in llm_response.message.content
            if isinstance(content, TextContent)
        ).strip()
        if not oracle_text:
            return AskOracleObservation.from_text(
                text="The Oracle did not return a response.",
                is_error=True,
            )

        return AskOracleObservation.from_text(text=oracle_text)
