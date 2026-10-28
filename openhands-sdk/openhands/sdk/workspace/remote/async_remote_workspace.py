from collections.abc import Generator
from pathlib import Path
from types import TracebackType
from typing import Any, Self
from urllib.request import urlopen

import httpx
from pydantic import PrivateAttr

from openhands.sdk.git.models import GitChange, GitDiff
from openhands.sdk.workspace.models import CommandResult, FileOperationResult
from openhands.sdk.workspace.remote.remote_workspace_mixin import RemoteWorkspaceMixin


class AsyncRemoteWorkspace(RemoteWorkspaceMixin):
    """异步远程工作区实施。"""

    _client: httpx.AsyncClient | None = PrivateAttr(default=None)

    async def __aenter__(self) -> Self:
        """输入工作区，其 HTTP 池在上下文退出时关闭。"""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """关闭客户端而不释放服务器的运行时。"""
        await self.reset_client()

    async def get_server_info(self) -> dict[str, Any]:
        """返回服务器元数据，匹配 RemoteWorkspace.get_server_info。"""
        response = await self.client.get("/server_info")
        response.raise_for_status()
        return response.json()

    async def reset_client(self) -> None:
        """重置 HTTP 客户端以强制重新初始化。

        当连接参数（主机，api_key）发生更改并且需要使用新值重新创建客户端时，这非常有
        用。
        """
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
        self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        client = self._client
        if client is None:
            # 为HTTP个请求配置合理的超时
            # - 连接：10秒建立连接
            # - 读取：60 秒读取响应（对于 LLM 操作）
            # - write: 10秒发送请求
            # - 池：从池中获取连接需要 10 秒
            timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
            client = httpx.AsyncClient(
                base_url=self.host, timeout=timeout, headers=self._headers
            )
            self._client = client
        return client

    async def _execute(self, generator: Generator[dict[str, Any], httpx.Response, Any]):
        try:
            kwargs = next(generator)
            while True:
                response = await self.client.request(**kwargs)
                kwargs = generator.send(response)
        except StopIteration as e:
            return e.value

    async def start_command(
        self,
        command: str,
        cwd: str | Path | None = None,
        timeout: float = 30,
    ) -> str:
        """启动命令并返回其 ID，无需等待完成。"""
        return await self._execute(self._start_command_generator(command, cwd, timeout))

    async def get_command_output(
        self, command_id: str | None = None
    ) -> dict[str, Any] | None:
        """读取最新输出； 缺少退出代码意味着它仍在运行。"""
        return await self._execute(self._get_command_output_generator(command_id))

    async def stop_command(self, command_id: str) -> None:
        """通过 id 停止正在运行的 bash 命令。

        未知或已经完成的 id 是无操作的，与服务器的幂等性契约相匹配。
        """
        await self._execute(self._stop_command_generator(command_id))

    async def get_runtime_session_key(self) -> str:
        """获取此对话运行时的作用域工作人员凭据。"""
        return await self._execute(self._runtime_lifecycle_generator(release=False))

    async def release_runtime(self) -> None:
        """释放执行资源，同时保留对话历史记录。"""
        await self._execute(self._runtime_lifecycle_generator(release=True))

    async def execute_command(
        self,
        command: str,
        cwd: str | Path | None = None,
        timeout: float = 30.0,
    ) -> CommandResult:
        """在远程系统上执行 bash 命令。

        此方法通过远程 Agent Server API 启动 bash 命令，然后轮询输出，直到命令完成。

        Args:
            command: 要执行的 bash 命令
            cwd: 工作目录（可选）
            timeout: 超时以秒为单位

        Returns:
            CommandResult: 包含 stdout、stderr、exit_code 和其他元数据的结果
        """
        generator = self._execute_command_generator(command, cwd, timeout)
        result = await self._execute(generator)
        return result

    async def file_upload(
        self,
        source_path: str | Path | bytes,
        destination_path: str | Path,
    ) -> FileOperationResult:
        """将文件上传到远程系统。

        读取本地文件并通过HTTPAPI发送到远程系统。

        Args:
            source_path: 本地文件路径或内存中字节
            destination_path: 文件应上传到远程系统的路径

        Returns:
            FileOperationResult: 包含成功状态和元数据的结果
        """
        generator = self._file_upload_generator(source_path, destination_path)
        result = await self._execute(generator)
        return result

    async def file_download(
        self,
        source_path: str | Path,
        destination_path: str | Path,
    ) -> FileOperationResult:
        """从远程系统下载文件。

        通过HTTPAPI从远程系统请求文件并将其保存在本地。

        Args:
            source_path: 远程系统上源文件的路径
            destination_path: 文件应保存在本地的路径

        Returns:
            FileOperationResult: 包含成功状态和元数据的结果
        """
        generator = self._file_download_generator(source_path, destination_path)
        result = await self._execute(generator)
        return result

    async def git_changes(self, path: str | Path) -> list[GitChange]:
        """在给定的路径中获取存储库的 git 更改。

        Args:
            path: git 存储库的路径

        Returns:
            list[GitChange]：更改列表

        Raises:
            Exception: 如果路径不是 git 存储库或获取更改失败
        """
        generator = self._git_changes_generator(path)
        result = await self._execute(generator)
        return result

    async def git_diff(self, path: str | Path) -> GitDiff:
        """获取给定路径中文件的 git diff。

        Args:
            path: 文件路径

        Returns:
            GitDiff: git diff

        Raises:
            Exception: 如果路径不是 git 存储库或获取 diff 失败
        """
        generator = self._git_diff_generator(path)
        result = await self._execute(generator)
        return result

    @property
    def alive(self) -> bool:
        """通过查询运行状况端点来检查远程工作区是否处于活动状态。

        Returns:
            如果运行状况端点返回成功响应，则为 True，否则为 False。
        """
        try:
            health_url = f"{self.host}/health"
            with urlopen(health_url, timeout=5.0) as resp:
                status = getattr(resp, "status", 200)
                return 200 <= status < 300
        except Exception:
            return False
