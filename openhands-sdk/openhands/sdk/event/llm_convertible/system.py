import json

from pydantic import Field
from rich.text import Text

from openhands.sdk.event.base import N_CHAR_PREVIEW, LLMConvertibleEvent
from openhands.sdk.event.types import SourceType
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.tool import ToolDefinition


class SystemPromptEvent(LLMConvertibleEvent):
    """系统提示词由智能体添加。

    系统提示词可以选择包含在对话之间变化的动态上下文。 当提供``dynamic_context``时，
    它作为第二内容块包含在同一系统消息中。 缓存标记在这里不应用 -
     它们在启用缓存时由 ``LLM._apply_prompt_caching()`` 应用，确保只有在适当的情况下
     才会添加提供商特定的缓存控制。

    Attributes:
        system_prompt: 静态系统提示词文本（可跨对话缓存）
        tools: 可用工具列表
        dynamic_context: 可选的每个会话上下文（主机、存储库信息等）
            作为系统消息内的第二个 TextContent 块发送。
    """

    source: SourceType = "agent"
    system_prompt: TextContent = Field(..., description="The system prompt text")
    tools: list[ToolDefinition] = Field(
        ..., description="List of tools as ToolDefinition objects"
    )
    dynamic_context: TextContent | None = Field(
        default=None,
        description=(
            "Optional dynamic per-conversation context (runtime info, repo context, "
            "secrets). When provided, this is included as a second content block in "
            "the system message (not cached)."
        ),
    )

    @property
    def visualize(self) -> Text:
        """返回此系统提示词事件的富文本表示形式。"""
        content = Text()
        content.append("System Prompt:\n", style="bold")
        content.append(self.system_prompt.text)
        if self.dynamic_context:
            content.append("\n\nDynamic Context:\n", style="bold italic")
            content.append(self.dynamic_context.text)
        content.append(f"\n\nTools Available: {len(self.tools)}")
        for tool in self.tools:
            # 直接使用ToolDefinition属性
            description = tool.description.split("\n")[0][:100]
            if len(description) < len(tool.description):
                description += "..."

            content.append(f"\n  - {tool.name}: {description}\n")

            # 从操作类型获取参数模式
            try:
                params_dict = tool.action_type.to_mcp_schema()
                params_str = json.dumps(params_dict)
                if len(params_str) > 200:
                    params_str = params_str[:197] + "..."
                content.append(f"  Parameters: {params_str}")
            except Exception:
                content.append("  Parameters: <unavailable>")
        return content

    def to_llm_message(self) -> Message:
        """转换为单个系统 LLM 消息。

        当 ``dynamic_context`` 存在时，消息包含两个内容
        blocks: 静态提示词后跟动态上下文。 缓存标记
        这里不应用了 - 应用时 ``LLM._apply_prompt_caching()`` 会缓存，标记静态块（索
        引 0），留下动态块（索引 1）未标记，以供
        跨会话缓存共享。
        """
        if self.dynamic_context:
            return Message(
                role="system", content=[self.system_prompt, self.dynamic_context]
            )
        return Message(role="system", content=[self.system_prompt])

    def __str__(self) -> str:
        """SystemPromptEvent 的纯文本字符串表示形式。"""
        base_str = f"{self.__class__.__name__} ({self.source})"
        prompt_preview = (
            self.system_prompt.text[:N_CHAR_PREVIEW] + "..."
            if len(self.system_prompt.text) > N_CHAR_PREVIEW
            else self.system_prompt.text
        )
        tool_count = len(self.tools)
        context_info = ""
        if self.dynamic_context:
            context_info = (
                f"\n  Dynamic Context: {len(self.dynamic_context.text)} chars"
            )
        return (
            f"{base_str}\n  System: {prompt_preview}\n  "
            f"Tools: {tool_count} available{context_info}"
        )
