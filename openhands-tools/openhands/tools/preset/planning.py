"""规划智能体预设配置。"""

from openhands.sdk import Agent
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.sdk.llm.llm import LLM
from openhands.sdk.logger import get_logger
from openhands.sdk.tool import Tool


logger = get_logger(__name__)


# 计划结构定义为 (section_title, section_description) 元组列表
PLAN_STRUCTURE: list[tuple[str, str]] = [
    (
        "OBJECTIVE",
        (
            "* Summarize the goal of the plan in one or two sentences.\n"
            "* Restate the problem in clear operational terms."
        ),
    ),
    (
        "CONTEXT SUMMARY",
        (
            "* Briefly describe the relevant system components, files, or data involved.\n"  # noqa: E501
            "* Mention any dependencies or constraints (technical, organizational, or external)."  # noqa: E501
        ),
    ),
    (
        "APPROACH OVERVIEW",
        (
            "* Outline the chosen approach at a high level.\n"
            "* Mention why it was selected (short rationale) if alternatives were considered."  # noqa: E501
        ),
    ),
    (
        "IMPLEMENTATION STEPS",
        (
            "* Provide a step-by-step plan for execution.\n"
            "* Each step should include:\n"
            "  - a **goal** (what this step accomplishes),\n"
            "  - a **method** (how to do it, briefly),\n"
            "  - and optionally a **reference** (file, module, or function impacted)."
        ),
    ),
    (
        "TESTING AND VALIDATION",
        (
            "* Describe how the implementation can be verified or validated.\n"
            "* This section should describe what success looks like — expected outputs, behaviors, or conditions."  # noqa: E501
        ),
    ),
]


def format_plan_structure() -> str:
    """将 PLAN_STRUCTURE 格式化为字符串以供系统提示词注入。

    Returns:
        格式化的计划结构字符串已准备好供系统提示词使用。
    """

    if not PLAN_STRUCTURE:
        return ""

    formatted_sections = []
    for i, (title, description) in enumerate(PLAN_STRUCTURE, 1):
        # 将描述分成几行并正确缩进每行
        description_lines = description.split("\n")
        indented_description = "\n   ".join(description_lines)
        formatted_sections.append(f"{i}. {title}\n   {indented_description}")

    return "The plan must follow this structure exactly:\n\n" + "\n\n".join(
        formatted_sections
    )


def get_plan_headers() -> str:
    """获取用于初始化的计划节标题 PLAN.md。

    Returns:
        将标题计划为 Markdown 字符串。
    """
    headers = []
    for i, (title, _) in enumerate(PLAN_STRUCTURE, 1):
        headers.append(f"# {i}. {title}\n")

    return "\n".join(headers)


def register_planning_tools() -> None:
    """注册规划智能体工具。"""
    # 现在导入时会自动注册工具
    from openhands.tools.glob import GlobTool  # noqa: F401
    from openhands.tools.grep import GrepTool  # noqa: F401
    from openhands.tools.planning_file_editor import (
        PlanningFileEditorTool,  # noqa: F401
    )

    logger.debug("Tool: GlobTool registered.")
    logger.debug("Tool: GrepTool registered.")
    logger.debug("Tool: PlanningFileEditorTool registered.")


def get_planning_tools(plan_path: str | None = None) -> list[Tool]:
    """获取规划智能体工具规格。

    Args:
        plan_path: PLAN.md 文件的可选绝对路径。 如果提供，则会
            通过 params 传递给 PlanningFileEditorTool。

    Returns:
        包括文件查看和PLAN.md编辑功能的工具列表，这些功能用于高级代码发现和导航。
    """
    register_planning_tools()

    # 导入工具以访问其名称属性
    from openhands.tools.glob import GlobTool
    from openhands.tools.grep import GrepTool
    from openhands.tools.planning_file_editor import PlanningFileEditorTool

    # 如果 plan_path 提供，则为 PlanningFileEditorTool 构建参数
    planning_tool_params = {}
    if plan_path:
        planning_tool_params["plan_path"] = plan_path

    return [
        Tool(name=GlobTool.name),
        Tool(name=GrepTool.name),
        Tool(name=PlanningFileEditorTool.name, params=planning_tool_params),
    ]


def get_planning_condenser(llm: LLM) -> LLMSummarizingCondenser:
    """获得针对规划工作流程进行优化的上下文压缩器。

    Args:
        llm: 用于上下文压缩的 LLM。

    Returns:
        A 上下文压缩器配置用于规划智能体需求。
    """
    # 规划智能体可能需要更多上下文进行彻底分析
    condenser = LLMSummarizingCondenser(
        llm=llm,
        max_size=100,  # 更大的上下文窗口用于规划
        keep_first=6,  # 保留更多初始上下文
    )
    return condenser


def get_planning_agent(
    llm: LLM,
) -> Agent:
    """获取配置的计划智能体。

    Args:
        llm: 用于规划智能体的 LLM。
        enable_security_analyzer: 是否启用安全分析。

    Returns:
        完全配置的规划智能体，具有只读文件操作和命令行功能，可实现全面的代码发现。
    """
    tools = get_planning_tools()

    agent = Agent(
        llm=llm,
        tools=tools,
        system_prompt_filename="system_prompt_planning.j2",
        system_prompt_kwargs={"plan_structure": format_plan_structure()},
        condenser=get_planning_condenser(
            llm=llm.model_copy(update={"usage_id": "planning_condenser"})
        ),
    )

    return agent
