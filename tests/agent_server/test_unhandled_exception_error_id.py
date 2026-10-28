"""测试未处理的异常是否返回相关性 ``error_id``。

``error_id`` 会出现在 500 响应体和服务器端日志行中（该日志行包含了完整的调用堆栈信息
），因此，一个调用者收到的无意义的 500 响应可以与服务器日志中的调
用堆栈信息匹配。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openhands.agent_server.api import _add_exception_handlers
from openhands.agent_server.conversation_lease import ConversationOwnershipLostError
from openhands.agent_server.conversation_service import (
    CredentialBindingActivationRequired,
)


@pytest.fixture
def app_with_failing_route():
    app = FastAPI()
    _add_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    return app


def test_unhandled_exception_returns_error_id(app_with_failing_route):
    # raise_server_exceptions=False so the registered handler's JSONResponse is
    # 返回，而不是在测试中重新引发异常。
    client = TestClient(app_with_failing_route, raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal Server Error"
    error_id = body.get("error_id")
    assert isinstance(error_id, str)
    assert len(error_id) == 32  # uuid4().十六进制


def test_error_id_is_unique_per_request(app_with_failing_route):
    client = TestClient(app_with_failing_route, raise_server_exceptions=False)
    first = client.get("/boom").json()["error_id"]
    second = client.get("/boom").json()["error_id"]
    assert first != second


def test_credential_binding_activation_required_is_retryable():
    app = FastAPI()
    _add_exception_handlers(app)

    @app.get("/conversation")
    async def conversation():
        raise CredentialBindingActivationRequired(
            "credential_binding_activation_required"
        )

    response = TestClient(app, raise_server_exceptions=False).get("/conversation")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "credential_binding_activation_required",
        "retryable": True,
    }


def test_conversation_ownership_lost_is_conflict(tmp_path):
    app = FastAPI()
    _add_exception_handlers(app)

    @app.patch("/conversation")
    async def conversation():
        raise ConversationOwnershipLostError(
            conversation_dir=tmp_path, owner_instance_id="stale", generation=1
        )

    client = TestClient(app, raise_server_exceptions=False)
    response = client.patch("/conversation")

    assert response.status_code == 409
    assert "owned by another agent server instance" in response.json()["detail"]
