"""
API 合规性测试：交错的用户消息

测试不同 LLM APIs 在 tool_use 和 tool_result 之间收到用户消息时的行为。


图案：
    [assistant with tool_use] → [user message] → [tool_result]
                                 ↑ 插入到 tool_use 和 tool_result 之间！
"""

from openhands.sdk.llm import Message, MessageToolCall, TextContent
from tests.integration.api_compliance.base import BaseAPIComplianceTest


PATTERN_NAME = "interleaved_user_message"
DESCRIPTION = """
Sends a conversation where a user message appears between a tool_use
(in assistant message) and its corresponding tool_result (tool message).

This pattern can occur when:
- User sends message via send_message() during pending tool execution
- Events are appended to the event list in incorrect order
- Async message delivery causes race conditions
"""


class InterleavedUserMessageTest(BaseAPIComplianceTest):
    """测试 API 对交错用户消息的响应。"""

    @property
    def pattern_name(self) -> str:
        return PATTERN_NAME

    @property
    def pattern_description(self) -> str:
        return DESCRIPTION

    def build_malformed_messages(self) -> list[Message]:
        """使用交错的用户消息构建消息序列。"""
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
            # INTERLEAVED：tool_result之前的用户留言
            Message(
                role="user",
                content=[TextContent(text="Actually, can you also show hidden files?")],
            ),
            # 工具结果来自之后交错的用户消息
            Message(
                role="tool",
                content=[TextContent(text="file1.txt\nfile2.txt")],
                tool_call_id="call_abc123",
                name="terminal",
            ),
        ]
