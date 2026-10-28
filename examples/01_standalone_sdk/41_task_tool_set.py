"""
带任务工具集的动物测验

演示 TaskToolSet，并将主要智能体委托给动物专家子智能体。 流程是：

1. Main 智能体选择一种动物并委托给“animal_expert”子智能体来生成有关它的多项选择题。
2. Main 智能体思考问题并选择答案。
3. Main 智能体恢复相同的子智能体对话，询问其答案是否正确。 子智能体证实或更正了它。
"""

import os

from openhands.sdk import LLM, Agent, AgentContext, Conversation, Tool
from openhands.sdk.context import Skill
from openhands.sdk.subagent import register_agent
from openhands.tools.delegate import DelegationVisualizer
from openhands.tools.task import TaskToolSet


llm = LLM(
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL", None),
)
# ── 注册动物专家子智能体 ──────────────────────────────


def create_animal_expert(llm: LLM) -> Agent:
    """动物专家工厂子智能体。"""
    return Agent(
        llm=llm,
        tools=[],  # 无需工具——纯知识
        agent_context=AgentContext(
            skills=[
                Skill(
                    name="animal_expertise",
                    content=(
                        "You are a world-class zoologist. "
                        "When asked to generate a quiz question, respond with "
                        "EXACTLY this format and nothing else:\n\n"
                        "Question: <question text>\n"
                        "A) <option>\n"
                        "B) <option>\n"
                        "C) <option>\n"
                        "D) <option>\n\n"
                        "When asked to verify an answer, state whether it is "
                        "correct or incorrect, reveal the right answer, and "
                        "give a short fun-fact explanation."
                    ),
                    trigger=None,  # 总是活跃的
                )
            ],
            system_message_suffix="Keep every response concise.",
        ),
    )


register_agent(
    name="animal_expert",
    factory_func=create_animal_expert,
    description="Zoologist that creates and verifies animal quiz questions.",
)

# ── 主要智能体 ──────────────────────────────────────────────────────────

main_agent = Agent(
    llm=llm,
    tools=[Tool(name=TaskToolSet.name)],
)

conversation = Conversation(
    agent=main_agent,
    workspace=os.getcwd(),
    visualizer=DelegationVisualizer(name="QuizHost"),
)

# ── 第一轮：生成问题──────────────────────────────────

conversation.send_message(
    "Pick any animal you like and use the task tool to delegate to the "
    "'animal_expert' sub-agent. Ask it to generate a single "
    "multiple-choice question (A-D) about that animal. "
    "Once you get the question back, think step-by-step about which "
    "answer is correct and pick one (A, B, C, or D). Tell the user "
    "the question and your chosen answer."
)
conversation.run()

# ── 第二轮：验证答案──────────────────────────────────────

conversation.send_message(
    "Now use the task tool to resume the previous 'animal_expert' "
    "sub-agent conversation. Tell it which answer you picked and ask "
    "it whether that answer is correct. Report the result to the user."
)
conversation.run()

# ── 完成了────────────────────────────────────────────────────────────

cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
print(f"\nEXAMPLE_COST: {cost}")
