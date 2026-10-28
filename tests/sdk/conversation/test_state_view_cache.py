"""在 ConversationState 上测试延迟更新、基于水印的视图缓存。"""

import uuid
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.context.view import View
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.event.condenser import Condensation, CondensationRequest
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.llm import LLM
from openhands.sdk.llm.message import Message, TextContent
from openhands.sdk.workspace import LocalWorkspace


@pytest.fixture
def state(tmp_path):
    """创建一个由临时目录支持的最小 ConversationState。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("k"), usage_id="test")
    agent = Agent(llm=llm, tools=[])
    working_dir = tmp_path / "work"
    working_dir.mkdir()
    return ConversationState.create(
        id=uuid.uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir=str(working_dir)),
        persistence_dir=str(tmp_path / "persist"),
    )


def _msg(text: str) -> MessageEvent:
    return MessageEvent(
        llm_message=Message(role="user", content=[TextContent(text=text)]),
        source="user",
    )


def test_fresh_state_has_empty_view(state):
    view = state.view
    assert isinstance(view, View)
    assert len(view.events) == 0


def test_view_updates_after_event_append(state):
    m = _msg("hello")
    state.events.append(m)
    assert len(state.view.events) == 1
    assert state.view.events[0].id == m.id


def test_view_tracks_multiple_appends(state):
    msgs = [_msg(f"msg-{i}") for i in range(5)]
    for m in msgs:
        state.events.append(m)
    assert len(state.view.events) == 5
    assert [e.id for e in state.view.events] == [m.id for m in msgs]


def test_view_matches_full_rebuild(state):
    """增量视图必须产生与 View.from_events 相同的结果。"""
    for i in range(10):
        state.events.append(_msg(f"msg-{i}"))
    incremental_ids = [e.id for e in state.view.events]
    full_ids = [e.id for e in View.from_events(state.events).events]
    assert incremental_ids == full_ids


def test_view_matches_full_rebuild_with_condensation(state):
    """奇偶校验适用于包含上下文压缩的序列。"""
    for i in range(5):
        state.events.append(_msg(f"msg-{i}"))
    condensation = Condensation(
        forgotten_event_ids={state.events[0].id},
        summary="drop first",
        llm_response_id="test-resp",
    )
    state.events.append(condensation)
    incremental_ids = [e.id for e in state.view.events]
    full_ids = [e.id for e in View.from_events(state.events).events]
    assert incremental_ids == full_ids


def test_condensation_applied_incrementally(state):
    m1 = _msg("first")
    m2 = _msg("second")
    m3 = _msg("third")
    state.events.append(m1)
    state.events.append(m2)
    state.events.append(m3)
    assert len(state.view.events) == 3

    condensation = Condensation(
        forgotten_event_ids={m1.id},
        summary="dropped first",
        llm_response_id="test-resp",
    )
    state.events.append(condensation)
    # 视图应反映上下文压缩：m1 已删除
    assert len(state.view.events) == 2
    remaining_ids = {e.id for e in state.view.events}
    assert m1.id not in remaining_ids
    assert m2.id in remaining_ids
    assert m3.id in remaining_ids


def test_condensation_request_sets_flag(state):
    state.events.append(_msg("x"))
    state.events.append(CondensationRequest())
    assert state.view.unhandled_condensation_request is True


def test_hot_path_does_not_call_enforce_properties(state):
    """正常的增量追加绝不能调用 enforce_properties。"""
    call_count = 0
    original = View.enforce_properties

    def counting_enforce(self, all_events):
        nonlocal call_count
        call_count += 1
        return original(self, all_events)

    with patch.object(View, "enforce_properties", counting_enforce):
        for i in range(10):
            state.events.append(_msg(f"msg-{i}"))
        _ = state.view  # 强制懒惰追赶

    assert call_count == 0


def test_rebuild_view_runs_enforce_properties(state):
    """rebuild_view 必须调用 enforce_properties（通过 View.from_events）。"""
    state.events.append(_msg("a"))
    call_count = 0
    original = View.enforce_properties

    def counting_enforce(self, all_events):
        nonlocal call_count
        call_count += 1
        return original(self, all_events)

    with patch.object(View, "enforce_properties", counting_enforce):
        state.rebuild_view()

    assert call_count >= 1


def test_rebuild_view_replaces_cached_instance(state):
    state.events.append(_msg("a"))
    _ = state.view  # 填充缓存
    old_view = state.view

    state.rebuild_view()
    assert state.view is not old_view
    assert len(state.view.events) == 1


def test_rebuild_view_matches_from_events(state):
    for i in range(5):
        state.events.append(_msg(f"msg-{i}"))
    state.events.append(
        Condensation(
            forgotten_event_ids={state.events[0].id},
            summary="drop",
            llm_response_id="test-resp",
        )
    )
    state.rebuild_view()
    rebuilt_ids = [e.id for e in state.view.events]
    fresh_ids = [e.id for e in View.from_events(state.events).events]
    assert rebuilt_ids == fresh_ids


def test_view_idempotent_on_repeated_reads(state):
    """在没有新事件的情况下多次读取视图是无操作的。"""
    state.events.append(_msg("x"))
    v1 = state.view
    v2 = state.view
    assert v1 is v2
    assert len(v1.events) == 1


def test_resume_path_rebuilds_view(tmp_path):
    """恢复已持久化 ConversationState 冷加载视图。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("k"), usage_id="test")
    agent = Agent(llm=llm, tools=[])
    working_dir = tmp_path / "work"
    working_dir.mkdir()
    persist = str(tmp_path / "persist")

    # 创建并填充
    state = ConversationState.create(
        id=uuid.uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir=str(working_dir)),
        persistence_dir=persist,
    )
    state.events.append(_msg("persisted-msg"))
    cid = state.id

    # 恢复到新鲜状态
    resumed = ConversationState.create(
        id=cid,
        agent=agent,
        workspace=LocalWorkspace(working_dir=str(working_dir)),
        persistence_dir=persist,
    )
    assert len(resumed.view.events) == 1
    assert resumed.view.events[0].id == state.events[0].id

    # 验证水印设置正确，以便增量读取在恢复后正常工作（防止 rebuild_view 将水印保留为 0）
    # 。
    #
    resumed.events.append(_msg("after-resume"))
    assert len(resumed.view.events) == 2


def test_rebuild_view_leaves_cache_unchanged_on_error(state):
    """如果 View.from_events 升高，则保留旧的缓存和分支标记。"""
    state.events.append(_msg("pre-error"))
    _ = state.view  # 填充增量缓存
    old_view = state._view
    old_branch_leaf = state._view_branch_leaf

    with patch.object(View, "from_events", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            state.rebuild_view()

    assert state._view is old_view
    assert state._view_branch_leaf == old_branch_leaf
