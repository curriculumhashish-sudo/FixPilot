import pytest

from openhands.tools.file_editor.exceptions import (
    EditorToolParameterInvalidError,
    EditorToolParameterMissingError,
    ToolError,
)


def test_tool_error():
    """测试 ToolError 引发正确的消息。"""
    with pytest.raises(ToolError) as exc_info:
        raise ToolError("A tool error occurred")
    assert str(exc_info.value) == "A tool error occurred"


def test_editor_tool_parameter_missing_error():
    """测试 EditorToolParameterMissingError 是否缺少参数错误消息。"""
    command = "str_replace"
    parameter = "old_str"
    with pytest.raises(EditorToolParameterMissingError) as exc_info:
        raise EditorToolParameterMissingError(command, parameter)
    assert exc_info.value.command == command
    assert exc_info.value.parameter == parameter
    assert (
        exc_info.value.message
        == f"Parameter `{parameter}` is required for command: {command}."
    )


def test_editor_tool_parameter_invalid_error_with_hint():
    """使用提示测试 EditorToolParameterInvalidError。"""
    parameter = "timeout"
    value = -10
    hint = "Must be a positive integer."
    with pytest.raises(EditorToolParameterInvalidError) as exc_info:
        raise EditorToolParameterInvalidError(parameter, str(value), hint)
    assert exc_info.value.parameter == parameter
    assert exc_info.value.value == str(value)
    assert exc_info.value.message == f"Invalid `{parameter}` parameter: {value}. {hint}"


def test_editor_tool_parameter_invalid_error_without_hint():
    """测试EditorToolParameterInvalidError，无提示。"""
    parameter = "timeout"
    value = -10
    with pytest.raises(EditorToolParameterInvalidError) as exc_info:
        raise EditorToolParameterInvalidError(parameter, str(value))
    assert exc_info.value.parameter == parameter
    assert exc_info.value.value == str(value)
    assert exc_info.value.message == f"Invalid `{parameter}` parameter: {value}."
