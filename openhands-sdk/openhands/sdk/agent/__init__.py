from __future__ import annotations

from typing import TYPE_CHECKING

from openhands.sdk.agent.agent import Agent
from openhands.sdk.agent.base import AgentBase


if TYPE_CHECKING:
    from openhands.sdk.agent.acp_agent import ACPAgent


# 懒加载：主动导入 ACPAgent 注册到  DiscriminatedUnionMixin, 这使得 `kind` 必需的智能体
# 载荷那之前就已默认。
#
def __getattr__(name: str):
    if name == "ACPAgent":
        from openhands.sdk.agent.acp_agent import ACPAgent

        return ACPAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Agent",
    "AgentBase",
    "ACPAgent",
]
