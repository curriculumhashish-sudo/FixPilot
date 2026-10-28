"""LLMCompletionLogEvent 序列化的测试和功能。"""

import json

from openhands.sdk.event import Event, LLMCompletionLogEvent


def test_llm_completion_log_event_creation() -> None:
    """测试创建 LLMCompletionLogEvent。"""
    event = LLMCompletionLogEvent(
        filename="test_model__1234567890.123-abcd.json",
        log_data='{"test": "data"}',
        model_name="test_model",
    )

    assert event.filename == "test_model__1234567890.123-abcd.json"
    assert event.log_data == '{"test": "data"}'
    assert event.model_name == "test_model"
    assert event.source == "environment"


def test_llm_completion_log_event_serialization() -> None:
    """测试LLMCompletionLogEvent序列化/反序列化。"""
    log_data = json.dumps(
        {
            "response": {"id": "response_123", "model": "test_model"},
            "cost": 0.0001,
            "timestamp": 1234567890.123,
        }
    )

    event = LLMCompletionLogEvent(
        filename="anthropic__claude-sonnet__1234567890.123-abcd.json",
        log_data=log_data,
        model_name="anthropic/claude-sonnet",
    )

    # 序列化
    json_str = event.model_dump_json()
    deserialized = LLMCompletionLogEvent.model_validate_json(json_str)

    assert deserialized == event
    assert deserialized.filename == event.filename
    assert deserialized.log_data == event.log_data
    assert deserialized.model_name == event.model_name


def test_llm_completion_log_event_as_base_event() -> None:
    """测试 LLMCompletionLogEvent 是否可以已反序列化作为基础事件。"""
    event = LLMCompletionLogEvent(
        filename="test_model__1234567890.123-abcd.json",
        log_data='{"test": "data"}',
        model_name="test_model",
    )

    # 序列化和反序列化作为基本事件
    json_str = event.model_dump_json()
    deserialized = Event.model_validate_json(json_str)

    assert isinstance(deserialized, LLMCompletionLogEvent)
    assert deserialized == event


def test_llm_completion_log_event_str() -> None:
    """测试字符串表示 LLMCompletionLogEvent。"""
    event = LLMCompletionLogEvent(
        filename="test_model__1234567890.123-abcd.json",
        log_data='{"test": "data"}',
        model_name="test_model",
    )

    str_repr = str(event)
    assert "test_model" in str_repr
    assert "test_model__1234567890.123-abcd.json" in str_repr
