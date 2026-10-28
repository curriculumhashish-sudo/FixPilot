"""列出目录工具定义（Gemini 风格）。"""

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, Field
from rich.text import Text

from openhands.sdk.tool import (
    Action,
    DeclaredResources,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    register_tool,
)


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState


class FileEntry(BaseModel):
    """有关文件或目录的信息。"""

    name: str = Field(description="Name of the file or directory")
    path: str = Field(description="Absolute path to the file or directory")
    is_directory: bool = Field(description="Whether this entry is a directory")
    size: int = Field(description="Size of the file in bytes (0 for directories)")
    modified_time: datetime = Field(description="Last modified timestamp")


class ListDirectoryAction(Action):
    """模式用于列表目录操作。"""

    dir_path: str = Field(
        default=".",
        description="The path to the directory to list. Defaults to current directory.",
    )
    recursive: bool = Field(
        default=False,
        description="Whether to list subdirectories recursively (up to 2 levels).",
    )


class ListDirectoryObservation(Observation):
    """观测结果来自列出目录。"""

    dir_path: str | None = Field(
        default=None, description="The directory path that was listed."
    )
    entries: list[FileEntry] = Field(
        default_factory=list, description="List of files and directories found."
    )
    total_count: int = Field(default=0, description="Total number of entries found.")
    is_truncated: bool = Field(
        default=False,
        description="Whether the listing was truncated due to too many entries.",
    )

    @property
    def visualize(self) -> Text:
        """返回此观测结果的富文本表示形式。"""
        text = Text()

        if self.is_error:
            text.append("❌ ", style="red bold")
            text.append(self.ERROR_MESSAGE_HEADER, style="bold red")
            return super().visualize

        if self.dir_path:
            text.append("📁 ", style="blue bold")
            text.append(f"Directory: {self.dir_path}\n", style="blue")

            if self.total_count == 0:
                text.append("(empty directory)\n", style="dim")
            else:
                # 构建一个简单的基于文本的表格
                lines = []
                lines.append(f"{'Type':<6} {'Name':<40} {'Size':>10} {'Modified':<16}")
                lines.append("-" * 76)

                for entry in self.entries[:50]:
                    entry_type = "📁" if entry.is_directory else "📄"
                    size_str = (
                        "-" if entry.is_directory else self._format_size(entry.size)
                    )
                    modified_str = entry.modified_time.strftime("%Y-%m-%d %H:%M")
                    # 如果名称太长则截断
                    name = (
                        entry.name[:38] + ".." if len(entry.name) > 40 else entry.name
                    )
                    lines.append(
                        f"{entry_type:<6} {name:<40} {size_str:>10} {modified_str:<16}"
                    )

                text.append("\n".join(lines) + "\n")

                if self.is_truncated:
                    text.append(
                        f"\n⚠️  Showing first 50 of {self.total_count} entries\n",
                        style="yellow",
                    )

        return text

    def _format_size(self, size: int) -> str:
        """以人类可读的格式格式化文件大小。"""
        size_float = float(size)
        for unit in ["B", "KB", "MB", "GB"]:
            if size_float < 1024.0:
                return f"{size_float:.1f}{unit}"
            size_float /= 1024.0
        return f"{size_float:.1f}TB"


TOOL_DESCRIPTION = """Lists the contents of a specified directory.

Returns detailed information about each file and subdirectory, including:
- Name and path
- Whether it's a file or directory
- File size (in bytes)
- Last modified timestamp

By default, lists only the immediate contents of the directory. Use `recursive=True`
to list subdirectories up to 2 levels deep.

Hidden files (starting with .) are included in the listing.

Examples:
- List current directory: list_directory()
- List specific directory: list_directory(dir_path="/path/to/dir")
- List recursively: list_directory(dir_path="/path/to/dir", recursive=True)
"""

# 返回的最大条目数（以防止压倒上下文）
MAX_ENTRIES = 500


class ListDirectoryTool(ToolDefinition[ListDirectoryAction, ListDirectoryObservation]):
    """用于列出带有元数据的目录内容的工具。"""

    user_selectable: ClassVar[bool] = False

    def declared_resources(self, action: Action) -> DeclaredResources:  # noqa: ARG002
        """声明并行执行的资源使用情况。

        每个调用都使用独立的只读文件系统操作(os.walk / Path.iterdir)，没有共享的可变
        状态，因此所有list_directory调用可以在并发
        环境中安全地运行锁。
        """
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState",
    ) -> Sequence["ListDirectoryTool"]:
        """使用执行器初始化 ListDirectoryTool。

        Args:
            conv_state: 要从中获取工作目录的对话状态。
        """
        from openhands.tools.gemini.list_directory.impl import ListDirectoryExecutor

        executor = ListDirectoryExecutor(
            workspace_root=conv_state.workspace.working_dir
        )

        working_dir = conv_state.workspace.working_dir
        enhanced_description = (
            f"{TOOL_DESCRIPTION}\n\n"
            f"Your current working directory is: {working_dir}\n"
            f"Relative paths will be resolved from this directory."
        )

        return [
            cls(
                action_type=ListDirectoryAction,
                observation_type=ListDirectoryObservation,
                description=enhanced_description,
                annotations=ToolAnnotations(
                    title="list_directory",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


register_tool(ListDirectoryTool.name, ListDirectoryTool)
