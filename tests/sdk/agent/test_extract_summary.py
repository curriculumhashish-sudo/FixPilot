"""测试 Agent._extract_summary 方法。"""

from unittest.mock import Mock

import mcp.types
import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.llm import LLM
from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.tool import MCPToolDefinition


@pytest.fixture
def agent():
    """创建测试智能体。"""
    return Agent(
        llm=LLM(
            usage_id="test-llm",
            model="test-model",
            api_key=SecretStr("test-key"),
            base_url="http://test",
        )
    )


@pytest.mark.parametrize(
    "summary_value,expected_result",
    [
        # 提供的有效摘要 - 使用它
        ("testing file system", "testing file system"),
        # 未提供摘要 - 生成默认值
        (None, 'test_tool: {"some_param": "value"}'),
        # 非字符串摘要 - 生成默认值
        (123, 'test_tool: {"some_param": "value"}'),
        # 空或仅空白 - 生成默认值
        ("", 'test_tool: {"some_param": "value"}'),
        ("   ", 'test_tool: {"some_param": "value"}'),
    ],
)
def test_extract_summary(agent, summary_value, expected_result):
    """使用各种场景测试 _extract_summary 方法。"""
    arguments = {"some_param": "value"}
    if summary_value is not None:
        arguments["summary"] = summary_value

    result = agent._extract_summary("test_tool", arguments)
    assert result == expected_result
    assert "summary" not in arguments


def _make_mcp_tool_with_summary():
    """创建一个 MCP 工具，其 inputSchema 根据需要声明“摘要”。"""
    mcp_tool = mcp.types.Tool(
        name="jira_create_issue",
        description="Create a Jira issue",
        inputSchema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "summary": {"type": "string", "description": "Ticket title"},
                "issue_type": {"type": "string"},
            },
            "required": ["project_key", "summary", "issue_type"],
        },
    )
    client = Mock(spec=MCPClient)
    return MCPToolDefinition.create(mcp_tool, client)[0]


def test_extract_summary_preserves_mcp_tool_summary_param(agent):
    """当工具声明它时，_extract_summary 必须不弹出“摘要”。"""
    tool = _make_mcp_tool_with_summary()
    arguments = {
        "project_key": "PROJ",
        "summary": "My ticket title",
        "issue_type": "Task",
    }

    result = agent._extract_summary(tool.name, arguments, tool=tool)

    # 该工具的真实“摘要”值必须保留在字典中
    assert arguments["summary"] == "My ticket title"
    # 该工具自己的摘要值被重新用作事件级摘要 (e.g. Jira 票证标题的描述性足以实现可视化）
    #
    assert result == "My ticket title"


def test_mcp_tool_with_summary_param_roundtrip(agent):
    """端到端：摘要必须在提取和操作中幸存下来验证。"""
    tool = _make_mcp_tool_with_summary()
    arguments = {
        "project_key": "PROJ",
        "summary": "My ticket title",
        "issue_type": "Task",
    }

    # 这是来自 _get_action_event 的确切调用序列
    _summary = agent._extract_summary(tool.name, arguments, tool=tool)
    action = tool.action_from_arguments(arguments)

    # action_from_arguments 应该成功（而不是提高 ValidationError）
    assert action.data["summary"] == "My ticket title"
    assert action.data["project_key"] == "PROJ"


def test_extract_summary_mcp_tool_summary_missing_falls_back(agent):
    """当工具声明“摘要”但它为空时，则回退到默认值。"""
    tool = _make_mcp_tool_with_summary()
    arguments = {
        "project_key": "PROJ",
        "summary": "",
        "issue_type": "Task",
    }

    result = agent._extract_summary(tool.name, arguments, tool=tool)

    # 空摘要→回退到默认格式
    assert "jira_create_issue:" in result
    # 空值必须仍保留在参数中
    assert arguments["summary"] == ""


def test_extract_summary_still_pops_for_tools_without_summary_param(agent):
    """对于没有声明“摘要”的工具，它仍然作为元弹出。"""
    mcp_tool = mcp.types.Tool(
        name="some_tool",
        description="A tool without a summary param",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
            },
            "required": ["url"],
        },
    )
    client = Mock(spec=MCPClient)
    tool = MCPToolDefinition.create(mcp_tool, client)[0]

    arguments = {"url": "https://example.com", "summary": "Fetch example"}
    result = agent._extract_summary(tool.name, arguments, tool=tool)

    assert result == "Fetch example"
    assert "summary" not in arguments
