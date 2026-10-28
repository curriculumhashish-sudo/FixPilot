"""用于对话完成操作的实验性结构化任务结果模型。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TaskOutcomeStatus = Literal[
    "success",
    "partial_success",
    "blocked",
    "failed",
    "unknown",
]


class TaskOutcome(BaseModel):
    """报告对话任务的最新语义结果。

    Experimental: 这种结构化响应模型可能会随着任务结果而改变
    报告细化。
    """

    model_config = ConfigDict(populate_by_name=True)

    status: TaskOutcomeStatus = Field(
        description="Agent's semantic assessment of task completion."
    )
    summary: str = Field(
        alias="outcome_summary",
        description=(
            "Concise outcome summary. Include what was completed, blockers, "
            "required user action, and relevant next steps."
        ),
    )
