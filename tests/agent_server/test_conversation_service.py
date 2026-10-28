import asyncio
import json
import socket
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from litellm.types.utils import ChatCompletionMessageToolCall, Function
from pydantic import SecretStr

from openhands.agent_server.conversation_lease import (
    LEASE_FILE_NAME,
    ConversationOwnershipLostError,
)
from openhands.agent_server.conversation_service import (
    AutoTitleSubscriber,
    ConversationService,
    UnavailableAgentTool,
    _compose_conversation_info,
    _ConversationRecord,
    _create_conversation_worktree,
    _get_worktree_start_point,
    _plan_conversation_worktree,
)
from openhands.agent_server.event_service import EventService
from openhands.agent_server.models import (
    ConversationInfo,
    ConversationPage,
    ConversationSortOrder,
    StartConversationRequest,
    StoredConversation,
    UpdateConversationRequest,
)
from openhands.agent_server.utils import safe_rmtree as _safe_rmtree
from openhands.sdk import LLM, Agent, AgentBase, Message, Tool
from openhands.sdk.agent.acp_agent import ACPAgent
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.request import ConversationWorktreeOptions
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.credential import CredentialSyncError
from openhands.sdk.critic.impl.api import APIBasedCritic
from openhands.sdk.event import ActionEvent, AgentErrorEvent, ObservationEvent
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.git.exceptions import GitCommandError
from openhands.sdk.git.utils import run_git_command
from openhands.sdk.llm import MessageToolCall, TextContent
from openhands.sdk.mcp.config import dump_mcp_config
from openhands.sdk.secret import SecretSource, StaticSecret
from openhands.sdk.security.confirmation_policy import NeverConfirm
from openhands.sdk.security.risk import SecurityRisk
from openhands.sdk.settings import ACPAgentSettings
from openhands.sdk.utils.cipher import Cipher
from openhands.sdk.workspace import LocalWorkspace
from openhands.tools.terminal.definition import TerminalAction, TerminalObservation


@pytest.fixture
def mock_event_service():
    """使用存储的对话数据创建模拟对象 EventService。"""
    service = AsyncMock(spec=EventService)
    return service


# 智能体不再存储在meta.json（StoredConversation）上； 它位于 base_state.json (
# ConversationState) 中。 需要智能体来构建状态的测试使用此帮助器，而不是读取它
# StoredConversation。
#
def _sample_agent() -> Agent:
    return Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[])


@pytest.fixture
def sample_stored_conversation():
    """创建样本 StoredConversation 进行测试。"""
    return StoredConversation(
        id=uuid4(),
        workspace=LocalWorkspace(working_dir="workspace/project"),
        confirmation_policy=NeverConfirm(),
        initial_message=None,
        metrics=None,
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_meta_json_has_no_agent_and_reload_uses_base_state(tmp_path):
    """端到端单一真实来源保证。

    新开始的对话必须持久化其智能体到base_state.json和不到meta.json。 新的
    ConversationService（模拟服务器重新启动）必须从
    base_state.json 重新加载智能体。
    """
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )
    async with ConversationService(conversations_dir=conversations_dir) as service:
        info, _ = await service.start_conversation(request)
        conv_id = info.id

    conv_dir = conversations_dir / conv_id.hex
    meta = json.loads((conv_dir / "meta.json").read_text())
    base_state = json.loads((conv_dir / "base_state.json").read_text())
    # meta.json 是智能体自由的； base_state.json 拥有智能体。
    assert "agent" not in meta
    assert base_state["agent"]["llm"]["model"] == "gpt-4o"

    # 全新服务（重新启动）会从 base_state.json 重新加载智能体。
    async with ConversationService(conversations_dir=conversations_dir) as service2:
        reloaded = await service2.get_conversation(conv_id)
        assert reloaded is not None
        assert reloaded.agent.llm.model == "gpt-4o"


@pytest.mark.asyncio
async def test_server_resolved_tool_modules_are_persisted(tmp_path):
    """轻量级创建者不需要导入运行时的工具模块。"""
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    request = StartConversationRequest(
        agent=Agent(
            llm=LLM(model="gpt-4o", usage_id="test-llm"),
            tools=[Tool(name="terminal")],
        ),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )

    async with ConversationService(conversations_dir=conversations_dir) as service:
        info, _ = await service.start_conversation(request)

    meta = json.loads((conversations_dir / info.id.hex / "meta.json").read_text())
    assert meta["tool_module_qualnames"]["terminal"] == (
        "openhands.tools.terminal.definition"
    )


@pytest.mark.asyncio
async def test_agent_tool_from_unimportable_module_rejects_create(tmp_path):
    """创建失败并出现客户端错误，而不是每条消息都失败。"""
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    qualnames = {"qa_ghost_tool": "qa_ghost_tool_missing_module"}

    def request(tools: list[Tool]) -> StartConversationRequest:
        return StartConversationRequest(
            agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=tools),
            workspace=LocalWorkspace(working_dir=str(workspace_dir)),
            confirmation_policy=NeverConfirm(),
            tool_module_qualnames=qualnames,
        )

    async with ConversationService(conversations_dir=conversations_dir) as service:
        with pytest.raises(UnavailableAgentTool) as exc_info:
            await service.start_conversation(request([Tool(name="qa_ghost_tool")]))
        assert "'qa_ghost_tool'" in str(exc_info.value)
        assert "qa_ghost_tool_missing_module" in str(exc_info.value)
        assert not conversations_dir.exists() or not any(conversations_dir.iterdir())

        # 智能体不使用其工具的不可导入模块将保留警告。
        info, is_new = await service.start_conversation(request([]))
        assert is_new and info.id is not None


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


def _adopt_saved_meta(mock_service: AsyncMock) -> None:
    """使模拟的``EventService.save_meta(stored)``采用``stored``的方式
    一旦写入成功，真正的就会执行。"""

    async def _save_meta(stored: StoredConversation | None = None) -> None:
        if stored is not None:
            mock_service.stored = stored

    mock_service.save_meta.side_effect = _save_meta


def _expire_conversation_lease(conversations_dir: Path, conversation_id) -> None:
    lease_path = conversations_dir / conversation_id.hex / LEASE_FILE_NAME
    payload = json.loads(lease_path.read_text())
    payload["expires_at"] = 0
    lease_path.write_text(json.dumps(payload))


def _init_git_repo(repo_dir: Path) -> None:
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# test repo\n")
    run_git_command(["git", "init", "-b", "main"], repo_dir)
    run_git_command(["git", "add", "README.md"], repo_dir)
    run_git_command(
        [
            "git",
            "-c",
            "user.name=OpenHands Test",
            "-c",
            "user.email=openhands@example.com",
            "commit",
            "-m",
            "init",
        ],
        repo_dir,
    )


@pytest.fixture
def conversation_service(tmp_path):
    """创建一个 ConversationService 实例用于测试。"""
    worktree_root = tmp_path / "conversation-worktrees"
    service = ConversationService(
        conversations_dir=tmp_path / "conversations",
        conversation_worktree_root=worktree_root,
    )
    # 初始化 _event_services 字典来模拟活动服务
    service._event_services = {}
    yield service


@pytest.fixture
async def persisted_conversation(tmp_path) -> tuple[Path, UUID]:
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )
    async with ConversationService(conversations_dir=conversations_dir) as service:
        conversation_info, _ = await service.start_conversation(request)
    return conversations_dir, conversation_info.id


@pytest.mark.asyncio
async def test_start_conversation_registers_and_injects_client_tools(
    conversation_service, tmp_path
):
    """client_tools 规格已注册，注入到智能体和已持久化中。

    ``StoredConversation`` 上的持久化允许分叉和服务器重新启动以重新注册动态客户端工具
    。
    """
    from openhands.sdk.tool.client_tool import ClientToolSpec

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
        client_tools=[
            ClientToolSpec(
                name="srv_show_dialog",
                description="Show a dialog",
                parameters={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            )
        ],
    )

    captured: dict[str, Any] = {}

    async def fake_start_event_service(stored: StoredConversation, **kwargs):
        agent = kwargs["launched"].agent
        captured["stored"] = stored
        captured["agent"] = agent
        service = AsyncMock(spec=EventService)
        service.stored = stored
        service.get_state.return_value = ConversationState(
            id=stored.id,
            agent=agent,
            workspace=stored.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=stored.confirmation_policy,
        )
        return service

    with patch.object(
        conversation_service,
        "_start_event_service",
        side_effect=fake_start_event_service,
    ):
        await conversation_service.start_conversation(request)

    stored = captured["stored"]
    agent = captured["agent"]
    # 注入智能体的工具规范，以便 _initialize() 可以解决它
    assert "srv_show_dialog" in {t.name for t in agent.tools}
    # 已持久化所以 forks/restarts 可以重新注册动态操作类型
    assert [s.name for s in stored.client_tools] == ["srv_show_dialog"]
    # 该类已在全局工具注册表中注册
    from openhands.sdk.tool.registry import list_registered_tools

    assert "srv_show_dialog" in list_registered_tools()


@pytest.mark.asyncio
async def test_start_conversation_decrypts_encrypted_agent_settings_mcp_env(
    conversation_service, tmp_path
):
    cipher = Cipher("mcp-env-test-key")
    conversation_service.cipher = cipher
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    encrypted_llm_key = cipher.encrypt(SecretStr("sk-plaintext"))
    encrypted_mcp_token = cipher.encrypt(SecretStr("ghp-plaintext"))
    request = StartConversationRequest(
        agent_settings={
            "schema_version": 1,
            "agent_kind": "llm",
            "llm": {
                "model": "gpt-4o",
                "usage_id": "test-llm",
                "api_key": encrypted_llm_key,
            },
            "tools": [],
            "mcp_config": {
                "mcpServers": {
                    "github": {
                        "command": "npx",
                        "env": {
                            "GITHUB_PERSONAL_ACCESS_TOKEN": encrypted_mcp_token,
                        },
                    }
                }
            },
        },
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
        secrets_encrypted=True,
    )
    assert request.agent is None

    captured: dict[str, Any] = {}

    async def fake_start_event_service(stored: StoredConversation, **kwargs):
        agent = kwargs["launched"].agent
        captured["stored"] = stored
        captured["agent"] = agent
        service = AsyncMock(spec=EventService)
        service.stored = stored
        service.get_state.return_value = ConversationState(
            id=stored.id,
            agent=agent,
            workspace=stored.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=stored.confirmation_policy,
        )
        return service

    with patch.object(
        conversation_service,
        "_start_event_service",
        side_effect=fake_start_event_service,
    ):
        await conversation_service.start_conversation(request)

    agent = captured["agent"]
    assert isinstance(agent.llm.api_key, SecretStr)
    assert agent.llm.api_key.get_secret_value() == "sk-plaintext"
    assert (
        dump_mcp_config(agent.mcp_config)["github"]["env"][
            "GITHUB_PERSONAL_ACCESS_TOKEN"
        ]
        == "ghp-plaintext"
    )


@pytest.mark.asyncio
async def test_second_service_does_not_resume_active_running_conversation(tmp_path):
    """第二个服务不应附加到实时运行的对话中。"""
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )

    async with ConversationService(conversations_dir=conversations_dir) as primary:
        conversation_info, _ = await primary.start_conversation(request)
        assert primary._event_services is not None

        primary_event_service = primary._event_services[conversation_info.id]
        primary_state = await primary_event_service.get_state()

        running_action = _create_running_terminal_action()
        primary_state.events.append(running_action)
        primary_state.execution_status = ConversationExecutionStatus.RUNNING

        async with ConversationService(
            conversations_dir=conversations_dir,
        ) as secondary:
            assert secondary._event_services is not None
            assert conversation_info.id not in secondary._event_services

            primary_state.events.append(
                ObservationEvent(
                    observation=TerminalObservation.from_text(
                        "done",
                        command="sleep 30",
                        exit_code=0,
                    ),
                    action_id=running_action.id,
                    tool_name="terminal",
                    tool_call_id=running_action.tool_call_id,
                )
            )

        events = primary_state.events[:]
        assert [type(event).__name__ for event in events] == [
            "ActionEvent",
            "ConversationStateUpdateEvent",
            "ObservationEvent",
        ]
        assert not any(isinstance(event, AgentErrorEvent) for event in events)


@pytest.mark.asyncio
async def test_stale_owner_cannot_append_after_lease_takeover(tmp_path):
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )

    async with ConversationService(conversations_dir=conversations_dir) as primary:
        conversation_info, _ = await primary.start_conversation(request)
        assert primary._event_services is not None
        primary_event_service = primary._event_services[conversation_info.id]
        primary_state = await primary_event_service.get_state()

        running_action = _create_running_terminal_action()
        primary_state.events.append(running_action)
        primary_state.execution_status = ConversationExecutionStatus.RUNNING
        _expire_conversation_lease(conversations_dir, conversation_info.id)

        async with ConversationService(
            conversations_dir=conversations_dir,
        ) as secondary:
            assert secondary._event_services is not None
            secondary_event_service = secondary._event_services[conversation_info.id]
            secondary_state = await secondary_event_service.get_state()

            assert any(
                isinstance(event, AgentErrorEvent)
                for event in secondary_state.events[:]
            )

            with pytest.raises(ConversationOwnershipLostError):
                primary_state.events.append(
                    ObservationEvent(
                        observation=TerminalObservation.from_text(
                            "late result",
                            command="sleep 30",
                            exit_code=0,
                        ),
                        action_id=running_action.id,
                        tool_name="terminal",
                        tool_call_id=running_action.tool_call_id,
                    )
                )

            with pytest.raises(ConversationOwnershipLostError):
                primary_state.execution_status = ConversationExecutionStatus.ERROR


@pytest.mark.asyncio
async def test_stale_owner_refused_update_leaves_no_trace(tmp_path):
    """由于失去所有权而拒绝元数据更新不会改变任何可见的内容。"""
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
        tags={"env": "old"},
    )

    async with ConversationService(conversations_dir=conversations_dir) as primary:
        conversation_info, _ = await primary.start_conversation(request)
        conversation_id = conversation_info.id
        await primary.update_conversation(
            conversation_id, UpdateConversationRequest(title="Original")
        )
        _expire_conversation_lease(conversations_dir, conversation_id)
        meta_file = conversations_dir / conversation_id.hex / "meta.json"

        async with ConversationService(
            conversations_dir=conversations_dir,
        ) as secondary:
            await secondary.update_conversation(
                conversation_id, UpdateConversationRequest(title="New owner")
            )
            meta_before = meta_file.read_text()

            with pytest.raises(ConversationOwnershipLostError):
                await primary.update_conversation(
                    conversation_id,
                    UpdateConversationRequest(
                        title="Stale owner", tags={"env": "stale"}
                    ),
                )

            assert meta_file.read_text() == meta_before
            info = await primary.get_conversation(conversation_id)
            assert info is not None
            assert info.title == "Original"
            assert info.tags == {"env": "old"}
            assert primary._event_services is not None
            state = await primary._event_services[conversation_id].get_state()
            assert state.tags == {"env": "old"}


@pytest.mark.asyncio
async def test_event_services_use_centralized_lease_renewal(tmp_path):
    """ConversationService 创建的事件服务不应生成
    他们自己的租约更新任务——更新是集中处理的。"""
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )

    async with ConversationService(conversations_dir=conversations_dir) as svc:
        info, _ = await svc.start_conversation(request)
        assert svc._event_services is not None
        es = svc._event_services[info.id]

        # 应创建每服务续订任务不
        assert es._lease_task is None
        assert es._external_lease_renewal is True

        # 集中任务应该存在
        assert svc._lease_renewal_task is not None
        assert not svc._lease_renewal_task.done()

    # __aexit__后，应清理集中任务
    assert svc._lease_renewal_task is None


@pytest.mark.asyncio
async def test_centralized_lease_renewal_invokes_renew(tmp_path):
    """集中式循环在每个活动服务上调用 renew_lease()。"""
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )

    with patch(
        "openhands.agent_server.conversation_service.LEASE_RENEW_INTERVAL_SECONDS",
        0.05,
    ):
        async with ConversationService(conversations_dir=conversations_dir) as svc:
            info1, _ = await svc.start_conversation(request)
            info2, _ = await svc.start_conversation(request)
            assert svc._event_services is not None
            es1 = svc._event_services[info1.id]
            es2 = svc._event_services[info2.id]

            renew_calls: dict[str, int] = {"es1": 0, "es2": 0}
            original_renew1 = es1.renew_lease
            original_renew2 = es2.renew_lease

            def counting_renew1():
                renew_calls["es1"] += 1
                original_renew1()

            def counting_renew2():
                renew_calls["es2"] += 1
                original_renew2()

            es1.renew_lease = counting_renew1  # type: ignore[method-assign]
            es2.renew_lease = counting_renew2  # type: ignore[method-assign]

            # 等待至少2个更新周期
            await asyncio.sleep(0.15)

            assert renew_calls["es1"] >= 1, "renew_lease not called on es1"
            assert renew_calls["es2"] >= 1, "renew_lease not called on es2"


@pytest.mark.asyncio
async def test_event_services_share_dedicated_run_executor(tmp_path):
    """ConversationService 创建的事件服务应共享一个
    用于 conversation.run() 调用的专用线程池。"""
    from concurrent.futures import ThreadPoolExecutor

    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )

    async with ConversationService(
        conversations_dir=conversations_dir, max_concurrent_runs=5
    ) as svc:
        info, _ = await svc.start_conversation(request)
        assert svc._event_services is not None
        es = svc._event_services[info.id]

        # 服务上应该存在专门的执行者
        assert svc._run_executor is not None
        assert isinstance(svc._run_executor, ThreadPoolExecutor)
        assert svc._run_executor._max_workers == 5

        # EventService 应该共享相同的执行器实例
        assert es._run_executor is svc._run_executor

    # __aexit__之后，执行器应该关闭
    assert svc._run_executor is None


@pytest.mark.asyncio
async def test_prepare_for_sandbox_pause_drains_active_services(tmp_path):
    service = ConversationService(conversations_dir=tmp_path / "conversations")
    await service.__aenter__()
    first_id = uuid4()
    second_id = uuid4()
    first = AsyncMock(spec=EventService)
    second = AsyncMock(spec=EventService)
    second.__aexit__.side_effect = [
        CredentialSyncError("broker unavailable"),
        None,
    ]
    assert service._event_services is not None
    service._event_services = {first_id: first, second_id: second}
    service._credential_bindings = {first_id: {"CODEX_AUTH_JSON": MagicMock()}}

    with pytest.raises(CredentialSyncError, match="broker unavailable"):
        await service.prepare_for_sandbox_pause()

    assert service._event_services == {second_id: second}
    assert service._credential_bindings

    await service.prepare_for_sandbox_pause()

    assert service._event_services == {}
    assert service._credential_bindings == {}
    first.__aexit__.assert_awaited_once_with(None, None, None)
    assert second.__aexit__.await_count == 2
    await service.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_conversation_lifecycle_serializes_only_matching_ids(tmp_path):
    service = ConversationService(conversations_dir=tmp_path / "conversations")
    first_id = uuid4()
    second_id = uuid4()
    same_id_entered = asyncio.Event()
    other_id_entered = asyncio.Event()

    async def enter_lifecycle(conversation_id: UUID, entered: asyncio.Event):
        async with service._conversation_lifecycle(conversation_id):
            entered.set()

    async with service._conversation_lifecycle(first_id):
        same_id_task = asyncio.create_task(enter_lifecycle(first_id, same_id_entered))
        other_id_task = asyncio.create_task(
            enter_lifecycle(second_id, other_id_entered)
        )
        await asyncio.wait_for(other_id_entered.wait(), timeout=1)
        assert not same_id_entered.is_set()

    await asyncio.gather(same_id_task, other_id_task)
    assert same_id_entered.is_set()


@pytest.mark.asyncio
async def test_conversation_read_completes_while_another_conversation_starts(
    tmp_path,
):
    """会话范围的读取不得在不相关的启动后面排队。

    Lifecycle 工作以前在一个全局进程锁中运行，因此任何解析 ``EventService`` 的请求都
    需要等待其他地方发生的启动、fork、删除或驱逐操作。
    驱动公共 API 而不是锁帮助者，以便在调用者实际点击的地方检查保证。
    """
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    def request() -> StartConversationRequest:
        return StartConversationRequest(
            agent=_sample_agent(),
            workspace=LocalWorkspace(working_dir=str(workspace_dir)),
            confirmation_policy=NeverConfirm(),
        )

    async with ConversationService(conversations_dir=conversations_dir) as service:
        live, _ = await service.start_conversation(request())

        start_entered = asyncio.Event()
        release_start = asyncio.Event()
        start_event_service = service._start_event_service

        async def blocking_start(stored: StoredConversation, **kwargs) -> EventService:
            # 将 *other* 对话嵌入其自己的生命周期部分。
            if stored.id != live.id:
                start_entered.set()
                await release_start.wait()
            return await start_event_service(stored, **kwargs)

        with patch.object(service, "_start_event_service", side_effect=blocking_start):
            starting = asyncio.create_task(service.start_conversation(request()))
            await asyncio.wait_for(start_entered.wait(), timeout=5)
            try:
                assert (
                    await asyncio.wait_for(
                        service.get_event_service(live.id), timeout=5
                    )
                    is not None
                )
            finally:
                release_start.set()
                await asyncio.wait_for(starting, timeout=5)


@pytest.mark.asyncio
async def test_prepare_for_sandbox_pause_blocks_new_hydration(
    persisted_conversation,
):
    conversations_dir, conversation_id = persisted_conversation
    service = ConversationService(conversations_dir=conversations_dir)
    await service.__aenter__()
    existing_id = uuid4()
    existing = AsyncMock(spec=EventService)
    close_entered = asyncio.Event()
    finish_close = asyncio.Event()
    hydration_entered = asyncio.Event()
    record = service._conversation_records[conversation_id]
    hydrated = AsyncMock(spec=EventService)
    hydrated.stored = record.stored

    async def close(*_args):
        close_entered.set()
        await finish_close.wait()

    async def hydrate(*_args, **_kwargs):
        hydration_entered.set()
        assert service._event_services is not None
        service._event_services[conversation_id] = hydrated
        return hydrated

    existing.__aexit__.side_effect = close
    assert service._event_services is not None
    service._event_services[existing_id] = existing

    try:
        with patch.object(service, "_start_event_service", side_effect=hydrate):
            pause_task = asyncio.create_task(service.prepare_for_sandbox_pause())
            await asyncio.wait_for(close_entered.wait(), timeout=1)
            hydration_task = asyncio.create_task(
                service.get_event_service(conversation_id)
            )
            await asyncio.sleep(0)
            assert not hydration_entered.is_set()

            finish_close.set()
            await asyncio.wait_for(pause_task, timeout=1)
            assert service._event_services == {}
            assert not hydration_entered.is_set()
            assert await asyncio.wait_for(hydration_task, timeout=1) is hydrated
    finally:
        finish_close.set()
        await service.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_prepare_for_sandbox_pause_closes_services_concurrently(tmp_path):
    service = ConversationService(conversations_dir=tmp_path / "conversations")
    await service.__aenter__()
    first = AsyncMock(spec=EventService)
    second = AsyncMock(spec=EventService)
    all_started = asyncio.Event()
    started = 0

    async def close(*_args):
        nonlocal started
        started += 1
        if started == 2:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=1)

    first.__aexit__.side_effect = close
    second.__aexit__.side_effect = close
    assert service._event_services is not None
    service._event_services = {uuid4(): first, uuid4(): second}

    await service.prepare_for_sandbox_pause()

    assert service._event_services == {}
    first.__aexit__.assert_awaited_once_with(None, None, None)
    second.__aexit__.assert_awaited_once_with(None, None, None)
    await service.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_shutdown_retains_credential_close_failure_for_retry(tmp_path):
    service = ConversationService(conversations_dir=tmp_path / "conversations")
    await service.__aenter__()
    conversation_id = uuid4()
    runtime = AsyncMock(spec=EventService)
    runtime.__aexit__.side_effect = [
        CredentialSyncError("broker unavailable"),
        None,
    ]
    record = MagicMock()
    binding = MagicMock()
    assert service._event_services is not None
    service._event_services[conversation_id] = runtime
    service._conversation_records[conversation_id] = record
    service._credential_bindings[conversation_id] = {"CODEX_AUTH_JSON": binding}

    with pytest.raises(CredentialSyncError, match="broker unavailable"):
        await service.__aexit__(None, None, None)

    assert service._event_services == {conversation_id: runtime}
    assert service._conversation_records == {conversation_id: record}
    assert service._credential_bindings == {
        conversation_id: {"CODEX_AUTH_JSON": binding}
    }
    assert service._run_executor is None
    assert service._lease_renewal_task is not None
    assert not service._lease_renewal_task.done()

    await service.__aexit__(None, None, None)

    assert runtime.__aexit__.await_count == 2
    assert service._event_services is None
    assert service._conversation_records == {}
    assert service._credential_bindings == {}


@pytest.mark.asyncio
async def test_shutdown_prioritizes_credential_failure_across_runtimes(tmp_path):
    service = ConversationService(conversations_dir=tmp_path / "conversations")
    await service.__aenter__()
    first_id = uuid4()
    second_id = uuid4()
    first = AsyncMock(spec=EventService)
    second = AsyncMock(spec=EventService)
    first.__aexit__.side_effect = OSError("save failed")
    second.__aexit__.side_effect = CredentialSyncError("broker unavailable")
    assert service._event_services is not None
    service._event_services = {first_id: first, second_id: second}
    service._conversation_records = {
        first_id: MagicMock(),
        second_id: MagicMock(),
    }

    with pytest.raises(CredentialSyncError, match="broker unavailable"):
        await service.__aexit__(None, None, None)

    assert service._event_services == {first_id: first, second_id: second}

    first.__aexit__.side_effect = None
    second.__aexit__.side_effect = None
    await service.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_restart_resumes_conversations_after_non_graceful_shutdown(tmp_path):
    """重现崩溃恢复错误：非正常关闭后租约
    文件留在磁盘上，指向仍然未来的expires_at。 在 TTL 过去之前启动的新服务器仍必须继
    续对话，而不是跳过它直到完整的 TTL 窗口。
    """
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )

    async with ConversationService(conversations_dir=conversations_dir) as primary:
        conversation_info, _ = await primary.start_conversation(request)
        conversation_id = conversation_info.id

    # 模拟非正常关闭：伪造一个指向 PID 的租约，该租约保证不会运行，并且具有遥远的未来
    # expires_at。 干净的退出将通过release()删除租约； 崩溃会将其抛在后面，这就是我们在
    # 这里复制的内容。
    #
    lease_path = conversations_dir / conversation_id.hex / LEASE_FILE_NAME
    forged_payload = {
        "owner_instance_id": "ghost-instance-from-crashed-server",
        "generation": 1,
        "expires_at": time.time() + 3600.0,
        "owner_host": socket.gethostname(),
        "owner_pid": 2**31 - 1,
    }
    lease_path.write_text(json.dumps(forged_payload))

    async with ConversationService(conversations_dir=conversations_dir) as restarted:
        assert restarted._event_services is not None
        assert conversation_id not in restarted._event_services
        restarted_event_service = await restarted.get_event_service(conversation_id)
        assert restarted_event_service is not None, (
            "Lazy hydration failed to pick up an existing conversation whose "
            "lease was left orphaned by a non-graceful shutdown."
        )


@pytest.mark.asyncio
async def test_startup_and_search_do_not_hydrate_idle_conversation(tmp_path):
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )
    async with ConversationService(conversations_dir=conversations_dir) as primary:
        conversation_info, _ = await primary.start_conversation(request)

    restarted = ConversationService(conversations_dir=conversations_dir)
    with patch.object(
        restarted,
        "_start_event_service",
        side_effect=AssertionError("idle conversation should remain unloaded"),
    ):
        async with restarted:
            assert restarted._event_services == {}
            assert conversation_info.id in restarted._conversation_records

            page = await restarted.search_conversations()
            assert [item.id for item in page.items] == [conversation_info.id]
            assert await restarted.count_conversations() == 1
            assert restarted._event_services == {}


@pytest.mark.asyncio
async def test_concurrent_access_hydrates_conversation_once(tmp_path):
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )
    async with ConversationService(conversations_dir=conversations_dir) as primary:
        conversation_info, _ = await primary.start_conversation(request)

    async with ConversationService(conversations_dir=conversations_dir) as restarted:
        with patch.object(
            restarted,
            "_start_event_service",
            wraps=restarted._start_event_service,
        ) as start_event_service:
            services = await asyncio.gather(
                *[restarted.get_event_service(conversation_info.id) for _ in range(5)]
            )

        assert start_event_service.await_count == 1
        assert services[0] is not None
        assert all(service is services[0] for service in services)


@pytest.mark.asyncio
async def test_status_filters_refresh_unloaded_shared_state(persisted_conversation):
    conversations_dir, conversation_id = persisted_conversation

    async with ConversationService(conversations_dir=conversations_dir) as primary:
        primary_runtime = await primary.get_event_service(conversation_id)
        assert primary_runtime is not None

        async with ConversationService(conversations_dir=conversations_dir) as observer:
            assert observer._event_services == {}
            assert (
                observer._conversation_records[conversation_id].execution_status
                == ConversationExecutionStatus.IDLE
            )

            primary_state = await primary_runtime.get_state()
            primary_state.execution_status = ConversationExecutionStatus.RUNNING
            assert (
                await observer.count_conversations(
                    execution_status=ConversationExecutionStatus.RUNNING
                )
                == 1
            )

            primary_state.execution_status = ConversationExecutionStatus.PAUSED
            page = await observer.search_conversations(
                execution_status=ConversationExecutionStatus.PAUSED
            )
            assert [item.id for item in page.items] == [conversation_id]
            assert observer._event_services == {}


@pytest.mark.asyncio
async def test_finished_status_refresh_invalidates_cached_info(persisted_conversation):
    """已持久化状态更改会使观察者的缓存行无效。

    观察者为 IDLE 快照缓存 ``ConversationInfo``。 所有者结束对话后，过滤的搜索必须为
    刷新的内容提供服务
    ``FINISHED`` 状态而不是过时的缓存 ``IDLE`` 行。
    """
    conversations_dir, conversation_id = persisted_conversation

    async with ConversationService(conversations_dir=conversations_dir) as primary:
        primary_runtime = await primary.get_event_service(conversation_id)
        assert primary_runtime is not None

        async with ConversationService(conversations_dir=conversations_dir) as observer:
            # 从 IDLE 快照填充观察者的目录条目 + cached_info（未过滤的搜索不会刷新状态）
            # 。
            #
            initial = await observer.search_conversations()
            assert [item.id for item in initial.items] == [conversation_id]
            record = observer._conversation_records[conversation_id]
            assert record.cached_info is not None
            assert record.execution_status == ConversationExecutionStatus.IDLE

            # Primary 在观察者背后结束了谈话。
            primary_state = await primary_runtime.get_state()
            primary_state.execution_status = ConversationExecutionStatus.FINISHED

            # 观察者的过滤搜索会刷新状态； 它不能提供过时的缓存 IDLE ConversationInfo。
            #
            page = await observer.search_conversations(
                execution_status=ConversationExecutionStatus.FINISHED
            )
            assert [item.id for item in page.items] == [conversation_id]
            assert (
                page.items[0].execution_status == ConversationExecutionStatus.FINISHED
            )

            # 搜索必须也显示刷新状态，而不是滞后的缓存 IDLE 行（否则会持久化一直存在，直
            # 到对话结束）。
            #
            unfiltered = await observer.search_conversations()
            assert [item.id for item in unfiltered.items] == [conversation_id]
            assert (
                unfiltered.items[0].execution_status
                == ConversationExecutionStatus.FINISHED
            )
            assert observer._event_services == {}


@pytest.mark.asyncio
async def test_search_refreshes_cached_info_on_metadata_only_update(
    persisted_conversation,
):
    """仅元数据更新 (meta.json) 使缓存的行无效。

    ``cached_info`` 嵌入 ``StoredConversation`` 元数据（标题、指标），但仅由
    ``base_state.json`` 键入。 实
    时对话仅发生变化
    ``stored`` 元数据 — e.g。 自动标题 - 不得提供陈旧的行。
    """
    conversations_dir, conversation_id = persisted_conversation

    async with ConversationService(conversations_dir=conversations_dir) as service:
        runtime = await service.get_event_service(conversation_id)
        assert runtime is not None

        # 从无标题快照填充缓存的 ConversationInfo。
        initial = await service.search_conversations()
        assert [item.id for item in initial.items] == [conversation_id]
        assert initial.items[0].title is None
        record = service._conversation_records[conversation_id]
        assert record.cached_info is not None

        # 仅更改存储的元数据； base_state.json 未受影响。
        runtime.stored = runtime.stored.model_copy(update={"title": "Generated Title"})
        await runtime.save_meta()

        page = await service.search_conversations()
        assert [item.id for item in page.items] == [conversation_id]
        assert page.items[0].title == "Generated Title"
        assert service._event_services is not None
        assert set(service._event_services) == {conversation_id}


@pytest.mark.asyncio
async def test_waiting_hydration_cannot_restore_deleted_conversation(
    persisted_conversation,
):
    conversations_dir, conversation_id = persisted_conversation

    async with ConversationService(conversations_dir=conversations_dir) as service:
        record = service._conversation_records[conversation_id]
        state = ConversationState(
            id=conversation_id,
            agent=_sample_agent(),
            workspace=record.stored.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=record.stored.confirmation_policy,
        )
        deleting_runtime = AsyncMock(spec=EventService)
        deleting_runtime.is_open.return_value = True
        deleting_runtime.stored = record.stored
        deleting_runtime.get_state.return_value = state
        deleting_runtime.conversation_dir = conversations_dir / conversation_id.hex

        replacement_runtime = AsyncMock(spec=EventService)
        replacement_runtime.stored = record.stored

        async def publish_replacement(
            _stored: StoredConversation, *, agent: AgentBase | None = None
        ) -> EventService:
            assert service._event_services is not None
            service._event_services[conversation_id] = replacement_runtime
            service._conversation_records[conversation_id] = record
            return replacement_runtime

        with (
            patch.object(
                service,
                "_start_event_service",
                side_effect=publish_replacement,
            ) as start_event_service,
            patch("openhands.agent_server.conversation_service.safe_rmtree"),
        ):
            conversation_lock = service._get_conversation_lock(conversation_id)
            await conversation_lock.acquire()
            try:
                getter_task = asyncio.create_task(
                    service.get_event_service(conversation_id)
                )
                await asyncio.sleep(0)
                assert service._event_services is not None
                service._event_services[conversation_id] = deleting_runtime
                delete_task = asyncio.create_task(
                    service.delete_conversation(conversation_id)
                )
                await asyncio.sleep(0)
            finally:
                conversation_lock.release()

            getter_result, deleted = await asyncio.gather(getter_task, delete_task)

        assert getter_result is deleting_runtime
        assert deleted is True
        start_event_service.assert_not_awaited()
        assert service._event_services is not None
        assert conversation_id not in service._event_services
        assert conversation_id not in service._conversation_records


@pytest.mark.asyncio
async def test_shutdown_closes_runtime_from_in_flight_hydration(
    persisted_conversation,
):
    conversations_dir, conversation_id = persisted_conversation
    service = ConversationService(conversations_dir=conversations_dir)
    await service.__aenter__()
    record = service._conversation_records[conversation_id]
    state = ConversationState(
        id=conversation_id,
        agent=_sample_agent(),
        workspace=record.stored.workspace,
        execution_status=ConversationExecutionStatus.IDLE,
        confirmation_policy=record.stored.confirmation_policy,
    )
    startup_entered = asyncio.Event()
    finish_startup = asyncio.Event()
    runtime = AsyncMock(spec=EventService)
    runtime.stored = record.stored
    runtime.get_state.return_value = state

    async def blocking_start() -> None:
        startup_entered.set()
        await finish_startup.wait()

    async def close_on_exit(*_args) -> None:
        await runtime.close()

    runtime.start.side_effect = blocking_start
    runtime.__aexit__.side_effect = close_on_exit

    try:
        with patch(
            "openhands.agent_server.conversation_service.EventService",
            return_value=runtime,
        ):
            hydration_task = asyncio.create_task(
                service.get_event_service(conversation_id)
            )
            await asyncio.wait_for(startup_entered.wait(), timeout=1)
            shutdown_task = asyncio.create_task(service.__aexit__(None, None, None))
            await asyncio.sleep(0)
            finish_startup.set()
            hydrated_runtime, _ = await asyncio.wait_for(
                asyncio.gather(hydration_task, shutdown_task), timeout=1
            )
    finally:
        finish_startup.set()
        if service._event_services is not None:
            await service.__aexit__(None, None, None)

    assert hydrated_runtime is runtime
    assert service._event_services is None
    assert service._conversation_records == {}
    runtime.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_fork_rejects_id_of_unloaded_persisted_conversation(tmp_path):
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )
    async with ConversationService(conversations_dir=conversations_dir) as primary:
        source, _ = await primary.start_conversation(request)
        target, _ = await primary.start_conversation(request)

    target_meta = conversations_dir / target.id.hex / "meta.json"
    original_meta = target_meta.read_text()
    async with ConversationService(conversations_dir=conversations_dir) as restarted:
        assert restarted._event_services == {}
        with pytest.raises(ValueError, match="already exists"):
            await restarted.fork_conversation(source.id, fork_id=target.id)

    assert target_meta.read_text() == original_meta


class TestConversationServiceSearchConversations:
    """测试用例代表 ConversationService.search_conversations 方法。"""

    @pytest.mark.asyncio
    async def test_search_conversations_inactive_service(self, conversation_service):
        """测试当服务处于非活动状态时 search_conversations 是否会引发 ValueError。"""
        conversation_service._event_services = None

        with pytest.raises(ValueError, match="inactive_service"):
            await conversation_service.search_conversations()

    @pytest.mark.asyncio
    async def test_search_conversations_empty_result(self, conversation_service):
        """在没有对话的情况下测试 search_conversations。"""
        result = await conversation_service.search_conversations()

        assert isinstance(result, ConversationPage)
        assert result.items == []
        assert result.next_page_id is None

    @pytest.mark.asyncio
    async def test_search_conversations_basic(
        self, conversation_service, sample_stored_conversation
    ):
        """测试基本 search_conversations 功能。"""
        # 创建模拟对象事件服务
        mock_service = AsyncMock(spec=EventService)
        mock_service.stored = sample_stored_conversation
        mock_state = ConversationState(
            id=sample_stored_conversation.id,
            agent=_sample_agent(),
            workspace=sample_stored_conversation.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=sample_stored_conversation.confirmation_policy,
        )
        mock_service.get_state.return_value = mock_state

        conversation_id = sample_stored_conversation.id
        conversation_service._event_services[conversation_id] = mock_service

        result = await conversation_service.search_conversations()

        assert len(result.items) == 1
        assert result.items[0].id == conversation_id
        assert result.items[0].execution_status == ConversationExecutionStatus.IDLE
        assert result.next_page_id is None

    @pytest.mark.asyncio
    async def test_search_conversations_with_critic_redacts_api_key(
        self, conversation_service
    ):
        """ConversationInfo应该序列化批评机密而不拒绝他们。"""
        agent = Agent(
            llm=LLM(model="gpt-4o", api_key=SecretStr("llm-secret")),
            tools=[],
            critic=APIBasedCritic(
                api_key=SecretStr("critic-secret"),
                server_url="https://critic.example.com",
                model_name="critic",
            ),
        )
        stored_conv = StoredConversation(
            id=uuid4(),
            workspace=LocalWorkspace(working_dir="workspace/project"),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
        )

        mock_service = AsyncMock(spec=EventService)
        mock_service.stored = stored_conv
        mock_service.get_state.return_value = ConversationState(
            id=stored_conv.id,
            agent=agent,
            workspace=stored_conv.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=stored_conv.confirmation_policy,
        )
        conversation_service._event_services[stored_conv.id] = mock_service

        result = await conversation_service.search_conversations()

        info = result.items[0]
        assert isinstance(info.agent.critic, APIBasedCritic)
        assert info.agent.critic.api_key is None

        payload = info.model_dump(mode="json")
        assert payload["agent"]["llm"]["api_key"] is None
        assert payload["agent"]["critic"]["api_key"] is None
        assert "llm-secret" not in str(payload)
        assert "critic-secret" not in str(payload)
        assert "critic-secret" not in str(info)

    @pytest.mark.asyncio
    async def test_search_conversations_status_filter(self, conversation_service):
        """测试按状态过滤对话。"""
        # 创建具有不同状态的多个对话
        conversations = []
        for i, status in enumerate(
            [
                ConversationExecutionStatus.IDLE,
                ConversationExecutionStatus.RUNNING,
                ConversationExecutionStatus.FINISHED,
            ]
        ):
            stored_conv = StoredConversation(
                id=uuid4(),
                workspace=LocalWorkspace(working_dir="workspace/project"),
                confirmation_policy=NeverConfirm(),
                initial_message=None,
                metrics=None,
                created_at=datetime(2025, 1, 1, 12, i, 0, tzinfo=UTC),
                updated_at=datetime(2025, 1, 1, 12, i + 30, 0, tzinfo=UTC),
            )

            mock_service = AsyncMock(spec=EventService)
            mock_service.stored = stored_conv
            mock_state = ConversationState(
                id=stored_conv.id,
                agent=_sample_agent(),
                workspace=stored_conv.workspace,
                execution_status=status,
                confirmation_policy=stored_conv.confirmation_policy,
            )
            mock_service.get_state.return_value = mock_state

            conversation_service._event_services[stored_conv.id] = mock_service
            conversations.append((stored_conv.id, status))

        # 按 IDLE 状态测试过滤
        result = await conversation_service.search_conversations(
            execution_status=ConversationExecutionStatus.IDLE
        )
        assert len(result.items) == 1
        assert result.items[0].execution_status == ConversationExecutionStatus.IDLE

        # 按 RUNNING 状态测试过滤
        result = await conversation_service.search_conversations(
            execution_status=ConversationExecutionStatus.RUNNING
        )
        assert len(result.items) == 1
        assert result.items[0].execution_status == ConversationExecutionStatus.RUNNING

        # 按不存在状态测试过滤
        result = await conversation_service.search_conversations(
            execution_status=ConversationExecutionStatus.ERROR
        )
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_search_conversations_sorting(self, conversation_service):
        """测试按不同标准对对话进行排序。"""
        # 创建具有不同时间戳的对话
        conversations = []

        for i in range(3):
            stored_conv = StoredConversation(
                id=uuid4(),
                workspace=LocalWorkspace(working_dir="workspace/project"),
                confirmation_policy=NeverConfirm(),
                initial_message=None,
                metrics=None,
                created_at=datetime(2025, 1, i + 1, 12, 0, 0, tzinfo=UTC),  # 不同的日子
                updated_at=datetime(2025, 1, i + 1, 12, 30, 0, tzinfo=UTC),
            )

            mock_service = AsyncMock(spec=EventService)
            mock_service.stored = stored_conv
            mock_state = ConversationState(
                id=stored_conv.id,
                agent=_sample_agent(),
                workspace=stored_conv.workspace,
                execution_status=ConversationExecutionStatus.IDLE,
                confirmation_policy=stored_conv.confirmation_policy,
            )
            mock_service.get_state.return_value = mock_state

            conversation_service._event_services[stored_conv.id] = mock_service
            conversations.append(stored_conv)

        # 测试 CREATED_AT（升序）
        result = await conversation_service.search_conversations(
            sort_order=ConversationSortOrder.CREATED_AT
        )
        assert len(result.items) == 3
        assert (
            result.items[0].created_at
            < result.items[1].created_at
            < result.items[2].created_at
        )

        # 测试 CREATED_AT_DESC（降序）- 默认
        result = await conversation_service.search_conversations(
            sort_order=ConversationSortOrder.CREATED_AT_DESC
        )
        assert len(result.items) == 3
        assert (
            result.items[0].created_at
            > result.items[1].created_at
            > result.items[2].created_at
        )

        # 测试 UPDATED_AT（升序）
        result = await conversation_service.search_conversations(
            sort_order=ConversationSortOrder.UPDATED_AT
        )
        assert len(result.items) == 3
        assert (
            result.items[0].updated_at
            < result.items[1].updated_at
            < result.items[2].updated_at
        )

        # 测试 UPDATED_AT_DESC（降序）
        result = await conversation_service.search_conversations(
            sort_order=ConversationSortOrder.UPDATED_AT_DESC
        )
        assert len(result.items) == 3
        assert (
            result.items[0].updated_at
            > result.items[1].updated_at
            > result.items[2].updated_at
        )

    @pytest.mark.asyncio
    async def test_search_conversations_pagination(self, conversation_service):
        """测试分页功能。"""
        # 创建 5 个对话
        conversation_ids = []
        for i in range(5):
            stored_conv = StoredConversation(
                id=uuid4(),
                workspace=LocalWorkspace(working_dir="workspace/project"),
                confirmation_policy=NeverConfirm(),
                initial_message=None,
                metrics=None,
                created_at=datetime(2025, 1, 1, 12, i, 0, tzinfo=UTC),
                updated_at=datetime(2025, 1, 1, 12, i + 30, 0, tzinfo=UTC),
            )

            mock_service = AsyncMock(spec=EventService)
            mock_service.stored = stored_conv
            mock_state = ConversationState(
                id=stored_conv.id,
                agent=_sample_agent(),
                workspace=stored_conv.workspace,
                execution_status=ConversationExecutionStatus.IDLE,
                confirmation_policy=stored_conv.confirmation_policy,
            )
            mock_service.get_state.return_value = mock_state

            conversation_service._event_services[stored_conv.id] = mock_service
            conversation_ids.append(stored_conv.id)

        # 测试首页限制为 2
        result = await conversation_service.search_conversations(limit=2)
        assert len(result.items) == 2
        assert result.next_page_id is not None

        # 使用 next_page_id 测试第二页
        result = await conversation_service.search_conversations(
            page_id=result.next_page_id, limit=2
        )
        assert len(result.items) == 2
        assert result.next_page_id is not None

        # 测试最后一页
        result = await conversation_service.search_conversations(
            page_id=result.next_page_id, limit=2
        )
        assert len(result.items) == 1  # 仅剩一件商品
        assert result.next_page_id is None

    @pytest.mark.asyncio
    async def test_search_conversations_combined_filter_and_sort(
        self, conversation_service
    ):
        """测试将状态过滤与排序相结合。"""
        # 创建具有混合状态和时间戳的对话
        conversations_data = [
            (
                ConversationExecutionStatus.IDLE,
                datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            ),
            (
                ConversationExecutionStatus.RUNNING,
                datetime(2025, 1, 2, 12, 0, 0, tzinfo=UTC),
            ),
            (
                ConversationExecutionStatus.IDLE,
                datetime(2025, 1, 3, 12, 0, 0, tzinfo=UTC),
            ),
            (
                ConversationExecutionStatus.FINISHED,
                datetime(2025, 1, 4, 12, 0, 0, tzinfo=UTC),
            ),
        ]

        for status, created_at in conversations_data:
            stored_conv = StoredConversation(
                id=uuid4(),
                workspace=LocalWorkspace(working_dir="workspace/project"),
                confirmation_policy=NeverConfirm(),
                initial_message=None,
                metrics=None,
                created_at=created_at,
                updated_at=created_at,
            )

            mock_service = AsyncMock(spec=EventService)
            mock_service.stored = stored_conv
            mock_state = ConversationState(
                id=stored_conv.id,
                agent=_sample_agent(),
                workspace=stored_conv.workspace,
                execution_status=status,
                confirmation_policy=stored_conv.confirmation_policy,
            )
            mock_service.get_state.return_value = mock_state

            conversation_service._event_services[stored_conv.id] = mock_service

        # 按 IDLE 状态过滤并按 CREATED_AT_DESC 排序
        result = await conversation_service.search_conversations(
            execution_status=ConversationExecutionStatus.IDLE,
            sort_order=ConversationSortOrder.CREATED_AT_DESC,
        )

        assert len(result.items) == 2  # 两个 IDLE 对话
        # 应按 created_at 降序排序（最新的在前）
        assert result.items[0].created_at > result.items[1].created_at

    @pytest.mark.asyncio
    async def test_search_conversations_invalid_page_id(
        self, conversation_service, sample_stored_conversation
    ):
        """使用无效的 page_id 测试 search_conversations。"""
        mock_service = AsyncMock(spec=EventService)
        mock_service.stored = sample_stored_conversation
        mock_state = ConversationState(
            id=sample_stored_conversation.id,
            agent=_sample_agent(),
            workspace=sample_stored_conversation.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=sample_stored_conversation.confirmation_policy,
        )
        mock_service.get_state.return_value = mock_state

        conversation_service._event_services[sample_stored_conversation.id] = (
            mock_service
        )

        # 使用不存在的 page_id
        invalid_page_id = uuid4().hex
        result = await conversation_service.search_conversations(
            page_id=invalid_page_id
        )

        # 应该返回所有项目，因为 page_id 与任何对话都不匹配
        assert len(result.items) == 1
        assert result.next_page_id is None


class TestConversationServiceCountConversations:
    """测试用例代表 ConversationService.count_conversations 方法。"""

    @pytest.mark.asyncio
    async def test_count_conversations_inactive_service(self, conversation_service):
        """测试当服务处于非活动状态时 count_conversations 是否会引发 ValueError。"""
        conversation_service._event_services = None

        with pytest.raises(ValueError, match="inactive_service"):
            await conversation_service.count_conversations()

    @pytest.mark.asyncio
    async def test_count_conversations_empty_result(self, conversation_service):
        """在没有对话的情况下测试 count_conversations。"""
        result = await conversation_service.count_conversations()
        assert result == 0

    @pytest.mark.asyncio
    async def test_count_conversations_basic(
        self, conversation_service, sample_stored_conversation
    ):
        """测试基本 count_conversations 功能。"""
        # 创建模拟对象事件服务
        mock_service = AsyncMock(spec=EventService)
        mock_service.stored = sample_stored_conversation
        mock_state = ConversationState(
            id=sample_stored_conversation.id,
            agent=_sample_agent(),
            workspace=sample_stored_conversation.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=sample_stored_conversation.confirmation_policy,
        )
        mock_service.get_state.return_value = mock_state

        conversation_id = sample_stored_conversation.id
        conversation_service._event_services[conversation_id] = mock_service

        result = await conversation_service.count_conversations()
        assert result == 1

    @pytest.mark.asyncio
    async def test_count_conversations_status_filter(self, conversation_service):
        """测试使用状态过滤器对对话进行计数。"""
        # 创建具有不同状态的多个对话
        statuses = [
            ConversationExecutionStatus.IDLE,
            ConversationExecutionStatus.RUNNING,
            ConversationExecutionStatus.FINISHED,
            ConversationExecutionStatus.IDLE,  # 另IDLE一个
        ]

        for i, status in enumerate(statuses):
            stored_conv = StoredConversation(
                id=uuid4(),
                workspace=LocalWorkspace(working_dir="workspace/project"),
                confirmation_policy=NeverConfirm(),
                initial_message=None,
                metrics=None,
                created_at=datetime(2025, 1, 1, 12, i, 0, tzinfo=UTC),
                updated_at=datetime(2025, 1, 1, 12, i + 30, 0, tzinfo=UTC),
            )

            mock_service = AsyncMock(spec=EventService)
            mock_service.stored = stored_conv
            mock_state = ConversationState(
                id=stored_conv.id,
                agent=_sample_agent(),
                workspace=stored_conv.workspace,
                execution_status=status,
                confirmation_policy=stored_conv.confirmation_policy,
            )
            mock_service.get_state.return_value = mock_state

            conversation_service._event_services[stored_conv.id] = mock_service

        # 测试统计所有对话
        result = await conversation_service.count_conversations()
        assert result == 4

        # 按 IDLE 状态测试计数（应为 2）
        result = await conversation_service.count_conversations(
            execution_status=ConversationExecutionStatus.IDLE
        )
        assert result == 2

        # 按 RUNNING 状态测试计数（应为 1）
        result = await conversation_service.count_conversations(
            execution_status=ConversationExecutionStatus.RUNNING
        )
        assert result == 1

        # 按不存在状态测试计数（应为 0）
        result = await conversation_service.count_conversations(
            execution_status=ConversationExecutionStatus.ERROR
        )
        assert result == 0

    @pytest.mark.asyncio
    async def test_count_conversations_includes_regular_and_acp(
        self, conversation_service
    ):
        legacy_conversation = StoredConversation(
            id=uuid4(),
            workspace=LocalWorkspace(working_dir="workspace/project"),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
        )
        acp_conversation = StoredConversation(
            id=uuid4(),
            workspace=LocalWorkspace(working_dir="workspace/project"),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
            created_at=datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 13, 30, 0, tzinfo=UTC),
        )

        for stored_conv in (legacy_conversation, acp_conversation):
            mock_service = AsyncMock(spec=EventService)
            mock_service.stored = stored_conv
            mock_service.get_state.return_value = ConversationState(
                id=stored_conv.id,
                agent=_sample_agent(),
                workspace=stored_conv.workspace,
                execution_status=ConversationExecutionStatus.IDLE,
                confirmation_policy=stored_conv.confirmation_policy,
            )
            conversation_service._event_services[stored_conv.id] = mock_service

        assert await conversation_service.count_conversations() == 2


class TestConversationServiceStartConversation:
    """测试用例代表 ConversationService.start_conversation 方法。"""

    @pytest.mark.asyncio
    async def test_start_conversation_with_secrets(self, conversation_service):
        """测试开始时机密是否传递到新对话。"""
        # 创建测试机密
        test_secrets: dict[str, SecretSource] = {
            "api_key": StaticSecret(value=SecretStr("secret-api-key-123")),
            "database_url": StaticSecret(
                value=SecretStr("postgresql://user:pass@host:5432/db")
            ),
        }

        # 使用机密创建开始对话请求
        with tempfile.TemporaryDirectory() as temp_dir:
            request = StartConversationRequest(
                agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
                workspace=LocalWorkspace(working_dir=temp_dir),
                confirmation_policy=NeverConfirm(),
                secrets=test_secrets,
            )

            # 模拟对象 EventService 构造函数和启动方法
            with patch(
                "openhands.agent_server.conversation_service.EventService"
            ) as mock_event_service_class:
                mock_event_service = AsyncMock(spec=EventService)
                mock_event_service_class.return_value = mock_event_service

                # 模拟对象将返回的状态
                mock_state = ConversationState(
                    id=uuid4(),
                    agent=request.agent,
                    workspace=request.workspace,
                    execution_status=ConversationExecutionStatus.IDLE,
                    confirmation_policy=request.confirmation_policy,
                )
                mock_event_service.get_state.return_value = mock_state
                mock_event_service.stored = StoredConversation(
                    id=mock_state.id,
                    **request.model_dump(mode="json", context={"expose_secrets": True}),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )

                # 开始对话
                result, _ = await conversation_service.start_conversation(request)

                # 验证 EventService 是否正确创建
                mock_event_service_class.assert_called_once()
                call_args = mock_event_service_class.call_args
                stored_conversation = call_args.kwargs["stored"]

                # 验证机密是否已传递到存储的对话
                assert stored_conversation.secrets == test_secrets
                assert "api_key" in stored_conversation.secrets
                assert "database_url" in stored_conversation.secrets
                assert (
                    stored_conversation.secrets["api_key"].get_value()
                    == "secret-api-key-123"
                )
                assert (
                    stored_conversation.secrets["database_url"].get_value()
                    == "postgresql://user:pass@host:5432/db"
                )

                # 验证对话已开始
                mock_event_service.start.assert_called_once()

                # 验证结果
                assert result.id == mock_state.id
                assert result.execution_status == ConversationExecutionStatus.IDLE

    @pytest.mark.asyncio
    async def test_start_conversation_without_secrets(self, conversation_service):
        """测试是否可以在没有机密的情况下启动对话。"""
        # 创建不带机密的开始对话请求
        with tempfile.TemporaryDirectory() as temp_dir:
            request = StartConversationRequest(
                agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
                workspace=LocalWorkspace(working_dir=temp_dir),
                confirmation_policy=NeverConfirm(),
            )

            # 模拟对象 EventService 构造函数和启动方法
            with patch(
                "openhands.agent_server.conversation_service.EventService"
            ) as mock_event_service_class:
                mock_event_service = AsyncMock(spec=EventService)
                mock_event_service_class.return_value = mock_event_service

                # 模拟对象将返回的状态
                mock_state = ConversationState(
                    id=uuid4(),
                    agent=request.agent,
                    workspace=request.workspace,
                    execution_status=ConversationExecutionStatus.IDLE,
                    confirmation_policy=request.confirmation_policy,
                )
                mock_event_service.get_state.return_value = mock_state
                mock_event_service.stored = StoredConversation(
                    id=mock_state.id,
                    **request.model_dump(mode="json", context={"expose_secrets": True}),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )

                # 开始对话
                result, _ = await conversation_service.start_conversation(request)

                # 验证 EventService 是否正确创建
                mock_event_service_class.assert_called_once()
                call_args = mock_event_service_class.call_args
                stored_conversation = call_args.kwargs["stored"]

                # 验证机密是一个空字典（默认）
                assert stored_conversation.secrets == {}

                # 验证对话已开始
                mock_event_service.start.assert_called_once()

                # 验证结果
                assert result.id == mock_state.id
                assert result.execution_status == ConversationExecutionStatus.IDLE

    @pytest.mark.asyncio
    async def test_start_conversation_with_worktree_uses_git_worktree(
        self, conversation_service, tmp_path
    ):
        repo_dir = tmp_path / "repo"
        _init_git_repo(repo_dir)
        conversation_id = uuid4()

        request = StartConversationRequest(
            conversation_id=conversation_id,
            agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
            workspace=LocalWorkspace(working_dir=repo_dir),
            confirmation_policy=NeverConfirm(),
            worktree=True,
        )

        captured: dict[str, Any] = {}

        def _event_service_factory(**kwargs):
            stored = kwargs["stored"]
            agent = cast(AgentBase, kwargs.get("agent"))
            captured["stored"] = stored
            captured["agent"] = agent
            mock_event_service = AsyncMock(spec=EventService)
            mock_event_service.stored = stored
            mock_event_service.get_state.return_value = ConversationState(
                id=stored.id,
                agent=agent or _sample_agent(),
                workspace=stored.workspace,
                execution_status=ConversationExecutionStatus.IDLE,
                confirmation_policy=stored.confirmation_policy,
            )
            return mock_event_service

        worktree_root = conversation_service.conversation_worktree_root
        with patch(
            "openhands.agent_server.conversation_service.EventService",
            side_effect=_event_service_factory,
        ):
            result, _ = await conversation_service.start_conversation(request)

        stored = captured["stored"]
        expected_worktree = worktree_root / str(conversation_id) / repo_dir.name
        expected_branch = f"openhands/{conversation_id}"

        assert stored.worktree is True
        assert stored.workspace.working_dir == str(expected_worktree)
        assert result.workspace.working_dir == str(expected_worktree)
        assert (expected_worktree / ".git").exists()
        assert (
            run_git_command(
                ["git", "--no-pager", "branch", "--show-current"],
                expected_worktree,
            )
            == expected_branch
        )
        agent = captured["agent"]
        assert agent.agent_context is not None
        suffix = agent.agent_context.system_message_suffix
        assert suffix is not None
        assert str(repo_dir.resolve()) in suffix
        assert str(expected_worktree) in suffix
        assert expected_branch in suffix
        assert "Do all file and git work inside this worktree" in suffix

    @pytest.mark.asyncio
    async def test_start_conversation_with_worktree_preserves_relative_workspace(
        self, conversation_service, tmp_path
    ):
        repo_dir = tmp_path / "repo"
        _init_git_repo(repo_dir)
        workspace_dir = repo_dir / "src" / "pkg"
        workspace_dir.mkdir(parents=True)
        conversation_id = uuid4()

        request = StartConversationRequest(
            conversation_id=conversation_id,
            agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
            workspace=LocalWorkspace(working_dir=workspace_dir),
            confirmation_policy=NeverConfirm(),
            worktree=True,
        )

        captured: dict[str, Any] = {}

        def _event_service_factory(**kwargs):
            stored = kwargs["stored"]
            agent = cast(AgentBase, kwargs.get("agent"))
            captured["stored"] = stored
            captured["agent"] = agent
            mock_event_service = AsyncMock(spec=EventService)
            mock_event_service.stored = stored
            mock_event_service.get_state.return_value = ConversationState(
                id=stored.id,
                agent=agent or _sample_agent(),
                workspace=stored.workspace,
                execution_status=ConversationExecutionStatus.IDLE,
                confirmation_policy=stored.confirmation_policy,
            )
            return mock_event_service

        worktree_root = conversation_service.conversation_worktree_root
        with patch(
            "openhands.agent_server.conversation_service.EventService",
            side_effect=_event_service_factory,
        ):
            result, _ = await conversation_service.start_conversation(request)

        stored = captured["stored"]
        expected_worktree = worktree_root / str(conversation_id) / repo_dir.name
        expected_workspace = expected_worktree / "src" / "pkg"

        assert stored.worktree is True
        assert stored.workspace.working_dir == str(expected_workspace)
        assert result.workspace.working_dir == str(expected_workspace)
        assert (expected_worktree / ".git").exists()

    @pytest.mark.asyncio
    async def test_start_conversation_with_worktree_ignores_non_git_workspace(
        self, conversation_service, tmp_path
    ):
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        conversation_id = uuid4()
        worktree_root = conversation_service.conversation_worktree_root

        request = StartConversationRequest(
            conversation_id=conversation_id,
            agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
            workspace=LocalWorkspace(working_dir=workspace_dir),
            confirmation_policy=NeverConfirm(),
            worktree=True,
        )

        captured: dict[str, Any] = {}

        def _event_service_factory(**kwargs):
            stored = kwargs["stored"]
            agent = cast(AgentBase, kwargs.get("agent"))
            captured["stored"] = stored
            captured["agent"] = agent
            mock_event_service = AsyncMock(spec=EventService)
            mock_event_service.stored = stored
            mock_event_service.get_state.return_value = ConversationState(
                id=stored.id,
                agent=agent or _sample_agent(),
                workspace=stored.workspace,
                execution_status=ConversationExecutionStatus.IDLE,
                confirmation_policy=stored.confirmation_policy,
            )
            return mock_event_service

        with patch(
            "openhands.agent_server.conversation_service.EventService",
            side_effect=_event_service_factory,
        ):
            result, _ = await conversation_service.start_conversation(request)

        stored = captured["stored"]

        agent = captured["agent"]
        assert stored.worktree is True
        assert stored.workspace.working_dir == str(workspace_dir)
        assert result.workspace.working_dir == str(workspace_dir)
        assert agent.agent_context is None
        assert not (worktree_root / str(conversation_id)).exists()

    def test_get_worktree_start_point_prefers_origin_default_branch(self, tmp_path):
        """对于 ``origin`` 遥控器，首先获取并返回 ``origin/<default>``。

        当远程默认分支可用时，本地 ``main``/``master`` 不应影响选择。
        """
        upstream = tmp_path / "upstream.git"
        run_git_command(["git", "init", "--bare", "-b", "trunk", str(upstream)])

        repo_dir = tmp_path / "repo"
        _init_git_repo(repo_dir)
        # 将本地默认值重命名为“trunk”并将其发布，以便 origin/HEAD 解析为 origin/trunk（
        # 而不是 main/master）。
        #
        run_git_command(["git", "branch", "-m", "main", "trunk"], repo_dir)
        run_git_command(
            ["git", "remote", "add", "origin", str(upstream)],
            repo_dir,
        )
        run_git_command(["git", "push", "-u", "origin", "trunk"], repo_dir)
        run_git_command(
            ["git", "remote", "set-head", "origin", "trunk"],
            repo_dir,
        )
        # 创建一个本地“主”分支，我们希望该分支成为 IGNORED 支持远程默认分支，因此如果我
        # 们默默地失败，则此测试将失败。
        #
        run_git_command(["git", "branch", "main"], repo_dir)

        # 添加新的上游提交； 起点必须反映此提交，证明我们在解析之前已获取。
        #
        clone_dir = tmp_path / "publisher"
        run_git_command(
            ["git", "clone", str(upstream), str(clone_dir)],
        )
        (clone_dir / "remote.txt").write_text("remote\n")
        run_git_command(["git", "add", "remote.txt"], clone_dir)
        run_git_command(
            [
                "git",
                "-c",
                "user.name=OpenHands Test",
                "-c",
                "user.email=openhands@example.com",
                "commit",
                "-m",
                "remote update",
            ],
            clone_dir,
        )
        run_git_command(["git", "push", "origin", "trunk"], clone_dir)
        remote_tip = run_git_command(
            ["git", "--no-pager", "rev-parse", "trunk"], clone_dir
        )

        start_point = _get_worktree_start_point(repo_dir)

        assert start_point == "origin/trunk"
        resolved = run_git_command(
            ["git", "--no-pager", "rev-parse", start_point], repo_dir
        )
        assert resolved == remote_tip

    def test_get_worktree_start_point_falls_back_to_local_main(self, tmp_path):
        """无``origin``远程→回退到本地``main``。"""
        repo_dir = tmp_path / "repo"
        _init_git_repo(repo_dir)  # 创建本地“主”
        # 将 HEAD 移出 main，以便我们证明 main 是通过策略选择的，而不是因为它恰好是当前
        # 分支。
        #
        run_git_command(["git", "checkout", "-b", "feature/x"], repo_dir)

        assert _get_worktree_start_point(repo_dir) == "main"

    def test_get_worktree_start_point_falls_back_to_master(self, tmp_path):
        """没有远程也没有本地 ``main`` → 回退到本地 ``master``。"""
        repo_dir = tmp_path / "repo"
        _init_git_repo(repo_dir)
        run_git_command(["git", "branch", "-m", "main", "master"], repo_dir)
        # 分离，这样 main 和 master 都不是当前分支。
        run_git_command(["git", "checkout", "--detach"], repo_dir)

        assert _get_worktree_start_point(repo_dir) == "master"

    @pytest.mark.parametrize(
        ("options", "expected_ref", "guidance"),
        [
            (ConversationWorktreeOptions(), "main", "main/master branch"),
            (
                ConversationWorktreeOptions(base="head"),
                "feature/x",
                "current HEAD",
            ),
            (
                ConversationWorktreeOptions(
                    base="ref", ref="release", branch_prefix="me/"
                ),
                "release",
                "`release`",
            ),
        ],
    )
    def test_worktree_options_pick_the_branch_point_and_name(
        self, tmp_path, options, expected_ref, guidance
    ):
        repo_dir = tmp_path / "repo"
        _init_git_repo(repo_dir)

        def commit(message: str) -> None:
            run_git_command(
                [
                    "git",
                    "-c",
                    "user.name=OpenHands Test",
                    "-c",
                    "user.email=openhands@example.com",
                    "commit",
                    "--allow-empty",
                    "-m",
                    message,
                ],
                repo_dir,
            )

        # 三个不同的提示：主要、发布（参考）和签出 HEAD。
        run_git_command(["git", "checkout", "-b", "release"], repo_dir)
        commit("release")
        run_git_command(["git", "checkout", "-b", "feature/x", "main"], repo_dir)
        commit("feature")
        conversation_id = uuid4()
        plan = _plan_conversation_worktree(
            LocalWorkspace(working_dir=repo_dir),
            conversation_id,
            tmp_path / "worktrees",
            options,
        )
        assert plan is not None

        workspace = _create_conversation_worktree(plan)

        def tip(ref: str, cwd: Path) -> str:
            return run_git_command(["git", "--no-pager", "rev-parse", ref], cwd)

        assert tip("HEAD", Path(workspace.working_dir)) == tip(expected_ref, repo_dir)
        assert plan.branch == f"{options.branch_prefix}{conversation_id}"
        assert guidance in plan.guidance

    @pytest.mark.asyncio
    async def test_start_conversation_rejects_missing_worktree_ref(
        self, conversation_service, tmp_path
    ):
        repo_dir = tmp_path / "repo"
        _init_git_repo(repo_dir)
        conversation_id = uuid4()
        request = StartConversationRequest(
            conversation_id=conversation_id,
            agent=_sample_agent(),
            workspace=LocalWorkspace(working_dir=repo_dir),
            worktree=True,
            worktree_options=ConversationWorktreeOptions(
                base="ref", ref="missing-branch"
            ),
        )

        with pytest.raises(GitCommandError, match="missing-branch"):
            await conversation_service.start_conversation(request)

        assert not (
            conversation_service.conversation_worktree_root / str(conversation_id)
        ).exists()
        assert not (
            conversation_service.conversations_dir / conversation_id.hex
        ).exists()

    def test_get_worktree_start_point_tolerates_fetch_failure(self, tmp_path):
        """如果 ``git fetch origin`` 失败，则回退到缓存的引用。

        通过将 ``origin`` 指向不存在的路径来模拟无法访问的远程； 我们仍然希望使用在远
        程 URL 损坏之前设置的缓存引用来解析
        ``origin/<default>``。
        """
        upstream = tmp_path / "upstream.git"
        run_git_command(["git", "init", "--bare", "-b", "main", str(upstream)])

        repo_dir = tmp_path / "repo"
        _init_git_repo(repo_dir)
        run_git_command(
            ["git", "remote", "add", "origin", str(upstream)],
            repo_dir,
        )
        run_git_command(["git", "push", "-u", "origin", "main"], repo_dir)
        run_git_command(
            ["git", "remote", "set-head", "origin", "main"],
            repo_dir,
        )
        # 破坏远程 URL，因此获取失败，但 origin/HEAD 仍被缓存。
        run_git_command(
            ["git", "remote", "set-url", "origin", str(tmp_path / "does-not-exist")],
            repo_dir,
        )

        assert _get_worktree_start_point(repo_dir) == "origin/main"

    @pytest.mark.asyncio
    async def test_start_conversation_with_custom_id(self, conversation_service):
        """测试是否可以使用自定义 conversation_id 启动对话。"""
        custom_id = uuid4()

        # 使用自定义 conversation_id 创建开始对话请求
        with tempfile.TemporaryDirectory() as temp_dir:
            request = StartConversationRequest(
                agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
                workspace=LocalWorkspace(working_dir=temp_dir),
                confirmation_policy=NeverConfirm(),
                conversation_id=custom_id,
            )

            result, is_new = await conversation_service.start_conversation(request)
            assert result.id == custom_id
            assert is_new

    @pytest.mark.asyncio
    async def test_start_conversation_with_duplicate_id(self, conversation_service):
        """测试检测到重复的对话 ID。"""
        custom_id = uuid4()

        # 使用自定义 conversation_id 创建开始对话请求
        with tempfile.TemporaryDirectory() as temp_dir:
            request = StartConversationRequest(
                agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
                workspace=LocalWorkspace(working_dir=temp_dir),
                confirmation_policy=NeverConfirm(),
                conversation_id=custom_id,
            )

            result, is_new = await conversation_service.start_conversation(request)
            assert result.id == custom_id
            assert is_new

            duplicate_request = StartConversationRequest(
                agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
                workspace=LocalWorkspace(working_dir=temp_dir),
                confirmation_policy=NeverConfirm(),
                conversation_id=custom_id,
            )

            result, is_new = await conversation_service.start_conversation(
                duplicate_request
            )
            assert result.id == custom_id
            assert not is_new

    @pytest.mark.asyncio
    async def test_concurrent_start_conversation_same_id_starts_event_service_once(
        self, conversation_service, tmp_path
    ):
        """为一个 id 创建的两个并发不得同时创建。

        预锁存在检查在执行之前会等待，因此并发创建可以在其间提交。 然后，两个调用者都
        会观察到“new”，失败者会为现有 id 启动第二个 EventService
        ，重新运行初始消息。 生命周期锁下的重新检查会关闭该窗口。
        """
        custom_id = uuid4()
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()

        def make_request():
            return StartConversationRequest(
                agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
                workspace=LocalWorkspace(working_dir=str(workspace_dir)),
                confirmation_policy=NeverConfirm(),
                conversation_id=custom_id,
            )

        results = await asyncio.gather(
            conversation_service.start_conversation(make_request()),
            conversation_service.start_conversation(make_request()),
        )

        assert [r.id for r, _ in results] == [custom_id, custom_id]
        # 正是一位呼叫者发起了这次对话； 另一个重复使用了它。
        assert sorted(is_new for _, is_new in results) == [False, True]
        # 决定性检查：一个 EventService，因此初始消息将被传递一次而不是两次。
        #
        assert list(conversation_service._event_services) == [custom_id]

    @pytest.mark.asyncio
    async def test_concurrent_fork_same_id_forks_once(
        self, conversation_service, tmp_path
    ):
        """并发分叉到一个 id 上不得同时分叉。

        失败者必须在``fork()``写入共享持久化目录之前被拒绝； 否则，他们会重新打开获胜
        者的目录，并在其已已持久化事件而不是重复的 ID 上失败。
        """
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()

        source, _ = await conversation_service.start_conversation(
            StartConversationRequest(
                agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
                workspace=LocalWorkspace(working_dir=str(workspace_dir)),
                confirmation_policy=NeverConfirm(),
            )
        )
        source_service = await conversation_service.get_event_service(source.id)
        assert source_service is not None
        await source_service.send_message(
            Message(role="user", content=[TextContent(text="hi")]), run=False
        )

        fork_id = uuid4()
        real_fork = LocalConversation.fork
        fork_calls = 0

        def fork_after_winner_commits(self, **kwargs):
            # 强制进行有害的交错：稍后的 fork() 调用仅在获胜者注册后运行，就像缓慢失败者
            # 的情况一样。
            #
            nonlocal fork_calls
            fork_calls += 1
            if fork_calls > 1:
                deadline = time.monotonic() + 5
                while (
                    fork_id not in conversation_service._conversation_records
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.01)
            return real_fork(self, **kwargs)

        async def fork():
            return await conversation_service.fork_conversation(
                source.id, fork_id=fork_id
            )

        with patch.object(LocalConversation, "fork", fork_after_winner_commits):
            results = await asyncio.gather(fork(), fork(), return_exceptions=True)
        successes = [r for r in results if not isinstance(r, BaseException)]
        failures = [r for r in results if isinstance(r, BaseException)]

        assert len(successes) == 1
        assert successes[0].id == fork_id
        assert [str(f) for f in failures] == [
            f"Conversation with id {fork_id} already exists"
        ]

    @pytest.mark.asyncio
    async def test_start_conversation_reuse_checks_is_open(self, conversation_service):
        """测试会话重用检查事件服务是否打开。"""
        custom_id = uuid4()

        # 创建存在但未打开的模拟对象事件服务
        mock_event_service = AsyncMock(spec=EventService)
        mock_event_service.is_open.return_value = False
        mock_event_service.stored = StoredConversation(
            id=custom_id,
            workspace=LocalWorkspace(working_dir="workspace/project"),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
        )
        conversation_service._event_services[custom_id] = mock_event_service

        with tempfile.TemporaryDirectory() as temp_dir:
            request = StartConversationRequest(
                agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
                workspace=LocalWorkspace(working_dir=temp_dir),
                confirmation_policy=NeverConfirm(),
                conversation_id=custom_id,
            )

            # 模拟对象_start_event_service方法避免实际启动
            with patch.object(
                conversation_service, "_start_event_service"
            ) as mock_start:
                mock_new_service = AsyncMock(spec=EventService)
                mock_new_service.stored = StoredConversation(
                    id=custom_id,
                    workspace=request.workspace,
                    confirmation_policy=request.confirmation_policy,
                    initial_message=request.initial_message,
                    metrics=None,
                    created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                    updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
                )
                mock_state = ConversationState(
                    id=custom_id,
                    agent=request.agent,
                    workspace=request.workspace,
                    execution_status=ConversationExecutionStatus.IDLE,
                    confirmation_policy=request.confirmation_policy,
                )
                mock_new_service.get_state.return_value = mock_state
                mock_start.return_value = mock_new_service

                result, is_new = await conversation_service.start_conversation(request)

                # 应该创建一个新对话，因为现有对话未打开
                assert result.id == custom_id
                assert is_new
                mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_conversation_reuse_when_open(self, conversation_service):
        """测试事件服务打开时对话是否被重用。"""
        custom_id = uuid4()

        # 创建存在且开放的模拟对象事件服务
        mock_event_service = AsyncMock(spec=EventService)
        mock_event_service.is_open.return_value = True
        mock_event_service.stored = StoredConversation(
            id=custom_id,
            workspace=LocalWorkspace(working_dir="workspace/project"),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
        )
        mock_state = ConversationState(
            id=custom_id,
            agent=_sample_agent(),
            workspace=mock_event_service.stored.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=mock_event_service.stored.confirmation_policy,
        )
        mock_event_service.get_state.return_value = mock_state
        conversation_service._event_services[custom_id] = mock_event_service

        with tempfile.TemporaryDirectory() as temp_dir:
            request = StartConversationRequest(
                agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
                workspace=LocalWorkspace(working_dir=temp_dir),
                confirmation_policy=NeverConfirm(),
                conversation_id=custom_id,
            )

            # 模拟对象 _start_event_service 方法以确保它不被调用
            with patch.object(
                conversation_service, "_start_event_service"
            ) as mock_start:
                result, is_new = await conversation_service.start_conversation(request)

                # 应该重用现有的对话，因为它是开放的
                assert result.id == custom_id
                assert not is_new
                mock_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_conversation_returns_existing_acp_conversation(
        self, conversation_service
    ):
        custom_id = uuid4()
        acp_agent = ACPAgent(acp_command=["echo", "test"])
        stored = StoredConversation(
            id=custom_id,
            workspace=LocalWorkspace(working_dir="workspace/project"),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
        )
        mock_event_service = AsyncMock(spec=EventService)
        mock_event_service.is_open.return_value = True
        mock_event_service.stored = stored
        # 智能体现在存在于 base_state.json / 实时对话中。
        mock_event_service._conversation = MagicMock()
        mock_event_service._conversation.agent = acp_agent
        mock_event_service.get_state.return_value = ConversationState(
            id=stored.id,
            agent=acp_agent,
            workspace=stored.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=stored.confirmation_policy,
        )
        conversation_service._event_services[custom_id] = mock_event_service

        with tempfile.TemporaryDirectory() as temp_dir:
            request = StartConversationRequest(
                agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
                workspace=LocalWorkspace(working_dir=temp_dir),
                confirmation_policy=NeverConfirm(),
                conversation_id=custom_id,
            )

            # 通过 conversation_id 重新连接时，会返回存储的会话合同，这样调用者就可以通
            # 过统一端点重新开始 ACP 会话，即使新请求携带的是常规智能体配置。
            #
            with patch.object(
                conversation_service, "_start_event_service"
            ) as mock_start:
                (
                    conversation_info,
                    is_new,
                ) = await conversation_service.start_conversation(request)

                assert is_new is False
                assert isinstance(conversation_info, ConversationInfo)
                assert conversation_info.agent.kind == "ACPAgent"
                mock_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_event_service_failure_cleanup(self, conversation_service):
        """测试启动失败时事件服务是否被清理。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            stored = StoredConversation(
                id=uuid4(),
                workspace=LocalWorkspace(working_dir=temp_dir),
                confirmation_policy=NeverConfirm(),
                initial_message=None,
                metrics=None,
                created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
            )

            # 模拟对象EventService模拟启动失败
            with patch(
                "openhands.agent_server.conversation_service.EventService"
            ) as mock_event_service_class:
                mock_event_service = AsyncMock()
                mock_event_service.start.side_effect = Exception("Startup failed")
                mock_event_service.close = AsyncMock()
                mock_event_service_class.return_value = mock_event_service

                # 尝试启动事件服务应该失败并清理
                with pytest.raises(Exception, match="Startup failed"):
                    await conversation_service._start_event_service(stored)

                # 验证是否调用了清理操作
                mock_event_service.close.assert_called_once()

                # 验证事件服务未存储
                assert stored.id not in conversation_service._event_services

    @pytest.mark.asyncio
    async def test_start_event_service_success_stores_service(
        self, conversation_service
    ):
        """测试事件服务仅在成功启动后才存储。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            stored = StoredConversation(
                id=uuid4(),
                workspace=LocalWorkspace(working_dir=temp_dir),
                confirmation_policy=NeverConfirm(),
                initial_message=None,
                metrics=None,
                created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
                updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
            )

            # 模拟对象EventService模拟成功启动
            with patch(
                "openhands.agent_server.conversation_service.EventService"
            ) as mock_event_service_class:
                mock_event_service = AsyncMock()
                mock_event_service.start = AsyncMock()  # Successful startup
                # 同步方法不得为 AsyncMock（将返回未等待的协程）；
                # mark_subscription_baseline称为同步。
                #
                mock_event_service.mark_subscription_baseline = MagicMock()
                mock_event_service_class.return_value = mock_event_service

                # 启动事件服务应该成功
                result = await conversation_service._start_event_service(stored)

                # 验证启动是否被调用
                mock_event_service.start.assert_called_once()

                # 验证事件服务在成功启动后是否已存储
                assert stored.id in conversation_service._event_services
                assert (
                    conversation_service._event_services[stored.id]
                    == mock_event_service
                )
                assert result == mock_event_service


class TestConversationServiceUpdateConversation:
    """测试用例代表 ConversationService.update_conversation 方法。"""

    @pytest.mark.asyncio
    async def test_update_conversation_success(
        self, conversation_service, sample_stored_conversation
    ):
        """测试对话标题更新是否成功。"""
        # 创建模拟对象事件服务
        mock_service = AsyncMock(spec=EventService)
        mock_service.stored = sample_stored_conversation
        _adopt_saved_meta(mock_service)
        mock_state = ConversationState(
            id=sample_stored_conversation.id,
            agent=_sample_agent(),
            workspace=sample_stored_conversation.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=sample_stored_conversation.confirmation_policy,
        )
        mock_service.get_state.return_value = mock_state

        conversation_id = sample_stored_conversation.id
        conversation_service._event_services[conversation_id] = mock_service

        # 更新标题
        new_title = "My Updated Conversation Title"
        request = UpdateConversationRequest(title=new_title)
        result = await conversation_service.update_conversation(
            conversation_id, request
        )

        # 验证更新是否成功
        assert result is True
        assert mock_service.stored.title == new_title
        mock_service.save_meta.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_conversation_strips_whitespace(
        self, conversation_service, sample_stored_conversation
    ):
        """测试 update_conversation 是否去除前导/尾随空格。"""
        mock_service = AsyncMock(spec=EventService)
        mock_service.stored = sample_stored_conversation
        _adopt_saved_meta(mock_service)
        mock_state = ConversationState(
            id=sample_stored_conversation.id,
            agent=_sample_agent(),
            workspace=sample_stored_conversation.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=sample_stored_conversation.confirmation_policy,
        )
        mock_service.get_state.return_value = mock_state

        conversation_id = sample_stored_conversation.id
        conversation_service._event_services[conversation_id] = mock_service

        # 使用包含空格的标题进行更新
        new_title = "   Whitespace Test   "
        request = UpdateConversationRequest(title=new_title)
        result = await conversation_service.update_conversation(
            conversation_id, request
        )

        # 验证空白已被删除
        assert result is True
        assert mock_service.stored.title == "Whitespace Test"
        mock_service.save_meta.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_conversation_tags_uses_state_lock(
        self, conversation_service, sample_stored_conversation
    ):
        """测试标签更新是否保留 ConversationState 锁。"""
        mock_service = AsyncMock(spec=EventService)
        mock_service.stored = sample_stored_conversation
        _adopt_saved_meta(mock_service)
        mock_state = ConversationState(
            id=sample_stored_conversation.id,
            agent=_sample_agent(),
            workspace=sample_stored_conversation.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=sample_stored_conversation.confirmation_policy,
        )
        acquire_spy = MagicMock(wraps=mock_state._lock.acquire)
        release_spy = MagicMock(wraps=mock_state._lock.release)
        mock_state._lock.acquire = acquire_spy
        mock_state._lock.release = release_spy
        mock_service.get_state.return_value = mock_state

        conversation_id = sample_stored_conversation.id
        conversation_service._event_services[conversation_id] = mock_service

        request = UpdateConversationRequest(tags={"env": "prod"})
        result = await conversation_service.update_conversation(
            conversation_id, request
        )

        assert result is True
        assert mock_service.stored.tags == {"env": "prod"}
        assert mock_state.tags == {"env": "prod"}
        assert acquire_spy.call_count >= 2
        assert release_spy.call_count == acquire_spy.call_count

    @pytest.mark.asyncio
    async def test_update_conversation_tags_wait_does_not_block_event_loop(
        self, conversation_service, sample_stored_conversation
    ):
        """等待状态锁不得停止不相关的异步工作。"""
        mock_service = AsyncMock(spec=EventService)
        mock_service.stored = sample_stored_conversation
        _adopt_saved_meta(mock_service)
        state = ConversationState(
            id=sample_stored_conversation.id,
            agent=_sample_agent(),
            workspace=sample_stored_conversation.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=sample_stored_conversation.confirmation_policy,
        )
        mock_service.get_state.return_value = state

        conversation_id = sample_stored_conversation.id
        conversation_service._event_services[conversation_id] = mock_service

        lock_acquired = threading.Event()
        release_lock = threading.Event()
        timings: dict[str, float] = {}

        def hold_state_lock() -> None:
            with state:
                timings["lock_start"] = time.monotonic()
                lock_acquired.set()
                release_lock.wait(timeout=1.0)
                timings["lock_end"] = time.monotonic()

        holder = threading.Thread(target=hold_state_lock, daemon=True)
        holder.start()
        assert lock_acquired.wait(timeout=1.0)

        async def heartbeat() -> None:
            await asyncio.sleep(0.05)
            timings["heartbeat"] = time.monotonic()

        async def release_after_delay() -> None:
            await asyncio.sleep(0.2)
            release_lock.set()

        with patch.object(
            conversation_service, "_notify_conversation_webhooks", new=AsyncMock()
        ):
            await asyncio.wait_for(
                asyncio.gather(
                    conversation_service.update_conversation(
                        conversation_id,
                        UpdateConversationRequest(tags={"env": "prod"}),
                    ),
                    heartbeat(),
                    release_after_delay(),
                ),
                timeout=1.0,
            )

        holder.join(timeout=1.0)
        assert not holder.is_alive()
        assert mock_service.stored.tags == {"env": "prod"}
        assert state.tags == {"env": "prod"}
        assert timings["heartbeat"] < timings["lock_end"], (
            "update_conversation blocked the async loop while waiting for the "
            "state lock"
        )

    @pytest.mark.asyncio
    async def test_update_conversation_not_found(self, conversation_service):
        """测试更新不存在的对话会返回 False。"""
        non_existent_id = uuid4()
        request = UpdateConversationRequest(title="New Title")
        result = await conversation_service.update_conversation(
            non_existent_id, request
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_update_conversation_inactive_service(self, conversation_service):
        """测试当服务处于非活动状态时 update_conversation 是否会引发 ValueError。"""
        conversation_service._event_services = None

        request = UpdateConversationRequest(title="New Title")
        with pytest.raises(ValueError, match="inactive_service"):
            await conversation_service.update_conversation(uuid4(), request)

    @pytest.mark.asyncio
    async def test_update_conversation_notifies_webhooks(
        self, conversation_service, sample_stored_conversation
    ):
        """测试更新对话是否会触发 Webhook 条通知。"""
        # 创建模拟对象事件服务
        mock_service = AsyncMock(spec=EventService)
        mock_service.stored = sample_stored_conversation
        _adopt_saved_meta(mock_service)
        mock_state = ConversationState(
            id=sample_stored_conversation.id,
            agent=_sample_agent(),
            workspace=sample_stored_conversation.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=sample_stored_conversation.confirmation_policy,
        )
        mock_service.get_state.return_value = mock_state

        conversation_id = sample_stored_conversation.id
        conversation_service._event_services[conversation_id] = mock_service

        # 模拟对象 Webhook 通知
        with patch.object(
            conversation_service, "_notify_conversation_webhooks", new=AsyncMock()
        ) as mock_notify:
            new_title = "Updated Title for Webhook Test"
            request = UpdateConversationRequest(title=new_title)
            result = await conversation_service.update_conversation(
                conversation_id, request
            )

            # 验证 Webhook 被调用
            assert result is True
            mock_notify.assert_called_once()
            # 验证传递给 Webhook 的对话信息是否具有更新的标题
            call_args = mock_notify.call_args[0]
            conversation_info = call_args[0]
            assert conversation_info.title == new_title
            assert isinstance(conversation_info, ConversationInfo)

    @pytest.mark.asyncio
    async def test_update_acp_conversation_notifies_webhooks_with_acp_shape(
        self, conversation_service
    ):
        acp_agent = ACPAgent(acp_command=["echo", "test"])
        stored_conversation = StoredConversation(
            id=uuid4(),
            workspace=LocalWorkspace(working_dir="workspace/project"),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
        )
        mock_service = AsyncMock(spec=EventService)
        mock_service.stored = stored_conversation
        _adopt_saved_meta(mock_service)
        mock_state = ConversationState(
            id=stored_conversation.id,
            agent=acp_agent,
            workspace=stored_conversation.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=stored_conversation.confirmation_policy,
        )
        mock_service.get_state.return_value = mock_state

        conversation_id = stored_conversation.id
        conversation_service._event_services[conversation_id] = mock_service

        with patch.object(
            conversation_service, "_notify_conversation_webhooks", new=AsyncMock()
        ) as mock_notify:
            result = await conversation_service.update_conversation(
                conversation_id, UpdateConversationRequest(title="ACP Title")
            )

            assert result is True
            mock_notify.assert_called_once()
            conversation_info = mock_notify.call_args[0][0]
            assert isinstance(conversation_info, ConversationInfo)
            assert conversation_info.agent.kind == "ACPAgent"

    @pytest.mark.asyncio
    async def test_update_conversation_persists_changes(
        self, conversation_service, sample_stored_conversation
    ):
        """测试标题更改是否已已持久化写入磁盘。"""
        mock_service = AsyncMock(spec=EventService)
        mock_service.stored = sample_stored_conversation
        _adopt_saved_meta(mock_service)
        mock_state = ConversationState(
            id=sample_stored_conversation.id,
            agent=_sample_agent(),
            workspace=sample_stored_conversation.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=sample_stored_conversation.confirmation_policy,
        )
        mock_service.get_state.return_value = mock_state

        conversation_id = sample_stored_conversation.id
        conversation_service._event_services[conversation_id] = mock_service

        # 初始标题应为 None
        assert mock_service.stored.title is None

        # 更新标题
        new_title = "Persisted Title"
        request = UpdateConversationRequest(title=new_title)
        await conversation_service.update_conversation(conversation_id, request)

        # 验证 save_meta 被调用以进行持久化更改
        mock_service.save_meta.assert_called_once()
        # 验证存储的对话具有新标题
        assert mock_service.stored.title == new_title

    @pytest.mark.asyncio
    async def test_update_conversation_multiple_times(
        self, conversation_service, sample_stored_conversation
    ):
        """测试多次更新同一对话。"""
        mock_service = AsyncMock(spec=EventService)
        mock_service.stored = sample_stored_conversation
        _adopt_saved_meta(mock_service)
        mock_state = ConversationState(
            id=sample_stored_conversation.id,
            agent=_sample_agent(),
            workspace=sample_stored_conversation.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=sample_stored_conversation.confirmation_policy,
        )
        mock_service.get_state.return_value = mock_state

        conversation_id = sample_stored_conversation.id
        conversation_service._event_services[conversation_id] = mock_service

        # 第一次更新
        request1 = UpdateConversationRequest(title="First Title")
        result1 = await conversation_service.update_conversation(
            conversation_id, request1
        )
        assert result1 is True
        assert mock_service.stored.title == "First Title"

        # 第二次更新
        request2 = UpdateConversationRequest(title="Second Title")
        result2 = await conversation_service.update_conversation(
            conversation_id, request2
        )
        assert result2 is True
        assert mock_service.stored.title == "Second Title"

        # 第三次更新
        request3 = UpdateConversationRequest(title="Third Title")
        result3 = await conversation_service.update_conversation(
            conversation_id, request3
        )
        assert result3 is True
        assert mock_service.stored.title == "Third Title"

        # 验证 save_meta 被调用了 3 次
        assert mock_service.save_meta.call_count == 3

    @pytest.mark.asyncio
    async def test_update_conversation_sets_updated_at(
        self, conversation_service, sample_stored_conversation
    ):
        """测试 update_conversation 是否前进 updated_at。

        重命名对话是一个有意义的改变； 时间戳必须反映事件发生的时间，而不是停留在会话
        创建时设置的值。
        """
        mock_service = AsyncMock(spec=EventService)
        mock_service.stored = sample_stored_conversation
        _adopt_saved_meta(mock_service)
        mock_state = ConversationState(
            id=sample_stored_conversation.id,
            agent=_sample_agent(),
            workspace=sample_stored_conversation.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=sample_stored_conversation.confirmation_policy,
        )
        mock_service.get_state.return_value = mock_state

        conversation_id = sample_stored_conversation.id
        conversation_service._event_services[conversation_id] = mock_service

        original_updated_at = mock_service.stored.updated_at

        request = UpdateConversationRequest(title="New Title")
        await conversation_service.update_conversation(conversation_id, request)

        assert mock_service.stored.updated_at > original_updated_at


class TestConversationServiceDeleteConversation:
    """测试用例代表 ConversationService.delete_conversation 方法。"""

    @pytest.mark.asyncio
    async def test_delete_conversation_inactive_service(self, conversation_service):
        """测试当服务处于非活动状态时 delete_conversation 是否会引发 ValueError。"""
        conversation_service._event_services = None

        with pytest.raises(ValueError, match="inactive_service"):
            await conversation_service.delete_conversation(uuid4())

    @pytest.mark.asyncio
    async def test_delete_conversation_not_found(self, conversation_service):
        """使用不存在的对话 ID 测试 delete_conversation。"""
        result = await conversation_service.delete_conversation(uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_missing_conversations_do_not_accumulate_locks(
        self, conversation_service
    ):
        for _ in range(100):
            conversation_id = uuid4()
            assert await conversation_service.get_event_service(conversation_id) is None
            assert (
                await conversation_service.resume_conversation(conversation_id) is False
            )
            assert (
                await conversation_service.delete_conversation(conversation_id) is False
            )

        assert len(conversation_service._conversation_locks) == 0

    @pytest.mark.asyncio
    async def test_delete_conversation_success(self, conversation_service):
        """测试成功删除对话。"""
        conversation_id = uuid4()

        # 创建模拟对象事件服务
        mock_service = AsyncMock(spec=EventService)
        mock_service.conversation_dir = "/tmp/test_conversation"
        mock_service.stored = StoredConversation(
            id=conversation_id,
            workspace=LocalWorkspace(working_dir="/tmp/test_workspace"),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
        )
        mock_state = ConversationState(
            id=conversation_id,
            agent=_sample_agent(),
            workspace=mock_service.stored.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=mock_service.stored.confirmation_policy,
        )
        mock_service.get_state.return_value = mock_state

        # 添加到服务
        conversation_service._event_services[conversation_id] = mock_service

        # 模拟对象删除目录以避免实际的文件系统操作
        with patch(
            "openhands.agent_server.conversation_service.safe_rmtree"
        ) as mock_rmtree:
            mock_rmtree.return_value = True

            result = await conversation_service.delete_conversation(conversation_id)

            assert result is True
            assert conversation_id not in conversation_service._event_services

            # 验证事件服务已关闭
            mock_service.close.assert_called_once()

            # 验证目录是否已删除
            assert mock_rmtree.call_count == 1
            mock_rmtree.assert_any_call(
                "/tmp/test_conversation",
                "conversation directory for " + str(conversation_id),
            )

    @pytest.mark.asyncio
    async def test_delete_conversation_notifies_webhooks_with_deleting_status(
        self, conversation_service, sample_stored_conversation
    ):
        """测试删除对话是否会触发 Webhook 条通知。

        验证当调用 delete_conversation 时，Webhook 是否收到设置为“删除”的
        execution_status 的对话信息。
        """
        # 创建模拟对象事件服务
        mock_service = AsyncMock(spec=EventService)
        mock_service.conversation_dir = "/tmp/test_conversation"
        mock_service.stored = sample_stored_conversation
        mock_state = ConversationState(
            id=sample_stored_conversation.id,
            agent=_sample_agent(),
            workspace=sample_stored_conversation.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=sample_stored_conversation.confirmation_policy,
        )
        mock_service.get_state.return_value = mock_state

        conversation_id = sample_stored_conversation.id
        conversation_service._event_services[conversation_id] = mock_service

        # 模拟对象 Webhook 通知
        with patch.object(
            conversation_service, "_notify_conversation_webhooks", new=AsyncMock()
        ) as mock_notify:
            # 模拟对象目录删除
            with patch(
                "openhands.agent_server.conversation_service.safe_rmtree"
            ) as mock_rmtree:
                mock_rmtree.return_value = True

                result = await conversation_service.delete_conversation(conversation_id)

                # 验证删除成功
                assert result is True
                assert conversation_id not in conversation_service._event_services

                # 验证 Webhook 被调用
                mock_notify.assert_called_once()

                # 验证传递给 Webhook 的对话信息是否具有“删除”状态
                call_args = mock_notify.call_args[0]
                conversation_info = call_args[0]
                assert (
                    conversation_info.execution_status
                    == ConversationExecutionStatus.DELETING
                )
                assert isinstance(conversation_info, ConversationInfo)

                # 验证事件服务已关闭
                mock_service.close.assert_called_once()

                # 验证目录是否已删除
                assert mock_rmtree.call_count == 1

    @pytest.mark.asyncio
    async def test_delete_conversation_webhook_failure(self, conversation_service):
        """当 Webhook 通知失败时，测试 delete_conversation 继续。"""
        conversation_id = uuid4()

        # 创建模拟对象事件服务
        mock_service = AsyncMock(spec=EventService)
        mock_service.conversation_dir = "/tmp/test_conversation"
        mock_service.stored = StoredConversation(
            id=conversation_id,
            workspace=LocalWorkspace(working_dir="/tmp/test_workspace"),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
        )

        # 让 get_state 引发异常来模拟 Webhook 失败
        mock_service.get_state.side_effect = Exception("Webhook notification failed")

        # 添加到服务
        conversation_service._event_services[conversation_id] = mock_service

        # 模拟对象目录删除
        with patch(
            "openhands.agent_server.conversation_service.safe_rmtree"
        ) as mock_rmtree:
            mock_rmtree.return_value = True

            result = await conversation_service.delete_conversation(conversation_id)

            # 尽管 Webhook 失败，但仍应成功
            assert result is True
            assert conversation_id not in conversation_service._event_services

            # 验证事件服务仍然关闭
            mock_service.close.assert_called_once()

            # 验证目录是否仍被删除
            assert mock_rmtree.call_count == 1

    @pytest.mark.asyncio
    async def test_delete_conversation_close_failure(self, conversation_service):
        """当事件服务关闭失败时，测试 delete_conversation 继续。"""
        conversation_id = uuid4()

        # 创建模拟对象事件服务
        mock_service = AsyncMock(spec=EventService)
        mock_service.conversation_dir = "/tmp/test_conversation"
        mock_service.stored = StoredConversation(
            id=conversation_id,
            workspace=LocalWorkspace(working_dir="/tmp/test_workspace"),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
        )
        mock_state = ConversationState(
            id=conversation_id,
            agent=_sample_agent(),
            workspace=mock_service.stored.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=mock_service.stored.confirmation_policy,
        )
        mock_service.get_state.return_value = mock_state

        # 使关闭引发异常
        mock_service.close.side_effect = Exception("Close failed")

        # 添加到服务
        conversation_service._event_services[conversation_id] = mock_service

        # 模拟对象目录删除
        with patch(
            "openhands.agent_server.conversation_service.safe_rmtree"
        ) as mock_rmtree:
            mock_rmtree.return_value = True

            result = await conversation_service.delete_conversation(conversation_id)

            # 尽管失败了，但仍应该成功
            assert result is True
            assert conversation_id not in conversation_service._event_services

            # 验证目录是否仍被删除
            assert mock_rmtree.call_count == 1

    @pytest.mark.asyncio
    async def test_delete_conversation_retains_retryable_credential_close(
        self, conversation_service, tmp_path
    ):
        conversation_id = uuid4()
        conversation_dir = tmp_path / conversation_id.hex
        conversation_dir.mkdir()
        mock_service = AsyncMock(spec=EventService)
        mock_service.conversation_dir = conversation_dir
        mock_service.stored = StoredConversation(
            id=conversation_id,
            workspace=LocalWorkspace(working_dir=tmp_path / "workspace"),
            confirmation_policy=NeverConfirm(),
        )
        mock_service.get_state.return_value = ConversationState(
            id=conversation_id,
            agent=_sample_agent(),
            workspace=mock_service.stored.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=mock_service.stored.confirmation_policy,
        )
        mock_service.close.side_effect = CredentialSyncError("broker unavailable")
        binding = MagicMock()
        conversation_service._event_services[conversation_id] = mock_service
        conversation_service._conversation_records[conversation_id] = MagicMock()
        conversation_service._credential_bindings[conversation_id] = {
            "CODEX_AUTH_JSON": binding
        }

        with (
            patch(
                "openhands.agent_server.conversation_service.safe_rmtree"
            ) as mock_rmtree,
            pytest.raises(CredentialSyncError, match="broker unavailable"),
        ):
            await conversation_service.delete_conversation(conversation_id)

        assert conversation_service._event_services[conversation_id] is mock_service
        assert conversation_id in conversation_service._conversation_records
        assert conversation_service._credential_bindings[conversation_id] == {
            "CODEX_AUTH_JSON": binding
        }
        assert conversation_dir.exists()
        mock_rmtree.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_conversation_directory_removal_failure(
        self, conversation_service
    ):
        """即使目录删除失败，测试 delete_conversation 也会成功。"""
        conversation_id = uuid4()

        # 创建模拟对象事件服务
        mock_service = AsyncMock(spec=EventService)
        mock_service.conversation_dir = "/tmp/test_conversation"
        mock_service.stored = StoredConversation(
            id=conversation_id,
            workspace=LocalWorkspace(working_dir="/tmp/test_workspace"),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
        )
        mock_state = ConversationState(
            id=conversation_id,
            agent=_sample_agent(),
            workspace=mock_service.stored.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=mock_service.stored.confirmation_policy,
        )
        mock_service.get_state.return_value = mock_state

        # 添加到服务
        conversation_service._event_services[conversation_id] = mock_service

        # 模拟对象目录删除失败（模拟权限错误）
        with patch(
            "openhands.agent_server.conversation_service.safe_rmtree"
        ) as mock_rmtree:
            mock_rmtree.return_value = False  # 模拟移除失败

            result = await conversation_service.delete_conversation(conversation_id)

            # 应该仍然会成功 - 对话已从跟踪中删除
            assert result is True
            assert conversation_id not in conversation_service._event_services

            # 验证事件服务已关闭
            mock_service.close.assert_called_once()

            # 验证已尝试删除
            assert mock_rmtree.call_count == 1


class TestSafeRmtree:
    """测试用例用于 _safe_rmtree 辅助函数。"""

    def test_safe_rmtree_nonexistent_path(self):
        """使用不存在的路径测试 _safe_rmtree。"""
        result = _safe_rmtree("/nonexistent/path", "test directory")
        assert result is True

    def test_safe_rmtree_empty_path(self):
        """使用空路径测试 _safe_rmtree。"""
        result = _safe_rmtree("", "test directory")
        assert result is True

        result = _safe_rmtree(None, "test directory")
        assert result is True

    def test_safe_rmtree_success(self):
        """测试成功的目录删除。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test_subdir"
            test_dir.mkdir()

            # 创建测试文件
            test_file = test_dir / "test.txt"
            test_file.write_text("test content")

            result = _safe_rmtree(str(test_dir), "test directory")
            assert result is True
            assert not test_dir.exists()

    def test_safe_rmtree_permission_error(self):
        """测试 _safe_rmtree 优雅地处理权限错误。"""
        with patch("shutil.rmtree") as mock_rmtree:
            mock_rmtree.side_effect = PermissionError("Permission denied")

            with patch("os.path.exists", return_value=True):
                result = _safe_rmtree("/test/path", "test directory")
                assert result is False

    def test_safe_rmtree_os_error(self):
        """测试 _safe_rmtree 优雅地处理操作系统错误。"""
        with patch("shutil.rmtree") as mock_rmtree:
            mock_rmtree.side_effect = OSError("OS error")

            with patch("os.path.exists", return_value=True):
                result = _safe_rmtree("/test/path", "test directory")
                assert result is False

    def test_safe_rmtree_unexpected_error(self):
        """测试 _safe_rmtree 优雅地处理意外错误。"""
        with patch("shutil.rmtree") as mock_rmtree:
            mock_rmtree.side_effect = ValueError("Unexpected error")

            with patch("os.path.exists", return_value=True):
                result = _safe_rmtree("/test/path", "test directory")
                assert result is False

    def test_safe_rmtree_readonly_file_handling(self):
        """测试 _safe_rmtree 处理只读个文件。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test_subdir"
            test_dir.mkdir()

            # 创建一个测试文件并将其设为只读
            test_file = test_dir / "readonly.txt"
            test_file.write_text("readonly content")
            test_file.chmod(0o444)  # 只读

            result = _safe_rmtree(str(test_dir), "test directory")
            assert result is True
            assert not test_dir.exists()


class TestAutoTitle:
    """测试 AutoTitleSubscriber。"""

    _GENERATE_TITLE_PATH = (
        "openhands.agent_server.conversation_service.generate_title_from_message"
    )
    _TITLE_WITH_LLM_PATH = (
        "openhands.sdk.conversation.title_utils.generate_title_with_llm"
    )

    def _make_service(
        self,
        title: str | None = None,
        title_llm_profile: str | None = None,
        prompt: str | None = None,
        llm_model: str = "gpt-4o",
        llm_usage_id: str = "test-llm",
    ) -> AsyncMock:
        agent = Agent(llm=LLM(model=llm_model, usage_id=llm_usage_id), tools=[])
        stored = StoredConversation(
            id=uuid4(),
            workspace=LocalWorkspace(working_dir="workspace/project"),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
            title=title,
            title_llm_profile=title_llm_profile,
            prompt=prompt,
        )
        service = AsyncMock(spec=EventService)
        service.stored = stored
        _adopt_saved_meta(service)

        mock_conversation = MagicMock()
        mock_conversation.agent.llm = agent.llm
        service._conversation = mock_conversation
        return service

    def _user_message_event(self, text: str = "Fix the login bug") -> MessageEvent:
        from openhands.sdk.llm.message import TextContent

        return MessageEvent(
            id="evt-1",
            source="user",
            llm_message=Message(role="user", content=[TextContent(text=text)]),
        )

    @staticmethod
    async def _drain_title_task(
        predicate=lambda: True, max_iterations: int = 50, step: float = 0.02
    ) -> None:
        """屈服于事件循环，直到后台标题任务完成。

        `AutoTitleSubscriber` 通过 `run_in_executor` 调度生成，因此单个
        `await asyncio.sleep(0)`
        不足以让执行器线程完成。 进行短暂睡眠的轮询，直到 `predicate()` 变为 true 或
        超时过去。
        """
        for _ in range(max_iterations):
            await asyncio.sleep(step)
            if predicate():
                return

    @pytest.mark.asyncio
    async def test_autotitle_sets_title_on_first_user_message(self):
        """当第一条用户消息到达时，标题被生成并保存。"""
        service = self._make_service()

        with patch(self._GENERATE_TITLE_PATH, return_value="✨ Generated Title"):
            subscriber = AutoTitleSubscriber(service=service)
            await subscriber(self._user_message_event())
            await self._drain_title_task(lambda: service.stored.title is not None)

        assert service.stored.title == "✨ Generated Title"
        service.save_meta.assert_called_once()

    @pytest.mark.asyncio
    async def test_autotitle_passes_custom_prompt_to_title_generation(self):
        service = self._make_service(prompt="Use {conversation_content} as the title.")

        with patch(
            self._GENERATE_TITLE_PATH, return_value="Fix the login bug"
        ) as mock_generate_title:
            subscriber = AutoTitleSubscriber(service=service)
            await subscriber(self._user_message_event())
            await self._drain_title_task(lambda: service.stored.title is not None)

        assert mock_generate_title.call_args.kwargs["prompt"] == (
            "Use {conversation_content} as the title."
        )

    async def test_autotitle_refused_save_leaves_title_unset(self):
        """保存被拒绝（失去所有权）的标题永远不会可见。"""
        service = self._make_service()
        service.save_meta.side_effect = ConversationOwnershipLostError(
            conversation_dir=Path("conv"), owner_instance_id="stale", generation=1
        )

        with patch(self._GENERATE_TITLE_PATH, return_value="Refused Title"):
            subscriber = AutoTitleSubscriber(service=service)
            await subscriber(self._user_message_event())
            await self._drain_title_task(lambda: service.save_meta.called)

        service.save_meta.assert_called_once()
        assert service.stored.title is None

    @pytest.mark.asyncio
    async def test_autotitle_skips_non_user_events(self):
        """非用户事件不会触发标题生成。

        涵盖ConversationStateUpdateEvent和助手MessageEvents。
        """
        service = self._make_service()
        subscriber = AutoTitleSubscriber(service=service)

        # ConversationStateUpdateEvent 应被忽略
        await subscriber(
            ConversationStateUpdateEvent(key="execution_status", value="IDLE")
        )
        # 助理 MessageEvent 应被忽略
        await subscriber(
            MessageEvent(
                id="evt-2", source="agent", llm_message=Message(role="assistant")
            )
        )

        await asyncio.sleep(0)
        assert service.stored.title is None

    @pytest.mark.asyncio
    async def test_autotitle_skips_when_title_already_set(self):
        """当对话已有标题时，不会进行 LLM 呼叫。"""
        service = self._make_service(title="Existing Title")
        subscriber = AutoTitleSubscriber(service=service)

        with patch(self._GENERATE_TITLE_PATH) as mock_generate_title:
            await subscriber(self._user_message_event())
            await asyncio.sleep(0)
            mock_generate_title.assert_not_called()

        assert service.stored.title == "Existing Title"

    @pytest.mark.asyncio
    async def test_autotitle_handles_generate_title_failure(self):
        """失败的标题生成将被记录为警告并且不会重新引发。"""
        service = self._make_service()

        with patch(self._GENERATE_TITLE_PATH, side_effect=Exception("LLM unavailable")):
            subscriber = AutoTitleSubscriber(service=service)
            # 不应该提高
            await subscriber(self._user_message_event())
            await asyncio.sleep(0)

        # 标题仍未设置； save_meta 从未被调用过
        assert service.stored.title is None
        service.save_meta.assert_not_called()

    @pytest.mark.asyncio
    async def test_autotitle_surfaces_llm_error_to_ui(self):
        """当 title LLM 调用失败时，错误将通过以下方式呈现给 UI
        EventService 错误事件助手（问题#16686）——而自动标题保持非致命并回退到截断。
        """
        service = self._make_service()

        # 让真正的title utils运行起来； 只有 LLM 调用失败，因此错误被包含在回退方案标题
        # 中并通过 on_error 报告。
        #
        with patch(
            "openhands.sdk.llm.llm.LLM.completion",
            side_effect=Exception("model does not exist"),
        ):
            subscriber = AutoTitleSubscriber(service=service)
            await subscriber(self._user_message_event())
            await self._drain_title_task(
                lambda: service._publish_error_event_sync.called
            )

        service._publish_error_event_sync.assert_called_once()
        (exc,) = service._publish_error_event_sync.call_args.args
        assert str(exc) == "model does not exist"

    @pytest.mark.asyncio
    async def test_autotitle_skips_empty_message(self):
        """如果用户消息没有文本内容，则不会生成标题。"""
        service = self._make_service()
        event = MessageEvent(
            id="evt-1", source="user", llm_message=Message(role="user")
        )

        with patch(self._GENERATE_TITLE_PATH) as mock_generate_title:
            subscriber = AutoTitleSubscriber(service=service)
            await subscriber(event)
            await asyncio.sleep(0)
            mock_generate_title.assert_not_called()

        assert service.stored.title is None

    @pytest.mark.asyncio
    async def test_autotitle_uses_llm_profile_when_configured(self):
        """配置后，配置文件 LLM 优先于 agent.llm。"""
        service = self._make_service(title_llm_profile="cheap-model")
        mock_llm = LLM(model="gpt-3.5-turbo", usage_id="title-llm")

        with (
            patch(
                "openhands.agent_server.persistence.store.get_llm_profile_store"
            ) as MockStore,
            patch(
                self._GENERATE_TITLE_PATH, return_value="✨ Profile LLM Title"
            ) as mock_generate_title,
        ):
            mock_store_instance = MockStore.return_value
            mock_store_instance.load.return_value = mock_llm

            subscriber = AutoTitleSubscriber(service=service)
            await subscriber(self._user_message_event())
            await self._drain_title_task(lambda: service.stored.title is not None)

            MockStore.assert_called_once_with()
            mock_store_instance.load.assert_called_once_with(
                "cheap-model", cipher=service.cipher
            )
            # 配置文件加载 LLM 战胜 agent.llm
            assert mock_generate_title.called
            assert mock_generate_title.call_args.args[1] is mock_llm

        assert service.stored.title == "✨ Profile LLM Title"
        service.save_meta.assert_called_once()

    @pytest.mark.asyncio
    async def test_autotitle_falls_back_to_agent_llm_when_profile_not_found(self):
        """缺少配置文件 → 回退到 agent.llm（非中断行为）。"""
        service = self._make_service(title_llm_profile="nonexistent-profile")
        agent_llm = service._conversation.agent.llm

        with (
            patch(
                "openhands.agent_server.persistence.store.get_llm_profile_store"
            ) as MockStore,
            patch(
                self._GENERATE_TITLE_PATH, return_value="✨ Agent LLM Title"
            ) as mock_generate_title,
        ):
            mock_store_instance = MockStore.return_value
            mock_store_instance.load.side_effect = FileNotFoundError(
                "Profile 'nonexistent-profile' not found"
            )

            subscriber = AutoTitleSubscriber(service=service)
            await subscriber(self._user_message_event())
            await self._drain_title_task(lambda: service.stored.title is not None)

            # 配置文件加载失败 → 回退到 agent.llm
            assert mock_generate_title.called
            assert mock_generate_title.call_args.args[1] is agent_llm

        assert service.stored.title == "✨ Agent LLM Title"
        service.save_meta.assert_called_once()

    @pytest.mark.asyncio
    async def test_autotitle_no_profile_uses_agent_llm(self):
        """未配置配置文件 → 使用 agent.llm（保留现有行为）。"""
        service = self._make_service(title_llm_profile=None)
        agent_llm = service._conversation.agent.llm

        with patch(
            self._GENERATE_TITLE_PATH, return_value="✨ Agent LLM Title"
        ) as mock_generate_title:
            subscriber = AutoTitleSubscriber(service=service)
            await subscriber(self._user_message_event())
            await self._drain_title_task(lambda: service.stored.title is not None)

            # 没有配置文件→使用agent.llm（向后兼容）
            assert mock_generate_title.called
            assert mock_generate_title.call_args.args[1] is agent_llm

        assert service.stored.title == "✨ Agent LLM Title"
        service.save_meta.assert_called_once()

    @pytest.mark.asyncio
    async def test_autotitle_handles_profile_load_value_error(self):
        """配置文件加载 ValueError → 回落到 agent.llm。"""
        service = self._make_service(title_llm_profile="corrupted-profile")
        agent_llm = service._conversation.agent.llm

        with (
            patch(
                "openhands.agent_server.persistence.store.get_llm_profile_store"
            ) as MockStore,
            patch(
                self._GENERATE_TITLE_PATH, return_value="✨ Agent LLM Title"
            ) as mock_generate_title,
        ):
            mock_store_instance = MockStore.return_value
            mock_store_instance.load.side_effect = ValueError("Invalid profile format")

            subscriber = AutoTitleSubscriber(service=service)
            await subscriber(self._user_message_event())
            await self._drain_title_task(lambda: service.stored.title is not None)

            assert mock_generate_title.called
            assert mock_generate_title.call_args.args[1] is agent_llm

        assert service.stored.title == "✨ Agent LLM Title"
        service.save_meta.assert_called_once()

    @pytest.mark.asyncio
    async def test_autotitle_falls_back_for_acp_managed_llm(self):
        """ACP 管理智能体，无标题配置文件 → 截断回退方案。"""
        service = self._make_service(llm_usage_id="acp-managed")
        subscriber = AutoTitleSubscriber(service=service)

        await subscriber(self._user_message_event("Fix the login bug"))
        await self._drain_title_task(lambda: service.stored.title is not None)

        assert service.stored.title == "Fix the login bug"
        service.save_meta.assert_called_once()

    @pytest.mark.asyncio
    async def test_autotitle_skips_llm_for_settings_built_acp_agent(self):
        service = self._make_service()
        acp_agent = ACPAgentSettings(acp_model="claude-opus-4-7").create_agent()
        service._conversation.agent.llm = acp_agent.llm

        with patch(self._TITLE_WITH_LLM_PATH) as mock_llm_title:
            subscriber = AutoTitleSubscriber(service=service)
            await subscriber(self._user_message_event("Fix the login bug"))
            await self._drain_title_task(lambda: service.stored.title is not None)

        mock_llm_title.assert_not_called()
        assert service.stored.title == "Fix the login bug"

    @pytest.mark.asyncio
    async def test_autotitle_uses_title_profile_for_settings_built_acp_agent(self):
        service = self._make_service(title_llm_profile="cheap-model")
        service._conversation.agent.llm = ACPAgentSettings().create_agent().llm
        profile_llm = LLM(model="gpt-3.5-turbo", usage_id="title-llm")

        with (
            patch(
                "openhands.agent_server.persistence.store.get_llm_profile_store"
            ) as MockStore,
            patch(
                self._TITLE_WITH_LLM_PATH, return_value="Profile Title"
            ) as mock_llm_title,
        ):
            MockStore.return_value.load.return_value = profile_llm
            subscriber = AutoTitleSubscriber(service=service)
            await subscriber(self._user_message_event())
            await self._drain_title_task(lambda: service.stored.title is not None)

        assert mock_llm_title.call_args.args[1] is profile_llm
        assert service.stored.title == "Profile Title"

    @pytest.mark.asyncio
    async def test_autotitle_integration_routes_through_profile_store(
        self, tmp_path, monkeypatch, request
    ):
        """端到端：磁盘上的配置文件 → LLMProfileStore.load → 标题 LLM 调用。

        测试实际的接线 AutoTitleSubscriber 通过 LLMProfileStore to LLM.generate. 仅通
        用调用边界（
        LLM.generate) is 模拟的因此，这能捕获加载性能图时的回归 LLM passthrough, and
        the 智能体-server SDK 集
        成 ——  单元测试仅锻炼以上内容 AutoTitleSubscriber 在孤立状态下。
        """
        from litellm.types.utils import (
            Choices,
            Message as LiteLLMMessage,
            ModelResponse,
            Usage,
        )

        from openhands.sdk.llm import LLMResponse, MetricsSnapshot
        from openhands.sdk.llm.llm_profile_store import LLMProfileStore

        # 持久化一个真实的 LLM 配置文件到磁盘，具有独特的 usage_id，因此我们可以将断言中
        # 的标题 LLM 与智能体的 LLM 区分开来。
        #
        profile_dir = tmp_path / "profiles"
        title_llm_on_disk = LLM(
            usage_id="title-llm",
            model="claude-haiku-4-5",
            api_key=SecretStr("title-key"),
        )
        LLMProfileStore(base_dir=profile_dir).save(
            "title-fast", title_llm_on_disk, include_secrets=True
        )

        service = self._make_service(title_llm_profile="title-fast")

        calls: list[str] = []

        def fake_generate(self_llm, _messages, **_kwargs):
            calls.append(self_llm.usage_id)
            msg = LiteLLMMessage(content="✨ Generated", role="assistant")
            choice = Choices(finish_reason="stop", index=0, message=msg)
            raw = ModelResponse(
                id="resp-1",
                choices=[choice],
                created=0,
                model=self_llm.model,
                object="chat.completion",
                usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )
            return LLMResponse(
                message=Message.from_llm_chat_message(choice["message"]),
                metrics=MetricsSnapshot(
                    model_name=self_llm.model,
                    accumulated_cost=0.0,
                    max_budget_per_task=None,
                    accumulated_token_usage=None,
                ),
                raw_response=raw,
            )

        # 通过 OH_PERSISTENCE_DIR 将智能体-服务器配置文件存储单例指向我们的 tmp 目录，以
        # 便真正的 _load_title_llm 代码路径在 `{tmp_path}/profiles` 下找到我们的磁盘配置
        # 文件。
        #
        from openhands.agent_server.persistence import reset_stores

        monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path))
        reset_stores()
        # 即使引发断言，也会在拆卸时清除单例，因此过时的存储（指向即将删除的 tmp_path）
        # 不会泄漏。
        #
        request.addfinalizer(reset_stores)

        with patch(
            "openhands.sdk.llm.llm.LLM.generate",
            autospec=True,
            side_effect=fake_generate,
        ):
            subscriber = AutoTitleSubscriber(service=service)
            await subscriber(self._user_message_event("Fix the login bug"))
            # 等待后台执行器任务完成。 生产代码使用 run_in_executor，因此 sleep(0) 不够
            # 。
            #
            for _ in range(50):
                await asyncio.sleep(0.02)
                if service.stored.title is not None:
                    break

        # 配置文件的 LLM (usage_id="title-llm") 被调用，而不是 agent.llm (usage_id="test
        # -llm")。 这是回归敏感的断言。
        #
        assert calls == ["title-llm"], (
            f"Expected only the title profile LLM to be called, got: {calls}"
        )
        assert service.stored.title == "✨ Generated"
        service.save_meta.assert_called_once()

    @pytest.mark.asyncio
    async def test_autotitle_decrypts_cipher_encrypted_title_profile(
        self, tmp_path, monkeypatch, request
    ):
        """回归对于 #3164：密码加密的 title-LLM 配置文件必须是
        在加载时解密，因此标题 LLM 看到的是明文 API 密钥，而不是 Fernet 密文。
        """
        from litellm.types.utils import (
            Choices,
            Message as LiteLLMMessage,
            ModelResponse,
            Usage,
        )

        from openhands.sdk.llm import LLMResponse, MetricsSnapshot
        from openhands.sdk.llm.llm_profile_store import LLMProfileStore
        from openhands.sdk.utils.cipher import Cipher

        cipher = Cipher("title-cipher-test-key")

        profile_dir = tmp_path / "profiles"
        LLMProfileStore(base_dir=profile_dir).save(
            "title-encrypted",
            LLM(
                usage_id="title-llm",
                model="claude-haiku-4-5",
                api_key=SecretStr("plaintext-title-key"),
            ),
            include_secrets=True,
            cipher=cipher,
        )

        service = self._make_service(title_llm_profile="title-encrypted")
        # 注入密码； AutoTitleSubscriber通过service.cipher读取它。
        service.cipher = cipher

        seen_keys: list[str] = []

        def fake_generate(self_llm, _messages, **_kwargs):
            seen_keys.append(
                self_llm.api_key.get_secret_value() if self_llm.api_key else ""
            )
            msg = LiteLLMMessage(content="✨ Generated", role="assistant")
            choice = Choices(finish_reason="stop", index=0, message=msg)
            raw = ModelResponse(
                id="resp-1",
                choices=[choice],
                created=0,
                model=self_llm.model,
                object="chat.completion",
                usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )
            return LLMResponse(
                message=Message.from_llm_chat_message(choice["message"]),
                metrics=MetricsSnapshot(
                    model_name=self_llm.model,
                    accumulated_cost=0.0,
                    max_budget_per_task=None,
                    accumulated_token_usage=None,
                ),
                raw_response=raw,
            )

        from openhands.agent_server.persistence import reset_stores

        monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path))
        reset_stores()
        # 即使引发断言，也会在拆卸时清除单例，因此过时的存储（指向即将删除的 tmp_path）
        # 不会泄漏。
        #
        request.addfinalizer(reset_stores)

        with patch(
            "openhands.sdk.llm.llm.LLM.generate",
            autospec=True,
            side_effect=fake_generate,
        ):
            subscriber = AutoTitleSubscriber(service=service)
            await subscriber(self._user_message_event("Fix the login bug"))
            for _ in range(50):
                await asyncio.sleep(0.02)
                if service.stored.title is not None:
                    break

        assert seen_keys == ["plaintext-title-key"], (
            f"Expected title LLM to receive decrypted key, got: {seen_keys}"
        )


class TestACPActivityHeartbeatWiring:
    """测试 EventService 中的 _setup_acp_activity_heartbeat。"""

    def test_acp_agent_gets_on_activity_wired(self):
        """_setup_acp_activity_heartbeat 应该设置 _on_activity 在 ACPAgent。"""
        from openhands.agent_server.event_service import EventService
        from openhands.agent_server.server_details_router import (
            update_last_execution_time,
        )

        service = AsyncMock(spec=EventService)
        # 调用真实方法
        agent = ACPAgent(acp_command=["echo", "test"])
        assert agent._on_activity is None

        EventService._setup_acp_activity_heartbeat(service, agent)

        assert agent._on_activity is update_last_execution_time

    def test_non_acp_agent_unchanged(self):
        """_setup_acp_activity_heartbeat 对于非 ACP 智能体是无操作。"""
        from openhands.agent_server.event_service import EventService

        service = AsyncMock(spec=EventService)
        agent = Agent(llm=LLM(model="test-model"))

        # 不应引发也不应设置任何属性
        EventService._setup_acp_activity_heartbeat(service, agent)
        assert not hasattr(agent, "_on_activity")


@pytest.mark.asyncio
async def test_refresh_persisted_conversation_adds_and_removes_record(
    tmp_path, sample_stored_conversation
):
    conversations_dir = tmp_path / "conversations"
    async with ConversationService(conversations_dir=conversations_dir) as service:
        assert (await service.search_conversations()).items == []

        conversation_dir = conversations_dir / sample_stored_conversation.id.hex
        conversation_dir.mkdir(parents=True)
        (conversation_dir / "meta.json").write_text(
            sample_stored_conversation.model_dump_json()
        )
        state = ConversationState(
            id=sample_stored_conversation.id,
            agent=_sample_agent(),
            workspace=sample_stored_conversation.workspace,
            persistence_dir=str(conversations_dir),
        )
        (conversation_dir / "base_state.json").write_text(state.model_dump_json())

        await service.refresh_persisted_conversation(sample_stored_conversation.id)
        info = await service.get_conversation(sample_stored_conversation.id)
        page = await service.search_conversations()
        (conversation_dir / "meta.json").unlink()
        await service.refresh_persisted_conversation(sample_stored_conversation.id)
        removed = await service.get_conversation(sample_stored_conversation.id)

    assert info is not None
    assert info.id == sample_stored_conversation.id
    assert [item.id for item in page.items] == [sample_stored_conversation.id]
    assert removed is None


def _branch_events(conversation) -> list:
    """记录不包括异步 ``ConversationStateUpdateEvent`` 工件的事件。

    这些状态同步工件会异步附加到日志 (``EventService._emit_event_from_thread``)，因此
    它们的位置在
    ``_state.events``相对于同步消息附加是活泼的。 过滤它们可以使下面的 fork/navigate
    断言的位置索引和长度不变量保持确定性。
    """
    return [
        e
        for e in conversation._state.events
        if not isinstance(e, ConversationStateUpdateEvent)
    ]


class TestConversationTreeForkAndNavigate:
    """事件沿袭和导航的分叉服务级别覆盖范围。"""

    async def _start_with_events(self, svc, workspace_dir, texts):
        """开始对话并附加 ``texts`` 作为用户消息（不运行）。"""
        from openhands.sdk.testing import TestLLM
        from tests.agent_server.stress.scripts import (
            start_conversation_with_test_llm,
        )

        parent_llm = TestLLM(
            usage_id="test-llm",
            model="openai/gpt-4o",
            api_key=SecretStr("unused"),
        )
        info = await start_conversation_with_test_llm(
            svc,
            parent_llm=parent_llm,
            workspace_dir=str(workspace_dir),
            usage_id="test-llm",
            initial_text=texts[0],
        )
        event_service = await svc.get_event_service(info.id)
        assert event_service is not None
        for text in texts[1:]:
            await event_service.send_message(
                Message(role="user", content=[TextContent(text=text)]),
                run=False,
            )
        events = _branch_events(event_service.get_conversation())
        return info, event_service, events

    @pytest.mark.asyncio
    async def test_fork_from_event_slices_branch_and_records_lineage(self, tmp_path):
        """fork(from_event_id) 仅复制分支并标记血统。"""
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        async with ConversationService(
            conversations_dir=tmp_path / "conversations"
        ) as svc:
            info, source_service, events = await self._start_with_events(
                svc, workspace_dir, ["first", "second", "third"]
            )
            branch_point = next(e for e in events if isinstance(e, MessageEvent))
            expected_branch_ids = [
                e.id
                for e in source_service.get_conversation()._state.events.path_to_root(
                    branch_point.id
                )
            ]

            fork_info = await svc.fork_conversation(
                info.id, from_event_id=branch_point.id
            )

            assert fork_info is not None
            assert fork_info.forked_from_conversation_id == info.id
            assert fork_info.forked_from_event_id == branch_point.id
            assert fork_info.leaf_event_id == branch_point.id
            # forked_from_conversation_id 必须 JSON-序列化与 ``id`` 具有相同的（虚线）形
            # 状，以便客户端可以通过网络将两者关联起来。
            #
            dumped = fork_info.model_dump(mode="json")
            assert dumped["forked_from_conversation_id"] == str(info.id)

            fork_service = await svc.get_event_service(fork_info.id)
            assert fork_service is not None
            fork_events = _branch_events(fork_service.get_conversation())
            # 仅复制 path_to_root(branch_point) — 直到分支点（包括分支点）的活动分支，而
            # 不是整个日志。
            #
            assert [e.id for e in fork_events] == expected_branch_ids
            assert len(fork_events) < len(events)

            # 源未受到分叉的影响。
            src_events = _branch_events(source_service.get_conversation())
            assert len(src_events) == len(events)

    @pytest.mark.asyncio
    async def test_whole_conversation_fork_has_no_branch_point(self, tmp_path):
        """fork() 没有 from_event_id 复制所有内容； 谱系事件是None。"""
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        async with ConversationService(
            conversations_dir=tmp_path / "conversations"
        ) as svc:
            info, _, events = await self._start_with_events(
                svc, workspace_dir, ["first", "second"]
            )

            fork_info = await svc.fork_conversation(info.id)

            assert fork_info is not None
            assert fork_info.forked_from_conversation_id == info.id
            assert fork_info.forked_from_event_id is None
            fork_service = await svc.get_event_service(fork_info.id)
            assert fork_service is not None
            fork_events = _branch_events(fork_service.get_conversation())
            assert len(fork_events) == len(events)

    @pytest.mark.asyncio
    async def test_fork_unknown_event_raises_without_leaking_dir(self, tmp_path):
        """fork(from_event_id) 具有未知的 id 会引发并且不留下任何孤立目录。"""
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        conversations_dir = tmp_path / "conversations"
        async with ConversationService(conversations_dir=conversations_dir) as svc:
            info, _, _ = await self._start_with_events(svc, workspace_dir, ["first"])
            before = {p.name for p in conversations_dir.iterdir()}
            with pytest.raises(ValueError, match="from_event_id"):
                await svc.fork_conversation(info.id, from_event_id="evt-missing")
            # 验证在将任何 fork 目录写入磁盘之前必须快速失败。
            assert {p.name for p in conversations_dir.iterdir()} == before

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "navigate_to_none", [False, True], ids=["to_event", "to_empty_tree"]
    )
    async def test_navigate_moves_head_in_place(self, tmp_path, navigate_to_none):
        """导航移动 HEAD（到事件或空树），不修剪任何事件。"""
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        async with ConversationService(
            conversations_dir=tmp_path / "conversations"
        ) as svc:
            info, event_service, events = await self._start_with_events(
                svc, workspace_dir, ["first", "second", "third"]
            )
            target = None if navigate_to_none else events[0].id

            nav_info = await svc.navigate_conversation(info.id, event_id=target)

            assert nav_info is not None
            assert nav_info.leaf_event_id == target
            # 所有分支都保留在磁盘上——没有任何分支被删除。
            assert len(_branch_events(event_service.get_conversation())) == len(events)

    @pytest.mark.asyncio
    async def test_navigate_unknown_event_raises(self, tmp_path):
        """导航到未知事件引发 ValueError。"""
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        async with ConversationService(
            conversations_dir=tmp_path / "conversations"
        ) as svc:
            info, _, _ = await self._start_with_events(svc, workspace_dir, ["first"])
            with pytest.raises(ValueError, match="event_id"):
                await svc.navigate_conversation(info.id, event_id="evt-missing")

    @pytest.mark.asyncio
    async def test_navigate_missing_conversation_returns_none(self, tmp_path):
        """导航未知对话返回 None（路由器映射到 404）。"""
        async with ConversationService(
            conversations_dir=tmp_path / "conversations"
        ) as svc:
            assert await svc.navigate_conversation(uuid4(), event_id=None) is None

    @pytest.mark.asyncio
    async def test_lineage_and_navigated_head_persist_across_restart(self, tmp_path):
        """分叉谱系 (meta.json) 和导航的 HEAD (base_state.json) 幸存
        服务器重新启动 - 导航故意跳过 save_meta 并依赖于对话状态自己的自动保存。
        """
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        conversations_dir = tmp_path / "conversations"

        async with ConversationService(conversations_dir=conversations_dir) as svc:
            info, _, events = await self._start_with_events(
                svc, workspace_dir, ["first", "second", "third"]
            )
            src_id = info.id
            branch_point = events[1].id
            target_leaf = events[0].id

            fork_info = await svc.fork_conversation(src_id, from_event_id=branch_point)
            assert fork_info is not None
            fork_id = fork_info.id
            await svc.navigate_conversation(src_id, event_id=target_leaf)

        # 同一目录上的新服务 = 进程重新启动。
        async with ConversationService(conversations_dir=conversations_dir) as svc2:
            reloaded_src = await svc2.get_conversation(src_id)
            reloaded_fork = await svc2.get_conversation(fork_id)

            assert reloaded_src is not None
            assert reloaded_src.leaf_event_id == target_leaf
            assert reloaded_fork is not None
            assert reloaded_fork.forked_from_conversation_id == src_id
            assert reloaded_fork.forked_from_event_id == branch_point


class TestConversationSearchScaling:
    """搜索/计数必须不得全扫描对话状态。

    回归覆盖 #3142，其中每个目录条目都调用 ``get_state()`` 以读取每个对话的一个枚举字
    段。
    """

    @staticmethod
    def _seed(conversations_dir: Path, count: int, workspace_dir: Path) -> list[UUID]:
        """将 ``count`` 个空闲对话直接写入磁盘。"""
        conversations_dir.mkdir(parents=True, exist_ok=True)
        ids = []
        for i in range(count):
            conversation_id = uuid4()
            target = conversations_dir / conversation_id.hex
            target.mkdir()
            stored = StoredConversation(
                id=conversation_id,
                workspace=LocalWorkspace(working_dir=str(workspace_dir)),
                confirmation_policy=NeverConfirm(),
            )
            stored.created_at = datetime(2026, 1, 1, tzinfo=UTC).replace(microsecond=i)
            stored.updated_at = stored.created_at
            (target / "meta.json").write_text(stored.model_dump_json())
            state = ConversationState(
                id=conversation_id,
                agent=_sample_agent(),
                workspace=stored.workspace,
                persistence_dir=str(target),
            )
            (target / "base_state.json").write_text(state.model_dump_json())
            ids.append(conversation_id)
        return ids

    @pytest.mark.asyncio
    async def test_filtered_search_loads_state_only_for_the_page(self, tmp_path):
        """过滤后的页面加载页面项目的完整状态，而不是整个目录。"""
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        conversations_dir = tmp_path / "conversations"
        self._seed(conversations_dir, 40, workspace_dir)

        async with ConversationService(conversations_dir=conversations_dir) as svc:
            assert len(svc._conversation_records) == 40
            real_load = svc._load_persisted_state_sync
            loaded: list[UUID] = []

            def _tracking_load(conversation_id: UUID):
                loaded.append(conversation_id)
                return real_load(conversation_id)

            with patch.object(
                svc, "_load_persisted_state_sync", side_effect=_tracking_load
            ):
                page = await svc.search_conversations(
                    limit=5, execution_status=ConversationExecutionStatus.IDLE
                )

            assert len(page.items) == 5
            assert page.next_page_id is not None
            # 修复之前：40，每个对话一个完整状态负载。
            assert len(loaded) == 5, (
                f"expected 5 full state loads (the page), got {len(loaded)}"
            )

    @pytest.mark.asyncio
    async def test_filtered_count_loads_no_state(self, tmp_path):
        """按状态计数不得加载任何完整的对话状态。"""
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        conversations_dir = tmp_path / "conversations"
        self._seed(conversations_dir, 25, workspace_dir)

        async with ConversationService(conversations_dir=conversations_dir) as svc:
            with patch.object(
                svc, "_load_persisted_state_sync", side_effect=AssertionError
            ):
                idle = await svc.count_conversations(
                    execution_status=ConversationExecutionStatus.IDLE
                )
                running = await svc.count_conversations(
                    execution_status=ConversationExecutionStatus.RUNNING
                )
                total = await svc.count_conversations()

            assert idle == 25
            assert running == 0
            assert total == 25

    @pytest.mark.asyncio
    async def test_status_index_picks_up_on_disk_changes(self, tmp_path):
        """当base_state.json改变时，缓存状态失效。"""
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        conversations_dir = tmp_path / "conversations"
        ids = self._seed(conversations_dir, 3, workspace_dir)

        async with ConversationService(conversations_dir=conversations_dir) as svc:
            assert (
                await svc.count_conversations(
                    execution_status=ConversationExecutionStatus.FINISHED
                )
                == 0
            )

            # 模拟另一个进程完成一次对话。
            base_state = conversations_dir / ids[0].hex / "base_state.json"
            payload = json.loads(base_state.read_text())
            payload["execution_status"] = ConversationExecutionStatus.FINISHED.value
            # 大小也会改变，因此测试不依赖于 mtime 粒度。
            #
            payload["max_iterations"] = 1234567
            base_state.write_text(json.dumps(payload))

            assert (
                await svc.count_conversations(
                    execution_status=ConversationExecutionStatus.FINISHED
                )
                == 1
            )
            page = await svc.search_conversations(
                execution_status=ConversationExecutionStatus.FINISHED
            )
            assert [item.id for item in page.items] == [ids[0]]
            assert (
                await svc.count_conversations(
                    execution_status=ConversationExecutionStatus.IDLE
                )
                == 2
            )

    @pytest.mark.asyncio
    async def test_live_conversation_status_is_read_from_memory(self, tmp_path):
        """实时对话从内存状态回答过滤器。"""
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        conversations_dir = tmp_path / "conversations"
        self._seed(conversations_dir, 5, workspace_dir)

        request = StartConversationRequest(
            agent=Agent(llm=LLM(model="gpt-4o", usage_id="live-llm"), tools=[]),
            workspace=LocalWorkspace(working_dir=str(workspace_dir)),
            confirmation_policy=NeverConfirm(),
        )
        async with ConversationService(conversations_dir=conversations_dir) as svc:
            live, _ = await svc.start_conversation(request)
            assert svc._event_services is not None
            event_service = svc._event_services[live.id]

            # 翻转实时状态而不接触磁盘。
            state = await event_service.get_state()
            with state:
                state.execution_status = ConversationExecutionStatus.RUNNING

            assert (
                await svc.count_conversations(
                    execution_status=ConversationExecutionStatus.RUNNING
                )
                == 1
            )
            page = await svc.search_conversations(
                execution_status=ConversationExecutionStatus.RUNNING
            )
            assert [item.id for item in page.items] == [live.id]
            assert (
                await svc.count_conversations(
                    execution_status=ConversationExecutionStatus.IDLE
                )
                == 5
            )

    @pytest.mark.asyncio
    async def test_filtered_search_sees_records_replaced_during_refresh(self, tmp_path):
        """筛选的搜索必须先刷新，然后才能对目录进行快照。

        刷新期间进行的对话会用权威的内存状态替换其记录。 首先，快照将过滤被取代的对象
        并从页面中删除对话。
        """
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        conversations_dir = tmp_path / "conversations"
        self._seed(conversations_dir, 3, workspace_dir)

        async with ConversationService(conversations_dir=conversations_dir) as svc:
            target = next(iter(svc._conversation_records))
            real_refresh = svc._refresh_execution_statuses

            async def refresh_then_replace():
                await real_refresh()
                # 代表 _start_event_service 交换新记录
                # while the refresh awaited.
                old = svc._conversation_records[target]
                svc._conversation_records[target] = _ConversationRecord(
                    stored=old.stored,
                    execution_status=ConversationExecutionStatus.RUNNING,
                )

            with patch.object(svc, "_refresh_execution_statuses", refresh_then_replace):
                page = await svc.search_conversations(
                    execution_status=ConversationExecutionStatus.RUNNING
                )

            assert [item.id for item in page.items] == [target]


@pytest.mark.asyncio
async def test_search_composes_conversation_info_off_event_loop(persisted_conversation):
    """Regression: 在列表/搜索期间编写 ConversationInfo 不得运行
    在事件循环线程上。

    ``_compose_conversation_info`` 中的重型 Pydantic 构造（及其大型嵌套对象图）用于在
    单个 asyncio 事件循环线程上同步执
    行。 在负载下，这会导致长时间的阻塞 GC 暂停，从而拖延每个请求（异步和执行程序支持
    的请求）——这是生产中看到的楔子。 将其卸载给工作人员线程可以使 GC/分配脱
    离循环。

    此测试通过 ``search_conversations`` 加载已持久化（空闲）对话，并断言组合在线程而
    非事件循环上运行。
    """
    import threading
    from unittest.mock import patch as _patch

    conversations_dir, conversation_id = persisted_conversation
    original_compose = _compose_conversation_info

    loop_ident = threading.get_ident()
    found = {}

    def spy(stored, state, children):
        found["thread_ident"] = threading.get_ident()
        return original_compose(stored, state, children)

    async with ConversationService(conversations_dir=conversations_dir) as restarted:
        assert restarted._event_services == {}
        with _patch(
            "openhands.agent_server.conversation_service._compose_conversation_info",
            side_effect=spy,
        ) as comp:
            page = await restarted.search_conversations()
            assert [item.id for item in page.items] == [conversation_id]
            assert comp.call_count >= 1

    # 证明在事件循环上执行的合成。
    assert found.get("thread_ident") is not None
    assert found["thread_ident"] != loop_ident


@pytest.mark.asyncio
async def test_search_reuses_persisted_conversation_info_until_state_changes(
    persisted_conversation,
):
    """重复的侧边栏民意调查不应重新解析不变base_state.json。"""
    conversations_dir, conversation_id = persisted_conversation
    async with ConversationService(conversations_dir=conversations_dir) as service:
        real_load = service._load_persisted_state_sync
        with patch.object(
            service, "_load_persisted_state_sync", wraps=real_load
        ) as load:
            first = await service.search_conversations()
            second = await service.search_conversations()

        assert [item.id for item in first.items] == [conversation_id]
        assert [item.id for item in second.items] == [conversation_id]
        assert load.call_count == 1


@pytest.mark.asyncio
async def test_search_invalidates_cached_info_when_state_file_changes(
    persisted_conversation,
):
    conversations_dir, conversation_id = persisted_conversation
    async with ConversationService(conversations_dir=conversations_dir) as service:
        first = await service.search_conversations()
        base_state = conversations_dir / conversation_id.hex / "base_state.json"
        payload = json.loads(base_state.read_text())
        payload["execution_status"] = ConversationExecutionStatus.FINISHED.value
        # 更改大小和运行时间，以便每个 FS 上的签名都会更改。
        payload["max_iterations"] = 1234567
        base_state.write_text(json.dumps(payload))

        second = await service.search_conversations()

    assert first.items[0].execution_status != ConversationExecutionStatus.FINISHED
    assert second.items[0].execution_status == ConversationExecutionStatus.FINISHED


@pytest.mark.asyncio
async def test_search_live_conversation_does_not_wait_for_state_lock(tmp_path):
    """侧边栏列表不得挡在实时智能体的长步骤锁后面。"""
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )

    async with ConversationService(conversations_dir=conversations_dir) as service:
        conversation_info, _ = await service.start_conversation(request)
        event_services = service._event_services
        assert event_services is not None
        live_state = await event_services[conversation_info.id].get_state()

        # 保持 FIFOLock 和 LocalConversation.arun() 在一个原生 OpenHands 智能体步骤中的
        # 相同。 由活状态和被阻塞的旧列表路径，直到锁发布。
        #
        acquired = threading.Event()
        release = threading.Event()

        def hold_state_lock():
            with live_state:
                acquired.set()
                assert release.wait(timeout=5)

        holder = threading.Thread(target=hold_state_lock)
        holder.start()
        assert acquired.wait(timeout=2)
        try:
            page = await asyncio.wait_for(service.search_conversations(), timeout=1)
        finally:
            release.set()
            holder.join(timeout=2)

    assert [item.id for item in page.items] == [conversation_info.id]


@pytest.mark.asyncio
async def test_refresh_persisted_conversation_updates_metadata_without_state_change(
    persisted_conversation,
):
    conversations_dir, conversation_id = persisted_conversation
    directory = conversations_dir / conversation_id.hex
    async with ConversationService(conversations_dir=conversations_dir) as service:
        initial = await service.search_conversations()
        assert initial.items[0].title is None
        state_before = (directory / "base_state.json").read_bytes()
        metadata = json.loads((directory / "meta.json").read_text())
        metadata["title"] = "Generated externally"
        (directory / "meta.json").write_text(json.dumps(metadata))

        await service.refresh_persisted_conversation(conversation_id)
        info = await service.get_conversation(conversation_id)
        assert info is not None
        assert info.title == "Generated externally"
        assert (await service.search_conversations()).items[0].title == info.title
        assert (directory / "base_state.json").read_bytes() == state_before


@pytest.mark.asyncio
async def test_refresh_persisted_conversation_preserves_live_metadata(
    persisted_conversation,
):
    conversations_dir, conversation_id = persisted_conversation
    async with ConversationService(conversations_dir=conversations_dir) as service:
        runtime = await service.get_event_service(conversation_id)
        assert runtime is not None
        runtime.stored = runtime.stored.model_copy(update={"title": "Live title"})
        metadata_path = conversations_dir / conversation_id.hex / "meta.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["title"] = "Stale disk title"
        metadata_path.write_text(json.dumps(metadata))

        await service.refresh_persisted_conversation(conversation_id)
        info = await service.get_conversation(conversation_id)
        assert info is not None
        assert info.title == "Live title"
        assert (await service.search_conversations()).items[0].title == "Live title"
        assert await service.get_event_service(conversation_id) is runtime


@pytest.mark.asyncio
async def test_refresh_persisted_conversation_only_decrypts_requested_record(
    persisted_conversation,
):
    conversations_dir, conversation_id = persisted_conversation
    reads = []

    def cipher_for(cid):
        reads.append(cid)
        return Cipher("catalog-test-key")

    async with ConversationService(
        conversations_dir=conversations_dir,
        runtime_cipher_resolver=cipher_for,
    ) as service:
        unrelated = uuid4()
        directory = conversations_dir / unrelated.hex
        directory.mkdir()
        (directory / "meta.json").write_bytes(
            (conversations_dir / conversation_id.hex / "meta.json").read_bytes()
        )
        reads.clear()
        assert (await service.search_conversations()).items
        assert reads == [conversation_id]

        reads.clear()
        await service.refresh_persisted_conversation(conversation_id)
        assert reads == [conversation_id]
        assert await service.get_conversation(conversation_id) is not None
        assert reads == [conversation_id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enable_browser", "usable", "tools", "expected"),
    [
        (
            True,
            True,
            None,
            ["terminal", "file_editor", "task_tracker", "browser_tool_set"],
        ),
        (True, False, None, ["terminal", "file_editor", "task_tracker"]),
        (False, True, None, ["terminal", "file_editor", "task_tracker"]),
        (True, True, [{"name": "terminal"}], ["terminal"]),
        (
            True,
            True,
            [{"name": "browser_tool_set"}, {"name": "terminal"}],
            ["browser_tool_set", "terminal"],
        ),
        (
            True,
            False,
            [{"name": "terminal"}, {"name": "browser_tool_set"}],
            ["terminal"],
        ),
        (
            False,
            True,
            [{"name": "terminal"}, {"name": "browser_tool_set"}],
            ["terminal"],
        ),
    ],
)
async def test_settings_launch_resolves_tools_for_this_server(
    conversation_service, tmp_path, enable_browser, usable, tools, expected
):
    conversation_service.enable_browser = enable_browser
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    request = StartConversationRequest(
        agent_settings={
            "agent_kind": "openhands",
            "llm": {"model": "gpt-4o", "usage_id": "test-llm"},
            "tools": tools,
        },
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
    )
    captured: dict[str, Any] = {}

    async def fake_start_event_service(stored: StoredConversation, **kwargs):
        agent = kwargs["launched"].agent
        captured["agent"] = agent
        service = AsyncMock(spec=EventService)
        service.stored = stored
        service.get_state.return_value = ConversationState(
            id=stored.id,
            agent=agent,
            workspace=stored.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=stored.confirmation_policy,
        )
        return service

    with (
        patch(
            "openhands.agent_server.launch.is_tool_usable",
            return_value=usable,
        ),
        patch.object(
            conversation_service,
            "_start_event_service",
            side_effect=fake_start_event_service,
        ),
    ):
        await conversation_service.start_conversation(request)

    assert [t.name for t in captured["agent"].tools] == expected


async def test_explicit_agent_wins_over_agent_settings(conversation_service, tmp_path):
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    request = StartConversationRequest(
        agent=Agent(
            llm=LLM(model="gpt-4o", usage_id="test-llm"),
            tools=[Tool(name="terminal")],
        ),
        agent_settings={
            "agent_kind": "openhands",
            "llm": {"model": "gpt-4o", "usage_id": "test-llm"},
            "tools": [{"name": "file_editor"}],
        },
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
    )
    captured: dict[str, Any] = {}

    async def fake_start_event_service(stored: StoredConversation, **kwargs):
        agent = kwargs["launched"].agent
        captured["agent"] = agent
        service = AsyncMock(spec=EventService)
        service.stored = stored
        service.get_state.return_value = ConversationState(
            id=stored.id,
            agent=agent,
            workspace=stored.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=stored.confirmation_policy,
        )
        return service

    with patch.object(
        conversation_service,
        "_start_event_service",
        side_effect=fake_start_event_service,
    ):
        await conversation_service.start_conversation(request)

    assert [t.name for t in captured["agent"].tools] == ["terminal"]


@pytest.mark.asyncio
async def test_settings_launch_builds_the_agent_once(conversation_service, tmp_path):
    from openhands.sdk.settings import OpenHandsAgentSettings

    conversation_service.enable_browser = True
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    request = StartConversationRequest(
        agent_settings={
            "agent_kind": "openhands",
            "llm": {"model": "gpt-4o", "usage_id": "test-llm"},
        },
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
    )
    captured: dict[str, Any] = {}

    async def fake_start_event_service(stored: StoredConversation, **kwargs):
        agent = kwargs["launched"].agent
        captured["agent"] = agent
        service = AsyncMock(spec=EventService)
        service.stored = stored
        service.get_state.return_value = ConversationState(
            id=stored.id,
            agent=agent,
            workspace=stored.workspace,
            execution_status=ConversationExecutionStatus.IDLE,
            confirmation_policy=stored.confirmation_policy,
        )
        return service

    with (
        patch("openhands.agent_server.launch.is_tool_usable", return_value=True),
        patch.object(
            OpenHandsAgentSettings,
            "create_agent",
            autospec=True,
            side_effect=OpenHandsAgentSettings.create_agent,
        ) as create_agent,
        patch.object(
            conversation_service,
            "_start_event_service",
            side_effect=fake_start_event_service,
        ),
    ):
        await conversation_service.start_conversation(request)

    create_agent.assert_called_once()
    assert "browser_tool_set" in [t.name for t in captured["agent"].tools]
