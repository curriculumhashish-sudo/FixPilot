"""``/goal`` 循环的传输层不可知大脑。

``GoalController`` 决定 -- 每次智能体运行完成后 -- 是否
continue (with a followup message) or stop (with a ``GoalOutcome``). It performs
无 I/O：* 驱动程序 *（同步 ``run_goal`` 或异步智能体服务器任务）拥有发送消息并运行智
能体； 控制者只是判断和决定。 这种划分让同步和异步驱动程序共享相
同的决策逻辑。
"""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from openhands.sdk.conversation.goal.judge import GoalVerdict, judge_goal
from openhands.sdk.conversation.goal.prompts import FOLLOWUP_PROMPT
from openhands.sdk.event import Event
from openhands.sdk.llm import LLM
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


class GoalOutcome(BaseModel):
    """``/goal`` 循环的结果。

    ``status`` 将真正的完成与达到迭代上限区分开来，因此驾驶员永远不必猜测无声的完成是
    否意味着成功。
    """

    status: Literal["complete", "capped"]
    iterations: int = Field(ge=1, description="Number of audit rounds performed.")
    verdict: GoalVerdict


GoalStatusName = Literal["running", "complete", "capped", "interrupted"]
"""``/goal`` 循环的生命周期状态。"""


class GoalStatus(BaseModel):
    """UI 进度芯片的 ``/goal`` 循环的实时状态。

    Agent Server 将其发布为 ``value``
    ``ConversationStateUpdateEvent`` 与 ``key="goal"`` 在每个生命周期点（开始、每轮和
    终止/中断状态）。
    """

    active: bool = Field(description="Whether the goal loop is still running.")
    status: GoalStatusName
    iteration: int = Field(ge=0, description="Audit rounds completed so far.")
    max_iterations: int = Field(ge=1)
    objective: str
    verdict: GoalVerdict | None = Field(
        default=None, description="Last judge verdict; set once the loop ends."
    )


class GoalContinue(BaseModel):
    """决定继续：在下一次运行之前发送 ``followup``。"""

    followup: str
    verdict: GoalVerdict = Field(
        description="The judge's verdict for the round that just finished."
    )


class GoalDone(BaseModel):
    """决定停止：循环以``outcome``结束。"""

    outcome: GoalOutcome


GoalStep = GoalContinue | GoalDone
""":meth:`GoalController.on_run_finished` 返回的一项决定。"""


class GoalController:
    """判断目标完成情况并决定继续还是停止，而不进行 I/O。

    驱动程序调用：meth:`start` 一次以获取要发送的第一条消息，然后在每次智能体运行后调
    用：meth:`on_run_finished` 以获得下一个决定。
    控制器拥有迭代计数和 ``max_iterations`` 上限，因此驱动程序保持微不足道。
    """

    def __init__(
        self, objective: str, judge_llm: LLM, *, max_iterations: int = 10
    ) -> None:
        if not objective.strip():
            raise ValueError("Goal objective must not be empty.")
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1.")
        self.objective = objective
        self.judge_llm = judge_llm
        self.max_iterations = max_iterations
        self.iteration = 0

    def start(self) -> str:
        """返回驱动程序应发送的第一条消息（目标）。"""
        return self.objective

    def on_run_finished(self, events: Sequence[Event]) -> GoalStep:
        """跑步后判断目标并决定是否继续。

        ``events``与法官LLM进行审计，当法官给出判决时计数一次，并返回一个：class:
        `GoalContinue`（有后续）或一个终端：class:
        `GoalDone`（有：class:`GoalOutcome`）。 法官提出加注后，计数保持不变：失败或
        放弃的审核并不是完整的一轮。
        """
        verdict = judge_goal(self.judge_llm, self.objective, events)
        self.iteration += 1
        logger.info(
            "Goal audit %d/%d: score=%.2f complete=%s",
            self.iteration,
            self.max_iterations,
            verdict.score,
            verdict.complete,
        )
        if verdict.complete:
            return GoalDone(
                outcome=GoalOutcome(
                    status="complete", iterations=self.iteration, verdict=verdict
                )
            )
        if self.iteration >= self.max_iterations:
            return GoalDone(
                outcome=GoalOutcome(
                    status="capped", iterations=self.iteration, verdict=verdict
                )
            )
        missing = verdict.missing or "Some requirements are not yet verified."
        followup = FOLLOWUP_PROMPT.format(iteration=self.iteration, missing=missing)
        return GoalContinue(followup=followup, verdict=verdict)
