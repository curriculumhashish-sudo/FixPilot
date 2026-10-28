"""智能体的并行工具执行。

该模块提供了用于同时执行多个工具调用的实用程序，以及可配置的每智能体并发限制和资源级
锁定。

资源锁定（通过``ResourceLockManager``）确保在相同共享状态（文件、终端会话、浏览器等）
上运行的工具是已序列化，
while tools touching *different* resources can run concurrently.

.. 个别工具的警告：: 线程安全

   当 ``tool_concurrency_limit > 1`` 时，多个工具并行运行线程，共享相同的
   ``conversation`` 对象。 执行者使用
   ``ResourceLockManager`` 到序列化访问共享资源，但工具必须正确实现
   ``declared_resources()`` 才能有效。
"""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from openhands.sdk.conversation.cancellation import CancellationToken
from openhands.sdk.conversation.resource_lock_manager import ResourceLockManager
from openhands.sdk.event.error_classification import (
    AGENT_OUTCOME,
    ErrorClassification,
    FailureKind,
)
from openhands.sdk.event.llm_convertible import AgentErrorEvent
from openhands.sdk.logger import get_logger
from openhands.sdk.observability.laminar import record_tool_result
from openhands.sdk.observability.utils import extract_action_name


if TYPE_CHECKING:
    from openhands.sdk.event.base import Event
    from openhands.sdk.event.llm_convertible import ActionEvent
    from openhands.sdk.tool.tool import DeclaredResources, ToolDefinition

logger = get_logger(__name__)

# ：意外的内部故障 - 应作为诊断而不是结果出现。
_INTERNAL = ErrorClassification(kind=FailureKind.INTERNAL, retryable=False)


class ParallelToolExecutor:
    """与资源锁定同时执行一批工具调用。

    每个实例都有自己的线程池、并发限制，以及
    ``ResourceLockManager``，因此嵌套执行 (e.g., 子智能体) 不能死锁父级。
    """

    def __init__(
        self,
        max_workers: int = 1,
        lock_manager: ResourceLockManager | None = None,
    ) -> None:
        self._max_workers = max_workers
        self._lock_manager = lock_manager or ResourceLockManager()

    def execute_batch(
        self,
        action_events: Sequence[ActionEvent],
        tool_runner: Callable[[ActionEvent], list[Event]],
        tools: dict[str, ToolDefinition] | None = None,
        cancel_token: CancellationToken | None = None,
        span_owner: object | None = None,
    ) -> list[list[Event]]:
        """同时执行一批动作事件。

        Args:
            action_events: 要执行的 ActionEvent 个对象的序列。
            tool_runner: 接受 ActionEvent 并返回的可调用对象
                        由执行产生的事件对象列表。
            tools: 使用工具名称到 ToolDefinition 的可选映射
                   派生用于锁定的资源密钥。 当 *None* 时，跳过锁定 (向后兼容)。
            cancel_token: 如果设置和取消，待处理的工具调用是
                          跳过并返回合成错误事件。
            span_owner: 携带对话根跨度的对象
                        综合取消结果。

        Returns:
            事件列表的列表与输入 action_events 的顺序相同。
        """
        if not action_events:
            return []

        def _resolve(ae: ActionEvent) -> ToolDefinition | None:
            return tools.get(ae.tool_name) if tools else None

        if len(action_events) == 1 or self._max_workers == 1:
            return [
                self._run_safe(
                    action,
                    tool_runner,
                    _resolve(action),
                    cancel_token,
                    span_owner,
                )
                for action in action_events
            ]

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            # submit() 本身不传播上下文变量； 每个任务一个新副本，因为一个上下文不能由两
            # 个线程输入。
            #
            futures = [
                executor.submit(
                    contextvars.copy_context().run,
                    self._run_safe,
                    action,
                    tool_runner,
                    _resolve(action),
                    cancel_token,
                    span_owner,
                )
                for action in action_events
            ]

        return [future.result() for future in futures]

    async def aexecute_batch(
        self,
        action_events: Sequence[ActionEvent],
        tool_runner: Callable[[ActionEvent], list[Event]],
        tools: dict[str, ToolDefinition] | None = None,
        cancel_token: CancellationToken | None = None,
        span_owner: object | None = None,
    ) -> list[list[Event]]:
        """异步：meth:`execute_batch` 的变体。

        每个工具调用被分派到一个专用的
        :class:`~concurrent.futures.ThreadPoolExecutor` （大小为
        ``max_workers``）通过：func:`asyncio.loop.run_in_executor` 并与：func:
        `asyncio.gather` 同时调度。 池本身边界并发，匹配同步路径的每批次
        ：类：`ThreadPoolExecutor`； 使用专用池可以避免
        在 asyncio 的共享默认执行器上序列化（小且全局的），这可能会 throttling 之前并
        行的请求工具调用 when other
        ``run_in_executor`` 用户为它争抢。

        *tool_runner* 与 **同步** 所使用的可调用相同
        ：方法：`execute_batch`（i.e。 ``_execute_action_event``).
        ``span_owner`` 将综合取消结果锚定到其根跨度。 通过：class:
        `ResourceLockManager`（线程锁）进行的资源锁定可以正常工
        作，因为每个工具调用都在自己的线程中运行。
        """
        if not action_events:
            return []

        def _resolve(ae: ActionEvent) -> ToolDefinition | None:
            return tools.get(ae.tool_name) if tools else None

        if len(action_events) == 1 or self._max_workers == 1:
            return [
                await self._arun_safe(
                    action,
                    tool_runner,
                    _resolve(action),
                    cancel_token,
                    span_owner=span_owner,
                )
                for action in action_events
            ]

        with ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="aexecute_batch",
        ) as pool:
            return list(
                await asyncio.gather(
                    *[
                        self._arun_safe(
                            action,
                            tool_runner,
                            _resolve(action),
                            cancel_token,
                            pool,
                            span_owner,
                        )
                        for action in action_events
                    ]
                )
            )

    async def _arun_safe(
        self,
        action: ActionEvent,
        tool_runner: Callable[[ActionEvent], list[Event]],
        tool: ToolDefinition | None = None,
        cancel_token: CancellationToken | None = None,
        executor: ThreadPoolExecutor | None = None,
        span_owner: object | None = None,
    ) -> list[Event]:
        """通过 ``run_in_executor`` 在线程中运行：meth:`_run_safe`。

        这样保持了事件循环的自由，而 (阻塞) 工具执行时确保了 ``ResourceLockManager``
        的线程锁在工作线程线程上获取，而不是事件循环线程。

        当 *executor* 为 ``None`` 时，使用 asyncio 默认池（适合一次性/单操作调用）；
        批处理调用者应传递专用池，以便并发工具调用不会
        与共享默认池上的其他 ``run_in_executor`` 用户竞争。

        如果在线程运行时取消 asyncio 任务 (e.g. 通过``conversation.interrupt()``），
        我们称
        ``tool.executor.interrupt()`` 向工具发出信号以中止 (e.g. 将 Ctrl+C 发送到终端
        子进程)。 线程仍然运行完成，但被
        中断的命令很快完成，而不是阻塞到原来的超时。
        """
        loop = asyncio.get_running_loop()
        # 与 asyncio.to_thread 不同，run_in_executor 不复制上下文变量。
        ctx = contextvars.copy_context()

        def run_in_caller_context() -> list[Event]:
            return ctx.run(
                self._run_safe,
                action,
                tool_runner,
                tool,
                cancel_token,
                span_owner,
            )

        fut = loop.run_in_executor(executor, run_in_caller_context)
        try:
            return await fut
        except asyncio.CancelledError:
            # asyncio 任务已取消（中断），但线程-池工作线程仍在运行。 向工具发出信号以中
            # 止其正在进行的工作，以便线程快速退出。
            #
            if tool is not None and tool.executor is not None:
                try:
                    tool.executor.interrupt()
                except Exception:
                    logger.debug(
                        "executor.interrupt() failed for '%s'",
                        action.tool_name,
                        exc_info=True,
                    )
            raise

    @staticmethod
    def _cancelled_error(
        action: ActionEvent, span_owner: object | None = None
    ) -> list[Event]:
        """返回因取消而跳过的工具调用的综合错误。"""
        error = AgentErrorEvent(
            error="Tool call cancelled by interrupt.",
            tool_name=action.tool_name,
            tool_call_id=action.tool_call_id,
            classification=AGENT_OUTCOME,
        )
        record_tool_result(
            span_owner if span_owner is not None else action,
            name=extract_action_name(action),
            tool_call_id=action.tool_call_id,
            tool_input=action.action,
            tool_output=error.to_llm_message(),
        )
        return [error]

    def _run_safe(
        self,
        action: ActionEvent,
        tool_runner: Callable[[ActionEvent], list[Event]],
        tool: ToolDefinition | None = None,
        cancel_token: CancellationToken | None = None,
        span_owner: object | None = None,
    ) -> list[Event]:
        """使用资源锁定运行 tool_runner。

        将异常转换为 ``AgentErrorEvent``。 如果在工具开始之前设置了 *cancel_token*，
        则会跳过调用并返回综合错误。

        锁定策略：

        - ``declared=False`` → ``tool:<name>`` 互斥体。
        - ``declared=True``，空键→无锁定。
        - ``declared=True``，键存在 → 锁这些资源。
        """
        if cancel_token is not None and cancel_token.is_cancelled:
            logger.info(
                "Skipping tool '%s' -- cancelled before execution",
                action.tool_name,
            )
            return self._cancelled_error(action, span_owner)

        try:
            if tool is None:
                return tool_runner(action)

            resources = self._extract_declared_resources(action, tool)
            lock_keys = self._resolve_lock_keys(resources, tool)
            if not lock_keys:
                return tool_runner(action)
            with self._lock_manager.lock(*lock_keys):
                return tool_runner(action)

        except ValueError as e:
            logger.info(f"Tool error in '{action.tool_name}': {e}")
            return [
                AgentErrorEvent(
                    error=f"Error executing tool '{action.tool_name}': {e}",
                    tool_name=action.tool_name,
                    tool_call_id=action.tool_call_id,
                    classification=AGENT_OUTCOME,
                )
            ]
        except Exception as e:
            logger.error(
                f"Unexpected error in tool '{action.tool_name}': {e}",
                exc_info=True,
            )
            return [
                AgentErrorEvent(
                    error=f"Error executing tool '{action.tool_name}': {e}",
                    tool_name=action.tool_name,
                    tool_call_id=action.tool_call_id,
                    classification=_INTERNAL,
                )
            ]

    @staticmethod
    def _extract_declared_resources(
        action: ActionEvent,
        tool: ToolDefinition,
    ) -> DeclaredResources | None:
        """如果解析了操作，则调用 ``tool.declared_resources()``。"""
        parsed_action = action.action
        return tool.declared_resources(parsed_action) if parsed_action else None

    @staticmethod
    def _resolve_lock_keys(
        resources: DeclaredResources | None,
        tool: ToolDefinition,
    ) -> list[str]:
        """将声明的资源转换为锁键。

        当不需要锁定时返回一个空列表。
        """
        if resources is None or not resources.declared:
            return [f"tool:{tool.name}"]
        return list(resources.keys)
