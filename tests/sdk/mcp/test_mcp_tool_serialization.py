"""使用 DiscriminatedUnionMixin 测试 MCP 工具 JSON 序列化。

Note: MCPTool 序列化可能由于复杂 MCP 对象而受限
（mcp_tool 字段包含 mcp.types.Tool，但 JSON 可能无法完全序列化）。 这些测试展示了预期
的行为和限制。
"""

from unittest.mock import Mock

import mcp.types

from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.definition import MCPToolAction, MCPToolObservation
from openhands.sdk.mcp.tool import MCPToolDefinition
from openhands.sdk.tool.schema import Action
from openhands.sdk.tool.tool import ToolDefinition


def create_mock_mcp_tool(name: str) -> mcp.types.Tool:
    """创建模拟对象 MCP 工具进行测试。"""
    return mcp.types.Tool(
        name=name,
        description=f"A test MCP tool named {name}",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query parameter"}
            },
            "required": ["query"],
        },
    )


def test_mcp_tool_json_serialization_deserialization() -> None:
    # 创建模拟对象 MCP 工具和客户端
    mock_mcp_tool = create_mock_mcp_tool(
        "test_mcp_tool_json_serialization_deserialization"
    )
    mock_client = Mock(spec=MCPClient)
    tools = MCPToolDefinition.create(mock_mcp_tool, mock_client)
    mcp_tool = tools[0]  # 从序列中提取单个工具

    tool_json = mcp_tool.model_dump_json()
    deserialized_tool = MCPToolDefinition.model_validate_json(tool_json)
    assert isinstance(deserialized_tool, MCPToolDefinition)
    # 我们使用 model_dump 因为工具执行器不可序列化并且被排除在外
    assert deserialized_tool.model_dump() == mcp_tool.model_dump()


def test_mcp_tool_polymorphic_behavior() -> None:
    """Test MCPTool 使用工具基类的多态行为。"""
    # 创建模拟对象 MCP 工具和客户端
    mock_mcp_tool = create_mock_mcp_tool("test_mcp_tool_polymorphic_behavior")
    mock_client = Mock(spec=MCPClient)

    # 创建 MCPTool 个实例
    tools = MCPToolDefinition.create(mock_mcp_tool, mock_client)
    mcp_tool = tools[0]  # 从序列中提取单个工具

    # 应该是 ToolDefinition 的实例
    assert isinstance(mcp_tool, ToolDefinition)
    assert isinstance(mcp_tool, MCPToolDefinition)

    # 检查基本属性
    assert mcp_tool.name == "test_mcp_tool_polymorphic_behavior"
    assert "test MCP tool" in mcp_tool.description
    assert hasattr(mcp_tool, "mcp_tool")


def test_mcp_tool_kind_field() -> None:
    """测试 MCPTool 类型字段是否正确设置。"""
    # 创建模拟对象 MCP 工具和客户端
    mock_mcp_tool = create_mock_mcp_tool("test_mcp_tool_kind_field")
    mock_client = Mock(spec=MCPClient)

    # 创建 MCPTool 个实例
    tools = MCPToolDefinition.create(mock_mcp_tool, mock_client)
    mcp_tool = tools[0]  # 从序列中提取单个工具

    # 检查种类字段
    assert hasattr(mcp_tool, "kind")
    expected_kind = mcp_tool.__class__.__name__
    assert mcp_tool.kind == expected_kind


def test_mcp_tool_fallback_behavior() -> None:
    """Test MCPTool  回退方案手动数据的行为。"""
    # 创建能够表示 MCPTool 的数据
    tool_data = {
        "name": "fallback-tool",
        "description": "A fallback test tool",
        "action_type": "MCPToolAction",
        "observation_type": "MCPToolObservation",
        "kind": "MCPToolDefinition",
        "mcp_tool": {
            "name": "fallback-tool",
            "description": "A fallback test tool",
            "inputSchema": {"type": "object", "properties": {}},
        },
    }

    deserialized_tool = ToolDefinition.model_validate(tool_data)
    assert isinstance(deserialized_tool, ToolDefinition)
    assert deserialized_tool.name == "fallback-tool"
    assert issubclass(deserialized_tool.action_type, Action)
    assert deserialized_tool.observation_type and issubclass(
        deserialized_tool.observation_type, MCPToolObservation
    )


def test_mcp_tool_essential_properties() -> None:
    """测试 MCPTool 在创建后是否保持关键属性。"""
    # 创建具有特定属性的模拟对象 MCP 工具
    mock_mcp_tool = mcp.types.Tool(
        name="essential_tool",
        description="Tool with essential properties",
        inputSchema={
            "type": "object",
            "properties": {"param1": {"type": "string"}, "param2": {"type": "integer"}},
            "required": ["param1"],
        },
    )
    mock_client = Mock(spec=MCPClient)

    # 创建 MCPTool 个实例
    tools = MCPToolDefinition.create(mock_mcp_tool, mock_client)
    mcp_tool = tools[0]  # 从序列中提取单个工具

    # 验证基本属性是否得到保留
    assert mcp_tool.name == "essential_tool"
    assert mcp_tool.description == "Tool with essential properties"
    assert mcp_tool.mcp_tool.name == "essential_tool"
    assert mcp_tool.mcp_tool.inputSchema is not None

    # 验证操作类型是否已正确创建
    assert mcp_tool.action_type is not None and issubclass(
        mcp_tool.action_type, MCPToolAction
    )
    assert hasattr(mcp_tool.action_type, "to_mcp_arguments")
