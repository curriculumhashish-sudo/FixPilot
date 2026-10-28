"""共享 tree-sitter-bash 解析的往返测试入口。

这些测试将下游消费者所依赖的合约 ``openhands-tools.terminal.utils.command`` 并且计划
中的安全分析器依赖于： ``parse``
返回一个 ``ParseResult`` whose ``tree`` 可以使用标准的 tree-sitter 走路 API 和他们的
``has_error`` 国旗忠实
地反映了 ``tree.root_node.has_error``.
"""

from dataclasses import FrozenInstanceError

import pytest

from openhands.sdk.security.shell_parser import ParseResult, parse


class TestParseSuccessShape:
    """成功的解析会生成可用的树和 ``has_error=False``。"""

    def test_returns_parse_result(self):
        result = parse("ls -l")
        assert isinstance(result, ParseResult)

    def test_root_node_is_walkable(self):
        result = parse("echo hello && ls -l")
        # 标准树木保护者 API 表面必须可达。
        assert result.tree.root_node.type == "program"
        assert len(result.tree.root_node.named_children) >= 1

    def test_has_error_false_on_valid_input(self):
        result = parse("for i in 1 2 3; do echo $i; done")
        assert result.has_error is False


class TestParseErrorRecovery:
    """树保姆通过 ERROR 个节点恢复； 它绝不能升高。"""

    @pytest.mark.parametrize(
        "command",
        [
            'echo "unclosed quote',
            "echo 'unclosed quote",
            "cat <<EOF\nunclosed heredoc",
            "echo `unclosed backtick",
        ],
        ids=["double_quote", "single_quote", "heredoc", "backtick"],
    )
    def test_malformed_input_does_not_raise(self, command: str):
        result = parse(command)
        assert isinstance(result, ParseResult)

    def test_has_error_true_on_malformed_input(self):
        result = parse('echo "unclosed quote')
        assert result.has_error is True


class TestParseEdgeCases:
    """空和 unicode 输入往返毫无意外。"""

    def test_empty_string_parses(self):
        result = parse("")
        assert isinstance(result, ParseResult)
        assert result.has_error is False

    def test_utf8_input_parses(self):
        # 参数位置中的多字节字符不应破坏解析。
        result = parse("echo 'héllo wörld'")
        assert result.has_error is False


class TestParseResultIsImmutable:
    """``ParseResult`` 被冻结，因此消费者无法改变共享状态。"""

    def test_frozen(self):
        result = parse("ls")
        with pytest.raises(FrozenInstanceError):
            result.has_error = True  # type: ignore[misc]


class TestParseAdversarialBytes:
    """锁定异常字节序列的合约。

    这些测试记录了编码（可能会引发）和解析（永远不会通过 ERROR 节点引发和报告错误）之
    间的边界。
    """

    def test_emoji_argument_parses(self):
        # 参数位置中的 4 字节 UTF-8 不得使解析器脱轨。
        result = parse("echo 🚀")
        assert result.has_error is False

    def test_embedded_null_byte_parses_with_error_flag(self):
        # NUL 字节解析（无例外），但语法标记了它们。
        result = parse("echo \x00 hello")
        assert isinstance(result, ParseResult)
        assert result.has_error is True

    def test_lone_surrogate_raises_unicode_encode_error(self):
        # 在树守护者看到输入之前，严格 UTF-8 在编码时拒绝单独的代理。 文档字符串对此进行
        # 了记录。
        #
        with pytest.raises(UnicodeEncodeError):
            parse("echo \ud800 hello")


class TestParseByteSemantics:
    """固定字节偏移语义，以便将来的库升级不会漂移。"""

    def test_root_node_spans_full_input(self):
        command = "echo hello"
        result = parse(command)
        assert result.tree.root_node.start_byte == 0
        assert result.tree.root_node.end_byte == len(command.encode())

    def test_root_node_spans_multibyte_input(self):
        # 多字节字符：end_byte 计算字节，而不是代码点。
        command = "echo 'héllo'"
        result = parse(command)
        assert result.tree.root_node.end_byte == len(command.encode())


class TestParseDeterminism:
    """重复解析相同的输入会返回相同的结果。

    防止任何全局可变状态通过解析器构造或共享 ``_BASH_LANGUAGE`` 单例进入。
    """

    def test_repeated_parse_has_equal_error_flag(self):
        first = parse("echo hello && ls")
        second = parse("echo hello && ls")
        assert first.has_error == second.has_error

    def test_repeated_parse_of_malformed_input_is_stable(self):
        first = parse('echo "unclosed')
        second = parse('echo "unclosed')
        assert first.has_error is True
        assert second.has_error is True
