"""测试智能体插件 ``mcp.json`` 加载器。"""

import json
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from openhands.sdk import LLM, Agent
from openhands.sdk.mcp.config import MCPServer, to_fastmcp_mcp_config
from openhands.sdk.mcp.utils import create_mcp_tools
from openhands.sdk.plugin import (
    AgentPluginsFormat,
    Plugin,
    PluginSource,
    get_plugin_data_dir,
)
from openhands.sdk.plugin.discovery import USER_PLUGINS_DIRS, load_user_plugins
from openhands.sdk.plugin.format.agent_plugins_mcp import DEFAULT_PLUGIN_DATA_DIR
from openhands.sdk.plugin.loader import load_plugins
from openhands.sdk.settings.model import OpenHandsAgentSettings
from openhands.sdk.skills.utils import expand_mcp_servers


MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"

MANIFEST = {
    "$schema": PLUGIN_SCHEMA,
    "name": "example",
    "version": "1.0.0",
    "description": "An Agent Plugins package.",
}

# 规范自己的示例，逐字记录（第 7.2.1 节）。
SPEC_EXAMPLE = {
    "local-validator": {
        "type": "stdio",
        "command": "./bin/validator",
        "args": ["--data", "${PLUGIN_DATA}/validator"],
        "env": {"CONFIG": "${PLUGIN_ROOT}/config.json"},
        "cwd": "${PLUGIN_ROOT}",
    },
    "deployment-api": {
        "type": "streamable-http",
        "url": "https://deploy.example.com/mcp",
        "headers": {"X-Tenant": "public-tenant"},
    },
    "legacy-events": {"type": "sse", "url": "https://legacy.example.com/sse"},
}


@pytest.fixture
def plugin_dir(tmp_path: Path) -> Path:
    """具有有效清单和 ``./bin/validator`` 的插件根。"""
    root = tmp_path / "example"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "validator").touch()
    (root / "plugin.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    return root


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "plugin-data"


def write_mcp(plugin_dir: Path, document: dict | str) -> Path:
    path = plugin_dir / "mcp.json"
    path.write_text(
        document if isinstance(document, str) else json.dumps(document),
        encoding="utf-8",
    )
    return path


def load(plugin_dir: Path, data_root: Path, servers: dict) -> dict[str, MCPServer]:
    """在有效的顶级文档下加载 ``mcpServers``。"""
    write_mcp(plugin_dir, {"$schema": MCP_SCHEMA, "mcpServers": servers})
    return AgentPluginsFormat(plugin_data_root=data_root).load_mcp_config(plugin_dir)


def load_one(plugin_dir: Path, data_root: Path, server: dict) -> MCPServer | None:
    """加载名为 ``s`` 的单个条目，如果跳过则加载 None。"""
    return load(plugin_dir, data_root, {"s": server}).get("s")


class TestDocument:
    """顶级文档：关闭模式，固定版本（§7.2.1）。"""

    def test_absent_file_is_not_an_error(self, plugin_dir: Path, data_root: Path):
        fmt = AgentPluginsFormat(plugin_data_root=data_root)

        assert fmt.load_mcp_config(plugin_dir) == {}

    def test_dotted_mcp_json_is_not_read(self, plugin_dir: Path, data_root: Path):
        """克劳德代码文件名是不同格式的文件。"""
        (plugin_dir / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"s": {"command": "echo"}}}), encoding="utf-8"
        )

        assert (
            AgentPluginsFormat(plugin_data_root=data_root).load_mcp_config(plugin_dir)
            == {}
        )

    def test_loads_the_spec_example(self, plugin_dir: Path, data_root: Path):
        servers = load(plugin_dir, data_root, SPEC_EXAMPLE)

        # sse 不受支持并被跳过； 另外两个负载。
        assert sorted(servers) == ["deployment-api", "local-validator"]

    def test_empty_server_map(self, plugin_dir: Path, data_root: Path):
        assert load(plugin_dir, data_root, {}) == {}

    @pytest.mark.parametrize(
        "document",
        [
            pytest.param("{not json", id="unparseable"),
            pytest.param(json.dumps([]), id="not-an-object"),
            pytest.param(json.dumps({"mcpServers": {}}), id="no-schema"),
            pytest.param(
                json.dumps({"$schema": PLUGIN_SCHEMA, "mcpServers": {}}),
                id="manifest-schema",
            ),
            pytest.param(
                json.dumps(
                    {
                        "$schema": (
                            "https://agent-plugins.org/schemas/2.0.0/mcp.schema.json"
                        ),
                        "mcpServers": {},
                    }
                ),
                id="unsupported-version",
            ),
            pytest.param(json.dumps({"$schema": MCP_SCHEMA}), id="no-servers"),
            pytest.param(
                json.dumps({"$schema": MCP_SCHEMA, "mcpServers": {}, "extra": "field"}),
                id="unknown-top-level-field",
            ),
            pytest.param(
                json.dumps({"$schema": MCP_SCHEMA, "mcpServers": []}),
                id="servers-not-an-object",
            ),
        ],
    )
    def test_invalid_document_disables_mcp(
        self, plugin_dir: Path, data_root: Path, document: str
    ):
        write_mcp(plugin_dir, document)

        assert (
            AgentPluginsFormat(plugin_data_root=data_root).load_mcp_config(plugin_dir)
            == {}
        )

    def test_invalid_document_leaves_other_components_alone(
        self, plugin_dir: Path, data_root: Path
    ):
        """§7.2.2 规则 2：MCP 被禁用，插件仍然加载。"""
        skill = plugin_dir / "skills" / "greet"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: greet\ndescription: Greet someone.\n---\n\nHi.\n",
            encoding="utf-8",
        )
        write_mcp(plugin_dir, "{not json")

        plugin = Plugin.load(plugin_dir)

        assert plugin.mcp_config == {}
        assert [s.name for s in plugin.skills] == ["greet"]


class TestFailureIsolation:
    """§7.2.2 规则 3-4：1 个错误条目，1 个跳过条目。"""

    def test_sibling_entries_still_load(self, plugin_dir: Path, data_root: Path):
        servers = load(
            plugin_dir,
            data_root,
            {
                "broken": {"type": "stdio"},
                "unknown-transport": {"type": "carrier-pigeon"},
                "good": {"type": "stdio", "command": "echo"},
            },
        )

        assert sorted(servers) == ["good"]

    @pytest.mark.parametrize(
        "server",
        [
            pytest.param({"type": "stdio", "command": "echo", "url": "x"}, id="mixed"),
            pytest.param(
                {"type": "stdio", "command": "echo", "extra": 1}, id="unknown-field"
            ),
            pytest.param({"command": "echo"}, id="no-type"),
            pytest.param(
                {"type": "stdio", "command": "echo", "env": {"PLUGIN_ROOT": "/x"}},
                id="reserved-env-name",
            ),
            pytest.param(
                {"type": "stdio", "command": "echo", "cwd": "data"},
                id="bare-relative-cwd",
            ),
            pytest.param(
                {"type": "sse", "url": "https://legacy.example.com/sse"},
                id="unsupported-sse",
            ),
        ],
    )
    def test_invalid_entry_is_skipped(
        self, plugin_dir: Path, data_root: Path, server: dict
    ):
        assert load_one(plugin_dir, data_root, server) is None


class TestStdio:
    """§7.2.1 stdio：命令解析、扩展、包含。"""

    def test_bare_command_is_left_to_the_platform(
        self, plugin_dir: Path, data_root: Path
    ):
        server = load_one(plugin_dir, data_root, {"type": "stdio", "command": "npx"})

        assert server is not None
        assert server.command == "npx"

    def test_plugin_relative_command_resolves_to_the_package(
        self, plugin_dir: Path, data_root: Path
    ):
        server = load_one(
            plugin_dir, data_root, {"type": "stdio", "command": "./bin/validator"}
        )

        assert server is not None
        assert server.command == str(plugin_dir.resolve() / "bin" / "validator")

    @pytest.mark.parametrize(
        "command",
        ["../outside", "/usr/bin/outside", "bin/validator", "./../outside"],
    )
    def test_command_must_be_bare_or_contained(
        self, plugin_dir: Path, data_root: Path, command: str
    ):
        assert (
            load_one(plugin_dir, data_root, {"type": "stdio", "command": command})
            is None
        )

    def test_command_is_never_expanded(self, plugin_dir: Path, data_root: Path):
        """§9.2：扩展不适用于``command``。"""
        server = load_one(
            plugin_dir, data_root, {"type": "stdio", "command": "${PLUGIN_ROOT}"}
        )

        assert server is not None
        assert server.command == "${PLUGIN_ROOT}"

    def test_expands_args_and_env_values(self, plugin_dir: Path, data_root: Path):
        server = load_one(
            plugin_dir,
            data_root,
            {
                "type": "stdio",
                "command": "echo",
                "args": ["--root=${PLUGIN_ROOT}", "${PLUGIN_DATA}/cache", "plain"],
                "env": {"CONFIG": "${PLUGIN_ROOT}/config.json"},
            },
        )

        assert server is not None
        root = str(plugin_dir.resolve())
        data = str(get_plugin_data_dir(plugin_dir, data_root=data_root))
        assert server.args == [f"--root={root}", f"{data}/cache", "plain"]
        assert server.env is not None
        assert server.env["CONFIG"].get_secret_value() == f"{root}/config.json"

    def test_other_placeholders_stay_literal(self, plugin_dir: Path, data_root: Path):
        """§9.2：无环境、机密或任何类型的默认扩展。"""
        server = load_one(
            plugin_dir,
            data_root,
            {
                "type": "stdio",
                "command": "echo",
                "args": ["${HOME}", "${MISSING:-fallback}", "$PLUGIN_ROOT"],
            },
        )

        assert server is not None
        assert server.args == ["${HOME}", "${MISSING:-fallback}", "$PLUGIN_ROOT"]

    def test_expansion_is_not_recursive(self, tmp_path: Path, data_root: Path):
        """替换引入的文本不会重新扫描，即使路径
        本身包含另一个占位符。"""
        root = tmp_path / "${PLUGIN_DATA}"
        root.mkdir()
        (root / "plugin.json").write_text(json.dumps(MANIFEST), encoding="utf-8")

        server = load_one(
            root,
            data_root,
            {"type": "stdio", "command": "echo", "args": ["${PLUGIN_ROOT}"]},
        )

        assert server is not None
        assert server.args == [str(root.resolve())]

    def test_reserved_variables_are_set_last(self, plugin_dir: Path, data_root: Path):
        """§9.1：客户端提供它们并且插件不能覆盖它们。"""
        server = load_one(
            plugin_dir,
            data_root,
            {"type": "stdio", "command": "echo", "env": {"OTHER": "value"}},
        )

        assert server is not None
        assert server.env is not None
        assert server.env["PLUGIN_ROOT"].get_secret_value() == str(plugin_dir.resolve())
        assert server.env["PLUGIN_DATA"].get_secret_value() == str(
            get_plugin_data_dir(plugin_dir, data_root=data_root)
        )

    def test_default_cwd_is_the_plugin_root(self, plugin_dir: Path, data_root: Path):
        server = load_one(plugin_dir, data_root, {"type": "stdio", "command": "echo"})

        assert server is not None
        assert server.cwd == str(plugin_dir.resolve())

    @pytest.mark.parametrize(
        ("cwd", "expected"),
        [
            ("./data", "root/data"),
            ("${PLUGIN_ROOT}", "root"),
            ("${PLUGIN_ROOT}/data", "root/data"),
            ("${PLUGIN_DATA}", "data"),
            ("${PLUGIN_DATA}/cache", "data/cache"),
        ],
    )
    def test_cwd_forms(
        self, plugin_dir: Path, data_root: Path, cwd: str, expected: str
    ):
        server = load_one(
            plugin_dir, data_root, {"type": "stdio", "command": "echo", "cwd": cwd}
        )

        roots = {
            "root": plugin_dir.resolve(),
            "data": get_plugin_data_dir(plugin_dir, data_root=data_root).resolve(),
        }
        head, _, tail = expected.partition("/")
        assert server is not None
        assert server.cwd == str(roots[head] / tail if tail else roots[head])

    @pytest.mark.parametrize(
        "cwd", ["./../outside", "${PLUGIN_ROOT}/../outside", "${PLUGIN_DATA}/../other"]
    )
    def test_cwd_may_not_escape_its_root(
        self, plugin_dir: Path, data_root: Path, cwd: str
    ):
        assert (
            load_one(
                plugin_dir, data_root, {"type": "stdio", "command": "echo", "cwd": cwd}
            )
            is None
        )


class TestRemote:
    """§7.2.1 远程端点：URL 规则和文字标头。"""

    def test_streamable_http_is_mapped(self, plugin_dir: Path, data_root: Path):
        server = load_one(
            plugin_dir,
            data_root,
            {
                "type": "streamable-http",
                "url": "https://deploy.example.com/mcp",
                "headers": {"X-Tenant": "public-tenant"},
            },
        )

        assert server is not None
        assert server.transport == "streamable-http"
        assert server.url == "https://deploy.example.com/mcp"
        assert server.headers is not None
        assert server.headers["X-Tenant"].get_secret_value() == "public-tenant"

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:3000/mcp",
            "http://127.0.0.1:3000/mcp",
            "http://127.8.9.10/mcp",
            "http://[::1]:3000/mcp",
        ],
    )
    def test_loopback_may_use_http(self, plugin_dir: Path, data_root: Path, url: str):
        server = load_one(
            plugin_dir, data_root, {"type": "streamable-http", "url": url}
        )

        assert server is not None

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("/mcp", id="relative"),
            pytest.param("ftp://example.com/mcp", id="scheme"),
            pytest.param("http://deploy.example.com/mcp", id="remote-plaintext"),
            pytest.param("https://user:pw@example.com/mcp", id="user-info"),
            pytest.param("https://example.com/mcp#frag", id="fragment"),
            pytest.param("https://example.com/mcp#", id="empty-fragment"),
            pytest.param("https://@example.com/mcp", id="empty-user-info"),
            pytest.param("http://127.evil.example/mcp", id="loopback-lookalike-name"),
        ],
    )
    def test_invalid_url_skips_the_entry(
        self, plugin_dir: Path, data_root: Path, url: str
    ):
        assert (
            load_one(plugin_dir, data_root, {"type": "streamable-http", "url": url})
            is None
        )

    @pytest.mark.parametrize(
        "headers",
        [
            pytest.param({"X Tenant": "v"}, id="space-in-name"),
            pytest.param({"X-Tenant": "v", "x-tenant": "w"}, id="case-duplicate"),
            pytest.param({"X-Tenant": "line\nbreak"}, id="value-newline"),
        ],
    )
    def test_invalid_headers_skip_the_entry(
        self, plugin_dir: Path, data_root: Path, headers: dict
    ):
        assert (
            load_one(
                plugin_dir,
                data_root,
                {
                    "type": "streamable-http",
                    "url": "https://example.com/mcp",
                    "headers": headers,
                },
            )
            is None
        )

    @pytest.mark.parametrize(
        "name",
        [
            "Host",
            "content-length",
            "Transfer-Encoding",
            "Connection",
            "Accept",
            "Content-Type",
            "Mcp-Session-Id",
            "MCP-Protocol-Version",
        ],
    )
    def test_client_generated_headers_are_dropped(
        self, plugin_dir: Path, data_root: Path, name: str
    ):
        """§7.2.1：客户端自己的标头优先； httpx 会
        否则发送一份已配置的书面文件。"""
        server = load_one(
            plugin_dir,
            data_root,
            {
                "type": "streamable-http",
                "url": "https://example.com/mcp",
                "headers": {name: "configured", "X-Tenant": "public-tenant"},
            },
        )

        assert server is not None
        assert server.headers is not None
        assert list(server.headers) == ["X-Tenant"]

    def test_headers_are_never_expanded(self, plugin_dir: Path, data_root: Path):
        server = load_one(
            plugin_dir,
            data_root,
            {
                "type": "streamable-http",
                "url": "https://example.com/mcp",
                "headers": {"X-Root": "${PLUGIN_ROOT}"},
            },
        )

        assert server is not None
        assert server.headers is not None
        assert server.headers["X-Root"].get_secret_value() == "${PLUGIN_ROOT}"


class TestLiteralValues:
    """包数据是可见的，因此它必须在未编辑的情况下保留序列化。"""

    def test_plugin_values_are_redacted_like_any_secret(
        self, plugin_dir: Path, data_root: Path
    ):
        """插件不得将机密放入 headers 或 env 中； 无论如何，如果有人这么做的话
        脱敏仍然保护用户。 客户端不需要纯文本副本：每次加载时都会从包中重建插件服务器
        。
        """
        servers = load(
            plugin_dir,
            data_root,
            {
                "api": {
                    "type": "streamable-http",
                    "url": "https://example.com/mcp",
                    "headers": {"X-Tenant": "public-tenant"},
                },
                "local": {"type": "stdio", "command": "echo", "env": {"K": "v"}},
            },
        )

        assert servers["api"].model_dump(mode="json")["headers"] == {
            "X-Tenant": "**********"
        }
        assert servers["local"].model_dump(mode="json")["env"]["K"] == "**********"
        # 连接路径仍然获得实际值。
        fastmcp = to_fastmcp_mcp_config(servers)["mcpServers"]
        assert fastmcp["api"]["headers"] == {"X-Tenant": "public-tenant"}
        assert fastmcp["local"]["env"]["K"] == "v"

    def test_flag_is_never_serialized(self, plugin_dir: Path, data_root: Path):
        servers = load(
            plugin_dir, data_root, {"s": {"type": "stdio", "command": "echo"}}
        )

        assert "literal_values" not in servers["s"].model_dump(mode="json")
        assert "literal_values" not in to_fastmcp_mcp_config(servers)["mcpServers"]["s"]

    @pytest.mark.parametrize(
        "validate",
        [
            pytest.param(MCPServer.model_validate, id="server"),
            pytest.param(
                lambda server: OpenHandsAgentSettings.model_validate(
                    {"mcp_config": {"mine": server}}
                ),
                id="settings-payload",
            ),
        ],
    )
    def test_flag_cannot_be_set_from_input(self, validate):
        """否则，载荷可能会以明文形式存储真实的机密。"""
        with pytest.raises(ValidationError, match="literal_values"):
            validate(
                {
                    "url": "https://api.example.com/mcp",
                    "headers": {"Authorization": "Bearer real-secret"},
                    "literal_values": True,
                }
            )

    def test_flag_does_not_survive_a_data_round_trip(
        self, plugin_dir: Path, data_root: Path
    ):
        """只有加载程序才授予它； 重新加载的数据又是普通配置。"""
        server = load_one(plugin_dir, data_root, {"type": "stdio", "command": "echo"})
        assert server is not None

        reloaded = MCPServer.model_validate(
            server.model_dump(mode="json", context={"expose_secrets": "plaintext"})
        )

        assert not reloaded.literal_values

    def test_flag_survives_in_memory_copies(self, plugin_dir: Path, data_root: Path):
        """对话合并在服务器及其智能体上使用 model_copy。"""
        server = load_one(plugin_dir, data_root, {"type": "stdio", "command": "echo"})
        assert server is not None
        agent = Agent(llm=LLM(model="gpt-4o", usage_id="test"), tools=[])

        copied = agent.model_copy(update={"mcp_config": {"s": server}})

        assert server.model_copy(update={"enabled": False}).literal_values
        assert copied.mcp_config["s"].literal_values

    def test_secret_expansion_leaves_package_servers_literal(
        self, plugin_dir: Path, data_root: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """§9.2：包不能将机密或环境变量拉入其子进程中。"""
        monkeypatch.setenv("LEAKED", "from-environment")
        package = load_one(
            plugin_dir,
            data_root,
            {"type": "stdio", "command": "echo", "args": ["${TOKEN}", "${LEAKED}"]},
        )
        ordinary = MCPServer(command="echo", args=["${TOKEN}", "${LEAKED}"])
        assert package is not None

        expanded = expand_mcp_servers(
            {"package": package, "ordinary": ordinary}, {"TOKEN": "secret"}.get
        )

        assert expanded["package"].args == ["${TOKEN}", "${LEAKED}"]
        assert expanded["ordinary"].args == ["secret", "from-environment"]

    def test_ordinary_servers_are_still_redacted(self):
        server = MCPServer(
            transport="streamable-http",
            url="https://example.com/mcp",
            headers={"Authorization": SecretStr("Bearer t0ken")},
        )

        assert not server.literal_values
        assert server.model_dump(mode="json")["headers"] == {
            "Authorization": "**********"
        }


class TestPluginData:
    """§9.1：更新后仍存在的可写目录。"""

    def test_created_under_a_readable_name(self, plugin_dir: Path, data_root: Path):
        load(plugin_dir, data_root, {"s": {"type": "stdio", "command": "echo"}})

        (created,) = data_root.iterdir()
        assert created == get_plugin_data_dir(plugin_dir, data_root=data_root)
        assert created.name.startswith("example-")

    def test_same_name_elsewhere_gets_its_own_directory(
        self, plugin_dir: Path, tmp_path: Path, data_root: Path
    ):
        """借用已安装插件名称的项目插件不得共享，
        并能够将文件放入该插件的数据目录中。"""
        impostor = tmp_path / "repo" / ".agents" / "plugins" / "example"
        impostor.mkdir(parents=True)
        (impostor / "plugin.json").write_text(json.dumps(MANIFEST), encoding="utf-8")

        assert get_plugin_data_dir(
            impostor, data_root=data_root
        ) != get_plugin_data_dir(plugin_dir, data_root=data_root)

    def test_survives_an_update_in_place(self, plugin_dir: Path, data_root: Path):
        """安装和获取更新相同的根目录，因此密钥不能
        取决于包装内容。"""
        load(plugin_dir, data_root, {"s": {"type": "stdio", "command": "echo"}})
        data = get_plugin_data_dir(plugin_dir, data_root=data_root)
        (data / "state.txt").write_text("kept", encoding="utf-8")

        updated = MANIFEST | {"version": "2.0.0", "description": "Updated."}
        (plugin_dir / "plugin.json").write_text(json.dumps(updated), encoding="utf-8")
        load(plugin_dir, data_root, {"s": {"type": "stdio", "command": "echo"}})

        assert (data / "state.txt").read_text(encoding="utf-8") == "kept"
        assert list(data_root.iterdir()) == [data]

    @pytest.mark.parametrize(
        "document",
        [
            pytest.param("{not json", id="invalid-document"),
            pytest.param(
                json.dumps(
                    {
                        "$schema": MCP_SCHEMA,
                        "mcpServers": {
                            "api": {
                                "type": "streamable-http",
                                "url": "https://x.io/mcp",
                            },
                            "bad": {"type": "stdio", "command": "../escape"},
                        },
                    }
                ),
                id="no-usable-stdio-server",
            ),
        ],
    )
    def test_not_created_without_a_stdio_server(
        self, plugin_dir: Path, data_root: Path, document: str
    ):
        write_mcp(plugin_dir, document)

        AgentPluginsFormat(plugin_data_root=data_root).load_mcp_config(plugin_dir)

        assert not data_root.exists()

    def test_not_created_for_an_entry_the_model_rejects(
        self, plugin_dir: Path, data_root: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """模式不是最后一句话：模型验证仍然可以拒绝。"""

        def reject(*args, **kwargs):
            raise ValidationError.from_exception_data("MCPServer", [])

        monkeypatch.setattr(
            "openhands.sdk.plugin.format.agent_plugins_mcp.MCPServer.model_validate",
            reject,
        )

        server = load_one(plugin_dir, data_root, {"type": "stdio", "command": "echo"})

        assert server is None
        assert not data_root.exists()

    def test_lives_outside_the_plugin_package(self, plugin_dir: Path, data_root: Path):
        """更新时包内的任何内容都会丢失。"""
        load(plugin_dir, data_root, {"s": {"type": "stdio", "command": "echo"}})

        assert not (data_root / "example").is_relative_to(plugin_dir.resolve())

    def test_defaults_to_the_user_data_directory(
        self, plugin_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        default = tmp_path / "default-data"
        monkeypatch.setattr(
            "openhands.sdk.plugin.format.agent_plugins_mcp.DEFAULT_PLUGIN_DATA_DIR",
            default,
        )
        write_mcp(
            plugin_dir,
            {
                "$schema": MCP_SCHEMA,
                "mcpServers": {"s": {"type": "stdio", "command": "echo"}},
            },
        )

        AgentPluginsFormat().load_mcp_config(plugin_dir)

        assert list(default.iterdir()) == [get_plugin_data_dir(plugin_dir)]

    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")
    def test_keyed_by_the_resolved_root(
        self, plugin_dir: Path, tmp_path: Path, data_root: Path
    ):
        """同一插件的另一条路径必须到达相同的数据。"""
        link = tmp_path / "link"
        link.symlink_to(plugin_dir, target_is_directory=True)

        assert get_plugin_data_dir(link, data_root=data_root) == get_plugin_data_dir(
            plugin_dir, data_root=data_root
        )

    def test_default_location_is_not_scanned_for_plugins(self):
        """扫描根目录下的数据目录作为其自己的插件加载。

        ``_load_plugins_from_dir`` 将每个子目录视为插件，而Claude Code 格式允许接受任
        何目录，因此
        ``plugins/data`` 会自动发现并合并到每个智能体。
        """
        assert not any(
            DEFAULT_PLUGIN_DATA_DIR.is_relative_to(scanned)
            for scanned in USER_PLUGINS_DIRS
        )

    def test_default_location_stays_out_of_ambient_discovery(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            "openhands.sdk.plugin.discovery.USER_PLUGINS_DIRS",
            [tmp_path / ".agents" / "plugins", tmp_path / "plugins"],
        )
        get_plugin_data_dir(
            tmp_path / "example", data_root=tmp_path / "plugin-data"
        ).mkdir(parents=True)

        assert load_user_plugins() == []


PROBE_SERVER = """\
import json, os, sys
from pathlib import Path
from fastmcp import FastMCP

Path(os.environ["PLUGIN_DATA"], "launch.json").write_text(json.dumps({
    "cwd": os.getcwd(),
    "argv": sys.argv[1:],
    "env": {k: os.environ.get(k) for k in ("PLUGIN_ROOT", "PLUGIN_DATA", "CONFIG")},
    "inherits_path": "PATH" in os.environ,
}))
mcp = FastMCP("probe")

@mcp.tool()
def ping() -> str:
    return "pong"

mcp.run(transport="stdio", show_banner=False)
"""


@pytest.mark.skipif(sys.platform == "win32", reason="shebang-launched probe server")
def test_stdio_server_launches_with_the_agent_plugins_contract(
    plugin_dir: Path, data_root: Path
):
    """端到端：加载包，通过 stdio 连接，检查运行的内容。

    单元测试引脚映射； 只有真正的发布展示了 SDK 的 MCP 客户端 PLUGIN_DATA 相关命令、
    扩展参数、工作目录和环境变量覆盖（而不是替换）基础环境。
    """
    probe = plugin_dir / "bin" / "probe"
    probe.write_text(f"#!{sys.executable}\n{PROBE_SERVER}", encoding="utf-8")
    probe.chmod(0o755)
    servers = load(
        plugin_dir,
        data_root,
        {
            "probe": {
                "type": "stdio",
                "command": "./bin/probe",
                "args": ["${PLUGIN_ROOT}", "${HOME}"],
                "env": {"CONFIG": "${PLUGIN_ROOT}/config.json"},
                "cwd": "${PLUGIN_DATA}",
            }
        },
    )

    with create_mcp_tools(servers, timeout=60) as client:
        assert any(tool.name.endswith("ping") for tool in client.tools)

    root = plugin_dir.resolve()
    data = get_plugin_data_dir(plugin_dir, data_root=data_root)
    launch = json.loads((data / "launch.json").read_text(encoding="utf-8"))
    assert Path(launch["cwd"]).resolve() == data.resolve()
    assert launch["argv"] == [str(root), "${HOME}"]
    assert launch["env"] == {
        "PLUGIN_ROOT": str(root),
        "PLUGIN_DATA": str(data),
        "CONFIG": f"{root}/config.json",
    }
    assert launch["inherits_path"] is True


def test_load_plugins_does_not_expand_package_servers(
    plugin_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """公共加载器也扩展了机密； 包服务器必须跳过它。"""
    monkeypatch.setattr(
        "openhands.sdk.plugin.format.agent_plugins_mcp.DEFAULT_PLUGIN_DATA_DIR",
        tmp_path / "data",
    )
    monkeypatch.setenv("LEAKED", "from-environment")
    write_mcp(
        plugin_dir,
        {
            "$schema": MCP_SCHEMA,
            "mcpServers": {
                "s": {"type": "stdio", "command": "echo", "args": ["${LEAKED}"]}
            },
        },
    )
    agent = Agent(llm=LLM(model="gpt-4o", usage_id="test"), tools=[])

    updated, _ = load_plugins(
        [PluginSource(source=str(plugin_dir))], agent, get_secret={}.get
    )

    assert updated.mcp_config["s"].args == ["${LEAKED}"]


@pytest.fixture
def http_capture() -> Iterator[tuple[dict[str, list[dict[str, str]]], str, str]]:
    """两个本地来源：``a`` 在自身内部重定向，然后重定向到 ``b``。

    返回每个路径看到的请求，键为 ``"a/mcp"``、``"a/moved"`` 和
    ``"b/mcp"``加上基础 URLs.
    """
    seen: dict[str, list[dict[str, str]]] = {}
    servers: list[ThreadingHTTPServer] = []

    def make_handler(label: str, redirects: dict[str, str]):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                seen.setdefault(f"{label}{self.path}", []).append(
                    {k.lower(): v for k, v in self.headers.items()}
                )
                target = redirects.get(self.path)
                self.send_response(307 if target else 400)
                if target:
                    self.send_header("Location", target)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_GET = do_DELETE = do_POST

            def log_message(self, format: str, *args: Any) -> None:
                pass

        return Handler

    b = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("b", {}))
    b_url = f"http://127.0.0.1:{b.server_port}"
    a = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("a", {}))
    a_url = f"http://127.0.0.1:{a.server_port}"
    a.RequestHandlerClass = make_handler(
        "a", {"/mcp": f"{a_url}/moved", "/moved": f"{b_url}/mcp"}
    )
    for server in (a, b):
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield seen, a_url, b_url
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


def test_configured_headers_do_not_follow_a_redirect_off_origin(
    plugin_dir: Path, data_root: Path, http_capture
):
    """§7.2.1，over real HTTP：保持同源重定向，一旦
    请求离开原点，并且永远不允许覆盖客户端自己的标头。
    """
    seen, a_url, b_url = http_capture
    servers = load(
        plugin_dir,
        data_root,
        {
            "api": {
                "type": "streamable-http",
                "url": f"{a_url}/mcp",
                "headers": {"X-Tenant": "public-tenant", "Host": "evil.example"},
            }
        },
    )

    with pytest.raises(Exception):
        # 存根永远不会回答 MCP； 只有请求才重要。
        with create_mcp_tools(servers, timeout=10):
            pass

    first, same_origin, other_origin = (
        seen["a/mcp"][0],
        seen["a/moved"][0],
        seen["b/mcp"][0],
    )
    assert first["x-tenant"] == "public-tenant"
    assert first["host"] == a_url.removeprefix("http://")
    assert same_origin["x-tenant"] == "public-tenant"
    assert "x-tenant" not in other_origin
    assert other_origin["host"] == b_url.removeprefix("http://")
