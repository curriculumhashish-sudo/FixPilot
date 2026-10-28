"""标准的规范默认工具名称 OpenHands 智能体。

工具 * 名称 * 是一个电汇合约：它们位于已持久化设置/配置文件 JSON 中，并由客户端发送，
与实现所在的位置无关。 在这里保留规范默认值可以让
``openhands-sdk`` （不能导入
``openhands-tools``）默认仅来自数据的工具集 - ``Tool`` 是仅在运行时通过注册表解析为实
现的规范（名称 + 参数）。

``openhands.tools.preset.default.get_default_tools`` 仍然是注册实现的构造函数；
``tests/cross`` 断言它
与这些名称保持一致。
"""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter

from openhands.sdk.tool.spec import Tool


if TYPE_CHECKING:
    from openhands.sdk.tool.tool import ToolDefinition


DEFAULT_EXEC_TOOL_NAMES: tuple[str, ...] = (
    "terminal",
    "file_editor",
    "task_tracker",
)
"""每个默认 OpenHands 智能体获取的标准执行工具的名称。"""

BROWSER_TOOL_NAME = "browser_tool_set"
"""浏览器工具集名称，仅当设置为``enable_browser``时添加。"""

SUB_AGENT_TOOL_NAME = "task_tool_set"
"""子智能体委派工具集的名称。"""

SWITCH_LLM_TOOL_NAME = "switch_llm"
"""内置LLM-切换工具的名称。"""


def resolve_tool_specs(
    tools: Sequence[Tool] | None,
    *,
    enable_browser: bool = False,
) -> list[Tool]:
    """将 ``tools`` 解析为规格：``None`` 是标准集，保留列表。"""
    if tools is not None:
        return list(tools)
    return [
        *_preset_specs(enable_browser=enable_browser),
        Tool(name=SWITCH_LLM_TOOL_NAME),
    ]


def launch_tool_specs(
    tools: Sequence[Tool] | None, *, browser_available: bool
) -> list[Tool]:
    """解析 ``tools`` 以获得运行时，忽略它无法运行的浏览器。"""
    resolved = resolve_tool_specs(tools, enable_browser=browser_available)
    if browser_available:
        return resolved
    return [tool for tool in resolved if tool.name != BROWSER_TOOL_NAME]


def effective_builtin_class(name: str) -> "type[ToolDefinition] | None":
    """返回内置的 ``name`` 解析为，除非另一个工具保存它。"""
    from openhands.sdk.tool.builtins import builtin_tool_class
    from openhands.sdk.tool.registry import registered_tool_class

    builtin = builtin_tool_class(name)
    if builtin is None or registered_tool_class(name) not in (None, builtin):
        return None
    return builtin


def canonical_tool_name(name: str) -> str:
    """返回规范解析为的工具名称，折叠内置类名称。"""
    builtin = effective_builtin_class(name)
    if builtin is None or effective_builtin_class(builtin.name) is not builtin:
        return name
    return builtin.name


def selects_tool(tools: Sequence[Tool], name: str) -> bool:
    return any(canonical_tool_name(tool.name) == name for tool in tools)


def merge_duplicate_tools(tools: Sequence[Tool]) -> list[Tool]:
    """折叠命名相同工具的规范，保留第一个带有参数的规范。"""
    by_name: dict[str, Tool] = {}
    for tool in tools:
        name = canonical_tool_name(tool.name)
        kept = by_name.get(name)
        if kept is None or (tool.params and not kept.params):
            by_name[name] = Tool(name=name, params=tool.params)
    return list(by_name.values())


def reject_builtin_params(tools: Sequence[Tool]) -> None:
    """如果给定了一些不带参数的内置函数，则引发该错误。"""
    from openhands.sdk.tool.builtins import BUILT_IN_TOOLS_WITH_PARAMS

    for tool in tools:
        tool_class = effective_builtin_class(tool.name)
        if (
            set(tool.params) - {"response_schema"}
            and tool_class is not None
            and tool_class.__name__ not in BUILT_IN_TOOLS_WITH_PARAMS
        ):
            raise ValueError(f"Tool {tool.name!r} does not accept parameters")


def _preset_specs(*, enable_browser: bool) -> list[Tool]:
    specs = [Tool(name=name) for name in DEFAULT_EXEC_TOOL_NAMES]
    if enable_browser:
        specs.append(Tool(name=BROWSER_TOOL_NAME))
    return specs


def default_tool_specs(
    *,
    enable_sub_agents: bool = False,
    enable_browser: bool = False,
) -> list[Tool]:
    """OpenHands 智能体的默认工具规格，其设置不包含任何工具。

    Deterministic: 相同的输入在每个运行时产生相同的规格。
    浏览器默认处于关闭状态（请参阅：data:`BROWSER_TOOL_NAME` — 服务层在实际可以运行的
    地方启用它）。
    """
    specs = _preset_specs(enable_browser=enable_browser)
    if enable_sub_agents:
        specs.append(Tool(name=SUB_AGENT_TOOL_NAME))
    return specs


RETIRED_TOOL_SWITCHES = ("enable_sub_agents", "enable_switch_llm_tool")
_BOOL_ADAPTER = TypeAdapter(bool)


def drop_retired_tool_switches(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k not in RETIRED_TOOL_SWITCHES}


def fold_retired_tool_switches(
    payload: Mapping[str, Any],
    *,
    sparse: bool = False,
    enable_browser: bool = True,
) -> dict[str, Any]:
    """将退役的开关折叠到``tools``； ``sparse`` 跳过不存在的。"""
    folded = dict(payload)
    sub_agents = _pop_switch(folded, "enable_sub_agents", None if sparse else False)
    switch_llm = _pop_switch(folded, "enable_switch_llm_tool", None if sparse else True)
    tools = folded.get("tools")
    if tools is not None and not isinstance(tools, list | tuple):
        return folded
    # 已持久化 `[]` 早于 `None` 作为默认值。
    if not sparse and tools == []:
        tools = folded["tools"] = None
    if tools is None and not sub_agents and switch_llm is not False:
        return folded
    # “标准设置加/减一个工具”无法表达，所以将其固定。
    if tools is None:
        entries = _preset_specs(enable_browser=enable_browser)
        if sub_agents:
            entries.append(Tool(name=SUB_AGENT_TOOL_NAME))
        if switch_llm is None:
            switch_llm = True
    else:
        entries = [t if isinstance(t, Tool) else Tool.model_validate(t) for t in tools]
        # 存储的开关仅馈送默认设置。
        if sparse and sub_agents is not None:
            entries = _toggle(entries, SUB_AGENT_TOOL_NAME, sub_agents)
    if switch_llm is not None:
        entries = _toggle(entries, SWITCH_LLM_TOOL_NAME, switch_llm)
    folded["tools"] = entries
    return folded


def _toggle(entries: list[Tool], name: str, enabled: bool) -> list[Tool]:
    if not enabled:
        return [e for e in entries if canonical_tool_name(e.name) != name]
    if not selects_tool(entries, name):
        return [*entries, Tool(name=name)]
    return entries


def _pop_switch(payload: dict[str, Any], key: str, default: bool | None) -> bool | None:
    if key not in payload:
        return default
    return _BOOL_ADAPTER.validate_python(payload.pop(key))
