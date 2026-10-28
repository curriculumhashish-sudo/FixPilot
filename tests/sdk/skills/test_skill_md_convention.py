"""测试 SKILL.md 文件约定和名称验证（问题 #1475）。"""

from pathlib import Path

import pytest

from openhands.sdk.skills import (
    Skill,
    SkillValidationError,
    load_skills_from_dir,
)
from openhands.sdk.skills.utils import (
    find_skill_md,
    validate_skill_name,
)


def test_find_skill_md(tmp_path: Path) -> None:
    """find_skill_md() 应不区分大小写地定位 SKILL.md 文件。"""
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()

    # 未找到
    assert find_skill_md(skill_dir) is None

    # 找到了（不区分大小写）
    skill_md = skill_dir / "skill.MD"
    skill_md.write_text("# My Skill")
    assert find_skill_md(skill_dir) == skill_md


def test_validate_skill_name_valid() -> None:
    """validate_skill_name() 应接受有效的 AgentSkills 名称。"""
    assert validate_skill_name("my-skill") == []
    assert validate_skill_name("skill2") == []
    assert validate_skill_name("my-cool-skill") == []
    assert validate_skill_name("a") == []
    assert validate_skill_name("a" * 64) == []


def test_validate_skill_name_invalid_format() -> None:
    """validate_skill_name() 应拒绝无效的名称格式。"""
    # 大写 - 应包含格式错误
    errors = validate_skill_name("MySkill")
    assert any("lowercase" in e for e in errors)

    # 下划线 - 应包含格式错误
    errors = validate_skill_name("my_skill")
    assert any("lowercase" in e for e in errors)

    # 以连字符开头 - 应包含格式错误
    errors = validate_skill_name("-myskill")
    assert any("lowercase" in e for e in errors)

    # 连续的连字符 - 应包含格式错误
    errors = validate_skill_name("my--skill")
    assert any("lowercase" in e for e in errors)


def test_validate_skill_name_length() -> None:
    """validate_skill_name() 应该强制执行长度限制。"""
    # 太长 - 应包含长度错误
    errors = validate_skill_name("a" * 65)
    assert any("64 characters" in e for e in errors)

    # 空 - 应包含空错误
    errors = validate_skill_name("")
    assert any("empty" in e.lower() for e in errors)


def test_validate_skill_name_directory_mismatch() -> None:
    """validate_skill_name() 应该检测目录名称不匹配。"""
    errors = validate_skill_name("my-skill", directory_name="other-skill")
    assert any("does not match directory" in e for e in errors)


def test_skill_load_with_skill_md(tmp_path: Path) -> None:
    """Skill.load() 应使用 SKILL.md 格式的目录名称。"""
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    my_skill_dir = skill_dir / "pdf-tools"
    my_skill_dir.mkdir()
    (my_skill_dir / "SKILL.md").write_text("---\ntriggers:\n  - pdf\n---\n# PDF Tools")

    # 自动为 SKILL.md 个文件使用目录名称
    skill = Skill.load(my_skill_dir / "SKILL.md", skill_dir)
    assert skill.name == "pdf-tools"


def test_skill_load_auto_validates_skill_md(tmp_path: Path) -> None:
    """Skill.load() 应该自动验证 SKILL.md 目录名称。"""
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()

    # 无效的目录名称应自动引发验证错误
    bad_dir = skill_dir / "Bad_Name"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text("# Bad")
    with pytest.raises(SkillValidationError, match="Invalid skill name"):
        Skill.load(bad_dir / "SKILL.md", skill_dir)


def test_load_skills_from_dir_with_skill_md(tmp_path: Path) -> None:
    """load_skills_from_dir() 应该发现 SKILL.md 目录。"""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    # 平功
    (skills_dir / "flat-skill.md").write_text("---\ntriggers:\n  - flat\n---\n# Flat")

    # SKILL.md 目录
    dir_skill = skills_dir / "dir-skill"
    dir_skill.mkdir()
    (dir_skill / "SKILL.md").write_text("---\ntriggers:\n  - dir\n---\n# Dir")

    repo_skills, knowledge_skills, agent_skills = load_skills_from_dir(skills_dir)
    assert "flat-skill" in knowledge_skills
    assert "dir-skill" in agent_skills
    assert agent_skills["dir-skill"].name == "dir-skill"


def test_skill_md_always_agent_skill(tmp_path: Path) -> None:
    """SKILL.md 目录应始终为 agent_skills，即使没有触发器也是如此。

    AgentSkills 是与 OpenHands 技能不同的类别。 它们遵循 AgentSkills 标准，并且应与常
    规 .md 文件不同地处理。
    """
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    # 没有触发器的常规 .md 文件 -> repo_skills
    (skills_dir / "repo-style.md").write_text("# Repo Style\nNo triggers here.")

    # SKILL.md 没有触发器的目录 -> agent_skills
    no_trigger_skill = skills_dir / "no-trigger-skill"
    no_trigger_skill.mkdir()
    (no_trigger_skill / "SKILL.md").write_text("# No Trigger\nNo triggers here either.")

    repo_skills, knowledge_skills, agent_skills = load_skills_from_dir(skills_dir)

    # 没有触发器的常规 .md 会转到 repo_skills
    assert "repo-style" in repo_skills
    assert "repo-style" not in knowledge_skills
    assert "repo-style" not in agent_skills

    # SKILL.md 转到 agent_skills（单独类别）
    assert "no-trigger-skill" in agent_skills
    assert "no-trigger-skill" not in repo_skills
    assert "no-trigger-skill" not in knowledge_skills
