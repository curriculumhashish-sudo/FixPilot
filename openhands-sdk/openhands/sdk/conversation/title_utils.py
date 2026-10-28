"""用于生成对话标题的实用函数。"""

import re
from collections.abc import Callable, Sequence
from typing import Final

from openhands.sdk.event import MessageEvent
from openhands.sdk.event.base import Event
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.llm.call_context import LLMCallContext
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


categories = [
    {"emoji": "💄", "name": "frontend", "description": "UI and style files"},
    {"emoji": "👔", "name": "backend", "description": "Business logic"},
    {"emoji": "✅", "name": "test", "description": "Tests"},
    {"emoji": "👷", "name": "devops", "description": "CI build system"},
    {"emoji": "🚀", "name": "deployment", "description": "Deploy stuff"},
    {"emoji": "📦️", "name": "dependencies", "description": "Packages and dependencies"},
    {"emoji": "🗃️", "name": "database", "description": "Database changes"},
    {"emoji": "🔧", "name": "chores", "description": "Configuration and maintenance"},
    {"emoji": "✨", "name": "features", "description": "New features"},
    {"emoji": "🐛", "name": "bugfix", "description": "Bug fixes"},
    {"emoji": "⚡️", "name": "performance", "description": "Performance improvements"},
    {"emoji": "🔒️", "name": "security", "description": "Security fixes"},
    {"emoji": "📝", "name": "documentation", "description": "Documentation"},
    {"emoji": "♻️", "name": "refactor", "description": "Code refactoring"},
]

CONVERSATION_CONTENT_PLACEHOLDER: Final[str] = "{conversation_content}"
MAX_LENGTH_PLACEHOLDER: Final[str] = "{max_length}"


def extract_message_text(event: MessageEvent) -> str | None:
    """从消息事件中提取纯文本内容。"""
    if not event.llm_message.content:
        return None

    text_parts = []
    for content in event.llm_message.content:
        if isinstance(content, TextContent):
            text_parts.append(content.text)

    return " ".join(text_parts).strip() or None


def extract_first_user_message(events: Sequence[Event]) -> str | None:
    """从对话事件中提取第一条用户消息。

    Args:
        events: 对话事件列表。

    Returns:
        第一个用户消息文本，如果未找到用户消息，则为 None。
    """
    for event in events:
        if isinstance(event, MessageEvent) and event.source == "user":
            if text := extract_message_text(event):
                return text

    return None


_REASONING_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_UNCLOSED_REASONING = re.compile(r"<think>.*", re.DOTALL | re.IGNORECASE)


def strip_reasoning_blocks(text: str) -> str:
    """从模型文本中删除内联 ``<think>`` 推理。

    不将思想链拆分为 ``reasoning_content`` 的提供者将其内联返回到 ``content`` 中。 未
    终止的块意味着响应在思考过程中被切断，因此从开
    始标签开始的所有内容也是推理。
    """
    text = _REASONING_BLOCK.sub("", text)
    return _UNCLOSED_REASONING.sub("", text)


def generate_title_with_llm(
    message: str,
    llm: LLM,
    max_length: int = 50,
    *,
    call_context: LLMCallContext | None = None,
    on_error: Callable[[Exception], None] | None = None,
    prompt: str | None = None,
) -> str | None:
    """使用 LLM 生成对话标题。

    Args:
        message: 用于生成标题的第一条用户消息。
        llm: 用于标题生成的 LLM。
        max_length: 生成的标题的最大长度。
        on_error: 可选回调调用，但 LLM 时除外
            呼叫失败。 标题生成仍然会回落（返回None）； 回调让调用者能够发现否则会被
            吞掉的错误。
        prompt: 可选的用户消息提示词覆盖。 的
            ``{conversation_content}`` 和 ``{max_length}`` 占位符存在时将被替换。 如
            果省略对话占位符，则会自动附加
            消息内容。

    Returns:
        生成的标题，如果 LLM 失败或返回空响应，则为 None。
    """
    # 截断很长的消息以避免过多的词元用量
    if len(message) > 1000:
        truncated_message = message[:1000] + "...(truncated)"
    else:
        truncated_message = message

    emojis_descriptions = "\n- ".join(
        f"{c['emoji']} {c['name']}: {c['description']}" for c in categories
    )

    template = (prompt or "").strip()
    if template:
        user_prompt = template.replace(
            CONVERSATION_CONTENT_PLACEHOLDER, truncated_message
        ).replace(MAX_LENGTH_PLACEHOLDER, str(max_length))
        if CONVERSATION_CONTENT_PLACEHOLDER not in template:
            user_prompt = f"{user_prompt}\n\nConversation content:\n{truncated_message}"
    else:
        user_prompt = (
            f"Generate a title (maximum {max_length} characters) "
            f"for a conversation that starts with this message:\n\n"
            f"{truncated_message}."
            "Also make sure to include ONE most relevant emoji at "
            "the start of the title."
            f" Choose the emoji from this list:{emojis_descriptions} "
        )

    try:
        # 为LLM创建消息以生成标题
        messages = [
            Message(
                role="system",
                content=[
                    TextContent(
                        text=(
                            "You are a helpful assistant that generates concise, "
                            "descriptive titles for conversations with OpenHands. "
                            "OpenHands is a helpful AI agent that can interact "
                            "with a computer to solve tasks using bash terminal, "
                            "file editor, and browser. Given a user message "
                            "(which may be truncated), generate a concise, "
                            "descriptive title for the conversation. Return only "
                            "the title, with no additional text, quotes, or "
                            "explanations."
                        )
                    )
                ],
            ),
            Message(
                role="user",
                content=[TextContent(text=user_prompt)],
            ),
        ]

        response = llm.generate(
            messages,
            store=False,
            call_context=call_context,
        )

        # 从响应中提取标题
        if response.message.content and isinstance(
            response.message.content[0], TextContent
        ):
            title = strip_reasoning_blocks(response.message.content[0].text).strip()

            if not title:
                logger.warning(
                    "LLM returned only reasoning content for title generation"
                )
                return None

            # 确保标题不要太长
            if len(title) > max_length:
                title = title[: max_length - 3] + "..."

            return title
        else:
            logger.warning("LLM returned empty response for title generation")
            return None

    except Exception as e:
        logger.warning(f"Error generating conversation title with LLM: {e}")
        # 非致命（我们回退到截断），但让调用者向 UI 显示原本不可见的 LLM 错误（问题＃
        # 16686）。
        #
        if on_error is not None:
            on_error(e)
        return None


def generate_fallback_title(message: str, max_length: int = 50) -> str:
    """通过截断第一条用户消息生成回退方案标题。

    Args:
        message: 第一条用户消息。
        max_length: 标题的最大长度。

    Returns:
        一个被截断的标题。
    """
    title = message.strip()
    if len(title) > max_length:
        title = title[: max_length - 3] + "..."
    return title


def generate_title_from_message(
    message: str,
    llm: LLM | None = None,
    max_length: int = 50,
    *,
    call_context: LLMCallContext | None = None,
    on_error: Callable[[Exception], None] | None = None,
    prompt: str | None = None,
) -> str:
    """从已提取的用户消息生成标题。"""
    # 跳过ACP哨兵值LLM——它没有凭据，不能被调用。 通过``usage_id``检测到，因此真实的模型
    # 名称仍然可以出现在日志和已序列化状态中。
    #
    llm_to_use = None if llm and llm.usage_id == "acp-managed" else llm

    if llm_to_use:
        llm_title = generate_title_with_llm(
            message,
            llm_to_use,
            max_length,
            call_context=call_context,
            on_error=on_error,
            prompt=prompt,
        )
        if llm_title:
            return llm_title

    return generate_fallback_title(message, max_length)


def generate_conversation_title(
    events: Sequence[Event],
    llm: LLM | None = None,
    max_length: int = 50,
    *,
    call_context: LLMCallContext | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> str:
    """根据第一条用户消息生成对话标题。

    这是协调标题生成过程的主要实用函数：
    1. 从事件中提取第一条用户消息
    2. 尝试使用 LLM 生成标题
    3. 如果 LLM 失败，则退回到简单截断

    Args:
        events: 对话事件列表。
        llm: 可选 LLM 用于标题生成。
        max_length: 生成的标题的最大长度。

    Returns:
        为对话生成的标题。

    Raises:
        ValueError: 如果在对话事件中没有找到用户消息。
    """
    # 查找事件中的第一条用户消息
    first_user_message = extract_first_user_message(events)

    if not first_user_message:
        raise ValueError("No user messages found in conversation events")

    return generate_title_from_message(
        first_user_message,
        llm,
        max_length,
        call_context=call_context,
        on_error=on_error,
    )
