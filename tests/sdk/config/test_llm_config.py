import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError

from openhands.sdk.llm import LLM


def test_llm_config_secret_str():
    """测试 api_key 是否被正确处理为 SecretStr。"""
    config = LLM(
        model="gpt-4o-mini", api_key=SecretStr("secret-key"), usage_id="test-llm"
    )
    assert config.api_key is not None
    assert isinstance(config.api_key, SecretStr)
    assert config.api_key.get_secret_value() == "secret-key"
    # 确保机密未在字符串表示形式中暴露
    assert "secret-key" not in str(config)


def test_llm_config_aws_credentials():
    """测试 AWS 凭据处理。"""
    config = LLM(
        usage_id="test-llm",
        model="gpt-4o-mini",
        aws_access_key_id=SecretStr("test-access-key"),
        aws_secret_access_key=SecretStr("test-secret-key"),
        aws_region_name="us-east-1",
    )
    assert config.aws_access_key_id is not None
    assert isinstance(config.aws_access_key_id, SecretStr)
    assert config.aws_access_key_id.get_secret_value() == "test-access-key"
    assert config.aws_secret_access_key is not None
    assert isinstance(config.aws_secret_access_key, SecretStr)
    assert config.aws_secret_access_key.get_secret_value() == "test-secret-key"
    assert config.aws_region_name == "us-east-1"


def test_llm_config_openrouter_defaults():
    """测试 OpenRouter 默认值。"""
    config = LLM(model="gpt-4o-mini", usage_id="test-llm")
    assert config.openrouter_site_url == "https://docs.all-hands.dev/"
    assert config.openrouter_app_name == "OpenHands"


def test_llm_config_post_init_openrouter_does_not_set_env():
    """OpenRouter 网站/应用程序必须不融入 os.environ。

    构建一个 LLM (可能在多租户环境中按会话处理) Agent Server用于设置的
    ``OR_SITE_URL`` / ``OR_APP_NAME``它会通过共
    享进程环境泄露到会话中（issue #3138）。 这些值现在应该通过每次调用流动
    ``extra_headers`` 代替。
    """
    with patch.dict(os.environ, {}, clear=True):
        llm = LLM(
            model="gpt-4o-mini",
            openrouter_site_url="https://custom.site.com",
            openrouter_app_name="CustomApp",
            usage_id="test-llm",
        )
        assert "OR_SITE_URL" not in os.environ
        assert "OR_APP_NAME" not in os.environ
        # 值仍然通过每次调用助手传递。
        assert llm._openrouter_headers() == {
            "HTTP-Referer": "https://custom.site.com",
            "X-Title": "CustomApp",
        }


def test_llm_config_post_init_reasoning_effort_default():
    """测试 reasoning_effort 默认为高。"""
    config = LLM(model="gpt-4o-mini", usage_id="test-llm")
    assert config.reasoning_effort == "high"

    # 测试一下Gemini机型也默认高
    config = LLM(model="gemini-2.5-pro-experimental", usage_id="test-llm")
    assert config.reasoning_effort == "high"

    # 测试显式 reasoning_effort 是否被保留
    config = LLM(model="gpt-4o-mini", reasoning_effort="low", usage_id="test-llm")
    assert config.reasoning_effort == "low"
    config = LLM(model="gpt-4o-mini", reasoning_effort="xhigh", usage_id="test-llm")
    assert config.reasoning_effort == "xhigh"


def test_llm_config_post_init_azure_api_version():
    """测试 Azure 模型是否获得默认 API 版本。"""
    config = LLM(model="azure/gpt-4o-mini", usage_id="test-llm")
    assert config.api_version == "2024-12-01-preview"

    # 测试非 Azure 模型是否未获得默认 API 版本
    config = LLM(model="gpt-4o-mini", usage_id="test-llm")
    assert config.api_version is None

    # 测试是否保留显式 API 版本
    config = LLM(
        model="azure/gpt-4o-mini", api_version="custom-version", usage_id="test-llm"
    )
    assert config.api_version == "custom-version"


def test_llm_config_post_init_aws_does_not_set_env():
    """AWS 凭据必须在 init 时将不写入 os.environ。

    这样做会在多租户 Agent Server 中的对话中泄漏凭据（问题 #3138）。 它们通过每次呼叫
    转发
    ``_aws_kwargs()`` 代替。
    """
    with patch.dict(os.environ, {}, clear=True):
        llm = LLM(
            usage_id="test-llm",
            model="gpt-4o-mini",
            aws_access_key_id=SecretStr("test-access-key"),
            aws_secret_access_key=SecretStr("test-secret-key"),
            aws_region_name="us-west-2",
        )
        assert "AWS_ACCESS_KEY_ID" not in os.environ
        assert "AWS_SECRET_ACCESS_KEY" not in os.environ
        assert "AWS_REGION_NAME" not in os.environ
        # 值仍然通过每次调用助手传递。
        kw = llm._aws_kwargs()
        assert kw["aws_access_key_id"] == "test-access-key"
        assert kw["aws_secret_access_key"] == "test-secret-key"
        assert kw["aws_region_name"] == "us-west-2"


def test_llm_config_log_completions_folder_default():
    """测试 log_completions_folder 是否具有默认值。"""
    config = LLM(model="gpt-4o-mini", usage_id="test-llm")
    assert config.log_completions_folder is not None
    assert "completions" in config.log_completions_folder


def test_llm_config_extra_fields_permitted():
    """测试是否禁止额外字段。"""
    LLM(model="gpt-4o-mini", invalid_field="should_be_permitted", usage_id="test-llm")  # type: ignore


def test_llm_config_validation():
    """使用 ge 约束测试 LLM 字段的验证。"""
    # 测试具有 ge 约束的字段是否拒绝负值
    with pytest.raises(ValidationError) as exc_info:
        LLM(
            model="gpt-4o-mini",
            num_retries=-1,  # 应该失败：ge=0
            retry_multiplier=-1,  # 应该失败：ge=0
            retry_min_wait=-1,  # 应该失败：ge=0
            retry_max_wait=-1,  # 应该失败：ge=0
            timeout=-1,  # 应该失败：ge=0
            max_message_chars=-1,  # 应该失败：ge=1
            temperature=-1,  # 应该失败：ge=0
            top_p=-1,  # 应该失败：ge=0
            usage_id="test-llm",
        )

    # 验证验证错误是否包含预期的字段名称
    error_str = str(exc_info.value)
    expected_fields = [
        "num_retries",
        "retry_multiplier",
        "retry_min_wait",
        "retry_max_wait",
        "timeout",
        "max_message_chars",
        "temperature",
        "top_p",
    ]
    for field in expected_fields:
        assert field in error_str

    # 测试有效值（>=约束）是否正常工作
    config = LLM(
        model="gpt-4o-mini",
        num_retries=0,  # 有效：ge=0
        retry_multiplier=0.0,  # 有效：ge=0
        retry_min_wait=0,  # 有效：ge=0
        retry_max_wait=0,  # 有效：ge=0
        timeout=0,  # 有效：ge=0
        max_message_chars=1,  # 有效：ge=1
        temperature=0.0,  # 有效：ge=0
        top_p=0.0,  # 有效：ge=0
        usage_id="test-llm",
    )
    assert config.num_retries == 0
    assert config.retry_multiplier == 0.0
    assert config.retry_min_wait == 0
    assert config.retry_max_wait == 0
    assert config.timeout == 0
    assert config.max_message_chars == 1
    assert config.temperature == 0.0
    assert config.top_p == 0.0


def test_llm_config_optional_fields():
    """测试可选字段是否可以为 None。"""
    config = LLM(
        model="gpt-4o-mini",
        api_key=None,
        base_url=None,
        api_version=None,
        aws_access_key_id=None,
        aws_secret_access_key=None,
        aws_region_name=None,
        timeout=None,
        top_k=None,
        max_input_tokens=None,
        max_output_tokens=None,
        input_cost_per_token=None,
        output_cost_per_token=None,
        ollama_base_url=None,
        disable_vision=None,
        disable_stop_word=None,
        custom_tokenizer=None,
        reasoning_effort=None,
        seed=None,
        usage_id="test-llm",
    )

    assert config.api_key is None
    assert config.base_url is None
    assert config.api_version is None
    assert config.aws_access_key_id is None
    assert config.aws_secret_access_key is None
    assert config.aws_region_name is None
    assert config.timeout is None
    assert config.top_k is None
    assert config.max_input_tokens is None
    assert config.max_output_tokens is None
    assert config.effective_max_input_tokens == 128000
    assert config.effective_max_output_tokens == 16384
    assert config.input_cost_per_token is None
    assert config.output_cost_per_token is None
    assert config.ollama_base_url is None
    assert config.disable_vision is None
    assert config.disable_stop_word is None
    assert config.custom_tokenizer is None
    assert config.reasoning_effort is None  # 明确设置为 None 覆盖默认值
    assert config.seed is None
