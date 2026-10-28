"""回归测试 MCP 工具嵌套模式保存。

测试了 MCP 工具的嵌套对象参数保留其完整值 JSON  模式结构（属性，必填项） 枚举，arrays
) in the LLM- facing 模式由生成的
``to_openai_tool()`` 和
``to_responses_tool()``.

回归覆盖范围：
    https://github.com/OpenHands/software-agent-sdk/issues/3955
"""

import json
from typing import Any, ClassVar
from unittest.mock import MagicMock

import mcp.types

from openhands.sdk.mcp.definition import MCPToolAction
from openhands.sdk.mcp.tool import MCPToolDefinition, MCPToolExecutor


class DummyExecutor(MCPToolExecutor):
    """满足MCPToolDefinition.create()的最小执行器。"""

    def __init__(self):
        self.tool_name = "dummy"
        self.client = MagicMock()
        self.timeout = 300


def _make_tool(
    name: str, input_schema: dict[str, Any], description: str = "test"
) -> MCPToolDefinition:
    """构建一个 MCPToolDefinition 从原始的 inputSchema dict."""
    mcp_tool = mcp.types.Tool(
        name=name,
        description=description,
        inputSchema=input_schema,
    )
    return MCPToolDefinition(
        description=description,
        action_type=MCPToolAction,
        observation_type=None,
        executor=DummyExecutor(),
        mcp_tool=mcp_tool,
    )


def _get_params(tool: MCPToolDefinition, **kwargs: Any) -> dict[str, Any]:
    """从生成的 OpenAI 工具中提取 ``parameters`` 字典。"""
    openai_tool = tool.to_openai_tool(**kwargs)
    return dict(openai_tool)["function"]["parameters"]  # type: ignore[index]


# ---------------------------------------------------------------------------
# 问题 #3955 的精确复制
# ---------------------------------------------------------------------------


class TestNestedObjectPreservation:
    """MCP 具有嵌套对象参数的工具必须保留其完整的
    JSON 模式结构位于 LLM 面向模式。
    """

    INPUT_SCHEMA: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "definition": {
                "description": "Component model ID",
                "type": "string",
            },
            "position": {
                "description": "Component position",
                "type": "object",
                "properties": {
                    "0": {"type": "number"},
                    "1": {"type": "number"},
                },
                "required": ["0", "1"],
            },
        },
        "required": ["definition", "position"],
    }

    def _get_position_field(self, add_security_risk: bool = False) -> dict[str, Any]:
        """从生成的模式中提取 ``position`` 字段。"""
        tool = _make_tool("add_diagram_component", self.INPUT_SCHEMA)
        params = _get_params(tool, add_security_risk_prediction=add_security_risk)
        return params["properties"]["position"]

    def test_nested_properties_preserved(self) -> None:
        """Regression: position.properties 不得被展平。"""
        position = self._get_position_field()
        assert "properties" in position, (
            "Nested object properties were lost in LLM-facing schema "
            f"(got {json.dumps(position)})"
        )
        assert position["properties"]["0"] == {"type": "number"}
        assert position["properties"]["1"] == {"type": "number"}

    def test_nested_required_preserved(self) -> None:
        """Regression: position.required 不得删除。"""
        position = self._get_position_field()
        assert "required" in position
        assert set(position["required"]) == {"0", "1"}

    def test_nested_description_preserved(self) -> None:
        """嵌套对象的描述应该保留。"""
        position = self._get_position_field()
        assert position.get("description") == "Component position"

    def test_with_security_risk(self) -> None:
        """添加 security_risk 后，嵌套属性必须保留。"""
        position = self._get_position_field(add_security_risk=True)
        assert "properties" in position
        assert set(position["required"]) == {"0", "1"}

    def test_responses_tool_preserves_nested(self) -> None:
        """to_responses_tool() 还必须保留嵌套属性。"""
        tool = _make_tool("add_diagram_component", self.INPUT_SCHEMA)
        responses_tool = tool.to_responses_tool()
        params: dict[str, Any] = responses_tool["parameters"]  # type: ignore[assignment]
        position = params["properties"]["position"]
        assert "properties" in position
        assert position["properties"]["0"] == {"type": "number"}
        assert position["properties"]["1"] == {"type": "number"}
        assert set(position["required"]) == {"0", "1"}


# ---------------------------------------------------------------------------
# 更深层次的嵌套和混合型模式
# ---------------------------------------------------------------------------


class TestDeeplyNestedSchema:
    """模式具有多层嵌套。"""

    def test_three_level_nesting(self) -> None:
        """深三层：工具 -> 配置 -> 主题 -> 颜色。"""
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "description": "App configuration",
                    "properties": {
                        "theme": {
                            "type": "object",
                            "description": "Theme settings",
                            "properties": {
                                "primary": {"type": "string"},
                                "secondary": {"type": "string"},
                            },
                            "required": ["primary"],
                        }
                    },
                    "required": ["theme"],
                }
            },
            "required": ["config"],
        }
        tool = _make_tool("configure_app", schema)
        params = _get_params(tool)
        config = params["properties"]["config"]
        assert "properties" in config
        theme = config["properties"]["theme"]
        assert "properties" in theme
        assert theme["properties"]["primary"] == {"type": "string"}
        assert theme["properties"]["secondary"] == {"type": "string"}
        assert theme["required"] == ["primary"]
        assert config["required"] == ["theme"]

    def test_nested_array_of_objects(self) -> None:
        """应保留具有对象模式的数组项。"""
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "List of entries",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "label": {"type": "string"},
                        },
                        "required": ["id"],
                    },
                }
            },
        }
        tool = _make_tool("batch_create", schema)
        params = _get_params(tool)
        items_field = params["properties"]["items"]
        assert items_field["type"] == "array"
        item_schema = items_field["items"]
        assert "properties" in item_schema
        assert item_schema["properties"]["id"] == {"type": "integer"}
        assert item_schema["required"] == ["id"]


# ---------------------------------------------------------------------------
# OpenHands-注入字段
# ---------------------------------------------------------------------------


class TestInjectedFields:
    """验证 OpenHands 特定字段（security_risk，摘要）
    与嵌套的 MCP 属性一起正确注入。
    """

    SIMPLE_NESTED: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "data": {
                "type": "object",
                "properties": {"x": {"type": "number"}},
            }
        },
    }

    def test_summary_injected(self) -> None:
        """摘要必须出现在LLM模式中。"""
        tool = _make_tool("test_tool", self.SIMPLE_NESTED)
        params = _get_params(tool)
        assert "summary" in params["properties"]

    def test_security_risk_injected(self) -> None:
        """security_risk 必须在请求时出现。"""
        tool = _make_tool("test_tool", self.SIMPLE_NESTED)
        params = _get_params(tool, add_security_risk_prediction=True)
        assert "security_risk" in params["properties"]
        sr = params["properties"]["security_risk"]
        assert "enum" in sr
        assert "UNKNOWN" in sr["enum"]

    def test_security_risk_not_injected_for_readonly(self) -> None:
        """只读工具应该不得到 security_risk。"""
        from openhands.sdk.tool import ToolAnnotations

        mcp_tool = mcp.types.Tool(
            name="readonly_tool",
            description="read only",
            inputSchema=self.SIMPLE_NESTED,
        )
        tool = MCPToolDefinition(
            description="read only",
            action_type=MCPToolAction,
            observation_type=None,
            executor=DummyExecutor(),
            mcp_tool=mcp_tool,
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        params = _get_params(tool, add_security_risk_prediction=True)
        assert "security_risk" not in params["properties"]

    def test_summary_not_injected_when_tool_declares_summary(self) -> None:
        """如果 MCP 工具本身声明了一个“摘要”参数 (e.g.,
        Jira 票证标题），我们的元摘要不得掩盖它。
        """
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Jira ticket title",
                },
                "body": {"type": "string"},
            },
            "required": ["summary"],
        }
        tool = _make_tool("create_ticket", schema)
        params = _get_params(tool)
        # 必须保留该工具自己的摘要，而不是替换
        assert params["properties"]["summary"]["description"] == "Jira ticket title"

    def test_priority_ordering(self) -> None:
        """security_risk 和摘要应出现在工具参数之前。"""
        tool = _make_tool("test_tool", self.SIMPLE_NESTED)
        params = _get_params(tool, add_security_risk_prediction=True)
        keys = list(params["properties"].keys())
        # security_risk 和摘要应该是前两个
        assert keys[0] == "security_risk"
        assert keys[1] == "summary"


# ---------------------------------------------------------------------------
# 公寓模式仍然有效
# ---------------------------------------------------------------------------


class TestFlatSchemaUnchanged:
    """扁平（非嵌套）MCP 模式应该仍然可以正常工作。"""

    def test_flat_string_params(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results"},
            },
            "required": ["query"],
        }
        tool = _make_tool("search", schema)
        params = _get_params(tool)
        assert params["properties"]["query"] == {
            "type": "string",
            "description": "Search query",
        }
        assert params["properties"]["limit"] == {
            "type": "integer",
            "description": "Max results",
        }
        assert "query" in params["required"]

    def test_empty_properties(self) -> None:
        """根本没有属性的工具。"""
        schema: dict[str, Any] = {"type": "object"}
        tool = _make_tool("no_args", schema)
        params = _get_params(tool)
        # 仍应注入摘要
        assert "summary" in params["properties"]
