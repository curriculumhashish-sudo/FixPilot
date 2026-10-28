"""测试 load_project_skills 功能。"""

from openhands.sdk.skills import (
    KeywordTrigger,
    load_project_skills,
)


def test_load_project_skills_no_directories(tmp_path):
    """当不存在项目技能目录时测试 load_project_skills。"""
    skills = load_project_skills(tmp_path)
    assert skills == []


def test_load_project_skills_agents_md_without_skills_directory(tmp_path):
    """测试 AGENTS.md 即使 openhands/skills 不存在也能加载。

    这是一个回归测试第三方技能文件，如 AGENTS.md 当时，它们没有被加载。
    openhands/skills 目录不存在。
    """
    # 在工作目录中创建 AGENTS.md（不要加 .openhands/skills）
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Project Guidelines\n\nThis is the AGENTS.md content.")

    skills = load_project_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == "agents"
    assert "Project Guidelines" in skills[0].content
    assert skills[0].trigger is None  # 第三方技能始终活跃


def test_load_project_skills_agents_md_case_insensitive(tmp_path):
    """测试 AGENTS.md 是否加载了不区分大小写的匹配。"""
    # 在工作目录中创建agents.md（小写）
    agents_md = tmp_path / "agents.md"
    agents_md.write_text("# Lowercase agents.md content")

    skills = load_project_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == "agents"


def test_load_project_skills_multiple_third_party_files(tmp_path):
    """测试加载多个第三方技能文件。"""
    # 创建AGENTS.md
    (tmp_path / "AGENTS.md").write_text("# AGENTS.md content")

    # 创建.cursorrules
    (tmp_path / ".cursorrules").write_text("# Cursor rules content")

    skills = load_project_skills(tmp_path)
    assert len(skills) == 2
    skill_names = {s.name for s in skills}
    assert "agents" in skill_names
    assert "cursorrules" in skill_names


def test_load_project_skills_third_party_with_skills_directory(tmp_path):
    """第三方文件的测试文件与技能一起加载。openhands/skills."""
    # 在工作目录中创建AGENTS.md
    (tmp_path / "AGENTS.md").write_text("# AGENTS.md content")

    # 创建。openhands/skills 包含技能的目录
    skills_dir = tmp_path / ".openhands" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "test_skill.md").write_text(
        "---\nname: test_skill\ntriggers:\n  - test\n---\nTest skill content."
    )

    skills = load_project_skills(tmp_path)
    assert len(skills) == 2
    skill_names = {s.name for s in skills}
    assert "agents" in skill_names
    assert "test_skill" in skill_names


def test_load_project_skills_with_skills_directory(tmp_path):
    """load_project_skills 测试从 openhands/skills 目录加载。"""
    # 创建openhands/skills目录
    skills_dir = tmp_path / ".openhands" / "skills"
    skills_dir.mkdir(parents=True)

    # 创建测试技能文件
    skill_file = skills_dir / "test_skill.md"
    skill_file.write_text(
        "---\nname: test_skill\ntriggers:\n  - test\n---\nThis is a test skill."
    )

    skills = load_project_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == "test_skill"
    assert skills[0].content == "This is a test skill."
    assert isinstance(skills[0].trigger, KeywordTrigger)


def test_load_project_skills_with_agents_directory(tmp_path):
    """测试 load_project_skills 从 .agents/skills 目录加载。"""
    # 创建 .agents/skills 目录
    skills_dir = tmp_path / ".agents" / "skills"
    skills_dir.mkdir(parents=True)

    # 创建测试技能文件
    skill_file = skills_dir / "agent_skill.md"
    skill_file.write_text(
        "---\nname: agent_skill\ntriggers:\n  - agent\n---\nAgent skill content."
    )

    skills = load_project_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == "agent_skill"
    assert skills[0].content == "Agent skill content."
    assert isinstance(skills[0].trigger, KeywordTrigger)


def test_load_project_skills_agents_directory_precedence(tmp_path):
    """Test .agents/skills 优先于其他目录。"""
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

    skills = load_project_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == "duplicate"
    assert skills[0].content == "From .agents/skills."


def test_load_project_skills_merges_agents_and_openhands(tmp_path):
    """加载来自 .agents/skills 和 .openhands/skills. 的唯一技能"""
    agents_dir = tmp_path / ".agents" / "skills"
    openhands_dir = tmp_path / ".openhands" / "skills"
    agents_dir.mkdir(parents=True)
    openhands_dir.mkdir(parents=True)

    (agents_dir / "agent_skill.md").write_text(
        "---\nname: agent_skill\n---\nAgent skill content."
    )
    (openhands_dir / "legacy_skill.md").write_text(
        "---\nname: legacy_skill\n---\nLegacy skill content."
    )

    skills = load_project_skills(tmp_path)
    assert len(skills) == 2
    skill_names = {skill.name for skill in skills}
    assert skill_names == {"agent_skill", "legacy_skill"}


def test_load_project_skills_with_microagents_directory(tmp_path):
    """load_project_skills 测试从 .openhands/microagents 目录加载（遗留）。"""
    # 创建openhands/microagents目录
    microagents_dir = tmp_path / ".openhands" / "microagents"
    microagents_dir.mkdir(parents=True)

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

    skills = load_project_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == "legacy_skill"
    assert skills[0].content == "This is a legacy microagent skill."


def test_load_project_skills_priority_order(tmp_path):
    """测试 Skills/ 目录优先于 microagents/。"""
    # 创建两个目录
    skills_dir = tmp_path / ".openhands" / "skills"
    microagents_dir = tmp_path / ".openhands" / "microagents"
    skills_dir.mkdir(parents=True)
    microagents_dir.mkdir(parents=True)

    # 在两个目录中创建重复的技能
    (skills_dir / "duplicate.md").write_text(
        "---\nname: duplicate\n---\nFrom skills directory."
    )

    (microagents_dir / "duplicate.md").write_text(
        "---\nname: duplicate\n---\nFrom microagents directory."
    )

    skills = load_project_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == "duplicate"
    # 应来自技能目录（优先）
    assert skills[0].content == "From skills directory."


def test_load_project_skills_both_directories(tmp_path):
    """测试从两个目录加载独特技能。"""
    # 创建两个目录
    skills_dir = tmp_path / ".openhands" / "skills"
    microagents_dir = tmp_path / ".openhands" / "microagents"
    skills_dir.mkdir(parents=True)
    microagents_dir.mkdir(parents=True)

    # 在每个目录下创建不同的技能
    (skills_dir / "skill1.md").write_text("---\nname: skill1\n---\nSkill 1 content.")
    (microagents_dir / "skill2.md").write_text(
        "---\nname: skill2\n---\nSkill 2 content."
    )

    skills = load_project_skills(tmp_path)
    assert len(skills) == 2
    skill_names = {s.name for s in skills}
    assert skill_names == {"skill1", "skill2"}


def test_load_project_skills_handles_errors_gracefully(tmp_path):
    """测试加载错误是否得到妥善处理。"""
    # 创建openhands/skills目录
    skills_dir = tmp_path / ".openhands" / "skills"
    skills_dir.mkdir(parents=True)

    # 创建无效的技能文件
    invalid_file = skills_dir / "invalid.md"
    invalid_file.write_text(
        "---\n"
        "triggers: not_a_list\n"  # 无效：触发器必须是列表
        "---\n"
        "Invalid skill."
    )

    # 不应引发异常，仅返回空列表
    skills = load_project_skills(tmp_path)
    assert skills == []


def test_load_project_skills_one_bad_skill_does_not_break_others(tmp_path):
    """测试一项无效技能不会阻止其他有效技能的加载。

    这是针对错误的回归测试，其中单个技能验证错误将导致目录中的全部技能加载失败。
    """
    # 创建openhands/skills目录
    skills_dir = tmp_path / ".openhands" / "skills"
    skills_dir.mkdir(parents=True)

    # 创建有效技能
    valid_skill = skills_dir / "valid-skill.md"
    valid_skill.write_text(
        "---\nname: valid-skill\ntriggers:\n  - valid\n---\nThis is a valid skill."
    )

    # 创建无效技能（名称与文件名不匹配）
    invalid_skill_dir = skills_dir / "bad-skill"
    invalid_skill_dir.mkdir()
    (invalid_skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: wrong_name\n"  # 名称有下划线，与目录不匹配
        "---\n"
        "This skill has a mismatched name."
    )

    # 创建另一个有效技能
    another_valid = skills_dir / "another-valid.md"
    another_valid.write_text(
        "---\nname: another-valid\ntriggers:\n  - another\n---\nAnother valid skill."
    )

    # 尽管技能无效，但仍应加载有效技能
    skills = load_project_skills(tmp_path)

    # 两个有效技能都应该加载
    skill_names = {s.name for s in skills}
    assert "valid-skill" in skill_names
    assert "another-valid" in skill_names
    # 应加载无效技能不
    assert "wrong_name" not in skill_names
    assert "bad-skill" not in skill_names


def test_long_description_skill_does_not_break_other_skills(tmp_path):
    """回归测试：不应有很长描述的技能
    阻止加载同一目录中的其他有效技能。

    描述应该被静默地截断（通过 maybe_truncate）而不是引发错误。
    """
    skills_dir = tmp_path / ".agents" / "skills"
    skills_dir.mkdir(parents=True)

    # 创建有效技能
    (skills_dir / "good-skill.md").write_text(
        "---\nname: good-skill\ntriggers:\n  - good\n---\nGood skill content."
    )

    # 创建描述超过 1024 个字符的技能
    long_desc = "A" * 2000
    bad_skill_dir = skills_dir / "bad-skill"
    bad_skill_dir.mkdir()
    (bad_skill_dir / "SKILL.md").write_text(
        f"---\nname: bad-skill\ndescription: {long_desc}\n---\n"
        "# Bad Skill\nContent here."
    )

    skills = load_project_skills(tmp_path)
    skill_names = {s.name for s in skills}

    # 好技能无论如何都要加载
    assert "good-skill" in skill_names

    # 糟糕的技能也应该加载（描述被截断，而不是拒绝）
    assert "bad-skill" in skill_names
    bad = next(s for s in skills if s.name == "bad-skill")
    assert bad.description is not None
    assert len(bad.description) <= 1024


def test_load_project_skills_with_string_path(tmp_path):
    """测试 load_project_skills 是否接受字符串路径。"""
    # 创建openhands/skills目录
    skills_dir = tmp_path / ".openhands" / "skills"
    skills_dir.mkdir(parents=True)

    # 创建测试技能文件
    skill_file = skills_dir / "test_skill.md"
    skill_file.write_text("---\nname: test_skill\n---\nTest skill content.")

    # 将路径作为字符串传递
    skills = load_project_skills(str(tmp_path))
    assert len(skills) == 1
    assert skills[0].name == "test_skill"


def test_load_project_skills_loads_from_git_root_when_called_from_subdir(tmp_path):
    """从子目录运行仍应加载存储库级别的技能（git root）。"""
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("# Project Guidelines\n\nFrom root")

    subdir = tmp_path / "subdir"
    subdir.mkdir()

    skills = load_project_skills(subdir)
    assert any(s.name == "agents" and "From root" in s.content for s in skills)


def test_load_project_skills_workdir_takes_precedence_over_git_root(tmp_path):
    """更多本地（工作目录）技能应该覆盖回购根技能。"""
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("# Project Guidelines\n\nFrom root")

    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "AGENTS.md").write_text("# Project Guidelines\n\nFrom subdir")

    skills = load_project_skills(subdir)
    agents = [s for s in skills if s.name == "agents"]
    assert len(agents) == 1
    assert agents[0].content.strip() == "# Project Guidelines\n\nFrom subdir"


def test_load_project_skills_loads_skills_directories_from_git_root(tmp_path):
    """技能目录（.agents/skills 等）应从 git root 加载。"""
    (tmp_path / ".git").mkdir()

    skills_dir = tmp_path / ".agents" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "root_skill.md").write_text(
        "---\nname: root_skill\ntriggers:\n  - root\n---\nLoaded from root"
    )

    subdir = tmp_path / "subdir"
    subdir.mkdir()

    skills = load_project_skills(subdir)
    assert any(
        s.name == "root_skill" and "Loaded from root" in s.content for s in skills
    )
