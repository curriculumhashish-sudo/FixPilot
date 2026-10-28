import json
import types
from pathlib import Path

import pytest

from openhands.sdk import LLM, LocalConversation, OpenHandsAgentSettings
from openhands.sdk.agent import Agent
from openhands.sdk.llm import Message, TextContent, llm_profile_store
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.llm.meta_profile_store import MetaProfile, MetaProfileStore
from openhands.sdk.testing import TestLLM
from openhands.sdk.tool.builtins import (
    ClassifyAndSwitchLLMAction,
    ClassifyAndSwitchLLMExecutor,
    ClassifyAndSwitchLLMObservation,
    ClassifyAndSwitchLLMTool,
)
from openhands.sdk.tool.builtins.classify_and_switch_llm import (
    _recent_messages_text,
    build_classifier_messages,
    build_classifier_prompt,
    parse_class_index,
    parse_direct_model,
    render_direct_prompt,
)


META = {
    "classifier_model": "classifier",
    "classes": [
        {"description": "UI / images", "model": "fast"},
        {"description": "tests", "model": "slow"},
    ],
}

DIRECT_META = {
    "classifier_model": "classifier",
    "prompt_template": (
        "Pick one model.\n\n"
        "{{ model_table }}\n\n"
        "Task:\n{{ instance_text }}\n\n"
        'Return ONLY JSON: {"model": "<exact model name>", "reason": "<short>"}'
    ),
    "model_table": "- GPT-5.4\n- MiniMax-M3",
}


def _make_llm(model: str, usage_id: str) -> LLM:
    return TestLLM.from_messages([], model=model, usage_id=usage_id)


@pytest.fixture()
def meta_store(tmp_path: Path) -> MetaProfileStore:
    meta_dir = tmp_path / "meta-profiles"
    meta_dir.mkdir()
    (meta_dir / "balanced.json").write_text(json.dumps(META), encoding="utf-8")
    return MetaProfileStore(base_dir=meta_dir)


@pytest.fixture()
def profile_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LLMProfileStore:
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    monkeypatch.setattr(llm_profile_store, "_DEFAULT_PROFILE_DIR", profile_dir)
    store = LLMProfileStore(base_dir=profile_dir)
    store.save("fast", _make_llm("fast-model", "fast"))
    store.save("slow", _make_llm("slow-model", "slow"))
    store.save("gpt-5.4", _make_llm("gpt-model", "gpt"))
    store.save("minimax-m3", _make_llm("slow-model", "minimax"))
    store.save("default", _make_llm("default-profile-model", "default-profile"))
    return store


def _make_conversation() -> LocalConversation:
    return LocalConversation(
        agent=Agent(llm=_make_llm("default-model", "default"), tools=[]),
        workspace=Path.cwd(),
    )


def _patch_classifier(
    conversation: LocalConversation,
    monkeypatch: pytest.MonkeyPatch,
    reply: str,
) -> None:
    """使分类器配置文件解析为脚本化的 TestLLM。"""
    real_load = conversation._profile_store.load

    def fake_load(name: str, *, cipher=None):
        if name == "classifier":
            return TestLLM.from_messages(
                [Message(role="assistant", content=[TextContent(text=reply)])],
                usage_id="classifier",
            )
        return real_load(name, cipher=cipher)

    monkeypatch.setattr(conversation._profile_store, "load", fake_load)


# ── 纯粹的帮手──────────────────────────────────────────────────────────


def test_build_classifier_prompt_lists_categories() -> None:
    from openhands.sdk.llm.meta_profile_store import MetaProfile

    prompt = build_classifier_prompt(MetaProfile.model_validate(META))
    assert prompt.startswith("You are a model-routing classifier.")
    assert "1. UI / images" in prompt
    assert "2. tests" in prompt
    assert "respond with 0" in prompt.lower()


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("1", 1),
        ("2", 2),
        ("0", 0),
        ("9", 0),  # 超出范围 -> 不匹配
        ("none", 0),  # 没有整数 -> 不匹配
        ("Category 2 fits best", 2),
    ],
)
def test_parse_class_index(reply: str, expected: int) -> None:
    assert parse_class_index(reply, num_classes=2) == expected


def test_render_direct_prompt_replaces_supported_placeholders() -> None:
    from openhands.sdk.llm.meta_profile_store import MetaProfile

    prompt = render_direct_prompt(
        MetaProfile.model_validate(DIRECT_META),
        "user: add parser tests",
    )

    # 渲染后的body不再包含系统前缀； 它存在于build_classifier_messages组装的系统消息中。
    #
    assert "You are a model-routing classifier." not in prompt
    assert "{{" not in prompt
    assert "- GPT-5.4" in prompt
    assert "user: add parser tests" in prompt


def test_build_classifier_messages_class_mode_has_system_and_user() -> None:
    from openhands.sdk.llm.meta_profile_store import MetaProfile

    messages = build_classifier_messages(MetaProfile.model_validate(META), "user: hi")

    assert [m.role for m in messages] == ["system", "user"]
    system_text = "".join(
        c.text for c in messages[0].content if isinstance(c, TextContent)
    )
    user_text = "".join(
        c.text for c in messages[1].content if isinstance(c, TextContent)
    )
    assert system_text.startswith("You are a model-routing classifier.")
    assert "1. UI / images" in system_text
    assert "user: hi" in user_text
    assert "Category number:" in user_text


def test_build_classifier_messages_direct_mode_has_system_and_user() -> None:
    from openhands.sdk.llm.meta_profile_store import MetaProfile

    messages = build_classifier_messages(
        MetaProfile.model_validate(DIRECT_META), "user: add parser tests"
    )

    # 直接路由不得发送仅系统请求：某些提供程序 (e.g. MiniMax) 当没有用户轮到时拒绝“聊天
    # 内容为空”。
    #
    assert [m.role for m in messages] == ["system", "user"]
    system_text = "".join(
        c.text for c in messages[0].content if isinstance(c, TextContent)
    )
    user_text = "".join(
        c.text for c in messages[1].content if isinstance(c, TextContent)
    )
    assert system_text == "You are a model-routing classifier."
    assert "user: add parser tests" in user_text
    assert "- GPT-5.4" in user_text
    assert user_text  # 非空


@pytest.mark.parametrize(
    "reply,expected",
    [
        ('{"model": "GPT-5.4", "reason": "qa"}', "GPT-5.4"),
        ('```json\n{"model": "MiniMax-M3", "reason": "tests"}\n```', "MiniMax-M3"),
        ("I choose GPT-5.4 for this task", "GPT-5.4"),
        ('{"model": "unknown"}', None),
    ],
)
def test_parse_direct_model(reply: str, expected: str | None) -> None:
    assert parse_direct_model(reply, ["GPT-5.4", "MiniMax-M3"]) == expected


def test_parse_direct_model_matches_saved_profile_names_case_insensitively() -> None:
    assert parse_direct_model('{"model": "GPT-5.4"}', ["gpt-5.4"]) == "gpt-5.4"
    assert parse_direct_model('{"model": "MiniMax-M3"}', ["minimax-m3"]) == (
        "minimax-m3"
    )


def test_recent_messages_text_takes_last_n() -> None:
    from openhands.sdk.event.llm_convertible.message import MessageEvent

    events = [
        MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text=f"m{i}")]),
        )
        for i in range(8)
    ]
    conv = types.SimpleNamespace(state=types.SimpleNamespace(events=events))

    text = _recent_messages_text(conv, limit=3)  # type: ignore[arg-type]
    assert text == "user: m5\nuser: m6\nuser: m7"


# ── create() ──────────────────────────────────────────────────────────────


def test_create_falls_back_to_first_when_no_active_profile(
    meta_store: MetaProfileStore,
) -> None:
    # “平衡”是唯一的配置文件，因此它是第一个解决的配置文件。 解析会延迟到调用时间，因此
    # 请直接检查解析器。
    #
    tool = ClassifyAndSwitchLLMTool.create(meta_profile_store=meta_store)[0]
    assert isinstance(tool.executor, ClassifyAndSwitchLLMExecutor)
    assert tool.executor._resolve_meta_profile().classifier_model == "classifier"


def test_create_picks_alphabetically_first_meta_profile(
    meta_store: MetaProfileStore,
) -> None:
    # 添加第二个配置文件，其名称排在“平衡”之前。
    other = dict(META)
    other["classifier_model"] = "other-classifier"
    (Path(meta_store.base_dir) / "aaa.json").write_text(
        json.dumps(other), encoding="utf-8"
    )
    assert meta_store.list()[0] == "aaa"
    tool = ClassifyAndSwitchLLMTool.create(meta_profile_store=meta_store)[0]
    assert isinstance(tool.executor, ClassifyAndSwitchLLMExecutor)
    assert tool.executor._resolve_meta_profile().classifier_model == "other-classifier"


def test_create_does_not_touch_disk_when_no_meta_profiles_exist(
    tmp_path: Path,
) -> None:
    # 延迟解决方案：create() 不得读取存储，因此空（或丢失）元配置文件目录无法中断代理/对
    # 话启动。
    #
    empty_store = MetaProfileStore(base_dir=tmp_path / "empty")
    tools = ClassifyAndSwitchLLMTool.create(meta_profile_store=empty_store)
    assert len(tools) == 1
    assert isinstance(tools[0].executor, ClassifyAndSwitchLLMExecutor)


def test_create_does_not_load_missing_active_meta_profile(
    meta_store: MetaProfileStore,
) -> None:
    # 悬空的 active_meta_profile 不得在 create() 时间引发。
    tool = ClassifyAndSwitchLLMTool.create(
        active_meta_profile="does-not-exist", meta_profile_store=meta_store
    )[0]
    assert isinstance(tool.executor, ClassifyAndSwitchLLMExecutor)


def test_create_rejects_unknown_params(meta_store: MetaProfileStore) -> None:
    with pytest.raises(ValueError):
        ClassifyAndSwitchLLMTool.create(
            active_meta_profile="balanced",
            meta_profile_store=meta_store,
            bogus=1,
        )


def test_create_loads_meta_profile(meta_store: MetaProfileStore) -> None:
    tool = ClassifyAndSwitchLLMTool.create(
        active_meta_profile="balanced", meta_profile_store=meta_store
    )[0]
    assert tool.name == "route_task_to_model"
    assert isinstance(tool.executor, ClassifyAndSwitchLLMExecutor)
    assert tool.executor._resolve_meta_profile().classifier_model == "classifier"


def test_create_prefers_inline_meta_profile_over_filesystem(tmp_path: Path) -> None:
    empty_store = MetaProfileStore(base_dir=tmp_path / "empty")
    tool = ClassifyAndSwitchLLMTool.create(
        active_meta_profile="cloud-router",
        meta_profile=DIRECT_META,
        meta_profile_store=empty_store,
    )[0]

    assert isinstance(tool.executor, ClassifyAndSwitchLLMExecutor)
    assert tool.executor._resolve_meta_profile() == MetaProfile.model_validate(
        DIRECT_META
    )


def test_resolve_prefers_store_over_stale_inline_blob(tmp_path: Path) -> None:
    """当设置了有效名称时，商店具有权威性。

    回归对于内联斑点分歧：激活烘焙内联
    ``meta_profile`` blob，但仅更改活动名称的后续 ``PATCH /api/settings`` 不得保留与
    过时 blob 的路由。 设置名称后，
    执行器按名称从存储中加载元配置文件； 当存储无法解析名称时，内联 blob 只是回退方案
     (e.g. 磁盘上没有存储的云运行时）。
    """
    meta_dir = tmp_path / "meta-profiles"
    meta_dir.mkdir()
    profile_a = dict(META)
    profile_a["classifier_model"] = "classifier-a"
    profile_b = dict(META)
    profile_b["classifier_model"] = "classifier-b"
    (meta_dir / "a.json").write_text(json.dumps(profile_a), encoding="utf-8")
    (meta_dir / "b.json").write_text(json.dumps(profile_b), encoding="utf-8")
    store = MetaProfileStore(base_dir=meta_dir)

    # 模拟激活“a”：名称集 AND 内联 blob 烘焙（配置文件 a）。
    tool = ClassifyAndSwitchLLMTool.create(
        active_meta_profile="a",
        meta_profile=MetaProfile.model_validate(profile_a),
        meta_profile_store=store,
    )[0]
    assert isinstance(tool.executor, ClassifyAndSwitchLLMExecutor)
    assert tool.executor._resolve_meta_profile().classifier_model == "classifier-a"

    # 现在，只有活动名称更改为“b”（PATCH /api/settings)，但内联 blob 仍然是配置文件 a 的
    # （陈旧）。 商店一定会赢。
    #
    stale = ClassifyAndSwitchLLMTool.create(
        active_meta_profile="b",
        meta_profile=MetaProfile.model_validate(profile_a),
        meta_profile_store=store,
    )[0]
    assert isinstance(stale.executor, ClassifyAndSwitchLLMExecutor)
    assert stale.executor._resolve_meta_profile().classifier_model == "classifier-b"

    # 并且会反映覆盖活动文件（没有过时的内联 blob 获胜）。
    profile_a_updated = dict(profile_a)
    profile_a_updated["classifier_model"] = "classifier-a-prime"
    (meta_dir / "a.json").write_text(json.dumps(profile_a_updated), encoding="utf-8")
    overwritten = ClassifyAndSwitchLLMTool.create(
        active_meta_profile="a",
        meta_profile=MetaProfile.model_validate(profile_a),
        meta_profile_store=store,
    )[0]
    assert isinstance(overwritten.executor, ClassifyAndSwitchLLMExecutor)
    assert (
        overwritten.executor._resolve_meta_profile().classifier_model
        == "classifier-a-prime"
    )


def test_create_uses_oh_persistence_dir_meta_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    meta_dir = tmp_path / "meta-profiles"
    meta_dir.mkdir()
    (meta_dir / "balanced.json").write_text(json.dumps(META), encoding="utf-8")
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path))

    tool = ClassifyAndSwitchLLMTool.create(active_meta_profile="balanced")[0]

    assert isinstance(tool.executor, ClassifyAndSwitchLLMExecutor)
    assert tool.executor._resolve_meta_profile().classifier_model == "classifier"


# ── 执行人────────────────────────────────────────────────────────────


def _register_tool(
    conversation: LocalConversation, meta_store: MetaProfileStore
) -> None:
    tool = ClassifyAndSwitchLLMTool.create(
        active_meta_profile="balanced", meta_profile_store=meta_store
    )[0]
    conversation._ensure_agent_ready()
    conversation.agent.add_runtime_tools([tool])


def test_executor_switches_to_matched_class(
    profile_store, meta_store, monkeypatch
) -> None:
    conversation = _make_conversation()
    _register_tool(conversation, meta_store)
    _patch_classifier(conversation, monkeypatch, reply="1")

    obs = conversation.execute_tool("route_task_to_model", ClassifyAndSwitchLLMAction())

    assert isinstance(obs, ClassifyAndSwitchLLMObservation)
    assert not obs.is_error
    assert obs.model == "fast"
    assert obs.chosen_class == "UI / images"
    assert conversation.agent.llm.model == "fast-model"


def test_executor_uses_inline_cloud_llms_without_profile_store(tmp_path) -> None:
    conversation = _make_conversation()
    conversation._profile_store = LLMProfileStore(base_dir=tmp_path / "empty-profiles")
    classifier = TestLLM.from_messages(
        [Message(role="assistant", content=[TextContent(text="1")])],
        model="classifier-model",
        usage_id="classifier",
    )
    tool = ClassifyAndSwitchLLMTool.create(
        active_meta_profile="cloud-router",
        meta_profile=META,
        meta_profile_llms={
            "classifier": classifier,
            "fast": _make_llm("cloud-fast-model", "fast"),
            "slow": _make_llm("cloud-slow-model", "slow"),
        },
        meta_profile_store=MetaProfileStore(base_dir=tmp_path / "empty-meta"),
    )[0]
    conversation._ensure_agent_ready()
    conversation.agent.add_runtime_tools([tool])

    obs = conversation.execute_tool("route_task_to_model", ClassifyAndSwitchLLMAction())

    assert isinstance(obs, ClassifyAndSwitchLLMObservation)
    assert not obs.is_error
    assert obs.model == "fast"
    assert conversation.agent.llm.model == "cloud-fast-model"


def test_classifier_call_is_accounted_in_conversation_stats(
    profile_store, meta_store, monkeypatch
) -> None:
    """分类器的完成必须通过对话注册表。

    回归对于预算绕过漏洞：分类器 LLM 需要在 ``conversation.llm_registry``（使用稳定使
    用 ID）下注册，其词/token 和成本才能计
    入 ``conversation_stats`` 并计数
    ``max_budget_per_run`` — 未注册的 LLM 会在账本上花掉。
    """
    conversation = _make_conversation()
    _register_tool(conversation, meta_store)
    _patch_classifier(conversation, monkeypatch, reply="1")

    usage_id = "classifier:classifier"
    assert usage_id not in conversation.conversation_stats.usage_to_metrics

    obs = conversation.execute_tool("route_task_to_model", ClassifyAndSwitchLLMAction())

    assert isinstance(obs, ClassifyAndSwitchLLMObservation)
    assert not obs.is_error
    # 分类器 LLM 现在已由统计数据注册和跟踪，因此其支出包含在组合（预算强制）指标中。
    #
    assert usage_id in conversation.llm_registry.list_usage_ids()
    assert usage_id in conversation.conversation_stats.usage_to_metrics


def test_classifier_call_receives_conversation_call_context(
    profile_store, meta_store, monkeypatch
) -> None:
    """分类器完成必须携带对话的调用上下文。

    Regression: 分类器 LLM 无法从 ``Agent.step()`` 到达，因此
    没有其他线程上下文来完成它。 没有明确的
    ``call_context`` 调用不会发送 ``x-litellm-session-id`` 标头，并且不会参与对话的提
    示词缓存。
    """
    conversation = _make_conversation()
    _register_tool(conversation, meta_store)

    seen: list[object] = []

    real_load = conversation._profile_store.load

    class RecordingClassifier(TestLLM):
        __test__ = False

        def completion(self, messages, *args, **kwargs):
            seen.append(kwargs.get("call_context"))
            return super().completion(messages, *args, **kwargs)

    def fake_load(name: str, *, cipher=None):
        if name != "classifier":
            return real_load(name, cipher=cipher)
        return RecordingClassifier.from_messages(
            [Message(role="assistant", content=[TextContent(text="1")])],
            usage_id="classifier",
        )

    monkeypatch.setattr(conversation._profile_store, "load", fake_load)

    obs = conversation.execute_tool("route_task_to_model", ClassifyAndSwitchLLMAction())

    assert isinstance(obs, ClassifyAndSwitchLLMObservation)
    assert not obs.is_error
    expected = conversation.get_llm_call_context()
    assert seen == [expected]
    assert expected.session_id == str(conversation._state.id)


def test_repeated_routing_reuses_one_classifier_usage_bucket(
    profile_store, meta_store, monkeypatch
) -> None:
    """第二个路由调用必须重用缓存的分类器，而不是重新注册。"""
    conversation = _make_conversation()
    _register_tool(conversation, meta_store)
    _patch_classifier(conversation, monkeypatch, reply="1")

    conversation.execute_tool("route_task_to_model", ClassifyAndSwitchLLMAction())
    conversation.execute_tool("route_task_to_model", ClassifyAndSwitchLLMAction())

    usage_ids = conversation.llm_registry.list_usage_ids()
    assert usage_ids.count("classifier:classifier") == 1


def test_executor_errors_when_no_class_matches(
    profile_store, meta_store, monkeypatch
) -> None:
    # 分类器返回 0（没有匹配的类别）：该工具必须大声失败，而不是默默地路由到默认模型。
    # 对话的 LLM 保持不变。
    #
    conversation = _make_conversation()
    _register_tool(conversation, meta_store)
    _patch_classifier(conversation, monkeypatch, reply="0")

    obs = conversation.execute_tool("route_task_to_model", ClassifyAndSwitchLLMAction())

    assert isinstance(obs, ClassifyAndSwitchLLMObservation)
    assert obs.is_error
    assert obs.model is None
    assert obs.chosen_class is None
    assert conversation.agent.llm.model == "default-model"


def test_executor_direct_prompt_switches_to_selected_model(
    profile_store, tmp_path, monkeypatch
) -> None:
    meta_dir = tmp_path / "direct-meta-profiles"
    meta_dir.mkdir()
    (meta_dir / "pareto.json").write_text(json.dumps(DIRECT_META), encoding="utf-8")
    direct_store = MetaProfileStore(base_dir=meta_dir)
    conversation = _make_conversation()
    tool = ClassifyAndSwitchLLMTool.create(
        active_meta_profile="pareto", meta_profile_store=direct_store
    )[0]
    conversation._ensure_agent_ready()
    conversation.agent.add_runtime_tools([tool])
    _patch_classifier(conversation, monkeypatch, reply='{"model": "MiniMax-M3"}')

    obs = conversation.execute_tool("route_task_to_model", ClassifyAndSwitchLLMAction())

    assert isinstance(obs, ClassifyAndSwitchLLMObservation)
    assert not obs.is_error
    assert obs.model == "minimax-m3"
    assert obs.chosen_class == "model: minimax-m3"
    assert conversation.agent.llm.model == "slow-model"


def test_executor_direct_prompt_errors_when_model_is_unknown(
    profile_store, tmp_path, monkeypatch
) -> None:
    # 分类器回复无法解析为已保存的配置文件：该工具必须大声失败，而不是默默地路由到默认模
    # 型。
    #
    meta_dir = tmp_path / "direct-meta-profiles"
    meta_dir.mkdir()
    (meta_dir / "pareto.json").write_text(json.dumps(DIRECT_META), encoding="utf-8")
    direct_store = MetaProfileStore(base_dir=meta_dir)
    conversation = _make_conversation()
    tool = ClassifyAndSwitchLLMTool.create(
        active_meta_profile="pareto", meta_profile_store=direct_store
    )[0]
    conversation._ensure_agent_ready()
    conversation.agent.add_runtime_tools([tool])
    _patch_classifier(conversation, monkeypatch, reply='{"model": "unknown"}')

    obs = conversation.execute_tool("route_task_to_model", ClassifyAndSwitchLLMAction())

    assert isinstance(obs, ClassifyAndSwitchLLMObservation)
    assert obs.is_error
    assert obs.model is None
    assert obs.chosen_class is None
    assert conversation.agent.llm.model == "default-model"


def test_executor_errors_when_classifier_profile_missing(
    profile_store, meta_store
) -> None:
    conversation = _make_conversation()
    _register_tool(conversation, meta_store)
    # 没有保存“分类器”配置文件，也没有补丁 -> 加载失败。

    obs = conversation.execute_tool("route_task_to_model", ClassifyAndSwitchLLMAction())

    assert obs.is_error
    assert "classifier" in obs.text
    assert conversation.agent.llm.model == "default-model"


def test_executor_errors_when_target_profile_missing(
    profile_store, meta_store, monkeypatch
) -> None:
    conversation = _make_conversation()
    _register_tool(conversation, meta_store)
    # 分类器选择类别 2 ->“慢”，但将其从存储中删除。
    (Path(profile_store.base_dir) / "slow.json").unlink()
    _patch_classifier(conversation, monkeypatch, reply="2")

    obs = conversation.execute_tool("route_task_to_model", ClassifyAndSwitchLLMAction())

    assert isinstance(obs, ClassifyAndSwitchLLMObservation)
    assert obs.is_error
    assert obs.model == "slow"
    assert "not found" in obs.text


def test_executor_errors_when_no_meta_profile_available(
    profile_store, tmp_path
) -> None:
    # 空存储 + 无活动配置文件：调用（而非启动）报告错误。
    empty_store = MetaProfileStore(base_dir=tmp_path / "empty")
    conversation = _make_conversation()
    tool = ClassifyAndSwitchLLMTool.create(meta_profile_store=empty_store)[0]
    conversation._ensure_agent_ready()
    conversation.agent.add_runtime_tools([tool])

    obs = conversation.execute_tool("route_task_to_model", ClassifyAndSwitchLLMAction())

    assert obs.is_error
    assert "no meta-profile" in obs.text.lower()
    assert conversation.agent.llm.model == "default-model"


def test_executor_errors_when_active_meta_profile_missing(
    profile_store, meta_store
) -> None:
    # 悬空active_meta_profile：调用报告错误，没有崩溃。
    conversation = _make_conversation()
    tool = ClassifyAndSwitchLLMTool.create(
        active_meta_profile="does-not-exist", meta_profile_store=meta_store
    )[0]
    conversation._ensure_agent_ready()
    conversation.agent.add_runtime_tools([tool])

    obs = conversation.execute_tool("route_task_to_model", ClassifyAndSwitchLLMAction())

    assert obs.is_error
    assert "resolve" in obs.text.lower()


def test_missing_active_meta_profile_does_not_break_startup(
    meta_store, monkeypatch
) -> None:
    # 延迟负载的全部要点：丢失的活动元配置文件不得中断 _ensure_agent_ready() / 对话启动
    # 。
    #
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(meta_store.base_dir.parent))
    agent = OpenHandsAgentSettings(
        llm=_make_llm("default-model", "default"),
        tools=[],
        enable_classify_and_switch_llm_tool=True,
        active_meta_profile="does-not-exist",
    ).create_agent()
    conversation = LocalConversation(agent=agent, workspace=Path.cwd())

    # 即使活动元配置文件不存在也不得引发。
    conversation._ensure_agent_ready()

    assert any(t.name == "ClassifyAndSwitchLLMTool" for t in agent.tools)


# ── create_agent接线──────────────────────────────────────────────────────


def test_create_agent_adds_tool_when_enabled(meta_store, monkeypatch) -> None:
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(meta_store.base_dir.parent))
    agent = OpenHandsAgentSettings(
        llm=_make_llm("default-model", "default"),
        enable_classify_and_switch_llm_tool=True,
        active_meta_profile="balanced",
    ).create_agent()

    assert any(t.name == "ClassifyAndSwitchLLMTool" for t in agent.tools)


def test_create_agent_passes_inline_meta_profile_without_filesystem(tmp_path) -> None:
    agent = OpenHandsAgentSettings(
        llm=_make_llm("default-model", "default"),
        enable_classify_and_switch_llm_tool=True,
        active_meta_profile="cloud-router",
        meta_profile=MetaProfile.model_validate(DIRECT_META),
    ).create_agent()

    tool = next(t for t in agent.tools if t.name == "ClassifyAndSwitchLLMTool")
    assert MetaProfile.model_validate(tool.params["meta_profile"]) == (
        MetaProfile.model_validate(DIRECT_META)
    )


def test_create_agent_passes_inline_cloud_llms() -> None:
    inline_llm = _make_llm("cloud-model", "cloud")
    agent = OpenHandsAgentSettings(
        llm=_make_llm("default-model", "default"),
        enable_classify_and_switch_llm_tool=True,
        active_meta_profile="cloud-router",
        meta_profile=MetaProfile.model_validate(DIRECT_META),
        meta_profile_llms={"classifier": inline_llm},
    ).create_agent()

    tool = next(t for t in agent.tools if t.name == "ClassifyAndSwitchLLMTool")
    assert tool.params["meta_profile_llms"]["classifier"] == inline_llm


def test_create_agent_adds_tool_when_enabled_without_active_profile(
    meta_store, monkeypatch
) -> None:
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(meta_store.base_dir.parent))
    # 否 active_meta_profile：该工具仍处于连接状态并解决第一个问题。
    agent = OpenHandsAgentSettings(
        llm=_make_llm("default-model", "default"),
        enable_classify_and_switch_llm_tool=True,
    ).create_agent()

    assert any(t.name == "ClassifyAndSwitchLLMTool" for t in agent.tools)


def test_create_agent_omits_tool_when_disabled() -> None:
    agent = OpenHandsAgentSettings(
        llm=_make_llm("default-model", "default"),
    ).create_agent()

    assert not any(t.name == "ClassifyAndSwitchLLMTool" for t in agent.tools)
