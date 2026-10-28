import uuid

from pydantic import SecretStr

from openhands.sdk.agent.base import AgentBase
from openhands.sdk.conversation import Conversation, LocalConversation
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.conversation.types import (
    ConversationCallbackType,
    ConversationTokenCallbackType,
)
from openhands.sdk.event.llm_convertible import SystemPromptEvent
from openhands.sdk.llm import LLM, TextContent
from openhands.sdk.security.confirmation_policy import AlwaysConfirm, NeverConfirm


class ConversationIdDummyAgent(AgentBase):
    def __init__(self):
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        super().__init__(llm=llm, tools=[])

    def init_state(
        self, state: ConversationState, on_event: ConversationCallbackType
    ) -> None:
        event = SystemPromptEvent(
            source="agent", system_prompt=TextContent(text="dummy"), tools=[]
        )
        on_event(event)

    def step(
        self,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
        on_token: ConversationTokenCallbackType | None = None,
    ) -> None:
        pass


def test_conversation_has_unique_id():
    """测试每个对话是否都有唯一的 UUID。"""
    agent = ConversationIdDummyAgent()
    conversation = Conversation(agent=agent)

    # 检查 id 是否存在并且是 UUID
    assert hasattr(conversation, "id")
    assert isinstance(conversation.id, uuid.UUID)


def test_conversation_ids_are_unique():
    """测试不同的对话获得不同的 ID。"""
    agent1 = ConversationIdDummyAgent()
    agent2 = ConversationIdDummyAgent()

    conversation1 = Conversation(agent=agent1)
    conversation2 = Conversation(agent=agent2)

    # 检查ID是否不同
    assert conversation1.id != conversation2.id

    # 检查两者都 UUIDs
    assert isinstance(conversation1.id, uuid.UUID)
    assert isinstance(conversation2.id, uuid.UUID)


def test_conversation_id_persists():
    """测试对话 ID 在对话生命周期内不会更改。"""  # noqa: E501
    agent = ConversationIdDummyAgent()
    conversation = Conversation(agent=agent)

    original_id = conversation.id

    # 执行一些可能影响通话的操作
    conversation.set_confirmation_policy(AlwaysConfirm())
    conversation.set_confirmation_policy(NeverConfirm())

    # 确认ID没有改变
    assert conversation.id == original_id


def test_conversation_pins_prompt_cache_key_to_id():
    """回归测试 #2904。"""
    agent = ConversationIdDummyAgent()
    conversation = Conversation(agent=agent)
    assert conversation.get_llm_call_context().prompt_cache_key == str(conversation.id)
