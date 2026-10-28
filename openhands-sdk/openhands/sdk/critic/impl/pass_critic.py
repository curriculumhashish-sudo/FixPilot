"""
PassCritic实施。

该批评家总是返回成功，在不需要评估或所有实例都应被视为成功时很有用。
"""

from collections.abc import Sequence

from openhands.sdk.critic.base import CriticBase, CriticResult
from openhands.sdk.event import LLMConvertibleEvent
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


class PassCritic(CriticBase):
    """
    总是返回成功的批评者。

    当不需要评估或所有实例无论其输出如何都应被视为成功时，可以使用此批评家。
    """

    def evaluate(
        self,
        events: Sequence[LLMConvertibleEvent],  # noqa: ARG002
        git_patch: str | None = None,  # noqa: ARG002
    ) -> CriticResult:
        """
        始终评估为成功。

        Args:
            events: 智能体执行中的事件列表（未使用）
            git_patch: 智能体生成的可选 git 补丁（未使用）

        Returns:
            CriticResult 得分 1.0（总是成功）
        """
        logger.debug("PassCritic: Always returns success")
        return CriticResult(score=1.0, message="PassCritic always succeeds")
