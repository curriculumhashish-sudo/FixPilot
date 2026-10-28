"""为 Gemini 工具测试共享测试夹具。"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_conv_state(tmp_path):
    """最小模拟对象 ConversationState 和工作区目录。"""
    cs = MagicMock()
    cs.workspace.working_dir = str(tmp_path)
    return cs
