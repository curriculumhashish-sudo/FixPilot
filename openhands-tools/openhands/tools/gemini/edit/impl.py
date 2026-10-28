"""编辑工具执行器实现。"""

from pathlib import Path
from typing import TYPE_CHECKING

from openhands.sdk.tool import ToolExecutor
from openhands.tools.gemini.edit.definition import EditAction, EditObservation


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation


class EditExecutor(ToolExecutor[EditAction, EditObservation]):
    """编辑工具的执行器。"""

    def __init__(self, workspace_root: str):
        """使用工作区 root 初始化执行器。

        Args:
            workspace_root: 文件操作的根目录
        """
        self.workspace_root = Path(workspace_root)

    def __call__(
        self,
        action: EditAction,
        conversation: "LocalConversation | None" = None,  # noqa: ARG002
    ) -> EditObservation:
        """执行编辑操作。

        Args:
            action: EditAction 与 file_path、old_string、new_string 等
            conversation: 执行上下文

        Returns:
            EditObservation 结果
        """

        file_path = action.file_path
        old_string = action.old_string
        new_string = action.new_string
        expected_replacements = action.expected_replacements

        resolved_path = (self.workspace_root / file_path).resolve()

        # 处理文件创建（old_string为空）
        if old_string == "":
            if resolved_path.exists():
                return EditObservation.from_text(
                    is_error=True,
                    text=(
                        f"Error: Cannot create file that already exists: "
                        f"{resolved_path}. "
                        f"Use write_file to overwrite or provide non-empty old_string."
                    ),
                )

            try:
                # 如果需要，创建父目录
                resolved_path.parent.mkdir(parents=True, exist_ok=True)

                # 写入文件
                with open(resolved_path, "w", encoding="utf-8") as f:
                    f.write(new_string)

                return EditObservation.from_text(
                    text=f"Created new file: {resolved_path}",
                    file_path=str(resolved_path),
                    is_new_file=True,
                    replacements_made=1,
                    old_content=None,
                    new_content=new_string,
                )

            except PermissionError:
                return EditObservation.from_text(
                    is_error=True,
                    text=f"Error: Permission denied: {resolved_path}",
                )
            except Exception as e:
                return EditObservation.from_text(
                    is_error=True,
                    text=f"Error creating file: {e}",
                )

        # 编辑现有文件
        if not resolved_path.exists():
            return EditObservation.from_text(
                is_error=True,
                text=(
                    f"Error: File not found: {resolved_path}. "
                    f"To create a new file, use old_string=''."
                ),
            )

        if resolved_path.is_dir():
            return EditObservation.from_text(
                is_error=True,
                text=f"Error: Path is a directory, not a file: {resolved_path}",
            )

        try:
            # 读取当前内容
            with open(resolved_path, encoding="utf-8", errors="replace") as f:
                old_content = f.read()

            # 检查无操作
            if old_string == new_string:
                return EditObservation.from_text(
                    is_error=True,
                    text=(
                        "Error: No changes to apply. "
                        "old_string and new_string are identical."
                    ),
                )

            # 计数出现次数
            occurrences = old_content.count(old_string)

            if occurrences == 0:
                return EditObservation.from_text(
                    is_error=True,
                    text=(
                        f"Error: Could not find the string to replace. "
                        f"0 occurrences found in {resolved_path}. "
                        f"Use read_file to verify the exact text."
                    ),
                    file_path=str(resolved_path),
                )

            if occurrences != expected_replacements:
                occurrence_word = (
                    "occurrence" if expected_replacements == 1 else "occurrences"
                )
                return EditObservation.from_text(
                    is_error=True,
                    text=(
                        f"Error: Expected {expected_replacements} {occurrence_word} "
                        f"but found {occurrences} in {resolved_path}."
                    ),
                    file_path=str(resolved_path),
                )

            # 执行更换
            new_content = old_content.replace(old_string, new_string)

            # 检查内容是否实际更改
            if old_content == new_content:
                return EditObservation.from_text(
                    is_error=True,
                    text=(
                        "Error: No changes made. "
                        "The new content is identical to the current content."
                    ),
                    file_path=str(resolved_path),
                )

            # 写入文件
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            msg = f"Successfully edited {resolved_path} ({occurrences} replacement(s))"
            return EditObservation.from_text(
                text=msg,
                file_path=str(resolved_path),
                is_new_file=False,
                replacements_made=occurrences,
                old_content=old_content,
                new_content=new_content,
            )

        except PermissionError:
            return EditObservation.from_text(
                is_error=True,
                text=f"Error: Permission denied: {resolved_path}",
            )
        except Exception as e:
            return EditObservation.from_text(
                is_error=True,
                text=f"Error editing file: {e}",
            )
