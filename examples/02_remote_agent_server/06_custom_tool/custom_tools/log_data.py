"""日志数据工具 - 用于将结构化数据记录到 JSON 的示例自定义工具。

该工具演示了如何创建一个自定义工具，在智能体执行期间将结构化数据记录到本地 JSON 文件
。 智能体完成后可以检索和验证数据。
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field

from openhands.sdk import (
    Action,
    ImageContent,
    Observation,
    TextContent,
    ToolDefinition,
)
from openhands.sdk.tool import ToolExecutor, register_tool


# --- 枚举和型号 ---


class LogLevel(StrEnum):
    """条目的日志级别。"""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class LogDataAction(Action):
    """将结构化数据记录到 JSON 文件的操作。"""

    message: str = Field(description="The log message")
    level: LogLevel = Field(
        default=LogLevel.INFO,
        description="Log level (debug, info, warning, error)",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured data to include in the log entry",
    )


class LogDataObservation(Observation):
    """观测结果记录数据后返回。"""

    success: bool = Field(description="Whether the data was successfully logged")
    log_file: str = Field(description="Path to the log file")
    entry_count: int = Field(description="Total number of entries in the log file")

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        """将观测结果内容转换为 LLM 内容。"""
        if self.success:
            return [
                TextContent(
                    text=(
                        f"✅ Data logged successfully to {self.log_file}\n"
                        f"Total entries: {self.entry_count}"
                    )
                )
            ]
        return [TextContent(text="❌ Failed to log data")]


# ---执行者---

# 默认日志文件路径
DEFAULT_LOG_FILE = "/tmp/agent_data.json"


class LogDataExecutor(ToolExecutor[LogDataAction, LogDataObservation]):
    """将结构化数据记录到 JSON 文件的执行器。"""

    def __init__(self, log_file: str = DEFAULT_LOG_FILE):
        """初始化日志数据执行器。

        Args:
            log_file: JSON 日志文件的路径
        """
        self.log_file = Path(log_file)

    def __call__(
        self,
        action: LogDataAction,
        conversation=None,  # noqa: ARG002
    ) -> LogDataObservation:
        """执行记录数据操作。

        Args:
            action: 记录数据操作
            conversation: 可选对话上下文（未使用）

        Returns:
            LogDataObservation 结果
        """
        # 加载现有条目或重新开始
        entries: list[dict[str, Any]] = []
        if self.log_file.exists():
            try:
                with open(self.log_file) as f:
                    entries = json.load(f)
            except (json.JSONDecodeError, OSError):
                entries = []

        # 创建带有时间戳的新条目
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": action.level.value,
            "message": action.message,
            "data": action.data,
        }
        entries.append(entry)

        # 写入文件
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, "w") as f:
            json.dump(entries, f, indent=2)

        return LogDataObservation(
            success=True,
            log_file=str(self.log_file),
            entry_count=len(entries),
        )


# --- 工具定义 ---

_LOG_DATA_DESCRIPTION = """Log structured data to a JSON file.

Use this tool to record information, findings, or events during your work.
Each log entry includes a timestamp and can contain arbitrary structured data.

Parameters:
* message: A descriptive message for the log entry
* level: Log level - one of 'debug', 'info', 'warning', 'error' (default: info)
* data: Optional dictionary of additional structured data to include

Example usage:
- Log a finding: message="Found potential issue", level="warning", data={"file": "app.py", "line": 42}
- Log progress: message="Completed analysis", level="info", data={"files_checked": 10}
"""  # noqa: E501


class LogDataTool(ToolDefinition[LogDataAction, LogDataObservation]):
    """用于将结构化数据记录到 JSON 文件的工具。"""

    @classmethod
    def create(cls, conv_state, **params) -> Sequence[ToolDefinition]:  # noqa: ARG003
        """创建 LogDataTool 实例。

        Args:
            conv_state: 对话状态（本例中未使用）
            **params: 附加参数：
                - log_file: JSON 日志文件的路径（默认值：/tmp/agent_data.json)

        Returns:
            包含单个 LogDataTool 实例的序列
        """
        log_file = params.get("log_file", DEFAULT_LOG_FILE)
        executor = LogDataExecutor(log_file=log_file)

        return [
            cls(
                description=_LOG_DATA_DESCRIPTION,
                action_type=LogDataAction,
                observation_type=LogDataObservation,
                executor=executor,
            )
        ]


# 导入此模块时自动注册工具这就是在远程 Agent Server 中启用动态工具注册的原因
#
register_tool("LogDataTool", LogDataTool)
