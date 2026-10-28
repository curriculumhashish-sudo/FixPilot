"""
智能体-SDK 集成测试的基类。
"""

import os
import sys
from abc import ABC, abstractmethod
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from typing import Any, Literal

from pydantic import BaseModel, SecretStr

from openhands.sdk import (
    LLM,
    Agent,
    Message,
    TextContent,
)
from openhands.sdk.context.condenser import CondenserBase
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.visualizer import DefaultConversationVisualizer
from openhands.sdk.event.base import Event
from openhands.sdk.event.llm_convertible import (
    MessageEvent,
)
from openhands.sdk.tool import Tool
from tests.integration.early_stopper import EarlyStopperBase, EarlyStopResult


# 用于选择要使用的文件编辑工具集的工具预设类型
ToolPresetType = Literal["default", "gemini", "gpt5", "planning"]


def get_tools_for_preset(
    preset: ToolPresetType, enable_browser: bool = False
) -> list[Tool]:
    """获取给定预设的工具列表。

    Args:
        preset: 预设要使用的工具（默认、gemini、gpt5 或 Planning）。
        enable_browser: 是否包含浏览器工具。

    Returns:
        给定预设的工具实例列表。
    """
    match preset:
        case "gemini":
            from openhands.tools.preset.gemini import get_gemini_tools

            return get_gemini_tools(enable_browser=enable_browser)
        case "gpt5":
            from openhands.tools.preset.gpt5 import get_gpt5_tools

            return get_gpt5_tools(enable_browser=enable_browser)
        case "planning":
            from openhands.tools.preset.planning import get_planning_tools

            # 规划预设为只读，不支持浏览器工具
            return get_planning_tools()
        case "default":
            from openhands.tools.preset.default import get_default_tools

            return get_default_tools(enable_browser=enable_browser)
        case _:
            raise ValueError(f"Unknown `preset` parameter: {preset}")


class SkipTest(Exception):
    """
    引发异常表明应跳过测试。

    这对于需要特定能力（如 e.g 和 LLMs 的视觉能力）的测试来说很有用，这些能力在所有情
    况下可能都不可用。
    """

    pass


class TestResult(BaseModel):
    """集成测试的结果。"""

    success: bool
    reason: str | None = None
    skipped: bool = False


class BaseIntegrationTest(ABC):
    """
    智能体-SDK 集成测试的基类。

    此类提供了一种结构化方法来编写使用实际 LLM 调用的集成测试。 它处理常见的设置，如
    LLM 配置、临时目录管理和智能体创建。

    与使用运行时的 OpenHands 方法不同，该方法直接使用带有临时目录的工具来进行隔离。

    工具预设通过 tool_preset 构造函数参数传递，以选择要使用的文件编辑工具集（默认、
    gemini、gpt5 或 Planning）。
    """

    INSTRUCTION: str

    def __init__(
        self,
        instruction: str,
        llm_config: dict[str, Any],
        instance_id: str,
        workspace: str,
        tool_preset: ToolPresetType = "default",
    ):
        self.instruction: str = instruction
        self.llm_config: dict[str, Any] = llm_config
        self.workspace: str = workspace
        self.instance_id: str = instance_id
        self.tool_preset: ToolPresetType = tool_preset
        api_key = os.getenv("LLM_API_KEY")
        if not api_key:
            raise ValueError(
                "LLM_API_KEY environment variable not set. Skipping real LLM test."
            )
        base_url = os.getenv("LLM_BASE_URL")
        if not base_url:
            raise ValueError(
                "LLM_BASE_URL environment variable not set. Skipping real LLM test."
            )

        # 使用所有配置参数创建 LLM
        llm_kwargs = {
            **self.llm_config,  # 传递所有配置参数
            "base_url": base_url,
            "api_key": SecretStr(api_key),
        }

        self.llm: LLM = LLM(**llm_kwargs, usage_id="test-llm")
        self.agent: Agent = Agent(
            llm=self.llm, tools=self.tools, condenser=self.condenser
        )
        self.collected_events: list[Event] = []
        self.llm_messages: list[dict[str, Any]] = []

        # 为此测试实例创建日志文件路径
        self.log_file_path: str = os.path.join(
            self.workspace, f"{self.instance_id}_agent_logs.txt"
        )

        # 提前停止支持 - 必须初始化之前 LocalConversation，因为回调可以访问这些属性
        #
        self.early_stopper: EarlyStopperBase | None = None
        self.early_stop_result: EarlyStopResult | None = None

        self.conversation: LocalConversation = LocalConversation(
            agent=self.agent,
            workspace=self.workspace,
            callbacks=[self.conversation_callback],
            visualizer=DefaultConversationVisualizer(),  # 使用默认可视化工具
            max_iteration_per_run=self.max_iteration_per_run,
        )

    def conversation_callback(self, event: Event):
        """回调收集对话事件。"""
        self.collected_events.append(event)
        if isinstance(event, MessageEvent):
            self.llm_messages.append(event.llm_message.model_dump())

        # 检查提前停止条件
        if self.early_stopper and not self.early_stop_result:
            result = self.early_stopper.check(self.collected_events)
            if result.should_stop:
                self.early_stop_result = result
                self.conversation.pause()  # 触发优雅停止

    def run_integration_test(self) -> TestResult:
        """
        通过智能体运行用户指令并验证结果。

        Returns:
            TestResult: 测试结果
        """
        try:
            # 设置
            self.setup()

            # 使用标头初始化日志文件
            with open(self.log_file_path, "w") as f:
                f.write(f"Agent Logs for Test: {self.instance_id}\n")
                f.write("=" * 50 + "\n\n")

            # 在对话期间捕获 stdout 和 stderr
            stdout_buffer = StringIO()
            stderr_buffer = StringIO()

            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                self.run_instructions(self.conversation)

            # 将捕获的输出保存到日志文件
            captured_output = stdout_buffer.getvalue()
            captured_errors = stderr_buffer.getvalue()

            with open(self.log_file_path, "a") as f:
                if captured_output:
                    f.write("STDOUT:\n")
                    f.write(captured_output)
                    f.write("\n")
                if captured_errors:
                    f.write("STDERR:\n")
                    f.write(captured_errors)
                    f.write("\n")

            # 还打印到控制台进行调试
            if captured_output:
                print(captured_output, end="")
            if captured_errors:
                print(captured_errors, file=sys.stderr, end="")

            # 检查是否提前停止 - 跳过完整验证
            if self.early_stop_result:
                return TestResult(
                    success=False,
                    reason=f"Early stopped: {self.early_stop_result.reason}",
                )

            # 验证结果
            result = self.verify_result()

            return result

        except SkipTest:
            # 重新加注 SkipTest，以便测试选手可以接住它
            raise

        except Exception as e:
            return TestResult(success=False, reason=f"Test execution failed: {str(e)}")

        finally:
            self.teardown()

    def run_instructions(self, conversation: LocalConversation) -> None:
        """将用户指令提供给智能体并管理对话。"""
        conversation.send_message(message=self.instruction_message)
        conversation.run()

    @property
    def instruction_message(self) -> Message:
        """初始指令消息为智能体。"""
        return Message(role="user", content=[TextContent(text=self.instruction)])

    @property
    def enable_browser(self) -> bool:
        """是否启用浏览器工具。 在需要浏览的子类中重写。

        Returns:
            默认为 False。 对于需要浏览器访问的测试，覆盖 True。
        """
        return False

    @property
    def tools(self) -> list[Tool]:
        """智能体可用的工具列表。

        默认情况下，使用已配置的工具预设以及由 ``enable_browser`` 属性控制的浏览器支
        持。 这可确保集成测试验证交付生产的相同智能体配置 (GUI
        /CLI)。

        在需要自定义工具配置的子类中重写此属性。
        """
        return get_tools_for_preset(
            self.tool_preset, enable_browser=self.enable_browser
        )

    @property
    def condenser(self) -> CondenserBase | None:
        """智能体可选上下文压缩器。 重写以提供自定义上下文压缩器。

        Returns:
            CondenserBase 实例或 None（默认）
        """
        return None

    @property
    def max_iteration_per_run(self) -> int:
        """每个对话运行的最大迭代次数。 覆盖以设置自定义限制。

        Returns:
            最大迭代次数（默认值：100）
        """
        return 100

    def setup(self) -> None:
        """
        初始化特定于测试的设置。

        此方法应创建测试所需的任何文件、目录或其他资源。
        """
        pass

    def skip_if_model_matches(self, pattern: str | list[str], reason: str) -> None:
        """如果模型名称与给定的 pattern(s) 匹配，则跳过测试。

        提取规范模型名称并检查它是否与任何提供的模式匹配。 如果找到匹配项，则根据给定
        原因引发 SkipTest。

        Args:
            pattern: 要检查的单个模型名称或模型名称列表
            reason: 跳过测试的原因

        Raises:
            SkipTest: 如果模型名称与任何模式匹配
        """
        model_name = self.llm.model
        canonical = self.llm.model_info.get("model") if self.llm.model_info else None
        name = (canonical or model_name or "").split("/")[-1]

        patterns = [pattern] if isinstance(pattern, str) else pattern
        if name in patterns:
            raise SkipTest(reason)

    def create_llm_copy(self, usage_id: str) -> LLM:
        """使用不同的 usage_id 创建测试 LLM 的副本。

        当测试需要多个 LLM 实例用于不同目的（e.g.，上下文压缩器需要一个单独的 LLM）时
        ，这非常有用。

        Args:
            usage_id: LLM 副本的 usage_id（用于指标跟踪）

        Returns:
            具有指定 usage_id 的 self.llm 副本
        """
        return self.llm.model_copy(update={"usage_id": usage_id})

    @abstractmethod
    def verify_result(self) -> TestResult:
        """
        验证测试结果。

        该方法应检查智能体是否成功完成了任务，通过检查 self.temp_dir 中的文件、
        self.events 中的事件或其他验证方法。

        Returns:
            TestResult: 验证结果
        """
        pass

    def add_judge_usage(
        self, prompt_tokens: int, completion_tokens: int, cost: float
    ) -> None:
        """
        将 LLM 判断使用情况添加到对话统计中。

        这确保了评审成本包含在总测试成本中。

        Args:
            prompt_tokens: 法官使用的提示词token个数
            completion_tokens: 法官使用的完成次数token
            cost: 法官通话费用
        """
        from openhands.sdk.llm.utils.metrics import TokenUsage

        # 添加到测试的对话统计信息 LLM
        stats = self.conversation.conversation_stats
        if stats:
            try:
                metrics = stats.get_metrics_for_usage("test-llm")
                # 更新累积指标
                if metrics.accumulated_token_usage:
                    metrics.accumulated_token_usage.prompt_tokens = (
                        metrics.accumulated_token_usage.prompt_tokens or 0
                    ) + prompt_tokens
                    metrics.accumulated_token_usage.completion_tokens = (
                        metrics.accumulated_token_usage.completion_tokens or 0
                    ) + completion_tokens
                else:
                    # 如果不存在则创建新的TokenUsage
                    metrics.accumulated_token_usage = TokenUsage(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )
                metrics.accumulated_cost += cost
            except Exception:
                # 如果统计中尚不存在 test-llm，请跳过
                pass

    def teardown(self):
        """
        清理测试资源。 工作区目录被外部拆除。 如果需要，请在此处添加任何其他清理（git
        、服务器等）。
        """
        # 关闭对话以确保所有工具执行程序（包括浏览器/Chrome 进程）均已关闭。 如果没有这
        # 个，ProcessPoolExecutor 中的工作进程将无限期挂起，因为浏览器的背景线程让它们保
        # 持活动状态。
        #
        self.conversation.close()
