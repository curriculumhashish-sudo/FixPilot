"""端到端：驱动到已配置对话的智能体插件包。

``test_local_conversation_plugins.py`` 的镜像为可移植格式。 重要的是，这些断言在这里
运行，而不仅仅是在 ``Plugin`` 上：
``LocalConversation`` 合并插件本身并且从不调用 ``load_plugins()``，因此这是用户实际点
击的路径。

软件包来自 ``tests/fixtures/plugins/agent_plugins/``——本地目录源，因此不会获取任何插
件，也不会触及任何网络。
"""

from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from openhands.sdk import LLM, Agent, Conversation
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.config import MCPServer
from openhands.sdk.plugin import PluginSource
from openhands.sdk.plugin.format.agent_plugins_mcp import get_plugin_data_dir


FIXTURES = Path(__file__).parents[2] / "fixtures" / "plugins" / "agent_plugins"


def fixture(name: str) -> Path:
    return (FIXTURES / name).resolve()


class EmptyMCPClient:
    def __init__(self):
        self.tools = []
        self._tools_reconciled_callback: Any = None


class RecordingMCPToolProvider:
    """记录到达工具创建的 MCP 配置，并且不启动任何内容。"""

    def __init__(self, created: list[dict[str, MCPServer]]):
        self.created = created
        self.client = EmptyMCPClient()

    def create_tools(
        self,
        mcp_config: dict[str, MCPServer],
        timeout: float = 30.0,
        *,
        on_tools_changed: Any = None,
        on_tools_reconciled: Any = None,
    ) -> MCPClient:
        self.created.append(mcp_config)
        self.client._tools_reconciled_callback = on_tools_reconciled
        return cast(MCPClient, self.client)


@pytest.fixture(autouse=True)
def plugin_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """将 ``PLUGIN_DATA`` 保留在真实用户目录之外。"""
    root = tmp_path / "plugin-data"
    monkeypatch.setattr(
        "openhands.sdk.plugin.format.agent_plugins_mcp.DEFAULT_PLUGIN_DATA_DIR", root
    )
    return root


@pytest.fixture(autouse=True)
def no_ambient_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    """仅加载附加的包，无论开发人员安装了什么。"""
    monkeypatch.setattr(
        "openhands.sdk.conversation.impl.local_conversation.load_available_plugins",
        lambda **kwargs: {},
    )


@pytest.fixture
def agent() -> Agent:
    return Agent(llm=LLM(model="test/model", api_key=SecretStr("test-key")), tools=[])


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    path = tmp_path / "workspace"
    path.mkdir()
    return path


def conversation_with(
    package: str, agent: Agent, workspace: Path, **kwargs
) -> LocalConversation:
    return LocalConversation(
        agent=agent,
        workspace=workspace,
        plugins=[PluginSource(source=str(fixture(package)))],
        visualizer=None,
        **kwargs,
    )


def env_of(server: MCPServer) -> dict[str, str]:
    return {key: value.get_secret_value() for key, value in (server.env or {}).items()}


class TestSkills:
    """便携式布局的技能达到智能体上下文。"""

    def test_skills_reach_the_agent_context(self, agent: Agent, workspace: Path):
        conversation = conversation_with("full-package", agent, workspace)

        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        names = {s.name for s in conversation.agent.agent_context.skills}
        assert {"greet", "summarize"} <= names
        conversation.close()

    def test_the_entry_command_arrives_as_a_skill(self, agent: Agent, workspace: Path):
        """我们的扩展程序的命令成为关键字触发的技能。"""
        conversation = conversation_with("full-package", agent, workspace)

        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        skills = {s.name: s for s in conversation.agent.agent_context.skills}
        assert "full-package:report" in skills
        assert skills["full-package:report"].trigger is not None
        conversation.close()

    def test_the_vendored_example_package_works(self, agent: Agent, workspace: Path):
        """官方示例插件，端到端，来自供应字节。"""
        conversation = conversation_with("agent-plugins-example", agent, workspace)

        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        names = {s.name for s in conversation.agent.agent_context.skills}
        assert "migrate-agent-plugin" in names
        assert conversation.resolved_plugins is not None
        assert len(conversation.resolved_plugins) == 1
        conversation.close()

    def test_the_conversation_factory_takes_the_same_path(
        self, agent: Agent, workspace: Path
    ):
        conversation = Conversation(
            agent=agent,
            workspace=workspace,
            plugins=[PluginSource(source=str(fixture("full-package")))],
            visualizer=None,
        )

        assert isinstance(conversation, LocalConversation)
        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        names = {s.name for s in conversation.agent.agent_context.skills}
        assert {"greet", "summarize"} <= names
        conversation.close()

    def test_a_manifest_only_package_configures_an_agent(
        self, agent: Agent, workspace: Path
    ):
        """§6.2：缺少组件位置也不是此级别的错误。"""
        conversation = conversation_with("manifest-only", agent, workspace)

        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        assert conversation.agent.agent_context.skills == []
        assert conversation.agent.mcp_config == {}
        conversation.close()


class TestMCPServers:
    """``mcp.json`` 服务器达到实际工具创建，完全扩展。"""

    def test_servers_reach_tool_creation(self, agent: Agent, workspace: Path):
        created: list[dict[str, MCPServer]] = []
        conversation = conversation_with(
            "full-package",
            agent,
            workspace,
            mcp_tool_provider=RecordingMCPToolProvider(created),
        )
        assert conversation.agent.mcp_config == {}

        conversation._ensure_agent_ready()

        assert set(conversation.agent.mcp_config) == {"local-tools", "remote-api"}
        assert created, "plugin MCP servers never reached create_tools()"
        assert set(created[-1]) == {"local-tools", "remote-api"}
        conversation.close()

    def test_placeholders_are_expanded_on_the_constructed_server(
        self, agent: Agent, workspace: Path, plugin_data_root: Path
    ):
        created: list[dict[str, MCPServer]] = []
        conversation = conversation_with(
            "full-package",
            agent,
            workspace,
            mcp_tool_provider=RecordingMCPToolProvider(created),
        )

        conversation._ensure_agent_ready()

        root = str(fixture("full-package"))
        data = str(
            get_plugin_data_dir(fixture("full-package"), data_root=plugin_data_root)
        )
        server = created[-1]["local-tools"]
        assert server.args == ["--root", root, "--cache", f"{data}/cache"]
        assert env_of(server)["TOOLS_STATE"] == f"{data}/state"
        assert server.cwd == f"{data}/work"
        assert env_of(server)["PLUGIN_ROOT"] == root
        assert env_of(server)["PLUGIN_DATA"] == data
        conversation.close()

    def test_the_declared_transport_reaches_the_tool_provider(
        self, agent: Agent, workspace: Path
    ):
        """§7.2.1：条目声明的传输层是与之连接的工具。"""
        created: list[dict[str, MCPServer]] = []
        conversation = conversation_with(
            "full-package",
            agent,
            workspace,
            mcp_tool_provider=RecordingMCPToolProvider(created),
        )

        conversation._ensure_agent_ready()

        assert created[-1]["local-tools"].transport == "stdio"
        assert created[-1]["remote-api"].transport == "streamable-http"
        conversation.close()

    def test_placeholders_are_left_untouched_elsewhere(
        self, agent: Agent, workspace: Path
    ):
        """命令、环境键、URL 和标头不包含扩展（第 9.2 节）。

        此时，配置的 ``Host`` 已经消失：客户端自己生成该配置，因此它永远不会到达构建
        的服务器。
        """
        created: list[dict[str, MCPServer]] = []
        conversation = conversation_with(
            "full-package",
            agent,
            workspace,
            mcp_tool_provider=RecordingMCPToolProvider(created),
        )

        conversation._ensure_agent_ready()

        stdio = created[-1]["local-tools"]
        remote = created[-1]["remote-api"]
        assert stdio.command == str(fixture("full-package") / "bin" / "serve.sh")
        assert "${PLUGIN_ROOT}" in env_of(stdio)
        assert remote.url == "https://api.example.com/mcp?root=${PLUGIN_ROOT}"
        assert remote.headers is not None
        assert {
            key: value.get_secret_value() for key, value in remote.headers.items()
        } == {
            "Authorization": "Bearer ${PLUGIN_DATA}",
            "X-Plugin-Root": "${PLUGIN_ROOT}",
        }
        conversation.close()


class TestClientExtension:
    """``dev.openhands`` 组件应用于对话。"""

    def test_hooks_reach_the_hook_processor(self, agent: Agent, workspace: Path):
        conversation = conversation_with("full-package", agent, workspace)
        processor = MagicMock()
        processor.on_event = MagicMock()

        with patch(
            "openhands.sdk.conversation.impl.local_conversation.create_hook_callback",
            return_value=(processor, processor.on_event),
        ) as create_hook_callback:
            conversation._ensure_plugins_loaded()

        hook_config = create_hook_callback.call_args.kwargs["hook_config"]
        assert hook_config is not None
        assert [matcher.matcher for matcher in hook_config.pre_tool_use] == [
            "full-package-*"
        ]
        conversation.close()

    def test_agents_are_registered(self, agent: Agent, workspace: Path):
        conversation = conversation_with("full-package", agent, workspace)

        with patch(
            "openhands.sdk.conversation.impl.local_conversation.register_plugin_agents"
        ) as register:
            conversation._ensure_plugins_loaded()

        registered = register.call_args.kwargs["agents"]
        assert [definition.name for definition in registered] == ["full-package-helper"]
        conversation.close()


class TestFailureBoundaries:
    """包的损坏部分会单独损坏，或者完全停止插件。"""

    def test_broken_entries_do_not_stop_the_conversation(
        self, agent: Agent, workspace: Path
    ):
        created: list[dict[str, MCPServer]] = []
        conversation = conversation_with(
            "partial-failures",
            agent,
            workspace,
            mcp_tool_provider=RecordingMCPToolProvider(created),
        )

        conversation._ensure_agent_ready()

        assert conversation.agent.agent_context is not None
        assert [s.name for s in conversation.agent.agent_context.skills] == ["good"]
        assert set(conversation.agent.mcp_config) == {"good-server"}
        assert set(created[-1]) == {"good-server"}
        conversation.close()

    @pytest.mark.parametrize(
        "package, message",
        [
            ("fatal-manifest", "Invalid Agent Plugins manifest"),
            ("unsupported-schema", r"Unsupported or missing \$schema"),
        ],
    )
    def test_a_rejected_package_stops_the_conversation(
        self, agent: Agent, workspace: Path, package: str, message: str
    ):
        """被拒绝的插件不会被默默删除：附加它是一个错误。"""
        conversation = conversation_with(package, agent, workspace)

        with pytest.raises(ValueError, match=message):
            conversation._ensure_plugins_loaded()

        assert conversation.agent.mcp_config == {}
        conversation.close()

    def test_a_disabled_mcp_component_still_yields_skills(
        self, agent: Agent, workspace: Path
    ):
        """针对另一个版本的 ``mcp.json`` 会禁用 MCP，而不是插件。"""
        created: list[dict[str, MCPServer]] = []
        conversation = conversation_with(
            "mcp-version-mismatch",
            agent,
            workspace,
            mcp_tool_provider=RecordingMCPToolProvider(created),
        )

        conversation._ensure_agent_ready()

        assert conversation.agent.agent_context is not None
        assert [s.name for s in conversation.agent.agent_context.skills] == [
            "still-here"
        ]
        assert conversation.agent.mcp_config == {}
        conversation.close()

    def test_components_outside_the_fixed_locations_never_reach_the_agent(
        self, agent: Agent, workspace: Path
    ):
        """根部的克劳德代码布局在这里没有任何贡献。"""
        conversation = conversation_with("wrong-locations", agent, workspace)

        with patch(
            "openhands.sdk.conversation.impl.local_conversation.register_plugin_agents"
        ) as register:
            conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        assert [s.name for s in conversation.agent.agent_context.skills] == ["only"]
        assert conversation.agent.mcp_config == {}
        register.assert_not_called()
        conversation.close()

    def test_non_fatal_manifest_violations_still_configure_the_agent(
        self, agent: Agent, workspace: Path
    ):
        conversation = conversation_with("non-fatal-manifest", agent, workspace)

        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        assert [s.name for s in conversation.agent.agent_context.skills] == ["ok"]
        conversation.close()
