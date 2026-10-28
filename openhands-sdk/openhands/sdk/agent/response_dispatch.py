"""对 LLM 响应进行分类并分派到特定于类型的处理程序。

包含：
  - ``LLMResponseType`` — 枚举用于响应分类。
  - ``classify_response`` — 纯分类器函数（无副作用）。
  - ``ResponseDispatchMixin`` — 处理程序方法混合到 ``Agent`` 中。
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from openhands.sdk.agent.stream_context import StreamContext
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event import MessageEvent
from openhands.sdk.llm import LLMResponse, Message, TextContent
from openhands.sdk.logger import get_logger


if TYPE_CHECKING:
    from openhands.sdk.conversation import (
        ConversationCallbackType,
        ConversationState,
        LocalConversation,
    )
    from openhands.sdk.critic.base import CriticBase, CriticResult
    from openhands.sdk.event import ActionEvent
    from openhands.sdk.llm import (
        MessageToolCall,
        ReasoningItemModel,
        RedactedThinkingBlock,
        ThinkingBlock,
    )
    from openhands.sdk.security.analyzer import SecurityAnalyzerBase

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 分类
# ---------------------------------------------------------------------------


class LLMResponseType(StrEnum):
    """LLM 响应的互斥分类。"""

    TOOL_CALLS = "tool_calls"
    CONTENT = "content"
    REASONING_ONLY = "reasoning_only"
    EMPTY = "empty"


def classify_response(message: Message) -> LLMResponseType:
    """将 LLM 响应消息准确分类为一种类型。

    判定优先级（第一场比赛获胜）：
      1. TOOL_CALLS — 消息包含工具调用
      2. CONTENT — 消息包含非空白 TextContent
      3. REASONING_ONLY — 消息有推理但没有可见内容
      4. EMPTY — 没有什么用处

    这个函数是纯粹的：没有副作用，没有日志记录，没有突变。
    """
    if message.tool_calls:
        return LLMResponseType.TOOL_CALLS

    if any(isinstance(c, TextContent) and c.text.strip() for c in message.content):
        return LLMResponseType.CONTENT

    if (
        message.responses_reasoning_item is not None
        or message.reasoning_content is not None
        or message.thinking_blocks
    ):
        return LLMResponseType.REASONING_ONLY

    return LLMResponseType.EMPTY


# ---------------------------------------------------------------------------
# 调度混合
# ---------------------------------------------------------------------------


class ResponseDispatchMixin:
    """每个 ``LLMResponseType`` 的处理程序方法。 混入``Agent``。

    期望宿主类（``Agent``）提供在
    下面的 ``TYPE_CHECKING`` 块。
    """

    # 为 Pyright 声明 — 实际实现位于智能体上。
    if TYPE_CHECKING:
        critic: CriticBase | None

        def _get_action_event(
            self,
            tool_call: MessageToolCall,
            conversation: LocalConversation,
            llm_response_id: str,
            on_event: ConversationCallbackType,
            security_analyzer: SecurityAnalyzerBase | None = None,
            thought: list[TextContent] | None = None,
            reasoning_content: str | None = None,
            thinking_blocks: (
                list[ThinkingBlock | RedactedThinkingBlock] | None
            ) = None,
            responses_reasoning_item: ReasoningItemModel | None = None,
            stream: StreamContext | None = None,
        ) -> ActionEvent | None: ...

        def _execute_actions(
            self,
            conversation: LocalConversation,
            action_events: list[ActionEvent],
            on_event: ConversationCallbackType,
        ) -> None: ...

        async def _aexecute_actions(
            self,
            conversation: LocalConversation,
            action_events: list[ActionEvent],
            on_event: ConversationCallbackType,
        ) -> None: ...

        def _requires_user_confirmation(
            self,
            state: ConversationState,
            action_events: list[ActionEvent],
            on_event: ConversationCallbackType | None = None,
        ) -> bool: ...

        async def _arequires_user_confirmation(
            self,
            conversation: LocalConversation,
            state: ConversationState,
            action_events: list[ActionEvent],
            on_event: ConversationCallbackType,
        ) -> bool: ...

        def _maybe_emit_vllm_tokens(
            self,
            llm_response: LLMResponse,
            on_event: ConversationCallbackType,
        ) -> None: ...

        def _evaluate_with_critic(
            self,
            conversation: LocalConversation,
            event: ActionEvent | MessageEvent,
        ) -> CriticResult | None: ...

    def _handle_tool_calls(
        self,
        message: Message,
        llm_response: LLMResponse,
        conversation: LocalConversation,
        state: ConversationState,
        on_event: ConversationCallbackType,
        stream: StreamContext | None = None,
    ) -> None:
        """处理包含工具调用的 LLM 响应。"""
        if not all(isinstance(c, TextContent) for c in message.content):
            logger.warning(
                "LLM returned tool calls but message content is not all "
                "TextContent - ignoring non-text content"
            )

        thought_content = [c for c in message.content if isinstance(c, TextContent)]

        action_events: list[ActionEvent] = []
        assert message.tool_calls, "classify_response guarantees tool_calls"
        for i, tool_call in enumerate(message.tool_calls):
            action_event = self._get_action_event(
                tool_call,
                conversation=conversation,
                llm_response_id=llm_response.id,
                on_event=on_event,
                security_analyzer=state.security_analyzer,
                thought=thought_content if i == 0 else [],
                reasoning_content=(message.reasoning_content if i == 0 else None),
                thinking_blocks=(list(message.thinking_blocks) if i == 0 else []),
                responses_reasoning_item=(
                    message.responses_reasoning_item if i == 0 else None
                ),
                # 流式文本是该操作的思想，因此第一个操作事件是使槽退出的原因。
                #
                stream=stream if i == 0 else None,
            )
            if action_event is None:
                continue
            action_events.append(action_event)

        if self._requires_user_confirmation(state, action_events, on_event):
            return

        if action_events:
            self._execute_actions(conversation, action_events, on_event)

        self._maybe_emit_vllm_tokens(llm_response, on_event)

    async def _ahandle_tool_calls(
        self,
        message: Message,
        llm_response: LLMResponse,
        conversation: LocalConversation,
        state: ConversationState,
        on_event: ConversationCallbackType,
        stream: StreamContext | None = None,
    ) -> None:
        """异步：meth:`_handle_tool_calls` 的变体。

        将工具执行委托给：meth:`_aexecute_actions`，以便每个工具调用在自己的线程中运
        行，并且通过：func:`asyncio.gather`
         同时调度多个调用。
        """
        if not all(isinstance(c, TextContent) for c in message.content):
            logger.warning(
                "LLM returned tool calls but message content is not all "
                "TextContent - ignoring non-text content"
            )

        thought_content = [c for c in message.content if isinstance(c, TextContent)]

        action_events: list[ActionEvent] = []
        assert message.tool_calls, "classify_response guarantees tool_calls"
        for i, tool_call in enumerate(message.tool_calls):
            action_event = self._get_action_event(
                tool_call,
                conversation=conversation,
                llm_response_id=llm_response.id,
                on_event=on_event,
                security_analyzer=state.security_analyzer,
                thought=thought_content if i == 0 else [],
                reasoning_content=(message.reasoning_content if i == 0 else None),
                thinking_blocks=(list(message.thinking_blocks) if i == 0 else []),
                responses_reasoning_item=(
                    message.responses_reasoning_item if i == 0 else None
                ),
                # 流式文本是该操作的思想，因此第一个操作事件是使槽退出的原因。
                #
                stream=stream if i == 0 else None,
            )
            if action_event is None:
                continue
            action_events.append(action_event)

        if await self._arequires_user_confirmation(
            conversation, state, action_events, on_event
        ):
            return

        if action_events:
            await self._aexecute_actions(conversation, action_events, on_event)

        self._maybe_emit_vllm_tokens(llm_response, on_event)

    def _handle_content_response(
        self,
        message: Message,
        llm_response: LLMResponse,
        conversation: LocalConversation,
        state: ConversationState,
        on_event: ConversationCallbackType,
        stream: StreamContext | None = None,
        *,
        mask_secrets: bool = True,
    ) -> None:
        """使用文本内容处理 LLM 响应 — 结束对话。"""
        self._emit_message_event(
            message,
            llm_response,
            conversation,
            on_event,
            stream,
            mask_secrets=mask_secrets,
        )
        self._maybe_emit_vllm_tokens(llm_response, on_event)
        logger.debug("LLM produced a message response - awaits user input")
        state.execution_status = ConversationExecutionStatus.FINISHED

    def _handle_no_content_response(
        self,
        message: Message,
        llm_response: LLMResponse,
        conversation: LocalConversation,
        state: ConversationState,  # noqa: ARG002
        on_event: ConversationCallbackType,
        stream: StreamContext | None = None,
        *,
        response_type: LLMResponseType,
        mask_secrets: bool = True,
    ) -> None:
        """处理没有面向用户的内容的 LLM 响应。

        涵盖仅推理和空洞的回答。 发出消息事件并发送纠正反馈，以便模型知道它必须生成工
        具调用或面向用户的内容。
        """
        if response_type is LLMResponseType.EMPTY:
            logger.warning("LLM produced empty response - continuing agent loop")
        self._emit_message_event(
            message,
            llm_response,
            conversation,
            on_event,
            stream,
            mask_secrets=mask_secrets,
        )
        self._maybe_emit_vllm_tokens(llm_response, on_event)
        self._send_corrective_nudge(on_event)

    def _emit_message_event(
        self,
        message: Message,
        llm_response: LLMResponse,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
        stream: StreamContext | None = None,
        *,
        mask_secrets: bool = True,
    ) -> MessageEvent:
        """创建并发出一个 MessageEvent，如果已配置，则运行批评家。

        该消息携带其自己的流铸造的 id，因此持有开放槽的客户端将其在
        ``frame.event.id == slot.item_id`` 上退役。
        """
        minted: dict[str, Any] = {}
        if stream is not None and (item_id := stream.claim()):
            minted["id"] = item_id
        msg_event = MessageEvent(
            **minted,
            source="agent",
            llm_message=self._mask_secrets(message, conversation)
            if mask_secrets
            else message,
            llm_response_id=llm_response.id,
        )
        if self.critic is not None and self.critic.mode == "finish_and_message":
            critic_result = self._evaluate_with_critic(conversation, msg_event)
            if critic_result is not None:
                msg_event = msg_event.model_copy(
                    update={"critic_result": critic_result}
                )
        on_event(msg_event)
        # 现在才退休：on_event 可以在坚持的同时提高，并且在此之前退休的槽位会让客户端永
        # 远保持开放状态。
        #
        if stream is not None and minted:
            stream.commit()
        return msg_event

    @staticmethod
    def _mask_secrets(message: Message, conversation: LocalConversation) -> Message:
        """返回 ``message``，并在其文本中屏蔽注册的机密值。

        ``thinking_blocks`` 和 ``responses_reasoning_item`` 保持不变：它们是签名的提
        供者载荷，重写它们会使下一个请
        求时重放的签名无效。
        """
        mask = conversation.state.secret_registry.mask_secrets_in_output
        reasoning = message.reasoning_content
        return message.model_copy(
            update={
                "content": [
                    part.model_copy(update={"text": mask(part.text)})
                    if isinstance(part, TextContent)
                    else part
                    for part in message.content
                ],
                "reasoning_content": mask(reasoning) if reasoning else reasoning,
            }
        )

    def _send_corrective_nudge(self, on_event: ConversationCallbackType) -> None:
        """当没有工具调用且没有内容时注入纠正反馈。

        该模型仍然将其作为用户角色消息接收，但事件源标记它来自框架而不是人类。
        """
        logger.warning(
            "LLM response contained no tool call and no content"
            " - sending corrective feedback"
        )
        nudge = MessageEvent(
            source="environment",
            llm_message=Message(
                role="user",
                content=[
                    TextContent(
                        text=(
                            "Your last response did not include a "
                            "function call or a message. Please "
                            "use a tool to proceed with the task."
                        )
                    )
                ],
            ),
        )
        on_event(nudge)
