"""通过智能体-服务器 API 客户端定义的工具。

演示客户端定义工具的服务器端路径：智能体在本地 ``openhands.agent_server`` 子进程内运
行，工具规格在其中发送
``POST /api/conversations``，并且 SDK 通过 WebSocket 广播 ``ActionEvent`` ，因此该客
户端进程可以拦截它们——这正
是浏览器前端 (e.g. Agent Canvas）就可以了。

与独立 SDK 示例的差异：
  - 没有本地工具注册：服务器自动调用``ClientTool.from_spec()``并将``Tool(name=...)``
  注入智能体。
  - ``ActionEvent`` 通过 WebSocket 到回调异步到达。
  - ``client_tools=SPECS`` 是 ``Conversation`` 上唯一的新参数。

用途：
    LLM_API_KEY=... uv run examples/02_remote_agent_server/14_client_defined_tools.py
"""

import os
import tempfile

from pydantic import SecretStr
from scripts.utils import ManagedAPIServer

from openhands.sdk import LLM, Conversation, Event, RemoteConversation, get_logger
from openhands.sdk.event.llm_convertible.action import ActionEvent
from openhands.sdk.tool.client_tool import ClientToolSpec
from openhands.tools.preset.default import get_default_agent


logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 1. 通过 JSON 规范定义工具 — 无 Python 执行器，无服务器端代码
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
                    "description": "Route or URL path to navigate to, e.g. '/files'",
                },
            },
            "required": ["route"],
        },
    ),
]

CLIENT_TOOL_NAMES = {spec.name for spec in SPECS}

# ---------------------------------------------------------------------------
# 2. 事件回调：拦截通过 WebSocket 传递的客户端工具调用在真实的浏览器客户端中，这会将调用
# 转发到 UI 层。
# ---------------------------------------------------------------------------

intercepted: list[dict] = []


def on_event(event: Event) -> None:
    if isinstance(event, ActionEvent) and event.tool_name in CLIENT_TOOL_NAMES:
        args = event.action.model_dump() if event.action else {}
        intercepted.append({"tool": event.tool_name, "args": args})
        logger.info("[CLIENT HANDLER] %s(%s)", event.tool_name, args)


# ---------------------------------------------------------------------------
# 3. 构建 LLM — 智能体在服务器上运行，此配置在那里序列化
# ---------------------------------------------------------------------------

api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."

llm = LLM(
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    api_key=SecretStr(api_key),
    base_url=os.getenv("LLM_BASE_URL"),
)

# ---------------------------------------------------------------------------
# 4. 启动本地智能体-服务器，连接并运行对话
# ---------------------------------------------------------------------------

with ManagedAPIServer(port=8004) as server:
    workspace_dir = tempfile.mkdtemp(prefix="client_tools_demo_")

    from openhands.sdk import Workspace

    workspace = Workspace(host=server.base_url, working_dir=workspace_dir)

    # 智能体确实不需要列出客户端工具 - 服务器在处理请求中的 client_tools 字段时自动注入
    # 它们。
    #
    agent = get_default_agent(llm=llm, cli_mode=True)

    conversation = Conversation(
        agent=agent,
        workspace=workspace,
        callbacks=[on_event],
        client_tools=SPECS,  # 发送到 POST /api/conversations 中的服务器
    )
    assert isinstance(conversation, RemoteConversation)

    try:
        logger.info("Conversation ID: %s", conversation.state.id)

        conversation.send_message(
            "Use the terminal to count how many Python files are in the current "
            "directory (use: find . -name '*.py' | wc -l). "
            "Then call show_notification with the count result and level='info', "
            "and call navigate_to with route='/files'."
        )
        conversation.run()

        # -----------------------------------------------------------------------
        # 5. 验证客户端工具实际上是通过 WebSocket 调用的
        # -----------------------------------------------------------------------

        logger.info("\n=== %d client tool call(s) intercepted ===", len(intercepted))
        for call in intercepted:
            logger.info("  %s: %s", call["tool"], call["args"])

        called_names = {c["tool"] for c in intercepted}
        assert "show_notification" in called_names, (
            "Expected show_notification to be called"
        )
        assert "navigate_to" in called_names, "Expected navigate_to to be called"

        cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
        print(f"EXAMPLE_COST: {cost}")

    finally:
        conversation.close()
