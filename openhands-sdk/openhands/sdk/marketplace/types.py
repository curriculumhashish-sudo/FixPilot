"""Marketplace 模块的类型定义。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from openhands.sdk.logger import get_logger
from openhands.sdk.plugin.types import (
    HooksConfigDict,
    LspServersDict,
    McpServersDict,
    PluginAuthor,
    PluginManifest,
)


logger = get_logger(__name__)

# 用于检查市场清单的目录
MARKETPLACE_MANIFEST_DIRS = [".plugin", ".claude-plugin"]
MARKETPLACE_MANIFEST_FILE = "marketplace.json"


class MarketplaceOwner(BaseModel):
    """市场的所有者信息。

    所有者代表负责市场的维护者或团队。
    """

    name: str = Field(description="Name of the maintainer or team")
    email: str | None = Field(
        default=None, description="Contact email for the maintainer"
    )


class MarketplacePluginSource(BaseModel):
    """非本地源的插件源规范。

    支持GitHub仓库和通用的gitURLs。
    """

    source: str = Field(description="Source type: 'github' or 'url'")
    repo: str | None = Field(
        default=None, description="GitHub repository in 'owner/repo' format"
    )
    url: str | None = Field(default=None, description="Git URL for 'url' source type")
    ref: str | None = Field(
        default=None, description="Branch, tag, or commit reference"
    )
    path: str | None = Field(
        default=None, description="Subdirectory path within the repository"
    )

    model_config = {"extra": "allow"}

    @model_validator(mode="after")
    def validate_source_fields(self) -> MarketplacePluginSource:
        """根据源类型验证是否存在必填字段。"""
        if self.source == "github" and not self.repo:
            raise ValueError("GitHub source requires 'repo' field")
        if self.source == "url" and not self.url:
            raise ValueError("URL source requires 'url' field")
        return self


class MarketplaceEntry(BaseModel):
    """市场条目的基类（插件和技能）。

    插件和技能都是指向目录的指针：
    - 插件目录包含：plugin.json、skills/、commands/、agents/等。
    - 技能目录包含：SKILL.md 和可选的 script/、references/、assets/

    源是字符串路径（本地路径或 GitHub URL）。
    """

    name: str = Field(description="Identifier (kebab-case, no spaces)")
    source: str = Field(description="Path to directory (local path or GitHub URL)")
    description: str | None = Field(default=None, description="Brief description")
    version: str | None = Field(default=None, description="Version")
    author: PluginAuthor | None = Field(default=None, description="Author information")
    category: str | None = Field(default=None, description="Category for organization")
    homepage: str | None = Field(
        default=None, description="Homepage or documentation URL"
    )

    model_config = {"extra": "allow", "populate_by_name": True}

    @field_validator("author", mode="before")
    @classmethod
    def _parse_author(cls, v: Any) -> Any:
        if isinstance(v, str):
            return PluginAuthor.from_string(v)
        return v


class MarketplacePluginEntry(MarketplaceEntry):
    """市场中的插件入口。

    使用 Claude Code 兼容性字段扩展 MarketplaceEntry 以实现内联插件定义（当 strict=
    False 时）。

    插件支持字符串源和复杂的源对象（MarketplacePluginSource）GitHub/git URLs，其中
    ref 和 path。
    """

    # 覆盖源以允许插件使用复杂的源对象
    source: str | MarketplacePluginSource = Field(  # type: ignore[assignment]
        description="Path to plugin directory or source object for GitHub/git"
    )

    # 插件特定字段
    entry_command: str | None = Field(
        default=None,
        description=(
            "Default command to invoke when launching this plugin. "
            "Should match a command name from the commands/ directory."
        ),
    )

    # 克劳德代码兼容性字段
    strict: bool = Field(
        default=True,
        description="If True, plugin source must contain plugin.json. "
        "If False, marketplace entry defines the plugin inline.",
    )
    commands: str | list[str] | None = Field(default=None)
    agents: str | list[str] | None = Field(default=None)
    hooks: str | HooksConfigDict | None = Field(default=None)
    mcp_config: McpServersDict | None = Field(default=None, alias="mcpServers")
    lsp_servers: LspServersDict | None = Field(default=None, alias="lspServers")

    # 附加元数据字段
    license: str | None = Field(default=None, description="SPDX license identifier")
    keywords: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    repository: str | None = Field(
        default=None, description="Source code repository URL"
    )

    @field_validator("source", mode="before")
    @classmethod
    def _parse_source(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return MarketplacePluginSource.model_validate(v)
        return v

    def to_plugin_manifest(self) -> PluginManifest:
        """转换为 PluginManifest（对于 strict=False 条目）。"""
        return PluginManifest(
            name=self.name,
            version=self.version or "1.0.0",
            description=self.description or "",
            author=self.author,
            entry_command=self.entry_command,
        )


class MarketplaceMetadata(BaseModel):
    """市场的可选元数据。"""

    description: str | None = Field(default=None)
    version: str | None = Field(default=None)

    model_config = {"extra": "allow", "populate_by_name": True}


class Marketplace(BaseModel):
    """列出可用插件和技能的插件市场。

    遵循 Claude Code 市场结构以实现兼容性，并附加一个用于独立技能参考的 `skills` 字段
    。

    marketplace.json 文件位于市场存储库根目录的 `.plugin/` 或 `.claude-plugin/` 目录
    中。

    Example:
    ```json
    {
        "name": "company-tools",
        "owner": {"name": "DevTools Team"},
        "plugins": [
            {"name": "formatter", "source": "./plugins/formatter"}
        ],
        "skills": [
            {"name": "github", "source": "./skills/github"}
        ]
    }
    ```
    """

    name: str = Field(
        description="Marketplace identifier (kebab-case, no spaces). "
        "Users see this when installing plugins: /plugin install tool@<marketplace>"
    )
    owner: MarketplaceOwner = Field(description="Marketplace maintainer information")
    description: str | None = Field(
        default=None,
        description="Brief marketplace description. Can also be in metadata.",
    )
    plugins: list[MarketplacePluginEntry] = Field(
        default_factory=list, description="List of available plugins"
    )
    skills: list[MarketplaceEntry] = Field(
        default_factory=list, description="List of standalone skills"
    )
    metadata: MarketplaceMetadata | None = Field(
        default=None, description="Optional marketplace metadata"
    )
    path: str | None = Field(
        default=None,
        description="Path to the marketplace directory (set after loading)",
    )

    model_config = {"extra": "allow"}

    @classmethod
    def load(cls, marketplace_path: str | Path) -> Marketplace:
        """从目录加载市场。

        在 .plugin/ 或 .claude-plugin/ 目录中查找 marketplace.json。

        Args:
            marketplace_path: 市场目录的路径。

        Returns:
            已加载 Marketplace 实例。

        Raises:
            FileNotFoundError: 如果市场目录或清单不存在。
            ValueError: 如果市场清单无效。
        """
        marketplace_dir = Path(marketplace_path).resolve()
        if not marketplace_dir.is_dir():
            raise FileNotFoundError(
                f"Marketplace directory not found: {marketplace_dir}"
            )

        # 查找 manifest 文件
        manifest_path = None
        for manifest_dir in MARKETPLACE_MANIFEST_DIRS:
            candidate = marketplace_dir / manifest_dir / MARKETPLACE_MANIFEST_FILE
            if candidate.exists():
                manifest_path = candidate
                break

        if manifest_path is None:
            dirs = " or ".join(MARKETPLACE_MANIFEST_DIRS)
            raise FileNotFoundError(
                f"Marketplace manifest not found. "
                f"Expected {MARKETPLACE_MANIFEST_FILE} in {dirs} "
                f"directory under {marketplace_dir}"
            )

        try:
            with open(manifest_path) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {manifest_path}: {e}") from e

        return cls.model_validate({**data, "path": str(marketplace_dir)})

    @classmethod
    def from_skills_dir(cls, marketplace_path: str | Path, name: str) -> Marketplace:
        """从普通的技能文件夹构建市场，无需清单。

        每个 ``<name>/SKILL.md`` 文件夹都成为一项独立技能：
        ``skills/`` 和 ``.skills/``，或者，当两者都不存在时，直接位于
        ``marketplace_path``，因此 ``repo_path`` 可以指向技能文件夹本身。 松散的
        Markdown 文件不会被读取，因此存储库的
         README 和文档永远不会成为技能。 找到None时结果没有技能。

        Args:
            marketplace_path: 存储库或技能文件夹的路径。
            name: 市场名称，因为没有清单可以提供。

        Returns:
            市场列出了已发现的技能，没有插件。
        """
        from openhands.sdk.skills import Skill
        from openhands.sdk.skills.utils import find_skill_md_directories

        marketplace_dir = Path(marketplace_path).resolve()
        skills_dirs = [
            path
            for path in (marketplace_dir / "skills", marketplace_dir / ".skills")
            if path.is_dir()
        ] or [marketplace_dir]

        entries: dict[str, MarketplaceEntry] = {}
        for skills_dir in skills_dirs:
            for skill_md in find_skill_md_directories(skills_dir, marketplace_dir):
                try:
                    skill = Skill.load(skill_md, strict=False)
                except Exception as e:
                    logger.warning(f"Failed to load skill from {skill_md}: {e}")
                    continue
                source = f"./{skill_md.parent.relative_to(marketplace_dir).as_posix()}"
                entry = entries.setdefault(
                    skill.name,
                    MarketplaceEntry(
                        name=skill.name,
                        source=source,
                        description=skill.description,
                    ),
                )
                if entry.source != source:
                    logger.warning(
                        f"Skill '{skill.name}' in {source} has the same name as "
                        f"the one in {entry.source}; keeping {entry.source}"
                    )

        return cls(
            name=name,
            owner=MarketplaceOwner(name=name),
            skills=list(entries.values()),
            path=str(marketplace_dir),
        )

    def get_plugin(self, name: str) -> MarketplacePluginEntry | None:
        """按名称获取插件条目。

        Args:
            name: 要查找的插件名称。

        Returns:
            如果找到则为 MarketplacePluginEntry，否则为 None。
        """
        for plugin in self.plugins:
            if plugin.name == name:
                return plugin
        return None

    def resolve_plugin_source(
        self, plugin: MarketplacePluginEntry
    ) -> tuple[str, str | None, str | None]:
        """将插件的源解析为完整路径或 URL。

        Returns:
            (源、引用、子路径) 的元组，其中：
            - source: 已解析的源字符串（路径或 URL）
            - ref: 分支、标记或提交引用（None 表示本地路径）
            - subpath: 存储库内的子目录路径（如果未指定，则为 None）
        """
        source = plugin.source

        # 处理复杂源对象(GitHub, git URLs)
        if isinstance(source, MarketplacePluginSource):
            if source.source == "github" and source.repo:
                return (f"github:{source.repo}", source.ref, source.path)
            if source.source == "url" and source.url:
                return (source.url, source.ref, source.path)
            raise ValueError(
                f"Invalid plugin source for '{plugin.name}': "
                f"source type '{source.source}' is missing required field"
            )

        # 绝对路径或 URLs - 保持不变
        if source.startswith(("/", "~")) or "://" in source:
            return (source, None, None)

        # 相对路径 - 根据市场路径（如果已知）进行解析
        if self.path:
            source = str(Path(self.path) / source.lstrip("./"))

        return (source, None, None)
