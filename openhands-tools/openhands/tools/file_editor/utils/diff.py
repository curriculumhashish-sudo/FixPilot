from difflib import SequenceMatcher

from pydantic import BaseModel
from rich.text import Text


class EditGroup(BaseModel):
    before_edits: list[str]
    after_edits: list[str]


def get_edit_groups(
    old_content: str | None, new_content: str | None, n_context_lines: int = 2
) -> list[EditGroup]:
    """获取显示新旧内容之间更改的编辑组。

    Args:
        n_context_lines: 每次更改周围显示的上下文行数。

    Returns:
        编辑组列表，其中每个组包含编辑前/后的内容。
    """
    if old_content is None or new_content is None:
        return []
    old_lines = old_content.split("\n")
    new_lines = new_content.split("\n")
    # 借用difflib.unified_diff直接解析成结构化格式
    edit_groups: list[EditGroup] = []
    for group in SequenceMatcher(None, old_lines, new_lines).get_grouped_opcodes(
        n_context_lines
    ):
        # 取组内最大行数
        _indent_pad_size = len(str(group[-1][3])) + 1  # +1 表示“*”前缀
        cur_group: EditGroup = EditGroup(
            before_edits=[],
            after_edits=[],
        )
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for idx, line in enumerate(old_lines[i1:i2]):
                    line_num = i1 + idx + 1
                    cur_group.before_edits.append(
                        f"{line_num:>{_indent_pad_size}}|{line}"
                    )
                for idx, line in enumerate(new_lines[j1:j2]):
                    line_num = j1 + idx + 1
                    cur_group.after_edits.append(
                        f"{line_num:>{_indent_pad_size}}|{line}"
                    )
                continue
            if tag in {"replace", "delete"}:
                for idx, line in enumerate(old_lines[i1:i2]):
                    line_num = i1 + idx + 1
                    cur_group.before_edits.append(
                        f"-{line_num:>{_indent_pad_size - 1}}|{line}"
                    )
            if tag in {"replace", "insert"}:
                for idx, line in enumerate(new_lines[j1:j2]):
                    line_num = j1 + idx + 1
                    cur_group.after_edits.append(
                        f"+{line_num:>{_indent_pad_size - 1}}|{line}"
                    )
        edit_groups.append(cur_group)
    return edit_groups


def visualize_diff(
    path: str,
    old_content: str | None,
    new_content: str | None,
    n_context_lines: int = 2,
    change_applied: bool = True,
) -> Text:
    """可视化字符串替换编辑的差异。

    此函数不是逐行显示差异，而是将每个更改块显示为单独的实体。

    Args:
        n_context_lines: 显示更改之前/之后的上下文行数。
        change_applied: 是否应用更改。 如果False，则显示为
            尝试编辑。

    Returns:
        包含格式化差异可视化的字符串。
    """
    content = Text()
    # 检查是否有变化
    if change_applied and old_content == new_content:
        msg = "(no changes detected. Please make sure your edits change "
        msg += "the content of the existing file.)\n"
        content.append(msg, style="bold red")
        return content

    if old_content is None:
        # 创建一个新文件
        old_content = ""
    assert new_content is not None, "new_content cannot be None"
    edit_groups = get_edit_groups(
        old_content, new_content, n_context_lines=n_context_lines
    )

    if change_applied:
        header = f"[File {path} edited with "
        header += f"{len(edit_groups)} changes.]\n"
    else:
        header = f"[Changes are NOT applied to {path} - Here's how "
        header += "the file looks like if changes are applied.]\n"

    content.append(header, style="bold" if change_applied else "bold yellow")

    op_type = "edit" if change_applied else "ATTEMPTED edit"
    for i, cur_edit_group in enumerate(edit_groups):
        if i != 0:
            content.append("\n-------------------------\n")
        content.append(f"[begin of {op_type} {i + 1} / {len(edit_groups)}]\n")
        content.append(f"(content before {op_type})\n")
        for line in cur_edit_group.before_edits:
            content.append(line + "\n", style="red")
        content.append(f"(content after {op_type})\n")
        for line in cur_edit_group.after_edits:
            content.append(line + "\n", style="green")
        content.append(f"[end of {op_type} {i + 1} / {len(edit_groups)}]", style="bold")
    return content
