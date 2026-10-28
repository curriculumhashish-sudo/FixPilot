"""测试 LocalConversation 如何将 MCP 服务器连接到正在运行的智能体。"""

import logging
from pathlib import Path
from typing import Any, cast

import mcp.types as mcp_types
import pytest
from pydantic import SecretStr

from openhands.sdk import LLM, Agent
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.config import MCPServer, coerce_mcp_config
from openhands.sdk.mcp.exceptions import MCPError
from openhands.sdk.mcp.tool import MCPToolDefinition
from openhands.sdk.mcp.utils import MCPToolProvider


class EmptyMCPClient:
    def __init__(self) -> None:
        self.tools: list[MCPToolDefinition] = []
        self._tools_reconciled_callback: Any = None

    def sync_close(self) -> None:
        pass


class RecordingMCPToolProvider:
    """记录每次打开 MCP 连接的尝试。"""

    def __init__(self, client: EmptyMCPClient | None = None) -> None:
        self.calls: list[dict[str, MCPServer]] = []
        self.client = client if client is not None else EmptyMCPClient()

    def create_tools(
        self,
        mcp_config: dict[str, MCPServer],
        timeout: float = 30.0,
        *,
        on_tools_changed: Any = None,
        on_tools_reconciled: Any = None,
    ) -> MCPClient:
        self.calls.append(mcp_config)
        self.client._tools_reconciled_callback = on_tools_reconciled
        return cast(MCPClient, self.client)


def test_disabling_every_server_skips_the_mcp_connection(tmp_path: Path) -> None:
    """智能体仍然开始； 它只是没有 MCP 个服务器可以访问。"""
    provider = RecordingMCPToolProvider()
    agent = Agent(
        llm=LLM(model="test-model", api_key=SecretStr("test-key")),
        tools=[],
        mcp_config=coerce_mcp_config({"fetch": {"command": "uvx", "enabled": False}}),
    )
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        visualizer=None,
        mcp_tool_provider=provider,
    )

    conversation._ensure_agent_ready()

    assert provider.calls == []
    conversation.close()


def test_reconciliation_targets_replaced_agent(tmp_path: Path) -> None:
    client = EmptyMCPClient()
    initial = MCPToolDefinition.create(
        mcp_tool=mcp_types.Tool(
            name="initial",
            description="initial",
            inputSchema={"type": "object", "properties": {}},
        ),
        mcp_client=cast(MCPClient, client),
    )[0]
    client.tools = [initial]
    conversation = LocalConversation(
        agent=Agent(
            llm=LLM(model="test-model", api_key=SecretStr("test-key")),
            tools=[],
            include_default_tools=[],
            mcp_config=coerce_mcp_config({"fake": {"command": "true"}}),
        ),
        workspace=str(tmp_path),
        visualizer=None,
        mcp_tool_provider=RecordingMCPToolProvider(client),
    )
    conversation._ensure_agent_ready()
    old_agent = conversation.agent
    conversation.agent = old_agent.model_copy()
    replacement = MCPToolDefinition.create(
        mcp_tool=mcp_types.Tool(
            name="replacement",
            description="replacement",
            inputSchema={"type": "object", "properties": {}},
        ),
        mcp_client=cast(MCPClient, client),
    )[0]

    client._tools_reconciled_callback(cast(MCPClient, client), [replacement])

    updated_mcp_tools = {
        name
        for name, tool in conversation.agent.tools_map.items()
        if isinstance(tool, MCPToolDefinition)
    }
    old_mcp_tools = {
        name
        for name, tool in old_agent.tools_map.items()
        if isinstance(tool, MCPToolDefinition)
    }
    assert updated_mcp_tools == {"replacement"}
    assert old_mcp_tools == {"initial"}
    conversation.close()


class LegacyMCPToolProvider:
    """根据预协调协议编写的自定义提供程序。"""

    def create_tools(
        self,
        mcp_config: dict[str, MCPServer],
        timeout: float = 30.0,
        *,
        on_tools_changed: Any = None,
    ) -> MCPClient:
        return cast(MCPClient, EmptyMCPClient())


def test_legacy_provider_without_on_tools_reconciled_still_works(
    tmp_path: Path,
) -> None:
    """一个预设的 MCPToolProvider 必须不使用 on_tools_reconciled
    break; it just won't receive full-snapshot reconciliation."""
    conversation = LocalConversation(
        agent=Agent(
            llm=LLM(model="test-model", api_key=SecretStr("test-key")),
            tools=[],
            include_default_tools=[],
            mcp_config=coerce_mcp_config({"fake": {"command": "true"}}),
        ),
        workspace=str(tmp_path),
        visualizer=None,
        # 故意不兼容当前 MCPToolProvider 协议结构。 这就是正在测试的场景。
        #
        mcp_tool_provider=cast(MCPToolProvider, LegacyMCPToolProvider()),
    )

    conversation._ensure_agent_ready()

    conversation.close()


class _KwargsMCPToolProvider:
    """通过 **kwargs 接受任意关键字的提供程序。"""

    def create_tools(
        self, mcp_config: dict[str, MCPServer], timeout: float = 30.0, **kwargs: Any
    ) -> MCPClient:
        return cast(MCPClient, EmptyMCPClient())


def test_provider_supports_on_tools_reconciled() -> None:
    from openhands.sdk.mcp.utils import (
        DefaultMCPToolProvider,
        provider_supports_on_tools_reconciled,
    )

    assert provider_supports_on_tools_reconciled(DefaultMCPToolProvider())
    assert provider_supports_on_tools_reconciled(RecordingMCPToolProvider())
    assert provider_supports_on_tools_reconciled(_KwargsMCPToolProvider())
    assert not provider_supports_on_tools_reconciled(
        cast(MCPToolProvider, LegacyMCPToolProvider())
    )


class FailingMCPToolProvider:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def create_tools(
        self,
        mcp_config: dict[str, MCPServer],
        timeout: float = 30.0,
        *,
        on_tools_changed: Any = None,
        on_tools_reconciled: Any = None,
    ) -> MCPClient:
        raise self.error


@pytest.mark.parametrize(
    "error",
    [
        MCPError("MCP Connection Failure"),
        OSError("offline"),
        RuntimeError("unhealthy server"),
    ],
)
def test_mcp_startup_failure_does_not_abort_conversation(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, error: Exception
) -> None:
    conversation = LocalConversation(
        agent=Agent(
            llm=LLM(model="test-model", api_key=SecretStr("test-key")),
            tools=[],
            include_default_tools=[],
            mcp_config=coerce_mcp_config({"broken": {"command": "missing-mcp"}}),
        ),
        workspace=str(tmp_path),
        visualizer=None,
        mcp_tool_provider=FailingMCPToolProvider(error),
    )

    with caplog.at_level(logging.WARNING):
        conversation._ensure_agent_ready()

    assert conversation._agent_ready
    assert any(
        "MCP server startup failed for broken" in record.message
        for record in caplog.records
    )
    conversation.close()
