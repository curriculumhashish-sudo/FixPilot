"""使用思维块演示 Anthropic 的扩展思维功能的示例。"""

import os

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Agent,
    Conversation,
    Event,
    LLMConvertibleEvent,
    RedactedThinkingBlock,
    ThinkingBlock,
)
from openhands.sdk.tool import Tool
from openhands.tools.terminal import TerminalTool


# 配置具有扩展思维的 Anthropic 模型。
api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
model = os.getenv("LLM_MODEL")
assert model is not None, (
    "LLM_MODEL environment variable is not set. Use an Anthropic model, "
    "for example anthropic/claude-sonnet-4-5-20250929."
)
base_url = os.getenv("LLM_BASE_URL")

llm = LLM(
    usage_id="agent",
    model=model,
    base_url=base_url,
    api_key=SecretStr(api_key),
)

# 使用 bash 工具设置智能体
agent = Agent(llm=llm, tools=[Tool(name=TerminalTool.name)])


# 回调展示思维方块
def show_thinking(event: Event):
    if isinstance(event, LLMConvertibleEvent):
        message = event.to_llm_message()
        if hasattr(message, "thinking_blocks") and message.thinking_blocks:
            print(f"\n🧠 Found {len(message.thinking_blocks)} thinking blocks")
            for i, block in enumerate(message.thinking_blocks):
                if isinstance(block, RedactedThinkingBlock):
                    print(f"  Block {i + 1}: {block.data}")
                elif isinstance(block, ThinkingBlock):
                    print(f"  Block {i + 1}: {block.thinking}")


conversation = Conversation(
    agent=agent, callbacks=[show_thinking], workspace=os.getcwd()
)

conversation.send_message(
    "Calculate compound interest for $10,000 at 5% annually, "
    "compounded quarterly for 3 years. Show your work.",
)
conversation.run()

conversation.send_message(
    "Now, write that number to RESULTs.txt.",
)
conversation.run()
print("✅ Done!")

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
