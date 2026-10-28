"""技能的触发类型。

该模块定义了不同的触发器类型，以确定何时应激活技能。
"""

from abc import ABC
from typing import Literal

from pydantic import BaseModel


class BaseTrigger(BaseModel, ABC):
    """所有触发器类型的基类。"""

    pass


class KeywordTrigger(BaseTrigger):
    """触发基于关键字的技能。

    当用户查询中出现特定关键字时，这些技能就会被激活。
    """

    type: Literal["keyword"] = "keyword"
    keywords: list[str]


class TaskTrigger(BaseTrigger):
    """触发特定任务技能。

    这些技能针对特定任务类型而激活，并且可以修改提示词。
    """

    type: Literal["task"] = "task"
    triggers: list[str]


class PathTrigger(BaseTrigger):
    """触发路径范围的技能（“规则”）。

    当智能体触及路径与 ``paths`` glob 模式之一（gitignore 样式 ``**`` 语义）匹配的文
    件时，这些技能将被激活。
    """

    type: Literal["path"] = "path"
    paths: list[str]
