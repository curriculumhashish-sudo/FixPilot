"""测试 profiles_router 端点。"""

import tempfile
import time
import warnings
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from openhands.agent_server import profiles_router as profiles_router_module
from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config
from openhands.agent_server.persistence import reset_stores
from openhands.sdk.llm import LLM, Message
from openhands.sdk.llm.auth.credentials import OAuthCredentials
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.llm.provider_connection_store import (
    ProviderConnection,
    ProviderConnectionStore,
)
from openhands.sdk.profiles import AgentProfileStore, OpenHandsAgentProfile
from openhands.sdk.utils.pydantic_secrets import REDACTED_SECRET_VALUE


@pytest.fixture
def temp_profiles_dir():
    """为配置文件创建临时目录。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        profiles_dir = Path(tmpdir) / "profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        yield profiles_dir


@pytest.fixture
def temp_agent_profiles_dir():
    """为智能体个配置文件创建临时目录（FK 存储）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = Path(tmpdir) / "agent-profiles"
        agent_dir.mkdir(parents=True, exist_ok=True)
        yield agent_dir


@pytest.fixture
def temp_settings_dir():
    """创建一个临时目录用于设置。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings_dir = Path(tmpdir) / "settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        yield settings_dir


@pytest.fixture
def client(temp_profiles_dir, temp_agent_profiles_dir, temp_settings_dir, monkeypatch):
    """使用隔离的配置文件/设置目录创建测试客户端，无需密码。"""
    # 重置存储单例以确保干净状态
    reset_stores()

    # 将持久化目录设置为环境变量
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(temp_settings_dir))

    # 通过将 secret_key 设置为 None 显式禁用密码
    config = Config(static_files_path=None, session_api_keys=[], secret_key=None)
    app = create_app(config)

    # Patch 应该使用临时目录AgentProfileStore 在删除/重命名时被 FK 锁住。 的 LLM profile
    #  store 与共享的提供者连接存储关联 ``load`` 解析提供者引用，并且路由自身的
    # ``get_provider_connections_store`` 返回同一个实例 CRUD 并且查看一个文件。
    #
    provider_store = ProviderConnectionStore(
        base_dir=temp_profiles_dir.parent / "provider-connections"
    )

    def make_llm_store():
        return LLMProfileStore(
            base_dir=temp_profiles_dir, provider_store=provider_store
        )

    with (
        patch(
            "openhands.agent_server.profiles_router.get_llm_profile_store",
            make_llm_store,
        ),
        patch(
            "openhands.agent_server.profiles_router.get_agent_profile_store",
            lambda: AgentProfileStore(base_dir=temp_agent_profiles_dir),
        ),
        patch(
            "openhands.agent_server.profiles_router.get_provider_connections_store",
            lambda config=None: provider_store,
        ),
        patch(
            "openhands.agent_server.settings_router.get_llm_profile_store",
            make_llm_store,
        ),
        patch(
            "openhands.agent_server.provider_connections_router.get_llm_profile_store",
            make_llm_store,
        ),
        patch(
            "openhands.agent_server.provider_connections_router."
            "get_provider_connections_store",
            lambda config=None: provider_store,
        ),
    ):
        yield TestClient(app)

    # 测试后重置存储
    reset_stores()


@pytest.fixture
def store(temp_profiles_dir):
    """使用临时目录创建配置文件存储。"""
    return LLMProfileStore(base_dir=temp_profiles_dir)


@pytest.fixture
def agent_store(temp_agent_profiles_dir):
    """创建支持 FK 防护的智能体-配置文件存储。"""
    return AgentProfileStore(base_dir=temp_agent_profiles_dir)


# ── FK Guard：删除/重命名引用的LLM配置文件────────────────────


def test_delete_referenced_llm_profile_returns_409(client, store, agent_store):
    """删除 AgentProfile 引用的 LLM 配置文件会返回 409 w/ 引用者。"""
    store.save("base-llm", LLM(model="gpt-4o"))
    agent_store.save(OpenHandsAgentProfile(name="agent-a", llm_profile_ref="base-llm"))

    response = client.delete("/api/profiles/base-llm")

    assert response.status_code == 409
    assert "agent-a" in response.json()["detail"]
    # LLM 配置文件保持不变。
    assert store.load("base-llm").model == "gpt-4o"


def test_delete_unreferenced_llm_profile_succeeds(client, store, agent_store):
    """AgentProfile 引用的 LLM 配置文件通常会删除。"""
    store.save("lonely", LLM(model="gpt-4o"))
    agent_store.save(OpenHandsAgentProfile(name="agent-a", llm_profile_ref="other-llm"))

    response = client.delete("/api/profiles/lonely")

    assert response.status_code == 200
    with pytest.raises(FileNotFoundError):
        store.load("lonely")


def test_rename_llm_profile_cascades_to_agent_refs(client, store, agent_store):
    """重命名 LLM 配置文件会重新引用 AgentProfile.llm_profile_ref。"""
    store.save("old-llm", LLM(model="gpt-4o"))
    agent_store.save(OpenHandsAgentProfile(name="agent-a", llm_profile_ref="old-llm"))

    response = client.post("/api/profiles/old-llm/rename", json={"new_name": "new-llm"})

    assert response.status_code == 200
    # 智能体配置文件的 FK 级联到新名称。
    assert agent_store.load("agent-a").llm_profile_ref == "new-llm"


def test_delete_referenced_llm_profile_via_json_alias_returns_409(
    client, store, agent_store
):
    """``.json`` 别名寻址相同的配置文件，因此应用 FK 保护。"""
    store.save("base-llm", LLM(model="gpt-4o"))
    agent_store.save(OpenHandsAgentProfile(name="agent-a", llm_profile_ref="base-llm"))

    response = client.delete("/api/profiles/base-llm.json")

    assert response.status_code == 409
    assert "agent-a" in response.json()["detail"]
    assert store.load("base-llm").model == "gpt-4o"


def test_delete_active_profile_via_json_alias_clears_active_profile(client, store):
    store.save("active-profile", LLM(model="gpt-4o"))
    assert client.post("/api/profiles/active-profile.json/activate").status_code == 200
    assert client.get("/api/settings").json()["active_profile"] == "active-profile"

    response = client.delete("/api/profiles/active-profile.json")

    assert response.status_code == 200
    assert client.get("/api/settings").json()["active_profile"] is None


def test_rename_llm_profile_via_json_alias_moves_refs_and_active(
    client, store, agent_store
):
    store.save("old-llm", LLM(model="gpt-4o"))
    agent_store.save(OpenHandsAgentProfile(name="agent-a", llm_profile_ref="old-llm"))
    assert client.post("/api/profiles/old-llm/activate").status_code == 200

    response = client.post(
        "/api/profiles/old-llm.json/rename", json={"new_name": "new-llm.json"}
    )

    assert response.status_code == 200
    assert agent_store.load("agent-a").llm_profile_ref == "new-llm"
    assert client.get("/api/settings").json()["active_profile"] == "new-llm"


# ── 简介简介──────────────────────────────────────────────────────────


def test_list_profiles_empty(client):
    """当不存在配置文件时，GET /api/profiles 返回空列表。"""
    response = client.get("/api/profiles")

    assert response.status_code == 200
    body = response.json()
    assert body["profiles"] == []


def test_list_profiles_returns_saved_profiles(client, store):
    """GET /api/profiles 返回所有已保存的配置文件以及型号信息。"""
    # 直接通过商店保存一些配置文件
    llm1 = LLM(model="gpt-4o")
    llm2 = LLM(model="claude-3-opus", api_key="sk-test-key")
    store.save("profile-a", llm1)
    store.save("profile-b", llm2, include_secrets=True)

    response = client.get("/api/profiles")

    assert response.status_code == 200
    body = response.json()
    profiles = body["profiles"]
    assert len(profiles) == 2

    names = {p["name"] for p in profiles}
    assert names == {"profile-a", "profile-b"}

    # 检查个人资料详细信息
    profile_a = next(p for p in profiles if p["name"] == "profile-a")
    assert profile_a["model"] == "gpt-4o"
    assert profile_a["api_key_set"] is False

    profile_b = next(p for p in profiles if p["name"] == "profile-b")
    assert profile_b["model"] == "claude-3-opus"
    assert profile_b["api_key_set"] is True


# ── 获取个人资料────────────────────────────────────────────────────────────


def test_provider_connection_key_shared_by_linked_profiles(client):
    """配置文件保持可运行，而提供者字段通过引用共享。"""
    connection = client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "Anthropic Work",
            "provider": "anthropic",
            "api_key": "sk-ant-old",
            "base_url": "https://api.anthropic.com",
        },
    )
    assert connection.status_code == 201
    connection_body = connection.json()
    connection_id = connection_body["id"]
    assert connection_body["api_key_set"] is True
    assert "api_key" not in connection_body
    assert "secret_name" not in connection_body

    for name, model in {
        "sonnet-4": "anthropic/claude-sonnet-4",
        "sonnet-5": "anthropic/claude-sonnet-5",
    }.items():
        response = client.post(
            f"/api/profiles/{name}",
            json={
                "llm": {
                    "model": model,
                    "provider_connection_id": connection_id,
                },
                "include_secrets": False,
            },
        )
        assert response.status_code == 201

    profiles = client.get("/api/profiles").json()["profiles"]
    linked = {p["name"]: p for p in profiles}
    assert linked["sonnet-4"]["provider_connection_id"] == connection_id
    assert linked["sonnet-4"]["api_key_set"] is True
    assert linked["sonnet-5"]["api_key_set"] is True

    detail = client.get("/api/profiles/sonnet-4").json()
    assert detail["config"]["api_key"] is None
    assert detail["config"]["base_url"] is None
    assert detail["api_key_set"] is True

    runtime = client.get(
        "/api/profiles/sonnet-4", headers={"X-Expose-Secrets": "plaintext"}
    ).json()["config"]
    assert runtime["api_key"] == "sk-ant-old"
    assert runtime["base_url"] == "https://api.anthropic.com"

    activated = client.post("/api/profiles/sonnet-4/activate")
    assert activated.status_code == 200
    settings = client.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()
    llm = settings["agent_settings"]["llm"]
    assert llm["model"] == "anthropic/claude-sonnet-4"
    assert llm["api_key"] == "sk-ant-old"
    assert llm["base_url"] == "https://api.anthropic.com"

    delete = client.delete(f"/api/llm/provider-connections/{connection_id}")
    assert delete.status_code == 409
    assert "referenced by LLM profile" in delete.json()["detail"]

    # 轮换共享密钥。 使用时读取：活动设置保留先前解析的密钥，直到配置文件再次激活（不会
    # 自动复制任何内容）。
    #
    rotated = client.patch(
        f"/api/llm/provider-connections/{connection_id}",
        json={"api_key": "sk-ant-new"},
    )
    assert rotated.status_code == 200
    settings = client.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()
    assert settings["agent_settings"]["llm"]["api_key"] == "sk-ant-old"

    runtime = client.get(
        "/api/profiles/sonnet-4", headers={"X-Expose-Secrets": "plaintext"}
    ).json()["config"]
    assert runtime["api_key"] == "sk-ant-new"

    # 重新激活会重新解析连接并应用轮换的密钥。
    activated = client.post("/api/profiles/sonnet-4/activate")
    assert activated.status_code == 200
    settings = client.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()
    assert settings["agent_settings"]["llm"]["api_key"] == "sk-ant-new"

    activated = client.post("/api/profiles/sonnet-5/activate")
    assert activated.status_code == 200
    settings = client.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()
    llm = settings["agent_settings"]["llm"]
    assert llm["model"] == "anthropic/claude-sonnet-5"
    assert llm["api_key"] == "sk-ant-new"


def test_settings_active_profile_resolves_provider_connection(client):
    connection_id = client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "OpenAI",
            "provider": "openai",
            "api_key": "sk-openai-provider",
        },
    ).json()["id"]
    client.post(
        "/api/profiles/gpt-provider",
        json={
            "llm": {
                "model": "openai/gpt-5.5",
                "provider_connection_id": connection_id,
            },
            "include_secrets": False,
        },
    )

    response = client.patch("/api/settings", json={"active_profile": "gpt-provider"})

    assert response.status_code == 200
    settings = client.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()
    llm = settings["agent_settings"]["llm"]
    assert llm["model"] == "openai/gpt-5.5"
    assert llm["api_key"] == "sk-openai-provider"


def test_provider_connection_delete_rejects_active_settings_reference(client):
    connection_id = client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "Anthropic Work",
            "provider": "anthropic",
            "api_key": "sk-ant-old",
        },
    ).json()["id"]
    client.post(
        "/api/profiles/temporary-provider-profile",
        json={
            "llm": {
                "model": "anthropic/claude-sonnet-4",
                "provider_connection_id": connection_id,
            },
            "include_secrets": False,
        },
    )
    assert (
        client.post("/api/profiles/temporary-provider-profile/activate").status_code
        == 200
    )
    assert client.delete("/api/profiles/temporary-provider-profile").status_code == 200

    delete = client.delete(f"/api/llm/provider-connections/{connection_id}")

    assert delete.status_code == 409
    assert "referenced by the active agent settings" in delete.json()["detail"]
    settings = client.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()
    assert settings["agent_settings"]["llm"]["api_key"] == "sk-ant-old"


def test_provider_connection_delete_ignores_acp_settings(client):
    connection_id = client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "Anthropic Work",
            "provider": "anthropic",
            "api_key": "sk-ant-old",
        },
    ).json()["id"]
    client.patch("/api/settings", json={"agent_settings_diff": {"agent_kind": "acp"}})

    with warnings.catch_warnings():
        warnings.filterwarnings("error", message="ACPAgentSettings.llm")
        delete = client.delete(f"/api/llm/provider-connections/{connection_id}")

    assert delete.status_code == 200


def test_provider_connection_rotation_not_copied_into_active_settings(client):
    """使用时读取：旋转密钥不会重写已解析的活动设置。

    活动的 ``agent_settings.llm`` 使密钥在激活时保持解析状态，直到配置文件再次激活 -
    旋转时不会自动复制任何内容。
    """
    connection_id = client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "Anthropic Work",
            "provider": "anthropic",
            "api_key": "sk-ant-old",
        },
    ).json()["id"]
    client.post(
        "/api/profiles/provider-profile",
        json={
            "llm": {
                "model": "anthropic/claude-sonnet-4",
                "provider_connection_id": connection_id,
            },
            "include_secrets": False,
        },
    )
    assert client.post("/api/profiles/provider-profile/activate").status_code == 200

    rotated = client.patch(
        f"/api/llm/provider-connections/{connection_id}",
        json={"api_key": "sk-ant-new"},
    )
    assert rotated.status_code == 200

    # 活动设置仍然保留激活时解析的密钥。
    settings = client.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()
    assert settings["agent_settings"]["llm"]["api_key"] == "sk-ant-old"

    # 重新激活重新解析并拾取旋转的密钥。
    assert client.post("/api/profiles/provider-profile/activate").status_code == 200
    settings = client.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()
    assert settings["agent_settings"]["llm"]["api_key"] == "sk-ant-new"


def test_provider_connection_base_url_authoritative_on_activation(client):
    """连接的 ``base_url`` 在激活时获胜，包括清除时。"""
    connection_id = client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "Proxy",
            "provider": "custom",
            "api_key": "sk-provider",
            "base_url": "https://old.example",
        },
    ).json()["id"]
    client.post(
        "/api/profiles/provider-profile",
        json={
            "llm": {
                "model": "openai/gpt-5.5",
                "base_url": "https://profile.example",
                "provider_connection_id": connection_id,
            },
            "include_secrets": False,
        },
    )
    assert client.post("/api/profiles/provider-profile/activate").status_code == 200
    settings = client.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()
    # 连接 base_url 胜过配置文件自己的连接。
    assert settings["agent_settings"]["llm"]["base_url"] == "https://old.example"

    updated = client.patch(
        f"/api/llm/provider-connections/{connection_id}",
        json={"base_url": None},
    )
    assert updated.status_code == 200
    assert updated.json()["base_url"] is None

    # base_url是权威的，包括None：重新激活会清除它。
    assert client.post("/api/profiles/provider-profile/activate").status_code == 200
    settings = client.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()
    assert settings["agent_settings"]["llm"]["base_url"] is None


def test_activate_profile_with_dangling_provider_connection_fails(client):
    """连接不再存在的配置文件在激活时会大声失败。"""
    connection_id = client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "Anthropic Work",
            "provider": "anthropic",
            "api_key": "sk-ant-old",
        },
    ).json()["id"]
    client.post(
        "/api/profiles/provider-profile",
        json={
            "llm": {
                "model": "anthropic/claude-sonnet-4",
                "provider_connection_id": connection_id,
            },
            "include_secrets": False,
        },
    )
    # 删除配置文件，以便连接不被引用并且可以被删除，然后重新创建配置文件以留下悬空的提供
    # 程序引用。
    #
    assert client.delete("/api/profiles/provider-profile").status_code == 200
    assert (
        client.delete(f"/api/llm/provider-connections/{connection_id}").status_code
        == 200
    )
    client.post(
        "/api/profiles/provider-profile",
        json={
            "llm": {
                "model": "anthropic/claude-sonnet-4",
                "provider_connection_id": connection_id,
            },
            "include_secrets": False,
        },
    )

    activated = client.post("/api/profiles/provider-profile/activate")

    assert activated.status_code == 422
    assert connection_id in activated.json()["detail"]


def test_provider_connection_rejects_extra_headers(client):
    response = client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "Proxy",
            "provider": "custom",
            "api_key": "sk-provider",
            "extra_headers": {"Authorization": "Bearer proxy-secret"},
        },
    )

    assert response.status_code == 422


def test_get_profile_returns_config(client, store):
    """GET /api/profiles/{name} 返回配置文件配置，api_key 为空。"""
    llm = LLM(model="gpt-4o", api_key="sk-secret-key", temperature=0.7)
    store.save("my-profile", llm, include_secrets=True)

    response = client.get("/api/profiles/my-profile")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "my-profile"
    assert body["config"]["model"] == "gpt-4o"
    assert body["config"]["temperature"] == 0.7
    assert body["config"]["api_key"] is None  # 从未暴露
    assert body["api_key_set"] is True


def test_get_profile_not_found(client):
    """GET /api/profiles/{name} 对于不存在的配置文件返回 404。"""
    response = client.get("/api/profiles/nonexistent")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_profile_invalid_name(client):
    """GET /api/profiles/{name} 拒绝无效的配置文件名称。"""
    # 路径遍历尝试 - 可能是 404（解码并视为未找到）或 422（验证错误），具体取决于路径的
    # 解析方式
    #
    response = client.get("/api/profiles/..%2Fetc%2Fpasswd")
    assert response.status_code in (404, 422)

    # 隐藏文件尝试
    response = client.get("/api/profiles/.hidden")
    assert response.status_code in (400, 404, 422)


# ── 保存个人资料────────────────────────────────────────────────────────────


def test_save_profile_creates_new(client, store):
    """POST /api/profiles/{name} 创建一个新的配置文件。"""
    response = client.post(
        "/api/profiles/new-profile",
        json={
            "llm": {"model": "gpt-4o", "api_key": "sk-test-key"},
            "include_secrets": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "new-profile"
    assert "saved" in body["message"].lower()

    # 验证配置文件已保存
    loaded = store.load("new-profile")
    assert loaded.model == "gpt-4o"


def test_save_profile_overwrites_existing(client, store):
    """POST /api/profiles/{name} 覆盖现有配置文件。"""
    # 保存初始配置文件
    llm1 = LLM(model="gpt-4o")
    store.save("existing", llm1)

    # 用新配置覆盖
    response = client.post(
        "/api/profiles/existing",
        json={"llm": {"model": "claude-3-opus"}},
    )

    assert response.status_code == 201

    # 验证覆盖
    loaded = store.load("existing")
    assert loaded.model == "claude-3-opus"


def test_save_profile_without_secrets(client, store):
    """POST /api/profiles/{name} 且 include_secrets=False 省略 api_key。"""
    response = client.post(
        "/api/profiles/no-secrets",
        json={
            "llm": {"model": "gpt-4o", "api_key": "sk-should-not-save"},
            "include_secrets": False,
        },
    )

    assert response.status_code == 201

    # 验证 api_key 未保存
    loaded = store.load("no-secrets")
    assert loaded.api_key is None or loaded.api_key.get_secret_value() == ""


def test_save_profile_invalid_name(client):
    """POST /api/profiles/{name} 对于无效名称返回 422。"""
    response = client.post(
        "/api/profiles/invalid/name",
        json={"llm": {"model": "gpt-4o"}},
    )
    # 应在路径验证处失败或被视为不同的路线
    assert response.status_code in (404, 422)


# ── 删除个人资料──────────────────────────────────────────────────────────


def test_delete_profile_removes_existing(client, store):
    """DELETE /api/profiles/{name} 删除配置文件。"""
    llm = LLM(model="gpt-4o")
    store.save("to-delete", llm)

    response = client.delete("/api/profiles/to-delete")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "to-delete"
    assert "deleted" in body["message"].lower()

    # 验证已删除
    with pytest.raises(FileNotFoundError):
        store.load("to-delete")


def test_delete_profile_idempotent(client):
    """即使对于不存在的配置文件，DELETE /api/profiles/{name} 也会成功。"""
    response = client.delete("/api/profiles/nonexistent")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "nonexistent"


def test_delete_active_profile_clears_active_profile(client, store):
    """删除活动配置文件会清除设置中的 active_profile。"""
    llm = LLM(model="gpt-4o")
    store.save("active-profile", llm)
    store.save("other-profile", llm)
    activate_response = client.post("/api/profiles/active-profile/activate")
    assert activate_response.status_code == 200
    assert client.get("/api/settings").json()["active_profile"] == "active-profile"

    response = client.delete("/api/profiles/active-profile")

    assert response.status_code == 200
    settings_response = client.get("/api/settings")
    assert settings_response.status_code == 200
    assert settings_response.json()["active_profile"] is None

    profiles_response = client.get("/api/profiles")
    assert profiles_response.status_code == 200
    body = profiles_response.json()
    assert body["active_profile"] is None
    assert {profile["name"] for profile in body["profiles"]} == {"other-profile"}


# ── 重命名个人资料──────────────────────────────────────────────────────────


def test_rename_profile_success(client, store):
    """POST /api/profiles/{name}/rename 重命名配置文件。"""
    llm = LLM(model="gpt-4o", api_key="sk-secret")
    store.save("old-name", llm, include_secrets=True)

    response = client.post(
        "/api/profiles/old-name/rename",
        json={"new_name": "new-name"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "new-name"
    assert "renamed" in body["message"].lower()

    # 验证旧的已消失，新的是否存在且具有相同的配置
    with pytest.raises(FileNotFoundError):
        store.load("old-name")

    loaded = store.load("new-name")
    assert loaded.model == "gpt-4o"


def test_rename_profile_preserves_secrets(client, store):
    """POST /api/profiles/{name}/rename 保留 api_key。"""
    llm = LLM(model="gpt-4o", api_key="sk-secret-preserve")
    store.save("with-secret", llm, include_secrets=True)

    response = client.post(
        "/api/profiles/with-secret/rename",
        json={"new_name": "renamed-secret"},
    )

    assert response.status_code == 200

    # 验证机密已保留
    loaded = store.load("renamed-secret")
    assert loaded.api_key is not None
    assert loaded.api_key.get_secret_value() == "sk-secret-preserve"


def test_rename_profile_not_found(client):
    """POST /api/profiles/{name}/rename 对于不存在的配置文件返回 404。"""
    response = client.post(
        "/api/profiles/nonexistent/rename",
        json={"new_name": "new-name"},
    )

    assert response.status_code == 404


def test_rename_profile_conflict(client, store):
    """如果 new_name 存在，POST /api/profiles/{name}/rename 返回 409。"""
    llm1 = LLM(model="gpt-4o")
    llm2 = LLM(model="claude-3-opus")
    store.save("source", llm1)
    store.save("target", llm2)

    response = client.post(
        "/api/profiles/source/rename",
        json={"new_name": "target"},
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


def test_rename_profile_same_name(client, store):
    """POST /api/profiles/{name}/rename 具有相同的名称是无操作。"""
    llm = LLM(model="gpt-4o")
    store.save("same-name", llm)

    response = client.post(
        "/api/profiles/same-name/rename",
        json={"new_name": "same-name"},
    )

    assert response.status_code == 200
    assert "unchanged" in response.json()["message"].lower()


def test_rename_profile_same_name_missing_returns_404(client):
    """丢失的配置文件的同名重命名必须返回 404，而不是 200。"""
    response = client.post(
        "/api/profiles/ghost/rename",
        json={"new_name": "ghost"},
    )
    assert response.status_code == 404


def test_rename_profile_invalid_new_name(client, store):
    """对于无效的 new_name，POST /api/profiles/{name}/rename 返回 422。"""
    llm = LLM(model="gpt-4o")
    store.save("valid-name", llm)

    response = client.post(
        "/api/profiles/valid-name/rename",
        json={"new_name": "../etc/passwd"},
    )

    assert response.status_code == 422


# ── 个人资料名称验证 ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "simple",
        "with-dash",
        "with_underscore",
        "with.dot",
        "MixedCase123",
        "a" * 64,  # 最大长度
    ],
)
def test_valid_profile_names(client, name):
    """接受有效的配置文件名称。"""
    response = client.post(
        f"/api/profiles/{name}",
        json={"llm": {"model": "gpt-4o"}},
    )
    assert response.status_code == 201


def test_invalid_profile_name_too_long(client):
    """太长的配置文件名称将被拒绝。"""
    name = "a" * 65  # 超过 64 个字符限制
    response = client.post(
        f"/api/profiles/{name}",
        json={"llm": {"model": "gpt-4o"}},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("name", [".leading-dot", "-leading-dash", "_leading_under"])
def test_invalid_profile_name_leading_non_alnum(client, name):
    """配置文件名称必须以字母数字字符开头。"""
    response = client.post(
        f"/api/profiles/{name}",
        json={"llm": {"model": "gpt-4o"}},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("name", ["name@symbol", "name$dollar", "name space"])
def test_invalid_profile_name_special_chars(client, name):
    """包含不允许字符的配置文件名称将被拒绝。"""
    response = client.post(
        f"/api/profiles/{name}",
        json={"llm": {"model": "gpt-4o"}},
    )
    assert response.status_code == 422


# ── 档案限制────────────────────────────────────────────────────────────


def test_save_profile_at_limit_returns_409(client, store, monkeypatch):
    """当到达 MAX_PROFILES 时，POST /api/profiles/{name} 返回 409。"""
    monkeypatch.setattr(profiles_router_module, "MAX_PROFILES", 2)

    store.save("first", LLM(model="gpt-4o"))
    store.save("second", LLM(model="gpt-4o"))

    response = client.post(
        "/api/profiles/third",
        json={"llm": {"model": "gpt-4o"}},
    )
    assert response.status_code == 409
    assert "limit" in response.json()["detail"].lower()


def test_save_profile_at_limit_overwrite_allowed(client, store, monkeypatch):
    """即使有限制，也允许覆盖现有配置文件。"""
    monkeypatch.setattr(profiles_router_module, "MAX_PROFILES", 2)

    store.save("first", LLM(model="gpt-4o"))
    store.save("second", LLM(model="gpt-4o"))

    response = client.post(
        "/api/profiles/first",
        json={"llm": {"model": "claude-3-opus"}},
    )
    assert response.status_code == 201
    assert store.load("first").model == "claude-3-opus"


# ── 储存错误 → HTTP ────────────────────────────────────────────────────


def test_list_profiles_timeout_returns_503(client, monkeypatch):
    """列表端点表面 TimeoutError 503。"""

    def boom(self):
        raise TimeoutError("locked")

    monkeypatch.setattr(LLMProfileStore, "list_summaries", boom)

    response = client.get("/api/profiles")
    assert response.status_code == 503


def test_get_profile_timeout_returns_503(client, store, monkeypatch):
    """获取端点曲面 TimeoutError 作为 503。"""
    store.save("present", LLM(model="gpt-4o"))

    def boom(self, name, *, cipher=None, resolve_provider=True):
        raise TimeoutError("locked")

    monkeypatch.setattr(LLMProfileStore, "load", boom)

    response = client.get("/api/profiles/present")
    assert response.status_code == 503


def test_delete_profile_invalid_internal_name_returns_400(client, store, monkeypatch):
    """如果 store 引发 ValueError，则删除响应 400 而不是 500。"""

    def boom(self, name):
        raise ValueError("Invalid profile name: 'x'.")

    monkeypatch.setattr(LLMProfileStore, "delete", boom)

    response = client.delete("/api/profiles/some-name")
    assert response.status_code == 400


def test_list_profiles_skips_corrupted(client, temp_profiles_dir):
    """损坏的配置文件将被跳过，不会返回。"""
    (temp_profiles_dir / "good.json").write_text('{"model": "gpt-4o"}')
    (temp_profiles_dir / "bad.json").write_text("{ not valid json")

    response = client.get("/api/profiles")
    assert response.status_code == 200

    names = {p["name"] for p in response.json()["profiles"]}
    assert names == {"good"}


def test_list_profiles_api_key_set_for_redacted(client, store):
    """保存的配置文件没有机密报告 api_key_set=False。"""
    llm = LLM(model="gpt-4o", api_key="sk-secret-not-saved")
    store.save("redacted", llm, include_secrets=False)

    response = client.get("/api/profiles")
    assert response.status_code == 200

    profile = next(p for p in response.json()["profiles"] if p["name"] == "redacted")
    assert profile["api_key_set"] is False


# ── 畸形尸体────────────────────────────────────────────────────────


def test_save_profile_missing_llm_field(client):
    """如果没有必需的“llm”字段，则保存会返回 422。"""
    response = client.post("/api/profiles/missing", json={})
    assert response.status_code == 422


def test_save_profile_wrong_type_for_llm(client):
    """使用“llm”保存为非字典会返回 422。"""
    response = client.post(
        "/api/profiles/bad-llm",
        json={"llm": "not-an-object"},
    )
    assert response.status_code == 422


def test_rename_profile_missing_new_name(client, store):
    """如果没有必需的“new_name”字段重命名将返回 422。"""
    store.save("source", LLM(model="gpt-4o"))
    response = client.post("/api/profiles/source/rename", json={})
    assert response.status_code == 422


def test_rename_profile_empty_new_name(client, store):
    """使用空“new_name”重命名会返回 422。"""
    store.save("source", LLM(model="gpt-4o"))
    response = client.post("/api/profiles/source/rename", json={"new_name": ""})
    assert response.status_code == 422


def test_get_profile_corrupted_returns_400(client, temp_profiles_dir):
    """损坏的配置文件 JSON 从负载端点返回 400。"""
    (temp_profiles_dir / "broken.json").write_text("{ not valid json")
    response = client.get("/api/profiles/broken")
    assert response.status_code == 400
    assert "broken" in response.json()["detail"].lower()


def test_save_profile_timeout_returns_503(client, monkeypatch):
    """将端点个曲面 TimeoutError 保存为 503。"""

    def boom(self, name, llm, include_secrets=False, *, cipher=None, max_profiles=None):
        raise TimeoutError("locked")

    monkeypatch.setattr(LLMProfileStore, "save", boom)

    response = client.post(
        "/api/profiles/anything",
        json={"llm": {"model": "gpt-4o"}},
    )
    assert response.status_code == 503


def test_rename_profile_timeout_returns_503(client, store, monkeypatch):
    """将端点曲面 TimeoutError 重命名为 503。"""
    store.save("src", LLM(model="gpt-4o"))

    def boom(self, old, new):
        raise TimeoutError("locked")

    monkeypatch.setattr(LLMProfileStore, "rename", boom)

    response = client.post("/api/profiles/src/rename", json={"new_name": "dst"})
    assert response.status_code == 503


def test_delete_profile_timeout_returns_503(client, store, monkeypatch):
    """删除端点个曲面 TimeoutError 作为 503。"""
    store.save("present", LLM(model="gpt-4o"))

    def boom(self, name):
        raise TimeoutError("locked")

    monkeypatch.setattr(LLMProfileStore, "delete", boom)

    response = client.delete("/api/profiles/present")
    assert response.status_code == 503


def test_whitespace_api_key_reports_not_set(client, store):
    """仅包含空格的配置文件 api_key 报告 api_key_set=False。"""
    # 使用真实密钥保存，然后在磁盘文件中插入空格。
    store.save("ws", LLM(model="gpt-4o", api_key="placeholder"), include_secrets=True)
    profile_path = store.base_dir / "ws.json"
    profile_path.write_text('{"model": "gpt-4o", "api_key": "   "}')

    response = client.get("/api/profiles")
    profile = next(p for p in response.json()["profiles"] if p["name"] == "ws")
    assert profile["api_key_set"] is False

    detail = client.get("/api/profiles/ws").json()
    assert detail["api_key_set"] is False


def test_save_at_limit_does_not_write_partial_state(client, store, monkeypatch):
    """当达到限制时，不应出现任何配置文件（或 .tmp 剩余文件）。"""
    monkeypatch.setattr(profiles_router_module, "MAX_PROFILES", 1)

    store.save("first", LLM(model="gpt-4o"))
    files_before = sorted(p.name for p in store.base_dir.iterdir())

    response = client.post(
        "/api/profiles/second",
        json={"llm": {"model": "gpt-4o"}},
    )
    assert response.status_code == 409

    files_after = sorted(p.name for p in store.base_dir.iterdir())
    assert files_after == files_before  # 没有新文件，没有 .tmp 剩余


def test_get_profile_does_not_expose_api_key(client, store):
    """即使保存了 api_key，GET 响应也会将其清空。"""
    llm = LLM(model="gpt-4o", api_key="sk-very-secret")
    store.save("secret-profile", llm, include_secrets=True)

    response = client.get("/api/profiles/secret-profile")
    assert response.status_code == 200
    body = response.json()
    assert body["config"]["api_key"] is None
    assert body["api_key_set"] is True
    # 并且机密字符串本身永远不会出现在响应中
    assert "sk-very-secret" not in response.text


# ── 密码加密测试──────────────────────────────────────────────────


@pytest.fixture
def secret_key():
    """生成用于密码加密的机密密钥。"""
    from base64 import urlsafe_b64encode

    return urlsafe_b64encode(b"a" * 32).decode("ascii")


@pytest.fixture
def client_with_cipher(
    temp_profiles_dir,
    temp_agent_profiles_dir,
    temp_settings_dir,
    secret_key,
    monkeypatch,
):
    """创建配置了密码的测试客户端。"""
    from pydantic import SecretStr

    # 重置存储单例以确保干净状态
    reset_stores()

    # 将持久化目录设置为环境变量
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(temp_settings_dir))

    config = Config(
        static_files_path=None,
        session_api_keys=[],
        secret_key=SecretStr(secret_key),
    )
    app = create_app(config)

    with (
        patch(
            "openhands.agent_server.profiles_router.get_llm_profile_store",
            lambda: LLMProfileStore(base_dir=temp_profiles_dir),
        ),
        patch(
            "openhands.agent_server.profiles_router.get_agent_profile_store",
            lambda: AgentProfileStore(base_dir=temp_agent_profiles_dir),
        ),
    ):
        yield TestClient(app)

    # 测试后重置存储
    reset_stores()


@pytest.fixture
def cipher(secret_key):
    """创建一个密码实例用于测试。"""
    from openhands.sdk.utils.cipher import Cipher

    return Cipher(secret_key)


def test_get_profile_invalid_expose_secrets_header_returns_400(client_with_cipher):
    """具有无效 X-Expose-机密标头的 GET 返回 400。"""
    response = client_with_cipher.get(
        "/api/profiles/any", headers={"X-Expose-Secrets": "invalid-value"}
    )
    assert response.status_code == 400
    assert "Invalid X-Expose-Secrets" in response.json()["detail"]


def test_get_profile_with_plaintext_header_exposes_secrets(
    client_with_cipher, store, cipher
):
    """GET 与 X-Expose-机密：明文返回原始机密。"""
    llm = LLM(model="gpt-4o", api_key="sk-test-secret-key")
    store.save("with-secret", llm, include_secrets=True, cipher=cipher)

    response = client_with_cipher.get(
        "/api/profiles/with-secret", headers={"X-Expose-Secrets": "plaintext"}
    )

    assert response.status_code == 200
    body = response.json()
    # 机密应该暴露
    assert body["config"]["api_key"] == "sk-test-secret-key"


@pytest.mark.parametrize("expose_mode", [None, "encrypted", "plaintext"])
def test_linked_profile_with_encrypted_provider_credentials(
    client_with_cipher, store, temp_profiles_dir, cipher, expose_mode
):
    """只有运行时读取才能解析提供者的加密地址 REST 凭据。"""
    provider_store = ProviderConnectionStore(
        base_dir=temp_profiles_dir.parent / "provider-connections"
    )
    provider_store.create(
        ProviderConnection(
            id="automation-provider",
            display_name="Automation provider",
            api_key=SecretStr("sk-linked-secret"),
            base_url="https://provider.example/v1",
            created_at=1,
            updated_at=1,
        ),
        cipher=cipher,
    )
    store.save(
        "linked-profile",
        LLM(model="gpt-4o", provider_connection_id="automation-provider"),
        cipher=cipher,
    )

    response = client_with_cipher.get(
        "/api/profiles/linked-profile",
        headers={"X-Expose-Secrets": expose_mode} if expose_mode else {},
    )

    assert response.status_code == 200
    config = response.json()["config"]
    assert config["provider_connection_id"] == "automation-provider"
    if expose_mode == "plaintext":
        assert config["api_key"] == "sk-linked-secret"
        assert config["base_url"] == "https://provider.example/v1"
    else:
        assert config["api_key"] is None
        assert config["base_url"] is None
    # 读取运行时凭据不得将它们复制到存储的配置文件中。
    stored = store.load("linked-profile", cipher=cipher, resolve_provider=False)
    assert stored.api_key is None
    assert stored.base_url is None


def test_get_profile_with_encrypted_header_encrypts_secrets(
    client_with_cipher, store, cipher
):
    """GET 与 X-Expose-机密：加密返回密码加密的机密。"""
    llm = LLM(model="gpt-4o", api_key="sk-test-secret-key")
    store.save("with-secret", llm, include_secrets=True, cipher=cipher)

    response = client_with_cipher.get(
        "/api/profiles/with-secret", headers={"X-Expose-Secrets": "encrypted"}
    )

    assert response.status_code == 200
    body = response.json()
    api_key = body["config"]["api_key"]
    # 应该加密（不是明文，不是None）
    assert api_key != "sk-test-secret-key"
    assert api_key is not None
    # 应该可以解密
    decrypted = cipher.decrypt(api_key)
    assert decrypted is not None
    assert decrypted.get_secret_value() == "sk-test-secret-key"


def test_get_profile_with_true_header_treats_as_encrypted(
    client_with_cipher, store, cipher
):
    """GET 与 X-Expose-机密：True 视为加密（安全）。"""
    llm = LLM(model="gpt-4o", api_key="sk-test-secret-key")
    store.save("with-secret", llm, include_secrets=True, cipher=cipher)

    response = client_with_cipher.get(
        "/api/profiles/with-secret", headers={"X-Expose-Secrets": "true"}
    )

    assert response.status_code == 200
    body = response.json()
    api_key = body["config"]["api_key"]
    # 应该加密（不是明文）
    assert api_key != "sk-test-secret-key"
    # 应该可以解密
    decrypted = cipher.decrypt(api_key)
    assert decrypted is not None
    assert decrypted.get_secret_value() == "sk-test-secret-key"


def test_save_profile_with_cipher_encrypts_at_rest(
    client_with_cipher, temp_profiles_dir, cipher
):
    """配置了密码的 POST 在 REST 处加密机密。"""
    import json

    response = client_with_cipher.post(
        "/api/profiles/encrypted-profile",
        json={
            "llm": {"model": "gpt-4o", "api_key": "sk-test-secret"},
            "include_secrets": True,
        },
    )

    assert response.status_code == 201

    # 读取原始文件以验证加密
    profile_path = temp_profiles_dir / "encrypted-profile.json"
    data = json.loads(profile_path.read_text())
    # api_key 应该加密，而不是明文
    assert data["api_key"] != "sk-test-secret"
    # 应该可以解密
    decrypted = cipher.decrypt(data["api_key"])
    assert decrypted is not None
    assert decrypted.get_secret_value() == "sk-test-secret"


def test_encrypted_roundtrip_workflow(client_with_cipher, store, cipher):
    """客户端可以GET加密、修改并重新提交加密的机密。"""
    llm = LLM(model="gpt-4o", api_key="sk-original-secret")
    store.save("roundtrip", llm, include_secrets=True, cipher=cipher)

    get_response = client_with_cipher.get(
        "/api/profiles/roundtrip", headers={"X-Expose-Secrets": "encrypted"}
    )
    assert get_response.status_code == 200
    encrypted_api_key = get_response.json()["config"]["api_key"]

    update_response = client_with_cipher.post(
        "/api/profiles/roundtrip",
        json={
            "llm": {"model": "gpt-4o-mini", "api_key": encrypted_api_key},
            "include_secrets": True,
        },
    )
    assert update_response.status_code == 201

    get_final = client_with_cipher.get(
        "/api/profiles/roundtrip", headers={"X-Expose-Secrets": "plaintext"}
    )
    assert get_final.status_code == 200
    body = get_final.json()
    assert body["config"]["api_key"] == "sk-original-secret"
    assert body["config"]["model"] == "gpt-4o-mini"


def test_save_plaintext_secret_with_cipher_encrypts_at_rest(
    client_with_cipher, temp_profiles_dir, cipher
):
    """首次保存路径：明文输入+密码配置→加密到磁盘。"""
    import json

    response = client_with_cipher.post(
        "/api/profiles/first-save",
        json={
            "llm": {"model": "gpt-4o", "api_key": "sk-plaintext-input"},
            "include_secrets": True,
        },
    )
    assert response.status_code == 201

    profile_path = temp_profiles_dir / "first-save.json"
    data = json.loads(profile_path.read_text())
    assert data["api_key"] != "sk-plaintext-input"
    decrypted = cipher.decrypt(data["api_key"])
    assert decrypted is not None
    assert decrypted.get_secret_value() == "sk-plaintext-input"


def test_get_profile_encrypted_without_cipher_returns_503(client, store):
    """GET 与 X-Expose-机密：在未配置密码的情况下进行加密返回 503。"""
    llm = LLM(model="gpt-4o", api_key="sk-test-secret")
    store.save("no-cipher", llm, include_secrets=True)

    response = client.get(
        "/api/profiles/no-cipher", headers={"X-Expose-Secrets": "encrypted"}
    )

    assert response.status_code == 503
    body = response.json()
    # 503错误使用“异常”字段来避免泄露内部细节
    error_text = body.get("detail", "") + body.get("exception", "")
    assert "OH_SECRET_KEY" in error_text


def test_save_without_cipher_stores_plaintext_for_backward_compat(client, store):
    """未配置密码的 POST 存储明文 (向后兼容)。"""
    import json

    response = client.post(
        "/api/profiles/plaintext-profile",
        json={
            "llm": {"model": "gpt-4o", "api_key": "sk-plain-secret"},
            "include_secrets": True,
        },
    )

    assert response.status_code == 201

    # 读取原始文件 - 应该是纯文本
    profile_path = store.base_dir / "plaintext-profile.json"
    data = json.loads(profile_path.read_text())
    assert data["api_key"] == "sk-plain-secret"


# ── 主动档案测试──────────────────────────────────────────────────────


def test_list_profiles_includes_active_profile_null_by_default(client):
    """当 None 处于活动状态时，GET /api/profiles 将 active_profile 返回为 null。"""
    response = client.get("/api/profiles")

    assert response.status_code == 200
    body = response.json()
    assert "active_profile" in body
    assert body["active_profile"] is None


def test_activate_profile_success(client, store):
    """POST /api/profiles/{name}/activate 激活配置文件。"""
    llm = LLM(model="gpt-4o", api_key="sk-test-key")
    store.save("my-profile", llm, include_secrets=True)

    response = client.post("/api/profiles/my-profile/activate")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "my-profile"
    assert "activated" in body["message"].lower()
    assert body["llm_applied"] is True


def test_activate_profile_updates_active_profile(client, store):
    """POST /api/profiles/{name}/activate 更新 active_profile 字段。"""
    llm = LLM(model="gpt-4o")
    store.save("first-profile", llm)
    store.save("second-profile", llm)

    # 激活第一个配置文件
    client.post("/api/profiles/first-profile/activate")
    list_response = client.get("/api/profiles")
    assert list_response.json()["active_profile"] == "first-profile"

    # 激活第二个配置文件
    client.post("/api/profiles/second-profile/activate")
    list_response = client.get("/api/profiles")
    assert list_response.json()["active_profile"] == "second-profile"


def test_activate_profile_applies_llm_config(client, store):
    """POST /api/profiles/{name}/activate 应用配置文件的 LLM 配置。"""
    llm = LLM(model="claude-3-opus", temperature=0.8)
    store.save("claude-profile", llm)

    client.post("/api/profiles/claude-profile/activate")

    # 验证设置已更新
    settings_response = client.get("/api/settings")
    assert settings_response.status_code == 200
    agent_settings = settings_response.json()["agent_settings"]
    assert agent_settings["llm"]["model"] == "claude-3-opus"
    assert agent_settings["llm"]["temperature"] == 0.8


def test_activate_profile_replaces_stale_llm_extra_body(client, store):
    """激活配置文件不应保留旧 LLM 中的 extra_body。"""
    response = client.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "llm": {
                    "model": "openai/qwen3",
                    "litellm_extra_body": {"enable_thinking": True, "store": False},
                }
            }
        },
    )
    assert response.status_code == 200

    llm = LLM(
        model="openai/target-model",
        base_url="https://api.example.test/v1",
        litellm_extra_body={},
    )
    store.save("target-profile", llm)

    response = client.post("/api/profiles/target-profile/activate")

    assert response.status_code == 200
    settings_response = client.get("/api/settings")
    assert settings_response.status_code == 200
    llm_settings = settings_response.json()["agent_settings"]["llm"]
    assert llm_settings["model"] == "openai/target-model"
    assert llm_settings["litellm_extra_body"] == {}


def test_activate_profile_not_found(client):
    """POST /api/profiles/{name}/activate 对于不存在的配置文件返回 404。"""
    response = client.post("/api/profiles/nonexistent/activate")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_activate_profile_with_api_key(client, store):
    """POST /api/profiles/{name}/activate 应用 api_key 的配置文件。"""
    llm = LLM(model="gpt-4o", api_key="sk-profile-secret")
    store.save("with-key", llm, include_secrets=True)

    client.post("/api/profiles/with-key/activate")

    # 验证已应用 API 键（检查 llm_api_key_is_set）
    settings_response = client.get("/api/settings")
    assert settings_response.status_code == 200
    assert settings_response.json()["llm_api_key_is_set"] is True


def test_activate_profile_leaves_acp_settings_without_llm(client, store):
    store.save(
        "with-key",
        LLM(model="gpt-4o", api_key="sk-profile-secret"),
        include_secrets=True,
    )
    client.patch("/api/settings", json={"agent_settings_diff": {"agent_kind": "acp"}})

    response = client.post("/api/profiles/with-key/activate")

    assert response.status_code == 200
    assert response.json()["llm_applied"] is False
    settings = client.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()
    assert settings["active_profile"] == "with-key"
    assert "llm" not in settings["agent_settings"]
    assert settings["llm_api_key_is_set"] is False


def test_list_profiles_shows_active_after_activation(client, store):
    """GET /api/profiles 显示激活后正确的 active_profile。"""
    llm = LLM(model="gpt-4o")
    store.save("profile-a", llm)
    store.save("profile-b", llm)

    # 最初没有活动配置文件
    response = client.get("/api/profiles")
    assert response.json()["active_profile"] is None

    # 激活配置文件-a
    client.post("/api/profiles/profile-a/activate")
    response = client.get("/api/profiles")
    body = response.json()
    assert body["active_profile"] == "profile-a"

    # 验证配置文件-a 是否在列表中
    names = {p["name"] for p in body["profiles"]}
    assert "profile-a" in names
    assert "profile-b" in names


def test_activate_profile_invalid_name(client):
    """POST /api/profiles/{name}/activate 拒绝无效的配置文件名称。"""
    # 路径遍历尝试
    response = client.post("/api/profiles/..%2Fetc%2Fpasswd/activate")
    assert response.status_code in (404, 422)

    # 隐藏文件尝试
    response = client.post("/api/profiles/.hidden/activate")
    assert response.status_code in (400, 404, 422)


# ── 重命名活动配置文件测试 ────────────────────────────────────────────


def test_rename_active_profile_updates_active_profile(client, store):
    """重命名活动配置文件应更新设置中的 active_profile。"""
    # 创建并激活配置文件
    llm = LLM(model="gpt-4o", api_key=SecretStr("sk-test"))
    store.save("my-profile", llm)
    client.post("/api/profiles/my-profile/activate")

    # 验证它是否处于活动状态
    response = client.get("/api/profiles")
    assert response.json()["active_profile"] == "my-profile"

    # 重命名活动配置文件
    response = client.post(
        "/api/profiles/my-profile/rename",
        json={"new_name": "renamed-profile"},
    )
    assert response.status_code == 200

    # 验证 active_profile 已更新为新名称
    response = client.get("/api/profiles")
    assert response.status_code == 200
    body = response.json()
    assert body["active_profile"] == "renamed-profile"
    assert len(body["profiles"]) == 1
    assert body["profiles"][0]["name"] == "renamed-profile"


def test_rename_inactive_profile_preserves_active_profile(client, store):
    """重命名非活动配置文件不应更改 active_profile。"""
    # 创建两个配置文件
    llm1 = LLM(model="gpt-4o", api_key=SecretStr("sk-test1"))
    llm2 = LLM(model="claude-3-opus", api_key=SecretStr("sk-test2"))
    store.save("profile-a", llm1)
    store.save("profile-b", llm2)

    # 激活配置文件-a
    client.post("/api/profiles/profile-a/activate")

    # 重命名配置文件-b（不是活动的配置文件）
    response = client.post(
        "/api/profiles/profile-b/rename",
        json={"new_name": "profile-b-renamed"},
    )
    assert response.status_code == 200

    # 验证 active_profile 仍然是配置文件-a
    response = client.get("/api/profiles")
    assert response.json()["active_profile"] == "profile-a"


# ── 自动创建配置文件测试 ──────────────────────────────────────────────


def test_list_profiles_does_not_auto_create_from_settings(client):
    """没有配置文件的已配置 LLM + API 键必须不创建配置文件。

    已移除遗留的一次性设置->配置迁移：配置是显式创建的，因此LLM键在agent_settings中永
    远不会生成配置。
    """
    client.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {"llm": {"model": "gpt-4o", "api_key": "sk-no-auto"}}
        },
    )

    response = client.get("/api/profiles")

    assert response.status_code == 200
    body = response.json()
    assert body["profiles"] == []
    assert body["active_profile"] is None


def test_list_profiles_no_auto_create_without_api_key(client):
    """当agent_settings.llm没有API键时不自动创建。"""
    # 配置模型但没有API键
    client.patch(
        "/api/settings",
        json={"agent_settings_diff": {"llm": {"model": "gpt-4o"}}},
    )

    response = client.get("/api/profiles")

    assert response.status_code == 200
    body = response.json()
    assert body["profiles"] == []
    assert body["active_profile"] is None


def test_list_profiles_no_auto_create_when_no_config(client):
    """使用默认设置时不会自动创建（无显式配置）。"""
    # 不要配置任何东西 - 将设置留空
    response = client.get("/api/profiles")

    assert response.status_code == 200
    body = response.json()
    assert body["profiles"] == []
    assert body["active_profile"] is None


def test_list_profiles_no_auto_create_when_profiles_exist(client, store):
    """当配置文件已存在时不会自动创建。"""
    # 首先创建个人资料
    llm = LLM(model="claude-3-opus")
    store.save("existing-profile", llm)

    # 使用API键在设置中配置不同的LLM
    client.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "llm": {"model": "gpt-4o", "api_key": "sk-should-not-auto"}
            }
        },
    )

    response = client.get("/api/profiles")

    assert response.status_code == 200
    body = response.json()
    # 只有现有的配置文件，没有自动创建的配置文件
    assert len(body["profiles"]) == 1
    assert body["profiles"][0]["name"] == "existing-profile"


def test_list_profiles_no_auto_create_after_deleting_active_profile(client, store):
    """删除所有配置文件会使列表为空 (回归)。

    激活配置文件会将其 API 密钥复制到 agent_settings 中； 如果没有从设置中自动创建，
    则该滞留键不得在下一次列表调用中复活配置文件。
    """
    llm = LLM(model="gpt-4o", api_key="sk-test")
    store.save("my-profile", llm, include_secrets=True)
    client.post("/api/profiles/my-profile/activate")

    client.delete("/api/profiles/my-profile")
    response = client.get("/api/profiles")

    assert response.status_code == 200
    body = response.json()
    assert body["profiles"] == []
    assert body["active_profile"] is None


def test_patch_provider_connection_rejects_clearing_api_key(client):
    """PATCH api_key: null 是 422，而不是默默忽略的无操作。"""
    connection_id = client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "Anthropic",
            "provider": "anthropic",
            "api_key": "sk-ant-old",
        },
    ).json()["id"]

    cleared = client.patch(
        f"/api/llm/provider-connections/{connection_id}",
        json={"api_key": None},
    )
    assert cleared.status_code == 422
    assert "api_key cannot be cleared" in cleared.json()["detail"]

    # 存储的密钥未受影响：链接的配置文件仍然可以解析它。
    client.post(
        "/api/profiles/linked",
        json={
            "llm": {
                "model": "anthropic/claude-sonnet-4",
                "provider_connection_id": connection_id,
            },
            "include_secrets": False,
        },
    )
    assert client.get("/api/profiles/linked").json()["api_key_set"] is True


@pytest.mark.parametrize("unusable_key", ["", "   ", REDACTED_SECRET_VALUE])
def test_create_provider_connection_rejects_unusable_api_key(client, unusable_key):
    """POST 拒绝空白钥匙或已脱敏钥匙，而不是存储无钥匙钥匙。"""
    response = client.post(
        "/api/llm/provider-connections",
        json={"display_name": "Blank", "api_key": unusable_key},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "api_key"
    assert client.get("/api/llm/provider-connections").json() == []

    created = client.post(
        "/api/llm/provider-connections",
        json={"display_name": "Valid", "api_key": "sk-valid"},
    )
    assert created.status_code == 201
    assert created.json()["api_key_set"] is True


@pytest.mark.parametrize("unusable_key", ["", "   ", REDACTED_SECRET_VALUE])
def test_patch_provider_connection_rejects_unusable_api_key(client, unusable_key):
    """PATCH 拒绝空白或已脱敏键并保留存储的键。"""
    created = client.post(
        "/api/llm/provider-connections",
        json={"display_name": "Anthropic", "api_key": "sk-ant-old"},
    ).json()
    connection_id = created["id"]
    client.post(
        "/api/profiles/linked",
        json={
            "llm": {
                "model": "anthropic/claude-sonnet-4",
                "provider_connection_id": connection_id,
            },
            "include_secrets": False,
        },
    )

    response = client.patch(
        f"/api/llm/provider-connections/{connection_id}",
        json={"api_key": unusable_key},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "api_key"
    [stored] = client.get("/api/llm/provider-connections").json()
    assert stored == created

    assert client.post("/api/profiles/linked/activate").status_code == 200
    settings = client.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()
    assert settings["agent_settings"]["llm"]["api_key"] == "sk-ant-old"

    rotated = client.patch(
        f"/api/llm/provider-connections/{connection_id}",
        json={"api_key": "sk-ant-new"},
    )
    assert rotated.status_code == 200
    assert rotated.json()["api_key_set"] is True


def test_get_profile_maps_corrupted_provider_file(client, temp_profiles_dir):
    """损坏的提供程序文件会生成映射的 4xx，而不是未处理的 500。

    ``_profile_api_key_set`` 在渲染链接的配置文件时读取提供商存储； 读取必须经过
    ``store_errors()``，因此损坏的文件不会在
    GET /profiles/{name}. 上以 500 的形式转义
    """
    connection_id = client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "Anthropic",
            "provider": "anthropic",
            "api_key": "sk-ant-old",
        },
    ).json()["id"]
    client.post(
        "/api/profiles/linked",
        json={
            "llm": {
                "model": "anthropic/claude-sonnet-4",
                "provider_connection_id": connection_id,
            },
            "include_secrets": False,
        },
    )

    provider_file = (
        temp_profiles_dir.parent / "provider-connections" / "provider_connections.json"
    )
    provider_file.write_text("{ not valid json", encoding="utf-8")

    response = client.get("/api/profiles/linked")

    assert response.status_code == 400
    assert response.status_code != 500


def test_patch_provider_connection_rejects_null_display_name(client):
    """Fix: PATCH display_name=null 必须返回 422，而不是持久化 null。"""
    connection_id = client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "Anthropic",
            "provider": "anthropic",
            "api_key": "sk-ant",
        },
    ).json()["id"]

    response = client.patch(
        f"/api/llm/provider-connections/{connection_id}",
        json={"display_name": None},
    )
    assert response.status_code == 422

    # 被拒绝后连接必须完好PATCH。
    conn = client.get("/api/llm/provider-connections").json()[0]
    assert conn["display_name"] == "Anthropic"


def test_patch_provider_connection_rejects_null_provider(client):
    """Fix: PATCHprovider=null必须返回422。"""
    connection_id = client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "Anthropic",
            "provider": "anthropic",
            "api_key": "sk-ant",
        },
    ).json()["id"]

    response = client.patch(
        f"/api/llm/provider-connections/{connection_id}",
        json={"provider": None},
    )
    assert response.status_code == 422


def test_list_provider_connections_maps_corrupted_file(client, temp_profiles_dir):
    """GET 提供程序连接将损坏的文件映射到 400，而不是 500。"""
    client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "Anthropic",
            "provider": "anthropic",
            "api_key": "sk-ant",
        },
    )

    provider_file = (
        temp_profiles_dir.parent / "provider-connections" / "provider_connections.json"
    )
    provider_file.write_text("{ not valid json", encoding="utf-8")

    response = client.get("/api/llm/provider-connections")

    assert response.status_code == 400
    assert response.status_code != 500


def test_patch_provider_connection_maps_corrupted_file(client, temp_profiles_dir):
    """PATCH 提供程序连接将损坏的文件映射到 400，而不是 500。"""
    connection_id = client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "Anthropic",
            "provider": "anthropic",
            "api_key": "sk-ant",
        },
    ).json()["id"]

    provider_file = (
        temp_profiles_dir.parent / "provider-connections" / "provider_connections.json"
    )
    provider_file.write_text("{ not valid json", encoding="utf-8")

    response = client.patch(
        f"/api/llm/provider-connections/{connection_id}",
        json={"display_name": "Renamed"},
    )

    assert response.status_code == 400
    assert response.status_code != 500


# ── 飞行前验证：POST /api/profiles/{name}/validate ────────────────


def test_validate_profile_success(client):
    """当LLM工作时，POST/api/profiles/{name}/validate返回valid=True。"""
    from unittest.mock import MagicMock

    with (
        patch("openhands.sdk.llm.llm.LLM.uses_responses_api", return_value=False),
        patch(
            "openhands.sdk.llm.llm.LLM.acompletion",
            return_value=MagicMock(),
        ),
    ):
        response = client.post(
            "/api/profiles/test-profile/validate",
            json={"llm": {"model": "gpt-4o", "api_key": "sk-test"}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["error"] is None


def test_validate_profile_sends_system_first(client):
    """飞行前 ping 必须使用系统消息打开（repo 不变量 #5146）。"""
    from unittest.mock import MagicMock

    captured: dict[str, list[Message]] = {}

    async def fake_acompletion(self, messages, **kwargs):
        captured["messages"] = list(messages)
        return MagicMock()

    with (
        patch("openhands.sdk.llm.llm.LLM.uses_responses_api", return_value=False),
        patch(
            "openhands.sdk.llm.llm.LLM.acompletion",
            new=fake_acompletion,
        ),
    ):
        response = client.post(
            "/api/profiles/test-profile/validate",
            json={"llm": {"model": "gpt-4o", "api_key": "sk-test"}},
        )

    assert response.status_code == 200
    msgs = captured["messages"]
    assert [m.role for m in msgs] == ["system", "user"]


def test_validate_profile_responses_api(client):
    """当配置文件模型需要时，飞行前会使用响应 API。

    Regression: 对于配置文件，端点必须通过 ``aresponses`` 路由
    ``uses_responses_api()`` 是 True，与实际对话使用的运行时分发匹配（`LLM.agenerate`
    ）——否则预检将验证与服务器实际调用的
    路径不同的路径。
    """
    from unittest.mock import MagicMock

    traced: dict[str, bool] = {}

    def fake_append(messages, **kwargs):
        traced["called"] = True
        return MagicMock()

    with (
        patch(
            "openhands.sdk.llm.llm.LLM.uses_responses_api",
            return_value=True,
        ),
        patch("openhands.sdk.llm.llm.LLM.aresponses", side_effect=fake_append),
    ):
        response = client.post(
            "/api/profiles/responses-profile/validate",
            json={
                "llm": {
                    "model": "gpt-4o",
                    "api_mode": "responses",
                    "api_key": "sk-test",
                }
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["error"] is None
    assert traced["called"], "expected aresponses to be used for responses-api profiles"


def test_validate_profile_invalid_model_returns_error(client):
    """POST /api/profiles/{name}/validate 在错误模型上返回 valid=False。"""
    from openhands.sdk.llm.exceptions import LLMBadRequestError

    with (
        patch("openhands.sdk.llm.llm.LLM.uses_responses_api", return_value=False),
        patch(
            "openhands.sdk.llm.llm.LLM.acompletion",
            side_effect=LLMBadRequestError(
                "The supported API model names are deepseek-v4-pro or "
                "deepseek-v4-flash, but you passed deepseek-chat"
            ),
        ),
    ):
        response = client.post(
            "/api/profiles/bad-model/validate",
            json={"llm": {"model": "deepseek-chat", "api_key": "sk-test"}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["error"]["type"] == "LLMBadRequestError"
    assert "deepseek" in body["error"]["message"]


def test_validate_profile_auth_error_returns_error(client):
    """POST /api/profiles/{name}/validate 在错误的 API 键上返回 valid=False。"""
    from openhands.sdk.llm.exceptions import LLMAuthenticationError

    with (
        patch("openhands.sdk.llm.llm.LLM.uses_responses_api", return_value=False),
        patch(
            "openhands.sdk.llm.llm.LLM.acompletion",
            side_effect=LLMAuthenticationError("Invalid or missing API credentials"),
        ),
    ):
        response = client.post(
            "/api/profiles/bad-key/validate",
            json={"llm": {"model": "gpt-4o", "api_key": "sk-invalid"}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["error"]["type"] == "LLMAuthenticationError"


def test_validate_profile_rate_limit_does_not_block(client):
    """POST /api/profiles/{name}/validate 在速率限制上返回 valid=True。"""
    from openhands.sdk.llm.exceptions import LLMRateLimitError

    with (
        patch("openhands.sdk.llm.llm.LLM.uses_responses_api", return_value=False),
        patch(
            "openhands.sdk.llm.llm.LLM.acompletion",
            side_effect=LLMRateLimitError("Rate limit exceeded"),
        ),
    ):
        response = client.post(
            "/api/profiles/rate-limited/validate",
            json={"llm": {"model": "gpt-4o", "api_key": "sk-test"}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["error"] is None


def test_validate_profile_service_unavailable_blocks(client):
    """POST /api/profiles/{name}/validate 在提供者 503 上返回 valid=False。"""
    from openhands.sdk.llm.exceptions import LLMServiceUnavailableError

    with (
        patch("openhands.sdk.llm.llm.LLM.uses_responses_api", return_value=False),
        patch(
            "openhands.sdk.llm.llm.LLM.acompletion",
            side_effect=LLMServiceUnavailableError("Service unavailable"),
        ),
    ):
        response = client.post(
            "/api/profiles/unavailable/validate",
            json={"llm": {"model": "gpt-4o", "api_key": "sk-test"}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["error"]["type"] == "LLMServiceUnavailableError"


def test_validate_profile_unknown_error_returns_error(client):
    """POST /api/profiles/{name}/validate 捕获意外异常。"""

    with (
        patch("openhands.sdk.llm.llm.LLM.uses_responses_api", return_value=False),
        patch(
            "openhands.sdk.llm.llm.LLM.acompletion",
            side_effect=RuntimeError("Connection refused"),
        ),
    ):
        response = client.post(
            "/api/profiles/unknown-err/validate",
            json={"llm": {"model": "gpt-4o", "api_key": "sk-test"}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["error"]["type"] == "RuntimeError"
    assert "Connection refused" in body["error"]["message"]


def _stub_litellm_error(error: Exception) -> tuple[Any, list[dict[str, Any]]]:
    """记录每个调用并引发 ``error`` 的 LiteLLM 完成存根。"""
    calls: list[dict[str, Any]] = []

    async def fake_litellm_acompletion(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        raise error

    return fake_litellm_acompletion, calls


def test_validate_profile_does_not_retry_unreachable_endpoint(client):
    """无论配置文件的重试政策如何，飞行前都会在一次尝试后得到答案。

    回归对于 #5100：ping 通过配置文件的运行时重试策略（默认情况下 5 次尝试，退避时间
    为 8-64 秒），因此无法访问
    ``base_url`` 将该请求保留了大约两分钟。
    """
    from litellm.exceptions import APIConnectionError

    fake, calls = _stub_litellm_error(
        APIConnectionError(
            message="Connection refused", llm_provider="openai", model="gpt-4o"
        )
    )
    with patch("openhands.sdk.llm.llm.litellm_acompletion", new=fake):
        response = client.post(
            "/api/profiles/unreachable/validate",
            json={
                "llm": {
                    "model": "openai/gpt-4o",
                    "api_key": "sk-test",
                    "base_url": "http://127.0.0.1:9/v1",
                    "num_retries": 5,
                    "retry_min_wait": 0,
                    "retry_max_wait": 0,
                }
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["error"]["type"] == "LLMServiceUnavailableError"
    assert len(calls) == 1


def test_validate_profile_caps_the_attempt_timeout(client):
    """飞行前尝试使用短超时，而不是 300 秒运行时。"""
    from unittest.mock import MagicMock

    seen: dict[str, Any] = {}

    async def fake_acompletion(self, messages, **kwargs):
        seen["timeout"] = self.timeout
        seen["num_retries"] = self.num_retries
        seen["fallback_strategy"] = self.fallback_strategy
        return MagicMock()

    with (
        patch("openhands.sdk.llm.llm.LLM.uses_responses_api", return_value=False),
        patch("openhands.sdk.llm.llm.LLM.acompletion", new=fake_acompletion),
    ):
        default = client.post(
            "/api/profiles/slow/validate",
            json={"llm": {"model": "gpt-4o", "api_key": "sk-test"}},
        )
        default_timeout = seen["timeout"]
        shorter = client.post(
            "/api/profiles/slow/validate",
            json={
                "llm": {
                    "model": "gpt-4o",
                    "api_key": "sk-test",
                    "timeout": 3,
                    "fallback_strategy": {"fallback_llms": ["backup"]},
                }
            },
        )

    assert default.status_code == 200 and shorter.status_code == 200
    assert default_timeout == profiles_router_module.PREFLIGHT_TIMEOUT_SECONDS
    assert seen["timeout"] == 3
    assert seen["num_retries"] == 0
    assert seen["fallback_strategy"] is None


def test_validate_profile_budget_exceeded_rate_limit_blocks(client):
    """报告预算耗尽的 429 是失败的验证 (#5100)。"""
    from litellm.exceptions import RateLimitError

    fake, calls = _stub_litellm_error(
        RateLimitError(
            message=(
                '{"error":{"message":"Budget has been exceeded! Current cost: '
                '1060.95, Max budget: 1016.82","type":"budget_exceeded",'
                '"code":"429"}}'
            ),
            llm_provider="litellm_proxy",
            model="litellm_proxy/gpt-5.5",
        )
    )
    with (
        patch("openhands.sdk.llm.llm.litellm_acompletion", new=fake),
        patch("openhands.sdk.llm.llm.litellm_aresponses", new=fake),
    ):
        response = client.post(
            "/api/profiles/over-budget/validate",
            json={
                "llm": {
                    "model": "litellm_proxy/gpt-5.5",
                    "api_key": "sk-test",
                    "base_url": "http://proxy.invalid",
                }
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["error"]["type"] == "LLMRateLimitError"
    assert "Budget has been exceeded" in body["error"]["message"]
    assert len(calls) == 1


def test_validate_profile_insufficient_quota_blocks(client):
    """OpenAI的``insufficient_quota`` 429也是失败的验证。"""
    from openhands.sdk.llm.exceptions import LLMRateLimitError

    with (
        patch("openhands.sdk.llm.llm.LLM.uses_responses_api", return_value=False),
        patch(
            "openhands.sdk.llm.llm.LLM.acompletion",
            side_effect=LLMRateLimitError(
                'RateLimitError: OpenAIException - {"error":{"type":'
                '"insufficient_quota","message":"You exceeded your current quota"}}'
            ),
        ),
    ):
        response = client.post(
            "/api/profiles/no-quota/validate",
            json={"llm": {"model": "gpt-4o", "api_key": "sk-test"}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["error"]["type"] == "LLMRateLimitError"


def test_validate_profile_invalid_name(client):
    """POST /api/profiles/{name}/validate 对于无效的配置文件名称返回 422。"""
    response = client.post(
        "/api/profiles/invalid name/validate",
        json={"llm": {"model": "gpt-4o", "api_key": "sk-test"}},
    )

    assert response.status_code == 422


def test_validate_profile_redacts_api_key_in_error(client):
    """飞行前错误消息不得泄露 API 键。

    Regression: 当 LLM 提供者返回一个错误，其消息包含
    提交的 API 键 (e.g. OpenAI 的 ``Incorrect API key provided: sk-proj-…``），验证端
    点必须在将密钥返回到
    HTTP 响应或记录之前对密钥进行编辑。
    """
    from openhands.sdk.llm.exceptions import LLMAuthenticationError

    leaked_key = "sk-proj-abc123defGHIjklMNOpqrsTUVwxyz1234567890"

    with (
        patch("openhands.sdk.llm.llm.LLM.uses_responses_api", return_value=False),
        patch(
            "openhands.sdk.llm.llm.LLM.acompletion",
            side_effect=LLMAuthenticationError(
                f"Incorrect API key provided: {leaked_key}"
            ),
        ),
    ):
        response = client.post(
            "/api/profiles/leaky/validate",
            json={"llm": {"model": "gpt-4o", "api_key": leaked_key}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert leaked_key not in body["error"]["message"], (
        "API key must not appear in the validate error response"
    )


def test_validate_profile_redacts_api_key_in_unknown_error(client):
    """未知异常还必须具有响应中的 API 键已脱敏。"""
    leaked_key = "sk-proj-abc123defGHIjklMNOpqrsTUVwxyz1234567890"

    with (
        patch("openhands.sdk.llm.llm.LLM.uses_responses_api", return_value=False),
        patch(
            "openhands.sdk.llm.llm.LLM.acompletion",
            side_effect=RuntimeError(f"Request failed with key {leaked_key}"),
        ),
    ):
        response = client.post(
            "/api/profiles/leaky-unknown/validate",
            json={"llm": {"model": "gpt-4o", "api_key": leaked_key}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert leaked_key not in body["error"]["message"], (
        "API key must not appear in the validate error response"
    )


def test_validate_profile_subscription_restores_credentials(client):
    """飞行前解析订阅配置文件的 OAuth 凭据。

    Regression: ``validate_profile`` 已反序列化 LLM 通过普通 Pydantic
    但从未调用过``create_subscription_llm_from_config``。 前端发送
    ``auth_type=subscription`` 时不带
     OAuth 访问令牌（它位于凭据存储中，而不是已序列化配置中），因此发送的飞行前
    ``api_key=None`` 并失败，并显示“提供的 API 密钥不正确：None”。

    通过调用修复镜像 ``LLM.from_persisted``
    ``create_subscription_llm_from_config`` 当 ``auth_type == subscription`` 时。
    """
    from unittest.mock import MagicMock

    # 修补凭据存储，以便 OpenAISubscriptionAuth 找到假（有效）凭据，而无需访问文件系统或
    #  OpenAI。 REST 的
    # ``create_subscription_llm_from_config`` 使用真实代码运行，生成一个真实的 LLM，其
    # ``is_subscription`` 标志和凭据已设置。
    #
    fake_creds = OAuthCredentials(
        vendor="openai",
        access_token="fake-access-token",
        refresh_token="fake-refresh-token",
        expires_at=int(time.time() * 1000) + 3_600_000,  # 未过期
    )

    captured: dict = {}

    async def fake_acompletion(self, messages, **kwargs):
        # API 键必须从凭据存储解析，而不是 None。
        api_key = self._get_litellm_api_key_value()
        captured["api_key"] = api_key
        captured["is_subscription"] = self.is_subscription
        return MagicMock()

    with (
        patch(
            "openhands.sdk.llm.auth.credentials.CredentialStore.get",
            return_value=fake_creds,
        ),
        patch("openhands.sdk.llm.llm.LLM.uses_responses_api", return_value=False),
        patch("openhands.sdk.llm.llm.LLM.acompletion", fake_acompletion),
    ):
        response = client.post(
            "/api/profiles/sub-profile/validate",
            json={
                "llm": {
                    "model": "openai/gpt-6-astra",
                    "auth_type": "subscription",
                    "subscription_vendor": "openai",
                    "stream": True,
                    "native_tool_calling": True,
                }
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["error"] is None
    assert captured["is_subscription"] is True
    assert captured["api_key"] == "fake-access-token"


def test_validate_profile_subscription_missing_credentials(client):
    """当订阅凭据不存在时，飞行前返回 ``valid=False``。

    当不存在存储的 OAuth 凭据时，``create_subscription_llm_from_config`` 引发
    ``ValueError``。 端点必须捕
    获此错误并返回结构化错误而不是 500。
    """
    # CredentialStore.get 返回 None → refresh_if_needed_sync 返回 None →
    # create_subscription_llm_from_config 引发 ValueError。
    #
    with (
        patch(
            "openhands.sdk.llm.auth.credentials.CredentialStore.get",
            return_value=None,
        ),
        patch("openhands.sdk.llm.llm.LLM.uses_responses_api", return_value=False),
    ):
        response = client.post(
            "/api/profiles/sub-profile/validate",
            json={
                "llm": {
                    "model": "openai/gpt-6-astra",
                    "auth_type": "subscription",
                    "subscription_vendor": "openai",
                    "stream": True,
                    "native_tool_calling": True,
                }
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert "subscription login" in body["error"]["message"].lower()


def test_validate_profile_resolves_provider_connection(client):
    """链接到提供者连接的草稿通过其凭据进行检查。

    回归对于 #5644：飞行前按原样发送已发布的 LLM，因此没有内嵌密钥的链接草稿被无密钥
    检查并报告
    ``valid=False`` 即使激活它会在连接的密钥上运行。
    """
    from unittest.mock import MagicMock

    connection_id = client.post(
        "/api/llm/provider-connections",
        json={
            "display_name": "Anthropic Work",
            "provider": "anthropic",
            "api_key": "sk-ant-conn",
            "base_url": "https://conn.example.com",
        },
    ).json()["id"]

    captured: dict = {}

    async def fake_acompletion(self, messages, **kwargs):
        captured["api_key"] = self._get_litellm_api_key_value()
        captured["base_url"] = self.base_url
        return MagicMock()

    with (
        patch("openhands.sdk.llm.llm.LLM.uses_responses_api", return_value=False),
        patch("openhands.sdk.llm.llm.LLM.acompletion", fake_acompletion),
    ):
        response = client.post(
            "/api/profiles/draft/validate",
            json={
                "llm": {
                    "model": "anthropic/claude-sonnet-4",
                    "provider_connection_id": connection_id,
                }
            },
        )

    assert response.status_code == 200
    assert response.json() == {"valid": True, "error": None}
    assert captured == {
        "api_key": "sk-ant-conn",
        "base_url": "https://conn.example.com",
    }


def test_validate_profile_with_dangling_provider_connection_returns_422(client):
    """链接到缺失连接的草稿将其命名，就像激活一样。"""
    with patch("openhands.sdk.llm.llm.LLM.acompletion") as acompletion:
        response = client.post(
            "/api/profiles/draft/validate",
            json={
                "llm": {
                    "model": "anthropic/claude-sonnet-4",
                    "provider_connection_id": "missing-connection",
                }
            },
        )

    assert response.status_code == 422
    assert "missing-connection" in response.json()["detail"]
    acompletion.assert_not_called()
