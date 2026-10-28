"""测试插件合并实用程序。"""

import pytest

from openhands.sdk.context import AgentContext
from openhands.sdk.mcp.config import MCPServer
from openhands.sdk.plugin import Plugin, PluginManifest
from openhands.sdk.skills import Skill


def mcp_config(
    servers: dict[str, MCPServer] | None = None,
) -> dict[str, MCPServer]:
    return servers or {}


class TestPluginAddSkillsTo:
    """测试 Plugin.add_skills_to() 方法。"""

    def test_add_skills_to_empty_plugin(self, empty_plugin):
        """测试从空插件添加技能返回不变上下文。"""
        context = AgentContext(skills=[])
        new_context = empty_plugin.add_skills_to(context)
        assert new_context.skills == []

    def test_add_skills_to_none_context_empty_plugin(self, empty_plugin):
        """使用 None 上下文和空插件测试添加技能。"""
        new_context = empty_plugin.add_skills_to(None)
        assert isinstance(new_context, AgentContext)
        assert new_context.skills == []

    def test_add_skills_to_none_input(self, mock_plugin_with_skills):
        """测试使用 None 输入添加技能会创建新的上下文。"""
        new_context = mock_plugin_with_skills.add_skills_to()
        assert isinstance(new_context, AgentContext)
        assert len(new_context.skills) > 0

    def test_add_skills_to_with_skills(self, mock_plugin_with_skills):
        """测试将插件技能添加到上下文。"""
        context = AgentContext(skills=[])
        new_context = mock_plugin_with_skills.add_skills_to(context)
        assert len(new_context.skills) == len(mock_plugin_with_skills.skills)

    def test_add_skills_to_adds_new_skill(self, mock_skill, another_mock_skill):
        """测试添加技能在不冲突的情况下添加新技能。"""
        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            skills=[another_mock_skill],
        )
        context = AgentContext(skills=[mock_skill])
        new_context = plugin.add_skills_to(context)
        assert len(new_context.skills) == 2
        skill_names = {s.name for s in new_context.skills}
        assert skill_names == {mock_skill.name, another_mock_skill.name}

    def test_add_skills_to_overrides_existing_skill(self):
        """测试插件技能会覆盖同名的现有技能。"""
        original_skill = Skill(name="test-skill", content="Original content")
        updated_skill = Skill(name="test-skill", content="Updated content")
        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            skills=[updated_skill],
        )
        context = AgentContext(skills=[original_skill])
        new_context = plugin.add_skills_to(context)
        assert len(new_context.skills) == 1
        assert new_context.skills[0].content == "Updated content"

    def test_add_skills_to_preserves_insertion_order(self):
        """测试 add_skills_to 保留现有技能的顺序。"""
        skill_a = Skill(name="skill-a", content="A")
        skill_b = Skill(name="skill-b", content="B")
        skill_c = Skill(name="skill-c", content="C")
        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            skills=[skill_c],
        )
        context = AgentContext(skills=[skill_a, skill_b])
        new_context = plugin.add_skills_to(context)
        skill_names = [s.name for s in new_context.skills]
        assert skill_names == ["skill-a", "skill-b", "skill-c"]

    def test_add_skills_to_returns_new_context(self, mock_skill):
        """测试 add_skills_to 返回新的上下文实例，而不修改原始实例。"""
        new_skill = Skill(name="new-skill", content="New")
        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            skills=[new_skill],
        )
        original_context = AgentContext(skills=[mock_skill])
        new_context = plugin.add_skills_to(original_context)
        # 原来的上下文应该不变
        assert len(original_context.skills) == 1
        assert len(new_context.skills) == 2
        assert new_context is not original_context

    def test_add_skills_to_enforces_max_skills(self, mock_plugin_with_skills):
        """测试 add_skills_to 强制执行 max_skills 限制。"""
        context = AgentContext(skills=[])
        with pytest.raises(ValueError, match="exceeds maximum"):
            mock_plugin_with_skills.add_skills_to(context, max_skills=0)

    def test_add_skills_to_max_skills_with_existing(self, mock_skill):
        """测试max_skills统计合并后的独特技能。"""
        plugin_skill_1 = Skill(name="plugin-skill-1", content="P1")
        plugin_skill_2 = Skill(name="plugin-skill-2", content="P2")
        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            skills=[plugin_skill_1, plugin_skill_2],
        )
        context = AgentContext(skills=[mock_skill])

        # 限制为 3 应允许合并（1 个现有 + 2 个新 = 3）
        new_context = plugin.add_skills_to(context, max_skills=3)
        assert len(new_context.skills) == 3

        # 2 的限制应该失败 (3 > 2)
        with pytest.raises(ValueError, match="exceeds maximum"):
            plugin.add_skills_to(context, max_skills=2)

    def test_add_skills_to_max_skills_with_override(self):
        """当插件覆盖现有技能时，测试 max_skills 计数正确。"""
        existing_skill = Skill(name="shared-skill", content="Old")
        context = AgentContext(skills=[existing_skill])

        plugin_skill = Skill(name="shared-skill", content="New")
        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            skills=[plugin_skill],
        )

        new_context = plugin.add_skills_to(context, max_skills=1)
        assert len(new_context.skills) == 1
        assert new_context.skills[0].content == "New"

    def test_add_skills_to_preserves_context_fields(self, mock_plugin_with_skills):
        """测试 add_skills_to 保留其他 AgentContext 字段。"""
        context = AgentContext(
            skills=[],
            system_message_suffix="Custom suffix",
        )
        new_context = mock_plugin_with_skills.add_skills_to(context)
        assert new_context.system_message_suffix == context.system_message_suffix


class TestPluginAddMcpConfigTo:
    """测试 Plugin.add_mcp_config_to() 方法。"""

    def test_add_mcp_config_to_empty_plugin(self, empty_plugin):
        """测试从空插件添加 MCP 服务器会返回空地图。"""
        new_mcp = empty_plugin.add_mcp_config_to(mcp_config())
        assert new_mcp == {}

    def test_add_mcp_config_to_both_none(self, empty_plugin):
        """测试添加 MCP 服务器与 None 会返回一个空地图。"""
        new_mcp = empty_plugin.add_mcp_config_to(None)
        assert new_mcp == {}

    def test_add_mcp_config_to_none_input(self, mock_plugin_with_mcp):
        """测试使用 None 输入添加 MCP 个服务器。"""
        new_mcp = mock_plugin_with_mcp.add_mcp_config_to()
        assert new_mcp == mock_plugin_with_mcp.mcp_config

    def test_add_mcp_config_to_with_config(self, mock_plugin_with_mcp):
        """测试添加插件 MCP 服务器。"""
        new_mcp = mock_plugin_with_mcp.add_mcp_config_to(mcp_config())
        assert new_mcp == mock_plugin_with_mcp.mcp_config

    def test_add_mcp_config_to_merges_servers(self):
        """测试 add_mcp_config_to 返回正确合并的 MCP 服务器。"""
        base_mcp = mcp_config({"server1": MCPServer(command="base")})
        plugin_mcp = mcp_config({"server2": MCPServer(command="plugin")})

        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            mcp_config=plugin_mcp,
        )

        new_mcp = plugin.add_mcp_config_to(base_mcp)

        assert new_mcp["server1"].command == "base"
        assert new_mcp["server2"].command == "plugin"

    def test_add_mcp_config_to_plugin_overrides(self):
        """测试插件 MCP 服务器会覆盖相同密钥的基本服务器。"""
        base_mcp = mcp_config(
            {"server1": MCPServer(command="python", args=["-m", "base_server"])}
        )
        plugin_mcp = mcp_config(
            {"server1": MCPServer(command="python", args=["-m", "plugin_server"])}
        )

        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            mcp_config=plugin_mcp,
        )

        new_mcp = plugin.add_mcp_config_to(base_mcp)
        assert new_mcp["server1"].args == ["-m", "plugin_server"]

    def test_add_mcp_config_to_does_not_modify_inputs(self):
        """测试 add_mcp_config_to 不修改输入映射。"""
        base_mcp = mcp_config({"server1": MCPServer(command="python")})
        plugin_mcp = mcp_config({"server2": MCPServer(command="node")})
        original_base = dict(base_mcp)
        original_plugin = dict(plugin_mcp)

        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            mcp_config=plugin_mcp,
        )

        plugin.add_mcp_config_to(base_mcp)

        assert base_mcp == original_base
        assert plugin_mcp == original_plugin

    def test_add_mcp_config_to_merges_mcp_config(self):
        """测试 add_mcp_config_to 按服务器名称合并本机服务器映射。"""
        base_mcp = mcp_config({"server1": MCPServer(command="base")})
        plugin_mcp = mcp_config({"server2": MCPServer(command="plugin")})

        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            mcp_config=plugin_mcp,
        )

        new_mcp = plugin.add_mcp_config_to(base_mcp)

        assert "server1" in new_mcp
        assert "server2" in new_mcp

    def test_add_mcp_config_to_mcp_config_plugin_overrides(self):
        """测试插件 MCP 配置覆盖相同服务器名称的基本配置。"""
        base_mcp = mcp_config({"server1": MCPServer(command="base")})
        plugin_mcp = mcp_config({"server1": MCPServer(command="plugin")})

        plugin = Plugin(
            manifest=PluginManifest(name="test", version="1.0.0", description="Test"),
            path="/tmp/test",
            mcp_config=plugin_mcp,
        )

        new_mcp = plugin.add_mcp_config_to(base_mcp)

        assert new_mcp["server1"].command == "plugin"


# 测试夹具


@pytest.fixture
def mock_skill():
    """创建模拟对象技能进行测试。"""
    return Skill(
        name="test-skill",
        content="Test skill content",
    )


@pytest.fixture
def another_mock_skill():
    """创建另一个模拟对象技能进行测试。"""
    return Skill(
        name="another-skill",
        content="Another skill content",
    )


@pytest.fixture
def empty_plugin():
    """创建一个空插件。"""
    return Plugin(
        manifest=PluginManifest(
            name="empty", version="1.0.0", description="Empty plugin"
        ),
        path="/tmp/empty",
    )


@pytest.fixture
def mock_plugin_with_skills(mock_skill, another_mock_skill):
    """创建一个具有技能的插件。"""
    return Plugin(
        manifest=PluginManifest(
            name="test-plugin", version="1.0.0", description="Test plugin"
        ),
        path="/tmp/test",
        skills=[mock_skill, another_mock_skill],
    )


@pytest.fixture
def mock_plugin_with_mcp():
    """使用 MCP 个服务器创建一个插件。"""
    return Plugin(
        manifest=PluginManifest(
            name="mcp-plugin", version="1.0.0", description="MCP plugin"
        ),
        path="/tmp/mcp",
        mcp_config=mcp_config(
            {"server1": MCPServer(command="python", args=["-m", "server1"])}
        ),
    )
