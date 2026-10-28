import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from openhands.sdk import LLM, LocalConversation
from openhands.sdk.agent import Agent
from openhands.sdk.agent.acp_agent import ACPAgent
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.sdk.context.view import View
from openhands.sdk.conversation.persistence_const import BASE_STATE
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.llm import Message, MessageToolCall, TextContent, llm_profile_store
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.testing import TestLLM
from openhands.sdk.utils.cipher import Cipher
from tests.conftest import create_mock_litellm_response


def _make_llm(model: str, usage_id: str) -> LLM:
    return TestLLM.from_messages([], model=model, usage_id=usage_id)


def _message_event(content: str) -> MessageEvent:
    return MessageEvent(
        llm_message=Message(role="user", content=[TextContent(text=content)]),
        source="user",
    )


@pytest.fixture()
def profile_store(tmp_path, monkeypatch):
    """
    创建一个临时配置文件存储，其中包含通过 _make_llm 保存的“快”和“慢”配置文件。
    """

    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    monkeypatch.setattr(llm_profile_store, "_DEFAULT_PROFILE_DIR", profile_dir)

    store = LLMProfileStore(base_dir=profile_dir)
    store.save("fast", _make_llm("fast-model", "fast"))
    store.save("slow", _make_llm("slow-model", "slow"))
    return store


def _make_conversation(profile_store_dir: Path | None = None) -> LocalConversation:
    return LocalConversation(
        agent=Agent(
            llm=_make_llm("default-model", "test-llm"),
            tools=[],
        ),
        workspace=Path.cwd(),
        profile_store_dir=profile_store_dir,
    )


def test_switch_acp_model_rejects_non_acp_agent():
    """switch_acp_model 仅对 ACP 个对话有效。"""
    conv = _make_conversation()  # 智能体，不是ACPAgent
    with pytest.raises(ValueError, match="only supported for ACP"):
        conv.switch_acp_model("haiku")


def _make_acp_conversation(tmp_path) -> tuple[LocalConversation, ACPAgent]:
    """与伪造的实时会话的已持久化 ACP 对话。

    假的 ``_conn`` / ``_executor`` 让 ``set_acp_model`` 发出其协议调用，而不启动真正
    的 ACP 子进程。
    """
    agent = ACPAgent(acp_command=["echo", "test"], acp_model="model-a")
    agent._conn = MagicMock()
    agent._session_id = "sess-1"
    agent._agent_name = "codex-acp"
    executor = MagicMock()
    executor.run_async = MagicMock()
    agent._executor = executor
    conv = LocalConversation(
        agent=agent,
        workspace=tmp_path,
        persistence_dir=str(tmp_path / "persist"),
    )
    return conv, agent


def _make_pre_session_acp_conversation(tmp_path) -> tuple[LocalConversation, ACPAgent]:
    """已创建 ACP 对话，但尚未 ``run()``。

    ``_conn`` / ``_session_id`` / ``_executor`` 没有连接，因此没有实时会话 -
    ``switch_acp_model`` 必
    须推迟而不是发出协议调用。
    """
    agent = ACPAgent(acp_command=["echo", "test"], acp_model="model-a")
    agent._agent_name = "codex-acp"
    conv = LocalConversation(
        agent=agent,
        workspace=tmp_path,
        persistence_dir=str(tmp_path / "persist"),
    )
    return conv, agent


def test_switch_acp_model_before_session_defers_and_persists(tmp_path):
    """pre-``run()`` 开关保留新模型而不引发。

    回归对于 #3763：``switch_acp_model`` 曾经首先调用 ``set_acp_model``，这在第一个
    ``run()`` 之前引发了
    ``RuntimeError``，因此持久化块从未运行，并且新模型默默地丢失了 - 第一个会话保留了
    构建时间 ``acp_model``。 如果没有实时会话，则必须
    跳过实时呼叫和值已持久化，因此第一个 ``run()`` 上的会话创建将遵循切换模型。
    """
    conv, agent = _make_pre_session_acp_conversation(tmp_path)
    assert not agent.has_live_acp_session

    conv.switch_acp_model("model-b")

    # 尽管没有触及任何现场会议，但权威模型仍然在移动。
    switched = conv.agent
    assert isinstance(switched, ACPAgent)
    assert switched.acp_model == "model-b"
    assert not switched.has_live_acp_session
    assert isinstance(conv.state.agent, ACPAgent)
    assert conv.state.agent.acp_model == "model-b"
    # 在任何会话存在之前，为芯片/选择器更新冷读提示。
    assert conv.state.agent_state["acp_current_model_id"] == "model-b"

    # base_state.json 在第一次运行之前就存活下来，它携带了切换后的模型，而
    # model_post_init 会从它那里重新导出哨兵值 LLM，因此第一个会话会从模型b（接受标准#3
    # ）开始。
    #
    base_text = conv.state._fs.read(BASE_STATE)
    reloaded = ConversationState.model_validate(json.loads(base_text))
    assert isinstance(reloaded.agent, ACPAgent)
    assert reloaded.agent.acp_model == "model-b"
    assert reloaded.agent.llm.model == "model-b"


@pytest.mark.parametrize("model", ["", "   "])
def test_switch_acp_model_before_session_rejects_blank_model(tmp_path, model):
    """在第一个 ``run()`` 之前，空白模型也会被拒绝，因为它是实时的。

    会话前路径用于跳过 ``set_acp_model``（拥有非空检查）和持久化未检查的值，因此
    ``acp_model`` 变成
    ``"   "``.
    """
    conv, agent = _make_pre_session_acp_conversation(tmp_path)

    with pytest.raises(ValueError, match="non-empty"):
        conv.switch_acp_model(model)

    assert conv.agent is agent
    assert isinstance(conv.state.agent, ACPAgent)
    assert conv.state.agent.acp_model == "model-a"
    assert conv.state.agent_state.get("acp_current_model_id") != model


def test_switch_acp_model_persists_authoritative_model(tmp_path):
    """运行时开关仍然是权威的 ``acp_model``。

    回归对于重新分配同一（变异）的审查发现智能体对象是一个自动保存的无操作，冻结了
    ``acp_model`` field — which
    ``model_post_init`` / ``_start_acp_server`` 继续加载/继续播放 — 保持了构造时的值
    。
    """
    conv, agent = _make_acp_conversation(tmp_path)
    live_conn = agent._conn

    conv.switch_acp_model("model-b")

    # 内存中：智能体 + 状态同意新模型，并且实时连接在 model_copy 中幸存下来，因此对话可
    # 以继续运行。
    #
    switched = conv.agent
    assert isinstance(switched, ACPAgent)
    assert switched.acp_model == "model-b"
    assert isinstance(conv.state.agent, ACPAgent)
    assert conv.state.agent.acp_model == "model-b"
    assert switched.llm.model == "model-b"
    assert switched._conn is live_conn
    assert switched._session_id == "sess-1"

    # 在磁盘上：base_state.json 实际上已更改（不是自动保存无操作），并且已持久化智能体使
    # 用切换后的模型进行重建作为权威。
    #
    base_text = conv.state._fs.read(BASE_STATE)
    reloaded = ConversationState.model_validate(json.loads(base_text))
    assert isinstance(reloaded.agent, ACPAgent)
    assert reloaded.agent.acp_model == "model-b"
    # model_post_init 从已持久化 acp_model 导出哨兵值 LLM 模型。
    assert reloaded.agent.llm.model == "model-b"


def test_switch_acp_model_refreshes_surfaced_current_model_id(tmp_path):
    """实时切换后，模型状态出现在 ``ConversationInfo``
    必须反映新模型，而不是过时的会话起始值。

    回归软件-智能体-SDK#3347 + #3390 集成：芯片/内联拾取器读取
    ``ACPAgent.current_model_id``（并且已持久化
    ``acp_current_model_id``冷读提示）。 如果不在运行时开关上刷新两者，芯片就会在最重
    要的时候变得陈旧。
    """
    conv, agent = _make_acp_conversation(tmp_path)
    agent._current_model_id = "model-a"  # _init 在会话开始时捕获的内容
    # 故意做不种子前投资 ``acp_current_model_id`` 在 agent_state：一个较旧/自定义服务器
    # 可能在初始化时没有报告模型，但成功的切换仍然具有权威性，必须仍然执行持久化提示。
    #
    assert "acp_current_model_id" not in conv.state.agent_state

    conv.switch_acp_model("model-b")

    switched = conv.agent
    assert isinstance(switched, ACPAgent)
    # 直播 PrivateAttr（由 model_copy 传送到已持久化智能体）。
    assert switched.current_model_id == "model-b"
    # 已持久化重新初始化之前无条件为冷读写入的提示。
    assert conv.state.agent_state["acp_current_model_id"] == "model-b"


def test_switch_acp_model_disarms_discarded_agent_finalizer(tmp_path):
    """预切换智能体不得拆除共享实时会话。

    Regression: ``switch_acp_model`` 交换为浅层 ``model_copy``
    shares ``_conn`` / ``_executor`` / ``_process`` with the old 智能体。 在解除武装
    之前，
    ``ACPAgent.__del__`` -> ``close()`` 废弃的智能体关闭连接并终止子进程并关闭执行器—
    —从复制中溜走，破坏了下一个回合。
    """
    conv, old_agent = _make_acp_conversation(tmp_path)
    live_conn = old_agent._conn
    live_executor = old_agent._executor
    lifecycle = MagicMock()
    lifecycle.path = tmp_path / "auth.json"
    lifecycle.may_have_changed = True
    old_agent._file_credential_lifecycles["CODEX_AUTH_JSON"] = lifecycle
    credential_lock = old_agent._file_credential_lock
    client = MagicMock()
    old_agent._client = client
    old_agent._bind_file_credential_masking()
    old_agent._register_atexit_cleanup()
    old_cleanup = old_agent._atexit_callback

    conv.switch_acp_model("model-b")

    # 副本接管了实时运行时间......
    switched = conv.agent
    assert isinstance(switched, ACPAgent)
    assert switched._conn is live_conn
    assert switched._executor is live_executor
    assert switched._file_credential_lifecycles == {"CODEX_AUTH_JSON": lifecycle}
    assert switched._file_credential_lock is credential_lock
    assert old_agent._atexit_callback is None
    assert switched._atexit_callback is not None
    assert switched._atexit_callback is not old_cleanup

    # ...and the discarded agent's finalizer was disarmed (marked closed)
    # WITHOUT 清除其运行时引用 - 仍在保留旧智能体的运行中 ask_agent()/fork 保持有效连接
    # 。
    #
    assert old_agent._closed is True
    assert old_agent._conn is live_conn
    assert old_agent._executor is live_executor
    assert old_agent._file_credential_lifecycles == {}
    lifecycle.track_current.reset_mock()
    client.before_mask()
    lifecycle.track_current.assert_called_once_with()

    # 在解除武装的旧智能体上模拟 GC (__del__ -> close()) 是无操作：副本的共享连接/执行器
    # 保持不变。
    #
    live_executor.run_async.reset_mock()
    old_agent.close()
    live_executor.run_async.assert_not_called()
    live_executor.close.assert_not_called()
    switched.release_runtime()
    assert switched._atexit_callback is None


def test_switch_profile(profile_store):
    """switch_profile 切换智能体的 LLM。"""
    conv = _make_conversation()
    conv.switch_profile("fast")
    assert conv.agent.llm.model == "fast-model"
    conv.switch_profile("slow")
    assert conv.agent.llm.model == "slow-model"


def test_switch_profile_uses_custom_profile_store(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profiles"
    store = LLMProfileStore(profile_dir)
    store.save("fast", _make_llm("fast-model", "fast"))

    conv = _make_conversation(profile_store_dir=profile_dir)
    conv.switch_profile("fast")

    assert conv.agent.llm.model == "fast-model"


def test_switch_profile_updates_state(profile_store):
    """switch_profile 更新对话状态智能体。"""
    conv = _make_conversation()
    conv.switch_profile("fast")
    assert conv.state.agent.llm.model == "fast-model"


def test_switch_between_profiles(profile_store):
    """切换快速->慢速->快速，验证每次模型的变化。"""
    conv = _make_conversation()

    conv.switch_profile("fast")
    assert conv.agent.llm.model == "fast-model"

    conv.switch_profile("slow")
    assert conv.agent.llm.model == "slow-model"

    conv.switch_profile("fast")
    assert conv.agent.llm.model == "fast-model"


def test_switch_reuses_registry_entry(profile_store):
    """切换回配置文件会重复使用相同的注册表 LLM 对象。"""
    conv = _make_conversation()

    conv.switch_profile("fast")
    llm_first = conv.llm_registry.get("profile:fast")

    conv.switch_profile("slow")
    conv.switch_profile("fast")
    llm_second = conv.llm_registry.get("profile:fast")

    assert llm_first is llm_second


def test_switch_nonexistent_raises(profile_store):
    """切换到不存在的配置文件会引发 FileNotFoundError。"""
    conv = _make_conversation()
    with pytest.raises(FileNotFoundError):
        conv.switch_profile("nonexistent")
    assert conv.agent.llm.model == "default-model"
    assert conv.state.agent.llm.model == "default-model"


def test_switch_profile_preserves_prompt_cache_key(profile_store):
    """回归测试 #2918：切换保持会话缓存身份。"""
    conv = _make_conversation()
    expected = str(conv.id)
    assert conv.get_llm_call_context().prompt_cache_key == expected

    conv.switch_profile("fast")
    assert conv.get_llm_call_context().prompt_cache_key == expected

    conv.switch_profile("slow")
    assert conv.get_llm_call_context().prompt_cache_key == expected

    # 切换回缓存的注册表条目不得更改上下文。
    conv.switch_profile("fast")
    assert conv.get_llm_call_context().prompt_cache_key == expected


def test_switch_then_send_message(profile_store):
    """switch_profile 后跟 send_message 不会因注册表碰撞而崩溃。"""
    conv = _make_conversation()
    conv.switch_profile("fast")
    # send_message 触发 _ensure_agent_ready，后者会重新注册智能体 LLMs。 LLM 必须避免导
    # 致重复注册错误。
    #
    conv.send_message("hello")


@pytest.fixture()
def empty_profile_store(tmp_path, monkeypatch):
    """空配置文件目录 — 模拟智能体服务器沙箱，其中
    应用程序服务器从未上传过配置文件 JSON。 这是#3017 正在修复的真正故障模式。
    """
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    monkeypatch.setattr(llm_profile_store, "_DEFAULT_PROFILE_DIR", profile_dir)
    return profile_dir


def test_switch_llm_swaps_when_store_empty(empty_profile_store):
    """真实的应用程序服务器案例 (#3017)：沙箱 FS 不知道配置文件，
    应用服务器直接提供LLM，交换成功。
    """
    conv = _make_conversation()
    inline = _make_llm("inline-model", "caller-supplied-id")

    conv.switch_llm(inline)

    assert conv.agent.llm.model == "inline-model"
    # 状态必须同意 - agent_server 通过 _state 读取 agent.llm。
    assert conv.state.agent.llm.model == "inline-model"
    # 主叫方的 usage_id 被保留为注册表键。
    assert conv.agent.llm.usage_id == "caller-supplied-id"
    assert conv.llm_registry.get("caller-supplied-id").model == "inline-model"
    # 缓存标识属于会话，而不是所选的LLM。
    assert conv.get_llm_call_context().prompt_cache_key == str(conv.id)


def test_switch_llm_refreshes_llm_condenser_credentials(
    empty_profile_store, tmp_path, monkeypatch
):
    """会话中的 LLM 切换还必须刷新默认的上下文压缩器 LLM。

    上下文压缩器拥有智能体 LLM 的单独副本。 如果智能体 LLM 被切换但该副本被留下，则正
    常轮换可以继续工作，而下一个上下文压缩请求仍然调用旧的 no-凭据模型。
    """
    initial_llm = LLM(model="litellm_proxy/old-model", usage_id="default")
    initial_condenser_llm = initial_llm.model_copy(update={"usage_id": "condenser"})
    initial_condenser_llm.reset_metrics()
    condenser = LLMSummarizingCondenser(
        llm=initial_condenser_llm,
        max_size=100,
        keep_first=2,
    )
    conv = LocalConversation(
        agent=Agent(llm=initial_llm, condenser=condenser, tools=[]),
        workspace=tmp_path,
    )
    conv._ensure_agent_ready()

    switched_llm = LLM(
        model="litellm_proxy/new-model",
        api_key=SecretStr("new-test-key"),
        usage_id="profile:new",
    )

    conv.switch_llm(switched_llm)

    assert conv.agent.llm.model == "litellm_proxy/new-model"
    assert isinstance(conv.agent.condenser, LLMSummarizingCondenser)
    assert isinstance(conv.state.agent.condenser, LLMSummarizingCondenser)

    condenser_llm = conv.agent.condenser.llm
    state_condenser_llm = conv.state.agent.condenser.llm
    assert condenser_llm is not initial_condenser_llm
    assert condenser_llm.model == "litellm_proxy/new-model"
    assert condenser_llm.usage_id == "condenser"
    assert isinstance(condenser_llm.api_key, SecretStr)
    assert condenser_llm.api_key.get_secret_value() == "new-test-key"
    assert state_condenser_llm.model == condenser_llm.model
    assert state_condenser_llm.api_key == condenser_llm.api_key
    assert condenser_llm.metrics is not conv.agent.llm.metrics
    assert condenser_llm._telemetry is not None

    async def _fake_acompletion(**kwargs):
        return create_mock_litellm_response(
            content="condensed summary",
            model=kwargs["model"],
        )

    monkeypatch.setattr("openhands.sdk.llm.llm.litellm_acompletion", _fake_acompletion)

    response = asyncio.run(
        condenser_llm.acompletion(
            [Message(role="user", content=[TextContent(text="summarize")])]
        )
    )

    content = response.message.content[0]
    assert isinstance(content, TextContent)
    assert content.text == "condensed summary"


def test_switch_llm_condenser_can_generate_condensation(
    empty_profile_store, tmp_path, monkeypatch
):
    initial_llm = LLM(model="litellm_proxy/old-model", usage_id="default")
    condenser = LLMSummarizingCondenser(
        llm=initial_llm.model_copy(update={"usage_id": "condenser"}),
        max_size=6,
        keep_first=1,
    )
    conv = LocalConversation(
        agent=Agent(llm=initial_llm, condenser=condenser, tools=[]),
        workspace=tmp_path,
    )
    conv._ensure_agent_ready()

    switched_llm = LLM(
        model="litellm_proxy/new-model",
        api_key=SecretStr("new-test-key"),
        usage_id="profile:new",
    )
    conv.switch_llm(switched_llm)

    def _fake_completion(**kwargs):
        return create_mock_litellm_response(
            content="condensed summary",
            model=kwargs["model"],
        )

    monkeypatch.setattr("openhands.sdk.llm.llm.litellm_completion", _fake_completion)

    assert isinstance(conv.agent.condenser, LLMSummarizingCondenser)
    condensation = conv.agent.condenser.get_condensation(
        View.from_events([_message_event(f"event {i}") for i in range(12)]),
        agent_llm=conv.agent.llm,
    )

    assert condensation.summary == "condensed summary"
    assert len(condensation.forgotten_event_ids) > 0


def test_switch_llm_preserves_independent_condenser_profile(
    empty_profile_store, tmp_path
):
    initial_llm = LLM(
        model="litellm_proxy/agent-old",
        api_key=SecretStr("agent-old-key"),
        usage_id="default",
    )
    independent_condenser_llm = LLM(
        model="litellm_proxy/condenser-profile",
        api_key=SecretStr("condenser-key"),
        usage_id="condenser",
    )
    condenser = LLMSummarizingCondenser(
        llm=independent_condenser_llm,
        max_size=100,
        keep_first=2,
    )
    conv = LocalConversation(
        agent=Agent(llm=initial_llm, condenser=condenser, tools=[]),
        workspace=tmp_path,
    )
    conv._ensure_agent_ready()

    conv.switch_llm(
        LLM(
            model="litellm_proxy/agent-new",
            api_key=SecretStr("agent-new-key"),
            usage_id="profile:new",
        )
    )

    assert isinstance(conv.agent.condenser, LLMSummarizingCondenser)
    condenser_llm = conv.agent.condenser.llm
    assert condenser_llm.model == "litellm_proxy/condenser-profile"
    assert isinstance(condenser_llm.api_key, SecretStr)
    assert condenser_llm.api_key.get_secret_value() == "condenser-key"


def test_switch_llm_then_send_message(empty_profile_store):
    """send_message 触发 _ensure_agent_ready，重新注册智能体
    LLMs in the 注册表。 switch_llm 添加了关于usage_id的条目。 这必须与智能体的 LLM
    重注册在 send_message() 时不冲
    突。
    """
    conv = _make_conversation()
    conv.switch_llm(_make_llm("inline-model", "x"))
    conv.send_message("hello")


def test_switch_between_two_llms(empty_profile_store):
    """每个寄存器在不同的 usage_ids 下连续 switch_llm 调用
    他们自己的插槽并最终成为智能体的 LLM。
    """
    conv = _make_conversation()

    conv.switch_llm(_make_llm("model-a", "x"))
    assert conv.agent.llm.model == "model-a"

    conv.switch_llm(_make_llm("model-b", "y"))
    assert conv.agent.llm.model == "model-b"


def test_switch_llm_does_not_consult_store(empty_profile_store, monkeypatch):
    """switch_llm 不得点击 LLMProfileStore.load — 调用者是
    权威的。 防止内联路径默默地进入磁盘 IO 的回归。
    """
    calls: list[str] = []

    def _spy_load(self, name):
        calls.append(name)
        raise FileNotFoundError(name)

    monkeypatch.setattr(LLMProfileStore, "load", _spy_load)

    conv = _make_conversation()
    conv.switch_llm(_make_llm("inline-model", "x"))

    assert calls == [], f"profile store was consulted: {calls}"


def test_switch_profile_decrypts_with_cipher(tmp_path, monkeypatch):
    """使用密码加密机密保存的配置文件必须在交换机上解密
    因此智能体的 LLM 最终得到的是明文 API 密钥，而不是 Fernet token（#3164 的回归）。
    """
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    monkeypatch.setattr(llm_profile_store, "_DEFAULT_PROFILE_DIR", profile_dir)

    cipher = Cipher("test-key-for-switch-profile")
    store = LLMProfileStore(base_dir=profile_dir)
    store.save(
        "encrypted",
        LLM(
            model="gpt-4o",
            usage_id="encrypted",
            api_key=SecretStr("plaintext-secret"),
        ),
        include_secrets=True,
        cipher=cipher,
    )

    conv = LocalConversation(
        agent=Agent(
            llm=_make_llm("default-model", "test-llm"),
            tools=[],
        ),
        workspace=Path.cwd(),
        cipher=cipher,
    )

    conv.switch_profile("encrypted")

    api_key = conv.agent.llm.api_key
    assert isinstance(api_key, SecretStr)
    assert api_key.get_secret_value() == "plaintext-secret"


def test_switch_profile_delegates_to_switch_llm(profile_store, monkeypatch):
    """switch_profile从磁盘加载并委托给switch_llm； LLM
    传递的内容带有规范的 ``profile:{name}`` usage_id。
    """
    conv = _make_conversation()
    seen: list[LLM] = []
    real_switch_llm = conv.switch_llm

    def _spy(llm):
        seen.append(llm)
        real_switch_llm(llm)

    monkeypatch.setattr(conv, "switch_llm", _spy)

    conv.switch_profile("fast")

    assert len(seen) == 1
    assert seen[0].usage_id == "profile:fast"
    assert seen[0].model == "fast-model"


def test_duplicate_usage_ids_in_registration_loop_are_silently_deduped(tmp_path):
    """Regression: 如果智能体 LLM 和上下文压缩器 LLM 都带有相同的
    usage_id（当对话从 #3368 之前编写的 base_state.json 反序列化时发生），
    _ensure_agent_ready() 必须不引发
    ValueError。 先写胜合约意味着只有智能体LLM条目被注册； 上下文压缩器重复项将被静默
    跳过。
    """
    # 模拟损坏的已持久化状态：上下文压缩器继承智能体LLM的usage_id
    agent_llm = LLM(
        model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="default"
    )
    condenser_llm = agent_llm.model_copy()  # 继承usage_id=“默认”
    condenser = LLMSummarizingCondenser(llm=condenser_llm, max_size=100, keep_first=2)
    agent = Agent(llm=agent_llm, condenser=condenser, tools=[])

    conv = LocalConversation(agent=agent, workspace=tmp_path)

    # 不得引发 ValueError（“使用 ID 'default' 已存在于注册表中”）
    conv._ensure_agent_ready()

    # First-write-wins: 共享 usage_id 下只有一个条目
    assert conv.llm_registry.list_usage_ids().count("default") == 1


def test_switch_llm_tool_during_arun_does_not_deadlock(profile_store, tmp_path):
    """回归对于 #3485：``arun()`` 期间的 ``switch_llm`` 工具调用必须
    不是死锁对话运行时间。

    ``arun()`` 在 (异步) 智能体步长上保持 ConversationState 锁
    while tools execute on worker threads. ``switch_llm()`` used to re-acquire
    that 锁从工具工人那里线程，与已经持有的运行循环死锁并被阻塞等待工具 —— 无观测结果
    从未发出过，对话悬而未决 ``running``.

    智能体在一个步骤中发出切换和结束，因此切换发生在步骤中间（死锁站点）并且运行可以
    完成。
    """
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[
                    MessageToolCall(
                        id="switch_1",
                        name="switch_llm",
                        arguments='{"profile_name": "fast", "reason": "test"}',
                        origin="completion",
                    ),
                    MessageToolCall(
                        id="finish_1",
                        name="finish",
                        arguments='{"message": "done"}',
                        origin="completion",
                    ),
                ],
            ),
        ],
        model="default-model",
        usage_id="test-llm",
    )

    # 解析 BUILT_IN_TOOL_CLASSES 中的工具（无全局注册表写入）。
    agent = Agent(llm=llm, include_default_tools=["FinishTool", "SwitchLLMTool"])
    conv = LocalConversation(agent=agent, workspace=tmp_path, visualizer=None)
    conv.send_message("please switch")

    # 因此，回归表面上表现为快速测试失败，而不是挂起的套件。 在固定路径 arun() 上几乎立
    # 即完成。
    #
    asyncio.run(asyncio.wait_for(conv.arun(), timeout=10))

    assert conv.state.execution_status == ConversationExecutionStatus.FINISHED
    # 切换生效：智能体现在带有“快速”配置文件的模型。
    assert conv.agent.llm.model == "fast-model"


def test_switch_llm_to_subscription_profile_keeps_condenser(
    monkeypatch, empty_profile_store
):
    import openhands.sdk.conversation.impl.local_conversation as local_conversation

    condenser = LLMSummarizingCondenser(
        llm=_make_llm("condenser-model", "condenser"),
        max_size=100,
        keep_first=5,
    )
    conv = LocalConversation(
        agent=Agent(
            llm=_make_llm("default-model", "test-llm"),
            tools=[],
            condenser=condenser,
        ),
        workspace=Path.cwd(),
    )
    assert conv.agent.condenser is condenser

    def fake_create_subscription_llm_from_config(llm: LLM) -> LLM:
        runtime = llm.model_copy()
        if llm.auth_type == "subscription":
            runtime.is_subscription = True
        return runtime

    monkeypatch.setattr(
        local_conversation,
        "create_subscription_llm_from_config",
        fake_create_subscription_llm_from_config,
    )

    conv.switch_llm(
        LLM(
            model="gpt-5.4",
            usage_id="profile:codex",
            auth_type="subscription",
            subscription_vendor="openai",
        )
    )

    assert conv.agent.llm.is_subscription
    # 上下文压缩器必须不禁用订阅 LLMs — the 上下文压缩器自己的 LLM 配置与不同智能体'，因
    # 此保留原样。
    #
    assert conv.agent.condenser is condenser
    assert conv.state.agent.condenser is condenser

    conv.switch_llm(_make_llm("regular-model", "regular"))

    assert conv.agent.llm.model == "regular-model"
    assert conv.agent.condenser is condenser
    assert conv.state.agent.condenser is condenser


def test_switch_llm_replaces_registered_usage_id_after_init(empty_profile_store):
    """#5636: 一旦智能体初始化，``default``就被注册。 发布一个
    usage_id 下的不同配置必须安装它，而不是保留旧的 LLM，并且使用情况的累积指标必须转
    移到新的 LLM。
    """
    # LLMs: 智能体初始化只注册基类 LLMs，而不是 TestLLM。
    original = LLM(model="original-model", api_key=SecretStr("k"))
    conv = LocalConversation(
        agent=Agent(llm=original, tools=[]),
        workspace=Path.cwd(),
    )
    conv.send_message("hi")  # 初始化智能体并注册“默认”
    conv.llm_registry.get("default").metrics.add_cost(0.5)

    # usage_id省略：默认为“default”，注册的槽位。
    conv.switch_llm(LLM(model="switched-model", api_key=SecretStr("k")))

    assert conv.agent.llm.model == "switched-model"
    assert conv.state.agent.llm.model == "switched-model"
    assert conv.llm_registry.get("default") is conv.agent.llm
    stats_metrics = conv.state.stats.usage_to_metrics["default"]
    assert stats_metrics.accumulated_cost == 0.5
    assert conv.agent.llm.metrics is stats_metrics


def test_switch_llm_identical_config_reuses_registered_llm(empty_profile_store):
    """在相同的 usage_id 下重新发布注册的配置将保留
    注册 LLM 对象（及其指标）而不是替换它。
    """
    conv = _make_conversation()
    conv.switch_llm(_make_llm("model-a", "x"))
    registered = conv.llm_registry.get("x")

    conv.switch_llm(_make_llm("model-b", "y"))
    conv.switch_llm(_make_llm("model-a", "x"))

    assert conv.agent.llm is registered
    assert conv.llm_registry.get("x") is registered
