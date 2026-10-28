"""网关对继续对话的等待会在新对话停止时停止。"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from openhands.agent_server.openai import service
from openhands.agent_server.openai.service import (
    _raise_for_terminal_error,
    _wait_for_reused_conversation_completion,
)
from openhands.sdk.conversation.state import ConversationExecutionStatus


class _StatusSequence:
    """代表 EventService：每个 get_state() 返回下一个状态。"""

    def __init__(self, *statuses: ConversationExecutionStatus, events: int = 0):
        self._statuses = list(statuses)
        self._events = events

    async def get_state(self):
        status = self._statuses.pop(0) if len(self._statuses) > 1 else self._statuses[0]
        return SimpleNamespace(execution_status=status, events=[None] * self._events)


@pytest.fixture(autouse=True)
def _fast_poll(monkeypatch):
    monkeypatch.setattr(service, "_POLL_INTERVAL_SECONDS", 0)


@pytest.mark.parametrize(
    "stopped",
    [
        ConversationExecutionStatus.WAITING_FOR_CONFIRMATION,
        ConversationExecutionStatus.PAUSED,
    ],
)
def test_a_continued_run_that_stops_for_the_user_answers_409_at_once(stopped):
    events = _StatusSequence(ConversationExecutionStatus.RUNNING, stopped)

    status_value = asyncio.run(
        _wait_for_reused_conversation_completion(
            events,  # type: ignore[arg-type]
            min_event_count=10,
            timeout_seconds=5,
        )
    )

    assert status_value == stopped
    with pytest.raises(HTTPException) as exc_info:
        _raise_for_terminal_error(status_value)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == f"Agent run ended with status: {stopped.value}"


def test_a_conversation_left_waiting_before_the_new_turn_is_not_the_answer():
    # 本回合的运行尚未开始：未看到 RUNNING，也没有新事件，因此较早回合的等待状态不得结束
    # 等待。
    #
    events = _StatusSequence(ConversationExecutionStatus.WAITING_FOR_CONFIRMATION)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            _wait_for_reused_conversation_completion(
                events,  # type: ignore[arg-type]
                min_event_count=10,
                timeout_seconds=0,
            )
        )
    assert exc_info.value.status_code == 504
