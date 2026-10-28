"""对话中模式切换。

用途：
    uv run examples/01_standalone_sdk/44_model_switching_in_convo.py
"""

import os

from openhands.sdk import LLM, Agent, LocalConversation, Tool
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.tools.terminal import TerminalTool


LLM_API_KEY = os.getenv("LLM_API_KEY")
store = LLMProfileStore()

store.save(
    "gpt",
    LLM(model="openhands/gpt-5.2", api_key=LLM_API_KEY),
    include_secrets=True,
)

agent = Agent(
    llm=LLM(
        model=os.getenv("LLM_MODEL", "gpt-5.5"),
        api_key=LLM_API_KEY,
    ),
    tools=[Tool(name=TerminalTool.name)],
)
conversation = LocalConversation(agent=agent, workspace=os.getcwd())

# 使用默认模型发送消息
conversation.send_message("Say hello in one sentence.")
conversation.run()

# 切换到不同的型号并发送另一条消息
conversation.switch_profile("gpt")
print(f"Switched to: {conversation.agent.llm.model}")

conversation.send_message("Say goodbye in one sentence.")
conversation.run()

# 打印每个模型的指标
for usage_id, metrics in conversation.state.stats.usage_to_metrics.items():
    print(f"  [{usage_id}] cost=${metrics.accumulated_cost:.6f}")

combined = conversation.state.stats.get_combined_metrics()
print(f"Total cost: ${combined.accumulated_cost:.6f}")
print(f"EXAMPLE_COST: {combined.accumulated_cost}")

store.delete("gpt")
