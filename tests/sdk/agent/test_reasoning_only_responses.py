"""使用仅推理响应测试智能体行为（e.g.、GPT-5 法典）。"""

from unittest.mock import MagicMock

from litellm.types.utils import ModelResponse
from pydantic import PrivateAttr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event.llm_convertible.message import MessageEvent
from openhands.sdk.llm import LLM, LLMResponse, Message, MessageToolCall, TextContent
from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage


class ReasoningOnlyLLM(LLM):
    """测试 LLM 首先返回仅推理响应，然后完成。"""

    _call_count: int = PrivateAttr(default=0)

    def __init__(self):
        super().__init__(model="test-model")

    def completion(  # type: ignore[override]
        self, *, messages, tools=None, **kwargs
    ) -> LLMResponse:
        self._call_count += 1

        if self._call_count == 1:
            # 第一次调用：返回仅推理响应
            message = Message(role="assistant")
            message.reasoning_content = "Let me think about this..."
            return LLMResponse(
                message=message,
                metrics=MetricsSnapshot(
                    model_name="test",
                    accumulated_cost=0.0,
                    max_budget_per_task=0.0,
                    accumulated_token_usage=TokenUsage(model="test"),
                ),
                raw_response=MagicMock(spec=ModelResponse, id="r1"),
            )
        else:
            # 第二次调用：返回完成操作
            message = Message(role="assistant")
            message.tool_calls = [
                MessageToolCall(
                    id="finish-call-1",
                    name="finish",
                    arguments='{"message": "Task completed"}',
                    origin="completion",
                )
            ]
            return LLMResponse(
                message=message,
                metrics=MetricsSnapshot(
                    model_name="test",
                    accumulated_cost=0.0,
                    max_budget_per_task=0.0,
                    accumulated_token_usage=TokenUsage(model="test"),
                ),
                raw_response=MagicMock(spec=ModelResponse, id="r2"),
            )


def test_agent_continues_after_reasoning_only_response():
    """测试智能体在收到仅推理响应后是否继续循环。"""
    llm = ReasoningOnlyLLM()
    agent = Agent(llm=llm, tools=[])
    conversation = Conversation(agent=agent)

    # 发送初始用户消息
    conversation.send_message("Please solve this task")

    # 运行对话
    conversation.run()

    # 验证智能体被调用两次（仅推理，然后完成）
    assert llm._call_count == 2

    # 验证对话已完成
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED


class ContentOnlyLLM(LLM):
    """返回仅内容响应的测试 LLM（应立即完成）。"""

    _call_count: int = PrivateAttr(default=0)

    def __init__(self):
        super().__init__(model="test-model")

    def completion(  # type: ignore[override]
        self, *, messages, tools=None, **kwargs
    ) -> LLMResponse:
        self._call_count += 1

        # 仅返回内容响应 - 应立即结束对话
        message = Message(role="assistant")
        message.content = [TextContent(text="I'm thinking about this...")]
        return LLMResponse(
            message=message,
            metrics=MetricsSnapshot(
                model_name="test",
                accumulated_cost=0.0,
                max_budget_per_task=0.0,
                accumulated_token_usage=TokenUsage(model="test"),
            ),
            raw_response=MagicMock(spec=ModelResponse, id="r1"),
        )


def test_agent_finishes_after_content_only_response():
    """测试智能体在收到纯内容响应后立即完成。"""
    llm = ContentOnlyLLM()
    agent = Agent(llm=llm, tools=[])
    conversation = Conversation(agent=agent)

    conversation.send_message("Analyze this")
    conversation.run()

    # 验证智能体被调用一次 - 内容响应立即完成
    assert llm._call_count == 1
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED

    # 验证内容消息已发出
    msg_events = [
        e
        for e in conversation.state.events
        if isinstance(e, MessageEvent) and e.source == "agent"
    ]
    assert len(msg_events) == 1
    assert any(
        isinstance(c, TextContent) and c.text == "I'm thinking about this..."
        for c in msg_events[0].llm_message.content
    )


class EmptyResponseLLM(LLM):
    """首先测试LLM返回空响应，然后完成。"""

    _call_count: int = PrivateAttr(default=0)

    def __init__(self):
        super().__init__(model="test-model")

    def completion(  # type: ignore[override]
        self, *, messages, tools=None, **kwargs
    ) -> LLMResponse:
        self._call_count += 1

        if self._call_count == 1:
            # 第一次调用：返回空响应（边缘情况）
            message = Message(role="assistant")
            message.content = []
            return LLMResponse(
                message=message,
                metrics=MetricsSnapshot(
                    model_name="test",
                    accumulated_cost=0.0,
                    max_budget_per_task=0.0,
                    accumulated_token_usage=TokenUsage(model="test"),
                ),
                raw_response=MagicMock(spec=ModelResponse, id="r1"),
            )
        else:
            # 第二次调用：返回完成操作
            message = Message(role="assistant")
            message.tool_calls = [
                MessageToolCall(
                    id="finish-call-3",
                    name="finish",
                    arguments='{"message": "Done"}',
                    origin="completion",
                )
            ]
            return LLMResponse(
                message=message,
                metrics=MetricsSnapshot(
                    model_name="test",
                    accumulated_cost=0.0,
                    max_budget_per_task=0.0,
                    accumulated_token_usage=TokenUsage(model="test"),
                ),
                raw_response=MagicMock(spec=ModelResponse, id="r2"),
            )


def test_agent_handles_empty_response():
    """测试智能体是否继续，即使响应完全为空。"""
    llm = EmptyResponseLLM()
    agent = Agent(llm=llm, tools=[])
    conversation = Conversation(agent=agent)

    conversation.send_message("Test")
    conversation.run()

    # 验证智能体空响应后继续
    assert llm._call_count == 2
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED
