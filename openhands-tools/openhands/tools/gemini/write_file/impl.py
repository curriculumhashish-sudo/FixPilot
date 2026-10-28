"""写文件工具执行器实现。"""

import os
from pathlib import Path
from typing import TYPE_CHECKING

from openhands.sdk.tool import ToolExecutor
from openhands.tools.gemini.write_file.definition import (
    WriteFileAction,
    WriteFileObservation,
)


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation


class WriteFileExecutor(ToolExecutor[WriteFileAction, WriteFileObservation]):
    """write_file 工具的执行器。"""

    def __init__(self, workspace_root: str):
        """使用工作区 root 初始化执行器。

        Args:
            workspace_root: 文件操作的根目录
        """
        self.workspace_root = Path(workspace_root)

    def __call__(
        self,
        action: WriteFileAction,
        conversation: "LocalConversation | None" = None,  # noqa: ARG002
    ) -> WriteFileObservation:
        """执行写文件操作。

        Args:
            action: WriteFileAction 与 file_path 和内容
            conversation: 执行上下文

        Returns:
            WriteFileObservation 结果
        """

        file_path = action.file_path
        content = action.content

        # 解析相对于工作区的路径
        if not os.path.isabs(file_path):
            resolved_path = self.workspace_root / file_path
        else:
            resolved_path = Path(file_path)

        # 检查path是否是一个目录
        if resolved_path.exists() and resolved_path.is_dir():
            return WriteFileObservation.from_text(
                is_error=True,
                text=(f"Error: Path is a directory, not a file: {resolved_path}"),
            )

        # 如果文件存在则读取旧内容
        is_new_file = not resolved_path.exists()
        old_content = None
        if not is_new_file:
            try:
                with open(resolved_path, encoding="utf-8", errors="replace") as f:
                    old_content = f.read()
            except Exception:
                pass

        try:
            # 如果需要，创建父目录
            resolved_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入文件
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(content)

            action_verb = "Created" if is_new_file else "Updated"
            return WriteFileObservation.from_text(
                text=f"{action_verb} file: {resolved_path}",
                file_path=str(resolved_path),
                is_new_file=is_new_file,
                old_content=old_content,
                new_content=content,
            )

        except PermissionError:
            return WriteFileObservation.from_text(
                is_error=True,
                text=f"Error: Permission denied: {resolved_path}",
            )
        except Exception as e:
            return WriteFileObservation.from_text(
                is_error=True,
                text=f"Error writing file: {e}",
            )
