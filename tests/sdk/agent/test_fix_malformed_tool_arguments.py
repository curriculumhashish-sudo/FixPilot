"""测试 fix_malformed_tool_arguments 辅助函数。

该模块测试了 fix_malformed_tool_arguments 自动解码的辅助工具 JSON 列表/字典字段的字符
串。 这处理了这种情况 LLMs (like GL
M返回数组/对象值 JSON 字符串而不是原生 JSON 数组/对象。
"""

from typing import Annotated

import pytest
from pydantic import Field, ValidationError

from openhands.sdk.agent.utils import fix_malformed_tool_arguments
from openhands.sdk.tool.schema import Action


class JsonDecodingTestAction(Action):
    """使用列表和字典字段测试操作。"""

    items: list[str] = Field(description="A list of items")
    config: dict[str, int] = Field(description="Configuration dictionary")
    name: str = Field(description="A regular string field")


class JsonDecodingAnnotatedAction(Action):
    """使用带注释的类型测试操作。"""

    items: Annotated[list[str], Field(description="A list of items")]
    config: Annotated[dict[str, int], Field(description="Configuration dictionary")]


class JsonDecodingAliasAction(Action):
    """使用字段别名测试操作。"""

    my_list: list[int] = Field(alias="myList", description="A list with alias")
    my_dict: dict[str, str] = Field(alias="myDict", description="A dict with alias")


class JsonDecodingOptionalAction(Action):
    """使用可选列表/字典字段测试操作。"""

    items: list[str] | None = Field(default=None, description="Optional list")
    config: dict[str, int] | None = Field(default=None, description="Optional dict")


class StrFieldAction(Action):
    """使用仅 str 字段（镜像 file_editor old_str/new_str）测试操作。"""

    old_str: str | None = Field(default=None, description="A required string field")
    name: str = Field(description="A regular string field")


class StrOrListAction(Action):
    """使用接受 str 或列表的字段测试操作。"""

    value: str | list[str] = Field(description="A str-or-list field")


class _NestedActionForMalformedArgs(Action):
    """用于测试 JSON 解码的嵌套结构的操作。

    此类在模块级别定义（而不是在测试函数内部），以确保它在序列化/反序列化期间可由
    Pydantic 导入。 当与 pytest-xdist 并行运行测试时，在测试函数
    中定义它会导致测试污染。
    """

    nested_list: list[list[int]] = Field(description="Nested list")
    nested_dict: dict[str, dict[str, str]] = Field(description="Nested dict")


def test_decode_json_string_list():
    """测试 JSON 字符串列表是否已解码为本机列表。"""
    data = {
        "items": '["a", "b", "c"]',
        "config": '{"x": 1, "y": 2}',
        "name": "test",
    }
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingTestAction)
    action = JsonDecodingTestAction.model_validate(fixed_data)

    assert action.items == ["a", "b", "c"]
    assert action.config == {"x": 1, "y": 2}
    assert action.name == "test"


def test_decode_json_string_dict():
    """测试 JSON 字符串字典是否已解码为本机字典。"""
    data = {
        "items": '["item1", "item2"]',
        "config": '{"key1": 10, "key2": 20}',
        "name": "dict_test",
    }
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingTestAction)
    action = JsonDecodingTestAction.model_validate(fixed_data)

    assert action.items == ["item1", "item2"]
    assert action.config == {"key1": 10, "key2": 20}
    assert action.name == "dict_test"


def test_native_list_dict_passthrough():
    """测试本机列表和字典是否不变地通过。"""
    data = {
        "items": ["direct", "list"],
        "config": {"direct": 42},
        "name": "native_test",
    }
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingTestAction)
    action = JsonDecodingTestAction.model_validate(fixed_data)

    assert action.items == ["direct", "list"]
    assert action.config == {"direct": 42}
    assert action.name == "native_test"


def test_regular_string_not_decoded():
    """测试常规字符串字段是否不受 JSON 解码的影响。"""
    data = {
        "items": "[]",
        "config": "{}",
        "name": "this is not json but a regular string",
    }
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingTestAction)
    action = JsonDecodingTestAction.model_validate(fixed_data)

    assert action.items == []
    assert action.config == {}
    # 常规字符串字段应不进行解码
    assert action.name == "this is not json but a regular string"


def test_annotated_types():
    """测试带注释的类型是否得到正确处理。"""
    data = {
        "items": '["x", "y", "z"]',
        "config": '{"a": 1, "b": 2}',
    }
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingAnnotatedAction)
    action = JsonDecodingAnnotatedAction.model_validate(fixed_data)

    assert action.items == ["x", "y", "z"]
    assert action.config == {"a": 1, "b": 2}


def test_field_aliases():
    """测试字段别名是否得到正确处理。"""
    data = {
        "myList": "[1, 2, 3]",
        "myDict": '{"key": "value"}',
    }
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingAliasAction)
    action = JsonDecodingAliasAction.model_validate(fixed_data)

    assert action.my_list == [1, 2, 3]
    assert action.my_dict == {"key": "value"}


def test_optional_fields_with_json_strings():
    """测试可选列表/字典字段是否适用于 JSON 字符串。"""
    data = {
        "items": '["opt1", "opt2"]',
        "config": '{"opt": 99}',
    }
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingOptionalAction)
    action = JsonDecodingOptionalAction.model_validate(fixed_data)

    assert action.items == ["opt1", "opt2"]
    assert action.config == {"opt": 99}


def test_optional_fields_with_none():
    """测试可选字段是否可以为 None。"""
    data = {}
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingOptionalAction)
    action = JsonDecodingOptionalAction.model_validate(fixed_data)

    assert action.items is None
    assert action.config is None


def test_optional_fields_with_native_values():
    """测试可选字段是否适用于本机值。"""
    data = {
        "items": ["native1", "native2"],
        "config": {"native": 100},
    }
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingOptionalAction)
    action = JsonDecodingOptionalAction.model_validate(fixed_data)

    assert action.items == ["native1", "native2"]
    assert action.config == {"native": 100}


def test_invalid_json_string_rejected():
    """测试无效的 JSON 字符串是否被拒绝并出现验证错误。"""
    data = {
        "items": "not valid json",
        "config": "{}",
        "name": "test",
    }
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingTestAction)

    with pytest.raises(ValidationError) as exc_info:
        JsonDecodingTestAction.model_validate(fixed_data)

    # 应该失败验证，因为“无效 JSON”无法解析为列表
    assert "items" in str(exc_info.value)


def test_json_string_with_wrong_type_rejected():
    """测试类型错误的 JSON 字符串是否被拒绝。"""
    # 字段需要列表，但 JSON 字符串包含字典
    data = {
        "items": '{"not": "a list"}',
        "config": "{}",
        "name": "test",
    }
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingTestAction)

    with pytest.raises(ValidationError) as exc_info:
        JsonDecodingTestAction.model_validate(fixed_data)

    assert "items" in str(exc_info.value)


def test_nested_structures():
    """测试 JSON 字符串中的嵌套列表和字典是否有效。"""
    data = {
        "nested_list": "[[1, 2], [3, 4]]",
        "nested_dict": '{"outer": {"inner": "value"}}',
    }
    fixed_data = fix_malformed_tool_arguments(data, _NestedActionForMalformedArgs)
    action = _NestedActionForMalformedArgs.model_validate(fixed_data)

    assert action.nested_list == [[1, 2], [3, 4]]
    assert action.nested_dict == {"outer": {"inner": "value"}}


def test_empty_collections():
    """测试空列表和空字典是否工作。"""
    data = {
        "items": "[]",
        "config": "{}",
        "name": "empty",
    }
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingTestAction)
    action = JsonDecodingTestAction.model_validate(fixed_data)

    assert action.items == []
    assert action.config == {}


def test_mixed_native_and_json_strings():
    """测试在同一模型中混合本机值和 JSON 字符串。"""
    data = {
        "items": ["native", "list"],  # 本地列表
        "config": '{"from": 1, "json": 2}',  # JSON 字符串
        "name": "mixed",
    }
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingTestAction)
    action = JsonDecodingTestAction.model_validate(fixed_data)

    assert action.items == ["native", "list"]
    assert action.config == {"from": 1, "json": 2}
    assert action.name == "mixed"


def test_unicode_in_json_strings():
    """测试 JSON 字符串中的 unicode 字符是否被正确处理。"""
    data = {
        "items": '["hello", "世界", "🌍"]',
        "config": '{"greeting": 1, "你好": 2}',
        "name": "unicode",
    }
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingTestAction)
    action = JsonDecodingTestAction.model_validate(fixed_data)

    assert action.items == ["hello", "世界", "🌍"]
    assert action.config == {"greeting": 1, "你好": 2}


def test_whitespace_in_json_strings():
    """测试带有额外空格的 JSON 字符串是否有效。"""
    data = {
        "items": '  [ "a" , "b" , "c" ]  ',
        "config": '  { "x" : 1 , "y" : 2 }  ',
        "name": "whitespace",
    }
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingTestAction)
    action = JsonDecodingTestAction.model_validate(fixed_data)

    assert action.items == ["a", "b", "c"]
    assert action.config == {"x": 1, "y": 2}


@pytest.mark.parametrize(
    "field, raw_value, expected",
    [
        pytest.param(
            "items",
            '["a", "b"]<parameter name="security_risk">LOW',
            ["a", "b"],
            id="list_with_trailing_xml",
        ),
        pytest.param(
            "config",
            '{"x": 1}<extra>stuff</extra>',
            {"x": 1},
            id="dict_with_trailing_xml",
        ),
        pytest.param(
            "items",
            "no brackets at all",
            None,
            id="completely_invalid_rejected",
        ),
    ],
)
def test_trailing_garbage_truncation(field, raw_value, expected):
    """测试有效 JSON 之后尾随垃圾的截断（#2670）。"""
    data = {"items": "[]", "config": "{}", "name": "test", field: raw_value}
    fixed_data = fix_malformed_tool_arguments(data, JsonDecodingTestAction)

    if expected is None:
        with pytest.raises(ValidationError):
            JsonDecodingTestAction.model_validate(fixed_data)
    else:
        action = JsonDecodingTestAction.model_validate(fixed_data)
        assert getattr(action, field) == expected


def test_trailing_garbage_with_nested_braces():
    """测试截断适用于有效 JSON 前缀中的嵌套大括号 (#2670)。"""
    data = {
        "nested_dict": '{"outer": {"inner": "v"}}  <tag>junk',
        "nested_list": "[[1]]",
    }
    fixed_data = fix_malformed_tool_arguments(data, _NestedActionForMalformedArgs)
    action = _NestedActionForMalformedArgs.model_validate(fixed_data)

    assert action.nested_dict == {"outer": {"inner": "v"}}


def test_str_field_list_joined():
    """连接给定字符串块列表的仅 str 字段（minimax-m2.5）。"""
    data = {
        "old_str": ["[dependencies]\nhypatia = ", '{ features = ["arrow"] }'],
        "name": "test",
    }
    fixed_data = fix_malformed_tool_arguments(data, StrFieldAction)
    action = StrFieldAction.model_validate(fixed_data)

    # "".join 保留嵌入的换行符并连接而不使用分隔符。
    assert action.old_str == '[dependencies]\nhypatia = { features = ["arrow"] }'
    assert action.name == "test"


def test_str_field_native_string_passthrough():
    """给定普通字符串的仅 str 字段保持不变。"""
    data = {"old_str": "already a string", "name": "test"}
    fixed_data = fix_malformed_tool_arguments(data, StrFieldAction)
    action = StrFieldAction.model_validate(fixed_data)

    assert action.old_str == "already a string"


def test_str_field_list_with_non_strings_not_joined():
    """给定包含非字符串成员的列表的 str 字段不会被连接。"""
    data = {"old_str": ["a", 1], "name": "test"}
    fixed_data = fix_malformed_tool_arguments(data, StrFieldAction)

    # 保持原样，因此 Pydantic 拒绝它而不是默默地破坏它。
    with pytest.raises(ValidationError):
        StrFieldAction.model_validate(fixed_data)


def test_str_or_list_field_list_passthrough():
    """A string|给定一个列表的字段有效且不能连接。"""
    data = {"value": ["a", "b", "c"]}
    fixed_data = fix_malformed_tool_arguments(data, StrOrListAction)
    action = StrOrListAction.model_validate(fixed_data)

    assert action.value == ["a", "b", "c"]
