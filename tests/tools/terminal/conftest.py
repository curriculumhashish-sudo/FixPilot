"""用于终端测试的共享测试实用程序。"""

import platform
import tempfile
from pathlib import Path

import pytest

from openhands.sdk.logger import get_logger
from openhands.tools.terminal.constants import TIMEOUT_MESSAGE_TEMPLATE
from openhands.tools.terminal.terminal import create_terminal_session


logger = get_logger(__name__)


_WINDOWS_UNSUPPORTED_BACKEND_TEST_MODULES = {
    "test_conversation_cleanup.py",
    "test_large_environment.py",
    "test_pool_integration.py",
    "test_schema.py",
    "test_secrets_masking.py",
    "test_terminal_env_sanitization.py",
    "test_terminal_exit_code_top_level.py",
    "test_terminal_reset.py",
    "test_terminal_session.py",
    "test_terminal_tool.py",
    "test_tmux_pane_pool.py",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """跳过在 Windows 上使用仅限 Unix 的终端后端的测试。"""
    if platform.system() != "Windows":
        return

    skip_backend = pytest.mark.skip(
        reason="Terminal runtime backends currently depend on Unix PTY/tmux support"
    )
    for item in items:
        module_name = Path(str(item.fspath)).name
        if module_name in _WINDOWS_UNSUPPORTED_BACKEND_TEST_MODULES:
            item.add_marker(skip_backend)
        elif module_name == "test_escape_filter.py" and item.name.startswith(
            "test_session_"
        ):
            item.add_marker(skip_backend)


def get_no_change_timeout_suffix(timeout_seconds):
    """用于生成预期的无变化超时后缀的辅助函数。"""
    return (
        f"\n[The command has no new output after {timeout_seconds} seconds. "
        f"{TIMEOUT_MESSAGE_TEMPLATE}]"
    )


def create_test_bash_session(work_dir=None):
    """创建终端会话以进行测试。"""
    if work_dir is None:
        work_dir = tempfile.mkdtemp()
    return create_terminal_session(work_dir=work_dir)


def cleanup_bash_session(session):
    """测试后清理终端会话。"""
    if hasattr(session, "close"):
        try:
            session.close()
        except Exception as e:
            # 忽略清理错误 - 会话可能已关闭
            logger.warning(f"Error during session cleanup: {e}")
