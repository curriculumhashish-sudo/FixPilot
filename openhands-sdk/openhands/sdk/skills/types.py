from datetime import UTC, datetime

from pydantic import BaseModel, Field


class InputMetadata(BaseModel):
    """任务技能输入的元数据。"""

    name: str = Field(description="Name of the input parameter")
    description: str = Field(description="Description of the input parameter")


class SkillKnowledge(BaseModel):
    """代表来自触发技能的知识。"""

    name: str = Field(description="The name of the skill that was triggered")
    trigger: str = Field(description="The word that triggered this skill")
    content: str = Field(description="The actual content/knowledge from the skill")
    location: str | None = Field(
        default=None,
        description="Path to the SKILL.md file (for resolving relative resource paths)",
    )


class SkillResponse(BaseModel):
    """技能响应模型端点。

    Note: 该模型仅包含可以确定的基本元数据
    无需解析技能内容。 使用单独的内容API来获取详细的技能信息。
    """

    name: str = Field(description="The name of the skill")
    path: str = Field(description="The path or identifier of the skill")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the skill was created",
    )


class SkillContentResponse(BaseModel):
    """个人技能内容的响应模型端点。"""

    content: str = Field(description="The full content of the skill")
    path: str = Field(description="The path or identifier of the skill")
    triggers: list[str] = Field(
        description="List of triggers associated with the skill"
    )
    git_provider: str | None = Field(
        None,
        description="Git provider if the skill is sourced from a Git repository",
    )
