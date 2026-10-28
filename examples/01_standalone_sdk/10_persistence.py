import os
import uuid

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Agent,
    Conversation,
    Event,
    LLMConvertibleEvent,
    get_logger,
)
from openhands.sdk.mcp import MCPServer
from openhands.sdk.tool import Tool
from openhands.tools.file_editor import FileEditorTool
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
    Tool(name=TerminalTool.name),
    Tool(name=FileEditorTool.name),
]

# 添加 MCP 工具
mcp_config = {
    "fetch": MCPServer(
        command="uvx",
        args=["--with", "mcp==1.29.0", "mcp-server-fetch==2026.7.10"],
    ),
}
# 智能体
agent = Agent(llm=llm, tools=tools, mcp_config=mcp_config)

llm_messages = []  # 收集原始 LLM 消息


def conversation_callback(event: Event):
    if isinstance(event, LLMConvertibleEvent):
        llm_messages.append(event.to_llm_message())


conversation_id = uuid.uuid4()
persistence_dir = "./.conversations"

conversation = Conversation(
    agent=agent,
    callbacks=[conversation_callback],
    workspace=cwd,
    persistence_dir=persistence_dir,
    conversation_id=conversation_id,
)
conversation.send_message(
    "Read https://github.com/OpenHands/OpenHands. Then write 3 facts "
    "about the project into FACTS.txt."
)
conversation.run()

conversation.send_message("Great! Now delete that file.")
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
    workspace=cwd,
    persistence_dir=persistence_dir,
    conversation_id=conversation_id,
)

print("Sending message to deserialized conversation...")
conversation.send_message("Hey what did you create? Return an agent finish action")
conversation.run()

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
