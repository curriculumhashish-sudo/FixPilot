"""列表目录工具执行器实现。"""

import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from openhands.sdk.tool import ToolExecutor
from openhands.tools.gemini.list_directory.definition import (
    MAX_ENTRIES,
    FileEntry,
    ListDirectoryAction,
    ListDirectoryObservation,
)


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation


class ListDirectoryExecutor(
    ToolExecutor[ListDirectoryAction, ListDirectoryObservation]
):
    """list_directory 工具的执行器。"""

    def __init__(self, workspace_root: str):
        """使用工作区 root 初始化执行器。

        Args:
            workspace_root: 文件操作的根目录
        """
        self.workspace_root = Path(workspace_root)

    def __call__(
        self,
        action: ListDirectoryAction,
        conversation: "LocalConversation | None" = None,  # noqa: ARG002
    ) -> ListDirectoryObservation:
        """执行列出目录操作。

        Args:
            action: ListDirectoryAction 与 dir_path 和递归
            conversation: 执行上下文

        Returns:
            ListDirectoryObservation 包含目录内容
        """

        dir_path = action.dir_path
        recursive = action.recursive

        # 解析相对于工作区的路径
        if not os.path.isabs(dir_path):
            resolved_path = self.workspace_root / dir_path
        else:
            resolved_path = Path(dir_path)

        # 检查目录是否存在
        if not resolved_path.exists():
            return ListDirectoryObservation.from_text(
                is_error=True,
                text=f"Error: Directory not found: {resolved_path}",
            )

        # 检查是否是一个目录
        if not resolved_path.is_dir():
            return ListDirectoryObservation.from_text(
                is_error=True,
                text=f"Error: Path is not a directory: {resolved_path}",
            )

        try:
            entries = []

            if recursive:
                # 列出最多 2 层深度
                for root, dirs, files in os.walk(resolved_path):
                    root_path = Path(root)
                    depth = len(root_path.relative_to(resolved_path).parts)
                    if depth >= 2:
                        dirs.clear()
                        continue

                    # 添加目录
                    for d in sorted(dirs):
                        d_path = root_path / d
                        try:
                            stat = d_path.stat()
                            entries.append(
                                FileEntry(
                                    name=d,
                                    path=str(d_path),
                                    is_directory=True,
                                    size=0,
                                    modified_time=datetime.fromtimestamp(stat.st_mtime),
                                )
                            )
                        except Exception:
                            continue

                    # 添加文件
                    for f in sorted(files):
                        f_path = root_path / f
                        try:
                            stat = f_path.stat()
                            entries.append(
                                FileEntry(
                                    name=f,
                                    path=str(f_path),
                                    is_directory=False,
                                    size=stat.st_size,
                                    modified_time=datetime.fromtimestamp(stat.st_mtime),
                                )
                            )
                        except Exception:
                            continue

                    if len(entries) >= MAX_ENTRIES:
                        break
            else:
                # 仅列出直接内容
                for entry in sorted(resolved_path.iterdir()):
                    try:
                        stat = entry.stat()
                        entries.append(
                            FileEntry(
                                name=entry.name,
                                path=str(entry),
                                is_directory=entry.is_dir(),
                                size=0 if entry.is_dir() else stat.st_size,
                                modified_time=datetime.fromtimestamp(stat.st_mtime),
                            )
                        )

                        if len(entries) >= MAX_ENTRIES:
                            break
                    except Exception:
                        continue

            total_count = len(entries)
            is_truncated = total_count >= MAX_ENTRIES

            agent_obs = f"Listed directory: {resolved_path} ({total_count} entries"
            if is_truncated:
                agent_obs += f", truncated to {MAX_ENTRIES}"
            agent_obs += ")"

            return ListDirectoryObservation.from_text(
                text=agent_obs,
                dir_path=str(resolved_path),
                entries=entries[:MAX_ENTRIES],
                total_count=total_count,
                is_truncated=is_truncated,
            )

        except PermissionError:
            return ListDirectoryObservation.from_text(
                is_error=True,
                text=f"Error: Permission denied: {resolved_path}",
            )
        except Exception as e:
            return ListDirectoryObservation.from_text(
                is_error=True,
                text=f"Error listing directory: {e}",
            )
