"""设置和机密写入不得破坏存储在另一个键下的值。

回归测试 #5622：在密码密钥更改后，读取-修改-写入用于将不可解密的值加载为 ``None`` 并
将它们保存回 ``null``。
"""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config
from openhands.agent_server.persistence import (
    FileSecretsStore,
    FileSettingsStore,
    PersistedSettings,
    reencrypt_stale_stores,
    reset_stores,
)
from openhands.agent_server.persistence.models import SettingsUpdatePayload
from openhands.sdk.llm import LLM
from openhands.sdk.settings import OpenHandsAgentSettings
from openhands.sdk.utils.cipher import Cipher


KEY_A = "qa-cipher-key-a"
KEY_B = "qa-cipher-key-b"
LLM_KEY = "sk-test-original"
SECRET_VALUE = "token-original"


@pytest.fixture
def persistence_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        reset_stores()
        old_val = os.environ.get("OH_PERSISTENCE_DIR")
        os.environ["OH_PERSISTENCE_DIR"] = tmpdir
        yield Path(tmpdir)
        reset_stores()
        if old_val is not None:
            os.environ["OH_PERSISTENCE_DIR"] = old_val
        else:
            os.environ.pop("OH_PERSISTENCE_DIR", None)


def _apply(
    settings: PersistedSettings, payload: SettingsUpdatePayload
) -> PersistedSettings:
    settings.update(payload)
    return settings


def _seed(persistence_dir: Path) -> tuple[bytes, bytes]:
    """在KEY_A下存储一个LLM键和一个自定义机密； 返回原始文件。"""
    cipher = Cipher(KEY_A)
    settings_store = FileSettingsStore(persistence_dir, cipher=cipher)
    settings_store.update(
        lambda s: _apply(s, {"agent_settings_diff": {"llm": {"api_key": LLM_KEY}}})
    )
    secrets_store = FileSecretsStore(persistence_dir, cipher=cipher)
    secrets_store.set_secret("QA_TOKEN", SECRET_VALUE)
    return (
        (persistence_dir / "settings.json").read_bytes(),
        (persistence_dir / "secrets.json").read_bytes(),
    )


def _assert_original_key_reads_back(persistence_dir: Path) -> None:
    cipher = Cipher(KEY_A)
    settings = FileSettingsStore(persistence_dir, cipher=cipher).load()
    assert settings is not None
    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    llm = settings.agent_settings.llm
    assert isinstance(llm, LLM)
    assert llm.api_key is not None
    assert isinstance(llm.api_key, SecretStr)
    assert llm.api_key.get_secret_value() == LLM_KEY
    secrets_store = FileSecretsStore(persistence_dir, cipher=cipher)
    assert secrets_store.get_secret("QA_TOKEN") == SECRET_VALUE


def test_settings_update_refuses_under_wrong_cipher(persistence_dir):
    settings_before, _ = _seed(persistence_dir)
    store = FileSettingsStore(persistence_dir, cipher=Cipher(KEY_B))

    with pytest.raises(RuntimeError, match="different key"):
        store.update(lambda s: _apply(s, {"misc_settings_diff": {"qa_note": True}}))

    assert (persistence_dir / "settings.json").read_bytes() == settings_before
    _assert_original_key_reads_back(persistence_dir)


@pytest.mark.parametrize(
    "write",
    [
        lambda store: store.set_secret("QA_OTHER", "x"),
        lambda store: store.delete_secret("QA_TOKEN"),
        lambda store: store.load_versioned_secret("QA_TOKEN"),
    ],
    ids=["set_secret", "delete_secret", "load_versioned_secret"],
)
def test_secrets_writes_refuse_under_wrong_cipher(persistence_dir, write):
    _, secrets_before = _seed(persistence_dir)
    store = FileSecretsStore(persistence_dir, cipher=Cipher(KEY_B))

    with pytest.raises(RuntimeError, match="different key"):
        write(store)

    assert (persistence_dir / "secrets.json").read_bytes() == secrets_before
    _assert_original_key_reads_back(persistence_dir)


def test_reads_stay_lenient_under_wrong_cipher(persistence_dir):
    _seed(persistence_dir)
    cipher = Cipher(KEY_B)

    settings = FileSettingsStore(persistence_dir, cipher=cipher).load()
    assert settings is not None
    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    assert isinstance(settings.agent_settings.llm, LLM)
    assert settings.agent_settings.llm.api_key is None
    secrets_store = FileSecretsStore(persistence_dir, cipher=cipher)
    assert secrets_store.load() is not None
    assert secrets_store.get_secret("QA_TOKEN") is None


def test_api_writes_refuse_under_wrong_cipher(persistence_dir):
    settings_before, secrets_before = _seed(persistence_dir)
    config = Config(
        static_files_path=None,
        session_api_keys=[],
        secret_key=SecretStr(KEY_B),
    )
    client = TestClient(create_app(config))

    patch = client.patch(
        "/api/settings", json={"misc_settings_diff": {"qa_note": True}}
    )
    assert patch.status_code == 409
    put = client.put("/api/settings/secrets", json={"name": "QA_OTHER", "value": "x"})
    assert put.status_code == 500
    delete = client.delete("/api/settings/secrets/QA_TOKEN")
    assert delete.status_code == 500
    for response in (patch, put, delete):
        assert "gAAAAA" not in response.text

    # 读错键下依然答案。
    assert client.get("/api/settings").status_code == 200
    assert client.get("/api/settings/secrets").status_code == 200

    assert (persistence_dir / "settings.json").read_bytes() == settings_before
    assert (persistence_dir / "secrets.json").read_bytes() == secrets_before
    _assert_original_key_reads_back(persistence_dir)


# ── 密钥轮换：previous_secret_keys中列出的旧密钥──────────────

KEY_C = "qa-cipher-key-c"


def _rotated() -> Cipher:
    return Cipher(KEY_B, previous_keys=[KEY_A])


def _assert_readable_with(persistence_dir: Path, cipher: Cipher) -> None:
    """每个存储的值都严格加载（无 ``None``）在 ``cipher`` 下。"""
    settings = FileSettingsStore(persistence_dir, cipher=cipher).load(strict=True)
    assert settings is not None
    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    llm = settings.agent_settings.llm
    assert isinstance(llm, LLM)
    assert isinstance(llm.api_key, SecretStr)
    assert llm.api_key.get_secret_value() == LLM_KEY
    secrets = FileSecretsStore(persistence_dir, cipher=cipher).load(strict=True)
    assert secrets is not None
    secret = secrets.custom_secrets["QA_TOKEN"].secret
    assert secret is not None
    assert secret.get_secret_value() == SECRET_VALUE


def test_rotation_keeps_values_readable_and_reencrypts_on_save(persistence_dir):
    _seed(persistence_dir)
    cipher = _rotated()
    settings_store = FileSettingsStore(persistence_dir, cipher=cipher)
    secrets_store = FileSecretsStore(persistence_dir, cipher=cipher)

    # 在新密钥下读取可以看到旧密钥下保存的值。
    _assert_readable_with(persistence_dir, cipher)
    assert secrets_store.get_secret("QA_TOKEN") == SECRET_VALUE

    # 写入会在新密钥下遍历并重新加密所有内容。
    settings_store.update(
        lambda s: _apply(s, {"misc_settings_diff": {"qa_note": True}})
    )
    secrets_store.set_secret("QA_OTHER", "x")

    # 不再需要以前的密钥...
    _assert_readable_with(persistence_dir, Cipher(KEY_B))
    assert (
        FileSecretsStore(persistence_dir, cipher=Cipher(KEY_B)).get_secret("QA_OTHER")
        == "x"
    )
    # ... and the old key alone can no longer read anything.
    old = FileSettingsStore(persistence_dir, cipher=Cipher(KEY_A)).load()
    assert old is not None
    assert isinstance(old.agent_settings, OpenHandsAgentSettings)
    assert isinstance(old.agent_settings.llm, LLM)
    assert old.agent_settings.llm.api_key is None


def test_reencrypt_rewrites_only_stale_files(persistence_dir):
    settings_before, secrets_before = _seed(persistence_dir)

    # 错误的先前密钥：无法解密任何内容，也无法重写任何内容。
    wrong = Cipher(KEY_B, previous_keys=[KEY_C])
    assert FileSettingsStore(persistence_dir, cipher=wrong).reencrypt() is False
    assert FileSecretsStore(persistence_dir, cipher=wrong).reencrypt() is False
    assert (persistence_dir / "settings.json").read_bytes() == settings_before
    assert (persistence_dir / "secrets.json").read_bytes() == secrets_before

    cipher = _rotated()
    assert FileSettingsStore(persistence_dir, cipher=cipher).reencrypt() is True
    assert FileSecretsStore(persistence_dir, cipher=cipher).reencrypt() is True
    _assert_readable_with(persistence_dir, Cipher(KEY_B))

    # 现在一切都是最新的：第二遍将保留文件。
    settings_after = (persistence_dir / "settings.json").read_bytes()
    secrets_after = (persistence_dir / "secrets.json").read_bytes()
    assert FileSettingsStore(persistence_dir, cipher=cipher).reencrypt() is False
    assert FileSecretsStore(persistence_dir, cipher=cipher).reencrypt() is False
    assert (persistence_dir / "settings.json").read_bytes() == settings_after
    assert (persistence_dir / "secrets.json").read_bytes() == secrets_after


def test_reencrypt_stale_stores_at_startup(persistence_dir):
    _seed(persistence_dir)
    config = Config(
        static_files_path=None,
        session_api_keys=[],
        secret_key=SecretStr(KEY_B),
        previous_secret_keys=[SecretStr(KEY_A)],
    )
    reencrypt_stale_stores(config)
    _assert_readable_with(persistence_dir, Cipher(KEY_B))


def test_api_writes_succeed_after_rotation_with_previous_key(persistence_dir):
    _seed(persistence_dir)
    config = Config(
        static_files_path=None,
        session_api_keys=[],
        secret_key=SecretStr(KEY_B),
        previous_secret_keys=[SecretStr(KEY_A)],
    )
    client = TestClient(create_app(config))

    assert client.get("/api/settings").json()["llm_api_key_is_set"] is True
    assert client.get("/api/settings/secrets/QA_TOKEN").text == SECRET_VALUE
    patch = client.patch(
        "/api/settings", json={"misc_settings_diff": {"qa_note": True}}
    )
    assert patch.status_code == 200
    put = client.put("/api/settings/secrets", json={"name": "QA_OTHER", "value": "x"})
    assert put.status_code == 200
    delete = client.delete("/api/settings/secrets/QA_OTHER")
    assert delete.status_code == 200

    # 写入操作重新加密了这两个文件：现在仅用新密钥即可读取它们。
    reset_stores()
    client = TestClient(
        create_app(
            Config(
                static_files_path=None,
                session_api_keys=[],
                secret_key=SecretStr(KEY_B),
            )
        )
    )
    assert client.get("/api/settings").json()["llm_api_key_is_set"] is True
    assert client.get("/api/settings/secrets/QA_TOKEN").text == SECRET_VALUE
    assert (
        client.patch(
            "/api/settings", json={"misc_settings_diff": {"qa_note": False}}
        ).status_code
        == 200
    )


def test_api_refusal_names_previous_keys(persistence_dir):
    _seed(persistence_dir)
    config = Config(
        static_files_path=None,
        session_api_keys=[],
        secret_key=SecretStr(KEY_B),
        previous_secret_keys=[SecretStr(KEY_C)],
    )
    client = TestClient(create_app(config))
    patch = client.patch(
        "/api/settings", json={"misc_settings_diff": {"qa_note": True}}
    )
    assert patch.status_code == 409
    assert "OH_PREVIOUS_SECRET_KEYS" in patch.json()["detail"]
    put = client.put("/api/settings/secrets", json={"name": "QA_OTHER", "value": "x"})
    # 服务器屏蔽了 500 个详细信息； 该指导位于服务器日志中。
    assert put.status_code == 500
