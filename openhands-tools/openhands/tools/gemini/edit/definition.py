"""编辑工具定义（Gemini 风格）。"""

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


class EditAction(Action):
    """模式用于编辑操作。"""

    file_path: str = Field(description="The path to the file to modify.")
    old_string: str = Field(
        description=(
            "The text to replace. To create a new file, use an empty string. "
            "Must match the exact text in the file including whitespace."
        )
    )
    new_string: str = Field(description="The text to replace it with.")
    expected_replacements: int = Field(
        default=1,
        ge=0,
        description=(
            "Number of replacements expected. Defaults to 1. "
            "Use when you want to replace multiple occurrences. "
            "The edit will fail if the actual count doesn't match."
        ),
    )


class EditObservation(FileChangeObservation):
    """观测结果来自编辑文件。"""

    file_path: str | None = Field(
        default=None, description="The file path that was edited."
    )
    is_new_file: bool = Field(
        default=False, description="Whether a new file was created."
    )
    replacements_made: int = Field(
        default=0, description="Number of replacements actually made."
    )
    old_content: str | None = Field(
        default=None, description="The content before the edit."
    )
    new_content: str | None = Field(
        default=None, description="The content after the edit."
    )

    def change_summary(self) -> str:
        return f"Edited: {self.file_path} ({self.replacements_made} replacement(s))\n"


TOOL_DESCRIPTION = """Replaces text within a file.

By default, replaces a single occurrence, but can replace multiple occurrences
when `expected_replacements` is specified. The edit will fail if the actual
number of occurrences doesn't match the expected count.

This tool is useful for making targeted changes to files without rewriting
the entire content.

Key behaviors:
- To create a new file: use an empty string for `old_string`
- The `old_string` must match EXACTLY (including whitespace and indentation)
- If 0 occurrences are found, the edit fails with an error
- If the number of occurrences doesn't match `expected_replacements`, the edit fails
- If `old_string` equals `new_string`, no changes are made

Tips for success:
- Include enough context (3-5 lines) to make `old_string` unique
- Use the `read_file` tool first to verify the exact text to replace
- For large changes affecting many lines, consider `write_file` instead

Examples:
- Simple replacement: edit(file_path="test.py", old_string="old text", new_string="new text")
- Create file: edit(file_path="new.py", old_string="", new_string="print('hello')")
- Multiple replacements: edit(file_path="test.py", old_string="foo", new_string="bar", expected_replacements=3)
"""  # noqa: E501


class EditTool(ToolDefinition[EditAction, EditObservation]):
    """通过查找/替换编辑文件的工具。"""

    user_selectable: ClassVar[bool] = False

    def declared_resources(self, action: Action) -> DeclaredResources:
        """锁在目标文件路径上，因此并发编辑为相同
        文件是已序列化，同时对不同文件的编辑并行运行。
        """
        assert isinstance(action, EditAction)
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
    ) -> Sequence["EditTool"]:
        """使用执行器初始化 EditTool。

        Args:
            conv_state: 要从中获取工作目录的对话状态。
        """
        from openhands.tools.gemini.edit.impl import EditExecutor

        executor = EditExecutor(workspace_root=conv_state.workspace.working_dir)

        working_dir = conv_state.workspace.working_dir
        enhanced_description = (
            f"{TOOL_DESCRIPTION}\n\n"
            f"Your current working directory is: {working_dir}\n"
            f"File paths can be absolute or relative to this directory."
        )

        return [
            cls(
                action_type=EditAction,
                observation_type=EditObservation,
                description=enhanced_description,
                annotations=ToolAnnotations(
                    title="edit",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
                executor=executor,
                meta={"workspace_root": working_dir},
            )
        ]


register_tool(EditTool.name, EditTool)
