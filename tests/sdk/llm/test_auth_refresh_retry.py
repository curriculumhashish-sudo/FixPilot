"""测试：class:`LLM` 上的刷新 401 缓解措施。

当完成/响应调用失败并出现身份验证错误时（HTTP 401、e.g. 旋转/修复的托管代理密钥，
LiteLLM 报告为
``token_not_found_in_db``）并且注册了 API 键刷新挂钩，LLM 重新解析密钥一次，重试重新
解析一次调用。 请参阅 OpenHands/软件-智能
体-SDK#5189。
"""

from typing import Literal
from unittest.mock import AsyncMock, patch

import pytest
from litellm.exceptions import AuthenticationError
from litellm.types.llms.openai import ResponseAPIUsage, ResponsesAPIResponse
from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse, Usage
from openai.types.responses.response_output_message import ResponseOutputMessage
from openai.types.responses.response_output_text import ResponseOutputText
from pydantic import SecretStr

from openhands.sdk.llm import LLM, LLMResponse, Message, TextContent
from openhands.sdk.llm.exceptions import LLMAuthenticationError
from openhands.sdk.llm.llm import LLMCallContext


def create_mock_response(content: str = "Test response", response_id: str = "test-id"):
    return ModelResponse(
        id=response_id,
        choices=[
            Choices(
                finish_reason="stop",
                index=0,
                message=LiteLLMMessage(content=content, role="assistant"),
            )
        ],
        created=1234567890,
        model="gpt-4o",
        object="chat.completion",
        system_fingerprint="test",
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def create_mock_responses_response(content: str = "Recovered") -> ResponsesAPIResponse:
    """构建一个成功的最小响应 API。"""
    msg = ResponseOutputMessage.model_construct(
        id="m1",
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text=content, annotations=[])],
    )
    usage = ResponseAPIUsage(input_tokens=10, output_tokens=5, total_tokens=15)
    return ResponsesAPIResponse(
        id="r1",
        created_at=0,
        output=[msg],
        parallel_tool_calls=False,
        tool_choice="auto",
        top_p=None,
        tools=[],
        usage=usage,
        instructions="",
        status="completed",
    )


def _auth_error() -> AuthenticationError:
    return AuthenticationError(
        message=(
            "Invalid proxy server token passed. Unable to find token in cache or "
            "LiteLLM_VerificationTokenTable (token_not_found_in_db)"
        ),
        llm_provider="openhands",
        model="gpt-4o",
    )


def _make_llm(auth_type: Literal["api_key", "subscription"] = "api_key") -> LLM:
    return LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("stale_key"),
        auth_type=auth_type,
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )


def _message() -> list[Message]:
    return [Message(role="user", content=[TextContent(text="Hello!")])]


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_completion_refreshes_key_and_retries_once(mock_litellm_completion):
    """带有刷新钩子的 401 会重新解析 key 和重试一次。"""
    mock_litellm_completion.side_effect = [
        _auth_error(),
        create_mock_response("Recovered"),
    ]
    calls = {"count": 0}

    def refresh() -> str:
        calls["count"] += 1
        return "fresh_key"

    llm = _make_llm()
    llm.set_api_key_refresh_hook(refresh)

    response = llm.completion(messages=_message())

    assert isinstance(response, LLMResponse)
    assert mock_litellm_completion.call_count == 2  # 初始+1刷新重试
    assert calls["count"] == 1  # 钩子仅调用一次
    # 重试的调用使用新解析的密钥，而不是陈旧的密钥。
    assert mock_litellm_completion.call_args_list[1].kwargs["api_key"] == "fresh_key"


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_completion_no_refresh_without_hook(mock_litellm_completion):
    """如果没有钩子，401 立即浮出水面，没有重试。"""
    mock_litellm_completion.side_effect = _auth_error()

    llm = _make_llm()

    with pytest.raises(LLMAuthenticationError):
        llm.completion(messages=_message())
    assert mock_litellm_completion.call_count == 1


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_completion_refresh_retries_only_once(mock_litellm_completion):
    """如果刷新的 key 仍然是 401s，则错误出现（没有无限循环）。"""
    mock_litellm_completion.side_effect = [_auth_error(), _auth_error()]
    calls = {"count": 0}

    def refresh() -> str:
        calls["count"] += 1
        return f"fresh_key_{calls['count']}"

    llm = _make_llm()
    llm.set_api_key_refresh_hook(refresh)

    with pytest.raises(LLMAuthenticationError):
        llm.completion(messages=_message())
    assert mock_litellm_completion.call_count == 2  # 初始+一重试，然后停止
    assert calls["count"] == 1  # 只刷新一次


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_completion_no_retry_when_hook_returns_none(mock_litellm_completion):
    """不产生键的钩子不会触发重试。"""
    mock_litellm_completion.side_effect = _auth_error()

    llm = _make_llm()
    llm.set_api_key_refresh_hook(lambda: None)

    with pytest.raises(LLMAuthenticationError):
        llm.completion(messages=_message())
    assert mock_litellm_completion.call_count == 1


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_completion_no_retry_when_hook_returns_same_key(mock_litellm_completion):
    """返回已拒绝密钥的钩子不会重试。"""
    mock_litellm_completion.side_effect = _auth_error()

    llm = _make_llm()
    llm.set_api_key_refresh_hook(lambda: "stale_key")

    with pytest.raises(LLMAuthenticationError):
        llm.completion(messages=_message())
    assert mock_litellm_completion.call_count == 1


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_completion_raising_hook_surfaces_original_error(mock_litellm_completion):
    """升起的钩子不得掩盖原来的 401。"""
    mock_litellm_completion.side_effect = _auth_error()

    def refresh() -> str:
        raise RuntimeError("hook boom")

    llm = _make_llm()
    llm.set_api_key_refresh_hook(refresh)

    with pytest.raises(LLMAuthenticationError):
        llm.completion(messages=_message())
    assert mock_litellm_completion.call_count == 1


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_hook_not_called_for_non_auth_error(mock_litellm_completion):
    """非身份验证错误永远不会调用刷新挂钩。"""
    from litellm.exceptions import APIConnectionError

    mock_litellm_completion.side_effect = APIConnectionError(
        message="API connection error",
        llm_provider="test_provider",
        model="test_model",
    )
    calls = {"count": 0}

    def refresh() -> str:
        calls["count"] += 1
        return "fresh_key"

    llm = _make_llm()
    llm.set_api_key_refresh_hook(refresh)

    with pytest.raises(Exception):
        llm.completion(messages=_message())
    assert calls["count"] == 0  # 钩子因连接错误而未受影响


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_refresh_hook_not_serialized(mock_litellm_completion):
    """该钩子是私有属性，不能泄漏到已序列化状态。"""
    llm = _make_llm()
    llm.set_api_key_refresh_hook(lambda: "fresh_key")
    dumped = llm.model_dump()
    assert "_api_key_refresh_hook" not in dumped
    assert "api_key_refresh_hook" not in dumped


@pytest.mark.asyncio
@patch("openhands.sdk.llm.llm.litellm_acompletion")
async def test_acompletion_refreshes_key_and_retries_once(mock_litellm_acompletion):
    """异步路径还会在 401 上刷新密钥和重试一次。"""
    mock_litellm_acompletion.side_effect = [
        _auth_error(),
        create_mock_response("Recovered"),
    ]
    calls = {"count": 0}

    def refresh() -> str:
        calls["count"] += 1
        return "fresh_key"

    llm = _make_llm()
    llm.set_api_key_refresh_hook(refresh)

    response = await llm.acompletion(messages=_message())

    assert isinstance(response, LLMResponse)
    assert mock_litellm_acompletion.call_count == 2
    assert calls["count"] == 1
    assert mock_litellm_acompletion.call_args_list[1].kwargs["api_key"] == "fresh_key"


# ---------------------------------------------------------------------------
# API 路径 (GPT-5 / 理由-努力模型) — 重试块在所有四个调用面之间重复，因此 responses()
# /aresponses() 需要各自的覆盖； 上述完成测试并不执行它们。
# ---------------------------------------------------------------------------


@patch("openhands.sdk.llm.llm.litellm_responses")
def test_responses_refreshes_key_and_retries_once(mock_litellm_responses):
    """响应路径上的 401 重新解析密钥和重试一次。"""
    mock_litellm_responses.side_effect = [
        _auth_error(),
        create_mock_responses_response("Recovered"),
    ]
    calls = {"count": 0}

    def refresh() -> str:
        calls["count"] += 1
        return "fresh_key"

    llm = _make_llm()
    llm.set_api_key_refresh_hook(refresh)

    response = llm.responses(messages=_message())

    assert isinstance(response, LLMResponse)
    assert mock_litellm_responses.call_count == 2  # 初始+1刷新重试
    assert calls["count"] == 1  # 钩子仅调用一次
    # 重试的调用使用新解析的密钥，而不是陈旧的密钥。
    assert mock_litellm_responses.call_args_list[1].kwargs["api_key"] == "fresh_key"


@patch("openhands.sdk.llm.llm.litellm_responses")
def test_responses_refresh_retries_only_once(mock_litellm_responses):
    """如果刷新的密钥仍然是 401s，则响应路径在 1重试后停止。"""
    mock_litellm_responses.side_effect = [_auth_error(), _auth_error()]
    calls = {"count": 0}

    def refresh() -> str:
        calls["count"] += 1
        return f"fresh_key_{calls['count']}"

    llm = _make_llm()
    llm.set_api_key_refresh_hook(refresh)

    with pytest.raises(LLMAuthenticationError):
        llm.responses(messages=_message())
    assert mock_litellm_responses.call_count == 2  # 初始+一重试，然后停止
    assert calls["count"] == 1  # 只刷新一次


@pytest.mark.asyncio
@patch("openhands.sdk.llm.llm.litellm_aresponses", new_callable=AsyncMock)
async def test_aresponses_refreshes_key_and_retries_once(mock_litellm_aresponses):
    """异步响应路径还会在 401 上刷新密钥和重试一次。"""
    mock_litellm_aresponses.side_effect = [
        _auth_error(),
        create_mock_responses_response("Recovered"),
    ]
    calls = {"count": 0}

    def refresh() -> str:
        calls["count"] += 1
        return "fresh_key"

    llm = _make_llm()
    llm.set_api_key_refresh_hook(refresh)

    response = await llm.aresponses(messages=_message())

    assert isinstance(response, LLMResponse)
    assert mock_litellm_aresponses.call_count == 2
    assert calls["count"] == 1
    assert mock_litellm_aresponses.call_args_list[1].kwargs["api_key"] == "fresh_key"


@pytest.mark.asyncio
@patch("openhands.sdk.llm.llm.litellm_aresponses", new_callable=AsyncMock)
async def test_aresponses_refresh_retries_only_once(mock_litellm_aresponses):
    """异步响应路径在重复 401 秒刷新一次重试后停止。"""
    mock_litellm_aresponses.side_effect = [_auth_error(), _auth_error()]
    calls = {"count": 0}

    def refresh() -> str:
        calls["count"] += 1
        return f"fresh_key_{calls['count']}"

    llm = _make_llm()
    llm.set_api_key_refresh_hook(refresh)

    with pytest.raises(LLMAuthenticationError):
        await llm.aresponses(messages=_message())
    assert mock_litellm_aresponses.call_count == 2
    assert calls["count"] == 1


# ---------------------------------------------------------------------------
# 解析器守卫——订阅身份验证和空键边缘。
# ---------------------------------------------------------------------------


def test_non_api_key_auth_skips_refresh():
    """订阅模式 LLMs 不能让 API-key 键钩覆盖键。"""
    llm = _make_llm(auth_type="subscription")
    llm.set_api_key_refresh_hook(lambda: "fresh_key")
    assert llm._resolve_refreshed_api_key(_auth_error()) is None


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_completion_no_retry_when_hook_returns_empty_key(mock_litellm_completion):
    """返回空字符串的钩子不会触发 (凭据-less) 重试。"""
    mock_litellm_completion.side_effect = _auth_error()

    llm = _make_llm()
    llm.set_api_key_refresh_hook(lambda: "")

    with pytest.raises(LLMAuthenticationError):
        llm.completion(messages=_message())
    assert mock_litellm_completion.call_count == 1


# ---------------------------------------------------------------------------
# call_context parity — the refreshed 重试重新发行的 *相同的* 逻辑呼叫，因此必须携带相同
# 的会话级线程上下文 (prompt_cache_key / x-LiteLLMsession-id) 作为初始尝试。 的异步之前
# 丢弃了线程上下文并退回到  LLM'的界限 _call_context偏离了同步路径 (#3443)。 参见
# OpenHands软件-智能体-SDK#5218.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("openhands.sdk.llm.llm.litellm_acompletion")
async def test_acompletion_retry_preserves_threaded_call_context(
    mock_litellm_acompletion,
):
    """异步完成重试在线程 call_context 下重新发出。"""
    mock_litellm_acompletion.side_effect = [
        _auth_error(),
        create_mock_response("Recovered"),
    ]

    llm = _make_llm()  # bound _call_context 是空的默认值
    llm.set_api_key_refresh_hook(lambda: "fresh_key")

    ctx = LLMCallContext(prompt_cache_key="threaded-pck", session_id="threaded-sid")
    await llm.acompletion(messages=_message(), call_context=ctx)

    assert mock_litellm_acompletion.call_count == 2
    initial_kwargs = mock_litellm_acompletion.call_args_list[0].kwargs
    retry_kwargs = mock_litellm_acompletion.call_args_list[1].kwargs
    # 重试必须使用与尝试 0 相同的线程上下文的新密钥 AND。
    assert retry_kwargs["api_key"] == "fresh_key"
    assert retry_kwargs["prompt_cache_key"] == initial_kwargs["prompt_cache_key"]
    assert retry_kwargs["prompt_cache_key"] == "threaded-pck"
    assert (
        retry_kwargs["extra_headers"]["x-litellm-session-id"]
        == initial_kwargs["extra_headers"]["x-litellm-session-id"]
        == "threaded-sid"
    )


@pytest.mark.asyncio
@patch("openhands.sdk.llm.llm.litellm_aresponses", new_callable=AsyncMock)
async def test_aresponses_retry_preserves_threaded_call_context(
    mock_litellm_aresponses,
):
    """异步响应重试在线程 call_context 下重新发布。"""
    mock_litellm_aresponses.side_effect = [
        _auth_error(),
        create_mock_responses_response("Recovered"),
    ]

    llm = _make_llm()  # bound _call_context 是空的默认值
    llm.set_api_key_refresh_hook(lambda: "fresh_key")

    ctx = LLMCallContext(prompt_cache_key="threaded-pck", session_id="threaded-sid")
    await llm.aresponses(messages=_message(), call_context=ctx)

    assert mock_litellm_aresponses.call_count == 2
    initial_kwargs = mock_litellm_aresponses.call_args_list[0].kwargs
    retry_kwargs = mock_litellm_aresponses.call_args_list[1].kwargs
    assert retry_kwargs["api_key"] == "fresh_key"
    assert retry_kwargs["prompt_cache_key"] == initial_kwargs["prompt_cache_key"]
    assert retry_kwargs["prompt_cache_key"] == "threaded-pck"
    assert (
        retry_kwargs["extra_headers"]["x-litellm-session-id"]
        == initial_kwargs["extra_headers"]["x-litellm-session-id"]
        == "threaded-sid"
    )
