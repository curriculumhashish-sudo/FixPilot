"""
AgentFinishedCritic实施。

该评论家通过检查以下内容来评估智能体是否正确完成了任务：
1. 智能体的最后一个动作是 FinishAction（正确完成）
2. 生成的git补丁非空（实际进行了更改）
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from openhands.sdk.critic.base import CriticBase, CriticResult
from openhands.sdk.logger import get_logger
from openhands.sdk.tool.builtins.finish import FinishAction


if TYPE_CHECKING:
    from openhands.sdk.event.base import LLMConvertibleEvent


logger = get_logger(__name__)


class AgentFinishedCritic(CriticBase):
    """
    评估智能体是否正确完成任务的批评者。

    这位批评家检查了两个主要标准：
    1. 智能体的最后一个动作是 FinishAction（正确完成）
    2. 生成的git补丁非空（实际进行了更改）
    """

    def evaluate(
        self, events: Sequence["LLMConvertibleEvent"], git_patch: str | None = None
    ) -> CriticResult:
        """
        评估智能体是否使用非空 git 补丁正确完成。

        Args:
            events: 智能体的执行列表
            git_patch: 由智能体生成的可选 git 补丁

        Returns:
            CriticResult 如果成功则得分 1.0，否则得分 0.0
        """
        reasons = []

        # 检查 git patch 是否非空
        if not git_patch or not git_patch.strip():
            reasons.append("Empty git patch")
            logger.debug("AgentFinishedCritic: Empty git patch")
            return CriticResult(
                score=0.0,
                message="Agent did not produce a non-empty git patch. "
                + "; ".join(reasons),
            )

        # 检查智能体是否正确完成FinishAction
        if not self._has_finish_action(events):
            reasons.append("No FinishAction found")
            logger.debug("AgentFinishedCritic: No FinishAction")
            return CriticResult(
                score=0.0,
                message="Agent did not finish properly. " + "; ".join(reasons),
            )

        logger.debug("AgentFinishedCritic: Successfully completed")
        return CriticResult(
            score=1.0,
            message="Agent completed with FinishAction and non-empty patch",
        )

    def _has_finish_action(self, events: Sequence["LLMConvertibleEvent"]) -> bool:
        """检查最后一个操作是否为 FinishAction。"""
        if not events:
            return False

        # 查找历史记录中的最后一个ActionEvent
        from openhands.sdk.event.llm_convertible.action import ActionEvent

        for event in reversed(events):
            if isinstance(event, ActionEvent):
                if event.action and isinstance(event.action, FinishAction):
                    return True
                return False

        return False
