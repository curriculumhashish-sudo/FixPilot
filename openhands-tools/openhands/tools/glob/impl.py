"""Glob 工具执行器实现。"""

# 使用绝对导入以避免与本地 glob 模块发生冲突
import glob as glob_module
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from openhands.sdk.tool import ToolExecutor
from openhands.sdk.utils import sanitized_env


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation
from openhands.tools.glob.definition import GlobAction, GlobObservation
from openhands.tools.utils import (
    _check_ripgrep_available,
    _log_ripgrep_fallback_warning,
)


class GlobExecutor(ToolExecutor[GlobAction, GlobObservation]):
    """全局模式匹配操作的执行器。

    此实现更喜欢 ripgrep 来提高性能，但如果 ripgrep 不可用，则回退到 Python 的 glob
    模块：
    - Primary: 使用 rg --files 列出所有文件，通过带有 -g 标志的 glob 模式进行过滤
    - Fallback: 使用 Python 的 glob.glob() 进行模式匹配
    """

    def __init__(self, working_dir: str):
        """初始化 glob 执行器。

        Args:
            working_dir: 用于搜索的基础工作目录
        """
        self.working_dir: Path = Path(working_dir).resolve()
        self._ripgrep_available: bool = _check_ripgrep_available()
        if not self._ripgrep_available:
            _log_ripgrep_fallback_warning("glob", "Python glob module")

    def is_parallel_safe(self) -> bool:
        """执行器对于无锁的并行执行是否安全。

        True 当 ripgrep 可用时（独立子进程）。 False 为 Python glob 回退方案（进程全
        局 os.chdir()）。
        """
        return self._ripgrep_available

    def __call__(
        self,
        action: GlobAction,
        conversation: "LocalConversation | None" = None,  # noqa: ARG002
    ) -> GlobObservation:
        """使用 ripgrep 或回退方案到 Python glob 执行 glob 模式匹配。

        Args:
            action: 包含模式和可选路径的 glob 操作

        Returns:
            GlobObservation 具有匹配文件或错误信息
        """
        try:
            original_pattern = action.pattern  # 存储观测结果的原始模式

            if action.path:
                search_path = Path(action.path).resolve()
                pattern = action.pattern
            else:
                extracted_path, pattern = self._extract_search_path_from_pattern(
                    action.pattern
                )
                search_path = (
                    extracted_path if extracted_path is not None else self.working_dir
                )

            if not search_path.is_dir():
                return GlobObservation.from_text(
                    text=f"Search path '{search_path}' is not a valid directory",
                    files=[],
                    pattern=original_pattern,
                    search_path=str(search_path),
                    is_error=True,
                )

            if self._ripgrep_available:
                files, truncated = self._execute_with_ripgrep(pattern, search_path)
            else:
                files, truncated = self._execute_with_glob(pattern, search_path)

            # 格式化内容消息
            if not files:
                content = (
                    f"No files found matching pattern '{original_pattern}' "
                    f"in directory '{search_path}'"
                )
            else:
                file_list = "\n".join(files)
                content = (
                    f"Found {len(files)} file(s) matching pattern "
                    f"'{original_pattern}' in '{search_path}':\n{file_list}"
                )
                if truncated:
                    content += (
                        "\n\n[Results truncated to first 100 files. "
                        "Consider using a more specific pattern.]"
                    )

            return GlobObservation.from_text(
                text=content,
                files=files,
                pattern=original_pattern,
                search_path=str(search_path),
                truncated=truncated,
            )

        except Exception as e:
            # 确定错误报告的搜索路径
            try:
                if action.path:
                    error_search_path = str(Path(action.path).resolve())
                else:
                    error_search_path = str(self.working_dir)
            except Exception:
                error_search_path = "unknown"

            return GlobObservation.from_text(
                text=str(e),
                files=[],
                pattern=action.pattern,
                search_path=error_search_path,
                is_error=True,
            )

    def _execute_with_ripgrep(
        self, pattern: str, search_path: Path
    ) -> tuple[list[str], bool]:
        """使用 ripgrep 执行全局模式匹配。

        Args:
            pattern: 要匹配的全局模式
            search_path: 要搜索的目录

        Returns:
            (file_paths, truncated) 元组，其中 file_paths 是匹配文件的列表，如果结果
            限制为 100 个文件，则截断为 Tru
            e
        """  # noqa: E501
        search_path = search_path.resolve()

        # 构建 ripgrep 命令： rg --files {path} -g {pattern} --sortr=modified
        cmd = [
            "rg",
            "--files",
            str(search_path),
            "-g",
            pattern,
            "--sortr=modified",
        ]

        # 执行ripgrep
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=sanitized_env(),
        )

        # 将输出解析为文件路径
        file_paths = []
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                if line:
                    file_paths.append(str(Path(line).resolve()))
                    # 限制为前 100 个文件
                    if len(file_paths) >= 100:
                        break

        truncated = len(file_paths) >= 100

        return file_paths, truncated

    def _execute_with_glob(
        self, pattern: str, search_path: Path
    ) -> tuple[list[str], bool]:
        """使用 Python 的 glob 模块执行 glob 模式匹配。

        Args:
            pattern: 要匹配的全局模式
            search_path: 要搜索的目录

        Returns:
            (file_paths, truncated) 元组，其中 file_paths 是匹配文件的列表，如果结果
            限制为 100 个文件，则截断为 Tru
            e
        """  # noqa: E501
        search_path = search_path.resolve()

        # 更改为 glob 的搜索目录才能正常工作
        original_cwd = os.getcwd()
        try:
            os.chdir(search_path)

            # Ripgrep 的 -g 标志始终是递归的，因此如果它尚未包含 **，我们需要使模式递归
            #
            if "**" not in pattern:
                # 将非递归模式（如“*.py”）转换为“**/*.py"”以匹配 ripgrep 的递归行为
                #
                pattern = f"**/{pattern}"

            # 使用glob查找匹配文件
            matches = glob_module.glob(pattern, recursive=True)

            # 转换为绝对路径而不解析符号链接并按修改时间排序。
            #
            file_paths = []
            for match in matches:
                abs_path = str((search_path / match).absolute())
                if os.path.isfile(abs_path):
                    file_paths.append((abs_path, os.path.getmtime(abs_path)))

            # 按修改时间排序（最新的在前）和提取路径
            file_paths.sort(key=lambda x: x[1], reverse=True)
            sorted_files = [path for path, _ in file_paths[:100]]

            truncated = len(file_paths) > 100

            return sorted_files, truncated
        finally:
            os.chdir(original_cwd)

    @staticmethod
    def _extract_search_path_from_pattern(pattern: str) -> tuple[Path | None, str]:
        """从绝对路径模式中提取搜索路径和相对模式。

        这是因为智能体可能发送绝对路径模式，如 `/path/to/dir/**/*.py"`，而 ripgrep 的
         `-g` 标志期望一个搜索目录和一个相对模式
        。 该函数将绝对模式分为这两个部分。

        对于相对模式，返回 (None,pattern) 以指示调用者应使用其默认值工作目录。

        Args:
            pattern: 全局模式（可以是绝对的或相对的）

        Returns:
            (search_path, adjusted_pattern) 的元组，其中：
            - search_path: 要搜索的目录（None 表示相关模式）
            - adjusted_pattern: 相对于 search_path 的模式

        Examples:
            >>> _extract_search_path_from_pattern("/path/to/dir/**/*.py")
            (Path("/path/to/dir"), "**/*.py")

            >>> _extract_search_path_from_pattern("/path/to/*.py")
            (Path("/path/to"), "*.py")

            >>> _extract_search_path_from_pattern("**/*.py")
            (None, "**/*.py")
        """
        if not pattern:
            return None, "**/*"

        # 展开 ~ 作为用户主目录
        pattern = os.path.expanduser(pattern)

        path_obj = Path(pattern)

        # 检查模式是否是绝对路径。 保持 POSIX 样式的绝对路径在 Windows 上也有效，因为智
        # 能体经常发出 /tmp-style 路径。
        #
        if not pattern.startswith("/") and not path_obj.is_absolute():
            # 相对模式 - 调用者应使用默认工作目录
            return None, pattern

        # 绝对路径模式 - 提取基本路径
        parts = path_obj.parts

        # 使用 glob.has_magic() 查找全局字符开始的位置
        search_parts = []
        for part in parts:
            if glob_module.has_magic(part):
                break
            search_parts.append(part)

        if not search_parts:
            # 模式以 glob 开头 (e.g., "/*/*.py")
            search_path = Path("/")
            adjusted_pattern = pattern.lstrip("/")
        else:
            search_path = Path(*search_parts)
            # 获取剩余部分作为图案
            remaining = parts[len(search_parts) :]
            adjusted_pattern = "/".join(remaining) if remaining else "**/*"

        return search_path.resolve(), adjusted_pattern
