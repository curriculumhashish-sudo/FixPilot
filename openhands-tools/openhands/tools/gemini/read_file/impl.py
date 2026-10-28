"""读文件工具执行器实现。"""

import os
from pathlib import Path
from typing import TYPE_CHECKING

from openhands.sdk.tool import ToolExecutor
from openhands.tools.gemini.read_file.definition import (
    MAX_LINES_PER_READ,
    ReadFileAction,
    ReadFileObservation,
)


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation


class ReadFileExecutor(ToolExecutor[ReadFileAction, ReadFileObservation]):
    """read_file 工具的执行器。"""

    def __init__(self, workspace_root: str):
        """使用工作区 root 初始化执行器。

        Args:
            workspace_root: 文件操作的根目录
        """
        self.workspace_root = Path(workspace_root)

    def __call__(
        self,
        action: ReadFileAction,
        conversation: "LocalConversation | None" = None,  # noqa: ARG002
    ) -> ReadFileObservation:
        """执行读取文件操作。

        Args:
            action: ReadFileAction 与 file_path、偏移量和限制
            conversation: 执行上下文

        Returns:
            ReadFileObservation 包含文件内容
        """

        file_path = action.file_path
        offset = action.offset or 0
        limit = action.limit

        # 解析相对于工作区的路径
        if not os.path.isabs(file_path):
            resolved_path = self.workspace_root / file_path
        else:
            resolved_path = Path(file_path)

        # 检查文件是否存在
        if not resolved_path.exists():
            return ReadFileObservation.from_text(
                text=f"Error: File not found: {resolved_path}",
                is_error=True,
                file_path=str(resolved_path),
                file_content="",
            )

        # 检查是否是一个目录
        if resolved_path.is_dir():
            return ReadFileObservation.from_text(
                text=f"Error: Path is a directory, not a file: {resolved_path}",
                is_error=True,
                file_path=str(resolved_path),
                file_content="",
            )

        try:
            # 读取文件内容
            with open(resolved_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)

            # 应用偏移和限制
            if offset >= total_lines:
                return ReadFileObservation.from_text(
                    text=(
                        f"Error: Offset {offset} is beyond file length "
                        f"({total_lines} lines)"
                    ),
                    is_error=True,
                    file_path=str(resolved_path),
                    file_content="",
                )

            # 确定读取范围
            start = offset
            if limit:
                end = min(start + limit, total_lines)
            else:
                # 如果未指定限制，则应用默认最大值
                end = min(start + MAX_LINES_PER_READ, total_lines)

            # 获取返回的线路
            lines_to_show = lines[start:end]

            # 添加行号
            numbered_lines = []
            for i, line in enumerate(lines_to_show, start=start + 1):
                numbered_lines.append(f"{i:6d}  {line}")
            content_with_numbers = "".join(numbered_lines)

            # 检查是否被截断
            is_truncated = end < total_lines
            lines_shown = (start + 1, end) if is_truncated else None

            agent_obs_parts = [f"Read file: {resolved_path}"]
            if is_truncated:
                agent_obs_parts.append(
                    f"(showing lines {start + 1}-{end} of {total_lines})"
                )
                next_offset = end
                agent_obs_parts.append(
                    f"To read more, use: read_file(file_path='{action.file_path}', "
                    f"offset={next_offset}, limit={limit or MAX_LINES_PER_READ})"
                )

            return ReadFileObservation.from_text(
                text=" ".join(agent_obs_parts) + "\n\n" + content_with_numbers,
                file_path=str(resolved_path),
                file_content=content_with_numbers,
                is_truncated=is_truncated,
                lines_shown=lines_shown,
                total_lines=total_lines,
            )

        except UnicodeDecodeError:
            return ReadFileObservation.from_text(
                is_error=True,
                text=f"Error: File is not a text file: {resolved_path}",
                file_path=str(resolved_path),
                file_content="",
            )
        except PermissionError:
            return ReadFileObservation.from_text(
                is_error=True,
                text=f"Error: Permission denied: {resolved_path}",
                file_path=str(resolved_path),
                file_content="",
            )
        except Exception as e:
            return ReadFileObservation.from_text(
                is_error=True,
                text=f"Error reading file: {e}",
                file_path=str(resolved_path),
                file_content="",
            )
