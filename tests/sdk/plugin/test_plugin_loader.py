"""测试 load_plugins() 实用程序和 HookConfig.merge()。"""

import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from openhands.sdk import LLM, Agent
from openhands.sdk.context import AgentContext
from openhands.sdk.hooks import HookConfig
from openhands.sdk.hooks.config import HookDefinition, HookMatcher
from openhands.sdk.mcp.config import coerce_mcp_config
from openhands.sdk.plugin import (
    PluginFetchError,
    PluginSource,
    load_plugins,
)
from openhands.sdk.skills import Skill


@pytest.fixture
def mock_llm():
    """为智能体个测试创建模拟对象 LLM。"""
    return LLM(
        model="test/model",
        api_key=SecretStr("test-key"),
    )


@pytest.fixture
def basic_agent(mock_llm):
    """创建一个基本的智能体进行测试。"""
    return Agent(
        llm=mock_llm,
        tools=[],
    )


@pytest.fixture
def agent_with_context(mock_llm):
    """使用现有的上下文创建智能体。"""
    context = AgentContext(
        skills=[Skill(name="existing-skill", content="Existing skill content")]
    )
    return Agent(
        llm=mock_llm,
        tools=[],
        agent_context=context,
    )


@pytest.fixture
def agent_with_mcp(mock_llm):
    """使用现有的 MCP 配置创建智能体。"""
    return Agent(
        llm=mock_llm,
        tools=[],
        mcp_config=coerce_mcp_config({"existing-server": {"command": "test"}}),
    )


def create_test_plugin(
    plugin_dir: Path,
    name: str = "test-plugin",
    skills: list[dict] | None = None,
    mcp_config: dict | None = None,
    hooks: dict | None = None,
):
    """帮助程序创建测试插件目录。"""
    # 创建插件结构
    manifest_dir = plugin_dir / ".plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    # 编写清单
    manifest = {"name": name, "version": "1.0.0", "description": f"Test plugin {name}"}
    (manifest_dir / "plugin.json").write_text(json.dumps(manifest))

    # 写作技巧
    if skills:
        skills_dir = plugin_dir / "skills"
        skills_dir.mkdir(exist_ok=True)
        for skill in skills:
            skill_name = skill["name"]
            skill_content = skill["content"]
            skill_file = skills_dir / f"{skill_name}.md"
            skill_file.write_text(f"---\nname: {skill_name}\n---\n{skill_content}")

    # 写入MCP配置
    if mcp_config:
        mcp_file = plugin_dir / ".mcp.json"
        mcp_file.write_text(json.dumps(mcp_config))

    # 写钩子
    if hooks:
        hooks_dir = plugin_dir / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        hooks_file = hooks_dir / "hooks.json"
        hooks_file.write_text(json.dumps(hooks))

    return plugin_dir


class TestHookConfigMerge:
    """测试 HookConfig.merge 类方法。"""

    def test_merge_empty_list_returns_none(self):
        """测试空列表返回 None。"""
        result = HookConfig.merge([])
        assert result is None

    def test_merge_single_config(self):
        """测试合并单个配置会返回等效配置。"""
        config = HookConfig(
            pre_tool_use=[
                HookMatcher(matcher="*", hooks=[HookDefinition(command="test")])
            ]
        )
        result = HookConfig.merge([config])
        assert result is not None
        assert len(result.pre_tool_use) == 1
        assert result.pre_tool_use[0].matcher == "*"

    def test_merge_multiple_pre_tool_use(self):
        """测试合并多个配置连接 pre_tool_use。"""
        config1 = HookConfig(
            pre_tool_use=[
                HookMatcher(matcher="terminal", hooks=[HookDefinition(command="cmd1")])
            ]
        )
        config2 = HookConfig(
            pre_tool_use=[
                HookMatcher(matcher="*", hooks=[HookDefinition(command="cmd2")])
            ]
        )
        result = HookConfig.merge([config1, config2])
        assert result is not None
        assert len(result.pre_tool_use) == 2
        assert result.pre_tool_use[0].matcher == "terminal"
        assert result.pre_tool_use[1].matcher == "*"

    def test_merge_different_event_types(self):
        """测试具有不同事件类型的合并配置。"""
        config1 = HookConfig(
            pre_tool_use=[
                HookMatcher(matcher="*", hooks=[HookDefinition(command="pre")])
            ]
        )
        config2 = HookConfig(
            post_tool_use=[
                HookMatcher(matcher="*", hooks=[HookDefinition(command="post")])
            ]
        )
        result = HookConfig.merge([config1, config2])
        assert result is not None
        assert len(result.pre_tool_use) == 1
        assert len(result.post_tool_use) == 1

    def test_merge_all_event_types(self):
        """测试合并配置涵盖所有事件类型。"""
        config1 = HookConfig(
            pre_tool_use=[
                HookMatcher(matcher="*", hooks=[HookDefinition(command="c1")])
            ],
            session_start=[
                HookMatcher(matcher="*", hooks=[HookDefinition(command="c2")])
            ],
        )
        config2 = HookConfig(
            post_tool_use=[
                HookMatcher(matcher="*", hooks=[HookDefinition(command="c3")])
            ],
            session_end=[
                HookMatcher(matcher="*", hooks=[HookDefinition(command="c4")])
            ],
        )
        config3 = HookConfig(
            user_prompt_submit=[
                HookMatcher(matcher="*", hooks=[HookDefinition(command="c5")])
            ],
            stop=[HookMatcher(matcher="*", hooks=[HookDefinition(command="c6")])],
        )
        result = HookConfig.merge([config1, config2, config3])
        assert result is not None
        assert len(result.pre_tool_use) == 1
        assert len(result.post_tool_use) == 1
        assert len(result.user_prompt_submit) == 1
        assert len(result.session_start) == 1
        assert len(result.session_end) == 1
        assert len(result.stop) == 1

    def test_merge_empty_configs_returns_none(self):
        """仅测试合并空配置返回 None。"""
        config1 = HookConfig()
        config2 = HookConfig()
        result = HookConfig.merge([config1, config2])
        assert result is None


class TestLoadPluginsSinglePlugin:
    """使用单个插件测试 load_plugins。"""

    def test_load_empty_list_returns_unchanged_agent(self, basic_agent):
        """测试空插件列表返回智能体不变。"""
        updated_agent, hooks = load_plugins([], basic_agent)
        assert updated_agent is basic_agent
        assert hooks is None

    def test_load_single_plugin_with_skills(self, tmp_path: Path, basic_agent):
        """测试加载具有技能的插件合并到智能体上下文。"""
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="test-plugin",
            skills=[{"name": "my-skill", "content": "Skill content here"}],
        )

        plugins = [PluginSource(source=str(plugin_dir))]
        updated_agent, hooks = load_plugins(plugins, basic_agent)

        assert updated_agent.agent_context is not None
        assert len(updated_agent.agent_context.skills) == 1
        assert updated_agent.agent_context.skills[0].name == "my-skill"
        assert hooks is None

    def test_load_single_plugin_with_mcp(self, tmp_path: Path, basic_agent):
        """测试加载具有 MCP 配置的插件合并到智能体。"""
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="test-plugin",
            mcp_config={"mcpServers": {"test-server": {"command": "test-cmd"}}},
        )

        plugins = [PluginSource(source=str(plugin_dir))]
        updated_agent, hooks = load_plugins(plugins, basic_agent)

        assert "test-server" in updated_agent.mcp_config
        assert hooks is None

    def test_load_single_plugin_with_hooks(self, tmp_path: Path, basic_agent):
        """测试加载带有钩子的插件会返回钩子配置。"""
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="test-plugin",
            hooks={
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "*", "hooks": [{"command": "echo test"}]}
                    ]
                }
            },
        )

        plugins = [PluginSource(source=str(plugin_dir))]
        updated_agent, hooks = load_plugins(plugins, basic_agent)

        assert hooks is not None
        assert len(hooks.pre_tool_use) == 1


class TestLoadPluginsMultiplePlugins:
    """使用多个插件测试 load_plugins。"""

    def test_load_multiple_plugins_skills_override(self, tmp_path: Path, basic_agent):
        """测试以后的插件是否会按名称覆盖技能。"""
        plugin1 = create_test_plugin(
            tmp_path / "plugin1",
            name="plugin1",
            skills=[{"name": "shared-skill", "content": "First content"}],
        )
        plugin2 = create_test_plugin(
            tmp_path / "plugin2",
            name="plugin2",
            skills=[{"name": "shared-skill", "content": "Second content"}],
        )

        plugins = [
            PluginSource(source=str(plugin1)),
            PluginSource(source=str(plugin2)),
        ]
        updated_agent, _ = load_plugins(plugins, basic_agent)

        assert updated_agent.agent_context is not None
        assert len(updated_agent.agent_context.skills) == 1
        assert "Second content" in updated_agent.agent_context.skills[0].content

    def test_load_multiple_plugins_mcp_override(self, tmp_path: Path, basic_agent):
        """测试以后的插件是否通过按键覆盖 MCP 配置。"""
        plugin1 = create_test_plugin(
            tmp_path / "plugin1",
            name="plugin1",
            mcp_config={"mcpServers": {"server": {"command": "first"}}},
        )
        plugin2 = create_test_plugin(
            tmp_path / "plugin2",
            name="plugin2",
            mcp_config={"mcpServers": {"server": {"command": "second"}}},
        )

        plugins = [
            PluginSource(source=str(plugin1)),
            PluginSource(source=str(plugin2)),
        ]
        updated_agent, _ = load_plugins(plugins, basic_agent)

        assert updated_agent.mcp_config["server"].command == "second"

    def test_load_multiple_plugins_hooks_concatenate(self, tmp_path: Path, basic_agent):
        """测试所有插件的挂钩是否已连接。"""
        plugin1 = create_test_plugin(
            tmp_path / "plugin1",
            name="plugin1",
            hooks={
                "hooks": {
                    "PreToolUse": [{"matcher": "a", "hooks": [{"command": "c1"}]}]
                }
            },
        )
        plugin2 = create_test_plugin(
            tmp_path / "plugin2",
            name="plugin2",
            hooks={
                "hooks": {
                    "PreToolUse": [{"matcher": "b", "hooks": [{"command": "c2"}]}]
                }
            },
        )

        plugins = [
            PluginSource(source=str(plugin1)),
            PluginSource(source=str(plugin2)),
        ]
        _, hooks = load_plugins(plugins, basic_agent)

        assert hooks is not None
        assert len(hooks.pre_tool_use) == 2

    def test_load_multiple_plugins_different_skills(self, tmp_path: Path, basic_agent):
        """测试来自多个插件的不同技能的组合。"""
        plugin1 = create_test_plugin(
            tmp_path / "plugin1",
            name="plugin1",
            skills=[{"name": "skill-a", "content": "A"}],
        )
        plugin2 = create_test_plugin(
            tmp_path / "plugin2",
            name="plugin2",
            skills=[{"name": "skill-b", "content": "B"}],
        )

        plugins = [
            PluginSource(source=str(plugin1)),
            PluginSource(source=str(plugin2)),
        ]
        updated_agent, _ = load_plugins(plugins, basic_agent)

        assert updated_agent.agent_context is not None
        skill_names = [s.name for s in updated_agent.agent_context.skills]
        assert "skill-a" in skill_names
        assert "skill-b" in skill_names


class TestLoadPluginsWithExistingContext:
    """使用已存在上下文的智能体测试 load_plugins。"""

    def test_preserves_existing_skills(self, tmp_path: Path, agent_with_context):
        """测试加载插件时是否保留现有技能。"""
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="plugin",
            skills=[{"name": "new-skill", "content": "New content"}],
        )

        plugins = [PluginSource(source=str(plugin_dir))]
        updated_agent, _ = load_plugins(plugins, agent_with_context)

        assert updated_agent.agent_context is not None
        skill_names = [s.name for s in updated_agent.agent_context.skills]
        assert "existing-skill" in skill_names
        assert "new-skill" in skill_names

    def test_plugin_skill_overrides_existing(self, tmp_path: Path, agent_with_context):
        """测试同名插件技能是否覆盖现有技能。"""
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="plugin",
            skills=[{"name": "existing-skill", "content": "Plugin content"}],
        )

        plugins = [PluginSource(source=str(plugin_dir))]
        updated_agent, _ = load_plugins(plugins, agent_with_context)

        assert updated_agent.agent_context is not None
        assert len(updated_agent.agent_context.skills) == 1
        assert "Plugin content" in updated_agent.agent_context.skills[0].content

    def test_preserves_existing_mcp(self, tmp_path: Path, agent_with_mcp):
        """测试现有的 MCP 配置是否被保留。"""
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="plugin",
            mcp_config={"mcpServers": {"new-server": {"command": "new"}}},
        )

        plugins = [PluginSource(source=str(plugin_dir))]
        updated_agent, _ = load_plugins(plugins, agent_with_mcp)

        assert "existing-server" in updated_agent.mcp_config
        assert "new-server" in updated_agent.mcp_config


class TestLoadPluginsMaxSkills:
    """测试 max_skills 限制执行。"""

    def test_max_skills_not_exceeded(self, tmp_path: Path, basic_agent):
        """测试在max_skills下是否加载成功。"""
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="plugin",
            skills=[
                {"name": "skill-1", "content": "C1"},
                {"name": "skill-2", "content": "C2"},
            ],
        )

        plugins = [PluginSource(source=str(plugin_dir))]
        updated_agent, _ = load_plugins(plugins, basic_agent, max_skills=10)

        assert updated_agent.agent_context is not None
        assert len(updated_agent.agent_context.skills) == 2

    def test_max_skills_exceeded_raises_error(self, tmp_path: Path, basic_agent):
        """测试超过 max_skills 会引发 ValueError。"""
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="plugin",
            skills=[
                {"name": "skill-1", "content": "C1"},
                {"name": "skill-2", "content": "C2"},
                {"name": "skill-3", "content": "C3"},
            ],
        )

        plugins = [PluginSource(source=str(plugin_dir))]
        with pytest.raises(ValueError, match="exceeds maximum"):
            load_plugins(plugins, basic_agent, max_skills=2)


class TestLoadPluginsErrorHandling:
    """测试load_plugins中的错误处理。"""

    def test_nonexistent_plugin_raises_error(self, basic_agent):
        """测试不存在的插件路径是否会引发错误。"""
        plugins = [PluginSource(source="/nonexistent/path")]
        with pytest.raises(PluginFetchError):
            load_plugins(plugins, basic_agent)

    def test_invalid_plugin_dir_raises_error(self, tmp_path: Path, basic_agent):
        """测试无效插件（无清单）是否仍然加载推断的清单。"""
        # 创建一个空目录（无清单）
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        plugins = [PluginSource(source=str(empty_dir))]
        # 不应引发 - Plugin.load() 从目录名称推断清单
        updated_agent, _ = load_plugins(plugins, basic_agent)
        assert updated_agent is not None


class TestPluginSource:
    """测试 PluginSource 模型。"""

    def test_create_basic(self):
        """测试创建一个基本的 PluginSource。"""
        source = PluginSource(source="github:owner/repo")
        assert source.source == "github:owner/repo"
        assert source.ref is None
        assert source.repo_path is None

    def test_create_with_ref(self):
        """测试使用 ref 创建 PluginSource。"""
        source = PluginSource(source="github:owner/repo", ref="v1.0.0")
        assert source.ref == "v1.0.0"

    def test_create_with_repo_path(self):
        """测试用 repo_path 创建 PluginSource。"""
        source = PluginSource(
            source="github:owner/monorepo",
            repo_path="plugins/my-plugin",
        )
        assert source.repo_path == "plugins/my-plugin"

    def test_create_local_path(self):
        """测试使用本地路径创建 PluginSource。"""
        source = PluginSource(source="/path/to/plugin")
        assert source.source == "/path/to/plugin"
