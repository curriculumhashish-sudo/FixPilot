"""字符串替换编辑器工具实现。"""

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import Field, PrivateAttr


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState

from rich.text import Text

from openhands.sdk.tool import (
    Action,
    DeclaredResources,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    register_tool,
)
from openhands.tools.file_editor.utils.diff import visualize_diff


CommandLiteral = Literal["view", "create", "str_replace", "insert", "undo_edit"]


class FileEditorAction(Action):
    """模式用于文件编辑器操作。"""

    command: CommandLiteral = Field(
        description="The commands to run. Allowed options are: `view`, `create`, "
        "`str_replace`, `insert`, `undo_edit`."
    )
    path: str = Field(description="Absolute path to file or directory.")
    file_text: str | None = Field(
        default=None,
        description="Required parameter of `create` command, with the content of "
        "the file to be created.",
    )
    old_str: str | None = Field(
        default=None,
        description="Required parameter of `str_replace` command containing the "
        "string in `path` to replace.",
    )
    new_str: str | None = Field(
        default=None,
        description="Optional parameter of `str_replace` command containing the "
        "new string (if not given, no string will be added). Required parameter "
        "of `insert` command containing the string to insert.",
    )
    insert_line: int | None = Field(
        default=None,
        ge=0,
        description="Required parameter of `insert` command. The `new_str` will "
        "be inserted AFTER the line `insert_line` of `path`.",
    )
    view_range: list[int] | None = Field(
        default=None,
        description="Optional parameter of `view` command when `path` points to a "
        "file. If none is given, the full file is shown. If provided, the file "
        "will be shown in the indicated line number range, e.g. [11, 12] will "
        "show lines 11 and 12. Indexing at 1 to start. Setting `[start_line, "
        "-1]` shows all lines from `start_line` to the end of the file.",
    )


class FileEditorObservation(Observation):
    """可以呈现为 CLI 输出的 ToolResult。"""

    command: CommandLiteral = Field(
        description=(
            "The command that was run: `view`, `create`, `str_replace`, "
            "`insert`, or `undo_edit`."
        )
    )

    path: str | None = Field(default=None, description="The file path that was edited.")
    prev_exist: bool = Field(
        default=True,
        description="Indicates if the file previously existed. If not, it was created.",
    )
    old_content: str | None = Field(
        default=None, description="The content of the file before the edit."
    )
    new_content: str | None = Field(
        default=None, description="The content of the file after the edit."
    )

    _diff_cache: Text | None = PrivateAttr(default=None)

    @property
    def visualize(self) -> Text:
        """返回此观测结果的富文本表示形式。

        显示有意义的更改（文件创建、成功编辑）的差异可视化，否则回退到智能体观测结果
        。
        """
        text = Text()

        if self.is_error:
            text.append("❌ ", style="red bold")
            text.append(self.ERROR_MESSAGE_HEADER, style="bold red")

        if not self._has_meaningful_diff:
            return super().visualize

        assert self.path is not None, "path should be set for meaningful diff"
        # 生成并缓存差异可视化
        if not self._diff_cache:
            change_applied = self.command != "view" and not self.is_error
            self._diff_cache = visualize_diff(
                self.path,
                self.old_content,
                self.new_content,
                n_context_lines=2,
                change_applied=change_applied,
            )

        # 将错误前缀与差异可视化相结合
        text.append(self._diff_cache)
        return text

    @property
    def _has_meaningful_diff(self) -> bool:
        """检查是否有有意义的差异要显示。"""
        if self.is_error:
            return False

        if not self.path:
            return False

        if self.command not in ("create", "str_replace", "insert", "undo_edit"):
            return False

        # 文件创建案例
        if self.command == "create" and self.new_content and not self.prev_exist:
            return True

        # 文件修改案例（str_replace、插入、undo_edit）
        if self.command in ("str_replace", "insert", "undo_edit"):
            # 需要新旧内容来显示有意义的差异
            if self.old_content is not None and self.new_content is not None:
                # 仅在内容实际更改时才显示差异
                return self.old_content != self.new_content

        return False


Command = Literal[
    "view",
    "create",
    "str_replace",
    "insert",
    "undo_edit",
]


TOOL_DESCRIPTION = """Custom editing tool for viewing, creating and editing files in plain-text format
* State is persistent across command calls and discussions with the user
* If `path` is a text file, `view` displays the result of applying `cat -n`. If `path` is a directory, `view` lists non-hidden files and directories up to 2 levels deep
* The `create` command cannot be used if the specified `path` already exists as a file
* If a `command` generates a long output, it will be truncated and marked with `<response clipped>`
* The `undo_edit` command will revert the last edit made to the file at `path`
* This tool can be used for creating and editing files in plain-text format.


Before using this tool:
1. Use the view tool to understand the file's contents and context
2. Verify the directory path is correct (only applicable when creating new files):
   - Use the view tool to verify the parent directory exists and is the correct location

When making edits:
   - Ensure the edit results in idiomatic, correct code
   - Do not leave the code in a broken state
   - Always use absolute file paths (starting with /)

CRITICAL REQUIREMENTS FOR USING THIS TOOL:

1. EXACT MATCHING: The `old_str` parameter must match EXACTLY one or more consecutive lines from the file, including all whitespace and indentation. The tool will fail if `old_str` matches multiple locations or doesn't match exactly with the file content.

2. UNIQUENESS: The `old_str` must uniquely identify a single instance in the file:
   - Include sufficient context before and after the change point (3-5 lines recommended)
   - If not unique, the replacement will not be performed

3. REPLACEMENT: The `new_str` parameter should contain the edited lines that replace the `old_str`. Both strings must be different.

Remember: when making multiple file edits in a row to the same file, you should prefer to send all edits in a single message with multiple calls to this tool, rather than multiple messages with a single call each.
"""  # noqa: E501


class FileEditorTool(ToolDefinition[FileEditorAction, FileEditorObservation]):
    """自动初始化 FileEditorExecutor 的 ToolDefinition 子类。"""

    catalog_description: ClassVar[str] = "View, create and edit files."

    def declared_resources(self, action: Action) -> DeclaredResources:
        """声明此操作访问的文件资源。

        目标文件路径上的所有命令 - 包括只读 ``view`` - 锁。 这确保视图在并发写入期间
        永远不会读取部分写入的内容。 修改或访问
        *不同的*文件并行运行。
        """
        assert isinstance(action, FileEditorAction)
        normalized_path = Path(action.path).resolve()
        return DeclaredResources(keys=(f"file:{normalized_path}",), declared=True)

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState",
    ) -> Sequence["FileEditorTool"]:
        """用 FileEditorExecutor 初始化 FileEditorTool。

        Args:
            conv_state: 要从中获取工作目录的对话状态。
                         如果提供，workspace_root 将从 conv_state.workspace 中获取
        """
        # 在这里导入以避免循环导入
        from openhands.tools.file_editor.impl import FileEditorExecutor

        # 初始化执行器
        executor = FileEditorExecutor(workspace_root=conv_state.workspace.working_dir)

        # 使用条件图像查看支持构建工具描述 Split TOOL_DESCRIPTION 以在第二个项目符号后插
        # 入图像查看行
        #
        description_lines = TOOL_DESCRIPTION.split("\n")
        base_description = "\n".join(description_lines[:2])  # 前两行
        remaining_description = "\n".join(description_lines[2:])  # REST 描述

        # 如果LLM支持视觉，则添加图像查看线
        if conv_state.agent.llm.vision_is_active():
            tool_description = (
                f"{base_description}\n"
                "* If `path` is an image file (.png, .jpg, .jpeg, .gif, .webp, "
                ".bmp), `view` displays the image content\n"
                f"{remaining_description}"
            )
        else:
            tool_description = TOOL_DESCRIPTION

        # 在工具描述中添加工作目录信息，引导智能体使用正确的目录而不是root
        #
        working_dir = conv_state.workspace.working_dir
        enhanced_description = (
            f"{tool_description}\n\n"
            f"Your current working directory is: {working_dir}\n"
            f"When exploring project structure, start with this directory "
            f"instead of the root filesystem."
        )

        # 使用执行器初始化父 Tool
        return [
            cls(
                action_type=FileEditorAction,
                observation_type=FileEditorObservation,
                description=enhanced_description,
                annotations=ToolAnnotations(
                    title="file_editor",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


# 导入此模块时自动注册该工具
register_tool(FileEditorTool.name, FileEditorTool)
