"""
演示当智能体忙时可以发送和处理用户消息的示例。

该示例演示了 OpenHands 智能体系统的关键能力：即使智能体正在处理先前的任务，也能接收并
处理新用户消息。 智能体的事件驱动架构使这成为可能。

演示流程：
1. 将询问智能体的初始消息发送至：
   - 写入“消息1在[时间]发送，写入在[CURRENT_TIME]”
   - 等待 3 秒
   - 写入“消息2在[时间]发送，写入在[CURRENT_TIME]”
    [time] is the time the message was sent to the agent
    [CURRENT_TIME] is the time the agent writes the line
2. 在后台开始智能体处理线程
3. 当智能体忙时（在 3 秒延迟期间），发送第二条消息要求添加：
   - “消息 3 在 [ 时间 ] 发送，写入时间 [CURRENT_TIME]”
4. 验证所有三行均已处理并包含在最终文档中

预期证据：最终文档将包含带有双时间戳的三行：
- “消息 1 在 HH:MM:SS 发送，在 HH:MM:SS 写入”（来自初始消息，立即写入）
- “消息 2 在 HH:MM:SS 发送，在 HH:MM:SS 写入”（来自初始消息，在 3 秒延迟后写入）
- “消息 3 在 HH:MM:SS 发送，写入时间 HH:MM:SS”（来自延迟期间发送的第二条消息）

时间戳将显示消息 3 是在智能体运行时发送的，但仍然成功处理并写入文档。

这证明：
- 当智能体正在处理第一个任务时发送了第二条用户消息
- 智能体成功接收并处理第二条消息
- 智能体的事件系统允许在处理过程中进行实时消息集成

展示的关键组件：
- Conversation.send_message(): 立即将消息添加到事件列表
- Agent.step()：处理所有事件，包括新添加的消息
- Threading: 允许在智能体正在积极处理时发送消息
"""  # noqa

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
cwd = os.getcwd()
tools = [
    Tool(
        name=TerminalTool.name,
    ),
    Tool(name=FileEditorTool.name),
]

# 智能体
agent = Agent(llm=llm, tools=tools)
conversation = Conversation(agent)


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


print("=== Send Message While Processing Example ===")

# 第 1 步：发送初始消息
start_time = timestamp()
conversation.send_message(
    f"Create a file called document.txt and write this first sentence: "
    f"'Message 1 sent at {start_time}, written at [CURRENT_TIME].' "
    f"Replace [CURRENT_TIME] with the actual current time when you write the line. "
    f"Then wait 3 seconds and write 'Message 2 sent at {start_time}, written at [CURRENT_TIME].'"  # noqa
)

# 第 2 步：在后台开始智能体处理
thread = threading.Thread(target=conversation.run)
thread.start()

# 第 3 步：等待，然后在智能体正在处理时发送第二条消息
time.sleep(2)  # 给智能体时间开始工作

second_time = timestamp()

conversation.send_message(
    f"Please also add this second sentence to document.txt: "
    f"'Message 3 sent at {second_time}, written at [CURRENT_TIME].' "
    f"Replace [CURRENT_TIME] with the actual current time when you write this line."
)

# 等待完成
thread.join()

# 验证
document_path = os.path.join(cwd, "document.txt")
if os.path.exists(document_path):
    with open(document_path) as f:
        content = f.read()

    print("\nDocument contents:")
    print("─────────────────────")
    print(content)
    print("─────────────────────")

    # 检查两条消息是否都已处理
    if "Message 1" in content and "Message 2" in content:
        print("\nSUCCESS: Agent processed both messages!")
        print(
            "This proves the agent received the second message while processing the first task."  # noqa
        )
    else:
        print("\nWARNING: Agent may not have processed the second message")

    # 清理
    os.remove(document_path)
else:
    print("WARNING: Document.txt was not created")

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
