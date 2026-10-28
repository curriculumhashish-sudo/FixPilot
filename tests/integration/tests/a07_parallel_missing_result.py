"""
API 一致性测试：并行工具调用 - 缺少结果

测试不同情况 LLM  APIs 当助手消息包含多个时，响应 tool_calls 但并非所有都对应
tool_results.

图案：
    [assistant with tool_calls [A, B, C]] → [tool_result A] → [tool_result B]
                                                               ^ 缺少 C 的结果！
"""

from openhands.sdk.llm import Message, MessageToolCall, TextContent
from tests.integration.api_compliance.base import BaseAPIComplianceTest


PATTERN_NAME = "parallel_missing_result"
DESCRIPTION = """
Sends a conversation where an assistant message contains multiple parallel
tool_calls, but only some of them have corresponding tool_results.

This pattern can occur when:
- Partial tool execution failure
- Event loss for some observations
- Timeout causes some results to be missing
"""


class ParallelMissingResultTest(BaseAPIComplianceTest):
    """测试 API 对并行工具调用的响应，但缺少结果。"""

    @property
    def pattern_name(self) -> str:
        return PATTERN_NAME

    @property
    def pattern_description(self) -> str:
        return DESCRIPTION

    def build_malformed_messages(self) -> list[Message]:
        """构建缺少结果的并行工具调用的消息序列。"""
        return [
            Message(
                role="system",
                content=[TextContent(text="You are a helpful assistant.")],
            ),
            Message(
                role="user",
                content=[
                    TextContent(
                        text="Get the weather in San Francisco, Tokyo, and Paris."
                    )
                ],
            ),
            # 助理消息与 THREE 并行 tool_calls
            Message(
                role="assistant",
                content=[
                    TextContent(text="I'll check the weather in all three cities.")
                ],
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
                    MessageToolCall(
                        id="call_paris",
                        name="terminal",
                        arguments='{"command": "weather paris"}',
                        origin="completion",
                    ),
                ],
            ),
            # SF 的工具结果 - 提供
            Message(
                role="tool",
                content=[TextContent(text="San Francisco: 65°F, Sunny")],
                tool_call_id="call_sf",
                name="terminal",
            ),
            # 东京的工具结果 - 提供
            Message(
                role="tool",
                content=[TextContent(text="Tokyo: 72°F, Cloudy")],
                tool_call_id="call_tokyo",
                name="terminal",
            ),
            # 注意：巴黎的工具结果是 MISSING！
            # 下一条用户消息在巴黎结果之前到达
            Message(
                role="user",
                content=[TextContent(text="What about Paris?")],
            ),
        ]
