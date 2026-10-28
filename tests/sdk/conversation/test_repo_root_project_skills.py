from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from openhands.sdk.agent import Agent
from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.event import SystemPromptEvent
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.skills import Skill, load_project_skills
from openhands.sdk.testing import TestLLM


def _agent(agent_context: AgentContext) -> Agent:
    return Agent(
        llm=TestLLM.from_messages(
            [Message(role="assistant", content=[TextContent(text="ok")])],
            model="test-model",
        ),
        tools=[],
        include_default_tools=[],
        agent_context=agent_context,
    )


def test_system_prompt_includes_repo_root_agents_md_when_workdir_is_subdir(
    tmp_path: Path,
):
    """从子目录启动时，仍应注入 Repo-root AGENTS.md。

    这是 CLI 手动测试的集成样式等效项：
    - work_dir 是子目录
    - git repo 根目录包含 AGENTS.md
    - AgentContext 由 load_project_skills(work_dir) 构建
    - LocalConversation 初始化发出 SystemPromptEvent

    我们断言存储库根 AGENTS.md 中的哨兵值出现在 SystemPromptEvent.dynamic_context 中
    。
    """

    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("# Project Guidelines\n\nSENTINEL_ROOT_123\n")

    subdir = tmp_path / "subdir"
    subdir.mkdir()

    skills = load_project_skills(subdir)
    ctx = AgentContext(
        skills=skills,
        # 跨环境保持确定性。
        current_datetime="2026-01-01T00:00:00Z",
    )

    agent = Agent(
        llm=TestLLM.from_messages(
            [
                Message(
                    role="assistant",
                    content=[TextContent(text="ok")],
                )
            ],
            model="test-model",
        ),
        tools=[],
        include_default_tools=[],
        agent_context=ctx,
    )

    conversation = LocalConversation(
        agent=agent,
        workspace=subdir,
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )
    conversation.send_message("hi")

    system_prompt_event = next(
        e for e in conversation.state.events if isinstance(e, SystemPromptEvent)
    )
    assert system_prompt_event.dynamic_context is not None
    assert "SENTINEL_ROOT_123" in system_prompt_event.dynamic_context.text

    conversation.close()


def test_load_project_skills_flag_injects_skills_in_standalone_sdk(tmp_path: Path):
    """``AgentContext(load_project_skills=True)`` 无需智能体服务器即可工作。

    LocalConversation 在启动时从工作区解析项目技能，因此该标志对于独立 SDK 使用具有一
    致的行为 (智能体-canvas#574)。
    """
    (tmp_path / "AGENTS.md").write_text("# Guidelines\n\nSENTINEL_FLAG_456\n")

    agent = _agent(
        AgentContext(
            load_project_skills=True,
            current_datetime="2026-01-01T00:00:00Z",
        )
    )
    conversation = LocalConversation(
        agent=agent,
        workspace=tmp_path,
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )
    conversation.send_message("hi")

    # 技能被合并到现场智能体上下文...
    assert conversation.agent.agent_context is not None
    assert "agents" in {s.name for s in conversation.agent.agent_context.skills}
    # ...and rendered into the system prompt.
    system_prompt_event = next(
        e for e in conversation.state.events if isinstance(e, SystemPromptEvent)
    )
    assert system_prompt_event.dynamic_context is not None
    assert "SENTINEL_FLAG_456" in system_prompt_event.dynamic_context.text

    conversation.close()


def test_load_project_skills_flag_off_does_not_inject(tmp_path: Path):
    """如果未设置该标志（默认），则不会加载项目技能。"""
    (tmp_path / "AGENTS.md").write_text("# Guidelines\n\nSENTINEL_OFF_789\n")

    agent = _agent(AgentContext(current_datetime="2026-01-01T00:00:00Z"))
    conversation = LocalConversation(
        agent=agent,
        workspace=tmp_path,
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )
    conversation.send_message("hi")

    assert conversation.agent.agent_context is not None
    assert conversation.agent.agent_context.skills == []
    system_prompt_event = next(
        e for e in conversation.state.events if isinstance(e, SystemPromptEvent)
    )
    dynamic = system_prompt_event.dynamic_context
    assert dynamic is None or "SENTINEL_OFF_789" not in dynamic.text

    conversation.close()


def test_load_project_skills_flag_merges_with_project_precedence(tmp_path: Path):
    """项目技能优先于同名上下文技能； 其他的则被保留。"""
    (tmp_path / "AGENTS.md").write_text("# Guidelines\n\nSENTINEL_NEW\n")

    agent = _agent(
        AgentContext(
            skills=[
                Skill(name="keep", content="keep me"),
                Skill(name="agents", content="OLD_CONTENT"),
            ],
            load_project_skills=True,
            current_datetime="2026-01-01T00:00:00Z",
        )
    )
    conversation = LocalConversation(
        agent=agent,
        workspace=tmp_path,
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )
    conversation.send_message("hi")

    assert conversation.agent.agent_context is not None
    skills = {s.name: s for s in conversation.agent.agent_context.skills}
    assert skills["keep"].content == "keep me"
    assert "SENTINEL_NEW" in skills["agents"].content
    assert "OLD_CONTENT" not in skills["agents"].content

    conversation.close()


def test_disabled_skills_drops_project_skill_at_lazy_merge(tmp_path: Path):
    """名称为 ``disabled_skills`` 的项目技能在
    惰性 ``LocalConversation`` 合并 — 绕过 ``model_copy`` 路径
    ``AgentContext`` 验证器。 不相关的禁用名称是无害的空操作。
    """
    # AGENTS.md 成为名为“智能体”的项目技能。
    (tmp_path / "AGENTS.md").write_text("# Guidelines\n\nSENTINEL\n")

    agent = _agent(
        AgentContext(
            skills=[Skill(name="keep", content="keep me")],
            load_project_skills=True,
            disabled_skills=["agents", "not-in-catalog"],
            current_datetime="2026-01-01T00:00:00Z",
        )
    )
    conversation = LocalConversation(
        agent=agent,
        workspace=tmp_path,
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )
    conversation.send_message("hi")

    assert conversation.agent.agent_context is not None
    names = {s.name for s in conversation.agent.agent_context.skills}
    # 延迟加载的项目技能“智能体”被禁用 -> 在合并时被删除。
    assert "agents" not in names
    # 非残障技能不受影响； 缺少的“不在目录中”是无操作。
    assert "keep" in names

    conversation.close()


def test_load_project_skills_failure_does_not_block_conversation(tmp_path: Path):
    """项目技能加载是尽力而为：加载错误不得中断启动。"""
    (tmp_path / "AGENTS.md").write_text("# Guidelines\n\nSENTINEL\n")

    agent = _agent(
        AgentContext(
            skills=[Skill(name="keep", content="keep me")],
            load_project_skills=True,
            current_datetime="2026-01-01T00:00:00Z",
        )
    )
    conversation = LocalConversation(
        agent=agent,
        workspace=tmp_path,
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )

    with patch(
        "openhands.sdk.conversation.impl.local_conversation.load_available_skills",
        side_effect=PermissionError("workspace unreadable"),
    ):
        conversation.send_message("hi")  # 不得提高

    # 谈话开始； 预先存在的技能保持不变。
    assert conversation.agent.agent_context is not None
    assert {s.name for s in conversation.agent.agent_context.skills} == {"keep"}

    conversation.close()
