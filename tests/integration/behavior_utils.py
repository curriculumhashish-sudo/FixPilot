"""
用于分析集成测试中的智能体行为的实用函数。

这些功能通过分析从对话中收集的事件来帮助验证智能体行为模式和对系统消息的遵守情况。
"""

import fnmatch

from openhands.sdk.event.base import Event
from openhands.sdk.event.llm_convertible.observation import (
    AgentErrorEvent,
    ObservationEvent,
)
from openhands.sdk.event.llm_convertible.system import SystemPromptEvent
from openhands.sdk.utils import maybe_truncate


def find_tool_calls(collected_events: list[Event], tool_name: str) -> list[Event]:
    """
    查找调用特定工具的所有 ActionEvents。

    Args:
        collected_events: 从对话中收集的事件列表
        tool_name: 要搜索的工具名称
            （e.g.、“file_editor”、“终端”）

    Returns:
        与工具名称匹配的 ActionEvents 列表
    """
    from openhands.sdk.event import ActionEvent

    return [
        event
        for event in collected_events
        if isinstance(event, ActionEvent) and event.tool_name == tool_name
    ]


def find_file_editing_operations(collected_events: list[Event]) -> list[Event]:
    """
    查找所有文件编辑操作（创建、str_replace、插入、undo_edit）。

    不包括“查看”等只读操作。

    Args:
        collected_events: 从对话中收集的事件列表

    Returns:
        执行文件编辑的 ActionEvents 列表
    """
    from openhands.sdk.event import ActionEvent
    from openhands.tools.file_editor.definition import FileEditorAction, FileEditorTool

    editing_operations = []
    for event in collected_events:
        if isinstance(event, ActionEvent) and event.tool_name == FileEditorTool.name:
            if event.action is not None:
                assert isinstance(event.action, FileEditorAction)
                # 检查命令是否为编辑操作
                if event.action.command in [
                    "create",
                    "str_replace",
                    "insert",
                    "undo_edit",
                ]:
                    editing_operations.append(event)
    return editing_operations


def find_file_operations(
    collected_events: list[Event], file_pattern: str | None = None
) -> list[Event]:
    """
    查找所有文件操作（读和写）。

    Args:
        collected_events: 从对话中收集的事件列表
        file_pattern: 用于匹配文件路径的可选模式
            (e.g., "*.md", "README")

    Returns:
        执行文件操作的 ActionEvents 列表
    """
    from openhands.sdk.event import ActionEvent
    from openhands.tools.file_editor.definition import FileEditorAction, FileEditorTool

    file_operations = []
    for event in collected_events:
        if isinstance(event, ActionEvent) and event.tool_name == FileEditorTool.name:
            if event.action is not None:
                assert isinstance(event.action, FileEditorAction)
                if file_pattern is None or _matches_pattern(
                    event.action.path, file_pattern
                ):
                    file_operations.append(event)
    return file_operations


def check_bash_command_used(
    collected_events: list[Event], command_pattern: str
) -> list[Event]:
    """
    检查智能体是否使用 bash 命令而不是专用工具。

    Args:
        collected_events: 从对话中收集的事件列表
        command_pattern: 在 bash 命令中搜索的模式（e.g.、“cat”、“sed”）

    Returns:
        ActionEvents 列表，其中 bash 与模式一起使用
    """
    from openhands.sdk.event import ActionEvent
    from openhands.tools.terminal.definition import TerminalAction, TerminalTool

    bash_commands = []
    for event in collected_events:
        if isinstance(event, ActionEvent) and event.tool_name == TerminalTool.name:
            if event.action is not None:
                assert isinstance(event.action, TerminalAction)
                if command_pattern in event.action.command:
                    bash_commands.append(event)
    return bash_commands


def get_conversation_summary(
    collected_events: list[Event], max_observation_chars: int = 2000
) -> str:
    """
    获取对话摘要，包括智能体想法和行动。

    为了防止 LLM 判断中的上下文窗口溢出，大的观测结果被截断以保留输出的开头和结尾。

    Args:
        collected_events: 从对话中收集的事件列表
        max_observation_chars: 观测结果个事件的最大字符数。
            使用头 + 尾截断（默认：2000 = ~1000 头 + ~1000 尾）

    Returns:
        对话的字符串摘要
    """
    summary_parts = []

    # 法官的自定义截断通知上下文（比默认简单）
    judge_truncate_notice = (
        "\n... [Output truncated for brevity - showing head and tail] ...\n"
    )

    for event in collected_events:
        # 跳过（很长）系统提示词，以便法官看到实际的智能体行为
        if isinstance(event, SystemPromptEvent):
            continue

        # 使用事件的可视化属性来获取富文本表示
        visualized = event.visualize
        # 转换为纯文本
        plain_text = visualized.plain.strip()

        if plain_text:
            # 截断大的观测结果以防止上下文溢出保持完整的错误事件，因为它们通常很小且很关
            # 键
            #
            if isinstance(event, ObservationEvent) and not isinstance(
                event, AgentErrorEvent
            ):
                plain_text = maybe_truncate(
                    plain_text,
                    truncate_after=max_observation_chars,
                    truncate_notice=judge_truncate_notice,
                )

            # 添加事件类型标签和内容
            event_type = event.__class__.__name__
            summary_parts.append(f"[{event_type}]\n{plain_text}\n")

    return "\n".join(summary_parts)


def _matches_pattern(path: str, pattern: str) -> bool:
    """将文件路径与模式进行匹配的帮助程序。"""
    return fnmatch.fnmatch(path, pattern) or pattern in path


def verify_all_actions_have_summary(collected_events: list[Event]) -> tuple[bool, str]:
    """
    验证所有 ActionEvents 都有非空汇总字段。

    摘要字段始终添加到工具模式中，并且应由 LLM 或默认值填充。

    Args:
        collected_events: 从对话中收集的事件列表

    Returns:
        (success, Reason) 的元组，其中如果所有操作都有摘要，则 success 为 True，并且
        Reason 解释任何失败
    """
    from openhands.sdk.event import ActionEvent

    action_events = [e for e in collected_events if isinstance(e, ActionEvent)]

    if not action_events:
        return True, "No action events found"

    missing_summaries = []
    for i, event in enumerate(action_events):
        if not event.summary or not event.summary.strip():
            missing_summaries.append(f"Action {i + 1}: {event.tool_name}")

    if missing_summaries:
        return False, f"Actions missing summaries: {', '.join(missing_summaries)}"

    return True, f"All {len(action_events)} actions have summaries"
