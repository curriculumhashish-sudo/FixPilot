import json
import os
import tempfile
import warnings
from base64 import urlsafe_b64encode
from pathlib import Path

import pytest
from deprecation import DeprecatedWarning
from fastapi.testclient import TestClient
from pydantic import SecretStr

from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config
from openhands.agent_server.persistence import (
    PERSISTED_SETTINGS_SCHEMA_VERSION,
    FileSettingsStore,
    PersistedSettings,
    get_agent_profile_store,
    get_llm_profile_store,
    reset_stores,
)
from openhands.agent_server.persistence.models import _deep_merge
from openhands.sdk.llm import LLM
from openhands.sdk.llm.meta_profile_store import MetaProfile, MetaProfileStore
from openhands.sdk.profiles import OpenHandsAgentProfile
from openhands.sdk.settings import (
    AGENT_SETTINGS_SCHEMA_VERSION,
    CONVERSATION_SETTINGS_SCHEMA_VERSION,
    ACPAgentSettings,
    OpenHandsAgentSettings,
)
from openhands.sdk.utils.cipher import Cipher
from openhands.sdk.utils.pydantic_secrets import REDACTED_SECRET_VALUE


@pytest.fixture
def temp_persistence_dir():
    """为持久化文件创建临时目录并重置存储。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 测试前重置全局存储单例
        reset_stores()
        # 将持久化目录设置为环境变量
        old_val = os.environ.get("OH_PERSISTENCE_DIR")
        os.environ["OH_PERSISTENCE_DIR"] = tmpdir
        yield Path(tmpdir)
        # 清理：重置商店并恢复环境
        reset_stores()
        if old_val is not None:
            os.environ["OH_PERSISTENCE_DIR"] = old_val
        else:
            os.environ.pop("OH_PERSISTENCE_DIR", None)


@pytest.fixture
def secret_key():
    """生成有效的 Fernet 密钥。"""
    return urlsafe_b64encode(b"a" * 32).decode("ascii")


@pytest.fixture
def config_with_settings(temp_persistence_dir, secret_key):
    """使用机密密钥创建一个配置以进行加密。"""
    return Config(
        static_files_path=None,
        session_api_keys=[],
        secret_key=SecretStr(secret_key),
    )


def _encrypt(cipher: Cipher, value: str) -> str:
    encrypted = cipher.encrypt(SecretStr(value))
    assert encrypted is not None
    return encrypted


def _write_settings_file(persistence_dir: Path, payload: dict) -> None:
    (persistence_dir / "settings.json").write_text(json.dumps(payload, indent=2))


@pytest.fixture
def client_with_settings(config_with_settings):
    """创建一个具有设置支持的测试客户端。"""
    return TestClient(create_app(config_with_settings))


def test_get_agent_settings_schema():
    client = TestClient(create_app(Config(static_files_path=None, session_api_keys=[])))

    response = client.get("/api/settings/agent-schema")

    assert response.status_code == 200
    body = response.json()
    assert body["model_name"] == "AgentSettings"

    section_keys = [section["key"] for section in body["sections"]]
    assert "llm" in section_keys
    assert "condenser" in section_keys
    assert "verification" in section_keys

    verification_section = next(
        section for section in body["sections"] if section["key"] == "verification"
    )
    verification_field_keys = {field["key"] for field in verification_section["fields"]}
    assert "verification.critic_enabled" in verification_field_keys
    assert "confirmation_mode" not in verification_field_keys
    assert "security_analyzer" not in verification_field_keys

    # agent_context 是经过策划的：只有带注释的 load_memory 场表面，而不是原始上下文模型
    # 。
    #
    assert "agent_context" in section_keys
    agent_context_section = next(
        section for section in body["sections"] if section["key"] == "agent_context"
    )
    assert [field["key"] for field in agent_context_section["fields"]] == [
        "agent_context.load_memory"
    ]


def test_get_conversation_settings_schema():
    client = TestClient(create_app(Config(static_files_path=None, session_api_keys=[])))

    response = client.get("/api/settings/conversation-schema")

    assert response.status_code == 200
    body = response.json()
    assert body["model_name"] == "ConversationSettings"

    section_keys = [section["key"] for section in body["sections"]]
    assert section_keys == ["general", "verification", "runtime"]

    verification_section = next(
        section for section in body["sections"] if section["key"] == "verification"
    )
    verification_field_keys = {field["key"] for field in verification_section["fields"]}
    assert "confirmation_mode" in verification_field_keys
    assert "security_analyzer" in verification_field_keys


# ── GET /api/settings 测试──────────────────────────────────────────────


def test_get_settings_returns_default_settings(client_with_settings):
    """当 None 为已持久化时，GET /api/settings 返回默认设置。"""
    response = client_with_settings.get("/api/settings")

    assert response.status_code == 200
    body = response.json()
    assert "agent_settings" in body
    assert "conversation_settings" in body
    assert "llm_api_key_is_set" in body
    assert body["agent_settings"]["schema_version"] == AGENT_SETTINGS_SCHEMA_VERSION
    assert body["llm_api_key_is_set"] is False
    assert body["active_profile"] is None


def test_get_settings_migrates_legacy_openhands_settings_and_resaves_current(
    client_with_settings, temp_persistence_dir, secret_key
):
    """旧的 OpenHands 设置文件会加载、迁移并保持可编辑状态。"""
    cipher = Cipher(secret_key)
    _write_settings_file(
        temp_persistence_dir,
        {
            "active_profile": "legacy-profile",
            "agent_settings": {
                "schema_version": 1,
                "agent_kind": "llm",
                "llm": {
                    "model": "legacy-model",
                    "api_key": _encrypt(cipher, "sk-legacy-agent-key"),
                },
                "tools": [{"name": "TerminalTool"}],
                "enable_sub_agents": False,
                "enable_switch_llm_tool": True,
                "mcp_config": {
                    "mcpServers": {
                        "github": {
                            "command": "uvx",
                            "args": ["mcp-server-github"],
                            "env": {
                                "GITHUB_TOKEN": _encrypt(cipher, "ghp-legacy-mcp-token")
                            },
                        },
                        "remote": {
                            "url": "https://example.com/mcp",
                            "headers": {
                                "Authorization": _encrypt(
                                    cipher, "Bearer legacy-mcp-token"
                                )
                            },
                        },
                    }
                },
                "condenser": {"enabled": False, "max_size": 120},
                "verification": {
                    "critic_enabled": True,
                    "confirmation_mode": True,
                    "security_analyzer": "llm",
                },
            },
            "conversation_settings": {
                "max_iterations": 42,
                "confirmation_mode": True,
                "security_analyzer": "llm",
            },
        },
    )

    store = FileSettingsStore(persistence_dir=temp_persistence_dir, cipher=cipher)
    loaded = store.load()

    assert loaded is not None
    assert loaded.active_profile == "legacy-profile"
    assert loaded.schema_version == PERSISTED_SETTINGS_SCHEMA_VERSION

    assert loaded.agent_settings.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert isinstance(loaded.agent_settings, OpenHandsAgentSettings)

    assert loaded.agent_settings.agent_kind == "openhands"
    assert loaded.agent_settings.llm.model == "legacy-model"
    assert isinstance(loaded.agent_settings.llm.api_key, SecretStr)
    assert loaded.agent_settings.llm.api_key.get_secret_value() == "sk-legacy-agent-key"
    assert loaded.conversation_settings.schema_version == (
        CONVERSATION_SETTINGS_SCHEMA_VERSION
    )
    assert loaded.conversation_settings.max_iterations == 42
    assert loaded.conversation_settings.confirmation_mode is True
    assert loaded.conversation_settings.security_analyzer == "llm"

    response = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["active_profile"] == "legacy-profile"
    agent_settings = body["agent_settings"]
    assert agent_settings["schema_version"] == AGENT_SETTINGS_SCHEMA_VERSION
    assert agent_settings["agent_kind"] == "openhands"
    assert agent_settings["llm"]["api_key"] == "sk-legacy-agent-key"
    assert agent_settings["condenser"] == {
        "enabled": False,
        "condenser_kind": "llm_summarizing",
        "max_size": 120,
        "max_tokens": None,
        "keep_first": 2,
        "minimum_progress": 0.1,
        "hard_context_reset_max_retries": 5,
        "hard_context_reset_context_scaling": 0.8,
    }
    assert agent_settings["verification"]["critic_enabled"] is True
    assert "confirmation_mode" not in agent_settings["verification"]
    assert "security_analyzer" not in agent_settings["verification"]
    servers = agent_settings["mcp_config"]
    assert servers["github"]["env"]["GITHUB_TOKEN"] == "ghp-legacy-mcp-token"
    assert servers["remote"]["auth"] == {
        "strategy": "header",
        "headers": {"Authorization": "Bearer legacy-mcp-token"},
    }
    assert "headers" not in servers["remote"]
    assert body["conversation_settings"] == {
        "schema_version": CONVERSATION_SETTINGS_SCHEMA_VERSION,
        "max_iterations": 42,
        "confirmation_mode": True,
        "security_analyzer": "llm",
        "default_runtime": "local",
        "worktree_base_ref": None,
        "worktree_branch_prefix": "openhands/",
        "worktree_base": "default_branch",
        "container_memory": None,
        "container_cpus": None,
        "container_browser": True,
    }

    patch_response = client_with_settings.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {"llm": {"model": "post-migration-model"}},
            "conversation_settings_diff": {"max_iterations": 84},
        },
    )
    assert patch_response.status_code == 200, patch_response.text

    on_disk_text = (temp_persistence_dir / "settings.json").read_text()
    assert "sk-legacy-agent-key" not in on_disk_text
    assert "ghp-legacy-mcp-token" not in on_disk_text
    assert "Bearer legacy-mcp-token" not in on_disk_text

    on_disk = json.loads(on_disk_text)
    assert on_disk["schema_version"] == PERSISTED_SETTINGS_SCHEMA_VERSION
    assert on_disk["active_profile"] == "legacy-profile"
    assert on_disk["agent_settings"]["schema_version"] == AGENT_SETTINGS_SCHEMA_VERSION
    assert on_disk["agent_settings"]["agent_kind"] == "openhands"
    assert on_disk["conversation_settings"]["max_iterations"] == 84

    response = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agent_settings"]["llm"]["model"] == "post-migration-model"
    assert body["agent_settings"]["llm"]["api_key"] == "sk-legacy-agent-key"
    servers = body["agent_settings"]["mcp_config"]
    assert servers["github"]["env"]["GITHUB_TOKEN"] == "ghp-legacy-mcp-token"
    assert servers["remote"]["auth"] == {
        "strategy": "header",
        "headers": {"Authorization": "Bearer legacy-mcp-token"},
    }
    assert "headers" not in servers["remote"]
    assert body["conversation_settings"]["max_iterations"] == 84


def test_get_settings_migrates_acp_settings_and_drops_persisted_llm(
    client_with_settings, temp_persistence_dir, secret_key
):
    """加载旧的 ACP 设置会删除它们的 ``llm`` 和凭据。"""
    cipher = Cipher(secret_key)
    _write_settings_file(
        temp_persistence_dir,
        {
            "agent_settings": {
                "schema_version": 1,
                "agent_kind": "acp",
                "acp_server": "custom",
                "acp_command": ["echo", "settings"],
                "acp_args": ["--verbose"],
                "acp_model": "acp-test-model",
                "acp_session_mode": "bypassPermissions",
                "acp_prompt_timeout": 123.0,
                "llm": {
                    "model": "acp-attribution-model",
                    "api_key": _encrypt(cipher, "sk-acp-llm"),
                },
            },
            "conversation_settings": {"max_iterations": 77},
        },
    )

    store = FileSettingsStore(persistence_dir=temp_persistence_dir, cipher=cipher)
    loaded = store.load()

    assert loaded is not None
    assert loaded.schema_version == PERSISTED_SETTINGS_SCHEMA_VERSION
    assert loaded.agent_settings.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert isinstance(loaded.agent_settings, ACPAgentSettings)

    assert loaded.agent_settings.agent_kind == "acp"
    assert loaded.agent_settings.acp_command == ["echo", "settings"]
    assert loaded.agent_settings.acp_args == ["--verbose"]
    assert loaded.agent_settings.acp_model == "acp-test-model"
    assert loaded.agent_settings.acp_session_mode == "bypassPermissions"
    assert loaded.agent_settings.acp_prompt_timeout == 123.0
    assert "llm" not in loaded.agent_settings.model_dump()

    response = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    )
    assert response.status_code == 200
    agent_settings = response.json()["agent_settings"]
    assert agent_settings["schema_version"] == AGENT_SETTINGS_SCHEMA_VERSION
    assert agent_settings["agent_kind"] == "acp"
    assert "llm" not in agent_settings
    assert response.json()["llm_api_key_is_set"] is False

    patch_response = client_with_settings.patch(
        "/api/settings", json={"conversation_settings_diff": {"max_iterations": 88}}
    )
    assert patch_response.status_code == 200, patch_response.text

    on_disk_text = (temp_persistence_dir / "settings.json").read_text()
    assert "sk-acp-llm" not in on_disk_text
    on_disk = json.loads(on_disk_text)
    assert on_disk["schema_version"] == PERSISTED_SETTINGS_SCHEMA_VERSION
    assert "llm" not in on_disk["agent_settings"]
    assert on_disk["conversation_settings"]["max_iterations"] == 88

    reloaded = store.load()
    assert reloaded is not None
    assert isinstance(reloaded.agent_settings, ACPAgentSettings)

    assert reloaded.conversation_settings.max_iterations == 88


def test_persisted_settings_from_persisted_rejects_newer_schema_version() -> None:
    with pytest.raises(ValueError, match="newer than supported"):
        PersistedSettings.from_persisted(
            {"schema_version": PERSISTED_SETTINGS_SCHEMA_VERSION + 1}
        )


def test_get_settings_without_header_redacts_secrets(
    client_with_settings, temp_persistence_dir, secret_key
):
    """GET /api/settings 没有 X-Expose-机密标头编辑机密。"""
    # 首先，使用商店以机密保存设置
    cipher = Cipher(secret_key)
    store = FileSettingsStore(persistence_dir=temp_persistence_dir, cipher=cipher)
    settings = PersistedSettings()
    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    settings.agent_settings.llm.api_key = SecretStr("sk-test-secret-key")
    store.save(settings)

    response = client_with_settings.get("/api/settings")

    assert response.status_code == 200
    body = response.json()
    # 机密应该是已脱敏（Pydantic 默认行为）
    api_key = body["agent_settings"]["llm"]["api_key"]
    assert api_key == "**********"
    assert body["llm_api_key_is_set"] is True


def test_get_settings_with_plaintext_header_exposes_secrets(
    client_with_settings, temp_persistence_dir, secret_key
):
    """GET /api/settings 与 X-Expose-机密：明文返回原始机密。"""
    # 使用机密保存设置
    cipher = Cipher(secret_key)
    store = FileSettingsStore(persistence_dir=temp_persistence_dir, cipher=cipher)
    settings = PersistedSettings()
    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    settings.agent_settings.llm.api_key = SecretStr("sk-test-secret-key")
    store.save(settings)

    response = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    )

    assert response.status_code == 200
    body = response.json()
    # 机密应该暴露
    api_key = body["agent_settings"]["llm"]["api_key"]
    assert api_key == "sk-test-secret-key"


def test_get_settings_with_encrypted_header_encrypts_secrets(
    client_with_settings, temp_persistence_dir, secret_key
):
    """GET /api/settings 与 X-Expose-机密：加密返回加密的机密。"""
    # 使用机密保存设置
    cipher = Cipher(secret_key)
    store = FileSettingsStore(persistence_dir=temp_persistence_dir, cipher=cipher)
    settings = PersistedSettings()
    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    settings.agent_settings.llm.api_key = SecretStr("sk-test-secret-key")
    store.save(settings)

    response = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "encrypted"}
    )

    assert response.status_code == 200
    body = response.json()
    api_key = body["agent_settings"]["llm"]["api_key"]
    # 应该加密（不是明文，不是已脱敏）
    assert api_key != "sk-test-secret-key"
    assert api_key != "**********"
    # 应该可以解密
    decrypted = cipher.decrypt(api_key)
    assert decrypted is not None
    assert decrypted.get_secret_value() == "sk-test-secret-key"


def test_mcp_oauth_state_is_encrypted_and_round_trips(
    client_with_settings, temp_persistence_dir, secret_key
):
    """存储在 MCP 服务器对象上的 OAuth token 使用设置机密处理。"""
    patch_response = client_with_settings.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "mcp_config": {
                    "superhuman": {
                        "url": "https://mcp.example.com/mcp",
                        "auth": {
                            "strategy": "oauth2",
                            "state": {
                                "tokens": {
                                    "access_token": "oauth-access-token",
                                    "refresh_token": "oauth-refresh-token",
                                },
                                "token_expires_at": 12345.0,
                            },
                        },
                    }
                }
            }
        },
    )

    assert patch_response.status_code == 200, patch_response.text
    response_agent_settings = patch_response.json()["agent_settings"]
    assert response_agent_settings["schema_version"] == AGENT_SETTINGS_SCHEMA_VERSION
    redacted_state = response_agent_settings["mcp_config"]["superhuman"]["auth"][
        "state"
    ]
    assert redacted_state["tokens"]["access_token"] == "**********"

    on_disk_text = (temp_persistence_dir / "settings.json").read_text()
    assert "oauth-access-token" not in on_disk_text
    assert "oauth-refresh-token" not in on_disk_text
    on_disk = json.loads(on_disk_text)
    encrypted_value = on_disk["agent_settings"]["mcp_config"]["superhuman"]["auth"][
        "state"
    ]["tokens"]
    assert encrypted_value["access_token"].startswith("gAAAA")
    assert encrypted_value["refresh_token"].startswith("gAAAA")

    plaintext_response = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    )
    assert plaintext_response.status_code == 200
    plaintext_value = plaintext_response.json()["agent_settings"]["mcp_config"][
        "superhuman"
    ]["auth"]["state"]
    assert plaintext_value == {
        "tokens": {
            "access_token": "oauth-access-token",
            "refresh_token": "oauth-refresh-token",
        },
        "token_expires_at": 12345.0,
    }

    encrypted_response = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "encrypted"}
    )
    assert encrypted_response.status_code == 200
    encrypted_round_trip_value = encrypted_response.json()["agent_settings"][
        "mcp_config"
    ]["superhuman"]["auth"]["state"]["tokens"]
    assert encrypted_round_trip_value["access_token"].startswith("gAAAA")


def test_patch_settings_decrypts_encrypted_mcp_oauth_state(
    client_with_settings, temp_persistence_dir, secret_key
):
    """前端往返的加密 OAuth 状态不会双重保存。"""
    cipher = Cipher(secret_key)
    patch_response = client_with_settings.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "mcp_config": {
                    "superhuman": {
                        "url": "https://mcp.example.com/mcp",
                        "auth": {
                            "strategy": "oauth2",
                            "state": {
                                "tokens": {
                                    "access_token": _encrypt(
                                        cipher, "oauth-access-token"
                                    ),
                                    "refresh_token": _encrypt(
                                        cipher, "oauth-refresh-token"
                                    ),
                                    "token_type": "Bearer",
                                },
                            },
                        },
                    }
                }
            }
        },
    )

    assert patch_response.status_code == 200, patch_response.text

    plaintext_response = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    )
    assert plaintext_response.status_code == 200
    plaintext_value = plaintext_response.json()["agent_settings"]["mcp_config"][
        "superhuman"
    ]["auth"]["state"]["tokens"]
    assert plaintext_value == {
        "access_token": "oauth-access-token",
        "refresh_token": "oauth-refresh-token",
        "token_type": "Bearer",
    }

    on_disk_text = (temp_persistence_dir / "settings.json").read_text()
    assert "oauth-access-token" not in on_disk_text
    assert "oauth-refresh-token" not in on_disk_text


def test_get_settings_with_true_header_treats_as_encrypted(
    client_with_settings, temp_persistence_dir, secret_key
):
    """GET /api/settings 与 X-Expose-机密：True 视为加密（安全）。"""
    # 使用机密保存设置
    cipher = Cipher(secret_key)
    store = FileSettingsStore(persistence_dir=temp_persistence_dir, cipher=cipher)
    settings = PersistedSettings()
    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    settings.agent_settings.llm.api_key = SecretStr("sk-test-secret-key")
    store.save(settings)

    response = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "true"}
    )

    assert response.status_code == 200
    body = response.json()
    api_key = body["agent_settings"]["llm"]["api_key"]
    # 应该加密（不是明文）
    assert api_key != "sk-test-secret-key"
    # 应该可以解密
    decrypted = cipher.decrypt(api_key)
    assert decrypted is not None
    assert decrypted.get_secret_value() == "sk-test-secret-key"


def test_get_settings_with_invalid_header_returns_400(client_with_settings):
    """GET /api/settings 具有无效的 X-Expose-机密值将返回 400。"""
    response = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "invalid-value"}
    )

    assert response.status_code == 400
    assert "Invalid X-Expose-Secrets header" in response.json()["detail"]


# ── PATCH /api/settings 测试────────────────────────────────────────────


def test_patch_settings_updates_llm_config(client_with_settings):
    """PATCH /api/settings可以更新LLM配置。"""
    response = client_with_settings.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {"llm": {"model": "gpt-4o", "api_key": "sk-new-key"}}
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["agent_settings"]["schema_version"] == AGENT_SETTINGS_SCHEMA_VERSION
    assert body["agent_settings"]["llm"]["model"] == "gpt-4o"
    # 响应应该不公开机密（无标头）
    assert body["agent_settings"]["llm"]["api_key"] == "**********"
    assert body["llm_api_key_is_set"] is True


def test_patch_settings_updates_active_profile(client_with_settings):
    """PATCH /api/settings 可以更新和清除活动的 LLM 配置文件。"""
    get_llm_profile_store().save("fast-profile", LLM(model="gpt-4o-mini"))

    response = client_with_settings.patch(
        "/api/settings",
        json={"active_profile": "fast-profile"},
    )

    assert response.status_code == 200
    assert response.json()["active_profile"] == "fast-profile"

    refetch = client_with_settings.get("/api/settings")
    assert refetch.status_code == 200
    assert refetch.json()["active_profile"] == "fast-profile"

    clear_response = client_with_settings.patch(
        "/api/settings",
        json={"active_profile": None},
    )

    assert clear_response.status_code == 200
    assert clear_response.json()["active_profile"] is None

    refetch = client_with_settings.get("/api/settings")
    assert refetch.status_code == 200
    assert refetch.json()["active_profile"] is None


def test_patch_settings_rejects_invalid_active_profile(client_with_settings):
    """PATCH /api/settings 验证活动配置文件名称。"""
    response = client_with_settings.patch(
        "/api/settings",
        json={"active_profile": "not a valid profile"},
    )

    assert response.status_code == 422


def test_patch_settings_active_agent_profile_id_independent(client_with_settings):
    """active_agent_profile_id 独立于 active_profile 设置/清除。"""
    get_llm_profile_store().save("fast-profile", LLM(model="gpt-4o-mini"))
    profile = OpenHandsAgentProfile(name="mine", llm_profile_ref="fast-profile")
    get_agent_profile_store().save(profile)

    agent_id = str(profile.id)
    set_response = client_with_settings.patch(
        "/api/settings",
        json={"active_profile": "fast-profile", "active_agent_profile_id": agent_id},
    )
    assert set_response.status_code == 200
    body = set_response.json()
    assert body["active_profile"] == "fast-profile"
    assert body["active_agent_profile_id"] == agent_id

    # 清除智能体指针必须保持 LLM 配置文件指针不变。
    clear_response = client_with_settings.patch(
        "/api/settings",
        json={"active_agent_profile_id": None},
    )
    assert clear_response.status_code == 200
    cleared = clear_response.json()
    assert cleared["active_agent_profile_id"] is None
    assert cleared["active_profile"] == "fast-profile"

    refetch = client_with_settings.get("/api/settings").json()
    assert refetch["active_agent_profile_id"] is None
    assert refetch["active_profile"] == "fast-profile"


def test_patch_settings_active_profile_applies_llm(client_with_settings):
    """PATCH active_profile 应用该配置文件的 LLM (#4314)。"""
    get_llm_profile_store().save("fast-profile", LLM(model="claude-haiku"))

    response = client_with_settings.patch(
        "/api/settings",
        json={"active_profile": "fast-profile"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["active_profile"] == "fast-profile"
    assert body["agent_settings"]["llm"]["model"] == "claude-haiku"

    refetch = client_with_settings.get("/api/settings").json()
    assert refetch["active_profile"] == "fast-profile"
    assert refetch["agent_settings"]["llm"]["model"] == "claude-haiku"


def test_patch_settings_active_profile_applies_encrypted_api_key(
    client_with_settings, secret_key
):
    """应用配置文件会携带其 at-REST 加密的 api_key 到 PATCH。"""
    cipher = Cipher(secret_key)
    get_llm_profile_store().save(
        "secure-profile",
        LLM(model="claude-haiku", api_key=SecretStr("sk-secret")),
        include_secrets=True,
        cipher=cipher,
    )

    response = client_with_settings.patch(
        "/api/settings",
        json={"active_profile": "secure-profile"},
    )
    assert response.status_code == 200

    exposed = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()
    assert exposed["agent_settings"]["llm"]["model"] == "claude-haiku"
    assert exposed["agent_settings"]["llm"]["api_key"] == "sk-secret"
    assert exposed["llm_api_key_is_set"] is True


def test_patch_settings_active_profile_leaves_acp_settings_without_llm(
    client_with_settings, monkeypatch
):
    monkeypatch.setattr(
        "openhands.sdk.utils.deprecation._current_version", lambda: "1.51.0"
    )
    get_llm_profile_store().save(
        "fast-profile",
        LLM(model="claude-haiku", api_key=SecretStr("sk-secret")),
        include_secrets=True,
    )
    client_with_settings.patch(
        "/api/settings", json={"agent_settings_diff": {"agent_kind": "acp"}}
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecatedWarning)
        response = client_with_settings.patch(
            "/api/settings", json={"active_profile": "fast-profile"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["active_profile"] == "fast-profile"
    assert body["agent_settings"]["agent_kind"] == "acp"
    assert "llm" not in body["agent_settings"]


def test_patch_settings_active_profile_applies_llm_when_switching_to_openhands(
    client_with_settings,
):
    get_llm_profile_store().save("fast-profile", LLM(model="claude-haiku"))
    client_with_settings.patch(
        "/api/settings", json={"agent_settings_diff": {"agent_kind": "acp"}}
    )

    response = client_with_settings.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {"agent_kind": "openhands"},
            "active_profile": "fast-profile",
        },
    )

    assert response.status_code == 200
    agent_settings = response.json()["agent_settings"]
    assert agent_settings["agent_kind"] == "openhands"
    assert agent_settings["llm"]["model"] == "claude-haiku"


def test_patch_settings_switching_active_profile_updates_llm(client_with_settings):
    """切换 active_profile 会重新应用新配置文件的 LLM。"""
    get_llm_profile_store().save("profile-a", LLM(model="model-a"))
    get_llm_profile_store().save("profile-b", LLM(model="model-b"))

    client_with_settings.patch("/api/settings", json={"active_profile": "profile-a"})
    response = client_with_settings.patch(
        "/api/settings", json={"active_profile": "profile-b"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["active_profile"] == "profile-b"
    assert body["agent_settings"]["llm"]["model"] == "model-b"


def test_patch_settings_active_profile_not_found_returns_404(client_with_settings):
    """PATCH active_profile 具有未知的配置文件名称 404s。"""
    response = client_with_settings.patch(
        "/api/settings",
        json={"active_profile": "does-not-exist"},
    )

    assert response.status_code == 404

    refetch = client_with_settings.get("/api/settings").json()
    assert refetch["active_profile"] is None


def test_patch_settings_explicit_llm_diff_overrides_profile_autoload(
    client_with_settings,
):
    """显式 agent_settings_diff.llm 会覆盖配置文件自动加载。"""
    get_llm_profile_store().save("fast-profile", LLM(model="claude-haiku"))

    response = client_with_settings.patch(
        "/api/settings",
        json={
            "active_profile": "fast-profile",
            "agent_settings_diff": {"llm": {"model": "explicitly-chosen-model"}},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["active_profile"] == "fast-profile"
    assert body["agent_settings"]["llm"]["model"] == "explicitly-chosen-model"


def test_patch_settings_rejects_malformed_active_agent_profile_id(client_with_settings):
    """非 UUID active_agent_profile_id 在 HTTP 层被拒绝。"""
    response = client_with_settings.patch(
        "/api/settings",
        json={"active_agent_profile_id": "not-a-uuid"},
    )
    assert response.status_code == 422


def test_patch_settings_rejects_unknown_active_agent_profile_id(
    client_with_settings,
):
    """未命名已存储的智能体配置文件的 id 为 404，如 /activate (#5847)。"""
    unknown = "00000000-0000-4000-8000-0000000000f1"
    response = client_with_settings.patch(
        "/api/settings", json={"active_agent_profile_id": unknown}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == (f"Agent profile with id '{unknown}' not found")
    assert (
        client_with_settings.get("/api/settings").json()["active_agent_profile_id"]
        is None
    )


def test_patch_settings_active_meta_profile_must_exist(
    client_with_settings, temp_persistence_dir
):
    """未知的元配置文件为 404，并且不启用任何功能； 存储的一个是
    接受并 null 清除它 (#5847)。"""
    response = client_with_settings.patch(
        "/api/settings", json={"active_meta_profile": "no-router"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Meta-profile 'no-router' not found"
    body = client_with_settings.get("/api/settings").json()
    assert body["active_meta_profile"] is None
    assert body["agent_settings"]["enable_classify_and_switch_llm_tool"] is False

    MetaProfileStore(base_dir=Path(temp_persistence_dir) / "meta-profiles").save(
        "router",
        MetaProfile.model_validate(
            {
                "classifier_model": "minimax",
                "classes": [{"description": "UI", "model": "deepseek"}],
            }
        ),
    )
    response = client_with_settings.patch(
        "/api/settings", json={"active_meta_profile": "router"}
    )
    assert response.status_code == 200
    assert response.json()["active_meta_profile"] == "router"

    response = client_with_settings.patch(
        "/api/settings", json={"active_meta_profile": None}
    )
    assert response.status_code == 200
    assert response.json()["active_meta_profile"] is None


def test_existing_settings_load_with_null_active_agent_profile_id(
    temp_persistence_dir, config_with_settings
):
    """字段加载前的设置文件为 active_agent_profile_id=None。"""
    _write_settings_file(
        temp_persistence_dir,
        {
            "schema_version": PERSISTED_SETTINGS_SCHEMA_VERSION,
            "agent_settings": {"agent_kind": "openhands"},
            "active_profile": "legacy-profile",
        },
    )

    client = TestClient(create_app(config_with_settings))
    response = client.get("/api/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["active_profile"] == "legacy-profile"
    assert body["active_agent_profile_id"] is None


def test_patch_settings_updates_condenser_config(client_with_settings):
    """PATCH /api/settings 可以更新上下文压缩器构造函数设置。"""
    response = client_with_settings.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "condenser": {
                    "enabled": True,
                    "condenser_kind": "llm_summarizing",
                    "max_size": 120,
                    "max_tokens": 56000,
                    "keep_first": 3,
                    "minimum_progress": 0.2,
                    "hard_context_reset_max_retries": 7,
                    "hard_context_reset_context_scaling": 0.6,
                }
            }
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["agent_settings"]["condenser"] == {
        "enabled": True,
        "condenser_kind": "llm_summarizing",
        "max_size": 120,
        "max_tokens": 56000,
        "keep_first": 3,
        "minimum_progress": 0.2,
        "hard_context_reset_max_retries": 7,
        "hard_context_reset_context_scaling": 0.6,
    }


def test_patch_settings_switches_condenser_variant(client_with_settings):
    """PATCH /api/settings 可以切换到不同的上下文压缩器设置变量。"""
    response = client_with_settings.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "condenser": {
                    "enabled": True,
                    "condenser_kind": "no_op",
                }
            }
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["agent_settings"]["condenser"] == {
        "enabled": True,
        "condenser_kind": "no_op",
    }


def test_patch_settings_encrypts_mcp_env_and_headers_on_disk(
    client_with_settings, temp_persistence_dir
):
    """PATCH /api/settings 必须加密 MCP ``env`` / ``headers`` 值
    REST 使用配置的密码 - 与其他机密字段为已持久化的方式相同 - 并且永远不要写入已脱敏
    哨兵值或明文。

    通过 ``X-Expose-Secrets: plaintext`` 读回它们必须往返到原始值（在加载时解密）。
    """
    response = client_with_settings.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "mcp_config": {
                    "github": {
                        "command": "uvx",
                        "args": ["mcp-server-github"],
                        "env": {"GITHUB_TOKEN": "ghp-router-secret"},
                    },
                    "remote": {
                        "url": "https://example.com/mcp",
                        "headers": {"X-Api-Key": "tok-router-secret"},
                    },
                }
            }
        },
    )
    assert response.status_code == 200, response.text

    # 检查磁盘上的 settings.json：明文必须出现不，值必须是 Fernet 密文。
    #
    on_disk_path = temp_persistence_dir / "settings.json"
    on_disk_text = on_disk_path.read_text()
    assert "<redacted>" not in on_disk_text
    assert "**********" not in on_disk_text
    assert "ghp-router-secret" not in on_disk_text
    assert "tok-router-secret" not in on_disk_text

    on_disk = json.loads(on_disk_text)
    servers_on_disk = on_disk["agent_settings"]["mcp_config"]
    assert servers_on_disk["github"]["env"]["GITHUB_TOKEN"].startswith("gAAAA")
    assert servers_on_disk["remote"]["headers"]["X-Api-Key"].startswith("gAAAA")
    # 非机密结构必须保持可读。
    assert servers_on_disk["github"]["command"] == "uvx"
    assert servers_on_disk["remote"]["url"] == "https://example.com/mcp"

    # GET 明文解密并返回原始的往返值。
    response = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    )
    assert response.status_code == 200
    agent_settings = response.json()["agent_settings"]
    assert agent_settings["schema_version"] == AGENT_SETTINGS_SCHEMA_VERSION
    servers = agent_settings["mcp_config"]
    assert servers["github"]["env"]["GITHUB_TOKEN"] == "ghp-router-secret"
    assert servers["remote"]["headers"] == {"X-Api-Key": "tok-router-secret"}


def test_mcp_server_crud_endpoints_preserve_sibling_credentials(client_with_settings):
    github = client_with_settings.post(
        "/api/settings/mcp/github",
        json={
            "transport": "http",
            "url": "https://github.example/mcp",
            "auth": {"strategy": "bearer", "value": "github-secret"},
        },
    )
    assert github.status_code == 201, github.text
    assert github.json()["agent_settings"]["mcp_config"]["github"]["auth"] == {
        "strategy": "bearer",
        "value": "**********",
    }

    docs = client_with_settings.post(
        "/api/settings/mcp/docs",
        json={"transport": "http", "url": "https://docs.example/mcp"},
    )
    assert docs.status_code == 201, docs.text

    updated_docs = client_with_settings.patch(
        "/api/settings/mcp/docs",
        json={"description": "Documentation"},
    )
    assert updated_docs.status_code == 200, updated_docs.text

    plaintext = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()["agent_settings"]["mcp_config"]
    assert plaintext["github"]["auth"]["value"] == "github-secret"
    assert plaintext["docs"]["description"] == "Documentation"

    deleted_docs = client_with_settings.delete("/api/settings/mcp/docs")
    assert deleted_docs.status_code == 200, deleted_docs.text
    assert set(deleted_docs.json()["agent_settings"]["mcp_config"]) == {"github"}

    replaced_auth = client_with_settings.patch(
        "/api/settings/mcp/github",
        json={"auth": {"strategy": "bearer", "value": "new-github-secret"}},
    )
    assert replaced_auth.status_code == 200, replaced_auth.text
    plaintext = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()["agent_settings"]["mcp_config"]
    assert plaintext["github"]["auth"]["value"] == "new-github-secret"

    cleared_auth = client_with_settings.patch(
        "/api/settings/mcp/github",
        json={"auth": None},
    )
    assert cleared_auth.status_code == 200, cleared_auth.text
    assert "auth" not in cleared_auth.json()["agent_settings"]["mcp_config"]["github"]


def test_mcp_server_patch_toggles_enabled_without_dropping_config(
    client_with_settings,
):
    """关闭服务器可以保持其及其凭据的配置。"""
    created = client_with_settings.post(
        "/api/settings/mcp/github",
        json={
            "transport": "http",
            "url": "https://github.example/mcp",
            "auth": {"strategy": "bearer", "value": "github-secret"},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["agent_settings"]["mcp_config"]["github"]["enabled"] is True

    disabled = client_with_settings.patch(
        "/api/settings/mcp/github",
        json={"enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    server = disabled.json()["agent_settings"]["mcp_config"]["github"]
    assert server["enabled"] is False
    assert server["url"] == "https://github.example/mcp"

    # 凭据在切换后仍然存在 - 这是禁用而不是删除的点。
    #
    plaintext = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()["agent_settings"]["mcp_config"]["github"]
    assert plaintext["auth"]["value"] == "github-secret"
    assert plaintext["enabled"] is False

    # 未提及该标志的补丁不得默默地重新启用它。
    described = client_with_settings.patch(
        "/api/settings/mcp/github",
        json={"description": "GitHub"},
    )
    assert described.status_code == 200, described.text
    still_disabled = described.json()["agent_settings"]["mcp_config"]["github"]
    assert still_disabled["enabled"] is False
    assert still_disabled["description"] == "GitHub"

    # null 清除覆盖，恢复规范默认值（启用）。
    restored = client_with_settings.patch(
        "/api/settings/mcp/github",
        json={"enabled": None},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["agent_settings"]["mcp_config"]["github"]["enabled"] is True


def test_mcp_server_crud_endpoints_enforce_key_preconditions(client_with_settings):
    created = client_with_settings.post(
        "/api/settings/mcp/github",
        json={"transport": "http", "url": "https://github.example/mcp"},
    )
    assert created.status_code == 201, created.text

    duplicate = client_with_settings.post(
        "/api/settings/mcp/github",
        json={"transport": "http", "url": "https://replacement.example/mcp"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "MCP server 'github' already exists"

    missing_patch = client_with_settings.patch(
        "/api/settings/mcp/missing",
        json={"description": "Missing"},
    )
    assert missing_patch.status_code == 404

    missing_delete = client_with_settings.delete("/api/settings/mcp/missing")
    assert missing_delete.status_code == 404

    plaintext = client_with_settings.get(
        "/api/settings", headers={"X-Expose-Secrets": "plaintext"}
    ).json()["agent_settings"]["mcp_config"]
    assert plaintext["github"]["url"] == "https://github.example/mcp"


def test_mcp_server_crud_endpoints_normalize_key_paths(client_with_settings):
    server = {"transport": "http", "url": "https://github.example/mcp"}
    created = client_with_settings.post("/api/settings/mcp/github", json=server)
    assert created.status_code == 201, created.text

    trailing_slash = client_with_settings.post(
        "/api/settings/mcp/github/",
        json=server,
        follow_redirects=False,
    )
    assert trailing_slash.status_code == 307
    assert trailing_slash.headers["location"].endswith("/api/settings/mcp/github")

    empty_key = client_with_settings.post(
        "/api/settings/mcp/",
        json=server,
        follow_redirects=False,
    )
    assert empty_key.status_code == 404

    mcp_config = client_with_settings.get("/api/settings").json()["agent_settings"][
        "mcp_config"
    ]
    assert set(mcp_config) == {"github"}


def test_patch_settings_empty_payload_returns_400(client_with_settings):
    """PATCH /api/settings 与空载荷返回 400。"""
    response = client_with_settings.patch("/api/settings", json={})

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "At least one of agent_settings_diff, "
        "conversation_settings_diff, misc_settings_diff, "
        "active_profile, active_agent_profile_id, or active_meta_profile "
        "must be provided"
    )


# ── misc_settings（不透明前端拥有的容器）──────────────────────
#
# 这些测试练习了持久化 + 深度合并行为
# ``misc_settings`` 容器。 智能体服务器将其视为透明，因此载荷下面使用无意义的键值对，其
# 唯一目的就是测试合并机制——它们故意不引用任何特定前端的模式。
#


def test_get_settings_returns_empty_misc_settings_by_default(client_with_settings):
    """GET /api/settings 默认返回一个空的 misc_settings 字典。"""
    response = client_with_settings.get("/api/settings")

    assert response.status_code == 200
    body = response.json()
    assert "misc_settings" in body
    assert body["misc_settings"] == {}


def test_patch_settings_writes_misc_settings(client_with_settings):
    """PATCH /api/settings 和 misc_settings_diff 保留载荷。"""
    payload = {
        "theme": "dark",
        "ui": {"sidebar": "open", "tags": ["alpha", "beta"]},
    }
    response = client_with_settings.patch(
        "/api/settings",
        json={"misc_settings_diff": payload},
    )

    assert response.status_code == 200
    assert response.json()["misc_settings"] == payload

    # 已持久化跨请求
    refetch = client_with_settings.get("/api/settings")
    assert refetch.status_code == 200
    assert refetch.json()["misc_settings"] == payload


def test_patch_settings_misc_settings_diff_is_deep_merged(client_with_settings):
    """部分 misc_settings_diff 合并到现有块中。

    一个更新一个嵌套字段的差异不由先前设置的兄弟字段覆盖 PATCH — 合并过程通过了同样的
     ``_deep_merge`` 用于 agent_settings /
    conversation_settings.
    """
    client_with_settings.patch(
        "/api/settings",
        json={
            "misc_settings_diff": {
                "theme": "dark",
                "ui": {"sidebar": "open", "density": "comfortable"},
            }
        },
    )

    response = client_with_settings.patch(
        "/api/settings",
        json={"misc_settings_diff": {"ui": {"sidebar": "collapsed"}}},
    )

    assert response.status_code == 200
    misc = response.json()["misc_settings"]
    # 保留同级顶级字段
    assert misc["theme"] == "dark"
    # 更新了嵌套字段
    assert misc["ui"]["sidebar"] == "collapsed"
    # 保留同级嵌套字段（这是深度合并属性）
    assert misc["ui"]["density"] == "comfortable"


def test_patch_settings_misc_settings_lists_replace_wholesale(client_with_settings):
    """misc_settings 内的列表将被批量替换，而不是合并。"""
    client_with_settings.patch(
        "/api/settings",
        json={"misc_settings_diff": {"tags": ["alpha", "beta", "gamma"]}},
    )

    response = client_with_settings.patch(
        "/api/settings",
        json={"misc_settings_diff": {"tags": []}},
    )

    assert response.status_code == 200
    assert response.json()["misc_settings"]["tags"] == []


def test_patch_settings_misc_settings_only_payload_is_accepted(client_with_settings):
    """misc_settings_diff 单独满足“至少一个”检查。"""
    response = client_with_settings.patch(
        "/api/settings",
        json={"misc_settings_diff": {"theme": "dark"}},
    )

    assert response.status_code == 200


def test_patch_settings_misc_settings_accepts_arbitrary_payloads(client_with_settings):
    """智能体-服务器不解释 misc_settings — 任何 JSON 形状都可以。

    *不透明*合约的覆盖范围：会被内部类型化模式拒绝的载荷（e.g. 一个列表“自然”会去的字
    符串）被接受并逐字已持久化，因为misc_settings的验证是前端的责
    任。
    """
    response = client_with_settings.patch(
        "/api/settings",
        json={"misc_settings_diff": {"tags": "not-a-list", "count": 42}},
    )

    assert response.status_code == 200
    misc = response.json()["misc_settings"]
    assert misc["tags"] == "not-a-list"
    assert misc["count"] == 42


def test_patch_settings_misc_settings_does_not_clobber_agent_settings(
    client_with_settings,
):
    """仅写入 misc_settings 不得重置 agent_settings。"""
    client_with_settings.patch(
        "/api/settings",
        json={"agent_settings_diff": {"llm": {"model": "gpt-4o"}}},
    )

    response = client_with_settings.patch(
        "/api/settings",
        json={"misc_settings_diff": {"theme": "dark"}},
    )

    assert response.status_code == 200
    assert response.json()["agent_settings"]["llm"]["model"] == "gpt-4o"


def test_persisted_settings_v1_loads_with_empty_misc_settings(
    temp_persistence_dir, client_with_settings
):
    """v1 设置文件（无 misc_settings）加载为空默认值。"""
    settings_path = temp_persistence_dir / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "agent_settings": {
                    "agent_kind": "openhands",
                    "schema_version": AGENT_SETTINGS_SCHEMA_VERSION,
                    "llm": {"model": "gpt-4o"},
                },
                "conversation_settings": {
                    "schema_version": CONVERSATION_SETTINGS_SCHEMA_VERSION,
                },
                "active_profile": None,
            }
        )
    )

    response = client_with_settings.get("/api/settings")
    assert response.status_code == 200
    assert response.json()["misc_settings"] == {}


def test_patch_settings_deep_merges(client_with_settings):
    """PATCH /api/settings 与现有设置深度合并。"""
    # 第一次更新：设置模型
    client_with_settings.patch(
        "/api/settings",
        json={"agent_settings_diff": {"llm": {"model": "gpt-4o"}}},
    )

    # 第二次更新：设置api_key（应保留模型）
    response = client_with_settings.patch(
        "/api/settings",
        json={"agent_settings_diff": {"llm": {"api_key": "sk-test-key"}}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["agent_settings"]["llm"]["model"] == "gpt-4o"
    assert body["llm_api_key_is_set"] is True


def test_patch_settings_agent_context_load_memory_round_trips(client_with_settings):
    """持久内存切换的线路路径：嵌套的 agent_context diff
    持续存在并由 GET 提供服务（GUI 内存页读取的内容）。"""
    response = client_with_settings.patch(
        "/api/settings",
        json={"agent_settings_diff": {"agent_context": {"load_memory": True}}},
    )
    assert response.status_code == 200

    fetched = client_with_settings.get("/api/settings")

    assert fetched.status_code == 200
    agent_settings = fetched.json()["agent_settings"]
    assert agent_settings["agent_context"]["load_memory"] is True


# ── JSON 合并补丁 (RFC 7386) 未设置语义 ──────────────────────────


def test_deep_merge_top_level_null_is_set_not_delete():
    """顶级 * 字段 * 上的 ``None`` 保持原样（设置），不已删除 —
    因此它流向验证并大声失败，而不是默默地将字段重置为其默认值。
    """
    merged = _deep_merge({"confirmation_mode": True}, {"confirmation_mode": None})
    assert merged == {"confirmation_mode": None}


def test_deep_merge_nested_null_deletes_entry():
    """嵌套映射 * 内的 ``None`` * 删除该条目； 兄弟姐妹生存下来。"""
    merged = _deep_merge(
        {"env": {"KEEP": "a", "DROP": "b"}},
        {"env": {"DROP": None}},
    )
    assert merged == {"env": {"KEEP": "a"}}


def test_deep_merge_nested_null_on_absent_key_is_noop():
    """取消设置不存在的嵌套键是无操作，而不是错误。"""
    merged = _deep_merge({"env": {"KEEP": "a"}}, {"env": {"MISSING": None}})
    assert merged == {"env": {"KEEP": "a"}}


def test_deep_merge_new_map_embedded_null_stored_as_is():
    """极端情况（记录在``_deep_merge``中）：当嵌套映射本身
    如果基础数据中尚不存在该映射，会整体赋予覆盖字典；其中的 null 条目不会按删除处理
    ，因为无法从尚不存在的映射中删除内容。 针对未来的重构提供保证。
    """
    merged = _deep_merge({}, {"new_map": {"KEY": None}})
    assert merged == {"new_map": {"KEY": None}}


def test_deep_merge_non_null_still_wins():
    """Regression: 非null值仍然像以前一样设置/覆盖和合并。"""
    merged = _deep_merge({"a": 1, "b": {"x": 1}}, {"a": 2, "b": {"y": 2}})
    assert merged == {"a": 2, "b": {"x": 1, "y": 2}}


# ── apply_agent_settings_diff parity (PersistedSettings.update) ─────────


def test_update_agent_settings_same_kind_merge() -> None:
    """同类更新在变体中深度合并。"""
    settings = PersistedSettings()
    settings.update({"agent_settings_diff": {"llm": {"model": "gpt-4o"}}})
    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    assert settings.agent_settings.llm.model == "gpt-4o"


def test_update_agent_settings_kind_switch_replaces_fresh() -> None:
    """种类切换从新变体开始； 不携带旧字段。"""
    settings = PersistedSettings()
    settings.update({"agent_settings_diff": {"llm": {"model": "gpt-x"}}})

    settings.update(
        {"agent_settings_diff": {"agent_kind": "acp", "acp_server": "claude-code"}}
    )

    assert isinstance(settings.agent_settings, ACPAgentSettings)
    assert settings.agent_settings.acp_server == "claude-code"


def test_update_agent_settings_switch_back_to_openhands() -> None:
    """切换回 OpenHands 重新开始； ACP 字段未泄漏。"""
    from openhands.sdk.settings.model import OpenHandsAgentSettings

    settings = PersistedSettings()
    settings.update(
        {"agent_settings_diff": {"agent_kind": "acp", "acp_server": "gemini-cli"}}
    )

    settings.update(
        {"agent_settings_diff": {"agent_kind": "openhands", "llm": {"model": "gpt-4o"}}}
    )

    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    assert settings.agent_settings.llm.model == "gpt-4o"


def test_update_agent_settings_null_unsets_optional_field() -> None:
    """可选字段上的 null 值会将其重置为默认值（RFC 7386 语义）。"""
    settings = PersistedSettings()
    settings.update(
        {
            "agent_settings_diff": {
                "agent_kind": "acp",
                "acp_server": "claude-code",
                "acp_model": "claude-opus-4-8",
            }
        }
    )
    assert isinstance(settings.agent_settings, ACPAgentSettings)
    assert settings.agent_settings.acp_model == "claude-opus-4-8"

    settings.update({"agent_settings_diff": {"acp_model": None}})
    assert isinstance(settings.agent_settings, ACPAgentSettings)
    assert settings.agent_settings.acp_model is None


def test_update_agent_settings_secret_survives_same_kind_merge() -> None:
    """agent_settings 中现有的 api_key 在同类更新中保留。"""
    from pydantic import SecretStr

    settings = PersistedSettings()
    settings.update(
        {"agent_settings_diff": {"llm": {"model": "gpt-4o", "api_key": "sk-SECRET"}}}
    )

    settings.update({"agent_settings_diff": {"llm": {"temperature": 0.5}}})

    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    assert isinstance(settings.agent_settings.llm.api_key, SecretStr)
    assert settings.agent_settings.llm.api_key.get_secret_value() == "sk-SECRET"


def test_patch_settings_null_on_scalar_field_fails_loudly(client_with_settings):
    """回归防范静音重置足枪：``null`` 在
    像 ``confirmation_mode`` 这样的非可选标量被拒绝（422），而不是默默地恢复到它的（
    不安全的）默认值。
    """
    response = client_with_settings.patch(
        "/api/settings",
        json={"conversation_settings_diff": {"confirmation_mode": None}},
    )
    assert response.status_code == 422


def test_patch_settings_switch_agent_kind_from_acp_to_openhands(
    client_with_settings, temp_persistence_dir
):
    """PATCH/api/settings可以从ACP到OpenHands切换。

    当 ``agent_kind`` 更改时，旧变体中的不兼容字段（如 ``acp_command``）不得合并到新
    变体中。 这是变体替换，而不是字段合并。
    """
    acp = ACPAgentSettings(acp_command=["echo", "test"])
    persisted = PersistedSettings(agent_settings=acp)
    payload = persisted.model_dump(mode="json", context={"expose_secrets": "plaintext"})
    _write_settings_file(temp_persistence_dir, payload)

    get_response = client_with_settings.get("/api/settings")
    seeded = get_response.json()["agent_settings"]
    assert seeded["agent_kind"] == "acp"
    assert "llm" not in seeded

    # 切换到 OpenHands，用新模型重申 ``llm``。
    response = client_with_settings.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "agent_kind": "openhands",
                "llm": {"model": "claude-3-5-sonnet-20241022"},
            }
        },
    )

    # 应该成功 — 关于剩余的 ACP 特定字段没有验证错误
    assert response.status_code == 200
    body = response.json()
    assert body["agent_settings"]["agent_kind"] == "openhands"
    # ACP 特定字段不应出现在响应中
    assert "acp_command" not in body["agent_settings"]
    assert body["agent_settings"]["llm"]["model"] == "claude-3-5-sonnet-20241022"


def test_patch_settings_switch_drops_shared_field_when_not_restated(
    client_with_settings, temp_persistence_dir
):
    """在 OLD 变体上设置的共享字段 (``llm``) 被删除到一个种类上
    除非调用者重申它，否则它会回退到新变体的默认值，而不是默默地保留。

    这固定了有意的“新变体的新开始”契约：种类切换是变体替换，因此共享字段不会被继承。
    想要保留共享字段的调用者必须将其包含在开关载荷中（请参阅兄弟测试，其中重申了
    ``llm``）。
    """
    # 在 v7 迁移之前存储的种子 ACP 设置，具有非默认 llm。
    _write_settings_file(
        temp_persistence_dir,
        {
            "agent_settings": {
                "schema_version": 6,
                "agent_kind": "acp",
                "acp_command": ["echo", "test"],
                "llm": {"model": "acp-only-model"},
            }
        },
    )

    # 切换到 OpenHands WITHOUT 重述 llm。
    response = client_with_settings.patch(
        "/api/settings",
        json={"agent_settings_diff": {"agent_kind": "openhands"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["agent_settings"]["agent_kind"] == "openhands"
    # ACP 种子模型被延续到不； llm 回退到 OpenHands 变体的默认模型。
    #
    default_model = OpenHandsAgentSettings().llm.model
    assert body["agent_settings"]["llm"]["model"] == default_model
    assert body["agent_settings"]["llm"]["model"] != "acp-only-model"


def test_patch_settings_switch_agent_kind_from_openhands_to_acp(client_with_settings):
    """PATCH/api/settings可以从OpenHands到ACP切换。

    切换到 ACP 时，应设置新变体的必填字段，而不会受到旧变体字段的干扰。
    """
    # 设置为 OpenHands 的种子（默认）
    response = client_with_settings.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "llm": {"model": "claude-3-5-sonnet-20241022"},
            }
        },
    )
    assert response.status_code == 200

    # 切换到ACP
    response = client_with_settings.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "agent_kind": "acp",
                "acp_command": ["echo", "hello"],
            }
        },
    )

    # 应该成功 — 关于剩余的 OpenHands 特定字段没有验证错误
    assert response.status_code == 200
    body = response.json()
    assert body["agent_settings"]["agent_kind"] == "acp"
    assert body["agent_settings"]["acp_command"] == ["echo", "hello"]


def test_patch_settings_same_kind_restated_still_deep_merges(client_with_settings):
    """重新声明当前的 ``agent_kind`` 是不的变体开关： diff
    必须仍然深合并，以保留无关字段。

    当类型被重述时，``new_kind != old_kind`` 是 False，因此深度合并分支运行。 这表明
    ，客户端回显当前 ``agent_kind`` 并且
    进行增量编辑时，不会意外触发全变体替换（这会重置兄弟字段）。
    """
    # 在默认 OpenHands 变体上建立模型。
    response = client_with_settings.patch(
        "/api/settings",
        json={"agent_settings_diff": {"llm": {"model": "gpt-4o"}}},
    )
    assert response.status_code == 200

    # 重新设置 agent_kind=OpenHands，同时仅设置 api_key。 因为种类没有改变，所以这种深度
    # 合并和模型必须被保留。
    #
    response = client_with_settings.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "agent_kind": "openhands",
                "llm": {"api_key": "sk-test-key"},
            }
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agent_settings"]["agent_kind"] == "openhands"
    # 第一个 PATCH 中设置的模型得以幸存——证明了深度合并运行。
    assert body["agent_settings"]["llm"]["model"] == "gpt-4o"
    assert body["llm_api_key_is_set"] is True


def test_patch_settings_same_kind_merge_after_a_switch(client_with_settings):
    """在变种切换后，后续同种类型的 PATCHes 会进行深合并。

    开关本身是一个替代方案，但新的激活变体必须像其他任何东西一样行为，之后的增量编辑
    必须不会抹掉在开关期间设置的字段。
    """
    # 从默认的 OpenHands 切换到 ACP，设置两个 ACP 字段。
    response = client_with_settings.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "agent_kind": "acp",
                "acp_command": ["my-cli"],
                "acp_args": ["--foo"],
            }
        },
    )
    assert response.status_code == 200
    assert response.json()["agent_settings"]["acp_command"] == ["my-cli"]

    # 同类后续：编辑不同的字段。 深度合并必须保留切换期间设置的 acp_command 和 acp_args
    # 。
    #
    response = client_with_settings.patch(
        "/api/settings",
        json={"agent_settings_diff": {"acp_model": "some-model"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agent_settings"]["acp_command"] == ["my-cli"]
    assert body["agent_settings"]["acp_args"] == ["--foo"]
    assert body["agent_settings"]["acp_model"] == "some-model"


# ── 机密 CRUD 测试 ──────────────────────────────────────────────────


def test_list_secrets_empty(client_with_settings):
    """当不存在机密时，GET /api/settings/secrets 返回空列表。"""
    response = client_with_settings.get("/api/settings/secrets")

    assert response.status_code == 200
    body = response.json()
    assert body["secrets"] == []


def test_create_and_list_secrets(client_with_settings):
    """PUT /api/settings/secrets 创建机密，GET 列出它。"""
    # 创建一个机密
    create_response = client_with_settings.put(
        "/api/settings/secrets",
        json={"name": "MY_SECRET", "value": "secret-value", "description": "Test"},
    )

    assert create_response.status_code == 200
    assert create_response.json()["name"] == "MY_SECRET"
    assert create_response.json()["description"] == "Test"

    # 列表机密（应不包含值）
    list_response = client_with_settings.get("/api/settings/secrets")

    assert list_response.status_code == 200
    secrets = list_response.json()["secrets"]
    assert len(secrets) == 1
    assert secrets[0]["name"] == "MY_SECRET"
    assert secrets[0]["description"] == "Test"
    assert "value" not in secrets[0]


@pytest.mark.parametrize("value", ["", " \t ", REDACTED_SECRET_VALUE])
def test_create_secret_rejects_unusable_value(client_with_settings, value):
    response = client_with_settings.put(
        "/api/settings/secrets",
        json={"name": "MY_SECRET", "value": value},
    )

    assert response.status_code == 422
    assert client_with_settings.get("/api/settings/secrets").json()["secrets"] == []
    assert (
        client_with_settings.get("/api/settings/secrets/MY_SECRET").status_code == 404
    )


@pytest.mark.parametrize("value", ["", " \t ", REDACTED_SECRET_VALUE])
def test_secret_upsert_rejects_unusable_value_without_changing_existing(
    client_with_settings, value
):
    created = client_with_settings.put(
        "/api/settings/secrets",
        json={
            "name": "MY_SECRET",
            "value": "original-value",
            "description": "Original",
        },
    )
    assert created.status_code == 200

    response = client_with_settings.put(
        "/api/settings/secrets",
        json={"name": "MY_SECRET", "value": value, "description": "Updated"},
    )

    assert response.status_code == 422
    stored = client_with_settings.get("/api/settings/secrets/MY_SECRET")
    assert stored.status_code == 200
    assert stored.text == "original-value"
    assert client_with_settings.get("/api/settings/secrets").json()["secrets"] == [
        {"name": "MY_SECRET", "description": "Original"}
    ]


def test_list_secrets_scoped_by_agent_profile(client_with_settings):
    for name in ("ALLOWED", "EXCLUDED"):
        client_with_settings.put(
            "/api/settings/secrets", json={"name": name, "value": "value"}
        )
    create = client_with_settings.post(
        "/api/agent-profiles/scoped",
        json={"llm_profile_ref": "default", "secret_refs": ["ALLOWED"]},
    )
    assert create.status_code == 201
    profile_id = client_with_settings.get("/api/agent-profiles/scoped").json()[
        "profile"
    ]["id"]

    response = client_with_settings.get(
        "/api/settings/secrets", params={"agent_profile_id": profile_id}
    )

    assert response.status_code == 200
    assert [secret["name"] for secret in response.json()["secrets"]] == ["ALLOWED"]


def test_list_secrets_rejects_unknown_agent_profile(client_with_settings):
    response = client_with_settings.get(
        "/api/settings/secrets", params={"agent_profile_id": "missing"}
    )

    assert response.status_code == 404


def test_list_secrets_unloadable_agent_profile_is_400(
    client_with_settings, temp_persistence_dir
):
    """范围界定配置文件不再验证答案 400，因为
    智能体-配置文件路由确实如此，而不是未处理的 500。"""
    create = client_with_settings.post(
        "/api/agent-profiles/broken",
        json={"llm_profile_ref": "default", "secret_refs": ["ALLOWED"]},
    )
    assert create.status_code == 201
    profile_id = client_with_settings.get("/api/agent-profiles/broken").json()[
        "profile"
    ]["id"]
    path = temp_persistence_dir / "agent-profiles" / "broken.json"
    data = json.loads(path.read_text())
    data["secret_refs"] = "ALLOWED"
    path.write_text(json.dumps(data))
    assert client_with_settings.get("/api/agent-profiles/broken").status_code == 400

    response = client_with_settings.get(
        "/api/settings/secrets", params={"agent_profile_id": profile_id}
    )

    assert response.status_code == 400
    assert "Failed to load profile" in response.json()["detail"]


def test_list_secrets_busy_agent_profile_store_is_503(
    client_with_settings, monkeypatch
):
    """智能体配置文件存储上的锁超时回答 503，而不是 500。"""
    store = get_agent_profile_store()

    def _timeout(*_args, **_kwargs):
        raise TimeoutError("Agent profile store lock acquisition timed out")

    monkeypatch.setattr(store, "name_for_id", _timeout)

    response = client_with_settings.get(
        "/api/settings/secrets",
        params={"agent_profile_id": "00000000-0000-4000-8000-0000000000f1"},
    )

    assert response.status_code == 503
    assert response.json()["exception"] == "503: Profile store is busy. Please retry."


def test_get_secret_value(client_with_settings):
    """GET /api/settings/secrets/{name} 返回原始机密值。"""
    # 创建一个机密
    client_with_settings.put(
        "/api/settings/secrets",
        json={"name": "MY_SECRET", "value": "secret-value-123"},
    )

    # 获取机密值
    response = client_with_settings.get("/api/settings/secrets/MY_SECRET")

    assert response.status_code == 200
    assert response.text == "secret-value-123"
    assert response.headers["content-type"] == "text/plain; charset=utf-8"


def test_get_secret_value_not_found(client_with_settings):
    """对于不存在的机密，GET /api/settings/secrets/{name} 返回 404。"""
    response = client_with_settings.get("/api/settings/secrets/NONEXISTENT")

    assert response.status_code == 404


def test_delete_secret(client_with_settings):
    """DELETE /api/settings/secrets/{name} 删除机密。"""
    # 创建一个机密
    client_with_settings.put(
        "/api/settings/secrets",
        json={"name": "MY_SECRET", "value": "secret-value"},
    )

    # 删除它
    delete_response = client_with_settings.delete("/api/settings/secrets/MY_SECRET")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    # 确认它已经消失
    get_response = client_with_settings.get("/api/settings/secrets/MY_SECRET")
    assert get_response.status_code == 404


def test_secret_name_validation(client_with_settings):
    """PUT /api/settings/secrets 验证机密名称格式。"""
    # 无效：以数字开头
    response = client_with_settings.put(
        "/api/settings/secrets",
        json={"name": "123_invalid", "value": "test"},
    )
    assert response.status_code == 422

    # 无效：包含特殊字符
    response = client_with_settings.put(
        "/api/settings/secrets",
        json={"name": "invalid-name", "value": "test"},
    )
    assert response.status_code == 422

    # 有效：以字母、字母数字+下划线开头
    response = client_with_settings.put(
        "/api/settings/secrets",
        json={"name": "VALID_NAME_123", "value": "test"},
    )
    assert response.status_code == 200


# ── PATCH 验证及错误处理测试 ────────────────────────────


def test_patch_settings_validation_error_returns_422(client_with_settings):
    """PATCH /api/settings 包含无效数据返回 422。"""
    # 无效：负数max_iterations
    response = client_with_settings.patch(
        "/api/settings",
        json={"conversation_settings_diff": {"max_iterations": -5}},
    )
    assert response.status_code == 422
    # 应清理错误消息（不公开机密）
    assert response.json()["detail"] == "Settings validation failed"


def test_patch_settings_validation_error_does_not_leak_secrets(client_with_settings):
    """PATCH 验证错误不会泄漏错误消息中的机密值。"""
    # 尝试使用无效的模型值更新（会导致验证失败） 这个测试即使在验证期间内存中有API键，也
    # 不会出现在错误消息中
    #
    response = client_with_settings.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "llm": {
                    "api_key": "sk-secret-value",
                    "model": "",
                }  # 空模型无效
            }
        },
    )
    # 应返回 422 并包含已清理的消息
    assert response.status_code == 422
    # 应清理错误消息 - 不包含机密值
    error_detail = response.json()["detail"]
    assert "sk-secret-value" not in error_detail
    # 它应该是通用的清理消息
    assert error_detail == "Settings validation failed"


def test_secret_upsert_updates_existing(client_with_settings):
    """PUT /api/settings/secrets 更新现有机密（更新插入行为）。"""
    # 创建初始机密
    client_with_settings.put(
        "/api/settings/secrets",
        json={
            "name": "MY_SECRET",
            "value": "original-value",
            "description": "Original",
        },
    )

    # 更新机密（相同名称，新值）
    update_response = client_with_settings.put(
        "/api/settings/secrets",
        json={"name": "MY_SECRET", "value": "updated-value", "description": "Updated"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["description"] == "Updated"

    # 验证值已更新
    get_response = client_with_settings.get("/api/settings/secrets/MY_SECRET")
    assert get_response.status_code == 200
    assert get_response.text == "updated-value"
    assert client_with_settings.get("/api/settings/secrets").json()["secrets"] == [
        {"name": "MY_SECRET", "description": "Updated"}
    ]


def test_secret_name_validation_on_get(client_with_settings):
    """GET /api/settings/secrets/{name} 验证名称格式。"""
    # 名称格式无效
    response = client_with_settings.get("/api/settings/secrets/123_invalid")
    assert response.status_code == 422


def test_secret_name_validation_on_delete(client_with_settings):
    """DELETE /api/settings/secrets/{name} 验证名称格式。"""
    # 名称格式无效
    response = client_with_settings.delete("/api/settings/secrets/invalid-name")
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs"),
    [
        ("get", "/api/settings/secrets/{name}", {}),
        ("delete", "/api/settings/secrets/{name}", {}),
        ("put", "/api/settings/secrets", {"json": {"name": "1bad", "value": "x"}}),
    ],
)
def test_secret_routes_document_the_invalid_name_status(
    client_with_settings, method, path, request_kwargs
):
    """OpenAPI 描述命名无效的机密名称所获得的状态。"""
    url = path.replace("{name}", "1bad")
    response = client_with_settings.request(method.upper(), url, **request_kwargs)
    assert response.status_code == 422

    description = client_with_settings.get("/openapi.json").json()["paths"][path][
        method
    ]["description"]
    assert "422 if" in description
    assert "400" not in description


# ── 并发更新测试────────────────────────────────────────────────


def test_concurrent_patch_updates_preserve_data(client_with_settings):
    """PATCH /api/settings 处理并发更新而不丢失数据。

    测试多个连续的 PATCH 请求不会因文件锁定机制中的竞态条件而损坏设置或丢失更新。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 初始化设置
    client_with_settings.patch(
        "/api/settings",
        json={"agent_settings_diff": {"llm": {"model": "initial-model"}}},
    )

    results = []
    errors = []

    def update_settings(model_name: str):
        """发出 PATCH 请求来更新模型。"""
        try:
            response = client_with_settings.patch(
                "/api/settings",
                json={"agent_settings_diff": {"llm": {"model": model_name}}},
            )
            return (model_name, response.status_code)
        except Exception as e:
            return (model_name, str(e))

    # 运行并发次更新
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(update_settings, f"model-{i}") for i in range(10)]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if result[1] != 200:
                errors.append(result)

    # 所有请求都应该成功（文件锁定应该序列化）
    assert len(errors) == 0, f"Some requests failed: {errors}"

    # 最终状态应该一致（模型值之一）
    final_response = client_with_settings.get("/api/settings")
    assert final_response.status_code == 200
    final_model = final_response.json()["agent_settings"]["llm"]["model"]
    # 最终值应该是我们设置的值之一（未损坏）
    assert final_model.startswith("model-"), f"Unexpected model value: {final_model}"


# ── 错误处理测试────────────────────────────────────────────────────


def test_get_settings_encrypted_mode_without_cipher_returns_503(temp_persistence_dir):
    """GET /api/settings 使用 X-Expose-机密：不使用密码加密返回 503。

    当未设置 OH_SECRET_KEY 时，config.cipher 为 None，并且请求加密模式应该会快速失败
    并出现明显错误（503 服务不可用）。
    """
    # 创建配置 WITHOUT secret_key（密码为 None）
    config = Config(
        static_files_path=None,
        session_api_keys=[],
        secret_key=None,  # 没有密码！
    )
    client = TestClient(create_app(config))

    # 首先，验证我们可以创建设置（明文不需要密码）
    # 注意：如果没有密码，我们需要手动创建一个设置文件
    store = FileSettingsStore(persistence_dir=temp_persistence_dir, cipher=None)
    settings = PersistedSettings()
    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    settings.agent_settings.llm.api_key = SecretStr("sk-test-secret-key")
    store.save(settings)

    # 现在请求加密模式 - 应该会失败，因为没有密码
    response = client.get("/api/settings", headers={"X-Expose-Secrets": "encrypted"})

    # 应返回 503（服务不可用 - 未配置加密）
    assert response.status_code == 503
    body = response.json()
    # 错误消息可能是“详细”或“异常”，具体取决于错误处理程序配置
    error_text = body.get("detail", "") + body.get("exception", "")
    assert "OH_SECRET_KEY" in error_text


def test_patch_settings_corrupted_file_returns_409(
    client_with_settings, temp_persistence_dir
):
    """当设置文件损坏时，PATCH /api/settings 返回 409。

    测试捕获损坏或加密密钥不匹配的 RuntimeError 处理路径。
    """
    # 首先初始化有效设置
    client_with_settings.patch(
        "/api/settings",
        json={"agent_settings_diff": {"llm": {"model": "gpt-4"}}},
    )

    # 直接损坏设置文件
    settings_file = temp_persistence_dir / "settings.json"
    settings_file.write_text("{ this is not valid JSON !!!}")

    # 尝试更新 - 应失败并显示 409（检测到损坏）
    response = client_with_settings.patch(
        "/api/settings",
        json={"agent_settings_diff": {"llm": {"model": "gpt-4o"}}},
    )

    # store.update() 中的 RuntimeError 应该被捕获并返回为 409
    assert response.status_code == 409
    assert "corrupted" in response.json()["detail"].lower()


# ── 损坏的机密个文件测试 ──────────────────────────────────────────────


def test_create_secret_corrupted_file_returns_500(
    client_with_settings, temp_persistence_dir
):
    """当机密文件损坏时，PUT /api/settings/secrets 返回 500。

    测试当 set_secret() 遇到损坏的机密文件时是否触发数据丢失保护路径。
    """
    # 创建初始机密
    client_with_settings.put(
        "/api/settings/secrets",
        json={"name": "MY_SECRET", "value": "test"},
    )

    # 损坏机密文件
    secrets_file = temp_persistence_dir / "secrets.json"
    secrets_file.write_text("{ corrupted !!!}")

    # 尝试创建新的机密 - 应该无法防止数据丢失
    response = client_with_settings.put(
        "/api/settings/secrets",
        json={"name": "OTHER_SECRET", "value": "value"},
    )

    assert response.status_code == 500


def test_delete_secret_corrupted_file_returns_500(
    client_with_settings, temp_persistence_dir
):
    """当机密文件损坏时，DELETE /api/settings/secrets 返回 500。

    测试当 delete_secret() 遇到损坏的机密文件时是否触发数据丢失保护路径。
    """
    # 创建初始机密
    client_with_settings.put(
        "/api/settings/secrets",
        json={"name": "MY_SECRET", "value": "test"},
    )

    # 损坏机密文件
    secrets_file = temp_persistence_dir / "secrets.json"
    secrets_file.write_text("{ corrupted !!!}")

    # 尝试删除机密 - 应该无法防止数据丢失
    response = client_with_settings.delete("/api/settings/secrets/MY_SECRET")

    assert response.status_code == 500
