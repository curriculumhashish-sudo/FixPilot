"""
智能体委托示例

此示例演示了智能体委托功能，其中包含一个主要的智能体将任务委派给子智能体用于并行处理
。 每个子智能体它独立运行并返回结果给主程序智能体然后将两份分析合并成一份综合报告。
"""

import os

from openhands.sdk import (
    LLM,
    Agent,
    AgentContext,
    Conversation,
    Tool,
    get_logger,
)
from openhands.sdk.context import Skill
from openhands.sdk.subagent import register_agent
from openhands.tools import register_builtins_agents
from openhands.tools.delegate import DelegationVisualizer
from openhands.tools.task import TaskToolSet


logger = get_logger(__name__)

# 配置LLM和智能体
llm = LLM(
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.environ.get("LLM_BASE_URL", None),
    usage_id="agent",
)


def create_lodging_planner(llm: LLM) -> Agent:
    """创建一个专注于伦敦住宿的住宿规划师。"""
    skills = [
        Skill(
            name="lodging_planning",
            content=(
                "You specialize in finding great places to stay in London. "
                "Provide 3-4 hotel recommendations with neighborhoods, quick "
                "pros/cons, "
                "and notes on transit convenience. Keep options varied by budget."
            ),
            trigger=None,
        )
    ]
    return Agent(
        llm=llm,
        tools=[],
        agent_context=AgentContext(
            skills=skills,
            system_message_suffix="Focus only on London lodging recommendations.",
        ),
    )


def create_activities_planner(llm: LLM) -> Agent:
    """创建一个专注于伦敦行程的活动计划。"""
    skills = [
        Skill(
            name="activities_planning",
            content=(
                "You design concise London itineraries. Suggest 2-3 daily "
                "highlights, grouped by proximity to minimize travel time. "
                "Include food/coffee stops "
                "and note required tickets/reservations."
            ),
            trigger=None,
        )
    ]
    return Agent(
        llm=llm,
        tools=[],
        agent_context=AgentContext(
            skills=skills,
            system_message_suffix="Plan practical, time-efficient days in London.",
        ),
    )


# 注册用户定义的智能体类型（默认智能体类型始终可用）
register_agent(
    name="lodging_planner",
    factory_func=create_lodging_planner,
    description="Finds London lodging options with transit-friendly picks.",
)
register_agent(
    name="activities_planner",
    factory_func=create_activities_planner,
    description="Creates time-efficient London activity itineraries.",
)
register_builtins_agents()

main_agent = Agent(
    llm=llm,
    tools=[Tool(name=TaskToolSet.name)],
    tool_concurrency_limit=2,
)
conversation = Conversation(
    agent=main_agent,
    workspace=os.getcwd(),
    visualizer=DelegationVisualizer(name="Delegator"),
)

print("=" * 100)
print("Demonstrating London trip delegation (lodging + activities)...")
print("=" * 100)

conversation.send_message("""
Let's plan a trip to London. I have two specific areas to address:

Lodging: What are the best areas to stay in while keeping a budget in mind?
Activities: What are the top five must-see attractions and hidden gems?

Please use the task tool to handle these two tasks in parallel.
Ensure the sub-agents use their own internal knowledge and do not
rely on internet access. Keep the responses concise.
Once you have the results, use the bash sub-agent to write a file
named london_trip_report.txt containing the findings in the working directory.
""")
conversation.run()

conversation.send_message(
    "Ask the lodging sub-agent what it thinks about Covent Garden."
)
conversation.run()

# 报告用户定义的智能体类型的成本示例
cost_user_defined = (
    conversation.conversation_stats.get_combined_metrics().accumulated_cost
)
print(f"EXAMPLE_COST: {cost_user_defined}")

print("All done!")
