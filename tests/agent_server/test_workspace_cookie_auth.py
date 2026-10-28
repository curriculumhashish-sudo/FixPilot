"""工作区 cookie 身份验证流程的端到端测试。

练习完整的 ``create_app(Config(session_api_keys=...))`` 连接，因此我们涵盖了新的
``/api/auth/workspace-session`` 端点和门控工作区静态文件路由的 cookie 或 header 依赖
项。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config
from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.dependencies import (
    WORKSPACE_SESSION_COOKIE_NAME,
    get_conversation_service,
)
from openhands.agent_server.event_service import EventService
from openhands.sdk.workspace import LocalWorkspace


SESSION_KEY = "test-key-abc"


@pytest.fixture
def client_factory(tmp_path):
    """构建一个配置了身份验证的 TestClient，并提供一个工作区。"""

    def _build(*, conversation_id: UUID, workspace_dir=None) -> TestClient:
        ws = workspace_dir if workspace_dir is not None else tmp_path

        event_service = AsyncMock(spec=EventService)
        event_service.stored = SimpleNamespace(
            workspace=LocalWorkspace(working_dir=str(ws))
        )
        conversation_service = AsyncMock(spec=ConversationService)

        async def _get_event_service(cid: UUID):
            if cid == conversation_id:
                return event_service
            return None

        conversation_service.get_event_service.side_effect = _get_event_service

        app = create_app(Config(session_api_keys=[SESSION_KEY]))
        # 使用我们的模拟对象覆盖生命周期管理的对话服务。
        app.dependency_overrides[get_conversation_service] = (
            lambda: conversation_service
        )
        return TestClient(app, raise_server_exceptions=False)

    return _build


@pytest.fixture
def workspace_with_index(tmp_path):
    (tmp_path / "index.html").write_text("<title>hello</title>")
    return tmp_path


def _workspace_url(cid: UUID, path: str = "index.html") -> str:
    return f"/api/conversations/{cid}/workspace/{path}"


# ---- 基线标头行为（回归覆盖范围） ----------------------


def test_workspace_rejects_request_without_credentials(
    client_factory, workspace_with_index
):
    cid = uuid4()
    client = client_factory(conversation_id=cid, workspace_dir=workspace_with_index)

    assert client.get(_workspace_url(cid)).status_code == 401


def test_workspace_accepts_valid_header(client_factory, workspace_with_index):
    cid = uuid4()
    client = client_factory(conversation_id=cid, workspace_dir=workspace_with_index)

    resp = client.get(
        _workspace_url(cid),
        headers={"X-Session-API-Key": SESSION_KEY},
    )
    assert resp.status_code == 200
    assert resp.text == "<title>hello</title>"


def test_workspace_rejects_invalid_header(client_factory, workspace_with_index):
    cid = uuid4()
    client = client_factory(conversation_id=cid, workspace_dir=workspace_with_index)

    resp = client.get(
        _workspace_url(cid),
        headers={"X-Session-API-Key": "not-the-key"},
    )
    assert resp.status_code == 401


# ---- POST /api/auth/workspace-session -------------------------------------


def test_mint_session_requires_header(client_factory, workspace_with_index):
    client = client_factory(conversation_id=uuid4())

    resp = client.post("/api/auth/workspace-session")
    assert resp.status_code == 401
    assert "set-cookie" not in {k.lower() for k in resp.headers}


def test_mint_session_rejects_bad_header(client_factory):
    client = client_factory(conversation_id=uuid4())

    resp = client.post(
        "/api/auth/workspace-session",
        headers={"X-Session-API-Key": "wrong"},
    )
    assert resp.status_code == 401


def test_mint_session_returns_cookie_attrs_over_https(client_factory):
    """在设置 X-Forwarded-Proto=HTTPS 的 TLS 终止代理后面，
    我们发布完整的跨站点 iframe cookie 属性集。"""
    client = client_factory(conversation_id=uuid4())

    resp = client.post(
        "/api/auth/workspace-session",
        headers={
            "X-Session-API-Key": SESSION_KEY,
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "agent.example.com",
        },
    )
    assert resp.status_code == 204

    set_cookie = resp.headers["set-cookie"]
    assert set_cookie.startswith(f"{WORKSPACE_SESSION_COOKIE_NAME}={SESSION_KEY}")
    # 跨站 iframe 要求：
    assert "SameSite=none" in set_cookie
    assert "Secure" in set_cookie
    assert "Partitioned" in set_cookie
    # 防守默认：
    assert "HttpOnly" in set_cookie
    assert "Path=/api/conversations" in set_cookie


@pytest.mark.parametrize(
    "host_header",
    [
        "localhost",
        "localhost:8000",
        "127.0.0.1",
        "127.0.0.1:8000",
        "[::1]",
        "[::1]:8000",
    ],
)
def test_mint_session_marks_cookie_secure_on_loopback(client_factory, host_header):
    """浏览器（根据安全上下文规范）接受 ``Secure`` cookie
    在普通的HTTP环回起源上。 在这里发出 Secure 可以让本地开发人员针对
    ``http://localhost`` 实际上接收 cookie，这是
    ``SameSite=None`` 非安全 cookie 不会。"""
    client = client_factory(conversation_id=uuid4())

    resp = client.post(
        "/api/auth/workspace-session",
        headers={"X-Session-API-Key": SESSION_KEY, "Host": host_header},
    )
    assert resp.status_code == 204

    set_cookie = resp.headers["set-cookie"]
    assert "Secure" in set_cookie
    assert "Partitioned" in set_cookie


def test_mint_session_marks_cookie_secure_on_forwarded_ipv6_loopback(
    client_factory,
):
    """``X-Forwarded-Host`` 中括号内的 IPv6 环回是安全的上下文。"""
    client = client_factory(conversation_id=uuid4())

    resp = client.post(
        "/api/auth/workspace-session",
        headers={
            "X-Session-API-Key": SESSION_KEY,
            "Host": "agent.example.com",
            "X-Forwarded-Host": "[::1]:8000",
        },
    )
    assert resp.status_code == 204

    set_cookie = resp.headers["set-cookie"]
    assert "Secure" in set_cookie
    assert "Partitioned" in set_cookie


def test_mint_session_over_remote_plain_http_drops_secure(client_factory):
    """在非 HTTPS 到非环回主机上，我们不声明安全 —
    浏览器无论如何都会拒绝普通 HTTP 上的安全 cookie。 在这种情况下，cookie实际上不会
    为跨站嵌入工作（SameSite=None 需要 Secure）
    ，但发出我们无法遵守的 Secure 属性只会让失败模式更加不明显。
    """
    client = client_factory(conversation_id=uuid4())

    resp = client.post(
        "/api/auth/workspace-session",
        headers={
            "X-Session-API-Key": SESSION_KEY,
            "Host": "agent.example.com",
        },
    )
    assert resp.status_code == 204

    set_cookie = resp.headers["set-cookie"]
    assert "SameSite=none" in set_cookie
    assert "Secure" not in set_cookie
    assert "Partitioned" not in set_cookie


# ---- 工作区路由器上的 Cookie 身份验证 ------------------------------------------------
# --


def test_workspace_accepts_valid_cookie(client_factory, workspace_with_index):
    cid = uuid4()
    client = client_factory(conversation_id=cid, workspace_dir=workspace_with_index)

    mint = client.post(
        "/api/auth/workspace-session",
        headers={"X-Session-API-Key": SESSION_KEY},
    )
    assert mint.status_code == 204
    assert WORKSPACE_SESSION_COOKIE_NAME in mint.cookies

    # 现在使用仅获取 cookie —— 没有 X-Session-API-Key 标头。
    resp = client.get(_workspace_url(cid))
    assert resp.status_code == 200
    assert resp.text == "<title>hello</title>"


def test_workspace_rejects_bogus_cookie(client_factory, workspace_with_index):
    cid = uuid4()
    client = client_factory(conversation_id=cid, workspace_dir=workspace_with_index)

    client.cookies.set(WORKSPACE_SESSION_COOKIE_NAME, "definitely-wrong")
    resp = client.get(_workspace_url(cid))
    assert resp.status_code == 401


# ---- Cookie 被非工作区端点拒绝 ------------------------


def test_cookie_does_not_authenticate_other_api_endpoints(client_factory):
    """该 cookie 只能由工作区路由器接受。 REST 的
    API 继续需要 X-Session-API-Key 标头，因此我们不会将 CSRF 表面添加到状态更改端点。
    """
    client = client_factory(conversation_id=uuid4())

    mint = client.post(
        "/api/auth/workspace-session",
        headers={"X-Session-API-Key": SESSION_KEY},
    )
    assert mint.status_code == 204

    # /api/conversations 由仅标头依赖项控制。
    resp = client.get("/api/conversations")
    assert resp.status_code == 401


# ---- DELETE 清除 cookie ------------------------------------------------------


def test_delete_session_clears_cookie(client_factory):
    client = client_factory(conversation_id=uuid4())

    resp = client.delete(
        "/api/auth/workspace-session",
        headers={"X-Session-API-Key": SESSION_KEY},
    )
    assert resp.status_code == 204
    # 通过 Max-Age=0 清除具有匹配属性的 Cookie。
    set_cookie = resp.headers["set-cookie"]
    assert f'{WORKSPACE_SESSION_COOKIE_NAME}=""' in set_cookie
    assert "Max-Age=0" in set_cookie
    assert "Path=/api/conversations" in set_cookie
