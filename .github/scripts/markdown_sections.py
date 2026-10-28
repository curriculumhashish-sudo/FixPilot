"""用于解析 GitHub 问题和 PR 主体中的 Markdown 部分的帮助程序。"""

import re
from dataclasses import dataclass


# CommonMark 允许开区间包含前导缩进，并且在列表项中，缩进是从列表的内容列而不是左边缘测
# 量的。 不要解析列表，而是接受起始栅栏上的任何缩进并相对于它绑定关闭栅栏（如下）。
#
FENCE_LINE_RE = re.compile(
    r"^(?P<indent>[ ]*)(?P<marker>`{3,}|~{3,})(?P<rest>[^\r\n]*)"
)

# CommonMark 让关闭的栅栏比它关闭的栅栏距离远三格； 除此之外，它是内容，而不是终结者。
#
MAX_CLOSING_INDENT_OFFSET = 3


def _mask_line(line: str) -> str:
    """替换行内容，同时保留偏移量和行结尾。"""
    return "".join(char if char in "\r\n" else " " for char in line)


@dataclass(frozen=True)
class _Fence:
    """用于打开受隔离的 Markdown 代码块的标记。"""

    char: str
    length: int
    indent: int

    @classmethod
    def opened_by(cls, line: str) -> "_Fence | None":
        """返回由 ``line`` 打开的栅栏（如果有）。"""
        match = FENCE_LINE_RE.match(line)
        if match is None:
            return None
        marker = match.group("marker")
        return cls(
            char=marker[0],
            length=len(marker),
            indent=len(match.group("indent")),
        )

    def closed_by(self, line: str) -> bool:
        """返回 ``line`` 是否关闭此栅栏。"""
        match = FENCE_LINE_RE.match(line)
        if match is None:
            return False
        marker = match.group("marker")
        return (
            marker[0] == self.char
            and len(marker) >= self.length
            and len(match.group("indent")) <= self.indent + MAX_CLOSING_INDENT_OFFSET
            and not match.group("rest").strip()
        )


def without_fenced_code_blocks(body: str) -> str:
    """屏蔽屏蔽代码块而不更改字符偏移量。

    永不关闭的栅栏就不会受到影响。 CommonMark 会一直读到文档的末尾，但这些解析器会贡
    献：在粘贴的日志中有一个孤立的标记就会遮盖掉之后的所有标题，并且拒绝报告
    ，因为其部分明显存在。 仅掩盖平衡的栅栏可以使失败保持在接受的一方。
    """
    masked_lines: list[str] = []
    fenced_lines: list[str] = []
    fence: _Fence | None = None

    for line in body.splitlines(keepends=True):
        if fence is None:
            fence = _Fence.opened_by(line)
            if fence is None:
                masked_lines.append(line)
            else:
                fenced_lines.append(line)
        else:
            fenced_lines.append(line)
            if fence.closed_by(line):
                masked_lines.extend(_mask_line(text) for text in fenced_lines)
                fenced_lines.clear()
                fence = None

    # 剩下的东西都属于未封闭的栅栏，所以它保持原样。
    masked_lines.extend(fenced_lines)

    return "".join(masked_lines)


def find_headings(body: str, heading_re: re.Pattern[str]) -> list[re.Match[str]]:
    """返回标题与受保护的代码块外部匹配。"""
    return list(heading_re.finditer(without_fenced_code_blocks(body)))
