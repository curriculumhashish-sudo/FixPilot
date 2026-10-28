"""测试服务器详细信息路由器，包括 /ready 端点。"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import openhands.agent_server.server_details_router as sdr
from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config


@pytest.fixture(autouse=True)
def reset_initialization_state():
    """在测试之间重置 asyncio.Event 以避免状态泄漏。"""
    sdr._initialization_complete = asyncio.Event()
    yield
    sdr._initialization_complete = asyncio.Event()


@pytest.fixture
def client():
    app = create_app(Config(static_files_path=None))
    return TestClient(app)


def test_alive_and_health_return_ok_status(client):
    """活性和健康检查应该共享相同的 JSON 载荷。"""
    for endpoint in ("/alive", "/health"):
        response = client.get(endpoint)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_ready_returns_503_before_init(client):
    """当初始化未完成时，/ready 端点应返回 503。"""
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "initializing"


def test_ready_returns_200_after_init(client):
    """/ready 端点在 mark_initialization_complete() 之后应返回 200。"""
    sdr.mark_initialization_complete()
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_ready_resets_after_new_event(client):
    """重置事件后，/ready 应再次返回 503。"""
    sdr.mark_initialization_complete()
    assert client.get("/ready").status_code == 200

    # 模拟重置 (e.g. 用于测试）
    sdr._initialization_complete = asyncio.Event()
    response = client.get("/ready")
    assert response.status_code == 503


def test_server_info_reports_usable_tools(client, monkeypatch: pytest.MonkeyPatch):
    """/server_info 应该公开注册表过滤的可用工具列表。"""
    monkeypatch.setattr(
        sdr,
        "list_usable_tools",
        lambda: ["terminal", "file_editor"],
    )

    response = client.get("/server_info")

    assert response.status_code == 200
    assert response.json()["usable_tools"] == ["terminal", "file_editor"]


def test_server_info_leaves_out_browser_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
):
    """当enable_browser=False时，usable_tools与目录一致。"""
    monkeypatch.setattr(
        sdr,
        "list_usable_tools",
        lambda: ["terminal", "browser_tool_set", "file_editor"],
    )
    client = TestClient(
        create_app(Config(static_files_path=None, enable_browser=False))
    )

    response = client.get("/server_info")

    assert response.status_code == 200
    assert response.json()["usable_tools"] == ["terminal", "file_editor"]


def test_server_info_browser_follows_configured_availability(
    monkeypatch: pytest.MonkeyPatch,
):
    """配置固定的浏览器可用性会覆盖进程探针。"""
    monkeypatch.setattr(sdr, "list_usable_tools", lambda: ["terminal"])
    monkeypatch.setattr(
        sdr, "list_registered_tools", lambda: ["terminal", "browser_tool_set"]
    )

    assert sdr.build_server_info(browser_available=None).usable_tools == ["terminal"]
    assert sdr.build_server_info(browser_available=True).usable_tools == [
        "terminal",
        "browser_tool_set",
    ]
    assert sdr.build_server_info(browser_available=False).usable_tools == ["terminal"]


def test_server_info_reports_credential_binding_probe(client):
    response = client.get("/server_info")

    assert response.status_code == 200
    payload = response.json()
    assert {
        "profile_secret_scope_v1",
        "profile_persona_v1",
        "credential_binding_v1",
        "credential_binding_readiness_probe_v1",
        "credential_binding_activation_guard_v1",
        "conversation_runtime_routes_v1",
        "agent_launch_pipeline_v1",
        "profile_public_skills_v1",
    } <= set(payload["capabilities"])
    assert payload["conversation_runtime"] == "local"


def test_server_info_reports_configured_app_backend_bridge():
    app = create_app(
        Config(
            static_files_path=None,
            app_backend_public_url="https://apps.example.test",
        )
    )
    with TestClient(app) as bridge_client:
        payload = bridge_client.get("/server_info").json()

    assert payload["app_backend_ingress_url"] == "https://apps.example.test"
    assert "canvas_app_backend_bridge_v1" in payload["capabilities"]


def test_server_info_omits_unconfigured_app_backend_bridge(client):
    payload = client.get("/server_info").json()

    assert payload["app_backend_ingress_url"] is None
    assert "canvas_app_backend_bridge_v1" not in payload["capabilities"]


def test_server_info_reports_configured_conversation_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path / "persistence"))
    app = create_app(
        Config(
            static_files_path=None,
            conversation_runtime="docker",
            conversations_path=tmp_path / "conversations",
            workspace_path=tmp_path / "workspaces",
            secret_key=SecretStr("test-key"),
        )
    )
    with TestClient(app) as docker_client:
        assert (
            docker_client.get("/server_info").json()["conversation_runtime"] == "docker"
        )


def test_server_info_reports_runtime_timeout_cap(
    client,
    monkeypatch: pytest.MonkeyPatch,
):
    """/server_info 应暴露空闲派生端子超时上限。"""
    monkeypatch.setenv("OH_RUNTIME_IDLE_TIMEOUT_SECONDS", "1200")

    response = client.get("/server_info")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime_idle_timeout_seconds"] == 1200
    assert payload["max_foreground_terminal_timeout_seconds"] == 1080


def test_server_info_advertises_profile_secret_enforcement(client):
    response = client.get("/server_info")
    assert response.status_code == 200
    assert "profile_secret_scope_v1" in response.json()["capabilities"]


def test_server_info_advertises_tool_catalog_and_draft_materialize(client):
    capabilities = client.get("/server_info").json()["capabilities"]
    assert "tool_catalog_v1" in capabilities
    assert "agent_profile_draft_materialize_v1" in capabilities
