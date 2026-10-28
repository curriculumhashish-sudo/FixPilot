"""测试 openhands.sdk.tool.schema 中的 MCP 模式代。"""

import json
from collections.abc import Sequence
from typing import Any, ClassVar

import pytest
from pydantic import Field

from openhands.sdk.llm import ImageContent, TextContent
from openhands.sdk.tool.schema import Action, Observation, Schema, _process_schema_node


class MCPSchemaTestAction(Action):
    """用于 MCP 模式测试的测试操作类。"""

    command: str = Field(description="Command to execute")
    optional_field: str | None = Field(default=None, description="Optional field")


class MCPComplexAction(Action):
    """复杂类型的操作。"""

    simple_field: str = Field(description="Simple string field")
    optional_int: int | None = Field(default=None, description="Optional integer")
    string_list: list[str] = Field(default_factory=list, description="List of strings")


class CustomAliasedAction(Action):
    mcp_schema_alias_specs: ClassVar[dict[str, dict[str, Any]]] = {
        "extra_field": {"type": "string"}
    }
    mcp_schema_alias_required: ClassVar[set[str]] = {"extra_field"}


class MCPSchemaTestObservation(Observation):
    """测试观测结果类进行 MCP 模式测试。"""

    result: str = Field(description="Result of the action")

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text=self.result)]


def test_action_to_mcp_schema_excludes_kind():
    """测试 Action.to_mcp_schema() 是否排除 'kind' 字段。"""
    schema = MCPSchemaTestAction.to_mcp_schema()

    # “kind”字段不应出现在属性中
    assert "kind" not in schema["properties"], (
        "'kind' field should not be present in MCP schema properties"
    )

    # “种类”字段不应为必填字段
    if "required" in schema:
        assert "kind" not in schema["required"], (
            "'kind' field should not be present in MCP schema required list"
        )


def test_action_to_mcp_schema_includes_actual_fields():
    """测试 to_mcp_schema() 是否包含实际操作字段。"""
    schema = MCPSchemaTestAction.to_mcp_schema()

    # 应包含实际字段
    assert "command" in schema["properties"]
    assert "optional_field" in schema["properties"]

    # 检查字段描述
    assert schema["properties"]["command"]["description"] == "Command to execute"
    assert schema["properties"]["optional_field"]["description"] == "Optional field"

    # 必填字段应正确标记
    assert "command" in schema["required"]


def test_observation_to_mcp_schema_excludes_kind():
    """测试 Observation.to_mcp_schema() 是否排除 'kind' 字段。"""
    schema = MCPSchemaTestObservation.to_mcp_schema()

    # “kind”字段不应出现在属性中
    assert "kind" not in schema["properties"], (
        "'kind' field should not be present in MCP schema properties"
    )

    # “种类”字段不应为必填字段
    if "required" in schema:
        assert "kind" not in schema["required"], (
            "'kind' field should not be present in MCP schema required list"
        )


def test_complex_action_to_mcp_schema_excludes_kind():
    """测试复杂的操作类型是否也排除“kind”字段。"""
    schema = MCPComplexAction.to_mcp_schema()

    # “kind”字段不应出现在属性中
    assert "kind" not in schema["properties"], (
        "'kind' field should not be present in MCP schema properties"
    )

    # 应包含所有实际字段
    assert "simple_field" in schema["properties"]
    assert "optional_int" in schema["properties"]
    assert "string_list" in schema["properties"]

    # 检查类型是否正确
    assert schema["properties"]["simple_field"]["type"] == "string"
    assert schema["properties"]["optional_int"]["type"] == "integer"
    assert schema["properties"]["string_list"]["type"] == "array"


def test_mcp_schema_structure():
    """测试 MCP 模式的结构是否正确。"""
    schema = MCPSchemaTestAction.to_mcp_schema()

    # 应该有类型和属性
    assert schema["type"] == "object"
    assert "properties" in schema
    assert isinstance(schema["properties"], dict)

    # 如果提供的话应该有描述
    assert "description" in schema
    assert schema["description"] == "Test action class for MCP schema testing."

    # 应该有需要的清单
    assert "required" in schema
    assert isinstance(schema["required"], list)


def test_kind_field_works_for_discriminated_union():
    """测试“kind”字段是否仍然适用于内部受歧视的工会。"""
    # 创建一个实例 - 这应该可以正常工作
    action = MCPSchemaTestAction(command="test")

    # 该实例应正确设置“kind”字段
    assert hasattr(action, "kind")
    assert action.kind == "MCPSchemaTestAction"

    # 序列化应包括“种类”
    dumped = action.model_dump()
    assert "kind" in dumped
    assert dumped["kind"] == "MCPSchemaTestAction"

    # 反序列化应该与“kind”一起使用
    data = {"kind": "MCPSchemaTestAction", "command": "test"}
    restored = MCPSchemaTestAction.model_validate(data)
    assert restored.command == "test"
    assert restored.kind == "MCPSchemaTestAction"


class TestCircularSchemaHandling:
    """测试工具模式中处理循环 $ref 模式。

    这些测试验证了循环模式可以在没有 RecursionError 的情况下得到妥善处理。 当检测到循
    环引用时，通用
    {"type": "object"} placeholder is returned.

    Related: Datadog 对话 ab9909a07571431a86ab6f1be36f555f 的日志
    """

    def test_circular_ref_returns_generic_object(self):
        """测试循环引用处理是否返回通用对象。

        当检测到循环引用时，该函数返回一个简单的
        {"type": "object"} placeholder to prevent infinite recursion.
        """
        circular_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "children": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/TreeNode"},
                },
            },
            "$defs": {
                "TreeNode": {
                    "type": "object",
                    "description": "A tree node",
                    "properties": {
                        "name": {"type": "string", "description": "Node name"},
                        "children": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/TreeNode"},
                            "description": "Child nodes",
                        },
                    },
                }
            },
        }

        defs = circular_schema.get("$defs", {})
        result = _process_schema_node(circular_schema, defs)

        # 验证基本结构
        assert result["type"] == "object"
        assert "properties" in result

        # 应保留顶级“名称”
        assert result["properties"]["name"]["type"] == "string"

        # 'children' 数组应该存在
        assert result["properties"]["children"]["type"] == "array"

        # 儿童中的项目应扩展TreeNodes（第一级）
        items = result["properties"]["children"]["items"]
        assert items["type"] == "object"
        assert "properties" in items

        # 应保留 TreeNode 的“名称”属性（第一级）
        assert "name" in items["properties"]
        assert items["properties"]["name"]["type"] == "string"

        # TreeNode 的“孩子”应该是一个数组
        assert "children" in items["properties"]
        assert items["properties"]["children"]["type"] == "array"

        # 嵌套项目（循环引用）应该是通用对象
        nested_items = items["properties"]["children"]["items"]
        assert nested_items["type"] == "object"
        # 描述从 ref 定义中保留
        assert nested_items.get("description") == "A tree node"

        # 应该是 JSON 可序列化
        json.dumps(result)

    def test_tree_schema_to_mcp_works(self):
        """测试自引用 Pydantic 模式是否可以转换为 MCP 模式。

        这是现实世界的场景：具有自引用字段（如树节点）的 Pydantic 模型应该可以在没有
        RecursionError 的情况下进行转换。
        """

        class TreeNode(Schema):
            """可以具有相同类型的子节点的树节点。"""

            value: str = Field(description="The value of this node")
            children: list["TreeNode"] | None = Field(
                default=None, description="Child nodes"
            )

        TreeNode.model_rebuild()

        result = TreeNode.to_mcp_schema()

        # 验证结果结构
        assert result["type"] == "object"
        assert "properties" in result

        # “值”字段应完全保留
        assert "value" in result["properties"]
        assert result["properties"]["value"]["type"] == "string"
        assert result["properties"]["value"]["description"] == "The value of this node"

        # “children”字段应以数组形式出现
        assert "children" in result["properties"]
        children_prop = result["properties"]["children"]
        assert children_prop["type"] == "array"

        # 这些项目应该是对象（循环引用返回通用对象）
        assert children_prop["items"]["type"] == "object"

        # 应该是 JSON 可序列化
        json.dumps(result)

    def test_deeply_nested_non_circular_schema_fully_resolved(self):
        """测试深度嵌套但非循环的模式是否已完全解析。

        这确保我们在修复循环引用问题时不会破坏有效的深层嵌套模式。
        """
        deep_schema = {
            "type": "object",
            "properties": {
                "level1": {
                    "type": "object",
                    "properties": {
                        "level2": {
                            "type": "object",
                            "properties": {
                                "level3": {
                                    "type": "object",
                                    "properties": {
                                        "value": {"type": "string"},
                                    },
                                }
                            },
                        }
                    },
                }
            },
        }

        result = _process_schema_node(deep_schema, {})

        # 验证完整嵌套是否保留
        assert result["type"] == "object"
        level1 = result["properties"]["level1"]
        assert level1["type"] == "object"
        level2 = level1["properties"]["level2"]
        assert level2["type"] == "object"
        level3 = level2["properties"]["level3"]
        assert level3["type"] == "object"
        assert level3["properties"]["value"]["type"] == "string"

        json.dumps(result)

    def test_non_circular_ref_fully_resolved(self):
        """测试带有非循环 $ref 的模式是否已完全解析。"""
        schema = {
            "type": "object",
            "properties": {
                "address": {"$ref": "#/$defs/Address"},
            },
            "$defs": {
                "Address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                        "city": {"type": "string"},
                    },
                }
            },
        }

        defs = schema.get("$defs", {})
        result = _process_schema_node(schema, defs)

        # 应该完全解决 $ref
        assert result["type"] == "object"
        address = result["properties"]["address"]
        assert address["type"] == "object"
        assert address["properties"]["street"]["type"] == "string"
        assert address["properties"]["city"]["type"] == "string"

        json.dumps(result)

    def test_circular_ref_does_not_raise_recursion_error(self):
        """测试循环 $ref 不会导致 RecursionError。"""
        circular_schema = {
            "type": "object",
            "properties": {
                "children": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/Node"},
                },
            },
            "$defs": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "children": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/Node"},
                        },
                    },
                }
            },
        }

        defs = circular_schema.get("$defs", {})

        # 不应提高 RecursionError
        result = _process_schema_node(circular_schema, defs)

        # 验证有效输出
        assert result["type"] == "object"
        assert "properties" in result
        json.dumps(result)

    def test_linked_list_schema_to_mcp_works(self):
        """测试链表模式可以转换为MCP模式。"""

        class LinkedListNode(Schema):
            """具有可选下一个指针的链表节点。"""

            value: int = Field(description="The value")
            next: "LinkedListNode | None" = Field(default=None, description="Next node")

        LinkedListNode.model_rebuild()

        result = LinkedListNode.to_mcp_schema()

        # 验证结构
        assert result["type"] == "object"
        assert "value" in result["properties"]
        assert result["properties"]["value"]["type"] == "integer"
        assert result["properties"]["value"]["description"] == "The value"

        # “下一个”应该存在（作为简化的对象）
        assert "next" in result["properties"]
        assert result["properties"]["next"]["type"] == "object"

        json.dumps(result)


@pytest.mark.parametrize(
    ("node", "expected"),
    [
        ({"type": "array", "items": True}, {"type": "array", "items": {}}),
        ({"type": "array", "items": False}, {"type": "array", "items": {"not": {}}}),
        ({"anyOf": [True, {"type": "null"}]}, {}),
        # ``anyOf: [true, X]`` 验证任何实例，因此它不能缩小到 X。
        ({"anyOf": [True, {"type": "string"}]}, {}),
        # ``false`` 永远不会验证，因此具体分支在任何位置都会获胜。
        ({"anyOf": [{"type": "string"}, False]}, {"type": "string"}),
        ({"anyOf": [False, {"type": "string"}]}, {"type": "string"}),
        # 由于没有留下可行的分支，``false`` 保持其拒绝所有的含义。
        ({"anyOf": [False]}, {"not": {}}),
        (
            {"type": "object", "properties": {"anything": True}},
            {"type": "object", "properties": {"anything": {}}},
        ),
        (
            {
                "type": "object",
                "properties": {
                    "cursor": {
                        "description": "Pagination cursor",
                        "anyOf": [{"type": "array", "items": True}, {"type": "null"}],
                    }
                },
            },
            {
                "type": "object",
                "properties": {
                    "cursor": {
                        "type": "array",
                        "items": {},
                        "description": "Pagination cursor",
                    }
                },
            },
        ),
    ],
)
def test_boolean_schema_nodes_are_normalized(node, expected):
    """布尔子模式标准化为它们的对象等价物。

    ``true`` 接受任何值，``false`` 接受 None； 只要需要模式，两者都是有效的。
    """
    result = _process_schema_node(node, {})

    assert result == expected
    json.dumps(result)


def test_anyof_with_false_does_not_clobber_concrete_type():
    """``anyOf`` 中的 ``false`` 成员不得成为代表类型。

    JSON  模式  ``false`` 意味着“拒绝一切” ``anyOf`` 在常见的具体类型中模式由
    TypeScript/MCP 服务器），处理器必须选择具
    体的类型，而不是
    ``false``. 之前处理过的过滤器 ``not isinstance(t, dict)``
    ``False`` 作为非 null 类型，因此返回 ``_process_schema_node(False)``
    ``{"not": {}}`` — 使参数不可能满足 LLM。
    """
    schema = {
        "type": "object",
        "properties": {
            "value": {
                "anyOf": [False, {"type": "string"}],
            },
        },
    }
    result = _process_schema_node(schema, {})
    assert result["properties"]["value"] == {"type": "string"}


@pytest.mark.parametrize(
    "member",
    [5, "str", None, [], 1.5],
)
def test_anyof_ignores_non_schema_members(member):
    """格式错误的 ``anyOf`` 成员必须被跳过，而不是使转换崩溃。

    来自第三方 MCP 服务器的 ``inputSchema`` 被馈送到
    ``_process_schema_node`` 逐字记录，并且产生的异常转义
    ``LLM.get_token_count`` 未捕获。 任何不是模式（字典或布尔值）的东西会被忽略，而不
    是引发 ``TypeError``
    /``AttributeError``.
    """
    assert _process_schema_node({"anyOf": [member]}, {}) == {}
    assert _process_schema_node({"anyOf": [member, {"type": "string"}]}, {}) == {
        "type": "string"
    }


def test_schema_mcp_aliases_use_declared_class_apis():
    """模式声明 mcp_schema_alias_specs 和 mcp_schema_alias_required。"""
    assert Schema.mcp_schema_alias_specs == {}
    assert Schema.mcp_schema_alias_required == set()

    mcp_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "custom_alias": {"type": "integer"},
        },
        "required": ["query", "custom_alias"],
    }
    model = Action.from_mcp_schema("GeneratedAction", mcp_schema)
    assert issubclass(model, Schema)
    assert model.mcp_schema_alias_specs == {}
    assert model.mcp_schema_alias_required == set()

    exported = CustomAliasedAction.to_mcp_schema()
    assert "extra_field" in exported.get("properties", {})
    assert "extra_field" in exported.get("required", [])
