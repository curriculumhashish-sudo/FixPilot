"""任务工具执行器。

该模块包含TaskExecutor类，它充当工具接口和TaskManager之间的桥梁。 它将 TaskAction 转
换为阻塞子智能体执行，并返回包含任务结果或错误的
TaskObservation。
"""

from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.logger import get_logger
from openhands.sdk.tool.tool import ToolExecutor
from openhands.tools.task.definition import TaskAction, TaskObservation
from openhands.tools.task.manager import TaskManager, TaskStatus


logger = get_logger(__name__)


class TaskExecutor(ToolExecutor):
    """任务工具的执行器（仅限阻塞）。"""

    def __init__(self, manager: TaskManager):
        self._manager = manager

    def __call__(
        self,
        action: TaskAction,
        conversation: LocalConversation | None = None,
    ) -> TaskObservation:
        try:
            task = self._manager.start_task(
                prompt=action.prompt,
                subagent_type=action.subagent_type,
                description=action.description,
                resume=action.resume,
                conversation=conversation,
            )
            match task.status:
                case TaskStatus.COMPLETED:
                    return TaskObservation.from_text(
                        text=task.result or "Task completed with no result.",
                        task_id=task.id,
                        subagent=action.subagent_type,
                        status=task.status,
                    )
                case TaskStatus.ERROR:
                    return TaskObservation.from_text(
                        text=task.error or "Task failed.",
                        task_id=task.id,
                        subagent=action.subagent_type,
                        status=task.status,
                        is_error=True,
                    )
                case _:
                    # 这永远不应该发生
                    raise RuntimeError(f"Unknown task status: {task.status}")
        except Exception as e:
            logger.error(f"Task execution failed: {e}", exc_info=True)
            return TaskObservation.from_text(
                text=f"Failed to execute task: {str(e)}",
                task_id="unknown",
                subagent=action.subagent_type,
                status="error",
                is_error=True,
            )

    def close(self) -> None:
        self._manager.close()
