from typing import Literal

from pydantic import BaseModel, Field

from openhands.sdk.llm.message import ImageContent, Message, TextContent


class SendMessageRequest(BaseModel):
    """载荷向智能体发送消息。"""

    role: Literal["user", "system", "assistant", "tool"] = "user"
    content: list[TextContent | ImageContent] = Field(default_factory=list)
    run: bool = Field(
        default=False,
        description="Whether the agent loop should automatically run if not running",
    )

    def create_message(self) -> Message:
        return Message(role=self.role, content=self.content)
