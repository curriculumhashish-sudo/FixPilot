from pathlib import Path

import pytest

from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.skills import load_project_skills


_REPO_BASELINE_TEXT = (
    "---\n# type: repo\nversion: 1.0.0\nagent: CodeActAgent\n---\n\nRepo baseline\n"
)
_REPO_BASELINE_TEXT = (
    "---\n# type: repo\nversion: 1.0.0\nagent: CodeActAgent\n---\n\nRepo baseline\n"
)
# 用于测试的不同基线格式向后兼容性：
# - _REPO_BASELINE_TEXT: 旧格式，前置元数据（在 .openhands/skills/repo.md 中使用）
# - _AGENTS_BASELINE_TEXT：简单的Markdown格式（在AGENTS.md中使用）
_AGENTS_BASELINE_TEXT = "# Project Guidelines\n\nRepo baseline\n"


def _write_repo_with_vendor_files(root: Path, baseline_source: str) -> None:
    """使用基线和特定于供应商的技能文件创建测试存储库。

    Args:
        root: 测试存储库的根目录
        baseline_source: 要么 "repo_md"（遗留的 .openhands/skills/repo.md）
                        或“agents_md”（仓库根目录中的AGENTS.md）
    """
    if baseline_source == "repo_md":
        skills_dir = root / ".openhands" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        (skills_dir / "repo.md").write_text(_REPO_BASELINE_TEXT)
    elif baseline_source == "agents_md":
        (root / "AGENTS.md").write_text(_AGENTS_BASELINE_TEXT)
    else:
        raise ValueError(f"Unknown baseline_source: {baseline_source}")

    (root / "claude.md").write_text("Claude-Specific Instructions")
    (root / "gemini.md").write_text("Gemini-Specific Instructions")


# 测试向后兼容性的两种加载机制：
# - repo_md：遗留的。openhands/skills/repo.md（对于现有仓库仍然支持）
# - “agents_md”：在存储库根目录中使用 AGENTS.md 的新方法（推荐）
@pytest.mark.parametrize("baseline_source", ["repo_md", "agents_md"])
def test_context_gates_claude_vendor_file(tmp_path: Path, baseline_source: str):
    _write_repo_with_vendor_files(tmp_path, baseline_source)
    skills = load_project_skills(tmp_path)
    ac = AgentContext(skills=skills)
    suffix = ac.get_system_message_suffix(
        llm_model="litellm_proxy/anthropic/claude-sonnet-4"
    )
    assert suffix is not None
    assert "Repo baseline" in suffix
    assert "Claude-Specific Instructions" in suffix
    assert "Gemini-Specific Instructions" not in suffix


@pytest.mark.parametrize("baseline_source", ["repo_md", "agents_md"])
def test_context_gates_gemini_vendor_file(tmp_path: Path, baseline_source: str):
    _write_repo_with_vendor_files(tmp_path, baseline_source)
    skills = load_project_skills(tmp_path)
    ac = AgentContext(skills=skills)
    suffix = ac.get_system_message_suffix(llm_model="gemini-2.5-pro")
    assert suffix is not None
    assert "Repo baseline" in suffix
    assert "Gemini-Specific Instructions" in suffix
    assert "Claude-Specific Instructions" not in suffix


@pytest.mark.parametrize("baseline_source", ["repo_md", "agents_md"])
def test_context_excludes_both_for_other_models(tmp_path: Path, baseline_source: str):
    _write_repo_with_vendor_files(tmp_path, baseline_source)
    skills = load_project_skills(tmp_path)
    ac = AgentContext(skills=skills)
    suffix = ac.get_system_message_suffix(llm_model="openai/gpt-4o")
    assert suffix is not None
    assert "Repo baseline" in suffix
    assert "Claude-Specific Instructions" not in suffix
    assert "Gemini-Specific Instructions" not in suffix


@pytest.mark.parametrize("baseline_source", ["repo_md", "agents_md"])
def test_context_uses_canonical_name_for_vendor_match(
    tmp_path: Path, baseline_source: str
):
    _write_repo_with_vendor_files(tmp_path, baseline_source)
    skills = load_project_skills(tmp_path)
    ac = AgentContext(skills=skills)
    suffix = ac.get_system_message_suffix(
        llm_model="proxy/test-model",
        llm_model_canonical="anthropic/claude-sonnet-4",
    )
    assert suffix is not None
    assert "Repo baseline" in suffix
    assert "Claude-Specific Instructions" in suffix
    assert "Gemini-Specific Instructions" not in suffix


@pytest.mark.parametrize("baseline_source", ["repo_md", "agents_md"])
def test_context_includes_all_when_model_unknown(tmp_path: Path, baseline_source: str):
    _write_repo_with_vendor_files(tmp_path, baseline_source)
    skills = load_project_skills(tmp_path)
    ac = AgentContext(skills=skills)
    # 未提供模型信息 -> 向后兼容包含所有行为
    suffix = ac.get_system_message_suffix()
    assert suffix is not None
    assert "Repo baseline" in suffix
    assert "Claude-Specific Instructions" in suffix
    assert "Gemini-Specific Instructions" in suffix
