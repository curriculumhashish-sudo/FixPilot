"""测试智能体与基于大小的上下文压缩器是否成功触发上下文压缩。

此集成测试验证：
1. 智能体可以通过 LLMSummarizingCondenser 来配置 max_size
2. 上下文压缩器正确计数事件以测量对话大小
3. 上下文压缩超出事件计数限制时触发
"""

from openhands.sdk import get_logger
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.sdk.event.condenser import Condensation
from openhands.sdk.tool import Tool, register_tool
from openhands.tools.terminal import TerminalTool
from tests.integration.base import BaseIntegrationTest, TestResult


# 旨在生成多个智能体消息的指令
INSTRUCTION = """
Count from 1 to 50. For each number, use the echo command to print it along with
a short description (e.g., "1 is the first number", "2 is an even number", etc.).

DO NOT write a script to do this. Instead, interactively call the echo command
50 times, once for each number from 1 to 50.

This is intentionally inefficient to test our context management system.
"""

logger = get_logger(__name__)


class SizeCondenserTest(BaseIntegrationTest):
    """测试智能体与基于大小的上下文压缩器触发器上下文压缩。"""

    INSTRUCTION: str = INSTRUCTION

    def __init__(self, *args, **kwargs):
        """使用跟踪变量初始化测试。"""
        self.condensations: list[Condensation] = []
        super().__init__(*args, **kwargs)

        # 出于成本/安全考虑，某些模型明确禁止使用长的、重复的工具循环。 对于拒绝此类请求
        # 的模型，请跳过此测试。
        #
        self.skip_if_model_matches(
            "gpt-5.1-codex-max",
            "This test stresses long repetitive tool loops to trigger size-based "
            "condensation. GPT-5.1 Codex Max often declines such requests for "
            "efficiency/safety reasons.",
        )

    @property
    def tools(self) -> list[Tool]:
        """智能体可用的工具列表。"""
        register_tool("TerminalTool", TerminalTool)
        return [
            Tool(name="TerminalTool"),
        ]

    @property
    def condenser(self) -> LLMSummarizingCondenser:
        """配置基于大小的上下文压缩器和触发下限上下文压缩。"""
        # 创建具有低 max_size 的上下文压缩器以触发上下文压缩使用 max_size 而不是
        # max_tokens 来测试事件计数
        #
        condenser_llm = self.create_llm_copy("test-condenser-llm")
        return LLMSummarizingCondenser(
            llm=condenser_llm,
            max_size=10,  # 低事件限制以确保上下文压缩个触发
            max_tokens=None,  # 不要使用 token 限制
            keep_first=1,  # 仅保留初始用户消息
        )

    @property
    def max_iteration_per_run(self) -> int:
        return 50

    def conversation_callback(self, event):
        """覆盖回调以检测上下文压缩事件。"""
        super().conversation_callback(event)

        if isinstance(event, Condensation):
            if len(self.condensations) >= 1:
                logger.info("2nd condensation detected! Stopping test early.")
                self.conversation.pause()
            # 我们允许第一个上下文压缩请求来测试上下文压缩是否有效
            self.condensations.append(event)

    def setup(self) -> None:
        logger.info(f"Size condenser test: max_size={self.condenser.max_size}")

    def verify_result(self) -> TestResult:
        """验证是否根据事件计数触发了上下文压缩。"""
        if len(self.condensations) == 0:
            return TestResult(
                success=False,
                reason="Condensation not triggered. Event counting may not work.",
            )

        events_summarized = len(self.condensations[0].forgotten_event_ids)
        return TestResult(
            success=True,
            reason=f"Condensation triggered, summarizing {events_summarized} events.",
        )
