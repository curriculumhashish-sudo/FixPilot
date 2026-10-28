"""测试工具模式摘要字段增强。"""

from collections.abc import Sequence
from typing import ClassVar
from unittest.mock import Mock

import mcp.types
import pytest
from pydantic import Field

from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.tool import MCPToolDefinition
from openhands.sdk.tool import Action, Observation, ToolDefinition


class TSAction(Action):
    x: int = Field(description="x")


class MockSummaryTool(ToolDefinition[TSAction, Observation]):
    """用于摘要测试的具体模拟对象工具。"""

    name: ClassVar[str] = "test_tool"

    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["MockSummaryTool"]:
        return [cls(**params)]


@pytest.fixture
def tool():
    return MockSummaryTool(
        description="Test tool",
        action_type=TSAction,
        observation_type=None,
        annotations=None,
    )


def test_to_responses_tool_summary_always_added(tool):
    """测试汇总字段是否始终添加到响应工具模式。"""
    t = tool.to_responses_tool()
    params = t["parameters"]
    assert isinstance(params, dict)
    props = params.get("properties") or {}
    assert "summary" in props
    assert props["summary"]["type"] == "string"


def test_to_openai_tool_summary_always_added(tool):
    """测试汇总字段是否始终添加到 OpenAI 工具模式。"""
    t = tool.to_openai_tool()
    func = t.get("function")
    assert func is not None
    params = func.get("parameters")
    assert isinstance(params, dict)
    props = params.get("properties") or {}
    assert "summary" in props
    assert props["summary"]["type"] == "string"


def test_mcp_tool_with_summary_param_preserves_original_description():
    """模式注入不得影响工具自己的“摘要”字段。"""
    mcp_tool = mcp.types.Tool(
        name="jira_create_issue",
        description="Create a Jira issue",
        inputSchema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "summary": {
                    "type": "string",
                    "description": "Ticket title",
                },
                "issue_type": {"type": "string"},
            },
            "required": ["project_key", "summary", "issue_type"],
        },
    )
    client = Mock(spec=MCPClient)
    tool = MCPToolDefinition.create(mcp_tool, client)[0]

    openai_tool = tool.to_openai_tool()
    func = openai_tool.get("function")
    assert func is not None
    params = func.get("parameters")
    assert isinstance(params, dict)
    props = params.get("properties") or {}

    # 工具自己的“摘要”字段应与其原始描述一起出现，不 SDK 的元摘要描述。
    #
    assert "summary" in props
    assert props["summary"]["description"] == "Ticket title"
