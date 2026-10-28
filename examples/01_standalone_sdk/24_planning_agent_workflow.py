#!/usr/bin/env python3
"""
规划智能体工作流程示例

此示例演示了一个两阶段工作流程：
1. 规划智能体：分析任务并创建详细的实施计划
2. 执行智能体：以完整的编辑功能实施计划

任务：创建一个 Python 网页爬虫来提取文章标题和 URLs
from a news website, handles rate limiting, and saves results to JSON.
"""

import os
import tempfile
from pathlib import Path

from pydantic import SecretStr

from openhands.sdk import LLM, Conversation
from openhands.sdk.llm import content_to_str
from openhands.tools.preset.default import get_default_agent
from openhands.tools.preset.planning import get_planning_agent


def get_event_content(event):
    """从事件中提取内容。"""
    if hasattr(event, "llm_message"):
        return "".join(content_to_str(event.llm_message.content))
    return str(event)


"""运行规划智能体工作流程示例。"""

# 创建临时工作区
workspace_dir = Path(tempfile.mkdtemp())
plan_path = workspace_dir / ".agents_tmp" / "PLAN.md"
print(f"Working in: {workspace_dir}")

# 配置LLM
api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
model = os.getenv("LLM_MODEL", "gpt-5.5")
base_url = os.getenv("LLM_BASE_URL")
llm = LLM(
    model=model,
    base_url=base_url,
    api_key=SecretStr(api_key),
    usage_id="agent",
)

# 任务描述
task = """
Create a Python web scraper with the following requirements:
- Scrape article titles and URLs from a news website
- Handle HTTP errors gracefully with retry logic
- Save results to a JSON file with timestamp
- Use requests and BeautifulSoup for scraping

Do NOT ask for any clarifying questions. Directly create your implementation plan.
"""

print("=" * 80)
print("PHASE 1: PLANNING")
print("=" * 80)

# 使用只读工具创建计划智能体
planning_agent = get_planning_agent(llm=llm)

# 创建对话以进行规划
planning_conversation = Conversation(
    agent=planning_agent,
    workspace=str(workspace_dir),
)

# 运行计划阶段
print("Planning Agent is analyzing the task and creating implementation plan...")
planning_conversation.send_message(
    f"Please analyze this web scraping task and create a detailed "
    f"implementation plan:\n\n{task}"
)
planning_conversation.run()

print("\n" + "=" * 80)
print("PLANNING COMPLETE")
print("=" * 80)
print(f"Implementation plan saved to: {plan_path}")

print("\n" + "=" * 80)
print("PHASE 2: EXECUTION")
print("=" * 80)

# 创建具有完整编辑功能的执行智能体
execution_agent = get_default_agent(llm=llm, cli_mode=True)

# 创建执行对话
execution_conversation = Conversation(
    agent=execution_agent,
    workspace=str(workspace_dir),
)

# 参考计划文件准备执行提示词
execution_prompt = f"""
Please implement the web scraping project according to the implementation plan.

The detailed implementation plan has been created and saved at: {plan_path}

Please read the plan from .agents_tmp/PLAN.md and implement all components
according to it.

Create all necessary files, implement the functionality, and ensure everything
works together properly.
"""

print("Execution Agent is implementing the plan...")
execution_conversation.send_message(execution_prompt)
execution_conversation.run()

# 获取对话中的最后一条消息
execution_result = execution_conversation.state.events[-1]

print("\n" + "=" * 80)
print("EXECUTION RESULT:")
print("=" * 80)
print(get_event_content(execution_result))

print("\n" + "=" * 80)
print("WORKFLOW COMPLETE")
print("=" * 80)
print(f"Project files created in: {workspace_dir}")

# 列出已创建的文件
print("\nCreated files:")
for file_path in workspace_dir.rglob("*"):
    if file_path.is_file():
        print(f"  - {file_path.relative_to(workspace_dir)}")

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
