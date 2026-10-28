"""
在终端会话中处理大型环境变量的测试。

此测试套件验证终端实现可以处理大型环境字典，而不会遇到命令行长度限制。 这解决了问题#
1330。
"""

import os
import tempfile

import pytest

from openhands.tools.terminal.definition import TerminalAction
from openhands.tools.terminal.terminal import create_terminal_session


@pytest.mark.parametrize("terminal_type", ["tmux"])
def test_large_environment_variables(terminal_type):
    """测试终端是否可以处理大的环境变量（问题＃1330）。"""
    # 存储原始环境变量以便稍后恢复
    original_vars = {}
    test_var_prefix = "TEST_LARGE_ENV_VAR_"

    try:
        # 添加 100 个大型环境变量（总计约 100KB）这将导致旧实现出现“命令太长”错误
        #
        for i in range(100):
            var_name = f"{test_var_prefix}{i}"
            var_value = "X" * 1000  # 每个变量 1KB
            original_vars[var_name] = os.environ.get(var_name)
            os.environ[var_name] = var_value

        with tempfile.TemporaryDirectory() as temp_dir:
            # 这不应该引发“命令太长”错误
            session = create_terminal_session(
                work_dir=temp_dir, terminal_type=terminal_type
            )
            session.initialize()

            # 使用简单的命令验证会话是否有效
            obs = session.execute(TerminalAction(command="echo 'test_large_env'"))
            assert "test_large_env" in obs.text
            assert obs.metadata.exit_code == 0

            # 验证大环境变量之一可访问
            test_var = f"{test_var_prefix}0"
            obs = session.execute(TerminalAction(command=f"echo ${test_var}"))
            assert "XXX" in obs.text  # 应该看到长值的一部分
            assert obs.metadata.exit_code == 0

            session.close()

    finally:
        # 清理：恢复原来的环境
        for var_name, original_value in original_vars.items():
            if original_value is None:
                if var_name in os.environ:
                    del os.environ[var_name]
            else:
                os.environ[var_name] = original_value


@pytest.mark.parametrize("terminal_type", ["tmux"])
def test_environment_variable_access(terminal_type):
    """测试环境变量在终端会话中是否可访问。"""
    test_var = "TEST_TERMINAL_ENV_VAR_12345"
    test_value = "test_value_xyz_abc"

    try:
        os.environ[test_var] = test_value

        with tempfile.TemporaryDirectory() as temp_dir:
            session = create_terminal_session(
                work_dir=temp_dir, terminal_type=terminal_type
            )
            session.initialize()

            # 检查环境变量是否可访问
            obs = session.execute(TerminalAction(command=f"echo ${test_var}"))
            assert test_value in obs.text
            assert obs.metadata.exit_code == 0

            session.close()

    finally:
        if test_var in os.environ:
            del os.environ[test_var]


@pytest.mark.parametrize("terminal_type", ["tmux"])
def test_very_large_environment(terminal_type):
    """在非常大的环境 (500KB+) 中进行测试以确保稳健性。"""
    original_vars = {}
    test_var_prefix = "TEST_VERY_LARGE_ENV_"

    try:
        # 添加 500 个大型环境变量（总计约 500KB），这在旧的实现中肯定会失败
        #
        for i in range(500):
            var_name = f"{test_var_prefix}{i}"
            var_value = "Y" * 1000  # 每个变量 1KB
            original_vars[var_name] = os.environ.get(var_name)
            os.environ[var_name] = var_value

        with tempfile.TemporaryDirectory() as temp_dir:
            # 这应该适用于新的实施
            session = create_terminal_session(
                work_dir=temp_dir, terminal_type=terminal_type
            )
            session.initialize()

            # 验证基本功能
            obs = session.execute(TerminalAction(command="echo 'very_large_env_test'"))
            assert "very_large_env_test" in obs.text
            assert obs.metadata.exit_code == 0

            session.close()

    finally:
        # 清理
        for var_name, original_value in original_vars.items():
            if original_value is None:
                if var_name in os.environ:
                    del os.environ[var_name]
            else:
                os.environ[var_name] = original_value
