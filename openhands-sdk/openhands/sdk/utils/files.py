import os
import tempfile
from pathlib import Path
from typing import Final


# 将文件标记为仍在写入的后缀。 ``atomic_write_text`` 写入 ``path`` 旁边的
# ``.<name>.<random>.tmp``，然后将其重命名为 ``<name>``。
#
_TEMP_SUFFIX: Final[str] = ".tmp"


def is_temp_file(path: Path) -> bool:
    """如果 ``path`` 的命名类似于仍在写入的文件，则返回 True。

    这是任何 ``*.tmp`` 名称：``atomic_write_text`` 的临时文件，以及其他编写者对他们重
    命名的文件使用相同后缀的临时文件。
    """
    return path.suffix == _TEMP_SUFFIX


def atomic_write_text(path: Path, value: str, mode: int = 0o600) -> None:
    """使用仅限所有者的权限自动写入文本。"""
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=_TEMP_SUFFIX, dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        fchmod = getattr(os, "fchmod", None)
        if fchmod is None:
            os.chmod(temporary_path, mode)
        else:
            fchmod(fd, mode)
        file = os.fdopen(fd, "w", encoding="utf-8")
        fd = -1
        with file:
            file.write(value)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
