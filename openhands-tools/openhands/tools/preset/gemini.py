"""Gemini 预设配置为 OpenHands 智能体。

此预设使用 Gemini 风格的文件编辑工具，而不是默认的 claude 风格 file_editor 工具。
"""

from openhands.sdk import Agent
from openhands.sdk.context.condenser import (
    LLMSummarizingCondenser,
)
from openhands.sdk.context.condenser.base import CondenserBase
from openhands.sdk.llm.llm import LLM
from openhands.sdk.logger import get_logger
from openhands.sdk.tool import Tool


logger = get_logger(__name__)


def register_gemini_tools(enable_browser: bool = True) -> None:
    """注册gemini工具集。"""
    from openhands.tools.gemini import (
        EditTool,
        ListDirectoryTool,
        ReadFileTool,
        WriteFileTool,
    )
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool

    logger.debug(f"Tool: {TerminalTool.name} registered.")
    logger.debug(f"Tool: {ReadFileTool.name} registered.")
    logger.debug(f"Tool: {WriteFileTool.name} registered.")
    logger.debug(f"Tool: {EditTool.name} registered.")
    logger.debug(f"Tool: {ListDirectoryTool.name} registered.")
    logger.debug(f"Tool: {TaskTrackerTool.name} registered.")

    if enable_browser:
        from openhands.tools.browser_use import BrowserToolSet

        logger.debug(f"Tool: {BrowserToolSet.name} registered.")


def get_gemini_tools(
    enable_browser: bool = True,
) -> list[Tool]:
    """获取 Gemini 工具规格集。

    这使用 Gemini 风格的文件编辑工具（read_file、write_file、edit、list_directory）而
    不是默认的 claude 风格
    file_editor 工具。

    Args:
        enable_browser: 是否包含浏览器工具。
    """
    register_gemini_tools(enable_browser=enable_browser)

    from openhands.tools.gemini import (
        EditTool,
        ListDirectoryTool,
        ReadFileTool,
        WriteFileTool,
    )
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool

    tools = [
        Tool(name=TerminalTool.name),
        Tool(name=ReadFileTool.name),
        Tool(name=WriteFileTool.name),
        Tool(name=EditTool.name),
        Tool(name=ListDirectoryTool.name),
        Tool(name=TaskTrackerTool.name),
    ]
    if enable_browser:
        from openhands.tools.browser_use import BrowserToolSet

        tools.append(Tool(name=BrowserToolSet.name))
    return tools


def get_gemini_condenser(llm: LLM) -> CondenserBase:
    """获取 Gemini 预设的默认值上下文压缩器。"""
    condenser = LLMSummarizingCondenser(llm=llm, max_size=80, keep_first=4)
    return condenser


def get_gemini_agent(
    llm: LLM,
    cli_mode: bool = False,
) -> Agent:
    """使用双子座风格的工具获取智能体：read_file、write_file、编辑、
    list_directory."""
    tools = get_gemini_tools(
        enable_browser=not cli_mode,
    )
    agent = Agent(
        llm=llm,
        tools=tools,
        system_prompt_kwargs={"cli_mode": cli_mode},
        condenser=get_gemini_condenser(
            llm=llm.model_copy(update={"usage_id": "condenser"})
        ),
    )
    return agent
