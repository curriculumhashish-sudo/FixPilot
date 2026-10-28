"""
API 合规性测试：重复 tool_call_id

测试不同 LLM APIs 对应的响应，当 tool_result 消息有相同的 tool_call_id 时。


图案：
    [assistant with tool_use id=X] → [tool_result id=X] → ... → [tool_result id=X]
                                                                 ↑ 重复！
"""

from openhands.sdk.llm import Message, MessageToolCall, TextContent
from tests.integration.api_compliance.base import BaseAPIComplianceTest


PATTERN_NAME = "duplicate_tool_call_id"
DESCRIPTION = """
Sends a conversation where two tool_result messages have the same tool_call_id,
meaning multiple results are provided for a single tool_use.

This pattern can occur when:
- Conversation is resumed and duplicate ObservationEvent is created
- Event sync issues during conversation restore
- get_unmatched_actions() incorrectly identifies action as unmatched
"""


class DuplicateToolCallIdTest(BaseAPIComplianceTest):
    """测试 API 对重复 tool_call_id 的响应。"""

    @property
    def pattern_name(self) -> str:
        return PATTERN_NAME

    @property
    def pattern_description(self) -> str:
        return DESCRIPTION

    def build_malformed_messages(self) -> list[Message]:
        """构建具有重复 tool_call_id 的消息序列。"""
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
            # 第一个工具结果（正确）
            Message(
                role="tool",
                content=[TextContent(text="file1.txt\nfile2.txt")],
                tool_call_id="call_abc123",
                name="terminal",
            ),
            # 一些介入消息（模拟对话继续）
            Message(
                role="user",
                content=[TextContent(text="Thanks! Now what?")],
            ),
            Message(
                role="assistant",
                content=[
                    TextContent(
                        text="You're welcome! Let me know if you need anything else."
                    )
                ],
            ),
            Message(
                role="user",
                content=[TextContent(text="Actually, show me the files again.")],
            ),
            # DUPLICATE：带有 SAME tool_call_id 的第二个工具结果
            Message(
                role="tool",
                content=[TextContent(text="file1.txt\nfile2.txt\nfile3.txt")],
                tool_call_id="call_abc123",  # 和之前的ID一样！
                name="terminal",
            ),
        ]
