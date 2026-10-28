"""提前停止行为测试的实用程序。

该模块提供基于模式的早期停止机制，用于早期检测测试失败并提前终止执行，从而减少 LLM 成
本。
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel

from openhands.sdk.event.base import Event
from openhands.sdk.event.llm_convertible.action import ActionEvent
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


class EarlyStopResult(BaseModel):
    """提前停止检查的结果。"""

    should_stop: bool
    reason: str | None = None


class EarlyStopperBase(ABC):
    """早期停止条件的基类。

    早期停止者监视对话事件，并在检测到明确的故障模式时触发提前终止。 通过避免运行已经
    失败的测试的完整轨迹，可以节省 LLM 成本。
    """

    @abstractmethod
    def check(self, events: list[Event]) -> EarlyStopResult:
        """检查是否应触发提前停止。

        Args:
            events: 迄今为止收集的对话事件列表

        Returns:
            EarlyStopResult表示是否停止以及为什么
        """
        pass


class FileEditPruner(EarlyStopperBase):
    """如果检测到文件编辑操作，请尽早停止。

    对于智能体应该不编辑文件的测试很有用，例如 b01_no_premature_implementation。
    """

    def __init__(self, forbidden_commands: list[str] | None = None):
        """初始化修剪器。

        Args:
            forbidden_commands: 要检测的文件编辑器命令列表。
                默认为 [“创建”、“str_replace”、“插入”、“undo_edit”]
        """
        self.forbidden_commands = forbidden_commands or [
            "create",
            "str_replace",
            "insert",
            "undo_edit",
        ]

    def check(self, events: list[Event]) -> EarlyStopResult:
        """检查是否执行过任何文件编辑操作。"""
        from openhands.tools.file_editor.definition import (
            FileEditorAction,
            FileEditorTool,
        )

        for event in events:
            if (
                isinstance(event, ActionEvent)
                and event.tool_name == FileEditorTool.name
            ):
                if event.action is not None and isinstance(
                    event.action, FileEditorAction
                ):
                    if event.action.command in self.forbidden_commands:
                        return EarlyStopResult(
                            should_stop=True,
                            reason=(
                                f"Detected forbidden file operation: "
                                f"{event.action.command} on {event.action.path}"
                            ),
                        )

        return EarlyStopResult(should_stop=False)


class BashCommandPruner(EarlyStopperBase):
    """如果检测到特定的 bash 命令，请尽早停止。

    对于应避免某些终端操作的测试很有用。
    """

    def __init__(self, forbidden_patterns: list[str]):
        """初始化修剪器。

        Args:
            forbidden_patterns: 要检测的命令模式列表。
                使用子字符串匹配。
        """
        self.forbidden_patterns = forbidden_patterns

    def check(self, events: list[Event]) -> EarlyStopResult:
        """检查是否执行了任何禁止的 bash 命令。"""
        from openhands.tools.terminal.definition import (
            TerminalAction,
            TerminalTool,
        )

        for event in events:
            if isinstance(event, ActionEvent) and event.tool_name == TerminalTool.name:
                if event.action is not None and isinstance(
                    event.action, TerminalAction
                ):
                    command = event.action.command
                    for pattern in self.forbidden_patterns:
                        if pattern in command:
                            return EarlyStopResult(
                                should_stop=True,
                                reason=(
                                    f"Detected forbidden command pattern "
                                    f"'{pattern}' in: {command[:100]}"
                                ),
                            )

        return EarlyStopResult(should_stop=False)


class CompositeEarlyStopper(EarlyStopperBase):
    """结合多个早期塞子。

    如果所包含的停止器中的 ANY 个触发，则停止。
    """

    def __init__(self, stoppers: list[EarlyStopperBase]):
        """使用要组合的停止器列表进行初始化。"""
        self.stoppers = stoppers

    def check(self, events: list[Event]) -> EarlyStopResult:
        """检查所有包含的塞子，如有触发则停止。"""
        for stopper in self.stoppers:
            result = stopper.check(events)
            if result.should_stop:
                return result

        return EarlyStopResult(should_stop=False)
