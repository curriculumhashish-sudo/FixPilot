"""测试智能体插件格式：检测、清单和组件。"""

import json
from pathlib import Path

import pytest

from openhands.sdk.plugin import (
    AgentPluginsFormat,
    ClaudeCodePluginFormat,
    Plugin,
    PluginManifest,
    detect_format,
)
from openhands.sdk.plugin.format.agent_plugins import (
    _MANIFEST_SCHEMA_FILE,
    EXTENSION_NAMESPACE,
    MANIFEST_SCHEMA_URL,
    _load_schema,
)


SCHEMA_1_0_0 = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"

# 官方示例插件的清单，逐字记录。
# https://github.com/agentplugins/agent-plugins-example/blob/main/plugin.json
EXAMPLE_MANIFEST = {
    "$schema": SCHEMA_1_0_0,
    "name": "agent-plugins-example",
    "version": "1.0.0",
    "description": (
        "A copyable reference package and migration guide for Agent Plugins v1.0.0."
    ),
    "license": "MIT",
    "keywords": ["agent-plugins", "example", "migration", "skills"],
}


def write_manifest(plugin_dir: Path, manifest: dict | str) -> Path:
    """写入根级别 plugin.json，创建插件目录。"""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    path = plugin_dir / "plugin.json"
    path.write_text(
        manifest if isinstance(manifest, str) else json.dumps(manifest),
        encoding="utf-8",
    )
    return path


def write_extension_components(root: Path) -> None:
    """在共享布局中，在 ``root`` 下编写一个钩子智能体和命令。"""
    (root / "hooks").mkdir(parents=True, exist_ok=True)
    (root / "hooks" / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "*",
                            "hooks": [{"type": "command", "command": "echo hi"}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "agents").mkdir(parents=True, exist_ok=True)
    (root / "agents" / "helper.md").write_text(
        "---\nname: helper\ndescription: A helper agent.\n---\n\nHelp out.\n",
        encoding="utf-8",
    )
    (root / "commands").mkdir(parents=True, exist_ok=True)
    (root / "commands" / "now.md").write_text(
        "---\ndescription: Report the weather now.\n---\n\nReport it.\n",
        encoding="utf-8",
    )


class TestDetect:
    """根 plugin.json 声明该目录，除非它缺少 $模式键。"""

    def test_detects_root_manifest(self, tmp_path: Path):
        write_manifest(tmp_path / "p", EXAMPLE_MANIFEST)
        assert AgentPluginsFormat.detect(tmp_path / "p") is True

    def test_ignores_nested_claude_code_manifest(self, tmp_path: Path):
        plugin_dir = tmp_path / "p"
        (plugin_dir / ".claude-plugin").mkdir(parents=True)
        (plugin_dir / ".claude-plugin" / "plugin.json").write_text('{"name": "p"}')

        assert AgentPluginsFormat.detect(plugin_dir) is False

    def test_ignores_bare_dir(self, tmp_path: Path):
        (tmp_path / "p").mkdir()
        assert AgentPluginsFormat.detect(tmp_path / "p") is False

    def test_claims_malformed_manifest(self, tmp_path: Path):
        """声称，但没有落空：load_manifest()大声拒绝。"""
        write_manifest(tmp_path / "p", "{not json")

        assert AgentPluginsFormat.detect(tmp_path / "p") is True

    def test_claims_manifest_with_unsupported_schema(self, tmp_path: Path):
        write_manifest(
            tmp_path / "p", {"$schema": "https://example.com/x", "name": "p"}
        )

        assert AgentPluginsFormat.detect(tmp_path / "p") is True

    def test_claims_non_object_manifest(self, tmp_path: Path):
        write_manifest(tmp_path / "p", '["not", "an", "object"]')

        assert AgentPluginsFormat.detect(tmp_path / "p") is True

    def test_ignores_manifest_without_schema(self, tmp_path: Path):
        """另一个工具的根 plugin.json（没有 $模式）不是智能体插件。"""
        write_manifest(tmp_path / "p", {"name": "p", "skills": ["./skills/"]})

        assert AgentPluginsFormat.detect(tmp_path / "p") is False

    def test_manifest_without_schema_loads_claude_code_layout(self, tmp_path: Path):
        """具有 GitHub Copilot 风格清单的插件的技能仍然会加载。"""
        plugin_dir = tmp_path / "dotnet"
        write_manifest(
            plugin_dir, {"name": "dotnet", "version": "0.2.5", "skills": ["./skills/"]}
        )
        skill_dir = plugin_dir / "skills" / "csharp-refactoring"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: csharp-refactoring\ndescription: Refactor C#.\n---\nBody\n"
        )

        assert isinstance(detect_format(plugin_dir), ClaudeCodePluginFormat)
        plugin = Plugin.load(plugin_dir)
        assert plugin.name == "dotnet"
        assert [s.name for s in plugin.get_all_skills()] == ["csharp-refactoring"]

    def test_ignores_manifest_directory(self, tmp_path: Path):
        """plugin.json *目录*不是清单。"""
        (tmp_path / "p" / "plugin.json").mkdir(parents=True)
        assert AgentPluginsFormat.detect(tmp_path / "p") is False

    def test_ignores_missing_dir(self, tmp_path: Path):
        assert AgentPluginsFormat.detect(tmp_path / "does-not-exist") is False

    def test_registered_ahead_of_claude_code(self, tmp_path: Path):
        """根清单胜过通用克劳德代码回退方案。"""
        write_manifest(tmp_path / "p", EXAMPLE_MANIFEST)

        assert isinstance(detect_format(tmp_path / "p"), AgentPluginsFormat)

    def test_claude_code_still_the_fallback(self, tmp_path: Path):
        (tmp_path / "p").mkdir()

        assert isinstance(detect_format(tmp_path / "p"), ClaudeCodePluginFormat)


class TestLoadManifestValid:
    """表明已关闭模式接受。"""

    def test_loads_example_plugin(self, tmp_path: Path):
        write_manifest(tmp_path, EXAMPLE_MANIFEST)

        manifest = AgentPluginsFormat().load_manifest(tmp_path)

        assert isinstance(manifest, PluginManifest)
        assert manifest.name == "agent-plugins-example"
        assert manifest.version == "1.0.0"
        assert manifest.description.startswith("A copyable reference package")

    def test_preserves_agent_plugins_only_fields(self, tmp_path: Path):
        """没有 PluginManifest 列的字段通过 extra='allow' 生存。"""
        write_manifest(
            tmp_path,
            {
                **EXAMPLE_MANIFEST,
                "homepage": "https://example.com",
                "repository": "https://github.com/example/plugin",
                "extensions": {"com.example.client": {"entry_command": "now"}},
            },
        )

        dumped = AgentPluginsFormat().load_manifest(tmp_path).model_dump()

        assert dumped["$schema"] == SCHEMA_1_0_0
        assert dumped["license"] == "MIT"
        assert dumped["keywords"] == ["agent-plugins", "example", "migration", "skills"]
        assert dumped["homepage"] == "https://example.com"
        assert dumped["repository"] == "https://github.com/example/plugin"
        assert dumped["extensions"] == {"com.example.client": {"entry_command": "now"}}

    def test_minimal_manifest_uses_model_defaults(self, tmp_path: Path):
        """模式仅需要 $模式和名称。"""
        write_manifest(tmp_path, {"$schema": SCHEMA_1_0_0, "name": "minimal"})

        manifest = AgentPluginsFormat().load_manifest(tmp_path)

        assert manifest.name == "minimal"
        assert manifest.version == "1.0.0"
        assert manifest.description == ""
        assert manifest.author is None

    def test_author_object(self, tmp_path: Path):
        write_manifest(
            tmp_path,
            {
                "$schema": SCHEMA_1_0_0,
                "name": "authored",
                "author": {"name": "Ada", "email": "ada@example.com"},
            },
        )

        manifest = AgentPluginsFormat().load_manifest(tmp_path)

        assert manifest.author is not None
        assert manifest.author.name == "Ada"
        assert manifest.author.email == "ada@example.com"

    @pytest.mark.parametrize(
        "author", [{}, {"email": "ada@example.com"}, {"url": "https://example.com"}]
    )
    def test_author_without_name(self, tmp_path: Path, author: dict):
        """模式不需要 author.name，所以我们也不需要。"""
        write_manifest(
            tmp_path, {"$schema": SCHEMA_1_0_0, "name": "p", **{"author": author}}
        )

        manifest = AgentPluginsFormat().load_manifest(tmp_path)

        assert manifest.author is not None
        assert manifest.author.name == ""

    def test_utf8_bom_is_tolerated(self, tmp_path: Path):
        """RFC 8259 让解析器忽略前导 BOM。"""
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "plugin.json").write_bytes(
            b"\xef\xbb\xbf" + json.dumps(EXAMPLE_MANIFEST).encode("utf-8")
        )

        assert AgentPluginsFormat().load_manifest(tmp_path).name == (
            "agent-plugins-example"
        )

    @pytest.mark.parametrize(
        "name",
        ["a", "a-b", "a.b", "plugin1", "a" * 64, "a-b.c-d", "0abc"],
    )
    def test_accepts_valid_names(self, tmp_path: Path, name: str):
        write_manifest(tmp_path, {"$schema": SCHEMA_1_0_0, "name": name})

        assert AgentPluginsFormat().load_manifest(tmp_path).name == name


class TestLoadManifestNonFatal:
    """规范要求报告和忽略的违规行为。"""

    def test_unknown_top_level_field_is_dropped(self, tmp_path: Path, caplog):
        write_manifest(
            tmp_path, {**EXAMPLE_MANIFEST, "entry_command": "now", "nonsense": 1}
        )

        manifest = AgentPluginsFormat().load_manifest(tmp_path)

        assert manifest.name == "agent-plugins-example"
        dumped = manifest.model_dump()
        assert "entry_command" not in dumped or dumped["entry_command"] is None
        assert "nonsense" not in dumped
        assert "Ignoring unknown top-level field(s)" in caplog.text
        assert "entry_command" in caplog.text
        assert "nonsense" in caplog.text

    @pytest.mark.parametrize("extensions", [[], "nope", 3, None])
    def test_non_object_extensions_is_dropped(self, tmp_path: Path, caplog, extensions):
        write_manifest(tmp_path, {**EXAMPLE_MANIFEST, "extensions": extensions})

        manifest = AgentPluginsFormat().load_manifest(tmp_path)

        assert manifest.name == "agent-plugins-example"
        assert "extensions" not in manifest.model_dump()
        assert "Ignoring non-object 'extensions'" in caplog.text

    def test_both_non_fatal_violations_together(self, tmp_path: Path, caplog):
        write_manifest(tmp_path, {**EXAMPLE_MANIFEST, "nonsense": 1, "extensions": []})

        manifest = AgentPluginsFormat().load_manifest(tmp_path)

        assert manifest.name == "agent-plugins-example"
        assert "Ignoring unknown top-level field(s)" in caplog.text
        assert "Ignoring non-object 'extensions'" in caplog.text

    def test_dropping_unknown_fields_does_not_mask_a_fatal_one(self, tmp_path: Path):
        """剥离非致命违规不能挽救无效名称。"""
        write_manifest(
            tmp_path, {"$schema": SCHEMA_1_0_0, "name": "BAD--NAME", "nonsense": 1}
        )

        with pytest.raises(ValueError, match="Invalid Agent Plugins manifest"):
            AgentPluginsFormat().load_manifest(tmp_path)


class TestLoadManifestFatal:
    """拒绝整个插件的违规行为。"""

    def test_missing_schema(self, tmp_path: Path):
        write_manifest(tmp_path, {"name": "no-schema"})

        with pytest.raises(ValueError, match="Unsupported or missing \\$schema"):
            AgentPluginsFormat().load_manifest(tmp_path)

    def test_unsupported_schema_version(self, tmp_path: Path):
        write_manifest(
            tmp_path,
            {
                "$schema": "https://agent-plugins.org/schemas/2.0.0/plugin.schema.json",
                "name": "from-the-future",
            },
        )

        with pytest.raises(ValueError, match="Unsupported or missing \\$schema"):
            AgentPluginsFormat().load_manifest(tmp_path)

    def test_non_string_schema(self, tmp_path: Path):
        write_manifest(tmp_path, {"$schema": 1, "name": "weird"})

        with pytest.raises(ValueError, match="Unsupported or missing \\$schema"):
            AgentPluginsFormat().load_manifest(tmp_path)

    def test_invalid_json(self, tmp_path: Path):
        write_manifest(tmp_path, "{not json")

        with pytest.raises(ValueError, match="Invalid JSON"):
            AgentPluginsFormat().load_manifest(tmp_path)

    def test_undecodable_bytes(self, tmp_path: Path):
        """解码失败被包装，而不是作为 UnicodeDecodeError 泄漏。"""
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "plugin.json").write_bytes(
            b'{"$schema": "' + SCHEMA_1_0_0.encode() + b'", "name": "caf\xe9"}'
        )

        with pytest.raises(ValueError, match="Failed to read manifest"):
            AgentPluginsFormat().load_manifest(tmp_path)

    @pytest.mark.parametrize("payload", ["[]", '"a string"', "42", "null"])
    def test_non_object_root(self, tmp_path: Path, payload: str):
        write_manifest(tmp_path, payload)

        with pytest.raises(ValueError, match="must contain a JSON object"):
            AgentPluginsFormat().load_manifest(tmp_path)

    def test_missing_name(self, tmp_path: Path):
        write_manifest(tmp_path, {"$schema": SCHEMA_1_0_0})

        with pytest.raises(ValueError, match="Invalid Agent Plugins manifest"):
            AgentPluginsFormat().load_manifest(tmp_path)

    @pytest.mark.parametrize(
        "name",
        [
            "",  # 太短
            "a" * 65,  # 太长
            "Uppercase",
            "-leading-hyphen",
            "trailing-hyphen-",
            ".leading-period",
            "trailing-period.",
            "double--hyphen",
            "double..period",
            "under_score",
            "with space",
        ],
    )
    def test_invalid_names(self, tmp_path: Path, name: str):
        write_manifest(tmp_path, {"$schema": SCHEMA_1_0_0, "name": name})

        with pytest.raises(ValueError, match="Invalid Agent Plugins manifest"):
            AgentPluginsFormat().load_manifest(tmp_path)

    def test_string_author_rejected(self, tmp_path: Path):
        """智能体插件作者只是对象，与 Claude Code 格式不同。"""
        write_manifest(
            tmp_path, {"$schema": SCHEMA_1_0_0, "name": "p", "author": "Ada <a@e.com>"}
        )

        with pytest.raises(ValueError, match="Invalid Agent Plugins manifest"):
            AgentPluginsFormat().load_manifest(tmp_path)

    def test_unknown_author_field_rejected(self, tmp_path: Path):
        """非致命规则仅涵盖顶级字段，而不涵盖嵌套对象。"""
        write_manifest(
            tmp_path,
            {"$schema": SCHEMA_1_0_0, "name": "p", "author": {"handle": "ada"}},
        )

        with pytest.raises(ValueError, match="Invalid Agent Plugins manifest"):
            AgentPluginsFormat().load_manifest(tmp_path)

    @pytest.mark.parametrize(
        "field,value",
        [
            ("version", 1),
            ("description", []),
            ("license", False),
            ("keywords", "not-a-list"),
            ("keywords", [1, 2]),
            ("extensions", {"com.example.client": "not-an-object"}),
        ],
    )
    def test_wrong_types(self, tmp_path: Path, field: str, value):
        write_manifest(tmp_path, {**EXAMPLE_MANIFEST, field: value})

        with pytest.raises(ValueError, match="Invalid Agent Plugins manifest"):
            AgentPluginsFormat().load_manifest(tmp_path)

    def test_missing_manifest_file(self, tmp_path: Path):
        with pytest.raises(ValueError, match="Failed to read manifest"):
            AgentPluginsFormat().load_manifest(tmp_path)

    def test_manifest_is_a_directory(self, tmp_path: Path):
        (tmp_path / "plugin.json").mkdir()

        with pytest.raises(ValueError, match="Failed to read manifest"):
            AgentPluginsFormat().load_manifest(tmp_path)


class TestComponentLoaders:
    """便携核心：技能与基地共享，mcp.json为后续。"""

    def test_load_assembles_plugin_with_skills(self, tmp_path: Path):
        write_manifest(tmp_path, EXAMPLE_MANIFEST)
        skill_dir = tmp_path / "skills" / "summarize"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: summarize\ndescription: Summarize text.\n---\n\nDo it.\n",
            encoding="utf-8",
        )

        plugin = AgentPluginsFormat().load(tmp_path)

        assert plugin.manifest.name == "agent-plugins-example"
        assert [s.name for s in plugin.skills] == ["summarize"]

    def test_mcp_loader_is_deferred(self, tmp_path: Path):
        """mcp.json 尚未读取。"""
        write_manifest(tmp_path, EXAMPLE_MANIFEST)
        (tmp_path / "mcp.json").write_text(
            json.dumps({"mcpServers": {"x": {"type": "stdio", "command": "echo"}}}),
            encoding="utf-8",
        )

        assert AgentPluginsFormat().load_mcp_config(tmp_path) == {}


class TestClientExtension:
    """我们的``dev.openhands``命名空间：清单数据和扩展目录。"""

    def test_entry_command_is_mapped_from_our_namespace(self, tmp_path: Path):
        write_manifest(
            tmp_path,
            {
                **EXAMPLE_MANIFEST,
                "extensions": {EXTENSION_NAMESPACE: {"entry_command": "now"}},
            },
        )

        manifest = AgentPluginsFormat().load_manifest(tmp_path)

        assert manifest.entry_command == "now"
        # 原始扩展数据与映射字段一起保留。
        assert manifest.model_dump()["extensions"] == {
            EXTENSION_NAMESPACE: {"entry_command": "now"}
        }

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(42, id="int"),
            pytest.param([], id="list"),
            pytest.param({"a": 1}, id="object"),
            pytest.param(True, id="bool"),
        ],
    )
    def test_non_string_entry_command_is_reported_and_ignored(
        self, tmp_path: Path, caplog, value
    ):
        """我们的命名空间，我们的规则：错误的值会删除字段，而不是插件。"""
        write_manifest(
            tmp_path,
            {
                **EXAMPLE_MANIFEST,
                "extensions": {EXTENSION_NAMESPACE: {"entry_command": value}},
            },
        )

        manifest = AgentPluginsFormat().load_manifest(tmp_path)

        assert manifest.entry_command is None
        assert "Ignoring non-string" in caplog.text

    @pytest.mark.parametrize(
        "extensions",
        [
            pytest.param({}, id="no-namespaces"),
            pytest.param({EXTENSION_NAMESPACE: {}}, id="ours-empty"),
            pytest.param({EXTENSION_NAMESPACE: {"entry_command": None}}, id="null"),
            pytest.param({EXTENSION_NAMESPACE: {"entry_command": ""}}, id="empty-str"),
            # §8.1：外国命名空间的内容永远不会被验证，因此它的 entry_command（任何类型）
            # 都不是我们可以读取的。
            #
            pytest.param(
                {"com.example.client": {"entry_command": 42}}, id="foreign-namespace"
            ),
        ],
    )
    def test_no_usable_entry_command(self, tmp_path: Path, extensions):
        write_manifest(tmp_path, {**EXAMPLE_MANIFEST, "extensions": extensions})

        assert AgentPluginsFormat().load_manifest(tmp_path).entry_command is None

    def test_components_load_from_the_extension_directory(self, tmp_path: Path):
        write_manifest(tmp_path, EXAMPLE_MANIFEST)
        write_extension_components(tmp_path / EXTENSION_NAMESPACE)

        fmt = AgentPluginsFormat()

        hooks = fmt.load_hooks(tmp_path)
        assert hooks is not None and len(hooks.pre_tool_use) == 1
        assert [a.name for a in fmt.load_agents(tmp_path)] == ["helper"]
        assert [c.name for c in fmt.load_commands(tmp_path)] == ["now"]

    @pytest.mark.parametrize(
        "location",
        [
            pytest.param(None, id="nowhere"),
            pytest.param(".", id="plugin-root"),
            pytest.param("com.example.client", id="foreign-namespace"),
        ],
    )
    def test_components_outside_our_namespace_are_not_read(
        self, tmp_path: Path, location: str | None
    ):
        """§8.2：只有命名空间的所有者才能读取其目录。

        插件根目录包含可移植核心，而另一个供应商的目录是他们自己的——任何一个地方的组
        件都不是我们可以加载的。
        """
        write_manifest(tmp_path, EXAMPLE_MANIFEST)
        if location is not None:
            write_extension_components(tmp_path / location)

        fmt = AgentPluginsFormat()

        assert fmt.load_hooks(tmp_path) is None
        assert fmt.load_agents(tmp_path) == []
        assert fmt.load_commands(tmp_path) == []

    def test_skills_stay_portable_core(self, tmp_path: Path):
        """技能来自``<root>/skills``，而不是来自扩展目录。"""
        write_manifest(tmp_path, EXAMPLE_MANIFEST)
        skill_dir = tmp_path / EXTENSION_NAMESPACE / "skills" / "summarize"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: summarize\ndescription: Summarize text.\n---\n\nDo it.\n",
            encoding="utf-8",
        )

        assert AgentPluginsFormat().load(tmp_path).skills == []

    def test_broken_components_do_not_sink_the_plugin(self, tmp_path: Path, caplog):
        """§4.1：故障边界是一个条目，而不是插件。

        损坏的代理/命令在其同级加载时会被跳过，并且不可解析的 hooks.json 只会花费插件
        的钩子。
        """
        write_manifest(tmp_path, EXAMPLE_MANIFEST)
        extension_dir = tmp_path / EXTENSION_NAMESPACE
        write_extension_components(extension_dir)
        (extension_dir / "hooks" / "hooks.json").write_text(
            '{"hooks": { broken }', encoding="utf-8"
        )
        # 无法解析 YAML 前置元数据：两个加载器共有的一个故障。
        broken_frontmatter = "---\nname: [unclosed\n---\n\nbody\n"
        (extension_dir / "agents" / "broken.md").write_text(
            broken_frontmatter, encoding="utf-8"
        )
        (extension_dir / "commands" / "broken.md").write_text(
            broken_frontmatter, encoding="utf-8"
        )

        plugin = AgentPluginsFormat().load(tmp_path)

        assert plugin.manifest.name == "agent-plugins-example"
        assert [a.name for a in plugin.agents] == ["helper"]
        assert [c.name for c in plugin.commands] == ["now"]
        assert plugin.hooks is None
        assert "Failed to load hooks" in caplog.text
        assert "Failed to load agent" in caplog.text
        assert "Failed to load command" in caplog.text

    def test_hooks_json_without_hooks_is_empty_not_missing(self, tmp_path: Path):
        """一个empty-but-valid hooks.json 它不同于一个缺失的。"""
        write_manifest(tmp_path, EXAMPLE_MANIFEST)
        hooks_json = tmp_path / EXTENSION_NAMESPACE / "hooks" / "hooks.json"
        hooks_json.parent.mkdir(parents=True)
        hooks_json.write_text('{"hooks": {}}', encoding="utf-8")

        hooks = AgentPluginsFormat().load_hooks(tmp_path)

        assert hooks is not None
        assert hooks.is_empty()

    def test_load_assembles_the_full_extension(self, tmp_path: Path):
        write_manifest(
            tmp_path,
            {
                **EXAMPLE_MANIFEST,
                "extensions": {
                    EXTENSION_NAMESPACE: {"entry_command": "now"},
                    "com.example.client": {"whatever": True},
                },
            },
        )
        write_extension_components(tmp_path / EXTENSION_NAMESPACE)

        plugin = AgentPluginsFormat().load(tmp_path)

        assert plugin.entry_slash_command == "/agent-plugins-example:now"
        assert plugin.hooks is not None
        assert [a.name for a in plugin.agents] == ["helper"]
        assert [c.name for c in plugin.commands] == ["now"]


class TestVendoredSchema:
    """提供的文件必须与我们接受的URL保持一致。"""

    def test_constant_matches_the_literal_url(self):
        assert MANIFEST_SCHEMA_URL == SCHEMA_1_0_0

    def test_schema_identity_matches_constant(self):
        schema = _load_schema(_MANIFEST_SCHEMA_FILE)

        assert schema["$id"] == MANIFEST_SCHEMA_URL
        assert schema["properties"]["$schema"]["const"] == MANIFEST_SCHEMA_URL

    def test_schema_is_closed(self):
        schema = _load_schema(_MANIFEST_SCHEMA_FILE)

        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == {"$schema", "name"}
