"""
API 一致性测试：并行工具调用 - 错误顺序

测试不同 LLM APIs 对应 tool_results 出现之前副作用助手消息 tool_calls 的反应。

图案：
    [tool_result A] → [tool_result B] → [assistant with tool_calls [A, B]]
    ↑ tool_calls之前的结果！
"""

from openhands.sdk.llm import Message, MessageToolCall, TextContent
from tests.integration.api_compliance.base import BaseAPIComplianceTest


PATTERN_NAME = "parallel_wrong_order"
DESCRIPTION = """
Sends a conversation where tool_results appear before the assistant message
that contains the corresponding tool_calls. This is a severe ordering violation.

This pattern might occur with:
- Severe event ordering bugs
- Manual conversation manipulation
- Corrupted event stream
"""


class ParallelWrongOrderTest(BaseAPIComplianceTest):
    """测试 API 对工具调用之前出现的工具结果的响应。"""

    @property
    def pattern_name(self) -> str:
        return PATTERN_NAME

    @property
    def pattern_description(self) -> str:
        return DESCRIPTION

    def build_malformed_messages(self) -> list[Message]:
        """使用工具调用之前的工具结果构建消息序列。"""
        return [
            Message(
                role="system",
                content=[TextContent(text="You are a helpful assistant.")],
            ),
            Message(
                role="user",
                content=[TextContent(text="Check the weather in SF and Tokyo.")],
            ),
            # 工具结果显示 FIRST（错误！）
            Message(
                role="tool",
                content=[TextContent(text="San Francisco: 65°F, Sunny")],
                tool_call_id="call_sf",
                name="terminal",
            ),
            Message(
                role="tool",
                content=[TextContent(text="Tokyo: 72°F, Cloudy")],
                tool_call_id="call_tokyo",
                name="terminal",
            ),
            # 带有 tool_calls 的助理消息来自之后 tool_results
            Message(
                role="assistant",
                content=[TextContent(text="I'll check both cities.")],
                tool_calls=[
                    MessageToolCall(
                        id="call_sf",
                        name="terminal",
                        arguments='{"command": "weather sf"}',
                        origin="completion",
                    ),
                    MessageToolCall(
                        id="call_tokyo",
                        name="terminal",
                        arguments='{"command": "weather tokyo"}',
                        origin="completion",
                    ),
                ],
            ),
        ]
