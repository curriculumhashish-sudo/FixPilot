"""
集成测试用于上下文压缩期间的思维块处理。

该测试验证了 Anthropic 布鲁诺的思考块在对话中被正确处理上下文压缩，防止了包含思考块时
可能出现的不完整签名错误。

Note: 该测试仅适用于支持extended_thinking（Anthropic
克劳德模型）。 具有 reasoning_effort 的模型（例如 OpenAI o 系列和 GPT-5.x）会产生推理
项而不是思维块，并且会被跳过。
"""

from openhands.sdk import LLM, Message, TextContent, Tool
from openhands.sdk.context.condenser.base import CondenserBase
from openhands.sdk.context.view import View
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.event import ActionEvent, Condensation
from openhands.sdk.llm.utils.model_features import get_features
from openhands.sdk.tool import register_tool
from openhands.tools.terminal import TerminalTool
from tests.integration.base import BaseIntegrationTest, SkipTest, TestResult


# 测试运行程序的模块级指令
INSTRUCTION = """Using bc calculator, compute:
1. Compound interest on $5000 at 6% annual rate for 10 years (compounded annually)
   Formula: A = P(1 + r/n)^(nt) where n=1
2. Simple interest on the same principal, rate, and time
   Formula: I = P * r * t
3. The difference between compound and simple interest

Show your calculations step by step."""


class FirstToolLoopCondenser(CondenserBase):
    """
    通过忘记第一个工具循环来处理上下文压缩的自定义上下文压缩器。

    这个上下文压缩器是为了测试思考块处理 - 它会忘记包含思考块的第一个原子单元，并替换
    它为总结。
    """

    def handles_condensation_requests(self) -> bool:
        """指示此上下文压缩器处理显式上下文压缩请求。"""
        return True

    def condense(self, view: View, agent_llm: LLM | None = None) -> View | Condensation:
        """
        通过忘记包含思维块的第一个工具循环来浓缩。

        这验证了：
        1. 我们可以用思维块来识别原子单位
        2. 我们可以忘记特定的单位
        3. 后来的思维块被保留
        """
        # 获取定义原子单元边界的操作索引。
        indices = sorted(view.manipulation_indices)

        # 使用思维块查找原子单位（连续索引之间的范围）
        units_with_thinking = []
        for i in range(len(indices) - 1):
            start_idx = indices[i]
            end_idx = indices[i + 1]
            has_thinking = False
            for event in view.events[start_idx:end_idx]:
                if isinstance(event, ActionEvent) and event.thinking_blocks:
                    has_thinking = True
                    break
            if has_thinking:
                units_with_thinking.append((start_idx, end_idx, i))

        # 我们至少需要两个具有思维模块的单元才能正确测试：
        # - 一个被遗忘的人（第一）
        # - 保留一个（第二个）
        if len(units_with_thinking) < 2:
            return view

        # 忘记第一个带有思维块的单元
        start_idx, end_idx, _ = units_with_thinking[0]

        # 为遗忘的内容创建摘要
        summary = (
            "Previously, I calculated compound and simple interest values "
            "using the bc calculator."
        )

        # 获取要忘记的事件 ID
        forgotten_event_ids = {event.id for event in view.events[start_idx:end_idx]}

        # 创建上下文压缩事件
        return Condensation(
            forgotten_event_ids=forgotten_event_ids,
            summary=summary,
            summary_offset=start_idx,
            llm_response_id="test-condenser-response",
        )


class ThinkingBlockCondenserTest(BaseIntegrationTest):
    """
    测试在上下文压缩期间是否正确处理了思维障碍。

    本次测试：
    1. 进行多步骤对话，产生思维块
    2. 手动触发上下文压缩
    3. 验证：
       - 产生了多个思维块
       - 上下文压缩只发生一次
       - 第一个思维块被遗忘了
       - 后来的思维块被保留下来
    """

    INSTRUCTION: str = INSTRUCTION

    def __init__(self, *args, **kwargs):
        """通过跟踪思维块和凝结来初始化测试。"""
        self.thinking_block_count = 0
        self.condensation_count = 0
        self.condensed_thinking_blocks = False
        self.preserved_thinking_blocks = False
        super().__init__(*args, **kwargs)

    @property
    def tools(self) -> list[Tool]:
        """提供bc计算器的终端工具。"""
        register_tool("TerminalTool", TerminalTool)
        return [Tool(name="TerminalTool")]

    @property
    def condenser(self) -> CondenserBase:
        """使用处理思维障碍的自定义上下文压缩器。"""
        return FirstToolLoopCondenser()

    @property
    def max_iteration_per_run(self) -> int:
        """每次运行最多允许 30 次迭代。"""
        return 30

    def setup(self) -> None:
        """
        验证模型支持扩展思维。

        启用了 extended_thinking 的 Anthropic Claude 模型特别支持思维块。 仅支持
        reasoning_effort 的模型（例
        如 OpenAI o-series 和 GPT-5.x）会产生推理项而不是思维块，因此应该跳过它们。
        """
        model = self.llm_config.get("model", "")
        features = get_features(model)

        # 检查模型是否配置了扩展思维
        has_extended_thinking = self.llm_config.get("extended_thinking", False)

        # 对于 Claude Opus，如果未设置，则自动启用扩展思维
        if "opus" in model.lower() and not has_extended_thinking:
            self.llm_config["extended_thinking"] = True
            # 使用更新的配置重新创建 LLM
            self.llm = self.llm.__class__(
                **{**self.llm.model_dump(), **self.llm_config}
            )
            self.agent.llm = self.llm
            has_extended_thinking = True

        # 如果模型不支持扩展思维（产生 thinking_blocks），则跳过测试。 仅支持
        # reasoning_effort 的模型会生成 responses_reasoning_item，这是一种不同的机制。
        #
        if not has_extended_thinking and not features.supports_extended_thinking:
            raise SkipTest(
                f"Model {model} does not support extended thinking "
                "(produces reasoning items instead of thinking blocks)"
            )

    def conversation_callback(self, event):
        """跟踪思维障碍和上下文压缩事件。"""
        super().conversation_callback(event)

        # 在任何上下文压缩之前计算思维块
        if isinstance(event, ActionEvent) and event.thinking_blocks:
            if self.condensation_count == 0:
                self.thinking_block_count += 1
            else:
                # 上下文压缩之后出现的思维块表示被保留
                self.preserved_thinking_blocks = True
                self.thinking_block_count += 1

        # 跟踪凝结
        if isinstance(event, Condensation):
            self.condensation_count += 1
            # 如果我们以前见过思维块，现在我们正在压缩，我们可以假设一些思维块被压缩了
            #
            if self.thinking_block_count > 0 and event.forgotten_event_ids:
                self.condensed_thinking_blocks = True

    def run_instructions(self, conversation: LocalConversation) -> None:
        """
        执行多步骤对话流。

        步骤：
        1. 初始计算请求
        2. 验证请求以确保正确性
        3. 手动上下文压缩触发
        4. 不同参数的附加计算
        """
        # 第 1 步：初始说明
        conversation.send_message(message=self.instruction_message)
        conversation.run()

        # 第 2 步：要求验证（产生更多思考）
        conversation.send_message(
            message=Message(
                role="user",
                content=[
                    TextContent(
                        text=(
                            "Please verify your calculations are correct "
                            "and explain the reasoning."
                        )
                    )
                ],
            )
        )
        conversation.run()

        # 步骤 3：手动触发上下文压缩
        conversation.send_message(
            message=Message(
                role="user",
                content=[
                    TextContent(
                        text="Now, compute the same for $10000 at 5% for 15 years."
                    )
                ],
            )
        )
        # 运行前请求上下文压缩
        conversation.condense()
        conversation.run()

    def verify_result(self) -> TestResult:
        """
        验证在上下文压缩期间是否正确处理了思维块。

        成功标准：
        1. 至少生成 3 个思维块（跨多个步骤）
        2. 至少触发 1 上下文压缩个事件（可以是自动或手动）
        3. 思维块在某个时刻被浓缩（被遗忘）
        4. 后来的思考块被保留（上下文压缩之后的新块）
        """
        reasons = []

        # 检查思维块数量
        if self.thinking_block_count < 3:
            reasons.append(
                f"Expected at least 3 thinking blocks, got {self.thinking_block_count}"
            )

        # 检查上下文压缩计数（允许多次冷凝）
        if self.condensation_count < 1:
            reasons.append(
                f"Expected at least 1 condensation event, got {self.condensation_count}"
            )

        # 检查思维块是否被浓缩
        if not self.condensed_thinking_blocks:
            reasons.append(
                "Expected first thinking block to be forgotten during condensation"
            )

        # 检查后来的思维块是否被保留
        if not self.preserved_thinking_blocks:
            reasons.append("Expected new thinking blocks to appear after condensation")

        if reasons:
            return TestResult(
                success=False,
                reason=(
                    f"Thinking block handling validation failed: {'; '.join(reasons)}"
                ),
            )

        return TestResult(
            success=True,
            reason=(
                f"Successfully handled {self.thinking_block_count} thinking blocks "
                f"with {self.condensation_count} condensation(s)"
            ),
        )
