"""清理配置文件：在人类读取智能体的外部文本之前对其进行修复。

智能体的推理可以正确，而消息的*表面*可能被破坏——由于未编码的emoji错误、意外的控制字符
或目标渠道的不一致格式。 大推理模型不应该每次都监控自己的输出。

该模块运行智能体的外文本并通过一个保存的小型LLM配置文件——根据约定以``cleanup`` (:data
:`CLEANUP_PROFILE_NAME`)的形式返回——修
复文本。 它反映了 ``ask_oracle`` 模式：无智能体设置且无接线； 呼叫者保存名为
``cleanup`` 的配置文件并呼叫
:func:`clean_outward_text` （或异步：func:`aclean_outward_text`）。

通道故意狭窄：

- 它仅在面向人的外部文本上运行。 调用者不得在内部智能体或工具消息上使用它。
- 它是无状态的：仅发送清理系统提示词和草稿，没有对话历史记录，也没有工具。 活动对话
LLM 永远不会切换。
- 它仅修复表面。 提示词禁止添加事实、链接或承诺； 它一定不能改变意义。
- 打开失败。 如果不存在 ``cleanup`` 配置文件，或者调用错误，则原样返回原始文本。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from openhands.sdk.llm.llm import LLM
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.llm.llm_response import LLMResponse
from openhands.sdk.llm.message import Message, TextContent
from openhands.sdk.logger import get_logger


if TYPE_CHECKING:
    from openhands.sdk.utils.cipher import Cipher


logger = get_logger(__name__)

# 清理模型是一个已保存的 LLM 配置文件，按惯例以该名称解析。 保存名为“cleanup”的配置文件
# (e.g. via LLMProfileStore.save("cleanup", llm)) 并且外向路径上的调用者将查阅它。 无需
# 智能体设置或接线。
#
CLEANUP_PROFILE_NAME: Final[str] = "cleanup"

_CLEANUP_SYSTEM_PROMPT = """\
You repair the surface of a message that an AI agent is about to send to a \
human. Fix only the presentation.

Rules:
- Fix mojibake, broken encoding, and stray control characters.
- Keep the meaning exactly. Do not add facts, links, numbers, or promises.
- Do not remove real content. Do not answer or continue the message.
- Keep the author's tone and any intentional formatting.
- Return only the repaired message text, with nothing added around it."""

_CLEANUP_USER_PROMPT_TEMPLATE = """\
Repair this message and return only the repaired text:

{text}"""


def _load_cleanup_llm(cipher: Cipher | None) -> LLM | None:
    """加载 ``cleanup`` 配置文件，或在清理不可用时加载 ``None``。

    退货 ``None`` (功能关闭/失败打开) 当无 ``cleanup`` 如果 profile 保存成功或无法加
    载 profile，那么调用者可以将原始文本原样
    传递。
    """
    try:
        return LLMProfileStore().load(CLEANUP_PROFILE_NAME, cipher=cipher)
    except FileNotFoundError:
        # 未配置清理配置文件：功能完全关闭。
        return None
    except Exception as exc:
        logger.warning("Cleanup profile could not be loaded: %s", exc)
        return None


def _cleanup_messages(text: str) -> list[Message]:
    return [
        Message(role="system", content=[TextContent(text=_CLEANUP_SYSTEM_PROMPT)]),
        Message(
            role="user",
            content=[TextContent(text=_CLEANUP_USER_PROMPT_TEMPLATE.format(text=text))],
        ),
    ]


def _repaired_or_original(response: LLMResponse, text: str) -> str:
    cleaned = "".join(
        content.text
        for content in response.message.content
        if isinstance(content, TextContent)
    ).strip()
    # 空回复意味着清理模型没有给我们任何可用的东西； 保留原件而不是发送空白消息。
    #
    return cleaned or text


def clean_outward_text(text: str, *, cipher: Cipher | None = None) -> str:
    """返回由 ``cleanup`` LLM 配置文件修复的 ``text``，或保持不变。

    从默认：class:`LLMProfileStore` 解析名为：data:`CLEANUP_PROFILE_NAME` 的已保存配
    置文件，并运行单个无状态完成来修
    复消息表面。 这是开环失败：如果配置缺失或调用失败，原始 ``text`` 会原样返回，以防
    止清理问题阻止或损坏外发消息。

    Args:
        text: 智能体向外的、面向人的草稿。 不要通过内部
            智能体或工具消息。
        cipher: 用于在 REST 处解密配置文件的机密的可选密码。

    Returns:
        修复后的文本，或原始文本 ``text`` 当清理不可用或失败，或当 ``text`` 是空的。
    """
    if not text.strip():
        return text

    cleanup_llm = _load_cleanup_llm(cipher)
    if cleanup_llm is None:
        return text

    try:
        response = cleanup_llm.generate(messages=_cleanup_messages(text), store=False)
    except Exception as exc:
        logger.warning("Cleanup profile call failed; sending original text: %s", exc)
        return text

    return _repaired_or_original(response, text)


async def aclean_outward_text(text: str, *, cipher: Cipher | None = None) -> str:
    """异步：func:`clean_outward_text` 的变体。

    相同的故障开放合约，用于异步向外路径 (e.g. 智能体-服务器出站表面）。 详细信息请参
    见：func:`clean_outward_text`。
    """
    if not text.strip():
        return text

    cleanup_llm = _load_cleanup_llm(cipher)
    if cleanup_llm is None:
        return text

    try:
        response = await cleanup_llm.agenerate(
            messages=_cleanup_messages(text), store=False
        )
    except Exception as exc:
        logger.warning("Cleanup profile call failed; sending original text: %s", exc)
        return text

    return _repaired_or_original(response, text)
