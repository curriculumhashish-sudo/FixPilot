"""
要管理长时间运行的对话中的上下文，智能体可以使用上下文上下文压缩器将对话历史记录保持
在指定的大小限制内。 该示例演示了如何使用
`LLMSummarizingCondenser`，该功能在历史记录超过定义阈值时自动总结较旧的部分。
"""

import os

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Agent,
    Conversation,
    Event,
    LLMConvertibleEvent,
    get_logger,
)
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.sdk.tool import Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool


logger = get_logger(__name__)

# 配置LLM
api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
model = os.getenv("LLM_MODEL", "gpt-5.5")
base_url = os.getenv("LLM_BASE_URL")
llm = LLM(
    usage_id="agent",
    model=model,
    base_url=base_url,
    api_key=SecretStr(api_key),
)

# 工具
cwd = os.getcwd()
tools = [
    Tool(
        name=TerminalTool.name,
    ),
    Tool(name=FileEditorTool.name),
    Tool(name=TaskTrackerTool.name),
]

# 创建上下文压缩器来管理上下文。 当超过 max_size 时，上下文压缩器将自动截断对话历史记录
# ，并用
#  LLM-生成的摘要。 当事件超过十个时触发此上下文压缩器
# 对话历史记录，并始终保留前两个事件（系统提示词、初始用户消息）以保留重要的上下文。
#
condenser = LLMSummarizingCondenser(
    llm=llm.model_copy(update={"usage_id": "condenser"}), max_size=10, keep_first=2
)

# 智能体与上下文压缩器
agent = Agent(llm=llm, tools=tools, condenser=condenser)

llm_messages = []  # 收集原始 LLM 消息


def conversation_callback(event: Event):
    if isinstance(event, LLMConvertibleEvent):
        llm_messages.append(event.to_llm_message())


conversation = Conversation(
    agent=agent,
    callbacks=[conversation_callback],
    persistence_dir="./.conversations",
    workspace=".",
)

# 发送多条消息进行演示上下文压缩
print("Sending multiple messages to demonstrate LLM Summarizing Condenser...")

conversation.send_message(
    "Hello! Can you create a Python file named math_utils.py with functions for "
    "basic arithmetic operations (add, subtract, multiply, divide)?"
)
conversation.run()

conversation.send_message(
    "Great! Now add a function to calculate the factorial of a number."
)
conversation.run()

conversation.send_message("Add a function to check if a number is prime.")
conversation.run()

conversation.send_message(
    "Add a function to calculate the greatest common divisor (GCD) of two numbers."
)
conversation.run()

conversation.send_message(
    "Now create a test file to verify all these functions work correctly."
)
conversation.run()

print("=" * 100)
print("Conversation finished. Got the following LLM messages:")
for i, message in enumerate(llm_messages):
    print(f"Message {i}: {str(message)[:200]}")

# 对话持久化
print("Serializing conversation...")

del conversation

# 反序列化对话
print("Deserializing conversation...")
conversation = Conversation(
    agent=agent,
    callbacks=[conversation_callback],
    persistence_dir="./.conversations",
    workspace=".",
)

print("Sending message to deserialized conversation...")
conversation.send_message("Finally, clean up by deleting both files.")
conversation.run()

print("=" * 100)
print("Conversation finished with LLM Summarizing Condenser.")
print(f"Total LLM messages collected: {len(llm_messages)}")
print("\nThe condenser automatically summarized older conversation history")
print("when the conversation exceeded the configured max_size threshold.")
print("This helps manage context length while preserving important information.")

# 报告费用
cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
print(f"EXAMPLE_COST: {cost}")
