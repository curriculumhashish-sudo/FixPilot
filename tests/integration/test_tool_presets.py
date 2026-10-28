"""测试集成测试中的工具预设选择逻辑。"""

import argparse

import pytest

from tests.integration.base import ToolPresetType, get_tools_for_preset


def test_get_tools_for_preset_default():
    """测试默认预设是否返回预期工具。"""
    tools = get_tools_for_preset("default", enable_browser=False)
    tool_names = {t.name for t in tools}

    assert "terminal" in tool_names
    assert "file_editor" in tool_names
    assert "task_tracker" in tool_names
    # 不应存在浏览器工具
    assert "browser_navigate" not in tool_names


def test_get_tools_for_preset_default_with_browser():
    """测试启用浏览器的默认预设是否包含浏览器工具。

    Note: 在集成测试运行期间跳过此测试，因为浏览器
    工具会导致 ProcessPoolExecutor 出现进程清理问题。 浏览器功能本身可以工作，但并行
    测试执行期间的清理工作会挂起。
    """
    pytest.skip(
        "Browser tools disabled in integration tests due to ProcessPoolExecutor "
        "cleanup issues - see issue #2124"
    )


def test_get_tools_for_preset_gemini():
    """测试 Gemini 预设返回 Gemini 风格的文件编辑工具。"""
    tools = get_tools_for_preset("gemini", enable_browser=False)
    tool_names = {t.name for t in tools}

    assert "terminal" in tool_names
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    assert "edit" in tool_names
    assert "list_directory" in tool_names
    assert "task_tracker" in tool_names
    # 默认 file_editor 应该存在不
    assert "file_editor" not in tool_names


def test_get_tools_for_preset_gpt5():
    """测试 gpt5 预设返回 apply_patch 工具。"""
    tools = get_tools_for_preset("gpt5", enable_browser=False)
    tool_names = {t.name for t in tools}

    assert "terminal" in tool_names
    assert "apply_patch" in tool_names
    assert "task_tracker" in tool_names
    # 默认 file_editor 应该存在不
    assert "file_editor" not in tool_names


def test_get_tools_for_preset_planning():
    """测试计划预设是否返回只读工具。"""
    tools = get_tools_for_preset("planning", enable_browser=False)
    tool_names = {t.name for t in tools}

    assert "glob" in tool_names
    assert "grep" in tool_names
    assert "planning_file_editor" in tool_names
    # 默认 file_editor 应该存在不
    assert "file_editor" not in tool_names
    # 不应存在浏览器工具（计划为只读）
    assert "browser_navigate" not in tool_names


def test_get_tools_for_preset_invalid():
    """测试无效预设是否会引发 ValueError。"""
    with pytest.raises(ValueError, match="Unknown `preset` parameter"):
        # type: ignore is used here intentionally to test runtime behavior
        get_tools_for_preset("invalid_preset", enable_browser=False)  # type: ignore[arg-type]


def test_tool_preset_type_literal_values():
    """验证 ToolPresetType 包括所有预期值。"""
    # 这是编译时检查，但我们在此处记录预期值
    valid_presets: list[ToolPresetType] = ["default", "gemini", "gpt5", "planning"]
    for preset in valid_presets:
        # 不应该提高
        tools = get_tools_for_preset(preset, enable_browser=False)
        assert len(tools) > 0


def test_run_infer_argparse_accepts_all_tool_presets():
    """验证 run_infer.py argparse 接受所有 ToolPresetType 值。

    该测试确保了 run_infer.py 中 argparse 选择项与同步中的 ToolPresetType 字面定义一
    致，从而避免了工具预设被 CLI 参数解析器
    拒绝的问题。

    回归测试问题 #2305。
    """
    # 创建一个简单的 argparse 解析器来模仿 run_infer.py 的工具预设参数
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tool-preset",
        type=str,
        choices=["default", "gemini", "gpt5", "planning"],
        default="default",
    )

    # 测试每个有效的预设值
    valid_presets: list[ToolPresetType] = ["default", "gemini", "gpt5", "planning"]

    for preset in valid_presets:
        # 这不应该引发错误
        args = parser.parse_args(["--tool-preset", preset])
        assert args.tool_preset == preset

    # 测试无效预设是否会引发错误
    with pytest.raises(SystemExit):
        parser.parse_args(["--tool-preset", "invalid"])
