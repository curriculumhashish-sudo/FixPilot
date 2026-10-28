class SkillError(Exception):
    """所有技能错误的基本例外。"""

    pass


class SkillValidationError(SkillError):
    """当技能元数据存在验证错误时引发。"""

    def __init__(self, message: str = "Skill validation failed") -> None:
        super().__init__(message)
