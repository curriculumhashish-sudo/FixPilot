"""集成测试 for LLM log_completions feature.

此测试验证当与真实的 LLM 响应一起使用时，log_completions 不会产生 Pydantic 序列化警告
。
"""

import json
import os
import tempfile
import warnings
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from openhands.sdk.llm import LLM, Message, TextContent

# 导入常用测试实用程序
from tests.conftest import create_mock_litellm_response


def test_llm_log_completions_integration_no_warnings():
    """测试启用 log_completions 的 LLM 不会产生警告。

    这是一项端到端测试，它创建启用了 log_completions 的实际 LLM 实例，并验证是否不会
    引发序列化警告。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建 LLM 并启用 log_completions
        llm = LLM(
            model="gpt-4o",
            api_key=SecretStr("test-key"),
            usage_id="test-log-completions-llm",
            log_completions=True,
            log_completions_folder=temp_dir,
            num_retries=0,
        )

        # 创建现实的模拟对象响应
        mock_response = create_mock_litellm_response(
            content="This is a test response with realistic structure.",
            response_id="integration-test-id",
            model="gpt-4o",
            prompt_tokens=100,
            completion_tokens=50,
            finish_reason="stop",
        )

        # 模拟对象 LiteLLM 完成调用
        with patch("openhands.sdk.llm.llm.litellm_completion") as mock_completion:
            mock_completion.return_value = mock_response

            # 捕获任何警告
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")

                # 进行完成调用
                messages = [
                    Message(
                        role="user",
                        content=[TextContent(text="Test message")],
                    )
                ]
                llm.completion(messages)

                # 检查 Pydantic 序列化警告
                pydantic_warnings = [
                    warning
                    for warning in w
                    if "PydanticSerializationUnexpectedValue" in str(warning.message)
                    or "Circular reference detected" in str(warning.message)
                ]

                warning_messages = [str(pw.message) for pw in pydantic_warnings]
                assert len(pydantic_warnings) == 0, (
                    f"Got unexpected serialization warnings: {warning_messages}"
                )

        # 验证是否已创建日志文件
        log_files = os.listdir(temp_dir)
        assert len(log_files) == 1, f"Expected 1 log file, got {len(log_files)}"

        # 验证日志文件有效 JSON 并包含预期数据
        log_path = os.path.join(temp_dir, log_files[0])
        with open(log_path) as f:
            log_data = json.loads(f.read())

        assert "response" in log_data
        assert "cost" in log_data
        assert "timestamp" in log_data
        assert "latency_sec" in log_data


def test_llm_log_completions_with_tool_calls():
    """在响应中使用工具调用测试 log_completions。

    工具调用为响应结构增加了额外的复杂性，因此我们也希望确保它们序列化正确。
    """
    from litellm.types.utils import (
        ChatCompletionMessageToolCall,
        Choices,
        Function,
        Message as LiteLLMMessage,
        ModelResponse,
        Usage,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建 LLM 并启用 log_completions
        llm = LLM(
            model="gpt-4o",
            api_key=SecretStr("test-key"),
            usage_id="test-tool-calls-llm",
            log_completions=True,
            log_completions_folder=temp_dir,
            num_retries=0,
        )

        # 使用工具调用创建响应
        tool_call = ChatCompletionMessageToolCall(
            id="call_1",
            function=Function(name="test_function", arguments='{"param": "value"}'),
            type="function",
        )
        message = LiteLLMMessage(
            role="assistant",
            content=None,
            tool_calls=[tool_call],
        )
        choice = Choices(
            finish_reason="tool_calls",
            index=0,
            message=message,
        )
        usage = Usage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_response = ModelResponse(
            id="tool-call-test-id",
            choices=[choice],
            created=1234567890,
            model="gpt-4o",
            object="chat.completion",
            usage=usage,
        )

        # 模拟对象 LiteLLM 完成调用
        with patch("openhands.sdk.llm.llm.litellm_completion") as mock_completion:
            mock_completion.return_value = mock_response

            # 捕获任何警告
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")

                # 进行完成调用
                messages = [
                    Message(
                        role="user",
                        content=[TextContent(text="Call a tool")],
                    )
                ]
                llm.completion(messages)

                # 检查 Pydantic 序列化警告
                pydantic_warnings = [
                    warning
                    for warning in w
                    if "PydanticSerializationUnexpectedValue" in str(warning.message)
                    or "Circular reference detected" in str(warning.message)
                ]

                warning_messages = [str(pw.message) for pw in pydantic_warnings]
                assert len(pydantic_warnings) == 0, (
                    f"Got unexpected serialization warnings: {warning_messages}"
                )

        # 验证是否已创建日志文件
        log_files = os.listdir(temp_dir)
        assert len(log_files) == 1

        # 验证日志包含工具调用信息
        log_path = os.path.join(temp_dir, log_files[0])
        with open(log_path) as f:
            log_data = json.loads(f.read())

        assert "response" in log_data
        assert log_data["response"]["choices"][0]["message"]["tool_calls"] is not None


def _read_only_log(log_dir: str) -> str:
    log_files = os.listdir(log_dir)
    assert len(log_files) == 1, f"Expected 1 log file, got {log_files}"
    with open(os.path.join(log_dir, log_files[0]), encoding="utf-8") as f:
        return f.read()


def _completion_with_provider_auth_header(
    log_dir: str,
    *,
    extra_headers: dict[str, str],
    fail: bool = False,
    error_message: str = "provider failed",
    completion_kwargs: dict[str, Any] | None = None,
    provider_metadata_api_key: str | None = None,
) -> dict[str, Any]:
    """运行一个补全，其提供程序在适当的位置添加 ``Authorization``。

    一些 LiteLLM 提供程序处理程序 (e.g. DeepSeek) 在调用期间将持有者令牌写入调用者的
    ``extra_headers`` 字典中。
    """
    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="test-log-completions-headers",
        log_completions=True,
        log_completions_folder=log_dir,
        extra_headers=extra_headers,
        num_retries=0,
    )

    received_kwargs: dict[str, Any] = {}

    def provider(**kwargs):
        received_kwargs.update(kwargs)
        kwargs["extra_headers"]["Authorization"] = "Bearer provider-secret"
        if provider_metadata_api_key is not None:
            metadata = kwargs["metadata"]
            assert isinstance(metadata, dict)
            metadata["api_key"] = provider_metadata_api_key
        if fail:
            raise ValueError(error_message)
        return create_mock_litellm_response(content="ok")

    messages = [
        Message(
            role="system", content=[TextContent(text="You are a helpful assistant.")]
        ),
        Message(role="user", content=[TextContent(text="hi")]),
    ]
    with patch("openhands.sdk.llm.llm.litellm_completion", side_effect=provider):
        if fail:
            with pytest.raises(Exception):
                llm.completion(messages, **(completion_kwargs or {}))
        else:
            llm.completion(messages, **(completion_kwargs or {}))
    return received_kwargs


@pytest.mark.parametrize("fail", [False, True], ids=["response", "error"])
def test_log_completions_omit_provider_added_auth_header(fail):
    with tempfile.TemporaryDirectory() as temp_dir:
        _completion_with_provider_auth_header(
            temp_dir, extra_headers={"X-Trace-Id": "trace-1"}, fail=fail
        )
        raw = _read_only_log(temp_dir)

    logged_headers = json.loads(raw)["kwargs"]["extra_headers"]
    assert "provider-secret" not in raw
    assert "Authorization" not in logged_headers
    assert logged_headers["X-Trace-Id"] == "trace-1"


def test_log_completions_redact_caller_credential_headers():
    with tempfile.TemporaryDirectory() as temp_dir:
        _completion_with_provider_auth_header(
            temp_dir,
            extra_headers={
                "X-Trace-Id": "trace-1",
                "api-key": "caller-api-key",
                "Proxy-Authorization": "Basic caller-proxy-secret",
            },
        )
        raw = _read_only_log(temp_dir)

    logged_headers = json.loads(raw)["kwargs"]["extra_headers"]
    assert "caller-api-key" not in raw
    assert "caller-proxy-secret" not in raw
    assert logged_headers["api-key"] == "<redacted>"
    assert logged_headers["Proxy-Authorization"] == "<redacted>"
    assert logged_headers["X-Trace-Id"] == "trace-1"


@pytest.mark.parametrize("fail", [False, True], ids=["response", "error"])
@pytest.mark.parametrize("credential_type", [str, SecretStr], ids=["str", "SecretStr"])
def test_log_completions_redact_credential_options_without_changing_request(
    credential_type: type[str] | type[SecretStr], fail: bool
):
    api_key = credential_type("caller-secret")
    aws_secret_access_key = credential_type("aws-secret")
    with tempfile.TemporaryDirectory() as temp_dir:
        received_kwargs = _completion_with_provider_auth_header(
            temp_dir,
            extra_headers={"X-Trace-Id": "trace-1"},
            fail=fail,
            completion_kwargs={
                "api_key": api_key,
                "aws_secret_access_key": aws_secret_access_key,
                "max_completion_tokens": 42,
            },
        )
        raw = _read_only_log(temp_dir)

    logged_kwargs = json.loads(raw)["kwargs"]
    assert received_kwargs["api_key"] == api_key
    assert received_kwargs["aws_secret_access_key"] == aws_secret_access_key
    assert received_kwargs["max_completion_tokens"] == 42
    assert "caller-secret" not in raw
    assert "aws-secret" not in raw
    assert logged_kwargs["api_key"] == "<redacted>"
    assert logged_kwargs["aws_secret_access_key"] == "<redacted>"
    assert logged_kwargs["max_completion_tokens"] == 42
    assert logged_kwargs["extra_headers"]["X-Trace-Id"] == "trace-1"


def test_log_completions_redact_and_detach_nested_request_credentials():
    metadata = {
        "api_key": "caller-nested-secret",
        "trace_id": "trace-2",
        "nested": [{"access_token": "list-secret"}],
        "wrapped": SecretStr("wrapped-secret"),
    }
    with tempfile.TemporaryDirectory() as temp_dir:
        received_kwargs = _completion_with_provider_auth_header(
            temp_dir,
            extra_headers={"X-Trace-Id": "trace-1"},
            completion_kwargs={"metadata": metadata},
            provider_metadata_api_key="provider-nested-secret",
        )
        raw = _read_only_log(temp_dir)

    logged_metadata = json.loads(raw)["kwargs"]["metadata"]
    assert received_kwargs["metadata"] is metadata
    assert metadata["api_key"] == "provider-nested-secret"
    assert metadata["nested"][0]["access_token"] == "list-secret"
    for secret in (
        "caller-nested-secret",
        "provider-nested-secret",
        "list-secret",
        "wrapped-secret",
    ):
        assert secret not in raw
    assert logged_metadata["api_key"] == "<redacted>"
    assert logged_metadata["nested"] == [{"access_token": "<redacted>"}]
    assert logged_metadata["trace_id"] == "trace-2"


@pytest.mark.parametrize(
    "error_message",
    [
        "provider failed: api_key='error-secret'",
        "provider failed: {'private_key': 'first-line\nerror-secret\nlast-line'}",
    ],
    ids=["api-key", "multiline"],
)
def test_log_completions_redact_credentials_in_provider_error(error_message):
    with tempfile.TemporaryDirectory() as temp_dir:
        _completion_with_provider_auth_header(
            temp_dir,
            extra_headers={"X-Trace-Id": "trace-1"},
            fail=True,
            error_message=error_message,
        )
        raw = _read_only_log(temp_dir)

    error = json.loads(raw)["error"]
    assert "error-secret" not in raw
    assert "<redacted>" in error["message"]
    assert "<redacted>" in error["repr"]
    assert "<redacted>" in error["traceback"]
