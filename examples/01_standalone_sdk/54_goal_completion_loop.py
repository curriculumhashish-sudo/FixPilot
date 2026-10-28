"""/goal 命令：追求一个目标，直到法官 LLM 确认目标已完成。

A plain ``conversation.run()`` 停止当智能体  *认为* 已完成。 的 ``/goal`` 循环更加严
格：每次运行后，它都会问一个“裁判”
LLM 审核转录以获取权威证据 -- 文件内容、命令输出、测试结果 -- 以证明目标是 *provably*
 完成。 如果还有缺失的部分，请继续提示词的智能体在法官的反馈下
再次运行，直到目标真正实现或达到硬迭代上限。

这使得它非常适合可验证的目标，例如“让测试通过”：智能体不能仅仅通过声称成功来完成； 法
官必须首先看到绿色输出。

演示的关键概念：
1. ``run_goal(conversation, objective, judge_llm, max_iterations=...)``从外部驱动对话
，重新提示，直到
法官满意为止。
2. 第二个独立的“法官”LLM 对完成情况进行评分——独立于完成工作的智能体。
3. 返回的 ``GoalOutcome`` 报告目标 ``"complete"``-d 是否为
   ``"capped"``，经过了多少轮审核，以及法官的最终判决。

因为 ``run_goal`` 驱动你传入的对话（它不会分叉或旋转 sidecar），所以每个回合——目标，
智能体工作，判断驱动的后续行动
——同样的``conversation.state.events``历史。 因此它
使用您已有的任何智能体、工具或评论家进行创作。
"""

import os
import tempfile

from openhands.sdk import LLM, Agent, Conversation, Tool
from openhands.sdk.conversation.goal import run_goal
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool


# 智能体 LLM 完成这项工作； 评委LLM独立对完成情况进行评分。 两个独立的实例（相同的模型，
# 不同的 usage_id）使它们的成本分开。
#
model = os.getenv("LLM_MODEL", "gpt-5.5")
api_key = os.getenv("LLM_API_KEY")
base_url = os.getenv("LLM_BASE_URL")
agent_llm = LLM(usage_id="agent", model=model, api_key=api_key, base_url=base_url)
judge_llm = LLM(usage_id="goal-judge", model=model, api_key=api_key, base_url=base_url)

agent = Agent(
    llm=agent_llm,
    tools=[Tool(name=TerminalTool.name), Tool(name=FileEditorTool.name)],
)

workspace = tempfile.mkdtemp(prefix="goal_demo_")
conversation = Conversation(agent=agent, workspace=workspace)

# 可验证的目标：法官只有在看到后才能宣布其完成
# pytest actually pass -- not merely the agent asserting that it did.
objective = (
    "Create mathx.py with an add(a, b) function and test_mathx.py with a pytest "
    "test for it. The goal is complete only when `python -m pytest -q` passes."
)

# 将对话推向目标，每次运行后重新判断。
outcome = run_goal(conversation, objective, judge_llm, max_iterations=3)

print("\n" + "=" * 70)
print(f"Goal {outcome.status} after {outcome.iterations} audit round(s).")
print(f"Judge score: {outcome.verdict.score:.2f}")
if outcome.verdict.missing:
    print(f"Still missing: {outcome.verdict.missing}")
print(f"Workspace: {workspace}")
print("=" * 70)

# 报告成本（智能体工作+法官审核）。
cost = agent_llm.metrics.accumulated_cost + judge_llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
