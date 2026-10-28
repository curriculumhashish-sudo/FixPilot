"""Example: 与 tool_concurrency_limit 并行执行工具。

演示如何在智能体上设置 tool_concurrency_limit 以在单个步骤中启用并发工具执行。 编排器
智能体并行委托给多个子智能体，每个子智能体本身同时运行工具。
这对并行执行系统进行端到端的压力测试。
"""

import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path

from openhands.sdk import (
    LLM,
    Agent,
    AgentContext,
    Conversation,
    Tool,
    register_agent,
)
from openhands.sdk.context import Skill
from openhands.tools.delegate import DelegationVisualizer
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task import TaskToolSet
from openhands.tools.terminal import TerminalTool


llm = LLM(
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
    usage_id="parallel-tools-demo",
)


# --- 子智能体 ---


def create_code_analyst(llm: LLM) -> Agent:
    """子智能体分析代码结构。"""
    return Agent(
        llm=llm,
        tools=[
            Tool(name=TerminalTool.name),
            Tool(name=FileEditorTool.name),
        ],
        tool_concurrency_limit=4,
        agent_context=AgentContext(
            skills=[
                Skill(
                    name="code_analysis",
                    content=(
                        "You analyze code structure. Use the terminal to count files, "
                        "lines of code, and list directory structure. Use the file "
                        "editor to read key files. Run multiple commands at once."
                    ),
                    trigger=None,
                )
            ],
            system_message_suffix="Be concise. Report findings in bullet points.",
        ),
    )


def create_doc_reviewer(llm: LLM) -> Agent:
    """子智能体审查文档。"""
    return Agent(
        llm=llm,
        tools=[
            Tool(name=TerminalTool.name),
            Tool(name=FileEditorTool.name),
        ],
        tool_concurrency_limit=4,
        agent_context=AgentContext(
            skills=[
                Skill(
                    name="doc_review",
                    content=(
                        "You review project documentation. Check README files, "
                        "docstrings, and inline comments. Use the terminal and "
                        "file editor to inspect files. Run multiple commands at once."
                    ),
                    trigger=None,
                )
            ],
            system_message_suffix="Be concise. Report findings in bullet points.",
        ),
    )


def create_dependency_checker(llm: LLM) -> Agent:
    """子智能体检查项目依赖关系。"""
    return Agent(
        llm=llm,
        tools=[
            Tool(name=TerminalTool.name),
            Tool(name=FileEditorTool.name),
        ],
        tool_concurrency_limit=4,
        agent_context=AgentContext(
            skills=[
                Skill(
                    name="dependency_check",
                    content=(
                        "You analyze project dependencies. Read pyproject.toml, "
                        "requirements files, and package configs. Summarize key "
                        "dependencies, their purposes, and any version constraints. "
                        "Run multiple commands at once."
                    ),
                    trigger=None,
                )
            ],
            system_message_suffix="Be concise. Report findings in bullet points.",
        ),
    )


# 注册子智能体
register_agent(
    name="code_analyst",
    factory_func=create_code_analyst,
    description="Analyzes code structure, file counts, and directory layout.",
)
register_agent(
    name="doc_reviewer",
    factory_func=create_doc_reviewer,
    description="Reviews documentation quality and completeness.",
)
register_agent(
    name="dependency_checker",
    factory_func=create_dependency_checker,
    description="Checks and summarizes project dependencies.",
)
# --- 并行执行的 Orchestrator 智能体 ---
main_agent = Agent(
    llm=llm,
    tools=[
        Tool(name=TaskToolSet.name),
        Tool(name=TerminalTool.name),
        Tool(name=FileEditorTool.name),
    ],
    tool_concurrency_limit=8,
)

persistence_dir = Path(tempfile.mkdtemp(prefix="parallel_example_"))

conversation = Conversation(
    agent=main_agent,
    workspace=Path.cwd(),
    visualizer=DelegationVisualizer(name="Orchestrator"),
    persistence_dir=persistence_dir,
)

print("=" * 80)
print("Parallel Tool Execution Stress Test")
print("=" * 80)

conversation.send_message("""
Analyze the current project by delegating to ALL THREE sub-agents IN PARALLEL:

1. code_analyst: Analyze the project structure (file counts, key directories)
2. doc_reviewer: Review documentation quality (README, docstrings)
3. dependency_checker: Check dependencies (pyproject.toml, requirements)

IMPORTANT: Delegate to all three agents at the same time using parallel tool calls.
Do NOT delegate one at a time - call all three delegate tools in a single response.

Once all three have reported back, write a consolidated summary to
project_analysis_report.txt in the working directory. The report should have
three sections (Code Structure, Documentation, Dependencies) with the key
findings from each sub-agent.
""")
conversation.run()

# --- 分析已持久化事件的并行性 ---
#
# 遍历持久化目录以查找所有对话（main + 子智能体）。 每个对话将事件存储为 event-*.JSON
# events/ 目录下的文件。 我们解析ActionEvent条记录，并按llm_response_id分组——具有相同响
# 应ID的2个或更多操作的批次证明了LLM并行调用的请求，并且执行器并发处理了它们。
#

print("\n" + "=" * 80)
print("Parallelism Report")
print("=" * 80)


def _analyze_conversation(events_dir: Path) -> dict[str, list[str]]:
    """对于多工具批次，返回 {llm_response_id: [tool_name, ...]}。"""
    batches: dict[str, list[str]] = defaultdict(list)
    for event_file in sorted(events_dir.glob("event-*.json")):
        data = json.loads(event_file.read_text())
        if data.get("kind") == "ActionEvent" and "llm_response_id" in data:
            batches[data["llm_response_id"]].append(data.get("tool_name", "?"))
    return {rid: tools for rid, tools in batches.items() if len(tools) >= 2}


for events_dir in sorted(persistence_dir.rglob("events")):
    if not events_dir.is_dir():
        continue
    # 从路径中派生标签（主转换 vs 子智能体）
    rel = events_dir.parent.relative_to(persistence_dir)
    is_subagent = "subagents" in rel.parts
    label = "sub-agent" if is_subagent else "main agent"

    multi_batches = _analyze_conversation(events_dir)
    if multi_batches:
        for resp_id, tools in multi_batches.items():
            print(f"\n  {label} batch ({resp_id[:16]}...):")
            print(f"    Parallel tools: {tools}")
    else:
        print(f"\n  {label}: no parallel batches")

cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
print(f"\nTotal cost: ${cost:.4f}")
print(f"EXAMPLE_COST: {cost:.4f}")
