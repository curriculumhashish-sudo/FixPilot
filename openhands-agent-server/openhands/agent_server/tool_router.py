"""OpenHands SDK 的工具刳刨机。"""

import asyncio

from fastapi import APIRouter, Request
from pydantic import BaseModel

# 仅在智能体-服务器中注册：该工具需要服务器来创建子级，因此故意不在 get_default_tools()
# 中。
#
import openhands.tools.child_conversation  # noqa: E402, F401
from openhands.agent_server.config import Config
from openhands.agent_server.launch import (
    can_probe_tools,
    configured_browser_available,
)
from openhands.sdk.tool import BROWSER_TOOL_NAME
from openhands.sdk.tool.registry import (
    ToolCatalogEntry,
    list_registered_tools,
    list_tool_catalog,
)
from openhands.tools.preset.default import (
    register_builtins_agents,
    register_default_tools,
)
from openhands.tools.preset.gemini import register_gemini_tools
from openhands.tools.preset.planning import register_planning_tools


tool_router = APIRouter(prefix="/tools", tags=["Tools"])
register_default_tools(enable_browser=True)
register_builtins_agents(enable_browser=True)
register_gemini_tools(enable_browser=True)
register_planning_tools()


# 工具清单
@tool_router.get("/")
async def list_available_tools() -> list[str]:
    """列出所有可用的工具。"""
    tools = list_registered_tools()
    return tools


class ToolCatalogResponse(BaseModel):
    tools: list[ToolCatalogEntry]


@tool_router.get("/catalog")
async def get_tool_catalog(request: Request) -> ToolCatalogResponse:
    """列出该服务器提供的用于配置智能体的工具。

    客户提供``user_selectable``条目； ``usable`` 表示运行时对话是否可以运行该工具。
    """
    config: Config = request.app.state.config
    entries = await asyncio.to_thread(
        list_tool_catalog, check_usable=can_probe_tools(config)
    )
    browser = configured_browser_available(config)
    if browser is not None:
        entries = [
            entry.model_copy(update={"usable": browser})
            if entry.name == BROWSER_TOOL_NAME
            else entry
            for entry in entries
        ]
    return ToolCatalogResponse(tools=entries)
