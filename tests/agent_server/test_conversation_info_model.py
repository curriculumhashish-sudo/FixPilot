"""测试 ``_compose_conversation_info`` 提升 ACP 模型状态。

链条是：

  1. ``ACPAgent._init`` 捕获会话的 ``current_model_id`` 和
     ``available_models`` 进入 PrivateAttrs（因为 ``AgentBase`` 被冻结）。
  2. PrivateAttrs 不会在 ``model_dump`` 后保留下来，因此这些值无法超出 API 响应的已序
  列化 ``agent`` 字段。
  3. 智能体-服务器将它们从实时智能体实例提升到顶层
     ``current_model_id`` / ``available_models`` 两个字段在 ``ConversationInfo``，因
     此下游
     OpenHands app_server (芯片) 和模型选择器可以读取它们——选择器从列表中解析 id 到标
     签。

这些测试确定了第 3 步 — ``_compose_conversation_info`` 读取智能体中的属性（回落到已持
久化 ``agent_state``）并将它们路由
到响应模型中。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import SecretStr

from openhands.agent_server.conversation_service import _compose_conversation_info
from openhands.agent_server.models import ConversationInfo, StoredConversation
from openhands.agent_server.utils import utc_now
from openhands.sdk import LLM, Agent, Tool
from openhands.sdk.agent.acp_agent import ACPAgent
from openhands.sdk.agent.acp_models import ACPModelInfo
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.security.confirmation_policy import NeverConfirm
from openhands.sdk.workspace import LocalWorkspace


def _make_state(agent) -> ConversationState:
    workspace = LocalWorkspace(working_dir="/tmp/test")
    return ConversationState(
        id=uuid4(),
        agent=agent,
        workspace=workspace,
        execution_status=ConversationExecutionStatus.IDLE,
        confirmation_policy=NeverConfirm(),
    )


def _make_stored(state: ConversationState) -> StoredConversation:
    # ``state.workspace`` 被键入为 ``BaseWorkspace`` 父级； 我们用 ``LocalWorkspace`` 构
    # 建了状态，因此可以安全地通过。 ``cast`` 会更正确，但对于测试助手来说是噪音 - 相反
    # ，从工作目录重建 LocalWorkspace。
    #
    workspace = LocalWorkspace(working_dir=state.workspace.working_dir)
    return StoredConversation(
        id=state.id,
        workspace=workspace,
        title="Test",
        metrics=None,
        created_at=utc_now(),
        updated_at=utc_now(),
    )


def test_tool_module_qualnames_are_returned_to_attaching_clients():
    agent = Agent(
        llm=LLM(model="gpt-4o", api_key=SecretStr("test-key"), usage_id="test-llm"),
        tools=[],
    )
    state = _make_state(agent)
    stored = _make_stored(state).model_copy(
        update={"tool_module_qualnames": {"TerminalTool": "example.terminal"}}
    )

    info = _compose_conversation_info(stored, state)

    assert info.tool_module_qualnames == {"TerminalTool": "example.terminal"}


def test_current_model_id_is_lifted_from_acp_agent():
    """当 ACP 智能体解析了模型后，它就会出现在响应中。"""
    agent = ACPAgent(acp_command=["echo", "test"])
    agent._current_model_id = "claude-opus-4-1"
    state = _make_state(agent)
    stored = _make_stored(state)

    info = _compose_conversation_info(stored, state)

    assert isinstance(info, ConversationInfo)
    assert info.current_model_id == "claude-opus-4-1"


def test_current_model_id_is_none_when_acp_agent_has_no_model():
    """较旧的 ACP 服务器不会出现在该领域 - 我们传播 ``None``。"""
    agent = ACPAgent(acp_command=["echo", "test"])
    # ``_current_model_id`` 默认为 None — 保持原样。
    state = _make_state(agent)
    stored = _make_stored(state)

    info = _compose_conversation_info(stored, state)

    assert info.current_model_id is None


def test_current_model_id_is_none_for_native_openhands_agent():
    """Native智能体没有该属性； ``getattr`` 返回 None。"""
    agent = Agent(
        llm=LLM(
            model="gpt-4o",
            api_key=SecretStr("test-key"),
            usage_id="test-llm",
        ),
        tools=[Tool(name="TerminalTool")],
    )
    state = _make_state(agent)
    stored = _make_stored(state)

    info = _compose_conversation_info(stored, state)

    # 消费者应该阅读 ``agent.llm.model`` 作为本机智能体。
    assert info.current_model_id is None


@pytest.mark.parametrize(
    "override_model,server_model,expected",
    [
        # 调用者通过 ``acp_model`` 强制建立一个模型——获胜（mirrors _init）。
        ("gpt-5", "claude-sonnet-4-5", "gpt-5"),
        # 不覆盖，服务器报告模型 - 使用服务器的值。
        (None, "claude-sonnet-4-5", "claude-sonnet-4-5"),
        # 双方都没有模型——通过None。
        (None, None, None),
    ],
)
def test_current_model_id_propagates_init_resolution(
    override_model, server_model, expected
):
    """解析语义 ``_init`` 的端到端检查是适用的。

    ``_init`` resolves ``self.acp_model or _extract_session_models(response)[0]``; 解
    析值
    落在``_current_model_id``中； 然后智能体服务器将其提升到 ``ConversationInfo``。
    该测试模拟作业
    ``_init`` 生成并验证值经过。
    """
    agent = ACPAgent(acp_command=["echo", "test"], acp_model=override_model)
    # 镜像 ``_init`` 末尾发生的分配。
    agent._current_model_id = override_model or server_model
    state = _make_state(agent)
    stored = _make_stored(state)

    info = _compose_conversation_info(stored, state)
    assert info.current_model_id == expected


def test_cold_read_falls_back_to_acp_model_override():
    """冷列表读取（``init_state`` 未触发）：没有实时/持续电流
    id，已序列化 ``acp_model`` 是最后已知的最佳提示并浮出水面。
    """
    agent = ACPAgent(acp_command=["echo", "test"], acp_model="model-x")
    # _initialized默认为False（冷读）； _current_model_id 默认为 None。
    state = _make_state(agent)
    stored = _make_stored(state)

    info = _compose_conversation_info(stored, state)

    assert info.current_model_id == "model-x"


def test_live_agent_does_not_fall_back_to_unapplied_override():
    """实时初始化智能体，其覆盖已应用不 (e.g. 一份简历，其
    模型选择调用服务器被拒绝了。``current_model_id`` 是权威的``None``，必须不
    fallback 到``acp_model`` — 这会重新
    激活一个已暂停的会话。
    """
    agent = ACPAgent(acp_command=["echo", "test"], acp_model="model-x")
    # init_state 已解雇； 覆盖解析为 None（已拒绝）并记录为未应用。 已持久化提示已被
    # init_state 清除。
    #
    agent._initialized = True
    agent._current_model_id = None
    agent._model_override_applied = False
    state = _make_state(agent)
    stored = _make_stored(state)

    info = _compose_conversation_info(stored, state)

    assert info.current_model_id is None


def test_available_models_lifted_from_acp_agent():
    """``ConversationInfo.available_models`` 反映智能体的型号列表。

    该列表原样呈现（已标准化 ``ACPModelInfo``），客户端可以渲染选择器并将其
    ``current_model_id`` 自己解析为标签——服务器不做名称
    校验。 模拟 claude-智能体-ACP 的默认配置，其中 ``current_model_id`` 是不透明别名
    ``"default"``，可读身份位于匹配的
     ``available_models`` 条目中。
    """
    agent = ACPAgent(acp_command=["echo", "test"])
    agent._current_model_id = "default"
    agent._available_models = [
        ACPModelInfo(
            model_id="default",
            name="Default (recommended)",
            description="Opus 4.7 with 1M context · Most capable for complex work",
        ),
        ACPModelInfo(model_id="sonnet", name="Sonnet", description="Sonnet 4.6"),
    ]
    state = _make_state(agent)
    stored = _make_stored(state)

    info = _compose_conversation_info(stored, state)

    assert info.current_model_id == "default"
    assert info.available_models == agent._available_models


def test_available_models_empty_when_server_omits_them():
    """不具备 UNSTABLE ``models`` 功能的服务器会产生 []。"""
    agent = ACPAgent(acp_command=["echo", "test"])
    agent._current_model_id = "gpt-5.5"
    state = _make_state(agent)
    stored = _make_stored(state)

    info = _compose_conversation_info(stored, state)

    assert info.current_model_id == "gpt-5.5"
    assert info.available_models == []


def test_available_models_empty_for_native_openhands_agent():
    """Native智能体没有该属性； 提升产生[]。"""
    agent = Agent(
        llm=LLM(
            model="gpt-4o",
            api_key=SecretStr("test-key"),
            usage_id="test-llm",
        ),
        tools=[Tool(name="TerminalTool")],
    )
    state = _make_state(agent)
    stored = _make_stored(state)

    info = _compose_conversation_info(stored, state)

    assert info.available_models == []


def test_current_model_fields_read_from_persisted_agent_state():
    """冷话列表：直播的智能体的PrivateAttrs还在
    无/空，因为 ``init_state`` 尚未触发，但 ``agent_state`` 已持久化是上次会话的值。
    提升应该来自那里，以便芯片+拾取器能够承受冷读。
     已持久化
    ``available_models`` 是普通字典列表； ``ConversationInfo`` 将其强制返回
    ``ACPModelInfo``。
    """
    agent = ACPAgent(acp_command=["echo", "test"])
    # 至关重要的是，将 PrivateAttrs 保留为默认值 - 这会模拟在任何 ``init_state`` 之前从
    # 已持久化 JSON 重新构建的智能体。
    #
    state = _make_state(agent)
    state.agent_state = {
        "acp_session_id": "prior-session",
        "acp_current_model_id": "default",
        "acp_available_models": [
            {
                "model_id": "default",
                "name": "Default (recommended)",
                "description": "Opus 4.7 with 1M context",
            }
        ],
    }
    stored = _make_stored(state)

    info = _compose_conversation_info(stored, state)

    assert info.current_model_id == "default"
    assert info.available_models == [
        ACPModelInfo(
            model_id="default",
            name="Default (recommended)",
            description="Opus 4.7 with 1M context",
        )
    ]


def test_live_agent_attrs_take_precedence_over_persisted_state():
    """在活动会话中，实时智能体是最新的来源。"""
    agent = ACPAgent(acp_command=["echo", "test"])
    agent._current_model_id = "claude-opus-4-1"
    agent._available_models = [
        ACPModelInfo(model_id="claude-opus-4-1", name="Opus 4.1")
    ]
    state = _make_state(agent)
    # 来自选择不同模型的先前会话的陈旧已持久化状态。
    state.agent_state = {
        "acp_current_model_id": "haiku",
        "acp_available_models": [{"model_id": "haiku", "name": "Haiku"}],
    }
    stored = _make_stored(state)

    info = _compose_conversation_info(stored, state)

    assert info.current_model_id == "claude-opus-4-1"
    assert info.available_models == [
        ACPModelInfo(model_id="claude-opus-4-1", name="Opus 4.1")
    ]


def test_current_model_id_falls_back_to_acp_model_on_cold_read():
    """冷读服务器从未切换/覆盖的对话
    浮出水面 ``models``：没有实时 PrivateAttr 和已持久化提示，但是
    ``acp_model`` 是真正的已序列化字段并且具有权威性 - 因此芯片仍然可以解析而不是空白
    。
    """
    agent = ACPAgent(acp_command=["echo", "test"], acp_model="enterprise-x")
    # 将 None 和 agent_state 处的 _current_model_id 留空：纯冷读。
    state = _make_state(agent)
    stored = _make_stored(state)

    info = _compose_conversation_info(stored, state)

    assert info.current_model_id == "enterprise-x"


def test_supports_runtime_model_switch_lifted_from_agent_state():
    """静态提供者能力读取自已持久化``agent_state``
    （在会话初始化时编写），所以它在冷列表读取上也是正确的。
    """
    agent = ACPAgent(acp_command=["echo", "test"])
    state = _make_state(agent)
    state.agent_state = {"acp_supports_runtime_model_switch": True}
    stored = _make_stored(state)

    info = _compose_conversation_info(stored, state)

    assert info.supports_runtime_model_switch is True


def test_supports_runtime_model_switch_defaults_false():
    """无提示（本机智能体或尚未开始的 ACP 对话）-> False。"""
    agent = Agent(
        llm=LLM(
            model="gpt-4o",
            api_key=SecretStr("test-key"),
            usage_id="test-llm",
        ),
        tools=[Tool(name="TerminalTool")],
    )
    state = _make_state(agent)
    stored = _make_stored(state)

    info = _compose_conversation_info(stored, state)

    assert info.supports_runtime_model_switch is False
