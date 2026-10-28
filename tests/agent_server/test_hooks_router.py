"""测试 hooks 路由器。"""

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config


@pytest.fixture
def client():
    """为 API 创建一个测试客户端。"""
    config = Config(session_api_keys=[])
    app = create_app(config)
    return TestClient(app)


class TestHooksRouter:
    """测试 hooks 路由器端点。"""

    def test_get_hooks_success(self, client):
        """测试从有效的 hooks.json 文件获取挂钩。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建 openhands/hooks.json
            openhands_dir = Path(tmpdir) / ".openhands"
            openhands_dir.mkdir()
            hooks_file = openhands_dir / "hooks.json"

            hooks_data = {
                "hooks": {
                    "stop": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {"type": "command", "command": "echo 'stop hook'"}
                            ],
                        }
                    ]
                }
            }
            hooks_file.write_text(json.dumps(hooks_data))

            response = client.post(
                "/api/hooks",
                json={"project_dir": tmpdir},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["hook_config"] is not None
            assert len(data["hook_config"]["stop"]) == 1

    def test_get_hooks_file_not_found(self, client):
        """测试当 hooks.json 不存在时获取钩子。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            response = client.post(
                "/api/hooks",
                json={"project_dir": tmpdir},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["hook_config"] is None

    def test_get_hooks_no_project_dir(self, client):
        """测试获取未提供 project_dir 的钩子。"""
        response = client.post(
            "/api/hooks",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["hook_config"] is None

    def test_get_hooks_empty_hooks(self, client):
        """测试 hooks.json 为空时获取钩子。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建一个 openhands/hooks.json，内容为空
            openhands_dir = Path(tmpdir) / ".openhands"
            openhands_dir.mkdir()
            hooks_file = openhands_dir / "hooks.json"
            hooks_file.write_text("{}")

            response = client.post(
                "/api/hooks",
                json={"project_dir": tmpdir},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["hook_config"] is None

    def test_get_hooks_multiple_event_types(self, client):
        """测试获取具有多种事件类型的挂钩。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建具有多种事件类型的 .openhands/hooks.json
            openhands_dir = Path(tmpdir) / ".openhands"
            openhands_dir.mkdir()
            hooks_file = openhands_dir / "hooks.json"

            hooks_data = {
                "hooks": {
                    "stop": [
                        {
                            "matcher": "*",
                            "hooks": [{"type": "command", "command": "echo 'stop'"}],
                        }
                    ],
                    "pre_tool_use": [
                        {
                            "matcher": "terminal",
                            "hooks": [
                                {"type": "command", "command": "echo 'pre_tool_use'"}
                            ],
                        }
                    ],
                }
            }
            hooks_file.write_text(json.dumps(hooks_data))

            response = client.post(
                "/api/hooks",
                json={"project_dir": tmpdir},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["hook_config"] is not None
            assert len(data["hook_config"]["stop"]) == 1
            assert len(data["hook_config"]["pre_tool_use"]) == 1
