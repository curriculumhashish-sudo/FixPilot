"""由 tree-sitter-bash 支持的命令分割和转义实用程序。"""

import re

from tree_sitter import Node

from openhands.sdk.logger import get_logger
from openhands.sdk.security.shell_parser import parse


logger = get_logger(__name__)

# 包含内容原封不动的区域——嵌套的转义字符在边界处停止e.g.) 双引号中的字符串保持不变。 行
# 走不会递归到这些节点。
#
_PRESERVE_TYPES: frozenset[str] = frozenset(
    {
        "string",
        "raw_string",
        "ansi_c_string",
        "translated_string",
        "command_substitution",
        "expansion",
        "simple_expansion",
        "heredoc_body",
        "comment",
    }
)

_ESCAPE_PATTERN: re.Pattern[bytes] = re.compile(rb"\\([;&|<>])")


def _ends_with_heredoc(node: Node) -> bool:
    """``node``的最终token是否是一个heredoc终止符。

    仅检查最后一个 *named* 后代是 ``heredoc_end`` 不是
    enough: 树上的叶子关闭 token，例如 ``fi``、``done`` 和
    ``)`` 未命名，因此复合语句或替换仅
    *contains* 定界符会匹配并吞掉实际结束的换行符
    声明。 要求终止符也到达``node``的末端。
    """
    last = node
    while last.named_children:
        last = last.named_children[-1]
    return last.type == "heredoc_end" and last.end_byte == node.end_byte


def _last_heredoc_is_closed(root: Node) -> bool:
    """不可解析输入中的最终定界符是否已看到其终止符。

    tree-sitter-bash 报告了 bash 自己接受的语法错误（一个引号分隔符，多个命令行的嵌入
    行） ``&`` 在主体之前) 并且可能随后省略
    ``heredoc_end`` 节点，将终止符线留在 ``heredoc_body`` 相反。 将最后一行与分隔符进
    行比较，以区分封闭的定界符和仍在读取的 bash
    。 决定
    from the tree keeps the guard identical on every platform instead of
    取决于 ``bash`` 可执行文件是否存在且正在运行。
    """
    entries: list[tuple[int, str, bytes]] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in ("heredoc_start", "heredoc_body", "heredoc_end"):
            entries.append((node.start_byte, node.type, node.text or b""))
        stack.extend(node.named_children)
    entries.sort()

    start = max(
        (
            index
            for index, (_, kind, _) in enumerate(entries)
            if kind == "heredoc_start"
        ),
        default=None,
    )
    if start is None:
        return False
    delimiter = re.sub(r"['\"]", "", entries[start][2].decode().strip())
    if delimiter.startswith("-"):
        delimiter = delimiter[1:]
    rest = entries[start + 1 :]
    if any(kind == "heredoc_end" for _, kind, _ in rest):
        return True
    bodies = [text for _, kind, text in rest if kind == "heredoc_body"]
    if not bodies:
        return False
    lines = [line for line in bodies[-1].decode().splitlines() if line.strip()]
    return bool(lines) and lines[-1].strip() == delimiter


def needs_heredoc_completion_boundary(commands: str) -> bool:
    """在此输入完全消耗之前，交互式 Bash 是否可以提示词。"""
    source = commands.encode()
    result = parse(commands)
    root = result.tree.root_node
    if result.has_error:
        stack = [root]
        has_heredoc = False
        while stack:
            node = stack.pop()
            has_heredoc = has_heredoc or node.type.startswith("heredoc_")
            stack.extend(node.named_children)
        if not has_heredoc:
            return False
        return _last_heredoc_is_closed(root)

    statements = [child for child in root.named_children if child.type != "comment"]
    return any(
        _ends_with_heredoc(current)
        and b"\n" in source[current.end_byte : following.start_byte]
        for current, following in zip(statements, statements[1:])
    )


def split_bash_commands(commands: str) -> list[str]:
    """将多语句 bash 输入拆分为顶级语句。

    由换行符分隔的语句（有或没有中间空格/注释）将成为单独的条目，除非在完成的定界文档
    之后。 由 ``;``、``&&``、``||``、``|`` 或 ``&`` 连
    接的语句保持在一起。 两个语句之间的注释和空格被折叠到前面的条目中。 解析失败时，
    输入将作为单元素列表返回。
    """
    if not commands.strip():
        return [""]

    source = commands.encode()
    result = parse(commands)
    root = result.tree.root_node

    if result.has_error:
        logger.debug(
            "tree-sitter-bash reported parse errors; returning input as-is\n"
            "[input]: %s",
            commands,
        )
        return [commands]

    statements = [c for c in root.named_children if c.type != "comment"]
    if not statements:
        return [commands]

    boundaries = [statements[0].start_byte]
    for cur, nxt in zip(statements, statements[1:]):
        if b"\n" in source[cur.end_byte : nxt.start_byte] and not _ends_with_heredoc(
            cur
        ):
            boundaries.append(nxt.start_byte)
    boundaries.append(len(source))

    return [source[a:b].decode().rstrip() for a, b in zip(boundaries, boundaries[1:])]


def escape_bash_special_chars(command: str) -> str:
    r"""对 ``\;``、``\&``、``\|``、``\<``、``\>`` 进行双倍转义。

    在区域内的序列（包括单引号和双引号的字符串、命令替换、参数扩展、行内文档体以及注
    释）将被保留原样。 解析失败时，输入将原样返回。
    """
    if command.strip() == "":
        return ""

    source = command.encode()
    result = parse(command)
    if result.has_error:
        logger.debug(
            "tree-sitter-bash reported parse errors; returning input as-is\n"
            "[input]: %s",
            command,
        )
        return command

    preserved: list[tuple[int, int]] = []

    def collect(node: Node) -> None:
        if node.type in _PRESERVE_TYPES:
            preserved.append((node.start_byte, node.end_byte))
            return
        for child in node.children:
            collect(child)

    collect(result.tree.root_node)

    out = bytearray()
    cursor = 0
    for start, end in preserved:
        out.extend(_ESCAPE_PATTERN.sub(rb"\\\\\1", source[cursor:start]))
        out.extend(source[start:end])
        cursor = end
    out.extend(_ESCAPE_PATTERN.sub(rb"\\\\\1", source[cursor:]))

    return out.decode()
