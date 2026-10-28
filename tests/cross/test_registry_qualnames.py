"""测试工具注册表模块限定名称跟踪。"""

from openhands.sdk.tool.registry import (
    get_tool_module_qualnames,
    list_registered_tools,
    register_tool,
)


def test_get_tool_module_qualnames_with_class():
    """测试注册类时是否跟踪模块限定名。"""
    from openhands.tools.glob import GlobTool

    # 注册 GlobTool 类
    register_tool("test_glob_class", GlobTool)

    # 获取模块限定名
    qualnames = get_tool_module_qualnames()

    # 验证该工具是否已通过其模块进行跟踪
    assert "test_glob_class" in qualnames
    assert qualnames["test_glob_class"] == "openhands.tools.glob.definition"


def test_get_tool_module_qualnames_after_import():
    """测试导入工具模块是否使用 qualname 注册它。"""
    # 导入glob工具模块触发自动注册
    import openhands.tools.glob.definition  # noqa: F401

    # 获取注册工具
    registered_tools = list_registered_tools()

    # 应该已经注册了 glob
    assert "glob" in registered_tools

    # 获取模块限定名
    qualnames = get_tool_module_qualnames()

    # 验证 glob 是否已跟踪其模块限定名
    if "glob" in qualnames:
        assert qualnames["glob"] == "openhands.tools.glob.definition"


def test_get_tool_module_qualnames_returns_copy():
    """测试 get_tool_module_qualnames 返回副本，而不是原始字典。"""
    qualnames1 = get_tool_module_qualnames()
    qualnames2 = get_tool_module_qualnames()

    # 应该相等但不是同一个对象
    assert qualnames1 == qualnames2
    assert qualnames1 is not qualnames2
