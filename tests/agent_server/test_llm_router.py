"""测试 LLM 路由器。"""

import httpx
import litellm
import pytest
from fastapi.testclient import TestClient

from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config
from openhands.agent_server.llm_router import (
    list_models,
    list_providers,
    list_verified_models,
)
from openhands.sdk.llm.auth.openai import OPENAI_CODEX_MODELS
from openhands.sdk.llm.utils.verified_models import VERIFIED_MODELS


@pytest.fixture
def client():
    """创建一个测试客户端。"""
    config = Config(session_api_keys=[])  # 禁用身份验证进行测试
    app = create_app(config)
    return TestClient(app)


@pytest.mark.asyncio
async def test_list_providers():
    """直接测试列表提供商。"""
    response = await list_providers()
    assert len(response.providers) > 0
    assert "openai" in response.providers
    assert "anthropic" in response.providers
    assert response.providers == sorted(response.providers)


@pytest.mark.asyncio
async def test_list_models():
    """直接测试列表模型。"""
    response = await list_models(provider=None)
    assert len(response.models) > 0
    assert response.models == sorted(set(response.models))


@pytest.mark.asyncio
async def test_list_models_filtered_by_provider():
    """测试按提供商过滤的列表模型。"""
    response = await list_models(provider="openai")
    assert len(response.models) > 0
    assert "gpt-5.6" in response.models
    assert "gpt-5.6-sol" in response.models
    assert "gpt-5.6-terra" in response.models
    assert "gpt-5.6-luna" in response.models
    # 验证过滤是否有效 - 模型数量应该少于未过滤的模型数量
    all_models_response = await list_models(provider=None)
    assert len(response.models) < len(all_models_response.models)


@pytest.mark.parametrize("openrouter_in_catalog", [False, True])
def test_list_models_filtered_by_openrouter_provider(
    client, monkeypatch, openrouter_in_catalog
):
    """经过验证的路线在目录删除后不会泄漏直接模型。"""
    catalog = [
        "deepseek/deepseek-chat",
        "deepseek/deepseek-v4-pro",
        "deepseek/deepseek-v4-flash",
    ]
    if openrouter_in_catalog:
        catalog.append("openrouter/deepseek/deepseek-chat")
    monkeypatch.setattr(litellm, "model_list", catalog)
    monkeypatch.setattr(
        litellm,
        "model_cost",
        {"openrouter/custom/model": {}} if openrouter_in_catalog else {},
    )

    response = client.get("/api/llm/models?provider=openrouter")

    assert response.status_code == 200
    models = response.json()["models"]
    assert "openrouter/deepseek/deepseek-chat" in models
    assert all(model.startswith("openrouter/") for model in models)
    assert models == sorted(set(models))
    if openrouter_in_catalog:
        assert "openrouter/custom/model" in models
    assert set(models) <= set(client.get("/api/llm/models").json()["models"])


@pytest.mark.asyncio
async def test_list_models_unknown_provider():
    """测试列出具有未知提供商的模型会返回空列表。"""
    response = await list_models(provider="unknown_provider_xyz")
    assert response.models == []


@pytest.mark.asyncio
async def test_list_verified_models():
    """测试直接列出经过验证的模型。"""
    response = await list_verified_models()
    assert response.models == VERIFIED_MODELS
    assert "openai" in response.models
    assert "anthropic" in response.models
    assert "openrouter" in response.models


def test_providers_endpoint_integration(client):
    """测试提供者端点到 API。"""
    response = client.get("/api/llm/providers")
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert len(data["providers"]) > 0
    assert "openai" in data["providers"]


def test_models_endpoint_integration(client):
    """测试模型端点到 API。"""
    response = client.get("/api/llm/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert len(data["models"]) > 0


def test_models_endpoint_with_provider_filter(client):
    """使用提供者查询参数测试模型端点。"""
    response = client.get("/api/llm/models?provider=openai")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert len(data["models"]) > 0
    assert "gpt-5.6" in data["models"]


def test_models_endpoint_with_unknown_provider(client):
    """具有未知提供商的测试模型端点返回空列表。"""
    response = client.get("/api/llm/models?provider=unknown_provider_xyz")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert data["models"] == []


def test_verified_models_endpoint_integration(client):
    """测试验证模型端点到 API。"""
    response = client.get("/api/llm/models/verified")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert "openai" in data["models"]
    assert "anthropic" in data["models"]
    assert "gpt-5.6" in data["models"]["openai"]
    assert "claude-opus-5" in data["models"]["anthropic"]
    assert "deepseek-v4-flash" in data["models"]["deepseek"]
    assert "kimi-k3" in data["models"]["moonshot"]
    assert "claude-opus-5" in data["models"]["openhands"]
    assert "deepseek-v4-flash" in data["models"]["openhands"]
    assert "kimi-k3" in data["models"]["openhands"]


def test_openai_subscription_models_endpoint_integration(client):
    """测试订阅模型端点到 API。"""
    response = client.get("/api/llm/subscription/openai/models")
    assert response.status_code == 200
    data = response.json()
    assert data == {"vendor": "openai", "models": sorted(OPENAI_CODEX_MODELS)}
    assert {
        "gpt-6.1-sol",
        "gpt-6-sol",
        "gpt-6-luna",
        "gpt-6-astra",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.5",
    } <= set(data["models"])


def test_openai_subscription_status_endpoint_does_not_return_tokens(
    client, monkeypatch
):
    """状态报告安全元数据而不暴露 OAuth token。"""
    from openhands.agent_server import llm_router
    from openhands.sdk.llm.auth.credentials import OAuthCredentials

    class FakeAuth:
        async def refresh_if_needed(self):
            return OAuthCredentials(
                vendor="openai",
                access_token="access-token",
                refresh_token="refresh-token",
                expires_at=4_102_444_800_000,
            )

        def get_credentials(self):
            return OAuthCredentials(
                vendor="openai",
                access_token="access-token",
                refresh_token="refresh-token",
                expires_at=4_102_444_800_000,
            )

    monkeypatch.setattr(llm_router, "_get_openai_subscription_auth", FakeAuth)

    response = client.get("/api/llm/subscription/openai/status")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "vendor": "openai",
        "connected": True,
        "account_email": None,
        "expires_at": 4_102_444_800_000,
    }
    assert "access_token" not in response.text
    assert "refresh_token" not in response.text


def test_openai_subscription_status_offline_refresh_reads_disconnected(
    client, monkeypatch
):
    """无法达到 OpenAI 的刷新将读取为已断开连接，而不是 500。"""
    from openhands.agent_server import llm_router

    class FakeAuth:
        async def refresh_if_needed(self):
            raise httpx.ConnectError("All connection attempts failed")

        def get_credentials(self):
            raise AssertionError("status must not read credentials after failure")

    monkeypatch.setattr(llm_router, "_get_openai_subscription_auth", FakeAuth)

    response = client.get("/api/llm/subscription/openai/status")

    assert response.status_code == 200
    assert response.json() == {
        "vendor": "openai",
        "connected": False,
        "account_email": None,
        "expires_at": None,
    }


def test_openai_subscription_device_start_returns_opaque_poll_token(
    client, monkeypatch
):
    """设备启动存储OpenAI内部服务器端。"""
    from openhands.agent_server import llm_router
    from openhands.sdk.llm.auth.openai import DeviceCode

    class FakeAuth:
        async def start_device_login(self):
            return DeviceCode(
                verification_url="https://auth.example/device",
                user_code="ABCD-EFGH",
                device_auth_id="openai-device-auth-id",
                interval=7,
            )

    monkeypatch.setattr(llm_router, "_get_openai_subscription_auth", FakeAuth)
    monkeypatch.setattr(llm_router.secrets, "token_urlsafe", lambda _: "opaque-token")

    response = client.post("/api/llm/subscription/openai/device/start")

    assert response.status_code == 200
    data = response.json()
    assert data["device_code"] == "opaque-token"
    assert data["user_code"] == "ABCD-EFGH"
    assert data["verification_uri"] == "https://auth.example/device"
    assert data["interval_seconds"] == 7
    assert "openai-device-auth-id" not in response.text


def test_openai_subscription_device_poll_pending_and_success(client, monkeypatch):
    """轮询在等待期间返回断开连接，在成功后返回连接。"""
    from openhands.agent_server import llm_router
    from openhands.sdk.llm.auth.credentials import OAuthCredentials
    from openhands.sdk.llm.auth.openai import DeviceCode

    llm_router._PENDING_OPENAI_DEVICE_LOGINS.clear()
    llm_router._PENDING_OPENAI_DEVICE_LOGINS["opaque-token"] = (
        llm_router.PendingDeviceLogin(
            device_code=DeviceCode(
                verification_url="https://auth.example/device",
                user_code="ABCD-EFGH",
                device_auth_id="openai-device-auth-id",
                interval=1,
            ),
            expires_at=int(llm_router.time.time() * 1000) + 60_000,
            epoch=llm_router._OPENAI_DEVICE_LOGIN_EPOCH,
        )
    )

    class FakeAuth:
        calls = 0

        saved_credentials = None

        async def poll_device_login(self, device_code, *, persist=True):
            assert persist is False
            self.__class__.calls += 1
            if self.__class__.calls == 1:
                return None
            return OAuthCredentials(
                vendor="openai",
                access_token="access-token",
                refresh_token="refresh-token",
                expires_at=4_102_444_800_000,
            )

        def save_credentials(self, credentials):
            self.__class__.saved_credentials = credentials

    monkeypatch.setattr(llm_router, "_get_openai_subscription_auth", FakeAuth)

    pending = client.post(
        "/api/llm/subscription/openai/device/poll",
        json={"device_code": "opaque-token"},
    )
    success = client.post(
        "/api/llm/subscription/openai/device/poll",
        json={"device_code": "opaque-token"},
    )

    assert pending.status_code == 200
    assert pending.json()["connected"] is False
    assert success.status_code == 200
    assert success.json()["connected"] is True
    assert success.json()["expires_at"] == 4_102_444_800_000
    assert FakeAuth.saved_credentials is not None
    assert "access-token" not in success.text
    assert "opaque-token" not in llm_router._PENDING_OPENAI_DEVICE_LOGINS


@pytest.mark.asyncio
async def test_openai_subscription_device_poll_failure_keeps_pending_login(
    monkeypatch,
):
    """暂时的提供者故障不会消耗不透明的轮询 token。"""
    from openhands.agent_server import llm_router
    from openhands.sdk.llm.auth.credentials import OAuthCredentials
    from openhands.sdk.llm.auth.openai import DeviceCode

    llm_router._PENDING_OPENAI_DEVICE_LOGINS.clear()
    llm_router._IN_FLIGHT_OPENAI_DEVICE_LOGINS.clear()
    llm_router._PENDING_OPENAI_DEVICE_LOGINS["opaque-token"] = (
        llm_router.PendingDeviceLogin(
            device_code=DeviceCode(
                verification_url="https://auth.example/device",
                user_code="ABCD-EFGH",
                device_auth_id="openai-device-auth-id",
                interval=1,
            ),
            expires_at=int(llm_router.time.time() * 1000) + 60_000,
            epoch=llm_router._OPENAI_DEVICE_LOGIN_EPOCH,
        )
    )

    class FakeAuth:
        calls = 0
        saved_credentials = None

        async def poll_device_login(self, device_code, *, persist=True):
            assert persist is False
            self.__class__.calls += 1
            if self.__class__.calls == 1:
                raise RuntimeError("temporary provider failure")
            return OAuthCredentials(
                vendor="openai",
                access_token="access-token",
                refresh_token="refresh-token",
                expires_at=4_102_444_800_000,
            )

        def save_credentials(self, credentials):
            self.__class__.saved_credentials = credentials

    monkeypatch.setattr(llm_router, "_get_openai_subscription_auth", FakeAuth)

    with pytest.raises(RuntimeError, match="temporary provider failure"):
        await llm_router.poll_openai_subscription_device_login(
            llm_router.SubscriptionDevicePollRequest(device_code="opaque-token")
        )
    assert "opaque-token" in llm_router._PENDING_OPENAI_DEVICE_LOGINS

    success = await llm_router.poll_openai_subscription_device_login(
        llm_router.SubscriptionDevicePollRequest(device_code="opaque-token")
    )

    assert success.connected is True
    assert FakeAuth.saved_credentials is not None
    assert "opaque-token" not in llm_router._PENDING_OPENAI_DEVICE_LOGINS
    assert "opaque-token" not in llm_router._IN_FLIGHT_OPENAI_DEVICE_LOGINS


def test_openai_subscription_logout_endpoint(client, monkeypatch):
    """注销会删除凭据并返回断开连接状态。"""
    from openhands.agent_server import llm_router

    llm_router._PENDING_OPENAI_DEVICE_LOGINS["opaque-token"] = (
        llm_router.PendingDeviceLogin(
            device_code=llm_router.DeviceCode(
                verification_url="https://auth.example/device",
                user_code="ABCD-EFGH",
                device_auth_id="openai-device-auth-id",
                interval=1,
            ),
            expires_at=int(llm_router.time.time() * 1000) + 60_000,
            epoch=llm_router._OPENAI_DEVICE_LOGIN_EPOCH,
        )
    )

    class FakeAuth:
        logged_out = False

        def logout(self):
            self.__class__.logged_out = True
            return True

    monkeypatch.setattr(llm_router, "_get_openai_subscription_auth", FakeAuth)

    response = client.post("/api/llm/subscription/openai/logout")

    assert response.status_code == 200
    assert response.json()["connected"] is False
    assert FakeAuth.logged_out is True
    assert llm_router._PENDING_OPENAI_DEVICE_LOGINS == {}
