"""测试工具 JSON 序列化和 DiscriminatedUnionMixin。"""

import json

import pytest
from pydantic import BaseModel

from openhands.sdk.tool import ToolDefinition
from openhands.sdk.tool.builtins import FinishTool, ThinkTool


def test_tool_serialization_deserialization() -> None:
    """测试工具是否支持多态 JSON 序列化/反序列化。"""
    # 使用 FinishTool 这个简单的内置工具
    tool_instances = FinishTool.create()
    tool = tool_instances[0]

    # 序列化至JSON
    tool_json = tool.model_dump_json()

    # 反序列化来自 JSON 使用基类
    deserialized_tool = ToolDefinition.model_validate_json(tool_json)

    # 应该反序列化为具有相同可序列化数据的正确类型
    assert isinstance(deserialized_tool, ToolDefinition)
    assert tool.model_dump() == deserialized_tool.model_dump()


def test_tool_supports_polymorphic_field_json_serialization() -> None:
    """测试 Tool 在用作字段时是否支持多态 JSON 序列化。"""

    class Container(BaseModel):
        tool: ToolDefinition

    # 使用工具创建容器
    tool_instances = FinishTool.create()
    tool = tool_instances[0]
    container = Container(tool=tool)

    # 序列化至JSON
    container_json = container.model_dump_json()

    # 反序列化来自 JSON
    deserialized_container = Container.model_validate_json(container_json)

    # 应保留具有相同可序列化数据的工具类型
    assert isinstance(deserialized_container.tool, ToolDefinition)
    assert tool.model_dump() == deserialized_container.tool.model_dump()


def test_tool_supports_nested_polymorphic_json_serialization() -> None:
    """测试 Tool 是否支持嵌套多态 JSON 序列化。"""

    class NestedContainer(BaseModel):
        tools: list[ToolDefinition]

    # 使用多种工具创建容器
    tool1_instances = FinishTool.create()
    tool1 = tool1_instances[0]
    tool2_instances = ThinkTool.create()
    tool2 = tool2_instances[0]
    container = NestedContainer(tools=[tool1, tool2])

    # 序列化至JSON
    container_json = container.model_dump_json()

    # 反序列化来自 JSON
    deserialized_container = NestedContainer.model_validate_json(container_json)

    # 应保留具有相同可序列化数据的所有工具类型
    assert len(deserialized_container.tools) == 2
    assert isinstance(deserialized_container.tools[0], ToolDefinition)
    assert isinstance(deserialized_container.tools[1], ToolDefinition)
    assert tool1.model_dump() == deserialized_container.tools[0].model_dump()
    assert tool2.model_dump() == deserialized_container.tools[1].model_dump()


def test_tool_model_validate_json_dict() -> None:
    """测试 Tool.model_validate 是否适用于 JSON 中的 dict。"""
    # 创建工具
    tool_instances = FinishTool.create()
    tool = tool_instances[0]

    # 序列化到JSON，然后解析为dict
    tool_json = tool.model_dump_json()
    tool_dict = json.loads(tool_json)

    # 反序列化来自字典
    deserialized_tool = ToolDefinition.model_validate(tool_dict)

    # 应该具有相同的可序列化数据
    assert isinstance(deserialized_tool, ToolDefinition)
    assert tool.model_dump() == deserialized_tool.model_dump()


def test_tool_no_fallback_behavior_json() -> None:
    """在 JSON 中测试 Tool 是否能够优雅地处理未知类型。"""
    # 创建类型未知的 JSON
    tool_dict = {
        "name": "test-tool",
        "description": "A test tool",
        "action_type": "FinishAction",
        "observation_type": None,
        "kind": "UnknownToolType",
    }
    tool_json = json.dumps(tool_dict)

    with pytest.raises(
        ValueError, match="Unexpected kind 'UnknownToolType' for ToolDefinition"
    ):
        ToolDefinition.model_validate_json(tool_json)


def test_tool_type_annotation_works_json() -> None:
    """测试 ToolType 注释是否与 JSON 一起正常工作。"""
    # 创建工具
    tool_instances = FinishTool.create()
    tool = tool_instances[0]

    # 使用ToolType注释
    class TestModel(BaseModel):
        tool: ToolDefinition

    model = TestModel(tool=tool)

    # 序列化至JSON
    model_json = model.model_dump_json()

    # 反序列化来自 JSON
    deserialized_model = TestModel.model_validate_json(model_json)

    # 应该使用相同的可序列化数据正确工作
    assert isinstance(deserialized_model.tool, ToolDefinition)
    assert tool.model_dump() == deserialized_model.tool.model_dump()


def test_tool_kind_field_json() -> None:
    """测试工具种类字段通过JSON正确设置和保存。"""
    # 创建工具
    tool_instances = FinishTool.create()
    tool = tool_instances[0]

    # 检查种类字段
    assert hasattr(tool, "kind")
    expected_kind = tool.__class__.__name__
    assert tool.kind == expected_kind

    # 序列化至JSON
    tool_json = tool.model_dump_json()

    # 反序列化来自 JSON
    deserialized_tool = ToolDefinition.model_validate_json(tool_json)

    # 应该保留善良的田野
    assert hasattr(deserialized_tool, "kind")
    assert deserialized_tool.kind == tool.kind
