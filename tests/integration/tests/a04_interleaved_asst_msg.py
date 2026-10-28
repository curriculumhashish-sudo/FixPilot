"""
API 合规性测试：交错助理消息

测试不同 LLM APIs 在 tool_use 和 tool_result 之间出现助手消息（没有 tool_calls）时的
响应。

图案：
    [assistant with tool_use] → [assistant message] → [tool_result]
                                 ↑ tool_result之前又一个助手转了！
"""

from openhands.sdk.llm import Message, MessageToolCall, TextContent
from tests.integration.api_compliance.base import BaseAPIComplianceTest


PATTERN_NAME = "interleaved_assistant_message"
DESCRIPTION = """
Sends a conversation where an assistant message (without tool_calls) appears
between a tool_use and its corresponding tool_result.

This pattern might occur in edge cases with:
- Malformed condensation that inserts summary messages incorrectly
- Manual event manipulation
- Corrupted conversation history
"""


class InterleavedAssistantMessageTest(BaseAPIComplianceTest):
    """测试 API 对交错助理消息的响应。"""

    @property
    def pattern_name(self) -> str:
        return PATTERN_NAME

    @property
    def pattern_description(self) -> str:
        return DESCRIPTION

    def build_malformed_messages(self) -> list[Message]:
        """使用交错的辅助消息构建消息序列。"""
        return [
            Message(
                role="system",
                content=[TextContent(text="You are a helpful assistant.")],
            ),
            Message(
                role="user",
                content=[TextContent(text="List the files in the current directory.")],
            ),
            # 第一助理消息 tool_use
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
            # INTERLEAVED：另一条没有tool_calls的助理消息
            Message(
                role="assistant",
                content=[TextContent(text="The command is running...")],
            ),
            # 工具结果来之后交错的辅助消息
            Message(
                role="tool",
                content=[TextContent(text="file1.txt\nfile2.txt")],
                tool_call_id="call_abc123",
                name="terminal",
            ),
        ]
