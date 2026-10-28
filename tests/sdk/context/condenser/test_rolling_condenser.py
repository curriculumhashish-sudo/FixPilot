from unittest.mock import MagicMock

import pytest

from openhands.sdk.context.condenser.base import (
    CondensationRequirement,
    NoCondensationAvailableException,
    RollingCondenser,
)
from openhands.sdk.context.view import View
from openhands.sdk.event.base import Event
from openhands.sdk.event.condenser import Condensation
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.llm import LLM, Message, TextContent


def message_event(content: str) -> MessageEvent:
    return MessageEvent(
        llm_message=Message(role="user", content=[TextContent(text=content)]),
        source="user",
    )


class MockRollingCondenser(RollingCondenser):
    """模拟对象实施RollingCondenser进行测试。"""

    def __init__(
        self,
        condensation_requirement_value: CondensationRequirement | None = None,
        raise_exception: bool = False,
    ):
        self._condensation_requirement_value = condensation_requirement_value
        self._raise_exception = raise_exception

    def condensation_requirement(
        self, view: View, agent_llm: LLM | None = None
    ) -> CondensationRequirement | None:
        return self._condensation_requirement_value

    def get_condensation(
        self, view: View, agent_llm: LLM | None = None
    ) -> Condensation:
        if self._raise_exception:
            raise NoCondensationAvailableException(
                "No condensation available due to API constraints"
            )
        # 成功案例返回简单的上下文压缩
        return Condensation(
            forgotten_event_ids={view.events[0].id},
            summary="Mock summary",
            summary_offset=0,
            llm_response_id="mock-response-id",
        )


def test_rolling_condenser_returns_view_when_no_condensation_needed() -> None:
    """测试 RollingCondenser 返回原始视图
    condensation_requirement 返回 None。
    """
    condenser = MockRollingCondenser(condensation_requirement_value=None)

    events: list[Event] = [
        message_event("Event 1"),
        message_event("Event 2"),
        message_event("Event 3"),
    ]
    view = View.from_events(events)

    result = condenser.condense(view)

    assert isinstance(result, View)
    assert result == view


def test_rolling_condenser_returns_condensation_when_needed() -> None:
    """测试当 condensation_requirement 时 RollingCondenser 返回上下文压缩
    返回 HARD。
    """
    condenser = MockRollingCondenser(
        condensation_requirement_value=CondensationRequirement.HARD,
        raise_exception=False,
    )

    events: list[Event] = [
        message_event("Event 1"),
        message_event("Event 2"),
        message_event("Event 3"),
    ]
    view = View.from_events(events)

    result = condenser.condense(view)

    assert isinstance(result, Condensation)
    assert result.summary == "Mock summary"


def test_rolling_condenser_returns_view_on_no_condensation_available_exception() -> (
    None
):
    """测试 RollingCondenser 返回原始视图
    NoCondensationAvailableException 是根据SOFT 要求提出的。

    这测试了 SOFT 上下文压缩要求的异常处理，它从 get_condensation() 捕获
    NoCondensationAvailableException 并
    将原始视图作为回退方案返回。
    """
    condenser = MockRollingCondenser(
        condensation_requirement_value=CondensationRequirement.SOFT,
        raise_exception=True,
    )

    events: list[Event] = [
        message_event("Event 1"),
        message_event("Event 2"),
        message_event("Event 3"),
    ]
    view = View.from_events(events)

    # 即使 condensation_requirement 返回 SOFT，也应该捕获异常并返回原始视图
    #
    result = condenser.condense(view)

    assert isinstance(result, View)
    assert result == view
    assert result.events == events


def test_rolling_condenser_with_agent_llm() -> None:
    """测试 RollingCondenser 是否与可选的 agent_llm 参数一起使用。"""
    condenser = MockRollingCondenser(
        condensation_requirement_value=CondensationRequirement.HARD,
        raise_exception=False,
    )

    events: list[Event] = [
        message_event("Event 1"),
        message_event("Event 2"),
        message_event("Event 3"),
    ]
    view = View.from_events(events)

    # 创建模拟对象 LLM
    mock_llm = MagicMock(spec=LLM)

    # 使用 agent_llm 参数进行压缩
    result = condenser.condense(view, agent_llm=mock_llm)

    assert isinstance(result, Condensation)
    assert result.summary == "Mock summary"


def test_no_condensation_available_exception_message() -> None:
    """测试 NoCondensationAvailableException 可通过自定义消息引发。"""
    exception_message = "Custom error message about API constraints"

    with pytest.raises(NoCondensationAvailableException, match=exception_message):
        raise NoCondensationAvailableException(exception_message)


def test_default_hard_context_reset_raises_error() -> None:
    """测试默认值 hard_context_reset 是否升高 NoCondensationAvailableException。

    当存在硬性要求但没有可用的上下文压缩且使用默认的 hard_context_reset 实现（返回
    None）时，应提出
    NoCondensationAvailableException。
    """
    condenser = MockRollingCondenser(
        condensation_requirement_value=CondensationRequirement.HARD,
        raise_exception=True,
    )

    events: list[Event] = [
        message_event("Event 1"),
        message_event("Event 2"),
        message_event("Event 3"),
    ]
    view = View.from_events(events)

    # 默认 hard_context_reset 返回 None，因此应该引发异常
    with pytest.raises(NoCondensationAvailableException):
        condenser.condense(view)


class MockRollingCondenserWithHardReset(RollingCondenser):
    """模拟对象使用自定义 hard_context_reset 实现 RollingCondenser。"""

    def __init__(self, hard_reset_condensation: Condensation):
        self._hard_reset_condensation = hard_reset_condensation

    def condensation_requirement(
        self, view: View, agent_llm: LLM | None = None
    ) -> CondensationRequirement | None:
        return CondensationRequirement.HARD

    def get_condensation(
        self, view: View, agent_llm: LLM | None = None
    ) -> Condensation:
        raise NoCondensationAvailableException(
            "No condensation available due to API constraints"
        )

    def hard_context_reset(
        self, view: View, agent_llm: LLM | None = None
    ) -> Condensation | None:
        return self._hard_reset_condensation


def test_hard_context_reset_condensation_is_returned() -> None:
    """测试是否返回 hard_context_reset 中的上下文压缩。

    当存在硬性要求但没有可用的上下文压缩且 hard_context_reset 返回上下文压缩时，应该
    返回该值而不是引发异常。
    """
    events: list[Event] = [
        message_event("Event 1"),
        message_event("Event 2"),
        message_event("Event 3"),
    ]
    view = View.from_events(events)

    # 创建将由 hard_context_reset 返回的上下文压缩
    hard_reset_condensation = Condensation(
        forgotten_event_ids={events[0].id, events[1].id},
        summary="Hard context reset summary",
        summary_offset=0,
        llm_response_id="hard_reset_response",
    )

    condenser = MockRollingCondenserWithHardReset(
        hard_reset_condensation=hard_reset_condensation
    )

    result = condenser.condense(view)

    assert isinstance(result, Condensation)
    assert result == hard_reset_condensation
    assert result.summary == "Hard context reset summary"
