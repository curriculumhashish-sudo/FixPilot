"""委托工具执行器的实现。"""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Final

from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.response_utils import get_agent_final_response
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.logger import get_logger
from openhands.sdk.subagent import get_agent_factory
from openhands.sdk.subagent.scope import inherit_mcp_config
from openhands.sdk.tool.tool import ToolExecutor
from openhands.tools.delegate.definition import DelegateObservation


if TYPE_CHECKING:
    from openhands.sdk.event import ActionEvent
    from openhands.tools.delegate.definition import DelegateAction

logger = get_logger(__name__)

_SUBAGENTS_DIR: Final[str] = "subagents"

# 当子智能体命中 WAITING_FOR_CONFIRMATION 时调用。 接收(agent_id, pending_actions)并返回
# True以批准，返回False以拒绝。
#
ConfirmationHandler = Callable[[str, list["ActionEvent"]], bool]


class DelegateExecutor(ToolExecutor):
    """委托操作的执行者。

    该类处理：
    - 使用有意义的字符串标识符生成子智能体 (e.g., 'refactor_module')
    - 将任务委托给子智能体并等待结果（阻塞）
    """

    def __init__(
        self,
        max_children: int = 5,
        confirmation_handler: ConfirmationHandler | None = None,
    ):
        self._parent_conversation: LocalConversation | None = None
        # 从用户友好的标识符映射到对话
        self._sub_agents: dict[str, LocalConversation] = {}
        self._max_children: int = max_children
        self._confirmation_handler = confirmation_handler

    @property
    def parent_conversation(self) -> LocalConversation:
        """获取家长对话。

        Raises:
            RuntimeError: 如果尚未设置家长对话。
        """
        if self._parent_conversation is None:
            raise RuntimeError(
                "Parent conversation not set. This should be set automatically "
                "on the first call to the executor."
            )
        return self._parent_conversation

    def __call__(  # type: ignore[override]
        self, action: "DelegateAction", conversation: LocalConversation
    ) -> DelegateObservation:
        """执行生成或委托操作。"""
        if self._parent_conversation is None:
            self._parent_conversation = conversation

        # 根据命令路由到适当的处理程序
        if action.command == "spawn":
            return self._spawn_agents(action)
        elif action.command == "delegate":
            return self._delegate_tasks(action)
        else:
            return DelegateObservation.from_text(
                text=(
                    f"Unsupported command: {action.command}. "
                    "Available commands: spawn, delegate"
                ),
                command=action.command,
                is_error=True,
            )

    @staticmethod
    def _format_agent_label(agent_id: str, agent_type: str) -> str:
        """为日志记录和用户消息编写友好的标签。"""
        type_suffix = " (default)" if agent_type == "default" else f" ({agent_type})"
        return f"{agent_id}{type_suffix}"

    def _resolve_agent_type(self, action: "DelegateAction", index: int) -> str:
        """获取给定索引的智能体类型，默认为通用智能体。"""
        if not action.agent_types or index >= len(action.agent_types):
            return "default"
        return action.agent_types[index].strip() or "default"

    def _close_sub_agent(self, agent_id: str, conversation: LocalConversation) -> None:
        try:
            conversation.close()
        except Exception as e:
            logger.warning(f"Error closing sub-agent '{agent_id}': {e}")

    def close(self) -> None:
        for agent_id, conversation in list(self._sub_agents.items()):
            self._close_sub_agent(agent_id, conversation)
        self._sub_agents.clear()

    def _run_until_finished(
        self, agent_id: str, conversation: LocalConversation
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
                agent_id, pending
            ):
                conversation.run()
            else:
                conversation.reject_pending_actions("User rejected the actions")
                conversation.run()

    def _spawn_agents(self, action: "DelegateAction") -> DelegateObservation:
        """生成具有可选智能体类型的子智能体。"""
        if not action.ids:
            return DelegateObservation.from_text(
                text="At least one ID is required for spawn action",
                command=action.command,
                is_error=True,
            )

        # 验证 agent_types（如果提供）
        if action.agent_types is not None:
            if len(action.agent_types) > len(action.ids):
                return DelegateObservation.from_text(
                    text=(
                        f"agent_types length ({len(action.agent_types)}) "
                        f"cannot exceed ids length ({len(action.ids)})"
                    ),
                    command=action.command,
                    is_error=True,
                )

        new_agent_ids = set(action.ids) - set(self._sub_agents)
        if len(self._sub_agents) + len(new_agent_ids) > self._max_children:
            return DelegateObservation.from_text(
                text=(
                    f"Cannot spawn {len(action.ids)} agents. "
                    f"Already have {len(self._sub_agents)} agents, "
                    f"maximum is {self._max_children}"
                ),
                command=action.command,
                is_error=True,
            )

        created_sub_agents: list[tuple[str, str, LocalConversation]] = []
        try:
            parent_conversation = self.parent_conversation
            parent_llm = parent_conversation.agent.llm
            parent_visualizer = parent_conversation._visualizer
            workspace_path = parent_conversation.state.workspace.working_dir

            resolved_agent_types = [
                self._resolve_agent_type(action, i) for i in range(len(action.ids))
            ]
            factories = [
                get_agent_factory(name=agent_type)
                for agent_type in resolved_agent_types
            ]

            for agent_id, agent_type, factory in zip(
                action.ids, resolved_agent_types, factories
            ):
                sub_agent_llm = parent_llm.model_copy()
                # 重置指标，使子智能体拥有自己的 Metrics 对象
                #
                sub_agent_llm.reset_metrics()

                worker_agent = factory.factory_func(sub_agent_llm)

                # 确保子智能体 LLM 已停用流
                worker_agent = inherit_mcp_config(
                    parent_conversation.agent, worker_agent
                ).model_copy(
                    update={
                        "llm": worker_agent.llm.model_copy(update={"stream": False})
                    }
                )

                # 如果可用，使用父可视化器的 create_sub_visualizer 方法。这允许自定义可
                # 视化器（e.g，TUI-基于的）为他们的环境创建适当的子可视化器
                #
                sub_visualizer = None
                if parent_visualizer is not None:
                    sub_visualizer = parent_visualizer.create_sub_visualizer(agent_id)

                # 从父对话继承持久化：如果父对话保留其对话，子智能体持久化他们的对话位于
                # “子智能体”子目录下。
                #
                parent_persistence_dir = parent_conversation.state.persistence_dir
                if parent_persistence_dir is not None:
                    subagents_persistence_dir: Path | None = (
                        Path(parent_persistence_dir) / _SUBAGENTS_DIR
                    )
                    subagents_persistence_dir.mkdir(parents=True, exist_ok=True)
                else:
                    subagents_persistence_dir = None

                # 如果设置，则使用智能体定义中的 max_iteration_per_run
                conv_kwargs: dict = {
                    "agent": worker_agent,
                    "workspace": workspace_path,
                    "visualizer": sub_visualizer,
                    "hook_config": factory.definition.hooks,
                    "persistence_dir": subagents_persistence_dir,
                    "_parent_llm_call_context": (
                        parent_conversation.get_llm_call_context()
                    ),
                    "mcp_tool_provider": parent_conversation._mcp_tool_provider,
                    "_mcp_config_from_parent": True,
                }

                if factory.definition.max_iteration_per_run is not None:
                    conv_kwargs["max_iteration_per_run"] = (
                        factory.definition.max_iteration_per_run
                    )

                sub_conversation = LocalConversation(**conv_kwargs)
                created_sub_agents.append((agent_id, agent_type, sub_conversation))

                # 应用permission_mode：根据定义显式模式，或者在None时继承父级策略。
                #
                confirmation_policy = factory.definition.get_confirmation_policy()
                if confirmation_policy is None:
                    sub_conversation.set_confirmation_policy(
                        parent_conversation.state.confirmation_policy
                    )
                else:
                    sub_conversation.set_confirmation_policy(confirmation_policy)

            for agent_id, agent_type, sub_conversation in created_sub_agents:
                previous_conversation = self._sub_agents.get(agent_id)
                if previous_conversation is not None:
                    self._close_sub_agent(agent_id, previous_conversation)
                self._sub_agents[agent_id] = sub_conversation

                # 记录创建的智能体类型
                logger.info(
                    f"Spawned sub-agent '{self._format_agent_label(agent_id, agent_type)}'"  # noqa: E501
                )

            # 创建包含详细信息的成功消息
            agent_details = [
                self._format_agent_label(agent_id, agent_type)
                for agent_id, agent_type in zip(action.ids, resolved_agent_types)
            ]

            message = (
                f"Successfully spawned {len(action.ids)} sub-agents: "
                f"{', '.join(agent_details)}"
            )
            return DelegateObservation.from_text(
                text=message,
                command=action.command,
            )

        except Exception as e:
            for agent_id, _, sub_conversation in created_sub_agents:
                self._close_sub_agent(agent_id, sub_conversation)
            logger.error(f"Error: failed to spawn agents: {e}", exc_info=True)
            return DelegateObservation.from_text(
                text=f"failed to spawn agents: {str(e)}",
                command=action.command,
                is_error=True,
            )

    def _delegate_tasks(self, action: "DelegateAction") -> "DelegateObservation":
        """使用用户友好的标识符将任务委托给子智能体
        并等待结果（阻塞）。

        Args:
            action: DelegateAction 任务字典将标识符映射到任务
                   (e.g., {'lodging': '查找酒店', 'activities': '列出景点'})

        Returns:
            DelegateObservation 包含所有子智能体的综合结果
        """
        if not action.tasks:
            return DelegateObservation.from_text(
                text="at least one task is required for delegate action",
                command=action.command,
                is_error=True,
            )

        # 检查所有请求的智能体 ID 是否存在
        missing_agents = set(action.tasks.keys()) - set(self._sub_agents.keys())
        if missing_agents:
            return DelegateObservation.from_text(
                text=(
                    f"sub-agents not found: {', '.join(missing_agents)}. "
                    f"Available agents: {', '.join(self._sub_agents.keys())}"
                ),
                command=action.command,
                is_error=True,
            )

        try:
            # 创建线程以并行运行任务
            threads = []
            results = {}
            errors = {}

            # 从可视化工具中获取父级智能体的姓名（如果可用）
            parent_conversation = self.parent_conversation
            parent_name = None
            if hasattr(parent_conversation, "_visualizer"):
                visualizer = parent_conversation._visualizer
                if visualizer is not None:
                    parent_name = getattr(visualizer, "_name", None)

            def run_task(
                agent_id: str,
                conversation: LocalConversation,
                task: str,
                parent_name: str | None,
            ):
                """在子智能体上运行单个任务。"""
                try:
                    logger.info(f"Sub-agent {agent_id} starting task: {task[:100]}...")
                    conversation.send_message(task, sender=parent_name)
                    self._run_until_finished(agent_id, conversation)

                    final_response = get_agent_final_response(conversation.state.events)
                    if final_response:
                        results[agent_id] = final_response
                        logger.info(f"Sub-agent {agent_id} completed successfully")
                    else:
                        results[agent_id] = "No response from sub-agent"
                        logger.warning(
                            f"Sub-agent {agent_id} completed but no final response"
                        )

                except Exception as e:
                    error_msg = f"Sub-agent {agent_id} failed: {str(e)}"
                    errors[agent_id] = error_msg
                    logger.error(error_msg, exc_info=True)

            # 并行启动所有任务
            for agent_id, task in action.tasks.items():
                conversation = self._sub_agents[agent_id]
                thread = threading.Thread(
                    target=run_task,
                    args=(agent_id, conversation, task, parent_name),
                    name=f"Task-{agent_id}",
                )
                threads.append(thread)
                thread.start()

            # 等待所有线程完成
            for thread in threads:
                thread.join()

            # 同步子智能体家长对话中的指标。 子智能体指标是累积的，因此替换（而不是合并
            # ）以避免重复委托的重复计算。
            #
            parent_stats = parent_conversation.conversation_stats
            for agent_id in action.tasks:
                if agent_id in self._sub_agents:
                    sub_conv = self._sub_agents[agent_id]
                    parent_stats.usage_to_metrics[f"delegate:{agent_id}"] = (
                        sub_conv.conversation_stats.get_combined_metrics()
                    )

            # 按照与输入任务相同的顺序收集结果
            all_results = []

            for agent_id in action.tasks.keys():
                if agent_id in results:
                    all_results.append(f"Agent {agent_id}: {results[agent_id]}")
                elif agent_id in errors:
                    all_results.append(f"Agent {agent_id} ERROR: {errors[agent_id]}")
                else:
                    all_results.append(f"Agent {agent_id}: No result")

            # 创建包含结果的综合消息
            output_text = f"Completed delegation of {len(action.tasks)} tasks"
            if errors:
                output_text += f" with {len(errors)} errors"

            if all_results:
                results_text = "\n".join(
                    f"{i}. {result}" for i, result in enumerate(all_results, 1)
                )
                output_text += f"\n\nResults:\n{results_text}"

            return DelegateObservation.from_text(
                text=output_text,
                command=action.command,
            )

        except Exception as e:
            logger.error(f"Failed to delegate tasks: {e}", exc_info=True)
            return DelegateObservation.from_text(
                text=f"failed to delegate tasks: {str(e)}",
                command=action.command,
                is_error=True,
            )
