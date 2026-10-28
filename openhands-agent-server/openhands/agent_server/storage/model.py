from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from uuid import UUID


class Tier(IntEnum):
    """停止运行时可能会丢弃什么； 每一层都包括较低层。"""

    # 沙盒主目录中的包缓存（$HOME/.cache、$HOME/.npm）。
    CACHES = 1
    # 工作区中 Git 忽略的目录（node_modules、.venv、构建输出）。
    DEPENDENCIES = 2
    # 整个运行时间； 对话的历史记录和身份都会被保留。
    RUNTIME = 3


@dataclass(frozen=True, slots=True)
class StoredRuntime:
    """该主机上的对话存储，仅限于服务器拥有的内容。"""

    id: UUID
    last_active: float
    # 沙盒自己的$HOME如果有，它就不是主机的。
    home: Path | None = None
    # 工作区服务器已创建； 从来没有来电者提供的结帐。
    workspaces: tuple[Path, ...] = ()
