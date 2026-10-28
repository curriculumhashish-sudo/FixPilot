"""当上下文压缩范围无效时，测试硬上下文重置。"""

from openhands.sdk import Tool
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event import (
    Condensation,
    LLMConvertibleEvent,
    SystemPromptEvent,
)
from openhands.sdk.tool import register_tool
from openhands.tools.terminal import TerminalTool
from tests.integration.base import BaseIntegrationTest, TestResult


# 在正常上下文压缩之前发送的确定性上下文标记事件的数量。 每个都是单个原子用户消息，因此
# 生成的事件计数与模型无关。 足够大，即使智能体选择不调用工具，也存在有效的上下文压缩范
# 围。
#
CONTEXT_MARKER_COUNT = 8

# token 放置在硬重置回合的指令中，这样我们就可以断言摘要包含内容，而不仅仅是忘记的 ID。
#
HARD_RESET_MARKER = "HARD_RESET_MARKER_7F3A"

# keep_first 必须足够大，以便在硬重置后视图上可以出现正常的上下文压缩（因此第二个上下文
# 压缩是正常的，而不是另一次硬重置）。 请参阅 `condenser` 中的内联注释。
#
KEEP_FIRST = 4

# 测试在 run_instructions() 中驱动对话本身； 这个模块级值正好满足集成运行者的要求。
#
INSTRUCTION: str = "This test defines its own instructions in run_instructions()."


class HardContextResetTest(BaseIntegrationTest):
    """当上下文压缩范围无效时，测试硬上下文重置。

    此测试设置了一种情况，其中请求显式上下文压缩，但没有可用的，这应该触发硬上下文重
    置。 然后我们验证，之后我们可以正常继续对话，当存在足够的事件时，我们可以执行正常
    的
    （非硬重置）上下文压缩，并且对话状态中两个浓缩都正确反映。
    """

    INSTRUCTION: str = "This test defines its own instructions in run_instructions()."

    def __init__(self, *args, **kwargs):
        """初始化测试并跟踪上下文压缩事件。"""
        self.condensations: list[Condensation] = []
        self.hard_reset_input: list[LLMConvertibleEvent] = []
        self.post_hard_reset_view: list[LLMConvertibleEvent] = []
        self.pre_normal_condensation_view: list[LLMConvertibleEvent] = []
        self.post_normal_condensation_view: list[LLMConvertibleEvent] = []
        super().__init__(*args, **kwargs)

    @property
    def tools(self) -> list[Tool]:
        """提供终端工具。"""
        register_tool("TerminalTool", TerminalTool)
        return [Tool(name="TerminalTool")]

    @property
    def condenser(self) -> LLMSummarizingCondenser:
        """使用 LLMSummarizingCondenser 来启用上下文压缩。"""
        condenser_llm = self.create_llm_copy("test-condenser-llm")
        return LLMSummarizingCondenser(
            llm=condenser_llm,
            max_size=100,  # 高以防止自动触发
            # keep_first=4 protects [system, summary, agent turn, action] so the
            # 下面的正常上下文压缩从观测结果边界开始，保证有效的遗忘范围并将动作/观察对
            # 与较新的历史记录分开。
            #
            # 它还将所需的遗忘开始 (4) 保持在或以上
            # `keep_first` 用于硬重置后视图，因此第二个上下文压缩是 * 正常 * 上下文压缩
            # 。 （当 keep_first=5 时，所需的起始范围将低于 `keep_first`，提高
            # ValueError 并回落到硬重置。）
            #
            keep_first=KEEP_FIRST,
        )

    @property
    def max_iteration_per_run(self) -> int:
        """限制迭代，因为这是一个简单的测试。"""
        return 100

    def conversation_callback(self, event):
        """覆盖回调以检测上下文压缩事件。"""
        super().conversation_callback(event)

        if isinstance(event, Condensation):
            self.condensations.append(event)

    def _assert_finished(self) -> None:
        """如果最后一个 run() 以错误/卡住状态结束，则失败。

        提供程序错误已显示为 ConversationRunError，但达到最大迭代限制只会设置 ERROR
        而不会引发错误，因此请在此处检查。
        """
        status = self.conversation.state.execution_status
        if status != ConversationExecutionStatus.FINISHED:
            raise AssertionError(f"Conversation did not finish cleanly: {status}")

    def run_instructions(self, conversation: LocalConversation) -> None:
        """测试硬重置语义和后续正常上下文压缩。"""
        # 首先执行真正的智能体回合（消息 -> 智能体消息），以便硬重置总结实际回合，而不仅
        # 仅是 [ 系统、用户 ]。 标记让我们断言摘要保留了内容。
        #
        conversation.send_message(
            message=(
                "Reply with a short one-line acknowledgement. Include the exact "
                f"token {HARD_RESET_MARKER} in your reply."
            )
        )
        conversation.run()
        self._assert_finished()

        # 仅具有短暂历史的显式上下文压缩：keep_first 之后不存在有效的遗忘范围，因此必须
        # 回退到硬重置。
        #
        self.hard_reset_input = list(conversation.state.view.events)
        conversation.condense()
        self.post_hard_reset_view = list(conversation.state.view.events)

        # 重置后进行一次真正的工具使用智能体转弯，以便下一个上下文压缩可以使用操作/观察
        # 对。
        #
        conversation.send_message(
            message='Run `echo hello` with the terminal tool, then reply "done".'
        )
        conversation.run()
        self._assert_finished()

        # 添加确定性的、独立于模型的标记事件，以便下一个显式请求始终具有正常上下文压缩的
        # 足够历史记录。
        #
        for index in range(CONTEXT_MARKER_COUNT):
            conversation.send_message(message=f"Context marker {index}.")

        self.pre_normal_condensation_view = list(conversation.state.view.events)
        conversation.condense()
        self.post_normal_condensation_view = list(conversation.state.view.events)

        # 验证正常压缩的对话是否也可以继续。
        conversation.send_message(message='Echo back "hello world".')
        conversation.run()
        self._assert_finished()

    def verify_result(self) -> TestResult:
        """通过两种凝结对活动视图的影响来验证它们。"""
        if len(self.condensations) != 2:
            return TestResult(
                success=False,
                reason=f"Expected 2 condensations, got {len(self.condensations)}",
            )

        hard_reset, normal_condensation = self.condensations

        # 第一个上下文压缩必须是硬重置：它完全忘记非系统历史记录并将其摘要插入到系统提示
        # 词之后。
        #
        system_index = next(
            (
                i
                for i, event in enumerate(self.hard_reset_input)
                if isinstance(event, SystemPromptEvent)
            ),
            None,
        )
        if system_index is None:
            return TestResult(
                success=False,
                reason="Hard-reset input did not contain a system prompt",
            )
        system_event = self.hard_reset_input[system_index]
        expected_forgotten = {
            event.id for event in self.hard_reset_input[system_index + 1 :]
        }
        if hard_reset.forgotten_event_ids != expected_forgotten:
            return TestResult(
                success=False,
                reason=(
                    "First condensation is not a hard reset: it did not forget "
                    "exactly the non-system history"
                ),
            )
        if hard_reset.summary_offset != system_index + 1:
            return TestResult(
                success=False,
                reason=(
                    "Hard reset did not insert the summary right after the system "
                    "prompt"
                ),
            )

        # 内容检查：摘要必须包含所请求的标记，而不仅仅是删除事件。
        #
        if not hard_reset.summary or HARD_RESET_MARKER not in hard_reset.summary:
            return TestResult(
                success=False,
                reason="Hard-reset summary did not retain the requested marker",
            )

        # 生成的视图正是 [ 系统提示词、摘要 ]，并且仍然打开并显示下一个 LLM 请求的系统消
        # 息。
        #
        if [event.id for event in self.post_hard_reset_view] != [
            system_event.id,
            hard_reset.summary_event.id,
        ]:
            return TestResult(
                success=False,
                reason="Hard reset did not preserve system-first summary placement",
            )
        hard_reset_messages = LLMConvertibleEvent.events_to_messages(
            self.post_hard_reset_view
        )
        if not hard_reset_messages or hard_reset_messages[0].role != "system":
            return TestResult(
                success=False,
                reason="Hard-reset view does not produce a system-first LLM request",
            )

        # 第二个上下文压缩必须是正常的（不是另一次硬重置）。
        if (
            normal_condensation.summary_offset is None
            or normal_condensation.summary_offset <= 0
        ):
            return TestResult(
                success=False,
                reason="Second condensation is not a normal condensation "
                "(summary_offset <= 0)",
            )
        if not normal_condensation.forgotten_event_ids:
            return TestResult(
                success=False,
                reason="Normal condensation did not forget any history",
            )

        # 它必须保护重置上下文并忘记在受保护的前缀之后开始的真实中间范围。
        #
        hard_summary_id = hard_reset.summary_event.id
        pre_normal_ids = {event.id for event in self.pre_normal_condensation_view}
        if hard_summary_id not in pre_normal_ids:
            return TestResult(
                success=False,
                reason="Hard-reset summary was missing before normal condensation",
            )
        protected = {system_event.id, hard_summary_id}
        if protected & normal_condensation.forgotten_event_ids:
            return TestResult(
                success=False,
                reason="Normal condensation forgot protected hard-reset context",
            )
        if normal_condensation.summary_offset > len(self.pre_normal_condensation_view):
            return TestResult(
                success=False,
                reason="Normal condensation summary offset is outside the view",
            )

        post_normal_ids = {event.id for event in self.post_normal_condensation_view}
        if not (protected | {normal_condensation.summary_event.id}).issubset(
            post_normal_ids
        ):
            return TestResult(
                success=False,
                reason="Normal condensation did not preserve and extend reset context",
            )

        return TestResult(
            success=True,
            reason=(
                "Hard reset preserved the system prompt, summarized the prior turn "
                "with the marker intact, and supported a later normal condensation."
            ),
        )
