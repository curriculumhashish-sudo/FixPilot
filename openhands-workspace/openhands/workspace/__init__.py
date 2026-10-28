"""OpenHands 工作区 - Docker 和基于容器的工作区实现。"""

from typing import TYPE_CHECKING

from openhands.sdk.workspace import PlatformType, TargetType

from .agent_sandbox import AgentSandboxWorkspace
from .apptainer import ApptainerWorkspace
from .cloud import (
    CloneResult,
    GitProvider,
    OpenHandsCloudWorkspace,
    RepoMapping,
    RepoSource,
)
from .docker import DockerWorkspace
from .remote_api import APIRemoteWorkspace


if TYPE_CHECKING:
    from .docker import DockerDevWorkspace

__all__ = [
    "APIRemoteWorkspace",
    "AgentSandboxWorkspace",
    "ApptainerWorkspace",
    "CloneResult",
    "DockerDevWorkspace",
    "DockerWorkspace",
    "GitProvider",
    "OpenHandsCloudWorkspace",
    "PlatformType",
    "RepoMapping",
    "RepoSource",
    "TargetType",
]


def __getattr__(name: str):
    """延迟导入 DockerDevWorkspace 以避免构建模块导入。"""
    if name == "DockerDevWorkspace":
        from .docker import DockerDevWorkspace

        return DockerDevWorkspace
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
