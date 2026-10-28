"""针对 base_state 单一事实来源修复的类似真实的端到端测试。

它们针对 *real* 磁盘上的持久化目录驱动 *real* ``ConversationService``（没有对话、事件
服务或 SDK 的模拟对象）。 他们重现了用户报
告的 bug —— 运行时模型切换在重新加载时被撤销 —— 并证明它在客户端（Agent Canvas）实际
执行的代码路径上保持不变。

    开始对话 -> switch_llm 在运行时 -> base_state.json 拥有智能体 -> 空闲驱逐（或完整
    的服务重启） -> 补充 -> 开关存活。

他们还防止了“它是否影响各种事物”的担忧：meta.json 从不携带智能体，无关的已持久化状态
（标签、确认政策、机密注册表）在往返过程中完好无损。

不需要网络：``switch_llm`` 和持久化从不调用模型。
"""

import json
from uuid import UUID

import pytest

from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.models import StartConversationRequest
from openhands.sdk import LLM, Agent
from openhands.sdk.security.confirmation_policy import NeverConfirm
from openhands.sdk.workspace import LocalWorkspace


def _request(workspace_dir, model: str, usage_id: str) -> StartConversationRequest:
    return StartConversationRequest(
        agent=Agent(llm=LLM(model=model, usage_id=usage_id), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
    )


def _read_json(path):
    return json.loads(path.read_text())


async def _switch_llm(service: ConversationService, conv_id: UUID, llm: LLM) -> None:
    """驱动实际运行时所使用的开关路径/switch_llm端点。"""
    event_service = await service.get_event_service(conv_id)
    assert event_service is not None
    conversation = event_service.get_conversation()
    conversation.switch_llm(llm)


@pytest.mark.asyncio
async def test_runtime_switch_llm_survives_idle_eviction(tmp_path):
    """报告的错误，端到端：运行时 switch_llm 必须不恢复
    空闲的对话会被逐出，然后从磁盘中重新恢复。
    """
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    async with ConversationService(conversations_dir=conversations_dir) as service:
        info, _ = await service.start_conversation(
            _request(workspace_dir, "gpt-4o", "primary")
        )
        conv_id = info.id

        # 运行时开关（新的 usage_id，因此注册表实际上安装了它）。
        await _switch_llm(
            service, conv_id, LLM(model="claude-sonnet-4", usage_id="switched")
        )

        conv_dir = conversations_dir / conv_id.hex
        base_state = _read_json(conv_dir / "base_state.json")
        meta = _read_json(conv_dir / "meta.json")
        # base_state.json拥有交换的智能体； meta.json根本没有智能体。
        assert base_state["agent"]["llm"]["model"] == "claude-sonnet-4"
        assert "agent" not in meta

        # 强制空闲驱逐（真实内部路径）； 实时服务会删除内存中的对话，但保留补液记录。
        #
        await service._evict_idle_conversations(0.0)

        # 再次访问它会从 base_state.json 重新水化。
        event_service = await service.get_event_service(conv_id)
        assert event_service is not None
        rehydrated = event_service.get_conversation()
        assert rehydrated.agent.llm.model == "claude-sonnet-4"


@pytest.mark.asyncio
async def test_runtime_switch_llm_survives_service_restart(tmp_path):
    """运行时 switch_llm 还必须在完整的智能体服务器重新启动后继续存在
    （新的 ConversationService 读取同一目录）。
    """
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    async with ConversationService(conversations_dir=conversations_dir) as service:
        info, _ = await service.start_conversation(
            _request(workspace_dir, "gpt-4o", "primary")
        )
        conv_id = info.id
        await _switch_llm(
            service, conv_id, LLM(model="gpt-5-codex", usage_id="switched")
        )

    # 新鲜服务==服务器重新启动：智能体从base_state.json返回。
    async with ConversationService(conversations_dir=conversations_dir) as service2:
        reloaded = await service2.get_conversation(conv_id)
        assert reloaded is not None
        assert reloaded.agent.llm.model == "gpt-5-codex"

        event_service = await service2.get_event_service(conv_id)
        assert event_service is not None
        assert event_service.get_conversation().agent.llm.model == "gpt-5-codex"


@pytest.mark.asyncio
async def test_new_conversation_agent_only_in_base_state(tmp_path):
    """全新的对话仅保留智能体到 base_state.json —
    从不到 meta.json — 因此导致错误的重复不会再次出现。
    """
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    async with ConversationService(conversations_dir=conversations_dir) as service:
        info, _ = await service.start_conversation(
            _request(workspace_dir, "gpt-4o", "primary")
        )
        conv_id = info.id

    conv_dir = conversations_dir / conv_id.hex
    meta = _read_json(conv_dir / "meta.json")
    base_state = _read_json(conv_dir / "base_state.json")
    assert "agent" not in meta
    assert base_state["agent"]["llm"]["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_switch_llm_preserves_unrelated_state_across_reload(tmp_path):
    """“它会影响各种事情吗？” — 不相关的已持久化状态（标签，
    确认政策）必须在转换+驱逐+补水后继续存在。
    """
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="primary"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        confirmation_policy=NeverConfirm(),
        tags={"client": "canvas", "kind": "regression"},
    )

    async with ConversationService(conversations_dir=conversations_dir) as service:
        info, _ = await service.start_conversation(request)
        conv_id = info.id
        await _switch_llm(
            service, conv_id, LLM(model="claude-opus-4", usage_id="switched")
        )
        await service._evict_idle_conversations(0.0)

        event_service = await service.get_event_service(conv_id)
        assert event_service is not None
        conversation = event_service.get_conversation()
        # 切换模型是权威的...
        assert conversation.agent.llm.model == "claude-opus-4"
        # ...and unrelated state came back intact.
        assert dict(event_service.stored.tags) == {
            "client": "canvas",
            "kind": "regression",
        }
        assert isinstance(conversation.state.confirmation_policy, NeverConfirm)


@pytest.mark.asyncio
async def test_switch_llm_after_init_replaces_registered_usage_id(tmp_path):
    """#5636: 在第一条消息之后，智能体的 usage_id 被注册。
    在同一 usage_id 下进行切换必须在实时对话、base_state.json 和服务的读取模型中安装
    发布的模型。
    """
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    async with ConversationService(conversations_dir=conversations_dir) as service:
        info, _ = await service.start_conversation(
            _request(workspace_dir, "gpt-4o", "default")
        )
        conv_id = info.id
        event_service = await service.get_event_service(conv_id)
        assert event_service is not None
        conversation = event_service.get_conversation()
        conversation.send_message("hi")  # 初始化智能体 (run=False)
        assert "default" in conversation.llm_registry.list_usage_ids()

        await _switch_llm(
            service, conv_id, LLM(model="gpt-5-codex", usage_id="default")
        )

        assert conversation.agent.llm.model == "gpt-5-codex"
        base_state = _read_json(conversations_dir / conv_id.hex / "base_state.json")
        assert base_state["agent"]["llm"]["model"] == "gpt-5-codex"
        read_back = await service.get_conversation(conv_id)
        assert read_back is not None
        assert read_back.agent.llm.model == "gpt-5-codex"
