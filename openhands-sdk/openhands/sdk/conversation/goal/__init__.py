"""``/goal``命令：判断驱动，自我持续完成目标。

对话级命令（不是批评家），将智能体推向
objective: 它发送目标，运行智能体，用 a 判断完成情况
第二次 LLM，然后重新提示词，直到完成目标或达到上限。

决策逻辑位于：class:`GoalController` （传输层不可知，无 I/O）； :func:`run_goal` 是一
个薄同步驱动程序。 异步智能体-服务器任务
可以通过其自己的 I/O 循环重用同一控制器。

用法：:

    from openhands.sdk.conversation.goal import run_goal

    outcome = run_goal(conversation, "make pytest pass for mathx.py", judge_llm)
"""

from openhands.sdk.conversation.goal.controller import (
    GoalContinue,
    GoalController,
    GoalDone,
    GoalOutcome,
    GoalStatus,
    GoalStatusName,
    GoalStep,
)
from openhands.sdk.conversation.goal.judge import GoalVerdict, judge_goal
from openhands.sdk.conversation.goal.runner import run_goal


__all__ = [
    "GoalContinue",
    "GoalController",
    "GoalDone",
    "GoalOutcome",
    "GoalStatus",
    "GoalStatusName",
    "GoalStep",
    "GoalVerdict",
    "judge_goal",
    "run_goal",
]
