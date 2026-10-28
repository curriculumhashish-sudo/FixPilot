"""测试市场加载功能。"""

from pathlib import Path

import pytest

from openhands.sdk.marketplace import (
    Marketplace,
    MarketplaceMetadata,
    MarketplaceOwner,
    MarketplacePluginEntry,
    MarketplacePluginSource,
)
from openhands.sdk.plugin import PluginAuthor


class TestMarketplaceOwner:
    """测试 MarketplaceOwner 模型。"""

    def test_basic_owner(self):
        """测试仅使用名称创建所有者。"""
        owner = MarketplaceOwner(name="DevTools Team")
        assert owner.name == "DevTools Team"
        assert owner.email is None

    def test_owner_with_email(self):
        """测试使用电子邮件创建所有者。"""
        owner = MarketplaceOwner(name="DevTools Team", email="devtools@example.com")
        assert owner.name == "DevTools Team"
        assert owner.email == "devtools@example.com"


class TestMarketplacePluginSource:
    """测试 MarketplacePluginSource 模型。"""

    def test_github_source(self):
        """测试GitHub源规范。"""
        source = MarketplacePluginSource(source="github", repo="owner/repo")
        assert source.source == "github"
        assert source.repo == "owner/repo"
        assert source.url is None

    def test_url_source(self):
        """测试 Git URL 源规范。"""
        source = MarketplacePluginSource(
            source="url", url="https://gitlab.com/org/repo.git"
        )
        assert source.source == "url"
        assert source.url == "https://gitlab.com/org/repo.git"
        assert source.repo is None

    def test_source_with_ref(self):
        """使用分支/标签引用测试源。"""
        source = MarketplacePluginSource(
            source="github", repo="owner/repo", ref="v1.0.0"
        )
        assert source.ref == "v1.0.0"

    def test_source_with_path(self):
        """使用子目录路径测试源。"""
        source = MarketplacePluginSource(
            source="github", repo="owner/monorepo", path="plugins/my-plugin"
        )
        assert source.path == "plugins/my-plugin"

    def test_github_source_missing_repo_raises_error(self):
        """测试没有存储库的 GitHub 源会引发验证错误。"""
        with pytest.raises(ValueError, match="GitHub source requires 'repo' field"):
            MarketplacePluginSource(source="github")

    def test_url_source_missing_url_raises_error(self):
        """测试没有 url 的 URL 源是否会引发验证错误。"""
        with pytest.raises(ValueError, match="URL source requires 'url' field"):
            MarketplacePluginSource(source="url")


class TestMarketplacePluginEntry:
    """测试 MarketplacePluginEntry 模型。"""

    def test_basic_entry(self):
        """使用字符串源测试基本插件条目。"""
        entry = MarketplacePluginEntry(name="my-plugin", source="./plugins/my-plugin")
        assert entry.name == "my-plugin"
        assert entry.source == "./plugins/my-plugin"
        assert entry.description is None
        assert entry.version is None

    def test_entry_with_all_fields(self):
        """使用所有可选字段测试插件条目。"""
        entry = MarketplacePluginEntry(
            name="enterprise-tools",
            source="./plugins/enterprise",
            description="Enterprise workflow tools",
            version="2.1.0",
            author=PluginAuthor(name="Enterprise Team", email="team@example.com"),
            homepage="https://docs.example.com",
            repository="https://github.com/company/enterprise-plugin",
            license="MIT",
            keywords=["enterprise", "workflow"],
            category="productivity",
            tags=["automation"],
            strict=False,
        )
        assert entry.name == "enterprise-tools"
        assert entry.description == "Enterprise workflow tools"
        assert entry.version == "2.1.0"
        assert entry.author is not None and entry.author.name == "Enterprise Team"
        assert entry.homepage == "https://docs.example.com"
        assert entry.license == "MIT"
        assert entry.keywords == ["enterprise", "workflow"]
        assert entry.category == "productivity"
        assert entry.tags == ["automation"]
        assert entry.strict is False

    def test_entry_with_string_author(self):
        """测试 model_validate 将作者作为字符串处理。"""
        entry = MarketplacePluginEntry.model_validate(
            {
                "name": "my-plugin",
                "source": "./plugins/my-plugin",
                "author": "John Doe <john@example.com>",
            }
        )
        assert entry.author is not None
        assert entry.author.name == "John Doe"
        assert entry.author.email == "john@example.com"

    def test_entry_with_github_source(self):
        """测试 model_validate 处理 GitHub 源对象。"""
        entry = MarketplacePluginEntry.model_validate(
            {
                "name": "github-plugin",
                "source": {"source": "github", "repo": "company/plugin"},
            }
        )
        assert isinstance(entry.source, MarketplacePluginSource)
        assert entry.source.source == "github"
        assert entry.source.repo == "company/plugin"

    def test_entry_camel_case_fields(self):
        """测试 model_validate 处理 camelCase 字段名称。"""
        entry = MarketplacePluginEntry.model_validate(
            {
                "name": "mcp-plugin",
                "source": "./plugins/mcp",
                "mcpServers": {"server1": {"command": "node"}},
                "lspServers": {"lsp1": {"command": "typescript-language-server"}},
            }
        )
        assert entry.mcp_config == {"server1": {"command": "node"}}
        assert entry.lsp_servers == {"lsp1": {"command": "typescript-language-server"}}


class TestMarketplaceMetadata:
    """测试 MarketplaceMetadata 模型。"""

    def test_basic_metadata(self):
        """测试基本元数据。"""
        metadata = MarketplaceMetadata(description="Internal tools", version="1.0.0")
        assert metadata.description == "Internal tools"
        assert metadata.version == "1.0.0"

    def test_metadata_extra_fields_allowed(self):
        """测试元数据中是否允许额外字段。"""
        metadata = MarketplaceMetadata.model_validate(
            {"description": "Tools", "custom_field": "value"}
        )
        assert metadata.description == "Tools"


class TestMarketplace:
    """测试市场加载。"""

    def test_load_marketplace_with_plugin_dir(self, tmp_path: Path):
        """测试从 .plugin 目录加载市场。"""
        marketplace_dir = tmp_path / "my-marketplace"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            """{
            "name": "my-marketplace",
            "owner": {"name": "Test Team"},
            "plugins": [
                {
                    "name": "test-plugin",
                    "source": "./plugins/test",
                    "description": "A test plugin"
                }
            ]
        }"""
        )

        marketplace = Marketplace.load(marketplace_dir)

        assert marketplace.name == "my-marketplace"
        assert marketplace.owner.name == "Test Team"
        assert len(marketplace.plugins) == 1
        assert marketplace.plugins[0].name == "test-plugin"
        assert marketplace.path == str(marketplace_dir)

    def test_load_marketplace_with_claude_plugin_dir(self, tmp_path: Path):
        """测试从 .claude-plugin 目录加载市场。"""
        marketplace_dir = tmp_path / "claude-marketplace"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".claude-plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            """{
            "name": "claude-marketplace",
            "owner": {"name": "Claude Team"}
        }"""
        )

        marketplace = Marketplace.load(marketplace_dir)

        assert marketplace.name == "claude-marketplace"
        assert marketplace.owner.name == "Claude Team"

    def test_load_marketplace_with_metadata(self, tmp_path: Path):
        """测试使用元数据加载市场。"""
        marketplace_dir = tmp_path / "meta-marketplace"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            """{
            "name": "meta-marketplace",
            "owner": {"name": "Meta Team", "email": "meta@example.com"},
            "metadata": {
                "description": "Marketplace with metadata",
                "version": "2.0.0"
            },
            "plugins": []
        }"""
        )

        marketplace = Marketplace.load(marketplace_dir)

        assert marketplace.metadata is not None
        assert marketplace.metadata.description == "Marketplace with metadata"
        assert marketplace.metadata.version == "2.0.0"
        assert marketplace.owner.email == "meta@example.com"

    def test_load_marketplace_with_github_plugin_source(self, tmp_path: Path):
        """使用 GitHub 插件源测试加载市场。"""
        marketplace_dir = tmp_path / "github-marketplace"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            """{
            "name": "github-marketplace",
            "owner": {"name": "GitHub Team"},
            "plugins": [
                {
                    "name": "github-plugin",
                    "source": {
                        "source": "github",
                        "repo": "company/plugin"
                    }
                }
            ]
        }"""
        )

        marketplace = Marketplace.load(marketplace_dir)

        assert len(marketplace.plugins) == 1
        plugin = marketplace.plugins[0]
        assert plugin.name == "github-plugin"
        assert isinstance(plugin.source, MarketplacePluginSource)
        assert plugin.source.source == "github"
        assert plugin.source.repo == "company/plugin"

    def test_load_marketplace_with_full_plugin_entry(self, tmp_path: Path):
        """使用完全填充的插件条目测试加载市场。"""
        marketplace_dir = tmp_path / "full-marketplace"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            """{
            "name": "full-marketplace",
            "owner": {"name": "Full Team"},
            "plugins": [
                {
                    "name": "enterprise-tools",
                    "source": "./plugins/enterprise",
                    "description": "Enterprise tools",
                    "version": "2.1.0",
                    "author": {"name": "Enterprise Team"},
                    "homepage": "https://docs.example.com",
                    "repository": "https://github.com/company/enterprise",
                    "license": "MIT",
                    "keywords": ["enterprise", "workflow"],
                    "category": "productivity",
                    "tags": ["automation"],
                    "strict": false
                }
            ]
        }"""
        )

        marketplace = Marketplace.load(marketplace_dir)

        plugin = marketplace.plugins[0]
        assert plugin.name == "enterprise-tools"
        assert plugin.description == "Enterprise tools"
        assert plugin.version == "2.1.0"
        assert plugin.author is not None and plugin.author.name == "Enterprise Team"
        assert plugin.homepage == "https://docs.example.com"
        assert plugin.license == "MIT"
        assert plugin.keywords == ["enterprise", "workflow"]
        assert plugin.category == "productivity"
        assert plugin.tags == ["automation"]
        assert plugin.strict is False

    def test_load_nonexistent_marketplace(self, tmp_path: Path):
        """测试加载不存在的市场会引发错误。"""
        with pytest.raises(FileNotFoundError, match="Marketplace directory not found"):
            Marketplace.load(tmp_path / "nonexistent")

    def test_load_marketplace_without_manifest(self, tmp_path: Path):
        """测试加载没有清单的市场会引发错误。"""
        marketplace_dir = tmp_path / "no-manifest"
        marketplace_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="Marketplace manifest not found"):
            Marketplace.load(marketplace_dir)

    def test_load_marketplace_with_invalid_json(self, tmp_path: Path):
        """测试加载无效 JSON 的市场会引发错误。"""
        marketplace_dir = tmp_path / "invalid-json"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text("{ invalid json }")

        with pytest.raises(ValueError, match="Invalid JSON"):
            Marketplace.load(marketplace_dir)

    def test_load_marketplace_missing_name(self, tmp_path: Path):
        """测试加载市场缺少名称会引发错误。"""
        marketplace_dir = tmp_path / "missing-name"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text('{"owner": {"name": "Team"}}')

        from pydantic import ValidationError

        with pytest.raises(ValidationError, match=r"name\n.*Field required"):
            Marketplace.load(marketplace_dir)

    def test_load_marketplace_missing_owner(self, tmp_path: Path):
        """测试加载缺少所有者的市场会引发错误。"""
        marketplace_dir = tmp_path / "missing-owner"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text('{"name": "test-marketplace"}')

        from pydantic import ValidationError

        with pytest.raises(ValidationError, match=r"owner\n.*Field required"):
            Marketplace.load(marketplace_dir)

    def test_get_plugin(self, tmp_path: Path):
        """测试get_plugin方法。"""
        marketplace_dir = tmp_path / "get-plugin-test"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            """{
            "name": "test-marketplace",
            "owner": {"name": "Test Team"},
            "plugins": [
                {"name": "plugin-a", "source": "./a"},
                {"name": "plugin-b", "source": "./b"},
                {"name": "plugin-c", "source": "./c"}
            ]
        }"""
        )

        marketplace = Marketplace.load(marketplace_dir)

        # 测试查找现有插件
        plugin_a = marketplace.get_plugin("plugin-a")
        plugin_b = marketplace.get_plugin("plugin-b")
        assert plugin_a is not None and plugin_a.name == "plugin-a"
        assert plugin_b is not None and plugin_b.source == "./b"
        assert marketplace.get_plugin("plugin-c") is not None

        # 测试不存在的插件
        assert marketplace.get_plugin("nonexistent") is None

    def test_resolve_plugin_source_relative_path(self, tmp_path: Path):
        """使用相对路径测试 resolve_plugin_source。"""
        marketplace_dir = tmp_path / "resolve-test"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            """{
            "name": "resolve-marketplace",
            "owner": {"name": "Test Team"},
            "plugins": [
                {"name": "local-plugin", "source": "./plugins/local"}
            ]
        }"""
        )

        marketplace = Marketplace.load(marketplace_dir)
        plugin = marketplace.plugins[0]

        source, ref, subpath = marketplace.resolve_plugin_source(plugin)
        # 应该解析为绝对路径
        assert str(marketplace_dir / "plugins/local") == source
        assert ref is None
        assert subpath is None

    def test_resolve_plugin_source_github(self, tmp_path: Path):
        """使用 GitHub 源测试 resolve_plugin_source。"""
        marketplace_dir = tmp_path / "github-resolve"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            """{
            "name": "github-marketplace",
            "owner": {"name": "Test Team"},
            "plugins": [
                {
                    "name": "github-plugin",
                    "source": {"source": "github", "repo": "owner/repo"}
                }
            ]
        }"""
        )

        marketplace = Marketplace.load(marketplace_dir)
        plugin = marketplace.plugins[0]

        source, ref, subpath = marketplace.resolve_plugin_source(plugin)
        assert source == "github:owner/repo"
        assert ref is None
        assert subpath is None

    def test_resolve_plugin_source_github_with_ref_and_path(self, tmp_path: Path):
        """使用 GitHub 源（包括引用和路径）测试 resolve_plugin_source。"""
        marketplace_dir = tmp_path / "github-full-resolve"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            """{
            "name": "github-marketplace",
            "owner": {"name": "Test Team"},
            "plugins": [
                {
                    "name": "github-plugin",
                    "source": {
                        "source": "github",
                        "repo": "owner/monorepo",
                        "ref": "v1.0.0",
                        "path": "plugins/my-plugin"
                    }
                }
            ]
        }"""
        )

        marketplace = Marketplace.load(marketplace_dir)
        plugin = marketplace.plugins[0]

        source, ref, subpath = marketplace.resolve_plugin_source(plugin)
        assert source == "github:owner/monorepo"
        assert ref == "v1.0.0"
        assert subpath == "plugins/my-plugin"

    def test_resolve_plugin_source_url(self, tmp_path: Path):
        """使用 URL 源测试 resolve_plugin_source。"""
        marketplace_dir = tmp_path / "url-resolve"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            """{
            "name": "url-marketplace",
            "owner": {"name": "Test Team"},
            "plugins": [
                {
                    "name": "url-plugin",
                    "source": {"source": "url", "url": "https://gitlab.com/org/repo.git"}
                }
            ]
        }"""
        )

        marketplace = Marketplace.load(marketplace_dir)
        plugin = marketplace.plugins[0]

        source, ref, subpath = marketplace.resolve_plugin_source(plugin)
        assert source == "https://gitlab.com/org/repo.git"
        assert ref is None
        assert subpath is None

    def test_resolve_plugin_source_url_with_ref_and_path(self, tmp_path: Path):
        """使用 URL 源（包括引用和路径）测试 resolve_plugin_source。"""
        marketplace_dir = tmp_path / "url-full-resolve"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            """{
            "name": "url-marketplace",
            "owner": {"name": "Test Team"},
            "plugins": [
                {
                    "name": "url-plugin",
                    "source": {
                        "source": "url",
                        "url": "https://gitlab.com/org/repo.git",
                        "ref": "main",
                        "path": "packages/plugin"
                    }
                }
            ]
        }"""
        )

        marketplace = Marketplace.load(marketplace_dir)
        plugin = marketplace.plugins[0]

        source, ref, subpath = marketplace.resolve_plugin_source(plugin)
        assert source == "https://gitlab.com/org/repo.git"
        assert ref == "main"
        assert subpath == "packages/plugin"


class TestMarketplaceIntegration:
    """集成测试用于带有插件的市场。"""

    def test_marketplace_plugin_entry_consistency(self):
        """测试 MarketplacePluginEntry 字段是否与 PluginManifest 对齐。"""
        # 两者都应支持名称、版本、描述、作者
        from openhands.sdk.plugin import PluginManifest

        author = PluginAuthor(name="Test Author")
        entry = MarketplacePluginEntry(
            name="test-plugin",
            source="./plugins/test",
            version="1.0.0",
            description="A test plugin",
            author=author,
        )

        manifest = PluginManifest(
            name="test-plugin",
            version="1.0.0",
            description="A test plugin",
            author=author,
        )

        assert entry.name == manifest.name
        assert entry.version == manifest.version
        assert entry.description == manifest.description
        assert entry.author is not None and manifest.author is not None
        assert entry.author.name == manifest.author.name

    def test_to_plugin_manifest(self):
        """测试将 MarketplacePluginEntry 转换为 PluginManifest。"""
        entry = MarketplacePluginEntry(
            name="my-plugin",
            source="./plugins/my-plugin",
            version="2.0.0",
            description="My awesome plugin",
            author=PluginAuthor(name="Author Name", email="author@example.com"),
            license="MIT",
            keywords=["testing", "example"],
        )

        manifest = entry.to_plugin_manifest()

        assert manifest.name == "my-plugin"
        assert manifest.version == "2.0.0"
        assert manifest.description == "My awesome plugin"
        assert manifest.author is not None
        assert manifest.author.name == "Author Name"
        assert manifest.author.email == "author@example.com"

    def test_to_plugin_manifest_defaults(self):
        """测试 to_plugin_manifest 使用缺失字段的默认值。"""
        entry = MarketplacePluginEntry(
            name="minimal-plugin",
            source="./plugins/minimal",
        )

        manifest = entry.to_plugin_manifest()

        assert manifest.name == "minimal-plugin"
        assert manifest.version == "1.0.0"  # 默认
        assert manifest.description == ""  # 默认
        assert manifest.author is None

    def test_to_plugin_manifest_with_entry_command(self):
        """测试 to_plugin_manifest 保留 entry_command 字段。"""
        entry = MarketplacePluginEntry(
            name="city-weather",
            source="./plugins/city-weather",
            version="1.0.0",
            description="Get current weather for any city",
            entry_command="now",
        )

        manifest = entry.to_plugin_manifest()

        assert manifest.name == "city-weather"
        assert manifest.entry_command == "now"

    def test_entry_with_entry_command(self):
        """使用 entry_command 字段测试 MarketplacePluginEntry。"""
        entry = MarketplacePluginEntry(
            name="city-weather",
            source="./plugins/city-weather",
            entry_command="now",
        )
        assert entry.name == "city-weather"
        assert entry.entry_command == "now"

    def test_invalid_github_source_missing_repo(self, tmp_path: Path):
        """测试无效的 GitHub 源（缺少存储库）是否会在加载时引发错误。"""
        marketplace_dir = tmp_path / "invalid-source"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            """{
            "name": "invalid-marketplace",
            "owner": {"name": "Test Team"},
            "plugins": [
                {
                    "name": "bad-plugin",
                    "source": {"source": "github"}
                }
            ]
        }"""
        )

        from pydantic import ValidationError

        with pytest.raises(
            ValidationError, match="GitHub source requires 'repo' field"
        ):
            Marketplace.load(marketplace_dir)

    def test_invalid_url_source_missing_url(self, tmp_path: Path):
        """测试无效的 URL 源（缺少 url）是否会在加载时引发错误。"""
        marketplace_dir = tmp_path / "invalid-url-source"
        marketplace_dir.mkdir()
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            """{
            "name": "invalid-marketplace",
            "owner": {"name": "Test Team"},
            "plugins": [
                {
                    "name": "bad-plugin",
                    "source": {"source": "url"}
                }
            ]
        }"""
        )

        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="URL source requires 'url' field"):
            Marketplace.load(marketplace_dir)

    def test_skill_compatible_fields(self):
        """测试 MarketplacePluginEntry 是否具有与技能兼容的字段。"""
        # 根据 AgentSkills 标准，技能类别具有 `license` 和 `description` 字段。
        # MarketplacePluginEntry 应该有匹配的字段。
        #
        entry = MarketplacePluginEntry(
            name="skill-compatible-plugin",
            source="./plugins/test",
            description="Plugin with skill-compatible fields",
            license="Apache-2.0",
            keywords=["skill", "compatible"],
        )

        # 这些字段与技能定义一致
        assert entry.license == "Apache-2.0"
        assert entry.description == "Plugin with skill-compatible fields"
        assert entry.keywords == ["skill", "compatible"]
