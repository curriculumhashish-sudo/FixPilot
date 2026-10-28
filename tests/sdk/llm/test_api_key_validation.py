import os
from unittest.mock import patch

from litellm.types.utils import ModelResponse
from pydantic import SecretStr

from openhands.sdk.llm import LLM, Message, TextContent


def test_empty_api_key_string_converted_to_none():
    """测试空字符串 API 键是否转换为 None。"""
    llm = LLM(
        usage_id="test-llm",
        model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        api_key=SecretStr(""),
    )
    assert llm.api_key is None


def test_whitespace_api_key_converted_to_none():
    """测试纯空白 API 键是否转换为 None。"""
    llm = LLM(
        usage_id="test-llm",
        model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        api_key=SecretStr("   "),
    )
    assert llm.api_key is None


def test_valid_api_key_preserved():
    """测试是否保留有效的 API 键。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("valid-key"), usage_id="test-llm")
    assert llm.api_key is not None
    assert isinstance(llm.api_key, SecretStr)
    assert llm.api_key.get_secret_value() == "valid-key"


def test_none_api_key_preserved():
    """测试 None API 键是否保留为 None。"""
    llm = LLM(
        model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        api_key=None,
        usage_id="test-llm",
    )
    assert llm.api_key is None


def test_empty_string_direct_input():
    """测试直接传递的空字符串（不是作为SecretStr）转换为None。"""  # noqa: E501
    # 这测试了有人可能直接传递字符串的情况字段验证器现在接受 str 并将其转换为 SecretStr
    #
    data = {"model": "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0", "api_key": ""}
    llm = LLM(**data, usage_id="test-llm")  # pyright: ignore[reportArgumentType]
    assert llm.api_key is None


def test_whitespace_string_direct_input():
    """测试直接传递的空白字符串是否转换为None。"""
    data = {
        "model": "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        "api_key": "   \t\n  ",
    }
    llm = LLM(**data, usage_id="test-llm")  # pyright: ignore[reportArgumentType]
    assert llm.api_key is None


def test_bedrock_model_with_none_api_key():
    """测试 Bedrock 模型是否与 None API 键（用于 IAM 认证）兼容。"""
    llm = LLM(
        model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        api_key=None,
        aws_region_name="us-east-1",
        usage_id="test-llm",
    )
    assert llm.api_key is None
    assert llm.aws_region_name == "us-east-1"


def test_bedrock_model_with_api_key_not_forwarded_to_litellm():
    """测试基岩模型永远不会转发 LLM.api_key 到 LiteLLM。

    LiteLLM 将基岩 api_key 参数解释为 AWS 持有者令牌。 转发非基岩密钥 (e.g. OpenAI/
    Anthropic) 破坏了 IAM/SigV4
     授权。
    """

    llm = LLM(
        usage_id="test-llm",
        model="us.anthropic.claude-3-sonnet-20240229-v1:0",
        api_key=SecretStr("sk-ant-not-a-bedrock-key"),
    )
    assert llm.api_key is not None
    assert isinstance(llm.api_key, SecretStr)
    provider = llm._provider_info
    assert provider is not None
    assert provider.api_key_for_litellm(llm.api_key.get_secret_value()) is None


def test_non_bedrock_model_with_valid_key():
    """测试非基岩模型是否可以使用有效的 API 键正常工作。"""
    llm = LLM(
        model="gpt-4o-mini", api_key=SecretStr("valid-openai-key"), usage_id="test-llm"
    )
    assert llm.api_key is not None
    assert isinstance(llm.api_key, SecretStr)
    assert llm.api_key.get_secret_value() == "valid-openai-key"


def test_aws_credentials_handling():
    """测试基岩模型的 AWS 凭据是否得到正确处理。"""
    llm = LLM(
        usage_id="test-llm",
        model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        api_key=None,
        aws_access_key_id=SecretStr("test-access-key"),
        aws_secret_access_key=SecretStr("test-secret-key"),
        aws_region_name="us-west-2",
    )
    assert llm.api_key is None
    assert llm.aws_access_key_id is not None
    assert isinstance(llm.aws_access_key_id, SecretStr)
    assert llm.aws_access_key_id.get_secret_value() == "test-access-key"
    assert llm.aws_secret_access_key is not None
    assert isinstance(llm.aws_secret_access_key, SecretStr)
    assert llm.aws_secret_access_key.get_secret_value() == "test-secret-key"
    assert llm.aws_region_name == "us-west-2"


def test_plain_string_api_key():
    """测试纯字符串 API 键是否转换为 SecretStr。"""
    llm = LLM(model="gpt-4o-mini", api_key="my-plain-string-key", usage_id="test-llm")
    assert llm.api_key is not None
    assert isinstance(llm.api_key, SecretStr)
    assert llm.api_key.get_secret_value() == "my-plain-string-key"


def test_plain_string_aws_credentials():
    """测试纯字符串 AWS 凭据是否转换为 SecretStr。"""
    llm = LLM(
        usage_id="test-llm",
        model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        api_key=None,
        aws_access_key_id="plain-access-key",
        aws_secret_access_key="plain-secret-key",
        aws_region_name="us-west-2",
    )
    assert llm.api_key is None
    assert llm.aws_access_key_id is not None
    assert isinstance(llm.aws_access_key_id, SecretStr)
    assert llm.aws_access_key_id.get_secret_value() == "plain-access-key"
    assert llm.aws_secret_access_key is not None
    assert isinstance(llm.aws_secret_access_key, SecretStr)
    assert llm.aws_secret_access_key.get_secret_value() == "plain-secret-key"
    assert llm.aws_region_name == "us-west-2"


def test_aws_session_token_handling():
    """测试 aws_session_token 是否被验证为机密。"""
    llm = LLM(
        usage_id="test-llm",
        model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        api_key=None,
        aws_access_key_id="access-key",
        aws_secret_access_key="secret-key",
        aws_session_token="session-token-value",
        aws_region_name="us-west-2",
    )
    assert isinstance(llm.aws_session_token, SecretStr)
    assert llm.aws_session_token.get_secret_value() == "session-token-value"


def test_aws_profile_name_handling():
    """测试 aws_profile_name 是否存储为纯字符串。"""
    llm = LLM(
        usage_id="test-llm",
        model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        api_key=None,
        aws_profile_name="dev-profile",
        aws_region_name="us-west-2",
    )
    assert llm.aws_profile_name == "dev-profile"


def test_aws_role_based_auth_fields():
    """测试是否接受 STS 基于角色的身份验证字段。"""
    llm = LLM(
        usage_id="test-llm",
        model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        api_key=None,
        aws_role_name="arn:aws:iam::123456789012:role/MyRole",
        aws_session_name="my-session",
        aws_region_name="us-west-2",
    )
    assert llm.aws_role_name == "arn:aws:iam::123456789012:role/MyRole"
    assert llm.aws_session_name == "my-session"


def test_aws_bedrock_runtime_endpoint():
    """测试是否接受自定义基岩端点。"""
    llm = LLM(
        usage_id="test-llm",
        model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        api_key=None,
        aws_bedrock_runtime_endpoint="https://my-proxy.example.com",
        aws_region_name="us-west-2",
    )
    assert llm.aws_bedrock_runtime_endpoint == "https://my-proxy.example.com"


def test_aws_bedrock_params_forwarded_to_litellm():
    """验证所有 AWS 参数都作为 kwargs 传递给 litellm.completion()。"""
    llm = LLM(
        usage_id="test-llm",
        model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        api_key=None,
        aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
        aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        aws_session_token="FwoGZXIvYXdzEBY",
        aws_region_name="us-west-2",
        aws_profile_name="dev-profile",
        aws_role_name="arn:aws:iam::123456789012:role/MyRole",
        aws_session_name="my-session",
        aws_bedrock_runtime_endpoint="https://my-proxy.example.com",
    )

    with patch("openhands.sdk.llm.llm.litellm_completion") as mock_completion:
        mock_completion.return_value = ModelResponse(
            id="test-id",
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hi"},
                    "finish_reason": "stop",
                }
            ],
            created=1234567890,
            model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
            object="chat.completion",
        )

        messages = [Message(role="user", content=[TextContent(text="Hello")])]
        llm.completion(messages=messages)

        kw = mock_completion.call_args[1]
        assert kw["aws_access_key_id"] == "AKIAIOSFODNN7EXAMPLE"
        assert kw["aws_secret_access_key"] == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert kw["aws_session_token"] == "FwoGZXIvYXdzEBY"
        assert kw["aws_region_name"] == "us-west-2"
        assert kw["aws_profile_name"] == "dev-profile"
        assert kw["aws_role_name"] == "arn:aws:iam::123456789012:role/MyRole"
        assert kw["aws_session_name"] == "my-session"
        assert kw["aws_bedrock_runtime_endpoint"] == "https://my-proxy.example.com"


def test_aws_env_vars_not_leaked_on_init(monkeypatch):
    """使用 AWS 信用构建 LLM 不得渗入 os.environ。

    将凭据写入流程环境将使一个对话的凭据被多租户 Agent Server 中的另一个对话接收（问
    题 #3138）。 它们必须通过每次调用流动
    ``_aws_kwargs()`` 代替。
    """
    for k in [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_REGION_NAME",
    ]:
        monkeypatch.delenv(k, raising=False)

    LLM(
        usage_id="test-llm",
        model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        api_key=None,
        aws_access_key_id="AKID",
        aws_secret_access_key="SECRET",
        aws_session_token="TOKEN",
        aws_region_name="us-west-2",
    )

    assert "AWS_ACCESS_KEY_ID" not in os.environ
    assert "AWS_SECRET_ACCESS_KEY" not in os.environ
    assert "AWS_SESSION_TOKEN" not in os.environ
    assert "AWS_REGION_NAME" not in os.environ


def test_aws_kwargs_returns_all_params():
    """验证 _aws_kwargs() 从 LLM 字段构建正确的字典。"""
    llm = LLM(
        usage_id="test-llm",
        model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        api_key=None,
        aws_access_key_id="AKID",
        aws_secret_access_key="SECRET",
        aws_session_token="TOKEN",
        aws_region_name="us-west-2",
        aws_profile_name="dev",
        aws_role_name="arn:aws:iam::123:role/R",
        aws_session_name="sess",
        aws_bedrock_runtime_endpoint="https://proxy.example.com",
    )

    kw = llm._aws_kwargs()
    assert kw == {
        "aws_access_key_id": "AKID",
        "aws_secret_access_key": "SECRET",
        "aws_session_token": "TOKEN",
        "aws_region_name": "us-west-2",
        "aws_profile_name": "dev",
        "aws_role_name": "arn:aws:iam::123:role/R",
        "aws_session_name": "sess",
        "aws_bedrock_runtime_endpoint": "https://proxy.example.com",
    }
