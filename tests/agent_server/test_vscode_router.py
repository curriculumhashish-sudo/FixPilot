"""测试 VSCode 路由器。"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config
from openhands.agent_server.vscode_router import (
    get_vscode_status,
    get_vscode_url,
)


@pytest.fixture
def client():
    """创建一个测试客户端。"""
    config = Config(session_api_keys=[])  # 禁用身份验证进行测试
    app = create_app(config)
    return TestClient(app)


@pytest.fixture
def mock_vscode_service():
    """模拟对象 VSCode 测试服务。"""
    with patch("openhands.agent_server.vscode_router.get_vscode_service") as mock:
        yield mock.return_value


@pytest.mark.asyncio
async def test_get_vscode_url_success(mock_vscode_service):
    """成功获取 VSCode URL。"""
    mock_vscode_service.get_connection_token.return_value = "test-token"
    mock_vscode_service.get_vscode_url.return_value = (
        "http://localhost:8001/?tkn=test-token&folder=/workspace"
    )

    response = await get_vscode_url("http://localhost")

    assert response.url == "http://localhost:8001/?tkn=test-token&folder=/workspace"
    mock_vscode_service.get_vscode_url.assert_called_once_with(
        "http://localhost", "workspace"
    )


@pytest.mark.asyncio
async def test_get_vscode_url_default_uses_configured_port(mock_vscode_service):
    """省略 base_url 必须遵循服务 (None)，而不是硬编码：8001。

    当 base_url 为 None 时，服务会构建 ``http://localhost:{self.port}``，因此不知道部
    署拓扑的客户端会收到服务器实际绑定
    的端口 (e.g. OH_VSCODE_PORT）而不是固定的默认值。
    """
    mock_vscode_service.get_vscode_url.return_value = (
        "http://localhost:19000/?tkn=test-token&folder=workspace"
    )

    response = await get_vscode_url()

    assert response.url == "http://localhost:19000/?tkn=test-token&folder=workspace"
    mock_vscode_service.get_vscode_url.assert_called_once_with(None, "workspace")


@pytest.mark.asyncio
async def test_get_vscode_url_error(mock_vscode_service):
    """测试 VSCode URL 与服务错误。"""
    mock_vscode_service.get_connection_token.side_effect = Exception("Service error")

    with pytest.raises(HTTPException) as exc_info:
        await get_vscode_url()

    assert exc_info.value.status_code == 500
    assert "Failed to get VSCode URL" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_vscode_status_running(mock_vscode_service):
    """测试运行时获取 VSCode 状态。"""
    mock_vscode_service.is_running.return_value = True

    response = await get_vscode_status()

    assert response == {"running": True, "enabled": True}
    mock_vscode_service.is_running.assert_called_once()


@pytest.mark.asyncio
async def test_get_vscode_status_not_running(mock_vscode_service):
    """测试 VSCode 状态获取时未运行。"""
    mock_vscode_service.is_running.return_value = False

    response = await get_vscode_status()

    assert response == {"running": False, "enabled": True}


@pytest.mark.asyncio
async def test_get_vscode_status_error(mock_vscode_service):
    """测试 VSCode 状态获取服务错误。"""
    mock_vscode_service.is_running.side_effect = Exception("Service error")

    with pytest.raises(HTTPException) as exc_info:
        await get_vscode_status()

    assert exc_info.value.status_code == 500
    assert "Failed to get VSCode status" in str(exc_info.value.detail)


def test_vscode_router_endpoints_integration(client):
    """测试路由器端点 VSCode API。"""
    # 修补路由器导入和服务模块
    with (
        patch(
            "openhands.agent_server.vscode_router.get_vscode_service"
        ) as mock_service_getter,
        patch("openhands.agent_server.api.get_vscode_service") as mock_api_service,
    ):
        mock_service = mock_service_getter.return_value
        mock_service.get_vscode_url.return_value = (
            "http://localhost:8001/?tkn=integration-token"
        )
        mock_service.is_running.return_value = True

        # 模拟对象 API 服务避免启动
        mock_api_service.return_value.start.return_value = True
        mock_api_service.return_value.stop.return_value = None

        # 测试 URL 端点
        response = client.get("/api/vscode/url")
        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "http://localhost:8001/?tkn=integration-token"

        # 使用自定义基础 URL 测试 URL 端点
        response = client.get("/api/vscode/url?base_url=http://example.com")
        assert response.status_code == 200

        # 测试状态端点
        response = client.get("/api/vscode/status")
        assert response.status_code == 200
        data = response.json()
        assert data["running"] is True


def test_vscode_router_endpoints_with_errors(client):
    """测试路由器 VSCode 和服务错误端点。"""
    # 修补路由器导入和服务模块
    with (
        patch(
            "openhands.agent_server.vscode_router.get_vscode_service"
        ) as mock_service_getter,
        patch("openhands.agent_server.api.get_vscode_service") as mock_api_service,
    ):
        mock_service = mock_service_getter.return_value
        mock_service.is_running.side_effect = Exception("Service down")

        # 模拟对象 API 服务避免启动
        mock_api_service.return_value.start.return_value = True
        mock_api_service.return_value.stop.return_value = None

        # 测试 URL 端点错误
        response = client.get("/api/vscode/url")
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Internal Server Error"

        # 测试状态端点错误
        response = client.get("/api/vscode/status")
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Internal Server Error"


@pytest.mark.asyncio
async def test_get_vscode_url_disabled():
    """测试 VSCode URL 当 VSCode 时。"""
    with patch(
        "openhands.agent_server.vscode_router.get_vscode_service"
    ) as mock_service:
        mock_service.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_vscode_url()

        assert exc_info.value.status_code == 503
        assert "VSCode is disabled in configuration" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_vscode_status_disabled():
    """测试 VSCode 时获取 VSCode 状态。"""
    with patch(
        "openhands.agent_server.vscode_router.get_vscode_service"
    ) as mock_service:
        mock_service.return_value = None

        response = await get_vscode_status()

        assert response == {
            "running": False,
            "enabled": False,
            "message": "VSCode is disabled in configuration",
        }


def test_vscode_router_disabled_integration(client):
    """Test VSCode router 端点当 VSCode 已禁用。"""
    with (
        patch(
            "openhands.agent_server.vscode_router.get_vscode_service"
        ) as mock_router_service,
        patch("openhands.agent_server.api.get_vscode_service") as mock_api_service,
    ):
        # 将 VSCode 配置为禁用
        mock_router_service.return_value = None

        # 模拟对象 API 服务避免启动
        mock_api_service.return_value = None

        # 禁用时测试 URL 端点返回 503
        response = client.get("/api/vscode/url")
        assert response.status_code == 503
        data = response.json()
        # 根据 FastAPI 错误处理，错误消息可能位于不同字段中
        #
        error_message = data.get("detail", data.get("message", ""))
        assert (
            "VSCode is disabled" in error_message
            or "Internal Server Error" in error_message
        )

        # 测试状态端点返回禁用状态
        response = client.get("/api/vscode/status")
        assert response.status_code == 200
        data = response.json()
        assert data["running"] is False
        assert data["enabled"] is False
        assert "VSCode is disabled in configuration" in data["message"]
