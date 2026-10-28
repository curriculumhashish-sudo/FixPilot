"""跨工具调用测试 MCP 会话持久化。

验证 MCP 连接是否在多个工具调用之间重用，避免了每次调用重新连接的开销。

相关问题： https://github.com/OpenHands/software-agent-sdk/issues/1739
"""

import asyncio
import socket
import threading
import time

import pytest
from fastmcp import FastMCP

from openhands.sdk.mcp import create_mcp_tools
from openhands.sdk.mcp.config import coerce_mcp_config
from openhands.sdk.mcp.tool import MCPToolExecutor


def _find_free_port() -> int:
    """找到可用的端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server():
    """测试夹具提供带有 echo/add 工具的实时 MCP 测试服务器。"""
    mcp = FastMCP("session-test-server")

    @mcp.tool()
    def echo(message: str) -> str:
        """回显一条消息。"""
        return f"Echo: {message}"

    @mcp.tool()
    def add_numbers(a: int, b: int) -> str:
        """添加两个数字。"""
        return str(a + b)

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
    yield port


class TestSessionPersistence:
    """测试验证会话/连接持久化。"""

    def test_connection_reused_across_tool_calls(self, live_server: int):
        """测试多个工具调用重用同一连接。"""
        config = {
            "mcpServers": {
                "test": {
                    "transport": "http",
                    "url": f"http://127.0.0.1:{live_server}/mcp",
                }
            }
        }

        with create_mcp_tools(
            coerce_mcp_config(config["mcpServers"]), timeout=10.0
        ) as client:
            assert len(client) == 2

            echo_tool = next(t for t in client if t.name == "echo")
            add_tool = next(t for t in client if t.name == "add_numbers")

            # 验证他们共享同一个客户端
            echo_executor = echo_tool.executor
            add_executor = add_tool.executor
            assert isinstance(echo_executor, MCPToolExecutor)
            assert isinstance(add_executor, MCPToolExecutor)
            assert echo_executor.client is add_executor.client

            # 拨打多个电话 - 均应使用同一连接
            for i in range(3):
                action = echo_tool.action_from_arguments({"message": f"test_{i}"})
                result = echo_executor(action)
                assert f"test_{i}" in result.text

            # 调用不同的工具 - 相同的连接
            action = add_tool.action_from_arguments({"a": 5, "b": 3})
            result = add_executor(action)
            assert "8" in result.text

    def test_close_releases_connection(self, live_server: int):
        """测试 close() 是否正确释放连接。"""
        config = {
            "mcpServers": {
                "test": {
                    "transport": "http",
                    "url": f"http://127.0.0.1:{live_server}/mcp",
                }
            }
        }

        with create_mcp_tools(
            coerce_mcp_config(config["mcpServers"]), timeout=10.0
        ) as client:
            tool = next(t for t in client if t.name == "echo")
            executor = tool.executor
            assert isinstance(executor, MCPToolExecutor)

            # 拨打电话
            action = tool.action_from_arguments({"message": "test"})
            result = executor(action)
            assert "test" in result.text
