"""测试凭据存储和检索。"""

import os
import time
from pathlib import Path

from openhands.sdk.llm.auth.credentials import (
    CredentialStore,
    OAuthCredentials,
    get_credentials_dir,
)


def test_oauth_credentials_model():
    """测试 OAuthCredentials 模型创建和验证。"""
    expires_at = int(time.time() * 1000) + 3600_000  # 1小时后
    creds = OAuthCredentials(
        vendor="openai",
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        expires_at=expires_at,
    )
    assert creds.vendor == "openai"
    assert creds.access_token == "test_access_token"
    assert creds.refresh_token == "test_refresh_token"
    assert creds.expires_at == expires_at
    assert creds.type == "oauth"


def test_oauth_credentials_is_expired():
    """测试 OAuthCredentials 过期检查。"""
    # 未过期（1 小时后）
    future_creds = OAuthCredentials(
        vendor="openai",
        access_token="test",
        refresh_token="test",
        expires_at=int(time.time() * 1000) + 3600_000,
    )
    assert not future_creds.is_expired()

    # 已过期（1 小时前）
    past_creds = OAuthCredentials(
        vendor="openai",
        access_token="test",
        refresh_token="test",
        expires_at=int(time.time() * 1000) - 3600_000,
    )
    assert past_creds.is_expired()


def test_get_credentials_dir_default(monkeypatch):
    """测试默认凭据目录。"""
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    creds_dir = get_credentials_dir()
    assert creds_dir == Path.home() / ".openhands" / "auth"


def test_get_credentials_dir_xdg(monkeypatch, tmp_path):
    """测试凭据目录忽略 XDG_DATA_HOME（使用 ~/.openhands/auth)."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    creds_dir = get_credentials_dir()
    # 实现使用 ~/.openhands/auth 而不管 XDG_DATA_HOME
    assert creds_dir == Path.home() / ".openhands" / "auth"


def test_credential_store_save_and_get(tmp_path):
    """测试保存和检索凭据。"""
    store = CredentialStore(credentials_dir=tmp_path)
    creds = OAuthCredentials(
        vendor="openai",
        access_token="test_access",
        refresh_token="test_refresh",
        expires_at=int(time.time() * 1000) + 3600_000,
    )

    store.save(creds)

    # 验证文件已创建
    creds_file = tmp_path / "openai_oauth.json"
    assert creds_file.exists()

    # 验证文件权限（所有者只读/写）
    if os.name != "nt":
        assert (creds_file.stat().st_mode & 0o777) == 0o600

    # 检索并验证
    retrieved = store.get("openai")
    assert retrieved is not None
    assert retrieved.vendor == creds.vendor
    assert retrieved.access_token == creds.access_token
    assert retrieved.refresh_token == creds.refresh_token
    assert retrieved.expires_at == creds.expires_at


def test_credential_store_get_nonexistent(tmp_path):
    """测试获取不存在的凭据。"""
    store = CredentialStore(credentials_dir=tmp_path)
    assert store.get("nonexistent") is None


def test_credential_store_get_invalid_json(tmp_path):
    """测试从无效的 JSON 文件获取凭据。"""
    store = CredentialStore(credentials_dir=tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)

    # 创建无效的 JSON 文件
    creds_file = tmp_path / "openai_oauth.json"
    creds_file.write_text("invalid json")

    # 应返回 None 并删除无效文件
    assert store.get("openai") is None
    assert not creds_file.exists()


def test_credential_store_delete(tmp_path):
    """测试删除凭据。"""
    store = CredentialStore(credentials_dir=tmp_path)
    creds = OAuthCredentials(
        vendor="openai",
        access_token="test",
        refresh_token="test",
        expires_at=int(time.time() * 1000) + 3600_000,
    )
    store.save(creds)

    # 删除并验证
    assert store.delete("openai") is True
    assert store.get("openai") is None

    # 再次删除应返回False
    assert store.delete("openai") is False


def test_credential_store_update_tokens(tmp_path):
    """测试现有凭据的更新 token。"""
    store = CredentialStore(credentials_dir=tmp_path)
    original = OAuthCredentials(
        vendor="openai",
        access_token="old_access",
        refresh_token="old_refresh",
        expires_at=int(time.time() * 1000) + 3600_000,
    )
    store.save(original)

    # 更新token
    updated = store.update_tokens(
        vendor="openai",
        access_token="new_access",
        refresh_token="new_refresh",
        expires_in=7200,  # 2小时
    )

    assert updated is not None
    assert updated.access_token == "new_access"
    assert updated.refresh_token == "new_refresh"

    # 验证已持久化
    retrieved = store.get("openai")
    assert retrieved is not None
    assert retrieved.access_token == "new_access"


def test_credential_store_update_tokens_keeps_refresh_if_not_provided(tmp_path):
    """如果未提供新的，则测试 update_tokens 是否保留旧的刷新令牌。"""
    store = CredentialStore(credentials_dir=tmp_path)
    original = OAuthCredentials(
        vendor="openai",
        access_token="old_access",
        refresh_token="original_refresh",
        expires_at=int(time.time() * 1000) + 3600_000,
    )
    store.save(original)

    # 更新无新内容刷新令牌
    updated = store.update_tokens(
        vendor="openai",
        access_token="new_access",
        refresh_token=None,
        expires_in=3600,
    )

    assert updated is not None
    assert updated.access_token == "new_access"
    assert updated.refresh_token == "original_refresh"


def test_credential_store_update_tokens_nonexistent(tmp_path):
    """测试更新 token 用于不存在的凭据。"""
    store = CredentialStore(credentials_dir=tmp_path)
    result = store.update_tokens(
        vendor="openai",
        access_token="new_access",
        refresh_token="new_refresh",
        expires_in=3600,
    )
    assert result is None
