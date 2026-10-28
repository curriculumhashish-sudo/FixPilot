"""
跨所有终端实现测试 bash 会话功能。

This 测试套件 uses pytest 参数化以运行相同的测试用例在所有可用终端实现之间子进程，
tmux确保在不同后端之间实现一致的行为。

测试会自动检测系统上可用的终端类型，并为每种类型运行参数化测试。
"""

import logging
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from openhands.sdk import TextContent
from openhands.sdk.logger import get_logger
from openhands.tools.terminal.constants import MIN_POLL_INTERVAL, POLL_INTERVAL
from openhands.tools.terminal.definition import (
    TerminalAction,
    TerminalObservation,
)
from openhands.tools.terminal.terminal import (
    TerminalCommandStatus,
    create_terminal_session,
    terminal_session as session_module,
)

from .conftest import get_no_change_timeout_suffix


logger = get_logger(__name__)

# 参数化测试以在所有可用的终端类型上运行
terminal_types = ["tmux", "subprocess"]
parametrize_terminal_types = pytest.mark.parametrize("terminal_type", terminal_types)


@parametrize_terminal_types
def test_session_initialization(terminal_type):
    # 使用自定义测试工作目录
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        obs = session.execute(TerminalAction(command="pwd"))

        assert temp_dir in obs.text
        assert "[The command completed with exit code 0.]" in obs.metadata.suffix
        session.close()

    # 使用自定义用户名进行测试
    session = create_terminal_session(
        work_dir=os.getcwd(), username="nobody", terminal_type=terminal_type
    )
    session.initialize()
    session.close()


@parametrize_terminal_types
def test_cwd_property(tmp_path, terminal_type):
    session = create_terminal_session(work_dir=tmp_path, terminal_type=terminal_type)
    session.initialize()
    # 更改目录并验证密码更新
    random_dir = tmp_path / "random"
    random_dir.mkdir()
    session.execute(TerminalAction(command=f"cd {random_dir}"))

    # 对于其他实现，只需验证命令执行成功即可
    obs = session.execute(TerminalAction(command="pwd"))
    assert str(random_dir) in obs.text

    # 注意：CWD 跟踪可能因终端实现而异
    # 对于 tmux，它应该正确跟踪。 对于子进程，可能不会。
    # if terminal_type == "tmux":
    assert session.cwd == str(random_dir)
    # else:
    session.close()


@parametrize_terminal_types
def test_basic_command(terminal_type):
    session = create_terminal_session(work_dir=os.getcwd(), terminal_type=terminal_type)
    session.initialize()

    # 测试简单命令
    obs = session.execute(TerminalAction(command="echo 'hello world'"))

    assert "hello world" in obs.text
    assert obs.metadata.suffix == "\n[The command completed with exit code 0.]"
    # 注意：前缀可能因终端实现而异
    assert obs.metadata.exit_code == 0
    assert session.prev_status == TerminalCommandStatus.COMPLETED

    # 测试命令有错误
    obs = session.execute(TerminalAction(command="nonexistent_command"))

    # 注意：退出代码处理可能因终端实现而异
    # 重要的是错误信息被捕获
    assert "nonexistent_command: command not found" in obs.text
    assert session.prev_status == TerminalCommandStatus.COMPLETED

    # 按顺序测试多个命令
    obs = session.execute(
        TerminalAction(command='echo "first" && echo "second" && echo "third"')
    )
    assert "first" in obs.text
    assert "second" in obs.text
    assert "third" in obs.text
    assert obs.metadata.suffix == "\n[The command completed with exit code 0.]"
    # 注意：前缀可能因终端实现而异
    assert obs.metadata.exit_code == 0
    assert session.prev_status == TerminalCommandStatus.COMPLETED

    session.close()


def test_subprocess_terminal_debug_logs_omit_command_and_output(caplog):
    session = create_terminal_session(work_dir=os.getcwd(), terminal_type="subprocess")
    session.initialize()
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    secret = "ghp_" + "d" * 36

    try:
        observation = session.execute(TerminalAction(command=f"printf '{secret}\\n'"))
    finally:
        session.close()

    assert secret in observation.text
    assert "Wrote to subprocess PTY" in caplog.text
    assert "Read from subprocess PTY" in caplog.text
    assert secret not in caplog.text


@parametrize_terminal_types
def test_session_truncates_large_command_output(monkeypatch, terminal_type):
    # 通过暂时降低最大截断大小来保持此测试快速。 （避免在单元测试中生成 30k+ 输出。）
    #
    small_max = 600

    from openhands.tools.terminal.terminal import (
        terminal_session as terminal_session_mod,
    )

    monkeypatch.setattr(terminal_session_mod, "MAX_CMD_OUTPUT_SIZE", small_max)

    session = create_terminal_session(work_dir=os.getcwd(), terminal_type=terminal_type)
    session.initialize()

    # 单行输出超出了我们修补的 MAX。
    obs = session.execute(TerminalAction(command="python3 -c 'print(\"A\" * 5000)'"))

    assert "<response clipped>" in obs.text
    assert len(obs.text) <= small_max

    session.close()


@parametrize_terminal_types
def test_session_truncates_multiline_output(monkeypatch, terminal_type):
    """确保会话级截断安全地处理大型多行输出。

    此测试专门用于检测新行密集输出，以捕获截断可能意外分割或与单行输出行为不同的回归
    。
    """

    small_max = 600

    from openhands.tools.terminal.terminal import (
        terminal_session as terminal_session_mod,
    )

    monkeypatch.setattr(terminal_session_mod, "MAX_CMD_OUTPUT_SIZE", small_max)

    session = create_terminal_session(work_dir=os.getcwd(), terminal_type=terminal_type)
    session.initialize()

    # 多行输出超出了我们修补的 MAX。 使用 printf 生成许多短行，练习换行边界。
    #
    obs = session.execute(
        TerminalAction(command="bash -lc \"printf 'A\\n%.0s' {1..5000}\"")
    )

    assert "<response clipped>" in obs.text
    assert len(obs.text) <= small_max

    # 一些后端可能包括终端控制序列（e.g. 括号内的粘贴）。 确保我们仍然获得换行符分隔的输
    # 出，并且截断不会破坏它。
    #
    assert "A\n" in obs.text
    assert obs.text.count("\n") > 10

    session.close()


@parametrize_terminal_types
def test_truncation_preserves_metadata_in_llm_content(monkeypatch, terminal_type):
    # 确保当我们截断 LLM 的最终格式化文本时，元数据后缀仍然可见。
    #
    from openhands.sdk.utils.truncate import DEFAULT_TRUNCATE_NOTICE
    from openhands.tools.terminal import definition as terminal_definition_mod

    session = create_terminal_session(work_dir=os.getcwd(), terminal_type=terminal_type)
    session.initialize()

    obs = session.execute(TerminalAction(command="python3 -c 'print(\"A\" * 5000)'"))

    assert "exit code 0" in obs.metadata.suffix

    trailing = obs.metadata.suffix
    if obs.metadata.working_dir:
        trailing += f"\n[Current working directory: {obs.metadata.working_dir}]"
    if obs.metadata.py_interpreter_path:
        trailing += f"\n[Python interpreter: {obs.metadata.py_interpreter_path}]"
    if obs.metadata.exit_code != -1:
        trailing += f"\n[Command finished with exit code {obs.metadata.exit_code}]"

    # 选择一个较小的截断预算，但确保尾部足够大，包含所有后缀和尾行（路径长度各不相同）。
    #
    min_tail = len(trailing) + 10
    small_max = len(DEFAULT_TRUNCATE_NOTICE) + 2 * min_tail

    monkeypatch.setattr(terminal_definition_mod, "MAX_CMD_OUTPUT_SIZE", small_max)

    llm_content = obs.to_llm_content
    assert isinstance(llm_content[0], TextContent)
    llm_text = llm_content[0].text

    assert "<response clipped>" in llm_text
    assert "[The command completed with exit code 0.]" in llm_text

    session.close()


@parametrize_terminal_types
def test_polling_starts_fast_and_backs_off_to_poll_interval(monkeypatch, terminal_type):
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        time.sleep(seconds)

    clock = SimpleNamespace(time=time.time, sleep=sleep)
    monkeypatch.setattr(session_module, "time", clock)
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        sleeps.clear()
        obs = session.execute(TerminalAction(command="sleep 2.5"))
        session.close()

    assert obs.metadata.exit_code == 0
    assert MIN_POLL_INTERVAL <= sleeps[0] < POLL_INTERVAL / 2
    assert sleeps == sorted(sleeps)
    assert sleeps[-1] == POLL_INTERVAL


@parametrize_terminal_types
def test_environment_variable_persistence(terminal_type):
    """跨命令测试环境变量持久化（有状态终端）。"""
    session = create_terminal_session(work_dir=os.getcwd(), terminal_type=terminal_type)
    session.initialize()

    # 设置环境变量
    obs = session.execute(TerminalAction(command="export TEST_VAR='hello world'"))
    assert obs.metadata.exit_code == 0

    # 在后续命令中使用环境变量
    obs = session.execute(TerminalAction(command="echo $TEST_VAR"))
    assert "hello world" in obs.text
    assert obs.metadata.exit_code == 0

    session.close()


@parametrize_terminal_types
def test_environment_variable_inheritance_from_parent(terminal_type):
    """测试环境变量是否从父进程继承。"""
    # 在当前进程中设置环境变量
    test_var_name = "OPENHANDS_TEST_INHERITANCE_VAR"
    test_var_value = "inherited_from_parent_12345"
    original_value = os.environ.get(test_var_name)

    try:
        # 在父进程中设置环境变量
        os.environ[test_var_name] = test_var_value

        # 创建一个新的终端会话
        session = create_terminal_session(
            work_dir=os.getcwd(), terminal_type=terminal_type
        )
        session.initialize()

        # 检查终端中是否存在环境变量
        obs = session.execute(TerminalAction(command=f"echo ${test_var_name}"))
        assert test_var_value in obs.text, (
            f"Expected '{test_var_value}' in output, but got: {obs.text}"
        )
        assert obs.metadata.exit_code == 0

        session.close()

    finally:
        # 清理：恢复原来的环境变量值
        if original_value is not None:
            os.environ[test_var_name] = original_value
        else:
            os.environ.pop(test_var_name, None)


@pytest.mark.timeout(60)  # 添加 60 秒超时以防止挂在 CI 中
def test_long_running_command_follow_by_execute():
    session = create_terminal_session(work_dir=os.getcwd(), no_change_timeout_seconds=2)
    session.initialize()

    # 缓慢产生输出的测试命令
    obs = session.execute(
        TerminalAction(command="echo 1; sleep 3; echo 2; sleep 3; echo 3")
    )

    assert "1" in obs.text  # 第一个数字应出现在超时之前
    assert obs.metadata.exit_code == -1  # -1表示命令仍在运行
    assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT
    assert obs.metadata.suffix == get_no_change_timeout_suffix(2)
    assert obs.metadata.prefix == ""

    # 继续观察输出
    obs = session.execute(TerminalAction(command="", is_input=True))

    assert "2" in obs.text
    assert obs.metadata.prefix == "[Below is the output of the previous command.]\n"
    assert obs.metadata.suffix == get_no_change_timeout_suffix(2)
    assert obs.metadata.exit_code == -1  # -1表示命令仍在运行
    assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT

    # 测试命令不产生输出
    obs = session.execute(TerminalAction(command="sleep 15"))

    assert "3" not in obs.text
    assert obs.metadata.prefix == "[Below is the output of the previous command.]\n"
    assert "The previous command is still running" in obs.metadata.suffix
    assert obs.metadata.exit_code == -1  # -1表示命令仍在运行
    assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT

    time.sleep(3)

    # 再次运行它，这次它应该产生输出，然后启动一个新命令
    obs = session.execute(TerminalAction(command="sleep 15"))

    assert "3" in obs.text  # 应该看到上一个命令的最终输出
    assert obs.metadata.exit_code == -1  # -1表示新命令仍在运行
    assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT

    session.close()


@parametrize_terminal_types
@pytest.mark.timeout(60)  # 添加 60 秒超时以防止挂在 CI 中
def test_interactive_command(terminal_type):
    session = create_terminal_session(
        work_dir=os.getcwd(), no_change_timeout_seconds=3, terminal_type=terminal_type
    )
    session.initialize()

    # 使用blocking=True测试交互式命令
    obs = session.execute(
        TerminalAction(
            command="read -p 'Enter name: ' name && echo \"Hello $name\"",
        )
    )

    assert "Enter name:" in obs.text
    assert obs.metadata.exit_code == -1  # -1表示命令仍在运行
    assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT
    assert obs.metadata.suffix == get_no_change_timeout_suffix(3)
    assert obs.metadata.prefix == ""

    # 发送输入
    obs = session.execute(TerminalAction(command="John", is_input=True))

    assert "Hello John" in obs.text
    assert obs.metadata.exit_code == 0
    assert obs.metadata.suffix == "\n[The command completed with exit code 0.]"
    assert obs.metadata.prefix == ""
    assert session.prev_status == TerminalCommandStatus.COMPLETED

    # 测试多行命令输入
    obs = session.execute(TerminalAction(command="cat << EOF"))

    assert obs.metadata.exit_code == -1
    assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT
    assert obs.metadata.suffix == get_no_change_timeout_suffix(3)
    assert obs.metadata.prefix == ""

    obs = session.execute(TerminalAction(command="line 1", is_input=True))

    assert obs.metadata.exit_code == -1
    assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT
    assert obs.metadata.suffix == get_no_change_timeout_suffix(3)
    assert obs.metadata.prefix == "[Below is the output of the previous command.]\n"

    obs = session.execute(TerminalAction(command="line 2", is_input=True))

    assert obs.metadata.exit_code == -1
    assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT
    assert obs.metadata.suffix == get_no_change_timeout_suffix(3)
    assert obs.metadata.prefix == "[Below is the output of the previous command.]\n"

    obs = session.execute(TerminalAction(command="EOF", is_input=True))

    assert "line 1" in obs.text and "line 2" in obs.text
    assert obs.metadata.exit_code == 0
    assert obs.metadata.suffix == "\n[The command completed with exit code 0.]"
    assert obs.metadata.prefix == ""

    session.close()


@parametrize_terminal_types
@pytest.mark.timeout(60)  # 添加 60 秒超时以防止挂在 CI 中
def test_ctrl_c(terminal_type):
    session = create_terminal_session(
        work_dir=os.getcwd(), no_change_timeout_seconds=2, terminal_type=terminal_type
    )
    session.initialize()

    # 开始无限循环
    obs = session.execute(
        TerminalAction(command="while true; do echo 'looping'; sleep 3; done"),
    )

    assert "looping" in obs.text
    assert obs.metadata.suffix == get_no_change_timeout_suffix(2)
    assert obs.metadata.prefix == ""
    assert obs.metadata.exit_code == -1  # -1表示命令仍在运行
    assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT

    # 发送 Ctrl+C
    obs = session.execute(TerminalAction(command="C-c", is_input=True))

    # 检查进程是否已中断（退出代码可以是 1 或 130，具体取决于 shell/操作系统）
    #
    assert obs.metadata.exit_code in (
        1,
        130,
    )  # 接受中断进程的两个常见退出代码
    assert "CTRL+C was sent" in obs.metadata.suffix
    assert obs.metadata.prefix == ""
    assert session.prev_status == TerminalCommandStatus.COMPLETED

    session.close()


@parametrize_terminal_types
def test_empty_command_error(terminal_type):
    session = create_terminal_session(work_dir=os.getcwd(), terminal_type=terminal_type)
    session.initialize()

    # 测试没有先前命令的空命令
    obs = session.execute(TerminalAction(command=""))

    assert obs.is_error is True
    assert obs.text == "No previous running command to retrieve logs from."
    assert len(obs.to_llm_content) == 2
    assert isinstance(obs.to_llm_content[0], TextContent)
    assert obs.to_llm_content[0].text == TerminalObservation.ERROR_MESSAGE_HEADER
    assert isinstance(obs.to_llm_content[1], TextContent)
    assert (
        "No previous running command to retrieve logs from."
        == obs.to_llm_content[1].text
    )
    assert obs.metadata.exit_code == -1
    assert obs.metadata.prefix == ""
    assert obs.metadata.suffix == ""
    assert session.prev_status is None

    session.close()


@parametrize_terminal_types
@pytest.mark.timeout(60)  # 添加 60 秒超时以防止挂在 CI 中
def test_command_output_continuation(terminal_type):
    """测试我们是否可以继续从长时间运行的命令获取输出。

    该测试已被修改为针对时序问题更加稳健。
    """
    session = create_terminal_session(
        work_dir=os.getcwd(), no_change_timeout_seconds=1, terminal_type=terminal_type
    )
    session.initialize()

    # 启动一个命令，该命令缓慢地生成输出，但睡眠时间更长，以确保我们达到超时
    #
    obs = session.execute(
        TerminalAction(command="for i in {1..5}; do echo $i; sleep 2; done")
    )

    # 检查命令是否立即完成或超时
    if session.prev_status == TerminalCommandStatus.COMPLETED:
        # 如果命令立即完成，请验证我们是否获得了所有输出
        logger.info("Command completed immediately", extra={"msg_type": "TEST_INFO"})
        assert "1" in obs.text
        assert "2" in obs.text
        assert "3" in obs.text
        assert "4" in obs.text
        assert "5" in obs.text
        assert "[The command completed with exit code 0.]" in obs.metadata.suffix
    else:
        # 如果命令超时，请验证我们是否收到了超时消息
        assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT
        assert "1" in obs.text
        assert "[The command has no new output after 1 seconds." in obs.metadata.suffix

        # 继续获取输出，直到我们看到所有数字
        numbers_seen = set()
        for i in range(1, 6):
            if str(i) in obs.text:
                numbers_seen.add(i)

        # 我们需要查看数字 2-5，然后是命令完成
        while (
            len(numbers_seen) < 5
            or session.prev_status != TerminalCommandStatus.COMPLETED
        ):
            obs = session.execute(TerminalAction(command="", is_input=True))

            # 检查输出中的数字
            for i in range(1, 6):
                if str(i) in obs.text and i not in numbers_seen:
                    numbers_seen.add(i)
                    logger.info(
                        f"Found number {i} in output", extra={"msg_type": "TEST_INFO"}
                    )

            # 检查命令是否完成
            if session.prev_status == TerminalCommandStatus.COMPLETED:
                assert (
                    "[The command completed with exit code 0.]" in obs.metadata.suffix
                )
                break
            else:
                assert (
                    "[The command has no new output after 1 seconds."
                    in obs.metadata.suffix
                )
                assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT

        # 验证我们已看到所有数字
        assert numbers_seen == {1, 2, 3, 4, 5}, (
            f"Expected to see numbers 1-5, but saw {numbers_seen}"
        )

        # 验证命令已完成
        assert session.prev_status == TerminalCommandStatus.COMPLETED

    session.close()


@parametrize_terminal_types
def test_history_expansion_disabled(terminal_type):
    session = create_terminal_session(work_dir=os.getcwd(), terminal_type=terminal_type)
    session.initialize()

    obs = session.execute(TerminalAction(command="echo A!B"))
    assert "event not found" not in obs.text
    assert "A!B" in obs.text

    session.close()


@parametrize_terminal_types
def test_long_output(terminal_type):
    session = create_terminal_session(work_dir=os.getcwd(), terminal_type=terminal_type)
    session.initialize()

    # 生成可能超出缓冲区大小的长输出
    obs = session.execute(
        TerminalAction(command='for i in {1..5000}; do echo "Line $i"; done')
    )

    assert "Line 1" in obs.text
    assert "Line 5000" in obs.text
    assert obs.metadata.exit_code == 0
    assert obs.metadata.prefix == ""
    assert obs.metadata.suffix == "\n[The command completed with exit code 0.]"

    session.close()


@parametrize_terminal_types
def test_long_output_exceed_history_limit(terminal_type):
    session = create_terminal_session(work_dir=os.getcwd(), terminal_type=terminal_type)
    session.initialize()

    # 生成可能超出缓冲区大小的长输出
    obs = session.execute(
        TerminalAction(command='for i in {1..50000}; do echo "Line $i"; done')
    )

    assert "Previous command outputs are truncated" in obs.metadata.prefix
    assert "Line 40000" in obs.text
    assert "Line 50000" in obs.text
    assert obs.metadata.exit_code == 0
    assert obs.metadata.suffix == "\n[The command completed with exit code 0.]"

    session.close()


def test_multiline_command():
    session = create_terminal_session(work_dir=os.getcwd())
    session.initialize()

    # 禁用 PS2 提示词测试多行命令
    obs = session.execute(
        TerminalAction(
            command="""if true; then
echo "inside if"
fi""",
        )
    )

    assert "inside if" in obs.text
    assert obs.metadata.exit_code == 0
    assert obs.metadata.prefix == ""
    assert obs.metadata.suffix == "\n[The command completed with exit code 0.]"

    session.close()


@parametrize_terminal_types
def test_python_interactive_input(terminal_type):
    session = create_terminal_session(
        work_dir=os.getcwd(), no_change_timeout_seconds=2, terminal_type=terminal_type
    )
    session.initialize()

    # 测试要求输入的 Python 程序 - 为 bash 正确转义
    python_script = (
        "name = input('Enter your name: '); age = input('Enter your age: '); "
        "print(f'Hello {name}, you are {age} years old')"
    )

    # 使用交互式脚本开始 Python
    obs = session.execute(TerminalAction(command=f'python3 -c "{python_script}"'))

    assert "Enter your name:" in obs.text
    assert obs.metadata.exit_code == -1  # -1表示命令仍在运行
    assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT

    # 发送第一个输入（名称）
    obs = session.execute(TerminalAction(command="Alice", is_input=True))

    assert "Enter your age:" in obs.text
    assert obs.metadata.exit_code == -1
    assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT

    # 发送第二个输入（年龄）
    obs = session.execute(TerminalAction(command="25", is_input=True))

    assert "Hello Alice, you are 25 years old" in obs.text
    assert obs.metadata.exit_code == 0
    assert obs.metadata.suffix == "\n[The command completed with exit code 0.]"
    assert session.prev_status == TerminalCommandStatus.COMPLETED

    session.close()


def _run_bash_action(session, command: str, **kwargs):
    """执行 bash 命令并返回观测结果的辅助函数。"""
    action = TerminalAction(command=command, **kwargs)
    obs = session.execute(action)
    logger.info(f"Command: {command}")
    output_text = obs.text if obs.content else ""
    logger.info(f"Output: {output_text}")
    logger.info(f"Exit code: {obs.metadata.exit_code}")
    return obs


@parametrize_terminal_types
def test_bash_server(terminal_type):
    """使用超时和中断测试运行服务器。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            # 使用 Python -u 进行无缓冲输出，可能有助于捕获 Windows 上的初始输出
            #
            obs = _run_bash_action(
                session, "python -u -m http.server 8081", timeout=1.0
            )
            assert obs.metadata.exit_code == -1
            assert "Serving HTTP on" in obs.text

            # 发送 Ctrl+C 中断
            obs = _run_bash_action(session, "C-c", is_input=True)
            assert "CTRL+C was sent" in obs.metadata.suffix
            assert "Keyboard interrupt received, exiting." in obs.text

            # 验证我们可以在中断后运行命令
            obs = _run_bash_action(session, "ls")
            assert obs.metadata.exit_code == 0

            # 再次运行服务器以验证其是否正常工作
            obs = _run_bash_action(
                session, "python -u -m http.server 8081", timeout=1.0
            )
            assert obs.metadata.exit_code == -1
            assert "Serving HTTP on" in obs.text

        finally:
            session.close()


@parametrize_terminal_types
def test_bash_background_server(terminal_type):
    """测试在后台运行服务器。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        server_port = 8081
        try:
            # 在后台启动服务器
            obs = _run_bash_action(session, f"python3 -m http.server {server_port} &")
            assert obs.metadata.exit_code == 0

            # 给服务器一点时间准备
            time.sleep(1)

            # 通过卷曲验证服务器正在运行
            obs = _run_bash_action(session, f"curl http://localhost:{server_port}")
            assert obs.metadata.exit_code == 0
            # 检查 Python http.server 目录列表的典型内容
            assert "Directory listing for" in obs.text

            # 杀死服务器
            obs = _run_bash_action(session, 'pkill -f "http.server"')
            assert obs.metadata.exit_code == 0

        finally:
            session.close()


@parametrize_terminal_types
def test_multiline_commands(terminal_type):
    """测试多行命令执行。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            # 原始Linux bash版本单多行命令
            #
            obs = _run_bash_action(session, 'echo \\\n -e "foo"')
            assert obs.metadata.exit_code == 0
            assert "foo" in obs.text

            # 测试多线回声
            obs = _run_bash_action(session, 'echo -e "hello\nworld"')
            assert obs.metadata.exit_code == 0
            assert "hello\nworld" in obs.text

            # 测试空白
            obs = _run_bash_action(session, 'echo -e "a\\n\\n\\nz"')
            assert obs.metadata.exit_code == 0
            assert "\n\n\n" in obs.text
        finally:
            session.close()


@parametrize_terminal_types
def test_complex_commands(terminal_type):
    """测试复杂的 bash 命令执行。"""
    cmd = (
        'count=0; tries=0; while [ $count -lt 3 ]; do result=$(echo "Heads"); '
        'tries=$((tries+1)); echo "Flip $tries: $result"; '
        'if [ "$result" = "Heads" ]; then count=$((count+1)); else count=0; fi; '
        'done; echo "Got 3 heads in a row after $tries flips!";'
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            obs = _run_bash_action(session, cmd)
            assert obs.metadata.exit_code == 0
            assert "Got 3 heads in a row after 3 flips!" in obs.text
        finally:
            session.close()


@parametrize_terminal_types
def test_no_ps2_in_output(terminal_type):
    """测试 PS2 符号是否未添加到多行命令的输出中。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            obs = _run_bash_action(session, 'echo -e "hello\nworld"')
            assert obs.metadata.exit_code == 0

            assert "hello\nworld" in obs.text
            assert ">" not in obs.text
        finally:
            session.close()


@parametrize_terminal_types
def test_multiline_command_loop(terminal_type):
    """使用循环测试多行命令。"""
    # https://github.com/OpenHands/OpenHands/issues/3143
    init_cmd = """mkdir -p _modules && \\
for month in {01..04}; do
    for day in {01..05}; do
        touch "_modules/2024-${month}-${day}-sample.md"
    done
done && echo "created files"
"""
    follow_up_cmd = """for file in _modules/*.md; do
    new_date=$(echo $file | sed -E \\
        's/2024-(01|02|03|04)-/2024-/;s/2024-01/2024-08/;s/2024-02/2024-09/;s/2024-03/2024-10/;s/2024-04/2024-11/')
    mv "$file" "$new_date"
done && echo "success"
"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            obs = _run_bash_action(session, init_cmd)
            assert obs.metadata.exit_code == 0
            assert "created files" in obs.text

            obs = _run_bash_action(session, follow_up_cmd)
            assert obs.metadata.exit_code == 0
            assert "success" in obs.text
        finally:
            session.close()


@parametrize_terminal_types
def test_chained_script_with_multiple_heredocs(terminal_type):
    command = """printf start; python - <<'PY'
print('first')
PY
printf middle; python - <<'PY'
print('second')
PY
sleep 0.2; printf done; echo completed > completion-marker
"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            obs = _run_bash_action(session, command)

            assert obs.is_error is False
            assert obs.metadata.exit_code == 0
            assert "start" in obs.text
            assert "first" in obs.text
            assert "middle" in obs.text
            assert "second" in obs.text
            assert "done" in obs.text
            assert "__OH_COMMAND_FINISHED_" not in obs.text
            marker = Path(temp_dir, "completion-marker")
            assert marker.read_text().strip() == "completed"
        finally:
            session.close()


@parametrize_terminal_types
def test_chained_heredoc_script_preserves_trailing_exit_status(terminal_type):
    command = "cat <<'EOF'\nbody\nEOF\nfalse\n"
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            obs = _run_bash_action(session, command)

            assert obs.is_error is False
            assert obs.metadata.exit_code == 1
            assert "body" in obs.text
            assert "__OH_COMMAND_FINISHED_" not in obs.text
        finally:
            session.close()


@parametrize_terminal_types
@pytest.mark.parametrize(
    "command",
    [
        "cat <<A <<B\na\nA\nb\nB\nsleep 0.2; touch completion-marker",
        'cat <<E"OF"\nbody\nEOF\nsleep 0.2; touch completion-marker',
        "cat <<EOF &\nbody\nEOF\nsleep 0.2; touch completion-marker",
    ],
)
def test_parser_fallback_heredocs_wait_for_trailing_command(terminal_type, command):
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            obs = _run_bash_action(session, command)

            assert obs.metadata.exit_code == 0
            assert Path(temp_dir, "completion-marker").exists()
            assert "__OH_COMMAND_FINISHED_" not in obs.text
        finally:
            session.close()


@parametrize_terminal_types
def test_heredoc_completion_preserves_aliases_and_ignores_stdout_redirect(
    terminal_type,
):
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            obs = _run_bash_action(
                session,
                "alias oh_test='echo alias-expanded'; cat <<EOF\nbody\nEOF\noh_test",
            )
            assert obs.metadata.exit_code == 0
            assert "alias-expanded" in obs.text

            obs = _run_bash_action(
                session,
                "cat <<EOF\nbody\nEOF\nexec > redirected.txt; false",
                timeout=3,
            )
            assert obs.metadata.exit_code == 1
            assert "__OH_COMMAND_FINISHED_" not in obs.text
            assert (
                "__OH_COMMAND_FINISHED_"
                not in Path(temp_dir, "redirected.txt").read_text()
            )
        finally:
            session.close()


@parametrize_terminal_types
def test_multiple_multiline_commands(terminal_type):
    """测试是否拒绝由换行符分隔的多个命令。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            cmds = [
                "ls -l",
                'echo -e "hello\nworld"',
                """echo -e "hello it's me\"""",
                """echo \\
-e 'hello' \\
world""",
                """echo -e 'hello\\nworld\\nare\\nyou\\nthere?'""",
                """echo -e 'hello\nworld\nare\nyou\n\nthere?'""",
                """echo -e 'hello\nworld "'""",
            ]
            joined_cmds = "\n".join(cmds)

            # 首先测试一次运行多个命令失败
            obs = _run_bash_action(session, joined_cmds)
            assert obs.is_error is True
            assert "Cannot execute multiple commands at once" in obs.text

            # 现在单独运行每个命令并验证它们是否有效
            results = []
            for cmd in cmds:
                obs = _run_bash_action(session, cmd)
                assert obs.metadata.exit_code == 0
                results.append(obs.text)

            # 验证所有预期输出是否存在
            assert "total 0" in results[0]  # ls-l
            assert "hello\nworld" in results[1]  # echo -e "hello\nworld"
            assert "hello it's me" in results[2]  # echo -e "hello it\'s me"
            assert "hello world" in results[3]  # echo -e 'hello' world
            assert (
                "hello\nworld\nare\nyou\nthere?" in results[4]
            )  # echo -e 'hello\nworld\nare\nyou\nthere?'
            assert (
                "hello\nworld\nare\nyou\n\nthere?" in results[5]
            )  # echo -e with literal newlines
            assert 'hello\nworld "' in results[6]  # echo -e with quote
        finally:
            session.close()


@parametrize_terminal_types
def test_cmd_run(terminal_type):
    """测试基本命令执行。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            # Unix版本
            obs = _run_bash_action(session, f"ls -l {temp_dir}")
            assert obs.metadata.exit_code == 0

            obs = _run_bash_action(session, "ls -l")
            assert obs.metadata.exit_code == 0
            assert "total 0" in obs.text

            obs = _run_bash_action(session, "mkdir test")
            assert obs.metadata.exit_code == 0

            obs = _run_bash_action(session, "ls -l")
            assert obs.metadata.exit_code == 0
            assert "test" in obs.text

            obs = _run_bash_action(session, "touch test/foo.txt")
            assert obs.metadata.exit_code == 0

            obs = _run_bash_action(session, "ls -l test")
            assert obs.metadata.exit_code == 0
            assert "foo.txt" in obs.text

            # 清理
            _run_bash_action(session, "rm -rf test")
            assert obs.metadata.exit_code == 0
        finally:
            session.close()


@parametrize_terminal_types
def test_run_as_user_correct_home_dir(terminal_type):
    """测试主目录是否正确。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            # 原始Linux版本
            obs = _run_bash_action(session, "cd ~ && pwd")
            assert obs.metadata.exit_code == 0
            home = os.getenv("HOME")
            assert home and home in obs.text
        finally:
            session.close()


@parametrize_terminal_types
def test_multi_cmd_run_in_single_line(terminal_type):
    """在一行中测试多个命令。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(work_dir=temp_dir)
        session.initialize()
        try:
            # 原始 Linux 版本使用 &&
            obs = _run_bash_action(session, "pwd && ls -l")
            assert obs.metadata.exit_code == 0
            assert temp_dir in obs.text
            assert "total 0" in obs.text
        finally:
            session.close()


@parametrize_terminal_types
def test_stateful_cmd(terminal_type):
    """测试命令在执行过程中是否保持状态。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            # 原始Linux版本
            obs = _run_bash_action(session, "mkdir -p test")
            assert obs.metadata.exit_code == 0

            obs = _run_bash_action(session, "cd test")
            assert obs.metadata.exit_code == 0

            obs = _run_bash_action(session, "pwd")
            assert obs.metadata.exit_code == 0
            assert f"{temp_dir}/test" in obs.text.strip()
        finally:
            session.close()


@parametrize_terminal_types
def test_failed_cmd(terminal_type):
    """命令执行失败了。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            obs = _run_bash_action(session, "non_existing_command")
            assert obs.metadata.exit_code != 0
        finally:
            session.close()


@parametrize_terminal_types
def test_python_version(terminal_type):
    """测试 Python 版本命令。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            obs = _run_bash_action(session, "python --version")
            assert obs.metadata.exit_code == 0
            assert "Python 3" in obs.text
        finally:
            session.close()


@parametrize_terminal_types
def test_pwd_property(terminal_type):
    """测试 pwd 属性更新。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            # 创建子目录并验证 pwd 更新
            obs = _run_bash_action(session, "mkdir -p random_dir")
            assert obs.metadata.exit_code == 0

            obs = _run_bash_action(session, "cd random_dir && pwd")
            assert obs.metadata.exit_code == 0
            assert "random_dir" in obs.text
        finally:
            session.close()


@parametrize_terminal_types
@pytest.mark.timeout(180)  # 为本次密集测试添加 3 分钟超时
def test_long_output_from_nested_directories(terminal_type):
    """测试嵌套目录操作的长输出。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            # 创建包含许多文件的嵌套目录
            setup_cmd = (
                "mkdir -p /tmp/test_dir && cd /tmp/test_dir && "
                'for i in $(seq 1 100); do mkdir -p "folder_$i"; '
                'for j in $(seq 1 100); do touch "folder_$i/file_$j.txt"; done; done'
            )
            obs = _run_bash_action(session, setup_cmd.strip(), timeout=60)
            assert obs.metadata.exit_code == 0

            # 递归列出目录结构
            obs = _run_bash_action(session, "ls -R /tmp/test_dir", timeout=60)
            assert obs.metadata.exit_code == 0

            # 验证输出包含预期文件
            assert "folder_1" in obs.text
            assert "file_1.txt" in obs.text
            assert "folder_100" in obs.text
            assert "file_100.txt" in obs.text
        finally:
            session.close()


@parametrize_terminal_types
def test_command_backslash(terminal_type):
    """使用反斜杠转义测试命令。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            # 创建内容为“implemented_function”的文件
            cmd = (
                "mkdir -p /tmp/test_dir && "
                'echo "implemented_function" > /tmp/test_dir/file_1.txt'
            )
            obs = _run_bash_action(session, cmd)
            assert obs.metadata.exit_code == 0

            # 不同终端类型有不同的转义
            if terminal_type == "subprocess":
                semicolon = '";"'  # 子进程不需要转义
            else:
                semicolon = "\\;"  # 逃离tmux

            cmd = (
                "find /tmp/test_dir -type f -exec grep"
                + f' -l "implemented_function" {{}} {semicolon}'
            )
            obs = _run_bash_action(session, cmd)
            assert obs.metadata.exit_code == 0
            assert "/tmp/test_dir/file_1.txt" in obs.text
        finally:
            session.close()


@parametrize_terminal_types
def test_bash_remove_prefix(terminal_type):
    """测试 bash 命令前缀删除。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            # 创建一个 git 存储库 - 两个平台都相同
            obs = _run_bash_action(
                session,
                "git init && git remote add origin https://github.com/OpenHands/OpenHands",
            )
            assert obs.metadata.exit_code == 0

            # 检查 git Remote - 两个平台都相同
            obs = _run_bash_action(session, "git remote -v")
            assert obs.metadata.exit_code == 0
            assert "https://github.com/OpenHands/OpenHands" in obs.text
            assert "git remote -v" not in obs.text
        finally:
            session.close()


@parametrize_terminal_types
def test_pager_does_not_hijack_terminal(tmp_path, terminal_type):
    """寻呼机 (git log/diff/man/...) 不得捕获 PTY。

    在使用TTY时，``less``命令会自动启动：终端被压住，之后的命令会发送到终端而不是
    shell。 在会话级别禁用寻呼机可以保留下一个命令的输出。 请参阅问题#3
    660。
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    # 一个大文件，因此 `git log -p` 输出超出了屏幕，并且寻呼机（如果启动）将保持打开状态
    # 等待输入。
    #
    (repo / "module.py").write_text(
        "".join(f"# line {i}\n" for i in range(800))
        + "\ndef encode(payload):\n    pass\n"
    )
    for cmd in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "-c", "user.email=a@b.c", "-c", "user.name=x", "commit", "-qm", "init"],
    ):
        subprocess.run(cmd, cwd=repo, check=True)

    session = create_terminal_session(
        work_dir=str(repo), no_change_timeout_seconds=2, terminal_type=terminal_type
    )
    session.initialize()
    try:
        # 如果没有修复，这将打开一个寻呼机并且永远不会返回到提示词。
        _run_bash_action(session, "git log -p")

        # 后续命令必须返回其 OWN 输出，而不是过时的分页 git-log 屏幕。
        #
        obs = _run_bash_action(session, "grep -n 'def encode' module.py")
        assert obs.metadata.exit_code == 0
        assert "def encode" in obs.text
        assert "diff --git" not in obs.text
    finally:
        session.close()


@parametrize_terminal_types
def test_indented_heredoc_echo_is_stripped(terminal_type):
    """制表符缩进的定界文档不得泄漏包装器或完成标记。

    readline 在回显一行时会消耗前导制表符，因此回显不再与逐字节发送的文本匹配。 用于
    剥离它的确切 ``removeprefix`` 随后失败，整个包装纸以及标
    记的两半出现在观测结果中。
    """
    command = "cat <<-EOF\n\tindented\n\tEOF\nprintf done"
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir, terminal_type=terminal_type
        )
        session.initialize()
        try:
            obs = _run_bash_action(session, command)

            assert obs.is_error is False
            assert obs.metadata.exit_code == 0
            assert "indented" in obs.text
            assert "done" in obs.text
            assert "__OH_COMMAND_FINISHED_" not in obs.text
            assert "__openhands_status" not in obs.text
        finally:
            session.close()


@parametrize_terminal_types
def test_no_change_timeout_strips_heredoc_wrapper(terminal_type):
    """软超时不得泄漏分组定界符脚本的包装器。

    只有已完成的分支才会剥离标记，因此超时的命令会将回显的包装器和完成标记返回到智能
    体。
    """
    command = "cat <<'EOF'\nbody\nEOF\nsleep 5; echo done"
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir,
            terminal_type=terminal_type,
            no_change_timeout_seconds=2,
        )
        session.initialize()
        try:
            obs = _run_bash_action(session, command)

            assert "body" in obs.text
            assert "__OH_COMMAND_FINISHED_" not in obs.text
            assert "__openhands_status" not in obs.text

            # 后续民意调查会看到相同的屏幕，并且也必须保持干净。
            obs = _run_bash_action(session, "", is_input=False, timeout=10)
            assert "__OH_COMMAND_FINISHED_" not in obs.text
            assert "__openhands_status" not in obs.text
        finally:
            session.close()


@parametrize_terminal_types
@pytest.mark.parametrize(
    "follow_up", ["echo second", "cat <<'EOF'\nsecond\nEOF\necho end"]
)
def test_running_heredoc_rejects_new_command_without_wrapper(
    tmp_path, terminal_type, follow_up
):
    session = create_terminal_session(
        work_dir=tmp_path,
        terminal_type=terminal_type,
        no_change_timeout_seconds=2,
    )
    session.initialize()
    try:
        session.execute(
            TerminalAction(command="cat <<'EOF'\nbody\nEOF\nsleep 8; echo done\n")
        )
        assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT

        obs = session.execute(TerminalAction(command=follow_up))
        assert obs.is_error
        assert "__openhands_status" not in obs.text
        assert "__OH_COMMAND_FINISHED_" not in obs.text

        obs = session.execute(TerminalAction(command="", timeout=10))
        assert "done" in obs.text
        assert "__openhands_status" not in obs.text
        assert "__OH_COMMAND_FINISHED_" not in obs.text

        obs = session.execute(TerminalAction(command="echo second"))
        assert not obs.is_error
        assert "second" in obs.text
    finally:
        session.close()


@parametrize_terminal_types
def test_closing_the_session_stops_waiting_on_a_running_command(terminal_type):
    session = create_terminal_session(work_dir=os.getcwd(), terminal_type=terminal_type)
    session.initialize()
    observations: list[TerminalObservation] = []
    action = TerminalAction(command="sleep 30", timeout=60)
    waiter = threading.Thread(
        target=lambda: observations.append(session.execute(action))
    )
    waiter.start()
    time.sleep(2)

    closed_at = time.monotonic()
    session.close()
    waiter.join(timeout=10)

    assert not waiter.is_alive(), "execute() kept waiting on a command after close()"
    assert time.monotonic() - closed_at < 10
    (obs,) = observations
    assert obs.is_error
    assert obs.exit_code == -1
    assert "terminal was closed" in obs.text
