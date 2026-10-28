"""用于安全分析器的共享 AST 支持的 shell 命令语义。

解析针对共享树管理员的命令名称和参数
``_shell_ast`` 视图（问题#2721）。 策略轨道将这些事实重新用于管道、包装器、原始磁盘、
删除和嵌套脚本分析。 模式分析器使用相同的视图进行递归强制删除检测
。 注入和 Python 代码模式在 ``pattern.py`` 中保留为正则表达式，因为它们不是 shell 语
法。

当破坏性命令扫描器无法验证相关结构时，它会报告 ``uncertain``。 然后分析器可以发出
``UNKNOWN`` 而不是 False
``LOW``:

- 破坏性标志形状出现在动词无法解析的命令上；
- 动态参数或不受支持的选项组会阻止安全选择直接执行的 shell 源；
- ERROR/MISSING 解析节点与检测器使用的命令范围相交； 或
- 嵌套运行器深度界限受到仍未扫描的脚本操作数的影响。

这些范围之外的 Shell 解析错误保留为 ``LOW``。 任意非 shell 文本可能包含解析错误，因此
将每个错误映射到 ``UNKNOWN`` 会产生太多不确定的结果
。 探测器 ID 归 ``pattern.py`` 所有，并且未更改地传入。
"""

from __future__ import annotations

import contextlib
import posixpath
from dataclasses import dataclass, replace
from fnmatch import fnmatchcase
from typing import Final

from tree_sitter import Node

from openhands.sdk.security import _shell_ast as ast_view
from openhands.sdk.security._shell_ast import (
    ShellCommand,
    ShellProgram,
    ShellWord,
)


# 脚本操作数是嵌套 shell 程序的命令基本名称。 解析并重新解析该操作数会关闭嵌套运行器绕过
#
# class without hardcoding payloads.
_SHELL_RUNNERS: Final[frozenset[str]] = frozenset(
    {"sh", "bash", "dash", "zsh", "ksh", "ash"}
)

# 递归强制删除命令的基本名称已结构解析。
_RM_BASENAME: Final[str] = "rm"

# 使跑步者的第一个操作数成为脚本的短选项字符。
_SCRIPT_FLAG_CHAR: Final[str] = "c"

# 终止选项解析的选项结束标记 (POSIX)。
_END_OF_OPTIONS: Final[str] = "--"

# 一个单独的破折号：历史上的选项结束同义词 POSIX sh 仍然接受。
_BARE_DASH: Final[str] = "-"

# 将运行程序 argv 单词标记为选项组的前导字符。 POSIX sh 接受 ``-x`` 样式和 ``+x`` 样式组
# 。
#
_OPTION_PREFIXES: Final[frozenset[str]] = frozenset({"-", "+"})

# 使用下一个单词作为参数的运行程序短选项（set -o / shopt -O 名称）。 如果没有这个，
# ``bash -o errexit -c ...`` 会将选项参数误读为第一个操作数并停止查找脚本标志。
#
_SHORT_OPTS_WITH_ARG: Final[frozenset[str]] = frozenset({"o", "O"})

# 运行长选项，将下一个单词作为参数。 无法识别的长选项使命令选择不确定。
#
_LONG_OPTS_WITH_ARG: Final[frozenset[str]] = frozenset({"--rcfile", "--init-file"})

_LONG_OPTS_WITHOUT_ARG: Final[frozenset[str]] = frozenset(
    {
        "--debugger",
        "--login",
        "--noediting",
        "--noprofile",
        "--norc",
        "--posix",
        "--restricted",
        "--verbose",
    }
)

_SHORT_RUNNER_OPTIONS: Final[frozenset[str]] = frozenset("abefhkmnptuvxBCDHPcilrsoO")

# 长标志名称映射到下面的短标志字符上。
_LONG_RECURSIVE: Final[str] = "recursive"
_LONG_FORCE: Final[str] = "force"

# 此分析器无法解析为文字文本的节点类型。 大多数是动态的。 ANSI-C 字符串是静态的，但对其
# 转义语言的解码位于此分析器的有界文字解析器之外。
#
_UNRESOLVED_LITERAL_NODE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "command_substitution",
        "process_substitution",
        "expansion",
        "simple_expansion",
        "arithmetic_expansion",
        "ansi_c_string",
    }
)

# 脚本操作数的嵌套深度有多深。 Bounds 适用于对抗性深度嵌套的跑步者争论； 使用仍未扫描的
# 操作数达到界限会表现为不确定，而不是沉默 LOW。
#
_MAX_NESTING_DEPTH: Final[int] = 8

# 反斜杠在双引号内转义的字符 (POSIX 2.2.3)。 在任何其他字符之前，反斜杠是字面意思，必须
# 保留。
#
_DOUBLE_QUOTE_ESCAPABLE: Final[frozenset[str]] = frozenset('$`"\\')

# 这些未解析的节点类型保留在一个 argv 位置。 下面单独处理引用的 Bash ``@`` 扩展。 其他未
# 解决的形状可能会分裂。
#
_SINGLE_ARGUMENT_UNRESOLVED_NODE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "string",
        "raw_string",
        "ansi_c_string",
        "arithmetic_expansion",
        "process_substitution",
    }
)

_DEFINITE_NON_OPTION_NODE_TYPES: Final[frozenset[str]] = frozenset(
    {"arithmetic_expansion", "process_substitution"}
)

_RM_OPTION_PATTERNS: Final[tuple[tuple[str, frozenset[str]], ...]] = (
    ("-r", frozenset("r")),
    ("-R", frozenset("R")),
    ("-f", frozenset("f")),
    ("-rf", frozenset("rf")),
    ("-fr", frozenset("rf")),
    ("-Rf", frozenset("Rf")),
    ("-fR", frozenset("Rf")),
    ("--recursive", frozenset("r")),
    ("--force", frozenset("f")),
)


@dataclass(frozen=True, slots=True)
class CommandSemantics:
    """一个已解析命令的静态 argv 事实。"""

    basename: str | None
    arguments: tuple[str | None, ...]
    argument_words: tuple[ShellWord, ...]
    uncertain: bool = False
    can_invoke_shell_builtin: bool = True
    can_invoke_shell_keyword: bool = True


@dataclass(frozen=True, slots=True)
class ShellScanResult:
    """AST 支持的 shell 扫描的结果。

    ``detector_id``是``matched``为True时匹配的模式稳定ID，
    else None. ``uncertain`` is True when the scan cannot resolve a relevant
    命令或 shell 运行程序边界，无法信任所需的解析范围，或达到嵌套深度限制。 然后调用
    者发出 ``UNKNOWN`` 而不是 ``LOW``。
    """

    matched: bool
    detector_id: str | None = None
    uncertain: bool = False


@dataclass(frozen=True, slots=True)
class SignalOutput:
    """扫描一个程序或命令以查找破坏性动词的结果。

    一旦递归强制删除被具体解决，``matched``就是True。
    当扫描无法验证破坏性形状或相关的壳-运行边界时，``uncertain`` 为 True。 调用者将其
    转换为 ``UNKNOWN`` 而不是 ``LOW``。

    具体的匹配总是胜过不确定性，因此 ``matched`` 和
    ``uncertain`` 永远不会同时是 True。
    """

    matched: bool
    uncertain: bool


_NO_SIGNAL: Final[SignalOutput] = SignalOutput(matched=False, uncertain=False)
_MATCH_SIGNAL: Final[SignalOutput] = SignalOutput(matched=True, uncertain=False)
_UNCERTAIN_SIGNAL: Final[SignalOutput] = SignalOutput(matched=False, uncertain=True)


def scan_shell_command(command: str, rm_detector_id: str) -> ShellScanResult:
    """扫描 ``command`` 查找 AST 可解析的破坏性 shell 命令。

    通过引号和路径前缀解析每个简单命令名，进入直接执行的 shell 源，并报告递归强制删除
    家族的匹配。

    不确定性的报道范围很窄。 当扫描无法验证破坏性命令、相关shell-runner选项边界、必需
    解析区间或在深度限制之前嵌套的脚本时，它适用。 在每种情况下，调用者都
    会发出 UNKNOWN 而不是 False LOW。 不相关的解析错误仍然存在 LOW。
    """
    program = _safe_parse(command)
    if program is None:
        # 编码失败（e.g. 孤独的代理人）。 正则表达式层已经扫描了扁平化的文本； 既不报告
        # 匹配也不报告不确定性。
        #
        return ShellScanResult(matched=False)

    signal = _program_signal(program, depth=0)
    if signal.matched:
        return ShellScanResult(matched=True, detector_id=rm_detector_id)
    return ShellScanResult(matched=False, uncertain=signal.uncertain)


def _safe_parse(command: str) -> ShellProgram | None:
    with contextlib.suppress(UnicodeEncodeError, ValueError):
        return ast_view.parse_shell_program(command)
    return None


def resolve_command(command: ShellCommand) -> CommandSemantics:
    """解析命令名称及其文字参数。"""
    name_word = command.name
    argument_words = command.words
    if (
        name_word is not None
        and name_word.text.isdecimal()
        and argument_words
        and any(
            name_word.node.end_byte == redirect.start_byte
            for redirect, _ in _command_redirects(command)
        )
    ):
        name_word = argument_words[0]
        argument_words = argument_words[1:]
    name_literal = (
        _resolve_node_literal(name_word.node) if name_word is not None else None
    )
    name_arity_uncertain = name_word is not None and argument_arity_is_uncertain(
        name_literal,
        name_word,
    )
    return CommandSemantics(
        basename=(
            posixpath.basename(name_literal)
            if name_literal is not None and not name_arity_uncertain
            else None
        ),
        arguments=tuple(_resolve_node_literal(word.node) for word in argument_words),
        argument_words=argument_words,
        uncertain=(
            name_word is not None and (name_literal is None or name_arity_uncertain)
        ),
        can_invoke_shell_builtin=(name_literal is not None and "/" not in name_literal),
        can_invoke_shell_keyword=(
            name_literal is not None
            and name_word is not None
            and name_word.text == name_literal
            and "/" not in name_literal
        ),
    )


def has_recursive_force_flags(command: CommandSemantics) -> bool:
    """返回已解析的命令是否具有递归和强制标志。"""
    flags = _collect_literal_flags(command.arguments)
    return ("r" in flags or "R" in flags) and "f" in flags


def static_shell_script(command: CommandSemantics) -> tuple[bool, str | None, bool]:
    """返回 shell 运行程序的脚本和选项边界不确定性。"""
    if not is_shell_runner(command):
        return False, None, False
    assert command.basename is not None
    return _extract_script_operand(
        command.arguments,
        command.argument_words,
        command.basename,
    )


def is_shell_runner(command: CommandSemantics) -> bool:
    """返回命令是否解析为受支持的 shell 运行程序。"""
    return command.basename in _SHELL_RUNNERS


def static_executable_shell_source(
    syntax: ShellCommand,
    command: CommandSemantics,
) -> tuple[bool, str | None, bool]:
    """返回命令直接执行的shell源。"""
    runner_command = _without_redirect_descriptor_words(syntax, command)
    has_script, script, uncertain = static_shell_script(runner_command)
    if has_script or uncertain:
        return has_script, script, uncertain

    eval_command, eval_uncertain = _effective_eval_command(runner_command)
    if eval_uncertain:
        return True, None, True
    if eval_command is not None:
        arguments = eval_command.arguments
        words = eval_command.argument_words
        if arguments and arguments[0] == _END_OF_OPTIONS:
            arguments = arguments[1:]
            words = words[1:]
        elif arguments and arguments[0] is not None and arguments[0].startswith("-"):
            return False, None, False
        if not arguments:
            return False, None, False
        if any(
            argument is None or argument_arity_is_uncertain(argument, word)
            for argument, word in zip(
                arguments,
                words,
                strict=True,
            )
        ):
            return True, None, True
        literal_arguments = [argument for argument in arguments if argument is not None]
        return True, " ".join(literal_arguments), False

    if not is_shell_runner(runner_command):
        return False, None, False
    has_source, source, source_uncertain = _static_standard_input_source(syntax)
    if not has_source:
        return False, None, False
    reads_standard_input = _runner_reads_standard_input(runner_command)
    if reads_standard_input is None:
        return True, None, True
    if not reads_standard_input:
        return False, None, False
    return True, source, source_uncertain


def static_pipeline_output(
    syntax: ShellCommand,
    command: CommandSemantics,
    enclosing_node: Node,
) -> tuple[bool, str | None, bool]:
    """返回命令写入作为下一个管道阶段的输入的输出。"""
    reaches_pipeline = standard_output_reaches_pipeline(syntax, enclosing_node)
    if reaches_pipeline is False:
        return False, None, False
    if reaches_pipeline is None or command.uncertain:
        return True, None, True

    if command.basename == "echo":
        return _static_echo_output(command)
    if command.basename == "printf":
        return _static_printf_output(command)
    if command.basename == "cat" and not command.arguments:
        has_source, source, uncertain = _static_standard_input_source(
            syntax,
            enclosing_node=enclosing_node,
        )
        if has_source:
            return has_source, source, uncertain
    return True, None, True


def static_piped_shell_source(
    syntax: ShellCommand,
    command: CommandSemantics,
    pipeline_source: tuple[bool, str | None, bool],
    enclosing_node: Node,
) -> tuple[bool, str | None, bool]:
    """返回 shell 运行程序作为源执行的管道输入。"""
    if not pipeline_source[0]:
        return False, None, False

    runner_command = _without_redirect_descriptor_words(syntax, command)
    has_script, _, script_uncertain = static_shell_script(runner_command)
    if has_script:
        return False, None, False
    if script_uncertain:
        return True, None, True
    if not is_shell_runner(runner_command):
        return False, None, False

    reads_standard_input = _runner_reads_standard_input(runner_command)
    if reads_standard_input is False:
        return False, None, False

    has_source, source, source_uncertain = static_standard_input_source(
        syntax,
        pipeline_source,
        enclosing_node,
    )
    if not has_source:
        return False, None, False
    if reads_standard_input is None or source_uncertain:
        return True, None, True
    return True, source, False


def static_standard_input_source(
    syntax: ShellCommand,
    initial_source: tuple[bool, str | None, bool],
    enclosing_node: Node,
) -> tuple[bool, str | None, bool]:
    """应用命令重定向后返回标准输入源。"""
    return _static_standard_input_source(
        syntax,
        initial_source,
        enclosing_node,
    )


def _static_echo_output(
    command: CommandSemantics,
) -> tuple[bool, str | None, bool]:
    if any(
        argument is None
        or argument_arity_is_uncertain(argument, word)
        or "\\" in argument
        for argument, word in zip(
            command.arguments,
            command.argument_words,
            strict=True,
        )
    ):
        return True, None, True
    arguments = [argument for argument in command.arguments if argument is not None]
    if arguments and arguments[0].startswith("-"):
        return True, None, True
    return True, " ".join(arguments) + "\n", False


def _static_printf_output(
    command: CommandSemantics,
) -> tuple[bool, str | None, bool]:
    if not command.arguments:
        return True, "", False
    format_index = 1 if command.arguments[0] == _END_OF_OPTIONS else 0
    if format_index >= len(command.arguments):
        return True, "", False
    format_string = command.arguments[format_index]
    if format_string is None or argument_arity_is_uncertain(
        format_string,
        command.argument_words[format_index],
    ):
        return True, None, True
    if format_index == 0 and format_string.startswith("-"):
        return True, None, True
    if "\\" in format_string:
        return True, None, True
    values = [
        (
            argument
            if argument is not None and not argument_arity_is_uncertain(argument, word)
            else None
        )
        for argument, word in zip(
            command.arguments[format_index + 1 :],
            command.argument_words[format_index + 1 :],
            strict=True,
        )
    ]
    output = _render_simple_printf(format_string, values)
    return True, output, output is None


def _render_simple_printf(
    format_string: str,
    values: list[str | None],
) -> str | None:
    output: list[str] = []
    value_index = 0
    consumes_values = False
    index = 0
    while index < len(format_string):
        if format_string[index] != "%":
            output.append(format_string[index])
            index += 1
            continue
        if index + 1 >= len(format_string):
            return None
        conversion = format_string[index + 1]
        if conversion == "%":
            output.append("%")
        elif conversion == "s" and value_index < len(values):
            value = values[value_index]
            if value is None:
                return None
            consumes_values = True
            output.append(value)
            value_index += 1
        else:
            return None
        index += 2
    if consumes_values and value_index != len(values):
        return None
    return "".join(output)


def standard_output_reaches_pipeline(
    command: ShellCommand,
    enclosing_node: Node | None = None,
) -> bool | None:
    """返回命令的标准输出是否仍到达其管道。"""
    pipe_output: dict[str, bool | None] = {"1": True, "2": False}
    for redirect, descriptor in _command_redirects(command, enclosing_node):
        target_fd = _normalize_descriptor(descriptor)
        redirect_text = _decode(redirect.text).lstrip("0123456789")
        if redirect_text.startswith(("&>", "&>>")):
            destination = _redirect_destination(redirect)
            alias = _file_descriptor_alias(destination)
            if alias is not None:
                redirected_output = pipe_output.get(alias, False)
            else:
                redirected_output = None if destination is None else False
            pipe_output["1"] = redirected_output
            pipe_output["2"] = redirected_output
            continue
        if redirect_text.startswith((">&", "<&")):
            destination = _redirect_destination(redirect)
            if destination == "-":
                pipe_output[target_fd] = False
            elif destination is not None and destination.isdecimal():
                pipe_output[target_fd] = pipe_output.get(
                    _normalize_descriptor(destination),
                    False,
                )
            else:
                pipe_output[target_fd] = None
            continue
        destination = _redirect_destination(redirect)
        alias = _file_descriptor_alias(destination)
        if alias is not None:
            pipe_output[target_fd] = pipe_output.get(alias, False)
        else:
            pipe_output[target_fd] = None if destination is None else False
    return pipe_output["1"]


def _effective_eval_command(
    command: CommandSemantics,
) -> tuple[CommandSemantics | None, bool]:
    for depth in range(_MAX_NESTING_DEPTH + 1):
        if not command.can_invoke_shell_builtin:
            return None, False
        if command.basename == "eval":
            return command, False
        if command.basename not in {"builtin", "command"}:
            return None, False
        if depth == _MAX_NESTING_DEPTH:
            return None, True

        index = 0
        if command.basename == "command":
            while index < len(command.arguments) and command.arguments[index] == "-p":
                index += 1
            if (
                index < len(command.arguments)
                and command.arguments[index] == _END_OF_OPTIONS
            ):
                index += 1
        elif command.arguments and command.arguments[0] == _END_OF_OPTIONS:
            index = 1
        if index >= len(command.arguments):
            return None, False

        target = command.arguments[index]
        target_word = command.argument_words[index]
        if target is None or argument_arity_is_uncertain(target, target_word):
            return None, True
        if target.startswith("-") or "/" in target:
            return None, False
        command = replace(
            command,
            basename=target,
            arguments=command.arguments[index + 1 :],
            argument_words=command.argument_words[index + 1 :],
            can_invoke_shell_keyword=False,
        )
    return None, True


def argument_arity_is_uncertain(
    literal: str | None,
    word: ShellWord,
) -> bool:
    """返回一个源单词是否可以改变 argv 单词的数量。"""
    if literal is not None:
        return _contains_unquoted_arity_syntax(word.text)
    return _node_arity_is_uncertain(word.node)


def static_word_prefix(word: ShellWord) -> str:
    """返回 shell 单词中第一个动态节点之前的文字前缀。"""
    prefix, _ = _static_node_prefix(word.node)
    return prefix


def _static_node_prefix(node: Node) -> tuple[str, bool]:
    if node.type in _UNRESOLVED_LITERAL_NODE_TYPES:
        return "", False
    if node.type in {"string", "command_name", "concatenation"}:
        parts: list[str] = []
        for child in node.named_children:
            prefix, complete = _static_node_prefix(child)
            parts.append(prefix)
            if not complete:
                return "".join(parts), False
        return "".join(parts), True
    literal = _resolve_node_literal(node)
    return (literal, True) if literal is not None else ("", False)


def _node_arity_is_uncertain(node: Node) -> bool:
    if node.type == "string":
        return _contains_multi_argument_expansion(node)
    if node.type in _SINGLE_ARGUMENT_UNRESOLVED_NODE_TYPES or node.type in {
        "word",
        "number",
    }:
        return False
    if node.type == "concatenation":
        return _contains_unquoted_arity_syntax(_decode(node.text)) or any(
            _node_arity_is_uncertain(child) for child in node.named_children
        )
    return True


def _contains_multi_argument_expansion(node: Node) -> bool:
    if node.type in {"expansion", "simple_expansion"}:
        if any(
            child.type == "special_variable_name" and _decode(child.text) == "@"
            for child in node.named_children
        ):
            return True
        if node.type == "expansion":
            subscript = next(
                (child for child in node.named_children if child.type == "subscript"),
                None,
            )
            if subscript is not None:
                index = subscript.child_by_field_name("index")
                if index is not None and _decode(index.text) == "@":
                    return True
            child_types = [child.type for child in node.children]
            if "!" in child_types and child_types[-2:] == ["@", "}"]:
                return True
    return any(
        _contains_multi_argument_expansion(child) for child in node.named_children
    )


def _contains_unquoted_arity_syntax(text: str) -> bool:
    """检测一个 shell 单词中不带引号的路径名和大括号扩展语法。"""
    return any(_unquoted_expansion_syntax(text))


def _unquoted_expansion_syntax(text: str) -> tuple[bool, bool]:
    """返回单词是否包含路径名或大括号扩展语法。"""
    bracket_open = False
    brace_expands: list[bool] = []
    pathname_expands = False
    has_brace_expansion = False
    quote: str | None = None
    index = 0
    while index < len(text):
        character = text[index]
        if quote == "'":
            if character == quote:
                quote = None
            index += 1
            continue
        if quote == '"':
            if (
                character == "\\"
                and index + 1 < len(text)
                and (
                    text[index + 1] in _DOUBLE_QUOTE_ESCAPABLE
                    or text[index + 1] == "\n"
                )
            ):
                index += 2
                continue
            if character == quote:
                quote = None
            index += 1
            continue
        if character == "\\":
            index += 2
            continue
        if character in {"'", '"'}:
            quote = character
        elif character in {"*", "?"}:
            pathname_expands = True
        elif character == "[":
            bracket_open = True
        elif character == "]" and bracket_open:
            pathname_expands = True
            bracket_open = False
        elif character == "{":
            brace_expands.append(False)
        elif character == "}" and brace_expands:
            if brace_expands.pop():
                has_brace_expansion = True
        elif brace_expands and (character == "," or text.startswith("..", index)):
            brace_expands[-1] = True
        index += 1
    return pathname_expands, has_brace_expansion


def _program_signal(program: ShellProgram, depth: int) -> SignalOutput:
    """返回已解析程序的扫描信号。

    当递归强制删除解决时，``matched`` 为 True。 当相关命令、标志形状、解析范围或嵌套
    执行边界无法静态解析时，``uncertain`` 为 True。
    """
    uncertain = False
    for command in ast_view.iter_commands(program):
        resolved = resolve_command(command)
        if has_recursive_force_flags(resolved):
            if resolved.basename == _RM_BASENAME:
                return _MATCH_SIGNAL
            if resolved.basename is None or command.has_error:
                # 在我们无法担保的危险动词形状上：要么名称不可解析，要么ERROR/MISSING解
                # 析节点与该命令重叠，因此解析后的动词可能不是shell将运行的动词。 首先继
                # 续扫描具体的匹配。
                #
                uncertain = True
        elif resolved.basename == _RM_BASENAME and _has_uncertain_recursive_force_flags(
            resolved
        ):
            uncertain = True
        nested = _nested_signal(command, resolved, depth)
        if nested.matched:
            return _MATCH_SIGNAL
        uncertain = uncertain or nested.uncertain
    return SignalOutput(matched=False, uncertain=uncertain)


def _collect_literal_flags(arguments: tuple[str | None, ...]) -> set[str]:
    """收集短标志字符并识别长标志。

    选项词通过与命令名称相同的引号删除路径来解析。 POSIX 引号删除使 ``rm "-rf" /`` 和
     ``rm -r"f" /`` argv 与
    ``rm -rf /`` 相同，因此将带引号的选项词视为不透明
    ——因此无标志——会让同样的灾难性删除通过
    在不同的拼写下，而取消引号的动词仍然解析为
    ``rm``. 解决动词而不是其选项是使绕过成为可能的不对称性。

    未解析的单词不会添加文字标记。 单独的检查标记它们不确定何时可以扩展到递归和强制标
    志。

    结束选项标志终止了标志解析，并且它还与脱引号的字面量进行比较——在 ``rm "--"`` 之后
    ，shell 真正将一个跟随的 ``-rf`` 视为一个文件名。 长
    标志被映射到它们的短标志字符上，以便排序和混合工作。
    """
    flags: set[str] = set()
    for literal in arguments:
        if literal is None:
            continue
        if literal == _END_OF_OPTIONS:
            break
        flags |= ast_view.split_short_flags(literal)
        if ast_view.is_long_flag(literal, _LONG_RECURSIVE):
            flags.add("r")
        elif ast_view.is_long_flag(literal, _LONG_FORCE):
            flags.add("f")
    return flags


def _has_uncertain_recursive_force_flags(command: CommandSemantics) -> bool:
    flags = _collect_literal_flags(command.arguments)
    for literal, word in zip(
        command.arguments,
        command.argument_words,
        strict=True,
    ):
        if literal == _END_OF_OPTIONS:
            break
        if literal is None or not argument_arity_is_uncertain(literal, word):
            continue
        pathname_expands, brace_expands = _unquoted_expansion_syntax(word.text)
        brace_can_start_option, brace_flags = _leading_brace_option_flags(literal)
        can_start_option = (
            literal.startswith("-")
            or (pathname_expands and _pathname_can_start_option(word.text))
            or (brace_expands and brace_can_start_option)
        )
        if pathname_expands and can_start_option:
            flags.update(_pathname_option_flags(literal))
        elif literal.startswith("-"):
            flags.update(character for character in literal if character in "rRf")
        elif brace_expands:
            flags.update(brace_flags)
    return ("r" in flags or "R" in flags) and "f" in flags


def _pathname_can_start_option(text: str) -> bool:
    quote: str | None = None
    index = 0
    while index < len(text):
        character = text[index]
        if quote is not None:
            if character == quote:
                quote = None
                index += 1
                continue
            return character == "-"
        if character == "\\" and index + 1 < len(text):
            return text[index + 1] == "-"
        if character in {"'", '"'}:
            quote = character
            index += 1
            continue
        return character in {"-", "*", "?", "["}
    return False


def _pathname_option_flags(pattern: str) -> set[str]:
    if pattern.startswith("-"):
        return set("rRf")
    if "[^" in pattern or "[[:" in pattern:
        return set("rRf")
    flags: set[str] = set()
    for option, option_flags in _RM_OPTION_PATTERNS:
        if fnmatchcase(option, pattern):
            flags.update(option_flags)
    return flags


def _leading_brace_option_flags(
    literal: str,
    recursion_depth: int = 0,
) -> tuple[bool, set[str]]:
    if not literal.startswith("{"):
        return False, set()
    if recursion_depth >= _MAX_NESTING_DEPTH:
        return "-" in literal, {
            character for character in literal if character in "rRf"
        }
    brace_depth = 0
    for index, character in enumerate(literal[1:], start=1):
        if character == "{":
            brace_depth += 1
        elif character == "}":
            if brace_depth == 0:
                alternatives = literal[1:index]
                suffix = literal[index + 1 :]
                return _brace_option_flags(
                    alternatives,
                    suffix,
                    recursion_depth,
                )
            brace_depth -= 1
    return False, set()


def _brace_option_flags(
    alternatives: str,
    suffix: str,
    recursion_depth: int,
) -> tuple[bool, set[str]]:
    can_start_option = False
    flags: set[str] = set()
    brace_depth = 0
    start = 0
    for index in range(len(alternatives) + 1):
        character = alternatives[index] if index < len(alternatives) else ","
        if character == "{":
            brace_depth += 1
        elif character == "}":
            brace_depth -= 1
        elif character == "," and brace_depth == 0:
            candidate = alternatives[start:index] + suffix
            if candidate.startswith("-"):
                can_start_option = True
                flags.update(character for character in candidate if character in "rRf")
            elif candidate.startswith("{"):
                nested_can_start, nested_flags = _leading_brace_option_flags(
                    candidate,
                    recursion_depth + 1,
                )
                can_start_option = can_start_option or nested_can_start
                flags.update(nested_flags)
            start = index + 1
    return can_start_option, flags


def _nested_signal(
    command: ShellCommand,
    resolved: CommandSemantics,
    depth: int,
) -> SignalOutput:
    """深入到直接执行的 shell 源代码并重新解析它。

    关闭嵌套运行器旁路类，包括脚本内外部模式看不到的带引号的动词。

    故障安全排序：首先运行操作数扫描，因此具体匹配始终获胜； 仅当未找到匹配项时，源命
    令节点上的解析错误才会强制不确定性 - 那里存在 ERROR/MISSING (
    e.g. 一个未闭合的引号截断了脚本参数，这意味着 argv 跨越刚刚读取的扫描无法信任，因
    此一个无声的 LOW 会证明从未见过的东西。
    """
    source_command = is_shell_runner(resolved) or resolved.basename in {
        "eval",
        "builtin",
        "command",
    }
    has_script, inner, uncertain = static_executable_shell_source(command, resolved)
    if has_script and inner is not None:
        if depth >= _MAX_NESTING_DEPTH:
            return _UNCERTAIN_SIGNAL
        inner_program = _safe_parse(inner)
        if inner_program is not None:
            nested = _program_signal(inner_program, depth + 1)
            if nested.matched:
                return _MATCH_SIGNAL
            if nested.uncertain:
                return _UNCERTAIN_SIGNAL
    if uncertain:
        return _UNCERTAIN_SIGNAL
    if source_command and command.has_error:
        return _UNCERTAIN_SIGNAL
    return _NO_SIGNAL


def _runner_reads_standard_input(command: CommandSemantics) -> bool | None:
    stdin_selected = False
    noexec = False
    dump_strings = False
    options_ended = False
    index = 0
    while index < len(command.arguments):
        literal = command.arguments[index]
        word = command.argument_words[index]
        if literal is None or argument_arity_is_uncertain(literal, word):
            if options_ended:
                return (
                    False
                    if noexec or dump_strings
                    else (True if stdin_selected else None)
                )
            return None
        if not options_ended:
            if literal in {_END_OF_OPTIONS, _BARE_DASH}:
                options_ended = True
                index += 1
                continue
            if _is_option_word(literal):
                if _is_definitely_invalid_option_word(literal):
                    return False
                value_count = _runner_option_value_count(literal, command.basename)
                if value_count is None:
                    return None
                stdin_selected = stdin_selected or _sets_stdin_flag(literal)
                noexec = _updated_noexec(noexec, literal)
                dump_strings = dump_strings or _sets_dump_strings(
                    command.basename,
                    literal,
                )
                if value_count and index + value_count >= len(command.arguments):
                    return False
                index += value_count + 1
                continue
        return False if noexec or dump_strings else stdin_selected
    return not (noexec or dump_strings)


def _static_standard_input_source(
    command: ShellCommand,
    initial_source: tuple[bool, str | None, bool] = (False, None, False),
    enclosing_node: Node | None = None,
) -> tuple[bool, str | None, bool]:
    sources = {"0": initial_source} if initial_source[0] else {}
    for redirect, descriptor in _command_redirects(command, enclosing_node):
        target_fd = _normalize_descriptor(descriptor)
        redirect_text = _decode(redirect.text).lstrip("0123456789")
        if redirect_text.startswith(("<&", ">&")):
            destination = _redirect_destination(redirect)
            if destination == "-":
                sources.pop(target_fd, None)
                continue
            if destination is not None and destination.isdecimal():
                source_fd = _normalize_descriptor(destination)
                if source_fd in sources:
                    sources[target_fd] = sources[source_fd]
                else:
                    sources.pop(target_fd, None)
                continue
            if target_fd == "0" or sources:
                sources[target_fd] = (True, None, True)
            continue
        if redirect_text.startswith(("&>", "&>>")):
            destination = _redirect_destination(redirect)
            alias = _file_descriptor_alias(destination)
            if alias is not None and alias in sources:
                sources["1"] = sources[alias]
                sources["2"] = sources[alias]
            elif destination is None and sources:
                sources["1"] = (True, None, True)
                sources["2"] = (True, None, True)
            else:
                sources.pop("1", None)
                sources.pop("2", None)
            continue
        if _is_herestring_redirect(redirect, redirect_text):
            sources[target_fd] = _static_herestring_source(redirect)
            continue
        if redirect.type == "heredoc_redirect":
            sources[target_fd] = _static_heredoc_source(redirect)
            continue
        destination = _redirect_destination(redirect)
        alias = _file_descriptor_alias(destination)
        if alias is not None and alias in sources:
            sources[target_fd] = sources[alias]
        elif destination is None and (target_fd == "0" or sources):
            sources[target_fd] = (True, None, True)
        else:
            sources.pop(target_fd, None)
    return sources.get("0", (False, None, False))


def _static_herestring_source(redirect: Node) -> tuple[bool, str | None, bool]:
    values = [
        child
        for child in redirect.named_children
        if child.type not in {"file_descriptor", "ERROR"}
        and "redirect" not in child.type
    ]
    if not values:
        return True, None, True
    source = _resolve_node_literal(values[0])
    return True, source, source is None


def _is_herestring_redirect(redirect: Node, text: str) -> bool:
    if redirect.type == "herestring_redirect" or text.startswith("<<<"):
        return True
    previous = redirect.prev_named_sibling
    return (
        previous is not None
        and previous.type == "ERROR"
        and previous.end_byte == redirect.start_byte
        and _decode(previous.text) == "<<"
        and text.startswith("<")
    )


def _redirect_destination(redirect: Node) -> str | None:
    for index, child in enumerate(redirect.children):
        if child.is_named and redirect.field_name_for_child(index) == "destination":
            return _resolve_node_literal(child)
    return None


def _file_descriptor_alias(path: str | None) -> str | None:
    aliases = {
        "/dev/stdin": "0",
        "/dev/stdout": "1",
        "/dev/stderr": "2",
    }
    if path in aliases:
        return aliases[path]
    if path is None:
        return None
    for prefix in ("/dev/fd/", "/proc/self/fd/"):
        descriptor = path.removeprefix(prefix)
        if descriptor != path and descriptor.isdecimal():
            return _normalize_descriptor(descriptor)
    return None


def _normalize_descriptor(descriptor: str) -> str:
    if descriptor.isdecimal():
        return str(int(descriptor))
    return descriptor


def _static_heredoc_source(redirect: Node) -> tuple[bool, str | None, bool]:
    start = next(
        (child for child in redirect.named_children if child.type == "heredoc_start"),
        None,
    )
    body = next(
        (child for child in redirect.named_children if child.type == "heredoc_body"),
        None,
    )
    end = next(
        (child for child in redirect.named_children if child.type == "heredoc_end"),
        None,
    )
    if start is None or body is None or end is None:
        return True, None, True

    body_text = _decode(body.text)
    delimiter_is_quoted = _decode(start.text) != _decode(end.text)
    if not delimiter_is_quoted and (body.named_children or "\\" in body_text):
        return True, None, True
    return True, body_text, False


def _without_redirect_descriptor_words(
    syntax: ShellCommand,
    command: CommandSemantics,
) -> CommandSemantics:
    redirects = _command_redirects(syntax)
    retained = [
        (argument, word)
        for argument, word in zip(
            command.arguments,
            command.argument_words,
            strict=True,
        )
        if not (
            argument is not None
            and argument.isdecimal()
            and word.text.isdecimal()
            and _is_redirect_descriptor_word(argument, word, redirects)
        )
    ]
    if len(retained) == len(command.arguments):
        return command
    return replace(
        command,
        arguments=tuple(argument for argument, _ in retained),
        argument_words=tuple(word for _, word in retained),
    )


def _is_redirect_descriptor_word(
    argument: str,
    word: ShellWord,
    redirects: list[tuple[Node, str]],
) -> bool:
    for redirect, descriptor in redirects:
        if _normalize_descriptor(argument) != _normalize_descriptor(descriptor):
            continue
        if word.node.end_byte == redirect.start_byte:
            return True
        previous = redirect.prev_named_sibling
        if (
            previous is not None
            and previous.type == "ERROR"
            and _decode(previous.text) == "<<"
            and word.node.end_byte == previous.start_byte
            and previous.end_byte == redirect.start_byte
        ):
            return True
    return False


def _command_redirects(
    command: ShellCommand,
    enclosing_node: Node | None = None,
) -> list[tuple[Node, str]]:
    redirects: list[tuple[Node, str]] = []
    container = command.node
    reached_enclosing_node = enclosing_node is None
    while True:
        for child in container.named_children:
            if "redirect" in child.type and child.type != "redirected_statement":
                _append_redirect_tree(redirects, command, child)
        if container == enclosing_node:
            reached_enclosing_node = True
        parent = container.parent
        if not reached_enclosing_node and parent is not None:
            container = parent
            continue
        if parent is not None and parent.type == "redirected_statement":
            container = parent
            continue
        if (
            parent is not None
            and parent.type == "pipeline"
            and parent.named_children
            and parent.named_children[-1] == container
        ):
            container = parent
            continue
        break

    parent = command.node.parent
    sibling = parent.next_named_sibling if parent is not None else None
    if parent is not None and parent.type == "ERROR" and sibling is not None:
        descriptor = _adjacent_trailing_descriptor(command, parent, sibling)
        if descriptor is not None:
            for child in parent.named_children:
                if "redirect" in child.type:
                    _append_redirect_tree(redirects, command, child)
            for child in sibling.named_children:
                if "redirect" in child.type:
                    _append_redirect_tree(redirects, command, child, descriptor)

    redirects.sort(key=lambda item: item[0].start_byte)
    return redirects


def _adjacent_trailing_descriptor(
    command: ShellCommand,
    parent: Node,
    sibling: Node,
) -> str | None:
    if sibling.start_byte != parent.end_byte:
        return None
    suffix = (parent.text or b"")[command.node.end_byte - parent.start_byte :]
    fields = suffix.rsplit(maxsplit=1)
    if not fields or not fields[-1].isdigit():
        return None
    return fields[-1].decode()


def _append_redirect_tree(
    redirects: list[tuple[Node, str]],
    command: ShellCommand,
    redirect: Node,
    descriptor: str | None = None,
) -> None:
    for index, nested in enumerate(ast_view.iter_redirect_nodes(redirect)):
        nested_descriptor = (
            descriptor
            if index == 0 and descriptor is not None
            else _redirect_descriptor(command, nested)
        )
        redirects.append((nested, nested_descriptor))


def _redirect_descriptor(command: ShellCommand, redirect: Node) -> str:
    text = _decode(redirect.text).lstrip()
    descriptor_length = len(text) - len(text.lstrip("0123456789"))
    if descriptor_length:
        return text[:descriptor_length]
    previous = redirect.prev_named_sibling
    if previous is not None and previous.end_byte == redirect.start_byte:
        fields = (previous.text or b"").rsplit(maxsplit=1)
        if fields and fields[-1].isdigit():
            return fields[-1].decode()
    for word in command.words:
        if word.node.end_byte == redirect.start_byte and word.text.isdecimal():
            return word.text
    return "0" if text[descriptor_length:].startswith("<") else "1"


def _extract_script_operand(
    arguments: tuple[str | None, ...],
    argument_words: tuple[ShellWord, ...],
    basename: str,
) -> tuple[bool, str | None, bool]:
    """使用支持的 shell 选项规则找到运行程序脚本操作数。

    短选项组合在一起，因此脚本标志在组中的任何位置都计数（``-xc``，``-cx``）。 支持的
    参数获取选项会在下一个单词位于其组中的最后一个单词时使用该单词。 其
    他安置仍不确定。
    ``--``（或历史上的单独的``-``）终止选项解析。 然后第一个操作数结束选项列表。 设置
    脚本标志后，该操作数就是脚本。 如果没有它，该操作数就是一个脚本文件。
     后面的标志属于脚本，不得触发嵌套扫描。

    返回 ``(has_flag, operand, uncertain)``。 当动态字或不受支持的选项组阻止安全选择
    脚本操作数时，``uncertain`` 为 T
    rue。
    """
    has_script_flag = False
    noexec = False
    dump_strings = False
    options_ended = False
    index = 0
    while index < len(arguments):
        literal = arguments[index]
        word = argument_words[index]
        if argument_arity_is_uncertain(literal, word):
            if options_ended and (noexec or dump_strings):
                return False, None, False
            if options_ended and not has_script_flag:
                return False, None, False
            return has_script_flag, None, True
        if literal is None:
            if has_script_flag:
                return (
                    (False, None, False)
                    if noexec or dump_strings
                    else (True, None, False)
                )
            if options_ended:
                return False, None, False
            if word.node_type in _DEFINITE_NON_OPTION_NODE_TYPES:
                return False, None, False
            return False, None, index + 1 < len(arguments)
        if not options_ended:
            if literal == _END_OF_OPTIONS or literal == _BARE_DASH:
                options_ended = True
                index += 1
                continue
            if _is_option_word(literal):
                if _is_definitely_invalid_option_word(literal):
                    return False, None, False
                value_count = _runner_option_value_count(literal, basename)
                if value_count is None:
                    return has_script_flag, None, True
                if _sets_script_flag(literal):
                    has_script_flag = True
                noexec = _updated_noexec(noexec, literal)
                dump_strings = dump_strings or _sets_dump_strings(basename, literal)
                if value_count:
                    value_index = index + 1
                    if value_index >= len(arguments):
                        return False, None, False
                    if (
                        argument_words[value_index].node_type
                        in _DEFINITE_NON_OPTION_NODE_TYPES
                        or argument_arity_is_uncertain(
                            arguments[value_index],
                            argument_words[value_index],
                        )
                    ):
                        return has_script_flag, None, True
                index += value_count + 1
                continue
        # 到达第一个操作数。
        if has_script_flag:
            return (
                (False, None, False)
                if noexec or dump_strings
                else (True, literal, False)
            )
        return False, None, False
    return (
        (False, None, False)
        if noexec or dump_strings
        else (has_script_flag, None, False)
    )


def _is_option_word(literal: str) -> bool:
    """返回已解析的 argv 单词是否是选项组。"""
    return len(literal) > 1 and literal[0] in _OPTION_PREFIXES


def _sets_script_flag(literal: str) -> bool:
    """返回短选项组是否包含脚本标志。

    单个 ``-`` 或 ``+`` 前缀启动一个短选项组。 重复的前缀则不然。
    """
    return _is_short_option_group(literal) and _SCRIPT_FLAG_CHAR in literal[1:]


def _is_short_option_group(literal: str) -> bool:
    return (
        len(literal) > 1
        and literal[0] in _OPTION_PREFIXES
        and literal[1] not in _OPTION_PREFIXES
    )


def _sets_stdin_flag(literal: str) -> bool:
    return _is_short_option_group(literal) and literal[0] == "-" and "s" in literal[1:]


def _updated_noexec(current: bool, literal: str) -> bool:
    if not _is_short_option_group(literal) or "n" not in literal[1:]:
        return current
    return literal.startswith("-")


def _sets_dump_strings(basename: str | None, literal: str) -> bool:
    return basename == "bash" and _is_short_option_group(literal) and "D" in literal[1:]


def _runner_option_value_count(literal: str, basename: str | None) -> int | None:
    if literal.startswith(_END_OF_OPTIONS) and basename != "bash":
        return None
    if literal in _LONG_OPTS_WITH_ARG:
        return 1
    if literal in _LONG_OPTS_WITHOUT_ARG:
        return 0
    if literal.startswith(_END_OF_OPTIONS):
        return None
    flags = literal[1:]
    if basename != "bash" and "D" in flags:
        return None
    if any(flag not in _SHORT_RUNNER_OPTIONS for flag in flags):
        return None
    if any(flag in _SHORT_OPTS_WITH_ARG for flag in flags[:-1]):
        return None
    return int(flags[-1] in _SHORT_OPTS_WITH_ARG)


def _is_definitely_invalid_option_word(literal: str) -> bool:
    return literal.startswith(("++", "-+", "+-"))


def _resolve_node_literal(node: Node) -> str | None:
    """连接文字文本，或在无法解析时返回 None。

    遍历 tree-sitter-bash 为命令名称和参数生成的串联/字符串/raw_string/单词结构。 动
    态或不受支持的子项（包括 ANSI-C 字符串）会生
    成 None。
    """
    parts = _collect_literal_parts(node)
    if parts is None:
        return None
    return "".join(parts)


def _collect_literal_parts(node: Node) -> list[str] | None:
    """当无法解析节点时返回文字片段或 None。

    None 表示子树不可静态解析。 片段被转义字符化为在去掉引号后产生的有效字面量：tree-
    sitter保留了 ``word`` 中的反斜杠转义字符
    ``string_content`` 文本，因此比较原始文本会让 ``r\\m``（shell 作为 ``rm`` 运行）
    溜过基本名称检查。
    """
    if node.type in _UNRESOLVED_LITERAL_NODE_TYPES:
        return None

    match node.type:
        case "word" | "number":
            return [_unescape_unquoted(_decode(node.text))]

        case "raw_string":
            # 单引号操作数：去掉引号； 内容是字面意思，单引号内的反斜杠没有特殊含义。
            #
            text = _decode(node.text)
            return [text[1:-1] if len(text) >= 2 else ""]

        case "string_content":
            return [_unescape_double_quoted(_decode(node.text))]

        # “string”是双引号的情况：递归将嵌入的扩展捕获为动态，而 string_content 片段按字
        # 面意思贡献。 command_name 和串联递归出于同样的原因，因此所有三个共享一个分支。
        #
        case "string" | "command_name" | "concatenation":
            parts: list[str] = []
            for child in node.named_children:
                child_parts = _collect_literal_parts(child)
                if child_parts is None:
                    return None
                parts.extend(child_parts)
            return parts

        # 名称位置中的未知/未处理的节点类型：视为动态，因此我们永远不会伪造我们不确定的
        # 已解析名称。
        #
        case _:
            return None


def _unescape_unquoted(text: str) -> str:
    """去掉未加引号的单词中的反斜杠转义符 (POSIX 2.2.1)。

    引号外的反斜杠生成下一个字符文字，因此有效值会删除反斜杠 (``r\\m`` -> ``rm``)；
    反斜杠-换行对是行延续并完全消失。
    """
    return _strip_backslash_escapes(text, escapable=None)


def _unescape_double_quoted(text: str) -> str:
    """去掉转义双引号（POSIX 2.2.3）。

    双引号内的反斜杠仅转义 ``$``, `````, ``"``,
    ``\\`` 和换行符； 在任何其他字符之前，反斜杠本身就是文字，必须保留（``"r\\m"`` 保
    留为 ``r\\m``）。
    """
    return _strip_backslash_escapes(text, escapable=_DOUBLE_QUOTE_ESCAPABLE)


def _strip_backslash_escapes(text: str, escapable: frozenset[str] | None) -> str:
    """返回 ``text``，并将反斜杠转义简化为其文字。

    ``escapable`` 是尊重转义的字符集，或者 None 尊重每个字符。 反斜杠换行始终是行延续
    并且不会产生任何结果。 保留尾随的单独反斜杠。
    """
    parts: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\\" and index + 1 < length:
            follower = text[index + 1]
            if follower == "\n":
                index += 2
                continue
            if escapable is None or follower in escapable:
                parts.append(follower)
                index += 2
                continue
        parts.append(char)
        index += 1
    return "".join(parts)


def _decode(raw: bytes | None) -> str:
    return raw.decode() if raw is not None else ""
