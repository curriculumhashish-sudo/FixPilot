import pytest
from pydantic import SecretStr

from openhands.sdk.agent.base import AgentBase
from openhands.sdk.conversation import Conversation, LocalConversation
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.conversation.types import (
    ConversationCallbackType,
    ConversationTokenCallbackType,
)
from openhands.sdk.event.llm_convertible import MessageEvent, SystemPromptEvent
from openhands.sdk.llm import LLM, Message, TextContent


class ConversationDefaultCallbackDummyAgent(AgentBase):
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
        on_event(
            MessageEvent(
                source="agent",
                llm_message=Message(role="assistant", content=[TextContent(text="ok")]),
            )
        )


def test_default_callback_appends_on_init():
    agent = ConversationDefaultCallbackDummyAgent()
    events_seen: list[str] = []

    conversation = Conversation(
        agent=agent, callbacks=[lambda e: events_seen.append(e.id)]
    )

    # 智能体初始化是惰性的 - 触发它生成 SystemPromptEvent
    conversation._ensure_agent_ready()

    assert len(conversation.state.events) == 1
    assert isinstance(conversation.state.events[0], SystemPromptEvent)
    assert conversation.state.events[0].id in events_seen


def test_send_message_appends_once():
    agent = ConversationDefaultCallbackDummyAgent()
    seen_ids: list[str] = []

    def user_cb(event):
        seen_ids.append(event.id)

    conversation = Conversation(agent=agent, callbacks=[user_cb])

    conversation.send_message(Message(role="user", content=[TextContent(text="hi")]))

    # 现在我们应该有两个事件：初始系统提示词和用户消息
    assert len(conversation.state.events) == 2
    assert isinstance(conversation.state.events[-1], MessageEvent)

    # 确保用户消息事件在状态中准确附加一次
    last_id = conversation.state.events[-1].id
    assert sum(1 for e in conversation.state.events if e.id == last_id) == 1

    # 确保回调看到了这两个事件
    assert set(seen_ids) == {e.id for e in conversation.state.events}


def test_user_callback_runs_after_event_is_persisted():
    """用户回调 (e.g. 套接字发布）之前绝不能看到事件
    它是持久的：它应该已经能够通过 ``EventLog.get_index`` 解析事件的序列号。
    """
    agent = ConversationDefaultCallbackDummyAgent()
    seen_indices: list[int] = []

    conversation = Conversation(
        agent=agent,
        callbacks=[
            lambda e: seen_indices.append(conversation.state.events.get_index(e.id))
        ],
    )

    conversation._ensure_agent_ready()

    assert seen_indices == [0]


def test_persist_failure_blocks_downstream_callback():
    """如果引发持续事件，则没有用户回调为其运行：什么都没有
    宣布了一个从未到达磁盘的事件。
    """
    agent = ConversationDefaultCallbackDummyAgent()
    seen_ids: list[str] = []

    conversation = Conversation(
        agent=agent, callbacks=[lambda e: seen_ids.append(e.id)]
    )
    conversation._ensure_agent_ready()

    duplicate = conversation.state.events[0]
    assert seen_ids == [duplicate.id]

    # 重新发出 ID 已在日志中的事件会使 EventLog.append 引发。 用户回调不得看到此尝试。
    #
    with pytest.raises(ValueError, match="already exists"):
        conversation._on_event(duplicate)

    assert seen_ids == [duplicate.id]
