"""凭据基于 OAuth 的存储和检索 LLM 身份验证。"""

from __future__ import annotations

import json
import os
import time
import warnings
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from openhands.sdk.logger import get_logger
from openhands.sdk.utils.path import get_user_persistence_dir


logger = get_logger(__name__)


def get_credentials_dir() -> Path:
    """获取存储凭据的目录。

    返回用户持久化目录的``auth``子目录：
    当设置 ``OH_PERSISTENCE_DIR`` 时为 ``OH_PERSISTENCE_DIR/auth``，否则
    ``~/.openhands/auth``.
    """
    return get_user_persistence_dir() / "auth"


class OAuthCredentials(BaseModel):
    """OAuth 凭据用于基于订阅的 LLM 访问。"""

    type: Literal["oauth"] = "oauth"
    vendor: str = Field(description="The vendor/provider (e.g., 'openai')")
    access_token: str = Field(description="The OAuth access token")
    refresh_token: str = Field(description="The OAuth refresh token")
    expires_at: int = Field(
        description="Unix timestamp (ms) when the access token expires"
    )

    def is_expired(self) -> bool:
        """检查访问令牌是否已过期。"""
        # 添加 60 秒缓冲区以避免边缘情况添加 60 秒缓冲区以避免请求期间 token 过期的边缘
        # 情况
        #
        return self.expires_at < (int(time.time() * 1000) + 60_000)


class CredentialStore:
    """存储和检索 LLM 提供商的 OAuth 凭据。"""

    def __init__(self, credentials_dir: Path | None = None):
        """初始化凭据存储。

        Args:
            credentials_dir: 用于存储凭据的可选自定义目录。
                           默认为用户持久化目录的 ``auth`` 子目录（设置时为
                           ``OH_PERSISTENCE_DIR/auth``，否
                           则为 ``~/.openhands/auth``）。
        """
        self._credentials_dir = credentials_dir or get_credentials_dir()
        logger.info(f"Using credentials directory: {self._credentials_dir}")

    @property
    def credentials_dir(self) -> Path:
        """获取凭据目录，必要时创建它。"""
        self._credentials_dir.mkdir(parents=True, exist_ok=True)
        # 将目录权限设置为仅限所有者 (rwx------)
        if os.name != "nt":
            self._credentials_dir.chmod(0o700)
        return self._credentials_dir

    def _get_credentials_file(self, vendor: str) -> Path:
        """获取供应商的凭据文件的路径。"""
        return self.credentials_dir / f"{vendor}_oauth.json"

    def get(self, vendor: str) -> OAuthCredentials | None:
        """为供应商存储凭据。

        Args:
            vendor: 供应商/提供商名称（e.g., 'OpenAI'）

        Returns:
            OAuthCredentials（如果找到且有效），否则为 None
        """
        creds_file = self._get_credentials_file(vendor)
        if not creds_file.exists():
            return None

        try:
            with open(creds_file, encoding="utf-8") as f:
                data = json.load(f)
            return OAuthCredentials.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            # 无效的凭据文件，请将其删除
            creds_file.unlink(missing_ok=True)
            return None

    def save(self, credentials: OAuthCredentials) -> None:
        """为供应商保存凭据。

        Args:
            credentials: 要保存的 OAuth 凭据
        """
        creds_file = self._get_credentials_file(credentials.vendor)
        with open(creds_file, "w", encoding="utf-8") as f:
            json.dump(credentials.model_dump(), f, indent=2)
        # 设置限制性权限（所有者只读/写）
        # 注意：在 Windows 上，NTFS ACLs 应该使用
        if os.name != "nt":  # 不是Windows
            creds_file.chmod(0o600)
        else:
            warnings.warn(
                "File permissions on Windows should be manually restricted",
                stacklevel=2,
            )

    def delete(self, vendor: str) -> bool:
        """删除为供应商存储的凭据。

        Args:
            vendor: 供应商/提供商名称

        Returns:
            True 如果凭据已删除，False 如果它们不存在
        """
        creds_file = self._get_credentials_file(vendor)
        if creds_file.exists():
            creds_file.unlink()
            return True
        return False

    def update_tokens(
        self,
        vendor: str,
        access_token: str,
        refresh_token: str | None,
        expires_in: int,
    ) -> OAuthCredentials | None:
        """更新现有凭据的 token。

        Args:
            vendor: 供应商/提供商名称
            access_token: 新访问令牌
            refresh_token: 新刷新令牌（如果提供）
            expires_in: token 秒后到期

        Returns:
            已更新凭据，如果未找到现有凭据，则更新 None
        """
        existing = self.get(vendor)
        if existing is None:
            return None

        updated = OAuthCredentials(
            vendor=vendor,
            access_token=access_token,
            refresh_token=refresh_token or existing.refresh_token,
            expires_at=int(time.time() * 1000) + (expires_in * 1000),
        )
        self.save(updated)
        return updated
