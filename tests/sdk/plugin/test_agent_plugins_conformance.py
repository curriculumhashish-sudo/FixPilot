"""智能体插件客户端一致性检查表，由真实包驱动。

这里的每个测试都会加载一个签入的包
``tests/fixtures/plugins/agent_plugins/`` 通过公众
:meth:`Plugin.load` 入口 -- 没有内联构建的清单，没有猴子补丁
格式注册表，无网络。

加载序列 ( https://agent-plugins.org/client-implementers )，这是问题要求的六项形状：

1. 建立文件系统解析的插件根 -> ``TestRootEstablishment``
2. 从``$schema``中选择本地规则，从不获取 -> ``TestSchemaSelection``
3. 拒绝致命违规行为，报告并忽略非致命违规行为 -> ``TestManifestRejection``
4. 从其固定位置发现每个受支持的组件类型 -> ``TestFixedLocations``、
``TestPlaceholderExpansion``、
``TestStdioDefaults``
5. 应用每个组件的故障边界 -> ``TestFailureBoundaries``
6. 应用已实现的扩展命名空间，忽略 REST -> ``TestClientExtensions``

对已发布的清单 ( https://agent-plugins.org/client-implementers/conformance ) 逐项进行
相同的测试：

插件加载器
  目录加载+包边界........ ``TestRootEstablishment`` 本地 ``$schema`` 选择，不可检索
  ``TestSchemaSelection`` 已关闭模式，必需 ``$schema``/``name``
                                             ``TestManifestRejection``（+ 中的现场级
                                             案例
                                             ``test_agent_plugins_format.py``)
  报告并忽略未知字段........................ ``TestManifestRejection`` 忽略非对象
  ``extensions`` 和未实
  现的命名空间 ................. ``TestManifestRejection``,
                                             ``TestClientExtensions``
  先拒绝其他致命违规行为…… ``TestManifestRejection``

发现与隔离
  仅限固定地点........................ ``TestFixedLocations`` 缺失地点均有效缺席.....
  .
  ``TestFixedLocations`` 隔离组件类型、技能、条目 ``TestFailureBoundaries`` 忽略不支
  持的组件类型.......
  ``TestFixedLocations``

MCP 支持
  至少一个传输层（我们两者都做）…… ``TestFixedLocations`` 与声明的传输层连接......
  ``TestFixedLocations`` 验证文档
  和每个条目...... ``TestVersioning``,
                                             ``TestFailureBoundaries``
  作为单个可执行文件的命令 token ..... ``TestStdioDefaults``
  ``PLUGIN_ROOT`` + 专用 ``PLUGIN_DATA``
                                             ``TestPlaceholderExpansion``
  仅扩展两个，仅扩展三个字段......................................
  ``TestPlaceholderExpansion`` cwd
   遏制，URL/标头规则 ........ ``TestFailureBoundaries``,
                                             ``TestPlaceholderExpansion``
  continue after an entry fails ............ ``TestFailureBoundaries``

版本控制
  两个文档中的匹配版本... ``TestVersioning`` 永远不会重新分配模式标识符.......
  ``TestVersioning`` 旧版本定位是一项本地政
  策 ``TestSchemaSelection``（我们
                                             完全支持 1.0.0)
"""

import socket
import sys
from pathlib import Path

import pytest

from openhands.sdk.plugin import AgentPluginsFormat, Plugin, detect_format
from openhands.sdk.plugin.format.agent_plugins import (
    _MANIFEST_SCHEMA_FILE,
    MANIFEST_SCHEMA_URL,
    _load_schema,
)
from openhands.sdk.plugin.format.agent_plugins_mcp import get_plugin_data_dir


FIXTURES = Path(__file__).parents[2] / "fixtures" / "plugins" / "agent_plugins"


def fixture(name: str) -> Path:
    """返回一个语料库包，按照调用者传递的方式进行解析。"""
    return (FIXTURES / name).resolve()


@pytest.fixture(autouse=True)
def plugin_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """将 ``PLUGIN_DATA`` 保留在真实用户目录之外。

    ``Plugin.load()`` 本身构建格式，因此数据根在模块默认值处重定向，而不是通过构造函
    数注入。
    """
    root = tmp_path / "plugin-data"
    monkeypatch.setattr(
        "openhands.sdk.plugin.format.agent_plugins_mcp.DEFAULT_PLUGIN_DATA_DIR", root
    )
    return root


def env_of(plugin: Plugin, server: str) -> dict[str, str]:
    return {
        key: value.get_secret_value()
        for key, value in (plugin.mcp_config[server].env or {}).items()
    }


def args_of(plugin: Plugin, server: str) -> list[str]:
    return plugin.mcp_config[server].args or []


def cwd_of(plugin: Plugin, server: str) -> str:
    return plugin.mcp_config[server].cwd or ""


def headers_of(plugin: Plugin, server: str) -> dict[str, str]:
    return {
        key: value.get_secret_value()
        for key, value in (plugin.mcp_config[server].headers or {}).items()
    }


class TestVendoredExample:
    """官方示例包，从供应的上游字节加载。"""

    def test_loads_as_an_agent_plugins_package(self):
        plugin = Plugin.load(fixture("agent-plugins-example"))

        assert isinstance(
            detect_format(fixture("agent-plugins-example")), AgentPluginsFormat
        )
        assert plugin.name == "agent-plugins-example"
        assert plugin.version == "1.0.0"
        assert [skill.name for skill in plugin.skills] == ["migrate-agent-plugin"]

    def test_skill_resources_come_along(self):
        """上游发布技能的参考/； 它们必须能够承受负载。"""
        plugin = Plugin.load(fixture("agent-plugins-example"))

        resources = plugin.skills[0].resources
        assert resources is not None
        assert sorted(resources.references) == [
            "client-extensions.md",
            "migration-guide.md",
            "validation-checklist.md",
        ]

    def test_skills_only_package_contributes_nothing_else(self):
        """它没有 mcp.json 也没有扩展目录（规范§6.2）。"""
        plugin = Plugin.load(fixture("agent-plugins-example"))

        assert plugin.mcp_config == {}
        assert plugin.agents == []
        assert plugin.commands == []
        assert plugin.entry_slash_command is None


class TestRootEstablishment:
    """第 1 项：建立文件系统解析的插件根（§4.1）。"""

    def test_root_is_the_directory_the_package_lives_in(self):
        plugin = Plugin.load(fixture("full-package"))

        assert Path(plugin.path) == fixture("full-package")
        assert args_of(plugin, "local-tools")[1] == str(fixture("full-package"))

    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")
    def test_root_is_resolved_before_anything_uses_it(
        self, tmp_path: Path, plugin_data_root: Path
    ):
        """通过符号链接到达时，该包仍然作为其真正的根加载。"""
        link = tmp_path / "link-to-full-package"
        link.symlink_to(fixture("full-package"), target_is_directory=True)

        plugin = Plugin.load(link)

        assert Path(plugin.path) == fixture("full-package")
        assert args_of(plugin, "local-tools")[1] == str(fixture("full-package"))
        assert cwd_of(plugin, "local-tools").startswith(
            str(
                get_plugin_data_dir(fixture("full-package"), data_root=plugin_data_root)
            )
        )

    def test_package_paths_stay_inside_the_root(self, caplog):
        """爬出包的 ``./`` 命令不会启动。"""
        plugin = Plugin.load(fixture("partial-failures"))

        assert "escaping-command" not in plugin.mcp_config
        assert "escapes" in caplog.text


class TestSchemaSelection:
    """第2项：从``$schema``中选择本地规则，从不检索一条。"""

    def test_no_socket_is_opened_while_loading(self, monkeypatch: pytest.MonkeyPatch):
        """使用供应商的模式； ``$schema`` URL 是一个标识符。"""

        def forbidden(*args, **kwargs):
            raise AssertionError("plugin loading must not touch the network")

        monkeypatch.setattr(socket, "socket", forbidden)
        monkeypatch.setattr(socket, "create_connection", forbidden)
        monkeypatch.setattr(socket, "getaddrinfo", forbidden)

        plugin = Plugin.load(fixture("full-package"))

        assert [skill.name for skill in plugin.skills] == ["greet", "summarize"]
        assert set(plugin.mcp_config) == {"local-tools", "remote-api"}

    def test_a_published_but_unvendored_version_is_rejected(self):
        """上游发布1.1.0； 这个SDK供应商只有1.0.0。"""
        with pytest.raises(ValueError, match=r"Unsupported or missing \$schema"):
            Plugin.load(fixture("unsupported-schema"))

    def test_rejection_names_the_version_we_support(self):
        with pytest.raises(ValueError, match="schemas/1.0.0/plugin.schema.json"):
            Plugin.load(fixture("unsupported-schema"))


class TestManifestRejection:
    """第3项：致命违规拒绝； 两个非致命的被忽略。"""

    def test_a_fatal_violation_rejects_the_whole_package(self):
        with pytest.raises(ValueError, match="Invalid Agent Plugins manifest"):
            Plugin.load(fixture("fatal-manifest"))

    def test_a_rejected_package_never_reaches_component_discovery(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """§11.3 规则 2：不得发现被拒绝插件的任何组件。"""
        discovered: list[str] = []
        for loader in (
            "load_skills",
            "load_mcp_config",
            "load_agents",
            "load_commands",
            "load_hooks",
        ):
            monkeypatch.setattr(
                AgentPluginsFormat,
                loader,
                lambda self, plugin_dir, _name=loader: discovered.append(_name),
            )

        with pytest.raises(ValueError):
            Plugin.load(fixture("fatal-manifest"))

        assert discovered == []

    def test_non_fatal_violations_are_reported_and_ignored(self, caplog):
        """未知的顶级字段和非对象 ``extensions``（第 5.2 节，第 8.1 节）。"""
        plugin = Plugin.load(fixture("non-fatal-manifest"))

        assert [skill.name for skill in plugin.skills] == ["ok"]
        assert "futureField" in caplog.text
        assert "non-object 'extensions'" in caplog.text


class TestFixedLocations:
    """第 4 项：从其固定位置发现每个受支持的组件类型。"""

    def test_every_supported_component_type_is_discovered(self):
        plugin = Plugin.load(fixture("full-package"))

        assert [skill.name for skill in plugin.skills] == ["greet", "summarize"]
        assert set(plugin.mcp_config) == {"local-tools", "remote-api"}
        assert [agent.name for agent in plugin.agents] == ["full-package-helper"]
        assert [command.name for command in plugin.commands] == ["report"]
        assert plugin.hooks is not None and not plugin.hooks.is_empty()

    def test_missing_locations_are_a_valid_absence(self):
        """§6.2：仅清单包是一致的，没有损坏。"""
        plugin = Plugin.load(fixture("manifest-only"))

        assert plugin.name == "manifest-only"
        assert plugin.skills == []
        assert plugin.mcp_config == {}
        assert plugin.agents == []
        assert plugin.commands == []
        assert plugin.hooks is None

    def test_only_the_fixed_locations_are_searched(self):
        """``wrong-locations`` 在根部提供 Claude Code 布局。

        ``.mcp.json``、``hooks/``、``commands/`` 和 ``agents/`` 没有此格式的位置，因
        此可以加载其中的 None 个
        位置（第 6.1 节）。
        """
        plugin = Plugin.load(fixture("wrong-locations"))

        assert [skill.name for skill in plugin.skills] == ["only"]
        assert plugin.mcp_config == {}
        assert plugin.hooks is None
        assert plugin.commands == []
        assert plugin.agents == []

    def test_an_unsupported_component_type_is_ignored(self):
        """§11.3 规则 1：``lsp/`` 不是 v1 组件类型，也不是错误。"""
        plugin = Plugin.load(fixture("wrong-locations"))

        assert (Path(plugin.path) / "lsp").is_dir()
        assert [skill.name for skill in plugin.skills] == ["only"]

    def test_the_declared_transport_is_the_one_carried(self):
        """§7.2.1：条目的传输层是客户端连接的条目。"""
        plugin = Plugin.load(fixture("full-package"))

        assert plugin.mcp_config["local-tools"].transport == "stdio"
        assert plugin.mcp_config["remote-api"].transport == "streamable-http"


class TestPlaceholderExpansion:
    """第 4 项的运行时一半：§9.2 在构建的服务器上进行扩展。"""

    def test_expanded_in_args_env_values_and_cwd(self, plugin_data_root: Path):
        plugin = Plugin.load(fixture("full-package"))
        root = str(fixture("full-package"))
        data = str(
            get_plugin_data_dir(fixture("full-package"), data_root=plugin_data_root)
        )

        assert args_of(plugin, "local-tools") == [
            "--root",
            root,
            "--cache",
            f"{data}/cache",
        ]
        assert env_of(plugin, "local-tools")["TOOLS_STATE"] == f"{data}/state"
        assert cwd_of(plugin, "local-tools") == f"{data}/work"

    def test_both_variables_are_provided_to_the_subprocess(
        self, plugin_data_root: Path
    ):
        """§9.1：客户端最后设置它们，插件不能覆盖它们。"""
        plugin = Plugin.load(fixture("full-package"))
        env = env_of(plugin, "local-tools")

        assert env["PLUGIN_ROOT"] == str(fixture("full-package"))
        assert env["PLUGIN_DATA"] == str(
            get_plugin_data_dir(fixture("full-package"), data_root=plugin_data_root)
        )

    def test_plugin_data_exists_before_the_subprocess_would_launch(
        self, plugin_data_root: Path
    ):
        Plugin.load(fixture("full-package"))

        assert get_plugin_data_dir(
            fixture("full-package"), data_root=plugin_data_root
        ).is_dir()

    def test_left_untouched_everywhere_else(self):
        """命令、环境键、URL 和标头永远不会扩展。"""
        plugin = Plugin.load(fixture("full-package"))

        assert plugin.mcp_config["local-tools"].command == str(
            fixture("full-package") / "bin" / "serve.sh"
        )
        assert "${PLUGIN_ROOT}" in env_of(plugin, "local-tools")
        assert plugin.mcp_config["remote-api"].url == (
            "https://api.example.com/mcp?root=${PLUGIN_ROOT}"
        )
        assert headers_of(plugin, "remote-api") == {
            "Authorization": "Bearer ${PLUGIN_DATA}",
            "X-Plugin-Root": "${PLUGIN_ROOT}",
        }

    def test_a_client_generated_header_is_dropped(self, caplog):
        """§7.2.1：配置的 ``Host`` 输给了客户端发送的。"""
        plugin = Plugin.load(fixture("full-package"))

        assert "Host" not in headers_of(plugin, "remote-api")
        assert "Host" in caplog.text

    def test_each_package_gets_its_own_plugin_data(self, plugin_data_root: Path):
        """§9.1：“专用”是指每个插件，并且在包之外。"""
        full = get_plugin_data_dir(fixture("full-package"), data_root=plugin_data_root)
        partial = get_plugin_data_dir(
            fixture("partial-failures"), data_root=plugin_data_root
        )

        assert full != partial
        assert not full.is_relative_to(fixture("full-package"))

    def test_other_placeholder_like_text_stays_literal(self):
        assert (
            env_of(Plugin.load(fixture("full-package")), "local-tools")["TOOLS_LABEL"]
            == "literal ${NOT_A_PLACEHOLDER} text"
        )


class TestFailureBoundaries:
    """第 5 项：应用为每个组件类型或条目定义的边界。"""

    def test_one_broken_skill_does_not_take_its_siblings(self, caplog):
        plugin = Plugin.load(fixture("partial-failures"))

        assert [skill.name for skill in plugin.skills] == ["good"]
        assert "broken" in caplog.text

    @pytest.mark.parametrize(
        "server",
        [
            "legacy-sse",  # 不支持传输层
            "escaping-command",  # 插件根目录之外的命令
            "placeholder-command",  # 命令永远不会扩展，因此永远不合法
            "escaping-cwd",  # 工作目录在其写入的根之外
            "insecure-url",  # 普通 HTTP 到远程主机
        ],
    )
    def test_one_bad_mcp_entry_does_not_take_its_siblings(self, server: str):
        """§7.2.2 规则 4：每个条目均自行验证并跳过。"""
        plugin = Plugin.load(fixture("partial-failures"))

        assert server not in plugin.mcp_config
        assert set(plugin.mcp_config) == {"good-server"}

    def test_a_bad_mcp_entry_does_not_take_another_component_type(self):
        """技能和智能体负载旁边有五个跳过的 MCP 条目。"""
        plugin = Plugin.load(fixture("partial-failures"))

        assert [skill.name for skill in plugin.skills] == ["good"]
        assert [agent.name for agent in plugin.agents] == ["partial-failures-helper"]

    def test_one_broken_agent_does_not_take_its_siblings(self):
        plugin = Plugin.load(fixture("partial-failures"))

        assert [agent.name for agent in plugin.agents] == ["partial-failures-helper"]


class TestStdioDefaults:
    """§7.2.1 的默认值，在未声明两者的条目上。"""

    def test_a_bare_command_stays_a_bare_token(self):
        """它进入平台可执行文件搜索，未解析和未扩展。"""
        plugin = Plugin.load(fixture("partial-failures"))

        assert plugin.mcp_config["good-server"].command == "echo"

    def test_the_plugin_root_is_the_default_working_directory(self):
        plugin = Plugin.load(fixture("partial-failures"))

        assert cwd_of(plugin, "good-server") == str(fixture("partial-failures"))


class TestVersioning:
    """检查表的版本控制部分。"""

    def test_an_mcp_json_targeting_another_version_disables_mcp_only(self):
        """§7.2.2规则2：文档无效，因此MCP关闭，而不是插件关闭。"""
        plugin = Plugin.load(fixture("mcp-version-mismatch"))

        assert plugin.mcp_config == {}
        assert [skill.name for skill in plugin.skills] == ["still-here"]

    def test_the_vendored_schema_keeps_its_published_identity(self):
        """规范标识符永远不会重新分配给不同的内容。"""
        schema = _load_schema(_MANIFEST_SCHEMA_FILE)

        assert schema["$id"] == MANIFEST_SCHEMA_URL


class TestClientExtensions:
    """第 6 项：应用我们的命名空间，忽略所有其他未经验证的项。"""

    def test_our_manifest_data_is_applied(self):
        plugin = Plugin.load(fixture("full-package"))

        assert plugin.entry_slash_command == "/full-package:report"

    def test_our_extension_directory_is_read(self):
        """§8.2：基于文件的组件位于 ``dev.openhands/`` 下。"""
        plugin = Plugin.load(fixture("full-package"))

        assert [command.name for command in plugin.commands] == ["report"]
        assert [agent.name for agent in plugin.agents] == ["full-package-helper"]
        assert plugin.hooks is not None
        assert [matcher.matcher for matcher in plugin.hooks.pre_tool_use] == [
            "full-package-*"
        ]

    def test_a_foreign_namespace_is_ignored_without_validation(self):
        """``com.example.other`` 带有错误类型的 ``entry_command``。

        §8.1 说这是我们的业务的 None：它既不能被应用也不能被拒绝。
        """
        plugin = Plugin.load(fixture("full-package"))

        assert plugin.entry_slash_command == "/full-package:report"
        assert plugin.manifest.model_extra is not None
        assert plugin.manifest.model_extra["extensions"]["com.example.other"] == {
            "entry_command": 17,
            "anything": [1, 2, 3],
        }

    def test_a_package_without_our_namespace_still_loads(self):
        plugin = Plugin.load(fixture("partial-failures"))

        assert plugin.entry_slash_command is None
