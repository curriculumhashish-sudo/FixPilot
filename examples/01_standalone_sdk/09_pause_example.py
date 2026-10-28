import os
import threading
import time

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Agent,
    Conversation,
)
from openhands.sdk.tool import Tool
from openhands.tools.file_editor import FileEditorTool
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
tools = [
    Tool(
        name=TerminalTool.name,
    ),
    Tool(name=FileEditorTool.name),
]

# 智能体
agent = Agent(llm=llm, tools=tools)
conversation = Conversation(agent, workspace=os.getcwd())

print("=" * 60)
print("Pause and Continue Example")
print("=" * 60)
print()

# 第 1 阶段：启动长时间运行的任务
print("Phase 1: Starting agent with a task...")
conversation.send_message(
    "Create a file called countdown.txt and write numbers from 100 down to 1, "
    "one number per line. After you finish, summarize what you did."
)

print(f"Initial status: {conversation.state.execution_status}")
print()

# 在后台启动智能体线程
thread = threading.Thread(target=conversation.run)
thread.start()

# 让智能体工作几秒钟
print("Letting agent work for 2 seconds...")
time.sleep(2)

# 第 2 阶段：暂停智能体
print()
print("Phase 2: Pausing the agent...")
conversation.pause()

# 等待线程完成（暂停时会停止）
thread.join()

print(f"Agent status after pause: {conversation.state.execution_status}")
print()

# 第 3 阶段：暂停时发送新消息
print("Phase 3: Sending a new message while agent is paused...")
conversation.send_message(
    "Actually, stop working on countdown.txt. Instead, create a file called "
    "hello.txt with just the text 'Hello, World!' in it."
)
print()

# 第 4 阶段：使用 .run() 恢复智能体
print("Phase 4: Resuming agent with .run()...")
print(f"Status before resume: {conversation.state.execution_status}")

# 恢复执行
conversation.run()

print(f"Final status: {conversation.state.execution_status}")

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
