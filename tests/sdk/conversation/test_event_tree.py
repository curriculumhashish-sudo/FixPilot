"""单元测试用于 EventLog 树助手和反向兼容规则 (#3747)。"""

import pytest
from pydantic import ValidationError

from openhands.sdk.conversation.event_store import ROOT_PARENT_ID, EventLog
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.io.memory import InMemoryFileStore
from openhands.sdk.llm import Message, TextContent


def test_event_id_cannot_equal_reserved_root_sentinel():
    """任何事件都不能将保留的 ROOT_PARENT_ID 作为其 id，否则其子事件
    将被读作无父项（parent_id == ROOT_PARENT_ID 表示“根”）。"""
    with pytest.raises(ValidationError):
        _event(ROOT_PARENT_ID)


def _event(event_id: str, parent_id: str | None = None) -> MessageEvent:
    return MessageEvent(
        id=event_id,
        parent_id=parent_id,
        llm_message=Message(role="user", content=[TextContent(text=event_id)]),
        source="user",
    )


def _log(*events: MessageEvent) -> EventLog:
    log = EventLog(InMemoryFileStore())
    for event in events:
        log.append(event)
    return log


def _branched_log() -> EventLog:
    """共享树：a -> b -> c 和 a -> d -> e（b/d 是兄弟）。"""
    return _log(
        _event("a"),
        _event("b", parent_id="a"),
        _event("c", parent_id="b"),
        _event("d", parent_id="a"),
        _event("e", parent_id="d"),
    )


@pytest.mark.parametrize("as_event", [False, True], ids=["by-id", "by-event"])
@pytest.mark.parametrize("target, expected", [("a", True), ("missing", False)])
def test_contains_accepts_event_id_or_event(as_event, target, expected):
    log = _log(_event("a"))
    item = _event(target) if as_event else target
    assert (item in log) is expected


@pytest.mark.parametrize(
    "leaf, expected",
    [
        (None, []),
        ("a", ["a"]),
        ("c", ["a", "b", "c"]),
        ("e", ["a", "d", "e"]),  # b->c 兄弟分支被排除
    ],
)
def test_path_to_root(leaf, expected):
    assert [e.id for e in _branched_log().path_to_root(leaf)] == expected


def test_path_to_root_cycle_raises():
    # 模拟已损坏的已持久化事件，绕过附加验证。
    log = _log(_event("a"), _event("b", parent_id="a"))
    log._event_cache[0] = _event("a", parent_id="b")
    with pytest.raises(ValueError, match="Cycle in event tree"):
        log.path_to_root("a")


@pytest.mark.parametrize("parent_id", ["missing", "a"], ids=["unknown", "self"])
def test_append_rejects_parent_that_does_not_exist(parent_id):
    log = EventLog(InMemoryFileStore())

    with pytest.raises(ValueError, match="Parent event .* does not exist"):
        log.append(_event("a", parent_id=parent_id))


def test_append_accepts_explicit_root_parent():
    log = _log(_event("a"), _event("b", parent_id=ROOT_PARENT_ID))

    assert log[1].parent_id == ROOT_PARENT_ID


def test_path_to_root_unknown_leaf_raises():
    with pytest.raises(KeyError):
        _log(_event("a")).path_to_root("nope")


def test_legacy_events_form_a_single_linear_branch():
    """没有 parent_id 的事件解析为线性 idx 链（不重写）。"""
    # 所有 parent_id 默认为 None -> 有效父规则行走 idx-1。
    log = _log(_event("a"), _event("b"), _event("c"))

    assert [e.id for e in log.path_to_root("c")] == ["a", "b", "c"]


@pytest.mark.parametrize(
    "idx, expected",
    [
        (0, None),  # 正版root
        (1, "a"),  # 传统线性链 (idx - 1)
        (2, "a"),  # 显式父级胜过 idx - 1
    ],
)
def test_effective_parent_id_rule(idx, expected):
    # idx 0, 1 是遗留的（没有明确的父级）； idx 2 带有 parent_id="a"。
    log = _log(_event("a"), _event("b"), _event("c", parent_id="a"))
    assert log._effective_parent_id(idx, log[idx]) == expected
