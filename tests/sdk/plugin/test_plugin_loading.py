"""测试插件加载功能。"""

from pathlib import Path

import pytest

from openhands.sdk.mcp.config import dump_mcp_config
from openhands.sdk.plugin import (
    ClaudeCodePluginFormat,
    Plugin,
    PluginManifest,
    detect_format,
)
from openhands.sdk.plugin.types import (
    CommandDefinition,
    PluginAuthor,
)


class TestPluginManifest:
    """测试 PluginManifest 解析。"""

    def test_basic_manifest(self):
        """测试解析基本清单。"""
        manifest = PluginManifest(
            name="test-plugin",
            version="1.0.0",
            description="A test plugin",
        )
        assert manifest.name == "test-plugin"
        assert manifest.version == "1.0.0"
        assert manifest.description == "A test plugin"
        assert manifest.author is None

    def test_manifest_with_author_object(self):
        """以作者为对象测试解析清单。"""
        from openhands.sdk.plugin.types import PluginAuthor

        manifest = PluginManifest(
            name="test-plugin",
            author=PluginAuthor(name="Test Author", email="test@example.com"),
        )
        assert manifest.author is not None
        assert manifest.author.name == "Test Author"
        assert manifest.author.email == "test@example.com"

    def test_manifest_with_entry_command(self):
        """使用 entry_command 字段测试解析清单。"""
        manifest = PluginManifest(
            name="city-weather",
            version="1.0.0",
            entry_command="now",
        )
        assert manifest.name == "city-weather"
        assert manifest.entry_command == "now"

    def test_manifest_without_entry_command(self):
        """测试 entry_command 默认为 None。"""
        manifest = PluginManifest(name="test-plugin")
        assert manifest.entry_command is None


class TestPluginLoading:
    """测试 Plugin.load() 功能。"""

    def test_load_plugin_with_manifest(self, tmp_path: Path):
        """测试使用清单文件加载插件。"""
        # 创建插件结构
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()

        # 编写清单
        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text(
            """{
            "name": "test-plugin",
            "version": "2.0.0",
            "description": "A test plugin"
        }"""
        )

        # 加载插件
        plugin = Plugin.load(plugin_dir)

        assert plugin.name == "test-plugin"
        assert plugin.version == "2.0.0"
        assert plugin.description == "A test plugin"

    def test_load_plugin_with_claude_plugin_dir(self, tmp_path: Path):
        """测试加载带有 .claude-plugin 目录的插件。"""
        plugin_dir = tmp_path / "claude-plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".claude-plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text(
            """{
            "name": "claude-plugin",
            "version": "1.0.0"
        }"""
        )

        plugin = Plugin.load(plugin_dir)
        assert plugin.name == "claude-plugin"

    def test_load_plugin_without_manifest(self, tmp_path: Path):
        """测试加载没有清单的插件（从目录名称推断）。"""
        plugin_dir = tmp_path / "inferred-plugin"
        plugin_dir.mkdir()

        plugin = Plugin.load(plugin_dir)

        assert plugin.name == "inferred-plugin"
        assert plugin.version == "1.0.0"

    def test_load_plugin_with_skills(self, tmp_path: Path):
        """测试加载具有技能的插件。"""
        plugin_dir = tmp_path / "skill-plugin"
        plugin_dir.mkdir()

        # 创建技能目录
        skills_dir = plugin_dir / "skills"
        skills_dir.mkdir()

        # 创建技能
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: test-skill
description: A test skill
---

This is a test skill content.
"""
        )

        plugin = Plugin.load(plugin_dir)

        assert len(plugin.skills) == 1
        assert plugin.skills[0].name == "test-skill"

    def test_load_single_skill_plugin_root_skill_md(self, tmp_path: Path):
        """插件根目录中的 SKILL.md 作为单技能插件加载。

        镜像 Claude Code 的单技能插件行为 (v2.1.142+)：当插件没有 Skills/ 目录时，根
        SKILL.md 会作为插件的技能加载。 这
        就是独立智能体技能作为插件发布而无需额外嵌套级别的方式。
        """
        plugin_dir = tmp_path / "solo-skill"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".claude-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            '{"name": "solo-skill", "version": "1.0.0"}'
        )
        (plugin_dir / "SKILL.md").write_text(
            """---
name: solo-skill
description: A standalone skill published as a single-skill plugin.
---

Body of the solo skill.
"""
        )

        plugin = Plugin.load(plugin_dir)

        assert plugin.name == "solo-skill"
        assert len(plugin.skills) == 1
        assert plugin.skills[0].name == "solo-skill"

    def test_load_single_skill_plugin_without_manifest(self, tmp_path: Path):
        """即使 plugin.json 不存在，根 SKILL.md 也会加载。"""
        plugin_dir = tmp_path / "inferred-solo"
        plugin_dir.mkdir()
        (plugin_dir / "SKILL.md").write_text(
            """---
name: inferred-solo
description: Root skill with no manifest.
---

Body.
"""
        )

        plugin = Plugin.load(plugin_dir)

        assert plugin.name == "inferred-solo"
        assert len(plugin.skills) == 1
        assert plugin.skills[0].name == "inferred-solo"

    def test_skills_dir_takes_precedence_over_root_skill_md(self, tmp_path: Path):
        """当技能/目录存在时，它会赢得根SKILL.md。

        匹配Claude代码：根SKILL.md只是在没有skills/目录时使用的回退方案。
        """
        plugin_dir = tmp_path / "both"
        plugin_dir.mkdir()
        # 根 SKILL.md 必须是 IGNORED，因为技能/ 存在。
        (plugin_dir / "SKILL.md").write_text(
            "---\nname: root-ignored\ndescription: should not load\n---\nbody\n"
        )
        skill_dir = plugin_dir / "skills" / "nested"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: nested\ndescription: the real one\n---\nbody\n"
        )

        plugin = Plugin.load(plugin_dir)

        names = {s.name for s in plugin.skills}
        assert names == {"nested"}
        assert "root-ignored" not in names

    def test_load_plugin_no_skills_anywhere(self, tmp_path: Path):
        """既没有技能/也没有根 SKILL.md 的插件加载零技能。"""
        plugin_dir = tmp_path / "empty"
        plugin_dir.mkdir()
        (plugin_dir / "README.md").write_text("# not a skill\n")

        plugin = Plugin.load(plugin_dir)

        assert plugin.skills == []

    def test_skills_dir_nested_md_and_relaxed_names(self, tmp_path: Path):
        """嵌套的.md文件是技能资源，而不是技能； 名字放宽了。"""
        plugin_dir = tmp_path / "nested"
        skill_dir = plugin_dir / "skills" / "Summarize_Tool"
        (skill_dir / "references").mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: Summarize_Tool\ndescription: d\n---\nbody\n"
        )
        (skill_dir / "references" / "notes.md").write_text("# notes\n")
        (plugin_dir / "skills" / "shared").mkdir()
        (plugin_dir / "skills" / "shared" / "notes.md").write_text("# notes\n")
        (plugin_dir / "skills" / "loose.md").write_text("loose skill\n")
        (plugin_dir / "skills" / "readme.md").write_text("# readme\n")

        plugin = Plugin.load(plugin_dir)

        assert [s.name for s in plugin.skills] == ["Summarize_Tool", "loose"]

    def test_skills_dir_bad_skill_skips_only_itself(self, tmp_path: Path):
        """加载失败的技能不会中止剩余的技能。"""
        plugin_dir = tmp_path / "partial"
        skills_dir = plugin_dir / "skills"
        (skills_dir / "broken").mkdir(parents=True)
        (skills_dir / "broken" / "SKILL.md").write_bytes(b"\xff\xfe\xfa")
        (skills_dir / "good").mkdir()
        (skills_dir / "good" / "SKILL.md").write_text(
            "---\nname: good\ndescription: d\n---\nbody\n"
        )

        plugin = Plugin.load(plugin_dir)

        assert [s.name for s in plugin.skills] == ["good"]

    def test_load_plugin_with_hooks(self, tmp_path: Path):
        """测试使用钩子加载插件。"""
        plugin_dir = tmp_path / "hook-plugin"
        plugin_dir.mkdir()

        # 创建钩子目录
        hooks_dir = plugin_dir / "hooks"
        hooks_dir.mkdir()

        # 创建hooks.json
        hooks_json = hooks_dir / "hooks.json"
        hooks_json.write_text(
            """{
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "echo test"
                            }
                        ]
                    }
                ]
            }
        }"""
        )

        plugin = Plugin.load(plugin_dir)

        assert plugin.hooks is not None
        assert not plugin.hooks.is_empty()
        assert len(plugin.hooks.pre_tool_use) == 1

    def test_load_plugin_with_agents(self, tmp_path: Path):
        """测试加载具有智能体定义的插件。"""
        plugin_dir = tmp_path / "agent-plugin"
        plugin_dir.mkdir()

        # 创建智能体目录
        agents_dir = plugin_dir / "agents"
        agents_dir.mkdir()

        # 创建智能体
        agent_md = agents_dir / "test-agent.md"
        agent_md.write_text(
            """---
name: test-agent
description: A test agent. <example>When user asks about testing</example>
model: inherit
tools:
  - Read
  - Write
---

You are a test agent. Help users with testing.
"""
        )

        plugin = Plugin.load(plugin_dir)

        assert len(plugin.agents) == 1
        agent = plugin.agents[0]
        assert agent.name == "test-agent"
        assert agent.model == "inherit"
        assert "Read" in agent.tools
        assert "Write" in agent.tools
        assert len(agent.when_to_use_examples) == 1
        assert "When user asks about testing" in agent.when_to_use_examples[0]
        assert "You are a test agent" in agent.system_prompt

    def test_load_plugin_with_commands(self, tmp_path: Path):
        """测试加载带有命令定义的插件。"""
        plugin_dir = tmp_path / "command-plugin"
        plugin_dir.mkdir()

        # 创建命令目录
        commands_dir = plugin_dir / "commands"
        commands_dir.mkdir()

        # 创建命令
        command_md = commands_dir / "review.md"
        command_md.write_text(
            """---
description: Review code changes
argument-hint: <file-or-directory>
allowed-tools:
  - Read
  - Grep
---

Review the specified code and provide feedback.
"""
        )

        plugin = Plugin.load(plugin_dir)

        assert len(plugin.commands) == 1
        command = plugin.commands[0]
        assert command.name == "review"
        assert command.description == "Review code changes"
        assert command.argument_hint == "<file-or-directory>"
        assert "Read" in command.allowed_tools
        assert "Review the specified code" in command.content

    def test_load_plugin_with_entry_command(self, tmp_path: Path):
        """测试加载清单中带有 entry_command 的插件。"""
        plugin_dir = tmp_path / "city-weather"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()

        # 用 entry_command 编写清单
        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text(
            """{
            "name": "city-weather",
            "version": "1.0.0",
            "description": "Get current weather for any city",
            "entry_command": "now"
        }"""
        )

        plugin = Plugin.load(plugin_dir)

        assert plugin.name == "city-weather"
        assert plugin.manifest.entry_command == "now"
        assert plugin.entry_slash_command == "/city-weather:now"

    def test_load_plugin_without_entry_command(self, tmp_path: Path):
        """测试当未设置 entry_command 时，entry_slash_command 返回 None。"""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        plugin = Plugin.load(plugin_dir)

        assert plugin.manifest.entry_command is None
        assert plugin.entry_slash_command is None

    def test_command_to_skill_conversion(self, tmp_path: Path):
        """测试将命令转换为关键字触发的技能。"""
        from openhands.sdk.skills.trigger import KeywordTrigger

        plugin_dir = tmp_path / "city-weather"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text('{"name": "city-weather", "version": "1.0.0"}')

        commands_dir = plugin_dir / "commands"
        commands_dir.mkdir()
        command_md = commands_dir / "now.md"
        command_md.write_text(
            """---
description: Get current weather for a city
argument-hint: <city-name>
allowed-tools:
  - tavily_search
---

Fetch and display the current weather for the specified city.
"""
        )

        plugin = Plugin.load(plugin_dir)
        assert len(plugin.commands) == 1

        # 将命令转换为技能
        command = plugin.commands[0]
        skill = command.to_skill("city-weather")

        # 验证技能属性
        assert skill.name == "city-weather:now"
        assert skill.description == "Get current weather for a city"
        assert skill.allowed_tools is not None
        assert "tavily_search" in skill.allowed_tools

        # 验证触发格式
        assert isinstance(skill.trigger, KeywordTrigger)
        assert "/city-weather:now" in skill.trigger.keywords

        # 验证内容包含参数提示
        assert "$ARGUMENTS" in skill.content
        assert "Fetch and display the current weather" in skill.content

    def test_get_all_skills_with_commands(self, tmp_path: Path):
        """测试 get_all_skills 返回技能和命令派生技能。"""
        from openhands.sdk.skills.trigger import KeywordTrigger

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text('{"name": "test-plugin", "version": "1.0.0"}')

        # 使用技能创建技能目录
        skills_dir = plugin_dir / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "my-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: my-skill
description: A regular skill
---

This is a regular skill content.
"""
        )

        # 使用命令创建命令目录
        commands_dir = plugin_dir / "commands"
        commands_dir.mkdir()
        command_md = commands_dir / "greet.md"
        command_md.write_text(
            """---
description: Greet someone
argument-hint: <name>
---

Say hello to the specified person.
"""
        )

        plugin = Plugin.load(plugin_dir)

        # 验证单独的计数
        assert len(plugin.skills) == 1
        assert len(plugin.commands) == 1

        # 验证组合技能
        all_skills = plugin.get_all_skills()
        assert len(all_skills) == 2

        # 查找常规技能和命令衍生技能
        skill_names = {s.name for s in all_skills}
        assert "my-skill" in skill_names
        assert "test-plugin:greet" in skill_names

        # 验证命令派生技能是否具有关键字触发
        command_skill = next(s for s in all_skills if s.name == "test-plugin:greet")
        assert isinstance(command_skill.trigger, KeywordTrigger)
        assert "/test-plugin:greet" in command_skill.trigger.keywords

    def test_get_all_skills_empty_commands(self, tmp_path: Path):
        """不使用命令测试 get_all_skills。"""
        plugin_dir = tmp_path / "no-commands"
        plugin_dir.mkdir()

        # 创建仅包含技能的技能目录
        skills_dir = plugin_dir / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "only-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: only-skill
description: The only skill
---

Content for the only skill.
"""
        )

        plugin = Plugin.load(plugin_dir)

        all_skills = plugin.get_all_skills()
        assert len(all_skills) == 1
        assert all_skills[0].name == "only-skill"

    def test_load_all_plugins(self, tmp_path: Path):
        """测试从目录加载所有插件。"""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # 创建多个插件
        for i in range(3):
            plugin_dir = plugins_dir / f"plugin-{i}"
            plugin_dir.mkdir()
            manifest_dir = plugin_dir / ".plugin"
            manifest_dir.mkdir()
            manifest_file = manifest_dir / "plugin.json"
            manifest_file.write_text(f'{{"name": "plugin-{i}"}}')

        plugins = Plugin.load_all(plugins_dir)

        assert len(plugins) == 3
        names = {p.name for p in plugins}
        assert names == {"plugin-0", "plugin-1", "plugin-2"}

    def test_load_nonexistent_plugin(self, tmp_path: Path):
        """测试加载不存在的插件会引发错误。"""
        with pytest.raises(FileNotFoundError):
            Plugin.load(tmp_path / "nonexistent")

    def test_load_plugin_with_invalid_manifest(self, tmp_path: Path):
        """测试加载具有无效清单的插件会引发错误。"""
        plugin_dir = tmp_path / "invalid-plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text("not valid json")

        with pytest.raises(ValueError, match="Invalid JSON"):
            Plugin.load(plugin_dir)

    def test_load_all_nonexistent_directory(self, tmp_path: Path):
        """使用不存在的目录测试 load_all 返回空列表。"""
        plugins = Plugin.load_all(tmp_path / "nonexistent")
        assert plugins == []

    def test_load_all_with_failing_plugin(self, tmp_path: Path):
        """当插件加载失败时，测试 load_all 继续（第 197-198 行）。"""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # 创建一个有效的插件
        valid_dir = plugins_dir / "valid-plugin"
        valid_dir.mkdir()
        manifest_dir = valid_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text('{"name": "valid-plugin"}')

        # 创建无效的插件（将无法加载）
        invalid_dir = plugins_dir / "invalid-plugin"
        invalid_dir.mkdir()
        invalid_manifest_dir = invalid_dir / ".plugin"
        invalid_manifest_dir.mkdir()
        (invalid_manifest_dir / "plugin.json").write_text("not valid json")

        plugins = Plugin.load_all(plugins_dir)

        # 应该加载有效的插件并跳过无效的插件
        assert len(plugins) == 1
        assert plugins[0].name == "valid-plugin"

    def test_load_plugin_with_author_string(self, tmp_path: Path):
        """测试加载清单，其中作者为字符串（第 225 行）。"""
        plugin_dir = tmp_path / "author-plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()

        # 将作者作为字符串写入清单
        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text(
            """{
            "name": "author-plugin",
            "version": "1.0.0",
            "author": "Test Author <test@example.com>"
        }"""
        )

        plugin = Plugin.load(plugin_dir)

        assert plugin.name == "author-plugin"
        assert plugin.manifest.author is not None
        assert plugin.manifest.author.name == "Test Author"
        assert plugin.manifest.author.email == "test@example.com"

    def test_load_plugin_with_manifest_parse_error(self, tmp_path: Path):
        """测试加载清单时出现解析错误（第 230-231 行）。"""
        plugin_dir = tmp_path / "error-plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()

        # 编写缺少必填字段或类型错误的清单这将解析为 JSON 但失败 Pydantic 验证
        #
        manifest_file = manifest_dir / "plugin.json"
        manifest_file.write_text('{"name": 123}')  # 名称应该是字符串

        with pytest.raises(ValueError, match="Failed to parse manifest"):
            Plugin.load(plugin_dir)


class TestPluginAuthor:
    """测试 PluginAuthor 解析。"""

    def test_from_string_with_email(self):
        """测试用电子邮件解析作者字符串（第 22-25 行）。"""
        author = PluginAuthor.from_string("John Doe <john@example.com>")
        assert author.name == "John Doe"
        assert author.email == "john@example.com"

    def test_from_string_without_email(self):
        """测试解析没有电子邮件的作者字符串（第 26 行）。"""
        author = PluginAuthor.from_string("John Doe")
        assert author.name == "John Doe"
        assert author.email is None

    def test_from_string_with_whitespace(self):
        """测试解析带有额外空格的作者字符串。"""
        author = PluginAuthor.from_string("  John Doe  <  john@example.com  >  ")
        assert author.name == "John Doe"
        assert author.email == "john@example.com"

    def test_with_url(self):
        """使用 url 字段测试 PluginAuthor。"""
        author = PluginAuthor(
            name="John Doe",
            email="john@example.com",
            url="https://github.com/johndoe",
        )
        assert author.name == "John Doe"
        assert author.email == "john@example.com"
        assert author.url == "https://github.com/johndoe"

    def test_url_defaults_to_none(self):
        """测试 url 字段是否默认为 None。"""
        author = PluginAuthor(name="John Doe")
        assert author.url is None


class TestCommandDefinition:
    """测试 CommandDefinition 加载。"""

    def test_load_command_basic(self, tmp_path: Path):
        """测试加载基本命令定义（第 184-218 行）。"""
        command_md = tmp_path / "review.md"
        command_md.write_text(
            """---
description: Review code
argument-hint: <file>
allowed-tools:
  - Read
  - Grep
---

Review the specified file.
"""
        )

        command = CommandDefinition.load(command_md)

        assert command.name == "review"
        assert command.description == "Review code"
        assert command.argument_hint == "<file>"
        assert command.allowed_tools == ["Read", "Grep"]
        assert command.content == "Review the specified file."

    def test_load_command_with_argument_hint_list(self, tmp_path: Path):
        """使用参数提示作为列表测试加载命令。"""
        command_md = tmp_path / "multi-arg.md"
        command_md.write_text(
            """---
description: Multi arg command
argument-hint:
  - <file>
  - <options>
---

Content.
"""
        )

        command = CommandDefinition.load(command_md)
        assert command.argument_hint == "<file> <options>"

    def test_load_command_with_camel_case_fields(self, tmp_path: Path):
        """使用 camelCase 字段名称测试加载命令。"""
        command_md = tmp_path / "camel.md"
        command_md.write_text(
            """---
description: Camel case command
argumentHint: <arg>
allowedTools:
  - Tool1
---

Content.
"""
        )

        command = CommandDefinition.load(command_md)
        assert command.argument_hint == "<arg>"
        assert command.allowed_tools == ["Tool1"]

    def test_load_command_with_allowed_tools_as_string(self, tmp_path: Path):
        """使用允许工具作为字符串加载测试命令。"""
        command_md = tmp_path / "single-tool.md"
        command_md.write_text(
            """---
description: Single tool
allowed-tools: Read
---

Content.
"""
        )

        command = CommandDefinition.load(command_md)
        assert command.allowed_tools == ["Read"]

    def test_load_command_defaults(self, tmp_path: Path):
        """当未提供字段时，测试命令默认。"""
        command_md = tmp_path / "minimal.md"
        command_md.write_text(
            """---
---

Just instructions.
"""
        )

        command = CommandDefinition.load(command_md)
        assert command.name == "minimal"
        assert command.description == ""
        assert command.argument_hint is None
        assert command.allowed_tools == []

    def test_load_command_with_metadata(self, tmp_path: Path):
        """使用额外的元数据测试加载命令。"""
        command_md = tmp_path / "meta.md"
        command_md.write_text(
            """---
description: Meta command
custom_field: custom_value
---

Content.
"""
        )

        command = CommandDefinition.load(command_md)
        assert command.metadata.get("custom_field") == "custom_value"


class TestPluginMcpConfigLoading:
    """测试插件 MCP 配置加载和变量扩展。

    这些测试验证了 MCP 配置变量在插件加载期间被正确处理，特别是那些有默认值的变量不过
    早展开。
    """

    def test_plugin_mcp_config_preserve_unexpanded_variables(self, tmp_path: Path):
        """测试是否保留 MCP 服务器变量 WITHOUT 默认值。

        像 ${VAR} 这样的变量应该在插件加载后保留为占位符，以便以后可以在每个对话中扩
        展它们机密。
        """
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # 创建最小清单
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        # 使用未扩展的变量创建 MCP 配置（无默认值）
        mcp_json = plugin_dir / ".mcp.json"
        mcp_json.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "test-server": {
                            "url": "https://example.com",
                            "headers": {"Authorization": "Bearer ${SECRET_TOKEN}"},
                        }
                    }
                }
            )
        )

        plugin = Plugin.load(plugin_dir)

        # 没有默认值的变量应保留为占位符
        auth_header = dump_mcp_config(plugin.mcp_config)["test-server"]["headers"][
            "Authorization"
        ]
        assert auth_header == "Bearer ${SECRET_TOKEN}", (
            f"Expected placeholder to be preserved, got '{auth_header}'"
        )

    def test_plugin_mcp_config_preserve_variables_with_defaults(self, tmp_path: Path):
        """测试 MCP 服务器变量 WITH 默认值是否保留为占位符。

        像 ${VAR:-default} 这样的变量应该在插件加载后保留为占位符，以便以后可以在每个
        对话中扩展它们机密。

        这是一个回归测试，用于检查插件加载时默认变量被提前替换为默认值的双扩展 bug。

        Expected: 应保留占位符 ${VAR:-default}，替换不
        在插件加载期间使用默认值。
        """
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # 创建最小清单
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        # 使用具有默认值的变量创建 MCP 配置
        mcp_json = plugin_dir / ".mcp.json"
        mcp_json.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "test-server": {
                            "url": "https://example.com",
                            "headers": {
                                "Authorization": "Bearer ${SECRET_TOKEN:-fallback}"
                            },
                        }
                    }
                }
            )
        )

        plugin = Plugin.load(plugin_dir)

        # CRITICAL：具有默认值的变量应保留为占位符，
        # 插件加载期间不替换为“回退方案”
        auth_header = dump_mcp_config(plugin.mcp_config)["test-server"]["headers"][
            "Authorization"
        ]

        # 该断言将FAIL与当前的实现
        expected = "Bearer ${SECRET_TOKEN:-fallback}"
        assert auth_header == expected, (
            f"Expected placeholder '{expected}' to be preserved, "
            f"but got '{auth_header}'. "
            "This is the double-expansion bug: the default value was applied "
            "during plugin loading instead of being deferred."
        )

    def test_plugin_mcp_config_drops_unknown_server_fields(self, tmp_path: Path):
        """插件 .mcp.json 加载允许来自较新的 MCP 模式的字段。"""
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        (plugin_dir / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "test-server": {
                            "type": "shttp",
                            "url": "https://example.com/mcp",
                            "future_field": "ignored",
                        }
                    }
                }
            )
        )

        plugin = Plugin.load(plugin_dir)

        assert dump_mcp_config(plugin.mcp_config) == {
            "test-server": {
                "transport": "http",
                "url": "https://example.com/mcp",
            }
        }

    def test_plugin_mcp_skill_root_is_expanded(self, tmp_path: Path):
        """测试 SKILL_ROOT 在插件加载期间是否正确扩展。

        ${SKILL_ROOT} 是一个特殊变量，应在加载期间扩展到插件目录路径。
        """
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # 创建最小清单
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        # 使用 SKILL_ROOT 变量创建 MCP 配置
        mcp_json = plugin_dir / ".mcp.json"
        mcp_json.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "test-server": {
                            "command": "${SKILL_ROOT}/scripts/server.py",
                        }
                    }
                }
            )
        )

        plugin = Plugin.load(plugin_dir)

        # SKILL_ROOT 应该扩展到插件目录
        command = dump_mcp_config(plugin.mcp_config)["test-server"]["command"]
        assert str(plugin_dir) in command
        assert "${SKILL_ROOT}" not in command


class TestRootSkillMcpHandling:
    """测试根 SKILL.md 插件中正确的 MCP 配置处理。

    这些测试验证了对根 .mcp.json 文件使用不同语义加载两次的问题的修复，从而导致失败和
    不一致。
    """

    def test_malformed_root_mcp_json_does_not_drop_skill(self, tmp_path: Path):
        """问题#1：格式错误的 root .mcp.json 不应默默地放弃该技能。

        在修复之前：插件级加载器容忍了mcp.json（发出警告），但技能级加载器抛出了
        SkillValidationError，被广义的异常捕获，返回[] - 技
        能无声地被丢弃。

        修复后：skip_mcp=True防止双重加载，技能加载成功。
        """
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # 创建最小清单
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        # 创建有效根SKILL.md
        (plugin_dir / "SKILL.md").write_text(
            """---
name: test-skill
description: A test skill
---

# Test Skill

This is a test skill.
"""
        )

        # 创建 MALFORMED root .mcp.json（无效 JSON）
        (plugin_dir / ".mcp.json").write_text('{ "mcpServers": { invalid json }')

        # 加载插件
        plugin = Plugin.load(plugin_dir)

        # 该技能仍应加载（根技能会跳过 MCP 加载）
        assert len(plugin.skills) == 1
        assert plugin.skills[0].name == "test-skill"
        # 插件级 MCP 配置应为空（允许格式错误的文件）
        assert plugin.mcp_config == {}

    def test_root_mcp_json_not_double_loaded(self, tmp_path: Path):
        """问题 #2：Root .mcp.json 不应以不同的语义加载两次。

        修复之前：_load_plugin_mcp_config (expand_defaults=False) 和 Skill.load (
        expand_defaults=True) 加载相同的文件。

        修复后：仅在插件级别加载一次，技能使用skip_mcp=True。
        """
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # 创建最小清单
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        # 创建根SKILL.md
        (plugin_dir / "SKILL.md").write_text(
            """---
name: test-skill
description: A test skill
---

# Test Skill
"""
        )

        # 使用变量占位符创建 root .mcp.json
        (plugin_dir / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "test-server": {
                            "command": "server",
                            "args": ["--token", "${DB_TOKEN:-DEFAULT_TOKEN}"],
                        }
                    }
                }
            )
        )

        # 加载插件
        plugin = Plugin.load(plugin_dir)

        # 插件级 MCP 保留占位符 (expand_defaults=False)
        mcp_dump = dump_mcp_config(plugin.mcp_config)
        assert "${DB_TOKEN:-DEFAULT_TOKEN}" in mcp_dump["test-server"]["args"]

        # 技能应该已成功加载 skip_mcp=True
        assert len(plugin.skills) == 1
        assert plugin.skills[0].name == "test-skill"
        # 技能的mcp_tools应该是None（由于skip_mcp=True而未加载）
        assert plugin.skills[0].mcp_tools is None

    def test_root_skill_resources_not_duplicated(self, tmp_path: Path):
        """问题#3：对于根技能来说，资源不应该被发现两次。

        修复之前：discover_skill_resources 由 Skill.load() 和插件加载器调用（冗余）。

        修复后：只有 Skill.load() 发现资源，插件加载器不会调用
        discover_skill_resources。
        """
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # 创建最小清单
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        # 创建根SKILL.md
        (plugin_dir / "SKILL.md").write_text(
            """---
name: test-skill
description: A test skill
---

# Test Skill
"""
        )

        # 创建一些资源
        (plugin_dir / "test.txt").write_text("test resource")
        assets_dir = plugin_dir / "assets"
        assets_dir.mkdir()
        (assets_dir / "asset.txt").write_text("asset content")

        # 加载插件
        plugin = Plugin.load(plugin_dir)

        # 应该发现并附加资源
        assert len(plugin.skills) == 1
        assert plugin.skills[0].resources is not None
        assert plugin.skills[0].resources.assets == ["asset.txt"]
        # 如果没有引发异常，则此测试通过 - 修复可以防止冗余调用，但最终结果是相同的
        #

    def test_nested_skill_with_own_mcp_json_still_loads(self, tmp_path: Path):
        """使用自己的 .mcp.json 验证嵌套技能是否仍然可以正常工作。

        嵌套技能应继续正常加载自己的 .mcp.json （不跳过），因为它们位于与插件根目录不
        同的目录中。
        """
        import json

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # 创建最小清单
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        # 使用自己的 .mcp.json 创建嵌套技能
        skills_dir = plugin_dir / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "nested-skill"
        skill_dir.mkdir()

        (skill_dir / "SKILL.md").write_text(
            """---
name: nested-skill
description: A nested skill
---

# Nested Skill
"""
        )

        (skill_dir / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "nested-server": {
                            "command": "nested-server",
                        }
                    }
                }
            )
        )

        # 加载插件
        plugin = Plugin.load(plugin_dir)

        # 技能应该加载自己的 MCP 配置
        assert len(plugin.skills) == 1
        assert plugin.skills[0].name == "nested-skill"
        # 嵌套技能 SHOULD 有 mcp_tools（不跳过）
        assert plugin.skills[0].mcp_tools is not None
        assert "nested-server" in plugin.skills[0].mcp_tools


class TestDetectFormat:
    """测试插件格式选择合约 (detect_format())。

    detect_format() 是决定哪个 PluginFormat 加载插件目录的接缝。 今天只注册了 Claude
    Code 布局，因此每个目录都是回退方案；
    这些测试将该优先级固定，因此未来智能体插件格式（根 plugin.json）可以提前插入手动
    地改变Claude代码的行为。
    """

    def test_detects_claude_code_for_nested_manifest(self, tmp_path: Path):
        """具有嵌套 .claude-plugin 清单的目录选择 Claude Code。"""
        plugin_dir = tmp_path / "with-manifest"
        manifest_dir = plugin_dir / ".claude-plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text('{"name": "with-manifest"}')

        fmt = detect_format(plugin_dir)

        assert isinstance(fmt, ClaudeCodePluginFormat)
        assert fmt.name == "claude-code"

    def test_detects_claude_code_for_bare_dir(self, tmp_path: Path):
        """没有清单的目录仍然会回退到 Claude Code。"""
        plugin_dir = tmp_path / "bare-plugin"
        plugin_dir.mkdir()

        assert isinstance(detect_format(plugin_dir), ClaudeCodePluginFormat)

    def test_detected_format_loads_equivalent_plugin(self, tmp_path: Path):
        """detect_format() 中的策略加载与 Plugin.load() 相同的插件。"""
        plugin_dir = tmp_path / "roundtrip"
        manifest_dir = plugin_dir / ".plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text(
            '{"name": "roundtrip", "version": "3.1.4"}'
        )

        # Plugin.load() 必须首先解析：策略作用于解析后的目录，并且路径存储在返回的插件中
        # 。
        #
        resolved_dir = plugin_dir.resolve()
        via_strategy = detect_format(resolved_dir).load(resolved_dir)
        via_load = Plugin.load(plugin_dir)

        assert via_strategy.name == via_load.name == "roundtrip"
        assert via_strategy.version == via_load.version == "3.1.4"
        assert via_strategy.path == via_load.path

    def test_strategy_load_raises_for_missing_dir(self, tmp_path: Path):
        """直接策略 API 保护丢失的目录，如 Plugin.load()。"""
        missing = tmp_path / "does-not-exist"

        with pytest.raises(FileNotFoundError):
            detect_format(missing).load(missing)

    def test_subclass_without_name_is_rejected(self):
        """PluginFormat 子类必须声明类级别 ``name``。"""
        from openhands.sdk.plugin.format.base import PluginFormat

        with pytest.raises(TypeError, match="name"):

            class _NamelessFormat(PluginFormat):  # pyright: ignore[reportUnusedClass]
                @classmethod
                def detect(cls, plugin_dir: Path) -> bool:
                    return False

                def load_manifest(self, plugin_dir: Path) -> PluginManifest:
                    raise NotImplementedError

                def load_mcp_config(self, plugin_dir: Path):
                    raise NotImplementedError

                def load_hooks(self, plugin_dir: Path):
                    raise NotImplementedError

                def load_agents(self, plugin_dir: Path):
                    raise NotImplementedError

                def load_commands(self, plugin_dir: Path):
                    raise NotImplementedError
