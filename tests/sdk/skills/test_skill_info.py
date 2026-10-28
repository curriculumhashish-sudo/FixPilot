"""测试 Skill.to_skill_info() 和相关方法。"""

from typing import Literal, get_args

from openhands.sdk.skills import (
    KeywordTrigger,
    Skill,
    TaskTrigger,
)
from openhands.sdk.skills.skill import SkillInfo


SkillType = Literal["repo", "knowledge", "agentskills"]


class TestSkillGetSkillType:
    """测试 Skill.get_skill_type() 方法。"""

    def test_repo_skill_type(self):
        """测试触发器 = None 的技能是否返回“repo”类型。"""
        skill = Skill(
            name="test-repo",
            content="Repository instructions",
            trigger=None,
        )
        assert skill.get_skill_type() == "repo"

    def test_knowledge_skill_type_with_keyword_trigger(self):
        """测试带有 KeywordTrigger 的技能是否返回“知识”类型。"""
        skill = Skill(
            name="test-knowledge",
            content="Knowledge instructions",
            trigger=KeywordTrigger(keywords=["python", "testing"]),
        )
        assert skill.get_skill_type() == "knowledge"

    def test_knowledge_skill_type_with_task_trigger(self):
        """测试带有 TaskTrigger 的技能是否返回“知识”类型。"""
        skill = Skill(
            name="test-task",
            content="Task instructions",
            trigger=TaskTrigger(triggers=["task"]),
        )
        assert skill.get_skill_type() == "knowledge"

    def test_agent_skill_type(self):
        """测试 AgentSkills 格式技能是否返回“agentskills”类型。"""
        skill = Skill(
            name="test-agent",
            content="Agent instructions",
            trigger=None,
            is_agentskills_format=True,
        )
        assert skill.get_skill_type() == "agentskills"

    def test_agent_skill_type_with_trigger(self):
        """测试 AgentSkills 格式是否优先于触发类型。"""
        skill = Skill(
            name="test-agent",
            content="Agent instructions",
            trigger=KeywordTrigger(keywords=["test"]),
            is_agentskills_format=True,
        )
        # AgentSkills 格式应返回“agentskills”，即使有触发器
        assert skill.get_skill_type() == "agentskills"


class TestSkillGetTriggers:
    """测试 Skill.get_triggers() 方法。"""

    def test_no_triggers(self):
        """测试触发器=None 的技能是否返回空列表。"""
        skill = Skill(
            name="test-repo",
            content="Repository instructions",
            trigger=None,
        )
        assert skill.get_triggers() == []

    def test_keyword_triggers(self):
        """测试 KeywordTrigger 返回其关键字。"""
        skill = Skill(
            name="test-knowledge",
            content="Knowledge instructions",
            trigger=KeywordTrigger(keywords=["python", "testing", "pytest"]),
        )
        assert skill.get_triggers() == ["python", "testing", "pytest"]

    def test_task_triggers(self):
        """测试 TaskTrigger 返回其触发器。"""
        skill = Skill(
            name="test-task",
            content="Task instructions",
            trigger=TaskTrigger(triggers=["/deploy", "/build"]),
        )
        assert skill.get_triggers() == ["/deploy", "/build"]

    def test_empty_keyword_triggers(self):
        """使用空关键字列表测试 KeywordTrigger。"""
        skill = Skill(
            name="test-empty",
            content="Instructions",
            trigger=KeywordTrigger(keywords=[]),
        )
        assert skill.get_triggers() == []


class TestSkillToSkillInfo:
    """测试 Skill.to_skill_info() 方法。"""

    def test_repo_skill_to_info(self):
        """测试 repo 技能到 SkillInfo 的转换。"""
        skill = Skill(
            name="test-repo",
            content="Repository instructions",
            source="/path/to/skill.md",
            description="A test repository skill",
            trigger=None,
        )
        info = skill.to_skill_info()

        assert isinstance(info, SkillInfo)
        assert info.name == "test-repo"
        assert info.type == "repo"
        assert info.content == "Repository instructions"
        assert info.triggers == []
        assert info.source == "/path/to/skill.md"
        assert info.description == "A test repository skill"
        assert info.is_agentskills_format is False

    def test_knowledge_skill_to_info(self):
        """测试知识技能到SkillInfo的转换。"""
        skill = Skill(
            name="test-knowledge",
            content="Knowledge instructions",
            source="/path/to/knowledge.md",
            trigger=KeywordTrigger(keywords=["python", "coding"]),
        )
        info = skill.to_skill_info()

        assert isinstance(info, SkillInfo)
        assert info.name == "test-knowledge"
        assert info.type == "knowledge"
        assert info.content == "Knowledge instructions"
        assert info.triggers == ["python", "coding"]
        assert info.source == "/path/to/knowledge.md"
        assert info.description is None
        assert info.is_agentskills_format is False

    def test_agent_skill_to_info(self):
        """测试AgentSkills格式技能到SkillInfo的转换。"""
        skill = Skill(
            name="pdf-tools",
            content="PDF processing instructions",
            source="/skills/pdf-tools/SKILL.md",
            description="Tools for working with PDF files",
            trigger=None,
            is_agentskills_format=True,
        )
        info = skill.to_skill_info()

        assert isinstance(info, SkillInfo)
        assert info.name == "pdf-tools"
        assert info.type == "agentskills"
        assert info.content == "PDF processing instructions"
        assert info.triggers == []
        assert info.source == "/skills/pdf-tools/SKILL.md"
        assert info.description == "Tools for working with PDF files"
        assert info.is_agentskills_format is True
        assert info.disable_model_invocation is False

    def test_agent_skill_to_info_preserves_disable_model_invocation(self):
        """AgentSkills 直接调用元数据应该保留下来序列化。"""
        skill = Skill(
            name="trigger-only",
            content="Trigger-only instructions",
            source="/skills/trigger-only/SKILL.md",
            description="Trigger-only skill",
            trigger=KeywordTrigger(keywords=["trigger-only"]),
            is_agentskills_format=True,
            disable_model_invocation=True,
        )
        info = skill.to_skill_info()

        assert info.disable_model_invocation is True

    def test_task_skill_to_info(self):
        """测试任务技能到SkillInfo的转换。"""
        skill = Skill(
            name="deploy-task",
            content="Deployment instructions with ${env}",
            source="/tasks/deploy.md",
            trigger=TaskTrigger(triggers=["/deploy"]),
        )
        info = skill.to_skill_info()

        assert isinstance(info, SkillInfo)
        assert info.name == "deploy-task"
        assert info.type == "knowledge"
        # TaskTrigger 在内容中附加有关变量的指导
        assert "Deployment instructions with ${env}" in info.content
        assert info.triggers == ["/deploy"]
        assert info.source == "/tasks/deploy.md"

    def test_skill_info_with_none_values(self):
        """测试 SkillInfo 正确处理 None 值。"""
        skill = Skill(
            name="minimal",
            content="Minimal content",
            trigger=None,
        )
        info = skill.to_skill_info()

        assert info.name == "minimal"
        assert info.type == "repo"
        assert info.content == "Minimal content"
        assert info.triggers == []
        assert info.source is None
        assert info.description is None
        assert info.is_agentskills_format is False


class TestSkillInfoDataclass:
    """测试 SkillInfo 数据类本身。"""

    def test_skill_info_creation(self):
        """测试直接创建SkillInfo。"""
        info = SkillInfo(
            name="test",
            type="repo",
            content="content",
            triggers=[],
            source=None,
            description=None,
            is_agentskills_format=False,
        )
        assert info.name == "test"
        assert info.type == "repo"

    def test_skill_info_with_all_types(self):
        """测试 SkillInfo 接受所有有效的类型值。"""
        for skill_type in get_args(SkillType):
            info = SkillInfo(
                name="test",
                type=skill_type,
                content="content",
                triggers=[],
                source=None,
                description=None,
                is_agentskills_format=False,
            )
            assert info.type == skill_type

    def test_skill_info_equality(self):
        """测试SkillInfo相等比较。"""
        info1 = SkillInfo(
            name="test",
            type="repo",
            content="content",
            triggers=["a", "b"],
            source="/path",
            description="desc",
            is_agentskills_format=True,
        )
        info2 = SkillInfo(
            name="test",
            type="repo",
            content="content",
            triggers=["a", "b"],
            source="/path",
            description="desc",
            is_agentskills_format=True,
        )
        assert info1 == info2

    def test_skill_info_inequality(self):
        """测试SkillInfo不等式比较。"""
        info1 = SkillInfo(
            name="test1",
            type="repo",
            content="content",
            triggers=[],
            source=None,
            description=None,
            is_agentskills_format=False,
        )
        info2 = SkillInfo(
            name="test2",
            type="repo",
            content="content",
            triggers=[],
            source=None,
            description=None,
            is_agentskills_format=False,
        )
        assert info1 != info2
