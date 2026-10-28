from types import SimpleNamespace

import pytest

from openhands.sdk.llm.message import Message, TextContent, content_to_str


def test_from_llm_chat_message_raises_when_only_non_function_tool_calls():
    # tool_calls 有一个非函数条目应该引发 ValueError
    non_function_call = SimpleNamespace(type="non_function")
    # 使用轻量级存根代替 LiteLLMMessage 以允许非功能 tool_calls
    m = SimpleNamespace(role="assistant", content="hi", tool_calls=[non_function_call])
    with pytest.raises(ValueError, match="none are of type 'function'"):
        Message.from_llm_chat_message(m)  # type: ignore[arg-type]


def test_coerce_content_validator_handles_none_and_string():
    # content=None coerces to [] via model_validate
    msg_none = Message.model_validate({"role": "user", "content": None})
    assert msg_none.content == []

    # 内容作为字符串通过 model_validate 强制到 [TextContent]
    msg_str = Message.model_validate({"role": "user", "content": "hello"})
    assert len(msg_str.content) == 1
    assert isinstance(msg_str.content[0], TextContent)
    assert msg_str.content[0].text == "hello"


def test_content_to_str_helper():
    parts = content_to_str([TextContent(text="a"), TextContent(text="b")])
    assert parts == ["a", "b"]


def test_to_responses_value_system_direct():
    # 通过to_responses_value直接测试系统指令
    m = Message(role="system", content=[TextContent(text="A"), TextContent(text="B")])
    val = m.to_responses_value(vision_enabled=False)
    assert val == "A\nB"
