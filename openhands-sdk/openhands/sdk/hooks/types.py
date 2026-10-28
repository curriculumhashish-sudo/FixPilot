"""挂钩事件类型和数据结构。"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class HookEventType(str, Enum):
    """可以触发钩子的钩子事件类型。"""

    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    STOP = "Stop"


class HookEvent(BaseModel):
    """通过 stdin 作为 JSON 传递到挂钩脚本的数据。"""

    event_type: HookEventType
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_response: dict[str, Any] | None = None
    message: str | None = None
    session_id: str | None = None
    working_dir: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"use_enum_values": True}


class HookDecision(str, Enum):
    """钩子可以对操作做出的决定。"""

    ALLOW = "allow"
    DENY = "deny"
    # ASK = "ask"  # 未来：提示词在继续之前需要用户确认
