"""用于安全分析器的私有 tree-sitter-bash 命令视图。"""

from __future__ import annotations

import posixpath
from collections.abc import Iterator
from dataclasses import dataclass, field

from tree_sitter import Node

from openhands.sdk.security.shell_parser import ParseResult, parse


_OPAQUE_WORD_CHARS = frozenset("\"'`\\$*?[]{}()<>|&;!~")
_COMMAND_CHILD_SKIP_TYPES = frozenset(
    {
        "command_name",
        "comment",
        "file_redirect",
        "heredoc_redirect",
        "herestring_redirect",
        "redirected_statement",
        "variable_assignment",
    }
)


@dataclass(frozen=True, slots=True)
class ShellProgram:
    """解析的 shell 源加上它来自的树守护者解析结果。"""

    source: str
    source_bytes: bytes
    parse_result: ParseResult = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class ShellWord:
    """带有原始 shell 语法文本的命令字或赋值。"""

    text: str
    node_type: str
    opaque: bool
    node: Node = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class ShellCommand:
    """一个简单的命令，包括其命令名称和参数字。"""

    name: ShellWord | None
    words: tuple[ShellWord, ...]
    assignments: tuple[ShellWord, ...]
    node: Node = field(repr=False, compare=False)
    has_error: bool = False


@dataclass(frozen=True, slots=True)
class ShellPipeline:
    """由 shell 管道运算符连接的简单命令的管道。"""

    commands: tuple[ShellCommand, ...]
    complete: bool
    node: Node = field(repr=False, compare=False)
    has_error: bool = False


def parse_shell_program(source: str) -> ShellProgram:
    """解析 ``source`` 并返回其私有 shell 语法视图。"""
    return view_shell_program(source, parse(source))


def view_shell_program(source: str, parse_result: ParseResult) -> ShellProgram:
    """从匹配的解析结果创建 shell 语法视图。

    解析树必须跨越 ``source`` 的 UTF-8 字节长度。 如果调用者传递与解析文本不同的相同
    长度源，则字节切片将反映该调用者错误； 这个助手故意不保留已解析
    字节的第二个副本来检测它。
    """
    source_bytes = source.encode()
    if parse_result.tree.root_node.end_byte != len(source_bytes):
        raise ValueError("parse result does not match source byte length")
    return ShellProgram(
        source=source,
        source_bytes=source_bytes,
        parse_result=parse_result,
    )


def node_text(program: ShellProgram, node: Node) -> str:
    """使用树托管字节偏移量返回 ``node`` 文本。"""
    return program.source_bytes[node.start_byte : node.end_byte].decode()


def iter_commands(program: ShellProgram) -> Iterator[ShellCommand]:
    """从解析的 shell 语法树中生成真实的 ``command`` 节点。"""
    for node in _iter_nodes(program.parse_result.tree.root_node):
        if node.type == "command":
            yield _view_command(program, node)


def iter_pipelines(program: ShellProgram) -> Iterator[ShellPipeline]:
    """生成树托管者 ``pipeline`` 节点的管道视图。"""
    for node in _iter_nodes(program.parse_result.tree.root_node):
        if node.type == "pipeline":
            yield _view_pipeline(program, node)


def command_basename(command: ShellCommand) -> str | None:
    """返回非不透明命令名称的 POSIX 基本名称。"""
    if command.name is None or command.name.opaque:
        return None
    return posixpath.basename(command.name.text)


def split_short_flags(text: str) -> frozenset[str]:
    """将短标志词的文字文本拆分为单独的标志字符。

    采用 shell 在删除引号后生成的文字而不是 ``ShellWord``，因此解析引号的调用者会得到
    相同的答案
    ``-rf``、``"-rf"`` 和 ``-r"f"``——它们是相同的 argv。 无法解析单词的调用者必须跳过
    它而不是传递其原始源文本。
    """
    if len(text) <= 1 or not text.startswith("-") or text.startswith("--"):
        return frozenset()
    return frozenset(text[1:])


def is_long_flag(text: str, name: str) -> bool:
    """返回单词的文字文本是否恰好为 ``--<name>``。"""
    return text == f"--{name}"


def split_key_value_word(word: ShellWord) -> tuple[str, str] | None:
    """分割一个透明的 ``KEY=VALUE`` 单词。"""
    if word.opaque:
        return None

    key, separator, value = word.text.partition("=")
    if not separator or not key:
        return None
    return key, value


def _view_pipeline(program: ShellProgram, node: Node) -> ShellPipeline:
    commands: list[ShellCommand] = []
    complete = True
    for child in node.named_children:
        command_node = _unwrap_redirected_command(child)
        if command_node is None:
            complete = False
            continue
        commands.append(_view_command(program, command_node))

    return ShellPipeline(
        commands=tuple(commands),
        complete=complete and bool(commands),
        node=node,
        has_error=_has_parse_uncertainty(node),
    )


def _view_command(program: ShellProgram, node: Node) -> ShellCommand:
    name: ShellWord | None = None
    words: list[ShellWord] = []
    assignments: list[ShellWord] = []
    found_name = False

    for child in node.named_children:
        if child.type == "command_name":
            name = _command_name_word(program, child)
            found_name = True
            continue

        if child.type == "variable_assignment" and not found_name:
            assignments.append(_shell_word(program, child))
            continue

        if not found_name or child.type in _COMMAND_CHILD_SKIP_TYPES:
            continue

        if "redirect" in child.type:
            continue

        words.append(_shell_word(program, child))

    redirects = _enclosing_redirects(node)
    redirect_starts = {
        nested.start_byte
        for redirect in redirects
        for nested in iter_redirect_nodes(redirect)
    }
    for redirect in redirects:
        words.extend(
            _shell_word(program, argument)
            for argument in _redirect_argument_nodes(
                program,
                redirect,
                redirect_starts,
            )
        )
    words.sort(key=lambda word: word.node.start_byte)

    return ShellCommand(
        name=name,
        words=tuple(words),
        assignments=tuple(assignments),
        node=node,
        has_error=_has_parse_uncertainty(node),
    )


def _enclosing_redirects(node: Node) -> tuple[Node, ...]:
    redirects: list[Node] = []
    container = node
    while (
        container.parent is not None and container.parent.type == "redirected_statement"
    ):
        container = container.parent
        redirects.extend(
            child for child in container.named_children if "redirect" in child.type
        )
    return tuple(redirects)


def _redirect_argument_nodes(
    program: ShellProgram,
    redirect: Node,
    redirect_starts: set[int],
) -> Iterator[Node]:
    destination_seen = False
    for index, child in enumerate(redirect.children):
        if not child.is_named:
            continue
        field = redirect.field_name_for_child(index)
        if field == "argument":
            yield child
        elif field == "destination":
            if destination_seen and not (
                node_text(program, child).isdecimal()
                and child.end_byte in redirect_starts
            ):
                yield child
            destination_seen = True
        elif field == "redirect":
            yield from _redirect_argument_nodes(program, child, redirect_starts)


def iter_redirect_nodes(redirect: Node) -> Iterator[Node]:
    """产生一个重定向及其嵌套的重定向节点。"""
    yield redirect
    for index, child in enumerate(redirect.children):
        if child.is_named and redirect.field_name_for_child(index) == "redirect":
            yield from iter_redirect_nodes(child)


def _command_name_word(program: ShellProgram, node: Node) -> ShellWord:
    text = node_text(program, node)
    named_children = node.named_children
    opaque = (
        len(named_children) != 1
        or named_children[0].type != "word"
        or _text_has_opaque_syntax(text)
    )
    return ShellWord(
        text=text,
        node_type=node.type,
        opaque=opaque,
        node=node,
    )


def _shell_word(program: ShellProgram, node: Node) -> ShellWord:
    text = node_text(program, node)
    return ShellWord(
        text=text,
        node_type=node.type,
        opaque=_is_opaque_word_node(node, text),
        node=node,
    )


def _is_opaque_word_node(node: Node, text: str) -> bool:
    if _text_has_opaque_syntax(text):
        return True

    if node.type == "word":
        return False

    if node.type == "variable_assignment":
        return any(
            child.type not in {"variable_name", "word"} for child in node.named_children
        )

    return True


def _text_has_opaque_syntax(text: str) -> bool:
    return not text or any(
        character.isspace() or character in _OPAQUE_WORD_CHARS for character in text
    )


def _has_parse_uncertainty(node: Node) -> bool:
    return node.has_error or _has_missing_descendant(node)


def _has_missing_descendant(node: Node) -> bool:
    if node.is_missing:
        return True
    return any(_has_missing_descendant(child) for child in node.children)


def _unwrap_redirected_command(node: Node) -> Node | None:
    current = node
    while current.type == "redirected_statement":
        command_children = [
            child for child in current.named_children if child.type == "command"
        ]
        if len(command_children) != 1:
            return None
        current = command_children[0]

    if current.type == "command":
        return current
    return None


def _iter_nodes(node: Node) -> Iterator[Node]:
    if node.is_named:
        yield node
    for child in node.children:
        yield from _iter_nodes(child)
