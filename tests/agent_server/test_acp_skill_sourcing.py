"""ACP 技能来源：谁提供 ACP 智能体的技能 (#4019)。

ACP CLI 从会话 cwd 中读取 ``AGENTS.md`` / ``CLAUDE.md`` 及其自己的项目技能，因此
OpenHands 永远不会注入这些内容。 是
否注入其
*Managed* 目录是每个部署的选择 (``Config.acp_skill_sourcing``)：
主机本地 CLI 可以达到用户自己的配置，而容器中的主机则不能。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from openhands.agent_server.config import ACPSkillSourcing, Config
from openhands.sdk import LLM, Agent, Conversation
from openhands.sdk.agent import ACPAgent, AgentBase
from openhands.sdk.context import AgentContext
from openhands.sdk.conversation.request import AgentLaunchAdditions
from openhands.sdk.launch import LaunchRuntime, finalize
from openhands.sdk.marketplace.registration import MarketplaceRegistration
from openhands.sdk.settings.model import validate_agent_settings
from openhands.sdk.skills import Skill


AGENTS_MD_BODY = "sentinel-agents-md-body"
MANAGED_SKILL = "managed-catalog-skill"


def _managed_skill() -> Skill:
    return Skill(
        name=MANAGED_SKILL,
        content="managed content",
        description="from the server catalog",
        source="public",
        is_agentskills_format=True,
    )


def _acp_agent(acp_server: str = "claude-code", **context_kwargs) -> ACPAgent:
    settings = validate_agent_settings(
        {
            "agent_kind": "acp",
            "acp_server": acp_server,
            "agent_context": AgentContext(**context_kwargs).model_dump(),
        }
    )
    agent = settings.create_agent()
    assert isinstance(agent, ACPAgent)
    return agent


def _workspace(root: Path) -> Path:
    project = root / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text(f"# Repo\n\n{AGENTS_MD_BODY}\n")
    skill_dir = project / ".agents" / "skills" / "project-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: project-skill\ndescription: local\n---\n\nbody\n"
    )
    return project


def _apply_acp_skill_sourcing(
    agent: AgentBase, sourcing: ACPSkillSourcing
) -> AgentBase:
    return finalize(agent, LaunchRuntime(acp_skill_sourcing=sourcing)).agent


def _installed_suffix(agent: AgentBase, project: Path) -> str:
    """后缀 ``init_state`` 渲染到 ACP 子进程的提示词中。

    仅子进程生成被存根； 渲染是生产渲染。
    """
    with patch.object(ACPAgent, "_start_acp_server", lambda self, state: None):
        conversation = Conversation(agent=agent, workspace=str(project))
        conversation._ensure_agent_ready()
        agent_after_load = conversation.agent
        assert isinstance(agent_after_load, ACPAgent)
        return agent_after_load._installed_suffix or ""


def test_config_defaults_to_native_sourcing() -> None:
    assert Config().acp_skill_sourcing == "native"


def test_acp_agent_clears_load_project_skills() -> None:
    agent = _acp_agent(load_project_skills=True)
    assert agent.agent_context is not None
    assert agent.agent_context.load_project_skills is False


def test_openhands_agent_keeps_load_project_skills() -> None:
    """守卫仅是ACP——常规智能体仍然加载项目技能。"""
    agent = Agent(
        llm=LLM(model="gpt-4o", usage_id="agent"),
        tools=[],
        agent_context=AgentContext(load_project_skills=True),
    )
    assert agent.agent_context is not None
    assert agent.agent_context.load_project_skills is True


@pytest.mark.parametrize("sourcing", ["native", "openhands_managed"])
def test_repo_context_never_reaches_the_acp_prompt(
    tmp_path: Path, sourcing: ACPSkillSourcing
) -> None:
    project = _workspace(tmp_path)
    agent = _apply_acp_skill_sourcing(
        _acp_agent(skills=[_managed_skill()], load_project_skills=True), sourcing
    )
    suffix = _installed_suffix(agent, project)
    assert AGENTS_MD_BODY not in suffix
    assert "project-skill" not in suffix


def test_native_sourcing_strips_managed_skills(tmp_path: Path) -> None:
    project = _workspace(tmp_path)
    agent = _apply_acp_skill_sourcing(
        _acp_agent(skills=[_managed_skill()], load_project_skills=True), "native"
    )
    assert agent.agent_context is not None
    assert agent.agent_context.skills == []
    assert MANAGED_SKILL not in _installed_suffix(agent, project)


def test_managed_sourcing_keeps_managed_skills(tmp_path: Path) -> None:
    project = _workspace(tmp_path)
    agent = _apply_acp_skill_sourcing(
        _acp_agent(skills=[_managed_skill()], load_project_skills=True),
        "openhands_managed",
    )
    assert agent.agent_context is not None
    assert [s.name for s in agent.agent_context.skills] == [MANAGED_SKILL]
    assert MANAGED_SKILL in _installed_suffix(agent, project)


def test_native_sourcing_clears_lazy_skill_sources() -> None:
    """旗帜和市场注册稍后会解决技能问题，所以一条条
    只有清空``skills``才能让他们回来。"""
    agent = _apply_acp_skill_sourcing(
        _acp_agent(
            load_user_skills=True,
            load_public_skills=True,
            registered_marketplaces=[
                MarketplaceRegistration(
                    name="mkt", source="https://example.invalid/mkt.git"
                )
            ],
        ),
        "native",
    )
    context = agent.agent_context
    assert context is not None
    assert context.load_user_skills is False
    assert context.load_public_skills is False
    assert context.registered_marketplaces == []


def test_native_sourcing_leaves_a_non_acp_agent_alone() -> None:
    agent = Agent(
        llm=LLM(model="gpt-4o", usage_id="agent"),
        tools=[],
        agent_context=AgentContext(skills=[_managed_skill()]),
    )
    sourced = _apply_acp_skill_sourcing(agent, "native")
    assert sourced.agent_context is not None
    assert [s.name for s in sourced.agent_context.skills] == [MANAGED_SKILL]


def test_native_sourcing_is_a_no_op_without_skills() -> None:
    agent = _acp_agent(current_datetime=None)
    assert _apply_acp_skill_sourcing(agent, "native") is agent


@pytest.mark.parametrize("sourcing", ["native", "openhands_managed"])
def test_launch_supplied_skills_reach_the_acp_agent(
    tmp_path: Path, sourcing: ACPSkillSourcing
) -> None:
    project = _workspace(tmp_path)
    launch_skill = Skill(name="launch-skill", content="launch content")
    agent = finalize(
        _acp_agent(skills=[_managed_skill()]),
        LaunchRuntime(acp_skill_sourcing=sourcing),
        additions=AgentLaunchAdditions(skills=[launch_skill]),
    ).agent
    assert agent.agent_context is not None
    names = {s.name for s in agent.agent_context.skills}
    assert "launch-skill" in names
    assert (MANAGED_SKILL in names) == (sourcing == "openhands_managed")
    assert "launch-skill" in _installed_suffix(agent, project)


def _skills_dir(project: Path) -> Path:
    return project / ".openhands" / "acp" / "skills"


@pytest.mark.parametrize("acp_server", ["claude-code", "codex", "gemini-cli"])
def test_acp_skills_are_listed_by_path_for_every_provider(
    tmp_path: Path, acp_server: str
) -> None:
    project = _workspace(tmp_path)
    agent = _acp_agent(
        acp_server,
        skills=[
            Skill(
                name="launch-skill",
                description="does the launch thing",
                content="launch body",
                is_agentskills_format=True,
            )
        ],
    )
    suffix = _installed_suffix(agent, project)

    skill_md = _skills_dir(project) / "launch-skill" / "SKILL.md"
    assert "launch body" in skill_md.read_text()
    assert f"<location>{skill_md}</location>" in suffix
    assert "does the launch thing" in suffix
    assert "launch body" not in suffix
    assert "invoke_skill" not in suffix


def test_skill_names_cannot_escape_the_skills_directory(tmp_path: Path) -> None:
    project = _workspace(tmp_path)
    agent = _acp_agent(
        skills=[Skill(name="../evil", content="x", is_agentskills_format=True)]
    )
    _installed_suffix(agent, project)

    written = [p for p in project.rglob("SKILL.md") if "evil" in str(p)]
    assert written
    assert all(_skills_dir(project) in p.parents for p in written)


def test_skills_hidden_from_the_model_are_not_written_or_listed(tmp_path: Path) -> None:
    project = _workspace(tmp_path)
    agent = _acp_agent(
        skills=[
            Skill(name="shown", content="s", is_agentskills_format=True),
            Skill(
                name="hidden",
                content="h",
                is_agentskills_format=True,
                disable_model_invocation=True,
            ),
        ]
    )
    suffix = _installed_suffix(agent, project)

    assert (_skills_dir(project) / "shown" / "SKILL.md").exists()
    assert not (_skills_dir(project) / "hidden").exists()
    assert "<name>hidden</name>" not in suffix


def test_skill_names_differing_only_by_case_get_separate_directories(
    tmp_path: Path,
) -> None:
    project = _workspace(tmp_path)
    agent = _acp_agent(
        skills=[
            Skill(name="Zebra", content="upper", is_agentskills_format=True),
            Skill(name="zebra", content="lower", is_agentskills_format=True),
        ]
    )
    _installed_suffix(agent, project)

    bodies = [p.read_text() for p in _skills_dir(project).rglob("SKILL.md")]
    assert len(bodies) == 2
    assert any("upper" in body for body in bodies)
    assert any("lower" in body for body in bodies)
