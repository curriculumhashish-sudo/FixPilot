"""回归 Codex 订阅模式修复测试。

测试涵盖了四个导致 LLM.subscription_login() 无法使用的错误：
1. prompt_cache_retention 被食品法典委员会拒绝端点 (400)
2. 包含/推理参数导致静默空输出
3. 流式传输输出项丢失（response.completed 输出=[]）
4. 推理项目 ID 导致后续请求出现 404 (store=False)
5. 重试路径不得添加不支持的温度参数

See: https://github.com/OpenHands/software-agent-sdk/issues/2797
"""

import json
from types import SimpleNamespace
from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from litellm.types.llms.base import BaseLiteLLMOpenAIResponseObject
from litellm.types.llms.openai import ResponsesAPIResponse
from openai.types.responses import ResponseOutputMessage, ResponseOutputText
from openai.types.responses.response_function_tool_call import (
    ResponseFunctionToolCall,
)
from pydantic import ConfigDict, model_validator

from openhands.sdk.llm.exceptions import LLMNoResponseError
from openhands.sdk.llm.llm import LLM
from openhands.sdk.llm.message import (
    Message,
    MessageToolCall,
    ReasoningItemModel,
    TextContent,
)
from openhands.sdk.llm.options.responses_options import select_responses_options


# ---------------------------------------------------------------------------
# 帮手
# ---------------------------------------------------------------------------


def _make_subscription_llm() -> LLM:
    """创建最小订阅模式 LLM 进行测试。"""
    llm = LLM(
        model="openai/gpt-5.4",
        base_url="https://chatgpt.com/backend-api/codex",
        reasoning_effort="high",
    )
    llm.is_subscription = True
    llm.enable_encrypted_reasoning = True
    return llm


def _make_generic_output_item(**kwargs: Any) -> BaseLiteLLMOpenAIResponseObject:
    """构建一个 BaseLiteLLMOpenAIResponseObject （类型 LiteLLM 用于
    流式传输输出项）具有给定的属性。"""
    return BaseLiteLLMOpenAIResponseObject.model_construct(**kwargs)


def _make_responses_api_response(text: str = "ok") -> ResponsesAPIResponse:
    return ResponsesAPIResponse(
        id="resp-1",
        created_at=1,
        output=[
            ResponseOutputMessage(
                id="msg-1",
                type="message",
                role="assistant",
                status="completed",
                content=[
                    ResponseOutputText(type="output_text", text=text, annotations=[])
                ],
            )
        ],
        model="gpt-5.4",
        object="response",
    )


# ---------------------------------------------------------------------------
# Bug 1 & 2：订阅模式下必须跳过不支持的参数
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "param",
    [
        "prompt_cache_retention",
        "include",
        "reasoning",
        "temperature",
        "max_output_tokens",
    ],
)
def test_subscription_skips_unsupported_param(param: str):
    """Codex 订阅端点拒绝或默默地错误处理这些
    参数。 当is_subscription为True时必须省略它们。"""
    llm = _make_subscription_llm()
    llm.max_output_tokens = 4096
    opts = select_responses_options(llm, {}, include=["text.output_text"], store=None)
    assert param not in opts


@pytest.mark.parametrize(
    "param,expected_value",
    [
        ("prompt_cache_retention", "24h"),
    ],
)
def test_non_subscription_keeps_scalar_param(param: str, expected_value: Any):
    """非订阅 GPT-5 模型仍应发送这些参数。"""
    llm = LLM(model="openai/gpt-5.4", reasoning_effort="high")
    llm.enable_encrypted_reasoning = True
    assert not llm.is_subscription
    opts = select_responses_options(llm, {}, include=None, store=None)
    assert opts.get(param) == expected_value


def test_non_subscription_does_not_invent_temperature():
    llm = LLM(model="openai/gpt-5.4", reasoning_effort="high")

    opts = select_responses_options(llm, {}, include=None, store=None)

    assert "temperature" not in opts


@pytest.mark.parametrize(
    "param,check",
    [
        ("include", lambda v: "reasoning.encrypted_content" in v),
        ("reasoning", lambda v: v["effort"] == "high"),
    ],
)
def test_non_subscription_keeps_structured_param(param: str, check: Any):
    """非订阅用户 LLMs 应该正常发送 include 和 reasoning。"""
    llm = LLM(model="openai/gpt-5.4", reasoning_effort="high")
    llm.enable_encrypted_reasoning = True
    assert not llm.is_subscription
    opts = select_responses_options(llm, {}, include=["text.output_text"], store=None)
    assert param in opts
    assert check(opts[param])


# ---------------------------------------------------------------------------
# Bug 5：重试路径必须保留省略的订阅参数
# ---------------------------------------------------------------------------


@patch("openhands.sdk.llm.llm.litellm_responses")
def test_subscription_retry_does_not_add_temperature(mock_responses: Any):
    """订阅模式故意省略了温度。

    A 重试之后 LLMNoResponseError 必须不制造温度为1.0的，因为 ChatGPT 订阅端点拒绝参
    数。
    """
    llm = _make_subscription_llm()
    llm.num_retries = 2
    llm.retry_min_wait = 0
    llm.retry_max_wait = 0
    llm.stream = True

    mock_responses.side_effect = [
        LLMNoResponseError("empty response"),
        _make_responses_api_response("ok"),
    ]

    # 订阅身份验证从磁盘加载 OAuth 凭据； 将其存根，以便测试不依赖于真实的 ChatGPT 登录
    # 。
    #
    with patch.object(llm, "_get_litellm_auth_values", return_value=(None, {})):
        llm.responses(messages=[Message(role="user", content=[TextContent(text="hi")])])

    assert mock_responses.call_count == 2
    _, first_kwargs = mock_responses.call_args_list[0]
    _, second_kwargs = mock_responses.call_args_list[1]
    assert "temperature" not in first_kwargs
    assert "temperature" not in second_kwargs


# ---------------------------------------------------------------------------
# Bug 3：from_llm_responses_output 必须处理通用 LiteLLM 类型
# ---------------------------------------------------------------------------


def _generic_function_call_item() -> BaseLiteLLMOpenAIResponseObject:
    return _make_generic_output_item(
        id="fc_abc",
        type="function_call",
        name="terminal",
        arguments='{"command": "ls"}',
        call_id="call_123",
        status="completed",
    )


def _generic_message_item() -> BaseLiteLLMOpenAIResponseObject:
    text_part = SimpleNamespace(type="output_text", text="Hello world")
    return _make_generic_output_item(
        id="m_1",
        type="message",
        role="assistant",
        status="completed",
        content=[text_part],
    )


def _generic_reasoning_item() -> BaseLiteLLMOpenAIResponseObject:
    summary = SimpleNamespace(type="summary_text", text="thinking")
    return _make_generic_output_item(
        id="rs_abc",
        type="reasoning",
        summary=[summary],
        content=None,
        encrypted_content=None,
        status="completed",
    )


def _dict_function_call_item() -> dict[str, Any]:
    return {
        "type": "function_call",
        "name": "file_editor",
        "arguments": '{"command": "view"}',
        "call_id": "call_456",
        "id": "fc_456",
    }


def _dict_message_item() -> dict[str, Any]:
    return {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "Hi"}],
    }


def _typed_function_call_item() -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        type="function_call",
        name="think",
        arguments="{}",
        call_id="fc_typed",
        id="fc_typed",
    )


@pytest.mark.parametrize(
    "item_factory,expected_tool,expected_text",
    [
        pytest.param(
            _generic_function_call_item,
            {"name": "terminal", "arguments": '{"command": "ls"}', "id": "call_123"},
            None,
            id="generic-function-call",
        ),
        pytest.param(
            _dict_function_call_item,
            {
                "name": "file_editor",
                "arguments": '{"command": "view"}',
                "id": "call_456",
            },
            None,
            id="dict-function-call",
        ),
        pytest.param(
            _typed_function_call_item,
            {"name": "think", "arguments": "{}", "id": "fc_typed"},
            None,
            id="typed-function-call",
        ),
        pytest.param(
            _generic_message_item,
            None,
            "Hello world",
            id="generic-message",
        ),
        pytest.param(
            _dict_message_item,
            None,
            "Hi",
            id="dict-message",
        ),
    ],
)
def test_from_llm_responses_output_item_type(
    item_factory: Any,
    expected_tool: dict[str, str] | None,
    expected_text: str | None,
):
    """from_llm_responses_output 必须解析 function_call 和消息项
    无论它们是作为类型化 Pydantic 对象、通用 BaseLiteLLMOpenAIResponseObject 还是普通
    字典到达。
    """
    item = item_factory()
    msg = Message.from_llm_responses_output([item])

    if expected_tool is not None:
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1
        tc = msg.tool_calls[0]
        assert tc.name == expected_tool["name"]
        assert tc.arguments == expected_tool["arguments"]
        assert tc.id == expected_tool["id"]
    if expected_text is not None:
        assert len(msg.content) == 1
        assert isinstance(msg.content[0], TextContent)
        assert msg.content[0].text == expected_text


@pytest.mark.parametrize(
    "item_factory,expected_id,expected_summary",
    [
        pytest.param(
            _generic_reasoning_item,
            "rs_abc",
            ["thinking"],
            id="generic-reasoning",
        ),
    ],
)
def test_from_llm_responses_output_reasoning_item(
    item_factory: Any,
    expected_id: str,
    expected_summary: list[str],
):
    """流式传输中的推理项应解析为 ReasoningItemModel。"""
    item = item_factory()
    msg = Message.from_llm_responses_output([item])
    assert msg.responses_reasoning_item is not None
    assert msg.responses_reasoning_item.id == expected_id
    assert msg.responses_reasoning_item.summary == expected_summary


def test_mixed_typed_and_generic_items():
    """解析器应该在一次调用中处理类型化和通用项的混合。"""
    typed_fc = _typed_function_call_item()
    generic_fc = _generic_function_call_item()
    msg = Message.from_llm_responses_output([typed_fc, generic_fc])
    assert msg.tool_calls is not None
    assert len(msg.tool_calls) == 2
    assert {tc.name for tc in msg.tool_calls} == {"think", "terminal"}


@pytest.mark.parametrize("as_objects", [False, True])
def test_response_output_preserves_replay_metadata(as_objects):
    def item(**fields):
        return SimpleNamespace(**fields) if as_objects else fields

    message = Message.from_llm_responses_output(
        [
            item(type="unknown"),
            item(type="message", content=[item(type="output_text", text="Answer")]),
            item(
                type="function_call",
                id="fc_item",
                call_id="call_tool",
                name="terminal",
                arguments="{}",
            ),
            item(
                type="reasoning",
                id="rs_item",
                summary=[item(text="summary")],
                content=[item(text="reasoning")],
                encrypted_content="encrypted",
                status="completed",
            ),
        ]
    )
    assert message.tool_calls
    assert message.tool_calls[0].id == "call_tool"
    assert message.tool_calls[0].responses_item_id == "fc_item"
    assert message.responses_reasoning_item
    assert message.responses_reasoning_item.model_dump() == {
        "id": "rs_item",
        "summary": ["summary"],
        "content": ["reasoning"],
        "encrypted_content": "encrypted",
        "status": "completed",
    }
    restored = Message.model_validate_json(message.model_dump_json())
    assert restored.to_responses_dict(vision_enabled=False) == (
        message.to_responses_dict(vision_enabled=False)
    )


def test_response_output_missing_optional_fields():
    message = Message.from_llm_responses_output(
        [
            object(),
            {"type": "message"},
            {"type": "function_call", "id": "fc_fallback"},
            {"type": "reasoning", "summary": [{}]},
        ]
    )
    assert message.content == []
    assert message.tool_calls
    assert message.tool_calls[0].id == "fc_fallback"
    assert message.tool_calls[0].arguments == ""
    assert message.responses_reasoning_item
    assert message.responses_reasoning_item.summary == [""]
    assert message.responses_reasoning_item.content is None


# ---------------------------------------------------------------------------
# Bug 4：在订阅模式下推理项目 ID 必须被剥离
# ---------------------------------------------------------------------------


def _make_conversation_messages() -> tuple[Message, Message, Message, Message]:
    """使用推理项目构建最小的多轮对话。"""
    sys_msg = Message(
        role="system",
        content=[TextContent(text="You are a helpful assistant.")],
    )
    user_msg = Message(
        role="user",
        content=[TextContent(text="Now create FACTS.txt")],
    )
    assistant_msg = Message(
        role="assistant",
        content=[TextContent(text="I'll look at the files.")],
        tool_calls=[
            MessageToolCall(
                id="call_1",
                name="terminal",
                arguments='{"command": "ls"}',
                origin="responses",
            )
        ],
        responses_reasoning_item=ReasoningItemModel(
            id="rs_should_be_stripped",
            summary=["thinking about files"],
            content=None,
            encrypted_content=None,
            status="completed",
        ),
    )
    tool_msg = Message(
        role="tool",
        content=[TextContent(text="file1.py file2.py")],
        tool_call_id="call_1",
    )
    return sys_msg, user_msg, assistant_msg, tool_msg


@pytest.mark.parametrize(
    "is_subscription,reasoning_id_present",
    [
        pytest.param(True, False, id="subscription-strips-reasoning"),
        pytest.param(False, True, id="non-subscription-preserves-reasoning"),
    ],
)
def test_format_messages_reasoning_item_handling(
    is_subscription: bool, reasoning_id_present: bool
):
    """订阅模式必须剥离推理项 ID（store=False 表示它们
    无法解决）。 非订阅模式必须保留它们。"""
    llm = LLM(model="openai/gpt-5.4")
    if is_subscription:
        llm.is_subscription = True

    sys_msg, user_msg, assistant_msg, tool_msg = _make_conversation_messages()
    _, input_items = llm.format_messages_for_responses(
        [sys_msg, user_msg, assistant_msg, tool_msg]
    )

    serialized = json.dumps(input_items, default=str)
    assert ("rs_should_be_stripped" in serialized) == reasoning_id_present


def test_is_subscription_survives_serialization_round_trip():
    """is_subscription 必须生存 model_dump -> model_validate。

    RemoteConversation 序列化 LLM，智能体服务器重建它； 如果标志丢失，所有与订阅相关
    的请求处理（流式传输豁免、系统提示词转换、理由项去除）将无声
    地在服务器端停止应用。
    """
    llm = _make_subscription_llm()
    restored = LLM.model_validate(llm.model_dump(context={"expose_secrets": True}))
    assert restored.is_subscription is True

    plain = LLM(model="gpt-4o")
    restored_plain = LLM.model_validate(
        plain.model_dump(context={"expose_secrets": True})
    )
    assert restored_plain.is_subscription is False


def test_is_subscription_runtime_update_is_the_serialized_state():
    llm = LLM(model="gpt-4o")

    llm.is_subscription = True

    assert llm.model_dump()["is_subscription"] is True
    assert LLM.model_validate(llm.model_dump()).is_subscription is True


def test_is_subscription_restore_respects_subclass_before_validator():
    class StrictLLM(LLM):
        model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

        @model_validator(mode="before")
        @classmethod
        def _drop_is_subscription(cls, data: Any) -> Any:
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if k != "is_subscription"}
            return data

    restored = StrictLLM.model_validate(
        {"model": "openai/gpt-4o-mini", "is_subscription": True}
    )

    assert restored.is_subscription is False
