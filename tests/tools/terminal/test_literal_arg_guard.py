"""SDK-5：防止传递给终端工具的 Python/JSON 文字。

Motivation: 在实际的评估运行中（e.g. SWE-Bench 上的 Nemotron 550B），该模型
有时会将结构化参数（设置字典、已安装应用程序列表、代码 blob）打包到单个 ``command``
字段中。 然后外壳发出回声
``bash: [{default:: command not found`` 并且模型会轮流重试类似的垃圾。 该守卫捕获字面
上的预执行，并用可操作的提示进行回复。
"""

import pytest

from openhands.tools.terminal.definition import (
    TerminalAction,
    TerminalObservation,
    looks_like_python_literal_argument,
)
from openhands.tools.terminal.impl import TerminalExecutor


# --------------------------------------------------------------------------
# 单元测试为启发式。
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command,expected",
    [
        # 从 SWE-Bench Nemotron 运行中提取的真实畸形示例。
        ("[['col1', 'col2'], ['col1', 'col2']]", "nested list literal"),
        (
            "[{'default': {'ENGINE': 'django.db.backends.sqlite3'}}, "
            "['django.contrib.auth']]",
            "list literal",
        ),
        ('["field.column]\\n\\nwith connection.schema_editor() ..."]', "list literal"),
        # 合成变体。
        ('{"key": "value"}', "dict literal"),
        ("{'key': 'value'}", "dict literal"),
        # 分类之前必须去除前导空格。
        ("   [{'a': 1}]", "list literal"),
        ('\t["x"]', "list literal"),
    ],
)
def test_python_literals_are_detected(command: str, expected: str) -> None:
    assert looks_like_python_literal_argument(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        # 合法的 bash 测试必须不绊倒警卫。
        "[ -f /tmp/foo ]",
        "[ -d /workspace ]",
        '[[ "$x" = "y" ]]',
        "[[ -z $VAR ]]",
        # Bash 组命令。
        "{ ls; echo done; }",
        # 正常命令。
        "ls -la",
        "python -c 'print(1)'",
        # 即使参数恰好是 JSON 形状的命令也可以，因为 COMMAND 名称是纯文本。
        #
        "echo '[1, 2, 3]'",
        "curl -d '{\"a\": 1}' http://x",
        # 边缘：空/单字符字符串永远不应该跳闸。
        "",
        "[",
        "{",
        " ",
    ],
)
def test_legitimate_commands_are_not_flagged(command: str) -> None:
    assert looks_like_python_literal_argument(command) is None


# --------------------------------------------------------------------------
# 执行器级集成：文字 => 结构化错误，无 shell。
# --------------------------------------------------------------------------


_SHELL_SENTINEL = "Executor should not reach the shell when the command is rejected"


@pytest.fixture
def executor_without_shell() -> TerminalExecutor:
    """在不接触真实外壳的情况下构建 TerminalExecutor。

    我们绕过 ``__init__`` (启动真实 tmux/subprocess 会话) 并 stub 两个 shell 执行路径
    以提高。  该守卫是 literal
     的 *之前* 那些路径，因此一个无关的命令必须绕过保护并触发哨兵值 ——这就是我们证明
     守卫没有开枪的方式。
    """
    exe = TerminalExecutor.__new__(TerminalExecutor)
    exe._pool = None

    def _reach_shell(*_args: object, **_kwargs: object) -> TerminalObservation:
        raise AssertionError(_SHELL_SENTINEL)

    exe._execute_pooled = _reach_shell  # type: ignore[method-assign]
    exe._execute_single_session = _reach_shell  # type: ignore[method-assign]
    return exe


def test_literal_command_returns_structured_error_without_shell(
    executor_without_shell: TerminalExecutor,
) -> None:
    action = TerminalAction(command="[{'default': {'ENGINE': 'sqlite3'}}]")
    obs = executor_without_shell(action)

    assert isinstance(obs, TerminalObservation)
    assert obs.is_error is True
    assert obs.exit_code is None
    assert obs.command == action.command
    text = obs.text
    assert "list literal" in text
    # 提示必须教导具体的恢复路径。
    assert "file_editor" in text
    assert "heredoc" in text or "<<'EOF'" in text


def test_bash_test_expression_not_blocked(
    executor_without_shell: TerminalExecutor,
) -> None:
    """真正的 bash `[ -f ... ]` 必须到达 shell，而不是文字保护。"""
    action = TerminalAction(command="[ -f /tmp/foo ]")
    with pytest.raises(AssertionError, match=_SHELL_SENTINEL):
        executor_without_shell(action)


def test_is_input_path_skips_guard(
    executor_without_shell: TerminalExecutor,
) -> None:
    """``is_input=True`` 将原始字节转发到正在运行的进程。 击键
    像 ``C-c`` 或任意文字在上下文中都是有效的，并且必须绕过防护。
    """
    action = TerminalAction(command="[{'sent_as_keystrokes': True}]", is_input=True)
    with pytest.raises(AssertionError, match=_SHELL_SENTINEL):
        executor_without_shell(action)


def test_guard_warning_is_logged(
    executor_without_shell: TerminalExecutor,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """操作员应该能够在评估日志中查找守卫触发情况。"""
    import logging

    caplog.set_level(logging.WARNING, logger="openhands.tools.terminal.impl")
    action = TerminalAction(command='["some code that should have been a script"]')
    executor_without_shell(action)
    assert any(
        "Rejected terminal call" in rec.message and "list literal" in rec.message
        for rec in caplog.records
    )
