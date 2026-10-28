"""默认预设配置为 OpenHands 智能体。"""

from pathlib import Path
from typing import Any

from openhands.sdk import Agent, agent_definition_to_factory, load_agents_from_dir
from openhands.sdk.context.condenser import default_condenser
from openhands.sdk.context.condenser.base import CondenserBase
from openhands.sdk.llm.llm import LLM
from openhands.sdk.logger import get_logger
from openhands.sdk.subagent import AgentDefinition, register_agent_if_absent
from openhands.sdk.tool import Tool
from openhands.sdk.tool.builtins import BUILT_IN_TOOLS, FinishTool
from openhands.sdk.tool.registry import list_registered_tools, register_tool


logger = get_logger(__name__)


def register_default_tools(enable_browser: bool = True) -> None:
    """注册默认的工具集。"""
    # 现在导入时会自动注册工具
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool

    logger.debug(f"Tool: {TerminalTool.name} registered.")
    logger.debug(f"Tool: {FileEditorTool.name} registered.")
    logger.debug(f"Tool: {TaskTrackerTool.name} registered.")

    if enable_browser:
        from openhands.tools.browser_use import BrowserToolSet

        logger.debug(f"Tool: {BrowserToolSet.name} registered.")


def get_default_tools(
    enable_browser: bool = True,
    enable_sub_agents: bool = False,
) -> list[Tool]:
    """获取标准体验的默认工具规范集。

    Args:
        enable_browser: 是否包含浏览器工具。
        enable_sub_agents: 是否包含TaskToolSet
            子智能体代表团。
    """
    register_default_tools(enable_browser=enable_browser)

    # 导入工具以访问其名称属性
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool

    tools = [
        Tool(name=TerminalTool.name),
        Tool(name=FileEditorTool.name),
        Tool(name=TaskTrackerTool.name),
    ]
    if enable_browser:
        from openhands.tools.browser_use import BrowserToolSet

        tools.append(Tool(name=BrowserToolSet.name))
    if enable_sub_agents:
        from openhands.tools.task import TaskToolSet

        tools.append(Tool(name=TaskToolSet.name))
    return tools


def get_default_condenser(llm: LLM) -> CondenserBase:
    # 与衍生的子智能体共享（参见 SDK default_condenser），因此两者都保留在同步中。
    return default_condenser(llm)


def get_default_agent(
    llm: LLM,
    cli_mode: bool = False,
    finish_tool_response_schema: Any | None = None,
) -> Agent:
    tools = get_default_tools(
        # 在 CLI 模式下禁用浏览器工具
        enable_browser=not cli_mode,
    )
    agent_kwargs: dict[str, Any] = {}
    if finish_tool_response_schema is not None:
        if FinishTool.__name__ not in list_registered_tools():
            register_tool(FinishTool.__name__, FinishTool)
        tools.append(
            Tool(
                name=FinishTool.__name__,
                params={"response_schema": finish_tool_response_schema},
            )
        )
        agent_kwargs["include_default_tools"] = [
            tool.__name__ for tool in BUILT_IN_TOOLS if tool is not FinishTool
        ]

    agent = Agent(
        llm=llm,
        tools=tools,
        system_prompt_kwargs={"cli_mode": cli_mode},
        condenser=get_default_condenser(
            llm=llm.model_copy(update={"usage_id": "condenser"})
        ),
        **agent_kwargs,
    )
    return agent


def discover_builtin_agents(enable_browser: bool = True) -> list[AgentDefinition]:
    """加载内置智能体定义 (``level='builtin'``) 而不注册它们。

    ``register_builtins_agents`` 的非变异对应物。 当 ``enable_browser`` 为 False 时，
    将跳过仅浏览器智能体。

    Args:
        enable_browser: 当False时，跳过需要浏览器工具的智能体（网络研究员）。

    Returns:
        内置智能体定义与 ``level="builtin"``。
    """
    subagent_dir = Path(__file__).parent / "subagents"
    builtins_agents_def = load_agents_from_dir(subagent_dir)

    # 当浏览器不可用时过滤掉依赖于浏览器的智能体
    if not enable_browser:
        _browser_only_agents = {"web-researcher"}
        builtins_agents_def = [
            agent
            for agent in builtins_agents_def
            if agent.name not in _browser_only_agents
        ]

    return [
        agent_def.model_copy(update={"level": "builtin"})
        for agent_def in builtins_agents_def
    ]


def register_builtins_agents(enable_browser: bool = True) -> list[str]:
    """从 ``subagent/*.md`` 加载并注册内置智能体。
    它们通过 `register_agent_if_absent` 注册，不会覆盖智能体由程序调用、插件或项目/用
    户级别的文件定义已注册的。
    Args:
        enable_browser: 浏览器工具是否可用。 当False时，
            智能体需要浏览器工具 (e.g. 网络研究员）被跳过。
    Returns:
        实际注册的智能体列表。
    """
    register_default_tools(enable_browser=enable_browser)

    builtins_agents_def = discover_builtin_agents(enable_browser=enable_browser)

    registered: list[str] = []
    for agent_def in builtins_agents_def:
        factory = agent_definition_to_factory(agent_def)
        was_registered = register_agent_if_absent(
            name=agent_def.name,
            factory_func=factory,
            description=agent_def,
        )
        if was_registered:
            registered.append(agent_def.name)
            logger.info(
                f"Registered file-based agent '{agent_def.name}'"
                + (f" from {agent_def.source}" if agent_def.source else "")
            )
    return registered
