"""子智能体 OpenHands Agent Server 的路由器。

一次读取端点列出了工作区可用的基于文件的内置子智能体（镜像 ``skills_router`` 的
``POST /skills``）。 否 CRUD：目录是被发现的，而不
是突变的。 命名为 ``sub_agents`` 以将这些委托智能体与顶级智能体和 ``agent_profiles``
区分开来。
"""

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from openhands.agent_server.config import Config
from openhands.agent_server.launch import configured_browser_available
from openhands.sdk.context.condenser import CondenserBase
from openhands.sdk.hooks.config import HookConfig
from openhands.sdk.mcp.config import MCPServer
from openhands.sdk.subagent import (
    AgentDefinition,
    AgentDefinitionLevel,
    discover_agents,
)
from openhands.tools.preset.default import discover_builtin_agents


sub_agents_router = APIRouter(prefix="/sub-agents", tags=["Sub Agents"])


class SubAgentsRequest(BaseModel):
    """请求正文列出子智能体。"""

    load_user: bool = Field(
        default=True,
        description="Load user agents from ~/.agents/agents and ~/.openhands/agents",
    )
    load_project: bool = Field(
        default=True,
        description="Load project agents from the workspace",
    )
    load_builtin: bool = Field(
        default=True,
        description="Load SDK built-in agents (general-purpose, code-explorer, ...)",
    )
    project_dir: str | None = Field(
        default=None,
        description="Workspace directory path for project agents",
    )


class SubAgentInfo(BaseModel):
    """API 返回的 ``AgentDefinition`` 的无损视图。

    每个前置元数据字段加上发现的 ``level``/``source``，一个
    ``is_builtin`` 标志和内联 ``system_prompt``（Markdown 主体），因此详细视图不需要
    额外的获取。
    """

    name: str
    description: str = ""
    model: str = "inherit"
    color: str | None = None
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    system_prompt: str = ""
    when_to_use_examples: list[str] = Field(default_factory=list)
    permission_mode: str | None = None
    max_iteration_per_run: int | None = None
    max_budget_per_run: float | None = None
    mcp_config: dict[str, MCPServer] | None = Field(
        default=None,
        description=(
            "MCP servers the definition declares. A delegated sub-agent ignores "
            "them and inherits its parent's MCP servers."
        ),
    )
    mcp_servers: dict[str, MCPServer] | None = Field(
        default=None,
        deprecated=True,
        description=(
            "Deprecated compatibility alias for mcp_config. "
            "Use mcp_config for new clients."
        ),
    )
    profile_store_dir: str | None = None
    hooks: HookConfig | None = None
    condenser: CondenserBase | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    level: AgentDefinitionLevel | None = None
    source: str | None = None
    is_builtin: bool = False

    @classmethod
    def from_definition(cls, agent_def: AgentDefinition) -> "SubAgentInfo":
        return cls(
            name=agent_def.name,
            description=agent_def.description,
            model=agent_def.model,
            color=agent_def.color,
            tools=agent_def.tools,
            skills=agent_def.skills,
            system_prompt=agent_def.system_prompt,
            when_to_use_examples=agent_def.when_to_use_examples,
            permission_mode=agent_def.permission_mode,
            max_iteration_per_run=agent_def.max_iteration_per_run,
            max_budget_per_run=agent_def.max_budget_per_run,
            mcp_config=agent_def.mcp_config,
            mcp_servers=agent_def.mcp_config,
            profile_store_dir=agent_def.profile_store_dir,
            hooks=agent_def.hooks,
            condenser=agent_def.condenser,
            metadata=agent_def.metadata,
            level=agent_def.level,
            source=agent_def.source,
            is_builtin=agent_def.level == "builtin",
        )


class SubAgentsResponse(BaseModel):
    """响应包含所有可用的子智能体。"""

    agents: list[SubAgentInfo]


@sub_agents_router.post("", response_model=SubAgentsResponse)
def get_sub_agents(
    request: SubAgentsRequest, http_request: Request
) -> SubAgentsResponse:
    """列表基于文件且内置子智能体为工作区。

    按名称合并优先项目 > 用户 > 内置。 只读：它没有在会话注册表中注册任何内容。 当服
    务器的配置禁用浏览器时，仅浏览器内置的插件将被排除。
    """
    discovered = discover_agents(
        project_dir=request.project_dir,
        include_project=request.load_project,
        include_user=request.load_user,
    )
    config: Config = http_request.app.state.config
    builtins = (
        discover_builtin_agents(
            enable_browser=configured_browser_available(config) is not False
        )
        if request.load_builtin
        else []
    )

    # 项目 > 用户（来自 discover_agents）> 内置：名称冲突时先胜。
    seen_names: set[str] = set()
    agents: list[SubAgentInfo] = []
    for agent_def in (*discovered, *builtins):
        if agent_def.name in seen_names:
            continue
        seen_names.add(agent_def.name)
        agents.append(SubAgentInfo.from_definition(agent_def))

    return SubAgentsResponse(agents=agents)
