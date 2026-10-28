"""测试提示词生成实用程序（问题 #1478）。"""

from openhands.sdk.skills import (
    Skill,
    to_prompt,
)


def test_to_prompt_generates_xml() -> None:
    """to_prompt() 应该为 AgentSkills 格式的技能生成有效的 XML。"""
    # 空列表显示“没有可用技能”
    assert (
        to_prompt([])
        == "<available_skills>\n  no available skills\n</available_skills>"
    )

    # 单一技能及描述
    skill = Skill(name="pdf-tools", content="# PDF", description="Process PDFs.")
    result = to_prompt([skill])
    assert "<skill>" in result
    assert "<name>pdf-tools</name>" in result
    assert "<description>Process PDFs.</description>" in result
    assert "<available_skills>" in result

    # 多种技能
    skills = [
        Skill(name="pdf-tools", content="# PDF", description="Process PDFs."),
        Skill(name="code-review", content="# Code", description="Review code."),
    ]
    result = to_prompt(skills)
    assert result.count("<skill>") == 2


def test_to_prompt_never_emits_location() -> None:
    """to_prompt() 不得发出 <location>：invoke_skill 是唯一的条目
    点和智能体不得指定文件路径。"""
    skill = Skill(
        name="pdf-tools",
        content="# PDF",
        description="Process PDFs.",
        source="/path/to/skill.md",
    )
    result = to_prompt([skill])
    assert "<location>" not in result
    assert "/path/to/skill.md" not in result


def test_to_prompt_escapes_xml() -> None:
    """to_prompt() 应该转义 XML 个特殊字符。"""
    skill = Skill(
        name="test", content="# Test", description='Handle <tags> & "quotes".'
    )
    result = to_prompt([skill])
    assert "&lt;tags&gt;" in result
    assert "&amp;" in result
    # XML 元素内容中的引号不需要转义（仅在属性中）
    assert '"quotes"' in result


def test_to_prompt_uses_content_fallback() -> None:
    """to_prompt() 在没有描述时应使用内容。"""
    skill = Skill(name="test", content="# Header\n\nActual content here.")
    result = to_prompt([skill])
    assert "Actual content here." in result
    assert "# Header" not in result


def test_to_prompt_content_fallback_counts_remaining_as_truncated() -> None:
    """to_prompt() 应该将第一行之后的内容计为被截断。"""
    # 包含标题、描述行和附加内容的内容
    content = "# Header\n\nFirst line used as description.\n\nMore content here."
    skill = Skill(name="test", content=content, source="/skills/test.md")
    result = to_prompt([skill])

    # 应使用第一个非标题行作为描述
    assert "First line used as description." in result
    # 应指示剩余内容的截断并将智能体指向 invoke_skill（不是文件路径）作为加载完整内容的
    # 方式。
    #
    assert "characters truncated" in result
    assert 'invoke_skill(name="test")' in result
    assert "/skills/test.md" not in result


def test_to_prompt_truncates_long_descriptions() -> None:
    """to_prompt() 应使用指示符截断长描述。"""
    skill = Skill(name="test", content="# Test", description="short")
    skill.description = "A" * 1034
    result = to_prompt([skill])

    # 应包含指向 invoke_skill 的截断指示符
    assert "... [10 characters truncated" in result
    assert 'invoke_skill(name="test")' in result
    # 应包含前 1024 个字符
    assert "A" * 1024 in result


def test_to_prompt_truncation_points_at_invoke_skill_not_source() -> None:
    """截断消息必须将智能体指向 invoke_skill，而不是
    技能的来源路径。"""
    skill = Skill(
        name="test",
        content="# Test",
        description="short",
        source="/path/to/skill.md",
    )
    skill.description = "B" * 1034
    result = to_prompt([skill])

    assert "... [10 characters truncated" in result
    assert 'invoke_skill(name="test")' in result
    assert "/path/to/skill.md" not in result
