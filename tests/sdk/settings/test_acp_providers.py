"""测试 ACP 提供者注册表。"""

from __future__ import annotations

import importlib
import warnings
from types import MappingProxyType
from typing import get_args

import pytest
from deprecation import DeprecatedWarning

from openhands.sdk.settings.acp_install_catalog import (
    PI_ACP_VERSION,
    PI_CODING_AGENT_VERSION,
)
from openhands.sdk.settings.acp_providers import (
    ACP_PROVIDERS,
    ACPModelOption,
    ACPProviderInfo,
    build_session_model_meta,
    detect_acp_provider_by_agent_name,
    detect_acp_provider_by_command,
    get_acp_provider,
)
from openhands.sdk.settings.model import ACPServerKind


class TestACPProviderInfo:
    def test_known_providers_are_registered(self):
        # 注册表个附加项不能无声，但那个使它无声的保护措施是
        # test_acp_server_kind_matches_registry_keys — 它将注册表与 ACPServerKind
        # Literal 连接起来，这是实际上需要发生的编辑。 在这里重申关键集只会让每个提供者
        # PR必须更新一个字面值，因此这断言了共享不变量。
        #
        assert ACP_PROVIDERS, "the registry must not be empty"
        for key, info in ACP_PROVIDERS.items():
            assert info.key == key, f"{key}: registry key does not match info.key"

    def test_all_entries_are_acp_provider_info(self):
        for info in ACP_PROVIDERS.values():
            assert isinstance(info, ACPProviderInfo)

    def test_default_commands_prefer_offline_cache(self):
        for info in ACP_PROVIDERS.values():
            assert info.default_command[:3] == ("npx", "-y", "--prefer-offline")

    def test_claude_code_metadata(self):
        info = ACP_PROVIDERS["claude-code"]
        assert info.key == "claude-code"
        assert info.display_name == "Claude Code"
        assert info.default_command[0] == "npx"
        assert "@agentclientprotocol/claude-agent-acp" in info.default_command[-1]
        assert info.api_key_env_var == "ANTHROPIC_API_KEY"
        assert info.base_url_env_var == "ANTHROPIC_BASE_URL"
        assert info.default_session_mode == "bypassPermissions"
        assert "claude-agent" in info.agent_name_patterns
        # 初始选择使用协议调用 — claude-智能体-ACP 忽略了会话-_meta 载荷 (#3654)，尽管它
        # 仍然以尽力而为的方式发送 (session_meta_key 以下)。 在 0.44.0 上，调用是
        # set_config_option。
        #
        assert info.supports_set_session_model is True
        assert info.supports_runtime_model_switch is True
        assert info.session_meta_key == "claudeCode"
        assert info.default_model == "opus[1m]"
        models = {model.id: model.label for model in info.available_models}
        assert models["opus[1m]"] == "Claude Opus (1M)"
        assert models["claude-opus-5"] == "Claude Opus 5"
        assert models["sonnet"] == "Claude Sonnet"
        assert models["haiku"] == "Claude Haiku"
        # 由智能体-服务器图像包装器公开的固定二进制文件。
        assert info.binary_name == "claude-agent-acp"
        assert info.data_dir_env_var == "CLAUDE_CONFIG_DIR"

    def test_codex_metadata(self):
        info = ACP_PROVIDERS["codex"]
        assert info.key == "codex"
        assert info.display_name == "Codex"
        assert "@agentclientprotocol/codex-acp" in info.default_command[-1]
        assert info.api_key_env_var == "OPENAI_API_KEY"
        assert info.base_url_env_var == "OPENAI_BASE_URL"
        assert info.default_session_mode == "agent-full-access"
        assert "codex-acp" in info.agent_name_patterns
        assert info.supports_set_session_model is True
        assert info.supports_runtime_model_switch is True
        assert info.session_meta_key is None
        assert info.default_model == "gpt-5.5"
        assert any(m.id == "gpt-5.6-sol" for m in info.available_models)
        assert any(m.id == "gpt-5.6-terra" for m in info.available_models)
        assert any(m.id == "gpt-5.6-luna" for m in info.available_models)
        assert any(m.id == "gpt-6-astra" for m in info.available_models)
        assert any(m.id == "gpt-5.5" for m in info.available_models)
        assert info.binary_name == "codex-acp"
        assert info.data_dir_env_var == "CODEX_HOME"

    def test_gemini_cli_metadata(self):
        info = ACP_PROVIDERS["gemini-cli"]
        assert info.key == "gemini-cli"
        assert info.display_name == "Gemini CLI"
        assert "--acp" in info.default_command
        assert info.api_key_env_var == "GEMINI_API_KEY"
        assert info.base_url_env_var == "GEMINI_BASE_URL"
        assert info.default_session_mode == "default"
        assert "gemini-cli" in info.agent_name_patterns
        assert info.supports_set_session_model is True
        assert info.supports_runtime_model_switch is True
        assert info.session_meta_key is None
        assert info.default_model == "auto"
        assert any(m.id == "auto" for m in info.available_models)
        # Gemini CLI 的 ACP 二进制文件只是 ``gemini``（``--acp`` 标志是一个尾随参数，在
        # 重写时由 resolve_acp_command 保留）。
        #
        assert info.binary_name == "gemini"
        # Gemini CLI 没有专用的配置目录变量，因此只有 HOME 重新定位它。
        assert info.data_dir_env_var == "HOME"

    def test_kimi_code_metadata(self):
        info = ACP_PROVIDERS["kimi-code"]
        assert info.key == "kimi-code"
        assert info.display_name == "Kimi Code"
        # 仅限作用域包：未作用域的 npm ``kimi-code`` 是一个第三方工具，还附带一个
        # ``kimi`` bin。
        #
        assert info.default_command[:3] == ("npx", "-y", "--prefer-offline")
        assert "@moonshot-ai/kimi-code@" in info.default_command[3]
        assert info.default_command[4] == "acp"
        assert info.api_key_env_var is None
        assert info.base_url_env_var == "KIMI_BASE_URL"
        assert info.default_session_mode == "yolo"
        assert "kimi" in info.agent_name_patterns
        assert info.supports_set_session_model is True
        assert info.supports_runtime_model_switch is True
        assert info.session_meta_key is None
        # 模型 ID 遵循凭据，而不是计划层，因此不会策划任何内容，并且 CLI 会解析其自己的
        # 默认值。 参见_UNCURATED_MODEL_PROVIDERS。
        #
        assert info.available_models == ()
        assert info.default_model is None
        # CLI 的 ACP 二进制就是 ``kimi``； ``acp`` 是一个尾随参数。
        assert info.binary_name == "kimi"
        assert info.data_dir_env_var == "KIMI_CODE_HOME"
        # 凭据是 config.toml 物化为 KIMI_CODE_HOME — 环境变量本身不验证任何内容。
        #
        assert [s.secret_name for s in info.file_secrets] == ["KIMI_CODE_CONFIG_TOML"]
        spec = info.file_secrets[0]
        assert spec.filename == "config.toml"
        assert spec.env_var == "KIMI_CODE_HOME"
        assert spec.env_points_to == "dir"

    def test_pi_metadata(self):
        info = ACP_PROVIDERS["pi"]
        assert info.key == "pi"
        assert info.display_name == "Pi"
        # pi-ACP 仅适应； 它会在 PATH 上生成单独固定的 `pi` 引擎，因此 npx 默认设置这两
        # 个包并运行 pi-ACP。
        #
        assert info.default_command == (
            "npx",
            "-y",
            "--prefer-offline",
            f"--package=pi-acp@{PI_ACP_VERSION}",
            f"--package=@earendil-works/pi-coding-agent@{PI_CODING_AGENT_VERSION}",
            "pi-acp",
        )
        assert info.api_key_env_var == "ANTHROPIC_API_KEY"
        # pi 从它自己的目录中获取它的基数 URL，而不是环境。
        assert info.base_url_env_var is None
        # pi-ACP 将 ACP 模式映射到思维层面，并且没有权限模式。
        assert info.default_session_mode is None
        assert info.agent_name_patterns == ("pi-acp",)
        assert info.supports_set_session_model is True
        assert info.supports_runtime_model_switch is True
        assert info.session_meta_key is None
        assert info.default_model is None
        assert info.binary_name == "pi-acp"
        assert info.data_dir_env_var == "HOME"
        assert [spec.secret_name for spec in info.file_secrets] == ["PI_AUTH_JSON"]

    def test_pi_credential_file_is_auth_json_in_the_config_dir(self):
        """PI_CODING_AGENT_DIR 命名 pi 从中读取 auth.json 的目录；
        settings.json同一目录下不进行身份验证。"""
        (spec,) = ACP_PROVIDERS["pi"].file_secrets
        assert spec.filename == "auth.json"
        assert spec.env_var == "PI_CODING_AGENT_DIR"
        assert spec.env_points_to == "dir"
        assert spec.subdir == "pi"

    def test_opencode_metadata(self):
        info = ACP_PROVIDERS["opencode"]
        assert info.key == "opencode"
        assert info.display_name == "OpenCode"
        assert info.default_command[:3] == ("npx", "-y", "--prefer-offline")
        assert "opencode-ai@" in info.default_command[3]
        # ``acp``是将CLI置于ACP模式的子命令； 当 resolve_acp_command 重写固定的二进制文
        # 件时，它被保留为尾随参数。
        #
        assert info.default_command[4] == "acp"
        assert info.api_key_env_var == "OPENCODE_API_KEY"
        # OpenCode Zen 从模型目录中解析其端点，因此没有 base-URL 覆盖变量。
        #
        assert info.base_url_env_var is None
        # OpenCode 的唯一模式是 ``build`` 和 ``plan``。
        assert info.default_session_mode == "build"
        assert "opencode" in info.agent_name_patterns
        assert info.supports_set_session_model is True
        assert info.supports_runtime_model_switch is True
        # session/new 忽略 _meta 模型选择。
        assert info.session_meta_key is None
        assert info.default_model == "opencode/big-pickle"
        model_ids = [m.id for m in info.available_models]
        assert "opencode/big-pickle" in model_ids
        assert "opencode/claude-opus-5" in model_ids
        # 一个免费层 ID，这是唯一一种无需密钥即可使用的 ID。
        assert "opencode/nemotron-3-ultra-free" in model_ids
        assert info.binary_name == "opencode"
        # OPENCODE_CONFIG_DIR 仅重定位配置文件； 身份验证、会话和缓存遵循 XDG 目录，该目
        # 录回退到 HOME。
        #
        assert info.data_dir_env_var == "HOME"
        # OPENCODE_AUTH_CONTENT 携带身份验证存储，因此没有凭据文件可实现。
        #
        assert info.file_secrets == ()

    def test_provider_info_is_frozen(self):
        info = ACP_PROVIDERS["claude-code"]
        with pytest.raises((AttributeError, TypeError)):
            info.key = "mutated"  # type: ignore[misc]

    def test_default_command_is_tuple(self):
        for key, info in ACP_PROVIDERS.items():
            assert isinstance(info.default_command, tuple), (
                f"{key}: default_command must be a tuple"
            )

    def test_acp_providers_is_read_only(self):
        assert isinstance(ACP_PROVIDERS, MappingProxyType)
        with pytest.raises(TypeError):
            ACP_PROVIDERS["new-provider"] = ACP_PROVIDERS["claude-code"]  # type: ignore[index]


class TestGetACPProvider:
    def test_returns_info_for_known_keys(self):
        for key in ACP_PROVIDERS:
            result = get_acp_provider(key)
            assert result is not None
            assert result.key == key

    def test_returns_none_for_custom(self):
        assert get_acp_provider("custom") is None

    def test_returns_none_for_unknown(self):
        assert get_acp_provider("nonexistent-provider") is None


class TestDetectACPProviderByAgentName:
    def test_detects_claude_code_by_agent_name(self):
        info = detect_acp_provider_by_agent_name("claude-agent-acp v0.29.0")
        assert info is not None
        assert info.key == "claude-code"

    def test_detects_codex_by_agent_name(self):
        info = detect_acp_provider_by_agent_name("codex-acp")
        assert info is not None
        assert info.key == "codex"

    def test_detects_gemini_cli_by_agent_name(self):
        info = detect_acp_provider_by_agent_name("gemini-cli 0.38.0")
        assert info is not None
        assert info.key == "gemini-cli"

    def test_detects_kimi_code_by_agent_name(self):
        # ``kimi acp``报告agentInfo.name“Kimi代码CLI”。
        info = detect_acp_provider_by_agent_name("Kimi Code CLI")
        assert info is not None
        assert info.key == "kimi-code"

    def test_detects_opencode_by_agent_name(self):
        # ``opencode acp`` 报告 agentInfo.name“OpenCode”。
        info = detect_acp_provider_by_agent_name("OpenCode")
        assert info is not None
        assert info.key == "opencode"

    def test_case_insensitive_detection(self):
        assert detect_acp_provider_by_agent_name("CLAUDE-AGENT-ACP") is not None
        assert detect_acp_provider_by_agent_name("Gemini-CLI") is not None

    def test_returns_none_for_unknown_agent_name(self):
        assert detect_acp_provider_by_agent_name("some-unknown-agent") is None

    def test_returns_none_for_empty_string(self):
        assert detect_acp_provider_by_agent_name("") is None


class TestDetectACPProviderByCommand:
    def test_detects_each_provider_from_default_command(self):
        for key, info in ACP_PROVIDERS.items():
            detected = detect_acp_provider_by_command(list(info.default_command))
            # 身份，而不仅仅是匹配的键：detect_acp_provider_by_command 必须解析回完全相
            # 同的 ACP_PROVIDERS 条目。
            #
            assert detected is info, key

    def test_tolerates_version_pin(self):
        info = detect_acp_provider_by_command(
            ["npx", "-y", "@google/gemini-cli@0.43.0", "--acp"]
        )
        assert info is not None
        assert info.key == "gemini-cli"

    def test_tolerates_absolute_path_form(self):
        info = detect_acp_provider_by_command(
            ["/usr/local/bin/node", "/opt/node_modules/.bin/codex-acp"]
        )
        assert info is not None
        assert info.key == "codex"

    def test_detects_kimi_code_by_command(self):
        # 故意不固定版本：检测与包名称匹配，因此客户端可以发送任何版本。
        #
        info = detect_acp_provider_by_command(
            ["npx", "-y", "@moonshot-ai/kimi-code@0.39.1", "acp"]
        )
        assert info is not None
        assert info.key == "kimi-code"
        info = detect_acp_provider_by_command(["/opt/acp-wrappers/kimi", "acp"])
        assert info is not None
        assert info.key == "kimi-code"

    def test_returns_none_for_custom_command(self):
        assert detect_acp_provider_by_command(["my-custom-acp", "serve"]) is None

    def test_returns_none_for_empty_command(self):
        assert detect_acp_provider_by_command([]) is None

    def test_rejects_incidental_substring_in_custom_command(self):
        # 普通子字符串匹配会将这些错误归因于法典； 基本名称+前缀规则拒绝它们（基本名称以
        # “my-”/"not-").开头
        #
        assert detect_acp_provider_by_command(["my-codex-acp-wrapper"]) is None
        assert detect_acp_provider_by_command(["/opt/shims/not-codex-acp"]) is None

    def test_prefix_match_accepts_provider_basename_prefix(self):
        # 以 * 开头的模式 * 被视为该提供程序（镜像“claude-智能体”必须如何匹配“claude-智
        # 能体-ACP”包）。
        #
        info = detect_acp_provider_by_command(["@acme/codex-acp-shim"])
        assert info is not None and info.key == "codex"


class TestProviderRegistryConsistency:
    """验证注册表内部一致。"""

    def test_every_provider_has_non_empty_default_command(self):
        for key, info in ACP_PROVIDERS.items():
            assert info.default_command, f"{key}: default_command must not be empty"

    def test_every_provider_has_agent_name_patterns(self):
        for key, info in ACP_PROVIDERS.items():
            assert info.agent_name_patterns, (
                f"{key}: agent_name_patterns must not be empty"
            )

    def test_session_mode_is_a_real_id_or_absent(self):
        """模式 ID 的范围仅限于其自己的服务器，因此唯一值得的
        断言注册表侧是记录的id是可用的id。

        两个提供者共享一个值，这没什么意义——``default`` 是几个ACP 服务器提供的模式，
        为第二个提供者选择它是一个正确的记录，而不是碰撞。 是否服务器
        接受 id，检查时可以：与运行中的服务器进行比较，在tests/sdk/agent/
        test_acp_conformance.py.
        """
        for key, info in ACP_PROVIDERS.items():
            mode = info.default_session_mode
            assert mode is None or (isinstance(mode, str) and mode.strip()), (
                f"{key}: default_session_mode must be a non-empty id or None"
            )

    def test_session_mode_is_a_non_empty_string_or_none(self):
        """``None`` 跳过 ``session/set_mode`` 调用； 空字符串会
        逐字发送并被服务器拒绝。"""
        for key, info in ACP_PROVIDERS.items():
            assert (
                info.default_session_mode is None or info.default_session_mode.strip()
            ), (  # noqa: E501
                f"{key}: default_session_mode must be None or non-blank"
            )

    def test_session_modes_are_distinct(self):
        modes = [
            info.default_session_mode
            for info in ACP_PROVIDERS.values()
            if info.default_session_mode is not None
        ]
        assert len(modes) == len(set(modes)), "each provider should use a unique mode"

    def test_detect_returns_matching_provider_for_all_registered_patterns(self):
        """每个注册的模式都应该解析回其自己的提供者。"""
        for key, info in ACP_PROVIDERS.items():
            for pattern in info.agent_name_patterns:
                detected = detect_acp_provider_by_agent_name(pattern)
                assert detected is not None, (
                    f"pattern {pattern!r} did not match any provider"
                )
                assert detected.key == key, (
                    f"pattern {pattern!r} matched {detected.key!r}, expected {key!r}"
                )

    def test_acp_server_kind_matches_registry_keys(self):
        # ACPServerKind (the ACPAgentSettings.acp_server discriminator) 是一个手动维护的
        #  Literal，不是从 ACP_PROVIDERS 中衍生的 —— 一个没有另一个的提供者，要么无法通
        # 过设置选择（Literal 缺失它），要么在运行时无法识别 (注册表缺失它）。 "custom"
        # 是它接受的唯一一个非注册表值。
        #
        assert set(get_args(ACPServerKind)) == set(ACP_PROVIDERS) | {"custom"}


# 其模型 ID 取决于用户提供的凭据的提供者，因此静态列表不可能是正确的。 与计划层差异不同
# ，策划列表已经容忍了计划层差异（它们是建议，而不是访问检查）。
#
_UNCURATED_MODEL_PROVIDERS = {
    # 帐户登录提供 ``kimi-code/*`` 个别名； config.toml 提供者提供用户指定的任何别名。
    # 对于没有帐户登录的任何人来说，静态列表不仅是不完整的，而且是错误的。
    #
    "kimi-code",
}


class TestProviderModelLists:
    """验证策划的 ``available_models`` / ``default_model`` 字段。"""

    def test_every_builtin_provider_has_available_models(self):
        for key, info in ACP_PROVIDERS.items():
            if key in _UNCURATED_MODEL_PROVIDERS:
                assert not info.available_models, (
                    f"{key}: now curates models — remove it from "
                    "_UNCURATED_MODEL_PROVIDERS"
                )
                assert info.default_model is None, (
                    f"{key}: an uncurated provider must leave default_model "
                    "None so the CLI resolves its own default"
                )
                continue
            assert info.available_models, f"{key}: available_models must not be empty"

    def test_every_uncurated_provider_is_a_real_registry_key(self):
        assert _UNCURATED_MODEL_PROVIDERS <= set(ACP_PROVIDERS)

    def test_available_models_entries_are_model_options(self):
        for info in ACP_PROVIDERS.values():
            for option in info.available_models:
                assert isinstance(option, ACPModelOption)
                assert option.id, "model option id must not be empty"
                assert option.label, "model option label must not be empty"

    def test_model_ids_unique_within_provider(self):
        for key, info in ACP_PROVIDERS.items():
            ids = [m.id for m in info.available_models]
            assert len(ids) == len(set(ids)), f"{key}: duplicate model ids"

    def test_default_model_is_one_of_available_models(self):
        for key, info in ACP_PROVIDERS.items():
            if info.default_model is None:
                continue
            ids = {m.id for m in info.available_models}
            assert info.default_model in ids, (
                f"{key}: default_model {info.default_model!r} not in available_models"
            )

    def test_model_option_is_frozen(self):
        option = ACP_PROVIDERS["claude-code"].available_models[0]
        with pytest.raises((AttributeError, TypeError)):
            option.id = "mutated"  # type: ignore[misc]


class TestModelListDeprecation:
    @pytest.fixture(autouse=True)
    def _released(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "openhands.sdk.utils.deprecation._current_version", lambda: "1.54.0"
        )

    @pytest.mark.parametrize("name", ["available_models", "default_model"])
    def test_reading_a_curated_model_field_warns(self, name: str) -> None:
        with pytest.warns(DeprecatedWarning, match=f"ACPProviderInfo.{name}"):
            getattr(ACP_PROVIDERS["codex"], name)

    def test_other_uses_of_a_provider_do_not_warn(self) -> None:
        info = ACP_PROVIDERS["codex"]
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert info.display_name == "Codex"
            assert info == get_acp_provider("codex")
            hash(info)
            repr(info)

    @pytest.mark.parametrize("module", ["openhands.sdk", "openhands.sdk.settings"])
    def test_importing_the_model_option_warns(self, module: str) -> None:
        with pytest.warns(DeprecatedWarning, match="ACPModelOption"):
            option = importlib.import_module(module).ACPModelOption
        assert option is ACPModelOption


class TestBuildSessionModelMeta:
    def test_empty_when_no_model(self):
        assert build_session_model_meta("claude-agent-acp", None) == {}
        assert build_session_model_meta("claude-agent-acp", "") == {}

    def test_claude_uses_meta_key(self):
        result = build_session_model_meta("claude-agent-acp v0.29.0", "claude-opus-4")
        assert result == {"claudeCode": {"options": {"model": "claude-opus-4"}}}

    def test_codex_returns_empty(self):
        result = build_session_model_meta("codex-acp", "gpt-4o")
        assert result == {}

    def test_gemini_returns_empty(self):
        result = build_session_model_meta("gemini-cli 0.38.0", "gemini-2.0-flash")
        assert result == {}

    def test_unknown_agent_returns_empty(self):
        result = build_session_model_meta("unknown-agent", "some-model")
        assert result == {}


class TestACPFileSecrets:
    """注册表声明保留文件内容凭据机密
    从磁盘上的文件进行身份验证的提供程序（问题＃1020）。"""

    def test_claude_code_has_no_file_secrets(self):
        # Claude Code 仅通过环境变量（token / API key）进行身份验证。
        assert ACP_PROVIDERS["claude-code"].file_secrets == ()

    def test_codex_auth_json_spec(self):
        specs = ACP_PROVIDERS["codex"].file_secrets
        assert len(specs) == 1
        spec = specs[0]
        assert spec.secret_name == "CODEX_AUTH_JSON"
        assert spec.filename == "auth.json"
        assert spec.env_var == "CODEX_HOME"
        assert spec.subdir == "codex"
        assert spec.env_points_to == "dir"

    def test_gemini_vertex_sa_spec(self):
        specs = ACP_PROVIDERS["gemini-cli"].file_secrets
        assert len(specs) == 1
        spec = specs[0]
        assert spec.secret_name == "GOOGLE_APPLICATION_CREDENTIALS_JSON"
        assert spec.filename == "gcloud-credentials.json"
        assert spec.env_var == "GOOGLE_APPLICATION_CREDENTIALS"
        assert spec.subdir == "gemini-cli"
        assert spec.env_points_to == "file"
        # Vertex 需要 SA JSON 旁边的项目 + 位置。
        assert spec.warn_if_unset == ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")

    def test_default_acp_file_secrets_aggregates_all_providers(self):
        from openhands.sdk.settings.acp_providers import default_acp_file_secrets

        specs = default_acp_file_secrets()
        assert {s.secret_name for s in specs} == {
            "CODEX_AUTH_JSON",
            "GOOGLE_APPLICATION_CREDENTIALS_JSON",
            "KIMI_CODE_CONFIG_TOML",
            "PI_AUTH_JSON",
        }
        # ACP_PROVIDERS 注册顺序中的确定性连接（codex、gemini-CLI、kimi-code、pi）——下游
        # 调用者可以依赖内置特性的稳定排序。
        #
        assert specs == (
            ACP_PROVIDERS["codex"].file_secrets
            + ACP_PROVIDERS["gemini-cli"].file_secrets
            + ACP_PROVIDERS["kimi-code"].file_secrets
            + ACP_PROVIDERS["pi"].file_secrets
        )

    def test_file_secret_subdirs_are_unique_across_providers(self):
        # 每个规范的子目录是共享的每个会话 acp/ root 下的一个文件夹（参见
        # ACPFileSecretSpec.subdir）； 冲突会让两个提供商的凭据文件互相覆盖。
        #
        subdirs = [
            spec.subdir for info in ACP_PROVIDERS.values() for spec in info.file_secrets
        ]
        assert len(subdirs) == len(set(subdirs)), subdirs

    def test_file_secret_spec_is_frozen(self):
        from pydantic import ValidationError

        from openhands.sdk.settings.acp_providers import ACPFileSecretSpec

        spec = ACPFileSecretSpec(
            secret_name="X", filename="x.json", env_var="X_HOME", subdir="x"
        )
        with pytest.raises(ValidationError):
            spec.secret_name = "Y"  # type: ignore[misc]

    def test_file_secret_spec_rejects_path_traversal(self):
        from pydantic import ValidationError

        from openhands.sdk.settings.acp_providers import ACPFileSecretSpec

        # 文件名必须是裸基名。
        with pytest.raises(ValidationError):
            ACPFileSecretSpec(
                secret_name="X", filename="../escape.json", env_var="X", subdir="x"
            )
        with pytest.raises(ValidationError):
            ACPFileSecretSpec(
                secret_name="X", filename="a/b.json", env_var="X", subdir="x"
            )
        # subdir 不得转义 ACP 根目录。
        with pytest.raises(ValidationError):
            ACPFileSecretSpec(
                secret_name="X", filename="x.json", env_var="X", subdir="../up"
            )
        with pytest.raises(ValidationError):
            ACPFileSecretSpec(
                secret_name="X", filename="x.json", env_var="X", subdir="/abs"
            )
        # “。” / 空格会将文件直接放入共享 acp/ 根目录中。
        for bad in (".", "  ", " . "):
            with pytest.raises(ValidationError):
                ACPFileSecretSpec(
                    secret_name="X", filename="x.json", env_var="X", subdir=bad
                )
