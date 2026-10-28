"""智能体中与批评者相关的功能的 Mixin 类。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from openhands.sdk.critic.base import CriticResult
from openhands.sdk.event import ActionEvent, LLMConvertibleEvent, MessageEvent
from openhands.sdk.logger import get_logger
from openhands.sdk.tool import Action
from openhands.sdk.tool.builtins import FinishAction


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation
    from openhands.sdk.critic.base import CriticBase


logger = get_logger(__name__)

# 用于在 agent_state 中存储迭代细化迭代计数的键
ITERATIVE_REFINEMENT_ITERATION_KEY = "iterative_refinement_iteration"


class CriticMixin:
    """Mixin 提供批评家评估和迭代细化功能。

    此混合模式设计用于与之配合使用智能体具有 [classes] 的 `critic` 类型属性
    CriticBase  |  None.
    """

    critic: CriticBase | None

    def _should_evaluate_with_critic(self, action: Action | None) -> bool:
        """确定评论家是否应根据行动类型和模式进行评估。"""
        if self.critic is None:
            return False

        if self.critic.mode == "all_actions":
            return True

        # 对于“finish_and_message”模式，仅评估FinishAction（MessageEvent将在step()中单独
        # 处理）
        #
        if isinstance(action, FinishAction):
            return True

        return False

    def _evaluate_with_critic(
        self, conversation: LocalConversation, event: ActionEvent | MessageEvent
    ) -> CriticResult | None:
        """对当前事件和历史进行评论家评估。"""
        if self.critic is None:
            return None

        try:
            # 建立事件历史记录，包括当前事件
            events = list(conversation.state.events) + [event]
            llm_convertible_events = [
                e for e in events if isinstance(e, LLMConvertibleEvent)
            ]

            # 暂时不使用 git_patch 进行评估
            critic_result = self.critic.evaluate(
                events=llm_convertible_events, git_patch=None
            )
            logger.info(
                f"✓ Critic evaluation: score={critic_result.score:.3f}, "
                f"success={critic_result.success}"
            )
            return critic_result
        except Exception as e:
            logger.error(f"✗ Critic evaluation failed: {e}", exc_info=True)
            return None

    def _check_iterative_refinement(
        self, conversation: LocalConversation, action_event: ActionEvent
    ) -> tuple[bool, str | None]:
        """检查迭代细化是否应在 FinishAction 之后继续。

        该方法检查批评者结果并确定是否继续进行另一次迭代。 状态突变（增加迭代计数器）
        仅在细化实际继续时发生。

        Returns:
            (should_continue, followup_message) 的元组。 如果should_continue是True，
            则智能体应该继续fo
            llowup_message而不是结束。
        """
        # 检查critic是否有迭代细化配置
        if self.critic is None or self.critic.iterative_refinement is None:
            return False, None

        config = self.critic.iterative_refinement
        state = conversation.state

        # 获取当前迭代计数（0-索引）
        iteration = state.agent_state.get(ITERATIVE_REFINEMENT_ITERATION_KEY, 0)

        # 检查我们是否已经超过最大迭代次数之前递增
        if iteration >= config.max_iterations:
            logger.info(
                f"Iterative refinement: max iterations "
                f"({config.max_iterations}) reached"
            )
            return False, None

        # 获取动作事件的评论结果
        critic_result = action_event.critic_result
        if critic_result is None:
            logger.warning("Iterative refinement: no critic result on FinishAction")
            return False, None

        if not self.critic.should_refine(critic_result):
            logger.info(
                f"Iterative refinement: success threshold "
                f"({config.success_threshold:.0%}) met with score "
                f"{critic_result.score:.3f}"
            )
            return False, None

        # 需要进一步细化，我们尚未达到最大迭代次数 NOW，因此我们继续计数器。使用重分配模
        # 式触发自动保存
        #
        new_iteration = iteration + 1
        state.agent_state = {
            **state.agent_state,
            ITERATIVE_REFINEMENT_ITERATION_KEY: new_iteration,
        }

        logger.info(
            "Iterative refinement: continuing after critic evaluation "
            f"(score={critic_result.score:.3f}, "
            f"threshold={config.success_threshold:.3f}, "
            f"iteration {new_iteration}/{config.max_iterations})"
        )
        followup = self.critic.get_followup_prompt(critic_result, new_iteration)
        return True, followup
