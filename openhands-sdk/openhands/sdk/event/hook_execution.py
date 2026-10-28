"""挂钩执行事件，以便可观察挂钩执行。"""

from typing import Any, Literal

from pydantic import Field
from rich.text import Text

from openhands.sdk.event.base import Event
from openhands.sdk.event.types import EventID, SourceType


HookEventType = Literal[
    "PreToolUse",
    "PostToolUse",
    "UserPromptSubmit",
    "SessionStart",
    "SessionEnd",
    "Stop",
]


class HookExecutionEvent(Event):
    """执行钩子时发出事件。

    此事件提供了对钩子执行的可观察性，包括：
    - 触发了哪种钩子类型
    - 运行的命令
    - 结果（成功/阻塞/错误）
    - 钩子的任何输出

    这允许客户端通过事件流跟踪钩子执行。
    """

    source: SourceType = Field(
        default="hook", description="Source is always 'hook' for hook execution events"
    )

    # 挂钩识别
    hook_event_type: HookEventType = Field(
        ..., description="The type of hook event that triggered this execution"
    )
    hook_command: str = Field(..., description="The hook command that was executed")
    tool_name: str | None = Field(
        default=None,
        description="Tool name for PreToolUse/PostToolUse hooks",
    )

    # 执行结果
    success: bool = Field(..., description="Whether the hook executed successfully")
    blocked: bool = Field(
        default=False,
        description="Whether the hook blocked the operation (exit code 2 or deny)",
    )
    exit_code: int = Field(..., description="Exit code from the hook command")

    # 输出
    stdout: str = Field(default="", description="Standard output from the hook")
    stderr: str = Field(default="", description="Standard error from the hook")
    reason: str | None = Field(
        default=None, description="Reason provided by hook (for blocking)"
    )
    additional_context: str | None = Field(
        default=None,
        description="Additional context injected by hook (e.g., for UserPromptSubmit)",
    )
    error: str | None = Field(
        default=None, description="Error message if hook execution failed"
    )

    # 上下文
    action_id: EventID | None = Field(
        default=None,
        description="ID of the action this hook is associated with (PreToolUse/PostToolUse)",  # noqa: E501
    )
    message_id: EventID | None = Field(
        default=None,
        description="ID of the message this hook is associated with (UserPromptSubmit)",
    )
    hook_input: dict[str, Any] | None = Field(
        default=None,
        description="The input data that was passed to the hook",
    )

    @property
    def visualize(self) -> Text:
        """返回此挂钩执行事件的富文本表示形式。"""
        content = Text()
        content.append("Hook: ", style="bold")
        content.append(f"{self.hook_event_type}")
        if self.tool_name:
            content.append(f" ({self.tool_name})")
        content.append("\n")

        # 状态
        if self.blocked:
            content.append("Status: ", style="bold")
            content.append("BLOCKED", style="bold red")
            if self.reason:
                content.append(f" - {self.reason}")
        elif self.success:
            content.append("Status: ", style="bold")
            content.append("SUCCESS", style="bold green")
        else:
            content.append("Status: ", style="bold")
            content.append("FAILED", style="bold red")
            if self.error:
                content.append(f" - {self.error}")

        content.append(f"\nExit Code: {self.exit_code}")

        # 输出（截断）
        if self.stdout:
            output_preview = self.stdout[:200]
            if len(self.stdout) > 200:
                output_preview += "..."
            content.append(f"\nOutput: {output_preview}")

        if self.additional_context:
            content.append(f"\nInjected Context: {self.additional_context[:100]}...")

        return content

    def __str__(self) -> str:
        """HookExecutionEvent 的纯文本字符串表示形式。"""
        status = (
            "BLOCKED" if self.blocked else ("SUCCESS" if self.success else "FAILED")
        )
        tool_info = f" ({self.tool_name})" if self.tool_name else ""
        return f"HookExecutionEvent: {self.hook_event_type}{tool_info} - {status}"
