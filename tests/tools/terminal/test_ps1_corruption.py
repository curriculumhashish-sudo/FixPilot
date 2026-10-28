"""
测试 PS1 元数据损坏恢复。

当并发终端输出（进度条、旋转器或其他标准输出）与 shell 的 PS1 提示词渲染交错时，PS1
块可能会损坏。 这是介于 shell 编写 PS1 和程序编写输出之间的
竞态条件。

正则表达式使用负向先行仅匹配每个 ###PS1END### 之前的 LAST ###PS1JSON###，自动处理损坏
情况。
"""

import logging
from unittest.mock import MagicMock

import pytest

from openhands.tools.terminal.constants import CMD_OUTPUT_METADATA_PS1_REGEX
from openhands.tools.terminal.metadata import CmdOutputMetadata
from openhands.tools.terminal.terminal.terminal_session import TerminalSession


class TestPS1Corruption:
    """测试 PS1 元数据块损坏恢复。"""

    # 输出损坏，其中并发 stdout 中断第一个 PS1 块。 正则表达式从第一个 ###PS1JSON### 匹
    # 配到仅 ###PS1END###，从而创建一个无效匹配。 该修复恢复了有效的第二个块。
    #
    CORRUPTED_OUTPUT_GRUNT_CAT = r"""
###PS1JSON###
{
  "pid": "",
  "exit_code": "0",
  "username": "openhands",
  "hostname": "runtime-uerbtodceoavkhsd-5f46cc485d-297jp",
  "working_dir": "/workspace/p5.js",
  "py_interpreter_path": "/usr/bin/python"
 8   -_-_-_-_-_,------,
 0#PS-_-_-_-_-_|   /\_/\
 0 /w-_-_-_-_-^|__( ^ .^) eout 300 npm test 2>&1 | tail -50
     -_-_-_-_-  ""  ""

  8 passing (6ms)


Done.

###PS1JSON###
{
  "pid": "",
  "exit_code": "0",
  "username": "openhands",
  "hostname": "runtime-uerbtodceoavkhsd-5f46cc485d-297jp",
  "working_dir": "/workspace/p5.js",
  "py_interpreter_path": "/usr/bin/python"
}
###PS1END###"""

    # 另一个带有 ANSI 残留的损坏输出
    CORRUPTED_OUTPUT_ANSI_REMNANTS = r"""
###PS1JSON###
{
  "pid": "877",
  "exit_code": "0",
  "username": "openhands",
  "hostname": "runtime-wurijejgnynchahc-f9f4f7f-ndqfp",
  "working_dir": "/workspace/p5.js",
  "py_interpreter_path": "/usr/bin/python"
 8   -_-_-_-_-_,------,
 0#PS-_-_-_-_-_|   /\_/\
 0 /w-_-_-_-_-^|__( ^ .^)  run grunt -- mochaTest:test 2>&1 | tail -30
     -_-_-_-_-  ""  ""

  8 passing (16ms)


Done.

###PS1JSON###
{
  "pid": "877",
  "exit_code": "0",
  "username": "openhands",
  "hostname": "runtime-wurijejgnynchahc-f9f4f7f-ndqfp",
  "working_dir": "/workspace/p5.js",
  "py_interpreter_path": "/usr/bin/python"
}
###PS1END###"""

    # 没有 PS1 标记的寻呼机输出（如 `less` 或 `help` 命令） 当寻呼机接管终端屏幕时会发生
    # 这种情况
    #
    PAGER_OUTPUT_NO_PS1 = """Help on class RidgeClassifierCV in sklearn.linear_model:

class RidgeClassifierCV(sklearn.linear_model.base.LinearClassifierMixin, _BaseRidgeCV)
 |  Ridge classifier with built-in cross-validation.
 |
 |  By default, it performs Generalized Cross-Validation, which is a form of
 |  efficient Leave-One-Out cross-validation. Currently, only the n_features >
 |  n_samples case is handled efficiently.
 |
 |  Read more in the :ref:`User Guide <ridge_regression>`.
 |
 |  Parameters
 |  ----------
 |  alphas : numpy array of shape [n_alphas]
~
~
~
~
~
(END)"""

    def test_regex_skips_corrupted_first_block(self):
        """
        测试具有负先行功能的正则表达式是否会跳过损坏的第一个块。

        正则表达式 `###PS1JSON###((?:(?!###PS1JSON###).)*?)###PS1END###` 使用负向先行
        来确保匹配中没有嵌套的
        ###PS1JSON###。 这意味着它仅匹配 ###PS1END### 之前的 LAST 有效块。
        """
        raw_matches = list(
            CMD_OUTPUT_METADATA_PS1_REGEX.finditer(self.CORRUPTED_OUTPUT_GRUNT_CAT)
        )

        # 正则表达式精确找到 1 个匹配项（嵌套标记后的有效块）
        assert len(raw_matches) == 1, (
            f"Expected exactly 1 raw regex match, got {len(raw_matches)}."
        )

        # 匹配的内容应不包含另一个 ###PS1JSON### 标记
        matched_content = raw_matches[0].group(1)
        assert "###PS1JSON###" not in matched_content, (
            "The matched content should NOT contain nested ###PS1JSON### marker."
        )

    def test_corrupted_ps1_recovery(self):
        """
        测试修复是否从损坏的输出中恢复有效的 PS1 块。

        当并发输出损坏第一个 PS1 块时，修复程序会检测嵌套的 ###PS1JSON### 标记并提取
        有效的第二个块。
        """
        matches = CmdOutputMetadata.matches_ps1_metadata(
            self.CORRUPTED_OUTPUT_GRUNT_CAT
        )

        assert len(matches) >= 1, (
            f"Expected at least 1 valid PS1 match, got {len(matches)}. "
            "The fix should recover the valid block from corrupted output."
        )

    def test_handle_completed_command_graceful_fallback_with_corrupted_output(self):
        """
        测试当未找到 PS1 块时 _handle_completed_command 是否返回有效的观测结果。

        当终端输出被损坏，无法显示有效的内容 PS1 发现区块后，会优雅地返回一个
        TerminalObservation 与 exit_code-1 而不是崩溃
         AssertionError.

        此修复解决了 Datadog 日志中出现的生产错误。
        """
        from openhands.tools.terminal.terminal.interface import TerminalObservation

        # 创建模拟对象终端接口
        mock_terminal = MagicMock()
        mock_terminal.work_dir = "/workspace"
        mock_terminal.username = None

        # 创建会话
        session = TerminalSession(terminal=mock_terminal)
        session._cwd = "/workspace"
        session._initialized = True

        # 模拟全部 PS1 块损坏的输出在这种情况下，JSON 完全损坏 - 根本没有有效块
        #
        completely_corrupted_output = """\n###PS1JSON###
{
  "pid": "",
  "exit_code": "0",
  "username": "openhands",
 8   -_-_-_-_-_,------,
 0#PS-_-_-_-_-_|   /\\_/\\
 ASCII ART BREAKS THE JSON
###PS1JSON###
ALSO BROKEN
{invalid json here}
###PS1END###"""

        ps1_matches = CmdOutputMetadata.matches_ps1_metadata(
            completely_corrupted_output
        )

        # 验证我们因损坏而获得 0 个匹配项
        assert len(ps1_matches) == 0, (
            f"Expected 0 PS1 matches from corrupted output, got {len(ps1_matches)}"
        )

        # 现在验证它返回有效的观测结果而不是崩溃
        obs = session._handle_completed_command(
            command="npm test",
            terminal_content=completely_corrupted_output,
            ps1_matches=ps1_matches,
        )

        # 验证优雅的回退方案行为
        assert isinstance(obs, TerminalObservation)
        assert obs.exit_code == -1  # 未知退出代码哨兵值
        assert "PS1 metadata" in obs.metadata.suffix

    def test_pager_output_causes_zero_ps1_matches(self):
        """
        测试寻呼机输出（如 `less`）是否产生零个 PS1 匹配。

        当命令打开寻呼机时（例如 Python REPL 或 `man ls` 中的 `help(some_func)`），寻
        呼机将接管终端屏幕。 PS1 提示词永
        远不会出现，因为寻呼机处于交互状态并正在等待
        for user input.

        这会导致“预期执行命令时正好有一个 PS1 元数据块之前，但收到了 0 PS1 个元数据块
        ”警告。
        """
        matches = CmdOutputMetadata.matches_ps1_metadata(self.PAGER_OUTPUT_NO_PS1)

        assert len(matches) == 0, (
            f"Expected 0 PS1 matches from pager output, got {len(matches)}"
        )

    def test_partial_ps1_block_not_matched(self):
        """
        测试部分 PS1 块（缺少 ###PS1END###）是否不匹配。

        这模拟了 PS1 提示词开始打印但在完成之前被中断的情况。 正则表达式应该不匹配不
        完整的块。
        """
        # PS1 开始但永不结束的块（常见于损坏场景）
        partial_block = """
###PS1JSON###
{
  "pid": "123",
  "exit_code": "0",
  "username": "openhands"
}
SOME EXTRA OUTPUT BUT NO PS1END MARKER
"""
        matches = CmdOutputMetadata.matches_ps1_metadata(partial_block)
        assert len(matches) == 0, (
            f"Expected 0 matches for partial PS1 block, got {len(matches)}"
        )

    def test_ps1_block_with_embedded_special_chars(self):
        """
        当特殊字符出现在 JSON 字段值中时测试 PS1 解析。
        """
        # 有效的 PS1 块，但字段值中包含特殊字符
        ps1_with_special_chars = """
###PS1JSON###
{
  "pid": "123",
  "exit_code": "0",
  "username": "openhands",
  "hostname": "host-with-#PS-in-name",
  "working_dir": "/path/with\\backslash",
  "py_interpreter_path": "/usr/bin/python"
}
###PS1END###
"""
        matches = CmdOutputMetadata.matches_ps1_metadata(ps1_with_special_chars)
        assert len(matches) == 1, (
            f"Expected 1 match for PS1 with special chars in values, got {len(matches)}"
        )

    def test_interleaved_output_between_ps1_markers(self):
        """
        测试 PS1 标记之间的交错输出是否会破坏解析。

        当并发输出中断 PS1 JSON 时，解析器应该优雅地跳过格式错误的块。
        """
        interleaved_output = """
###PS1JSON###
{
  "pid": "123"
INTERLEAVED COMMAND OUTPUT HERE - THIS BREAKS THE JSON
}
###PS1END###
"""
        matches = CmdOutputMetadata.matches_ps1_metadata(interleaved_output)

        # 正则表达式 WILL 与此匹配，因为存在标记，但 JSON 解析应该失败并跳过它
        #
        assert len(matches) == 0, (
            f"Expected 0 matches with interleaved output, got {len(matches)}. "
            "The JSON parser should reject malformed JSON between markers."
        )


class TestPS1CorruptionIntegration:
    """集成测试适用于 PS1 腐败场景。"""

    def test_terminal_session_handles_corrupted_output_gracefully(self):
        """
        测试 TerminalSession 是否正常处理缺失的 PS1 块。

        当损坏恢复失败并且找不到有效的 PS1 块时，会话现在会返回 exit_code=-1 的有效
        TerminalObservation，而不是因
        AssertionError 崩溃。
        """
        from openhands.tools.terminal.terminal.interface import TerminalObservation

        mock_terminal = MagicMock()
        mock_terminal.work_dir = "/workspace"
        mock_terminal.username = None

        session = TerminalSession(terminal=mock_terminal)
        session._cwd = "/workspace"
        session._initialized = True

        # 空 PS1 匹配列表（与完全损坏的输出一样）
        empty_matches = []

        # 验证优雅回退方案而不是崩溃
        obs = session._handle_completed_command(
            command="echo test",
            terminal_content="completely garbled output with no PS1 markers",
            ps1_matches=empty_matches,
        )

        # 验证优雅的回退方案行为
        assert isinstance(obs, TerminalObservation)
        assert obs.exit_code == -1  # 未知退出代码哨兵值
        assert "PS1 metadata" in obs.metadata.suffix
        assert "echo test" in obs.text or "garbled" in obs.text


class TestPS1ParserRobustness:
    """测试 PS1 解析器稳健性改进。"""

    def test_regex_handles_multiline_json(self):
        """测试 PS1 正则表达式是否正确处理多行 JSON。"""
        multiline_json = """
###PS1JSON###
{
  "pid": "123",
  "exit_code": "0",
  "username": "openhands",
  "hostname": "localhost",
  "working_dir": "/home/user",
  "py_interpreter_path": "/usr/bin/python"
}
###PS1END###
"""
        matches = CmdOutputMetadata.matches_ps1_metadata(multiline_json)
        assert len(matches) == 1

    def test_multiple_valid_ps1_blocks(self):
        """测试解析多个有效的 PS1 块（正常操作）。"""
        two_blocks = """
###PS1JSON###
{
  "pid": "100",
  "exit_code": "0",
  "username": "user1"
}
###PS1END###
Some command output here
###PS1JSON###
{
  "pid": "101",
  "exit_code": "1",
  "username": "user1"
}
###PS1END###
"""
        matches = CmdOutputMetadata.matches_ps1_metadata(two_blocks)
        assert len(matches) == 2

        # 验证我们可以从两者中提取数据
        meta1 = CmdOutputMetadata.from_ps1_match(matches[0])
        meta2 = CmdOutputMetadata.from_ps1_match(matches[1])
        assert meta1.pid == 100
        assert meta2.pid == 101
        assert meta1.exit_code == 0
        assert meta2.exit_code == 1


def test_regex_handles_nested_markers():
    """
    测试正则表达式是否正确处理嵌套的 ###PS1JSON### 标记。

    当并发输出损坏第一个 PS1 块时，正则表达式应仅匹配 ###PS1END### 之前的 LAST ###
    PS1JSON###。
    """
    corrupted_output = """\
COMMAND OUTPUT BEFORE PS1
###PS1JSON###
{
  "pid": "123",
  "exit_code": "0",
  "username": "openhands"
CONCURRENT OUTPUT CORRUPTS THIS BLOCK
###PS1JSON###
{
  "pid": "456",
  "exit_code": "0",
  "username": "openhands",
  "hostname": "localhost",
  "working_dir": "/workspace",
  "py_interpreter_path": "/usr/bin/python"
}
###PS1END###
COMMAND OUTPUT AFTER PS1"""

    matches = CmdOutputMetadata.matches_ps1_metadata(corrupted_output)

    # 我们应该得到 1 个匹配（嵌套标记之后的有效块）
    assert len(matches) == 1, f"Expected 1 match, got {len(matches)}"

    # 验证匹配包含有效的 JSON
    import json

    content = matches[0].group(1).strip()
    data = json.loads(content)
    assert data["pid"] == "456"  # 应该是第二个块的数据


@pytest.mark.parametrize(
    ("handler_name", "handler_kwargs"),
    [
        ("_handle_nochange_timeout_command", {}),
        ("_handle_hard_timeout_command", {"timeout": 1.0}),
    ],
)
def test_timeout_logs_omit_terminal_content(caplog, handler_name, handler_kwargs):
    terminal = MagicMock()
    terminal.work_dir = "/workspace"
    terminal.username = None
    terminal.is_powershell.return_value = False
    session = TerminalSession(terminal=terminal)
    session._cwd = "/workspace"
    secret = "ghp_" + "c" * 36
    caplog.set_level(logging.DEBUG)

    handler = getattr(session, handler_name)
    handler(
        command=f"echo {secret}",
        terminal_content=f"terminal output containing {secret}",
        ps1_matches=[],
        **handler_kwargs,
    )

    assert "Expected exactly one PS1 metadata block" in caplog.text
    assert secret not in caplog.text
