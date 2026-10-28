"""测试 openhands.sdk.tool.schema 中的 py_type 功能。"""

from typing import Any

from openhands.sdk.tool.schema import py_type


class TestPyTypePrimitiveTypes:
    """使用原始 JSON 模式类型测试 py_type。"""

    def test_string_type(self):
        """测试字符串类型是否映射到 Python str。"""
        # 安排
        spec = {"type": "string"}

        # 法案
        result = py_type(spec)

        # 断言
        assert result is str

    def test_integer_type(self):
        """测试整数类型映射到 Python int。"""
        # 安排
        spec = {"type": "integer"}

        # 法案
        result = py_type(spec)

        # 断言
        assert result is int

    def test_number_type(self):
        """测试数字类型映射到 Python float。"""
        # 安排
        spec = {"type": "number"}

        # 法案
        result = py_type(spec)

        # 断言
        assert result is float

    def test_boolean_type(self):
        """测试布尔类型是否映射到 Python bool。"""
        # 安排
        spec = {"type": "boolean"}

        # 法案
        result = py_type(spec)

        # 断言
        assert result is bool


class TestPyTypeObjectType:
    """使用对象类型测试 py_type。"""

    def test_object_type(self):
        """测试对象类型是否映射到 dict[str、Any]。"""
        # 安排
        spec = {"type": "object"}

        # 法案
        result = py_type(spec)

        # 断言
        assert result == dict[str, Any]


class TestPyTypeArrayType:
    """使用数组类型测试 py_type。"""

    def test_array_without_items(self):
        """测试没有项目的数组返回 list[Any]。"""
        # 安排
        spec = {"type": "array"}

        # 法案
        result = py_type(spec)

        # 断言
        assert result == list[Any]

    def test_array_with_dict_items(self):
        """使用 dict 项测试该数组递归处理内部类型。"""
        # 安排
        spec = {"type": "array", "items": {"type": "string"}}

        # 法案
        result = py_type(spec)

        # 断言
        assert result == list[str]

    def test_array_with_nested_array(self):
        """正确测试具有嵌套数组进程的数组。"""
        # 安排
        spec = {
            "type": "array",
            "items": {"type": "array", "items": {"type": "integer"}},
        }

        # 法案
        result = py_type(spec)

        # 断言
        assert result == list[list[int]]

    def test_array_with_non_dict_items(self):
        """测试包含非 dict 项的数组返回 list[Any]。"""
        # 安排
        spec = {"type": "array", "items": "string"}

        # 法案
        result = py_type(spec)

        # 断言
        assert result == list[Any]


class TestPyTypeUnionTypes:
    """使用联合类型（列表/元组/集合）测试 py_type。"""

    def test_union_list_with_single_non_null(self):
        """测试具有单个非 null 类型的联合列表是否提取该类型。"""
        # 安排
        spec = {"type": ["string", "null"]}

        # 法案
        result = py_type(spec)

        # 断言
        assert result is str

    def test_union_tuple_with_single_non_null(self):
        """测试具有单个非 null 类型的联合元组是否提取该类型。"""
        # 安排
        spec = {"type": ("integer", "null")}

        # 法案
        result = py_type(spec)

        # 断言
        assert result is int

    def test_union_set_with_single_non_null(self):
        """测试具有单个非 null 类型的联合集是否提取该类型。"""
        # 安排
        spec = {"type": {"number", "null"}}

        # 法案
        result = py_type(spec)

        # 断言
        assert result is float

    def test_union_with_multiple_non_null_types(self):
        """测试多个非 null 类型的联合是否返回 Any。"""
        # 安排
        spec = {"type": ["string", "integer"]}

        # 法案
        result = py_type(spec)

        # 断言
        assert result is Any

    def test_union_with_only_null(self):
        """测试仅具有 null 类型的联合返回 Any。"""
        # 安排
        spec = {"type": ["null"]}

        # 法案
        result = py_type(spec)

        # 断言
        assert result is Any

    def test_union_with_three_types_one_null(self):
        """测试具有三种类型（其中一种是 null）的并集提取非 null。"""
        # 安排
        spec = {"type": ["boolean", "null", "string"]}

        # 法案
        result = py_type(spec)

        # 断言
        assert result is Any


class TestPyTypeEdgeCases:
    """使用边缘情况和无效输入测试 py_type。"""

    def test_missing_type_key(self):
        """测试缺少的类型键是否返回 Any。"""
        # 安排
        spec = {}

        # 法案
        result = py_type(spec)

        # 断言
        assert result is Any

    def test_unknown_type(self):
        """测试未知类型返回 Any。"""
        # 安排
        spec = {"type": "unknown_type"}

        # 法案
        result = py_type(spec)

        # 断言
        assert result is Any

    def test_empty_dict(self):
        """测试空字典是否返回 Any。"""
        # 安排
        spec = {}

        # 法案
        result = py_type(spec)

        # 断言
        assert result is Any

    def test_type_none(self):
        """测试 type=None 返回 Any。"""
        # 安排
        spec = {"type": None}

        # 法案
        result = py_type(spec)

        # 断言
        assert result is Any

    def test_array_with_empty_items_dict(self):
        """测试带有空项的数组 dict 返回 list[Any]。"""
        # 安排
        spec = {"type": "array", "items": {}}

        # 法案
        result = py_type(spec)

        # 断言
        assert result == list[Any]
