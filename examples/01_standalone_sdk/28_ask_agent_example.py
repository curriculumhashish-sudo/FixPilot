"""
演示获取侧边栏回复的 ask_agent 功能的示例
from the agent for a running conversation.

此示例展示了如何使用 ask_agent快速回复的快捷方式智能体不打断主执行流程，获取当前对话
状态。
"""

import os
import threading
import time
from datetime import datetime

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Agent,
    Conversation,
)
from openhands.sdk.conversation import ConversationVisualizerBase
from openhands.sdk.event import Event
from openhands.sdk.tool import Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool


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
    Tool(name=TerminalTool.name),
    Tool(name=FileEditorTool.name),
    Tool(name=TaskTrackerTool.name),
]


class MinimalVisualizer(ConversationVisualizerBase):
    """一个最小的可视化工具，可以在原始事件发生时打印它们。"""

    count = 0

    def on_event(self, event: Event) -> None:
        """处理事件以实现最小进度可视化。"""
        print(f"\n\n[EVENT {self.count}] {type(event).__name__}")
        self.count += 1


# 智能体
agent = Agent(llm=llm, tools=tools)
conversation = Conversation(
    agent=agent, workspace=cwd, visualizer=MinimalVisualizer, max_iteration_per_run=5
)


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


print("=== Ask Agent Example ===")
print("This example demonstrates asking questions during conversation execution")

# 第 1 步：建立对话上下文
print(f"\n[{timestamp()}] Building conversation context...")
conversation.send_message("Explore the current directory and describe the architecture")

# 第 2 步：在后台开始对话线程
print(f"[{timestamp()}] Starting conversation in background thread...")
thread = threading.Thread(target=conversation.run)
thread.start()

# 给智能体时间开始处理
time.sleep(2)

# 第 3 步：在对话进行时使用 ask_agent
print(f"\n[{timestamp()}] Using ask_agent while conversation is processing...")

# 提出上下文相关问题
questions_and_responses = []

question_1 = "Summarize the activity so far in 1 sentence."
print(f"\n[{timestamp()}] Asking: {question_1}")
response1 = conversation.ask_agent(question_1)
questions_and_responses.append((question_1, response1))
print(f"Response: {response1}")

time.sleep(1)

question_2 = "How's the progress?"
print(f"\n[{timestamp()}] Asking: {question_2}")
response2 = conversation.ask_agent(question_2)
questions_and_responses.append((question_2, response2))
print(f"Response: {response2}")

time.sleep(1)

question_3 = "Have you finished running?"
print(f"\n[{timestamp()}] {question_3}")
response3 = conversation.ask_agent(question_3)
questions_and_responses.append((question_3, response3))
print(f"Response: {response3}")

# 第 4 步：等待对话完成
print(f"\n[{timestamp()}] Waiting for conversation to complete...")
thread.join()

# 第 5 步：验证对话状态未受影响
final_event_count = len(conversation.state.events)
# 第 6 步：对话结束后提出最后一个问题
print(f"\n[{timestamp()}] Asking final question after completion...")
final_response = conversation.ask_agent(
    "Can you summarize what you accomplished in this conversation?"
)
print(f"Final response: {final_response}")

# 第 7 步：总结
print("\n" + "=" * 60)
print("SUMMARY OF ASK_AGENT DEMONSTRATION")
print("=" * 60)

print("\nQuestions and Responses:")
for i, (question, response) in enumerate(questions_and_responses, 1):
    print(f"\n{i}. Q: {question}")
    print(f"   A: {response[:100]}{'...' if len(response) > 100 else ''}")

final_truncated = final_response[:100] + ("..." if len(final_response) > 100 else "")
print(f"\nFinal Question Response: {final_truncated}")

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost:.4f}")
