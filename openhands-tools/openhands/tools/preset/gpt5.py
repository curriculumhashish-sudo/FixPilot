"""GPT-5 OpenHands 智能体的预设配置。

此预设使用 ApplyPatchTool 进行文件编辑，而不是默认的克劳德风格 FileEditorTool。 它通
过提供可选的帮助程序而不更改全局默认值来反映 Gemin
i 预设模式。
"""

from openhands.sdk import Agent
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.sdk.context.condenser.base import CondenserBase
from openhands.sdk.llm.llm import LLM
from openhands.sdk.logger import get_logger
from openhands.sdk.tool import Tool


logger = get_logger(__name__)


def register_gpt5_tools(enable_browser: bool = True) -> None:
    """注册 GPT-5 工具集（终端、apply_patch、task_tracker、浏览器）。"""
    from openhands.tools.apply_patch import ApplyPatchTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool

    logger.debug(f"Tool: {TerminalTool.name} registered.")
    logger.debug(f"Tool: {ApplyPatchTool.name} registered.")
    logger.debug(f"Tool: {TaskTrackerTool.name} registered.")

    if enable_browser:
        from openhands.tools.browser_use import BrowserToolSet

        logger.debug(f"Tool: {BrowserToolSet.name} registered.")


def get_gpt5_tools(enable_browser: bool = True) -> list[Tool]:
    """使用 ApplyPatchTool 获取 GPT-5 工具规格进行编辑。

    Args:
        enable_browser: 是否包含浏览器工具。
    """
    register_gpt5_tools(enable_browser=enable_browser)

    from openhands.tools.apply_patch import ApplyPatchTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool

    tools: list[Tool] = [
        Tool(name=TerminalTool.name),
        Tool(name=ApplyPatchTool.name),
        Tool(name=TaskTrackerTool.name),
    ]
    if enable_browser:
        from openhands.tools.browser_use import BrowserToolSet

        tools.append(Tool(name=BrowserToolSet.name))
    return tools


def get_gpt5_condenser(llm: LLM) -> CondenserBase:
    """获取 GPT-5 预设的默认值上下文压缩器。"""
    return LLMSummarizingCondenser(llm=llm, max_size=80, keep_first=4)


def get_gpt5_agent(llm: LLM, cli_mode: bool = False) -> Agent:
    """获取智能体和 ApplyPatchTool 以进行统一差异样式文件编辑。"""
    tools = get_gpt5_tools(enable_browser=not cli_mode)
    agent = Agent(
        llm=llm,
        tools=tools,
        system_prompt_kwargs={"cli_mode": cli_mode},
        condenser=get_gpt5_condenser(
            llm=llm.model_copy(update={"usage_id": "condenser"})
        ),
    )
    return agent
