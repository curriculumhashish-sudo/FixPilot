"""测试终端转义序列过滤。

See: https://github.com/OpenHands/software-agent-sdk/issues/2244
"""

import tempfile

import pytest

from openhands.tools.terminal.definition import TerminalAction
from openhands.tools.terminal.terminal import create_terminal_session
from openhands.tools.terminal.utils.escape_filter import (
    TerminalQueryFilter,
    filter_terminal_queries,
)


class TestFilterTerminalQueries:
    """测试 filter_terminal_queries 函数（无状态 API）。"""

    def test_dsr_query_removed(self):
        """DSR（设备状态报告）查询应删除。"""
        # \x1b[6n 为光标位置查询
        output = "some text\x1b[6nmore text"
        result = filter_terminal_queries(output)
        assert result == "some textmore text"

    def test_osc_11_background_query_removed(self):
        """OSC 11（背景颜色查询）应删除。"""
        # \x1b]11;?\x07 查询背景颜色
        output = "start\x1b]11;?\x07end"
        result = filter_terminal_queries(output)
        assert result == "startend"

    def test_osc_10_foreground_query_removed(self):
        """OSC 10（前景色查询）应删除。"""
        output = "start\x1b]10;?\x07end"
        result = filter_terminal_queries(output)
        assert result == "startend"

    def test_osc_4_palette_query_removed(self):
        """OSC 4（调色板颜色查询）应删除。"""
        output = "start\x1b]4;?\x07end"
        result = filter_terminal_queries(output)
        assert result == "startend"

    def test_osc_4_palette_with_index_query_removed(self):
        """应删除带有调色板索引（e.g.，颜色 5）的 OSC 4。"""
        output = "start\x1b]4;5;?\x07end"
        result = filter_terminal_queries(output)
        assert result == "startend"

    def test_osc_12_cursor_color_query_removed(self):
        """OSC 12（光标颜色查询）应删除。"""
        output = "start\x1b]12;?\x07end"
        result = filter_terminal_queries(output)
        assert result == "startend"

    def test_osc_17_highlight_query_removed(self):
        """OSC 17（突出显示后台查询）应删除。"""
        output = "start\x1b]17;?\x07end"
        result = filter_terminal_queries(output)
        assert result == "startend"

    def test_osc_set_title_preserved(self):
        """OSC 0（设置窗口标题）应该删除不 - 这是一个 SET，而不是查询。"""
        output = "start\x1b]0;My Window Title\x07end"
        result = filter_terminal_queries(output)
        assert result == output  # 按原样保存

    def test_osc_hyperlink_preserved(self):
        """OSC 8（超链接）应删除不。"""
        output = "start\x1b]8;;https://example.com\x07link\x1b]8;;\x07end"
        result = filter_terminal_queries(output)
        assert result == output  # 按原样保存

    def test_osc_with_st_terminator_removed(self):
        """应删除带有 ST 终止符的 OSC 查询。"""
        # ST 终止符是 \x1b\\
        output = "start\x1b]11;?\x1b\\end"
        result = filter_terminal_queries(output)
        assert result == "startend"

    def test_da_primary_query_removed(self):
        """应删除 DA（设备属性）主要查询。"""
        # \x1b[c 和 \x1b[0c
        output = "start\x1b[cend"
        result = filter_terminal_queries(output)
        assert result == "startend"

        output2 = "start\x1b[0cend"
        result2 = filter_terminal_queries(output2)
        assert result2 == "startend"

    def test_da2_secondary_query_removed(self):
        """DA2（辅助设备属性）查询应删除。"""
        # \x1b[>c 和 \x1b[>0c
        output = "start\x1b[>cend"
        result = filter_terminal_queries(output)
        assert result == "startend"

        output2 = "start\x1b[>0cend"
        result2 = filter_terminal_queries(output2)
        assert result2 == "startend"

    def test_decrqss_query_removed(self):
        """DECRQSS（请求选择或设置）查询应删除。"""
        # \x1bP$q...\x1b\\
        output = "start\x1bP$qsetting\x1b\\end"
        result = filter_terminal_queries(output)
        assert result == "startend"

    def test_colors_preserved(self):
        """应删除 ANSI 颜色代码不。"""
        # 红色文本：\x1b[31m
        output = "normal \x1b[31mred text\x1b[0m normal"
        result = filter_terminal_queries(output)
        assert result == output

    def test_cursor_movement_preserved(self):
        """应删除光标移动代码不。"""
        # 移动光标：\x1b[H（起始位置）、\x1b[5A（向上 5）
        output = "start\x1b[Hmiddle\x1b[5Aend"
        result = filter_terminal_queries(output)
        assert result == output

    def test_multiple_queries_removed(self):
        """多个查询序列都应该被删除。"""
        output = "\x1b[6n\x1b]11;?\x07text\x1b[6n"
        result = filter_terminal_queries(output)
        assert result == "text"

    def test_mixed_queries_and_formatting(self):
        """删除查询，同时保留格式。"""
        # 颜色+查询+更多颜色
        output = "\x1b[32mgreen\x1b[6nmore\x1b]11;?\x07text\x1b[0m"
        result = filter_terminal_queries(output)
        assert result == "\x1b[32mgreenmoretext\x1b[0m"

    def test_empty_string(self):
        """空字符串应返回空字符串。"""
        assert filter_terminal_queries("") == ""

    def test_no_escape_sequences(self):
        """没有转义序列的纯文本会通过。"""
        output = "Hello, World!"
        assert filter_terminal_queries(output) == output

    def test_unicode_preserved(self):
        """应保留 Unicode 字符。"""
        output = "Hello 🌍 World \x1b[6n with emoji"
        result = filter_terminal_queries(output)
        assert result == "Hello 🌍 World  with emoji"


class TestTerminalQueryFilter:
    """测试有状态的 TerminalQueryFilter 类。"""

    def test_single_chunk_complete_query(self):
        """应删除单个块中的完整查询。"""
        f = TerminalQueryFilter()
        result = f.filter("text\x1b[6nmore")
        result += f.flush()
        assert result == "textmore"

    def test_split_dsr_query_across_chunks(self):
        """DSR 跨块的查询分割应该被删除。"""
        f = TerminalQueryFilter()
        # 块 1 以 ESC [ 结尾
        result1 = f.filter("prefix\x1b[")
        # 块 2 以 6n 开头
        result2 = f.filter("6nsuffix")
        result2 += f.flush()
        # 合并时应删除查询
        assert result1 + result2 == "prefixsuffix"

    def test_split_osc_query_across_chunks(self):
        """OSC 跨块的查询分割应该被删除。"""
        f = TerminalQueryFilter()
        # 块 1: ESC ] 11 ;
        result1 = f.filter("start\x1b]11;")
        # 大块 2：？ BEL
        result2 = f.filter("?\x07end")
        result2 += f.flush()
        assert result1 + result2 == "startend"

    def test_split_esc_alone_at_end(self):
        """块末尾的单独 ESC 应保留用于下一个块。"""
        f = TerminalQueryFilter()
        # 块 1 仅以 ESC 结尾
        result1 = f.filter("text\x1b")
        # ESC 应该被保留（尚未在结果1中）
        assert result1 == "text"
        # 块 2 完成非查询序列
        result2 = f.filter("[32mgreen")
        result2 += f.flush()
        # 保留颜色代码
        assert result2 == "\x1b[32mgreen"

    def test_incomplete_sequence_flushed_on_complete(self):
        """如果不是查询，则应刷新末尾不完整的序列。"""
        f = TerminalQueryFilter()
        # 末尾颜色代码不完整的块
        result1 = f.filter("text\x1b[32")
        assert result1 == "text"
        # Flush 发出非查询字节
        flushed = f.flush()
        assert flushed == "\x1b[32"

    def test_reset_clears_pending(self):
        """重置应清除所有待处理的字节。"""
        f = TerminalQueryFilter()
        # 留下不完整的序列
        _ = f.filter("text\x1b[")
        # 重置
        f.reset()
        # 新的过滤器调用不应看到旧的待处理
        result = f.filter("new text")
        result += f.flush()
        assert result == "new text"

    def test_multiple_commands_with_reset(self):
        """模拟多个命令输出，并在它们之间进行重置。"""
        f = TerminalQueryFilter()
        # 命令1输出
        result1 = f.filter("cmd1 output\x1b[6n")
        result1 += f.flush()
        assert result1 == "cmd1 output"
        # 重置以执行下一个命令
        f.reset()
        # 命令2输出
        result2 = f.filter("cmd2 output\x1b]11;?\x07")
        result2 += f.flush()
        assert result2 == "cmd2 output"

    def test_incremental_output_simulated(self):
        """模拟长时间运行命令的增量输出。"""
        f = TerminalQueryFilter()
        # 模拟：“进度：25%\x1b[6n50%\x1b]11;?\x0775%100%”
        # 在任意点分割成块
        chunk1 = "Progress: 25%\x1b["  # DSR开始
        chunk2 = "6n50%\x1b]"  # DSR 结束，OSC 开始
        chunk3 = "11;?\x0775%100%"  # OSC 结束

        r1 = f.filter(chunk1)
        r2 = f.filter(chunk2)
        r3 = f.filter(chunk3)
        r3 += f.flush()

        assert r1 + r2 + r3 == "Progress: 25%50%75%100%"

    def test_decrqss_split_across_chunks(self):
        """DECRQSS 跨块的查询分割应该被删除。"""
        f = TerminalQueryFilter()
        # DCS P $ q ... ST 其中 ST 是 ESC \
        result1 = f.filter("text\x1bP$q")
        result2 = f.filter("setting\x1b\\more")
        result2 += f.flush()
        assert result1 + result2 == "textmore"

    def test_decrqss_split_at_st_terminator(self):
        """在 ST 终止符边界处分块的 DECRQSS 查询应被移除。

        回归测试：https://github.com/OpenHands/software-agent-sdk/pull/2334
        当分块边界位于 ST 终止符（\x1b\\）的 ESC 与反斜杠之间时，
        仍必须过滤整个 DCS 序列。
        """
        f = TerminalQueryFilter()
        # ESC 位于分隔符 ST 的末端：chunk 1： "text\x1bP$qsetting\x1b"，chunk 1 结束；
        # ESC 位于分隔符 ST 的开始：chunk 2： "\\more"，反斜杠完成分隔符
        #
        result1 = f.filter("text\x1bP$qsetting\x1b")
        result2 = f.filter("\\more")
        result2 += f.flush()
        assert result1 + result2 == "textmore"

    def test_formatting_preserved_across_chunks(self):
        """应保留跨块分割的颜色/格式代码。"""
        f = TerminalQueryFilter()
        # 颜色代码分割：ESC [ 3 | 1 m
        result1 = f.filter("normal \x1b[3")
        result2 = f.filter("1mred text\x1b[0m")
        result2 += f.flush()
        assert result1 + result2 == "normal \x1b[31mred text\x1b[0m"

    def test_mixed_queries_and_formatting_across_chunks(self):
        """混合查询和格式化分为多个块。"""
        f = TerminalQueryFilter()
        # 输入：“\x1b[32mgreen\x1b[6nmore\x1b]11;?\x07text\x1b[0m”
        # 奇怪地分裂
        chunk1 = "\x1b[32mgreen\x1b["  # 颜色 + DSR 的开头
        chunk2 = "6nmore\x1b]11"  # DSR 结束 + OSC 开始
        chunk3 = ";?\x07text\x1b[0m"  # OSC结束+重置

        r1 = f.filter(chunk1)
        r2 = f.filter(chunk2)
        r3 = f.filter(chunk3)
        r3 += f.flush()

        assert r1 + r2 + r3 == "\x1b[32mgreenmoretext\x1b[0m"


# ── 集成测试：TerminalSession 中的过滤器 ────────────── 这些测试通过 TerminalSession 执
# 行实际命令，以验证终端查询序列是否从捕获的输出中过滤掉。 他们运用完整的管道（PTY → 输
# 出捕获 → 过滤器），而不仅仅是孤立的 TerminalQueryFilter 类。
#
# 在 main 上（没有过滤器），这些测试 FAIL 因为原始查询序列传递到观测结果文本。
#

terminal_types = ["subprocess", "tmux"]
parametrize_terminal = pytest.mark.parametrize("terminal_type", terminal_types)


@parametrize_terminal
def test_session_filters_osc_background_query(terminal_type):
    """OSC 11 命令输出中的背景颜色查询被删除。

    `gh` 和 `npm` 等工具发出 OSC 查询以进行终端功能检测。 如果不进行过滤，这些内容就
    会泄漏到观测结果文本中，并在显示时产生可见的垃圾。
    """
    with tempfile.TemporaryDirectory() as tmp:
        session = create_terminal_session(work_dir=tmp, terminal_type=terminal_type)
        session.initialize()
        try:
            obs = session.execute(
                TerminalAction(command="printf 'before\\x1b]11;?\\x07after\\n'")
            )
            assert "\x1b]11;?" not in obs.text
            assert "before" in obs.text
            assert "after" in obs.text
        finally:
            session.close()


@parametrize_terminal
def test_session_filters_dsr_cursor_query(terminal_type):
    """DSR 光标位置查询 (\\x1b[6n) 已从输出中删除。

    Spinner 库发送 DSR 以确定光标位置。 查询不得出现在返回的观测结果中。
    """
    with tempfile.TemporaryDirectory() as tmp:
        session = create_terminal_session(work_dir=tmp, terminal_type=terminal_type)
        session.initialize()
        try:
            obs = session.execute(
                TerminalAction(command="printf 'hello\\x1b[6nworld\\n'")
            )
            assert "\x1b[6n" not in obs.text
            assert "hello" in obs.text
            assert "world" in obs.text
        finally:
            session.close()


@parametrize_terminal
def test_session_filters_multiple_query_types(terminal_type):
    """单个命令输出中的多个查询类型均被剥离。"""
    with tempfile.TemporaryDirectory() as tmp:
        session = create_terminal_session(work_dir=tmp, terminal_type=terminal_type)
        session.initialize()
        try:
            obs = session.execute(
                TerminalAction(command=("printf 'a\\x1b[6nb\\x1b]11;?\\x07c\\n'"))
            )
            assert "\x1b[6n" not in obs.text
            assert "\x1b]11;?" not in obs.text
            assert "a" in obs.text
            assert "b" in obs.text
            assert "c" in obs.text
        finally:
            session.close()


def test_session_preserves_ansi_colors():
    """ANSI 颜色代码必须经过过滤（而不是查询）。

    仅使用子进程进行测试； tmux 捕获窗格条带 ANSI 属性。
    """
    with tempfile.TemporaryDirectory() as tmp:
        session = create_terminal_session(work_dir=tmp, terminal_type="subprocess")
        session.initialize()
        try:
            obs = session.execute(
                TerminalAction(command=("printf '\\x1b[32mgreen text\\x1b[0m\\n'"))
            )
            assert "\x1b[32m" in obs.text
            assert "\x1b[0m" in obs.text
            assert "green text" in obs.text
        finally:
            session.close()


def test_session_filters_query_but_preserves_colors():
    """混合输出：删除查询，保留格式。

    模拟一个工具同时发出和的真实世界场景 ANSI 在同一个输出流中显示格式化颜色和能力检
    测终端查询。

    仅使用子进程进行测试； tmux 捕获窗格条带 ANSI 属性。
    """
    with tempfile.TemporaryDirectory() as tmp:
        session = create_terminal_session(work_dir=tmp, terminal_type="subprocess")
        session.initialize()
        try:
            obs = session.execute(
                TerminalAction(
                    command=("printf '\\x1b[32mgreen\\x1b]11;?\\x07text\\x1b[0m\\n'")
                )
            )
            # 查询已删除
            assert "\x1b]11;?" not in obs.text
            # 保留颜色
            assert "\x1b[32m" in obs.text
            assert "\x1b[0m" in obs.text
            assert "green" in obs.text
            assert "text" in obs.text
        finally:
            session.close()
