import asyncio
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from openhands.sdk.agent.acp_agent import ACPAgent
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.conversation import Conversation, LocalConversation
from openhands.sdk.conversation.impl.local_conversation import (
    ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID,
    ACP_LAST_PROMPT_USER_MESSAGE_ID,
)
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.conversation.types import (
    ConversationCallbackType,
    ConversationTokenCallbackType,
)
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from openhands.sdk.event.llm_convertible import MessageEvent, SystemPromptEvent
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.skills import KeywordTrigger, Skill


class SendMessageDummyAgent(AgentBase):
    def __init__(self, agent_context: AgentContext | None = None):
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        super().__init__(llm=llm, tools=[], agent_context=agent_context)

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


def test_send_message_with_string_creates_correct_message():
    """测试带有字符串的 send_message 是否创建正确的消息结构。"""
    agent = SendMessageDummyAgent()
    conversation = Conversation(agent=agent)

    test_text = "Hello, world!"
    conversation.send_message(test_text)

    # 应该有系统提示词+用户消息
    assert len(conversation.state.events) == 2

    # 检查用户消息事件
    user_event = conversation.state.events[-1]
    assert isinstance(user_event, MessageEvent)
    assert user_event.source == "user"

    # 检查消息结构
    message = user_event.llm_message
    assert message.role == "user"
    assert len(message.content) == 1
    assert isinstance(message.content[0], TextContent)
    assert message.content[0].text == test_text


def test_send_message_string_equivalent_to_message_object():
    """测试使用字符串的 send_message 是否与使用 Message 对象产生相同的结果。"""  # noqa: E501
    agent1 = SendMessageDummyAgent()
    agent2 = SendMessageDummyAgent()

    conversation1 = Conversation(agent=agent1)
    conversation2 = Conversation(agent=agent2)

    test_text = "Test message"

    # 将 send_message 与字符串一起使用
    conversation1.send_message(test_text)

    # 将 send_message 与 Message 对象一起使用
    message = Message(role="user", content=[TextContent(text=test_text)])
    conversation2.send_message(message)

    # 两者应该具有相同数量的事件
    assert len(conversation1.state.events) == len(conversation2.state.events)

    # 用户消息事件应该是等效的
    user_event1 = conversation1.state.events[-1]
    user_event2 = conversation2.state.events[-1]

    assert isinstance(user_event1, MessageEvent)
    assert isinstance(user_event2, MessageEvent)

    assert user_event1.source == user_event2.source
    assert user_event1.llm_message.role == user_event2.llm_message.role
    assert isinstance(user_event1.llm_message.content[0], TextContent)
    assert isinstance(user_event2.llm_message.content[0], TextContent)
    assert (
        user_event1.llm_message.content[0].text
        == user_event2.llm_message.content[0].text
    )


def test_send_message_with_empty_string():
    """测试 send_message 是否适用于空字符串。"""
    agent = SendMessageDummyAgent()
    conversation = Conversation(agent=agent)

    conversation.send_message("")

    # 应该有系统提示词+用户消息
    assert len(conversation.state.events) == 2

    user_event = conversation.state.events[-1]
    assert isinstance(user_event, MessageEvent)
    assert isinstance(user_event.llm_message.content[0], TextContent)
    assert user_event.llm_message.content[0].text == ""


def test_send_message_with_multiline_string():
    """测试 send_message 是否适用于多行字符串。"""
    agent = SendMessageDummyAgent()
    conversation = Conversation(agent=agent)

    test_text = "Line 1\nLine 2\nLine 3"
    conversation.send_message(test_text)

    # 应该有系统提示词+用户消息
    assert len(conversation.state.events) == 2

    user_event = conversation.state.events[-1]
    assert isinstance(user_event, MessageEvent)
    assert isinstance(user_event.llm_message.content[0], TextContent)
    assert user_event.llm_message.content[0].text == test_text


def test_send_message_with_message_object():
    """测试 send_message 是否适用于 Message 对象（现有功能）。"""
    agent = SendMessageDummyAgent()
    conversation = Conversation(agent=agent)

    test_text = "Test message"
    message = Message(role="user", content=[TextContent(text=test_text)])
    conversation.send_message(message)

    # 应该有系统提示词+用户消息
    assert len(conversation.state.events) == 2

    user_event = conversation.state.events[-1]
    assert isinstance(user_event, MessageEvent)
    assert user_event.source == "user"
    assert user_event.llm_message.role == "user"
    assert len(user_event.llm_message.content) == 1
    assert isinstance(user_event.llm_message.content[0], TextContent)
    assert user_event.llm_message.content[0].text == test_text


def test_acp_send_message_defers_initialization_until_run(tmp_path):
    """ACP 对话应在启动 ACP 引导之前将消息排入队列。"""

    agent = ACPAgent(acp_command=["echo", "test"])
    conversation = LocalConversation(agent=agent, workspace=str(tmp_path))
    test_text = "Hello from ACP"

    def _finish_immediately(self, conv, on_event, on_token=None):
        conv.state.execution_status = ConversationExecutionStatus.FINISHED

    with (
        patch.object(ACPAgent, "init_state", autospec=True) as mock_init_state,
        patch.object(
            ACPAgent,
            "step",
            autospec=True,
            side_effect=_finish_immediately,
        ) as mock_step,
    ):
        conversation.send_message(test_text)

        assert mock_init_state.call_count == 0
        assert mock_step.call_count == 0
        assert len(conversation.state.events) == 1
        user_event = conversation.state.events[-1]
        assert isinstance(user_event, MessageEvent)
        assert user_event.source == "user"
        assert user_event.llm_message.role == "user"
        assert len(user_event.llm_message.content) == 1
        assert isinstance(user_event.llm_message.content[0], TextContent)
        assert user_event.llm_message.content[0].text == test_text

        conversation.run()

        assert mock_init_state.call_count == 1
        assert mock_step.call_count == 1
        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )
        assert conversation.state.events[-1] == user_event


@pytest.mark.asyncio
async def test_acp_arun_accepts_user_message_while_step_is_in_flight(tmp_path):
    """当长异步轮运行时，ACP 用户消息应为已持久化。"""

    agent = ACPAgent(acp_command=["echo", "test"])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        max_iteration_per_run=4,
        stuck_detection=False,
    )
    conversation.send_message("initial request")

    first_step_started = asyncio.Event()
    release_first_step = asyncio.Event()
    second_step_seen = asyncio.Event()
    prompts_seen: list[str] = []

    def user_text(event: MessageEvent | None) -> str:
        assert event is not None
        content = event.llm_message.content[0]
        assert isinstance(content, TextContent)
        return content.text

    async def blocking_astep(
        self,  # noqa: ARG001
        conv: LocalConversation,  # noqa: ARG001
        on_event: ConversationCallbackType,  # noqa: ARG001
        on_token: ConversationTokenCallbackType | None = None,  # noqa: ARG001
        prompt_message: MessageEvent | None = None,
    ) -> None:
        prompts_seen.append(user_text(prompt_message))
        if len(prompts_seen) == 1:
            first_step_started.set()
            await release_first_step.wait()
        else:
            second_step_seen.set()
        conv.state.execution_status = ConversationExecutionStatus.FINISHED

    with (
        patch.object(ACPAgent, "init_state", autospec=True),
        patch.object(ACPAgent, "astep", new=blocking_astep),
    ):
        run_task = asyncio.create_task(conversation.arun())
        send_done = asyncio.Event()

        async def send_intervening_message() -> None:
            await asyncio.to_thread(conversation.send_message, "intervening request")
            send_done.set()

        await asyncio.wait_for(first_step_started.wait(), timeout=1.0)
        send_task = asyncio.create_task(send_intervening_message())

        try:
            await asyncio.wait_for(send_done.wait(), timeout=5.0)
        finally:
            release_first_step.set()
            await asyncio.wait_for(send_task, timeout=1.0)
            await asyncio.wait_for(second_step_seen.wait(), timeout=1.0)
            await asyncio.wait_for(run_task, timeout=1.0)

    assert prompts_seen == ["initial request", "intervening request"]


@pytest.mark.asyncio
async def test_acp_arun_marks_queued_message_running_after_finish_gap(tmp_path):
    """即使发送看到 FINISHED，排队的 ACP 消息也应恢复 RUNNING。"""

    agent = ACPAgent(acp_command=["echo", "test"])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        max_iteration_per_run=4,
        stuck_detection=False,
    )
    conversation.send_message("initial request")

    first_step_finished = asyncio.Event()
    release_first_step = asyncio.Event()
    second_step_seen = asyncio.Event()
    second_step_statuses: list[ConversationExecutionStatus] = []
    prompts_seen: list[str] = []

    def user_text(event: MessageEvent | None) -> str:
        assert event is not None
        content = event.llm_message.content[0]
        assert isinstance(content, TextContent)
        return content.text

    async def blocking_astep(
        self,  # noqa: ARG001
        conv: LocalConversation,
        on_event: ConversationCallbackType,  # noqa: ARG001
        on_token: ConversationTokenCallbackType | None = None,  # noqa: ARG001
        prompt_message: MessageEvent | None = None,
    ) -> None:
        prompts_seen.append(user_text(prompt_message))
        if len(prompts_seen) == 1:
            conv.state.execution_status = ConversationExecutionStatus.FINISHED
            first_step_finished.set()
            await release_first_step.wait()
        else:
            second_step_statuses.append(conv.state.execution_status)
            conv.state.execution_status = ConversationExecutionStatus.FINISHED
            second_step_seen.set()

    with (
        patch.object(ACPAgent, "init_state", autospec=True),
        patch.object(ACPAgent, "astep", new=blocking_astep),
    ):
        run_task = asyncio.create_task(conversation.arun())
        await asyncio.wait_for(first_step_finished.wait(), timeout=1.0)
        await asyncio.to_thread(conversation.send_message, "intervening request")
        assert conversation.state.execution_status == ConversationExecutionStatus.IDLE
        release_first_step.set()
        await asyncio.wait_for(second_step_seen.wait(), timeout=1.0)
        await asyncio.wait_for(run_task, timeout=1.0)

    assert prompts_seen == ["initial request", "intervening request"]
    assert second_step_statuses == [ConversationExecutionStatus.RUNNING]


@pytest.mark.asyncio
async def test_acp_arun_processes_multiple_queued_messages_fifo(tmp_path):
    """ACP arun 不应跳过提示词期间排队的较早消息。"""

    agent = ACPAgent(acp_command=["echo", "test"])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        max_iteration_per_run=4,
        stuck_detection=False,
    )
    conversation.send_message("initial request")

    first_step_finished = asyncio.Event()
    release_first_step = asyncio.Event()
    all_queued_steps_seen = asyncio.Event()
    prompts_seen: list[str] = []

    def user_text(event: MessageEvent | None) -> str:
        assert event is not None
        content = event.llm_message.content[0]
        assert isinstance(content, TextContent)
        return content.text

    async def blocking_astep(
        self,  # noqa: ARG001
        conv: LocalConversation,
        on_event: ConversationCallbackType,  # noqa: ARG001
        on_token: ConversationTokenCallbackType | None = None,  # noqa: ARG001
        prompt_message: MessageEvent | None = None,
    ) -> None:
        prompts_seen.append(user_text(prompt_message))
        conv.state.execution_status = ConversationExecutionStatus.FINISHED
        if len(prompts_seen) == 1:
            first_step_finished.set()
            await release_first_step.wait()
        elif prompts_seen[-2:] == ["queued one", "queued two"]:
            all_queued_steps_seen.set()

    with (
        patch.object(ACPAgent, "init_state", autospec=True),
        patch.object(ACPAgent, "astep", new=blocking_astep),
    ):
        run_task = asyncio.create_task(conversation.arun())
        await asyncio.wait_for(first_step_finished.wait(), timeout=1.0)
        await asyncio.to_thread(conversation.send_message, "queued one")
        await asyncio.to_thread(conversation.send_message, "queued two")
        release_first_step.set()
        await asyncio.wait_for(all_queued_steps_seen.wait(), timeout=1.0)
        await asyncio.wait_for(run_task, timeout=1.0)

    assert prompts_seen == ["initial request", "queued one", "queued two"]


@pytest.mark.asyncio
async def test_acp_arun_processes_initial_queued_messages_fifo(tmp_path):
    """ACP arun 应按照从最旧到最新的顺序处理预运行排队消息。"""

    agent = ACPAgent(acp_command=["echo", "test"])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        max_iteration_per_run=3,
        stuck_detection=False,
    )
    conversation.send_message("queued one")
    conversation.send_message("queued two")

    prompts_seen: list[str] = []

    def user_text(event: MessageEvent | None) -> str:
        assert event is not None
        content = event.llm_message.content[0]
        assert isinstance(content, TextContent)
        return content.text

    async def blocking_astep(
        self,  # noqa: ARG001
        conv: LocalConversation,
        on_event: ConversationCallbackType,  # noqa: ARG001
        on_token: ConversationTokenCallbackType | None = None,  # noqa: ARG001
        prompt_message: MessageEvent | None = None,
    ) -> None:
        prompts_seen.append(user_text(prompt_message))
        conv.state.execution_status = ConversationExecutionStatus.FINISHED

    with (
        patch.object(ACPAgent, "init_state", autospec=True),
        patch.object(ACPAgent, "astep", new=blocking_astep),
    ):
        await asyncio.wait_for(conversation.arun(), timeout=1.0)

    assert prompts_seen == ["queued one", "queued two"]


@pytest.mark.asyncio
async def test_acp_arun_does_not_reprompt_when_cursor_is_current(tmp_path):
    """ACP 当没有排队的用户消息时，arun 应该完成。"""

    agent = ACPAgent(acp_command=["echo", "test"])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        max_iteration_per_run=3,
        stuck_detection=False,
    )
    conversation.send_message("already processed")
    conversation.state.agent_state = {
        ACP_LAST_PROMPT_USER_MESSAGE_ID: conversation.state.last_user_message_id
    }

    prompts_seen: list[MessageEvent | None] = []

    async def blocking_astep(
        self,  # noqa: ARG001
        conv: LocalConversation,  # noqa: ARG001
        on_event: ConversationCallbackType,  # noqa: ARG001
        on_token: ConversationTokenCallbackType | None = None,  # noqa: ARG001
        prompt_message: MessageEvent | None = None,
    ) -> None:
        prompts_seen.append(prompt_message)

    with (
        patch.object(ACPAgent, "init_state", autospec=True),
        patch.object(ACPAgent, "astep", new=blocking_astep),
    ):
        await asyncio.wait_for(conversation.arun(), timeout=1.0)

    assert prompts_seen == []
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED


@pytest.mark.asyncio
async def test_acp_arun_recovers_when_persisted_cursor_is_missing(tmp_path):
    """过时的已持久化 ACP 游标不应紧密循环运行。"""

    agent = ACPAgent(acp_command=["echo", "test"])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        max_iteration_per_run=3,
        stuck_detection=False,
    )
    conversation.send_message("surviving message")
    surviving_message_id = conversation.state.last_user_message_id
    conversation.state.agent_state = {ACP_LAST_PROMPT_USER_MESSAGE_ID: "missing-id"}

    prompts_seen: list[str] = []

    def user_text(event: MessageEvent | None) -> str:
        assert event is not None
        content = event.llm_message.content[0]
        assert isinstance(content, TextContent)
        return content.text

    async def record_astep(
        self,  # noqa: ARG001
        conv: LocalConversation,
        on_event: ConversationCallbackType,  # noqa: ARG001
        on_token: ConversationTokenCallbackType | None = None,  # noqa: ARG001
        prompt_message: MessageEvent | None = None,
    ) -> None:
        prompts_seen.append(user_text(prompt_message))
        conv.state.execution_status = ConversationExecutionStatus.FINISHED

    with (
        patch.object(ACPAgent, "init_state", autospec=True),
        patch.object(ACPAgent, "astep", new=record_astep),
    ):
        await asyncio.wait_for(conversation.arun(), timeout=1.0)

    assert prompts_seen == ["surviving message"]
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED
    assert (
        conversation.state.agent_state.get(ACP_LAST_PROMPT_USER_MESSAGE_ID)
        == surviving_message_id
    )


@pytest.mark.asyncio
async def test_acp_arun_sends_stop_hook_feedback_to_acp(tmp_path):
    """ACP 停止挂机反馈应作为下一个提示词排队。"""

    agent = ACPAgent(acp_command=["echo", "test"])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        max_iteration_per_run=3,
        stuck_detection=False,
    )
    conversation.send_message("initial request")

    hook = MagicMock()
    hook.run_stop.side_effect = [(False, "please continue"), (True, None)]
    conversation._hook_processor = hook
    prompts_seen: list[str] = []

    def user_text(event: MessageEvent | None) -> str:
        assert event is not None
        content = event.llm_message.content[0]
        assert isinstance(content, TextContent)
        return content.text

    async def finish_astep(
        self,  # noqa: ARG001
        conv: LocalConversation,
        on_event: ConversationCallbackType,  # noqa: ARG001
        on_token: ConversationTokenCallbackType | None = None,  # noqa: ARG001
        prompt_message: MessageEvent | None = None,
    ) -> None:
        prompts_seen.append(user_text(prompt_message))
        conv.state.execution_status = ConversationExecutionStatus.FINISHED

    with (
        patch.object(ACPAgent, "init_state", autospec=True),
        patch.object(ACPAgent, "astep", new=finish_astep),
    ):
        await asyncio.wait_for(conversation.arun(), timeout=1.0)

    assert hook.run_stop.call_count == 2
    assert prompts_seen == [
        "initial request",
        "[Stop hook feedback] please continue",
    ]
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED


@pytest.mark.asyncio
async def test_acp_arun_rechecks_messages_before_finishing(tmp_path):
    """附加在完成间隙中的用户消息应在同一运行中发送。"""

    agent = ACPAgent(acp_command=["echo", "test"])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        max_iteration_per_run=3,
        stuck_detection=False,
    )
    conversation.send_message("already processed")
    conversation.state.agent_state = {
        ACP_LAST_PROMPT_USER_MESSAGE_ID: conversation.state.last_user_message_id
    }
    conversation._agent_ready = True

    prompts_seen: list[str] = []

    def user_text(event: MessageEvent | None) -> str:
        assert event is not None
        content = event.llm_message.content[0]
        assert isinstance(content, TextContent)
        return content.text

    async def record_astep(
        self,  # noqa: ARG001
        conv: LocalConversation,
        on_event: ConversationCallbackType,  # noqa: ARG001
        on_token: ConversationTokenCallbackType | None = None,  # noqa: ARG001
        prompt_message: MessageEvent | None = None,
    ) -> None:
        prompts_seen.append(user_text(prompt_message))
        conv.state.execution_status = ConversationExecutionStatus.FINISHED

    original_exit = ConversationState.__exit__
    exit_count = 0
    injected = False

    def inject_after_empty_selection(
        state: ConversationState, exc_type, exc_val, exc_tb
    ) -> None:
        nonlocal exit_count, injected
        original_exit(state, exc_type, exc_val, exc_tb)
        if state is conversation.state:
            exit_count += 1
            if exit_count == 2 and not injected:
                injected = True
                conversation.send_message("arrived in finish gap")

    with (
        patch.object(ConversationState, "__exit__", new=inject_after_empty_selection),
        patch.object(ACPAgent, "init_state", autospec=True),
        patch.object(ACPAgent, "astep", new=record_astep),
    ):
        await asyncio.wait_for(conversation.arun(), timeout=1.0)

    assert injected is True
    assert prompts_seen == ["arrived in finish gap"]
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED
    assert (
        conversation.state.agent_state.get(ACP_LAST_PROMPT_USER_MESSAGE_ID)
        == conversation.state.last_user_message_id
    )


@pytest.mark.asyncio
async def test_acp_arun_does_not_commit_cursor_on_explicit_interrupt(tmp_path):
    """显式中断应该使进行中的 ACP 提示词可重试。"""

    agent = ACPAgent(acp_command=["echo", "test"])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        max_iteration_per_run=3,
        stuck_detection=False,
    )
    conversation.send_message("cancel me")
    first_message_id = conversation.state.last_user_message_id

    prompt_started = asyncio.Event()

    async def blocking_astep(
        self,  # noqa: ARG001
        conv: LocalConversation,  # noqa: ARG001
        on_event: ConversationCallbackType,  # noqa: ARG001
        on_token: ConversationTokenCallbackType | None = None,  # noqa: ARG001
        prompt_message: MessageEvent | None = None,  # noqa: ARG001
    ) -> None:
        prompt_started.set()
        await asyncio.Event().wait()

    with (
        patch.object(ACPAgent, "init_state", autospec=True),
        patch.object(ACPAgent, "astep", new=blocking_astep),
    ):
        task = asyncio.create_task(conversation.arun())
        await asyncio.wait_for(prompt_started.wait(), timeout=1.0)
        conversation.interrupt()
        await asyncio.wait_for(task, timeout=1.0)

    assert conversation.state.execution_status == ConversationExecutionStatus.PAUSED
    assert (
        conversation.state.agent_state.get(ACP_LAST_PROMPT_USER_MESSAGE_ID)
        != first_message_id
    )
    assert ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID not in conversation.state.agent_state


@pytest.mark.asyncio
async def test_acp_arun_commits_cursor_when_cancelled_prompt_completed(tmp_path):
    """已完成的 ACP 提示词不应在取消之后重播。"""

    agent = ACPAgent(acp_command=["echo", "test"])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        max_iteration_per_run=3,
        stuck_detection=False,
    )
    conversation.send_message("complete during cancel")
    first_message_id = conversation.state.last_user_message_id
    prompts_seen: list[str] = []

    async def finishing_cancelled_astep(
        self,  # noqa: ARG001
        conv: LocalConversation,
        on_event: ConversationCallbackType,  # noqa: ARG001
        on_token: ConversationTokenCallbackType | None = None,  # noqa: ARG001
        prompt_message: MessageEvent | None = None,
    ) -> None:
        assert prompt_message is not None
        content = prompt_message.llm_message.content[0]
        assert isinstance(content, TextContent)
        prompts_seen.append(content.text)
        conv.state.execution_status = ConversationExecutionStatus.FINISHED
        raise asyncio.CancelledError

    with (
        patch.object(ACPAgent, "init_state", autospec=True),
        patch.object(ACPAgent, "astep", new=finishing_cancelled_astep),
    ):
        await asyncio.wait_for(conversation.arun(), timeout=1.0)
        assert conversation.state.execution_status == ConversationExecutionStatus.PAUSED
        await asyncio.wait_for(conversation.arun(), timeout=1.0)

    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED
    assert (
        conversation.state.agent_state.get(ACP_LAST_PROMPT_USER_MESSAGE_ID)
        == first_message_id
    )
    assert ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID not in conversation.state.agent_state
    assert prompts_seen == ["complete during cancel"]


@pytest.mark.asyncio
async def test_acp_arun_resumes_queued_messages_fifo_after_iteration_cap(tmp_path):
    """排队的 ACP 消息在后续运行中应保持为 FIFO。"""

    agent = ACPAgent(acp_command=["echo", "test"])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        max_iteration_per_run=1,
        stuck_detection=False,
    )
    conversation.send_message("initial request")

    first_step_finished = asyncio.Event()
    release_first_step = asyncio.Event()
    prompts_seen: list[str] = []

    def user_text(event: MessageEvent | None) -> str:
        assert event is not None
        content = event.llm_message.content[0]
        assert isinstance(content, TextContent)
        return content.text

    async def blocking_astep(
        self,  # noqa: ARG001
        conv: LocalConversation,
        on_event: ConversationCallbackType,  # noqa: ARG001
        on_token: ConversationTokenCallbackType | None = None,  # noqa: ARG001
        prompt_message: MessageEvent | None = None,
    ) -> None:
        prompts_seen.append(user_text(prompt_message))
        conv.state.execution_status = ConversationExecutionStatus.FINISHED
        if len(prompts_seen) == 1:
            first_step_finished.set()
            await release_first_step.wait()

    with (
        patch.object(ACPAgent, "init_state", autospec=True),
        patch.object(ACPAgent, "astep", new=blocking_astep),
    ):
        first_run = asyncio.create_task(conversation.arun())
        await asyncio.wait_for(first_step_finished.wait(), timeout=1.0)
        await asyncio.to_thread(conversation.send_message, "queued one")
        await asyncio.to_thread(conversation.send_message, "queued two")
        release_first_step.set()
        await asyncio.wait_for(first_run, timeout=1.0)

        assert conversation.state.execution_status == ConversationExecutionStatus.IDLE
        await asyncio.wait_for(conversation.arun(), timeout=1.0)
        await asyncio.wait_for(conversation.arun(), timeout=1.0)

    assert prompts_seen == ["initial request", "queued one", "queued two"]


@pytest.mark.asyncio
async def test_acp_arun_stops_after_agent_sets_error(tmp_path):
    """ACP 超时/错误状态不应被最大迭代错误替换。"""

    agent = ACPAgent(acp_command=["echo", "test"])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        max_iteration_per_run=3,
        stuck_detection=False,
    )
    conversation.send_message("initial request")
    prompts_seen: list[str] = []

    async def failing_astep(
        self,  # noqa: ARG001
        conv: LocalConversation,
        on_event: ConversationCallbackType,  # noqa: ARG001
        on_token: ConversationTokenCallbackType | None = None,  # noqa: ARG001
        prompt_message: MessageEvent | None = None,
    ) -> None:
        assert prompt_message is not None
        prompts_seen.append("prompt")
        conv.state.execution_status = ConversationExecutionStatus.ERROR

    with (
        patch.object(ACPAgent, "init_state", autospec=True),
        patch.object(ACPAgent, "astep", new=failing_astep),
    ):
        await asyncio.wait_for(conversation.arun(), timeout=1.0)

    assert prompts_seen == ["prompt"]
    assert conversation.state.execution_status == ConversationExecutionStatus.ERROR


@pytest.mark.asyncio
async def test_acp_arun_leaves_queued_message_idle_at_iteration_cap(tmp_path):
    """处于运行上限的排队 ACP 消息应等待另一次运行。"""

    agent = ACPAgent(acp_command=["echo", "test"])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        max_iteration_per_run=1,
        stuck_detection=False,
    )
    conversation.send_message("initial request")

    step_finished = asyncio.Event()
    release_step = asyncio.Event()
    prompts_seen: list[str] = []

    def user_text(event: MessageEvent | None) -> str:
        assert event is not None
        content = event.llm_message.content[0]
        assert isinstance(content, TextContent)
        return content.text

    async def blocking_astep(
        self,  # noqa: ARG001
        conv: LocalConversation,
        on_event: ConversationCallbackType,  # noqa: ARG001
        on_token: ConversationTokenCallbackType | None = None,  # noqa: ARG001
        prompt_message: MessageEvent | None = None,
    ) -> None:
        prompts_seen.append(user_text(prompt_message))
        conv.state.execution_status = ConversationExecutionStatus.FINISHED
        step_finished.set()
        await release_step.wait()

    with (
        patch.object(ACPAgent, "init_state", autospec=True),
        patch.object(ACPAgent, "astep", new=blocking_astep),
    ):
        run_task = asyncio.create_task(conversation.arun())
        await asyncio.wait_for(step_finished.wait(), timeout=1.0)
        await asyncio.to_thread(conversation.send_message, "intervening request")
        release_step.set()
        await asyncio.wait_for(run_task, timeout=1.0)

    assert prompts_seen == ["initial request"]
    assert conversation.state.execution_status == ConversationExecutionStatus.IDLE


# ---技能激活接线------------------------------------------------
# 技能激活块的特性测试 LocalConversation.send_message().
# AgentContext.get_user_message_suffix它有自己的单元测试; 这些将对话级别的合同锁定：哪些
# 字段 MessageEvent 携带激活，用户自己的文本会发生什么，以及如何 ConversationState 记住
# 会话中的激活。
#


def _python_tips_skill() -> Skill:
    return Skill(
        name="python_tips",
        content="Use list comprehensions for better performance.",
        source="python-tips.md",
        trigger=KeywordTrigger(keywords=["python", "performance"]),
    )


def test_send_message_activates_skill_on_trigger_match():
    """关键字匹配将技能连接到事件和对话状态中。"""
    agent = SendMessageDummyAgent(
        agent_context=AgentContext(skills=[_python_tips_skill()])
    )
    conversation = Conversation(agent=agent)

    user_text = "How can I improve my Python code performance?"
    conversation.send_message(user_text)

    user_event = conversation.state.events[-1]
    assert isinstance(user_event, MessageEvent)

    # 用户自己的消息不会被重写...
    assert len(user_event.llm_message.content) == 1
    assert isinstance(user_event.llm_message.content[0], TextContent)
    assert user_event.llm_message.content[0].text == user_text

    # ... the recalled knowledge rides alongside it in extended_content.
    assert len(user_event.extended_content) == 1
    assert "Use list comprehensions" in user_event.extended_content[0].text
    assert user_event.activated_skills == ["python_tips"]

    # 状态会记录激活，以便以后的回合可以跳过该技能。
    assert conversation.state.activated_knowledge_skills == ["python_tips"]

    # 折叠到 LLM 载荷发生在 to_llm_message() 时间。
    llm_message = user_event.to_llm_message()
    assert len(llm_message.content) == 2
    assert isinstance(llm_message.content[0], TextContent)
    assert llm_message.content[0].text == user_text
    assert isinstance(llm_message.content[1], TextContent)
    assert llm_message.content[1].text == user_event.extended_content[0].text


def test_send_message_skips_already_activated_skill():
    """每个对话都会触发一次技能，而不是每个匹配的消息触发一次。"""
    agent = SendMessageDummyAgent(
        agent_context=AgentContext(skills=[_python_tips_skill()])
    )
    conversation = Conversation(agent=agent)

    conversation.send_message("Tell me about python performance")
    conversation.send_message("More python tips please")

    user_events = [
        e
        for e in conversation.state.events
        if isinstance(e, MessageEvent) and e.source == "user"
    ]
    first_event, second_event = user_events

    assert first_event.activated_skills == ["python_tips"]
    assert len(first_event.extended_content) == 1

    assert second_event.activated_skills == []
    assert second_event.extended_content == []

    # 记录一次，不重复。
    assert conversation.state.activated_knowledge_skills == ["python_tips"]


def test_send_message_without_trigger_match_leaves_event_plain():
    """没有关键字匹配：事件没有激活并且状态保持为空。"""
    agent = SendMessageDummyAgent(
        agent_context=AgentContext(skills=[_python_tips_skill()])
    )
    conversation = Conversation(agent=agent)

    conversation.send_message("How do I write JavaScript code?")

    user_event = conversation.state.events[-1]
    assert isinstance(user_event, MessageEvent)
    assert user_event.activated_skills == []
    assert user_event.extended_content == []
    assert conversation.state.activated_knowledge_skills == []


def test_send_message_without_agent_context_leaves_event_plain():
    """No agent_context：激活块是无操作。"""
    agent = SendMessageDummyAgent()
    conversation = Conversation(agent=agent)

    conversation.send_message("Tell me about python performance")

    user_event = conversation.state.events[-1]
    assert isinstance(user_event, MessageEvent)
    assert user_event.activated_skills == []
    assert user_event.extended_content == []
    assert conversation.state.activated_knowledge_skills == []


def test_send_message_activates_all_matching_skills():
    """每个匹配的技能都会在同一条消息上激活。"""
    testing_skill = Skill(
        name="testing_framework",
        content="Use pytest for comprehensive testing with fixtures.",
        source="testing-framework.md",
        trigger=KeywordTrigger(keywords=["testing", "pytest"]),
    )
    agent = SendMessageDummyAgent(
        agent_context=AgentContext(skills=[_python_tips_skill(), testing_skill])
    )
    conversation = Conversation(agent=agent)

    conversation.send_message("I need help with python testing using pytest")

    user_event = conversation.state.events[-1]
    assert isinstance(user_event, MessageEvent)
    # 激活顺序是确定性的：AgentContext.skills声明顺序。
    assert user_event.activated_skills == ["python_tips", "testing_framework"]
    # 所有匹配的技能都会合并到一个 extended_content 块中。
    assert len(user_event.extended_content) == 1
    assert "Use list comprehensions" in user_event.extended_content[0].text
    assert "Use pytest" in user_event.extended_content[0].text
    assert conversation.state.activated_knowledge_skills == [
        "python_tips",
        "testing_framework",
    ]


def test_send_message_user_message_suffix_without_skill_match():
    """静态 user_message_suffix 到达 extended_content，无需激活。"""
    agent = SendMessageDummyAgent(
        agent_context=AgentContext(user_message_suffix="Always cite your sources.")
    )
    conversation = Conversation(agent=agent)

    conversation.send_message("How do I write JavaScript code?")

    user_event = conversation.state.events[-1]
    assert isinstance(user_event, MessageEvent)
    assert user_event.activated_skills == []
    assert [c.text for c in user_event.extended_content] == [
        "Always cite your sources."
    ]
    assert conversation.state.activated_knowledge_skills == []


def test_user_message_reaches_callbacks_before_its_state_update(tmp_path):
    """回调在 last_user_message_id 更新之前查看用户消息。

    Agent Server 将 on_state_change 连接到对话自己的回调链，因此更新也作为事件附加（
    并发布）。 回调必须按照事件发生的顺序观察事件已持久化
    。
    """
    seen: list = []
    conversation = LocalConversation(
        agent=SendMessageDummyAgent(),
        workspace=str(tmp_path),
        persistence_dir=str(tmp_path / "conv"),
        callbacks=[seen.append],
        visualizer=None,
    )
    conversation._state.set_on_state_change(conversation._on_event)
    seen.clear()

    conversation.send_message("hello")

    persisted_ids = [e.id for e in conversation.state.events]
    seen_ids = [e.id for e in seen]
    assert seen_ids == persisted_ids[-len(seen_ids) :]
    kinds = [
        (type(e).__name__, getattr(e, "key", None))
        for e in seen
        if isinstance(e, (MessageEvent, ConversationStateUpdateEvent))
    ]
    assert kinds[:2] == [
        ("MessageEvent", None),
        ("ConversationStateUpdateEvent", "last_user_message_id"),
    ]
