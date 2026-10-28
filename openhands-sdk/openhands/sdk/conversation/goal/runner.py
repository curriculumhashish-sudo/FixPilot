"""同步 ``/goal`` 驱动程序。

``run_goal`` 是一个薄同步司机过：class：`GoalController`它拥有 I/O（发送消息、运行代
码）等智能体) 在控制器拥有评判和继续-停止决策时
。 安异步智能体服务器任务可以使用自己的 I/O 循环复用相同的控制器。

不同于评论家（run loop 会咨询） *inside* one ``run()``), 这驱动对话从外部，因此它与任
何批评者进行交互智能体已经拥有 -- 该批评家控制着
每个内层 ``run()``; 这个循环控制着总体目标。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from openhands.sdk.conversation.goal.controller import (
    GoalController,
    GoalDone,
    GoalOutcome,
)


if TYPE_CHECKING:
    from openhands.sdk.conversation.base import BaseConversation
    from openhands.sdk.llm import LLM


def run_goal(
    conversation: BaseConversation,
    objective: str,
    judge_llm: LLM,
    *,
    max_iterations: int = 10,
) -> GoalOutcome:
    """将 ``conversation`` 推向 ``objective``，每轮判断完成情况。

    发送目标，运行智能体直至结束，然后让
    :class:`GoalController` 根据法官的反馈决定是否重新提示词
    或停止。 返回一个：class:`GoalOutcome`，其 ``status`` 为 ``"complete"`` 或
    ``"capped"``.

    Args:
        conversation: 驱动的对话（任何代理/评论家配置）。
        objective: 追求和审计的目标。
        judge_llm: 第二个 LLM 表示完成度。
        max_iterations: 放弃之前对审计轮次进行硬性限制。
    """
    controller = GoalController(objective, judge_llm, max_iterations=max_iterations)
    conversation.send_message(controller.start())
    while True:
        conversation.run()
        step = controller.on_run_finished(conversation.state.events)
        if isinstance(step, GoalDone):
            return step.outcome
        conversation.send_message(step.followup)
