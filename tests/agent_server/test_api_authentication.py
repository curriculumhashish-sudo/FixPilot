"""
集成测试对于 API 身份验证，使用基于依赖关系的身份验证。 测试 FastAPI 应用程序的完整身
份验证流程。
"""

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from openhands.agent_server.api import _find_http_exception, create_app
from openhands.agent_server.config import Config
from openhands.agent_server.dependencies import get_conversation_service
from openhands.agent_server.openai.router import _parse_observability_overrides


@pytest.fixture
def client():
    """为没有身份验证的 API 创建一个测试客户端。"""
    return TestClient(create_app())


@pytest.fixture
def client_with_auth():
    """使用会话 API 密钥身份验证创建测试客户端。"""
    config = Config(session_api_keys=["test-key-123"])
    app = create_app(config)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_with_multiple_keys():
    """创建具有多个会话 API 密钥的测试客户端。"""
    config = Config(session_api_keys=["key-1", "key-2", "key-3"])
    app = create_app(config)
    return TestClient(app, raise_server_exceptions=False)


def test_find_http_exception():
    """测试用于查找 HTTPExceptions 在 ExceptionGroups 中的辅助函数。"""
    # HTTPException
    http_exc = HTTPException(status_code=401, detail="Unauthorized")
    exc_group = BaseExceptionGroup("test", [http_exc])

    found = _find_http_exception(exc_group)
    assert found is http_exc

    # HTTPException 首先测试多个异常
    other_exc = ValueError("Some error")
    exc_group = BaseExceptionGroup("test", [http_exc, other_exc])

    found = _find_http_exception(exc_group)
    assert found is http_exc

    # 测试无 HTTPException
    exc_group = BaseExceptionGroup("test", [other_exc])

    found = _find_http_exception(exc_group)
    assert found is None

    # 使用嵌套 ExceptionGroup 进行测试
    nested_group = BaseExceptionGroup("nested", [http_exc])
    outer_group = BaseExceptionGroup("outer", [other_exc, nested_group])

    found = _find_http_exception(outer_group)
    assert found is http_exc


def test_api_no_auth_required(client):
    """当未配置任何键时，测试 API 是否可以在没有身份验证的情况下工作。"""
    # 测试服务器详细信息端点（应始终可访问）
    response = client.get("/server_info")
    # 如果端点不存在，则可能返回 404，但不应返回 401
    assert response.status_code != 401


def test_api_auth_missing_key(client_with_auth):
    """集成测试：缺少 X-Session-API-Key 应返回 401。"""
    response = client_with_auth.get("/api/conversations")
    assert response.status_code == 401


def test_api_auth_invalid_key(client_with_auth):
    """集成测试：无效的 X-Session-API-Key 应返回 401。"""
    response = client_with_auth.get(
        "/api/conversations", headers={"X-Session-API-Key": "wrong-key"}
    )
    assert response.status_code == 401


def test_api_auth_valid_key(client_with_auth):
    """集成测试：有效的 X-Session-API-Key 应允许访问。"""
    response = client_with_auth.get(
        "/api/conversations", headers={"X-Session-API-Key": "test-key-123"}
    )
    # 不应是 401（可能是其他状态，具体取决于端点实现）
    assert response.status_code != 401


def test_api_auth_multiple_keys_all_valid(client_with_multiple_keys):
    """集成测试：所有配置的键都应该起作用。"""
    for key in ["key-1", "key-2", "key-3"]:
        response = client_with_multiple_keys.get(
            "/api/conversations", headers={"X-Session-API-Key": key}
        )
        assert response.status_code != 401, f"Key {key} should be valid"


def test_api_auth_multiple_keys_invalid(client_with_multiple_keys):
    """集成测试：配置多个密钥时无效密钥应该失败。"""
    response = client_with_multiple_keys.get(
        "/api/conversations", headers={"X-Session-API-Key": "invalid-key"}
    )
    assert response.status_code == 401


def test_api_server_details_no_auth_required(client_with_auth):
    """集成测试：服务器详细信息端点不应需要身份验证。"""
    # 服务器信息端点无需授权即可访问
    response = client_with_auth.get("/server_info")
    assert response.status_code != 401


def test_openai_routes_accept_bearer_session_key(client_with_auth, monkeypatch):
    class EmptyProfileStore:
        def list_summaries(self) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(
        "openhands.agent_server.openai.service.get_llm_profile_store", EmptyProfileStore
    )

    response = client_with_auth.get("/v1/models")
    assert response.status_code == 401

    response = client_with_auth.get(
        "/v1/models", headers={"Authorization": "Bearer test-key-123"}
    )
    assert response.status_code == 200

    response = client_with_auth.get(
        "/v1/models", headers={"X-Session-API-Key": "test-key-123"}
    )
    assert response.status_code == 200


def test_openai_observability_headers_parse_to_conversation_overrides():
    overrides = _parse_observability_overrides(
        span_name="pr_review_evaluation",
        tags="pr-review,evaluation",
        metadata='{"repo":"OpenHands/software-agent-sdk","pr_number":123}',
    )

    assert overrides == {
        "observability_span_name": "pr_review_evaluation",
        "observability_tags": ["pr-review", "evaluation"],
        "observability_metadata": {
            "repo": "OpenHands/software-agent-sdk",
            "pr_number": 123,
        },
    }


def test_openai_observability_headers_reject_invalid_span_name():
    with pytest.raises(HTTPException) as exc_info:
        _parse_observability_overrides(
            span_name="bad span name",
            tags=None,
            metadata=None,
        )

    assert exc_info.value.status_code == 422
    json.dumps(exc_info.value.detail)


def test_openai_route_invalid_observability_header_returns_422(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("run_chat_completion should not run for invalid headers")

    monkeypatch.setattr(
        "openhands.agent_server.openai.router.run_chat_completion",
        fail_if_called,
    )
    app = create_app(Config(session_api_keys=[]))
    app.dependency_overrides[get_conversation_service] = lambda: object()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/v1/chat/completions",
        headers={"X-OpenHands-Observability-Span-Name": "bad span name"},
        json={
            "model": "openhands/test",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 422
    assert "Observability span name" in response.text


def test_api_protected_endpoints_require_auth(client_with_auth):
    """测试 /api 前缀下的 API 端点是否需要身份验证。"""
    protected_endpoints = [
        ("/api/conversations", None),
        ("/api/tools/", None),
        ("/api/file/download", {"path": "/test.txt"}),
    ]

    for endpoint, params in protected_endpoints:
        # 没有 auth 标头
        response = client_with_auth.get(endpoint, params=params)
        assert response.status_code == 401, f"Endpoint {endpoint} should require auth"

        # 具有有效的身份验证标头
        response = client_with_auth.get(
            endpoint, params=params, headers={"X-Session-API-Key": "test-key-123"}
        )
        assert response.status_code != 401, (
            f"Endpoint {endpoint} should accept valid auth"
        )


def test_api_case_sensitive_keys(client_with_auth):
    """测试 API 键匹配是否区分大小写。"""
    # 使用混合大小写密钥创建客户端
    config = Config(session_api_keys=["Test-Key-123"])
    app = create_app(config)
    client = TestClient(app, raise_server_exceptions=False)

    # 精确匹配应该有效
    response = client.get(
        "/api/conversations", headers={"X-Session-API-Key": "Test-Key-123"}
    )
    assert response.status_code != 401

    # 大小写不匹配应该会失败
    response = client.get(
        "/api/conversations", headers={"X-Session-API-Key": "test-key-123"}
    )
    assert response.status_code == 401


def test_api_header_case_insensitive():
    """测试 HTTP 标头名称不区分大小写。"""
    config = Config(session_api_keys=["test-key"])
    app = create_app(config)
    client = TestClient(app, raise_server_exceptions=False)

    header_variations = [
        "X-Session-API-Key",
        "x-session-api-key",
        "X-SESSION-API-KEY",
        "x-Session-Api-Key",
    ]

    for header_name in header_variations:
        response = client.get("/api/conversations", headers={header_name: "test-key"})
        assert response.status_code != 401, f"Header {header_name} should work"


def test_api_special_character_keys():
    """测试带有特殊字符的 API 键。"""
    special_keys = [
        "key-with-dashes",
        "key_with_underscores",
        "key.with.dots",
        "key@with#special$chars",
    ]

    config = Config(session_api_keys=special_keys)
    app = create_app(config)
    client = TestClient(app, raise_server_exceptions=False)

    for key in special_keys:
        response = client.get("/api/conversations", headers={"X-Session-API-Key": key})
        assert response.status_code != 401, f"Special key {key} should work"


def test_api_empty_key_list():
    """测试空的 session_api_keys 列表禁用身份验证。"""
    config = Config(session_api_keys=[])
    app = create_app(config)
    client = TestClient(app)

    # 应该可以在没有任何身份验证的情况下工作
    response = client.get("/api/conversations")
    assert response.status_code != 401


def test_api_websocket_authentication():
    """测试 WebSocket 连接也遵循身份验证。"""
    config = Config(session_api_keys=["test-key"])
    app = create_app(config)
    client = TestClient(app)

    # 没有身份验证 -> 应该失败
    with pytest.raises(Exception):
        with client.websocket_connect("/sockets/bash-events"):
            assert False, "WebSocket connection should have failed without auth"

    # Query-param 身份验证 -> 应该可以工作（浏览器兼容）
    with client.websocket_connect("/sockets/bash-events?session_api_key=test-key"):
        pass

    # 标头身份验证 -> 应该适用于非浏览器客户端
    with client.websocket_connect(
        "/sockets/bash-events",
        headers={"X-Session-API-Key": "test-key"},
    ):
        pass

    # 查询参数应优先于标头（浏览器兼容的逃生舱口）。
    with client.websocket_connect(
        "/sockets/bash-events?session_api_key=test-key",
        headers={"X-Session-API-Key": "wrong-key"},
    ):
        pass

    # 如果查询参数存在且错误，即使标头正确，连接也会失败。
    #
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/sockets/bash-events?session_api_key=wrong-key",
            headers={"X-Session-API-Key": "test-key"},
        ):
            assert False, "WebSocket connection should have failed with wrong query key"

    # 错误的标头 -> 应该失败
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/sockets/bash-events",
            headers={"X-Session-API-Key": "wrong-key"},
        ):
            assert False, "WebSocket connection should have failed with wrong key"


def test_api_websocket_no_auth_required():
    """测试禁用身份验证时 WebSocket 连接是否正常工作。"""
    config = Config(session_api_keys=[])
    app = create_app(config)
    client = TestClient(app)

    with client.websocket_connect("/sockets/bash-events"):
        pass


def test_api_options_requests():
    """测试 OPTIONS 请求为 CORS 预检工作。"""
    config = Config(session_api_keys=["test-key"])
    app = create_app(config)
    client = TestClient(app)

    # OPTIONS 请求应该在没有身份验证的情况下对 CORS 起作用
    response = client.options("/api/conversations")
    # 不应是 401，可能是 405（不允许的方法）或 200
    assert response.status_code != 401


def test_api_dependency_injection_openapi():
    """测试依赖项是否出现在 OpenAPI 文档中。"""
    config = Config(session_api_keys=["test-key"])
    app = create_app(config)
    client = TestClient(app)

    # 获取OpenAPI模式
    response = client.get("/openapi.json")
    assert response.status_code == 200

    openapi_schema = response.json()

    # 检查模式中是否定义了安全。具体结构取决于 FastAPI 如何生成模式。这是一个基本检查，
    # 确保模式成功生成
    #
    assert "openapi" in openapi_schema
    assert "paths" in openapi_schema


def test_api_multiple_concurrent_requests():
    """测试使用不同键的多个并发请求是否正常工作。"""
    config = Config(session_api_keys=["key-1", "key-2"])
    app = create_app(config)
    client = TestClient(app, raise_server_exceptions=False)

    # 使用不同的键模拟并发个请求
    responses = []

    for key in ["key-1", "key-2", "invalid-key"]:
        response = client.get("/api/conversations", headers={"X-Session-API-Key": key})
        responses.append((key, response.status_code))

    # 有效的密钥应该有效
    assert responses[0][1] != 401  # 键1
    assert responses[1][1] != 401  # 键2

    # 无效密钥应该会失败
    assert responses[2][1] == 401  # 无效密钥


def test_api_error_response_format():
    """测试身份验证错误是否返回正确的 HTTP 401 状态。"""
    config = Config(session_api_keys=["test-key"])
    app = create_app(config)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/conversations")
    assert response.status_code == 401

    # 响应可能包含额外详情，但状态码是最重要FastAPI的HTTPException，状态码为401时应返回
    # 正确HTTP状态
    #
