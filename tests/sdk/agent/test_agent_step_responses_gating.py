from unittest.mock import MagicMock

import pytest
from litellm.types.utils import ModelResponse
from pydantic import PrivateAttr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.event import MessageEvent
from openhands.sdk.llm import LLM, LLMResponse, Message
from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage


class DummyLLM(LLM):
    _calls: list[str] = PrivateAttr(default_factory=list)
    _call_kwargs: list[dict] = PrivateAttr(default_factory=list)
    _force_responses: bool = PrivateAttr(default=False)

    def __init__(self, *, model: str, force_responses: bool):
        super().__init__(model=model, usage_id="test-llm")
        self._force_responses = force_responses

    def uses_responses_api(self) -> bool:  # 超越门控
        return self._force_responses

    # 最少的存根； 并没有真正调用提供者
    def completion(self, *, messages, tools=None, **kwargs) -> LLMResponse:  # type: ignore[override]
        self._calls.append("completion")
        self._call_kwargs.append(kwargs)
        # 返回不带工具调用的助理消息以结束该步骤
        return LLMResponse(
            message=Message(role="assistant", content=[]),
            metrics=MetricsSnapshot(
                model_name="test",
                accumulated_cost=0.0,
                max_budget_per_task=0.0,
                accumulated_token_usage=TokenUsage(model="test"),
            ),
            raw_response=MagicMock(spec=ModelResponse, id="c1"),
        )

    def responses(self, *, messages, tools=None, **kwargs) -> LLMResponse:  # type: ignore[override]
        self._calls.append("responses")
        self._call_kwargs.append(kwargs)
        return LLMResponse(
            message=Message(role="assistant", content=[]),
            metrics=MetricsSnapshot(
                model_name="test",
                accumulated_cost=0.0,
                max_budget_per_task=0.0,
                accumulated_token_usage=TokenUsage(model="test"),
            ),
            raw_response=MagicMock(spec=ModelResponse, id="r1"),
        )


@pytest.mark.parametrize(
    "force_responses, expected",
    [
        (True, "responses"),
        (False, "completion"),
    ],
)
def test_agent_step_routes_to_responses_or_completion(force_responses, expected):
    llm = DummyLLM(model="test-model", force_responses=force_responses)
    agent = Agent(llm=llm, tools=[])
    convo = Conversation(agent=agent)

    # 在调用 step() 之前触发惰性智能体初始化
    convo._ensure_agent_ready()

    events: list[MessageEvent] = []

    def on_event(e):
        if isinstance(e, MessageEvent):
            events.append(e)

    # 一个步骤应该调用适当的方法并发出一条辅助消息
    agent.step(convo, on_event=on_event)

    assert llm._calls == [expected]
    assert llm._call_kwargs == [
        {
            "add_security_risk_prediction": True,
            "on_token": None,
            "call_context": convo.get_llm_call_context(),
            **({"include": None, "store": False} if force_responses else {}),
        }
    ]
    assert any(isinstance(e, MessageEvent) for e in events)


class ModelGateLLM(LLM):
    _calls: list[str] = PrivateAttr(default_factory=list)

    def __init__(self, *, model: str):
        super().__init__(model=model, usage_id="test-llm")

    def completion(self, *, messages, tools=None, **kwargs) -> LLMResponse:  # type: ignore[override]
        self._calls.append("completion")
        return LLMResponse(
            message=Message(role="assistant", content=[]),
            metrics=MetricsSnapshot(
                model_name="test",
                accumulated_cost=0.0,
                max_budget_per_task=0.0,
                accumulated_token_usage=TokenUsage(model="test"),
            ),
            raw_response=MagicMock(spec=ModelResponse, id="c2"),
        )

    def responses(self, *, messages, tools=None, **kwargs) -> LLMResponse:  # type: ignore[override]
        self._calls.append("responses")
        return LLMResponse(
            message=Message(role="assistant", content=[]),
            metrics=MetricsSnapshot(
                model_name="test",
                accumulated_cost=0.0,
                max_budget_per_task=0.0,
                accumulated_token_usage=TokenUsage(model="test"),
            ),
            raw_response=MagicMock(spec=ModelResponse, id="r2"),
        )


@pytest.mark.parametrize(
    "model, expected",
    [
        ("gpt-5-mini-2025-08-07", "responses"),  # 可响应 model_features
        ("gpt-4o-mini", "completion"),  # 完成路径
    ],
)
def test_agent_step_model_features_gate_to_responses_or_completion(model, expected):
    llm = ModelGateLLM(model=model)
    agent = Agent(llm=llm, tools=[])
    convo = Conversation(agent=agent)

    # 在调用 step() 之前触发惰性智能体初始化
    convo._ensure_agent_ready()

    events: list[MessageEvent] = []

    def on_event(e):
        if isinstance(e, MessageEvent):
            events.append(e)

    agent.step(convo, on_event=on_event)

    assert llm._calls == [expected]
    assert any(isinstance(e, MessageEvent) for e in events)
