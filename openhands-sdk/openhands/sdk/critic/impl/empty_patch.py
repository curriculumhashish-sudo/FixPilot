"""
EmptyPatchCritic实施。

该批评家仅评估 git 补丁是否非空。 与 AgentFinishedCritic 不同，它不检查智能体是否正确
完成。
"""

from collections.abc import Sequence

from openhands.sdk.critic.base import CriticBase, CriticResult
from openhands.sdk.event import LLMConvertibleEvent
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


class EmptyPatchCritic(CriticBase):
    """
    只评估 git 补丁是否非空的批评家。

    这位批评家只检查一个标准：
    - 生成的git补丁非空（实际进行了更改）

    与 AgentFinishedCritic 不同，该批评家不会检查智能体与 FinishAction 是否正确完成。
    """

    def evaluate(
        self,
        events: Sequence[LLMConvertibleEvent],  # noqa: ARG002
        git_patch: str | None = None,
    ) -> CriticResult:
        """
        评估 git 补丁是否非空。

        Args:
            events: 智能体执行中的事件列表（未使用）
            git_patch: 由智能体生成的可选 git 补丁

        Returns:
            CriticResult 如果 patch 非空则得分 1.0，否则得分 0.0
        """
        if not git_patch or not git_patch.strip():
            logger.debug("EmptyPatchCritic: Empty git patch")
            return CriticResult(score=0.0, message="Git patch is empty or missing")

        logger.debug("EmptyPatchCritic: Non-empty git patch found")
        return CriticResult(score=1.0, message="Git patch is non-empty")
