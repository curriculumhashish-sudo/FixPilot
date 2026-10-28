"""Example: 使用ACPAgent与Claude CodeACP服务器。

此示例演示如何使用 ACP 兼容服务器 (claude-智能体-ACP) 作为智能体后端，而不是直接 LLM
调用。 它还演示了
``ask_agent()`` — 一个状态机侧问题，它会分叉 ACP 会话，但不会影响主对话 — 并通过文本
和图片一起发送以验证多模态（视觉）输入支持。

先决条件：
    - Node.js / npx 可用
    - ANTHROPIC_BASE_URL和ANTHROPIC_API_KEY设置（可以指向LiteLLM代理）

用途：
    uv run python examples/01_standalone_sdk/40_acp_agent_example.py
"""

import os

from openhands.sdk import ImageContent, Message, TextContent
from openhands.sdk.agent import ACPAgent
from openhands.sdk.conversation import Conversation
from openhands.sdk.settings.acp_providers import ACP_PROVIDERS


IMAGE_URL = "https://www.python.org/static/opengraph-icon-200x200.png"

agent = ACPAgent(acp_command=list(ACP_PROVIDERS["claude-code"].default_command))

try:
    cwd = os.getcwd()
    conversation = Conversation(agent=agent, workspace=cwd)

    # --- 主要对话轮次（仅限文本）---
    conversation.send_message(
        "List the Python source files under openhands-sdk/openhands/sdk/agent/, "
        "then read the __init__.py and summarize what agent classes are exported."
    )
    conversation.run()

    # --- 图片输入转（文字+图片）---
    print("\n--- image input ---")
    conversation.send_message(
        Message(
            role="user",
            content=[
                TextContent(
                    text="Describe what you see in this image in one sentence."
                ),
                ImageContent(image_urls=[IMAGE_URL]),
            ],
        )
    )
    conversation.run()

    # --- ask_agent：通过 fork_session 的无状态附带问题 ---
    print("\n--- ask_agent ---")
    response = conversation.ask_agent(
        "Based on what you just saw, which agent class is the newest addition?"
    )
    print(f"ask_agent response: {response}")
    # 报告成本（ACP 服务器通过 session_update 通知报告使用情况）
    cost = agent.llm.metrics.accumulated_cost
    print(f"EXAMPLE_COST: {cost:.4f}")
finally:
    # 清理 ACP 服务器子进程
    agent.close()

cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
print(f"\nEXAMPLE_COST: {cost}")
print("Done!")
