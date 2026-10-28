from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from openhands.sdk import LLM, Agent
from openhands.sdk.context.condenser import LLMSummarizingCondenser, NoOpCondenser
from openhands.sdk.hooks.config import HookConfig, HookDefinition, HookMatcher
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.mcp.config import MCPServer, dump_mcp_config
from openhands.sdk.subagent.registry import (
    _reset_registry_for_tests,
    agent_definition_to_factory,
    get_agent_factory,
    get_factory_info,
    register_agent,
    register_agent_if_absent,
    register_file_agents,
    register_plugin_agents,
)
from openhands.sdk.subagent.schema import AgentDefinition


def setup_function() -> None:
    _reset_registry_for_tests()


def teardown_function() -> None:
    _reset_registry_for_tests()


def _make_test_llm() -> LLM:
    """创建一个真实的 LLM 实例进行测试。"""
    return LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )


def _create_skill_file(skills_dir: Path, name: str, content: str) -> None:
    """在给定的技能目录中创建技能 .md 文件。"""
    skill_file = skills_dir / f"{name}.md"
    skill_file.write_text(
        f"---\nname: {name}\ntriggers:\n  - {name}\n---\n\n{content}\n"
    )


def test_register_file_agents_project_priority(tmp_path: Path) -> None:
    """项目级别智能体优先于同名的用户级别智能体。"""
    # 项目.代理/
    project_agents_dir = tmp_path / ".agents" / "agents"
    project_agents_dir.mkdir(parents=True)
    (project_agents_dir / "shared-agent.md").write_text(
        "---\nname: shared-agent\ndescription: Project version\n---\n\nProject prompt."
    )

    # 用户〜/.agents/（使用单独的临时目录）
    user_home = tmp_path / "fake_home"
    user_home.mkdir(parents=True)
    user_agents_dir = user_home / ".agents" / "agents"
    user_agents_dir.mkdir(parents=True)
    (user_agents_dir / "shared-agent.md").write_text(
        "---\nname: shared-agent\ndescription: User version\n---\n\nUser prompt."
    )

    with patch("openhands.sdk.subagent.load.Path.home", return_value=user_home):
        registered = register_file_agents(tmp_path)

    assert "shared-agent" in registered
    # 验证项目版本已赢得
    factory = get_agent_factory("shared-agent")
    assert factory.definition.description == "Project version"


def test_register_file_agents_skips_programmatic(tmp_path: Path) -> None:
    """不覆盖以编程方式注册的智能体。"""

    # 首先以编程方式注册智能体
    def existing_factory(llm: LLM) -> Agent:
        return cast(Agent, MagicMock())

    register_agent(
        name="existing-agent",
        factory_func=existing_factory,
        description="Programmatic version",
    )

    # 创建具有相同名称的基于文件的智能体
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "existing-agent.md").write_text(
        "---\nname: existing-agent\ndescription: File version\n---\n\nFile prompt."
    )

    with patch(
        "openhands.sdk.subagent.load.Path.home", return_value=tmp_path / "no_user"
    ):
        registered = register_file_agents(tmp_path)

    # 文件智能体应不已注册（程序化获胜）
    assert "existing-agent" not in registered
    # 验证编程版本是否仍然存在
    factory = get_agent_factory("existing-agent")
    assert factory.definition.description == "Programmatic version"


def test_register_plugin_agents(tmp_path: Path) -> None:
    """插件智能体通过 register_agent_if_absent 注册。"""
    plugin_agent = AgentDefinition(
        name="plugin-agent",
        description="From plugin",
        model="inherit",
        tools=["ReadTool"],
        system_prompt="Plugin prompt.",
    )

    registered = register_plugin_agents([plugin_agent], work_dir=tmp_path)

    assert registered == ["plugin-agent"]
    factory = get_agent_factory("plugin-agent")
    assert factory.definition.description == "From plugin"


def test_register_plugin_agents_skips_existing(tmp_path: Path) -> None:
    """插件智能体不会覆盖以编程方式注册的智能体。"""

    def existing_factory(llm: LLM) -> Agent:
        return cast(Agent, MagicMock())

    register_agent(
        name="my-agent",
        factory_func=existing_factory,
        description="Programmatic",
    )

    plugin_agent = AgentDefinition(
        name="my-agent",
        description="Plugin version",
        model="inherit",
        tools=[],
        system_prompt="",
    )

    registered = register_plugin_agents([plugin_agent], work_dir=tmp_path)
    assert registered == []
    # 程序化版本仍然存在
    factory = get_agent_factory("my-agent")
    assert factory.definition.description == "Programmatic"


def test_register_file_agents_skips_agent_with_missing_skill(tmp_path: Path) -> None:
    """跳过指定缺失技能的智能体； 另一个智能体寄存器。"""
    skills_dir = tmp_path / ".agents" / "skills"
    skills_dir.mkdir(parents=True)
    _create_skill_file(skills_dir, "real-skill", "Real skill content.")

    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    bad_file = agents_dir / "bad-agent.md"
    bad_file.write_text(
        "---\nname: bad-agent\ndescription: Bad\nskills: missing-skill\n---\n\nBad."
    )
    (agents_dir / "good-agent.md").write_text(
        "---\nname: good-agent\ndescription: Good\nskills: real-skill\n---\n\nGood."
    )

    with (
        patch(
            "openhands.sdk.subagent.load.Path.home", return_value=tmp_path / "no_user"
        ),
        patch("openhands.sdk.subagent.registry.logger") as mock_logger,
    ):
        registered = register_file_agents(tmp_path)

    assert registered == ["good-agent"]
    with pytest.raises(ValueError, match="Unknown agent 'bad-agent'"):
        get_agent_factory("bad-agent")
    agent = get_agent_factory("good-agent").factory_func(_make_test_llm())
    assert agent.agent_context is not None
    assert [s.name for s in agent.agent_context.skills] == ["real-skill"]

    warning = mock_logger.warning.call_args.args[0]
    assert "bad-agent" in warning
    assert str(bad_file) in warning
    assert "missing-skill" in warning


def test_register_plugin_agents_skips_agent_with_missing_skill(
    tmp_path: Path,
) -> None:
    """跳过命名缺失技能的插件智能体； 其他人注册。"""
    bad = AgentDefinition(
        name="bad-plugin-agent",
        description="Bad",
        skills=["missing-skill"],
    )
    good = AgentDefinition(name="good-plugin-agent", description="Good")

    with patch("openhands.sdk.subagent.registry.logger") as mock_logger:
        registered = register_plugin_agents([bad, good], work_dir=tmp_path)

    assert registered == ["good-plugin-agent"]
    warning = mock_logger.warning.call_args.args[0]
    assert "bad-plugin-agent" in warning
    assert "missing-skill" in warning


def test_register_agent_if_absent_existing() -> None:
    """register_agent_if_absent 为现有智能体返回 False。"""

    def factory1(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    def factory2(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    register_agent(name="dup_agent", factory_func=factory1, description="First")

    result = register_agent_if_absent(
        name="dup_agent",
        factory_func=factory2,
        description="Second",
    )
    assert result is False

    # 应保留首次注册
    factory = get_agent_factory("dup_agent")
    assert factory.definition.description == "First"


def test_agent_definition_to_factory_basic() -> None:
    """工厂使用正确的工具、系统提示词和 LLM 创建智能体。"""
    agent_def = AgentDefinition(
        name="test-agent",
        description="A test agent",
        model="inherit",
        tools=[],
        system_prompt="You are a test agent.",
    )

    factory = agent_definition_to_factory(agent_def)
    llm = _make_test_llm()
    agent = factory(llm)

    assert isinstance(agent, Agent)
    # 检查工具为空
    assert agent.tools == []
    # 检查技能（系统提示词为始终激活的技能）
    assert agent.agent_context is not None
    assert agent.agent_context.system_message_suffix == "You are a test agent."


def test_agent_definition_to_factory_model_inherit() -> None:
    """模型“继承”保留父级 LLM。"""
    agent_def = AgentDefinition(
        name="inherit-agent",
        description="Uses parent model",
        model="inherit",
        tools=[],
        system_prompt="Test prompt.",
    )

    factory = agent_definition_to_factory(agent_def)
    llm = _make_test_llm()
    agent = factory(llm)

    assert agent.llm is llm
    assert agent.llm.model == "gpt-4o"


def test_agent_definition_to_factory_model_override() -> None:
    """不是存储的配置文件的非继承模型引发 ValueError。"""
    agent_def = AgentDefinition(
        name="override-agent",
        description="Uses specific model",
        model="claude-sonnet-4-20250514",
        tools=[],
        system_prompt="Test prompt.",
    )

    factory = agent_definition_to_factory(agent_def)
    llm = _make_test_llm()

    with pytest.raises(ValueError, match="not found in profile store"):
        factory(llm)


def test_agent_definition_to_factory_no_system_prompt() -> None:
    """具有空系统提示词的工厂创建没有 agent_context 的智能体。"""
    agent_def = AgentDefinition(
        name="no-prompt-agent",
        description="No prompt",
        model="inherit",
        system_prompt="",
    )

    factory = agent_definition_to_factory(agent_def)
    llm = _make_test_llm()
    agent = factory(llm)

    assert agent.agent_context is None


def test_agent_definition_to_factory_with_skills(tmp_path: Path) -> None:
    """工厂解析技能名称并将其传递给 AgentContext。"""
    # 在项目目录下创建技能文件
    skills_dir = tmp_path / ".agents" / "skills"
    skills_dir.mkdir(parents=True)
    _create_skill_file(skills_dir, "test-skill", "Skill content here.")

    agent_def = AgentDefinition(
        name="skilled-agent",
        description="Agent with skills",
        model="inherit",
        tools=[],
        skills=["test-skill"],
        system_prompt="You are a skilled agent.",
    )

    factory = agent_definition_to_factory(agent_def, work_dir=tmp_path)
    llm = _make_test_llm()
    agent = factory(llm)

    assert agent.agent_context is not None
    assert len(agent.agent_context.skills) == 1
    assert agent.agent_context.skills[0].name == "test-skill"
    assert "Skill content here." in agent.agent_context.skills[0].content
    assert agent.agent_context.system_message_suffix == "You are a skilled agent."


def test_agent_definition_to_factory_skills_only_no_prompt(tmp_path: Path) -> None:
    """有技能但没有系统的工厂提示词仍然创造AgentContext。"""
    skills_dir = tmp_path / ".agents" / "skills"
    skills_dir.mkdir(parents=True)
    _create_skill_file(skills_dir, "only-skill", "Only skill content.")

    agent_def = AgentDefinition(
        name="skills-only-agent",
        description="Agent with skills but no prompt",
        model="inherit",
        tools=[],
        skills=["only-skill"],
        system_prompt="",
    )

    factory = agent_definition_to_factory(agent_def, work_dir=tmp_path)
    llm = _make_test_llm()
    agent = factory(llm)

    assert agent.agent_context is not None
    assert len(agent.agent_context.skills) == 1
    assert agent.agent_context.skills[0].name == "only-skill"
    assert agent.agent_context.system_message_suffix is None


def test_agent_definition_to_factory_no_skills_no_prompt() -> None:
    """没有技能、没有提示词的工厂就不会创造AgentContext。"""
    agent_def = AgentDefinition(
        name="empty-agent",
        description="No skills no prompt",
        model="inherit",
        tools=[],
        skills=[],
        system_prompt="",
    )

    factory = agent_definition_to_factory(agent_def)
    llm = _make_test_llm()
    agent = factory(llm)

    assert agent.agent_context is None


def test_agent_definition_to_factory_skill_not_found() -> None:
    """当未找到技能名称时，工厂会引发 ValueError。"""
    agent_def = AgentDefinition(
        name="missing-skill-agent",
        description="Agent with missing skill",
        model="inherit",
        skills=["nonexistent-skill"],
    )

    with pytest.raises(ValueError, match="Skill 'nonexistent-skill' not found"):
        agent_definition_to_factory(agent_def)


def test_agent_definition_to_factory_skills_project_over_user(tmp_path: Path) -> None:
    """项目技能优先于同名的用户技能。"""
    # 创建项目级技能
    project_skills_dir = tmp_path / ".agents" / "skills"
    project_skills_dir.mkdir(parents=True)
    _create_skill_file(project_skills_dir, "shared-skill", "Project version.")

    # 创建同名的用户级技能
    user_home = tmp_path / "fake_home"
    user_skills_dir = user_home / ".agents" / "skills"
    user_skills_dir.mkdir(parents=True)
    _create_skill_file(user_skills_dir, "shared-skill", "User version.")

    agent_def = AgentDefinition(
        name="priority-agent",
        skills=["shared-skill"],
    )

    with patch("openhands.sdk.skills.skill.Path.home", return_value=user_home):
        factory = agent_definition_to_factory(agent_def, work_dir=tmp_path)

    llm = _make_test_llm()
    agent = factory(llm)

    assert agent.agent_context is not None
    assert len(agent.agent_context.skills) == 1
    # 项目版本应该获胜
    assert "Project version." in agent.agent_context.skills[0].content


def test_factory_info() -> None:
    """get_factory_info 返回已注册的智能体的格式化列表。"""
    info = get_factory_info()
    assert "No user-registered agents" in info

    # 注册一些智能体
    def factory_a(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    def factory_b(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    register_agent(name="alpha-agent", factory_func=factory_a, description="Alpha desc")
    register_agent(name="beta-agent", factory_func=factory_b, description="Beta desc")

    info = get_factory_info()
    assert "No user-registered agents" not in info
    assert "**alpha-agent**: Alpha desc" in info
    assert "**beta-agent**: Beta desc" in info
    # 验证字母顺序：alpha 在 beta 之前
    assert info.index("alpha-agent") < info.index("beta-agent")


def test_factory_info_mixed_tools_and_no_tools() -> None:
    """get_factory_info 正确显示仅适用于智能体拥有的工具。"""

    def dummy(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    agent_with = AgentDefinition(
        name="with-tools",
        description="Has tools",
        tools=["TerminalTool"],
    )
    agent_without = AgentDefinition(
        name="without-tools",
        description="No tools",
        tools=[],
    )
    register_agent(name="with-tools", factory_func=dummy, description=agent_with)
    register_agent(name="without-tools", factory_func=dummy, description=agent_without)

    info = get_factory_info()
    assert info == (
        "- **with-tools**: Has tools (tools: TerminalTool)\n"
        "- **without-tools**: No tools"
    )


def test_factory_info_single_agent() -> None:
    """get_factory_info 与单个已注册的智能体一起正常工作。"""

    def dummy(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    register_agent(name="solo-agent", factory_func=dummy, description="Only agent")

    info = get_factory_info()
    assert info == "- **solo-agent**: Only agent"


@pytest.mark.parametrize("name", [None, "", "default", "alpha"])
def test_error_default_factory_empty(name: str | None) -> None:
    """确保在未提供类型时使用默认的智能体工厂。"""
    with pytest.raises(ValueError, match=f"Unknown agent '{name}'"):
        _ = get_agent_factory(name)


def test_register_and_retrieve_custom_agent_factory() -> None:
    """用户注册的智能体工厂应该可以通过名称检索。"""

    def dummy_factory(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    register_agent(
        name="custom_agent",
        factory_func=dummy_factory,
        description="Custom agent for testing",
    )

    factory = get_agent_factory("custom_agent")
    assert factory.definition.description == "Custom agent for testing"
    assert factory.factory_func is dummy_factory


def test_unknown_agent_type_raises_value_error() -> None:
    """检索未知的智能体类型应该会提供有用的错误。"""
    with pytest.raises(ValueError) as excinfo:
        get_agent_factory("missing")

    assert "Unknown agent 'missing'" in str(excinfo.value)


def test_register_agent_if_absent_new() -> None:
    """register_agent_if_absent 为新的智能体返回 True。"""

    def dummy_factory(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    result = register_agent_if_absent(
        name="new_agent",
        factory_func=dummy_factory,
        description="New agent",
    )
    assert result is True

    factory = get_agent_factory("new_agent")
    assert factory.definition.description == "New agent"


def test_agent_definition_to_factory_model_profile(tmp_path: Path) -> None:
    """配置文件名称从配置文件存储中加载完整的 LLM。"""
    store = LLMProfileStore(base_dir=tmp_path)
    profile_llm = LLM(
        model="claude-sonnet-4-20250514",
        api_key=SecretStr("profile-key"),
        usage_id="profile-llm",
        temperature=0.3,
    )
    store.save("fast-gpt", profile_llm, include_secrets=True)

    agent_def = AgentDefinition(
        name="profile-agent",
        description="Uses a profile",
        model="fast-gpt",
        tools=[],
        system_prompt="Profile test.",
    )

    factory = agent_definition_to_factory(agent_def)
    parent_llm = _make_test_llm()
    with patch(
        "openhands.sdk.subagent.registry._get_profile_store", return_value=store
    ):
        agent = factory(parent_llm)

    # 智能体的 LLM 应该来自配置文件，而不是父级
    assert agent.llm is not parent_llm
    assert agent.llm.model == "claude-sonnet-4-20250514"
    assert agent.llm.temperature == 0.3
    assert agent.llm.stream is False
    # 指标必须独立于父级 LLM
    assert agent.llm.metrics is not parent_llm.metrics


def test_agent_definition_to_factory_model_profile_with_json_suffix(
    tmp_path: Path,
) -> None:
    """JSON后缀的用户名格式被接受，并正确加载。"""
    store = LLMProfileStore(base_dir=tmp_path)
    profile_llm = LLM(
        model="claude-sonnet-4-20250514",
        api_key=SecretStr("profile-key"),
        usage_id="profile-llm",
        temperature=0.3,
    )
    store.save("fast-gpt", profile_llm, include_secrets=True)

    agent_def = AgentDefinition(
        name="profile-agent",
        description="Uses a profile with .json suffix",
        model="fast-gpt.json",
        tools=[],
        system_prompt="Profile test.",
    )

    factory = agent_definition_to_factory(agent_def)
    parent_llm = _make_test_llm()
    with patch(
        "openhands.sdk.subagent.registry._get_profile_store", return_value=store
    ):
        agent = factory(parent_llm)

    assert agent.llm is not parent_llm
    assert agent.llm.model == "claude-sonnet-4-20250514"
    assert agent.llm.temperature == 0.3


def test_agent_definition_to_factory_model_profile_not_found(tmp_path: Path) -> None:
    """缺少个人资料加注 ValueError。"""
    store = LLMProfileStore(base_dir=tmp_path)

    agent_def = AgentDefinition(
        name="missing-profile-agent",
        description="Profile does not exist",
        model="nonexistent.json",
        tools=[],
        system_prompt="",
    )

    factory = agent_definition_to_factory(agent_def)
    parent_llm = _make_test_llm()

    with patch(
        "openhands.sdk.subagent.registry._get_profile_store", return_value=store
    ):
        with pytest.raises(ValueError, match="nonexistent"):
            factory(parent_llm)


def test_agent_definition_to_factory_model_profile_custom_store(tmp_path: Path) -> None:
    """补丁配置文件存储由工厂使用。"""
    custom_store = LLMProfileStore(base_dir=tmp_path)
    profile_llm = LLM(
        model="gpt-4o-mini",
        api_key=SecretStr("custom-store-key"),
        usage_id="custom-store-llm",
    )
    custom_store.save("my-profile", profile_llm, include_secrets=True)

    agent_def = AgentDefinition(
        name="custom-store-agent",
        description="Uses custom store",
        model="my-profile",
        tools=[],
        system_prompt="",
    )

    factory = agent_definition_to_factory(agent_def)
    parent_llm = _make_test_llm()
    with patch(
        "openhands.sdk.subagent.registry._get_profile_store", return_value=custom_store
    ):
        agent = factory(parent_llm)

    assert agent.llm.model == "gpt-4o-mini"
    assert agent.llm.stream is False
    # 指标必须独立于父级 LLM
    assert agent.llm.metrics is not parent_llm.metrics


def test_agent_definition_to_factory_profile_store_dir(tmp_path: Path) -> None:
    """AgentDefinition 上的profile_store_dir 由工厂使用。"""
    store = LLMProfileStore(base_dir=tmp_path)
    profile_llm = LLM(
        model="gpt-4o-mini",
        api_key=SecretStr("dir-key"),
        usage_id="dir-llm",
    )
    store.save("my-profile", profile_llm, include_secrets=True)
    agent_def = AgentDefinition(
        name="dir-agent",
        description="Uses profile_store_dir",
        model="my-profile",
        tools=[],
        system_prompt="",
        profile_store_dir=str(tmp_path),
    )

    factory = agent_definition_to_factory(agent_def)
    parent_llm = _make_test_llm()
    agent = factory(parent_llm)

    assert agent.llm.model == "gpt-4o-mini"


def test_agent_definition_to_factory_profile_store_dir_not_found(
    tmp_path: Path,
) -> None:
    """自定义 profile_store_dir 中缺少配置文件会引发 ValueError。"""
    agent_def = AgentDefinition(
        name="missing-dir-agent",
        model="nonexistent",
        tools=[],
        system_prompt="",
        profile_store_dir=str(tmp_path),
    )

    factory = agent_definition_to_factory(agent_def)
    parent_llm = _make_test_llm()

    with pytest.raises(ValueError, match="nonexistent"):
        factory(parent_llm)


def test_agent_definition_to_factory_profile_store_dir_none_uses_default(
    tmp_path: Path,
) -> None:
    """当profile_store_dir为None时，使用默认缓存存储。"""
    store = LLMProfileStore(base_dir=tmp_path)
    profile_llm = LLM(
        model="claude-sonnet-4-20250514",
        api_key=SecretStr("default-key"),
        usage_id="default-llm",
    )
    store.save("default-profile", profile_llm, include_secrets=True)

    agent_def = AgentDefinition(
        name="default-store-agent",
        model="default-profile",
        tools=[],
        system_prompt="",
        profile_store_dir=None,
    )

    factory = agent_definition_to_factory(agent_def)
    parent_llm = _make_test_llm()

    with patch(
        "openhands.sdk.subagent.registry._get_profile_store", return_value=store
    ):
        agent = factory(parent_llm)

    assert agent.llm.model == "claude-sonnet-4-20250514"


def test_register_agent_with_hook_config() -> None:
    """register_agent通过AgentDefinition将hook_config存储到AgentFactory中。"""
    hook_config = HookConfig(
        pre_tool_use=[
            HookMatcher(
                matcher="terminal",
                hooks=[HookDefinition(command="./validate.sh")],
            )
        ]
    )

    def dummy_factory(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    agent_def = AgentDefinition(
        name="hooked-agent",
        description="Agent with hooks",
        hooks=hook_config,
    )

    register_agent(
        name="hooked-agent",
        factory_func=dummy_factory,
        description=agent_def,
    )

    factory = get_agent_factory("hooked-agent")
    assert factory.definition.hooks is not None
    assert len(factory.definition.hooks.pre_tool_use) == 1
    assert factory.definition.hooks.pre_tool_use[0].matcher == "terminal"


def test_register_agent_hook_config_defaults_to_none() -> None:
    """如果未提供，AgentFactory.hook_config 默认为 None。"""

    def dummy_factory(llm: LLM) -> Agent:  # type: ignore[unused-argument]
        return cast(Agent, MagicMock())

    register_agent(
        name="no-hooks-agent",
        factory_func=dummy_factory,
        description="Agent without hooks",
    )

    factory = get_agent_factory("no-hooks-agent")
    assert factory.definition.hooks is None


def test_register_file_agents_with_hooks(tmp_path: Path) -> None:
    """带挂钩的基于文件的智能体在工厂中已存储 hook_config。"""
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "hooked.md").write_text(
        "---\n"
        "name: hooked-file-agent\n"
        "description: File agent with hooks\n"
        "hooks:\n"
        "  pre_tool_use:\n"
        "    - matcher: '*'\n"
        "      hooks:\n"
        "        - command: ./log.sh\n"
        "---\n\n"
        "You are an agent with hooks.\n"
    )

    with patch(
        "openhands.sdk.subagent.load.Path.home", return_value=tmp_path / "no_user"
    ):
        registered = register_file_agents(tmp_path)

    assert "hooked-file-agent" in registered
    factory = get_agent_factory("hooked-file-agent")
    assert factory.definition.hooks is not None
    assert len(factory.definition.hooks.pre_tool_use) == 1


def test_register_plugin_agents_with_hooks() -> None:
    """带钩子的插件智能体在工厂中已存储 hook_config。"""
    hook_config = HookConfig(
        stop=[
            HookMatcher(
                matcher="*",
                hooks=[HookDefinition(command="./check_stop.sh")],
            )
        ]
    )
    plugin_agent = AgentDefinition(
        name="plugin-hooked",
        description="Plugin agent with hooks",
        model="inherit",
        tools=[],
        system_prompt="Plugin prompt.",
        hooks=hook_config,
    )

    registered = register_plugin_agents([plugin_agent])
    assert "plugin-hooked" in registered

    factory = get_agent_factory("plugin-hooked")
    assert factory.definition.hooks is not None
    assert len(factory.definition.hooks.stop) == 1


def test_end_to_end_md_to_factory_to_registry(tmp_path: Path) -> None:
    """端到端：.md 文件 -> AgentDefinition.load() -> 工厂 -> 注册 -> 获取。"""
    md_file = tmp_path / "test-agent.md"
    md_file.write_text(
        "---\n"
        "name: e2e-test-agent\n"
        "description: End-to-end test agent\n"
        "model: inherit\n"
        "---\n\n"
        "You are a test agent for end-to-end testing.\n"
        "Focus on correctness and clarity.\n"
    )

    # 从文件加载
    agent_def = AgentDefinition.load(md_file)
    assert agent_def.name == "e2e-test-agent"
    assert agent_def.description == "End-to-end test agent"

    # 转为工厂
    factory = agent_definition_to_factory(agent_def)

    # 注册
    result = register_agent_if_absent(
        name=agent_def.name,
        factory_func=factory,
        description=agent_def.description,
    )
    assert result is True

    # 检索并验证
    retrieved = get_agent_factory("e2e-test-agent")
    assert retrieved.definition.description == "End-to-end test agent"

    # 从工厂创建智能体（使用真实的 LLM）
    test_llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )
    agent = retrieved.factory_func(test_llm)
    assert isinstance(agent, Agent)


def test_agent_definition_to_factory_mcp_config() -> None:
    """工厂将 mcp_config 传递到智能体。"""
    agent_def = AgentDefinition(
        name="mcp-agent",
        description="Agent with MCP servers",
        model="inherit",
        tools=[],
        system_prompt="",
        mcp_config={
            "fetch": MCPServer(command="uvx", args=["mcp-server-fetch"]),
        },
    )

    factory = agent_definition_to_factory(agent_def)
    llm = _make_test_llm()
    agent = factory(llm)

    assert dump_mcp_config(agent.mcp_config) == {
        "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}
    }


def test_agent_definition_to_factory_no_mcp_config() -> None:
    """没有 mcp_config 的工厂传递一个空的服务器映射。"""
    agent_def = AgentDefinition(
        name="no-mcp-agent",
        model="inherit",
        tools=[],
        system_prompt="",
    )

    factory = agent_definition_to_factory(agent_def)
    llm = _make_test_llm()
    agent = factory(llm)

    assert agent.mcp_config == {}


def test_register_file_agents_passes_mcp_config_to_agent(tmp_path: Path) -> None:
    """Integration: Markdown中的mcp_config流经注册表到智能体。"""
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "mcp-agent.md").write_text(
        "---\n"
        "name: mcp-agent\n"
        "description: Agent with MCP servers\n"
        "mcp_config:\n"
        "  fetch:\n"
        "    command: uvx\n"
        "    args: [mcp-server-fetch]\n"
        "---\n\n"
        "Agent with MCP.\n"
    )

    with patch(
        "openhands.sdk.subagent.load.Path.home", return_value=tmp_path / "no_user"
    ):
        registered = register_file_agents(tmp_path)

    assert "mcp-agent" in registered

    factory = get_agent_factory("mcp-agent")
    llm = _make_test_llm()
    agent = factory.factory_func(llm)

    assert dump_mcp_config(agent.mcp_config) == {
        "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}
    }


def test_factory_attaches_default_condenser() -> None:
    """子智能体默认得到一个总结上下文压缩器（与顶级
    智能体) 如此深度地运行自动压缩，而不是在上下文溢出时出错。"""
    factory = agent_definition_to_factory(AgentDefinition(name="gp"))
    agent = factory(_make_test_llm())
    assert isinstance(agent.condenser, LLMSummarizingCondenser)


def test_factory_condenser_uses_distinct_usage_id() -> None:
    """上下文压缩器 LLM 必须使用不同的 usage_id 或其 token 被重复数据删除
    对话统计信息（usage_id 上的先写胜出）。"""
    factory = agent_definition_to_factory(AgentDefinition(name="gp"))
    agent = factory(_make_test_llm())
    assert isinstance(agent.condenser, LLMSummarizingCondenser)
    assert agent.condenser.llm.usage_id == "condenser"
    assert agent.llm.usage_id != agent.condenser.llm.usage_id


def test_factory_noop_condenser_disables_condensation() -> None:
    factory = agent_definition_to_factory(
        AgentDefinition(name="x", condenser=NoOpCondenser())
    )
    assert isinstance(factory(_make_test_llm()).condenser, NoOpCondenser)


def test_factory_explicit_condenser_passthrough() -> None:
    custom = LLMSummarizingCondenser(
        llm=_make_test_llm().model_copy(update={"usage_id": "custom-condenser"}),
        max_size=40,
        keep_first=2,
    )
    factory = agent_definition_to_factory(AgentDefinition(name="x", condenser=custom))
    agent = factory(_make_test_llm())
    assert isinstance(agent.condenser, LLMSummarizingCondenser)
    assert agent.condenser.max_size == 40


def test_factory_explicit_condenser_fresh_per_spawn() -> None:
    """显式上下文压缩器会在每次生成时复制，因此子智能体不会共享一个
    指标对象（交叉污染/种族）和冲突 usage_id 已标准化，因此上下文压缩器 token 不会从
    统计数据中删除重复数据。
    """
    custom = LLMSummarizingCondenser(
        llm=_make_test_llm(),  # usage_id 与智能体相同 -> 必须标准化
        max_size=40,
        keep_first=2,
    )
    factory = agent_definition_to_factory(AgentDefinition(name="x", condenser=custom))
    a1 = factory(_make_test_llm())
    a2 = factory(_make_test_llm())

    c1, c2 = a1.condenser, a2.condenser
    assert isinstance(c1, LLMSummarizingCondenser)
    assert isinstance(c2, LLMSummarizingCondenser)
    # 每次生成时新鲜：不同的上下文压缩器、LLM 和 Metrics 对象。
    assert c1 is not c2
    assert c1.llm is not c2.llm
    assert c1.llm.metrics is not c2.llm.metrics
    # 碰撞 usage_id 标准化； 通过副本保存的配置。
    assert c1.llm.usage_id == "condenser"
    assert c1.llm.usage_id != a1.llm.usage_id
    assert c1.max_size == 40


def test_factory_explicit_condenser_preserves_distinct_usage_id() -> None:
    """已与智能体不同的上下文压缩器 usage_id 被保留。"""
    custom = LLMSummarizingCondenser(
        llm=_make_test_llm().model_copy(update={"usage_id": "my-condenser"}),
        max_size=40,
        keep_first=2,
    )
    factory = agent_definition_to_factory(AgentDefinition(name="x", condenser=custom))
    agent = factory(_make_test_llm())
    assert isinstance(agent.condenser, LLMSummarizingCondenser)
    assert agent.condenser.llm.usage_id == "my-condenser"
