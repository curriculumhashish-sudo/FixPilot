"""ACPToolCallEvent — 表面 ACP 工具调用轨迹 OpenHands 为事件。"""

from __future__ import annotations

from typing import Any

from rich.text import Text

from openhands.sdk.event.base import Event
from openhands.sdk.event.types import SourceType, ToolCallID


_MAX_DISPLAY_CHARS = 500

_MISSING: Any = object()


def _block_field(block: Any, *names: str) -> Any:
    """读取 ``block`` 上 ``names`` 中的第一个匹配字段。

    ACP 内容块以三种形式到达此代码：

      * Pydantic 模型（实时通知）——通过 ``getattr`` 读取；
      * snake_case dict (在 ``model_dump`` 持久化之后) — Pydantic 默认使用 Python 属
      性名称转储；
      * camelCase dict (ACP JSON wire format) — ACP TypeScript 规范将 diff blocks 视
      为
      ``{ type: "diff", oldText, newText, path }``，而 JSON 从外部 API 或 WebSocket
      帧到达则保留这些
      键的原始值。

    多个别名 (e.g. ``"old_text", "oldText"``) 可以通过，第一个到场的获胜。 如果没有别
    名匹配，则返回 ``None``。
    """
    if isinstance(block, dict):
        for name in names:
            if name in block:
                return block[name]
        return None
    for name in names:
        value = getattr(block, name, _MISSING)
        if value is not _MISSING:
            return value
    return None


class ACPToolCallEvent(Event):
    """表示 ACP 服务器执行的工具调用的事件。

    从 ACP 捕获工具名称、输入、输出和状态
    ``ToolCallStart`` / ``ToolCallProgress`` 通知，以便它们可以显示在 OpenHands 事件
    流和可视化工具中。

    这是 * 不是 * ``LLMConvertibleEvent`` — ACP 工具调用不参与 LLM 消息转换。
    """

    source: SourceType = "agent"
    tool_call_id: ToolCallID
    title: str
    status: str | None = None
    tool_kind: str | None = None
    raw_input: Any | None = None
    raw_output: Any | None = None
    content: list[Any] | None = None
    is_error: bool = False

    @property
    def is_patch_edit(self) -> bool:
        """True 如果此事件代表补丁/差异编辑（不是完整文件写入）。

        ACP-spec 编辑工具发出一个 ``diff`` 内容块，其 ``old_text`` 字段（JSON 线上的
        ``oldText``）区分两种情况：
          * 补丁编辑（e.g. ``Edit``): 设置``old_text``
          * 完整文件创建 (e.g. ``Write``): ``old_text`` 是 ``None``

        此检查在遵循 ACP 规范的 Claude Code、Codex 和 Gemini 服务器上与提供者无关。

        稳健性：
          * ``content`` 是任意顺序的混合块变体（文本、差异、终端​​等）的列表 - 这会扫
          描 ``diff`` 块而不是假设
          ``content[0]``。
          * 单个工具调用可以承载 ** 多个 ** ``diff`` 块 (e.g. 一个多文件补丁，创建一
          个文件并编辑另一个文件）。 如果 *any* dif
          f 块具有非 null ``old_text``，则该事件被归类为补丁编辑； 仅当以下情况时才算
          作写入
            *每个* diff 块都是一个完整文件写入。
          * 块形状可以是 Pydantic 模型（实时通知）、snake_case 字典（``model_dump``
          之后）或 camelCase 字典（
          ACP JSON 线）。 ``_block_field`` 读取所有三个内容，其中
            ``"oldText"`` 接受作为 ``"old_text"`` 的别名。

        对于省略结构化内容块但仍然通过原始输入键公开差异意图的提供者，检查回退到
        ``raw_input``。 回退方案需要一个非空的 ``old_string``
         — 仅 ``new_string`` 的载荷（或空的 ``old_string``）描述创建/写入，而不是补丁
         。 回退方案仅适用于*否*的情况
        ``content`` 中存在 ``diff`` 块； 结构化ACP数据总是优先于启发式。
        """
        diff_blocks = [
            b for b in self.content or () if _block_field(b, "type") == "diff"
        ]
        if diff_blocks:
            return any(
                _block_field(b, "old_text", "oldText") is not None for b in diff_blocks
            )
        raw = self.raw_input if isinstance(self.raw_input, dict) else {}
        old = raw.get("old_string")
        return isinstance(old, str) and len(old) > 0

    @property
    def visualize(self) -> Text:
        """返回此工具调用事件的富文本表示。"""
        content = Text()
        content.append(self.title, style="bold")

        # 种类/状态元数据行
        meta_parts: list[str] = []
        if self.tool_kind:
            meta_parts.append(f"kind={self.tool_kind}")
        if self.status:
            meta_parts.append(f"status={self.status}")
        if meta_parts:
            content.append(f"\n{' | '.join(meta_parts)}", style="dim")

        # 输入（跳过 None 和空容器，如 {}）
        if self.raw_input:
            input_str = str(self.raw_input)
            if len(input_str) > _MAX_DISPLAY_CHARS:
                input_str = input_str[:_MAX_DISPLAY_CHARS] + "..."
            content.append("\nInput: ", style="bold")
            content.append(input_str)

        # 输出（跳过None和空容器）
        if self.raw_output:
            output_str = str(self.raw_output)
            if len(output_str) > _MAX_DISPLAY_CHARS:
                output_str = output_str[:_MAX_DISPLAY_CHARS] + "..."
            content.append("\nOutput: ", style="bold")
            content.append(output_str)

        return content

    def __str__(self) -> str:
        parts = [f"{self.__class__.__name__} ({self.source}): {self.title}"]
        if self.status:
            parts.append(f"[{self.status}]")
        if self.tool_kind:
            parts.append(f"({self.tool_kind})")
        return " ".join(parts)
