"""使用真实的 MCP 服务器测试 MCP utils 功能 - 集成测试。"""

import asyncio
import logging
import socket
import sys
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock, patch

import httpx
import pytest
import uvicorn
from fastmcp import FastMCP
from fastmcp.client.auth import OAuth
from fastmcp.mcp_config import MCPConfig as FastMCPConfig, RemoteMCPServer
from key_value.aio.stores.memory import MemoryStore
from pydantic import SecretStr
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

from openhands.sdk.mcp import create_mcp_tools
from openhands.sdk.mcp.config import (
    MCPApiKeyAuthCredential,
    MCPBasicAuthCredential,
    MCPBearerAuthCredential,
    MCPHeaderAuthCredential,
    MCPNoneAuthCredential,
    MCPOAuthAuthCredential,
    coerce_mcp_config,
    to_fastmcp_mcp_config,
)
from openhands.sdk.mcp.exceptions import MCPError, MCPTimeoutError
from openhands.sdk.mcp.oauth import MCPOAuth
from openhands.sdk.mcp.utils import _prepare_mcp_config


logger = logging.getLogger(__name__)

MCPTransport = Literal["http", "streamable-http", "sse"]


def native_mcp_config(config: dict) -> dict:
    return coerce_mcp_config(config["mcpServers"])


def stdio_fetch_mcp_config() -> dict:
    repo_root = Path(__file__).resolve().parents[3]
    return {
        "mcpServers": {
            "fetch": {
                "command": sys.executable,
                "args": ["-m", "tests.sdk.mcp.stdio_test_server"],
                "cwd": str(repo_root),
            }
        }
    }


@pytest.mark.parametrize(
    ("credential", "expected"),
    [
        (MCPNoneAuthCredential(strategy="none"), {}),
        (
            MCPApiKeyAuthCredential(strategy="api_key", value=SecretStr("token")),
            {"Authorization": "Bearer token"},
        ),
        (
            MCPApiKeyAuthCredential(
                strategy="api_key",
                value=SecretStr("token"),
                header_name="X-API-Key",
            ),
            {"X-API-Key": "token"},
        ),
        (
            MCPBearerAuthCredential(strategy="bearer", value=SecretStr("token")),
            {"Authorization": "Bearer token"},
        ),
        (
            MCPBasicAuthCredential(
                strategy="basic",
                username="user",
                password=SecretStr("pass"),
            ),
            {"Authorization": "Basic dXNlcjpwYXNz"},
        ),
        (
            MCPHeaderAuthCredential(
                strategy="header",
                headers={"X-Token": SecretStr("token")},
            ),
            {"X-Token": "token"},
        ),
        (MCPOAuthAuthCredential(strategy="oauth2"), None),
    ],
)
def test_mcp_auth_credentials_to_http_headers(credential, expected):
    assert credential.to_http_headers() == expected


def _find_free_port() -> int:
    """在本地主机上查找可用端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 5.0, interval: float = 0.1) -> None:
    """通过使用 HTTP 请求进行轮询，等待端口变得可用。"""
    max_attempts = int(timeout / interval)
    for _ in range(max_attempts):
        try:
            # 由于 MCP 服务器使用 HTTP，因此尝试 HTTP 请求
            with httpx.Client(timeout=interval) as client:
                client.get(f"http://127.0.0.1:{port}/")
                return
        except httpx.ConnectError:
            pass
        except (httpx.TimeoutException, httpx.HTTPStatusError):
            # 任何响应（甚至错误）都意味着服务器已启动
            return
        except Exception:
            # 任何其他响应都意味着服务器已启动
            return
        time.sleep(interval)
    raise RuntimeError(f"Server failed to start on port {port} within {timeout}s")


class MCPTestServer:
    """用于管理 MCP 测试服务器进行测试的帮助程序类。"""

    def __init__(self, name: str = "test-server"):
        self.mcp = FastMCP(name)
        self.port: int | None = None
        self._server_thread: threading.Thread | None = None

    def add_tool(self, func):
        """向服务器添加一个工具。"""
        return self.mcp.tool()(func)

    def start(self, transport: MCPTransport = "http") -> int:
        """启动服务器并返回端口。"""
        self.port = _find_free_port()
        path = "/sse" if transport == "sse" else "/mcp"
        startup_error: list[Exception] = []

        async def run_server():
            assert self.port is not None
            await self.mcp.run_http_async(
                host="127.0.0.1",
                port=self.port,
                transport=transport,
                show_banner=False,
                path=path,
            )

        def server_thread_target():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_server())
            except Exception as e:
                logger.error(f"MCP test server failed: {e}")
                startup_error.append(e)
            finally:
                loop.close()

        self._server_thread = threading.Thread(target=server_thread_target, daemon=True)
        self._server_thread.start()

        # 通过轮询端口等待服务器准备就绪
        _wait_for_port(self.port)

        # 检查服务器线程在启动过程中是否失败
        if startup_error:
            raise startup_error[0]

        return self.port

    def stop(self):
        """停止服务器并清理资源。"""
        if self._server_thread is not None:
            # 进程退出时守护进程线程将自动清理
            self._server_thread = None
        self.port = None


@pytest.fixture
def http_mcp_server() -> Generator[MCPTestServer]:
    """测试夹具提供正在运行的 HTTP MCP 服务器以及测试工具。"""
    server = MCPTestServer("http-test-server")

    @server.add_tool
    def greet(name: str) -> str:
        """称呼某人的名字来打招呼。"""
        return f"Hello, {name}!"

    @server.add_tool
    def add_numbers(a: int, b: int) -> int:
        """将两个数字相加。"""
        return a + b

    server.start(transport="http")
    yield server
    server.stop()


@pytest.fixture
def sse_mcp_server() -> Generator[MCPTestServer]:
    """测试夹具提供正在运行的 SSE MCP 服务器以及测试工具。"""
    server = MCPTestServer("sse-test-server")

    @server.add_tool
    def echo(message: str) -> str:
        """回显一条消息。"""
        return message

    @server.add_tool
    def multiply(x: int, y: int) -> int:
        """两个数字相乘。"""
        return x * y

    server.start(transport="sse")
    yield server
    server.stop()


def test_create_mcp_tools_empty_config():
    """测试使用空配置创建 MCP 工具会引发错误。"""
    config = {}
    with pytest.raises(ValueError, match="No MCP servers defined"):
        create_mcp_tools(config)


def test_create_mcp_tools_rejects_external_config_shapes():
    """运行时工具仅接受MCPServer的原生地图。"""
    config = {
        "mcpServers": {
            "remote": {
                "url": "https://mcp.example.com/mcp",
            }
        }
    }
    with pytest.raises(TypeError, match="dict\\[str, MCPServer\\]"):
        create_mcp_tools(config)  # type: ignore[arg-type]

    fastmcp_config = FastMCPConfig.model_validate(config)
    with pytest.raises(TypeError, match="dict\\[str, MCPServer\\]"):
        create_mcp_tools(fastmcp_config)  # type: ignore[arg-type]


def test_create_mcp_tools_skips_disabled_servers():
    """用户关闭的服务器永远不会连接到。"""
    config = {
        "mcpServers": {
            "kept": {"url": "https://kept.example.com/mcp"},
            "switched_off": {
                "url": "https://switched-off.example.com/mcp",
                "enabled": False,
            },
        }
    }

    with patch("openhands.sdk.mcp.utils.MCPClient") as mock_client_class:
        create_mcp_tools(native_mcp_config(config))

    prepared = mock_client_class.call_args.args[0]
    assert list(prepared.mcpServers) == ["kept"]


def test_create_mcp_tools_all_servers_disabled():
    """禁用每个服务器是按名称报告的，而不是“未定义服务器”。"""
    config = {
        "mcpServers": {
            "switched_off": {
                "url": "https://switched-off.example.com/mcp",
                "enabled": False,
            }
        }
    }

    with pytest.raises(ValueError, match="switched_off"):
        create_mcp_tools(native_mcp_config(config))


def test_to_fastmcp_mcp_config_strips_enabled():
    """``enabled``只是OpenHands一方，FastMCP会默默地吸收它。"""
    config = native_mcp_config(
        {
            "mcpServers": {
                "switched_off": {
                    "url": "https://switched-off.example.com/mcp",
                    "enabled": False,
                }
            }
        }
    )

    prepared = to_fastmcp_mcp_config(config)

    assert "enabled" not in prepared["mcpServers"]["switched_off"]


def test_prepare_mcp_config_converts_bare_oauth_credential():
    config = {
        "mcpServers": {
            "remote": {
                "url": "https://mcp.example.com/mcp",
                "auth": {"strategy": "oauth2"},
            }
        }
    }

    prepared = _prepare_mcp_config(native_mcp_config(config))

    server = prepared.mcpServers["remote"]
    assert isinstance(server, RemoteMCPServer)
    assert server.auth == "oauth"


def test_prepare_mcp_config_applies_explicit_oauth_authentication():
    config = {
        "mcpServers": {
            "remote": {
                "url": "https://mcp.example.com/mcp",
                "auth": {
                    "strategy": "oauth2",
                    "authentication": {
                        "type": "oauth",
                        "client_auth_method": "private_key_jwt",
                        "additional_client_metadata": {
                            "application_type": "native",
                        },
                        "scopes": ["email", "offline_access"],
                        "client_name": "OpenHands",
                        "client_id": "openhands-client",
                        "client_secret": "openhands-secret",
                    },
                },
            }
        }
    }

    prepared = _prepare_mcp_config(native_mcp_config(config))
    server = prepared.mcpServers["remote"]
    assert isinstance(server, RemoteMCPServer)
    auth = server.auth

    assert isinstance(auth, OAuth)
    assert auth._additional_client_metadata == {
        "application_type": "native",
        "token_endpoint_auth_method": "private_key_jwt",
    }
    assert auth._scopes == ["email", "offline_access"]
    assert auth._client_name == "OpenHands"
    assert auth._client_id == "openhands-client"
    assert auth._client_secret == "openhands-secret"


def test_prepare_mcp_config_applies_oauth_token_storage_to_explicit_auth():
    token_storage = MemoryStore()
    config = {
        "mcpServers": {
            "remote": {
                "url": "https://mcp.example.com/mcp",
                "auth": {
                    "strategy": "oauth2",
                    "authentication": {
                        "type": "oauth",
                        "client_auth_method": "none",
                    },
                },
            }
        }
    }

    prepared = _prepare_mcp_config(
        native_mcp_config(config),
        mcp_oauth_token_storage=token_storage,
    )

    server = prepared.mcpServers["remote"]
    assert isinstance(server, RemoteMCPServer)
    auth = server.auth
    assert isinstance(auth, OAuth)
    assert auth._token_storage is token_storage


def test_prepare_mcp_config_uses_custom_oauth_factory():
    token_storage = MemoryStore()
    calls = []
    config = {
        "mcpServers": {
            "remote": {
                "url": "https://mcp.example.com/mcp",
                "auth": {
                    "strategy": "oauth2",
                    "authentication": {
                        "type": "oauth",
                        "client_auth_method": "none",
                    },
                },
            }
        }
    }

    def factory(server_name, server, auth, storage):
        calls.append((server_name, server, auth, storage))
        return OAuth(client_name="Factory OAuth")

    prepared = _prepare_mcp_config(
        native_mcp_config(config),
        mcp_oauth_token_storage=token_storage,
        mcp_oauth_factory=factory,
    )

    server = prepared.mcpServers["remote"]
    assert isinstance(server, RemoteMCPServer)
    auth = server.auth
    assert isinstance(auth, OAuth)
    assert auth._client_name == "Factory OAuth"
    assert len(calls) == 1
    assert calls[0][0] == "remote"
    assert calls[0][3] is token_storage


def test_prepare_mcp_config_applies_oauth_token_storage_to_bare_oauth_credential():
    token_storage = MemoryStore()
    config = {
        "mcpServers": {
            "remote": {
                "url": "https://mcp.example.com/mcp",
                "auth": {"strategy": "oauth2"},
            }
        }
    }

    prepared = _prepare_mcp_config(
        native_mcp_config(config),
        mcp_oauth_token_storage=token_storage,
    )

    server = prepared.mcpServers["remote"]
    assert isinstance(server, RemoteMCPServer)
    auth = server.auth
    assert isinstance(auth, OAuth)
    assert auth._token_storage is token_storage


def test_prepare_mcp_config_builds_endpoint_discovering_oauth_clients():
    # 安排：一台服务器带有显式身份验证，一台服务器裸露凭据。
    config = {
        "mcpServers": {
            "explicit": {
                "url": "https://mcp.example.com/mcp",
                "auth": {
                    "strategy": "oauth2",
                    "authentication": {"type": "oauth", "client_auth_method": "none"},
                },
            },
            "bare": {
                "url": "https://mcp.example.org/mcp",
                "auth": {"strategy": "oauth2"},
            },
        }
    }

    # 法案
    prepared = _prepare_mcp_config(
        native_mcp_config(config), mcp_oauth_token_storage=MemoryStore()
    )

    # 断言：两者均针对发现的 token 端点进行刷新。
    for name in ("explicit", "bare"):
        server = prepared.mcpServers[name]
        assert isinstance(server, RemoteMCPServer)
        assert isinstance(server.auth, MCPOAuth)


def test_create_mcp_tools_http_server(http_mcp_server: MCPTestServer):
    """使用真实的 HTTP 服务器测试创建 MCP 工具。"""
    config = {
        "mcpServers": {
            "http_server": {
                "transport": "http",
                "url": f"http://127.0.0.1:{http_mcp_server.port}/mcp",
            }
        }
    }

    tools = create_mcp_tools(native_mcp_config(config), timeout=10.0)

    assert len(tools) == 2
    tool_names = {t.name for t in tools}
    assert "greet" in tool_names
    assert "add_numbers" in tool_names

    # 验证工具模式已正确加载
    greet_tool = next(t for t in tools if t.name == "greet")
    openai_schema = greet_tool.to_openai_tool()
    assert openai_schema["type"] == "function"
    assert "parameters" in openai_schema["function"]
    assert "name" in openai_schema["function"]["parameters"]["properties"]


def test_create_mcp_tools_sse_server(sse_mcp_server: MCPTestServer):
    """使用真实的 SSE 服务器测试创建 MCP 工具。"""
    config = {
        "mcpServers": {
            "sse_server": {
                "transport": "sse",
                "url": f"http://127.0.0.1:{sse_mcp_server.port}/sse",
            }
        }
    }

    tools = create_mcp_tools(native_mcp_config(config), timeout=10.0)

    assert len(tools) == 2
    tool_names = {t.name for t in tools}
    assert "echo" in tool_names
    assert "multiply" in tool_names


def test_create_mcp_tools_mixed_servers(
    http_mcp_server: MCPTestServer, sse_mcp_server: MCPTestServer
):
    """测试使用 HTTP 和 SSE 服务器创建 MCP 工具。"""
    config = {
        "mcpServers": {
            "http_server": {
                "transport": "http",
                "url": f"http://127.0.0.1:{http_mcp_server.port}/mcp",
            },
            "sse_server": {
                "transport": "sse",
                "url": f"http://127.0.0.1:{sse_mcp_server.port}/sse",
            },
        }
    }

    tools = create_mcp_tools(native_mcp_config(config), timeout=10.0)

    # 应该有来自两个服务器的工具（以服务器名称为前缀）
    assert len(tools) == 4
    tool_names = {t.name for t in tools}
    assert "http_server_greet" in tool_names
    assert "http_server_add_numbers" in tool_names
    assert "sse_server_echo" in tool_names
    assert "sse_server_multiply" in tool_names


def test_create_mcp_tools_http_schema_validation(http_mcp_server: MCPTestServer):
    """测试工具模式是否已从 HTTP 服务器正确加载。"""
    config = {
        "mcpServers": {
            "http_server": {
                "transport": "http",
                "url": f"http://127.0.0.1:{http_mcp_server.port}/mcp",
            }
        }
    }

    tools = create_mcp_tools(native_mcp_config(config), timeout=10.0)
    add_tool = next(t for t in tools if t.name == "add_numbers")

    openai_schema = add_tool.to_openai_tool()
    params = openai_schema["function"].get("parameters", {})
    assert params["properties"]["a"]["type"] == "integer"
    assert params["properties"]["b"]["type"] == "integer"
    assert "a" in params["required"]
    assert "b" in params["required"]

    responses_schema = add_tool.to_responses_tool()
    responses_params = responses_schema["parameters"]
    assert isinstance(responses_params, dict)
    responses_properties = responses_params["properties"]
    assert isinstance(responses_properties, dict)
    responses_required = responses_params["required"]
    assert isinstance(responses_required, list)
    assert responses_properties["a"]["type"] == "integer"
    assert responses_properties["b"]["type"] == "integer"
    assert "a" in responses_required
    assert "b" in responses_required
    assert "data" not in responses_properties


def test_create_mcp_tools_transport_inferred_from_url(http_mcp_server: MCPTestServer):
    """测试在未明确指定时是否推断出传输层类型。"""
    config = {
        "mcpServers": {
            "auto_http": {
                # 没有明确的传输层 - 应该从 URL 推断
                "url": f"http://127.0.0.1:{http_mcp_server.port}/mcp",
            }
        }
    }

    tools = create_mcp_tools(native_mcp_config(config), timeout=10.0)
    assert len(tools) == 2


def test_create_mcp_tools_sse_inferred_from_url(sse_mcp_server: MCPTestServer):
    """测试 SSE 传输层是从包含 /sse. 的 URL 推断出来的"""
    config = {
        "mcpServers": {
            "auto_sse": {
                # 没有明确的传输层 - 应该从 URL 中的 /sse 推断出 SSE
                "url": f"http://127.0.0.1:{sse_mcp_server.port}/sse",
            }
        }
    }

    tools = create_mcp_tools(native_mcp_config(config), timeout=10.0)
    assert len(tools) == 2


def test_execute_http_tool(http_mcp_server: MCPTestServer):
    """测试在 HTTP MCP 服务器上执行工具。"""
    config = {
        "mcpServers": {
            "http_server": {
                "transport": "http",
                "url": f"http://127.0.0.1:{http_mcp_server.port}/mcp",
            }
        }
    }

    tools = create_mcp_tools(native_mcp_config(config), timeout=10.0)
    greet_tool = next(t for t in tools if t.name == "greet")

    action = greet_tool.action_from_arguments({"name": "World"})
    assert greet_tool.executor is not None
    observation = greet_tool.executor(action)

    assert observation is not None
    assert "Hello, World!" in observation.text


def test_execute_sse_tool(sse_mcp_server: MCPTestServer):
    """测试在 SSE MCP 服务器上执行工具。"""
    config = {
        "mcpServers": {
            "sse_server": {
                "transport": "sse",
                "url": f"http://127.0.0.1:{sse_mcp_server.port}/sse",
            }
        }
    }

    tools = create_mcp_tools(native_mcp_config(config), timeout=10.0)
    multiply_tool = next(t for t in tools if t.name == "multiply")

    action = multiply_tool.action_from_arguments({"x": 6, "y": 7})
    assert multiply_tool.executor is not None
    observation = multiply_tool.executor(action)

    assert observation is not None
    assert "42" in observation.text


def test_create_mcp_tools_connection_to_nonexistent_server():
    """测试与不存在的服务器的连接是否正常失败。"""
    config = {
        "mcpServers": {
            "nonexistent": {
                "transport": "http",
                "url": "http://127.0.0.1:59999/mcp",
            }
        }
    }

    # 应该返回空工具或引发与连接相关的错误关键是它不应该挂起
    #
    try:
        tools = create_mcp_tools(native_mcp_config(config), timeout=5.0)
        assert len(tools) == 0  # 连接失败没有工具
    except (ConnectionError, TimeoutError, MCPTimeoutError, OSError, MCPError):
        pass  # 预期的连接错误是可以接受的


def test_create_mcp_tools_stdio_server():
    """测试从本机服务器映射创建 MCP 工具。"""
    mcp_config = stdio_fetch_mcp_config()

    tools = create_mcp_tools(native_mcp_config(mcp_config), timeout=10.0)
    assert len(tools) == 1
    assert tools[0].name == "fetch"

    # 从OpenAI工具中获取模式，因为MCPToolAction现在使用动态模式
    #
    openai_tool = tools[0].to_openai_tool()
    assert openai_tool["type"] == "function"
    assert "parameters" in openai_tool["function"]
    input_schema = openai_tool["function"]["parameters"]

    assert "type" in input_schema
    assert input_schema["type"] == "object"
    assert "properties" in input_schema
    assert "url" in input_schema["properties"]
    assert input_schema["properties"]["url"]["type"] == "string"
    assert "required" in input_schema
    assert "url" in input_schema["required"]

    # security_risk 应该不在… 模式当没有启用安全分析器时
    assert "security_risk" not in input_schema["required"]
    assert "security_risk" not in input_schema["properties"]

    mcp_tool = tools[0].to_mcp_tool()
    mcp_schema = mcp_tool["inputSchema"]

    # 检查两个模式是否具有相同的基本结构
    assert mcp_schema["type"] == input_schema["type"]
    assert set(mcp_schema["required"]) == set(input_schema["required"])

    # 检查 input_schema 中的所有属性是否存在于 mcp_schema 中（不包括用于 LLM 的“摘要”等
    # 元字段，而不是工具接口）
    #
    for prop_name, prop_def in input_schema["properties"].items():
        if prop_name == "summary":
            continue  # 摘要是 LLM 的元字段，不是工具界面的一部分
        assert prop_name in mcp_schema["properties"]
        assert mcp_schema["properties"][prop_name]["type"] == prop_def["type"]
        assert (
            mcp_schema["properties"][prop_name]["description"]
            == prop_def["description"]
        )

    assert openai_tool["function"]["name"] == "fetch"

    # 未启用安全分析器时，OpenAI 工具模式中不应包含 security_risk  # noqa: E501
    assert "security_risk" not in input_schema["required"]
    assert "security_risk" not in input_schema["properties"]

    assert tools[0].executor is not None


def test_create_mcp_tools_timeout_error_message():
    """测试超时错误是否包含有信息性错误消息。

    Note: 此测试使用模拟来模拟超时，因为等待真实的
    超时会很慢而且不稳定。
    """
    config = {
        "mcpServers": {
            "slow_server": {
                "transport": "stdio",
                "command": "python",
                "args": ["./slow_server.py"],
            },
            "another_server": {
                "transport": "http",
                "url": "https://api.example.com/mcp",
            },
        }
    }

    with patch("openhands.sdk.mcp.utils.MCPClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.call_async_from_sync.side_effect = TimeoutError()

        with pytest.raises(MCPTimeoutError) as exc_info:
            create_mcp_tools(native_mcp_config(config), timeout=30.0)

        error_message = str(exc_info.value)
        assert "30" in error_message
        assert "seconds" in error_message
        assert "slow_server" in error_message
        assert "another_server" in error_message
        assert "Possible solutions" in error_message
        assert "timeout" in error_message.lower()

        assert exc_info.value.timeout == 30.0
        assert exc_info.value.config is not None


def test_mcp_tool_reconnects_after_http_error():
    mcp = FastMCP("http-error-test-server")

    @mcp.tool()
    def ping() -> str:
        return "pong"

    class FailFirstToolCall(BaseHTTPMiddleware):
        failed = False

        async def dispatch(self, request, call_next):
            body = (await request.body()).replace(b" ", b"")
            if not self.failed and b'"method":"tools/call"' in body:
                self.failed = True
                return PlainTextResponse("gateway timeout", status_code=504)
            return await call_next(request)

    port = _find_free_port()
    app = mcp.http_app(path="/mcp")
    app.add_middleware(FailFirstToolCall)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_port(port)

    try:
        config = {
            "server": {"transport": "http", "url": f"http://127.0.0.1:{port}/mcp"}
        }
        with create_mcp_tools(coerce_mcp_config(config), timeout=5) as client:
            tool = next(tool for tool in client if tool.name == "ping")
            assert tool.executor is not None
            action = tool.action_from_arguments({})

            first = tool.executor(action)
            second = tool.executor(action)

            assert first.is_error
            assert "504 Gateway Timeout" in first.text
            assert not second.is_error
            assert "pong" in second.text
    finally:
        server.should_exit = True
        thread.join(timeout=5)
