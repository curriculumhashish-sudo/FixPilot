"""用于截断文本内容的实用函数。"""

import hashlib
from pathlib import Path

from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

# 默认截断限制
DEFAULT_TEXT_CONTENT_LIMIT = 50_000

# 默认截断通知
DEFAULT_TRUNCATE_NOTICE = (
    "<response clipped><NOTE>Due to the max output limit, only part of the full "
    "response has been shown to you.</NOTE>"
)  # 113 个字符

DEFAULT_TRUNCATE_NOTICE_WITH_PERSIST = (
    "<response clipped><NOTE>Due to the max output limit, only part of the full "
    "response has been shown to you. The complete output has been saved to "
    "{file_path} - you can use other tools to view the full content (truncated "
    "part starts around line {line_num}).</NOTE>"
)


def _save_full_content(content: str, save_dir: str, tool_prefix: str) -> str | None:
    """将完整内容保存到指定目录并返回文件路径。"""

    save_dir_path = Path(save_dir)
    save_dir_path.mkdir(parents=True, exist_ok=True)

    # 生成基于哈希的文件名以进行重复数据删除
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    filename = f"{tool_prefix}_output_{content_hash}.txt"
    file_path = save_dir_path / filename

    # 仅当文件不存在时才写入（重复数据删除）
    if not file_path.exists():
        try:
            file_path.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.debug(f"Failed to save full content to {file_path}: {e}")
            return None

    return str(file_path)


def maybe_truncate(
    content: str,
    truncate_after: int | None = None,
    truncate_notice: str = DEFAULT_TRUNCATE_NOTICE,
    save_dir: str | None = None,
    tool_prefix: str = "output",
) -> str:
    """
    如果内容超过指定长度，则截断内容的中间部分。

    保留内容的头部和尾部，两端保留上下文。 （可选）将完整内容保存到文件中以供以后调查
    。

    Args:
        content: 可能被截断的文本内容
        truncate_after: 截断前的最大长度。 如果None，则不发生截断
        truncate_notice: 注意内容被截断时要在中间插入
        save_dir: 工作目录将完整内容文件保存在
        tool_prefix: 保存文件的前缀（e.g.、“bash”、“浏览器”、“编辑器”）

    Returns:
        原始内容（如果低于限制）或截断的内容，保留头部和尾部并引用已保存的文件（如果
        适用）
    """
    # 1) 提前退出：不要求截断，或内容已在限制范围内
    if not truncate_after or len(content) <= truncate_after or truncate_after < 0:
        return content

    # 2) 如果连基本通知都不适合，则返回其中的一部分
    if len(truncate_notice) >= truncate_after:
        return truncate_notice[:truncate_after]

    # 3) 根据基本通知计算建议的头部尺寸
    # （为了一致的行号计算）
    available_chars = truncate_after - len(truncate_notice)
    # 更喜欢将“额外”字符赋予头部（ceil split）
    proposed_head = available_chars // 2 + (available_chars % 2)

    # 4) （可选）保存完整内容，然后构建最终通知
    final_notice = truncate_notice
    if save_dir:
        saved_file_path = _save_full_content(content, save_dir, tool_prefix)
        if saved_file_path:
            # 计算发生截断的行号（使用 head_chars）
            head_content_lines = len(content[:proposed_head].splitlines())

            final_notice = DEFAULT_TRUNCATE_NOTICE_WITH_PERSIST.format(
                file_path=saved_file_path,
                line_num=head_content_lines + 1,  # +1 表示下一行
            )

    # 5) 如果最终通知（带有持久化信息）单独填写
    # 预算，返回一部分
    if len(final_notice) >= truncate_after:
        return final_notice[:truncate_after]

    # 6) 将剩余预算分配给头/尾
    remaining = truncate_after - len(final_notice)
    head_chars = min(proposed_head, remaining)  # 确保 head_chars 不超过剩余
    tail_chars = remaining - head_chars  # 由于之前的检查结果为非负值

    return (
        content[:head_chars]
        + final_notice
        + (content[-tail_chars:] if tail_chars > 0 else "")
    )
