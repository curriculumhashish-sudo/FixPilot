from typing import Any, cast
from unittest.mock import Mock

import mcp.types
import pytest
from pydantic import ValidationError

from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.tool import MCPToolDefinition


def _make_tool_with_schema(schema: dict, name: str = "fetch"):
    mcp_tool = mcp.types.Tool(
        name=name,
        description="Fetch a URL",
        inputSchema=schema,
    )
    client = Mock(spec=MCPClient)
    return MCPToolDefinition.create(mcp_tool, client)[0]


def test_mcp_action_from_arguments_validates_and_sanitizes():
    tool = _make_tool_with_schema(
        {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["url"],
        }
    )

    # 包含应删除的 None
    args = {"url": "https://example.com", "timeout": None}
    action = tool.action_from_arguments(args)
    # 注意：DiscriminatedUnionMixin 中的“kind”字段应该在 action.data 中不
    # 因为它不是 MCP 工具模式的一部分，并且在发送到 MCP 服务器时会导致验证错误
    #
    assert action.data == {"url": "https://example.com"}


def test_mcp_action_from_arguments_preserves_schema_kind_argument():
    tool = _make_tool_with_schema(
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "file_path": {"type": "string"},
                "kind": {
                    "type": "string",
                    "description": "Symbol kind hint, such as Function or Method",
                },
                "repo": {"type": "string"},
            },
            "required": ["name"],
        },
        name="gitnexus_context",
    )

    function = tool.to_openai_tool()["function"]
    openai_schema = cast(dict[str, Any], function.get("parameters"))
    properties = cast(dict[str, Any], openai_schema["properties"])
    kind_schema = cast(dict[str, Any], properties["kind"])
    assert kind_schema["description"] == "Symbol kind hint, such as Function or Method"

    action = tool.action_from_arguments(
        {
            "name": "executeCommand",
            "file_path": "src/vs/workbench/services/commands/common/commandService.ts",
            "kind": "Method",
            "repo": "vscode-benchmark-repo",
        }
    )

    assert action.data == {
        "name": "executeCommand",
        "file_path": "src/vs/workbench/services/commands/common/commandService.ts",
        "kind": "Method",
        "repo": "vscode-benchmark-repo",
    }


def test_mcp_action_from_arguments_raises_on_invalid():
    tool = _make_tool_with_schema(
        {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
            },
            "required": ["url"],
        }
    )

    # 缺少必需的网址
    with pytest.raises(ValidationError):
        tool.action_from_arguments({})

    # 额外的字段也应该导致验证错误
    with pytest.raises(ValidationError):
        tool.action_from_arguments({"url": "https://x.com", "data": {"x": 1}})
