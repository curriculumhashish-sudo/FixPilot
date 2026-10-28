"""测试资源目录支持（问题#1477）。"""

from pathlib import Path

from openhands.sdk.skills import (
    RESOURCE_DIRECTORIES,
    Skill,
    SkillResources,
    discover_skill_resources,
)
from openhands.sdk.utils.path import to_posix_path


def test_skill_resources_model(tmp_path: Path) -> None:
    """SkillResources 应跟踪资源并提供目录路径。"""
    # 空资源
    resources = SkillResources(skill_root="/path/to/skill")
    assert not resources.has_resources()

    # 拥有资源
    resources = SkillResources(skill_root="/path", scripts=["run.sh"])
    assert resources.has_resources()

    # 目录路径获取器
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "scripts").mkdir()
    resources = SkillResources(skill_root=str(skill_dir))
    assert resources.get_scripts_dir() == skill_dir / "scripts"
    assert resources.get_references_dir() is None  # 不存在


def test_discover_skill_resources(tmp_path: Path) -> None:
    """discover_skill_resources() 应该在资源目录中查找文件。"""
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()

    # 使用文件创建资源目录
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "run.sh").write_text("#!/bin/bash")
    subdir = scripts_dir / "utils"
    subdir.mkdir()
    (subdir / "helper.py").write_text("# helper")

    refs_dir = skill_dir / "references"
    refs_dir.mkdir()
    (refs_dir / "guide.md").write_text("# Guide")

    resources = discover_skill_resources(skill_dir)
    assert isinstance(resources, SkillResources)
    assert "run.sh" in resources.scripts
    assert "utils/helper.py" in resources.scripts  # 嵌套文件
    assert "guide.md" in resources.references
    assert resources.assets == []  # 没有资产目录
    assert resources.skill_root == to_posix_path(skill_dir.resolve())


def test_resource_directories_constant() -> None:
    """RESOURCE_DIRECTORIES 应包含标准目录名称。"""
    assert set(RESOURCE_DIRECTORIES) == {"scripts", "references", "assets"}


def test_skill_load_with_resources(tmp_path: Path) -> None:
    """Skill.load() 应该发现 SKILL.md 目录的资源。"""
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    my_skill_dir = skill_dir / "my-skill"
    my_skill_dir.mkdir()

    (my_skill_dir / "SKILL.md").write_text("# My Skill")
    scripts_dir = my_skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "run.sh").write_text("#!/bin/bash")

    # SKILL.md 目录格式 - 应该有资源（自动检测目录名称）
    skill = Skill.load(my_skill_dir / "SKILL.md", skill_dir)
    assert skill.resources is not None
    assert "run.sh" in skill.resources.scripts

    # 平面文件格式 - 不应包含资源
    flat_skill = skill_dir / "flat.md"
    flat_skill.write_text("# Flat Skill")
    skill = Skill.load(flat_skill, skill_dir)
    assert skill.resources is None
