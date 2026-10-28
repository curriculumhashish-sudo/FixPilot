import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal, get_args

from pydantic import BaseModel, Field, ValidationError, field_validator


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation
    from openhands.sdk.conversation.state import ConversationState

from rich.text import Text

from openhands.sdk.logger import get_logger
from openhands.sdk.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)


logger = get_logger(__name__)

# 任务跟踪器状态的类型别名
TaskTrackerStatusType = Literal["todo", "in_progress", "done"]

# 在其他智能体' 待办事项工具上训练的模型会发送这些名称来表示我们的状态。
_STATUS_ALIASES: dict[str, TaskTrackerStatusType] = {
    "pending": "todo",
    "to_do": "todo",
    "completed": "done",
    "complete": "done",
}


class TaskItem(BaseModel):
    title: str = Field(..., description="A brief title for the task.")
    notes: str = Field("", description="Additional details or notes about the task.")
    status: TaskTrackerStatusType = Field(
        "todo",
        description="The current status of the task. "
        "One of 'todo', 'in_progress', or 'done'.",
    )

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in get_args(TaskTrackerStatusType):
            return normalized
        return _STATUS_ALIASES.get(normalized, value)


class TaskTrackerAction(Action):
    """智能体写入或更新任务列表以进行任务管理的操作。"""

    command: Literal["view", "plan"] = Field(
        default="view",
        description="The command to execute. `view` shows the current task list. `plan` creates or updates the task list based on provided requirements and progress. Always `view` the current list before making changes.",  # noqa: E501
    )
    task_list: list[TaskItem] = Field(
        default_factory=list,
        description="The full task list. Required parameter of `plan` command.",
    )

    @property
    def visualize(self) -> Text:
        """返回具有任务管理样式的富文本表示形式。"""
        content = Text()

        # 添加带有图标的命令标题
        if self.command == "view":
            content.append("👀 ", style="blue")
            content.append("View Task List", style="blue")
        else:  # 计划
            content.append("📋 ", style="green")
            content.append("Update Task List", style="green")

        # 如果有计划，则显示任务数
        if self.command == "plan" and self.task_list:
            content.append(f" ({len(self.task_list)} tasks)")

        return content


class TaskTrackerObservation(Observation):
    """该数据类表示任务跟踪操作的结果。"""

    command: Literal["view", "plan"] = Field(
        description='The command that was executed: "view" or "plan".'
    )
    task_list: list[TaskItem] = Field(
        default_factory=list, description="The current task list"
    )

    @property
    def visualize(self) -> Text:
        """返回具有任务列表格式的富文本表示形式。"""
        text = Text()

        if self.is_error:
            text.append("❌ ", style="red bold")
            text.append(self.ERROR_MESSAGE_HEADER, style="bold red")

        if self.task_list:
            # 按状态计数任务
            todo_count = sum(1 for task in self.task_list if task.status == "todo")
            in_progress_count = sum(
                1 for task in self.task_list if task.status == "in_progress"
            )
            done_count = sum(1 for task in self.task_list if task.status == "done")

            # 显示状态摘要
            if self.command == "plan":
                text.append("✅ ", style="green")
                text.append("Task list updated: ", style="green")
            else:  # 查看命令
                text.append("📋 ", style="blue")
                text.append("Current task list: ", style="blue")

            # 状态计数
            status_parts = []
            if todo_count:
                status_parts.append(f"{todo_count} todo")
            if in_progress_count:
                status_parts.append(f"{in_progress_count} in progress")
            if done_count:
                status_parts.append(f"{done_count} done")

            if status_parts:
                text.append(", ".join(status_parts), style="white")
                text.append("\n\n")

            # 显示实际任务列表
            for i, task in enumerate(self.task_list, 1):
                # 状态图标
                if task.status == "done":
                    text.append("✅ ", style="green")
                elif task.status == "in_progress":
                    text.append("🔄 ", style="yellow")
                else:  # 待办事项
                    text.append("⏳ ", style="blue")

                # 任务标题
                text.append(f"{i}. {task.title}", style="white")

                # NEW：在标题下显示注释（如果存在）
                if task.notes:
                    text.append("\n   Notes: " + task.notes, style="italic")

                if i < len(self.task_list):
                    text.append("\n")
        else:
            text.append("📝 ", style="blue")
            text.append("Task list is empty")

        return text


class TaskTrackerExecutor(ToolExecutor[TaskTrackerAction, TaskTrackerObservation]):
    """任务跟踪器工具的执行器。"""

    save_dir: Path | None

    def __init__(self, save_dir: str | None = None):
        """初始化TaskTrackerExecutor。

        Args:
            save_dir: 用于保存任务的可选目录。 如果提供，任务将是
                     已持久化至save_dir/TASKS.md
        """
        self.save_dir = Path(save_dir) if save_dir else None
        logger.info(f"TaskTrackerExecutor initialized with save_dir: {self.save_dir}")
        self._task_list: list[TaskItem] = []

        # 如果提供了 save_dir 并且文件存在，则加载现有任务
        if self.save_dir:
            self._load_tasks()

    def __call__(
        self,
        action: TaskTrackerAction,
        conversation: "LocalConversation | None" = None,  # noqa: ARG002
    ) -> TaskTrackerObservation:
        """执行任务跟踪器操作。"""
        if action.command == "plan":
            # 更新任务列表
            self._task_list = action.task_list
            # 如果提供 save_dir，则保存到文件
            if self.save_dir:
                self._save_tasks()
            return TaskTrackerObservation.from_text(
                text=(
                    f"Task list has been updated with {len(self._task_list)} item(s)."
                ),
                command=action.command,
                task_list=self._task_list,
            )
        elif action.command == "view":
            # 返回当前任务列表
            if not self._task_list:
                return TaskTrackerObservation.from_text(
                    text=('No task list found. Use the "plan" command to create one.'),
                    command=action.command,
                    task_list=[],
                )
            content = self._format_task_list(self._task_list)
            return TaskTrackerObservation.from_text(
                text=content,
                command=action.command,
                task_list=self._task_list,
            )
        else:
            return TaskTrackerObservation.from_text(
                text=(
                    f"Unknown command: {action.command}. "
                    'Supported commands are "view" and "plan".'
                ),
                is_error=True,
                command=action.command,
                task_list=[],
            )

    def _format_task_list(self, task_list: list[TaskItem]) -> str:
        """设置任务列表的格式以供显示。"""
        if not task_list:
            return "No tasks in the list."

        content = "# Task List\n\n"
        for i, task in enumerate(task_list, 1):
            status_icon = {"todo": "⏳", "in_progress": "🔄", "done": "✅"}.get(
                task.status, "⏳"
            )

            title = task.title
            notes = task.notes

            content += f"{i}. {status_icon} {title}\n"
            if notes:
                content += f"   {notes}\n"
            content += "\n"

        return content.strip()

    def _load_tasks(self) -> None:
        """从 TASKS.json 文件加载任务（如果存在）。"""
        if not self.save_dir:
            return

        tasks_file = self.save_dir / "TASKS.json"
        if not tasks_file.exists():
            return

        try:
            with open(tasks_file, encoding="utf-8") as f:
                self._task_list = [TaskItem.model_validate(d) for d in json.load(f)]
        except (OSError, json.JSONDecodeError, TypeError, ValidationError) as e:
            logger.warning(
                f"Failed to load tasks from {tasks_file}: {e}. Starting with "
                "an empty task list."
            )
            self._task_list = []

    def _save_tasks(self) -> None:
        """将任务保存到 TASKS.json 文件。"""
        if not self.save_dir:
            return

        tasks_file = self.save_dir / "TASKS.json"
        try:
            # 如果目录不存在则创建
            self.save_dir.mkdir(parents=True, exist_ok=True)

            with open(tasks_file, "w", encoding="utf-8") as f:
                json.dump([task.model_dump() for task in self._task_list], f, indent=2)
        except OSError as e:
            logger.warning(f"Failed to save tasks to {tasks_file}: {e}")
            pass


# 工具定义及详细说明
TASK_TRACKER_DESCRIPTION = """This tool provides structured task management capabilities for development workflows.
It enables systematic tracking of work items, progress monitoring, and efficient
organization of complex development activities.

The tool maintains visibility into project status and helps communicate
progress effectively to users.

## Application Guidelines

Utilize this tool in the following situations:

1. Multi-phase development work - When projects involve multiple sequential or
   parallel activities
2. Complex implementation tasks - Work requiring systematic planning and
   coordination across multiple components
3. Explicit user request for task organization - When users specifically ask
   for structured task management
4. Multiple concurrent requirements - When users present several work items
   that need coordination
5. Project initiation - Capture and organize user requirements at project start
6. Work commencement - Update task status to in_progress before beginning
   implementation. Maintain focus by limiting active work to one task
7. Task completion - Update status to done and identify any additional work
   that emerged during implementation

## Situations Where Tool Usage Is Unnecessary

Avoid using this tool when:

1. Single atomic tasks that require no decomposition
2. Trivial operations where tracking adds no organizational value
3. Simple activities completable in minimal steps
4. Pure information exchange or discussion

Note: For single straightforward tasks, proceed with direct implementation
rather than creating tracking overhead.

## Usage Scenarios

**Scenario A: Feature Development with Validation**
User request: "Build a user authentication system with login/logout functionality.
Don't forget to include input validation and error handling!"

Response approach: I'll implement a user authentication system with comprehensive
validation. Let me organize this work systematically.

*Task breakdown includes:*
1. Design authentication API endpoints and data models
2. Implement user login/logout controllers with session management
3. Add client-side form validation and error display
4. Create backend input sanitization and security checks
5. Implement comprehensive error handling for edge cases
6. Perform integration testing and fix any issues

**Scenario B: Codebase Refactoring**
User request: "I need to update all instances of the method 'fetchData' to
'retrieveInformation' throughout the entire project"

Response approach: Let me first analyze your codebase to identify all locations
where 'fetchData' appears.

*After code analysis*

I've located 12 occurrences of 'fetchData' across 6 files in your project.
I'll create a systematic plan to update these references.

*Organized task list includes specific file-by-file updates*

**Scenario C: Multi-feature Development**
User request: "Set up a blog platform with these components: admin dashboard,
article management, comment system, and user profiles."

Response approach: I'll help build your blog platform. Let me break down these
components into manageable implementation phases.

*Creates structured plan with each feature decomposed into specific development tasks*

## Counter-examples - Direct Implementation Preferred

**Counter-example A: Simple inquiry**
User request: "What's the syntax for a for loop in JavaScript?"

Response approach: Here's how to write a for loop in JavaScript:

```javascript
for (let i = 0; i < array.length; i++) {
    console.log(array[i]);
}
```

*No task tracking needed - single informational response*

**Counter-example B: Minor modification**
User request: "Please add a docstring to the processPayment function explaining
its parameters."

Response approach: I'll add a docstring to explain the processPayment function.

*Direct edit without task tracking for simple modification*

## Status Management and Workflow

1. **Status Values**: Track work using these states:
   - todo: Not yet initiated
   - in_progress: Currently active (maintain single focus)
   - done: Successfully completed

2. **Workflow Practices**:
   - Update status dynamically as work progresses
   - Mark completion immediately upon task finish
   - Limit active work to ONE task at any given time
   - Complete current activities before initiating new ones
   - Remove obsolete tasks from tracking entirely

3. **Completion Criteria**:
   - Mark tasks as done only when fully achieved
   - Keep status as in_progress if errors, blocks, or partial completion exist
   - Create new tasks for discovered issues or dependencies
   - Never mark done when:
       - Test suites are failing
       - Implementation remains incomplete
       - Unresolved errors persist
       - Required resources are unavailable

4. **Task Organization**:
   - Write precise, actionable descriptions
   - Decompose complex work into manageable units
   - Use descriptive, clear naming conventions

When uncertain, favor using this tool. Proactive task management demonstrates
systematic approach and ensures comprehensive requirement fulfillment."""  # noqa: E501


class TaskTrackerTool(ToolDefinition[TaskTrackerAction, TaskTrackerObservation]):
    """自动初始化 TaskTrackerExecutor 的 ToolDefinition 子类。"""  # noqa: E501

    catalog_description: ClassVar[str] = (
        "Keep a running task list to organise multi-step work."
    )
    conversation_local: ClassVar[bool] = True

    @classmethod
    def create(cls, conv_state: "ConversationState") -> Sequence["TaskTrackerTool"]:
        """用 TaskTrackerExecutor 初始化 TaskTrackerTool。

        Args:
            conv_state: 从中获取持久化目录的对话状态。
                         如果提供，save_dir 将从 conv_state.persistence_dir 中获取
        """
        executor = TaskTrackerExecutor(save_dir=conv_state.persistence_dir)

        # 使用执行器初始化父 Tool
        return [
            cls(
                description=TASK_TRACKER_DESCRIPTION,
                action_type=TaskTrackerAction,
                observation_type=TaskTrackerObservation,
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


# 导入此模块时自动注册该工具
register_tool(TaskTrackerTool.name, TaskTrackerTool)
