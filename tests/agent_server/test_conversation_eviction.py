"""``ConversationService`` (OSS-1495) 中的空闲会话驱逐。"""

import asyncio
import time

import pytest

from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.models import StartConversationRequest
from openhands.agent_server.pub_sub import Subscriber
from openhands.sdk import LLM, Agent, Event
from openhands.sdk.credential import ResolvedCredential
from openhands.sdk.security.confirmation_policy import NeverConfirm
from openhands.sdk.workspace import LocalWorkspace


def _make_request(workspace_dir) -> StartConversationRequest:
    workspace_dir.mkdir()
    return StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )


class _DummySubscriber(Subscriber):
    """替代外部 (e.g. WebSocket)订户。"""

    async def __call__(self, event: Event) -> None:
        return None


class _FakeBinding:
    """最小 VersionedCredentialBinding 存根（仅检查其身份）。"""

    async def load(self) -> ResolvedCredential:
        return ResolvedCredential(value="v", version="1")

    async def replace(self, expected_version: str, value: str) -> str:
        return value


@pytest.mark.asyncio
async def test_eviction_task_started_only_when_configured(tmp_path):
    conversations_dir = tmp_path / "conversations"

    async with ConversationService(conversations_dir=conversations_dir) as service:
        assert service._eviction_task is None

    async with ConversationService(
        conversations_dir=conversations_dir,
        conversation_idle_ttl_seconds=1800,
    ) as service:
        assert service._eviction_task is not None
        assert not service._eviction_task.done()

    # 该任务在关闭时被取消并清除。
    assert service._eviction_task is None


@pytest.mark.asyncio
async def test_idle_conversation_is_evicted_and_rehydrated(tmp_path):
    """空闲的对话会从内存中清除，但在访问时会重新恢复。

    这重现了报告的泄露：在没有驱逐的情况下，一个完成的对话在``_event_services``中保持
    完全加载，直到它被显式删除或服务器重启。
    """
    conversations_dir = tmp_path / "conversations"
    request = _make_request(tmp_path / "workspace")

    async with ConversationService(
        conversations_dir=conversations_dir,
        conversation_idle_ttl_seconds=1800,
    ) as service:
        info, _ = await service.start_conversation(request)
        conversation_id = info.id

        assert service._event_services is not None
        event_service = service._event_services[conversation_id]
        assert event_service.is_open()

        # 模拟对话在 TTL 后闲置。
        event_service._last_active_monotonic = time.monotonic() - 10_000
        await service._evict_idle_conversations(1800)

        # 运行时已从内存中消失，但目录记录仍然存在。
        assert conversation_id not in service._event_services
        assert conversation_id in service._conversation_records
        assert not event_service.is_open()

        # 下一次访问会透明地从磁盘重新补充新的运行时。
        rehydrated = await service.get_event_service(conversation_id)
        assert rehydrated is not None
        assert rehydrated is not event_service
        assert conversation_id in service._event_services


@pytest.mark.asyncio
async def test_recently_active_conversation_is_not_evicted(tmp_path):
    conversations_dir = tmp_path / "conversations"
    request = _make_request(tmp_path / "workspace")

    async with ConversationService(
        conversations_dir=conversations_dir,
        conversation_idle_ttl_seconds=1800,
    ) as service:
        info, _ = await service.start_conversation(request)
        conversation_id = info.id

        # 刚开始：空闲时间约为 0，因此它保持驻留。
        await service._evict_idle_conversations(1800)

        assert service._event_services is not None
        assert conversation_id in service._event_services


@pytest.mark.asyncio
async def test_access_defers_eviction(tmp_path):
    """访问实时运行时会刷新其空闲时钟（触摸）。"""
    conversations_dir = tmp_path / "conversations"
    request = _make_request(tmp_path / "workspace")

    async with ConversationService(
        conversations_dir=conversations_dir,
        conversation_idle_ttl_seconds=1800,
    ) as service:
        info, _ = await service.start_conversation(request)
        conversation_id = info.id
        assert service._event_services is not None
        event_service = service._event_services[conversation_id]

        # 将对话老化到TTL之后，然后访问它。
        event_service._last_active_monotonic = time.monotonic() - 10_000
        assert await service.get_event_service(conversation_id) is event_service
        assert event_service.idle_seconds() < 1800

        # 由于访问刷新了时钟，驱逐将其留在原地。
        await service._evict_idle_conversations(1800)
        assert conversation_id in service._event_services


@pytest.mark.asyncio
async def test_running_conversation_is_not_evicted(tmp_path):
    conversations_dir = tmp_path / "conversations"
    request = _make_request(tmp_path / "workspace")

    async with ConversationService(
        conversations_dir=conversations_dir,
        conversation_idle_ttl_seconds=1800,
    ) as service:
        info, _ = await service.start_conversation(request)
        conversation_id = info.id
        assert service._event_services is not None
        event_service = service._event_services[conversation_id]

        event_service._last_active_monotonic = time.monotonic() - 10_000
        # 模拟飞行中的智能体运行。
        run_task = asyncio.create_task(asyncio.sleep(3600))
        event_service._run_task = run_task
        try:
            await service._evict_idle_conversations(1800)
            assert conversation_id in service._event_services
            assert event_service.is_open()
        finally:
            run_task.cancel()
            event_service._run_task = None


@pytest.mark.asyncio
async def test_conversation_with_external_subscriber_is_not_evicted(tmp_path):
    conversations_dir = tmp_path / "conversations"
    request = _make_request(tmp_path / "workspace")

    async with ConversationService(
        conversations_dir=conversations_dir,
        conversation_idle_ttl_seconds=1800,
    ) as service:
        info, _ = await service.start_conversation(request)
        conversation_id = info.id
        assert service._event_services is not None
        event_service = service._event_services[conversation_id]

        # WebSocket 样式的外部订阅者在启动后连接。
        assert not event_service.has_external_subscribers()
        subscriber_id = await event_service.subscribe_to_events(_DummySubscriber())
        assert event_service.has_external_subscribers()

        event_service._last_active_monotonic = time.monotonic() - 10_000
        await service._evict_idle_conversations(1800)
        assert conversation_id in service._event_services
        assert event_service.is_open()

        # 一旦订阅者断开连接，对话就可以被驱逐。
        await event_service.unsubscribe_from_events(subscriber_id)
        assert not event_service.has_external_subscribers()
        await service._evict_idle_conversations(1800)
        assert conversation_id not in service._event_services
        assert conversation_id in service._conversation_records


@pytest.mark.asyncio
async def test_eviction_preserves_credential_bindings(tmp_path):
    """仅运行时的凭据绑定不会被逐出，因此补水可以保留它们。"""
    conversations_dir = tmp_path / "conversations"
    request = _make_request(tmp_path / "workspace")

    async with ConversationService(
        conversations_dir=conversations_dir,
        conversation_idle_ttl_seconds=1800,
    ) as service:
        info, _ = await service.start_conversation(request)
        conversation_id = info.id
        assert service._event_services is not None
        event_service = service._event_services[conversation_id]

        # 在运行时激活的绑定仅存在于 EventService 上并被 close() 清除； 它不能从磁盘重新
        # 派生。
        #
        binding = _FakeBinding()
        event_service.credential_bindings = {"MY_SECRET": binding}

        event_service._last_active_monotonic = time.monotonic() - 10_000
        await service._evict_idle_conversations(1800)

        assert conversation_id not in service._event_services
        # 装订被交回目录以进行下一次水合。
        assert (
            service._credential_bindings.get(conversation_id, {}).get("MY_SECRET")
            is binding
        )


@pytest.mark.asyncio
async def test_eviction_preserves_reassigned_stored_metadata(tmp_path):
    """A 存储在运行时替换 (e.g. switch_acp_model) 经补水后仍可存活。"""
    conversations_dir = tmp_path / "conversations"
    request = _make_request(tmp_path / "workspace")

    async with ConversationService(
        conversations_dir=conversations_dir,
        conversation_idle_ttl_seconds=1800,
    ) as service:
        info, _ = await service.start_conversation(request)
        conversation_id = info.id
        assert service._event_services is not None
        event_service = service._event_services[conversation_id]

        # switch_acp_model / 机密更新 * 替换 * event_service.stored 和持久化； 过时的目
        # 录对象不得用于再水化。
        #
        event_service.stored = event_service.stored.model_copy(
            update={"title": "new-title"}
        )
        await event_service.save_meta()

        event_service._last_active_monotonic = time.monotonic() - 10_000
        await service._evict_idle_conversations(1800)
        assert conversation_id not in service._event_services

        rehydrated = await service.get_event_service(conversation_id)
        assert rehydrated is not None
        assert rehydrated.stored.title == "new-title"
