"""测试规范的默认工具规格 (openhands.sdk.tool.defaults)。"""

import pytest

from openhands.sdk.tool import registry
from openhands.sdk.tool.defaults import (
    BROWSER_TOOL_NAME,
    DEFAULT_EXEC_TOOL_NAMES,
    SUB_AGENT_TOOL_NAME,
    SWITCH_LLM_TOOL_NAME,
    default_tool_specs,
    resolve_tool_specs,
)
from openhands.sdk.tool.spec import Tool


def _names(**kwargs) -> list[str]:
    return [t.name for t in default_tool_specs(**kwargs)]


def test_default_is_deterministic_exec_set() -> None:
    """默认值从不依赖于运行时/注册表状态——浏览器是
    服务层注入（参见BROWSER_TOOL_NAME），不是默认的一部分。"""
    assert _names() == list(DEFAULT_EXEC_TOOL_NAMES)
    assert BROWSER_TOOL_NAME not in _names()


def test_enable_sub_agents_appends_task_tool_set() -> None:
    assert _names(enable_sub_agents=True) == [
        *DEFAULT_EXEC_TOOL_NAMES,
        SUB_AGENT_TOOL_NAME,
    ]


def test_explicit_browser_appends_before_sub_agents() -> None:
    assert _names(enable_browser=True, enable_sub_agents=True) == [
        *DEFAULT_EXEC_TOOL_NAMES,
        BROWSER_TOOL_NAME,
        SUB_AGENT_TOOL_NAME,
    ]


def test_resolve_unset_tools_is_the_default_set() -> None:
    assert [t.name for t in resolve_tool_specs(None, enable_browser=True)] == [
        *DEFAULT_EXEC_TOOL_NAMES,
        BROWSER_TOOL_NAME,
        SWITCH_LLM_TOOL_NAME,
    ]


def test_preset_default_specs_exclude_the_sdk_builtin() -> None:
    """``default_tool_specs`` 与 OpenHands 工具预设保持同步。

    ``switch_llm`` 是 SDK 内置函数，因此它属于设置/配置文件默认值 (
    ``resolve_tool_specs``)，而不属于预设构造函数。
    """
    assert SWITCH_LLM_TOOL_NAME not in [
        t.name for t in default_tool_specs(enable_browser=True)
    ]


def test_resolve_configured_tools_is_used_as_given() -> None:
    """明确的列表是权威的——浏览器永远不会添加到顶部。"""
    assert resolve_tool_specs([], enable_browser=True) == []
    spec = Tool(name="terminal", params={"username": "dev"})
    assert resolve_tool_specs([spec], enable_browser=True) == [spec]


def test_is_tool_usable_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    assert registry.is_tool_usable("definitely-not-registered") is False
    monkeypatch.setitem(registry._REG, "probe", lambda params, conv: [])
    monkeypatch.setitem(registry._USABILITY_REG, "probe", lambda: True)
    assert registry.is_tool_usable("probe") is True

    def _boom() -> bool:
        raise RuntimeError("checker crashed")

    monkeypatch.setitem(registry._USABILITY_REG, "probe", _boom)
    assert registry.is_tool_usable("probe") is False
