"""测试 Agent Server 中的 RequestValidationError 消毒。

验证 422 错误响应不会泄漏敏感字段，例如
``api_key``、``env`` 或其他机密轴承请求值。

Refs: OpenHands/评估#385
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from openhands.agent_server.api import (
    _add_exception_handlers,
    _sanitize_validation_errors,
)


# ---------------------------------------------------------------------------
# 单元测试为 _sanitize_validation_errors
# ---------------------------------------------------------------------------


class TestSanitizeValidationErrors:
    """单元测试为 _sanitize_validation_errors 助手。"""

    def test_redacts_api_key_in_input(self):
        """输入字典内的 api_key 值应为已脱敏。"""
        errors = [
            {
                "type": "missing",
                "loc": ["body", "agent", "tools"],
                "msg": "Field required",
                "input": {
                    "agent": {
                        "llm": {
                            "model": "gpt-4",
                            "api_key": "sk-real-secret-key-12345",
                        },
                        "tools": [],
                    },
                    "workspace": {"working_dir": "/tmp"},
                },
            }
        ]
        result = _sanitize_validation_errors(errors)
        assert len(result) == 1
        agent_input = result[0]["input"]["agent"]
        assert agent_input["llm"]["api_key"] == "<redacted>"
        # 应保留非机密字段
        assert agent_input["llm"]["model"] == "gpt-4"

    def test_redacts_env_values(self):
        """redact-all 映射键下的所有值 (e.g. ``env``）是已脱敏。"""
        errors = [
            {
                "type": "value_error",
                "loc": ["body"],
                "msg": "Invalid value",
                "input": {
                    "agent": {
                        "env": {
                            "OPENAI_API_KEY": "sk-secret",
                            "DATABASE_URL": "postgres://user:pass@host/db",
                        },
                    },
                },
            }
        ]
        result = _sanitize_validation_errors(errors)
        env = result[0]["input"]["agent"]["env"]
        assert env["OPENAI_API_KEY"] == "<redacted>"
        assert env["DATABASE_URL"] == "<redacted>"

    def test_preserves_non_secret_fields(self):
        """非机密字段应不变地通过。"""
        errors = [
            {
                "type": "missing",
                "loc": ["body", "workspace"],
                "msg": "Field required",
                "input": {
                    "agent": {
                        "llm": {"model": "claude-3"},
                        "tools": [{"name": "bash"}],
                    },
                },
            }
        ]
        result = _sanitize_validation_errors(errors)
        assert result[0]["input"]["agent"]["llm"]["model"] == "claude-3"
        assert result[0]["input"]["agent"]["tools"] == [{"name": "bash"}]

    def test_handles_errors_without_input(self):
        """缺少“输入”键的错误应保持不变。"""
        errors = [
            {
                "type": "missing",
                "loc": ["body"],
                "msg": "Field required",
            }
        ]
        result = _sanitize_validation_errors(errors)
        assert result == errors

    def test_handles_scalar_input(self):
        """标量输入值应不变地通过。"""
        errors = [
            {
                "type": "type_error",
                "loc": ["body", "max_iterations"],
                "msg": "value is not a valid integer",
                "input": "not_a_number",
            }
        ]
        result = _sanitize_validation_errors(errors)
        assert result[0]["input"] == "not_a_number"

    def test_does_not_mutate_original(self):
        """不应修改原始错误列表。"""
        original_errors = [
            {
                "type": "missing",
                "loc": ["body"],
                "msg": "Field required",
                "input": {
                    "agent": {
                        "llm": {"api_key": "sk-secret"},
                    },
                },
            }
        ]
        # 保留对原始输入的引用
        original_api_key = original_errors[0]["input"]["agent"]["llm"]["api_key"]
        _sanitize_validation_errors(original_errors)
        # 原件应该不受影响
        assert (
            original_errors[0]["input"]["agent"]["llm"]["api_key"] == original_api_key
        )

    def test_redacts_multiple_secret_patterns(self):
        """各种机密键模式应该都是已脱敏。"""
        errors = [
            {
                "type": "value_error",
                "loc": ["body"],
                "msg": "Invalid",
                "input": {
                    "api_key": "secret1",
                    "api_token": "secret2",
                    "password": "secret3",
                    "authorization": "Bearer secret4",
                    "x_session_id": "secret5",
                    "name": "safe_value",
                },
            }
        ]
        result = _sanitize_validation_errors(errors)
        inp = result[0]["input"]
        assert inp["api_key"] == "<redacted>"
        assert inp["api_token"] == "<redacted>"
        assert inp["password"] == "<redacted>"
        assert inp["authorization"] == "<redacted>"
        assert inp["x_session_id"] == "<redacted>"
        assert inp["name"] == "safe_value"

    def test_stringifies_value_error_context(self):
        """ValueError 在 ctx 中不应该破坏 JSONResponse 的渲染。"""
        errors = [
            {
                "type": "value_error",
                "loc": ["body", "observability_metadata"],
                "msg": "Value error, bad metadata",
                "input": {"nested": {"bad": True}},
                "ctx": {"error": ValueError("bad metadata")},
            }
        ]
        result = _sanitize_validation_errors(errors)
        assert result[0]["ctx"]["error"] == "bad metadata"

    def test_empty_errors_list(self):
        """空错误列表应返回空列表。"""
        assert _sanitize_validation_errors([]) == []


# ---------------------------------------------------------------------------
# 集成测试使用真实的 FastAPI 测试客户端
# ---------------------------------------------------------------------------


class TestValidationErrorResponse:
    """集成测试验证 422 响应是否经过端到端清理。"""

    @pytest.fixture
    def app_with_validation(self):
        """使用我们的异常处理程序和一个创建一个最小的 FastAPI 应用程序
        将触发 RequestValidationError 的路由。"""
        app = FastAPI()
        _add_exception_handlers(app)

        class SecretPayload(BaseModel):
            name: str
            api_key: str
            env: dict[str, str] = {}

        @app.post("/test-endpoint")
        async def test_endpoint(payload: SecretPayload):
            return {"ok": True}

        return app

    def test_422_response_redacts_api_key(self, app_with_validation):
        """发送失败验证的载荷不应泄漏 api_key。"""
        client = TestClient(app_with_validation)
        # 发送缺少必填“名称”字段但包含 api_key 的载荷
        response = client.post(
            "/test-endpoint",
            json={
                "api_key": "sk-super-secret-key",
                "env": {"PROVIDER_KEY": "provider-secret"},
            },
        )
        assert response.status_code == 422
        body = response.json()

        # 验证响应具有预期的结构
        assert "detail" in body
        assert len(body["detail"]) > 0

        # 检查输入中的机密是否为已脱敏
        for error in body["detail"]:
            if "input" in error and isinstance(error["input"], dict):
                if "api_key" in error["input"]:
                    assert error["input"]["api_key"] == "<redacted>"
                if "env" in error["input"]:
                    for val in error["input"]["env"].values():
                        assert val == "<redacted>"

    def test_422_response_preserves_error_structure(self, app_with_validation):
        """清理后的 422 应保留错误类型、loc 和 msg。"""
        client = TestClient(app_with_validation)
        response = client.post(
            "/test-endpoint",
            json={"api_key": "sk-secret"},
        )
        assert response.status_code == 422
        body = response.json()

        # 验证标准 FastAPI 验证错误结构
        assert "detail" in body
        for error in body["detail"]:
            assert "type" in error
            assert "loc" in error
            assert "msg" in error

    def test_valid_request_unaffected(self, app_with_validation):
        """有效请求不应受到异常处理程序的影响。"""
        client = TestClient(app_with_validation)
        response = client.post(
            "/test-endpoint",
            json={
                "name": "test",
                "api_key": "sk-key",
                "env": {},
            },
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_422_with_non_json_body(self, app_with_validation):
        """发送非 JSON 主体仍应返回清理后的 422。"""
        client = TestClient(app_with_validation)
        response = client.post(
            "/test-endpoint",
            content="this is not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422
        body = response.json()
        assert "detail" in body
