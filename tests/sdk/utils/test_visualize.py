"""测试 openhands.sdk.utils.visualize 模块。"""

from rich.text import Text

from openhands.sdk.utils.visualize import display_json


def test_display_json_with_dictionary():
    """使用字典输入测试 display_json。"""
    data = {"key1": "value1", "key2": 42, "key3": None}
    result = display_json(data)

    assert isinstance(result, Text)
    text_content = str(result)
    assert "key1" in text_content
    assert "value1" in text_content
    assert "key2" in text_content
    assert "42" in text_content
    # 应跳过 None 字段
    assert "key3" not in text_content


def test_display_json_with_list():
    """使用列表输入测试 display_json（这是错误）。"""
    data = ["item1", "item2", 42, True]
    result = display_json(data)

    assert isinstance(result, Text)
    text_content = str(result)
    assert "[List with 4 items]" in text_content
    assert "[0]" in text_content
    assert "item1" in text_content
    assert "[1]" in text_content
    assert "item2" in text_content
    assert "[2]" in text_content
    assert "42" in text_content
    assert "[3]" in text_content
    assert "True" in text_content


def test_display_json_with_string():
    """使用字符串输入测试 display_json。"""
    data = "simple string"
    result = display_json(data)

    assert isinstance(result, Text)
    text_content = str(result)
    assert '"simple string"' in text_content


def test_display_json_with_multiline_string():
    """使用多行字符串输入测试 display_json。"""
    data = "line1\nline2\nline3"
    result = display_json(data)

    assert isinstance(result, Text)
    text_content = str(result)
    assert "String:" in text_content
    assert "line1" in text_content
    assert "line2" in text_content
    assert "line3" in text_content


def test_display_json_with_number():
    """输入数字测试 display_json。"""
    data = 42
    result = display_json(data)

    assert isinstance(result, Text)
    text_content = str(result)
    assert "42" in text_content


def test_display_json_with_float():
    """使用浮点输入测试 display_json。"""
    data = 3.14159
    result = display_json(data)

    assert isinstance(result, Text)
    text_content = str(result)
    assert "3.14159" in text_content


def test_display_json_with_boolean():
    """使用布尔输入测试 display_json。"""
    data = True
    result = display_json(data)

    assert isinstance(result, Text)
    text_content = str(result)
    assert "True" in text_content

    data = False
    result = display_json(data)

    assert isinstance(result, Text)
    text_content = str(result)
    assert "False" in text_content


def test_display_json_with_none():
    """使用 None 输入测试 display_json。"""
    data = None
    result = display_json(data)

    assert isinstance(result, Text)
    text_content = str(result)
    assert "null" in text_content


def test_display_json_with_nested_structures():
    """使用嵌套字典和列表测试 display_json。"""
    data = {
        "simple": "value",
        "nested_dict": {"inner": "data"},
        "list_data": [1, 2, 3],
        "multiline": "line1\nline2\nline3",
    }
    result = display_json(data)

    assert isinstance(result, Text)
    text_content = str(result)
    assert "simple" in text_content
    assert "nested_dict" in text_content
    assert "list_data" in text_content
    assert "multiline" in text_content
