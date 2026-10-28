"""测试 --import-modules 预加载和 --extra-Python-path 帮助程序。"""

import importlib
import logging
import os
import sys
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from openhands.agent_server.__main__ import (
    _EXTRA_PYTHON_PATH_ENV,
    _get_internal_server_url,
    extend_python_path,
    preload_modules,
)


class TestPreloadModules:
    def test_none_is_noop(self):
        with patch(
            "openhands.agent_server.__main__.importlib.import_module"
        ) as mock_import:
            preload_modules(None)
        mock_import.assert_not_called()

    def test_empty_string_is_noop(self):
        with patch(
            "openhands.agent_server.__main__.importlib.import_module"
        ) as mock_import:
            preload_modules("")
        mock_import.assert_not_called()

    def test_single_module(self):
        with patch(
            "openhands.agent_server.__main__.importlib.import_module"
        ) as mock_import:
            preload_modules("myapp.tools")
        mock_import.assert_called_once_with("myapp.tools")

    def test_comma_separated_strips_whitespace(self):
        with patch(
            "openhands.agent_server.__main__.importlib.import_module"
        ) as mock_import:
            preload_modules(" myapp.tools , myapp.plugins ")
        assert [c.args[0] for c in mock_import.call_args_list] == [
            "myapp.tools",
            "myapp.plugins",
        ]

    def test_empty_segments_skipped(self):
        with patch(
            "openhands.agent_server.__main__.importlib.import_module"
        ) as mock_import:
            preload_modules("myapp.tools,,myapp.plugins, ")
        assert [c.args[0] for c in mock_import.call_args_list] == [
            "myapp.tools",
            "myapp.plugins",
        ]

    def test_missing_module_raises(self):
        # 遵循项目惯例：不要吞咽导入错误。
        with pytest.raises(ModuleNotFoundError):
            preload_modules("definitely_not_a_real_module_xyz_2771")

    @pytest.fixture
    def fake_tool_module(self, tmp_path, monkeypatch):
        """创建一个磁盘模块，其顶层主体有一个可观察的
        副作用（类似于 `register_tool(...)` 调用）。"""
        pkg_name = "preload_modules_test_pkg"
        pkg = tmp_path / pkg_name
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "my_tool.py").write_text(
            textwrap.dedent(
                """\
                REGISTRY = []
                REGISTRY.append("MyCustomTool")
                """
            )
        )
        monkeypatch.syspath_prepend(str(tmp_path))
        qualname = f"{pkg_name}.my_tool"
        sys.modules.pop(pkg_name, None)
        sys.modules.pop(qualname, None)
        yield qualname
        sys.modules.pop(pkg_name, None)
        sys.modules.pop(qualname, None)

    def test_module_side_effects_execute(self, fake_tool_module):
        """带有标志：副作用在对话开始之前就出现了——
        该标志的存在是为了解决种族问题。"""
        preload_modules(fake_tool_module)

        imported = sys.modules[fake_tool_module]
        assert imported.REGISTRY == ["MyCustomTool"]

    def test_module_not_imported_without_flag(self, fake_tool_module):
        """合约伴侣：如果 `preload_modules` 没有被调用 (i.e. 的
        操作员忘记了 `--import-modules`），该模块保持未导入状态，并且其
        `register_tool` 样式的副作用永远不会运行。 这正是
        CLI 标志所要防止的破坏状态。
        """
        preload_modules(None)

        assert fake_tool_module not in sys.modules

    def test_import_error_is_logged_before_raising(self, caplog):
        """导入失败应记录模块名称和错误
        重新提高之前操作员诊断。"""
        with caplog.at_level(logging.ERROR):
            with pytest.raises(ModuleNotFoundError):
                preload_modules("no_such_module_xyz_2771")

        assert any(
            "no_such_module_xyz_2771" in r.message and "--import-modules" in r.message
            for r in caplog.records
        )


class TestExtendPythonPath:
    """测试 extend_python_path() — 自定义工具导入的推动者
    在源代码和二进制 (PyInstaller) 智能体-服务器构建中。"""

    def test_none_and_no_env_is_noop(self, monkeypatch):
        monkeypatch.delenv(_EXTRA_PYTHON_PATH_ENV, raising=False)
        original = sys.path.copy()
        extend_python_path(None)
        assert sys.path == original

    def test_empty_string_and_no_env_is_noop(self, monkeypatch):
        monkeypatch.delenv(_EXTRA_PYTHON_PATH_ENV, raising=False)
        original = sys.path.copy()
        extend_python_path("")
        assert sys.path == original

    def test_adds_directory_from_cli_arg(self, tmp_path, monkeypatch):
        monkeypatch.delenv(_EXTRA_PYTHON_PATH_ENV, raising=False)
        d = tmp_path / "custom_tools"
        d.mkdir()
        extend_python_path(str(d))
        assert str(d) in sys.path
        sys.path.remove(str(d))

    def test_adds_directory_from_env_var(self, tmp_path, monkeypatch):
        d = tmp_path / "env_tools"
        d.mkdir()
        monkeypatch.setenv(_EXTRA_PYTHON_PATH_ENV, str(d))
        extend_python_path(None)
        assert str(d) in sys.path
        sys.path.remove(str(d))

    def test_merges_cli_and_env(self, tmp_path, monkeypatch):
        d1 = tmp_path / "cli_tools"
        d2 = tmp_path / "env_tools"
        d1.mkdir()
        d2.mkdir()
        monkeypatch.setenv(_EXTRA_PYTHON_PATH_ENV, str(d2))
        extend_python_path(str(d1))
        assert str(d1) in sys.path
        assert str(d2) in sys.path
        sys.path.remove(str(d1))
        sys.path.remove(str(d2))

    def test_skips_nonexistent_dir_with_warning(self, tmp_path, monkeypatch, caplog):
        monkeypatch.delenv(_EXTRA_PYTHON_PATH_ENV, raising=False)
        bogus = str(tmp_path / "does_not_exist")
        with caplog.at_level(logging.WARNING):
            extend_python_path(bogus)
        assert bogus not in sys.path
        assert any("non-existent" in r.message for r in caplog.records)

    def test_deduplicates(self, tmp_path, monkeypatch):
        monkeypatch.delenv(_EXTRA_PYTHON_PATH_ENV, raising=False)
        d = tmp_path / "dup_tools"
        d.mkdir()
        extend_python_path(f"{d}{os.pathsep}{d}")
        count = sys.path.count(str(d))
        assert count == 1
        sys.path.remove(str(d))

    def test_skips_already_on_sys_path(self, tmp_path, monkeypatch):
        monkeypatch.delenv(_EXTRA_PYTHON_PATH_ENV, raising=False)
        d = tmp_path / "already_there"
        d.mkdir()
        abs_d = str(d.resolve())
        sys.path.insert(0, abs_d)
        before_count = sys.path.count(abs_d)
        extend_python_path(abs_d)
        assert sys.path.count(abs_d) == before_count
        sys.path.remove(abs_d)

    def test_multiple_dirs_via_pathsep(self, tmp_path, monkeypatch):
        monkeypatch.delenv(_EXTRA_PYTHON_PATH_ENV, raising=False)
        d1 = tmp_path / "tools_a"
        d2 = tmp_path / "tools_b"
        d1.mkdir()
        d2.mkdir()
        extend_python_path(f"{d1}{os.pathsep}{d2}")
        assert str(d1) in sys.path
        assert str(d2) in sys.path
        sys.path.remove(str(d1))
        sys.path.remove(str(d2))

    def test_enables_import_of_external_module(self, tmp_path, monkeypatch):
        """端到端：extend_python_path + importlib.import_module 有效
        对于放置在额外目录中的 .py 文件。"""
        monkeypatch.delenv(_EXTRA_PYTHON_PATH_ENV, raising=False)
        d = tmp_path / "ext_tools"
        d.mkdir()
        mod_name = "ext_test_tool_abc123"
        (d / f"{mod_name}.py").write_text("REGISTERED = True\n")

        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(mod_name)

        extend_python_path(str(d))
        try:
            mod = importlib.import_module(mod_name)
            assert mod.REGISTERED is True
        finally:
            sys.path.remove(str(d))
            sys.modules.pop(mod_name, None)

    def test_enables_preload_modules_integration(self, tmp_path, monkeypatch):
        """确认预期的工作流程：extend_python_path() 然后
        preload_modules() 成功导入外部工具模块。"""
        monkeypatch.delenv(_EXTRA_PYTHON_PATH_ENV, raising=False)
        d = tmp_path / "integration_tools"
        d.mkdir()
        mod_name = "integration_test_tool_xyz789"
        (d / f"{mod_name}.py").write_text(
            textwrap.dedent("""\
                TOOL_REGISTRY = []
                TOOL_REGISTRY.append("IntegrationTestTool")
            """)
        )

        extend_python_path(str(d))
        try:
            preload_modules(mod_name)
            imported = sys.modules[mod_name]
            assert imported.TOOL_REGISTRY == ["IntegrationTestTool"]
        finally:
            sys.path.remove(str(d))
            sys.modules.pop(mod_name, None)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "[::]"])
def test_get_internal_server_url_rewrites_wildcard_host(host):
    assert _get_internal_server_url(host, 4321) == "http://127.0.0.1:4321"


def test_get_internal_server_url_preserves_explicit_host():
    assert _get_internal_server_url("localhost", 4321) == "http://localhost:4321"


def test_get_internal_server_url_brackets_ipv6_host():
    assert _get_internal_server_url("fe80::1", 4321) == "http://[fe80::1]:4321"


class TestMainCheckBrowserOrdering:
    """验证 --check-browser 独立于 --import-modules 运行。"""

    def test_check_browser_exits_before_preload(self):
        """--check-browser 应在 preload_modules 之前短路
        运行，因此损坏的用户模块无法屏蔽浏览器检查。"""
        mock_result = MagicMock()
        mock_result.is_error = False

        mock_executor = MagicMock()
        mock_executor.return_value = mock_result

        with (
            patch("sys.argv", ["prog", "--check-browser", "--import-modules", "boom"]),
            patch("openhands.tools.preset.default.register_default_tools"),
            patch(
                "openhands.tools.browser_use.impl.BrowserToolExecutor",
                return_value=mock_executor,
            ),
            patch("openhands.agent_server.__main__.preload_modules") as mock_preload,
        ):
            from openhands.agent_server.__main__ import main

            with pytest.raises(SystemExit) as exc_info:
                main()

            # 浏览器检查成功→退出0
            assert exc_info.value.code == 0
            # preload_modules 必须已调用不
            mock_preload.assert_not_called()

    def test_main_sets_internal_server_url(self, monkeypatch):
        monkeypatch.delenv("OH_INTERNAL_SERVER_URL", raising=False)
        # 显式通配符绑定需要启用身份验证； 设置一个密钥，以便绑定主机防护允许 0.0.0.0，
        # 并且我们仍然对内部服务器 URL 执行通配符→环回重写。
        #
        monkeypatch.setenv("SESSION_API_KEY", "test-key-for-internal-url")

        with (
            patch("sys.argv", ["prog", "--host", "0.0.0.0", "--port", "4321"]),
            patch("openhands.agent_server.__main__.preload_modules"),
            patch("openhands.agent_server.__main__.LoggingServer") as mock_server_cls,
        ):
            mock_server_cls.return_value.run.side_effect = SystemExit(0)

            from openhands.agent_server.__main__ import main

            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        assert os.environ["OH_INTERNAL_SERVER_URL"] == "http://127.0.0.1:4321"


class TestMainBindHostGuard:
    """Agent Server 不得绑定所有没有身份验证的接口。"""

    def _no_key_env(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SESSION_API_KEY", raising=False)
        monkeypatch.delenv("OH_SESSION_API_KEYS_0", raising=False)
        cfg = tmp_path / "empty_config.json"
        cfg.write_text("{}")
        monkeypatch.setenv("OPENHANDS_AGENT_SERVER_CONFIG_PATH", str(cfg))

    def test_default_host_is_loopback_without_key(self, monkeypatch, tmp_path):
        """如果没有会话 API 密钥，则默认绑定主机为 127.0.0.1。"""
        self._no_key_env(monkeypatch, tmp_path)
        captured: dict = {}

        def capture_config(app, *, host, **kwargs):
            captured["host"] = host
            return MagicMock()

        with (
            patch("sys.argv", ["prog", "--port", "4321"]),
            patch("openhands.agent_server.__main__.preload_modules"),
            patch("openhands.agent_server.__main__._setup_crash_diagnostics"),
            patch("openhands.agent_server.__main__.LoggingServer") as mock_server,
            patch("openhands.agent_server.__main__.Config", side_effect=capture_config),
        ):
            mock_server.return_value.run.side_effect = SystemExit(0)
            from openhands.agent_server.__main__ import main

            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        assert captured["host"] == "127.0.0.1"

    def test_default_host_is_wildcard_with_key(self, monkeypatch, tmp_path):
        """配置会话 API 密钥后，默认绑定主机为 0.0.0.0。"""
        self._no_key_env(monkeypatch, tmp_path)
        monkeypatch.setenv("SESSION_API_KEY", "test-secret-123")
        captured: dict = {}

        def capture_config(app, *, host, **kwargs):
            captured["host"] = host
            return MagicMock()

        with (
            patch("sys.argv", ["prog", "--port", "4321"]),
            patch("openhands.agent_server.__main__.preload_modules"),
            patch("openhands.agent_server.__main__._setup_crash_diagnostics"),
            patch("openhands.agent_server.__main__.LoggingServer") as mock_server,
            patch("openhands.agent_server.__main__.Config", side_effect=capture_config),
        ):
            mock_server.return_value.run.side_effect = SystemExit(0)
            from openhands.agent_server.__main__ import main

            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        assert captured["host"] == "0.0.0.0"

    @pytest.mark.parametrize("wildcard", ["0.0.0.0", "::", "[::]"])
    def test_explicit_wildcard_warns_without_key(
        self, monkeypatch, tmp_path, wildcard, caplog
    ):
        """允许使用没有密钥的显式 --host <wildcard>，但会发出警告。"""
        self._no_key_env(monkeypatch, tmp_path)
        captured: dict = {}

        def capture_config(app, *, host, **kwargs):
            captured["host"] = host
            return MagicMock()

        with (
            patch("sys.argv", ["prog", "--host", wildcard, "--port", "4321"]),
            patch("openhands.agent_server.__main__.preload_modules"),
            patch("openhands.agent_server.__main__._setup_crash_diagnostics"),
            patch("openhands.agent_server.__main__.Config", side_effect=capture_config),
            patch("openhands.agent_server.__main__.LoggingServer") as mock_server,
            caplog.at_level(logging.WARNING, logger="openhands.agent_server.__main__"),
        ):
            mock_server.return_value.run.side_effect = SystemExit(0)
            from openhands.agent_server.__main__ import main

            with pytest.raises(SystemExit) as exc_info:
                main()

        # 允许（操作员明确选择）但警告。
        assert exc_info.value.code == 0
        assert captured["host"] == wildcard
        assert any("without a session API key" in r.message for r in caplog.records)

    def test_explicit_wildcard_allowed_with_key(self, monkeypatch, tmp_path):
        """允许使用带有密钥的显式 --host 0.0.0.0。"""
        self._no_key_env(monkeypatch, tmp_path)
        monkeypatch.setenv("SESSION_API_KEY", "test-secret-123")
        captured: dict = {}

        def capture_config(app, *, host, **kwargs):
            captured["host"] = host
            return MagicMock()

        with (
            patch("sys.argv", ["prog", "--host", "0.0.0.0", "--port", "4321"]),
            patch("openhands.agent_server.__main__.preload_modules"),
            patch("openhands.agent_server.__main__._setup_crash_diagnostics"),
            patch("openhands.agent_server.__main__.LoggingServer") as mock_server,
            patch("openhands.agent_server.__main__.Config", side_effect=capture_config),
        ):
            mock_server.return_value.run.side_effect = SystemExit(0)
            from openhands.agent_server.__main__ import main

            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        assert captured["host"] == "0.0.0.0"

    def test_explicit_loopback_allowed_without_key(self, monkeypatch, tmp_path):
        """允许不带密钥的显式 --host 127.0.0.1。"""
        self._no_key_env(monkeypatch, tmp_path)
        captured: dict = {}

        def capture_config(app, *, host, **kwargs):
            captured["host"] = host
            return MagicMock()

        with (
            patch("sys.argv", ["prog", "--host", "127.0.0.1", "--port", "4321"]),
            patch("openhands.agent_server.__main__.preload_modules"),
            patch("openhands.agent_server.__main__._setup_crash_diagnostics"),
            patch("openhands.agent_server.__main__.LoggingServer") as mock_server,
            patch("openhands.agent_server.__main__.Config", side_effect=capture_config),
        ):
            mock_server.return_value.run.side_effect = SystemExit(0)
            from openhands.agent_server.__main__ import main

            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        assert captured["host"] == "127.0.0.1"


def test_auth_enabled_reads_config_keys(monkeypatch, tmp_path):
    from openhands.agent_server.__main__ import _auth_enabled

    cfg = tmp_path / "config.json"
    monkeypatch.delenv("SESSION_API_KEY", raising=False)
    monkeypatch.delenv("OH_SESSION_API_KEYS_0", raising=False)
    monkeypatch.setenv("OPENHANDS_AGENT_SERVER_CONFIG_PATH", str(cfg))

    cfg.write_text("{}")
    assert _auth_enabled() is False

    cfg.write_text('{"session_api_keys": ["abc"]}')
    assert _auth_enabled() is True


def test_auth_enabled_reads_env_key(monkeypatch, tmp_path):
    from openhands.agent_server.__main__ import _auth_enabled

    cfg = tmp_path / "config.json"
    cfg.write_text("{}")
    monkeypatch.setenv("OPENHANDS_AGENT_SERVER_CONFIG_PATH", str(cfg))
    monkeypatch.delenv("OH_SESSION_API_KEYS_0", raising=False)
    monkeypatch.setenv("SESSION_API_KEY", "from-env")
    assert _auth_enabled() is True


def test_auth_enabled_ignores_empty_env_key(monkeypatch, tmp_path):
    from openhands.agent_server.__main__ import _auth_enabled

    cfg = tmp_path / "config.json"
    cfg.write_text("{}")
    monkeypatch.setenv("OPENHANDS_AGENT_SERVER_CONFIG_PATH", str(cfg))
    monkeypatch.delenv("SESSION_API_KEY", raising=False)
    monkeypatch.setenv("OH_SESSION_API_KEYS_0", "")
    assert _auth_enabled() is False


@pytest.mark.parametrize(
    ("config_json", "expected"),
    [
        ("{}", False),
        ('{"trust_forwarded_headers": false}', False),
        ('{"trust_forwarded_headers": true}', True),
    ],
)
def test_main_ties_uvicorn_proxy_headers_to_trust_forwarded_headers(
    monkeypatch, tmp_path, config_json, expected
):
    """uvicorn 仅在以下情况下重写来自 X-Forwarded-Proto 的请求方案：
    trust_forwarded_headers 打开，因此客户端无法更改 Canvas 桥在关闭时派生的原点。
    """
    cfg = tmp_path / "config.json"
    cfg.write_text(config_json)
    monkeypatch.setenv("OPENHANDS_AGENT_SERVER_CONFIG_PATH", str(cfg))
    monkeypatch.delenv("SESSION_API_KEY", raising=False)
    monkeypatch.delenv("OH_SESSION_API_KEYS_0", raising=False)
    captured: dict = {}

    def capture_config(app, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    with (
        patch("sys.argv", ["prog", "--port", "4321"]),
        patch("openhands.agent_server.__main__.preload_modules"),
        patch("openhands.agent_server.__main__._setup_crash_diagnostics"),
        patch("openhands.agent_server.__main__.LoggingServer") as mock_server,
        patch("openhands.agent_server.__main__.Config", side_effect=capture_config),
    ):
        mock_server.return_value.run.side_effect = SystemExit(0)
        from openhands.agent_server.__main__ import main

        with pytest.raises(SystemExit):
            main()

    assert captured["proxy_headers"] is expected
