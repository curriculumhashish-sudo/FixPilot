from unittest.mock import MagicMock

from openhands.sdk.context.condenser.no_op_condenser import NoOpCondenser
from openhands.sdk.context.view import View
from openhands.sdk.event.base import Event
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.llm import LLM, Message, TextContent


def message_event(content: str) -> MessageEvent:
    return MessageEvent(
        llm_message=Message(role="user", content=[TextContent(text=content)]),
        source="user",
    )


def test_noop_condenser() -> None:
    """测试 NoOpCondensers 保留其输入事件。"""
    events: list[Event] = [
        message_event("Event 1"),
        message_event("Event 2"),
        message_event("Event 3"),
    ]

    condenser = NoOpCondenser()
    view = View.from_events(events)

    condensation_result = condenser.condense(view)
    assert isinstance(condensation_result, View)
    assert condensation_result.events == events


def test_noop_condenser_with_llm() -> None:
    """测试 NoOpCondenser 是否与可选的 agent_llm 参数一起使用。"""
    events: list[Event] = [
        message_event("Event 1"),
        message_event("Event 2"),
        message_event("Event 3"),
    ]

    condenser = NoOpCondenser()
    view = View.from_events(events)

    # 创建模拟对象 LLM
    mock_llm = MagicMock(spec=LLM)

    # 使用 agent_llm 参数进行压缩
    condensation_result = condenser.condense(view, agent_llm=mock_llm)
    assert isinstance(condensation_result, View)
    assert condensation_result.events == events


def test_noop_condenser_get_llm() -> None:
    """NoOpCondenser 公开 get_llm()=None 并将其从序列化中排除。"""
    condenser = NoOpCondenser()
    assert condenser.get_llm() is None
    assert "llm" not in condenser.model_dump()
