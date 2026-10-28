"""将 SDK 事件渲染为恢复引导记录。

当 ACP 支持的对话必须重新启动但 ACP 服务器自己的会话存储已被擦除时 (e.g. 沙箱被回收）
，
``session/load``恢复路径不可用：服务器没有我们已持久化的会话ID记录。 一种解决方法是开
始一个新的
``new_session`` 并重播 SDK 的持久事件历史记录作为打开用户消息 — “bootstrap-提示词恢复
”。

该模块提供渲染原语。 调用者决定事件来自哪里（持久事件存储、内存中状态……）、如何打包渲
染的字符串（e.g. 作为``SendMessageRequest``），以及对结果
应用哪些特定于提供者的后处理（路径清理、输出清理等）。

伴随 ``RESUME_CONTEXT_MARKER`` 常量被导出，因此生产者和消费者都可以检测到已经恢复的消
息，而无需对字符串进行硬编码。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from openhands.sdk.event.acp_tool_call import ACPToolCallEvent, _block_field
from openhands.sdk.event.base import Event
from openhands.sdk.event.llm_convertible import ActionEvent, MessageEvent
from openhands.sdk.llm import content_to_str


RESUME_CONTEXT_MARKER = "<<RESUMED CONVERSATION>>"
"""为每个引导恢复记录添加前缀的标头标记。

生产者（渲染器）和消费者（需要检测已恢复的消息并避免双包裹的调用者）都引用了这个常量
，因此合同是单源的。
"""

DEFAULT_HEADER_BODY = (
    "The conversation history below is from a prior session whose live "
    "context was lost. Treat it as background and continue from where "
    "the previous session left off."
)
DEFAULT_FOOTER = "--- End of prior session ---"

DEFAULT_MAX_CHARS = 60_000
DEFAULT_MAX_MESSAGE_CHARS = 8_000
DEFAULT_MAX_TOOL_CHARS = 2_000

_HEAD_ELLIPSIS = "...\n"
_TAIL_ELLIPSIS = "..."


def _truncate_keep_head(text: str, max_chars: int) -> str:
    """将 ``text`` 截断至最多 ``max_chars`` 个字符，保留开头。

    严格遵守任何非负 ``max_chars``：``max_chars=0`` 收益率
    ``""``，并且低于 4 的值会生成普通切片（没有省略号标记的空间）。 用于每条消息和每
    工具块的上限，其中开放内容（问题、命令、文件路径）才是重要的。
    """
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars < len(_TAIL_ELLIPSIS) + 1:
        return text[:max_chars]
    return text[: max_chars - len(_TAIL_ELLIPSIS)] + _TAIL_ELLIPSIS


def _truncate_keep_tail(text: str, max_chars: int) -> str:
    """将 ``text`` 截断至最多 ``max_chars`` 个字符，保留结尾。

    严格遵守任何非负 ``max_chars``。 用于当完整历史不适用时，用于简历正文。 上下文最
    新鲜的事件对智能体重新开始最有用，因此我们先丢掉最旧的内容。
    """
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars < len(_HEAD_ELLIPSIS) + 1:
        return text[-max_chars:]
    return _HEAD_ELLIPSIS + text[-(max_chars - len(_HEAD_ELLIPSIS)) :]


def _render_message_event(event: MessageEvent, max_chars: int) -> str | None:
    role_label = "[USER]" if event.llm_message.role == "user" else "[ASSISTANT]"
    # ``to_llm_message`` 折叠 ``extended_content``（AgentContext / 每转提供的钩子上下文
    # ）为 ``content`` — 正是原始 LLM 所看到的。 单独阅读``llm_message.content``会默默地
    # 放弃上下文。
    #
    message = event.to_llm_message()
    parts = [p for p in content_to_str(message.content) if p]
    text = "\n".join(parts).strip()
    if not text:
        return None
    return f"{role_label}: {_truncate_keep_head(text, max_chars)}"


def _render_action_event(event: ActionEvent, max_chars: int) -> str | None:
    # 内置操作 (e.g. ``FinishAction``) 1. ``message`` 一个字段，该字段携带智能体的最终摘
    # 要。 其他操作不这样做，LLMConvertible 路径则单独处理它们——默默地跳过。
    #
    message = event.message
    if not isinstance(message, str) or not message.strip():
        return None
    return f"[AGENT]: {_truncate_keep_head(message.strip(), max_chars)}"


def _render_content_block(block: Any) -> str | None:
    """将单个 ACP 内容块渲染为紧凑摘要。

    ACP 协议定义了三个 ``ToolCallContent`` 变体 -
    ``diff``、``content``（包装泛型 ``ContentBlock``）和
    ``terminal`` — 但 ``_serialize_tool_content`` 保留直接
    ``ContentBlock`` 字典（``{type: "text", text: …}`` 和朋友）也在顶层，所以这两种形
    状都可以出现在
    ``ACPToolCallEvent.content``.

    返回单行或多行字符串，如果块不携带可用信号，则返回 ``None``。 所有字段读取均接受
    snake_case 和 camelCase 命名约定。
    """
    block_type = _block_field(block, "type")
    if block_type == "diff":
        path = _block_field(block, "path") or ""
        old_text = _block_field(block, "old_text", "oldText")
        kind = "patch" if old_text is not None else "write"
        header = f"[diff {kind}] {path}".rstrip()
        new_text = _block_field(block, "new_text", "newText")
        if isinstance(new_text, str) and new_text:
            return f"{header}\n{new_text}"
        return header
    if block_type == "content":
        inner = _block_field(block, "content")
        if inner is None:
            return None
        return _render_content_block(inner)
    if block_type == "terminal":
        tid = _block_field(block, "terminal_id", "terminalId")
        return f"[terminal {tid}]" if tid else "[terminal]"
    # 直接 ContentBlock 变体（也在顶层接受 - 一些 ACP 服务器将它们展开，并且
    # ``_serialize_tool_content`` 在持久化期间保持该形状）。 文本内容必须逐字返回，以便
    # 简历记录不会丢失实际内容载荷。
    #
    if block_type == "text":
        text = _block_field(block, "text")
        if isinstance(text, str) and text:
            return text
        return None
    if block_type == "image":
        return "[Image]"
    if block_type == "audio":
        return "[Audio]"
    # 任何其他命名变体（资源，resource_link，...）呈现为
    # ``[<type>]`` 占位符。
    if block_type:
        return f"[{block_type}]"
    return None


def _render_content_list(content: list[Any] | None) -> list[str]:
    if not content:
        return []
    out: list[str] = []
    for block in content:
        rendered = _render_content_block(block)
        if rendered:
            out.append(rendered)
    return out


def _render_tool_event(event: ACPToolCallEvent, max_chars: int) -> str | None:
    # ACP 流 ``pending → pending → completed`` 为单个工具调用； 在参数到达之前发出的占位
    # 符事件带有用于输入/输出的 None、用于 is_error 的 False 以及一个空/无内容列表。 在
    # 这里区分``is None``与伪空但有效的载荷：``raw_output``的``0``、``False``或``""``的
    # 工具是一个*完成*的调用，而不是一个占位符。 可渲染性：当且仅当raw_input、raw_output
    # 、is_error中的任何一个或内容携带实际信息时，某些东西就存在。
    #
    if (
        event.raw_input is None
        and event.raw_output is None
        and not event.is_error
        and not event.content
    ):
        return None
    status = "failed" if event.is_error else (event.status or "completed")
    name = event.title or event.tool_kind or "tool"
    parts: list[str] = [f"[TOOL USE: {name}] ({status})"]
    if event.raw_input is not None:
        parts.append("  input:")
        for line in str(event.raw_input).splitlines() or [""]:
            parts.append(f"    {line}")
    content_lines = _render_content_list(event.content)
    if content_lines:
        parts.append("  content:")
        for entry in content_lines:
            for line in entry.splitlines() or [""]:
                parts.append(f"    {line}")
    if event.raw_output is not None:
        parts.append("  output:")
        for line in str(event.raw_output).splitlines() or [""]:
            parts.append(f"    {line}")
    return _truncate_keep_head("\n".join(parts), max_chars)


def _terminal_tool_indices(events: Sequence[Event]) -> set[int]:
    """每个*流式传输序列*的终端ACPToolCallEvent的索引。

    ACP 为单个工具调用连续发出一个早期 ``started`` 事件和一个终止 (``completed`` /
    ``failed``) 事件； 只有终端事件携带最
    终的 I/O。 我们保留那个终端事件，丢弃之前的 ``started`` 个。（这也容忍在源塌陷之
    前已持久化的旧日日志，其中
    ``pending → … → completed`` 次运行保留了几个中间结果——保留最后的结果仍然选择终端
    帧。）

    重要的是，重复数据删除的范围是由 MessageEvents** 分隔的 ** 连续运行，而不是整个历
    史记录。 ACP 提供商 (e.g. Codex）重置
    ``tool_call_id`` 计数器每个会话 - 在沙箱回收后，新的 ``exec_1`` 与之前的
    ``exec_1`` 完全无关。 A
    ``MessageEvent`` 是自然的会话边界信号：如果任何消息事件发生在同一个
    ``tool_call_id`` 两次出现之间，它们属于不同的会话，且两个事件
    独立渲染。
    """
    # 收集 MessageEvents（会话边界标记）的位置。
    msg_indices: set[int] = set()
    tool_positions: dict[str, list[int]] = {}
    for i, event in enumerate(events):
        if isinstance(event, MessageEvent):
            msg_indices.add(i)
        elif isinstance(event, ACPToolCallEvent) and event.tool_call_id:
            tool_positions.setdefault(event.tool_call_id, []).append(i)

    keep: set[int] = set()
    for positions in tool_positions.values():
        if len(positions) == 1:
            keep.add(positions[0])
            continue
        # 在 MessageEvent 边界处分成组。
        groups: list[list[int]] = [[positions[0]]]
        for idx in positions[1:]:
            prev = groups[-1][-1]
            if any(prev < m < idx for m in msg_indices):
                groups.append([idx])
            else:
                groups[-1].append(idx)
        for group in groups:
            keep.add(group[-1])

    return keep


def render_resume_transcript(
    events: Sequence[Event],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_message_chars: int = DEFAULT_MAX_MESSAGE_CHARS,
    max_tool_chars: int = DEFAULT_MAX_TOOL_CHARS,
    marker: str = RESUME_CONTEXT_MARKER,
    header_body: str = DEFAULT_HEADER_BODY,
    footer: str = DEFAULT_FOOTER,
) -> str | None:
    """将 ``events`` 渲染为单个简历引导脚本字符串。

    退货 ``None`` 当没有事件时 ``events`` 生成可见输出 (e.g. 新的对话，或仅过滤的占位
    符工具事件）。 也返回 ``None`` 当
    ``max_chars < len(marker)``预算太小，无法容纳完整的标记，这将迫使出现部分标记，这
    将破坏
    ``out.startswith(marker)`` 双流检测 —— 调用方应将这种情况视为新的对话。

    ``MessageEvent`` 变成 ``[USER]: …`` / ``[ASSISTANT]: …`` 块（包括
    ``to_llm_message()`` 中
    的 ``extended_content``），
    ``ACPToolCallEvent``s成为``[TOOL USE: <name>] (<status>)``块，块内包含原始输入/输
    出缩进，以及
    ``ActionEvent``s
    ``action`` 公开 ``message`` (e.g. ``FinishAction``）成为
    ``[AGENT]: …`` 摘要行。 其他事件类型将被忽略。

    ``ACPToolCallEvent`` 由 ``tool_call_id`` 进行重复数据删除：仅渲染每个 ACP 流式传
    输待处理→已完成序列中的最终（终端）事件
    。

    截断是 **保留尾部** 对于整体转录：当完整历史超过 ``max_chars``保留标记和脚注，以
    及删除最旧的主体内容（保留一个） ``"...\\n"`` 标示
    剪辑的前缀）。 每条消息和每个工具的容量是头保持的——长的单独块保留其开头的文本并添
    加 ``"..."``.

    所有 ``max_*`` 参数都严格遵守为零； 输出字符串保证满足
    ``len(result) <= max_chars``。

    调用者负责：
      * 按时间顺序传递事件（在提交之前必须反转最新的优先获取）；
      * 任何特定于提供商的工具清理 ``raw_input`` /
        ``raw_output``（路径清理、过滤提供者内部元数据键、剥离 shell/测试样板等）；
      * 将渲染的字符串打包到 ``SendMessageRequest`` 或等效的消息信封中。
    """
    keep_tool_indices = _terminal_tool_indices(events)

    blocks: list[str] = []
    for i, event in enumerate(events):
        rendered: str | None
        if isinstance(event, MessageEvent):
            rendered = _render_message_event(event, max_message_chars)
        elif isinstance(event, ACPToolCallEvent):
            if event.tool_call_id and i not in keep_tool_indices:
                continue
            rendered = _render_tool_event(event, max_tool_chars)
        elif isinstance(event, ActionEvent):
            rendered = _render_action_event(event, max_message_chars)
        else:
            rendered = None
        if rendered:
            blocks.append(rendered)

    if not blocks:
        return None

    header_lines = [marker] + ([header_body] if header_body else [])
    header_text = "\n\n".join(header_lines)
    body_text = "\n\n".join(blocks)

    full = "\n\n".join([header_text, body_text, footer])
    if len(full) <= max_chars:
        return full

    # 文字记录太长。 按原样保留标记、页眉正文和页脚； 头部截断主体，以便最新鲜的事件得以
    # 幸存 - 这就是上下文和智能体进行最需要的对话。
    #
    sep = "\n\n"
    overhead = len(header_text) + len(sep) + len(sep) + len(footer)
    body_budget = max_chars - overhead
    if body_budget >= len(_HEAD_ELLIPSIS) + 1:
        return (
            header_text
            + sep
            + _truncate_keep_tail(body_text, body_budget)
            + sep
            + footer
        )

    # ``max_chars`` 太紧了，即使是页眉+页脚本身也没有为有意义的正文留出空间。 保留标记契
    # 约：每个非 None 结果必须以完整的 ``marker`` 字符串开头，以便调用者可以使用
    # ``out.startswith(marker)`` 进行双恢复检测。 部分标记（e.g. ``<<RESUMED `` for
    # max_chars=10) 看起来像可用的上下文，但默默地绕过了那个守卫。 当预算无法满足完整标
    # 记时返回 ``None`` — 呼叫者应将其视为一次新的对话，而不是一份格式错误的简历。
    #
    if max_chars < len(marker):
        return None
    marker_prefix = marker + "\n"
    if len(marker_prefix) > max_chars:
        # 标记适合，但没有空间容纳换行符 - 仅返回标记（不带换行符），因此输出恰好是
        # max_chars。
        #
        return marker
    # 用成绩单的最新尾部填写剩余的预算。
    content_budget = max_chars - len(marker_prefix)
    return marker_prefix + _truncate_keep_tail(
        full[len(marker_prefix) :], content_budget
    )
