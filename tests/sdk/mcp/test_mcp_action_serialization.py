import pytest
from pydantic import ValidationError

from openhands.sdk.mcp import MCPToolAction


class _ChildMCPToolActionForSerialization(MCPToolAction):
    """子 MCP 操作，用于使用数据测试声明的字段。

    此类在模块级别定义（而不是在测试函数内部），以确保它在序列化/反序列化期间可由
    Pydantic 导入。 当与 pytest-xdist 并行运行测试时，在测试函数
    中定义它会导致测试污染。
    """

    declared: int


def test_data_field_emerges_from_to_mcp_arguments():
    """测试数据字段内容是否由 to_mcp_arguments 返回。"""
    data = {"new_field": "value", "dynamic": 123}
    a = MCPToolAction(data=data)
    out = a.to_mcp_arguments()

    # 应返回数据字段内容
    assert out["new_field"] == "value"
    assert out["dynamic"] == 123
    assert out == data


def test_declared_child_fields_with_data():
    """测试子类是否可以使用数据字段。"""
    data = {"tool_param": "value"}
    a = _ChildMCPToolActionForSerialization(declared=7, data=data)
    out = a.to_mcp_arguments()

    # 只有数据字段内容应位于 MCP 参数中
    assert out == {"tool_param": "value"}
    # 声明的字段应该是可访问的，但不能在 MCP 参数中访问
    assert a.declared == 7


def test_empty_data_field():
    """使用空数据字段测试行为。"""
    a = MCPToolAction()
    out = a.to_mcp_arguments()
    assert out == {}


def test_data_field_with_none_values():
    """测试数据中的 None 值是否被保留。"""
    data = {"keep_me": "ok", "drop_me": None}
    a = MCPToolAction(data=data)
    out = a.to_mcp_arguments()
    assert out.get("keep_me") == "ok"
    assert out.get("drop_me") is None  # None 值保存在数据中


def test_frozen_model_is_immutable():
    """测试 MCPToolAction 是不可变的。"""
    a = MCPToolAction(data={"x": 1})
    with pytest.raises(ValidationError):
        a.data = {"y": 2}  # type: ignore


def test_data_field_type_validation():
    """测试数据字段接受 dict[str、Any]。"""
    # 有效数据
    a = MCPToolAction(data={"string": "value", "number": 123, "bool": True})
    assert a.data == {"string": "value", "number": 123, "bool": True}

    # 空字典有效
    b = MCPToolAction(data={})
    assert b.data == {}


def test_extra_fields_not_allowed():
    """测试数据之外不允许有额外的字段。"""
    with pytest.raises(ValidationError):
        MCPToolAction(extra_field="not_allowed")  # type: ignore
