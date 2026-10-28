"""挂钩管理器 - 协调对话中的挂钩执行。"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from openhands.sdk.conversation.visualizer import ConversationVisualizerBase
from openhands.sdk.hooks.config import HookConfig
from openhands.sdk.hooks.executor import HookExecutor, HookResult
from openhands.sdk.hooks.types import HookEvent, HookEventType


if TYPE_CHECKING:
    from openhands.sdk.conversation.conversation_stats import ConversationStats
    from openhands.sdk.llm import LLM
    from openhands.sdk.llm.call_context import LLMCallContext


logger = logging.getLogger(__name__)


class HookManager:
    """管理对话的钩子执行。"""

    def __init__(
        self,
        config: HookConfig | None = None,
        working_dir: str | None = None,
        session_id: str | None = None,
        llm: "LLM | None" = None,
        llm_getter: "Callable[[], LLM | None] | None" = None,
        llm_call_context: "LLMCallContext | None" = None,
        persistence_dir: str | None = None,
        visualizer: type[ConversationVisualizerBase]
        | ConversationVisualizerBase
        | None = None,
        conversation_stats: "ConversationStats | None" = None,
    ):
        self.config = config or HookConfig.load(working_dir=working_dir)
        self.executor = HookExecutor(
            working_dir=working_dir,
            llm=llm,
            llm_getter=llm_getter,
            llm_call_context=llm_call_context,
            persistence_dir=persistence_dir,
            visualizer=visualizer,
            conversation_stats=conversation_stats,
        )
        self.session_id = session_id
        self.working_dir = working_dir

    def _create_event(
        self,
        event_type: HookEventType,
        tool_name: str | None = None,
        tool_input: dict[str, Any] | None = None,
        tool_response: dict[str, Any] | None = None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> HookEvent:
        """创建一个填充了公共字段的挂钩事件。"""
        return HookEvent(
            event_type=event_type,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_response=tool_response,
            message=message,
            session_id=self.session_id,
            working_dir=self.working_dir,
            metadata=metadata or {},
        )

    def run_pre_tool_use(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> tuple[bool, list[HookResult]]:
        """运行 PreToolUse 挂钩。 返回（should_continue，结果）。"""
        hooks = self.config.get_hooks_for_event(HookEventType.PRE_TOOL_USE, tool_name)
        if not hooks:
            return True, []

        # 警告 PreToolUse 中的异步挂钩 - 它们无法阻止操作
        async_hooks = [h for h in hooks if h.async_]
        if async_hooks:
            logger.warning(
                "Async hooks in PreToolUse cannot block tool execution. "
                f"Found {len(async_hooks)} async hook(s) that will run in background."
            )

        event = self._create_event(
            HookEventType.PRE_TOOL_USE,
            tool_name=tool_name,
            tool_input=tool_input,
        )

        results = self.executor.execute_all(hooks, event, stop_on_block=True)

        # 检查是否有任何钩子阻止了操作
        should_continue = all(r.should_continue for r in results)

        return should_continue, results

    def run_post_tool_use(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_response: dict[str, Any],
    ) -> list[HookResult]:
        """工具完成后运行 PostToolUse 挂钩。"""
        hooks = self.config.get_hooks_for_event(HookEventType.POST_TOOL_USE, tool_name)
        if not hooks:
            return []

        event = self._create_event(
            HookEventType.POST_TOOL_USE,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_response=tool_response,
        )

        # PostToolUse 钩子不会阻塞 - 它们只是运行
        return self.executor.execute_all(hooks, event, stop_on_block=False)

    def run_user_prompt_submit(
        self,
        message: str,
    ) -> tuple[bool, str | None, list[HookResult]]:
        """运行 UserPromptSubmit 挂钩。"""
        hooks = self.config.get_hooks_for_event(HookEventType.USER_PROMPT_SUBMIT)
        if not hooks:
            return True, None, []

        event = self._create_event(
            HookEventType.USER_PROMPT_SUBMIT,
            message=message,
        )

        results = self.executor.execute_all(hooks, event, stop_on_block=True)

        # 检查是否有任何钩子被阻塞
        should_continue = all(r.should_continue for r in results)

        # 从钩子上收集额外的上下文
        additional_context_parts = [
            r.additional_context for r in results if r.additional_context
        ]
        additional_context = (
            "\n".join(additional_context_parts) if additional_context_parts else None
        )

        return should_continue, additional_context, results

    def run_session_start(self) -> list[HookResult]:
        """对话开始时运行 SessionStart 挂钩。"""
        hooks = self.config.get_hooks_for_event(HookEventType.SESSION_START)
        if not hooks:
            return []

        event = self._create_event(HookEventType.SESSION_START)
        return self.executor.execute_all(hooks, event, stop_on_block=False)

    def run_session_end(self) -> list[HookResult]:
        """对话结束时运行 SessionEnd 挂钩。"""
        hooks = self.config.get_hooks_for_event(HookEventType.SESSION_END)
        results: list[HookResult] = []
        if hooks:
            event = self._create_event(HookEventType.SESSION_END)
            results = self.executor.execute_all(hooks, event, stop_on_block=False)

        # 清理所有后台异步进程
        self.cleanup_async_processes()

        return results

    def cleanup_async_processes(self) -> None:
        """清理所有后台挂钩进程。"""
        self.executor.async_process_manager.cleanup_all()

    def run_stop(
        self,
        reason: str | None = None,
    ) -> tuple[bool, list[HookResult]]:
        """运行停止挂钩。 返回（should_stop，结果）。"""
        hooks = self.config.get_hooks_for_event(HookEventType.STOP)
        if not hooks:
            return True, []

        event = self._create_event(
            HookEventType.STOP,
            metadata={"reason": reason} if reason else {},
        )

        results = self.executor.execute_all(hooks, event, stop_on_block=True)

        # 如果钩子阻塞，智能体应该不停止（继续运行）
        should_stop = all(r.should_continue for r in results)

        return should_stop, results

    def has_hooks(self, event_type: HookEventType) -> bool:
        """检查是否有为事件类型配置的挂钩。"""
        return self.config.has_hooks_for_event(event_type)

    def get_blocking_reason(self, results: list[HookResult]) -> str | None:
        """从钩子结果中获取阻塞原因。"""
        for result in results:
            if result.blocked:
                if result.reason:
                    return result.reason
                if result.stderr:
                    return result.stderr.strip()
                return "Blocked by hook"
        return None
