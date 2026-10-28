"""选择跨会话持久内存（两层 ``MEMORY.md``）。

对于 ``AgentContext(load_memory=True)``，对话会从 ``~/.openhands/memory/``（用户层）
加载
``MEMORY.md`` 索引，并且
``<workspace>/.openhands/memory/``（项目层）在会话开始时（``<MEMORY_CONTEXT>`` 块）进
入系统提示词，系统提示词指示智能
体在工作时维护这些文件。

此示例在同一工作区上运行两个对话：

1. 会话 1 要求智能体在其持久项目内存中记录项目决策 - 智能体写入
``.openhands/memory/MEMORY.md`` 本身。
2. Session 2 是一场全新的对话：保存的记忆注入到系统中提示词 automatically, so the 智
能体他已经知道决定，无需再被告知。

默认情况下，内存处于选择加入和关闭状态。 该示例仅在临时工作区内写入； ``~``下的用户层
保持不变。
"""

import os
import tempfile
from pathlib import Path

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, AgentContext, Conversation, get_logger
from openhands.sdk.event import SystemPromptEvent
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

tools = [Tool(name=TerminalTool.name), Tool(name=FileEditorTool.name)]

# 选择持久内存。 其他一切都是自动的：对话在会话开始时解析 MEMORY.md 记录，并且系统提示词
# 告诉智能体如何维护它们。
#
agent_context = AgentContext(load_memory=True)

with tempfile.TemporaryDirectory() as workspace:
    memory_index = Path(workspace) / ".openhands" / "memory" / "MEMORY.md"

    print("=" * 100)
    print("Session 1: ask the agent to record a decision in project memory.")
    agent = Agent(llm=llm, tools=tools, agent_context=agent_context)
    conversation = Conversation(agent=agent, workspace=workspace)
    conversation.send_message(
        "We just decided to use `uv` (not pip/poetry) for all Python "
        "dependency management in this project. Record that decision in your "
        "persistent project memory so future sessions know it."
    )
    conversation.run()
    conversation.close()

    print("=" * 100)
    print(f"Project memory after session 1 ({memory_index}):")
    if memory_index.exists():
        print(memory_index.read_text())
    else:
        print("(the agent did not create the memory index)")

    print("=" * 100)
    print("Session 2: a brand-new conversation over the same workspace.")
    agent = Agent(llm=llm, tools=tools, agent_context=agent_context)
    conversation = Conversation(agent=agent, workspace=workspace)
    conversation.send_message(
        "Which tool do we use for Python dependency management in this "
        "project? Answer from what you already know about the project."
    )
    conversation.run()

    # 记录的内存被注入到会话 2 的系统提示词作为 <MEMORY_CONTEXT> 块 - 显示它以使机制可见
    # 。
    #
    system_prompt_event = next(
        event
        for event in conversation.state.events
        if isinstance(event, SystemPromptEvent)
    )
    dynamic_context = system_prompt_event.dynamic_context
    injected = dynamic_context.text if dynamic_context else ""
    print("=" * 100)
    print(
        "<MEMORY_CONTEXT> injected into session 2's system prompt: "
        f"{'<MEMORY_CONTEXT>' in injected}"
    )
    conversation.close()

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
