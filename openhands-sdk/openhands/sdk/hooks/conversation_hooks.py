"""用于对话的 Hook 集成。"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from openhands.sdk.conversation.visualizer import ConversationVisualizerBase
from openhands.sdk.event import (
    ActionEvent,
    Event,
    HookExecutionEvent,
    MessageEvent,
    ObservationEvent,
)
from openhands.sdk.hooks.config import HookConfig
from openhands.sdk.hooks.executor import HookResult
from openhands.sdk.hooks.manager import HookManager
from openhands.sdk.hooks.types import HookEventType
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.logger import get_logger


if TYPE_CHECKING:
    from openhands.sdk.conversation.conversation_stats import ConversationStats
    from openhands.sdk.conversation.state import ConversationState
    from openhands.sdk.llm import LLM
    from openhands.sdk.llm.call_context import LLMCallContext

logger = get_logger(__name__)

# 我们在 HookExecutionEvent 日志字段中持久化的最大字符数。 Hooks 可以发出任意输出； 截断
# 可以防止事件持久化膨胀。
#
MAX_HOOK_LOG_CHARS = 50_000
_TRUNCATION_SUFFIX = "\n<TRUNCATED>"


def _truncate_hook_log(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) <= MAX_HOOK_LOG_CHARS:
        return value
    if MAX_HOOK_LOG_CHARS <= len(_TRUNCATION_SUFFIX):
        return value[:MAX_HOOK_LOG_CHARS]
    return value[: MAX_HOOK_LOG_CHARS - len(_TRUNCATION_SUFFIX)] + _TRUNCATION_SUFFIX


# 发出事件的回调函数的类型别名
EventEmitter = Callable[[Event], None]


class HookEventProcessor:
    """处理事件并在适当的点运行挂钩。

    创建对话后调用 set_conversation_state() 以使阻塞起作用。

    当 emit_hook_events=True 时，每个钩子执行都会发出 HookExecutionEvent，为客户端提
    供对钩子执行的完全可观察性。
    """

    def __init__(
        self,
        hook_manager: HookManager,
        original_callback: Any = None,
        emit_hook_events: bool = True,
    ):
        self.hook_manager = hook_manager
        self.original_callback = original_callback
        self._conversation_state: ConversationState | None = None
        self.emit_hook_events = emit_hook_events
        # SessionStart additional_context 由 run_session_start() 收集并随后由
        # inject_pending_additional_context() 交付； 看看那些方法。
        #
        self._pending_additional_context: list[str] = []

    def set_conversation_state(self, state: "ConversationState") -> None:
        """设置阻止支持的对话状态。"""
        self._conversation_state = state

    def _emit_hook_execution_event(
        self,
        hook_event_type: HookEventType,
        hook_command: str,
        result: HookResult,
        tool_name: str | None = None,
        action_id: str | None = None,
        message_id: str | None = None,
        hook_input: dict[str, Any] | None = None,
    ) -> None:
        """发出 HookExecutionEvent 以提高可观察性。"""
        if not self.emit_hook_events or not self.original_callback:
            return

        event = HookExecutionEvent(
            hook_event_type=hook_event_type.value,
            hook_command=hook_command,
            tool_name=tool_name,
            success=result.success,
            blocked=result.blocked,
            exit_code=result.exit_code,
            stdout=_truncate_hook_log(result.stdout) or "",
            stderr=_truncate_hook_log(result.stderr) or "",
            reason=_truncate_hook_log(result.reason),
            additional_context=_truncate_hook_log(result.additional_context),
            error=_truncate_hook_log(result.error),
            action_id=action_id,
            message_id=message_id,
            hook_input=hook_input,
        )
        self.original_callback(event)

    def on_event(self, event: Event) -> None:
        """处理事件并运行适当的挂钩。"""
        # 跟踪要传递给回调的事件（可能会被钩子修改）
        callback_event = event

        # 为动作事件运行 PreToolUse 挂钩
        if isinstance(event, ActionEvent) and event.action is not None:
            self._handle_pre_tool_use(event)

        # 为观测结果事件运行 PostToolUse 挂钩
        if isinstance(event, ObservationEvent):
            self._handle_post_tool_use(event)

        # 为用户消息运行 UserPromptSubmit 挂钩
        if isinstance(event, MessageEvent) and event.source == "user":
            callback_event = self._handle_user_prompt_submit(event)

        # 使用（可能已修改）事件调用原始回调
        if self.original_callback:
            self.original_callback(callback_event)

    def _handle_pre_tool_use(self, event: ActionEvent) -> None:
        """Handle PreToolUse hooks. 阻止的操作在对话状态中标记。"""
        if not self.hook_manager.has_hooks(HookEventType.PRE_TOOL_USE):
            return

        tool_name = event.tool_name
        tool_input: dict[str, Any] = {}

        # 从操作中提取工具输入
        if event.action is not None:
            try:
                tool_input = event.action.model_dump()
            except Exception as e:
                logger.debug(f"Could not extract tool input: {e}")

        # 获取带有命令信息的挂钩以发出事件
        hooks = self.hook_manager.config.get_hooks_for_event(
            HookEventType.PRE_TOOL_USE, tool_name
        )

        should_continue, results = self.hook_manager.run_pre_tool_use(
            tool_name=tool_name,
            tool_input=tool_input,
        )

        # 为每个钩子发出 HookExecutionEvents
        for hook, result in zip(hooks, results, strict=False):
            self._emit_hook_execution_event(
                hook_event_type=HookEventType.PRE_TOOL_USE,
                hook_command=hook.display_command,
                result=result,
                tool_name=tool_name,
                action_id=event.id,
                hook_input={"tool_name": tool_name, "tool_input": tool_input},
            )

        if not should_continue:
            reason = self.hook_manager.get_blocking_reason(results)
            logger.warning(f"Hook blocked action {tool_name}: {reason}")

            # 将此操作标记为在对话状态中被阻止智能体将检查此操作并发出拒绝而不是执行
            #
            if self._conversation_state is not None:
                block_reason = reason or "Blocked by hook"
                self._conversation_state.block_action(event.id, block_reason)
            else:
                logger.warning(
                    "Cannot block action: conversation state not set. "
                    "Call processor.set_conversation_state(conversation.state) "
                    "after creating the Conversation."
                )

    def _handle_post_tool_use(self, event: ObservationEvent) -> None:
        """操作完成后处理 PostToolUse 挂钩。"""
        if not self.hook_manager.has_hooks(HookEventType.POST_TOOL_USE):
            return

        # O(1) 从状态事件中查找对应的动作
        action_event = None
        if self._conversation_state is not None:
            try:
                idx = self._conversation_state.events.get_index(event.action_id)
                event_at_idx = self._conversation_state.events[idx]
                if isinstance(event_at_idx, ActionEvent):
                    action_event = event_at_idx
            except KeyError:
                pass  # 未找到操作

        if action_event is None:
            return

        tool_name = event.tool_name
        tool_input: dict[str, Any] = {}
        tool_response: dict[str, Any] = {}

        # 从操作中提取工具输入
        if action_event.action is not None:
            try:
                tool_input = action_event.action.model_dump()
            except Exception as e:
                logger.debug(f"Could not extract tool input: {e}")

        # 从观测结果中提取结构化工具响应
        if event.observation is not None:
            try:
                tool_response = event.observation.model_dump()
            except Exception as e:
                logger.debug(f"Could not extract tool response: {e}")

        # 获取带有命令信息的挂钩以发出事件
        hooks = self.hook_manager.config.get_hooks_for_event(
            HookEventType.POST_TOOL_USE, tool_name
        )

        results = self.hook_manager.run_post_tool_use(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_response=tool_response,
        )

        # 为每个钩子发出 HookExecutionEvents 并记录错误
        for hook, result in zip(hooks, results, strict=False):
            self._emit_hook_execution_event(
                hook_event_type=HookEventType.POST_TOOL_USE,
                hook_command=hook.display_command,
                result=result,
                tool_name=tool_name,
                action_id=action_event.id,
                hook_input={
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "tool_response": tool_response,
                },
            )
            if result.error:
                logger.warning(f"PostToolUse hook error: {result.error}")

    def _handle_user_prompt_submit(self, event: MessageEvent) -> MessageEvent:
        """在处理用户消息之前处理 UserPromptSubmit 挂钩。

        返回（可能已修改的）事件。 如果钩子注入 additional_context，则会创建一个新的
        MessageEvent，并将上下文附加到
        extended_content。
        """
        if not self.hook_manager.has_hooks(HookEventType.USER_PROMPT_SUBMIT):
            return event

        # 提取消息文本
        message = ""
        if event.llm_message and event.llm_message.content:
            for content in event.llm_message.content:
                if isinstance(content, TextContent):
                    message += content.text

        # 获取带有命令信息的挂钩以发出事件
        hooks = self.hook_manager.config.get_hooks_for_event(
            HookEventType.USER_PROMPT_SUBMIT
        )

        should_continue, additional_context, results = (
            self.hook_manager.run_user_prompt_submit(message=message)
        )

        # 为每个钩子发出 HookExecutionEvents
        for hook, result in zip(hooks, results, strict=False):
            self._emit_hook_execution_event(
                hook_event_type=HookEventType.USER_PROMPT_SUBMIT,
                hook_command=hook.display_command,
                result=result,
                message_id=event.id,
                hook_input={"message": message},
            )

        if not should_continue:
            reason = self.hook_manager.get_blocking_reason(results)
            logger.warning(f"Hook blocked user message: {reason}")

            # 将此消息标记为在对话状态下被阻止智能体将检查此项并跳过处理该消息
            #
            if self._conversation_state is not None:
                block_reason = reason or "Blocked by hook"
                self._conversation_state.block_message(event.id, block_reason)
            else:
                logger.warning(
                    "Cannot block message: conversation state not set. "
                    "Call processor.set_conversation_state(conversation.state) "
                    "after creating the Conversation."
                )

        # 将 additional_context 注入 extended_content
        if additional_context:
            logger.debug(f"Hook injecting context: {additional_context[:100]}...")
            new_extended_content = list(event.extended_content) + [
                TextContent(text=additional_context)
            ]
            # MessageEvent 已冻结，因此创建一个新的
            event = MessageEvent(
                source=event.source,
                llm_message=event.llm_message,
                llm_response_id=event.llm_response_id,
                activated_skills=event.activated_skills,
                extended_content=new_extended_content,
                sender=event.sender,
            )

        return event

    def is_action_blocked(self, action_id: str) -> bool:
        """检查某个操作是否被钩子阻止。"""
        if self._conversation_state is None:
            return False
        return action_id in self._conversation_state.blocked_actions

    def is_message_blocked(self, message_id: str) -> bool:
        """检查消息是否被钩子阻止。"""
        if self._conversation_state is None:
            return False
        return message_id in self._conversation_state.blocked_messages

    def run_session_start(self) -> None:
        """运行 SessionStart 挂钩。 创建对话后拨打电话。"""
        hooks = self.hook_manager.config.get_hooks_for_event(
            HookEventType.SESSION_START
        )
        results = self.hook_manager.run_session_start()

        for hook, result in zip(hooks, results, strict=False):
            self._emit_hook_execution_event(
                hook_event_type=HookEventType.SESSION_START,
                hook_command=hook.display_command,
                result=result,
            )
            if result.error:
                logger.warning(f"SessionStart hook error: {result.error}")

        # 收集 additional_context 以传送到智能体，但不要在此处发出。 run_session_start()
        #  在插件加载时运行，在智能体发出 SystemPromptEvent 之前，因此现在发出会将用户消
        # 息置于系统提示词之前，并破坏系统优先不变量（以及提示词缓存，仅适用于前导系统消
        # 息）。 一旦 init_state() 发出系统提示词，对话就会用
        # inject_pending_additional_context() 刷新它。
        #
        self._pending_additional_context.extend(
            r.additional_context for r in results if r.additional_context
        )

    def inject_pending_additional_context(self) -> None:
        """将收集到的 SessionStart additional_context 传送到智能体。

        将上下文作为单个 ``MessageEvent`` 发出。 在智能体's ``SystemPromptEvent``出现
        在日志中之后，调用此方法，以确保系统
        提示词在请求中处于首位，与``UserPromptSubmit``路径相同（而不是在现有用户回合
        之前添加一个新的）。 待处理的上下文在交付时被清除，因此重新
        运行 SessionStart 挂钩（例如，当运行时插件挂钩合并时）不会将其交付两次。
        """
        if not self._pending_additional_context or not self.original_callback:
            return

        additional_context = "\n".join(self._pending_additional_context)
        self._pending_additional_context = []
        logger.debug(
            f"SessionStart hook injecting context: {additional_context[:100]}..."
        )
        self.original_callback(
            MessageEvent(
                source="environment",
                llm_message=Message(
                    role="user",
                    content=[TextContent(text=additional_context)],
                ),
            )
        )

    def run_session_end(self) -> None:
        """运行 SessionEnd 挂钩。 在对话结束前致电。"""
        hooks = self.hook_manager.config.get_hooks_for_event(HookEventType.SESSION_END)
        results = self.hook_manager.run_session_end()

        for hook, result in zip(hooks, results, strict=False):
            self._emit_hook_execution_event(
                hook_event_type=HookEventType.SESSION_END,
                hook_command=hook.display_command,
                result=result,
            )
            if result.error:
                logger.warning(f"SessionEnd hook error: {result.error}")

    def run_stop(self, reason: str | None = None) -> tuple[bool, str | None]:
        """运行停止挂钩。 返回（should_stop，反馈）。"""
        if not self.hook_manager.has_hooks(HookEventType.STOP):
            return True, None

        hooks = self.hook_manager.config.get_hooks_for_event(HookEventType.STOP)
        should_stop, results = self.hook_manager.run_stop(reason=reason)

        # 发出事件并记录错误
        for hook, result in zip(hooks, results, strict=False):
            self._emit_hook_execution_event(
                hook_event_type=HookEventType.STOP,
                hook_command=hook.display_command,
                result=result,
                hook_input={"reason": reason} if reason else None,
            )
            if result.error:
                logger.warning(f"Stop hook error: {result.error}")

        # 如果被拒绝收集反馈
        feedback = None
        if not should_stop:
            reason_text = self.hook_manager.get_blocking_reason(results)
            logger.info(f"Stop hook denied stopping: {reason_text}")
            feedback_parts = [
                r.additional_context for r in results if r.additional_context
            ]
            if feedback_parts:
                feedback = "\n".join(feedback_parts)
            elif reason_text:
                feedback = reason_text

        return should_stop, feedback


def create_hook_callback(
    hook_config: HookConfig | None = None,
    working_dir: str | None = None,
    session_id: str | None = None,
    original_callback: Any = None,
    emit_hook_events: bool = True,
    llm: "LLM | None" = None,
    llm_getter: "Callable[[], LLM | None] | None" = None,
    llm_call_context: "LLMCallContext | None" = None,
    persistence_dir: str | None = None,
    visualizer: type[ConversationVisualizerBase]
    | ConversationVisualizerBase
    | None = None,
    conversation_stats: "ConversationStats | None" = None,
) -> tuple[HookEventProcessor, Any]:
    """创建一个启用挂钩的事件回调。 返回（处理器，回调）。

    Args:
        hook_config: 要运行的钩子的配置。
        working_dir: 工作目录用于钩子执行。
        session_id: 会话 ID 传递给钩子。
        original_callback: 回调钩子处理后转为链条。
        emit_hook_events: 如果为 True，则每次钩子执行时发出 HookExecutionEvent。
            默认为 True 以实现完全可观察。
        llm: LLM 实例继承自父会话，由智能体挂钩使用。
        llm_getter: 可调用返回对话的当前 LLM。 首选
            超过 ``llm``，因此智能体钩子跟随 switch_llm()/switch_profile().
        llm_call_context: 运行时上下文由智能体挂钩对话继承。
        persistence_dir: 目录用于持久化智能体挂钩子会话事件。
        visualizer: 可视化工具实例传递到智能体挂钩子对话。
        conversation_stats: 家长对话统计数据应包括挂钩支出。

    Returns:
        (HookEventProcessor, 回调函数) 的元组。
    """
    hook_manager = HookManager(
        config=hook_config,
        working_dir=working_dir,
        session_id=session_id,
        llm=llm,
        llm_getter=llm_getter,
        llm_call_context=llm_call_context,
        persistence_dir=persistence_dir,
        visualizer=visualizer,
        conversation_stats=conversation_stats,
    )

    processor = HookEventProcessor(
        hook_manager=hook_manager,
        original_callback=original_callback,
        emit_hook_events=emit_hook_events,
    )

    return processor, processor.on_event
