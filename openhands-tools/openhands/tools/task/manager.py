"""任务生命周期管理器。

该模块实现了核心任务编排层。 TaskManager 类负责创建、恢复和运行子智能体任务。 换句话
说，它处理与任务管理相关的所有事情。

与已完成任务相关的对话已持久化存放在临时目录中，确保任务暂停后可以恢复状态。
"""

import shutil
import tempfile
import threading
import uuid
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict, Field

from openhands.sdk import Agent
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.response_utils import get_agent_final_response
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.conversation.types import TraceMetadataValue
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.hooks.config import HookConfig
from openhands.sdk.logger import get_logger
from openhands.sdk.observability.laminar import detached_delegate_context
from openhands.sdk.security import ConfirmationPolicyBase
from openhands.sdk.subagent.registry import AgentFactory, get_agent_factory
from openhands.sdk.subagent.scope import (
    SubAgentScope,
    inherit_mcp_config,
    scope_delegation_tools,
)


if TYPE_CHECKING:
    from openhands.sdk.event import ActionEvent

ConfirmationHandler = Callable[[str, list["ActionEvent"]], bool]


logger = get_logger(__name__)

_SUBAGENTS_DIR: Final[str] = "subagents"


class TaskStatus(StrEnum):
    """表示任务的生命周期状态。"""

    RUNNING = "running"
    """该任务当前正在由智能体处理。"""

    COMPLETED = "completed"
    """任务成功完成并返回有效结果或响应。"""

    ERROR = "error"
    """由于未处理的异常或系统故障，任务未能完成。"""


class Task(BaseModel):
    """代表一个任务。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(description="Unique identifier of the task.")
    status: TaskStatus = Field(description="Task status.")
    conversation_id: uuid.UUID = Field(
        description="Conversation ID. Used to identify the conversation."
    )
    result: str | None = Field(default=None, description="Result of the task.")
    error: str | None = Field(default=None, description="Error if task failed.")
    conversation: LocalConversation | None = Field(
        default=None,
        exclude=True,
        description="Conversation state of the task.",
    )

    def set_result(self, result: str) -> None:
        """将任务设置为成功。"""
        self.result = result
        self.error = None
        self.status = TaskStatus.COMPLETED

    def set_error(self, error: str) -> None:
        """将任务设置为因错误而失败。"""
        self.error = error
        self.result = None
        self.status = TaskStatus.ERROR


class TaskManager:
    """Manage 子智能体 tasks."""

    def __init__(
        self,
        confirmation_handler: ConfirmationHandler | None = None,
        sub_agent_scope: SubAgentScope | None = None,
    ):
        self._parent_conversation: LocalConversation | None = None
        self._confirmation_handler = confirmation_handler
        self._sub_agent_scope = sub_agent_scope or SubAgentScope()

        self._tasks: dict[str, Task] = {}
        self._tasks_lock = threading.Lock()

        # 在 _ensure_parent 中设置一次：当父级持续存在时，使用父级的子智能体目录，否则使
        # 用临时目录。
        #
        self._persistence_dir: Path | None = None

    def attach_parent(self, conversation: LocalConversation) -> None:
        """附加用于创建子智能体任务的父对话。

        Idempotent: 如果已附加父级对话，则后续
        具有相同对话的呼叫没有效果。 带有不同对话的呼叫也被忽略，但会记录警告，以显示
        两个子系统尝试注册不同父节点时可能存在的潜在编程错误。
        """
        if (
            self._parent_conversation is not None
            and self._parent_conversation is not conversation
        ):
            logger.warning(
                "attach_parent called with a different conversation; ignoring."
            )
        self._ensure_parent(conversation)

    def _ensure_parent(self, conversation: LocalConversation) -> None:
        if self._parent_conversation is None:
            self._parent_conversation = conversation
            parent_persistence_dir = conversation.state.persistence_dir
            if parent_persistence_dir is not None:
                self._persistence_dir = Path(parent_persistence_dir) / _SUBAGENTS_DIR
                self._persistence_dir.mkdir(parents=True, exist_ok=True)
            else:
                self._persistence_dir = Path(
                    tempfile.mkdtemp(prefix="openhands_tasks_")
                )

    @property
    def parent_conversation(self) -> LocalConversation:
        if self._parent_conversation is None:
            raise RuntimeError(
                "Parent conversation not set. This should be set automatically "
                "on the first call to the executor."
            )
        return self._parent_conversation

    def _generate_ids(self) -> tuple[str, uuid.UUID]:
        """生成唯一的任务 ID 和对话 ID。"""
        task_number = len(self._tasks) + 1
        task_id = f"task_{task_number:08x}"
        uuid_ = uuid.uuid4()
        return task_id, uuid_

    def _evict_task(self, task: Task) -> None:
        if task.conversation:
            task.conversation.pause()
            task.conversation.close()
        with self._tasks_lock:
            self._tasks[task.id] = task.model_copy(update={"conversation": None})

    def start_task(
        self,
        prompt: str,
        subagent_type: str = "default",
        resume: str | None = None,
        description: str | None = None,
        conversation: LocalConversation | None = None,
    ) -> Task:
        """启动阻塞子智能体任务。

        Args:
            prompt: 子智能体的任务描述。
            subagent_type: 要使用的智能体类型。
            resume: 要恢复的任务 ID（继续现有对话）。
            description: 任务的短标签。
            conversation: 家长对话（在第一次通话时设置）。

        Returns:
            TaskState 最终结果。
        """
        if conversation:
            self._ensure_parent(conversation)

        if resume:
            task = self._resume_task(
                resume=resume,
                subagent_type=subagent_type,
            )
        else:
            task = self._create_task(
                subagent_type=subagent_type,
                description=description,
            )

        return self._run_task(
            task=task,
            prompt=prompt,
        )

    def _resume_task(self, resume: str, subagent_type: str) -> Task:
        """恢复子智能体任务。"""
        with self._tasks_lock:
            if resume not in self._tasks:
                raise ValueError(
                    f"Task '{resume}' not found. "
                    f"Available tasks: {', '.join(sorted(self._tasks))}"
                )

            factory = get_agent_factory(subagent_type)
            worker_agent = self._get_sub_agent_from_factory(factory)
            conversation_id = self._tasks[resume].conversation_id
            with detached_delegate_context() as link:
                conversation = LocalConversation(
                    agent=worker_agent,
                    workspace=self.parent_conversation.state.workspace.working_dir,
                    persistence_dir=self._persistence_dir,
                    conversation_id=conversation_id,
                    hook_config=factory.definition.hooks,
                    _parent_llm_call_context=(
                        self.parent_conversation.get_llm_call_context()
                    ),
                    mcp_tool_provider=self.parent_conversation._mcp_tool_provider,
                    _mcp_config_from_parent=True,
                    delete_on_close=True,
                    observability_metadata=self._delegate_observability_metadata(
                        task_id=resume, subagent_type=subagent_type, link=link
                    ),
                    observability_tags=["delegate"],
                )

            self._set_confirmation_policy(
                conversation,
                factory.definition.get_confirmation_policy(),
            )

            self._tasks[resume] = self._tasks[resume].model_copy(
                update={
                    "conversation": conversation,
                    "status": TaskStatus.RUNNING,
                }
            )

            return self._tasks[resume]

    def _create_task(
        self,
        subagent_type: str,
        description: str | None,
    ) -> Task:
        """创建一个新任务。

        迭代限制按以下优先级解决：
        1. ``factory.definition.max_iteration_per_run``（来自智能体定义）
        2. 家长对话的 ``max_iteration_per_run``
        """
        factory = get_agent_factory(subagent_type)
        worker_agent = self._get_sub_agent_from_factory(factory)

        effective_max_iter = (
            factory.definition.max_iteration_per_run
            if factory.definition.max_iteration_per_run
            else self.parent_conversation.max_iteration_per_run
        )
        # 子智能体预算：定义值，否则继承父级的。
        effective_max_budget = (
            factory.definition.max_budget_per_run
            or self.parent_conversation.max_budget_per_run
        )

        with self._tasks_lock:
            task_id, conversation_id = self._generate_ids()

            sub_conversation = self._get_conversation(
                description=description,
                max_iteration_per_run=effective_max_iter,
                max_budget_per_run=effective_max_budget,
                task_id=task_id,
                subagent_type=subagent_type,
                worker_agent=worker_agent,
                conversation_id=conversation_id,
                hook_config=factory.definition.hooks,
            )

            self._set_confirmation_policy(
                sub_conversation,
                factory.definition.get_confirmation_policy(),
            )

            self._tasks[task_id] = Task(
                id=task_id,
                conversation_id=conversation_id,
                conversation=sub_conversation,
                status=TaskStatus.RUNNING,
            )
            return self._tasks[task_id]

    def _get_conversation(
        self,
        description: str | None,
        max_iteration_per_run: int,
        task_id: str,
        subagent_type: str,
        conversation_id: uuid.UUID,
        worker_agent: Agent,
        hook_config: HookConfig | None = None,
        max_budget_per_run: float | None = None,
    ) -> LocalConversation:
        parent = self.parent_conversation
        parent_visualizer = parent._visualizer

        visualizer = None
        if parent_visualizer is not None:
            label = description or task_id
            visualizer = parent_visualizer.create_sub_visualizer(label)

        with detached_delegate_context() as link:
            return LocalConversation(
                agent=worker_agent,
                workspace=parent.state.workspace.working_dir,
                visualizer=visualizer,
                persistence_dir=self._persistence_dir,
                conversation_id=conversation_id,
                max_iteration_per_run=max_iteration_per_run,
                max_budget_per_run=max_budget_per_run,
                hook_config=hook_config,
                _parent_llm_call_context=parent.get_llm_call_context(),
                mcp_tool_provider=parent._mcp_tool_provider,
                _mcp_config_from_parent=True,
                delete_on_close=True,
                prompt_cache_key=str(parent.state.id),
                observability_metadata=self._delegate_observability_metadata(
                    task_id=task_id, subagent_type=subagent_type, link=link
                ),
                observability_tags=["delegate"],
            )

    def _delegate_observability_metadata(
        self,
        task_id: str,
        subagent_type: str,
        link: dict[str, TraceMetadataValue],
    ) -> dict[str, TraceMetadataValue]:
        """跟踪标识委托对话与其任务的元数据。

        ``link`` 是由以下方式产生的父踪迹链接
        ``detached_delegate_context`` (``delegate.parent_trace_id``/
        ``delegate.parent_span_id``/``tool_call_id``，尽力而为）。
        """
        return {
            "is_delegate": True,
            "task_id": task_id,
            "subagent_type": subagent_type,
            "parent_session_id": str(self.parent_conversation.state.id),
            **link,
        }

    def _get_sub_agent(self, subagent_type: str) -> Agent:
        """返回分配给任务的子智能体。

        Raises:
            ValueError: 如果子智能体类型无效。
        """
        factory = get_agent_factory(subagent_type)
        return self._get_sub_agent_from_factory(factory)

    def _get_sub_agent_from_factory(self, factory: "AgentFactory") -> Agent:
        """从 AgentFactory 创建子智能体。"""
        parent = self.parent_conversation
        parent_llm = parent.agent.llm

        llm_updates: dict = {"stream": False}
        sub_agent_llm = parent_llm.model_copy(update=llm_updates)
        # 重置指标，使子智能体拥有自己的 Metrics 对象
        #
        sub_agent_llm.reset_metrics()

        sub_agent = factory.factory_func(sub_agent_llm)

        if self._sub_agent_scope.restricts and not isinstance(sub_agent, Agent):
            raise ValueError(
                f"Agent '{factory.definition.name}' runs as "
                f"{type(sub_agent).__name__}, whose tools cannot be checked."
            )
        missing = self._sub_agent_scope.missing_from(parent.agent, sub_agent)
        if missing:
            raise ValueError(
                f"Agent '{factory.definition.name}' uses {', '.join(missing)}, "
                "which this agent does not have."
            )

        # 确保子智能体 LLM 已停用流
        sub_agent = inherit_mcp_config(parent.agent, sub_agent).model_copy(
            update={
                "llm": sub_agent.llm.model_copy(update={"stream": False}),
                "tools": scope_delegation_tools(sub_agent.tools, self._sub_agent_scope),
            }
        )
        return sub_agent

    def _run_task(self, task: Task, prompt: str) -> Task:
        """同步运行任务。"""
        if task.conversation is None:
            raise RuntimeError(f"Task '{task.id}' has no conversation to run.")
        # 获取发件人信息的父姓名
        parent_name = None
        parent = self.parent_conversation
        if hasattr(parent, "_visualizer") and parent._visualizer is not None:
            parent_name = getattr(parent._visualizer, "_name", None)

        try:
            task.conversation.send_message(prompt, sender=parent_name)
            self._run_until_finished(task.id, task.conversation)
            status = task.conversation.state.execution_status
            if status == ConversationExecutionStatus.FINISHED:
                result = get_agent_final_response(task.conversation.state.events)
                task.set_result(result)
                logger.info(f"Task '{task.id}' completed.")
            else:
                # 任何非 FINISHED 终端状态（运行限制、卡住、暂停等）都会显示为错误，而不
                # 是空的“已完成”； 详细信息保留部分输出，以便父级可以使用/重试它。
                #
                task.set_error(self._run_stop_detail(task.conversation, status))
                logger.warning(f"Task '{task.id}' stopped: status '{status.value}'.")
        except Exception as e:
            task.set_error(str(e))
            logger.warning(f"Task {task.id} failed with error: {e}")
        finally:
            self._update_parent_metrics(parent, task)
            self._evict_task(task)

        return task

    @staticmethod
    def _run_stop_detail(
        conversation: LocalConversation,
        status: ConversationExecutionStatus,
    ) -> str:
        """为什么子智能体没有完成就停止了（运行限制、卡住、暂停……），
        加上任何部分输出，这样父级就不会毫无用处。"""
        errors = [
            e
            for e in conversation.state.events
            if isinstance(e, ConversationErrorEvent)
        ]
        reason = (
            errors[-1].detail
            if errors
            else f"Sub-agent stopped without finishing (status: {status.value})."
        )
        partial = get_agent_final_response(conversation.state.events)
        return f"{reason}\nPartial result:\n{partial}" if partial else reason

    def _run_until_finished(
        self, task_id: str, conversation: LocalConversation
    ) -> None:
        """运行子智能体对话直至完成，处理确认。"""
        conversation.run()
        while (
            conversation.state.execution_status
            == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
        ):
            pending = ConversationState.get_unmatched_actions(conversation.state.events)
            if not pending:
                break

            if self._confirmation_handler is None or self._confirmation_handler(
                task_id, pending
            ):
                conversation.run()
            else:
                conversation.reject_pending_actions("User rejected the actions")
                conversation.run()

    def _set_confirmation_policy(
        self,
        conversation: LocalConversation,
        confirmation_policy: ConfirmationPolicyBase | None,
    ) -> None:
        """
        应用permission_mode：从定义中显式模式或在None时继承父级策略。
        """
        if confirmation_policy is None:
            conversation.set_confirmation_policy(
                self.parent_conversation.state.confirmation_policy
            )
        else:
            conversation.set_confirmation_policy(confirmation_policy)

    def _update_parent_metrics(self, parent: LocalConversation, task: Task) -> None:
        """
        同步子智能体在驱逐破坏对话之前进入父级的指标。 替换（不是合并），因为子智能体
        指标是跨简历累积的。
        """
        if task.conversation is not None:
            parent.conversation_stats.usage_to_metrics[f"task:{task.id}"] = (
                task.conversation.conversation_stats.get_combined_metrics()
            )

    def close(self) -> None:
        """清理临时目录（如果使用）并删除所有创建的任务。"""
        # 仅在使用临时目录时进行清理（父目录没有持久化）。 当父级持续存在时，子智能体数
        # 据位于其目录下。
        #
        parent_persists = (
            self._parent_conversation is not None
            and self._parent_conversation.state.persistence_dir is not None
        )
        if (
            not parent_persists
            and self._persistence_dir is not None
            and self._persistence_dir.exists()
        ):
            shutil.rmtree(self._persistence_dir, ignore_errors=True)

        with self._tasks_lock:
            self._tasks.clear()
