"""内容策略块会软恢复而不是硬错误。

请参阅 https://github.com/OpenHands/software-agent-sdk/issues/3798. Anthropic输出内容
策略块表面为
``LLMContentPolicyViolationError``。 智能体应该发出一个非致命的用户微移并返回，以便运
行循环继续，而不是让它逃脱 ``step``
/``astep`` 并成为致命的
``ConversationErrorEvent``.
"""

import pytest
from pydantic import PrivateAttr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.event import MessageEvent
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.llm import LLM
from openhands.sdk.llm.exceptions import LLMContentPolicyViolationError


class ContentPolicyRaisingLLM(LLM):
    _force_responses: bool = PrivateAttr(default=False)

    def __init__(self, *, model: str = "test-model", force_responses: bool = False):
        super().__init__(model=model, usage_id="test-llm")
        self._force_responses = force_responses

    def uses_responses_api(self) -> bool:  # 超越门控
        return self._force_responses

    def completion(self, *, messages, tools=None, **kwargs):  # type: ignore[override]
        raise LLMContentPolicyViolationError()

    async def acompletion(self, *, messages, tools=None, **kwargs):  # type: ignore[override]
        raise LLMContentPolicyViolationError()

    def responses(self, *, messages, tools=None, **kwargs):  # type: ignore[override]
        raise LLMContentPolicyViolationError()

    async def aresponses(self, *, messages, tools=None, **kwargs):  # type: ignore[override]
        raise LLMContentPolicyViolationError()


def _content_policy_nudges(events: list) -> list[MessageEvent]:
    return [
        e
        for e in events
        if isinstance(e, MessageEvent)
        and e.source == "user"
        and any(
            "content filter" in getattr(c, "text", "") for c in e.llm_message.content
        )
    ]


@pytest.mark.parametrize("force_responses", [True, False])
def test_step_emits_soft_nudge_on_content_policy(force_responses: bool):
    llm = ContentPolicyRaisingLLM(force_responses=force_responses)
    agent = Agent(llm=llm, tools=[])
    convo = Conversation(agent=agent)
    convo._ensure_agent_ready()

    seen: list = []
    # 不得引发——内容策略块是可恢复的。
    agent.step(convo, on_event=seen.append)

    assert len(_content_policy_nudges(seen)) == 1
    assert not any(isinstance(e, ConversationErrorEvent) for e in seen)


@pytest.mark.parametrize("force_responses", [True, False])
@pytest.mark.asyncio
async def test_astep_emits_soft_nudge_on_content_policy(force_responses: bool):
    llm = ContentPolicyRaisingLLM(force_responses=force_responses)
    agent = Agent(llm=llm, tools=[])
    convo = Conversation(agent=agent)
    convo._ensure_agent_ready()

    seen: list = []
    await agent.astep(convo, on_event=seen.append)

    assert len(_content_policy_nudges(seen)) == 1
    assert not any(isinstance(e, ConversationErrorEvent) for e in seen)
