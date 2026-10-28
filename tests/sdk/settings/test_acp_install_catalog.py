"""测试无依赖项 ACP npm 安装目录。"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from openhands.sdk.settings.acp_install_catalog import (
    ACP_INSTALL_CATALOG,
    CLAUDE_AGENT_ACP_VERSION,
    CODEX_ACP_VERSION,
    DEFAULT_PREINSTALLED_ACP_PROVIDERS,
    GEMINI_CLI_VERSION,
    PI_ACP_VERSION,
    PI_CODING_AGENT_VERSION,
    ACPInstallSpec,
    ACPPackagePin,
    _main,
    render_docker_install_plan,
)
from openhands.sdk.settings.acp_providers import ACP_PROVIDERS


CATALOG_PY = __import__(
    "openhands.sdk.settings.acp_install_catalog", fromlist=["__file__"]
).__file__


class TestACPPackagePin:
    def test_pinned_is_name_at_version(self):
        pin = ACPPackagePin(name="@scope/pkg", version="1.2.3")
        assert pin.pinned == "@scope/pkg@1.2.3"

    def test_is_frozen(self):
        pin = ACPPackagePin(name="pkg", version="1.0.0")
        with pytest.raises((AttributeError, TypeError)):
            pin.version = "2.0.0"  # type: ignore[misc]


class TestACPInstallSpecNpxCommand:
    def test_single_package_no_trailing_args(self):
        spec = ACPInstallSpec(
            key="codex",
            packages=(ACPPackagePin("@agentclientprotocol/codex-acp", "1.10.0"),),
            binary_name="codex-acp",
        )
        assert spec.npx_command() == (
            "npx",
            "-y",
            "--prefer-offline",
            "@agentclientprotocol/codex-acp@1.10.0",
        )

    def test_single_package_with_trailing_args(self):
        spec = ACPInstallSpec(
            key="gemini-cli",
            packages=(ACPPackagePin("@google/gemini-cli", "0.46.0"),),
            binary_name="gemini",
            trailing_args=("--acp",),
        )
        assert spec.npx_command() == (
            "npx",
            "-y",
            "--prefer-offline",
            "@google/gemini-cli@0.46.0",
            "--acp",
        )

    def test_multi_package_uses_package_flags_and_entry_binary(self):
        # Pi 形状需要：一个 ACP 适配器及其引擎包，两者均固定，并按位置调用适配器的 bin。
        #
        spec = ACPInstallSpec(
            key="pi",
            packages=(
                ACPPackagePin("pi-acp", "0.1.0"),
                ACPPackagePin("@earendil-works/pi-coding-agent", "0.2.0"),
            ),
            binary_name="pi-acp",
        )
        assert spec.npx_command() == (
            "npx",
            "-y",
            "--prefer-offline",
            "--package=pi-acp@0.1.0",
            "--package=@earendil-works/pi-coding-agent@0.2.0",
            "pi-acp",
        )


class TestPiInstallSpec:
    """Pi 是唯一拥有两个独立引脚的注册提供商：`pi-acp`
    适应 ACP 并产生一个单独安装的 `pi` 引擎关闭 PATH。"""

    def test_pins_both_the_adapter_and_the_engine(self):
        spec = ACP_INSTALL_CATALOG["pi"]
        assert [(p.name, p.version) for p in spec.packages] == [
            ("pi-acp", PI_ACP_VERSION),
            ("@earendil-works/pi-coding-agent", PI_CODING_AGENT_VERSION),
        ]
        assert spec.binary_name == "pi-acp"
        assert spec.trailing_args == ()

    def test_adapter_is_listed_first(self):
        """`test_acp_conformance_probe` 将 `packages[0].version` 与
        `agentInfo.version` 服务器报告 — 这是适配器的报告。 重新排序会默默地与引擎的
        版本进行比较。
        """
        spec = ACP_INSTALL_CATALOG["pi"]
        assert spec.packages[0].name == spec.binary_name == "pi-acp"

    def test_install_plan_installs_both_but_wraps_only_the_adapter(self):
        """`pi` 永远不会由 OpenHands 直接启动 - pi-ACP 生成它，并且
        适配器的包装器将 $ACP_NODE_DIR/bin 放在 PATH 上，因此第二个包装器将是自重。
        """
        packages, wrapper_bins = render_docker_install_plan(["pi"])
        assert packages == [
            f"pi-acp@{PI_ACP_VERSION}",
            f"@earendil-works/pi-coding-agent@{PI_CODING_AGENT_VERSION}",
        ]
        assert wrapper_bins == ["pi-acp"]


class TestACPInstallCatalogMatchesACPProviders:
    """ACP_PROVIDERS 源自此目录的 default_command/binary_name；
    验证每个 npm 可安装提供程序的两者保持同步。"""

    def test_catalog_keys_match_registered_npm_providers(self):
        assert set(ACP_INSTALL_CATALOG) == set(ACP_PROVIDERS)

    def test_default_commands_are_derived_from_catalog(self):
        for key, info in ACP_PROVIDERS.items():
            assert info.default_command == ACP_INSTALL_CATALOG[key].npx_command()

    def test_binary_names_are_derived_from_catalog(self):
        for key, info in ACP_PROVIDERS.items():
            assert info.binary_name == ACP_INSTALL_CATALOG[key].binary_name

    def test_pinned_versions_unchanged(self):
        assert CLAUDE_AGENT_ACP_VERSION == "0.63.0"
        assert CODEX_ACP_VERSION == "2.2.2"
        assert GEMINI_CLI_VERSION == "0.46.0"


class TestDefaultPreinstalledACPProviders:
    def test_preserves_todays_default_image_contents(self):
        assert DEFAULT_PREINSTALLED_ACP_PROVIDERS == (
            "claude-code",
            "codex",
            "gemini-cli",
        )

    def test_every_default_provider_is_in_the_catalog(self):
        for key in DEFAULT_PREINSTALLED_ACP_PROVIDERS:
            assert key in ACP_INSTALL_CATALOG


class TestRenderDockerInstallPlan:
    def test_default_set(self):
        packages, wrapper_bins = render_docker_install_plan(
            DEFAULT_PREINSTALLED_ACP_PROVIDERS
        )
        assert packages == [
            f"@agentclientprotocol/claude-agent-acp@{CLAUDE_AGENT_ACP_VERSION}",
            f"@agentclientprotocol/codex-acp@{CODEX_ACP_VERSION}",
            f"@google/gemini-cli@{GEMINI_CLI_VERSION}",
        ]
        assert wrapper_bins == ["claude-agent-acp", "codex-acp", "gemini"]

    def test_empty_selection_installs_nothing(self):
        assert render_docker_install_plan([]) == ([], [])

    def test_subset_selection(self):
        packages, wrapper_bins = render_docker_install_plan(["codex"])
        assert packages == [f"@agentclientprotocol/codex-acp@{CODEX_ACP_VERSION}"]
        assert wrapper_bins == ["codex-acp"]

    def test_unknown_key_raises_with_valid_keys_listed(self):
        with pytest.raises(ValueError, match="bogus") as exc_info:
            render_docker_install_plan(["codex", "bogus"])
        message = str(exc_info.value)
        assert "claude-code" in message
        assert "codex" in message
        assert "gemini-cli" in message

    def test_dedupes_shared_packages_preserving_first_seen_order(self):
        shared = ACPPackagePin("@acme/shared-engine", "9.9.9")
        catalog = {
            "a": ACPInstallSpec(key="a", packages=(shared,), binary_name="a-bin"),
            "b": ACPInstallSpec(
                key="b",
                packages=(ACPPackagePin("@acme/b-only", "1.0.0"), shared),
                binary_name="b-bin",
            ),
        }
        packages, wrapper_bins = render_docker_install_plan(["a", "b"], catalog=catalog)
        assert packages == ["@acme/shared-engine@9.9.9", "@acme/b-only@1.0.0"]
        assert wrapper_bins == ["a-bin", "b-bin"]


class TestACPInstallCatalogCLI:
    """Dockerfile的ACP-提供者阶段COPies了这个模块，并运行它
    直接使用系统 python3 — 进行精确的练习入口。"""

    def test_prints_shell_eval_able_plan(self, capsys):
        code = _main(["claude-code,codex"])
        assert code == 0
        out = capsys.readouterr().out
        assert out.splitlines() == [
            'PACKAGES="@agentclientprotocol/claude-agent-acp@'
            f"{CLAUDE_AGENT_ACP_VERSION} @agentclientprotocol/codex-acp@"
            f'{CODEX_ACP_VERSION}"',
            'WRAPPER_BINS="claude-agent-acp codex-acp"',
        ]

    def test_empty_string_installs_nothing(self, capsys):
        code = _main([""])
        assert code == 0
        out = capsys.readouterr().out
        assert out.splitlines() == ['PACKAGES=""', 'WRAPPER_BINS=""']

    def test_unknown_provider_fails_clearly(self, capsys):
        code = _main(["bogus"])
        assert code == 1
        err = capsys.readouterr().err
        assert "bogus" in err

    def test_runs_standalone_with_no_dependencies(self):
        """回归守护 Dockerfile 的 `python3 <file> ...`
        invocation: 这必须只与 stdlib 一起工作
        sys.path, since the acp-providers stage is a bare python image
        未安装 OpenHands 软件包（或 Pydantic）。
        """
        result = subprocess.run(
            [sys.executable, "-S", CATALOG_PY, "claude-code"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [
            f'PACKAGES="@agentclientprotocol/claude-agent-acp@{CLAUDE_AGENT_ACP_VERSION}"',
            'WRAPPER_BINS="claude-agent-acp"',
        ]

    def test_output_survives_a_real_shell_eval_multi_package(self):
        """回归测试 Dockerfile 遇到的确切错误：`eval`
        重新标记其在空格上的参数，因此是一个不带引号的多词
        `PACKAGES=a b c` 解析为“分配 PACKAGES=a，然后使用 arg c 运行命令 b”（退出 127
        ），而不是一个空格分隔的分配。 通过
         `sh -c 'eval "$PLAN"; ...'` 运行 CLI 的真实标准输出，与 Dockerfile 的
        `PLAN=$(...) || exit 1; eval "$PLAN"` 完全相同。
        """
        plan = subprocess.run(
            [sys.executable, "-S", CATALOG_PY, "claude-code,codex,gemini-cli"],
            capture_output=True,
            text=True,
        ).stdout
        result = subprocess.run(
            ["sh", "-c", 'eval "$PLAN"; echo "$PACKAGES"; echo "$WRAPPER_BINS"'],
            capture_output=True,
            text=True,
            env={**os.environ, "PLAN": plan},
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [
            f"@agentclientprotocol/claude-agent-acp@{CLAUDE_AGENT_ACP_VERSION} "
            f"@agentclientprotocol/codex-acp@{CODEX_ACP_VERSION} "
            f"@google/gemini-cli@{GEMINI_CLI_VERSION}",
            "claude-agent-acp codex-acp gemini",
        ]
