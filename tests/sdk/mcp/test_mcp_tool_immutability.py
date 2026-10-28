"""使用新的简化实现来测试 MCP 工具功能。"""

from typing import cast
from unittest.mock import MagicMock, Mock

import mcp.types
import pytest

from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.tool import MCPToolDefinition, MCPToolExecutor


class MockMCPClient(MCPClient):
    """用于测试的模拟对象 MCPClient，可绕过复杂的构造函数。"""

    def __init__(self):
        # 跳过父构造函数以避免需要传输层
        pass


class TestMCPToolImmutability:
    """测试套件对 MCPTool 的不变性功能。"""

    def setup_method(self):
        """设置测试环境。"""
        self.mock_client: MockMCPClient = MockMCPClient()

        # 创建模拟对象 MCP 工具
        self.mock_mcp_tool: Mock = MagicMock(spec=mcp.types.Tool)
        self.mock_mcp_tool.name = "test_tool"
        self.mock_mcp_tool.description = "Test tool description"
        self.mock_mcp_tool.inputSchema = {
            "type": "object",
            "properties": {"command": {"type": "string"}},
        }
        self.mock_mcp_tool.annotations = None
        self.mock_mcp_tool.meta = {"version": "1.0"}

        tools = MCPToolDefinition.create(
            mcp_tool=self.mock_mcp_tool, mcp_client=self.mock_client
        )
        self.tool: MCPToolDefinition = tools[0]  # 从序列中提取单个工具

    def test_mcp_tool_is_frozen(self):
        """测试 MCPTool 个实例是否被冻结，无法修改。"""
        # 测试直接字段分配是否会引发 ValidationError
        with pytest.raises(Exception):  # Pydantic 为冻结模型加薪 ValidationError
            self.tool.mcp_tool = mcp.types.Tool(
                name="modified_name",
                description="modified description",
                inputSchema={"type": "object", "properties": {}},
            )

        with pytest.raises(Exception):
            self.tool.description = "modified_description"

    def test_mcp_tool_set_executor_returns_new_instance(self):
        """测试 set_executor 返回一个新的 MCPTool 实例。"""
        new_executor = MCPToolExecutor(tool_name="new_tool", client=self.mock_client)
        new_tool = self.tool.set_executor(new_executor)

        # 验证是否创建了新实例
        assert new_tool is not self.tool
        assert cast(MCPToolExecutor, self.tool.executor).tool_name == "test_tool"
        assert cast(MCPToolExecutor, new_tool.executor).tool_name == "new_tool"
        assert new_tool.name == self.tool.name
        assert new_tool.description == self.tool.description

    def test_mcp_tool_model_copy_creates_modified_instance(self):
        """测试 model_copy 是否可以创建 MCPTool 的修改版本。"""
        # 使用不同的名称创建修改后的 MCP 工具
        from mcp.types import Tool as MCPTool

        modified_mcp_tool = MCPTool(
            name="modified_tool",
            description="Modified MCP tool description",
            inputSchema=self.tool.mcp_tool.inputSchema,
        )

        # 创建包含修改字段的副本
        modified_tool = self.tool.model_copy(
            update={
                "mcp_tool": modified_mcp_tool,
                "description": "Modified description",
            }
        )

        # 验证是否创建了经过修改的新实例
        assert modified_tool is not self.tool
        assert self.tool.name == "test_tool"
        assert self.tool.description == "Test tool description"
        assert modified_tool.name == "modified_tool"
        assert modified_tool.description == "Modified description"

    def test_mcp_tool_meta_field_immutability(self):
        """测试元字段是否正常工作并且不可变。"""
        # 验证元字段可访问
        assert self.tool.meta == {"version": "1.0"}

        # 测试meta字段不能直接修改
        with pytest.raises(Exception):
            self.tool.meta = {"version": "2.0"}

        # 测试元字段是否可以通过 model_copy 修改
        new_meta = {"version": "2.0", "author": "new_author"}
        modified_tool = self.tool.model_copy(update={"meta": new_meta})
        assert modified_tool.meta == new_meta
        assert self.tool.meta == {"version": "1.0"}  # Original unchanged

    def test_mcp_tool_extra_fields_immutability(self):
        """测试 MCPTool 附加字段 (mcp_client, mcp_tool) 是否不可变。"""

        with pytest.raises(Exception):
            self.tool.mcp_tool = self.mock_mcp_tool

        assert self.tool.mcp_tool is self.mock_mcp_tool

    def test_mcp_tool_create_immutable_instance(self):
        """测试 MCPToolDefinition.create() 创建不可变实例。"""
        # 使用 create 创建另一个工具
        mock_tool2 = MagicMock(spec=mcp.types.Tool)
        mock_tool2.name = "another_tool"
        mock_tool2.description = "Another test tool"
        mock_tool2.inputSchema = {"type": "object"}
        mock_tool2.annotations = None
        mock_tool2.meta = None

        tools2 = MCPToolDefinition.create(
            mcp_tool=mock_tool2, mcp_client=self.mock_client
        )
        tool2 = tools2[0]  # 从序列中提取单个工具

        # 验证它是不可变的
        with pytest.raises(Exception):
            tool2.mcp_tool = mcp.types.Tool(
                name="modified_name",
                description="modified description",
                inputSchema={"type": "object", "properties": {}},
            )

        # 验证它具有正确的属性
        assert tool2.name == "another_tool"
        assert tool2.description == "Another test tool"
        assert isinstance(tool2.executor, MCPToolExecutor)
