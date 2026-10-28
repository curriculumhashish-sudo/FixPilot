"""
Example: 在真实智能体对话中通过 LiteLLM 响应 API 路径

- 运行真实的代理/对话来验证 /responses 路径是否有效
- 演示在正常对话事件中呈现响应推理
"""

from __future__ import annotations

import os

from pydantic import SecretStr

from openhands.sdk import (
    Conversation,
    Event,
    LLMConvertibleEvent,
    get_logger,
)
from openhands.sdk.llm import LLM
from openhands.tools.preset.default import get_default_agent


logger = get_logger(__name__)

api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
assert api_key, "Set LLM_API_KEY or OPENAI_API_KEY in your environment."

model = "openhands/gpt-5-mini-2025-08-07"  # 使用支持响应的模型 API
base_url = os.getenv("LLM_BASE_URL")

llm = LLM(
    model=model,
    api_key=SecretStr(api_key),
    base_url=base_url,
    # 响应路径选项
    reasoning_effort="high",
    # 日志记录/行为调整
    log_completions=False,
    usage_id="agent",
)

print("\n=== Agent Conversation using /responses path ===")
agent = get_default_agent(
    llm=llm,
    cli_mode=True,  # 禁用浏览器工具以简化环境
)

llm_messages = []  # 收集原始 LLM-可转换消息以供检查


def conversation_callback(event: Event):
    if isinstance(event, LLMConvertibleEvent):
        llm_messages.append(event.to_llm_message())


conversation = Conversation(
    agent=agent,
    callbacks=[conversation_callback],
    workspace=os.getcwd(),
)

# 出于演示目的，请保持任务简短
conversation.send_message("Read the repo and write one fact into FACTS.txt.")
conversation.run()

conversation.send_message("Now delete FACTS.txt.")
conversation.run()

print("=" * 100)
print("Conversation finished. Got the following LLM messages:")
for i, message in enumerate(llm_messages):
    ms = str(message)
    print(f"Message {i}: {ms[:200]}{'...' if len(ms) > 200 else ''}")

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
