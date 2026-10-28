"""
API 合规性测试：无与伦比的 tool_use

测试不同 LLM APIs 对于没有 tool_use 对应的 tool_result 消息的响应。


图案：
    [system] → [user] → [assistant with tool_use] → [user message] → API CALL
                                                     ↑ 没有tool_result！
"""

from openhands.sdk.llm import Message, MessageToolCall, TextContent
from tests.integration.api_compliance.base import BaseAPIComplianceTest


PATTERN_NAME = "unmatched_tool_use"
DESCRIPTION = """
Sends a conversation where an assistant message contains a tool_use (tool_calls),
but no tool_result (tool message) follows before the next user message.

This pattern can occur when:
- ObservationEvent is delayed or lost
- User message arrives before observation is recorded
- Event sync issues during conversation resume
"""


class UnmatchedToolUseTest(BaseAPIComplianceTest):
    """测试 API 对不匹配的 tool_use 的响应。"""

    @property
    def pattern_name(self) -> str:
        return PATTERN_NAME

    @property
    def pattern_description(self) -> str:
        return DESCRIPTION

    def build_malformed_messages(self) -> list[Message]:
        """构建具有不匹配的 tool_use 的消息序列。"""
        return [
            Message(
                role="system",
                content=[TextContent(text="You are a helpful assistant.")],
            ),
            Message(
                role="user",
                content=[TextContent(text="List the files in the current directory.")],
            ),
            # 助理消息 tool_use
            Message(
                role="assistant",
                content=[TextContent(text="I'll list the files for you.")],
                tool_calls=[
                    MessageToolCall(
                        id="call_abc123",
                        name="terminal",
                        arguments='{"command": "ls -la"}',
                        origin="completion",
                    )
                ],
            ),
            # 注意：后面没有tool_result！ 直接另一个用户消息。
            Message(
                role="user",
                content=[TextContent(text="What was the result?")],
            ),
        ]
