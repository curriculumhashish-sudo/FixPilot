"""GitHub 集成的实用函数。"""

import re


# 零宽度连接符 (U+200D) 我们使用 ZWJ 而不是 ZWSP (U+200B)，因为：
# - ZWJ 在语义上更合适（连接字符而不添加空格）
# - ZWJ 在现代渲染器中有更好的支持
# - ZWJ 不可见，不影响文本渲染或选择
ZWJ = "\u200d"


def sanitize_openhands_mentions(text: str) -> str:
    """清理文本中的 @OpenHands 提及，以防止自我提及循环。

    该函数在 @ 符号后面插入一个零宽度连接符 (ZWJ)
    @OpenHands mentions, making them non-clickable in GitHub comments while
    保持可读性。 提及的原始情况被保留。

    Args:
        text: 要清理的文本

    Returns:
        带有经过净化处理的@OpenHands的文本提及（e.g., "@OpenHands" -> "@‍OpenHands"）

    Examples:
        >>> sanitize_openhands_mentions("Thanks @OpenHands for the help!")
        “感谢@\\u200dOpenHands 的帮助！”
        >>> sanitize_openhands_mentions("Check @openhands and @OPENHANDS")
        '检查@\\u200dopenhands 和@\\u200dOPENHANDS'
        >>> sanitize_openhands_mentions("No mention here")
        “这里没有提及”
    """
    # 与单词边界处提及的 @OpenHands 匹配的模式使用 re.IGNORECASE，因此我们不需要 [Oo]pen
    # [Hh] 并且捕获组保留原始大小写
    #
    pattern = r"@(OpenHands)\b"

    # 将 @ 替换为 @ + ZWJ，同时保留原始大小写 \1 反向引用保留匹配的大小写
    #
    sanitized = re.sub(pattern, f"@{ZWJ}\\1", text, flags=re.IGNORECASE)

    return sanitized
