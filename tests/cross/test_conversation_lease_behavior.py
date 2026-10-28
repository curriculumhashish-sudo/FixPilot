"""对话租赁所有权的类似集成测试。"""

import json
from pathlib import Path

import pytest
from litellm.types.utils import ChatCompletionMessageToolCall, Function

from openhands.agent_server.conversation_lease import (
    LEASE_FILE_NAME,
    ConversationOwnershipLostError,
)
from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.models import StartConversationRequest
from openhands.sdk import LLM, Agent
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    Event,
    MessageEvent,
    ObservationEvent,
    SystemPromptEvent,
)
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.security.confirmation_policy import NeverConfirm
from openhands.sdk.security.risk import SecurityRisk
from openhands.sdk.workspace import LocalWorkspace
from openhands.tools.terminal.definition import TerminalAction, TerminalObservation


def _request(workspace_dir: Path) -> StartConversationRequest:
    return StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )


def _create_running_terminal_action(tool_call_id: str = "call_1") -> ActionEvent:
    tool_call = MessageToolCall.from_chat_tool_call(
        ChatCompletionMessageToolCall(
            id=tool_call_id,
            type="function",
            function=Function(
                name="terminal",
                arguments='{"command": "sleep 30"}',
            ),
        )
    )
    return ActionEvent(
        thought=[TextContent(text="run sleep")],
        action=TerminalAction(command="sleep 30"),
        tool_name="terminal",
        tool_call_id=tool_call_id,
        tool_call=tool_call,
        llm_response_id="response_1",
        security_risk=SecurityRisk.LOW,
        summary="run sleep",
    )


def _terminal_observation(action: ActionEvent, text: str = "done") -> ObservationEvent:
    return ObservationEvent(
        observation=TerminalObservation.from_text(
            text,
            command="sleep 30",
            exit_code=0,
        ),
        action_id=action.id,
        tool_name="terminal",
        tool_call_id=action.tool_call_id,
    )


def _load_disk_events(conversation_dir: Path) -> list[Event]:
    event_files = sorted(
        (conversation_dir / "events").glob("event-*.json"),
        key=lambda path: int(path.name.split("-")[1]),
    )
    return [Event.model_validate_json(path.read_text()) for path in event_files]


def _expire_lease(conversation_dir: Path) -> None:
    lease_path = conversation_dir / LEASE_FILE_NAME
    payload = json.loads(lease_path.read_text())
    payload["expires_at"] = 0
    lease_path.write_text(json.dumps(payload))


@pytest.mark.asyncio
async def test_live_lease_blocks_split_brain_resume_with_disk_events(tmp_path):
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    async with ConversationService(conversations_dir=conversations_dir) as primary:
        conversation_info, _ = await primary.start_conversation(_request(workspace_dir))
        assert primary._event_services is not None
        primary_event_service = primary._event_services[conversation_info.id]
        primary_state = await primary_event_service.get_state()
        conversation_dir = conversations_dir / conversation_info.id.hex

        running_action = _create_running_terminal_action()
        primary_state.events.append(running_action)
        primary_state.execution_status = ConversationExecutionStatus.RUNNING

        assert [
            type(event).__name__ for event in _load_disk_events(conversation_dir)
        ] == [
            "ActionEvent",
            "ConversationStateUpdateEvent",
        ]

        async with ConversationService(
            conversations_dir=conversations_dir
        ) as secondary:
            assert secondary._event_services is not None
            assert conversation_info.id not in secondary._event_services
            primary_state.events.append(_terminal_observation(running_action))

        disk_events = _load_disk_events(conversation_dir)
        assert any(isinstance(event, ObservationEvent) for event in disk_events)
        assert not any(isinstance(event, AgentErrorEvent) for event in disk_events)


@pytest.mark.asyncio
async def test_expired_lease_takeover_fences_stale_writer_with_disk_events(tmp_path):
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    async with ConversationService(conversations_dir=conversations_dir) as primary:
        conversation_info, _ = await primary.start_conversation(_request(workspace_dir))
        assert primary._event_services is not None
        primary_event_service = primary._event_services[conversation_info.id]
        primary_state = await primary_event_service.get_state()
        conversation_dir = conversations_dir / conversation_info.id.hex

        running_action = _create_running_terminal_action()
        primary_state.events.append(running_action)
        primary_state.execution_status = ConversationExecutionStatus.RUNNING
        _expire_lease(conversation_dir)

        async with ConversationService(
            conversations_dir=conversations_dir
        ) as secondary:
            assert secondary._event_services is not None
            assert conversation_info.id in secondary._event_services

            disk_events = _load_disk_events(conversation_dir)
            assert any(isinstance(event, AgentErrorEvent) for event in disk_events)

            with pytest.raises(ConversationOwnershipLostError):
                primary_state.events.append(
                    _terminal_observation(running_action, "late result")
                )

            with pytest.raises(ConversationOwnershipLostError):
                primary_state.execution_status = ConversationExecutionStatus.ERROR


@pytest.mark.asyncio
async def test_crash_recovery_error_is_on_active_branch_for_next_turn(tmp_path):
    """事件文件附加和已持久化 HEAD 之间的重新启动必须保持可恢复。

    这将重现具有实际 ConversationService、LocalConversation、EventLog 和文件系统持久
    化的生产顺序：

    1. 持久化对话为 RUNNING 时的操作。
    2. 模拟操作文件落地之后但之前的进程死亡
       通过仅倒回已持久化 HEAD 来保存 ``leaf_event_id``。
    3. 让第二个服务接管过期的租约并综合崩溃恢复 AgentErrorEvent。
    4. 附加真实的后续用户消息，就像迭代看门狗所做的那样。
    5. 构建视图的操作索引，与总结上下文压缩器在下一个 LLM 回合之前执行的操作相同。

    当前实现将恢复错误写入动作的兄弟节点（两者都隶属于已过期的HEAD），因此活跃分支包
    含一个工具结果，但工具调用和manipulation_indices缺失，Key
    Error会引发。
    """
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    async with ConversationService(conversations_dir=conversations_dir) as primary:
        conversation_info, _ = await primary.start_conversation(_request(workspace_dir))
        assert primary._event_services is not None
        event_service = primary._event_services[conversation_info.id]
        state = await event_service.get_state()
        conversation = event_service._conversation
        assert conversation is not None
        conversation_dir = conversations_dir / conversation_info.id.hex

        # 在飞行动作之前建立一个现实的活动分支。
        system_prompt = SystemPromptEvent(
            system_prompt=TextContent(text="You are a coding agent."), tools=[]
        )
        conversation._on_event(system_prompt)
        user_message = MessageEvent(
            source="user",
            llm_message=Message(
                role="user", content=[TextContent(text="run the command")]
            ),
        )
        conversation._on_event(user_message)
        stale_leaf = state.leaf_event_id
        assert stale_leaf == user_message.id

        running_action = _create_running_terminal_action("chatcmpl-tool-crash-recovery")
        conversation._on_event(running_action)
        state.execution_status = ConversationExecutionStatus.RUNNING
        assert state.leaf_event_id == running_action.id

        # 重现崩溃窗口：操作事件文件存在，而基础快照仍然指向前面的用户消息。
        #
        base_state_path = conversation_dir / "base_state.json"
        base_state = json.loads(base_state_path.read_text())
        base_state["leaf_event_id"] = stale_leaf
        base_state_path.write_text(json.dumps(base_state))
        _expire_lease(conversation_dir)

        async with ConversationService(
            conversations_dir=conversations_dir
        ) as secondary:
            assert secondary._event_services is not None
            recovered = secondary._event_services[conversation_info.id]
            recovered_state = await recovered.get_state()

            disk_events = _load_disk_events(conversation_dir)
            recovery_error = next(
                event for event in disk_events if isinstance(event, AgentErrorEvent)
            )
            assert recovery_error.tool_call_id == running_action.tool_call_id

            # 完全按照后续自动化的方式恢复。
            await recovered.send_message(
                Message(
                    role="user",
                    content=[TextContent(text="continue after the restart")],
                ),
                run=False,
            )

            # 不得引发：下一轮/冷凝器需要活动分支中的有效工具调用边界。
            #
            recovered_state.view.manipulation_indices
