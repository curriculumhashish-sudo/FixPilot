"""测试 mcp_router.py 端点。"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config
from openhands.agent_server.mcp_router import (
    _OAUTH_PROBE_JOB_TTL_SECONDS,
    MCPTestFailure,
    MCPTestRequest,
    MCPTestSuccess,
    _BrowserCoordinatedOAuth,
    _MCPOAuthProbeJob,
    _oauth_probe_jobs,
    _oauth_probe_jobs_lock,
    _register_oauth_job,
)
from openhands.agent_server.persistence import reset_stores
from openhands.sdk.mcp.config import MCPServer, to_fastmcp_mcp_config

# 重用真实 FastMCP- 基于的测试服务器辅助工具 SDK tests 启动一个真实的过程子进程  MCP 在
# 服务器内部的单元测试不可靠的 CI images (depends on npx, network, etc.), but an in-
# process FastMCP  HTTP 服务器是完全可移植的，并且执行了与 connect/list-tools 代码路径相
# 同的代码端点依赖于。
#
from tests.sdk.mcp.test_create_mcp_tool import (  # noqa: E402
    MCPTestServer,
    _find_free_port,
)


@pytest.fixture
def client() -> Generator[TestClient]:
    reset_stores()
    config = Config(session_api_keys=[])  # 禁用身份验证。
    with TestClient(create_app(config), raise_server_exceptions=False) as test_client:
        yield test_client
    reset_stores()


@pytest.fixture
def http_mcp_server():
    server = MCPTestServer("test-mcp-router")

    @server.add_tool
    def echo(message: str) -> str:
        """回显一条消息。"""
        return message

    @server.add_tool
    def add(a: int, b: int) -> int:
        """将两个整数相加。"""
        return a + b

    server.start(transport="http")
    yield server
    server.stop()


@pytest.fixture
def slack_like_mcp_server():
    """服务器模仿 Slack MCP 服务器的错误报告。

    上游 API 失败以普通文本内容 (``{"ok": false, "error": ...}``) 呈现，没有 MCP
    ``isError`` 标志，这正是工具/
    只列出的探针 False 正确的行为
    for invalid credentials.
    """
    server = MCPTestServer("slack-like")

    @server.add_tool
    def slack_list_channels(limit: int = 100) -> str:
        """以纯内容形式返回 Slack 风格的身份验证失败载荷。"""
        return json.dumps({"ok": False, "error": "invalid_auth"})

    @server.add_tool
    def boom() -> str:
        """始终加注，以便调用结果带有 isError=True。"""
        raise RuntimeError("upstream exploded")

    server.start(transport="http")
    yield server
    server.stop()


# ---------------------------------------------------------------------------
# 幸福之路
# ---------------------------------------------------------------------------


def test_mcp_test_remote_success(client: TestClient, http_mcp_server: MCPTestServer):
    """可访问的 HTTP MCP 服务器应报告 ok=True 以及工具名称。"""
    response = client.post(
        "/api/mcp/test",
        json={
            "name": "happy-server",
            "server": {
                "transport": "http",
                "url": f"http://127.0.0.1:{http_mcp_server.port}/mcp",
            },
            "timeout": 10.0,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert set(body["tools"]) == {"echo", "add"}
    # 没有请求 tool_call -> 没有 tool_result（与旧客户端向后兼容）。
    assert body.get("tool_result") is None


def test_mcp_test_http_transport_is_accepted(
    client: TestClient, http_mcp_server: MCPTestServer
):
    response = client.post(
        "/api/mcp/test",
        json={
            "server": {
                "transport": "http",
                "url": f"http://127.0.0.1:{http_mcp_server.port}/mcp",
            },
            "timeout": 10.0,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True


def test_mcp_test_stdio_success(client: TestClient):
    """工作的 stdio MCP 服务器（FastMCP 通过当前 Python 运行）应该连接。

    我们通过当前的 Python 解释器运行一个微小的 FastMCP 脚本，以便测试保持密封（没有
    npx，没有网络）。
    """
    script = (
        "from fastmcp import FastMCP\n"
        "mcp = FastMCP('stdio-test')\n"
        "@mcp.tool()\n"
        "def ping() -> str:\n"
        "    return 'pong'\n"
        "mcp.run()\n"
    )

    response = client.post(
        "/api/mcp/test",
        json={
            "name": "stdio-happy",
            "server": {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-c", script],
            },
            "timeout": 20.0,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True, body
    assert "ping" in body["tools"]


# ---------------------------------------------------------------------------
# 工具调用探测（凭据验证）
# ---------------------------------------------------------------------------


def test_mcp_test_tool_call_reports_in_band_failure_payload(
    client: TestClient, slack_like_mcp_server: MCPTestServer
):
    """所请求的工具运行并逐字报告其载荷。

    Slack 风格的服务器将上游身份验证错误作为普通内容返回，且 isError 未设置； 端点必
    须显示载荷（好的仍然是 True——解释它是调用者的工作）。
    """
    response = client.post(
        "/api/mcp/test",
        json={
            "server": {
                "transport": "http",
                "url": f"http://127.0.0.1:{slack_like_mcp_server.port}/mcp",
            },
            "timeout": 10.0,
            "tool_call": {"name": "slack_list_channels", "arguments": {"limit": 1}},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["tool_result"]["is_error"] is False
    assert "invalid_auth" in body["tool_result"]["text"]


def test_mcp_test_tool_call_handler_error_sets_is_error(
    client: TestClient, slack_like_mcp_server: MCPTestServer
):
    """引发的工具处理程序通过 isError 标志报告。"""
    response = client.post(
        "/api/mcp/test",
        json={
            "server": {
                "transport": "http",
                "url": f"http://127.0.0.1:{slack_like_mcp_server.port}/mcp",
            },
            "timeout": 10.0,
            "tool_call": {"name": "boom"},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["tool_result"]["is_error"] is True


def test_mcp_test_tool_call_unknown_tool_reported_without_invocation(
    client: TestClient, http_mcp_server: MCPTestServer
):
    """请求服务器未公布的工具会产生错误
    tool_result 命名问题而不是盲目调用。"""
    response = client.post(
        "/api/mcp/test",
        json={
            "server": {
                "transport": "http",
                "url": f"http://127.0.0.1:{http_mcp_server.port}/mcp",
            },
            "timeout": 10.0,
            "tool_call": {"name": "definitely_not_a_tool"},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["tool_result"]["is_error"] is True
    assert "not advertised" in body["tool_result"]["text"]


def test_mcp_test_decrypts_encrypted_env_values_before_spawn():
    """从设置中往返的 Fernet 加密环境值被解密
    在服务器进程生成之前； 明文值通过。

    这就是让编辑流程测试 * 存储的 * 凭据的原因，即使 GUI 只看到已脱敏占位符。
    """
    config = Config(session_api_keys=[], secret_key=SecretStr("test-secret-key"))
    cipher = config.cipher
    assert cipher is not None
    client = TestClient(create_app(config), raise_server_exceptions=False)
    script = (
        "import json, os\n"
        "from fastmcp import FastMCP\n"
        "mcp = FastMCP('env-echo')\n"
        "@mcp.tool()\n"
        "def read_env() -> str:\n"
        "    return json.dumps({\n"
        "        'bot_token': os.environ.get('SLACK_BOT_TOKEN', ''),\n"
        "        'team_id': os.environ.get('SLACK_TEAM_ID', ''),\n"
        "    })\n"
        "mcp.run()\n"
    )

    response = client.post(
        "/api/mcp/test",
        json={
            "name": "env-echo",
            "server": {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-c", script],
                "env": {
                    "SLACK_BOT_TOKEN": cipher.encrypt(SecretStr("xoxb-real-token")),
                    "SLACK_TEAM_ID": "T0123",
                },
            },
            "timeout": 20.0,
            "tool_call": {"name": "read_env"},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True, body
    seen_env = json.loads(body["tool_result"]["text"])
    assert seen_env == {"bot_token": "xoxb-real-token", "team_id": "T0123"}


def test_mcp_test_decrypts_encrypted_remote_auth_before_connect(
    monkeypatch: pytest.MonkeyPatch,
):
    config = Config(session_api_keys=[], secret_key=SecretStr("test-secret-key"))
    cipher = config.cipher
    assert cipher is not None
    client = TestClient(create_app(config), raise_server_exceptions=False)
    seen_configs: list[dict[str, MCPServer]] = []

    class FakeClient:
        def __init__(self):
            self.tools: list[object] = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    def fake_create_mcp_tools(
        config: dict[str, MCPServer],
        timeout=30.0,
        *,
        mcp_oauth_token_storage=None,
    ):
        seen_configs.append(config)
        return FakeClient()

    monkeypatch.setattr(
        "openhands.agent_server.mcp_router.create_mcp_tools",
        fake_create_mcp_tools,
    )

    response = client.post(
        "/api/mcp/test",
        json={
            "name": "linear",
            "server": {
                "transport": "http",
                "url": "https://mcp.linear.app/mcp",
                "auth": {
                    "strategy": "bearer",
                    "value": cipher.encrypt(SecretStr("lin-real-token")),
                },
            },
            "timeout": 10.0,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    assert [to_fastmcp_mcp_config(config) for config in seen_configs] == [
        {
            "mcpServers": {
                "linear": {
                    "url": "https://mcp.linear.app/mcp",
                    "transport": "http",
                    "auth": "lin-real-token",
                }
            }
        }
    ]


# ---------------------------------------------------------------------------
# 失败路径——全部应该返回 HTTP 200 且 ok=False
# ---------------------------------------------------------------------------


def test_mcp_test_stdio_failure_returns_structured_error(client: TestClient):
    """错误的 stdio 命令应该返回 ok=False 并带有有用的错误。"""
    response = client.post(
        "/api/mcp/test",
        json={
            "name": "broken",
            "server": {
                "transport": "stdio",
                "command": "/this/path/does/not/exist/definitely-not-a-binary",
                "args": [],
            },
            "timeout": 5.0,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is False
    assert body["error_kind"] in {"connection", "timeout", "unknown"}
    assert body["error"], "expected a non-empty error message"


def test_mcp_test_remote_unreachable(client: TestClient):
    """连接到没有任何监听的端口应该会彻底失败。"""
    free_port = _find_free_port()
    response = client.post(
        "/api/mcp/test",
        json={
            "server": {
                "transport": "http",
                "url": f"http://127.0.0.1:{free_port}/mcp",
            },
            "timeout": 3.0,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is False
    assert body["error_kind"] in {"connection", "timeout"}


# ---------------------------------------------------------------------------
# 验证
# ---------------------------------------------------------------------------


def test_mcp_test_rejects_empty_command(client: TestClient):
    response = client.post(
        "/api/mcp/test",
        json={"server": {"transport": "stdio", "command": ""}},
    )
    assert response.status_code == 422


def test_mcp_test_rejects_unknown_transport(client: TestClient):
    response = client.post(
        "/api/mcp/test",
        json={"server": {"transport": "websocket", "url": "ws://example.com"}},
    )
    assert response.status_code == 422


def test_mcp_test_clamps_timeout_range(client: TestClient):
    """超时必须 > 0 且 <= 120； 0 应在模式层被拒绝。"""
    response = client.post(
        "/api/mcp/test",
        json={
            "server": {"transport": "stdio", "command": "true"},
            "timeout": 0,
        },
    )
    assert response.status_code == 422


def test_mcp_test_bearer_token_in_auth_field(
    client: TestClient, http_mcp_server: MCPTestServer
):
    """提供 bearer-token auth 不应中断连接。"""
    response = client.post(
        "/api/mcp/test",
        json={
            "server": {
                "transport": "http",
                "url": f"http://127.0.0.1:{http_mcp_server.port}/mcp",
                "auth": {"strategy": "bearer", "value": "test-token-123"},
            },
            "timeout": 10.0,
        },
    )

    # FastMCP 的 HTTP 服务器在此测试夹具中不强制执行身份验证，因此请求仍应成功； 这可以
    # 防止认证现场接线本身爆炸（e.g. 格式错误的标头会导致传输层崩溃）。
    #
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True


# ---------------------------------------------------------------------------
# OAuth 验证字段
# ---------------------------------------------------------------------------


def test_mcp_test_accepts_oauth_auth_credential(
    client: TestClient, http_mcp_server: MCPTestServer
):
    """应接受 OAuth 身份验证凭据并将其转发到 FastMCP。

    我们无法在单元测试中完成真正的 OAuth 握手，但我们可以验证该字段在模式层被接受并且
    不会使请求处理程序崩溃。 本地 FastMCP 测试服务器不需要 OAuth
    ，因此 FastMCP 将简单地忽略 ``auth`` 值并正常连接。
    """
    response = client.post(
        "/api/mcp/test",
        json={
            "server": {
                "transport": "http",
                "url": f"http://127.0.0.1:{http_mcp_server.port}/mcp",
                "auth": {"strategy": "oauth2"},
            },
            "timeout": 10.0,
        },
    )

    # 服务器不执行OAuth，所以连接应该成功。FastMCP 如果尝试了真实的OAuth流程，它会失败，
    # 因为测试服务器上没有OAuth元数据——但FastMCP 只在服务器返回401/403时启动流程。
    #
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert set(body["tools"]) == {"echo", "add"}


def test_mcp_test_rejects_auth_with_auth_header(client: TestClient):
    """FastMCP auth 字段与授权标头互斥。"""
    response = client.post(
        "/api/mcp/test",
        json={
            "server": {
                "transport": "http",
                "url": "https://example.com/mcp",
                "auth": {"strategy": "bearer", "value": "some-token"},
                "headers": {"Authorization": "Bearer other-token"},
            },
            "timeout": 5.0,
        },
    )
    assert response.status_code == 422


def test_mcp_test_rejects_oauth_auth_with_auth_header(client: TestClient):
    """OAuth 身份验证与顶级授权标头互斥。"""
    response = client.post(
        "/api/mcp/test",
        json={
            "server": {
                "transport": "http",
                "url": "https://example.com/mcp",
                "auth": {"strategy": "oauth2"},
                "headers": {"Authorization": "Bearer some-token"},
            },
            "timeout": 5.0,
        },
    )
    assert response.status_code == 422


def test_mcp_test_accepts_explicit_oauth_authentication(
    client: TestClient, http_mcp_server: MCPTestServer
):
    """结构化 OAuth 元数据应通过测试进行往返端点。"""
    response = client.post(
        "/api/mcp/test",
        json={
            "server": {
                "transport": "http",
                "url": f"http://127.0.0.1:{http_mcp_server.port}/mcp",
                "auth": {
                    "strategy": "oauth2",
                    "authentication": {
                        "type": "oauth",
                        "client_auth_method": "none",
                    },
                },
            },
            "timeout": 10.0,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert set(body["tools"]) == {"echo", "add"}


def test_mcp_test_returns_encrypted_oauth_state_from_probe(
    monkeypatch: pytest.MonkeyPatch,
):
    config = Config(session_api_keys=[], secret_key=SecretStr("test-secret-key"))
    client = TestClient(create_app(config), raise_server_exceptions=False)
    calls: list[object | None] = []

    class FakeClient:
        def __init__(self):
            self.tools: list[object] = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    def fake_create_mcp_tools(
        config,
        timeout=30.0,
        *,
        mcp_oauth_token_storage=None,
    ):
        calls.append(mcp_oauth_token_storage)
        assert mcp_oauth_token_storage is not None
        asyncio.run(
            mcp_oauth_token_storage.put(
                key="https://mcp.example.com/mcp/tokens",
                value={
                    "access_token": "oauth-access-token",
                    "refresh_token": "oauth-refresh-token",
                },
                collection="mcp-oauth-token",
            )
        )
        asyncio.run(
            mcp_oauth_token_storage.put(
                key="https://mcp.example.com/mcp/client_info",
                value={
                    "redirect_uris": ["http://127.0.0.1:64801/callback"],
                    "client_id": "superhuman-client",
                    "client_secret": "superhuman-client-secret",
                },
                collection="mcp-oauth-client-info",
            )
        )
        asyncio.run(
            mcp_oauth_token_storage.put(
                key="https://mcp.example.com/mcp/token_expiry",
                value={"expires_at": 12345.0},
                collection="mcp-oauth-token-expiry",
            )
        )
        return FakeClient()

    monkeypatch.setattr(
        "openhands.agent_server.mcp_router.create_mcp_tools",
        fake_create_mcp_tools,
    )

    response = client.post(
        "/api/mcp/test",
        json={
            "server": {
                "transport": "http",
                "url": "https://mcp.example.com/mcp",
                "auth": {
                    "strategy": "oauth2",
                    "authentication": {
                        "type": "oauth",
                        "client_auth_method": "none",
                    },
                },
            },
            "timeout": 10.0,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert len(calls) == 1
    assert "server" not in body
    oauth_state = body["oauth_state"]
    oauth_value = oauth_state["tokens"]
    assert oauth_value["access_token"].startswith("gAAAA")
    assert oauth_value["refresh_token"].startswith("gAAAA")
    assert oauth_value["access_token"] != "oauth-access-token"
    assert oauth_state["client_info"]["client_id"] == "superhuman-client"
    assert oauth_state["client_info"]["client_secret"].startswith("gAAAA")
    assert oauth_state["token_expires_at"] == 12345.0


def test_mcp_oauth_start_returns_authorization_url_and_final_state(
    monkeypatch: pytest.MonkeyPatch,
):
    config = Config(session_api_keys=[], secret_key=SecretStr("test-secret-key"))
    client = TestClient(create_app(config), raise_server_exceptions=False)

    class FakeOAuth:
        def __init__(self, job):
            self.job = job

        async def redirect_handler(self, authorization_url: str) -> None:
            self.job.set_authorization_url(authorization_url)

    def fake_oauth_from_authentication(authentication, *, oauth_token_storage, job):
        assert authentication.client_id == "notion-client"
        assert authentication.client_secret.get_secret_value() == "notion-secret"
        return FakeOAuth(job)

    class FakeClient:
        def __init__(self):
            self.tools = [SimpleNamespace(name="notion_lookup")]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    def fake_create_mcp_tools(
        config,
        timeout=30.0,
        *,
        mcp_oauth_token_storage=None,
        mcp_oauth_factory=None,
    ):
        assert mcp_oauth_token_storage is not None
        assert mcp_oauth_factory is not None
        server_name, server = next(iter(config.items()))
        oauth = mcp_oauth_factory(
            server_name,
            server,
            server.auth,
            mcp_oauth_token_storage,
        )
        asyncio.run(
            oauth.redirect_handler(
                "https://oauth.example.com/authorize?state=test-state"
            )
        )
        asyncio.run(
            mcp_oauth_token_storage.put(
                key="https://mcp.example.com/mcp/tokens",
                value={"access_token": "oauth-access-token"},
                collection="mcp-oauth-token",
            )
        )
        return FakeClient()

    monkeypatch.setattr(
        "openhands.agent_server.mcp_router._oauth_auth_from_authentication",
        fake_oauth_from_authentication,
    )
    monkeypatch.setattr(
        "openhands.agent_server.mcp_router.create_mcp_tools",
        fake_create_mcp_tools,
    )

    response = client.post(
        "/api/mcp/oauth/start",
        json={
            "server": {
                "transport": "http",
                "url": "https://mcp.example.com/mcp",
                "auth": {
                    "strategy": "oauth2",
                    "authentication": {
                        "type": "oauth",
                        "client_auth_method": "client_secret_post",
                        "client_id": "notion-client",
                        "client_secret": "notion-secret",
                    },
                },
            },
            "timeout": 10.0,
        },
    )

    assert response.status_code == 200, response.text
    start_body = response.json()
    assert start_body["ok"] is True
    assert start_body["authorization_url"].startswith("https://oauth.example.com/")

    status_body = None
    for _ in range(20):
        status_response = client.get(f"/api/mcp/oauth/status/{start_body['job_id']}")
        assert status_response.status_code == 200, status_response.text
        status_body = status_response.json()
        if status_body["status"] == "succeeded":
            break
        time.sleep(0.05)

    assert status_body is not None
    assert status_body["ok"] is True
    assert status_body["status"] == "succeeded"
    assert status_body["tools"] == ["notion_lookup"]
    access_token = status_body["oauth_state"]["tokens"]["access_token"]
    assert access_token.startswith("gAAAA")
    assert access_token != "oauth-access-token"


def test_mcp_oauth_start_succeeds_without_consent_when_stored_tokens_work(
    monkeypatch: pytest.MonkeyPatch,
):
    # 排列：探头与存储的token连接； FastMCP 从来没有
    # 发布授权 URL。
    config = Config(session_api_keys=[], secret_key=SecretStr("test-secret-key"))
    client = TestClient(create_app(config), raise_server_exceptions=False)

    class FakeClient:
        def __init__(self):
            self.tools = [SimpleNamespace(name="notion_lookup")]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(
        "openhands.agent_server.mcp_router.create_mcp_tools",
        lambda *args, **kwargs: FakeClient(),
    )

    # 法案
    started = time.monotonic()
    response = client.post(
        "/api/mcp/oauth/start",
        json={
            "server": {
                "transport": "http",
                "url": "https://mcp.example.com/mcp",
                "auth": {
                    "strategy": "oauth2",
                    "state": {"tokens": {"access_token": "stored-access-token"}},
                },
            },
            "timeout": 10.0,
        },
    )
    elapsed = time.monotonic() - started

    # 断言：仅使用作业 ID 即可成功，无需等待同意
    # 超时; 结果在状态路径上。
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    assert response.json() == {"ok": True, "job_id": job_id}
    assert elapsed < 5.0
    status_body = client.get(f"/api/mcp/oauth/status/{job_id}").json()
    assert status_body["status"] == "succeeded"
    assert status_body["tools"] == ["notion_lookup"]


def test_browser_coordinated_oauth_callback_handler_delegates_to_fastmcp(
    monkeypatch: pytest.MonkeyPatch,
):
    """原样返回FastMCP的结果； 重新包装它打破了 MCP 2.x。"""
    job = _MCPOAuthProbeJob(
        request=MCPTestRequest.model_validate(
            {"server": {"transport": "http", "url": "https://mcp.example.com/mcp"}}
        ),
        cipher=None,
    )
    oauth = _BrowserCoordinatedOAuth(
        job=job,
        mcp_url="https://mcp.example.com/mcp",
        callback_port=64801,
    )

    sentinel = object()
    seen: list[bool] = []

    async def fake_base_callback_handler(self):
        # URL 必须在回调上的基本块之前发布，否则前端永远不会知道将浏览器发送到哪里。
        #
        seen.append(job.callback_ready.is_set())
        return sentinel

    monkeypatch.setattr(
        "fastmcp.client.auth.oauth.OAuth.callback_handler",
        fake_base_callback_handler,
    )

    result = asyncio.run(oauth.callback_handler())

    assert result is sentinel
    assert seen == [True]
    assert job.callback_url == "http://localhost:64801/callback"


def test_mcp_oauth_callback_rejects_unknown_job(client: TestClient):
    response = client.post(
        "/api/mcp/oauth/callback/not-a-job",
        json={"callback_url": "http://127.0.0.1:12345/callback?code=x&state=y"},
    )

    assert response.status_code == 404


@pytest.fixture
def closed_callback_job() -> Generator[_MCPOAuthProbeJob]:
    """其本地回调服务器不再侦听的已注册作业。"""
    job = _MCPOAuthProbeJob(
        request=MCPTestRequest.model_validate(
            {"server": {"transport": "http", "url": "https://mcp.example.com/mcp"}}
        ),
        cipher=None,
    )
    job.set_authorization_url("https://oauth.example.com/authorize?state=s")
    job.set_callback_ready(f"http://localhost:{_find_free_port()}/callback")
    _register_oauth_job(job)
    try:
        yield job
    finally:
        with _oauth_probe_jobs_lock:
            _oauth_probe_jobs.pop(job.id, None)


@pytest.mark.parametrize(
    ("result", "expected_status"),
    [
        (MCPTestSuccess(tools=["echo"]), "succeeded"),
        (
            MCPTestFailure(error="Timed out", error_kind="timeout"),
            "failed",
        ),
    ],
)
def test_mcp_oauth_callback_replay_on_finished_job_returns_job_status(
    client: TestClient,
    closed_callback_job: _MCPOAuthProbeJob,
    result,
    expected_status: str,
):
    closed_callback_job.set_result(result)

    response = client.post(
        f"/api/mcp/oauth/callback/{closed_callback_job.id}",
        json={"callback_url": f"{closed_callback_job.callback_url}?code=x&state=s"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == expected_status
    assert closed_callback_job.status == expected_status


def test_mcp_oauth_callback_server_gone_on_live_job_returns_409(
    client: TestClient, closed_callback_job: _MCPOAuthProbeJob
):
    response = client.post(
        f"/api/mcp/oauth/callback/{closed_callback_job.id}",
        json={"callback_url": f"{closed_callback_job.callback_url}?code=x&state=s"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "OAuth callback server is not listening"
    assert closed_callback_job.status == "authorizing"


def test_register_oauth_job_sweeps_expired_jobs():
    old_job = _MCPOAuthProbeJob(
        request=MCPTestRequest.model_validate(
            {"server": {"transport": "http", "url": "https://mcp.example.com/mcp"}}
        ),
        cipher=None,
    )
    old_job.created_at -= _OAUTH_PROBE_JOB_TTL_SECONDS + 1
    new_job = _MCPOAuthProbeJob(
        request=MCPTestRequest.model_validate(
            {"server": {"transport": "http", "url": "https://mcp.example.com/mcp"}}
        ),
        cipher=None,
    )
    try:
        with _oauth_probe_jobs_lock:
            _oauth_probe_jobs.clear()
            _oauth_probe_jobs[old_job.id] = old_job
        _register_oauth_job(new_job)

        with _oauth_probe_jobs_lock:
            assert old_job.id not in _oauth_probe_jobs
            assert new_job.id in _oauth_probe_jobs
    finally:
        with _oauth_probe_jobs_lock:
            _oauth_probe_jobs.clear()


def test_mcp_test_rejects_legacy_top_level_oauth_authentication(client: TestClient):
    """OAuth 元数据现在属于 OAuth 身份验证凭据内部。"""
    response = client.post(
        "/api/mcp/test",
        json={
            "server": {
                "transport": "http",
                "url": "https://example.com/mcp",
                "authentication": {
                    "type": "oauth",
                    "client_auth_method": "none",
                },
            },
            "timeout": 5.0,
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("callback_url", "detail"),
    [
        ("http://localhost:99999/callback?code=x", "Unexpected OAuth callback URL"),
        ("http://localhost:abc/callback?code=x", "Unexpected OAuth callback URL"),
        ("http://[::1/callback?code=x", "Invalid OAuth callback URL"),
    ],
)
def test_mcp_oauth_callback_rejects_malformed_url_with_400(
    client: TestClient, callback_url: str, detail: str
):
    job = _MCPOAuthProbeJob(
        request=MCPTestRequest.model_validate(
            {"server": {"transport": "http", "url": "https://mcp.example.com/mcp"}}
        ),
        cipher=None,
    )
    job.set_authorization_url("https://auth.example.com/authorize")
    job.set_callback_ready("http://localhost:64801/callback")
    try:
        _register_oauth_job(job)
        response = client.post(
            f"/api/mcp/oauth/callback/{job.id}",
            json={"callback_url": callback_url},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == detail
        assert job.status == "authorizing"
    finally:
        with _oauth_probe_jobs_lock:
            _oauth_probe_jobs.clear()
