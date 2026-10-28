"""
API 合规性测试：无与伦比的 tool_result

测试不同 LLM APIs 对于一个 tool_result 消息引用不存在于任何先前 tool_call_id 的
tool_use 的响应如何。

图案：
    [system] → [user] → [assistant (no tool_use)] → [tool with unknown id]
                                                     ↑ 引用的 ID 不存在！
"""

from openhands.sdk.llm import Message, TextContent
from tests.integration.api_compliance.base import BaseAPIComplianceTest


PATTERN_NAME = "unmatched_tool_result"
DESCRIPTION = """
Sends a conversation where a tool_result message references a tool_call_id
that doesn't exist in any prior assistant message's tool_calls.

This pattern can occur when:
- tool_call_id is corrupted during serialization
- Tool results are sent for the wrong conversation
- Event ordering issues cause mismatched IDs
"""


class UnmatchedToolResultTest(BaseAPIComplianceTest):
    """测试 API 对不匹配的 tool_result 的响应。"""

    @property
    def pattern_name(self) -> str:
        return PATTERN_NAME

    @property
    def pattern_description(self) -> str:
        return DESCRIPTION

    def build_malformed_messages(self) -> list[Message]:
        """构建具有不匹配的 tool_result 的消息序列。"""
        return [
            Message(
                role="system",
                content=[TextContent(text="You are a helpful assistant.")],
            ),
            Message(
                role="user",
                content=[TextContent(text="List the files in the current directory.")],
            ),
            # 助理消息 WITHOUT tool_use
            Message(
                role="assistant",
                content=[
                    TextContent(text="I can help you list files. What directory?")
                ],
            ),
            # 引用不存在的 tool_call_id 的工具结果
            Message(
                role="tool",
                content=[TextContent(text="file1.txt\nfile2.txt\nfile3.txt")],
                tool_call_id="call_nonexistent_xyz",
                name="terminal",
            ),
        ]
