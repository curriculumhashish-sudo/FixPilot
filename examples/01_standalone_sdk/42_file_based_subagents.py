"""Example: 定义与 AgentDefinition 内联的子智能体。

使用 AgentDefinition 定义语法检查器子智能体，注册它，并将工作从协调器智能体委托给它。
"""

import os
from pathlib import Path

from openhands.sdk import (
    LLM,
    Agent,
    Conversation,
    Tool,
    agent_definition_to_factory,
    register_agent,
)
from openhands.sdk.subagent import AgentDefinition
from openhands.tools.delegate import DelegationVisualizer
from openhands.tools.task import TaskToolSet


# 1. 使用 AgentDefinition 定义子智能体
grammar_checker = AgentDefinition(
    name="grammar-checker",
    description="Checks documents for grammatical errors.",
    tools=["file_editor"],
    system_prompt="You are a grammar expert. Find and list grammatical errors.",
)

# 2. 在委托中注册它注册表
register_agent(
    name=grammar_checker.name,
    factory_func=agent_definition_to_factory(grammar_checker),
    description=grammar_checker,
)

# 3. 使用任务工具设置协调器智能体
llm = LLM(
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
    usage_id="file-agents-demo",
)

main_agent = Agent(
    llm=llm,
    tools=[Tool(name=TaskToolSet.name)],
)
conversation = Conversation(
    agent=main_agent,
    workspace=Path.cwd(),
    visualizer=DelegationVisualizer(name="Orchestrator"),
)

# 4. 要求协调器委托给我们的智能体
task = (
    "Please delegate to the grammar-checker agent and ask it to review "
    "the README.md file in search of grammatical errors."
)
conversation.send_message(task)
conversation.run()

cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
print(f"\nTotal cost: ${cost:.4f}")
print(f"EXAMPLE_COST: {cost:.4f}")
