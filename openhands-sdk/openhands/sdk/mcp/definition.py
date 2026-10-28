"""MCPTool 定义和实现。"""

import json
from typing import Any

import mcp.types
from pydantic import Field
from rich.text import Text

from openhands.sdk.llm import ImageContent, TextContent
from openhands.sdk.logger import get_logger
from openhands.sdk.tool import (
    Observation,
)
from openhands.sdk.tool.schema import Action
from openhands.sdk.utils.visualize import display_json


logger = get_logger(__name__)


# 注意我们不定义 MCPToolAction 因为它是
# 将从 MCP 工具模式动态创建。


class MCPToolAction(Action):
    """模式用于 MCP 输入操作。

    它只是原始 JSON 的薄包装，不执行任何验证操作。

    验证将由 MCPTool.__call__ 通过构建动态创建的 Pydantic 模型来执行
    from the MCP tool input schema.
    """

    data: dict[str, Any] = Field(
        default_factory=dict, description="Dynamic data fields from the tool call"
    )

    def to_mcp_arguments(self) -> dict:
        """将数据字段作为 MCP 工具调用参数返回。

        这用于将此操作转换为 MCP 工具调用参数。 数据字段包含工具调用中的动态字段。
        """
        return self.data


class MCPToolObservation(Observation):
    """观测结果来自 MCP 工具执行。"""

    tool_name: str = Field(description="Name of the tool that was called")

    @classmethod
    def from_call_tool_result(
        cls, tool_name: str, result: mcp.types.CallToolResult
    ) -> "MCPToolObservation":
        """从 CallToolResult 创建 MCPToolObservation。"""

        native_content: list[mcp.types.ContentBlock] = result.content
        content: list[TextContent | ImageContent] = [
            TextContent(text=f"[Tool '{tool_name}' executed.]")
        ]
        for block in native_content:
            if isinstance(block, mcp.types.TextContent):
                content.append(TextContent(text=block.text))
            elif isinstance(block, mcp.types.ImageContent):
                content.append(
                    ImageContent(
                        image_urls=[f"data:{block.mimeType};base64,{block.data}"],
                    )
                )
            else:
                logger.warning(
                    f"Unsupported MCP content block type: {type(block)}. Ignoring."
                )

        return cls(
            content=content,
            is_error=result.isError,
            tool_name=tool_name,
        )

    @property
    def visualize(self) -> Text:
        """返回此观测结果的富文本表示形式。"""
        text = Text()

        if self.is_error:
            text.append("❌ ", style="red bold")
            text.append(self.ERROR_MESSAGE_HEADER, style="bold red")

        text.append(f"[MCP Tool '{self.tool_name}' Observation]\n", style="bold")
        for block in self.content:
            if isinstance(block, TextContent):
                # try to see if block.text is a JSON
                try:
                    parsed = json.loads(block.text)
                    text.append(display_json(parsed))
                    continue
                except (json.JSONDecodeError, TypeError):
                    text.append(block.text + "\n")
            elif isinstance(block, ImageContent):
                text.append(f"[Image with {len(block.image_urls)} URLs]\n")
        return text
