"""已序列化和面向显示的路径字符串的路径助手。"""

from __future__ import annotations

import logging
import os
import re
from contextlib import suppress
from functools import cache
from pathlib import Path, PureWindowsPath


logger = logging.getLogger(__name__)

_URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")

# 相对 OH_PERSISTENCE_DIR 的锚点：捕获一次，以便在进程中某些 chdirs 时状态树无法移动。
#
_INITIAL_CWD = Path.cwd()


@cache
def _warn_relative_persistence_dir(env_dir: str) -> None:
    """每个不同的相对值警告一次； 每次查找时都会调用此方法。"""
    logger.warning(
        "OH_PERSISTENCE_DIR=%r is relative; anchoring it to %s. Set an absolute path.",
        env_dir,
        _INITIAL_CWD,
    )


def get_user_persistence_dir(default: Path | None = None) -> Path:
    """返回用户级别 OpenHands 持久化的基目录。

    尊重 ``OH_PERSISTENCE_DIR``  环境变量当设置（用于 ephemeral/isolated sandboxes 重
    定向状态到持久卷）时，否则返
    回 ``default``, 或 ``~/.openhands`` when no ``default`` 已给出。
    ``OH_PERSISTENCE_DIR``
    替换 ``~/.openhands`` 基础目录； callers append their usual subdirectories (e.g.
    ``profiles``,
    ``cache/skills``) 到结果。

    ``OH_PERSISTENCE_DIR`` 预计是绝对的。 相对值受到尊重，但锚定到导入此模块的工作目
    录，因此后面的 ``chdir`` 无法跨调用站点拆分状态树
    。

    将结果存储在模块级常量中的调用站点将其冻结在
    import time, so ``OH_PERSISTENCE_DIR`` must be set before ``openhands.sdk``
    是进口的； 只有呼叫时间呼叫站点才会接收稍后的更改。
    """
    env_dir = os.environ.get("OH_PERSISTENCE_DIR")
    if env_dir:
        resolved = Path(env_dir).expanduser()
        if not resolved.is_absolute():
            _warn_relative_persistence_dir(env_dir)
            resolved = _INITIAL_CWD / resolved
        return resolved
    if default is not None:
        return default
    return Path.home() / ".openhands"


def resolves_within(path: Path, root: Path) -> bool:
    """``path`` 是否在已解析的 ``root`` 内解析。

    符号链接可以指向 ``root`` 下的任何位置，但不能指向其外部。 无法解析的路径（Python
     3.12 上引发符号链接循环）被视为外部路径。
    """
    with suppress(OSError, RuntimeError):
        if path.resolve().is_relative_to(root.resolve()):
            return True
    logger.warning(f"Denying {path}: it resolves outside {root}")
    return False


def to_posix_path(path: str | os.PathLike[str]) -> str:
    """返回线路/存储/显示格式的斜杠分隔的路径字符串。

    这故意不解析或验证路径。 使用 ``Path`` 或
    ``os.path`` 与本地文件系统交互时直接进行。
    """

    return os.fspath(path).replace("\\", "/")


def posix_path_name(path: str | os.PathLike[str]) -> str:
    """从斜杠标准化路径字符串返回最终名称。"""

    normalized = to_posix_path(path).rstrip("/")
    return normalized.rsplit("/", 1)[-1] if normalized else ""


def is_absolute_path_source(path: str | os.PathLike[str]) -> bool:
    """返回 ``path`` 在 POSIX 或 Windows 语法中是否是绝对的。"""

    value = os.fspath(path).strip()
    if not value:
        return False
    if value.startswith(("/", "\\")):
        return True
    if Path(value).expanduser().is_absolute():
        return True
    return PureWindowsPath(value).is_absolute()


def is_host_absolute_path(path: str | os.PathLike[str]) -> bool:
    """返回 ``path`` 对于当前主机文件系统是否是绝对的。"""

    value = os.fspath(path).strip()
    if not value:
        return False
    return Path(value).expanduser().is_absolute()


def is_local_path_source(source: str) -> bool:
    """返回插件/技能源是否应被视为本地。

    此端点接受明确定义的本地路径语法，例如 ``file://`` URLs，家目录相对路径，任何以点
    开头的相对路径 (``.``，``..``)
    ``.openhands``)、主机本机绝对路径、Windows 绝对路径以及反斜杠分隔的路径（当它们与
     URL 不同时）。
    """

    value = source.strip()
    if not value:
        return False
    if value.startswith(("file://", "~", ".")):
        return True
    if is_absolute_path_source(value):
        return True
    return "\\" in value and _URL_SCHEME_RE.match(value) is None
