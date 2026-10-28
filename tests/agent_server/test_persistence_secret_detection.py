"""has_any_secret 测试：通过真实的序列化管道检测机密承载字段，而不是硬编码的字段检查
表。
"""

import logging
import tempfile
import warnings
from base64 import urlsafe_b64encode
from pathlib import Path

import pytest
from pydantic import SecretStr

from openhands.agent_server.persistence import (
    CustomSecret,
    FileSecretsStore,
    FileSettingsStore,
    PersistedSettings,
    Secrets,
)
from openhands.sdk.settings import ACPAgentSettings
from openhands.sdk.utils.cipher import Cipher


@pytest.fixture
def persistence_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def cipher():
    return Cipher(urlsafe_b64encode(b"a" * 32).decode("ascii"))


def test_has_any_secret_detects_llm_api_key():
    settings = PersistedSettings.model_validate(
        {"agent_settings": {"llm": {"model": "gpt-4o", "api_key": "sk-test"}}}
    )
    assert settings.has_any_secret


def test_has_any_secret_detects_critic_api_key():
    """critic_api_key 是独立于 llm.api_key 的机密。"""
    settings = PersistedSettings.model_validate(
        {"agent_settings": {"verification": {"critic_api_key": "sk-critic"}}}
    )
    assert settings.has_any_secret


def test_has_any_secret_detects_mcp_server_secret():
    settings = PersistedSettings.model_validate(
        {
            "agent_settings": {
                "mcp_config": {
                    "mcpServers": {
                        "github": {
                            "command": "uvx",
                            "args": ["mcp-server-github"],
                            "env": {"GITHUB_TOKEN": "ghp-test"},
                        }
                    }
                }
            }
        }
    )
    assert settings.has_any_secret


def test_has_any_secret_detects_agent_context_secret():
    """agent_context.secrets 值为 REST （仅机密形状的）
    在序列化时间通过他们自己的场序列化器），所以天真的isinstance(v, SecretStr)步行会
    错过这一点 - 仍然必须被抓住。
    """
    settings = PersistedSettings.model_validate(
        {"agent_settings": {"agent_context": {"secrets": {"MY_TOKEN": "sk-ctx"}}}}
    )
    assert settings.has_any_secret


def test_has_any_secret_false_for_empty_settings():
    assert not PersistedSettings().has_any_secret


def test_secrets_has_any_secret_detects_custom_secret():
    secrets = Secrets(
        custom_secrets={
            "MY_SECRET": CustomSecret(name="MY_SECRET", secret=SecretStr("sk-test"))
        }
    )
    assert secrets.has_any_secret


def test_secrets_has_any_secret_false_for_empty_secrets():
    assert not Secrets().has_any_secret


def test_settings_save_warns_for_critic_key_only_without_cipher(
    persistence_dir, caplog
):
    """回归测试：在has_any_secret之前，明文警告是
    单独对 llm_api_key_is_set 进行门控，因此仅 critic_api_key 的设置对象根本不会触发
    任何警告。
    """
    caplog.set_level(logging.WARNING)
    store = FileSettingsStore(persistence_dir=persistence_dir)
    settings = PersistedSettings.model_validate(
        {"agent_settings": {"verification": {"critic_api_key": "sk-critic"}}}
    )

    store.save(settings)

    assert "PLAINTEXT" in caplog.text


def test_settings_save_no_warning_when_no_secrets_present(persistence_dir, caplog):
    caplog.set_level(logging.WARNING)
    store = FileSettingsStore(persistence_dir=persistence_dir)

    store.save(PersistedSettings())

    assert "PLAINTEXT" not in caplog.text


def test_settings_save_with_cipher_round_trips_critic_key(persistence_dir, cipher):
    store = FileSettingsStore(persistence_dir=persistence_dir, cipher=cipher)
    settings = PersistedSettings.model_validate(
        {"agent_settings": {"verification": {"critic_api_key": "sk-critic"}}}
    )

    store.save(settings)

    reloaded = store.load()
    assert reloaded is not None
    assert reloaded.has_any_secret


def test_secrets_save_warns_without_cipher(persistence_dir, caplog):
    caplog.set_level(logging.WARNING)
    store = FileSecretsStore(persistence_dir=persistence_dir)
    secrets = Secrets(
        custom_secrets={
            "MY_SECRET": CustomSecret(name="MY_SECRET", secret=SecretStr("sk-test"))
        }
    )

    store.save(secrets)

    assert "PLAINTEXT" in caplog.text


def test_llm_api_key_is_set_is_false_for_acp_settings():
    settings = PersistedSettings(agent_settings=ACPAgentSettings())

    with warnings.catch_warnings():
        warnings.filterwarnings("error", message="ACPAgentSettings.llm")
        assert settings.llm_api_key_is_set is False
