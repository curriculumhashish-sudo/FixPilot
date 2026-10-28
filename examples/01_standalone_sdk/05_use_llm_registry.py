import os

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Agent,
    Conversation,
    Event,
    LLMConvertibleEvent,
    LLMRegistry,
    Message,
    TextContent,
    get_logger,
)
from openhands.sdk.tool import Tool
from openhands.tools.terminal import TerminalTool


logger = get_logger(__name__)

# 使用LLMRegistry配置LLM
api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
model = os.getenv("LLM_MODEL", "gpt-5.5")
base_url = os.getenv("LLM_BASE_URL")

# 创建 LLM 个实例
main_llm = LLM(
    usage_id="agent",
    model=model,
    base_url=base_url,
    api_key=SecretStr(api_key),
)

# 创建 LLM 注册表并添加 LLM
llm_registry = LLMRegistry()
llm_registry.add(main_llm)

# 从注册表获取 LLM
llm = llm_registry.get("agent")

# 工具
cwd = os.getcwd()
tools = [Tool(name=TerminalTool.name)]

# 智能体
agent = Agent(llm=llm, tools=tools)

llm_messages = []  # 收集原始 LLM 消息


def conversation_callback(event: Event):
    if isinstance(event, LLMConvertibleEvent):
        llm_messages.append(event.to_llm_message())


conversation = Conversation(
    agent=agent, callbacks=[conversation_callback], workspace=cwd
)

conversation.send_message("Please echo 'Hello!'")
conversation.run()

print("=" * 100)
print("Conversation finished. Got the following LLM messages:")
for i, message in enumerate(llm_messages):
    print(f"Message {i}: {str(message)[:200]}")

print("=" * 100)
print(f"LLM Registry usage IDs: {llm_registry.list_usage_ids()}")

# 演示从注册表获取相同的 LLM 实例
same_llm = llm_registry.get("agent")
print(f"Same LLM instance: {llm is same_llm}")

# 演示直接从 LLM 请求完成
resp = llm.completion(
    messages=[
        Message(role="user", content=[TextContent(text="Say hello in one word.")])
    ]
)
# 通过 OpenHands LLMResponse 访问响应内容
msg = resp.message
texts = [c.text for c in msg.content if isinstance(c, TextContent)]
print(f"Direct completion response: {texts[0] if texts else str(msg)}")

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
