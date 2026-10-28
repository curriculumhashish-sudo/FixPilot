"""创建序列化和反序列化 OpenHandsAgentSettings，然后构建智能体。

演示：
1. 完全通过 OpenHandsAgentSettings 配置智能体（LLM、工具、上下文压缩器）。
2. 将设置序列化为 JSON 并恢复它们。
3. 通过 ``create_agent()`` 从设置构建智能体。
4. 运行一个简短的对话来证明设置生效。
5. 更改工具列表并显示智能体的功能更改。
"""

import json
import os

from pydantic import SecretStr

from openhands.sdk import LLM, Conversation, OpenHandsAgentSettings, Tool
from openhands.sdk.settings import LLMSummarizingCondenserSettings
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool


# ── 1. 构建设置────────────────────────────────────────────────────
api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."

settings = OpenHandsAgentSettings(
    llm=LLM(
        model=os.getenv("LLM_MODEL", "gpt-5.5"),
        api_key=SecretStr(api_key),
        base_url=os.getenv("LLM_BASE_URL"),
    ),
    tools=[
        Tool(name=TerminalTool.name),
        Tool(name=FileEditorTool.name),
    ],
    condenser=LLMSummarizingCondenserSettings(enabled=True, max_size=50),
)

# ── 2. 序列化 → JSON → 反序列化 ────────────────────────────────────
payload = settings.model_dump(mode="json")
print("Serialized settings (JSON):")
print(json.dumps(payload, indent=2, default=str)[:800], "…")
print()

restored = OpenHandsAgentSettings.model_validate(payload)
assert restored.condenser.enabled is True
assert restored.condenser.max_size == 50
assert restored.tools is not None and len(restored.tools) == 2
print("✓ Roundtrip deserialization successful — all fields preserved")
print()

# ── 3. 从设置中创建智能体并运行任务──────────────────────────
agent = settings.create_agent()
print(f"Agent created: llm.model={agent.llm.model}")
print(f"  tools={[t.name for t in agent.tools]}")
print(f"  condenser={type(agent.condenser).__name__}")
print()

cwd = os.getcwd()
conversation = Conversation(agent=agent, workspace=cwd)
conversation.send_message(
    "Create a file called hello_settings.txt containing "
    "'Agent settings work!' then confirm the file exists with ls."
)
conversation.run()

# 验证智能体确实写入了该文件
assert os.path.exists(os.path.join(cwd, "hello_settings.txt")), (
    "Agent should have created hello_settings.txt"
)
print("✓ Agent created hello_settings.txt — settings drove real behavior")
print()

# ── 4. 不同的设置 → 不同的行为 ──────────────────────────── 现在使用仅终端工具并禁用上
# 下文压缩器来创建设置。
#
terminal_only_settings = OpenHandsAgentSettings(
    llm=settings.llm,
    tools=[Tool(name=TerminalTool.name)],
    condenser=LLMSummarizingCondenserSettings(enabled=False),
)

terminal_agent = terminal_only_settings.create_agent()
print(f"Terminal-only agent tools: {[t.name for t in terminal_agent.tools]}")
assert len(terminal_agent.tools) == 1
assert terminal_agent.condenser is None  # 上下文压缩器在这些设置中禁用
print("✓ Different settings produce different agent configuration")
print()

# ── 清理──────────────────────────────────────────────────────────────
os.remove(os.path.join(cwd, "hello_settings.txt"))

# 报告费用
cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
print(f"\nEXAMPLE_COST: {cost}")
