"""OpenHands 智能体 SDK — 可配置的安全策略示例

此示例演示如何将自定义安全策略与智能体结合使用。 安全策略定义了风险评估指南，有助于智
能体评估其行为的安全性。

默认情况下，智能体使用系统提示词中内置的安全策略（由 Python 提示词注册表组装而成； 没
有模板文件）。 此示例演示如何：
1. 使用默认安全策略
2. 提供嵌入在脚本中的自定义安全策略
3. 应用自定义策略来指导智能体行为
"""

import os
import tempfile
from pathlib import Path

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
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool


logger = get_logger(__name__)

# 定义内联的自定义安全策略（逐字插入，而不是 Jinja 渲染）
CUSTOM_SECURITY_POLICY = (
    "# 🔐 Custom Security Risk Policy\n"
    "When using tools that support the security_risk parameter, assess the "
    "safety risk of your actions:\n"
    "\n"
    "- **LOW**: Safe read-only actions.\n"
    "  - Viewing files, calculations, documentation.\n"
    "- **MEDIUM**: Moderate container-scoped actions.\n"
    "  - File modifications, package installations.\n"
    "- **HIGH**: Potentially dangerous actions.\n"
    "  - Network access, system modifications, data exfiltration.\n"
    "\n"
    "**Custom Rules**\n"
    "- Always prioritize user data safety.\n"
    "- Escalate to **HIGH** for any external data transmission.\n"
)

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

# 示例 1：智能体使用默认安全策略
print("=" * 100)
print("Example 1: Agent with default security policy")
print("=" * 100)
default_agent = Agent(llm=llm, tools=tools)
print(f"Security policy filename: {default_agent.security_policy_filename}")
print("\nDefault security policy is embedded in the agent's system message.")

# 示例 2：智能体具有自定义安全策略
print("\n" + "=" * 100)
print("Example 2: Agent with custom security policy")
print("=" * 100)

# 为自定义安全策略创建临时文件
with tempfile.NamedTemporaryFile(
    mode="w", suffix=".md", delete=False, encoding="utf-8"
) as temp_file:
    temp_file.write(CUSTOM_SECURITY_POLICY)
    custom_policy_path = temp_file.name

try:
    # 使用自定义安全策略创建智能体（使用绝对路径）
    custom_agent = Agent(
        llm=llm,
        tools=tools,
        security_policy_filename=custom_policy_path,
    )
    print(f"Security policy filename: {custom_agent.security_policy_filename}")
    print("\nCustom security policy loaded from temporary file.")

    # 验证自定义策略是否在系统消息中
    system_message = custom_agent.static_system_message
    if "Custom Security Risk Policy" in system_message:
        print("✓ Custom security policy successfully embedded in system message.")
    else:
        print("✗ Custom security policy not found in system message.")

    # 与自定义智能体进行对话
    print("\n" + "=" * 100)
    print("Running conversation with custom security policy")
    print("=" * 100)

    llm_messages = []  # 收集原始 LLM 消息

    def conversation_callback(event: Event):
        if isinstance(event, LLMConvertibleEvent):
            llm_messages.append(event.to_llm_message())

    conversation = Conversation(
        agent=custom_agent,
        callbacks=[conversation_callback],
        workspace=".",
    )

    conversation.send_message(
        "Please create a simple Python script named hello.py that prints "
        "'Hello, World!'. Make sure to follow security best practices."
    )
    conversation.run()

    print("\n" + "=" * 100)
    print("Conversation finished.")
    print(f"Total LLM messages: {len(llm_messages)}")
    print("=" * 100)

    # 报告费用
    cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
    print(f"EXAMPLE_COST: {cost}")

finally:
    # 清理临时文件
    Path(custom_policy_path).unlink(missing_ok=True)

print("\n" + "=" * 100)
print("Example Summary")
print("=" * 100)
print("This example demonstrated:")
print("1. Using the built-in default security policy")
print("2. Creating a custom security policy")
print("3. Applying the custom policy via security_policy_filename parameter")
print("4. Running a conversation with the custom security policy")
print(
    "\nYou can customize security policies to match your organization's "
    "specific requirements."
)
