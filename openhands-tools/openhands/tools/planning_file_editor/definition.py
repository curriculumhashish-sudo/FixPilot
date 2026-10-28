"""规划文件编辑器工具 - 将只读查看与 PLAN.md 编辑结合起来。"""

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState

from openhands.sdk.logger import get_logger
from openhands.sdk.tool import (
    ToolAnnotations,
    ToolDefinition,
    register_tool,
)
from openhands.tools.file_editor.definition import (
    TOOL_DESCRIPTION as FILE_EDITOR_TOOL_DESCRIPTION,
    FileEditorAction,
    FileEditorObservation,
)


logger = get_logger(__name__)

# 默认配置目录和计划文件名 PLAN.md 现在存储在 .agents_tmp/ 中，以保持工作区根目录干净并
# 将智能体临时文件与用户内容分开
#
DEFAULT_CONFIG_DIR = ".agents_tmp"
PLAN_FILENAME = "PLAN.md"


class PlanningFileEditorAction(FileEditorAction):
    """模式用于规划文件编辑器操作。

    继承自 FileEditorAction，但仅限编辑 PLAN.md。 允许查看任何文件，但只能编辑
    PLAN.md。
    """


class PlanningFileEditorObservation(FileEditorObservation):
    """观测结果来自规划文件编辑器的操作。

    继承自 FileEditorObservation - 结构相同，只是类型不同。
    """


TOOL_DESCRIPTION = (
    FILE_EDITOR_TOOL_DESCRIPTION
    + """

IMPORTANT RESTRICTION FOR PLANNING AGENT:
* You can VIEW any file in the workspace using the 'view' command
* You can ONLY EDIT the PLAN.md file (all other edit operations will be rejected)
* PLAN.md is automatically initialized with section headers at the configured
  plan path (by default, .agents_tmp/PLAN.md under the workspace root)
* All editing commands (create, str_replace, insert, undo_edit) are restricted to PLAN.md only
* The PLAN.md file already contains the required section structure - you just need to fill in the content
"""  # noqa
)


class PlanningFileEditorTool(
    ToolDefinition[PlanningFileEditorAction, PlanningFileEditorObservation]
):
    """具有只读、仅限 edit-PLAN.md 访问权限的规划文件编辑器工具。"""

    user_selectable: ClassVar[bool] = False

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState",
        plan_path: str | None = None,
    ) -> Sequence["PlanningFileEditorTool"]:
        """初始化PlanningFileEditorTool。

        Args:
            conv_state: 要从中获取工作目录的对话状态。
            plan_path: PLAN.md 文件的可选绝对路径。 如果没有提供，
                默认为{working_dir}/.agents_tmp/PLAN.md.

        Raises:
            ValueError: 如果提供了 plan_path 但不是绝对路径。
        """
        # 在这里导入以避免循环导入
        from openhands.tools.planning_file_editor.impl import (
            PlanningFileEditorExecutor,
        )

        working_dir = conv_state.workspace.working_dir

        # 验证 plan_path 是绝对的（如果提供）
        if plan_path is not None and not Path(plan_path).is_absolute():
            raise ValueError(f"plan_path must be an absolute path, got: {plan_path}")

        # 使用提供的 plan_path 或回退到工作区根处的 .agents_tmp/PLAN.md
        if plan_path is None:
            workspace_root = Path(working_dir).resolve()

            # 检查工作区根目录下的旧版 PLAN.md
            legacy_plan_path = workspace_root / PLAN_FILENAME
            if legacy_plan_path.exists():
                # 使用向后兼容性的旧位置
                new_recommended_path = (
                    workspace_root / DEFAULT_CONFIG_DIR / PLAN_FILENAME
                )
                logger.warning(
                    f"Found PLAN.md at legacy location {legacy_plan_path}. "
                    f"Consider moving it to {new_recommended_path} "
                    f"for consistency with OpenHands conventions."
                )
                plan_path = str(legacy_plan_path)
            else:
                # 使用新的默认位置
                plan_path = str(workspace_root / DEFAULT_CONFIG_DIR / PLAN_FILENAME)

        # 如果 PLAN.md 不存在，则使用标头初始化
        plan_file = Path(plan_path)
        if not plan_file.exists():
            # 在这里导入以避免循环导入
            from openhands.tools.preset.planning import get_plan_headers

            # 确保父目录存在
            plan_file.parent.mkdir(parents=True, exist_ok=True)
            plan_file.write_text(get_plan_headers())
            logger.info(f"Created new PLAN.md at {plan_path}")

        # 创建执行器，其编辑权限仅限于 PLAN.md
        executor = PlanningFileEditorExecutor(
            workspace_root=working_dir,
            plan_path=plan_path,
        )

        # 在工具描述中添加工作目录信息
        enhanced_description = (
            f"{TOOL_DESCRIPTION}\n\n"
            f"Your current working directory: {working_dir}\n"
            f"Your PLAN.md location: {plan_path}\n"
            f"This plan file will be accessible to other agents in the workflow."
        )

        return [
            cls(
                description=enhanced_description,
                action_type=PlanningFileEditorAction,
                observation_type=PlanningFileEditorObservation,
                annotations=ToolAnnotations(
                    title="planning_file_editor",
                    readOnlyHint=False,  # 可以编辑PLAN.md
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


# 导入此模块时自动注册该工具
register_tool(PlanningFileEditorTool.name, PlanningFileEditorTool)
