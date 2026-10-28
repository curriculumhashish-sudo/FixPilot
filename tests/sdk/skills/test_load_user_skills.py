"""测试 load_user_skills 功能。"""

import tempfile
from pathlib import Path

import pytest

from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.skills import (
    KeywordTrigger,
    Skill,
    installed,
    load_user_skills,
    skill,
)
from openhands.sdk.skills.installed import disable_skill, install_skill


@pytest.fixture
def temp_user_skills_dir():
    """创建临时用户技能目录结构。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        # 创建 .agents/skills 目录
        agents_dir = root / ".agents" / "skills"
        agents_dir.mkdir(parents=True)

        # 创建openhands/skills目录
        skills_dir = root / ".openhands" / "skills"
        skills_dir.mkdir(parents=True)

        yield root, agents_dir, skills_dir


@pytest.fixture
def temp_microagents_dir():
    """创建临时微代理目录结构。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        # 创建openhands/microagents目录
        microagents_dir = root / ".openhands" / "microagents"
        microagents_dir.mkdir(parents=True)

        yield root, microagents_dir


def test_load_user_skills_no_directories(tmp_path):
    """当不存在用户技能目录时测试 load_user_skills。"""
    # 将USER_SKILLS_DIRS指向不存在的目录
    from openhands.sdk.skills import skill

    original_dirs = skill.USER_SKILLS_DIRS
    try:
        skill.USER_SKILLS_DIRS = [
            tmp_path / "nonexistent1",
            tmp_path / "nonexistent2",
        ]
        skills = load_user_skills()
        assert skills == []
    finally:
        skill.USER_SKILLS_DIRS = original_dirs


def test_load_user_skills_with_agents_directory(temp_user_skills_dir):
    """测试 load_user_skills 从 .agents/skills 目录加载。"""
    root, agents_dir, _ = temp_user_skills_dir

    # 创建测试技能文件
    skill_file = agents_dir / "agent_skill.md"
    skill_file.write_text(
        "---\nname: agent_skill\ntriggers:\n  - agent\n---\nAgent skill content."
    )

    from openhands.sdk.skills import skill

    original_dirs = skill.USER_SKILLS_DIRS
    try:
        skill.USER_SKILLS_DIRS = [agents_dir]
        skills = load_user_skills()
        assert len(skills) == 1
        assert skills[0].name == "agent_skill"
        assert skills[0].content == "Agent skill content."
        assert isinstance(skills[0].trigger, KeywordTrigger)
    finally:
        skill.USER_SKILLS_DIRS = original_dirs


def test_load_user_skills_with_skills_directory(temp_user_skills_dir):
    """load_user_skills 测试从 openhands/skills 目录加载。"""
    root, _, skills_dir = temp_user_skills_dir

    # 创建测试技能文件
    skill_file = skills_dir / "test_skill.md"
    skill_file.write_text(
        "---\nname: test_skill\ntriggers:\n  - test\n---\nThis is a test skill."
    )

    from openhands.sdk.skills import skill

    original_dirs = skill.USER_SKILLS_DIRS
    try:
        skill.USER_SKILLS_DIRS = [skills_dir]
        skills = load_user_skills()
        assert len(skills) == 1
        assert skills[0].name == "test_skill"
        assert skills[0].content == "This is a test skill."
        assert isinstance(skills[0].trigger, KeywordTrigger)
    finally:
        skill.USER_SKILLS_DIRS = original_dirs


def test_load_user_skills_with_microagents_directory(temp_microagents_dir):
    """测试 load_user_skills 从 microagents 目录（旧版）加载。"""
    root, microagents_dir = temp_microagents_dir

    # 创建测试微代理文件
    microagent_file = microagents_dir / "legacy_skill.md"
    microagent_file.write_text(
        "---\n"
        "name: legacy_skill\n"
        "triggers:\n"
        "  - legacy\n"
        "---\n"
        "This is a legacy microagent skill."
    )

    from openhands.sdk.skills import skill

    original_dirs = skill.USER_SKILLS_DIRS
    try:
        skill.USER_SKILLS_DIRS = [microagents_dir]
        skills = load_user_skills()
        assert len(skills) == 1
        assert skills[0].name == "legacy_skill"
        assert skills[0].content == "This is a legacy microagent skill."
    finally:
        skill.USER_SKILLS_DIRS = original_dirs


def test_load_user_skills_priority_order(tmp_path):
    """测试优先级。agents/skills > openhands/skills > microagents。"""
    agents_dir = tmp_path / ".agents" / "skills"
    skills_dir = tmp_path / ".openhands" / "skills"
    microagents_dir = tmp_path / ".openhands" / "microagents"
    agents_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    microagents_dir.mkdir(parents=True)

    (agents_dir / "duplicate.md").write_text(
        "---\nname: duplicate\n---\nFrom .agents/skills."
    )
    (skills_dir / "duplicate.md").write_text(
        "---\nname: duplicate\n---\nFrom .openhands/skills."
    )
    (microagents_dir / "duplicate.md").write_text(
        "---\nname: duplicate\n---\nFrom .openhands/microagents."
    )

    from openhands.sdk.skills import skill

    original_dirs = skill.USER_SKILLS_DIRS
    try:
        skill.USER_SKILLS_DIRS = [agents_dir, skills_dir, microagents_dir]
        skills = load_user_skills()
        assert len(skills) == 1
        assert skills[0].name == "duplicate"
        assert skills[0].content == "From .agents/skills."
    finally:
        skill.USER_SKILLS_DIRS = original_dirs


def test_load_user_skills_merges_all_directories(tmp_path):
    """测试加载来自 .agents/skills 和 .openhands/skills 的唯一技能
    微代理。
    """
    agents_dir = tmp_path / ".agents" / "skills"
    skills_dir = tmp_path / ".openhands" / "skills"
    microagents_dir = tmp_path / ".openhands" / "microagents"
    agents_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    microagents_dir.mkdir(parents=True)

    (agents_dir / "agent_skill.md").write_text(
        "---\nname: agent_skill\n---\nAgent skill content."
    )
    (skills_dir / "skill1.md").write_text("---\nname: skill1\n---\nSkill 1 content.")
    (microagents_dir / "skill2.md").write_text(
        "---\nname: skill2\n---\nSkill 2 content."
    )

    from openhands.sdk.skills import skill

    original_dirs = skill.USER_SKILLS_DIRS
    try:
        skill.USER_SKILLS_DIRS = [agents_dir, skills_dir, microagents_dir]
        skills = load_user_skills()
        assert len(skills) == 3
        skill_names = {s.name for s in skills}
        assert skill_names == {"agent_skill", "skill1", "skill2"}
    finally:
        skill.USER_SKILLS_DIRS = original_dirs


def test_load_user_skills_handles_errors_gracefully(temp_user_skills_dir):
    """测试加载错误是否得到妥善处理。"""
    root, _, skills_dir = temp_user_skills_dir

    # 创建无效的技能文件
    invalid_file = skills_dir / "invalid.md"
    invalid_file.write_text(
        "---\n"
        "triggers: not_a_list\n"  # 无效：触发器必须是列表
        "---\n"
        "Invalid skill."
    )

    from openhands.sdk.skills import skill

    original_dirs = skill.USER_SKILLS_DIRS
    try:
        skill.USER_SKILLS_DIRS = [skills_dir]
        # 不应引发异常，仅返回空列表
        skills = load_user_skills()
        assert skills == []
    finally:
        skill.USER_SKILLS_DIRS = original_dirs


def test_agent_context_loads_user_skills_by_default(temp_user_skills_dir):
    """测试 AgentContext 启用后是否加载用户技能。"""
    root, _, skills_dir = temp_user_skills_dir

    # 创建测试技能
    skill_file = skills_dir / "auto_skill.md"
    skill_file.write_text("---\nname: auto_skill\n---\nAutomatically loaded skill.")

    from openhands.sdk.skills import skill

    original_dirs = skill.USER_SKILLS_DIRS
    try:
        skill.USER_SKILLS_DIRS = [skills_dir]
        context = AgentContext(load_user_skills=True)
        skill_names = [s.name for s in context.skills]
        assert "auto_skill" in skill_names
    finally:
        skill.USER_SKILLS_DIRS = original_dirs


def test_agent_context_can_disable_user_skills_loading():
    """测试是否可以禁用用户技能加载。"""
    context = AgentContext(load_user_skills=False)
    assert context.skills == []


def test_agent_context_merges_explicit_and_user_skills(temp_user_skills_dir):
    """测试显性技能和用户技能是否正确合并。"""
    root, _, skills_dir = temp_user_skills_dir

    # 创造用户技能
    user_skill_file = skills_dir / "user_skill.md"
    user_skill_file.write_text("---\nname: user_skill\n---\nUser skill content.")

    # 创造显性技能
    explicit_skill = Skill(
        name="explicit_skill",
        content="Explicit skill content.",
        trigger=None,
    )

    from openhands.sdk.skills import skill

    original_dirs = skill.USER_SKILLS_DIRS
    try:
        skill.USER_SKILLS_DIRS = [skills_dir]
        context = AgentContext(skills=[explicit_skill], load_user_skills=True)
        skill_names = [s.name for s in context.skills]
        assert "explicit_skill" in skill_names
        assert "user_skill" in skill_names
        assert len(context.skills) == 2
    finally:
        skill.USER_SKILLS_DIRS = original_dirs


def test_agent_context_explicit_skill_takes_precedence(temp_user_skills_dir):
    """测试明确提供的技能是否优先于用户技能。"""
    root, _, skills_dir = temp_user_skills_dir

    # 创建同名用户技能
    user_skill_file = skills_dir / "duplicate.md"
    user_skill_file.write_text("---\nname: duplicate\n---\nUser skill content.")

    # 创建同名的显式技能
    explicit_skill = Skill(
        name="duplicate",
        content="Explicit skill content.",
        trigger=None,
    )

    from openhands.sdk.skills import skill

    original_dirs = skill.USER_SKILLS_DIRS
    try:
        skill.USER_SKILLS_DIRS = [skills_dir]
        context = AgentContext(skills=[explicit_skill], load_user_skills=True)
        assert len(context.skills) == 1
        # 应使用显性技能，而不是用户技能
        assert context.skills[0].content == "Explicit skill content."
    finally:
        skill.USER_SKILLS_DIRS = original_dirs


def test_load_user_skills_includes_installed_skills(tmp_path, monkeypatch):
    """测试 load_user_skills 是否也加载已启用的已安装技能。"""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    installed_dir = tmp_path / "skills" / "installed"
    installed_dir.mkdir()

    # 创建并安装技能
    source_dir = tmp_path / "my-installed-skill"
    source_dir.mkdir()
    (source_dir / "SKILL.md").write_text(
        "---\nname: my-installed-skill\ndescription: Installed skill\n---\n"
        "Installed skill content."
    )
    install_skill(str(source_dir), installed_dir=installed_dir)

    original_dirs = skill.USER_SKILLS_DIRS
    try:
        skill.USER_SKILLS_DIRS = [skills_dir]
        monkeypatch.setattr(installed, "DEFAULT_INSTALLED_SKILLS_DIR", installed_dir)
        skills = load_user_skills()
        skill_names = {s.name for s in skills}
        assert "my-installed-skill" in skill_names
    finally:
        skill.USER_SKILLS_DIRS = original_dirs


def test_load_user_skills_user_skill_takes_precedence_over_installed(
    tmp_path, monkeypatch
):
    """测试用户技能是否优先于已安装的技能。"""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    installed_dir = tmp_path / "skills" / "installed"
    installed_dir.mkdir()

    # 创建用户技能
    (skills_dir / "duplicate.md").write_text("---\nname: duplicate\n---\nUser version.")

    # 安装同名技能
    source_dir = tmp_path / "duplicate"
    source_dir.mkdir()
    (source_dir / "SKILL.md").write_text(
        "---\nname: duplicate\ndescription: dup\n---\nInstalled version."
    )
    install_skill(str(source_dir), installed_dir=installed_dir)

    original_dirs = skill.USER_SKILLS_DIRS
    try:
        skill.USER_SKILLS_DIRS = [skills_dir]
        monkeypatch.setattr(installed, "DEFAULT_INSTALLED_SKILLS_DIR", installed_dir)
        skills = load_user_skills()
        dupes = [s for s in skills if s.name == "duplicate"]
        assert len(dupes) == 1
        assert dupes[0].content == "User version."
    finally:
        skill.USER_SKILLS_DIRS = original_dirs


def test_load_user_skills_disabled_installed_skill_excluded(tmp_path, monkeypatch):
    """测试已禁用的已安装技能是否未加载。"""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    installed_dir = tmp_path / "skills" / "installed"
    installed_dir.mkdir()

    # 安装和禁用技能
    source_dir = tmp_path / "disabled-skill"
    source_dir.mkdir()
    (source_dir / "SKILL.md").write_text(
        "---\nname: disabled-skill\ndescription: test\n---\nContent."
    )
    install_skill(str(source_dir), installed_dir=installed_dir)
    disable_skill("disabled-skill", installed_dir=installed_dir)

    original_dirs = skill.USER_SKILLS_DIRS
    try:
        skill.USER_SKILLS_DIRS = [skills_dir]
        monkeypatch.setattr(installed, "DEFAULT_INSTALLED_SKILLS_DIR", installed_dir)
        skills = load_user_skills()
        skill_names = {s.name for s in skills}
        assert "disabled-skill" not in skill_names
    finally:
        skill.USER_SKILLS_DIRS = original_dirs


@pytest.mark.parametrize("enabled", [True, False])
def test_installed_skill_resources_do_not_leak_into_user_skills(
    tmp_path, monkeypatch, enabled
):
    skills_dir = tmp_path / "skills"
    installed_dir = skills_dir / "installed"
    source = tmp_path / "resource-skill"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: resource-skill\ndescription: Resource skill\n---\nInstructions."
    )
    for directory in ("commands", "references"):
        (source / directory).mkdir()
        (source / directory / "notes.md").write_text("Private resource instructions.")
    install_skill(str(source), installed_dir=installed_dir)
    if not enabled:
        disable_skill("resource-skill", installed_dir=installed_dir)

    (skills_dir / "legacy").mkdir()
    (skills_dir / "legacy" / "notes.md").write_text("Legacy instructions.")
    direct = skills_dir / "direct-skill"
    direct.mkdir()
    (direct / "SKILL.md").write_text(
        "---\nname: direct-skill\ndescription: Direct skill\n---\nInstructions."
    )
    (direct / "reference.md").write_text("Direct resource instructions.")
    monkeypatch.setattr(skill, "USER_SKILLS_DIRS", [skills_dir])
    monkeypatch.setattr(installed, "DEFAULT_INSTALLED_SKILLS_DIR", installed_dir)

    loaded = load_user_skills()
    expected = {"legacy/notes", "direct-skill"}
    if enabled:
        expected.add("resource-skill")
    assert {entry.name for entry in loaded} == expected
    assert len(loaded) == len(expected)
    assert (installed_dir / "resource-skill" / "references" / "notes.md").is_file()


def test_user_skills_survive_symlink_loop_next_to_installed_dir(tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "good.md").write_text("Good instructions.")
    (skills_dir / "a.md").symlink_to(skills_dir / "b.md")
    (skills_dir / "b.md").symlink_to(skills_dir / "a.md")
    monkeypatch.setattr(skill, "USER_SKILLS_DIRS", [skills_dir])
    monkeypatch.setattr(
        installed, "DEFAULT_INSTALLED_SKILLS_DIR", skills_dir / "installed"
    )

    assert [entry.name for entry in load_user_skills()] == ["good"]


def test_installed_dir_excluded_through_symlinked_user_skills_dir(
    tmp_path, monkeypatch
):
    skills_dir = tmp_path / "openhands" / "skills"
    installed_dir = skills_dir / "installed"
    (installed_dir / "pkg" / "references").mkdir(parents=True)
    (installed_dir / "pkg" / "references" / "notes.md").write_text("Package notes.")
    agents_skills_dir = tmp_path / "agents" / "skills"
    agents_skills_dir.parent.mkdir()
    agents_skills_dir.symlink_to(skills_dir, target_is_directory=True)
    monkeypatch.setattr(skill, "USER_SKILLS_DIRS", [agents_skills_dir, skills_dir])
    monkeypatch.setattr(installed, "DEFAULT_INSTALLED_SKILLS_DIR", installed_dir)

    assert load_user_skills() == []


def test_load_skills_from_dir_keeps_installed_dir_without_exclusion(tmp_path):
    skills_dir = tmp_path / "skills"
    (skills_dir / "installed" / "pkg" / "references").mkdir(parents=True)
    (skills_dir / "installed" / "pkg" / "references" / "notes.md").write_text(
        "Package notes."
    )

    repo_skills, _, _ = skill.load_skills_from_dir(skills_dir)

    assert "installed/pkg/references/notes" in repo_skills
