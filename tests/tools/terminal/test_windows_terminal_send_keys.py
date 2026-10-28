"""``WindowsTerminal.send_keys`` 的字节级覆盖率。

这些测试针对存根 PowerShell 进程驱动真实的 ``send_keys()``，因此它们可以在每个平台上
运行，而不仅仅是在 Windows CI 作业中运行。 他们
将换行合同绑定在多行修复依赖的PowerShell上：``>>``在提示词的多行语句上，直到接收到空
白行，所以多行输入必须以``\\n\\n``结束，而单行输入则必须保持一
个``\\n``。
"""

import tempfile
from typing import Any, cast

import pytest

from openhands.tools.terminal.terminal.windows_terminal import WindowsTerminal


class _FakeStdin:
    def __init__(self) -> None:
        self.written = bytearray()

    def write(self, data: bytes) -> int:
        self.written.extend(data)
        return len(data)

    def flush(self) -> None:
        return None


class _FakeProcess:
    """实时 PowerShell 进程的最小替代。"""

    def __init__(self) -> None:
        self.stdin = _FakeStdin()

    def poll(self) -> int | None:
        return None


def _sent_text(command: str, enter: bool = True) -> str:
    """准确返回 ``send_keys`` 写入 PowerShell 的标准输入的内容。"""
    with tempfile.TemporaryDirectory() as work_dir:
        terminal = WindowsTerminal(work_dir=work_dir, shell_path="powershell.exe")
        process = _FakeProcess()
        terminal.process = cast(Any, process)
        terminal.send_keys(command, enter=enter)
        return process.stdin.written.decode("utf-8")


MULTILINE_COMMANDS = [
    pytest.param('Write-Output "a\nb"', id="newline-in-string"),
    pytest.param('if ($true) {\n    Write-Output "yes"\n}', id="if-block"),
    pytest.param('foreach ($i in 1..2) {\n    Write-Output "n$i"\n}', id="foreach"),
    pytest.param('Write-Output `\n    "cont"', id="backtick-continuation"),
    pytest.param('1..3 |\n    ForEach-Object { "v$_" }', id="pipeline"),
    pytest.param('Write-Output "a\r\nb"', id="crlf-newline"),
]

SINGLE_LINE_COMMANDS = [
    pytest.param("Get-ChildItem", id="bare-cmdlet"),
    pytest.param('Write-Output "hello"', id="quoted-arg"),
    pytest.param("Get-Process | Select-Object -First 1", id="single-line-pipeline"),
]


@pytest.mark.parametrize("command", MULTILINE_COMMANDS)
def test_multiline_input_ends_with_blank_line(command: str) -> None:
    """空行是提交 PowerShell 的连续缓冲区的内容。"""
    sent = _sent_text(command)

    assert sent.endswith("\n\n")


@pytest.mark.parametrize("command", SINGLE_LINE_COMMANDS)
def test_single_line_input_ends_with_exactly_one_newline(command: str) -> None:
    """单行路径保持不变：一个换行符，没有虚假的空行。"""
    sent = _sent_text(command)

    assert sent.endswith("\n")
    assert not sent.endswith("\n\n")


@pytest.mark.parametrize("command", MULTILINE_COMMANDS + SINGLE_LINE_COMMANDS)
def test_metadata_suffix_is_submitted_with_the_command(command: str) -> None:
    """PS1 元数据后缀随之而来，因此可以解析回标记。"""
    sent = _sent_text(command)

    assert "$oh1 = $?" in sent
    assert sent.startswith(command.rstrip())


@pytest.mark.parametrize("command", MULTILINE_COMMANDS + SINGLE_LINE_COMMANDS)
def test_enter_false_appends_no_newline(command: str) -> None:
    """``enter=False`` 不得提交任何内容，无论是否为多行。"""
    sent = _sent_text(command, enter=False)

    assert not sent.endswith("\n")
