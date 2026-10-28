"""测试智能体是否为每个工具调用提供了简洁的解释。"""

from __future__ import annotations

from textwrap import dedent

from tests.integration.base import TestResult
from tests.integration.behavior_utils import (
    get_conversation_summary,
    verify_all_actions_have_summary,
)
from tests.integration.utils.behavior_helpers import (
    SoftwareAgentSDKBehaviorTest,
    append_environment_tips,
)
from tests.integration.utils.llm_judge import judge_agent_behavior


INSTRUCTION_BODY = dedent(
    """
    The project is at version 1.4.1, and I'd like to bump it to 1.4.2
    throughout the SDK. Please update the version across the repo, I
    remember mostly in `pyproject.toml` and lock files.
    """
)
INSTRUCTION = append_environment_tips(INSTRUCTION_BODY)


class EachToolCallHavingExplanation(SoftwareAgentSDKBehaviorTest):
    """
    确保智能体为每个工具调用提供简洁的解释，而不是保持沉默。
    """

    INSTRUCTION: str = INSTRUCTION

    def verify_result(self) -> TestResult:
        if self.repo_dir is None:
            raise RuntimeError("Repository directory was not initialized.")

        # 首先，验证所有操作都填充了汇总字段这是一个硬性要求 - 汇总字段应始终存在
        #
        summary_check_passed, summary_check_reason = verify_all_actions_have_summary(
            self.collected_events
        )
        if not summary_check_passed:
            return TestResult(
                success=False,
                reason=f"Summary field check failed: {summary_check_reason}",
            )

        # 然后用LLM判断来评价解释的质量
        conversation_summary = get_conversation_summary(self.collected_events)
        evaluation_criteria = dedent(
            """
            Approve the agent only if it:
            1. Provides a concise explanation for each tool call. It is acceptable
            if the explanation seems vague or repetitive, we want to test for existence.
            Did the agent exhibit those behaviors?
            """
        )

        judgment = judge_agent_behavior(
            user_instruction=INSTRUCTION,
            conversation_summary=conversation_summary,
            evaluation_criteria=evaluation_criteria,
        )

        self.add_judge_usage(
            prompt_tokens=judgment.prompt_tokens,
            completion_tokens=judgment.completion_tokens,
            cost=judgment.cost,
        )

        if judgment.approved:
            return TestResult(
                success=True,
                reason=(
                    f"All actions have summaries ({summary_check_reason}). "
                    "Agent provided a concise explanation for each tool call. "
                    f"Judge reasoning: {judgment.reasoning} "
                    f"(confidence={judgment.confidence:.2f})"
                ),
            )

        return TestResult(
            success=False,
            reason=(
                "Agent behavior was not acceptable according to the LLM judge. "
                "Judge reasoning: "
                f"{judgment.reasoning} "
                f"(confidence={judgment.confidence:.2f})"
            ),
        )
