"""API 合规性测试的基类。"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from pydantic import SecretStr

from openhands.sdk import LLM
from openhands.sdk.llm import Message
from tests.integration.api_compliance.result import APIResponse, ComplianceTestResult


if TYPE_CHECKING:
    from openhands.sdk.tool import ToolDefinition


def get_minimal_tool_definitions() -> "Sequence[ToolDefinition[Any, Any]]":
    """为需要工具调用的测试创建最小的工具定义。"""
    from openhands.sdk.llm import TextContent
    from openhands.sdk.tool import Action, Observation, ToolDefinition

    class ComplianceTestAction(Action):
        """合规性测试的最少操作。"""

        command: str

    class ComplianceTestObservation(Observation):
        """用于合规性测试的最小观测结果。"""

        result: str

        @property
        def to_llm_content(self) -> list[TextContent]:
            return [TextContent(text=self.result)]

    # 直接创建一个最小的ToolDefinition
    class ComplianceTestTool(
        ToolDefinition[ComplianceTestAction, ComplianceTestObservation]
    ):
        """用于 API 合规性测试的最小工具。"""

        @classmethod
        def create(cls, *args: Any, **kwargs: Any) -> "Sequence[ComplianceTestTool]":
            return [
                cls(
                    description="Execute a terminal command",
                    action_type=ComplianceTestAction,
                    observation_type=ComplianceTestObservation,
                )
            ]

    return ComplianceTestTool.create()


class BaseAPIComplianceTest(ABC):
    """API 合规性测试的基类。

    子类必须实现：
    - pattern_name: 模式的唯一标识符
    - pattern_description: 人类可读的描述
    - build_malformed_messages(): 返回表示格式错误的对话的 Message 对象列表

    测试框架将使用不同的 LLM 配置调用 run_test()，以查看每个提供程序如何响应格式错误
    的输入。
    """

    @property
    @abstractmethod
    def pattern_name(self) -> str:
        """正在测试的格式错误模式的唯一标识符。"""
        pass

    @property
    @abstractmethod
    def pattern_description(self) -> str:
        """格式错误的模式的人类可读的描述。"""
        pass

    @abstractmethod
    def build_malformed_messages(self) -> list[Message]:
        """构造格式错误的消息序列以发送到 API。

        Returns:
            表示格式错误的对话的 Message 对象列表。
        """
        pass

    def needs_tools(self) -> bool:
        """该测试是否需要将工具定义发送到API。

        如果测试不需要工具，则重写返回 False。 大多数涉及 tool_use/tool_result 的测试
        都需要定义工具。
        """
        return True

    def get_tool_definitions(self) -> "Sequence[ToolDefinition[Any, Any]]":
        """获取与请求一起发送的工具定义。

        覆盖以自定义工具定义。
        """
        return get_minimal_tool_definitions()

    def run_test(
        self,
        llm: LLM,
        model_id: str,
    ) -> ComplianceTestResult:
        """针对给定的 LLM 执行测试并记录结果。

        Args:
            llm: LLM 要测试的实例
            model_id: 用于显示的短型号标识符

        Returns:
            ComplianceTestResult 与结果
        """
        messages = self.build_malformed_messages()
        provider = self._extract_provider(llm.model)

        tools = self.get_tool_definitions() if self.needs_tools() else None

        try:
            response = llm.completion(
                messages=messages,
                tools=tools,
            )
            # 如果我们到达这里，API 接受了格式错误的输入
            return ComplianceTestResult(
                pattern_name=self.pattern_name,
                model=llm.model,
                model_id=model_id,
                provider=provider,
                response_type=APIResponse.ACCEPTED,
                raw_response=response.raw_response.model_dump()
                if response.raw_response
                else None,
                notes="API accepted malformed input (unexpected)",
            )
        except TimeoutError as e:
            return ComplianceTestResult(
                pattern_name=self.pattern_name,
                model=llm.model,
                model_id=model_id,
                provider=provider,
                response_type=APIResponse.TIMEOUT,
                error_message=str(e),
                error_type=type(e).__name__,
            )
        except ConnectionError as e:
            return ComplianceTestResult(
                pattern_name=self.pattern_name,
                model=llm.model,
                model_id=model_id,
                provider=provider,
                response_type=APIResponse.CONNECTION_ERROR,
                error_message=str(e),
                error_type=type(e).__name__,
            )
        except Exception as e:
            # 提取 HTTP 状态（如果有）
            http_status = None
            error_str = str(e)
            # 检查 status_code 属性（常见于 HTTP 异常）
            status_code_attr = getattr(e, "status_code", None)
            if isinstance(status_code_attr, int):
                http_status = status_code_attr
            elif "status_code" in error_str:
                # 尝试从错误消息中解析
                import re

                match = re.search(r"status_code[=:\s]*(\d+)", error_str)
                if match:
                    http_status = int(match.group(1))

            return ComplianceTestResult(
                pattern_name=self.pattern_name,
                model=llm.model,
                model_id=model_id,
                provider=provider,
                response_type=APIResponse.REJECTED,
                error_message=str(e),
                error_type=type(e).__name__,
                http_status=http_status,
            )

    def _extract_provider(self, model: str) -> str:
        """从模型字符串中提取提供者名称。"""
        model_lower = model.lower()
        if "claude" in model_lower or "anthropic" in model_lower:
            return "anthropic"
        elif "gpt" in model_lower or "openai" in model_lower:
            return "openai"
        elif "gemini" in model_lower or "google" in model_lower:
            return "google"
        elif "deepseek" in model_lower:
            return "deepseek"
        elif "kimi" in model_lower or "moonshot" in model_lower:
            return "moonshot"
        elif "qwen" in model_lower or "dashscope" in model_lower:
            return "alibaba"
        elif "glm" in model_lower:
            return "zhipu"
        elif "minimax" in model_lower:
            return "minimax"
        else:
            # 返回模型名称的第一部分
            return model.split("/")[0] if "/" in model else "unknown"


def create_test_llm(llm_config: dict[str, Any]) -> LLM:
    """创建一个 LLM 实例以进行合规性测试。

    Args:
        llm_config: LLM 配置字典（型号、温度等）

    Returns:
        Configured LLM instance
    """
    import os

    api_key = os.environ.get("LLM_API_KEY")
    base_url = os.environ.get("LLM_BASE_URL")

    if not api_key:
        raise ValueError("LLM_API_KEY environment variable not set")

    return LLM(
        **llm_config,
        api_key=SecretStr(api_key),
        base_url=base_url,
        timeout=60,  # 短超时用于合规性测试
        num_retries=0,  # 否重试 - 我们想查看原始错误
        # 禁用某些型号上可能导致参数错误的功能
        prompt_cache_retention=None,
        caching_prompt=False,
    )
