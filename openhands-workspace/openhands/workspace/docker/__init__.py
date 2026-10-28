"""Docker 工作区实施。"""

from typing import TYPE_CHECKING

from .workspace import DockerWorkspace


if TYPE_CHECKING:
    from .dev_workspace import DockerDevWorkspace

__all__ = ["DockerWorkspace", "DockerDevWorkspace"]


def __getattr__(name: str):
    """延迟导入 DockerDevWorkspace 以避免构建模块导入。"""
    if name == "DockerDevWorkspace":
        from .dev_workspace import DockerDevWorkspace

        return DockerDevWorkspace
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
