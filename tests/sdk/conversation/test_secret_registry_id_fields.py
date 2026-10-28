"""机密屏蔽必须保持 id 字段不变。

短路机密可以发生在随机 UUID 内。 如果屏蔽重写了 ID，则事件文件名不再与
``EVENT_NAME_RE`` 匹配，因此 ``EventLog`` 无法重新加载对话
。 屏蔽的 ``tool_call_id`` 或 ``action_id`` 也会破坏 LLM 请求中的工具调用配对。
"""

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel

from openhands.sdk.conversation.event_store import EventLog
from openhands.sdk.conversation.secret_registry import SecretRegistry
from openhands.sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    Condensation,
    EventID,
    HookExecutionEvent,
    LLMCompletionLogEvent,
    MessageEvent,
    ObservationEvent,
    UserRejectObservation,
)
from openhands.sdk.event.acp_tool_call import ACPToolCallEvent
from openhands.sdk.event.security import SecurityAnalysisEvent
from openhands.sdk.io.local import LocalFileStore
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.tool.builtins.finish import FinishObservation


SECRET = "a1b"
MASK = "<secret-hidden>"
ID = "fa1b4e36-bdd7-42bf-99df-e184c9dc0d9a"
TEXT = f"text {SECRET}"


def _registry() -> SecretRegistry:
    registry = SecretRegistry()
    registry.update_secrets({"SHORT": SECRET})
    registry.get_secret_value("SHORT")  # 解析 -> 跟踪掩码
    return registry


def _message(parent_id: str | None) -> MessageEvent:
    return MessageEvent(
        source="user",
        parent_id=parent_id,
        llm_message=Message(role="user", content=[TextContent(text="hi")]),
    )


def _tool_call() -> MessageToolCall:
    return MessageToolCall(id=ID, name="tool", arguments="{}", origin="completion")


def test_masked_event_reloads_from_disk(tmp_path):
    """错误报告的重现：屏蔽后必须重新加载日志。"""
    log = EventLog(LocalFileStore(str(tmp_path)))
    first = _message(None)
    log.append(first)
    analysis = _registry().mask_secrets_in_model(
        SecurityAnalysisEvent(
            id=ID,
            parent_id=first.id,
            analyzer="LLMSecurityAnalyzer",
            policy="NeverConfirm",
            risks={},
        )
    )
    log.append(analysis)
    last = _message(analysis.id)
    log.append(last)

    assert analysis.id == ID
    assert EventLog(LocalFileStore(str(tmp_path))).get_index(last.id) == 2


# 每种情况：每个 id 字段中包含 ``ID`` 的事件、id 字段名称以及包含 ``TEXT`` 且仍必须屏蔽
# 的文本字段的 getter。
#
_CASES: list[tuple[Any, list[str], Callable[[Any], Any]]] = [
    (
        SecurityAnalysisEvent(
            id=ID, parent_id=ID, analyzer=TEXT, policy="NeverConfirm", risks={}
        ),
        ["id", "parent_id"],
        lambda e: e.analyzer,
    ),
    (
        ActionEvent(
            thought=[TextContent(text="thinking")],
            reasoning_content=TEXT,
            tool_name="tool",
            tool_call_id=ID,
            tool_call=_tool_call(),
            llm_response_id=ID,
        ),
        ["tool_call_id", "llm_response_id"],
        lambda e: e.reasoning_content,
    ),
    (
        MessageEvent(
            source="agent",
            llm_message=Message(role="assistant", content=[TextContent(text=TEXT)]),
            llm_response_id=ID,
        ),
        ["llm_response_id"],
        lambda e: e.llm_message.content[0].text,
    ),
    (
        ObservationEvent(
            observation=FinishObservation.from_text(TEXT),
            tool_name="tool",
            tool_call_id=ID,
            action_id=ID,
        ),
        ["tool_call_id", "action_id"],
        lambda e: e.observation.text,
    ),
    (
        UserRejectObservation(
            tool_name="tool", tool_call_id=ID, action_id=ID, rejection_reason=TEXT
        ),
        ["tool_call_id", "action_id"],
        lambda e: e.rejection_reason,
    ),
    (
        AgentErrorEvent(tool_name="tool", tool_call_id=ID, error=TEXT),
        ["tool_call_id"],
        lambda e: e.error,
    ),
    (
        ACPToolCallEvent(tool_call_id=ID, title=TEXT),
        ["tool_call_id"],
        lambda e: e.title,
    ),
    (
        Condensation(forgotten_event_ids={ID}, llm_response_id=ID, summary=TEXT),
        ["forgotten_event_ids", "llm_response_id"],
        lambda e: e.summary,
    ),
    (
        HookExecutionEvent(
            hook_event_type="PreToolUse",
            hook_command="hook.sh",
            success=True,
            exit_code=0,
            stdout=TEXT,
            action_id=ID,
            message_id=ID,
        ),
        ["action_id", "message_id"],
        lambda e: e.stdout,
    ),
    (
        LLMCompletionLogEvent(filename="log.json", log_data=TEXT, usage_id=ID),
        ["usage_id"],
        lambda e: e.log_data,
    ),
]


@pytest.mark.parametrize(
    ("event", "id_fields", "get_text"),
    _CASES,
    ids=[type(event).__name__ for event, _, _ in _CASES],
)
def test_masks_text_but_not_id_fields(event, id_fields, get_text):
    masked = _registry().mask_secrets_in_model(event)

    for name in id_fields:
        assert getattr(masked, name) == getattr(event, name), name
    assert get_text(masked) == f"text {MASK}"


def test_security_analysis_details_keyed_by_event_id_are_still_masked():
    """``dict[EventID, ...]`` 仅标记按键； 这些值保存分析器文本。"""
    event = SecurityAnalysisEvent(
        analyzer="LLMSecurityAnalyzer",
        policy="NeverConfirm",
        risks={},
        details={ID: {"reason": TEXT}},
    )

    masked = _registry().mask_secrets_in_model(event)

    assert masked.details == {ID: {"reason": f"text {MASK}"}}


class _IdContainers(BaseModel):
    optional: EventID | None = None
    many: list[EventID] = []
    unique: set[EventID] = set()
    fixed: tuple[EventID, ...] = ()
    by_name: dict[str, EventID] = {}


def test_id_types_inside_containers_are_not_masked():
    model = _IdContainers(
        optional=ID, many=[ID], unique={ID}, fixed=(ID,), by_name={"k": ID}
    )

    masked = _registry().mask_secrets_in_model(model)

    assert masked == model


class _MixedContainers(BaseModel):
    either: EventID | list[str]
    pair: tuple[EventID, str]
    by_name: dict[str, EventID | str]


def test_text_beside_an_id_type_is_still_masked():
    """仅当类型的每个带有 str 的部分都是 id 时，才会跳过该类型。"""
    model = _MixedContainers(either=[TEXT], pair=(ID, TEXT), by_name={"k": TEXT})

    masked = _registry().mask_secrets_in_model(model)

    assert masked.either == [f"text {MASK}"]
    assert masked.pair[1] == f"text {MASK}"
    assert masked.by_name == {"k": f"text {MASK}"}
