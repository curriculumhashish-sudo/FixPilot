"""证明有状态 MCP 服务器可与会话持久化配合使用的测试。

此测试创建一个状态为 PER-SESSION 的 MCP 服务器（由会话 ID 键入）。 它验证了：
1. SDK 保持在多个工具调用中的会话
2. 身份验证通过一个工具进行的设置可用于其他工具
3. 会话状态在调用之间丢失不

这直接解决了用户报告的问题，即由于每个工具调用创建了一个新会话，基于会话的身份验证被
破坏。

关键见解：使用 OLD 代码，每个 `async with client:` 都会在退出时断开连接，并在下一次进
入时重新连接，每次都会创建一个 NEW 会话。 对于 FIX
，我们调用 `__aenter__` 一次并保持连接打开。

Related: https://github.com/OpenHands/software-agent-sdk/issues/1739
"""

import asyncio
import socket
import threading
import time

import pytest
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_context

from openhands.sdk.mcp import create_mcp_tools
from openhands.sdk.mcp.config import coerce_mcp_config
from openhands.sdk.mcp.tool import MCPToolExecutor


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def stateful_server():
    """测试夹具提供每个会话有状态的 MCP 测试服务器。"""
    mcp = FastMCP("session-stateful-test-server")
    sessions: dict[str, dict] = {}

    @mcp.tool()
    def set_auth_token(token: str) -> str:
        """为此会话设置身份验证 token。"""
        ctx = get_context()
        session_id = ctx.session_id if ctx else "unknown"
        if session_id not in sessions:
            sessions[session_id] = {}
        sessions[session_id]["token"] = token
        return f"Session {session_id[:8]}: Auth token set to {token}"

    @mcp.tool()
    def get_auth_token() -> str:
        """获取当前的身份验证令牌（证明会话持久化）。"""
        ctx = get_context()
        session_id = ctx.session_id if ctx else "unknown"
        token = sessions.get(session_id, {}).get("token")
        if token is None:
            return (
                f"Session {session_id[:8]}: ERROR - "
                "No auth token! Session state was lost!"
            )
        return f"Session {session_id[:8]}: Current auth token is {token}"

    @mcp.tool()
    def increment_counter() -> str:
        """增加每个会话计数器。"""
        ctx = get_context()
        session_id = ctx.session_id if ctx else "unknown"
        if session_id not in sessions:
            sessions[session_id] = {"counter": 0}
        if "counter" not in sessions[session_id]:
            sessions[session_id]["counter"] = 0
        sessions[session_id]["counter"] += 1
        counter = sessions[session_id]["counter"]
        return f"Session {session_id[:8]}: Counter is now {counter}"

    @mcp.tool()
    def get_counter() -> str:
        """获取此会话的当前计数器值。"""
        ctx = get_context()
        session_id = ctx.session_id if ctx else "unknown"
        counter = sessions.get(session_id, {}).get("counter", 0)
        return f"Session {session_id[:8]}: Counter value is {counter}"

    port = _find_free_port()

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            mcp.run_http_async(
                host="127.0.0.1",
                port=port,
                transport="http",
                show_banner=False,
                path="/mcp",
            )
        )

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    time.sleep(0.5)
    yield sessions, port


class TestStatefulMCPSessionPersistence:
    """测试证明基于会话的 MCP 服务器正常工作。

    这些测试使用跟踪状态 PER SESSION ID 的服务器。 如果 SDK 为每个工具调用创建一个新
    会话，则状态将丢失。 该修复使会话保持打开状态，从而保留调用之
    间的状态。
    """

    def test_counter_persists_across_calls(self, stateful_server):
        """测试每个会话计数器是否在多个工具调用中持续存在。

        这是 CORE 测试 - 如果会话被重置，计数器将在调用之间重置为 0，因为每个新会话没
        有状态。
        """
        sessions, port = stateful_server
        sessions.clear()

        config = {
            "mcpServers": {
                "stateful": {
                    "transport": "http",
                    "url": f"http://127.0.0.1:{port}/mcp",
                }
            }
        }

        with create_mcp_tools(
            coerce_mcp_config(config["mcpServers"]), timeout=10.0
        ) as client:
            increment_tool = next(t for t in client if t.name == "increment_counter")
            get_tool = next(t for t in client if t.name == "get_counter")

            executor = increment_tool.executor
            assert isinstance(executor, MCPToolExecutor)

            # 增加 3 倍 - 全部应该使用 SAME 会话
            for i in range(3):
                action = increment_tool.action_from_arguments({})
                result = executor(action)
                assert f"Counter is now {i + 1}" in result.text

            # 验证计数器为 3（未因新会话而重置）
            get_executor = get_tool.executor
            assert isinstance(get_executor, MCPToolExecutor)
            action = get_tool.action_from_arguments({})
            result = get_executor(action)
            assert "Counter value is 3" in result.text

    def test_auth_token_persists_across_tools(self, stateful_server):
        """测试一次调用中设置的身份验证在后续调用中是否可用。

        这模拟了用户的确切用例：通过 set_token 设置 token，然后在后续操作中使用它。
        使用旧代码，每个工具调用创建一个新会话，丢失身份验证令牌。
        """
        sessions, port = stateful_server
        sessions.clear()

        config = {
            "mcpServers": {
                "stateful": {
                    "transport": "http",
                    "url": f"http://127.0.0.1:{port}/mcp",
                }
            }
        }

        with create_mcp_tools(
            coerce_mcp_config(config["mcpServers"]), timeout=10.0
        ) as client:
            set_auth_tool = next(t for t in client if t.name == "set_auth_token")
            get_auth_tool = next(t for t in client if t.name == "get_auth_token")

            set_executor = set_auth_tool.executor
            get_executor = get_auth_tool.executor
            assert isinstance(set_executor, MCPToolExecutor)
            assert isinstance(get_executor, MCPToolExecutor)

            # 设置身份验证令牌
            action = set_auth_tool.action_from_arguments({"token": "secret-123"})
            result = set_executor(action)
            assert "Auth token set to secret-123" in result.text

            # 验证身份验证令牌持续存在 WITH OLD CODE：这将失败并显示“ERROR - 否身份验证
            # 令牌！” WITH FIX：使用相同的会话，保留token
            #
            action = get_auth_tool.action_from_arguments({})
            result = get_executor(action)

            # THE KEY ASSERTION: token 必须仍然存在
            assert "secret-123" in result.text
            assert "ERROR" not in result.text  # 无会话重置错误

    def test_multiple_operations_same_session(self, stateful_server):
        """测试真实的工作流程：进行身份验证，然后执行多个操作。"""
        sessions, port = stateful_server
        sessions.clear()

        config = {
            "mcpServers": {
                "stateful": {
                    "transport": "http",
                    "url": f"http://127.0.0.1:{port}/mcp",
                }
            }
        }

        with create_mcp_tools(
            coerce_mcp_config(config["mcpServers"]), timeout=10.0
        ) as client:
            # 获取所有工具
            set_auth = next(t for t in client if t.name == "set_auth_token")
            get_auth = next(t for t in client if t.name == "get_auth_token")
            increment = next(t for t in client if t.name == "increment_counter")
            get_counter = next(t for t in client if t.name == "get_counter")

            # 验证执行者是否存在
            assert set_auth.executor is not None
            assert get_auth.executor is not None
            assert increment.executor is not None
            assert get_counter.executor is not None

            # 模拟真实的工作流程：
            # 1. 认证
            action = set_auth.action_from_arguments({"token": "my-api-key"})
            result = set_auth.executor(action)
            assert "my-api-key" in result.text

            # 2. 做一些操作（所有操作都应该使用同一个会话）
            for _ in range(5):
                action = increment.action_from_arguments({})
                increment.executor(action)

            # 3. 验证同一会话中的所有内容仍然有效
            action = get_counter.action_from_arguments({})
            result = get_counter.executor(action)
            assert "Counter value is 5" in result.text

            action = get_auth.action_from_arguments({})
            result = get_auth.executor(action)
            assert "my-api-key" in result.text  # 授权还在！
            assert "ERROR" not in result.text
