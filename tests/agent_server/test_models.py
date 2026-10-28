"""测试 agent_server 个模型。"""

from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from openhands.agent_server.models import UpdateSecretsRequest
from openhands.sdk.secret import LookupSecret, StaticSecret


def test_update_secrets_request_string_conversion():
    """测试纯字符串机密是否转换为 StaticSecret 对象。"""

    # 使用纯字符串机密进行测试
    request = UpdateSecretsRequest(
        secrets={  # type: ignore[arg-type]
            "API_KEY": "plain-secret-value",
            "TOKEN": "another-secret",
        }
    )

    # 验证转换是否发生
    assert isinstance(request.secrets["API_KEY"], StaticSecret)
    assert isinstance(request.secrets["TOKEN"], StaticSecret)

    # 验证实际的机密值
    assert request.secrets["API_KEY"].get_value() == "plain-secret-value"
    assert request.secrets["TOKEN"].get_value() == "another-secret"


def test_update_secrets_request_proper_secret_source():
    """测试正确的 SecretSource 对象是否未被修改。"""

    static_secret = StaticSecret(value=SecretStr("static-value"))
    lookup_secret = LookupSecret(url="https://example.com/secret")

    request = UpdateSecretsRequest(
        secrets={
            "STATIC_SECRET": static_secret,
            "LOOKUP_SECRET": lookup_secret,
        }
    )

    # 验证对象是否被保留
    assert request.secrets["STATIC_SECRET"] is static_secret
    assert request.secrets["LOOKUP_SECRET"] is lookup_secret
    assert isinstance(request.secrets["STATIC_SECRET"], StaticSecret)
    assert isinstance(request.secrets["LOOKUP_SECRET"], LookupSecret)


def test_update_secrets_request_mixed_formats():
    """测试混合格式（字符串和 SecretSource 对象）是否可以协同工作。"""

    secrets_dict: dict[str, Any] = {
        "PLAIN_SECRET": "plain-value",
        "STATIC_SECRET": StaticSecret(value=SecretStr("static-value")),
        "LOOKUP_SECRET": LookupSecret(url="https://example.com/secret"),
    }
    request = UpdateSecretsRequest(secrets=secrets_dict)  # type: ignore[arg-type]

    # 验证所有类型是否正确
    assert isinstance(request.secrets["PLAIN_SECRET"], StaticSecret)
    assert isinstance(request.secrets["STATIC_SECRET"], StaticSecret)
    assert isinstance(request.secrets["LOOKUP_SECRET"], LookupSecret)

    # 验证值
    assert request.secrets["PLAIN_SECRET"].get_value() == "plain-value"
    assert request.secrets["STATIC_SECRET"].get_value() == "static-value"


def test_update_secrets_request_dict_without_kind():
    """测试不包含 'kind' 字段的字典值的处理。"""

    request = UpdateSecretsRequest(
        secrets={  # type: ignore[arg-type]
            "SECRET_WITH_VALUE": {
                "value": "secret-value",
                "description": "A test secret",
            },
        }
    )

    # 机密的值应转换为 StaticSecret
    assert isinstance(request.secrets["SECRET_WITH_VALUE"], StaticSecret)
    assert request.secrets["SECRET_WITH_VALUE"].get_value() == "secret-value"


def test_update_secrets_request_invalid_dict():
    """测试对没有“kind”或“value”字段的无效字典值的处理。"""

    # 这应该会引发错误，因为字典无效。错误可能是 KeyError 或 ValidationError，具体取决于
    # 失败的位置
    #
    with pytest.raises((ValidationError, KeyError)) as exc_info:
        UpdateSecretsRequest(
            secrets={  # type: ignore[arg-type]
                "SECRET_WITHOUT_VALUE": {"description": "No value"},
            }
        )

    # 验证错误是否与缺少“kind”字段有关
    error_details = str(exc_info.value)
    assert "kind" in error_details.lower()


def test_update_secrets_request_empty_secrets():
    """测试空的机密字典是否被正确处理。"""

    request = UpdateSecretsRequest(secrets={})
    assert request.secrets == {}


def test_update_secrets_request_invalid_input():
    """测试无效的输入类型是否得到适当处理。"""

    # 应保留非字典输入（稍后将失败验证）
    with pytest.raises(ValidationError):
        UpdateSecretsRequest(secrets="not-a-dict")  # type: ignore[arg-type]
