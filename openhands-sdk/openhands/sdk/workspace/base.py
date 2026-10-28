import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Annotated, Any

import httpx
from pydantic import BeforeValidator, Field, PrivateAttr

from openhands.sdk.conversation.exceptions import ConversationRunError
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.git.models import GitChange, GitDiff
from openhands.sdk.logger import get_logger
from openhands.sdk.observability.laminar import observability_headers_from_env
from openhands.sdk.utils.models import DiscriminatedUnionMixin
from openhands.sdk.workspace.models import CommandResult, FileOperationResult


logger = get_logger(__name__)


def _convert_path_to_str(v: str | Path) -> str:
    """将 Path 对象转换为 working_dir 的字符串。"""
    if isinstance(v, Path):
        return str(v)
    return v


class BaseWorkspace(DiscriminatedUnionMixin, ABC):
    """工作区实现的抽象基类。

    工作区提供沙盒环境，智能体可以在其中执行命令、读/写文件以及执行其他操作。 所有工
    作区实现都支持上下文管理器协议以实现安全资源管理。

    Example:
        ```python
        with workspace:
            result = workspace.execute_command("echo 'hello'")
            content = workspace.read_file("example.txt")
        ```
    """

    working_dir: Annotated[
        str,
        BeforeValidator(_convert_path_to_str),
        Field(
            description=(
                "The working directory for agent operations and tool execution. "
                "Accepts both string paths and Path objects. "
                "Path objects are automatically converted to strings."
            )
        ),
    ]

    _conversation_id: str | None = PrivateAttr(default=None)
    _accumulated_cost: float | None = PrivateAttr(default=None)

    def __enter__(self) -> "BaseWorkspace":
        """输入工作区上下文。

        Returns:
            Self 用于 with 语句
        """
        return self

    def register_cost(self, cost: float) -> None:
        """注册此工作区运行的累积 LLM 成本。

        对话结束后，由对话关闭时调用，因此不需要呼叫者选择加入。 成本包含在发送到自动
        化服务的完成回调中。

        Args:
            cost: USD 中累计 LLM 成本
        """
        self._accumulated_cost = cost
        logger.debug(f"Registered cost: {cost}")

    @property
    def accumulated_cost(self) -> float | None:
        """获取最近注册的累计 LLM 成本。

        Returns:
            如果已注册，则费用在 USD 中，否则在 None 中。
        """
        return self._accumulated_cost

    def _send_completion_callback(
        self, exc_type: type | None, exc_val: BaseException | None
    ) -> None:
        """POST 自动化服务的完成状态（尽力而为）。

        在任何清理之前从 ``__exit__`` 调用它。 当
        ``AUTOMATION_CALLBACK_URL`` 环境变量未设置。

        从环境变量读取配置：
          - ``AUTOMATION_CALLBACK_URL`` — URL 至 POST 完成状态至
          - ``AUTOMATION_CALLBACK_API_KEY`` — 持有者令牌用于回调身份验证（可选）
          - ``AUTOMATION_RUN_ID`` — 要包含在回调载荷中的运行 ID（可选）

        注册时包括``conversation_id``和``cost``。 失败时，
        ``error`` 是 ``ConversationRunError`` 携带的现有结构化
        ``ConversationErrorEvent``，或者是对话
        之外的错误的分类回退方案事件。

        Args:
            exc_type: 如果引发异常则为异常类型，否则为 None
            exc_val: 如果引发异常则为异常值，否则为 None
        """
        callback_url = os.environ.get("AUTOMATION_CALLBACK_URL")
        if not callback_url:
            return

        callback_api_key = os.environ.get("AUTOMATION_CALLBACK_API_KEY")
        run_id = os.environ.get("AUTOMATION_RUN_ID")

        status = "COMPLETED" if exc_type is None else "FAILED"
        payload: dict[str, Any] = {"status": status}
        if run_id:
            payload["run_id"] = run_id
        if exc_val is not None:
            error = (
                exc_val.conversation_error
                if isinstance(exc_val, ConversationRunError)
                else None
            )
            if error is None:
                cause = (
                    exc_val.original_exception
                    if isinstance(exc_val, ConversationRunError)
                    else exc_val
                )
                error = ConversationErrorEvent(
                    source="environment",
                    code=type(cause).__name__,
                    detail=str(cause),
                )
            payload["error"] = error.model_dump(mode="json")

        # 如果已注册，请包含 conversation_id
        if self._conversation_id is not None:
            payload["conversation_id"] = self._conversation_id

        # 如果已注册，则包括累计 LLM 费用
        if self._accumulated_cost is not None:
            payload["cost"] = self._accumulated_cost

        try:
            headers = observability_headers_from_env()
            if callback_api_key:
                headers["Authorization"] = f"Bearer {callback_api_key}"
            with httpx.Client(timeout=10.0) as cb_client:
                resp = cb_client.post(callback_url, json=payload, headers=headers)
                logger.info(f"Completion callback sent ({status}): {resp.status_code}")
        except Exception as e:
            logger.warning(f"Completion callback failed: {e}")

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """退出工作区上下文并清理资源。

        默认实现不执行清理。 子类应该重写以添加清理逻辑（e.g.、停止容器、关闭连接）。

        Args:
            exc_type: 发生异常时的异常类型
            exc_val: 发生异常时的异常值
            exc_tb: 如果发生异常则进行异常回溯
        """
        pass

    @abstractmethod
    def execute_command(
        self,
        command: str,
        cwd: str | Path | None = None,
        timeout: float = 30.0,
    ) -> CommandResult:
        """在系统上执行 bash 命令。

        Args:
            command: 要执行的 bash 命令
            cwd: 工作目录为命令（可选）
            timeout: 超时以秒为单位（默认为 30.0）

        Returns:
            CommandResult: 结果包含 stdout、stderr、exit_code 和其他
                元数据

        Raises:
            Exception: 如果命令执行失败
        """
        ...

    @abstractmethod
    def file_upload(
        self,
        source_path: str | Path,
        destination_path: str | Path,
    ) -> FileOperationResult:
        """将文件上传到系统。

        Args:
            source_path: 源文件的路径
            destination_path: 文件应上传的路径

        Returns:
            FileOperationResult: 包含成功状态和元数据的结果

        Raises:
            Exception: 如果文件上传失败
        """
        ...

    @abstractmethod
    def file_download(
        self,
        source_path: str | Path,
        destination_path: str | Path,
    ) -> FileOperationResult:
        """从系统下载文件。

        Args:
            source_path: 系统上源文件的路径
            destination_path: 文件下载路径

        Returns:
            FileOperationResult: 包含成功状态和元数据的结果

        Raises:
            Exception: 如果文件下载失败
        """
        ...

    @abstractmethod
    def git_changes(self, path: str | Path) -> list[GitChange]:
        """在给定的路径中获取存储库的 git 更改。

        Args:
            path: git 存储库的路径

        Returns:
            list[GitChange]：更改列表

        Raises:
            Exception: 如果路径不是 git 存储库或获取更改失败
        """

    @abstractmethod
    def git_diff(self, path: str | Path) -> GitDiff:
        """获取给定路径中文件的 git diff。

        Args:
            path: 文件路径

        Returns:
            GitDiff: git diff

        Raises:
            Exception: 如果路径不是 git 存储库或获取 diff 失败
        """

    def pause(self) -> None:
        """暂停工作区以节省资源。

        对于本地工作区，这是一个无操作。 对于基于容器的工作区，这会暂停容器。

        Raises:
            NotImplementedError: 如果工作区类型不支持暂停。
        """
        raise NotImplementedError(f"{type(self).__name__} does not support pause()")

    def resume(self) -> None:
        """恢复暂停的工作区。

        对于本地工作区，这是一个无操作。 对于基于容器的工作区，这会恢复容器。

        Raises:
            NotImplementedError: 如果工作区类型不支持断点续传。
        """
        raise NotImplementedError(f"{type(self).__name__} does not support resume()")
