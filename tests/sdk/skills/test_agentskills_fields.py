"""测试技能模型中的 AgentSkills 标准字段。"""

import pytest
from pydantic import ValidationError

from openhands.sdk.skills import Skill, SkillValidationError


def test_skill_with_agentskills_fields(tmp_path) -> None:
    """技能应支持 AgentSkills 标准字段。"""
    skill_content = """---
name: pdf-processing
description: Extract text from PDF files.
license: Apache-2.0
compatibility: Requires poppler-utils
metadata:
  author: example-org
  version: "1.0"
allowed-tools: Bash(pdftotext:*) Read Write
disable-model-invocation: true
triggers:
  - pdf
---
# PDF Processing
"""
    path = tmp_path / "pdf.md"
    path.write_text(skill_content)
    skill = Skill.load(path)

    assert skill.name == "pdf-processing"
    assert skill.description == "Extract text from PDF files."
    assert skill.license == "Apache-2.0"
    assert skill.compatibility == "Requires poppler-utils"
    assert skill.metadata == {"author": "example-org", "version": "1.0"}
    assert skill.allowed_tools == ["Bash(pdftotext:*)", "Read", "Write"]
    assert skill.disable_model_invocation is True
    assert skill.match_trigger("process pdf") == "pdf"


def test_skill_allowed_tools_formats(tmp_path) -> None:
    """allowed-tools 应接受字符串或列表格式。"""
    # 字符串格式
    path = tmp_path / "s1.md"
    path.write_text("---\nname: s\nallowed-tools: A B\n---\n#")
    skill = Skill.load(path)
    assert skill.allowed_tools == ["A", "B"]

    # 列表格式
    path = tmp_path / "s2.md"
    path.write_text("---\nname: s\nallowed-tools:\n  - A\n  - B\n---\n#")
    skill = Skill.load(path)
    assert skill.allowed_tools == ["A", "B"]

    # 下划线变体
    path = tmp_path / "s3.md"
    path.write_text("---\nname: s\nallowed_tools: A B\n---\n#")
    skill = Skill.load(path)
    assert skill.allowed_tools == ["A", "B"]


def test_skill_invalid_field_types(tmp_path) -> None:
    """技能应通过 Pydantic 验证拒绝无效字段类型。"""
    # 无效描述 - Pydantic 验证字符串类型
    path = tmp_path / "invalid_desc.md"
    path.write_text("---\nname: s\ndescription:\n  - list\n---\n#")
    with pytest.raises(ValidationError, match="description"):
        Skill.load(path)

    # 元数据无效 - 自定义验证器引发 SkillValidationError
    path = tmp_path / "invalid_meta.md"
    path.write_text("---\nname: s\nmetadata: string\n---\n#")
    with pytest.raises(SkillValidationError, match="metadata must be a dictionary"):
        Skill.load(path)

    # 允许的工具无效 - 自定义验证器引发 SkillValidationError
    path = tmp_path / "invalid_tools.md"
    path.write_text("---\nname: s\nallowed-tools: 123\n---\n#")
    with pytest.raises(SkillValidationError, match="allowed-tools must be"):
        Skill.load(path)


def test_skill_backward_compatibility(tmp_path) -> None:
    """没有 AgentSkills 字段的技能应该仍然有效。"""
    path = tmp_path / "s.md"
    path.write_text("---\nname: legacy\ntriggers:\n  - test\n---\n#")
    skill = Skill.load(path)
    assert skill.name == "legacy"
    assert skill.description is None
    assert skill.license is None
    assert skill.disable_model_invocation is False
    assert skill.match_trigger("test") == "test"
