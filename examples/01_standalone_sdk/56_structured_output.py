"""通过 ``response_schema`` 进行结构化输出。

将 Pydantic 模型附加到 * 任何 * 工具规范，并且智能体在调用该工具时必须填充这些字段。
模式作为工具的 JSON-模式参数发送到 LLM，并在收到时进行验证。

在这里演示了两个工具：
  - ``TerminalTool``（现有的 SDK 工具）- 每个命令都必须带有一个
    ``purpose`` 和 ``expected_outcome``，位于工具自己的 ``command`` 字段的顶部。 不需
    要子类化：模式通过规范合并。
  - ``FinishTool``（内置）——最终答案作为类型对象返回。
"""

import os
from typing import cast

from pydantic import BaseModel, Field

from openhands.sdk import LLM, Agent, Conversation
from openhands.sdk.event import ActionEvent
from openhands.sdk.tool import Tool, register_tool
from openhands.sdk.tool.builtins.finish import FinishTool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool


# --- 结构化输出模式 ------------------------------------------------


class CommandRationale(BaseModel):
    """强制注释模式附加到 TerminalTool。"""

    purpose: str = Field(description="Why this command is being run, in one line.")
    expected_outcome: str = Field(
        description="What the assistant expects to observe from running it."
    )


class ProjectFacts(BaseModel):
    # 注意：``kind``、``security_risk``、``structured_output`` 和 ``summary``
    # 被保留，工具自己的字段名称也是保留的； 在解决时使用加注。
    #
    description: str = Field(description="One-paragraph description of the project.")
    facts: list[str] = Field(description="Three concise, distinct facts.")


# 注册 FinishTool，以便我们可以通过工具规范附加 response_schema。
register_tool("FinishTool", FinishTool)


# --- 智能体设置 -----------------------------------------------------------------------
# -----------


llm = LLM(
    model=os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4-5-20250929"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL", None),
)

agent = Agent(
    llm=llm,
    tools=[
        # 现有工具，增强了强制注释模式：
        Tool(name=TerminalTool.name, params={"response_schema": CommandRationale}),
        Tool(name=FileEditorTool.name),
        Tool(name="FinishTool", params={"response_schema": ProjectFacts}),
    ],
    # 跳过自动注入的默认 FinishTool，因此使用我们的模式绑定的。
    include_default_tools=["ThinkTool"],
)

conversation = Conversation(agent=agent, workspace=os.getcwd())
conversation.send_message(
    "Inspect the repo using terminal commands, then finish with three facts "
    "about the project."
)
conversation.run()


# --- 从具有 response_schema 的任何工具恢复键入的输出 --------------

events = conversation.state.events
terminal_tool = agent.tools_map[TerminalTool.name]
finish_tool = agent.tools_map["finish"]

# 现在每个 TerminalTool 调用都带有我们的注释字段。 遍历所有事件以表明 LLM 在每次调用时都
# 填充了它们。
#
print("\n[Terminal commands with rationale]")

for event in events:
    if (
        isinstance(event, ActionEvent)
        and event.tool_name == TerminalTool.name
        and event.action is not None
    ):
        rationale = cast(CommandRationale, terminal_tool.parse_response(event.action))
        # action.command是工具自己的字段； 基本原理。*来自模式。
        print(f"  $ {getattr(event.action, 'command', '?')}")
        print(f"    purpose:          {rationale.purpose}")
        print(f"    expected_outcome: {rationale.expected_outcome}")

# 以及输入的最终答案：
facts = cast(ProjectFacts | None, finish_tool.parse_last_response(events))
if facts:
    print("\n[Finish]")
    print(f"  description: {facts.description}")
    for fact in facts.facts:
        print(f"  - {fact}")

# 报告费用
cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
print(f"\nEXAMPLE_COST: {cost}")
