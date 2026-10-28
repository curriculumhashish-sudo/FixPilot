"""测试挂钩服务。"""

import json
import tempfile
from pathlib import Path

from openhands.agent_server.hooks_service import load_hooks_from_workspace


class TestLoadHooksFromWorkspace:
    """测试 load_hooks_from_workspace 功能。"""

    def test_load_hooks_success(self):
        """测试从有效的 hooks.json 文件加载挂钩。"""
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

            result = load_hooks_from_workspace(project_dir=tmpdir)

            assert result is not None
            assert not result.is_empty()
            assert len(result.stop) == 1

    def test_load_hooks_file_not_found(self):
        """当 hooks.json 不存在时测试加载钩子。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_hooks_from_workspace(project_dir=tmpdir)
            assert result is None

    def test_load_hooks_no_project_dir(self):
        """测试未提供 project_dir 的加载钩子。"""
        result = load_hooks_from_workspace(project_dir=None)
        assert result is None

    def test_load_hooks_empty_hooks(self):
        """当 hooks.json 为空时加载测试钩子。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建一个 openhands/hooks.json，内容为空
            openhands_dir = Path(tmpdir) / ".openhands"
            openhands_dir.mkdir()
            hooks_file = openhands_dir / "hooks.json"
            hooks_file.write_text("{}")

            result = load_hooks_from_workspace(project_dir=tmpdir)
            assert result is None

    def test_load_hooks_invalid_json(self):
        """当 hooks.json 包含无效的 JSON 时测试加载挂钩。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建。openhands/hooks.json 带有无效的 JSON
            openhands_dir = Path(tmpdir) / ".openhands"
            openhands_dir.mkdir()
            hooks_file = openhands_dir / "hooks.json"
            hooks_file.write_text("not valid json {")

            result = load_hooks_from_workspace(project_dir=tmpdir)
            assert result is None

    def test_load_hooks_multiple_event_types(self):
        """使用多种事件类型测试加载挂钩。"""
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

            result = load_hooks_from_workspace(project_dir=tmpdir)

            assert result is not None
            assert not result.is_empty()
            assert len(result.stop) == 1
            assert len(result.pre_tool_use) == 1

    def test_load_hooks_pascal_case_format(self):
        """使用 PascalCase 事件名称（旧格式）测试加载挂钩。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建 openhands/hooks.json，格式为 PascalCase
            openhands_dir = Path(tmpdir) / ".openhands"
            openhands_dir.mkdir()
            hooks_file = openhands_dir / "hooks.json"

            hooks_data = {
                "hooks": {
                    "Stop": [
                        {
                            "matcher": "*",
                            "hooks": [{"type": "command", "command": "echo 'stop'"}],
                        }
                    ],
                    "PreToolUse": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {"type": "command", "command": "echo 'pre_tool_use'"}
                            ],
                        }
                    ],
                }
            }
            hooks_file.write_text(json.dumps(hooks_data))

            result = load_hooks_from_workspace(project_dir=tmpdir)

            assert result is not None
            assert not result.is_empty()
            assert len(result.stop) == 1
            assert len(result.pre_tool_use) == 1
