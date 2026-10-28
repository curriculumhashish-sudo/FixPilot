"""测试智能体是否可以浏览 GitHub PR 并提取信息。"""

from openhands.sdk import get_logger
from openhands.sdk.conversation import get_agent_final_response
from tests.integration.base import BaseIntegrationTest, TestResult


INSTRUCTION = (
    "Look at https://github.com/OpenHands/OpenHands/pull/8, and tell me "
    "what is happening there and what did @asadm suggest. "
)


logger = get_logger(__name__)


class GitHubPRBrowsingTest(BaseIntegrationTest):
    """测试智能体是否可以浏览 GitHub PR 并提取信息。"""

    INSTRUCTION: str = INSTRUCTION

    @property
    def enable_browser(self) -> bool:
        """为此浏览测试启用浏览器工具。"""
        return True

    def setup(self) -> None:
        """GitHub PR 浏览无需特殊设置。"""

    def verify_result(self) -> TestResult:
        """验证智能体是否已成功浏览 GitHub PR。"""

        # 获取智能体对指令的最终答案/响应
        agent_answer = get_agent_final_response(self.conversation.state.events)

        if not agent_answer:
            return TestResult(
                success=False,
                reason=(
                    "No final answer found from agent. "
                    f"Events: {len(list(self.conversation.state.events))}, "
                    f"LLM messages: {len(self.llm_messages)}"
                ),
            )

        # 转换为小写以进行不区分大小写的匹配
        answer_text = agent_answer.lower()

        github_indicators = ["mit", "apache", "license"]

        if any(indicator in answer_text for indicator in github_indicators):
            return TestResult(
                success=True,
                reason="Agent's final answer contains information about the PR content",
            )
        else:
            return TestResult(
                success=False,
                reason=(
                    "Agent's final answer does not contain the expected information "
                    "about the PR content. "
                    f"Final answer preview: {agent_answer[:200]}..."
                ),
            )
