"""测试 bash_router.py 端点。"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from openhands.agent_server.api import create_app
from openhands.agent_server.bash_service import BashEventService
from openhands.agent_server.config import Config
from openhands.agent_server.dependencies import get_bash_event_service
from openhands.agent_server.models import BashCommand


@pytest.fixture
def test_bash_service():
    """创建一个 BashEventService 实例用于测试。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        yield BashEventService(
            bash_events_dir=temp_path / "bash_events",
        )


@pytest.fixture
def client():
    """为没有身份验证的 FastAPI 应用程序创建一个测试客户端。"""
    config = Config(session_api_keys=[])  # 禁用身份验证
    return TestClient(create_app(config))


def test_clear_all_bash_events_empty_storage():
    """测试存储为空时清除 bash 事件。"""
    mock_service = MagicMock(spec=BashEventService)
    mock_service.clear_all_events = AsyncMock(return_value=0)

    config = Config(session_api_keys=[])
    app = create_app(config)
    app.dependency_overrides[get_bash_event_service] = lambda: mock_service

    client = TestClient(app)
    response = client.delete("/api/bash/bash_events")

    assert response.status_code == 200
    assert response.json() == {"cleared_count": 0}
    mock_service.clear_all_events.assert_called_once()


def test_clear_all_bash_events_with_data():
    """当存储包含数据时测试清除 bash 事件。"""
    mock_service = MagicMock(spec=BashEventService)
    mock_service.clear_all_events = AsyncMock(return_value=5)

    config = Config(session_api_keys=[])
    app = create_app(config)
    app.dependency_overrides[get_bash_event_service] = lambda: mock_service

    client = TestClient(app)
    response = client.delete("/api/bash/bash_events")

    assert response.status_code == 200
    assert response.json() == {"cleared_count": 5}
    mock_service.clear_all_events.assert_called_once()


@pytest.mark.asyncio
async def test_clear_all_bash_events_integration(test_bash_service):
    """集成测试用于清除 bash 事件。"""
    # 执行一些命令来创建事件
    commands = [
        BashCommand(command='echo "first"', cwd="/tmp"),
        BashCommand(command='echo "second"', cwd="/tmp"),
    ]

    for cmd in commands:
        await test_bash_service.start_bash_command(cmd)

    # 等待命令完成
    import asyncio

    await asyncio.sleep(2)

    # 清除前验证事件是否存在
    page = await test_bash_service.search_bash_events()
    initial_count = len(page.items)
    assert initial_count > 0

    # 清除所有事件
    cleared_count = await test_bash_service.clear_all_events()
    assert cleared_count == initial_count

    # 验证事件已消失
    page_after = await test_bash_service.search_bash_events()
    assert len(page_after.items) == 0
