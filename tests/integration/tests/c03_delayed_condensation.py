"""由于软要求，测试延迟上下文压缩。

该测试验证：
1. 当触发软上下文压缩要求时（通过 max_size）
2. 但上下文压缩无法执行（无效范围）
3. 系统优雅地继续运行，不会引发异常
4. 一旦存在足够的事件，上下文压缩就会成功
"""

from openhands.sdk import Message, TextContent, Tool
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.event.condenser import Condensation
from openhands.sdk.tool import register_tool
from openhands.tools.terminal import TerminalTool
from tests.integration.base import BaseIntegrationTest, TestResult


# 测试运行程序的模块级指令
INSTRUCTION = """Using the echo command, print the numbers 1 through 10.
Use exactly 10 separate echo commands, one for each number."""


class DelayedCondensationTest(BaseIntegrationTest):
    """测试软需求是否允许延迟上下文压缩。"""

    INSTRUCTION: str = INSTRUCTION

    def __init__(self, *args, **kwargs):
        """初始化测试并跟踪上下文压缩。"""
        self.condensations: list[Condensation] = []
        super().__init__(*args, **kwargs)

    @property
    def tools(self) -> list[Tool]:
        """提供终端工具。"""
        register_tool("TerminalTool", TerminalTool)
        return [Tool(name="TerminalTool")]

    @property
    def condenser(self) -> LLMSummarizingCondenser:
        """使用 LLMSummarizingCondenser 低 max_size 对于软需求。"""
        condenser_llm = self.create_llm_copy("test-condenser-llm")
        return LLMSummarizingCondenser(
            llm=condenser_llm,
            max_size=6,  # 即使效率非常高，也足够低以触发智能体
            keep_first=1,
        )

    @property
    def max_iteration_per_run(self) -> int:
        """允许足够的迭代。"""
        return 30

    def conversation_callback(self, event):
        """跟踪上下文压缩事件。"""
        super().conversation_callback(event)

        if isinstance(event, Condensation):
            self.condensations.append(event)

    def run_instructions(self, conversation: LocalConversation) -> None:
        """测试软上下文压缩要求。

        步骤：
        1. 执行创建多个工具循环的任务
        2. 让软上下文压缩需求自然触发
        3. 即使无法立即满足上下文压缩，也验证系统是否继续
        4. 一旦存在有效范围，验证上下文压缩最终成功
        """
        # 执行主要任务
        conversation.send_message(message=self.instruction_message)
        conversation.run()

        # 添加更多消息以确保我们建立足够的事件这为潜在的上下文压缩创建了更多的原子单元
        #
        conversation.send_message(
            message=Message(
                role="user",
                content=[TextContent(text="Now print the numbers 11 through 15.")],
            )
        )
        conversation.run()

    def verify_result(self) -> TestResult:
        """验证软需求行为。

        成功标准：
        1. 对话成功完成（未因软要求而崩溃）
        2. 至少发生一次上下文压缩（一旦存在有效范围）
        """
        if len(self.condensations) == 0:
            return TestResult(
                success=False,
                reason="Expected at least one condensation to occur during the test",
            )

        return TestResult(
            success=True,
            reason=(
                f"Soft requirements handled correctly: {len(self.condensations)} "
                "condensation(s) occurred without crashing"
            ),
        )
