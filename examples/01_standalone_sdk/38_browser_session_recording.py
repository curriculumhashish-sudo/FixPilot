"""浏览器会话录制示例

示例展示了如何使用浏览器会话录制功能来捕获并保存智能体的浏览器交互记录。

稍后可以使用 rrweb-player 重播该记录，以可视化智能体的浏览会话。

当调用browser_stop_recording时，录音会自动保存到持久化目录中。 您可以通过以下方式重播
：
    - rrweb 播放器：
    https://github.com/rrweb-io/rrweb/tree/master/packages/rrweb-player
    - 在线浏览： https://www.rrweb.io/demo/
"""

import json
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
from openhands.sdk.tool import Tool
from openhands.tools.browser_use import BrowserToolSet
from openhands.tools.browser_use.definition import (
    BROWSER_RECORDING_OUTPUT_DIR,
    BrowserNavigateAction,
)


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

# 工具 - 包括具有录制功能的浏览器工具
cwd = os.getcwd()
tools = [
    Tool(name=BrowserToolSet.name),
]

# 智能体
agent = Agent(llm=llm, tools=tools)

llm_messages = []  # 收集原始 LLM 消息


def conversation_callback(event: Event):
    if isinstance(event, LLMConvertibleEvent):
        llm_messages.append(event.to_llm_message())


# 创建对话并将 persistence_dir 设置为保存浏览器录音
conversation = Conversation(
    agent=agent,
    callbacks=[conversation_callback],
    workspace=cwd,
    persistence_dir="./.conversations",
)

# 提示词指示智能体：
# 1. 开始记录浏览器会话
# 2. 导航到页面并获取其内容
# 3. 停止录音（自动保存到文件）
PROMPT = """
Please complete the following task to demonstrate browser session recording:

1. Use `browser_start_recording` to begin recording.
2. Navigate to https://docs.openhands.dev/ and:
    - Get the page content
    - Scroll down the page
    - Get the browser state to see interactive elements
3. Use `browser_stop_recording` to stop and save the recording.
"""

print("=" * 80)
print("Browser Session Recording Example")
print("=" * 80)
print("\nTask: Record an agent's browser session and save it for replay")

# 预初始化浏览器，以便 CDP 在智能体启动之前准备就绪。 这可以避免在浏览器无法连接时浪费
# LLM 调用。
#
print("\nInitializing browser...")

init_obs = conversation.execute_tool(
    "browser_navigate",
    BrowserNavigateAction(url="about:blank"),
)
if init_obs.is_error:
    print(f"Browser initialization failed: {init_obs.text}")
    print("Ensure Chrome/Chromium is installed and accessible.")
    exit(1)
print("Browser initialized successfully.\n")

print("Starting conversation with agent...\n")

conversation.send_message(PROMPT)
conversation.run()

print("\n" + "=" * 80)
print("Conversation finished!")
print("=" * 80)

# 检查录音文件是否创建录音保存在BROWSER_RECORDING_OUTPUT_DIR/recording-{timestamp}/
#
if os.path.exists(BROWSER_RECORDING_OUTPUT_DIR):
    # 查找录音子目录（以“录音-”开头）
    recording_dirs = sorted(
        [
            d
            for d in os.listdir(BROWSER_RECORDING_OUTPUT_DIR)
            if d.startswith("recording-")
            and os.path.isdir(os.path.join(BROWSER_RECORDING_OUTPUT_DIR, d))
        ]
    )

    if recording_dirs:
        # 处理最近的录音目录
        latest_recording = recording_dirs[-1]
        recording_path = os.path.join(BROWSER_RECORDING_OUTPUT_DIR, latest_recording)
        json_files = sorted(
            [f for f in os.listdir(recording_path) if f.endswith(".json")]
        )

        print(f"\n✓ Recording saved to: {recording_path}")
        print(f"✓ Number of files: {len(json_files)}")

        # 计算所有文件中的事件总数
        total_events = 0
        all_event_types: dict[int | str, int] = {}
        total_size = 0

        for json_file in json_files:
            filepath = os.path.join(recording_path, json_file)
            file_size = os.path.getsize(filepath)
            total_size += file_size

            with open(filepath) as f:
                events = json.load(f)

            # 事件以列表形式存储在每个文件中
            if isinstance(events, list):
                total_events += len(events)
                for event in events:
                    event_type = event.get("type", "unknown")
                    all_event_types[event_type] = all_event_types.get(event_type, 0) + 1

            print(f"  - {json_file}: {len(events)} events, {file_size} bytes")

        print(f"✓ Total events: {total_events}")
        print(f"✓ Total size: {total_size} bytes")
        if all_event_types:
            print(f"✓ Event types: {all_event_types}")

        print("\nTo replay this recording, you can use:")
        print(
            "  - rrweb-player: "
            "https://github.com/rrweb-io/rrweb/tree/master/packages/rrweb-player"
        )
    else:
        print(f"\n✗ No recording directories found in: {BROWSER_RECORDING_OUTPUT_DIR}")
        print("  The agent may not have completed the recording task.")
else:
    print(f"\n✗ Observations directory not found: {BROWSER_RECORDING_OUTPUT_DIR}")
    print("  The agent may not have completed the recording task.")

print("\n" + "=" * 100)
print("Conversation finished.")
print(f"Total LLM messages: {len(llm_messages)}")
print("=" * 100)

# 报告费用
cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
print(f"Conversation ID: {conversation.id}")
print(f"EXAMPLE_COST: {cost}")

# 关闭对话以关闭浏览器和其他工具执行器
conversation.close()
