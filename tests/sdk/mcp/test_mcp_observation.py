"""测试 MCP 观测结果列表错误修复。"""

import json

import mcp.types
from rich.text import Text

from openhands.sdk.llm import TextContent
from openhands.sdk.mcp.definition import MCPToolObservation


def test_mcp_observation_with_list_json():
    """测试 MCPToolObservation 是否能处理 JSON 列表而不崩溃。

    此测试重现并验证了当 MCP 工具返回列表时 JSON 渲染器崩溃的 bug 的修复。
    """
    # 创建一个会导致原始错误的列表
    list_data = ["item1", "item2", 42, True, None]
    json_string = json.dumps(list_data)

    # 使用 JSON 列表创建文本内容
    text_content = TextContent(text=json_string)

    # 使用列表 JSON 创建 MCP 工具结果
    result = mcp.types.CallToolResult(
        content=[mcp.types.TextContent(type="text", text=json_string)], isError=False
    )

    # 根据结果创建观测结果
    observation = MCPToolObservation.from_call_tool_result("test_tool", result)

    # 这不应该崩溃（在修复之前它会崩溃）
    visualization = observation.visualize

    # 验证它是一个 Text 对象
    assert isinstance(visualization, Text)

    # 验证内容包含预期元素
    text_content = str(visualization)
    assert "[List with 5 items]" in text_content
    assert "item1" in text_content
    assert "item2" in text_content
    assert "42" in text_content
    assert "True" in text_content


def test_mcp_observation_with_dict_json():
    """测试 MCPToolObservation 是否仍然可用，使用字典 JSON。"""
    # 创建字典（这总是有效）
    dict_data = {"key1": "value1", "key2": 42, "key3": None}
    json_string = json.dumps(dict_data)

    # 使用字典 JSON 创建 MCP 工具结果
    result = mcp.types.CallToolResult(
        content=[mcp.types.TextContent(type="text", text=json_string)], isError=False
    )

    # 根据结果创建观测结果
    observation = MCPToolObservation.from_call_tool_result("test_tool", result)

    # 这应该像以前一样工作
    visualization = observation.visualize

    # 验证它是一个 Text 对象
    assert isinstance(visualization, Text)

    # 验证内容包含预期元素
    text_content = str(visualization)
    assert "key1" in text_content
    assert "value1" in text_content
    assert "key2" in text_content
    assert "42" in text_content
    # key3 应该跳过，因为它 None


def test_mcp_observation_with_string_json():
    """测试 MCPToolObservation 是否能与字符串 JSON 正常工作。"""
    # 创建一个简单的字符串（这之前会崩溃）
    string_data = "simple string response"
    json_string = json.dumps(string_data)

    # 使用字符串 JSON 创建 MCP 工具结果
    result = mcp.types.CallToolResult(
        content=[mcp.types.TextContent(type="text", text=json_string)], isError=False
    )

    # 根据结果创建观测结果
    observation = MCPToolObservation.from_call_tool_result("test_tool", result)

    # 这不应该崩溃
    visualization = observation.visualize

    # 验证它是一个 Text 对象
    assert isinstance(visualization, Text)

    # 验证内容包含字符串
    text_content = str(visualization)
    assert "simple string response" in text_content


def test_mcp_observation_with_number_json():
    """MCPToolObservation 应该能与 JSON 进行测试。"""
    # 创建一个数字（这之前会崩溃）
    number_data = 42
    json_string = json.dumps(number_data)

    # 创建编号为 JSON 的 MCP 工具结果
    result = mcp.types.CallToolResult(
        content=[mcp.types.TextContent(type="text", text=json_string)], isError=False
    )

    # 根据结果创建观测结果
    observation = MCPToolObservation.from_call_tool_result("test_tool", result)

    # 这不应该崩溃
    visualization = observation.visualize

    # 验证它是一个 Text 对象
    assert isinstance(visualization, Text)

    # 验证内容包含数字
    text_content = str(visualization)
    assert "42" in text_content


def test_mcp_observation_with_invalid_json():
    """测试 MCPToolObservation 是否优雅地处理无效的 JSON。"""
    # 创建无效的 JSON（这应该回退为纯文本）
    invalid_json = "{ invalid json }"

    # 使用无效的 JSON 创建 MCP 工具结果
    result = mcp.types.CallToolResult(
        content=[mcp.types.TextContent(type="text", text=invalid_json)], isError=False
    )

    # 根据结果创建观测结果
    observation = MCPToolObservation.from_call_tool_result("test_tool", result)

    # 这不应该崩溃并且应该回退到纯文本
    visualization = observation.visualize

    # 验证它是一个 Text 对象
    assert isinstance(visualization, Text)

    # 验证内容是否包含原文
    text_content = str(visualization)
    assert "{ invalid json }" in text_content
