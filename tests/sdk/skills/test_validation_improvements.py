"""测试技能验证改进。"""

from openhands.sdk.skills import Skill
from openhands.sdk.utils import DEFAULT_TRUNCATE_NOTICE


MAX_DESCRIPTION_LENGTH = 1024


def test_description_at_limit() -> None:
    """技能应接受 1024 个字符的描述。"""
    desc = "x" * MAX_DESCRIPTION_LENGTH
    skill = Skill(name="test", content="# Test", description=desc)
    assert skill.description is not None
    assert len(skill.description) == MAX_DESCRIPTION_LENGTH


def test_description_exceeds_limit_is_truncated() -> None:
    """技能应该截断超过 1024 个字符的描述而不是出错。"""
    desc = "x" * (MAX_DESCRIPTION_LENGTH + 100)
    skill = Skill(name="test", content="# Test", description=desc)
    assert skill.description is not None
    assert len(skill.description) == MAX_DESCRIPTION_LENGTH
    # 如果没有源，则回退到默认截断通知
    assert DEFAULT_TRUNCATE_NOTICE in skill.description


def test_description_truncation_includes_source_path() -> None:
    """设置来源后，截断通知应引用技能路径。"""
    desc = "x" * (MAX_DESCRIPTION_LENGTH + 500)
    source = "/path/to/my-skill/SKILL.md"
    skill = Skill(name="test", content="# Test", description=desc, source=source)
    assert skill.description is not None
    assert len(skill.description) == MAX_DESCRIPTION_LENGTH
    assert source in skill.description
