"""对事件序列化和反序列化的综合测试。"""

import json

import pytest
from pydantic import ValidationError

from openhands.sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    Condensation,
    CondensationRequest,
    Event,
    MessageEvent,
    ObservationEvent,
    SystemPromptEvent,
)
from openhands.sdk.llm import (
    Message,
    MessageToolCall,
    TextContent,
)
from openhands.sdk.tool import Action, Observation


class EventSerializationMockEvent(Event):
    test_field: str = "test_value"


class EventsSerializationMockAction(Action):
    """模拟对象测试操作。"""

    def execute(self) -> "EventsSerializationMockObservation":
        return EventsSerializationMockObservation(
            content=[TextContent(text="mock result")]
        )


class EventsSerializationMockObservation(Observation):
    """模拟对象观测结果用于测试。"""

    pass


def test_event_base_serialization() -> None:
    """测试基本事件序列化/反序列化。"""
    event = EventSerializationMockEvent(source="agent", test_field="custom_value")

    json_data = event.model_dump_json()
    deserialized = EventSerializationMockEvent.model_validate_json(json_data)
    assert deserialized == event


def test_system_prompt_event_serialization() -> None:
    """测试SystemPromptEvent序列化/反序列化。"""
    event = SystemPromptEvent(
        system_prompt=TextContent(text="You are a helpful assistant"), tools=[]
    )

    json_data = event.model_dump_json()
    deserialized = SystemPromptEvent.model_validate_json(json_data)
    assert deserialized == event


def test_action_event_serialization() -> None:
    """测试ActionEvent序列化/反序列化。"""
    action = EventsSerializationMockAction()
    tool_call = MessageToolCall(
        id="call_123",
        name="mock_tool",
        arguments="{}",
        origin="completion",
    )
    event = ActionEvent(
        thought=[TextContent(text="I need to do something")],
        action=action,
        tool_name="mock_tool",
        tool_call_id="call_123",
        tool_call=tool_call,
        llm_response_id="response_456",
    )

    json_data = event.model_dump_json()
    deserialized = ActionEvent.model_validate_json(json_data)

    # 检查核心字段是否被保留
    assert deserialized.id == event.id
    assert deserialized.timestamp == event.timestamp
    assert deserialized.source == event.source
    assert deserialized.thought == event.thought
    assert deserialized.tool_name == event.tool_name
    assert deserialized.tool_call_id == event.tool_call_id
    assert deserialized.tool_call == event.tool_call
    assert deserialized.llm_response_id == event.llm_response_id
    # Action 是已反序列化作为 Action，所以我们无法检查完全相等


def test_observation_event_serialization() -> None:
    """测试ObservationEvent序列化/反序列化。"""
    observation = EventsSerializationMockObservation(
        content=[TextContent(text="test result")]
    )
    event = ObservationEvent(
        observation=observation,
        action_id="action_123",
        tool_name="mock_tool",
        tool_call_id="call_123",
    )

    json_data = event.model_dump_json()
    deserialized = ObservationEvent.model_validate_json(json_data)

    # 检查核心字段是否被保留
    assert deserialized.id == event.id
    assert deserialized.timestamp == event.timestamp
    assert deserialized.source == event.source
    assert deserialized.action_id == event.action_id
    assert deserialized.tool_name == event.tool_name
    assert deserialized.tool_call_id == event.tool_call_id
    # 观测结果是已反序列化作为观测结果，所以我们无法检查完全相等


def test_message_event_serialization() -> None:
    """测试MessageEvent序列化/反序列化。"""
    from openhands.sdk.llm import Message

    llm_message = Message(
        role="user",
        content=[TextContent(text="Hello, world!")],
    )
    event = MessageEvent(source="user", llm_message=llm_message)

    json_data = event.model_dump_json()
    deserialized = MessageEvent.model_validate_json(json_data)
    assert deserialized == event


def test_agent_error_event_serialization() -> None:
    """测试AgentErrorEvent序列化/反序列化。"""
    event = AgentErrorEvent(
        error="Something went wrong", tool_call_id="call_001", tool_name="test_tool"
    )

    json_data = event.model_dump_json()
    deserialized = AgentErrorEvent.model_validate_json(json_data)
    assert deserialized == event


def test_condensation_serialization() -> None:
    """测试上下文压缩序列化/反序列化。"""
    event = Condensation(
        summary="This is a summary",
        forgotten_event_ids={"event1", "event2", "event3", "event4", "event5"},
        llm_response_id="condensation_response_1",
    )

    # 序列化
    json_data = event.model_dump_json()
    deserialized = Condensation.model_validate_json(json_data)
    assert deserialized == event


def test_condensation_deserializes_from_list_format() -> None:
    """向后兼容：旧的已持久化数据存储为 forgotten_event_ids 作为列表。"""
    event = Condensation(
        summary="summary",
        forgotten_event_ids={"id1", "id2"},
        llm_response_id="resp_1",
    )
    raw = json.loads(event.model_dump_json())

    # 模拟旧的已持久化格式：ID 的 JSON 数组（列表）
    raw["forgotten_event_ids"] = ["id1", "id2"]
    deserialized = Condensation.model_validate(raw)

    assert deserialized.forgotten_event_ids == {"id1", "id2"}
    assert isinstance(deserialized.forgotten_event_ids, set)


def test_condensation_request_serialization() -> None:
    """测试CondensationRequest序列化/反序列化。"""
    event = CondensationRequest()

    json_data = event.model_dump_json()
    deserialized = CondensationRequest.model_validate_json(json_data)
    assert deserialized == event


def test_extra_fields_forbidden():
    """测试事件中是否禁止额外字段。"""
    data_with_extra = {
        "type": "SystemPromptEvent",
        "source": "agent",
        "id": "test-id",
        "timestamp": "2023-01-01T00:00:00",
        "system_prompt": {"text": "Test"},
        "tools": [],
        "extra_field": "should_not_be_allowed",
    }

    with pytest.raises(ValidationError) as exc_info:
        SystemPromptEvent.model_validate(data_with_extra)

    assert "extra_forbidden" in str(exc_info.value)


def test_event_deserialize():
    original = MessageEvent(
        source="user",
        llm_message=Message(
            role="user",
            content=[TextContent(text="Hello There!")],
        ),
        activated_skills=[],
        extended_content=[],
    )
    dumped = original.model_dump_json()
    loaded = Event.model_validate_json(dumped)
    assert loaded == original
