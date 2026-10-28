"""
API 合规性测试：错误 tool_call_id

测试不同情况 LLM  APIs 当  tool_result 引用了错误的内容 tool_call_id （已与另一个端点
交换过） tool_use(ID)

图案：
    [assistant with tool_use id=A] → [assistant with tool_use id=B] →
    [tool_result id=B] → [tool_result id=A]  ← IDs swapped!
"""

from openhands.sdk.llm import Message, MessageToolCall, TextContent
from tests.integration.api_compliance.base import BaseAPIComplianceTest


PATTERN_NAME = "wrong_tool_call_id"
DESCRIPTION = """
Sends a conversation where tool_results are provided but with swapped IDs,
so each tool_result references the wrong tool_use.

This pattern might occur with:
- ID corruption during serialization
- Race conditions in parallel tool execution
- Manual event manipulation errors
"""


class WrongToolCallIdTest(BaseAPIComplianceTest):
    """测试 API 响应到错误/交换 tool_call_id。"""

    @property
    def pattern_name(self) -> str:
        return PATTERN_NAME

    @property
    def pattern_description(self) -> str:
        return DESCRIPTION

    def build_malformed_messages(self) -> list[Message]:
        """使用交换的 tool_call_ids 构建消息序列。"""
        return [
            Message(
                role="system",
                content=[TextContent(text="You are a helpful assistant.")],
            ),
            Message(
                role="user",
                content=[TextContent(text="Run two commands: ls and pwd")],
            ),
            # 第一个助理消息 tool_use (id=A)
            Message(
                role="assistant",
                content=[TextContent(text="I'll run ls first.")],
                tool_calls=[
                    MessageToolCall(
                        id="call_A_ls",
                        name="terminal",
                        arguments='{"command": "ls"}',
                        origin="completion",
                    )
                ],
            ),
            # 第一个工具结果 - CORRECT
            Message(
                role="tool",
                content=[TextContent(text="file1.txt\nfile2.txt")],
                tool_call_id="call_A_ls",
                name="terminal",
            ),
            # 第二条助理消息 tool_use (id=B)
            Message(
                role="assistant",
                content=[TextContent(text="Now I'll run pwd.")],
                tool_calls=[
                    MessageToolCall(
                        id="call_B_pwd",
                        name="terminal",
                        arguments='{"command": "pwd"}',
                        origin="completion",
                    )
                ],
            ),
            # 第二个工具结果 - WRONG ID（引用第一个 tool_use）
            Message(
                role="tool",
                content=[TextContent(text="/home/user/project")],
                tool_call_id="call_A_ls",  # 错了！ 应该是call_B_pwd
                name="terminal",
            ),
        ]
