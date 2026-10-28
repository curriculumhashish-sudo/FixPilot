"""用于子智能体 MCP 继承测试的 Stdio MCP 服务器。

Usage: ``python mcp_echo_server.py TOOL_NAME [STARTED_MARKER]``. 它服务于一个
工具，``TOOL_NAME``，回显其文本和启动的 ``MCP_TOKEN``
with, and touches ``STARTED_MARKER`` on startup so a test can tell whether
任何与之相关的东西。
"""

import os
import sys
from pathlib import Path

from fastmcp import FastMCP


tool_name = sys.argv[1]
if len(sys.argv) > 2:
    Path(sys.argv[2]).touch()

mcp = FastMCP(f"{tool_name}-server")


@mcp.tool(name=tool_name)
def echo(text: str) -> str:
    """回显文本与该服务器启动时使用的 token。"""
    return f"{tool_name}:{text}:token={os.environ.get('MCP_TOKEN', '')}"


if __name__ == "__main__":
    mcp.run(transport="stdio", show_banner=False)
