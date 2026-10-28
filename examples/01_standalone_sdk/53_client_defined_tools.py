"""演示客户端定义的工具 - 通过 JSON 规范注册并由外部客户端执行的工具 (e.g. 浏览器前端
），而不是 SDK 本身。

这种模式允许前端应用程序注册“UI 操作”工具，而无需服务器端的任何 Python 代码。 当智能
体调用这样的工具时，SDK立即返回确认观测结果，并且事件回调（或WebSo
cket客户端）可以处理实际执行。

用途：
    LLM_API_KEY=... uv run python examples/01_standalone_sdk/53_client_defined_tools.py
"""

import os

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, Conversation, Event, Tool
from openhands.sdk.event.llm_convertible.action import ActionEvent
from openhands.sdk.tool import ClientToolSpec
from openhands.tools.terminal import TerminalTool


# ---------------------------------------------------------------------------
# 1. 通过 JSON 规范定义工具 — 不需要 Python 执行器
# ---------------------------------------------------------------------------

SPECS = [
    ClientToolSpec(
        name="show_notification",
        description=(
            "Display a notification banner in the UI. "
            "Use this to surface important status updates to the user."
        ),
        parameters={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Text to display in the notification",
                },
                "level": {
                    "type": "string",
                    "enum": ["info", "warning", "error"],
                    "description": "Severity level of the notification",
                },
            },
            "required": ["message", "level"],
        },
    ),
    ClientToolSpec(
        name="navigate_to",
        description=(
            "Navigate the UI to a specific page or route. "
            "Use this to direct the user to a relevant section."
        ),
        parameters={
            "type": "object",
            "properties": {
                "route": {
                    "type": "string",
                    "description": "Route or URL path to navigate to, e.g. '/settings'",
                },
            },
            "required": ["route"],
        },
    ),
]

CLIENT_TOOL_NAMES: set[str] = {spec.name for spec in SPECS}

# ---------------------------------------------------------------------------
# 2. 通过事件回调捕获客户端工具调用在实际应用程序中，此回调会通过 WebSocket 将调用转发到
# 前端； 这里我们只是对通话进行录音以供核实。
# ---------------------------------------------------------------------------

intercepted: list[dict] = []


def on_event(event: Event) -> None:
    if isinstance(event, ActionEvent) and event.tool_name in CLIENT_TOOL_NAMES:
        args = event.action.model_dump() if event.action else {}
        intercepted.append({"tool": event.tool_name, "args": args})
        print(f"[CLIENT HANDLER] {event.tool_name}({args})")


# ---------------------------------------------------------------------------
# 3. 使用标准工具构建智能体，然后将客户端工具直接传递给 Conversation。 SDK 注册它们并将
# 它们注入智能体 — 无需手动 register_tool / Tool(name=...) 接线。
# ---------------------------------------------------------------------------

api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."

llm = LLM(
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    api_key=SecretStr(api_key),
    base_url=os.getenv("LLM_BASE_URL"),
)

agent = Agent(
    llm=llm,
    tools=[Tool(name=TerminalTool.name)],
)

conversation = Conversation(
    agent=agent,
    workspace=os.getcwd(),
    callbacks=[on_event],
    client_tools=SPECS,
)

conversation.send_message(
    "Use the terminal to count how many Python files are in the current directory "
    "(use: find . -name '*.py' | wc -l). "
    "Then call show_notification with the count result and level='info', "
    "and call navigate_to with route='/files'."
)
conversation.run()

# ---------------------------------------------------------------------------
# 4. 验证客户端工具是否确实被调用
# ---------------------------------------------------------------------------

print(f"\n=== {len(intercepted)} client tool call(s) intercepted ===")
for call in intercepted:
    print(f"  {call['tool']}: {call['args']}")

called_names = {c["tool"] for c in intercepted}
assert "show_notification" in called_names, "Expected show_notification to be called"
assert "navigate_to" in called_names, "Expected navigate_to to be called"

print(f"EXAMPLE_COST: {llm.metrics.accumulated_cost}")
