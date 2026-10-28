import re
from re import Pattern


_EXTENSION_NAME_PATTERN: Pattern[str] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_extension_name(name: str) -> None:
    """验证 *name* 是短横线大小写 (``^[a-z0-9]+(-[a-z0-9]+)*$``)。

    Raises:
        ValueError: 如果 *name* 与模式不匹配。
    """
    if not _EXTENSION_NAME_PATTERN.fullmatch(name):
        raise ValueError(f"Invalid extension name. Expected kebab-case, got {name!r}.")
