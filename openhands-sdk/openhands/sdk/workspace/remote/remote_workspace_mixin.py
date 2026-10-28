import logging
import time
from collections.abc import Generator
from pathlib import Path, PureWindowsPath
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, Field, TypeAdapter

from openhands.sdk.git.models import GitChange, GitDiff
from openhands.sdk.observability.laminar import observability_headers_from_env
from openhands.sdk.utils.path import to_posix_path
from openhands.sdk.workspace.models import CommandResult, FileOperationResult


_logger = logging.getLogger(__name__)


def _remote_path(path: str | Path) -> str:
    return to_posix_path(path)


def _join_remote_path(base: str | Path, path: str | Path) -> str:
    path_str = _remote_path(path)
    if path_str.startswith("/") or PureWindowsPath(path_str).is_absolute():
        return path_str

    base_str = _remote_path(base)
    prefix = "/" if base_str.startswith("/") else ""
    base_parts = [part for part in base_str.split("/") if part]
    path_parts = [part for part in path_str.split("/") if part]
    return prefix + "/".join(base_parts + path_parts)


class RemoteWorkspaceMixin(BaseModel):
    """Mixin 提供远程工作区操作。
    这允许将相同的代码用于同步和异步。"""

    host: str = Field(description="The remote host URL for the workspace.")
    api_key: str | None = Field(
        default=None, description="API key for authenticating with the remote host."
    )
    working_dir: str = Field(
        description="The working directory for agent operations and tool execution."
    )
    read_timeout: float = Field(
        default=600.0,
        description="Timeout in seconds for reading operations of httpx.Client.",
    )
    max_connections: int | None = Field(
        default=None,
        description="Maximum number of connections for httpx.Client. "
        "None means no limit, useful for running many conversations in parallel.",
    )

    runtime_conversation_id: UUID | None = Field(
        default=None,
        frozen=True,
        description="Conversation runtime scope; None uses the host workspace.",
    )

    @property
    def api_prefix(self) -> str:
        """文件、命令和 Git 操作使用的不可变运行时范围。"""
        if self.runtime_conversation_id is None:
            return "/api"
        return f"/api/conversations/{self.runtime_conversation_id}"

    def model_post_init(self, context: Any) -> None:
        # 设置远程主机
        self.host = self.host.rstrip("/")
        return super().model_post_init(context)

    @property
    def _headers(self):
        headers = observability_headers_from_env()
        if self.api_key:
            headers["X-Session-API-Key"] = self.api_key
        return headers

    def _start_command_generator(
        self,
        command: str,
        cwd: str | Path | None,
        timeout: float,
    ) -> Generator[dict[str, Any], httpx.Response, str]:
        payload: dict[str, Any] = {"command": command, "timeout": int(timeout)}
        if cwd is not None:
            payload["cwd"] = _remote_path(cwd)
        response = yield {
            "method": "POST",
            "url": f"{self.host}{self.api_prefix}/bash/start_bash_command",
            "json": payload,
            "headers": self._headers,
            "timeout": timeout + 5,
        }
        response.raise_for_status()
        command_id = response.json().get("id")
        if not isinstance(command_id, str) or not command_id:
            raise ValueError("Agent Server returned no background command ID")
        return command_id

    def _search_command_output_generator(
        self,
        command_id: str | None,
        *,
        after_order: int | None = None,
        timeout: float = 60,
    ) -> Generator[dict[str, Any], httpx.Response, dict[str, Any]]:
        params: dict[str, str | int] = {
            "kind__eq": "BashOutput",
            "sort_order": "TIMESTAMP_DESC" if after_order is None else "TIMESTAMP",
            "limit": 1 if after_order is None else 100,
        }
        if command_id is not None:
            params["command_id__eq"] = command_id
        if after_order is not None and after_order >= 0:
            params["order__gt"] = after_order
        response = yield {
            "method": "GET",
            "url": f"{self.host}{self.api_prefix}/bash/bash_events/search",
            "params": params,
            "headers": self._headers,
            "timeout": timeout,
        }
        response.raise_for_status()
        return response.json()

    def _get_command_output_generator(
        self,
        command_id: str | None,
    ) -> Generator[dict[str, Any], httpx.Response, dict[str, Any] | None]:
        page = yield from self._search_command_output_generator(command_id)
        return next(iter(page.get("items", [])), None)

    def _stop_command_generator(
        self,
        command_id: str,
    ) -> Generator[dict[str, Any], httpx.Response]:
        response = yield {
            "method": "POST",
            "url": f"{self.host}{self.api_prefix}/bash/bash_commands/{command_id}/stop",
            "headers": self._headers,
            "timeout": 60,
        }
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return None

    def _runtime_lifecycle_generator(
        self,
        *,
        release: bool,
    ) -> Generator[dict[str, Any], httpx.Response, str | None]:
        if self.runtime_conversation_id is None:
            raise ValueError("Runtime lifecycle requires a conversation scope")
        response = yield {
            "method": "DELETE" if release else "POST",
            "url": f"{self.host}{self.api_prefix}/runtime"
            + ("" if release else "/credentials"),
            "headers": self._headers,
            "timeout": 60,
        }
        if release and response.status_code == 404:
            return None
        response.raise_for_status()
        if not release:
            key = response.json().get("session_api_key")
            if not isinstance(key, str) or not key:
                raise ValueError("Runtime returned an empty session credential")
            return key
        return None

    def _execute_command_generator(
        self,
        command: str,
        cwd: str | Path | None,
        timeout: float,
    ) -> Generator[dict[str, Any], httpx.Response, CommandResult]:
        """在远程系统上执行 bash 命令。

        此方法通过远程 Agent Server API 启动 bash 命令，然后轮询输出，直到命令完成。

        Args:
            command: 要执行的 bash 命令
            cwd: 工作目录（可选）
            timeout: 超时以秒为单位

        Returns:
            CommandResult: 包含 stdout、stderr、exit_code 和其他元数据的结果
        """
        _logger.debug("Executing remote command")

        try:
            command_id = yield from self._start_command_generator(command, cwd, timeout)

            _logger.debug(f"Started command with ID: {command_id}")

            # 第 2 步：轮询输出，直到命令完成
            start_time = time.time()
            stdout_parts = []
            stderr_parts = []
            exit_code = None
            last_order = -1  # 跟踪所见的最高顺序以仅获取新事件
            seen_event_ids: set[str] = set()  # 跟踪看到的 ID 以检测重复项

            while time.time() - start_time < timeout:
                search_result = yield from self._search_command_output_generator(
                    command_id,
                    after_order=last_order,
                    timeout=timeout,
                )

                # 处理 BashOutput 个事件
                for event in search_result.get("items", []):
                    if event.get("kind") == "BashOutput":
                        # 检查重复项 - 安全检查，以防调用者忘记添加 kind__eq 过滤器或
                        # API 有错误
                        #
                        event_id = event.get("id")
                        if event_id is not None:
                            if event_id in seen_event_ids:
                                raise RuntimeError(
                                    f"Duplicate event received: {event_id}. "
                                    "This should not happen with order__gt "
                                    "filtering and kind filtering."
                                )
                            seen_event_ids.add(event_id)

                        # 追踪我们见过的最高订单
                        event_order = event.get("order")
                        if event_order is not None and event_order > last_order:
                            last_order = event_order

                        if event.get("stdout"):
                            stdout_parts.append(event["stdout"])
                        if event.get("stderr"):
                            stderr_parts.append(event["stderr"])
                        if event.get("exit_code") is not None:
                            exit_code = event["exit_code"]

                # 如果我们有退出代码，则命令完成
                if exit_code is not None:
                    break

                # 请稍等一下，然后再次轮询
                time.sleep(0.1)

            # 如果我们等待完成超时
            if exit_code is None:
                _logger.warning(
                    "Command timed out after %s seconds (command_id=%s)",
                    timeout,
                    command_id,
                )
                exit_code = -1
                stderr_parts.append(f"Command timed out after {timeout} seconds")

            # 合并所有输出部分
            stdout = "".join(stdout_parts)
            stderr = "".join(stderr_parts)

            return CommandResult(
                command=command,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                timeout_occurred=exit_code == -1 and "timed out" in stderr,
            )

        except Exception as e:
            _logger.error(
                "Remote command execution failed (error_type=%s)",
                type(e).__name__,
            )
            return CommandResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=f"Remote execution error: {str(e)}",
                timeout_occurred=False,
            )

    def _file_upload_generator(
        self,
        source_path: str | Path | bytes,
        destination_path: str | Path,
    ) -> Generator[dict[str, Any], httpx.Response, FileOperationResult]:
        """将文件上传到远程系统。

        读取本地文件并通过HTTPAPI发送到远程系统。

        Args:
            source_path: 本地源文件的路径
            destination_path: 文件应上传到远程系统的路径

        Returns:
            FileOperationResult: 包含成功状态和元数据的结果
        """
        source = Path("upload") if isinstance(source_path, bytes) else Path(source_path)
        destination = Path(destination_path)
        destination_remote = _remote_path(destination_path)

        _logger.debug(f"Remote file upload: {source} -> {destination}")

        try:
            # 读取文件内容
            if isinstance(source_path, bytes):
                file_content = source_path
            else:
                with open(source, "rb") as f:
                    file_content = f.read()

            # 准备上传
            files = {"file": (source.name, file_content)}

            # 使用路径的查询参数进行 HTTP 调用
            response: httpx.Response = yield {
                "method": "POST",
                "url": f"{self.host}{self.api_prefix}/file/upload",
                "params": {"path": destination_remote},
                "files": files,
                "headers": self._headers,
                "timeout": 60.0,
            }
            response.raise_for_status()
            result_data = response.json()

            # 将 API 响应转换为我们的模型
            return FileOperationResult(
                success=result_data.get("success", True),
                source_path=str(source),
                destination_path=destination_remote,
                file_size=result_data.get("file_size"),
                error=result_data.get("error"),
            )

        except Exception as e:
            _logger.error(f"Remote file upload failed: {e}")
            return FileOperationResult(
                success=False,
                source_path=str(source),
                destination_path=destination_remote,
                error=str(e),
            )

    def _file_download_generator(
        self,
        source_path: str | Path,
        destination_path: str | Path,
    ) -> Generator[dict[str, Any], httpx.Response, FileOperationResult]:
        """从远程系统下载文件。

        通过HTTPAPI从远程系统请求文件并将其保存在本地。

        Args:
            source_path: 远程系统上源文件的路径
            destination_path: 文件应保存在本地的路径

        Returns:
            FileOperationResult: 包含成功状态和元数据的结果
        """
        source = Path(source_path)
        destination = Path(destination_path)
        source_remote = _remote_path(source_path)

        _logger.debug(f"Remote file download: {source} -> {destination}")

        try:
            # 使用路径的查询参数进行 HTTP 调用
            response = yield {
                "method": "GET",
                "url": f"{self.api_prefix}/file/download",
                "params": {"path": source_remote},
                "headers": self._headers,
                "timeout": 60.0,
            }
            response.raise_for_status()

            # 确保目标目录存在
            destination.parent.mkdir(parents=True, exist_ok=True)

            # 写入文件内容
            with open(destination, "wb") as f:
                f.write(response.content)

            return FileOperationResult(
                success=True,
                source_path=source_remote,
                destination_path=str(destination),
                file_size=len(response.content),
            )

        except Exception as e:
            _logger.error(f"Remote file download failed: {e}")
            return FileOperationResult(
                success=False,
                source_path=source_remote,
                destination_path=str(destination),
                error=str(e),
            )

    def _git_changes_generator(
        self,
        path: str | Path,
    ) -> Generator[dict[str, Any], httpx.Response, list[GitChange]]:
        """在给定的路径中获取存储库的 git 更改。

        Args:
            path: git 存储库的路径

        Returns:
            list[GitChange]：更改列表

        Raises:
            Exception: 如果路径不是 git 存储库或获取更改失败
        """
        remote_path = _join_remote_path(self.working_dir, path)
        response = yield {
            "method": "GET",
            "url": f"{self.api_prefix}/git/changes",
            "params": {"path": remote_path},
            "headers": self._headers,
            "timeout": 60.0,
        }
        response.raise_for_status()
        type_adapter = TypeAdapter(list[GitChange])
        changes = type_adapter.validate_python(response.json())
        return changes

    def _git_diff_generator(
        self,
        path: str | Path,
    ) -> Generator[dict[str, Any], httpx.Response, GitDiff]:
        """获取给定路径中文件的 git diff。

        Args:
            path: 文件路径

        Returns:
            GitDiff: git diff

        Raises:
            Exception: 如果路径不是 git 存储库或获取 diff 失败
        """
        remote_path = _join_remote_path(self.working_dir, path)
        response = yield {
            "method": "GET",
            "url": f"{self.api_prefix}/git/diff",
            "params": {"path": remote_path},
            "headers": self._headers,
            "timeout": 60.0,
        }
        response.raise_for_status()
        diff = GitDiff.model_validate(response.json())
        return diff
