"""从捕获的输出中过滤终端查询序列。

当 CLI 工具（如 `gh`、`npm` 等）在 PTY 内运行时，它们可能会发送终端查询序列作为其进度
/旋转器 UI 的一部分。 这些查询被捕获为输出。 显示时，终端会
处理它们并做出响应，从而导致可见的转义代码垃圾。

该模块提供过滤功能以删除这些查询序列，同时保留合法的格式转义码（颜色、粗体等）。

NOTE: 该模块仅处理从 PTY 输出捕获的查询（命令
通过终端工具运行）。 SDK-侧查询（如e.g.，丰富的库能力检测）未在此处处理，并且需要在会
话/可视化边界处进行过滤。

See: https://github.com/OpenHands/software-agent-sdk/issues/2244
"""

import re


# 触发响应（并导致可见垃圾）的终端查询序列应在显示之前从捕获的输出中删除。
#
# 参考：ECMA-48，XTerm 控制序列
# https://invisible-island.net/xterm/ctlseqs/ctlseqs.html

# DSR(设备状态报告)-光标位置查询
# 格式：ESC [ 6 n -> 响应：ESC [ 行； R 列
_DSR_PATTERN = re.compile(rb"\x1b\[6n")

# OSC（操作系统命令）查询
# Format: ESC ] Ps ; ? (BEL | ST)
# 这 ”;？”模式表示 QUERY（相对于具有实际值的 SET）
# Examples:
# OSC 10 ； ？ - 前景色查询 OSC 11 ; ？ - 背景颜色查询 OSC 4 ; 指数 ; ？ - 调色板颜色查
# 询 OSC 12 ; ？ - 光标颜色查询 OSC 17 ; ？ - 突出显示后台查询
# 终止符：BEL (\x07) 或 ST (ESC \)
#
# 此模式匹配 ANY OSC 查询（以 ;? 结尾）而不是特定代码，使其适用于其他查询类型。
#
_OSC_QUERY_PATTERN = re.compile(
    rb"\x1b\]"  # OSC 介绍人
    rb"\d+"  # 参数编号（10、11、4、12等）
    rb"(?:;[^;\x07\x1b]*)?"  # 可选子参数（e.g.，调色板索引）
    rb";\?"  # 查询标记 - 这是一个查询的关键指示符
    rb"(?:\x07|\x1b\\)"  # BEL 或 ST 终止符
)

# DA（设备属性）主查询
# 格式：ESC[c 或 ESC[0c
_DA_PATTERN = re.compile(rb"\x1b\[0?c")

# DA2（次设备属性）查询
# 格式：ESC [ > c 或 ESC [ > 0 c
_DA2_PATTERN = re.compile(rb"\x1b\[>0?c")

# DECRQSS（请求选择或设置）-各种终端状态查询
# 格式：ESCP$q<setting>ST
_DECRQSS_PATTERN = re.compile(
    rb"\x1bP\$q"  # DCS介绍人+DECRQSS
    rb"[^\x1b]*"  # 设置标识符
    rb"\x1b\\"  # ST终结者
)

# 用于检测块末尾不完整转义序列的模式。 这些是可能在下一个块中完成的潜在查询序列前缀。 我
# 们寻找：
#   - \x1b 单独（CSI/OSC/DCS 开始）
#   - \x1b[ 后跟可选数字/参数，但没有命令字符
#   - \x1b] 后跟数字但没有终止符
#   - \x1bP 后跟内容但无 ST 终止符（包括部分 ST）
#
# 注意：DCS 序列以 ST (\x1b\\) 终止。 当一个块结束时
# 开始 ST 的 ESC，我们必须保留 ENTIRE DCS 序列，而不仅仅是尾随的 ESC。 该模式通过匹配 \
# x1bP 后跟不包含完整 ST 终止符的任何内容来处理此问题。
#
_INCOMPLETE_ESC_PATTERN = re.compile(
    rb"(?:"
    rb"\x1b$|"  # ESC 结束（可能是任何序列的开始）
    rb"\x1b\[[0-9;>]*$|"  # CSI 无命令字符
    rb"\x1b\][^\x07]*$|"  # OSC 不带 BEL 终止符（ST 需要 \x1b\）
    rb"\x1bP(?:[^\x1b]|\x1b(?!\\))*$"  # DCS 无完整 ST 终止符
    rb")"
)


def _filter_complete_queries(output_bytes: bytes) -> bytes:
    """从输出字节中过滤完整的终端查询序列。"""
    output_bytes = _DSR_PATTERN.sub(b"", output_bytes)
    output_bytes = _OSC_QUERY_PATTERN.sub(b"", output_bytes)
    output_bytes = _DA_PATTERN.sub(b"", output_bytes)
    output_bytes = _DA2_PATTERN.sub(b"", output_bytes)
    output_bytes = _DECRQSS_PATTERN.sub(b"", output_bytes)
    return output_bytes


class TerminalQueryFilter:
    """终端查询序列的状态过滤器。

    该过滤器在处理可能跨越多个输出分块（例如，长运行命令以增量方式呈现）的转义序列时
    ，维护会话状态。

    用途：
        filter = TerminalQueryFilter()
        filtered1 = filter.filter(chunk1)
        filtered2 = filter.filter(chunk2)
        # ... 等等

        # 命令完成后，重置下一个命令：
        filter.reset()
    """

    def __init__(self) -> None:
        self._pending: bytes = b""

    def reset(self) -> None:
        """在命令之间重置过滤器状态。"""
        self._pending = b""

    def filter(self, output: str) -> str:
        """从捕获的终端输出中过滤终端查询序列。

        移除会导致终端响应的转义序列，同时保留合法的格式化序列（颜色、光标移动等）。

        此方法是状态化的：在分块末尾出现不完整的转义序列会被保留到下一个分块到达，因
        此分隔序列会被正确检测和过滤。

        Args:
            output: 可能包含查询序列的原始终端输出。

        Returns:
            已删除查询序列的过滤输出。
        """
        # 转换为字节以进行正则表达式匹配（转义序列是字节级的）
        output_bytes = output.encode("utf-8", errors="surrogateescape")

        # 在之前的调用中添加任何挂起的字节
        if self._pending:
            output_bytes = self._pending + output_bytes
            self._pending = b""

        # 检查末尾的转义序列是否不完整
        match = _INCOMPLETE_ESC_PATTERN.search(output_bytes)
        if match:
            # 保留下一个块的不完整序列
            self._pending = output_bytes[match.start() :]
            output_bytes = output_bytes[: match.start()]

        # 过滤完整的查询序列
        output_bytes = _filter_complete_queries(output_bytes)

        # 转换回字符串
        return output_bytes.decode("utf-8", errors="surrogateescape")

    def flush(self) -> str:
        """刷新不属于查询一部分的所有待处理字节。

        当输出完成时调用此函数以发出任何结果不是查询序列的尾随字节。

        Returns:
            任何挂起的字节作为字符串，针对查询进行过滤。
        """
        if not self._pending:
            return ""
        pending = self._pending
        self._pending = b""
        # 过滤待处理的字节，以防它们形成完整的查询
        filtered = _filter_complete_queries(pending)
        return filtered.decode("utf-8", errors="surrogateescape")


def filter_terminal_queries(output: str) -> str:
    """从捕获的终端输出中过滤终端查询序列。

    这是一个无状态的便利函数。 为了处理序列可能被分割成块的增量输出，请使用
    TerminalQueryFilter 类。

    移除会导致终端响应的转义序列，同时保留合法的格式化序列（颜色、光标移动等）。

    Args:
        output: 可能包含查询序列的原始终端输出。

    Returns:
        已删除查询序列的过滤输出。
    """
    # 使用新的过滤器进行无状态行为
    temp_filter = TerminalQueryFilter()
    result = temp_filter.filter(output)
    # 刷新任何待处理的内容（完整输入不应发生，但要安全）
    result += temp_filter.flush()
    return result
