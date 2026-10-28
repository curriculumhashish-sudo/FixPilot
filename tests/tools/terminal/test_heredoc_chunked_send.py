"""测试heredoc分块发送修复（GitHub问题#2181）。

这测试了长多行命令（如heredocs）是否逐行发送，以避免压垮macOS上的PTY输入缓冲区。
"""

import platform
import tempfile
import time

import pytest


if platform.system() == "Windows":
    pytest.skip(
        "SubprocessTerminal uses Unix PTY APIs and is not available on Windows",
        allow_module_level=True,
    )

from openhands.tools.terminal.terminal.subprocess_terminal import SubprocessTerminal


@pytest.fixture
def terminal():
    """创建一个 SubprocessTerminal 进行测试。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        term = SubprocessTerminal(work_dir=tmpdir)
        term.initialize()
        # 留出初始化时间
        time.sleep(1)
        yield term
        term.close()


def create_heredoc_command(num_lines: int) -> str:
    """创建具有指定行数的heredoc命令。"""
    lines = [f"print('Line {i}')" for i in range(num_lines)]
    script = "\n".join(lines)
    return f"""cat > /tmp/test_script.py << 'EOF'
{script}
EOF
python3 /tmp/test_script.py"""


def test_short_heredoc_works(terminal: SubprocessTerminal):
    """测试短heredocs（低于阈值）是否有效。"""
    terminal.clear_screen()
    time.sleep(0.1)

    # 5 行远低于阈值
    cmd = create_heredoc_command(5)
    terminal.send_keys(cmd)

    # 等待完成
    start_time = time.time()
    while terminal.is_running() and time.time() - start_time < 10:
        time.sleep(0.1)

    output = terminal.read_screen()
    assert "Line 4" in output


def test_long_heredoc_works(terminal: SubprocessTerminal):
    """测试长heredocs（超过阈值）是否适用于分块发送。"""
    terminal.clear_screen()
    time.sleep(0.1)

    # 50 行超过 20 的 _MULTILINE_THRESHOLD
    cmd = create_heredoc_command(50)
    terminal.send_keys(cmd)

    # 等待完成
    start_time = time.time()
    while terminal.is_running() and time.time() - start_time < 30:
        time.sleep(0.1)

    output = terminal.read_screen()
    assert "Line 49" in output


def test_very_long_heredoc_works(terminal: SubprocessTerminal):
    """测试很长的heredocs是否可以与分块发送一起使用。"""
    terminal.clear_screen()
    time.sleep(0.1)

    # 100 行 - 如果不修复的话就会挂起
    cmd = create_heredoc_command(100)
    terminal.send_keys(cmd)

    # 等待完成
    start_time = time.time()
    while terminal.is_running() and time.time() - start_time < 60:
        time.sleep(0.1)

    output = terminal.read_screen()
    assert "Line 99" in output


def test_multiline_threshold_boundary(terminal: SubprocessTerminal):
    """测试阈值边界处的行为。"""
    terminal.clear_screen()
    time.sleep(0.1)

    # 恰好在阈值（20 行）- 应使用正常路径
    cmd = create_heredoc_command(20)
    terminal.send_keys(cmd)

    start_time = time.time()
    while terminal.is_running() and time.time() - start_time < 15:
        time.sleep(0.1)

    output = terminal.read_screen()
    assert "Line 19" in output

    # 超过阈值一（21 行）- 应使用分块路径
    terminal.clear_screen()
    time.sleep(0.1)

    cmd = create_heredoc_command(21)
    terminal.send_keys(cmd)

    start_time = time.time()
    while terminal.is_running() and time.time() - start_time < 15:
        time.sleep(0.1)

    output = terminal.read_screen()
    assert "Line 20" in output


def test_special_keys_not_affected_by_chunking():
    """测试像 C-c 这样的特殊键不受多行逻辑的影响。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        term = SubprocessTerminal(work_dir=tmpdir)
        term.initialize()
        time.sleep(1)

        try:
            # 启动长时间运行的命令
            term.send_keys("sleep 60")
            time.sleep(0.5)

            # 发送 Ctrl-C - 这应该立即生效
            term.send_keys("C-c")
            time.sleep(0.5)

            # 通过检查我们是否可以读取输出来验证终端是否仍然响应
            screen = term.read_screen()
            assert len(screen) > 0  # 终端应该仍然可以运行

            # 验证一个简单的命令在 Ctrl-C 之后是否有效
            term.send_keys("echo 'test_complete'")
            time.sleep(0.5)
            screen = term.read_screen()
            assert "test_complete" in screen
        finally:
            term.close()
