"""测试 MCP 工具操作在发送到 MCP 服务器的数据中不包含“种类”字段。

此测试重现问题 #886，其中 DiscriminatedUnionMixin 中的“kind”字段错误地包含在 MCP 工具
参数中，导致验证错误。
"""

import sys
from pathlib import Path

import pytest

from openhands.sdk.mcp import create_mcp_tools
from openhands.sdk.mcp.config import coerce_mcp_config


@pytest.fixture
def fetch_tool():
    """使用本地 stdio 服务器创建一个真正的 MCP 获取工具。"""
    repo_root = Path(__file__).resolve().parents[3]
    mcp_config = {
        "mcpServers": {
            "fetch": {
                "command": sys.executable,
                "args": ["-m", "tests.sdk.mcp.stdio_test_server"],
                "cwd": str(repo_root),
            }
        }
    }
    tools = create_mcp_tools(coerce_mcp_config(mcp_config["mcpServers"]), timeout=10.0)
    assert len(tools) == 1
    return tools[0]


def test_real_mcp_tool_excludes_kind_field_from_action_data(fetch_tool):
    """测试 action_from_arguments 数据字段中不包含“kind”。

    这重现了问题 #886。 “kind”字段由 DiscriminatedUnionMixin 添加到动态创建的操作类型
    中，但它应该不包含在发送到 MCP 服务器的数
    据中。 MCP 具有 additionalProperties: False 的服务器将拒绝具有意外“种类”字段的请
    求。
    """
    # 从参数创建操作（这就是智能体的作用）
    args = {"url": "https://example.com"}
    action = fetch_tool.action_from_arguments(args)

    # action.data 应该不包含“kind”字段，因为它不是 MCP 工具模式的一部分
    #
    assert "kind" not in action.data
    assert action.data == {"url": "https://example.com"}

    # 验证 to_mcp_arguments 也不包含“kind”
    mcp_args = action.to_mcp_arguments()
    assert "kind" not in mcp_args
    assert mcp_args == {"url": "https://example.com"}


def test_real_mcp_tool_with_optional_field_no_kind(fetch_tool):
    """测试可选字段在没有“kind”字段的情况下是否正常工作。"""
    # 创建包含必填字段和可选字段的操作
    args = {"url": "https://example.com", "max_length": 5000}
    action = fetch_tool.action_from_arguments(args)

    # action.data 应不包含“种类”字段
    assert "kind" not in action.data
    assert "url" in action.data
    assert action.data["url"] == "https://example.com"
    assert "max_length" in action.data
    assert action.data["max_length"] == 5000


def test_real_mcp_tool_drops_none_values_but_not_kind(fetch_tool):
    """测试 None 值是否已删除且不包含“kind”。"""
    # 创建可选字段值为 None 的操作
    args = {"url": "https://example.com", "max_length": None}
    action = fetch_tool.action_from_arguments(args)

    # None 应该被删除，并且 'kind' 不应该出现
    assert "kind" not in action.data
    assert "max_length" not in action.data
    assert action.data == {"url": "https://example.com"}


def test_real_mcp_tool_execution_without_kind_field(fetch_tool):
    """测试在数据中没有“kind”字段的情况下执行该工具是否有效。

    这是终极测试 - 如果 'kind' 仍然被发送到 MCP 服务器，且服务器返回
    additionalProperties: False，这将失败：'输入验证错误：
    额外属性不允许 (kind 未预期)
    """
    # 创建并执行动作
    args = {"url": "https://example.com"}
    action = fetch_tool.action_from_arguments(args)

    # 执行该工具 - 如果发送到 MCP 的参数中包含“kind”，则会失败
    observation = fetch_tool(action)

    # 验证我们得到了有效的响应（不是关于“kind”的错误）如果没有错误则检查输出，否则检查错
    # 误消息
    #
    from openhands.sdk.llm import TextContent

    assert observation.content is not None
    # 从内容块中提取文本（内容现在始终是列表）
    text_parts = [
        block.text for block in observation.content if isinstance(block, TextContent)
    ]
    content_str = " ".join(text_parts)

    # 检查响应是否不包含有关“kind”的验证错误
    if "error" in content_str.lower():
        # 如果出现错误，请确保它与“kind”字段无关
        assert "kind" not in content_str.lower(), (
            "MCP server rejected 'kind' field - this means the fix didn't work"
        )
