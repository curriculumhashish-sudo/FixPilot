"""集成测试对于对话树：通过真实的 LocalConversation（无 LLM）进行标记、叶、视图、导航
和分支切片分叉。 （＃3747，＃3748）
"""

import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from litellm import ChatCompletionMessageToolCall
from litellm.types.utils import Function
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.context.view import View
from openhands.sdk.conversation import Conversation, LocalConversation
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.event import ActionEvent
from openhands.sdk.event.base import Event
from openhands.sdk.event.condenser import Condensation
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.event.types import ROOT_PARENT_ID, SourceType
from openhands.sdk.event.user_action import PauseEvent
from openhands.sdk.llm import LLM, Message, MessageToolCall, TextContent
from openhands.sdk.tool.schema import Action


def _agent() -> Agent:
    return Agent(
        llm=LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test"),
        tools=[],
    )


def _conversation(tmpdir: str, **kwargs) -> LocalConversation:
    conv = Conversation(
        agent=_agent(),
        persistence_dir=tmpdir,
        workspace=tmpdir,
        visualizer=None,
        **kwargs,
    )
    assert isinstance(conv, LocalConversation)
    return conv


def _emit(conv: LocalConversation, event: Event) -> Event:
    """通过冲压管道排出； 返回事件（id 被保留）。"""
    with conv._state:
        conv._on_event(event)
    return event


def _msg(text: str, source: SourceType = "user") -> MessageEvent:
    role = "user" if source == "user" else "assistant"
    return MessageEvent(
        source=source,
        llm_message=Message(role=role, content=[TextContent(text=text)]),
    )


def _by_id(events, event_id: str) -> Event:
    """通过 id 查找存储的事件。"""
    return next(e for e in events if e.id == event_id)


def _view_ids(conv: LocalConversation) -> list[str]:
    return [e.id for e in conv.state.view.events]


def _ground_truth_view_ids(conv: LocalConversation) -> list[str]:
    """从头开始计算的视图 - 独立于缓存/增量视图。"""
    leaf = conv.state._resolve_active_leaf()
    branch = conv.state.events.path_to_root(leaf)
    return [e.id for e in View.from_events(branch).events]


def test_parent_id_stamped_and_leaf_advances():
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        e0 = _emit(conv, _msg("first"))
        e1 = _emit(conv, _msg("second"))
        e2 = _emit(conv, _msg("third"))

        stored = {e.id: e for e in conv.state.events}
        assert stored[e0.id].parent_id is None  # 根
        assert stored[e1.id].parent_id == e0.id  # 链接到前一个叶子
        assert stored[e2.id].parent_id == e1.id
        assert conv.state.leaf_event_id == e2.id


def test_leaf_event_id_round_trips_through_base_state():
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        _emit(conv, _msg("a"))
        e1 = _emit(conv, _msg("b"))
        conv_id = conv.id
        conv.close()

        resumed = _conversation(tmp, conversation_id=conv_id)
        assert resumed.state.leaf_event_id == e1.id
        # 活动分支完好无损地恢复。
        assert _view_ids(resumed) == [e.id for e in resumed.state.events]


def test_view_reflects_only_the_active_branch():
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        e0 = _emit(conv, _msg("root"))
        e1 = _emit(conv, _msg("a1"))
        e2 = _emit(conv, _msg("a2"))
        assert _view_ids(conv) == [e0.id, e1.id, e2.id]


def test_navigate_then_emit_creates_sibling_branch():
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        e0 = _emit(conv, _msg("root"))
        e1 = _emit(conv, _msg("a1"))
        e2 = _emit(conv, _msg("a2"))  # 分支 A：根 -> a1 -> a2

        conv.navigate_to(e0.id)  # 将 HEAD 移回根
        assert conv.state.leaf_event_id == e0.id
        assert _view_ids(conv) == [e0.id]

        e3 = _emit(conv, _msg("b1"))  # 分支 B 从根上分叉
        assert _by_id(conv.state.events, e3.id).parent_id == e0.id

        # 废弃的分支 A 仍在磁盘上...
        assert e1.id in conv.state.events
        assert e2.id in conv.state.events
        # ...but absent from the active view.
        view_ids = _view_ids(conv)
        assert e1.id not in view_ids and e2.id not in view_ids
        assert view_ids == [e0.id, e3.id]

        # 两个分支都作为兄弟姐妹挂在根上。
        assert _by_id(conv.state.events, e1.id).parent_id == e0.id
        assert _by_id(conv.state.events, e3.id).parent_id == e0.id


@pytest.mark.parametrize(
    "operation",
    [
        lambda conv: conv.navigate_to("nope"),
        lambda conv: conv.fork(from_event_id="nope"),
    ],
    ids=["navigate_to", "fork"],
)
def test_unknown_event_id_raises(operation: Callable[[LocalConversation], object]):
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        _emit(conv, _msg("root"))
        with pytest.raises(ValueError, match="nope"):
            operation(conv)


def test_navigate_to_none_empties_the_active_branch():
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        _emit(conv, _msg("root"))
        _emit(conv, _msg("a1"))

        conv.navigate_to(None)
        assert conv.state.leaf_event_id is None
        assert _view_ids(conv) == []


def test_navigate_to_none_then_emit_starts_a_fresh_root():
    """navigate_to(None)之后，下一个事件是真正的根——不是默默地
    重新设置父级到废弃树枝的叶子上。

    非零存储索引处的标记根登陆具有 parent_id=None，与遗留事件的形状相同； 如果没有明
    确的标记，有效父规则会将其视为遗留子（idx-1），并复活废弃分支到
    活跃视图中。
    """
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        e0 = _emit(conv, _msg("root"))
        _emit(conv, _msg("a1"))  # 分支A：root -> a1，然后放弃

        conv.navigate_to(None)  # 故意空HEAD
        assert _view_ids(conv) == []

        fresh = _emit(conv, _msg("fresh"))  # 非空日志上的新根

        events = conv.state.events
        stored = _by_id(events, fresh.id)
        # 有效父代是 None：真正的根，未链接到 a1。
        assert events._effective_parent_id(events.get_index(fresh.id), stored) is None
        # 活性枝就是新鲜的根； 分支 A 保持在视野之外。
        assert _view_ids(conv) == [fresh.id]
        # 两个根都像兄弟一样挂在 None 上：e0 是真正的根，新鲜事件携带显式的
        # ROOT_PARENT_ID 哨兵值。
        #
        assert _by_id(events, e0.id).parent_id is None
        assert _by_id(events, fresh.id).parent_id == ROOT_PARENT_ID


def test_fork_from_event_slices_the_branch():
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        e0 = _emit(conv, _msg("root"))
        e1 = _emit(conv, _msg("a"))
        _emit(conv, _msg("b"))  # e2，不在切片分支上

        fork = conv.fork(from_event_id=e1.id)

        # 精确复制 path_to_root(e1)，在剪切点设置 HEAD。
        assert [e.id for e in fork.state.events] == [e0.id, e1.id]
        assert fork.state.leaf_event_id == e1.id
        assert _view_ids(fork) == [e0.id, e1.id]

        # 源对话未受影响。
        assert len(conv.state.events) == 3

        # 从切割点继续运行叉子。
        e3 = _emit(fork, _msg("c"))
        assert _by_id(fork.state.events, e3.id).parent_id == e1.id


def test_fork_after_condensation_replays_correctly():
    """从上下文压缩事件分叉会在切片分支上重播它。"""
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        e0 = _emit(conv, _msg("m0"))
        e1 = _emit(conv, _msg("m1"))
        e2 = _emit(conv, _msg("m2"))

        cond = Condensation(
            forgotten_event_ids={e0.id},
            summary="dropped m0",
            llm_response_id="resp-1",
        )
        _emit(conv, cond)

        # 在源上，活动视图已经反映了上下文压缩。
        assert e0.id not in _view_ids(conv)

        fork = conv.fork(from_event_id=cond.id)

        # 复制直到并包括上下文压缩的整个分支...
        assert len(fork.state.events) == 4
        # ...and replaying it drops the forgotten event while keeping the rest.
        fork_view_ids = _view_ids(fork)
        assert e0.id not in fork_view_ids
        assert e1.id in fork_view_ids and e2.id in fork_view_ids


def test_default_fork_is_unchanged_full_copy():
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        e0 = _emit(conv, _msg("root"))
        e1 = _emit(conv, _msg("a1"))
        _emit(conv, _msg("a2"))
        conv.navigate_to(e0.id)  # 分叉前使 HEAD 发散

        fork = conv.fork()  # 否 from_event_id -> 完整副本，HEAD 保留

        assert len(fork.state.events) == len(conv.state.events) == 3
        assert fork.state.leaf_event_id == e0.id  # 源 HEAD 被继承
        assert _view_ids(fork) == [e0.id]
        assert e1.id in fork.state.events  # 废弃的分支也被复制


def test_incremental_view_matches_ground_truth_across_branch_switches():
    """缓存 ``state.view`` 必须等于每一步后从头开始重建。

    读取突变之间的视图会固定增量快速路径并根据 ``View.from_events`` 进行分支切换重建
    。
    """
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)

        e0 = _emit(conv, _msg("root"))
        assert _view_ids(conv) == _ground_truth_view_ids(conv)  # 首先填充
        e1 = _emit(conv, _msg("a1"))
        e2 = _emit(conv, _msg("a2"))
        assert _view_ids(conv) == _ground_truth_view_ids(conv)  # 线性快速路径

        conv.navigate_to(e0.id)  # 分支切换 -> 完全重建
        assert _view_ids(conv) == _ground_truth_view_ids(conv) == [e0.id]

        _emit(conv, _msg("b1"))  # 通过 e0 之外的快速路径扩展同级分支
        assert _view_ids(conv) == _ground_truth_view_ids(conv)

        conv.navigate_to(e2.id)  # 回到废弃的枝叶
        assert _view_ids(conv) == _ground_truth_view_ids(conv) == [e0.id, e1.id, e2.id]


def test_legacy_conversation_resumes_and_continues():
    """没有 parent_id 的事件已持久化作为一个分支加载并继续（恢复）。"""
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp, delete_on_close=False)
        # 直接追加到日志中：绕过打标瓶颈，因此这些事件没有 parent_id，永远也不会推进叶节
        # 点——正是树功能存在的时候写入的数据形状。
        #
        legacy = [_msg(f"legacy-{i}") for i in range(3)]
        for ev in legacy:
            conv.state.events.append(ev)
        conv_id = conv.id
        conv.close()

        resumed = _conversation(tmp, conversation_id=conv_id, delete_on_close=False)
        # 磁盘上没有已持久化叶子，没有 parent_ids...
        assert resumed.state.leaf_event_id is None
        assert all(e.parent_id is None for e in resumed.state.events)
        # ...yet the full linear history is the active branch.
        assert _view_ids(resumed) == [e.id for e in legacy]
        assert _ground_truth_view_ids(resumed) == [e.id for e in legacy]

        # 新事件无缝地延续了上一个遗留事件的链。
        new = _emit(resumed, _msg("after-resume"))
        assert _by_id(resumed.state.events, new.id).parent_id == legacy[-1].id
        assert resumed.state.leaf_event_id == new.id
        assert [e.id for e in resumed.state.events.path_to_root(new.id)] == [
            *(e.id for e in legacy),
            new.id,
        ]


@pytest.mark.parametrize(
    "make_tail",
    [
        pytest.param(
            lambda parent_id: ConversationErrorEvent(
                source="environment",
                parent_id=parent_id,
                code="RuntimeError",
                detail="interrupted startup",
            ),
            id="conversation-error-tail",
        ),
        pytest.param(
            lambda parent_id: ConversationStateUpdateEvent(
                parent_id=parent_id,
                key="execution_status",
                value="idle",
            ),
            id="state-update-tail",
        ),
    ],
)
def test_legacy_resume_with_non_tree_artifact_tail_keeps_history(make_tail):
    """其存储的尾部是非树工件的遗留日志仍然可以完整恢复。

    较新的智能体服务器可以写入 ``ConversationStateUpdateEvent`` 或
    ``ConversationErrorEvent`` 在中断启动期间，将onto一个遗留尾部。 该 artifact 携带
    了  ``parent_id``但是它并不
    是真正的 HEAD必须链接到最后一个真正的遗留事件，而不是被标记为 False  ``__root__``
     这涵盖了所有先前的历史 (#4057)。
    """
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp, delete_on_close=False)
        # 传统的扁平原木（没有parent_id，叶子永远不会前进）——前树形状。
        legacy = [_msg(f"legacy-{i}") for i in range(3)]
        for ev in legacy:
            conv.state.events.append(ev)
        # 正如较新的服务器所写，尾随工件链接到遗留尾部
        # it：带有parent_id但不是树节点。
        conv.state.events.append(make_tail(legacy[-1].id))
        conv_id = conv.id
        conv.close()

        resumed = _conversation(tmp, conversation_id=conv_id, delete_on_close=False)
        assert resumed.state.leaf_event_id is None
        # 工件被跳过； 活动分支是完整的遗留历史记录。
        assert _view_ids(resumed) == [e.id for e in legacy]
        assert _ground_truth_view_ids(resumed) == [e.id for e in legacy]

        # 第一个新事件链接到最后一个旧事件，不一个 False 根。
        new = _emit(resumed, _msg("after-resume"))
        assert _by_id(resumed.state.events, new.id).parent_id == legacy[-1].id
        assert resumed.state.leaf_event_id == new.id
        assert [e.id for e in resumed.state.events.path_to_root(new.id)] == [
            *(e.id for e in legacy),
            new.id,
        ]


@pytest.mark.parametrize(
    "make_tail",
    [
        pytest.param(
            lambda pid: [
                ConversationStateUpdateEvent(parent_id=pid, key="k", value="v"),
                ConversationErrorEvent(
                    source="environment", parent_id=pid, code="E", detail="d"
                ),
                ConversationStateUpdateEvent(parent_id=pid, key="k2", value="v2"),
            ],
            id="multiple-stacked-artifacts",
        ),
        pytest.param(
            lambda pid: [PauseEvent(parent_id=pid)],
            id="tail-type-not-special-cased",
        ),
    ],
)
def test_legacy_resume_never_orphans_history_regardless_of_tail(make_tail):
    """遗留日志上的尾随非树噪声不会孤立先前的历史记录。

    无论新服务器在中断启动期间追加到遗留尾部的任何东西是什么——几个堆叠的组件，或者一
    个事件类型 ``_resolve_active_leaf`` 不特殊处理——第一次
    恢复后的事件必须不被标记为 False ``__root__``：所有遗留事件都必须从新叶 (#4057)
    可达。
    """
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp, delete_on_close=False)
        legacy = [_msg(f"legacy-{i}") for i in range(3)]
        for ev in legacy:
            conv.state.events.append(ev)
        for ev in make_tail(legacy[-1].id):
            conv.state.events.append(ev)
        conv_id = conv.id
        conv.close()

        resumed = _conversation(tmp, conversation_id=conv_id, delete_on_close=False)
        new = _emit(resumed, _msg("after-resume"))
        stored = _by_id(resumed.state.events, new.id)
        reachable = [e.id for e in resumed.state.events.path_to_root(new.id)]

        legacy_ids = [e.id for e in legacy]
        assert stored.parent_id != ROOT_PARENT_ID  # 不是 False 根
        # 每个遗留事件仍然可以按顺序访问（没有孤立事件）。
        assert [i for i in reachable if i in set(legacy_ids)] == legacy_ids
        assert reachable[-1] == new.id


def test_parent_id_round_trips_on_disk_and_root_omits_it():
    """parent_id survives 持久化; 根事件的 JSON 忽略它（附加）。"""
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp, delete_on_close=False)
        e0 = _emit(conv, _msg("root"))
        e1 = _emit(conv, _msg("child"))
        conv_id = conv.id
        persist = Path(conv.state.persistence_dir)  # type: ignore[arg-type]
        conv.close()

        # 字节相加：根事件 (parent_id None) 是已序列化，根本没有密钥； 子事件携带
        # parent_id 指向其父事件。
        #
        root_json = next(persist.rglob(f"event-*-{e0.id}.json")).read_text()
        child_json = next(persist.rglob(f"event-*-{e1.id}.json")).read_text()
        assert '"parent_id"' not in root_json
        assert '"parent_id"' in child_json
        assert e0.id in child_json

        # 并且它能够在往返内存中幸存下来。
        resumed = _conversation(tmp, conversation_id=conv_id, delete_on_close=False)
        stored = {e.id: e for e in resumed.state.events}
        assert stored[e0.id].parent_id is None
        assert stored[e1.id].parent_id == e0.id


def test_fork_from_event_on_an_abandoned_branch():
    """from_event_id 按谱系进行切片，甚至是从不是 HEAD 的分支上切片。"""
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        e0 = _emit(conv, _msg("root"))
        e1 = _emit(conv, _msg("a1"))
        e2 = _emit(conv, _msg("a2"))  # 分支A（将被废弃）

        conv.navigate_to(e0.id)
        _emit(conv, _msg("b1"))  # HEAD 现在在分支 B，A 已被放弃

        # 从 a2 分叉（在废弃的分支上）——独立于 live HEAD。
        fork = conv.fork(from_event_id=e2.id)
        assert [e.id for e in fork.state.events] == [e0.id, e1.id, e2.id]
        assert fork.state.leaf_event_id == e2.id
        assert _view_ids(fork) == _ground_truth_view_ids(fork) == [e0.id, e1.id, e2.id]


def test_append_event_stamps_swapped_event_to_active_leaf_not_storage_tail():
    """未标记的事件（作为 _tree_stamping 下游的钩子交换）是
    标记到 append_event 处的活动叶子 - 不留给 idx-1 回退方案，在导航后会将其链接到废
    弃的分支上。
    """
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        e0 = _emit(conv, _msg("root"))
        _emit(conv, _msg("a1"))
        _emit(conv, _msg("a2"))  # 分支A（废弃）； a2是存储尾部

        conv.navigate_to(e0.id)  # 活动叶子为 e0，但存储尾部为 a2

        swapped = _msg("swapped")  # 全新事件，parent_id 为 None
        with conv._state:
            conv._state.append_event(swapped)

        stored = _by_id(conv.state.events, swapped.id)
        assert stored.parent_id == e0.id  # 活动叶，不是A2（idx - 1）
        assert conv.state.leaf_event_id == swapped.id
        assert _view_ids(conv) == [e0.id, swapped.id]  # 分支 A 保持在视图之外


class _MockAction(Action):
    command: str


def _action_event(call_id: str = "call_1") -> ActionEvent:
    """最小可执行文件 ActionEvent — 等待匹配观测结果。"""
    tool_call = ChatCompletionMessageToolCall(
        id=call_id,
        type="function",
        function=Function(name="test_tool", arguments='{"command": "x"}'),
    )
    return ActionEvent(
        source="agent",
        thought=[TextContent(text="t")],
        action=_MockAction(command="x"),
        tool_name="test_tool",
        tool_call_id=call_id,
        tool_call=MessageToolCall.from_chat_tool_call(tool_call),
        llm_response_id="resp-1",
    )


def test_active_branch_returns_live_path_and_tail():
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        e0 = _emit(conv, _msg("root"))
        _emit(conv, _msg("a1"))
        _emit(conv, _msg("a2"))  # 分支A，待废弃
        conv.navigate_to(e0.id)
        e3 = _emit(conv, _msg("b1"))  # 分支B

        # 只有活路； 废弃的a1/a2除外。
        assert [e.id for e in conv.state.active_branch()] == [e0.id, e3.id]
        # limit 从叶子走回来。
        assert [e.id for e in conv.state.active_branch(limit=1)] == [e3.id]


def test_pending_actions_ignore_abandoned_branch():
    """get_unmatched_actions 在活动分支上删除一个废弃的分支
    孤立的操作 - 因此离开不会留下虚拟的待处理操作。
    """
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        e0 = _emit(conv, _msg("root"))
        pending = _emit(conv, _action_event("call_A"))  # 分支 A 上不匹配

        conv.navigate_to(e0.id)  # 放弃分支A

        # 完整的日志仍然显示孤立的操作......
        assert [
            a.id
            for a in ConversationState.get_unmatched_actions(list(conv.state.events))
        ] == [pending.id]
        # ...but the active branch (what the consumers now read) does not.
        assert ConversationState.get_unmatched_actions(conv.state.active_branch()) == []


def test_navigate_to_none_empties_single_root_tree():
    """navigate_to(None) 即使是单事件树也必须清空，并且下一个事件必须
    成为一根新鲜的根——而不是被束缚在废弃的根上。 （_resolve_active_leaf中的遗产回退方
    案用于复活孤根。）
    """
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        _emit(conv, _msg("only"))
        conv.navigate_to(None)
        assert conv.state.leaf_event_id is None
        assert conv.state.head_is_empty is True
        assert _view_ids(conv) == []

        fresh = _emit(conv, _msg("fresh"))
        assert _by_id(conv.state.events, fresh.id).parent_id == ROOT_PARENT_ID
        assert _view_ids(conv) == [fresh.id]


def test_empty_head_survives_reload():
    """故意的空 HEAD 在保存/重新加载 (head_is_empty) 中持续存在，而不是
    在冷负载时被遗产回退方案复活。
    """
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp, delete_on_close=False)
        _emit(conv, _msg("only"))
        conv.navigate_to(None)
        cid = conv.id
        conv.close()

        resumed = _conversation(tmp, conversation_id=cid, delete_on_close=False)
        assert resumed.state.head_is_empty is True
        assert resumed.state.leaf_event_id is None
        assert _view_ids(resumed) == []


def test_generate_title_reads_active_branch(monkeypatch):
    """generate_title() 从活动分支中提取第一条用户消息，而不是
    废弃分支的消息。
    """
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        _emit(conv, _msg("old root"))
        _emit(conv, _msg("reply", "agent"))  # 2 个事件前缀，因此导航为空
        conv.navigate_to(None)
        _emit(conv, _msg("fresh root"))

        captured: dict = {}

        def _fake_generate(events, llm, max_length=50, *, call_context=None):
            captured["events"] = list(events)
            captured["call_context"] = call_context
            return "title"

        monkeypatch.setattr(
            "openhands.sdk.conversation.impl.local_conversation."
            "generate_conversation_title",
            _fake_generate,
        )
        conv.generate_title()

        texts = [
            c.text
            for e in captured["events"]
            if isinstance(e, MessageEvent)
            for c in e.llm_message.content
            if isinstance(c, TextContent)
        ]
        assert texts == ["fresh root"]
        assert captured["call_context"] is conv.get_llm_call_context()


def test_fork_preserves_empty_head():
    """空 HEAD 对话的完整分叉保持为空（head_is_empty 是
    已复制），而不是复活最后一个事件的遗产回退方案。
    """
    with tempfile.TemporaryDirectory() as tmp:
        conv = _conversation(tmp)
        _emit(conv, _msg("only"))
        conv.navigate_to(None)

        fork = conv.fork()
        assert fork.state.head_is_empty is True
        assert _view_ids(fork) == []
