"""测试 AgentSkills 中的 .mcp.json 支持（问题 #1476）。

测试的关键行为：
1. AgentSkills (SKILL.md) 加载 .mcp.json（如果存在）
2. AgentSkills 忽略 mcp_tools 前置元数据（仅使用 .mcp.json）
3. 旧技能从前置元数据加载 mcp_tools
4. 老技能加载失败。mcp.json
5. 变量扩展有效 (${VAR}, ${VAR:-default}, ${SKILL_ROOT})
"""

import json
from pathlib import Path

import pytest

from openhands.sdk.skills import (
    Skill,
    SkillValidationError,
    load_skills_from_dir,
)


def test_agentskills_loads_mcp_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AgentSkills (SKILL.md) 应使用变量扩展加载 .mcp.json。"""
    monkeypatch.delenv("PORT", raising=False)
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# My Skill")
    mcp_config = {
        "mcpServers": {
            "server": {
                "command": "${SKILL_ROOT}/run.py",
                "args": ["--port", "${PORT:-8080}"],
            }
        }
    }
    (skill_dir / ".mcp.json").write_text(json.dumps(mcp_config))

    skill = Skill.load(skill_dir / "SKILL.md")

    assert skill.mcp_tools is not None
    # ${SKILL_ROOT} 应扩展
    assert skill.mcp_tools["server"].command == f"{skill_dir}/run.py"
    # ${PORT:-8080} 应使用默认值
    assert skill.mcp_tools["server"].args == ["--port", "8080"]


def test_agentskills_ignores_frontmatter_mcp_tools(tmp_path: Path) -> None:
    """AgentSkills 应该仅使用 .mcp.json，忽略 mcp_tools 前置元数据。"""
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    # 前置元数据有 mcp_tools 但没有 .mcp.json 文件
    (skill_dir / "SKILL.md").write_text(
        "---\nmcp_tools:\n  server: {command: python}\n---\n# Skill"
    )

    skill = Skill.load(skill_dir / "SKILL.md")
    assert skill.mcp_tools is None


def test_legacy_skill_loads_frontmatter_mcp_tools(tmp_path: Path) -> None:
    """旧技能（.md 文件）应从前置元数据加载 mcp_tools。"""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "legacy.md").write_text(
        "---\nmcp_tools:\n  server: {command: python}\n---\n# Legacy"
    )

    skill = Skill.load(skills_dir / "legacy.md", skills_dir)

    assert skill.mcp_tools is not None
    assert "server" in skill.mcp_tools


def test_legacy_skill_ignores_mcp_json_in_directory(tmp_path: Path) -> None:
    """旧技能应该不加载 .mcp.json，即使存在于目录中。"""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "legacy.md").write_text("# Legacy Skill")
    (skills_dir / ".mcp.json").write_text(
        '{"mcpServers": {"server": {"command": "python", "args": []}}}'
    )

    skill = Skill.load(skills_dir / "legacy.md", skills_dir)
    assert skill.mcp_tools is None


def test_mcp_json_invalid_json_raises_error(tmp_path: Path) -> None:
    """.mcp.json 中的无效 JSON 应引发 SkillValidationError。"""
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Skill")
    (skill_dir / ".mcp.json").write_text("not valid json")

    with pytest.raises(SkillValidationError, match="Invalid JSON"):
        Skill.load(skill_dir / "SKILL.md")


def test_load_skills_from_dir_mcp_json_only_for_agentskills(tmp_path: Path) -> None:
    """load_skills_from_dir() 应该只加载 agent_skills 的 .mcp.json。"""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    # AgentSkill 与 .mcp.json
    agent_dir = skills_dir / "agent-skill"
    agent_dir.mkdir()
    (agent_dir / "SKILL.md").write_text("# Agent Skill")
    (agent_dir / ".mcp.json").write_text(
        '{"mcpServers": {"server": {"command": "python", "args": []}}}'
    )

    # 遗留技能
    (skills_dir / "legacy.md").write_text("# Legacy Skill")

    repo_skills, _, agent_skills = load_skills_from_dir(skills_dir)

    assert agent_skills["agent-skill"].mcp_tools is not None
    assert repo_skills["legacy"].mcp_tools is None
