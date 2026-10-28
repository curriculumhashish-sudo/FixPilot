from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from openhands.sdk.extensions.installation.interface import ExtensionProtocol


class InstallationInfo(BaseModel):
    """单个已安装扩展的元数据记录。

    存储（按名称键入）``InstallationMetadata`` 和已持久化内到安装目录中的
    ``.installed.json`` 文件。
    """

    name: str = Field(description="Extension name")
    version: str = Field(default="", description="Extension version")
    description: str = Field(default="", description="Extension description")

    enabled: bool = Field(default=True, description="Whether the extension is enabled")

    source: str = Field(description="Original source (e.g., 'github:owner/repo')")
    requested_ref: str | None = Field(
        default=None,
        description=(
            "Branch, tag, or commit requested at install time. None means no "
            "ref was requested (tracking the source's default branch)."
        ),
    )
    resolved_ref: str | None = Field(
        default=None, description="Resolved git commit SHA (for version pinning)"
    )
    repo_path: str | None = Field(
        default=None,
        description="Subdirectory path within the repository (for monorepos)",
    )

    installed_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 timestamp of installation",
    )
    install_path: Path = Field(description="Path where the extension is installed")

    @staticmethod
    def from_extension(
        extension: ExtensionProtocol,
        source: str,
        install_path: Path,
        requested_ref: str | None = None,
        resolved_ref: str | None = None,
        repo_path: str | None = None,
    ) -> InstallationInfo:
        """从扩展创建 InstallationInfo 并安装它上下文。

        Args:
            extension: 任何满足``ExtensionProtocol``的对象。
            source: 原始源字符串 (e.g. ``"github:owner/repo"``).
            install_path: 扩展被复制到的文件系统路径。
            requested_ref: 安装时请求的分支、标记或提交，
                if applicable.
            resolved_ref: 已解决 git commit SHA（如果适用）。
            repo_path: 单体仓库内的子目录（如果适用）。
        """
        return InstallationInfo(
            name=extension.name,
            version=extension.version,
            description=extension.description or "",
            source=source,
            requested_ref=requested_ref,
            resolved_ref=resolved_ref,
            repo_path=repo_path,
            install_path=install_path,
        )
