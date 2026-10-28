"""编写文件工具定义（Gemini 风格）。"""

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from pydantic import Field

from openhands.sdk.tool import (
    Action,
    DeclaredResources,
    ToolAnnotations,
    ToolDefinition,
    register_tool,
)
from openhands.tools.gemini.file_change import FileChangeObservation


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState


class WriteFileAction(Action):
    """模式用于写文件操作。"""

    file_path: str = Field(description="The path to the file to write to.")
    content: str = Field(description="The content to write to the file.")


class WriteFileObservation(FileChangeObservation):
    """观测结果来自写入文件。"""

    file_path: str | None = Field(
        default=None, description="The file path that was written."
    )
    is_new_file: bool = Field(
        default=False, description="Whether a new file was created."
    )
    old_content: str | None = Field(
        default=None, description="The previous content of the file (if it existed)."
    )
    new_content: str | None = Field(
        default=None, description="The new content written to the file."
    )

    def change_summary(self) -> str:
        return f"Updated: {self.file_path}\n"


TOOL_DESCRIPTION = """Writes content to a specified file in the local filesystem.

This tool overwrites the entire content of the file. If the file doesn't exist,
it will be created. If it exists, all previous content will be replaced.

This is useful for:
- Creating new files
- Completely rewriting files when many changes are needed
- Setting initial file content

For smaller edits to existing files, consider using the 'edit' tool instead,
which allows targeted find/replace operations.

Examples:
- Create new file: write_file(file_path="/path/to/new.py", content="print('hello')")
- Overwrite file: write_file(file_path="/path/to/existing.py", content="new content")
"""


class WriteFileTool(ToolDefinition[WriteFileAction, WriteFileObservation]):
    """用于写入完整文件内容的工具。"""

    user_selectable: ClassVar[bool] = False

    def declared_resources(self, action: Action) -> DeclaredResources:
        """锁在目标文件路径上，因此并发写入相同的内容
        文件的大小为已序列化，而对不同文件的写入并行运行。
        """
        assert isinstance(action, WriteFileAction)
        path = Path(action.file_path)
        if not path.is_absolute():
            assert self.meta is not None, (
                "workspace_root required to resolve relative paths"
            )
            path = Path(self.meta["workspace_root"]) / path
        return DeclaredResources(keys=(f"file:{path.resolve()}",), declared=True)

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState",
    ) -> Sequence["WriteFileTool"]:
        """使用执行器初始化 WriteFileTool。

        Args:
            conv_state: 要从中获取工作目录的对话状态。
        """
        from openhands.tools.gemini.write_file.impl import WriteFileExecutor

        executor = WriteFileExecutor(workspace_root=conv_state.workspace.working_dir)

        working_dir = conv_state.workspace.working_dir
        enhanced_description = (
            f"{TOOL_DESCRIPTION}\n\n"
            f"Your current working directory is: {working_dir}\n"
            f"File paths can be absolute or relative to this directory."
        )

        return [
            cls(
                action_type=WriteFileAction,
                observation_type=WriteFileObservation,
                description=enhanced_description,
                annotations=ToolAnnotations(
                    title="write_file",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
                executor=executor,
                meta={"workspace_root": working_dir},
            )
        ]


register_tool(WriteFileTool.name, WriteFileTool)
