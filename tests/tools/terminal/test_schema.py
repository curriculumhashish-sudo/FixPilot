from openhands.tools.terminal import TerminalTool


def test_to_mcp_tool_detailed_type_validation_bash(mock_conversation_state):
    """测试 MCP 工具模式生成的详细类型验证（终端）。"""  # noqa: E501

    terminal_tool = TerminalTool.create(conv_state=mock_conversation_state)
    assert len(terminal_tool) == 1
    terminal_tool = terminal_tool[0]
    assert isinstance(terminal_tool, TerminalTool)

    # 测试终端工具模式
    bash_mcp = terminal_tool.to_mcp_tool()
    bash_schema = bash_mcp["inputSchema"]
    bash_props = bash_schema["properties"]

    # 测试命令字段为必填字符串
    bash_command_schema = bash_props["command"]
    assert bash_command_schema["type"] == "string"
    assert "command" in bash_schema["required"]

    # Test is_input 字段是可选布尔值，默认值
    is_input_schema = bash_props["is_input"]
    assert is_input_schema["type"] == "boolean"
    assert "is_input" not in bash_schema["required"]

    # 测试超时字段是可选数字
    timeout_schema = bash_props["timeout"]
    assert "anyOf" not in timeout_schema
    assert timeout_schema["type"] == "number"

    # security_risk应该不在#341之后的模式中
    assert "security_risk" not in bash_props
