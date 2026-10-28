"""动态工作流工具示例。

此示例演示了预期的工作流程形状：

1. 父级智能体编写 Python 工作流脚本。
2. 父级智能体使用生成的脚本调用工作流工具。
3. 工作流程呈扇形展开子智能体以按项目区域审核测试覆盖率。
4. 减速器子智能体总结了回购范围的覆盖风险。
"""

import os
from pathlib import Path

from openhands.sdk import LLM, Agent, AgentContext, Conversation, Tool
from openhands.sdk.context import Skill
from openhands.sdk.subagent import register_agent_if_absent
from openhands.tools.delegate import DelegationVisualizer
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool
from openhands.tools.workflow import WorkflowToolSet


llm = LLM(
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
    usage_id="dynamic-workflow-demo",
)


# 子智能体由生成的工作流使用。
def create_coverage_auditor(llm: LLM) -> Agent:
    return Agent(
        llm=llm,
        tools=[
            Tool(name=TerminalTool.name),
            Tool(name=FileEditorTool.name),
        ],
        agent_context=AgentContext(
            skills=[
                Skill(
                    name="coverage_audit",
                    content=(
                        "You audit whether source code has meaningful test "
                        "coverage. Use read-only inspection commands and file "
                        "views. Compare source modules against the matching "
                        "tests under tests/sdk, tests/tools, tests/workspace, "
                        "or tests/agent_server. Identify risky untested "
                        "behavior, and recommend the "
                        "next tests to add. Use at most three tool calls, "
                        "avoid broad dumps, and do not edit files."
                    ),
                    trigger=None,
                )
            ],
            system_message_suffix=(
                "Return a concise coverage assessment with evidence, gaps, "
                "and recommended tests. Keep command output under 200 lines "
                "and do not modify the repository."
            ),
        ),
    )


register_agent_if_absent(
    name="coverage_auditor",
    factory_func=create_coverage_auditor,
    description="Audits test coverage quality for one project area.",
)

# 父级智能体具有工作流程工具。 它负责编写工作流脚本，然后使用生成的 Python 代码调用该工
# 具。
#
parent_agent = Agent(
    llm=llm,
    tools=[Tool(name=WorkflowToolSet.name)],
    agent_context=AgentContext(
        skills=[
            Skill(
                name="workflow_author",
                content=(
                    "When a task benefits from parallel sub-agents, write a "
                    "Python workflow script with `async def main(wf):` and call "
                    "the workflow tool. Keep intermediate findings inside the "
                    "workflow and return only the reducer's final report. "
                    "Prefer bounded prompts and `max_concurrency=2` for "
                    "examples that inspect repositories."
                ),
                trigger=None,
            )
        ]
    ),
)

conversation = Conversation(
    agent=parent_agent,
    workspace=Path.cwd(),
    visualizer=DelegationVisualizer(name="CoverageWorkflow"),
    max_iteration_per_run=6,  # 如果需要更多回合来编写脚本，则增加
)

conversation.send_message(
    "Write and run a dynamic workflow that audits whether test coverage is "
    "good across this repository. In the workflow code you generate, create "
    "one item for each project area: `openhands-sdk/openhands/sdk`, "
    "`openhands-tools/openhands/tools`, "
    "`openhands-workspace/openhands/workspace`, and "
    "`openhands-agent-server/openhands/agent_server`. Use `wf.map_agents` "
    "with `max_concurrency=2` to fan out one `coverage_auditor` sub-agent "
    "per area. Each sub-agent should inspect source files and matching tests "
    "under `tests/sdk`, `tests/tools`, `tests/workspace`, or "
    "`tests/agent_server` with at most three read-only commands or file views, "
    "avoid running the full test suite, and report coverage strengths, risky "
    "gaps, and the "
    "next tests to add. Finally use `wf.reduce_agent` with "
    "`coverage_auditor` to synthesize a "
    "repo-wide coverage report with the highest-priority gaps. Return the "
    "final report to me."
)
conversation.run()

cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
print(f"EXAMPLE_COST: {cost}")
