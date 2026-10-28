import shutil
from pathlib import Path
from typing import Any

from openhands.sdk.git.git_changes import get_git_changes
from openhands.sdk.git.git_diff import get_git_diff
from openhands.sdk.git.models import GitChange, GitDiff
from openhands.sdk.logger import get_logger
from openhands.sdk.utils.command import execute_command
from openhands.sdk.workspace.base import BaseWorkspace
from openhands.sdk.workspace.models import CommandResult, FileOperationResult


logger = get_logger(__name__)


class LocalWorkspace(BaseWorkspace):
    """在主机文件系统上运行的本地工作区实现。

    LocalWorkspace 提供对本地文件系统和命令执行环境的直接访问。 它适用于智能体应直接
    在主机系统上运行的开发和测试场景。

    Example:
        >>> workspace = LocalWorkspace(working_dir="/path/to/project")
        >>> with workspace:
        ...     result = workspace.execute_command("ls -la")
        ...     content = workspace.read_file("README.md")
    """

    def __init__(self, *, working_dir: str | Path, **kwargs: Any):
        # 接受人体工程学和类型检查器签名中的 Path，但将底层模型字段标准化为 str。
        #
        super().__init__(working_dir=str(working_dir), **kwargs)

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """退出工作区上下文并发送完成回调。

        镜像 ``RemoteWorkspace.__exit__``，因此驱动本地智能体的自动化报告其结果 - 以
        及累积的 LLM 成本 - 与远程自动化的方式相
        同。 除非设置 ``AUTOMATION_CALLBACK_URL``，否则不执行任何操作，因此普通本地使
        用不受影响。
        """
        self._send_completion_callback(exc_type, exc_val)
        super().__exit__(exc_type, exc_val, exc_tb)

    def execute_command(
        self,
        command: str,
        cwd: str | Path | None = None,
        timeout: float = 30.0,
    ) -> CommandResult:
        """在本地执行 bash 命令。

        使用共享 shell 执行实用程序来运行具有正确超时处理、输出流式传输和错误管理的命
        令。

        Args:
            command: 要执行的 bash 命令
            cwd: 工作目录（可选）
            timeout: 超时以秒为单位

        Returns:
            CommandResult: 结果包含 stdout、stderr、exit_code、command 和
                timeout_occurred
        """
        logger.debug(f"Executing local bash command: {command} in {cwd}")
        result = execute_command(
            command,
            cwd=str(cwd) if cwd is not None else str(self.working_dir),
            timeout=timeout,
            print_output=True,
        )
        return CommandResult(
            command=command,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            timeout_occurred=result.returncode == -1,
        )

    def file_upload(
        self,
        source_path: str | Path,
        destination_path: str | Path,
    ) -> FileOperationResult:
        """在本地上传（复制）文件。

        对于本地系统，文件上传是作为文件复制操作实现的，使用 shutil.copy2 来保留元数
        据。

        Args:
            source_path: 源文件的路径
            destination_path: 文件应复制到的路径

        Returns:
            FileOperationResult: 结果包含成功状态和文件信息
        """
        source = Path(source_path)
        destination = Path(destination_path)

        logger.debug(f"Local file upload: {source} -> {destination}")

        try:
            # 确保目标目录存在
            destination.parent.mkdir(parents=True, exist_ok=True)

            # 复制并保留元数据的文件
            shutil.copy2(source, destination)

            return FileOperationResult(
                success=True,
                source_path=str(source),
                destination_path=str(destination),
                file_size=destination.stat().st_size,
            )

        except Exception as e:
            logger.error(f"Local file upload failed: {e}")
            return FileOperationResult(
                success=False,
                source_path=str(source),
                destination_path=str(destination),
                error=str(e),
            )

    def file_download(
        self,
        source_path: str | Path,
        destination_path: str | Path,
    ) -> FileOperationResult:
        """在本地下载（复制）文件。

        对于本地系统，文件下载是作为文件复制操作实现的，使用 shutil.copy2 来保留元数
        据。

        Args:
            source_path: 源文件的路径
            destination_path: 文件应复制到的路径

        Returns:
            FileOperationResult: 结果包含成功状态和文件信息
        """
        source = Path(source_path)
        destination = Path(destination_path)

        logger.debug(f"Local file download: {source} -> {destination}")

        try:
            # 确保目标目录存在
            destination.parent.mkdir(parents=True, exist_ok=True)

            # 复制并保留元数据的文件
            shutil.copy2(source, destination)

            return FileOperationResult(
                success=True,
                source_path=str(source),
                destination_path=str(destination),
                file_size=destination.stat().st_size,
            )

        except Exception as e:
            logger.error(f"Local file download failed: {e}")
            return FileOperationResult(
                success=False,
                source_path=str(source),
                destination_path=str(destination),
                error=str(e),
            )

    def git_changes(self, path: str | Path) -> list[GitChange]:
        """在给定的路径中获取存储库的 git 更改。

        Args:
            path: git 存储库的路径

        Returns:
            list[GitChange]：更改列表

        Raises:
            Exception: 如果路径不是 git 存储库或获取更改失败
        """
        path = Path(self.working_dir) / path
        return get_git_changes(path)

    def git_diff(self, path: str | Path) -> GitDiff:
        """获取给定路径中文件的 git diff。

        Args:
            path: 文件路径

        Returns:
            GitDiff: git diff

        Raises:
            Exception: 如果路径不是 git 存储库或获取 diff 失败
        """
        path = Path(self.working_dir) / path
        return get_git_diff(path)

    def pause(self) -> None:
        """暂停工作区（本地工作区无操作）。

        本地工作区无需暂停，因为它们直接在主机文件系统上操作。
        """
        logger.debug("pause() called on LocalWorkspace - nothing to do")

    def resume(self) -> None:
        """恢复工作区（本地工作区无操作）。

        本地工作区无需恢复，因为它们直接在主机文件系统上操作。
        """
        logger.debug("resume() called on LocalWorkspace - nothing to do")
