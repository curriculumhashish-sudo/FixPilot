"""测试智能体和基于 token 的上下文压缩器是否成功触发上下文压缩。

此集成测试验证：
1. 智能体可以通过 LLMSummarizingCondenser 来配置 max_tokens
2. 上下文压缩器正确使用 get_token_count 来衡量对话大小
3. 当超出 token 限制时触发上下文压缩
"""

from openhands.sdk import get_logger
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.sdk.event.condenser import Condensation
from openhands.sdk.tool import Tool, register_tool
from openhands.tools.terminal import TerminalTool
from tests.integration.base import BaseIntegrationTest, TestResult


# 大型工具结果跨越 token 限制，而无需长的、依赖于模型的循环。
INSTRUCTION = """
Run these two commands using the terminal tool, in separate calls, in order:

1. python -c "print('token pressure context ' * 2000)"
2. python -c "print('second context payload ' * 2000)"

Do not redirect, truncate, or combine their output. The large output is intentional:
we are testing conversation condensation. After both calls, reply "done".
Make sure you generate some "extended thinking" for each tool call to help test
thinking blocks together with condensation.
"""

logger = get_logger(__name__)


class TokenCondenserTest(BaseIntegrationTest):
    """测试智能体与基于 token 的上下文压缩器触发器上下文压缩。"""

    INSTRUCTION: str = INSTRUCTION

    def __init__(self, *args, **kwargs):
        """使用跟踪变量初始化测试。"""
        self.condensations: list[Condensation] = []
        super().__init__(*args, **kwargs)

    @property
    def tools(self) -> list[Tool]:
        """智能体可用的工具列表。"""
        register_tool("TerminalTool", TerminalTool)
        return [
            Tool(name="TerminalTool"),
        ]

    @property
    def condenser(self) -> LLMSummarizingCondenser:
        """配置基于 token 的上下文压缩器，并具有触发上下文压缩的下限。"""
        # 创建具有下限 token 的上下文压缩器以触发上下文压缩使用 max_tokens 而不是
        # max_size 来测试 token 计数
        #
        condenser_llm = self.create_llm_copy("test-condenser-llm")
        return LLMSummarizingCondenser(
            llm=condenser_llm,
            max_size=1000,  # 设置为高，这样它就不会在事件计数时触发
            # 载荷（约9千个token，2000个提示词）轻松完成了这一任务，因此，双方在系统CI或
            # 工具描述上的细微差别上都没有优势。
            #
            max_tokens=6000,  # 低 token 限制以确保上下文压缩触发
            # 保留系统提示词和用户说明。 当 keep_first=1 时，第一个上下文压缩会忘记该指
            # 令，只有当 LLM 摘要恰好保留它时，命令 2 才会存活。
            #
            keep_first=2,
        )

    @property
    def max_iteration_per_run(self) -> int:
        # 上下文压缩步骤仍然算作一次迭代：agent.step 在发出上下文压缩后提前返回，并且循
        # 环递增计数器。 因此，快乐路径已经有约 4 次迭代，因此请留出足够的空间。
        #
        return 20

    def conversation_callback(self, event):
        """覆盖回调以检测上下文压缩事件。"""
        super().conversation_callback(event)

        if isinstance(event, Condensation):
            if len(self.condensations) >= 1:
                logger.info("2nd condensation detected! Stopping test early.")
                self.conversation.pause()
            # 我们允许第一个上下文压缩请求来测试思维块 + 上下文压缩是否可以一起工作
            #
            self.condensations.append(event)

    def setup(self) -> None:
        logger.info(f"Token condenser test: max_tokens={self.condenser.max_tokens}")

    def verify_result(self) -> TestResult:
        """验证基于 token 计数的上下文压缩是否被触发两次。"""
        if len(self.condensations) < 2:
            return TestResult(
                success=False,
                reason=(
                    f"Expected at least 2 condensations, got "
                    f"{len(self.condensations)}. Token counting may not work, or the "
                    "second payload did not cross the token limit."
                ),
            )

        events_summarized = len(self.condensations[0].forgotten_event_ids)
        return TestResult(
            success=True,
            reason=(
                f"Condensation triggered {len(self.condensations)} times, first "
                f"summarizing {events_summarized} events."
            ),
        )
