"""流式传输 LLM 完成日志的事件从远程智能体发送到客户端。"""

from pydantic import Field

from openhands.sdk.event.base import Event
from openhands.sdk.event.types import SourceType, UnmaskedID


class LLMCompletionLogEvent(Event):
    """包含 LLM 完成日志数据的事件。

    当在远程对话中配置 LLM 为 log_completions=True 时，此事件会通过 WebSocket 而不是
    写入 Docker 容器内的文件来回传完成日志
    数据。
    """

    source: SourceType = "environment"
    filename: str = Field(
        ...,
        description="The intended filename for this log (relative to log directory)",
    )
    log_data: str = Field(
        ...,
        description="The JSON-encoded log data to be written to the file",
    )
    model_name: str = Field(
        default="unknown",
        description="The model name for context",
    )
    usage_id: UnmaskedID = Field(
        default="default",
        description="The LLM usage_id that produced this log",
    )

    def __str__(self) -> str:
        return (
            f"LLMCompletionLog(usage_id={self.usage_id}, model={self.model_name}, "
            f"file={self.filename})"
        )
