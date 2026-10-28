"""测试基于文件的智能体加载。"""

from pathlib import Path
from unittest.mock import patch

from openhands.sdk.subagent.load import (
    load_project_agents,
    load_user_agents,
)
from openhands.sdk.subagent.registry import (
    _reset_registry_for_tests,
)


def setup_function() -> None:
    _reset_registry_for_tests()


def teardown_function() -> None:
    _reset_registry_for_tests()


def test_load_project_agents(tmp_path: Path) -> None:
    """从 .agents/ 根目录加载 .md 文件。"""
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)

    (agents_dir / "code-reviewer.md").write_text(
        "---\n"
        "name: code-reviewer\n"
        "description: Reviews code\n"
        "tools:\n"
        "  - ReadTool\n"
        "---\n\n"
        "You are a code reviewer."
    )
    (agents_dir / "security-expert.md").write_text(
        "---\n"
        "name: security-expert\n"
        "description: Security analysis\n"
        "---\n\n"
        "You are a security expert."
    )

    agents = load_project_agents(tmp_path)
    names = {a.name for a in agents}
    assert names == {"code-reviewer", "security-expert"}

    # 验证代码审查器是否正确解析
    reviewer = next(a for a in agents if a.name == "code-reviewer")
    assert reviewer.description == "Reviews code"
    assert "ReadTool" in reviewer.tools
    assert reviewer.system_prompt == "You are a code reviewer."


def test_load_project_agents_skips_subdirs(tmp_path: Path) -> None:
    """不会递归到诸如 Skills/ 之类的子目录中。"""
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)

    # 顶级智能体
    (agents_dir / "top-agent.md").write_text(
        "---\nname: top-agent\ndescription: Top\n---\nPrompt."
    )

    # 子目录（应跳过）
    skills_dir = agents_dir / "skills"
    skills_dir.mkdir()
    (skills_dir / "nested-agent.md").write_text(
        "---\nname: nested-agent\ndescription: Nested\n---\nPrompt."
    )

    agents = load_project_agents(tmp_path)
    names = {a.name for a in agents}
    assert names == {"top-agent"}
    assert "nested-agent" not in names


def test_load_project_agents_empty(tmp_path: Path) -> None:
    """对于缺少的 .agents/ 目录，返回 []。"""
    agents = load_project_agents(tmp_path)
    assert agents == []


def test_load_project_agents_skips_readme(tmp_path: Path) -> None:
    """README.md 被跳过。"""
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)

    (agents_dir / "README.md").write_text("# Agents directory")
    (agents_dir / "readme.md").write_text("# Agents directory")
    (agents_dir / "real-agent.md").write_text(
        "---\nname: real-agent\ndescription: Real\n---\nPrompt."
    )

    agents = load_project_agents(tmp_path)
    names = [a.name for a in agents]
    assert names == ["real-agent"]


def test_load_project_agents_from_openhands_dir(tmp_path: Path) -> None:
    """当 .agents/ 不存在时，从 .openhands/ 加载 .md 文件。"""
    oh_dir = tmp_path / ".openhands" / "agents"
    oh_dir.mkdir(parents=True)

    (oh_dir / "legacy-agent.md").write_text(
        "---\nname: legacy-agent\ndescription: Legacy\n---\nLegacy prompt."
    )

    agents = load_project_agents(tmp_path)
    assert len(agents) == 1
    assert agents[0].name == "legacy-agent"


def test_load_project_agents_agents_dir_wins_over_openhands(tmp_path: Path) -> None:
    """对于重复名称，.agents/ 优先于 .openhands/。"""
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "shared.md").write_text(
        "---\nname: shared\ndescription: From .agents\n---\nAgents prompt."
    )

    oh_dir = tmp_path / ".openhands" / "agents"
    oh_dir.mkdir(parents=True)
    (oh_dir / "shared.md").write_text(
        "---\nname: shared\ndescription: From .openhands\n---\nOH prompt."
    )
    # 还要在 .openhands/ 中放置一个唯一的智能体以验证它是否仍然加载
    (oh_dir / "only-in-oh.md").write_text(
        "---\nname: only-in-oh\ndescription: OH only\n---\nOH only prompt."
    )

    agents = load_project_agents(tmp_path)
    names = [a.name for a in agents]
    assert sorted(names) == ["only-in-oh", "shared"]

    # .agents/ 版本应该赢得重复的 i.e。，第一个智能体应该来自 .智能体
    #
    assert agents[0].description == "From .agents"


def test_load_project_agents_merges_both_dirs(tmp_path: Path) -> None:
    """.agents/ 和 .openhands/ 中的智能体已合并。"""
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "agent-a.md").write_text(
        "---\nname: agent-a\ndescription: A\n---\nA."
    )

    oh_dir = tmp_path / ".openhands" / "agents"
    oh_dir.mkdir(parents=True)
    (oh_dir / "agent-b.md").write_text("---\nname: agent-b\ndescription: B\n---\nB.")

    agents = load_project_agents(tmp_path)
    names = [a.name for a in agents]
    assert sorted(names) == ["agent-a", "agent-b"]


def test_load_user_agents(tmp_path: Path) -> None:
    """从 ~/.agents/ 目录加载。"""
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)

    (agents_dir / "global-agent.md").write_text(
        "---\nname: global-agent\ndescription: Global\n---\nGlobal prompt."
    )

    with patch("openhands.sdk.subagent.load.Path.home", return_value=tmp_path):
        agents = load_user_agents()

    assert len(agents) == 1
    assert agents[0].name == "global-agent"


def test_load_user_agents_from_openhands_dir(tmp_path: Path) -> None:
    """当 ~/.agents/ 不存在时从 ~/.openhands/ 加载。"""
    oh_dir = tmp_path / ".openhands" / "agents"
    oh_dir.mkdir(parents=True)

    (oh_dir / "legacy-user.md").write_text(
        "---\nname: legacy-user\ndescription: Legacy user\n---\nLegacy."
    )

    with patch("openhands.sdk.subagent.load.Path.home", return_value=tmp_path):
        agents = load_user_agents()

    assert len(agents) == 1
    assert agents[0].name == "legacy-user"


def test_load_user_agents_agents_dir_wins_over_openhands(tmp_path: Path) -> None:
    """对于重复名称，~/.agents/ 优先于~/.openhands/。"""
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "shared.md").write_text(
        "---\nname: shared\ndescription: From .agents\n---\nAgents."
    )

    oh_dir = tmp_path / ".openhands" / "agents"
    oh_dir.mkdir(parents=True)
    (oh_dir / "shared.md").write_text(
        "---\nname: shared\ndescription: From .openhands\n---\nOH."
    )

    with patch("openhands.sdk.subagent.load.Path.home", return_value=tmp_path):
        agents = load_user_agents()

    assert len(agents) == 1
    assert agents[0].name == "shared"
    assert agents[0].description == "From .agents"
