"""实施规划文件编辑器工具。"""

from typing import TYPE_CHECKING

from openhands.sdk.tool import ToolExecutor


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation
from openhands.tools.file_editor.definition import FileEditorAction
from openhands.tools.file_editor.impl import FileEditorExecutor
from openhands.tools.planning_file_editor.definition import (
    PlanningFileEditorAction,
    PlanningFileEditorObservation,
)


class PlanningFileEditorExecutor(ToolExecutor):
    """包装 FileEditorExecutor 的规划文件编辑器的执行器。"""

    def __init__(self, workspace_root: str, plan_path: str):
        """初始化执行器。

        Args:
            workspace_root: 文件操作的根目录
            plan_path: PLAN.md 文件的绝对路径
        """
        self.file_editor_executor: FileEditorExecutor = FileEditorExecutor(
            workspace_root=workspace_root,
            allowed_edits_files=[plan_path],
        )

    def __call__(
        self,
        action: PlanningFileEditorAction,
        conversation: "LocalConversation | None" = None,  # noqa: ARG002
    ) -> PlanningFileEditorObservation:
        """执行计划文件编辑器操作。

        Args:
            action: 要执行的计划文件编辑器操作

        Returns:
            PlanningFileEditorObservation 结果
        """
        # 将 PlanningFileEditorAction 转换为 FileEditorAction
        file_editor_action = FileEditorAction(
            command=action.command,
            path=action.path,
            file_text=action.file_text,
            old_str=action.old_str,
            new_str=action.new_str,
            insert_line=action.insert_line,
            view_range=action.view_range,
        )

        # 用FileEditorExecutor执行
        file_editor_obs = self.file_editor_executor(file_editor_action)

        # 将 FileEditorObservation 转换为 PlanningFileEditorObservation
        return PlanningFileEditorObservation(
            command=action.command,
            content=file_editor_obs.content,
            is_error=file_editor_obs.is_error,
            path=file_editor_obs.path,
        )
