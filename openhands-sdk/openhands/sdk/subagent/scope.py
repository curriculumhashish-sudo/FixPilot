"""通过委托给它的智能体来绑定子智能体。

子智能体始终与其父级的 MCP 服务器 (:func:`inherit_mcp_config`) 一起运行。 :class:
`SubAgentScope` 还可以将其工具保
留在父级的工具中。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict, Field

from openhands.sdk.logger import get_logger
from openhands.sdk.subagent.schema import AgentDefinition
from openhands.sdk.tool.defaults import (
    SUB_AGENT_TOOL_NAME,
    canonical_tool_name,
    effective_builtin_class,
)
from openhands.sdk.tool.registry import registered_tool_class
from openhands.sdk.tool.spec import Tool


if TYPE_CHECKING:
    from openhands.sdk.agent.base import AgentBase


logger = get_logger(__name__)

SUB_AGENT_SCOPE_PARAM: Final = "sub_agent_scope"

DELEGATION_TOOL_NAMES: Final = (SUB_AGENT_TOOL_NAME, "workflow_tool_set", "workflow")
"""启动子智能体并采用 ``sub_agent_scope`` 参数的工具。"""


class SubAgentScope(BaseModel):
    """子智能体必须留在委托智能体的哪个工具中。

    MCP 服务器不属于该范围：每个子智能体都准确继承委托智能体的 MCP 服务器（请参阅：
    func:`inherit_mcp_config`）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tools: bool = False
    mcp_servers: bool = Field(
        default=False,
        exclude=True,
        deprecated=True,
        description=(
            "Deprecated and ignored: sub-agents always inherit the delegating "
            "agent's MCP servers. Still accepted so stored tool params load."
        ),
    )

    @property
    def restricts(self) -> bool:
        return self.tools

    def missing_from(
        self, parent: AgentBase, sub_agent: AgentBase | AgentDefinition
    ) -> list[str]:
        """返回 ``sub_agent`` 使用 ``parent`` 缺少的工具（如果有范围）。

        对话本地工具永远不会起作用：它们无法到达子智能体自己的对话之外的任何内容。
        """
        if not self.tools:
            return []
        return sorted(
            name
            for name in _tool_names(sub_agent) - _tool_names(parent)
            if not _conversation_local(name)
        )


def inherit_mcp_config[AgentT: AgentBase](
    parent: AgentBase, sub_agent: AgentT
) -> AgentT:
    """返回 ``sub_agent`` 和 ``parent`` 的 MCP 个服务器。

    ``parent`` 是委托会话的智能体，其 ``mcp_config`` 已解决（插件服务器合并，
    ``${VAR}`` 机密扩展）。 子智能体声明自己的服务器已被
    删除，从未合并。
    """
    declared = sub_agent.mcp_config
    if declared and declared != parent.mcp_config:
        logger.info(
            "Ignoring the sub-agent's own MCP servers (%s); it inherits its "
            "parent's (%s)",
            ", ".join(sorted(declared)),
            ", ".join(sorted(parent.mcp_config)) or "none",
        )
    return sub_agent.model_copy(update={"mcp_config": dict(parent.mcp_config)})


def scope_delegation_tools(tools: Sequence[Tool], scope: SubAgentScope) -> list[Tool]:
    """返回 ``tools``，并将 ``scope`` 添加到每个委托工具。"""
    if not scope.restricts:
        return list(tools)
    return [
        _narrowed(tool, scope)
        if canonical_tool_name(tool.name) in DELEGATION_TOOL_NAMES
        else tool
        for tool in tools
    ]


def _narrowed(tool: Tool, scope: SubAgentScope) -> Tool:
    current = SubAgentScope.model_validate(tool.params.get(SUB_AGENT_SCOPE_PARAM) or {})
    merged = SubAgentScope(tools=scope.tools or current.tools)
    return tool.model_copy(
        update={"params": {**tool.params, SUB_AGENT_SCOPE_PARAM: merged.model_dump()}}
    )


def _tool_names(agent: AgentBase | AgentDefinition) -> set[str]:
    if isinstance(agent, AgentDefinition):
        names = list(agent.tools)
    else:
        names = [*(tool.name for tool in agent.tools), *agent.include_default_tools]
    return {canonical_tool_name(name) for name in names}


def _conversation_local(name: str) -> bool:
    tool_class = registered_tool_class(name) or effective_builtin_class(name)
    return tool_class is not None and tool_class.conversation_local
