import abc
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from openhands.sdk.critic.result import CriticResult
from openhands.sdk.utils.models import DiscriminatedUnionMixin


if TYPE_CHECKING:
    from openhands.sdk.event.base import LLMConvertibleEvent


# 后续提示词生成器函数的类型别名
FollowupPromptFn = Callable[[CriticResult, int], str]
"""根据批评结果和迭代生成后续提示词的函数。"""


class IterativeRefinementConfig(BaseModel):
    """基于评论家反馈的迭代细化配置。

    当附加到 CriticBase 时，如果评论分数低于阈值，Conversation.run() 方法将自动重试任
    务。

    Example:
        critic = APIBasedCritic(
            server_url="...",
            api_key="...",
            model_name="critic",
            iterative_refinement=IterativeRefinementConfig(
                success_threshold=0.7,
                max_iterations=3,
            ),
        )
        agent = Agent(llm=llm, tools=tools, critic=critic)
        conversation = Conversation(agent=agent, workspace=workspace)
        conversation.send_message("Create a calculator module...")
        conversation.run()  # 如果评分低于0.7，将自动重试
    """

    success_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Score threshold (0-1) to consider task successful.",
    )
    max_iterations: int = Field(
        default=3,
        ge=1,
        description="Maximum number of iterations before giving up.",
    )
    # 注意：followup_prompt_fn 不可序列化，因此我们使用默认值
    # 用户可以通过子类化或直接使用 IterativeRefinement 类来覆盖


class CriticBase(DiscriminatedUnionMixin, abc.ABC):
    """评论家是一个接受事件列表的函数，
    可选的 git patch，并返回有关智能体操作质量的分数。
    """

    mode: Literal["finish_and_message", "all_actions"] = Field(
        default="finish_and_message",
        description=(
            "When to run critic evaluation:\n"
            "- 'finish_and_message': Evaluate on FinishAction and agent"
            " MessageEvent (default, minimal performance impact)\n"
            "- 'all_actions': Evaluate after every agent action (WARNING: "
            "significantly slower due to API calls on each action)"
        ),
    )

    iterative_refinement: IterativeRefinementConfig | None = Field(
        default=None,
        description=(
            "Optional configuration for iterative refinement. When set, "
            "Conversation.run() will automatically retry the task if the "
            "critic score is below the success_threshold, up to max_iterations."
        ),
    )

    @abc.abstractmethod
    def evaluate(
        self, events: Sequence["LLMConvertibleEvent"], git_patch: str | None = None
    ) -> CriticResult:
        pass

    def get_followup_prompt(self, critic_result: CriticResult, iteration: int) -> str:
        """生成后续提示词以进行迭代细化。

        子类可以重写此方法以提供自定义后续操作提示词。

        Args:
            critic_result: 批评家的结果来自上一次迭代。
            iteration: 当前迭代次数（1-索引）。

        Returns:
            要发送到智能体的后续提示词字符串。
        """
        score_percent = critic_result.score * 100

        return (
            f"The task appears incomplete (iteration {iteration}, "
            f"predicted success likelihood: {score_percent:.1f}%).\n\n"
            "Please review what you've done and verify each requirement is met.\n"
            "List what's working and what needs fixing, then complete the task.\n"
        )

    def should_refine(self, critic_result: CriticResult) -> bool:
        """评估是否应该继续迭代细化。"""
        if self.iterative_refinement is None:
            return False

        return critic_result.score < self.iterative_refinement.success_threshold
