import json
import shutil
import warnings
from typing import Any

import pytest
from deprecation import DeprecatedWarning
from pydantic import SecretStr, ValidationError

from openhands.agent_server.models import StartConversationRequest
from openhands.sdk import (
    LLM,
    ACPAgentSettings,
    Agent,
    AgentContext,
    AgentSettingsBase,
    ConversationSettings,
    OpenHandsAgentSettings,
    SettingProminence,
    Tool,
    default_agent_settings,
    export_agent_settings_schema,
    validate_agent_settings,
)
from openhands.sdk.agent.acp_agent import ACP_SENTINEL_USAGE_ID, ACPAgent
from openhands.sdk.context.condenser import LLMSummarizingCondenser, NoOpCondenser
from openhands.sdk.critic.base import IterativeRefinementConfig
from openhands.sdk.critic.impl.api import APIBasedCritic
from openhands.sdk.mcp.config import MCPServer, coerce_mcp_config, dump_mcp_config
from openhands.sdk.secret import StaticSecret
from openhands.sdk.security.confirmation_policy import AlwaysConfirm, ConfirmRisky
from openhands.sdk.security.llm_analyzer import LLMSecurityAnalyzer
from openhands.sdk.settings import (
    AGENT_SETTINGS_SCHEMA_VERSION,
    CondenserSettings,
    LLMSummarizingCondenserSettings,
    NoOpCondenserSettings,
    VerificationSettings,
    apply_agent_settings_diff,
)
from openhands.sdk.settings.model import (
    ACPServerKind,
    _agent_settings_discriminator,
    _condenser_settings_discriminator,
    _migrate_agent_settings_payload,
    export_settings_schema,
)
from openhands.sdk.workspace import LocalWorkspace


# LLM 上具有 ``exclude=True`` 的字段不应出现在模式中。
_LLM_EXCLUDED_FIELDS = {name for name, fi in LLM.model_fields.items() if fi.exclude}


# ---------------------------------------------------------------------------
# 模式导出 — 每个变体
# ---------------------------------------------------------------------------


def test_llm_agent_settings_export_schema_groups_sections() -> None:
    schema = OpenHandsAgentSettings.export_schema()

    assert schema.model_name == "OpenHandsAgentSettings"
    section_keys = [section.key for section in schema.sections]
    assert section_keys == [
        "general",
        "llm",
        "agent_context",
        "condenser",
        "verification",
    ]

    sections = {s.key: s for s in schema.sections}

    # -- 一般部分（顶级标量字段）--
    general_fields = {f.key: f for f in sections["general"].fields}
    assert set(general_fields) == {
        "agent",
        "tools",
        "enable_classify_and_switch_llm_tool",
        "active_meta_profile",
        "tool_concurrency_limit",
        "mcp_config",
    }
    assert general_fields["agent"].default == "CodeActAgent"
    assert general_fields["agent"].prominence is SettingProminence.MAJOR
    assert general_fields["tools"].value_type == "array"
    # None = "server default toolset" (materialized by create_agent, #3978).
    assert general_fields["tools"].default is None
    assert general_fields["tools"].prominence is SettingProminence.MAJOR
    assert general_fields["tool_concurrency_limit"].value_type == "integer"
    assert general_fields["tool_concurrency_limit"].default == 1
    assert (
        general_fields["tool_concurrency_limit"].prominence is SettingProminence.MAJOR
    )

    # -- 法学硕士部分 --
    llm_fields = {f.key: f for f in sections["llm"].fields}
    expected_llm_keys = {
        f"llm.{name}" for name in LLM.model_fields if name not in _LLM_EXCLUDED_FIELDS
    }
    assert set(llm_fields) == expected_llm_keys

    assert llm_fields["llm.model"].value_type == "string"
    assert llm_fields["llm.model"].prominence is SettingProminence.CRITICAL
    assert llm_fields["llm.max_input_tokens"].default is None
    assert llm_fields["llm.max_output_tokens"].default is None
    assert llm_fields["llm.api_key"].label == "API Key"
    assert llm_fields["llm.api_key"].secret is True
    assert llm_fields["llm.api_key"].prominence is SettingProminence.CRITICAL
    assert llm_fields["llm.base_url"].prominence is SettingProminence.MAJOR

    # 排除字段不得出现
    assert "llm.fallback_strategy" not in llm_fields
    assert "llm.retry_listener" not in llm_fields

    # -- agent_context 部分（仅带注释的字段表面）--
    assert sections["agent_context"].label == "Memory"
    ac_fields = {f.key: f for f in sections["agent_context"].fields}
    assert set(ac_fields) == {"agent_context.load_memory"}
    load_memory = ac_fields["agent_context.load_memory"]
    assert load_memory.label == "Persistent memory"
    assert load_memory.value_type == "boolean"
    assert load_memory.default is False
    assert load_memory.prominence is SettingProminence.MAJOR

    # -- 上下文压缩器部分 --
    condenser_fields = {f.key: f for f in sections["condenser"].fields}
    assert (
        condenser_fields["condenser.enabled"].prominence is SettingProminence.CRITICAL
    )
    assert condenser_fields["condenser.condenser_kind"].default == "llm_summarizing"
    assert [
        choice.value for choice in condenser_fields["condenser.condenser_kind"].choices
    ] == ["llm_summarizing", "no_op"]
    assert condenser_fields["condenser.max_size"].depends_on == ["condenser.enabled"]
    assert condenser_fields["condenser.max_size"].prominence is SettingProminence.MINOR
    assert condenser_fields["condenser.max_tokens"].default is None
    assert condenser_fields["condenser.max_tokens"].depends_on == ["condenser.enabled"]
    assert (
        condenser_fields["condenser.max_tokens"].prominence is SettingProminence.MINOR
    )

    # -- 验证部分（仅限批评设置）--
    v_fields = {f.key: f for f in sections["verification"].fields}
    assert v_fields["verification.critic_mode"].value_type == "string"
    assert [c.value for c in v_fields["verification.critic_mode"].choices] == [
        "finish_and_message",
        "all_actions",
    ]
    assert (
        v_fields["verification.enable_iterative_refinement"].prominence
        is SettingProminence.CRITICAL
    )

    # API 评论键必须在模式中作为 CRITICAL 和机密字段呈现，这些字段依赖于 critic_enabled
    # — 这是 GUI 用来渲染受切换控制的隐藏输入的关键。
    #
    critic_api_key = v_fields["verification.critic_api_key"]
    assert critic_api_key.secret is True
    assert critic_api_key.value_type == "string"
    assert critic_api_key.prominence is SettingProminence.CRITICAL
    assert critic_api_key.depends_on == ["verification.critic_enabled"]


def test_acp_agent_settings_export_schema_has_acp_section() -> None:
    schema = ACPAgentSettings.export_schema()
    assert schema.model_name == "ACPAgentSettings"

    section_keys = [section.key for section in schema.sections]
    assert "acp" in section_keys
    assert "llm" not in section_keys

    sections = {s.key: s for s in schema.sections}
    acp_fields = {f.key: f for f in sections["acp"].fields}
    assert set(acp_fields) == {
        "acp_server",
        "acp_command",
        "acp_args",
        "acp_model",
        "acp_session_mode",
        "acp_prompt_timeout",
        "acp_startup_timeout",
    }
    # 服务器选择器+模型都很关键——用户选择服务器然后模型。 对于高级用户来说，原始命令是一
    # 个较小的覆盖。
    #
    assert acp_fields["acp_server"].prominence is SettingProminence.CRITICAL
    assert acp_fields["acp_model"].prominence is SettingProminence.CRITICAL
    assert acp_fields["acp_command"].prominence is SettingProminence.MINOR

    # mcp_config 作为单个对象字段公开（与 OpenHands 变体匹配），而不是扩展为嵌套的每服务
    # 器字段。 服务器在会话创建时转发到 ACP 子进程。
    #
    general_fields = {f.key: f for f in sections["general"].fields}
    assert "mcp_config" in general_fields
    assert general_fields["mcp_config"].prominence is SettingProminence.MINOR


def test_conversation_settings_export_schema_groups_sections() -> None:
    schema = ConversationSettings.export_schema()

    assert schema.model_name == "ConversationSettings"
    section_keys = [section.key for section in schema.sections]
    assert section_keys == ["general", "verification", "runtime"]

    sections = {s.key: s for s in schema.sections}
    general_fields = {f.key: f for f in sections["general"].fields}
    assert set(general_fields) == {"max_iterations"}
    assert general_fields["max_iterations"].default == 500
    assert general_fields["max_iterations"].prominence is SettingProminence.MAJOR

    verification_fields = {f.key: f for f in sections["verification"].fields}
    assert set(verification_fields) == {
        "confirmation_mode",
        "security_analyzer",
    }
    assert verification_fields["confirmation_mode"].default is False
    assert (
        verification_fields["confirmation_mode"].prominence
        is SettingProminence.CRITICAL
    )
    assert verification_fields["security_analyzer"].default == "llm"
    assert verification_fields["security_analyzer"].choices[0].value == "llm"
    assert verification_fields["security_analyzer"].depends_on == ["confirmation_mode"]

    runtime_fields = {f.key: f for f in sections["runtime"].fields}
    assert [c.value for c in runtime_fields["default_runtime"].choices] == [
        "local",
        "worktree",
        "docker",
    ]
    assert runtime_fields["default_runtime"].default == "local"
    # 每个运行时的选项仅在该运行时为默认时显示。
    assert {key: f.depends_on for key, f in runtime_fields.items()} == {
        "default_runtime": [],
        "worktree_base": ["default_runtime=worktree"],
        "worktree_base_ref": ["default_runtime=worktree", "worktree_base=ref"],
        "worktree_branch_prefix": ["default_runtime=worktree"],
        "container_memory": ["default_runtime=docker"],
        "container_cpus": ["default_runtime=docker"],
        "container_browser": ["default_runtime=docker"],
    }
    assert [c.value for c in runtime_fields["worktree_base"].choices] == [
        "default_branch",
        "head",
        "ref",
    ]
    assert runtime_fields["worktree_branch_prefix"].default == "openhands/"
    assert runtime_fields["container_browser"].default is True
    # 第一层：页面有几个字段，None值得隐藏在“全部”后面。
    assert {f.prominence for f in runtime_fields.values()} == {SettingProminence.MAJOR}


def test_runtime_settings_stay_out_of_create_request() -> None:
    # 它们是 Canvas 启动器默认设置； create_request() 调用者（例如 OpenAI 网关）在进程内
    # 启动，并且必须保持在本地运行。
    #
    settings = ConversationSettings(
        default_runtime="worktree",
        worktree_base="head",
        container_memory="4g",
    )

    request = settings.create_request(
        StartConversationRequest,
        agent=Agent(llm=LLM(model="test-model", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir="/tmp"),
    )

    assert request.worktree is False
    assert request.conversation_runtime is None
    assert request.worktree_options is None
    assert request.container is None


@pytest.mark.parametrize(
    "values",
    [
        # “其他参考”需要参考本身。
        {"worktree_base": "ref"},
        # git would read a leading "-" as an option.
        {"worktree_base": "ref", "worktree_base_ref": "--orphan"},
        {"worktree_branch_prefix": "-b"},
    ],
)
def test_unusable_worktree_settings_are_refused(values: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        ConversationSettings.model_validate(values)


@pytest.mark.parametrize(
    ("field", "value", "valid"),
    [
        ("container_memory", "512m", True),
        ("container_memory", "4 GB", True),
        ("container_memory", "2GiB", True),
        # `docker run --memory` 拒绝这些，因此每次启动都会失败。
        ("container_memory", "lots", False),
        ("container_memory", "", False),
        ("container_cpus", 0.01, True),
        ("container_cpus", 0.001, False),
    ],
)
def test_container_limits_are_checked_when_saved(
    field: str, value: str | float, valid: bool
) -> None:
    if valid:
        ConversationSettings.model_validate({field: value})
    else:
        with pytest.raises(ValidationError):
            ConversationSettings.model_validate({field: value})


def test_export_settings_schema_remains_backward_compatible():
    """export_settings_schema产生相同结构的模式。"""
    schema_openhands = export_settings_schema(OpenHandsAgentSettings)
    assert any(s.key == "general" for s in schema_openhands.sections)
    assert any(s.key == "llm" for s in schema_openhands.sections)

    schema_acp = export_settings_schema(ACPAgentSettings)
    assert any(s.key == "acp" for s in schema_acp.sections)


def test_conversation_settings_validates_observability_metadata() -> None:
    settings = ConversationSettings(observability_metadata={"repo": "OpenHands/sdk"})
    assert settings.observability_metadata == {"repo": "OpenHands/sdk"}

    with pytest.raises(ValidationError):
        ConversationSettings(observability_metadata={"": "missing-key"})

    with pytest.raises(ValidationError):
        ConversationSettings(observability_metadata=[])  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        ConversationSettings(observability_tags=[1, 2])  # type: ignore[list-item]


def test_conversation_settings_model_dump_roundtrip() -> None:
    settings = ConversationSettings(
        max_iterations=42,
        confirmation_mode=True,
        security_analyzer="none",
    )

    restored = ConversationSettings.model_validate(settings.model_dump(mode="json"))

    assert restored == settings


def test_conversation_settings_create_request() -> None:
    settings = ConversationSettings(
        max_iterations=77,
        confirmation_mode=True,
        security_analyzer="llm",
    )
    workspace = LocalWorkspace(working_dir="/tmp")
    agent = OpenHandsAgentSettings(llm=LLM(model="test-model")).create_agent()

    request = settings.create_request(
        StartConversationRequest,
        agent=agent,
        workspace=workspace,
    )

    assert isinstance(request, StartConversationRequest)
    assert request.workspace == workspace
    assert request.max_iterations == 77
    assert isinstance(request.confirmation_policy, ConfirmRisky)
    assert isinstance(request.security_analyzer, LLMSecurityAnalyzer)

    overridden_request = settings.create_request(
        StartConversationRequest,
        agent=agent,
        workspace=workspace,
        max_iterations=5,
        confirmation_policy=AlwaysConfirm(),
        security_analyzer=None,
    )

    assert overridden_request.max_iterations == 5
    assert isinstance(overridden_request.confirmation_policy, AlwaysConfirm)
    assert overridden_request.security_analyzer is None


def test_conversation_settings_create_request_with_acp_agent() -> None:
    settings = ConversationSettings(
        max_iterations=77,
        confirmation_mode=True,
        security_analyzer="none",
    )
    workspace = LocalWorkspace(working_dir="/tmp")
    agent = ACPAgent(acp_command=["echo", "test"])

    request = settings.create_request(
        StartConversationRequest,
        agent=agent,
        workspace=workspace,
    )

    assert isinstance(request, StartConversationRequest)
    assert request.workspace == workspace
    assert request.max_iterations == 77
    assert isinstance(request.confirmation_policy, AlwaysConfirm)
    assert request.security_analyzer is None


def test_acp_create_request_lifts_context_secrets_into_request_secrets() -> None:
    # 端到端：agent_context.secrets（根据提供商的环境变量名称键）提供的凭证被
    # create_request（将它们注入到state.secret_registry上的智能体服务器）注入到request.
    # secrets，从_start_acp_server那里注入到子进程的环境。 llm.api_key 不再被读取（已弃
    # 用，#3632）。
    #
    agent = ACPAgentSettings(
        acp_server="claude-code",
        agent_context=AgentContext(
            secrets={
                "ANTHROPIC_API_KEY": StaticSecret(value=SecretStr("sk-provider")),
                "GITHUB_TOKEN": StaticSecret(value=SecretStr("ghp_x")),
            }
        ),
    ).create_agent()

    request = ConversationSettings().create_request(
        StartConversationRequest,
        agent=agent,
        workspace=LocalWorkspace(working_dir="/tmp"),
    )

    assert set(request.secrets) == {"ANTHROPIC_API_KEY", "GITHUB_TOKEN"}
    assert request.secrets["ANTHROPIC_API_KEY"].get_value() == "sk-provider"
    assert request.secrets["GITHUB_TOKEN"].get_value() == "ghp_x"


# ---------------------------------------------------------------------------
# 模式导出 — 联合（受歧视联合）
# ---------------------------------------------------------------------------


def test_export_agent_settings_schema_emits_variant_tagged_sections() -> None:
    schema = export_agent_settings_schema()
    assert schema.model_name == "AgentSettings"

    by_keyvariant = {(s.key, s.variant): s for s in schema.sections}

    # 共享常规部分包含仅限 LLM 的顶级字段，带有字段级变量 =“OpenHands”标签（因此它们隐藏
    # 在 ACP 页面上）。
    #
    general = by_keyvariant.get(("general", None))
    assert general is not None
    general_keys = {f.key for f in general.fields}
    assert general_keys == {
        "agent",
        "tools",
        "enable_classify_and_switch_llm_tool",
        "active_meta_profile",
        "tool_concurrency_limit",
        "mcp_config",
    }
    # 没有 agent_kind 字段 - 每个变体都有自己的设置页面，并在保存时注入鉴别器。
    #
    assert "agent_kind" not in general_keys
    for f in general.fields:
        assert f.variant == "openhands", (
            f"expected field {f.key} variant=openhands, got {f.variant}"
        )

    # LLM-变体部分。
    assert ("llm", "openhands") in by_keyvariant
    assert ("condenser", "openhands") in by_keyvariant
    assert ("verification", "openhands") in by_keyvariant

    # 内存部分仅是 OpenHands：GUI 按键匹配部分并忽略变体，因此标记两个变体将渲染切换两次
    # 。
    #
    assert ("agent_context", "openhands") in by_keyvariant
    assert ("agent_context", "acp") not in by_keyvariant

    # ACP-变体部分。
    acp_section = by_keyvariant.get(("acp", "acp"))
    assert acp_section is not None
    acp_keys = {f.key for f in acp_section.fields}
    assert "acp_server" in acp_keys
    assert "acp_command" in acp_keys
    assert "acp_model" in acp_keys

    # acp_server 是关键的用户可见字段（该命令是次要覆盖）。
    #
    server_field = next(f for f in acp_section.fields if f.key == "acp_server")
    assert server_field.prominence is SettingProminence.CRITICAL
    server_choices = {c.value for c in server_field.choices}
    assert server_choices == {
        "claude-code",
        "codex",
        "gemini-cli",
        "kimi-code",
        "pi",
        "opencode",
        "custom",
    }

    command_field = next(f for f in acp_section.fields if f.key == "acp_command")
    assert command_field.prominence is SettingProminence.MINOR

    assert ("llm", "acp") not in by_keyvariant


# ---------------------------------------------------------------------------
# 鉴别器 + 验证
# ---------------------------------------------------------------------------


def test_default_agent_settings_returns_openhands_variant() -> None:
    s = default_agent_settings()
    assert isinstance(s, OpenHandsAgentSettings)
    assert s.agent_kind == "openhands"


def test_condenser_settings_discriminator_declared_on_base():
    """CondenserSettings 基声明 condenser_kind。

    判别器直接访问它，无需 getattr。
    """
    base = CondenserSettings(enabled=True)
    assert base.condenser_kind == "llm_summarizing"
    assert _condenser_settings_discriminator(base) == "llm_summarizing"

    summarizing = LLMSummarizingCondenserSettings(enabled=True)
    assert summarizing.condenser_kind == "llm_summarizing"
    assert _condenser_settings_discriminator(summarizing) == "llm_summarizing"

    noop = NoOpCondenserSettings(enabled=True)
    assert noop.condenser_kind == "no_op"
    assert _condenser_settings_discriminator(noop) == "no_op"


def test_agent_settings_discriminator_declared_on_base():
    """AgentSettingsBase 声明 agent_kind。

    判别器直接访问它，无需 getattr。
    """
    base = AgentSettingsBase()
    assert base.agent_kind == "openhands"
    assert _agent_settings_discriminator(base) == "openhands"

    openhands_settings = OpenHandsAgentSettings()
    assert openhands_settings.agent_kind == "openhands"
    assert _agent_settings_discriminator(openhands_settings) == "openhands"

    acp_settings = ACPAgentSettings()
    assert acp_settings.agent_kind == "acp"
    assert _agent_settings_discriminator(acp_settings) == "acp"


def test_validate_agent_settings_defaults_to_openhands_when_discriminator_missing() -> (
    None
):
    """现有的已持久化载荷早于 ``agent_kind`` — 它们必须往返。"""
    v = validate_agent_settings({"llm": {"model": "test-model"}})
    assert isinstance(v, OpenHandsAgentSettings)
    assert v.llm.model == "test-model"


def test_validate_agent_settings_dispatches_on_agent_kind() -> None:
    openhands = validate_agent_settings(
        {"agent_kind": "openhands", "llm": {"model": "m"}}
    )
    assert isinstance(openhands, OpenHandsAgentSettings)
    assert openhands.agent_kind == "openhands"

    legacy_llm = validate_agent_settings(
        {"agent_kind": "llm", "llm": {"model": "legacy-model"}}
    )
    assert isinstance(legacy_llm, OpenHandsAgentSettings)
    assert legacy_llm.agent_kind == "openhands"
    assert legacy_llm.llm.model == "legacy-model"

    acp = validate_agent_settings(
        {
            "agent_kind": "acp",
            "acp_command": ["npx", "-y", "claude-agent-acp"],
            "acp_model": "claude-opus-4-6",
        }
    )
    assert isinstance(acp, ACPAgentSettings)
    assert acp.acp_command == ["npx", "-y", "claude-agent-acp"]


def test_validate_agent_settings_migrates_v0_llm_payload() -> None:
    settings = validate_agent_settings({"llm": {"model": "test-model"}})

    assert isinstance(settings, OpenHandsAgentSettings)
    assert settings.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert settings.agent_kind == "openhands"
    assert settings.llm.model == "test-model"


def test_validate_agent_settings_dispatches_current_acp_payload() -> None:
    settings = validate_agent_settings(
        {
            "schema_version": 1,
            "agent_kind": "acp",
            "acp_command": ["npx", "-y", "claude-agent-acp"],
            "acp_model": "claude-opus-4-6",
        }
    )

    assert isinstance(settings, ACPAgentSettings)
    # 迁移保持 ACP 载荷完整，同时碰撞 schema_version。
    assert settings.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert settings.acp_command == ["npx", "-y", "claude-agent-acp"]


def test_validate_agent_settings_canonicalizes_legacy_llm_kind() -> None:
    """v1载荷与已弃用``agent_kind: 'llm'``被迁移到
    读取时的规范 ``'openhands'`` 判别器。"""
    settings = validate_agent_settings(
        {
            "schema_version": 1,
            "agent_kind": "llm",
            "llm": {"model": "legacy-model"},
        }
    )

    assert isinstance(settings, OpenHandsAgentSettings)
    assert settings.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert settings.agent_kind == "openhands"
    assert settings.llm.model == "legacy-model"


def test_validate_agent_settings_drops_legacy_verification_fields() -> None:
    settings = validate_agent_settings(
        {
            "schema_version": 2,
            "agent_kind": "openhands",
            "verification": {
                "critic_enabled": True,
                "confirmation_mode": True,
                "security_analyzer": "llm",
            },
        }
    )

    assert isinstance(settings, OpenHandsAgentSettings)
    assert settings.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    verification = settings.verification.model_dump(mode="json")
    assert verification["critic_enabled"] is True
    assert "confirmation_mode" not in verification
    assert "security_analyzer" not in verification


def test_validate_agent_settings_migrates_legacy_openhands_proxy_llm() -> None:
    settings = validate_agent_settings(
        {
            "schema_version": 3,
            "agent_kind": "openhands",
            "llm": {
                "model": "litellm_proxy/claude-opus-5",
                "base_url": "https://llm-proxy.app.all-hands.dev/",
            },
        }
    )

    assert isinstance(settings, OpenHandsAgentSettings)
    assert settings.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert settings.llm.model == "openhands/claude-opus-5"
    assert settings.llm.base_url is None


def test_validate_agent_settings_migrates_v5_modify_params() -> None:
    """已持久化 ``llm.modify_params``（在 v1.47.0 中删除）在加载时被删除。"""
    settings = validate_agent_settings(
        {
            "schema_version": 5,
            "agent_kind": "openhands",
            "llm": {
                "model": "gpt-4o",
                "modify_params": True,
            },
        }
    )

    assert isinstance(settings, OpenHandsAgentSettings)
    assert settings.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert settings.llm.model == "gpt-4o"
    assert "modify_params" not in settings.llm.model_dump()


@pytest.fixture
def acp_llm_deprecated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "openhands.sdk.utils.deprecation._current_version", lambda: "1.51.0"
    )


@pytest.mark.usefixtures("acp_llm_deprecated")
def test_validate_agent_settings_migrates_v6_acp_llm_without_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecatedWarning)
        settings = validate_agent_settings(
            {
                "schema_version": 6,
                "agent_kind": "acp",
                "acp_model": "claude-opus-4-7",
                "llm": {"model": "gpt-5.6", "api_key": "sk-stored"},
            }
        )

    assert isinstance(settings, ACPAgentSettings)
    assert settings.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert "llm" not in settings.model_fields_set


def test_validate_agent_settings_migrates_v6_keeps_openhands_llm() -> None:
    settings = validate_agent_settings(
        {"schema_version": 6, "agent_kind": "openhands", "llm": {"model": "gpt-4o"}}
    )

    assert isinstance(settings, OpenHandsAgentSettings)
    assert settings.llm.model == "gpt-4o"


def test_validate_agent_settings_migrates_legacy_mcp_auth_shapes() -> None:
    settings = validate_agent_settings(
        {
            "schema_version": 4,
            "agent_kind": "openhands",
            "mcp_config": {
                "mcpServers": {
                    "oauth-top-level": {
                        "url": "https://mcp.oauth.example.com/mcp",
                        "unknown_secret": "drop-me",
                        "auth": "oauth",
                        "authentication": {
                            "type": "oauth",
                            "client_auth_method": "none",
                        },
                        "oauth_credentials": {
                            "mcp-oauth-token": {
                                "https://mcp.oauth.example.com/mcp/tokens": {
                                    "value": {
                                        "access_token": "access-secret",
                                        "refresh_token": "refresh-secret",
                                    }
                                }
                            },
                            "mcp-oauth-client-info": {
                                "https://mcp.oauth.example.com/mcp/client_info": {
                                    "value": {
                                        "client_id": "client-id",
                                        "client_secret": "client-secret",
                                    }
                                }
                            },
                            "mcp-oauth-token-expiry": {
                                "https://mcp.oauth.example.com/mcp/token_expiry": {
                                    "value": {"expires_at": 1234.5},
                                    "expires_at": 9999.0,
                                }
                            },
                        },
                    },
                    "oauth-auth-field": {
                        "url": "https://mcp.auth.example.com/mcp",
                        "auth": {
                            "strategy": "oauth2",
                            "credentials": {
                                "mcp-oauth-token": {
                                    "https://mcp.auth.example.com/mcp/tokens": {
                                        "value": {"access_token": "field-secret"}
                                    }
                                }
                            },
                        },
                    },
                    "fastmcp-fields": {
                        "url": "https://mcp.fields.example.com/mcp",
                        "type": "streamable-http",
                        "description": "Fields server",
                        "icon": "https://example.com/icon.png",
                        "timeout": 10,
                        "sse_read_timeout": 20,
                        "keep_alive": True,
                        "unknown_secret": "drop-me",
                    },
                    "bearer": {
                        "url": "https://mcp.bearer.example.com/mcp",
                        "auth": "bearer-secret",
                    },
                    "api-key": {
                        "url": "https://mcp.api.example.com/mcp",
                        "api_key": "api-secret",
                    },
                    "authorization": {
                        "url": "https://mcp.header.example.com/mcp",
                        "headers": {
                            "Authorization": "Bearer header-secret",
                            "X-Other": "other",
                        },
                    },
                    "sse": {
                        "url": "https://mcp.linear.app/sse",
                        "transport": "sse",
                        "auth": {"strategy": "bearer", "value": "linear-secret"},
                    },
                }
            },
        }
    )

    assert isinstance(settings, OpenHandsAgentSettings)
    assert settings.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    servers = dump_mcp_config(settings.mcp_config)

    assert servers["oauth-top-level"]["auth"] == {
        "strategy": "oauth2",
        "authentication": {"type": "oauth", "client_auth_method": "none"},
        "state": {
            "tokens": {
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
            },
            "client_info": {
                "client_id": "client-id",
                "client_secret": "client-secret",
            },
            "token_expires_at": 1234.5,
        },
    }
    assert "oauth_credentials" not in servers["oauth-top-level"]
    assert "authentication" not in servers["oauth-top-level"]
    assert "unknown_secret" not in servers["oauth-top-level"]

    assert servers["fastmcp-fields"] == {
        "url": "https://mcp.fields.example.com/mcp",
        "transport": "streamable-http",
        "description": "Fields server",
        "icon": "https://example.com/icon.png",
        "timeout": 10.0,
        "sse_read_timeout": 20.0,
        "keep_alive": True,
    }

    assert servers["oauth-auth-field"]["auth"] == {
        "strategy": "oauth2",
        "state": {"tokens": {"access_token": "field-secret"}},
    }
    assert servers["bearer"]["auth"] == {
        "strategy": "bearer",
        "value": "bearer-secret",
    }
    assert servers["api-key"]["auth"] == {
        "strategy": "api_key",
        "value": "api-secret",
    }
    assert servers["authorization"]["auth"] == {
        "strategy": "bearer",
        "value": "header-secret",
    }
    assert servers["authorization"]["headers"] == {"X-Other": "other"}
    assert "sse" not in servers
    assert servers["shttp"] == {
        "url": "https://mcp.linear.app/mcp",
        "auth": {"strategy": "bearer", "value": "linear-secret"},
    }


def test_validate_agent_settings_migrates_mcp_type_to_transport() -> None:
    settings = validate_agent_settings(
        {
            "schema_version": 4,
            "agent_kind": "openhands",
            "mcp_config": {
                "http": {
                    "url": "https://mcp.example.com/mcp",
                    "type": "streamable-http",
                },
                "shttp-alias": {
                    "url": "https://mcp.alias.example.com/mcp",
                    "type": "shttp",
                },
            },
        }
    )

    assert isinstance(settings, OpenHandsAgentSettings)
    assert settings.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert dump_mcp_config(settings.mcp_config) == {
        "http": {
            "url": "https://mcp.example.com/mcp",
            "transport": "streamable-http",
        },
        "shttp-alias": {
            "url": "https://mcp.alias.example.com/mcp",
            "transport": "http",
        },
    }


def test_openhands_mcp_config_reject_unknown_server_fields() -> None:
    with pytest.raises(ValidationError):
        OpenHandsAgentSettings.model_validate(
            {
                "mcp_config": {
                    "server": {
                        "url": "https://mcp.example.com/mcp",
                        "unknown_secret": "not-a-datamodel-field",
                    }
                }
            }
        )


def test_current_agent_settings_reject_legacy_mcp_wrapper_without_migration() -> None:
    with pytest.raises(ValidationError):
        validate_agent_settings(
            {
                "schema_version": AGENT_SETTINGS_SCHEMA_VERSION,
                "agent_kind": "openhands",
                "mcp_config": {
                    "mcpServers": {"server": {"url": "https://mcp.example.com/mcp"}}
                },
            }
        )


def test_validate_agent_settings_mcp_linear_migration_does_not_duplicate() -> None:
    settings = validate_agent_settings(
        {
            "schema_version": 4,
            "agent_kind": "openhands",
            "mcp_config": {
                "mcpServers": {
                    "sse": {
                        "url": "https://mcp.linear.app/sse",
                        "transport": "sse",
                        "auth": {"strategy": "bearer", "value": "old-secret"},
                    },
                    "shttp": {
                        "url": "https://mcp.linear.app/mcp",
                        "auth": {"strategy": "bearer", "value": "manual-secret"},
                    },
                }
            },
        }
    )

    assert isinstance(settings, OpenHandsAgentSettings)
    assert dump_mcp_config(settings.mcp_config) == {
        "shttp": {
            "url": "https://mcp.linear.app/mcp",
            "auth": {"strategy": "bearer", "value": "manual-secret"},
        }
    }


def test_validate_agent_settings_rejects_newer_schema_version() -> None:
    with pytest.raises(
        ValueError,
        match=f"newer than supported version {AGENT_SETTINGS_SCHEMA_VERSION}",
    ):
        validate_agent_settings(
            {"schema_version": AGENT_SETTINGS_SCHEMA_VERSION + 1, "llm": {"model": "m"}}
        )


def test_openhands_agent_settings_from_persisted_migrates_legacy_payloads() -> None:
    v0 = OpenHandsAgentSettings.from_persisted({"llm": {"model": "v0-model"}})
    assert isinstance(v0, OpenHandsAgentSettings)
    assert v0.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert v0.agent_kind == "openhands"
    assert v0.llm.model == "v0-model"

    v1 = OpenHandsAgentSettings.from_persisted(
        {
            "schema_version": 1,
            "agent_kind": "llm",
            "llm": {"model": "legacy-model"},
        }
    )
    assert isinstance(v1, OpenHandsAgentSettings)
    assert v1.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert v1.agent_kind == "openhands"
    assert v1.llm.model == "legacy-model"

    v2 = OpenHandsAgentSettings.from_persisted(
        {
            "schema_version": 2,
            "agent_kind": "openhands",
            "verification": {
                "critic_enabled": True,
                "confirmation_mode": True,
                "security_analyzer": "llm",
            },
        }
    )
    assert isinstance(v2, OpenHandsAgentSettings)
    assert v2.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert v2.verification.critic_enabled is True
    verification = v2.verification.model_dump(mode="json")
    assert "confirmation_mode" not in verification
    assert "security_analyzer" not in verification


def test_acp_agent_settings_from_persisted_returns_acp_subtype() -> None:
    settings = ACPAgentSettings.from_persisted(
        {
            "schema_version": 1,
            "agent_kind": "acp",
            "acp_command": ["echo", "test"],
            "acp_model": "claude-opus-4-6",
        }
    )

    assert type(settings) is ACPAgentSettings
    assert settings.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert settings.acp_command == ["echo", "test"]


def test_openhands_agent_settings_from_persisted_rejects_current_llm_kind() -> None:
    with pytest.raises(ValidationError):
        OpenHandsAgentSettings.from_persisted(
            {
                "schema_version": AGENT_SETTINGS_SCHEMA_VERSION,
                "agent_kind": "llm",
                "llm": {"model": "legacy-model"},
            }
        )


def test_agent_settings_from_persisted_current_payload_matches_model_validate() -> None:
    payload = OpenHandsAgentSettings(llm=LLM(model="current-model")).model_dump(
        mode="json"
    )
    original_payload = json.loads(json.dumps(payload))

    settings = OpenHandsAgentSettings.from_persisted(payload)

    assert settings == OpenHandsAgentSettings.model_validate(payload)
    assert payload == original_payload


def test_agent_settings_from_persisted_preserves_validated_instance_secrets() -> None:
    settings = OpenHandsAgentSettings(
        llm=LLM(model="current-model", api_key=SecretStr("sk-test-key"))
    )

    restored = OpenHandsAgentSettings.from_persisted(settings)

    assert restored is settings
    assert isinstance(restored.llm.api_key, SecretStr)
    assert restored.llm.api_key.get_secret_value() == "sk-test-key"


def test_agent_settings_from_persisted_decrypts_mcp_secrets() -> None:
    from openhands.sdk.utils.cipher import Cipher

    cipher = Cipher(secret_key="test-encryption-key")
    settings = OpenHandsAgentSettings(
        mcp_config=coerce_mcp_config(
            {
                "github": {
                    "command": "uvx",
                    "args": ["mcp-server-github"],
                    "env": {"GITHUB_TOKEN": "ghp-test-token"},
                    "headers": {"X-API-Token": "tok-test-token"},
                }
            }
        )
    )
    persisted = settings.model_dump(mode="json", context={"cipher": cipher})

    restored = OpenHandsAgentSettings.from_persisted(
        persisted, context={"cipher": cipher}
    )

    restored_mcp = dump_mcp_config(restored.mcp_config)
    assert restored_mcp["github"]["env"] == {"GITHUB_TOKEN": "ghp-test-token"}
    assert restored_mcp["github"]["headers"] == {"X-API-Token": "tok-test-token"}


def test_openhands_agent_settings_from_persisted_matches_union_validator() -> None:
    payload = {
        "schema_version": 1,
        "agent_kind": "llm",
        "llm": {"model": "legacy-model"},
    }

    from_persisted_settings = OpenHandsAgentSettings.from_persisted(payload)
    union_settings = validate_agent_settings(payload)

    # agent_context.current_datetime默认为now()； 排除它，以便比较对验证之间的微秒不敏感
    # 。
    #
    volatile = {"agent_context": {"current_datetime"}}
    assert from_persisted_settings.model_dump(
        exclude=volatile
    ) == union_settings.model_dump(exclude=volatile)


def test_agent_settings_from_persisted_rejects_malformed_payload() -> None:
    with pytest.raises(ValidationError):
        OpenHandsAgentSettings.from_persisted(
            {
                "schema_version": AGENT_SETTINGS_SCHEMA_VERSION,
                "agent_kind": "openhands",
                "llm": "not-an-llm-settings-payload",
            }
        )


def test_conversation_settings_from_persisted_migrates_v0_payload() -> None:
    settings = ConversationSettings.from_persisted({"max_iterations": 42})

    assert settings.schema_version == 1
    assert settings.max_iterations == 42


def test_conversation_settings_from_persisted_rejects_newer_schema_version() -> None:
    with pytest.raises(ValueError, match="newer than supported version 1"):
        ConversationSettings.from_persisted({"schema_version": 2})


# ---------------------------------------------------------------------------
# create_agent — LLM variant
# ---------------------------------------------------------------------------


def test_llm_create_agent_uses_settings_llm_and_tools() -> None:
    llm = LLM(model="test-model")
    tools = [Tool(name="TerminalTool")]
    settings = OpenHandsAgentSettings(llm=llm, tools=tools)
    agent = settings.create_agent()
    assert isinstance(agent, Agent)
    assert agent.llm is llm
    assert agent.tools == tools
    assert "SwitchLLMTool" not in agent.include_default_tools


def test_llm_create_agent_defaults_tool_concurrency_limit_to_one() -> None:
    agent = OpenHandsAgentSettings(llm=LLM(model="test-model")).create_agent()
    assert agent.tool_concurrency_limit == 1


def test_create_agent_defaults_tools_when_none() -> None:
    """tools=None (the default) materializes the canonical exec set at
    create_agent — 单个默认点 (#3967 / #3978)。 确定性：浏览器是服务层注入，绝不是默
    认的一部分。
    """
    settings = OpenHandsAgentSettings(llm=LLM(model="test-model"))
    assert settings.tools is None
    agent = settings.create_agent()
    assert [t.name for t in agent.tools] == ["terminal", "file_editor", "task_tracker"]
    assert "SwitchLLMTool" in agent.include_default_tools


@pytest.mark.parametrize("switch", ["enable_sub_agents", "enable_switch_llm_tool"])
def test_removed_switches_are_rejected_by_settings_and_diffs(switch: str) -> None:
    payload = {"llm": {"model": "test-model"}, switch: True}
    with pytest.raises(ValidationError, match="Removed agent settings"):
        OpenHandsAgentSettings.model_validate(payload)
    with pytest.raises(ValueError, match="Removed agent settings"):
        validate_agent_settings(payload)
    with pytest.raises(ValidationError, match="Removed agent settings"):
        apply_agent_settings_diff(OpenHandsAgentSettings(), {switch: True})


def test_create_agent_collapses_duplicate_tools() -> None:
    agent = OpenHandsAgentSettings(
        llm=LLM(model="test-model"),
        tools=[
            Tool(name="terminal"),
            Tool(name="terminal", params={"username": "dev"}),
        ],
    ).create_agent()

    assert [(t.name, t.params) for t in agent.tools] == [
        ("terminal", {"username": "dev"})
    ]


def test_explicit_tools_without_switch_llm_get_no_switch_llm() -> None:
    agent = OpenHandsAgentSettings(
        llm=LLM(model="test-model"), tools=[Tool(name="terminal")]
    ).create_agent()

    assert [t.name for t in agent.tools] == ["terminal"]
    assert "SwitchLLMTool" not in agent.include_default_tools


@pytest.mark.parametrize("name", ["switch_llm", "SwitchLLMTool"])
def test_selected_builtin_reaches_the_agent_by_class_name(name: str) -> None:
    agent = OpenHandsAgentSettings(
        llm=LLM(model="test-model"),
        tools=[Tool(name=name)],
    ).create_agent()

    assert agent.tools == []
    assert agent.include_default_tools.count("SwitchLLMTool") == 1


def test_builtin_with_params_reaches_the_agent_by_class_name() -> None:
    agent = OpenHandsAgentSettings(
        llm=LLM(model="test-model"),
        tools=[Tool(name="finish", params={"response_schema": {"type": "object"}})],
    ).create_agent()

    assert agent.tools == [
        Tool(name="FinishTool", params={"response_schema": {"type": "object"}})
    ]
    assert "FinishTool" not in agent.include_default_tools


@pytest.mark.parametrize(
    "tools",
    [
        [
            Tool(name="finish", params={"response_schema": {"type": "object"}}),
            Tool(name="FinishTool"),
        ],
        [
            Tool(name="FinishTool"),
            Tool(name="finish", params={"response_schema": {"type": "object"}}),
        ],
    ],
)
def test_builtin_named_twice_is_attached_once(tools: list[Tool]) -> None:
    agent = OpenHandsAgentSettings(
        llm=LLM(model="test-model"), tools=tools
    ).create_agent()

    assert agent.tools == [
        Tool(name="FinishTool", params={"response_schema": {"type": "object"}})
    ]
    assert "FinishTool" not in agent.include_default_tools


def test_registered_tool_named_like_a_builtin_is_not_replaced(monkeypatch) -> None:
    from openhands.sdk.tool import registry
    from openhands.sdk.tool.builtins import ThinkTool

    class _CustomThinkTool(ThinkTool):
        pass

    monkeypatch.setitem(registry._TOOL_CLASSES, "think", _CustomThinkTool)

    agent = OpenHandsAgentSettings(
        llm=LLM(model="test-model"), tools=[Tool(name="think")]
    ).create_agent()

    assert agent.tools == [Tool(name="think")]


def test_retired_tool_switches_are_not_serialized() -> None:
    dumped = OpenHandsAgentSettings(llm=LLM(model="test-model")).model_dump(mode="json")

    assert "enable_sub_agents" not in dumped
    assert "enable_switch_llm_tool" not in dumped


def test_settings_re_saved_with_new_tools_keep_them() -> None:
    stored = OpenHandsAgentSettings(llm=LLM(model="test-model"))
    payload = {
        **stored.model_dump(mode="json"),
        "tools": [{"name": "terminal"}, {"name": "glob"}],
    }

    settings = validate_agent_settings(payload)

    assert isinstance(settings, OpenHandsAgentSettings)
    assert [t.name for t in settings.tools or []] == ["terminal", "glob"]


@pytest.mark.parametrize(
    ("switches", "expected"),
    [
        ({}, ["terminal", "switch_llm"]),
        ({"enable_switch_llm_tool": False}, ["terminal"]),
        ({"enable_sub_agents": True}, ["terminal", "switch_llm"]),
    ],
)
def test_v6_settings_fold_the_retired_switches(
    switches: dict[str, bool], expected: list[str]
) -> None:
    settings = validate_agent_settings(
        {
            "schema_version": 6,
            "agent_kind": "openhands",
            "llm": {"model": "test-model"},
            "tools": [{"name": "terminal"}],
            **switches,
        }
    )

    assert isinstance(settings, OpenHandsAgentSettings)
    assert settings.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert [t.name for t in settings.tools or []] == expected


def test_v6_settings_pin_the_standard_set_the_server_launches() -> None:
    settings = validate_agent_settings(
        {
            "schema_version": 6,
            "agent_kind": "openhands",
            "llm": {"model": "test-model"},
            "enable_sub_agents": True,
        }
    )

    assert isinstance(settings, OpenHandsAgentSettings)
    assert [t.name for t in settings.tools or []] == [
        "terminal",
        "file_editor",
        "task_tracker",
        "browser_tool_set",
        "task_tool_set",
        "switch_llm",
    ]


_PINNED_WITH_SUB_AGENTS = [
    "terminal",
    "file_editor",
    "task_tracker",
    "browser_tool_set",
    "task_tool_set",
    "switch_llm",
]


@pytest.mark.parametrize("schema_version", [5, 6])
@pytest.mark.parametrize(
    ("switches", "expected"),
    [
        ({}, None),
        ({"enable_sub_agents": False, "enable_switch_llm_tool": True}, None),
        (
            {"enable_sub_agents": True, "enable_switch_llm_tool": True},
            _PINNED_WITH_SUB_AGENTS,
        ),
        (
            {"enable_switch_llm_tool": False},
            ["terminal", "file_editor", "task_tracker", "browser_tool_set"],
        ),
    ],
)
def test_persisted_empty_tools_migrate_as_the_standard_set(
    schema_version: int, switches: dict[str, bool], expected: list[str] | None
) -> None:
    settings = validate_agent_settings(
        {
            "schema_version": schema_version,
            "agent_kind": "openhands",
            "llm": {"model": "test-model"},
            "tools": [],
            **switches,
        }
    )

    assert isinstance(settings, OpenHandsAgentSettings)
    assert (
        None if settings.tools is None else [t.name for t in settings.tools]
    ) == expected


@pytest.mark.parametrize(
    ("tools", "expected"),
    [
        (None, None),
        ([], None),
        ([{"name": "terminal"}], ["terminal", "switch_llm"]),
    ],
)
def test_unversioned_persisted_settings_migrate_as_legacy_rows(
    tools: list[dict[str, str]] | None, expected: list[str] | None
) -> None:
    payload = {"agent_kind": "openhands", "llm": {"model": "m"}, "tools": tools}

    settings = validate_agent_settings(payload, persisted=True)
    concrete = OpenHandsAgentSettings.from_persisted(payload)

    for loaded in (settings, concrete):
        assert isinstance(loaded, OpenHandsAgentSettings)
        assert (
            None if loaded.tools is None else [t.name for t in loaded.tools]
        ) == expected


@pytest.mark.parametrize("schema_version", ["absent", None])
@pytest.mark.parametrize(
    ("tools", "expected"),
    [
        (None, None),
        ([], []),
        ([{"name": "terminal"}], ["terminal"]),
    ],
)
def test_unversioned_settings_get_no_retired_switch_defaults(
    schema_version: str | None,
    tools: list[dict[str, str]] | None,
    expected: list[str] | None,
) -> None:
    payload: dict[str, object] = {
        "agent_kind": "openhands",
        "llm": {"model": "test-model"},
        "tools": tools,
    }
    if schema_version is None:
        payload["schema_version"] = None

    settings = validate_agent_settings(payload)

    assert isinstance(settings, OpenHandsAgentSettings)
    assert settings.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert (
        None if settings.tools is None else [t.name for t in settings.tools]
    ) == expected


def test_unversioned_persisted_settings_fold_switches_they_carry() -> None:
    settings = OpenHandsAgentSettings.from_persisted(
        {
            "agent_kind": "openhands",
            "llm": {"model": "test-model"},
            "tools": [{"name": "terminal"}, {"name": "switch_llm"}],
            "enable_switch_llm_tool": False,
        }
    )

    assert isinstance(settings, OpenHandsAgentSettings)
    assert [t.name for t in settings.tools or []] == ["terminal"]


def test_unversioned_acp_settings_drop_the_retired_switches() -> None:
    payload = _migrate_agent_settings_payload(
        {"agent_kind": "acp", "acp_server": "claude-code", "enable_sub_agents": True},
        persisted=True,
    )

    assert payload["schema_version"] == AGENT_SETTINGS_SCHEMA_VERSION
    assert "enable_sub_agents" not in payload


def test_unversioned_acp_settings_drop_the_deprecated_llm() -> None:
    payload = _migrate_agent_settings_payload(
        {"agent_kind": "acp", "acp_server": "claude-code", "llm": {"model": "x"}},
        persisted=True,
    )

    assert "llm" not in payload


def test_v6_sub_agents_off_keeps_an_explicit_sub_agent_tool() -> None:
    settings = validate_agent_settings(
        {
            "schema_version": 6,
            "agent_kind": "openhands",
            "llm": {"model": "test-model"},
            "tools": [{"name": "task_tool_set"}],
            "enable_sub_agents": False,
            "enable_switch_llm_tool": False,
        }
    )

    assert isinstance(settings, OpenHandsAgentSettings)
    assert [t.name for t in settings.tools or []] == ["task_tool_set"]


def test_explicitly_selected_switch_llm_is_not_added_twice() -> None:
    agent = OpenHandsAgentSettings(
        llm=LLM(model="test-model"), tools=[Tool(name="switch_llm")]
    ).create_agent()

    assert agent.tools == []
    assert agent.include_default_tools.count("SwitchLLMTool") == 1


def test_create_agent_empty_tools_stays_bare() -> None:
    """tools=[] is an explicit choice: no default injection (persisted-payload
    兼容性 — [] 早于 None 默认值并保留其旧含义）。"""
    settings = OpenHandsAgentSettings(llm=LLM(model="test-model"), tools=[])
    agent = settings.create_agent()
    assert agent.tools == []


def test_create_agent_applies_persona() -> None:
    settings = OpenHandsAgentSettings(
        llm=LLM(model="test-model"), tools=[], persona="You are a classifier."
    )
    agent = settings.create_agent()
    assert agent.persona == "You are a classifier."
    assert agent.static_system_message.startswith("You are a classifier.")


def test_create_agent_without_persona_uses_builtin_prompt() -> None:
    settings = OpenHandsAgentSettings.model_validate({"agent_kind": "openhands"})
    assert settings.persona is None
    assert settings.create_agent().persona is None


def test_tool_concurrency_limit_defaults_to_one_when_omitted_from_payload() -> None:
    # 向后兼容性：载荷已持久化在字段存在之前仍然必须加载并回退到顺序默认值。
    #
    settings = OpenHandsAgentSettings.model_validate({"agent_kind": "openhands"})
    assert settings.tool_concurrency_limit == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1, 1),  # 顺序默认，显式
        (2, 2),
        (8, 8),
        (32, 32),
        (1000, 1000),  # 无上限——接受较大的值
        ("4", 4),  # 松散字符串 -> int 强制转换
        (4.0, 4),  # 整数浮点强制
        (True, 1),  # bool 是 int 子类； True -> 1（>= 1，因此有效）
    ],
)
def test_tool_concurrency_limit_valid_values_round_trip(
    raw: Any, expected: int
) -> None:
    settings = OpenHandsAgentSettings(
        llm=LLM(model="test-model"), tool_concurrency_limit=raw
    )
    assert settings.tool_concurrency_limit == expected
    assert type(settings.tool_concurrency_limit) is int

    # 该值必须在 JSON 序列化往返中保持不变...
    reloaded = OpenHandsAgentSettings.model_validate(settings.model_dump(mode="json"))
    assert reloaded.tool_concurrency_limit == expected

    # ...and propagate to the constructed Agent.
    agent = settings.create_agent()
    assert agent.tool_concurrency_limit == expected


@pytest.mark.parametrize(
    "raw",
    [
        0,  # 低于 ge=1
        -1,  # 消极的
        -100,
        False,  # bool False -> 0，低于 ge=1
        4.5,  # 非整数浮点数
        "abc",  # 无法解析的字符串
        None,  # 不可选
        [1],  # 完全错误的类型
    ],
)
def test_tool_concurrency_limit_invalid_values_rejected(raw: Any) -> None:
    with pytest.raises(ValidationError) as exc_info:
        OpenHandsAgentSettings(llm=LLM(model="test-model"), tool_concurrency_limit=raw)
    assert any(
        err["loc"] == ("tool_concurrency_limit",) for err in exc_info.value.errors()
    )


def test_llm_agent_settings_validates_mcp_config_as_typed_model() -> None:
    settings = OpenHandsAgentSettings.model_validate(
        {"mcp_config": {"fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}}}
    )

    assert isinstance(settings.mcp_config["fetch"], MCPServer)
    assert settings.model_dump()["mcp_config"] == {
        "fetch": {"command": "uvx", "args": ["mcp-server-fetch"], "enabled": True}
    }


def test_llm_create_agent_serializes_typed_mcp_config_compactly() -> None:
    mcp_config = coerce_mcp_config(
        {"fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}}
    )
    settings = OpenHandsAgentSettings(mcp_config=mcp_config)

    agent = settings.create_agent()

    assert dump_mcp_config(agent.mcp_config) == {
        "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}
    }


def test_disabled_mcp_server_survives_settings_round_trip() -> None:
    """关闭的服务器在重新加载期间保持关闭状态并保留其配置。"""
    settings = OpenHandsAgentSettings.model_validate(
        {
            "mcp_config": {
                "fetch": {
                    "command": "uvx",
                    "args": ["mcp-server-fetch"],
                    "enabled": False,
                }
            }
        }
    )

    reloaded = OpenHandsAgentSettings.model_validate(settings.model_dump(mode="json"))

    assert reloaded.mcp_config["fetch"].enabled is False
    assert reloaded.mcp_config["fetch"].command == "uvx"


def test_llm_create_agent_builds_condenser_when_enabled() -> None:
    llm = LLM(model="test-model", usage_id="agent")
    agent_metrics = llm.metrics
    settings = OpenHandsAgentSettings(
        llm=llm,
        condenser=LLMSummarizingCondenserSettings(
            enabled=True,
            max_size=100,
            max_tokens=5000,
            keep_first=3,
            minimum_progress=0.2,
            hard_context_reset_max_retries=7,
            hard_context_reset_context_scaling=0.6,
        ),
    )
    agent = settings.create_agent()

    assert agent.llm is llm
    assert isinstance(agent.condenser, LLMSummarizingCondenser)
    assert agent.condenser.max_size == 100
    assert agent.condenser.max_tokens == 5000
    assert agent.condenser.keep_first == 3
    assert agent.condenser.minimum_progress == 0.2
    assert agent.condenser.hard_context_reset_max_retries == 7
    assert agent.condenser.hard_context_reset_context_scaling == 0.6
    assert agent.condenser.llm is not llm
    assert agent.condenser.llm.model == llm.model
    assert agent.condenser.llm.usage_id == "condenser"
    assert agent.condenser.llm.metrics is not agent_metrics


def test_llm_summarizing_condenser_inherits_max_tokens_from_llm() -> None:
    """当上下文压缩器的``max_tokens``未设置时，它应该继承
    智能体 LLM 的 ``effective_max_input_tokens`` 以便上下文压缩可以由词元数量触发，而
    不仅仅是事件计数。 见#3746：配置的
    ``max_input_tokens``在LLM上没有对上下文压缩器产生影响，所以长工具输出可以不经上下
    文窗口就直接过。
    """
    llm = LLM(model="test-model", usage_id="agent", max_input_tokens=65536)
    settings = OpenHandsAgentSettings(
        llm=llm,
        condenser=LLMSummarizingCondenserSettings(enabled=True),
    )
    agent = settings.create_agent()

    assert isinstance(agent.condenser, LLMSummarizingCondenser)
    assert agent.condenser.max_tokens == 65536


def test_llm_summarizing_condenser_respects_explicit_max_tokens_over_llm() -> None:
    """显式配置的上下文压缩器 ``max_tokens`` 不得
    被LLM的``effective_max_input_tokens``覆盖。
    """
    llm = LLM(model="test-model", usage_id="agent", max_input_tokens=65536)
    settings = OpenHandsAgentSettings(
        llm=llm,
        condenser=LLMSummarizingCondenserSettings(enabled=True, max_tokens=5000),
    )
    agent = settings.create_agent()

    assert isinstance(agent.condenser, LLMSummarizingCondenser)
    assert agent.condenser.max_tokens == 5000


def test_llm_summarizing_condenser_max_tokens_none_when_llm_has_no_limit() -> None:
    """当上下文压缩器和LLM都没有配置token限制时，
    上下文压缩器的 ``max_tokens`` 应保留 ``None``（仅限事件计数上下文压缩），与从未设
    置的用户匹配前缀行为
    ``max_input_tokens``.
    """
    llm = LLM(model="test-model", usage_id="agent")
    settings = OpenHandsAgentSettings(
        llm=llm,
        condenser=LLMSummarizingCondenserSettings(enabled=True),
    )
    agent = settings.create_agent()

    assert isinstance(agent.condenser, LLMSummarizingCondenser)
    assert agent.condenser.max_tokens is None


def test_llm_summarizing_condenser_explicit_none_max_tokens_remains_unset() -> None:
    """上下文压缩器配置上的显式 ``max_tokens=None`` 保持未设置。

    运行时，活动智能体 LLM 的有效输入限制仍然控制上下文压缩。
    """
    llm = LLM(model="test-model", usage_id="agent", max_input_tokens=65536)
    settings = OpenHandsAgentSettings(
        llm=llm,
        condenser=LLMSummarizingCondenserSettings(enabled=True, max_tokens=None),
    )
    agent = settings.create_agent()

    assert isinstance(agent.condenser, LLMSummarizingCondenser)
    assert agent.condenser.max_tokens is None


def test_llm_summarizing_condenser_settings_match_condenser_fields() -> None:
    condenser_fields = set(LLMSummarizingCondenser.model_fields) - {"llm"}
    settings_fields = set(LLMSummarizingCondenserSettings.model_fields) - {
        "enabled",
        "condenser_kind",
    }

    assert settings_fields == condenser_fields


def test_openhands_agent_settings_defaults_legacy_condenser_payload() -> None:
    settings = OpenHandsAgentSettings.model_validate(
        {
            "condenser": {
                "enabled": True,
                "max_size": 100,
                "max_tokens": 5000,
            }
        }
    )

    assert isinstance(settings.condenser, LLMSummarizingCondenserSettings)
    assert settings.condenser.condenser_kind == "llm_summarizing"
    assert settings.condenser.max_size == 100
    assert settings.condenser.max_tokens == 5000


def test_openhands_agent_settings_dispatches_no_op_condenser_payload() -> None:
    settings = OpenHandsAgentSettings.model_validate(
        {
            "condenser": {
                "enabled": True,
                "condenser_kind": "no_op",
            }
        }
    )

    assert isinstance(settings.condenser, NoOpCondenserSettings)
    assert settings.condenser.condenser_kind == "no_op"
    assert settings.condenser.model_dump() == {
        "enabled": True,
        "condenser_kind": "no_op",
    }


def test_openhands_agent_settings_upgrades_base_condenser_settings_instance() -> None:
    settings = OpenHandsAgentSettings.model_validate(
        {"condenser": CondenserSettings(enabled=True, max_size=100)}
    )

    assert isinstance(settings.condenser, LLMSummarizingCondenserSettings)
    assert settings.condenser.max_size == 100


def test_condenser_settings_base_requires_concrete_build_method() -> None:
    with pytest.raises(NotImplementedError):
        CondenserSettings().build_condenser(LLM(model="test-model"))


def test_llm_create_agent_no_condenser_when_disabled() -> None:
    settings = OpenHandsAgentSettings(
        condenser=LLMSummarizingCondenserSettings(enabled=False),
    )
    agent = settings.create_agent()
    assert agent.condenser is None


def test_llm_create_agent_builds_no_op_condenser_variant() -> None:
    settings = OpenHandsAgentSettings(condenser=NoOpCondenserSettings())

    agent = settings.create_agent()

    assert isinstance(agent.condenser, NoOpCondenser)


def test_llm_create_agent_builds_critic_when_enabled() -> None:
    settings = OpenHandsAgentSettings(
        llm=LLM(model="m", api_key=SecretStr("k")),
        verification=VerificationSettings(
            critic_enabled=True,
            critic_mode="all_actions",
        ),
    )
    agent = settings.create_agent()
    assert isinstance(agent.critic, APIBasedCritic)
    assert agent.critic.mode == "all_actions"
    assert agent.critic.iterative_refinement is None


def test_llm_create_agent_no_critic_without_api_key() -> None:
    settings = OpenHandsAgentSettings(
        llm=LLM(model="m", api_key=None),
        verification=VerificationSettings(critic_enabled=True),
    )
    agent = settings.create_agent()
    assert agent.critic is None


def test_llm_create_agent_critic_uses_explicit_api_key() -> None:
    """当设置``verification.critic_api_key``时，批评者进行身份验证
    用它代替 LLM 键。 LLM 自己的密钥保持不变，因此主智能体循环仍然与其提供者对话。
    """
    settings = OpenHandsAgentSettings(
        llm=LLM(model="m", api_key=SecretStr("llm-key")),
        verification=VerificationSettings(
            critic_enabled=True,
            critic_api_key=SecretStr("critic-key"),
        ),
    )
    agent = settings.create_agent()
    assert isinstance(agent.critic, APIBasedCritic)
    assert isinstance(agent.critic.api_key, SecretStr)
    assert agent.critic.api_key.get_secret_value() == "critic-key"
    # LLM 键不受影响。
    assert isinstance(agent.llm.api_key, SecretStr)
    assert agent.llm.api_key.get_secret_value() == "llm-key"


def test_llm_create_agent_critic_falls_back_to_llm_api_key() -> None:
    """如果没有 ``verification.critic_api_key``，遗留行为将成立：
    评论家重复使用 LLM 键（All-Hands 代理的自动配置路径）。"""
    settings = OpenHandsAgentSettings(
        llm=LLM(model="m", api_key=SecretStr("llm-key")),
        verification=VerificationSettings(critic_enabled=True),
    )
    agent = settings.create_agent()
    assert isinstance(agent.critic, APIBasedCritic)
    assert isinstance(agent.critic.api_key, SecretStr)
    assert agent.critic.api_key.get_secret_value() == "llm-key"


def test_llm_create_agent_critic_with_only_critic_api_key() -> None:
    """如果 LLM 没有密钥但提供了 ``critic_api_key``，则批评者
    仍然被构建 - 它的凭据独立于 LLM。"""
    settings = OpenHandsAgentSettings(
        llm=LLM(model="m", api_key=None),
        verification=VerificationSettings(
            critic_enabled=True,
            critic_api_key=SecretStr("critic-only-key"),
        ),
    )
    agent = settings.create_agent()
    assert isinstance(agent.critic, APIBasedCritic)
    assert isinstance(agent.critic.api_key, SecretStr)
    assert agent.critic.api_key.get_secret_value() == "critic-only-key"


def test_verification_settings_critic_api_key_roundtrip() -> None:
    """``critic_api_key`` 在转储中幸存 → 当机密暴露时进行验证，
    并从纯字符串和 SecretStr 输入进行验证。"""
    settings = VerificationSettings(
        critic_enabled=True,
        critic_api_key="plain-string-key",
    )
    assert isinstance(settings.critic_api_key, SecretStr)
    assert settings.critic_api_key.get_secret_value() == "plain-string-key"

    dumped = settings.model_dump(context={"expose_secrets": "plaintext"})
    assert dumped["critic_api_key"] == "plain-string-key"

    restored = VerificationSettings.model_validate(dumped)
    assert isinstance(restored.critic_api_key, SecretStr)
    assert restored.critic_api_key.get_secret_value() == "plain-string-key"

    # 空字符串标准化为 None（与 LLM.api_key 处理一致）。
    empty = VerificationSettings(critic_enabled=True, critic_api_key="")
    assert empty.critic_api_key is None


def test_llm_create_agent_critic_with_iterative_refinement() -> None:
    settings = OpenHandsAgentSettings(
        llm=LLM(model="m", api_key=SecretStr("k")),
        verification=VerificationSettings(
            critic_enabled=True,
            enable_iterative_refinement=True,
            critic_threshold=0.8,
            max_refinement_iterations=5,
        ),
    )
    agent = settings.create_agent()
    assert isinstance(agent.critic, APIBasedCritic)
    ir = agent.critic.iterative_refinement
    assert isinstance(ir, IterativeRefinementConfig)
    assert ir.success_threshold == 0.8
    assert ir.max_iterations == 5


def test_llm_roundtrip_preserves_llm_model() -> None:
    settings = OpenHandsAgentSettings(llm=LLM(model="test-model"))
    data = settings.model_dump()
    restored = OpenHandsAgentSettings.model_validate(data)
    assert restored.llm.model == "test-model"


# ---------------------------------------------------------------------------
# create_agent — ACP variant
# ---------------------------------------------------------------------------


def test_acp_create_agent_uses_server_default_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """设置 ``acp_server`` 但没有显式命令时，使用内置默认值。

    将 ``shutil.which`` 粘贴到 ``None``，使 ``npx`` 的默认值被确定性地激活 —— 在已安
    装粘贴的
    ``claude-agent-acp`` 二进制文件的主机上，`resolve_acp_command` 方法 (正确地) 会重
    写为它。
    """
    monkeypatch.setattr(shutil, "which", lambda _: None)
    settings = ACPAgentSettings(acp_server="claude-code", acp_model="claude-opus-4-6")
    agent = settings.create_agent()
    assert isinstance(agent, ACPAgent)
    assert agent.acp_command == [
        "npx",
        "-y",
        "--prefer-offline",
        "@agentclientprotocol/claude-agent-acp@0.63.0",
    ]
    assert agent.acp_model == "claude-opus-4-6"
    # 权威提供商密钥被携带到智能体上。
    assert agent.acp_server == "claude-code"


def test_acp_create_agent_carries_provider_key() -> None:
    """``create_agent`` 将每个选择的提供者密钥标记到智能体上。

    ``acp_command`` 无法可靠地反向映射到提供商，因此密钥必须利用智能体（因此也是
    ``ConversationInfo.agent``）以便消费者解析品
    牌标签/型号列表。 习惯一字不差地贯彻执行； 直接构建的智能体（不是从设置）默认为
    ``None``； 并且密钥在通过 ``AgentBase`` 受歧视联盟的序列
    化往返中仍然存在。
    """
    for server in (
        "claude-code",
        "codex",
        "gemini-cli",
        "kimi-code",
        "pi",
        "opencode",
        "custom",
    ):
        kwargs: dict[str, Any] = {"acp_server": server}
        if server == "custom":
            kwargs["acp_command"] = ["my-acp"]
        agent = ACPAgentSettings(**kwargs).create_agent()
        assert agent.acp_server == server

    assert ACPAgent(acp_command=["x"]).acp_server is None

    agent = ACPAgentSettings(acp_server="gemini-cli").create_agent()
    reloaded = ACPAgent.model_validate_json(agent.model_dump_json())
    assert reloaded.acp_server == "gemini-cli"


def test_acp_resolve_command_for_known_servers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """每个非自定义选择都必须映射到可运行的默认值。

    由于 ``PATH`` (``shutil.which`` → ``None``) 上没有固定二进制文件，默认保留
    ``npx`` 调用。
    """
    monkeypatch.setattr(shutil, "which", lambda _: None)
    for server in ("claude-code", "codex", "gemini-cli", "kimi-code", "pi", "opencode"):
        settings = ACPAgentSettings(acp_server=server)
        cmd = settings.resolve_acp_command()
        assert cmd, f"expected default command for {server}, got empty"
        assert cmd[0] == "npx", f"expected npx-based default, got {cmd}"


def test_acp_create_agent_explicit_command_overrides_default() -> None:
    settings = ACPAgentSettings(
        acp_server="claude-code",
        acp_command=["my-local-acp-binary"],
    )
    agent = settings.create_agent()
    assert agent.acp_command == ["my-local-acp-binary"]


def test_acp_custom_server_requires_explicit_command() -> None:
    settings = ACPAgentSettings(acp_server="custom")
    try:
        settings.create_agent()
    except ValueError as e:
        assert "acp_command" in str(e) and "custom" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_acp_create_agent_forwards_isolate_data_dir() -> None:
    """``acp_isolate_data_dir`` 从设置传播到构建的智能体。

    默认情况下是错的，一个明确的 True 会到达 ``ACPAgent``，这样部署的应用可以将一个沙
    箱中的对话分享到一个会话 CLI 的数据目录 (#1019)。
    """
    default_agent = ACPAgentSettings(acp_server="codex").create_agent()
    assert default_agent.acp_isolate_data_dir is False

    isolated = ACPAgentSettings(
        acp_server="codex", acp_isolate_data_dir=True
    ).create_agent()
    assert isolated.acp_isolate_data_dir is True


def test_acp_custom_server_with_command_resolves() -> None:
    settings = ACPAgentSettings(
        acp_server="custom",
        acp_command=["bin", "--flag"],
    )
    assert settings.resolve_acp_command() == ["bin", "--flag"]


# ---------------------------------------------------------------------------
# resolve_acp_command() — 更喜欢固定的、预安装的 CLI 二进制文件
#
# 的智能体服务器预安装了 [server image] ACP  CLIs 并暴露为包装器 PATH (claude-智能体-ACP
#  / codex-ACP / gemini). resolve_acp_command 重写 ``npx -y <pkg>`` 启动命令 ——  注册表
# default AND explicit acp_command canvas 发送 — 当它在时，直接运行 pinned 二进制 PATH (
# 可重现的，不进行运行时的 npm 下载)，保留尾随参数。 当二进制文件不存在（本地开发）时，
# 它将回退到 npx 命令不变。
# ---------------------------------------------------------------------------


def _which_returning(*available: str):
    """构建仅解析指定二进制文件的 ``shutil.which`` 存根。"""
    paths = {name: f"/usr/local/bin/{name}" for name in available}
    return lambda name: paths.get(name)


@pytest.mark.parametrize(
    ("server", "binary", "expected"),
    [
        ("claude-code", "claude-agent-acp", ["claude-agent-acp"]),
        ("codex", "codex-acp", ["codex-acp"]),
        # Gemini 的默认值带有必须保留的尾随 ``--acp``。
        ("gemini-cli", "gemini", ["gemini", "--acp"]),
        ("pi", "pi-acp", ["pi-acp"]),
        # opencode 的尾随 arg 是一个 ``acp`` 子命令，其保留方式与 Gemini 的 ``--acp`` 标
        # 志相同。
        #
        ("opencode", "opencode", ["opencode", "acp"]),
    ],
)
def test_acp_resolve_command_rewrites_default_to_pinned_binary(
    monkeypatch: pytest.MonkeyPatch,
    server: ACPServerKind,
    binary: str,
    expected: list[str],
) -> None:
    """(a) 注册表默认 + PATH 上的二进制文件 → 直接运行固定的二进制文件。"""
    monkeypatch.setattr(shutil, "which", _which_returning(binary))
    settings = ACPAgentSettings(acp_server=server)
    assert settings.resolve_acp_command() == expected


def test_acp_resolve_command_rewrites_explicit_npx_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(b) 显式 ``npx -y <pkg>``（画布发送的内容）+ PATH 上的二进制 →
    重写为固定的二进制文件，并保留尾随参数。"""
    monkeypatch.setattr(shutil, "which", _which_returning("codex-acp"))
    settings = ACPAgentSettings(
        acp_server="codex",
        acp_command=[
            "npx",
            "-y",
            "@agentclientprotocol/codex-acp",
            "--verbose",
        ],
    )
    assert settings.resolve_acp_command() == ["codex-acp", "--verbose"]


def test_acp_resolve_command_rewrites_versioned_npx_to_pinned_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(b') 匹配与版本无关：提供者的 ``npx`` 命令
    包at *任何的* 版本（裸的、默认的锁定版本，或客户端发送的漂移版本）重写为锁定的二
    进制 PATH — 在图像中，我们总是将已审核的二进制文件呈现给提供者的包。
    """
    monkeypatch.setattr(shutil, "which", _which_returning("codex-acp"))
    for pkg in (
        "@agentclientprotocol/codex-acp",
        "@agentclientprotocol/codex-acp@1.10.0",
    ):
        settings = ACPAgentSettings(
            acp_server="codex",
            acp_command=["npx", "-y", pkg],
        )
        assert settings.resolve_acp_command() == ["codex-acp"], pkg


def test_acp_resolve_command_keeps_npx_when_binary_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(c) 二进制文件不在 PATH（本地开发）上 → ``npx`` 命令不变。

    默认情况下是版本固定的，因此本机回退方案启动经过审查的版本，而不是 npm ``latest``
    。
    """
    monkeypatch.setattr(shutil, "which", lambda _: None)
    settings = ACPAgentSettings(acp_server="codex")
    assert settings.resolve_acp_command() == [
        "npx",
        "-y",
        "--prefer-offline",
        "@agentclientprotocol/codex-acp@2.2.2",
    ]


def test_acp_resolve_command_leaves_custom_binary_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(d) 非 npx/用户提供的命令永远不会被重写，即使
    提供商的固定二进制文件位于 PATH。"""
    monkeypatch.setattr(shutil, "which", _which_returning("codex-acp"))
    settings = ACPAgentSettings(
        acp_server="codex",
        acp_command=["/opt/my-codex", "--flag"],
    )
    assert settings.resolve_acp_command() == ["/opt/my-codex", "--flag"]


def test_acp_resolve_command_leaves_unknown_package_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(d) 不重写 * different* 包的 ``npx`` 命令 —
    固定的二进制文件仅代表提供商自己的包。"""
    monkeypatch.setattr(shutil, "which", _which_returning("codex-acp"))
    settings = ACPAgentSettings(
        acp_server="codex",
        acp_command=["npx", "-y", "@other/some-acp"],
    )
    assert settings.resolve_acp_command() == ["npx", "-y", "@other/some-acp"]


def test_acp_resolve_command_custom_server_never_rewritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``custom`` 没有注册表条目（因此没有固定的二进制文件），所以即使
    与 Codex 完全相同的命令会逐字返回。"""
    monkeypatch.setattr(shutil, "which", _which_returning("codex-acp", "gemini"))
    settings = ACPAgentSettings(
        acp_server="custom",
        acp_command=["npx", "-y", "@agentclientprotocol/codex-acp"],
    )
    assert settings.resolve_acp_command() == [
        "npx",
        "-y",
        "@agentclientprotocol/codex-acp",
    ]


def test_acp_resolve_command_queries_which_with_binary_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PATH 探针使用提供者的 ``binary_name``，而不是 npm 包。"""
    queried: list[str] = []

    def fake_which(name: str) -> str | None:
        queried.append(name)
        return None

    monkeypatch.setattr(shutil, "which", fake_which)
    ACPAgentSettings(acp_server="gemini-cli").resolve_acp_command()
    assert queried == ["gemini"]

    queried.clear()
    ACPAgentSettings(acp_server="kimi-code").resolve_acp_command()
    assert queried == ["kimi"]


def test_acp_create_agent_uses_pinned_binary_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """端到端：create_agent()将重写的命令烘焙到智能体中。"""
    monkeypatch.setattr(shutil, "which", _which_returning("codex-acp"))
    agent = ACPAgentSettings(acp_server="codex").create_agent()
    assert agent.acp_command == ["codex-acp"]


def test_acp_create_agent_pinned_binary_preserves_subcommand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重写会在二进制文件之后保留尾随 args（``acp`` 子命令）。"""
    monkeypatch.setattr(shutil, "which", _which_returning("kimi"))
    agent = ACPAgentSettings(acp_server="kimi-code").create_agent()
    assert agent.acp_command == ["kimi", "acp"]


def test_acp_api_key_env_var_maps_known_servers() -> None:
    assert (
        ACPAgentSettings(acp_server="claude-code").api_key_env_var
        == "ANTHROPIC_API_KEY"
    )
    assert ACPAgentSettings(acp_server="codex").api_key_env_var == "OPENAI_API_KEY"
    assert ACPAgentSettings(acp_server="gemini-cli").api_key_env_var == "GEMINI_API_KEY"
    # Kimi 没有 env-var API 键； 凭据是 config.toml。
    assert ACPAgentSettings(acp_server="kimi-code").api_key_env_var is None
    # pi 是多提供者，但从进程环境中读取普通提供者密钥； ANTHROPIC_API_KEY 是注册表为其提
    # 供的通道。
    #
    assert ACPAgentSettings(acp_server="pi").api_key_env_var == "ANTHROPIC_API_KEY"
    assert (
        ACPAgentSettings(acp_server="custom", acp_command=["x"]).api_key_env_var is None
    )


def test_acp_create_agent_ignores_llm_credentials() -> None:
    # llm.api_key/base_url 永远不会被读取：LLM-配置文件 base_url 会泄漏到子进程中并默默
    # 地重新路由其 API 调用 (#3632)。 提供者凭据乘坐由提供者的环境变量名称键入的对话机密
    # 通道； 调用者的机密未受影响地通过。
    #
    context = AgentContext(secrets={"GITHUB_TOKEN": "ghp_test"})
    settings = ACPAgentSettings.from_persisted(
        dict(
            agent_kind="acp",
            acp_server="codex",
            llm=LLM(
                model="gpt-5.4",
                api_key=SecretStr("sk-openai"),
                base_url="https://llm-proxy.example.com",
            ),
            agent_context=context,
        )
    )

    agent = settings.create_agent()

    # 调用者的机密不受影响地通过； 没有提供者信用出现。
    assert agent.agent_context is not None
    assert dict(agent.agent_context.secrets or {}) == {"GITHUB_TOKEN": "ghp_test"}


def test_acp_create_agent_ignores_credentials_without_context() -> None:
    # 无调用者 agent_context：不会为被忽略的信用合成任何内容 — 上下文保留为 None。
    #
    settings = ACPAgentSettings.from_persisted(
        dict(
            agent_kind="acp",
            acp_server="claude-code",
            llm=LLM(model="claude-opus-4-6", api_key=SecretStr("sk-ui-key")),
        )
    )

    agent = settings.create_agent()

    assert agent.agent_context is None


@pytest.mark.parametrize(
    ("acp_model", "expected_model"),
    [(None, "acp-managed"), ("claude-opus-4-7", "claude-opus-4-7")],
)
def test_acp_create_agent_keeps_acp_managed_llm(
    acp_model: str | None, expected_model: str
) -> None:
    agent = ACPAgentSettings(acp_model=acp_model).create_agent()

    assert agent.llm.usage_id == ACP_SENTINEL_USAGE_ID
    assert agent.llm.model == expected_model


def test_acp_settings_llm_is_removed() -> None:
    with pytest.raises(ValidationError, match="ACPAgentSettings.llm was removed"):
        ACPAgentSettings.model_validate({"llm": {"model": "gpt-5.6"}})
    with pytest.raises(AttributeError):
        _ = getattr(ACPAgentSettings(), "llm")


@pytest.mark.usefixtures("acp_llm_deprecated")
def test_acp_settings_without_llm_do_not_warn() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecatedWarning)
        ACPAgentSettings(acp_model="sonnet").create_agent()


def test_acp_create_agent_passes_caller_context_through() -> None:
    # 机密通过 agent_context 提供，到达智能体不变； 它们在对话初始化（规范通道）时被播种
    # 到 state.secret_registry 中，而不是在这里重写。
    #
    context = AgentContext(secrets={"ANTHROPIC_API_KEY": "sk-direct"})
    settings = ACPAgentSettings(acp_server="claude-code", agent_context=context)

    agent = settings.create_agent()

    assert agent.agent_context is context


def test_llm_agent_settings_public_alias_removed() -> None:
    """已弃用 ``LLMAgentSettings`` 公共导入别名已在
    v1.24.0; 类本身为联合保留（仅限内部）。"""
    import openhands.sdk as _sdk_mod
    import openhands.sdk.settings as _settings_mod

    with pytest.raises(AttributeError):
        getattr(_settings_mod, "LLMAgentSettings")
    with pytest.raises(AttributeError):
        getattr(_sdk_mod, "LLMAgentSettings")

    # 该类仍然可以在其规范的内部位置访问并保持
    # agent_kind="llm" so the discriminated union deserializes legacy payloads
    # API-破损检查器看不到字段值变化。
    from openhands.sdk.settings.model import LLMAgentSettings

    assert issubclass(LLMAgentSettings, OpenHandsAgentSettings)
    settings = LLMAgentSettings(llm=LLM(model="test-model"))
    assert isinstance(settings, OpenHandsAgentSettings)
    assert settings.agent_kind == "llm"
    assert settings.llm.model == "test-model"


# ---------------------------------------------------------------------------
# ConversationSettings.create_request — 发送变体
# ---------------------------------------------------------------------------


def test_conversation_settings_create_request_for_llm_variant() -> None:
    settings = ConversationSettings(
        max_iterations=77,
        confirmation_mode=True,
        security_analyzer="llm",
    )
    workspace = LocalWorkspace(working_dir="/tmp")
    agent = OpenHandsAgentSettings(llm=LLM(model="test-model")).create_agent()

    request = settings.create_request(
        StartConversationRequest,
        agent=agent,
        workspace=workspace,
    )

    assert isinstance(request, StartConversationRequest)
    assert request.workspace == workspace
    assert request.max_iterations == 77
    assert isinstance(request.confirmation_policy, ConfirmRisky)
    assert isinstance(request.security_analyzer, LLMSecurityAnalyzer)


def test_conversation_settings_create_request_with_acp_agent_variant() -> None:
    settings = ConversationSettings(
        max_iterations=77,
        confirmation_mode=True,
        security_analyzer="none",
    )
    workspace = LocalWorkspace(working_dir="/tmp")
    agent = ACPAgentSettings(acp_command=["echo", "test"]).create_agent()

    request = settings.create_request(
        StartConversationRequest,
        agent=agent,
        workspace=workspace,
    )

    assert isinstance(request, StartConversationRequest)
    assert request.workspace == workspace
    assert request.max_iterations == 77
    assert isinstance(request.confirmation_policy, AlwaysConfirm)
    assert request.security_analyzer is None


def test_conversation_settings_agent_settings_field_accepts_both_variants() -> None:
    """agent_settings 运行时字段应该接受任一变体。"""
    llm_conv = ConversationSettings(
        agent_settings=OpenHandsAgentSettings(llm=LLM(model="m")),
    )
    assert isinstance(llm_conv.agent_settings, OpenHandsAgentSettings)

    acp_conv = ConversationSettings(
        agent_settings=ACPAgentSettings(acp_command=["x"]),
    )
    assert isinstance(acp_conv.agent_settings, ACPAgentSettings)


# ---------------------------------------------------------------------------
# 设置序列化中的机密脱敏
# ---------------------------------------------------------------------------


def test_openhands_agent_settings_mcp_config_redacts_env_and_headers() -> None:
    mcp_config = coerce_mcp_config(
        {
            "leaky": {
                "command": "echo",
                "args": ["mcp"],
                "env": {"API_KEY": "sk-mcp-secret"},
                "headers": {"X-API-Token": "tok-mcp-secret"},
            }
        }
    )
    settings = OpenHandsAgentSettings(mcp_config=mcp_config)

    blob = settings.model_dump_json()
    assert "sk-mcp-secret" not in blob
    assert "tok-mcp-secret" not in blob

    exposed = settings.model_dump(context={"expose_secrets": True})
    leaky = exposed["mcp_config"]["leaky"]
    assert leaky["env"]["API_KEY"] == "sk-mcp-secret"
    assert leaky["headers"]["X-API-Token"] == "tok-mcp-secret"


def test_mcp_config_encrypts_env_and_headers_with_cipher() -> None:
    """当密钥在序列化上下文 （磁盘上的持久化 ）时
    路径），MCP ``env`` / ``headers`` 值必须使用该密码对每个值进行加密 — 与其他机密字
    段的加密方式相同已持久化。

    使用相同密码进行 ``model_validate`` 的往返必须恢复原始明文值。
    """
    from openhands.sdk.utils.cipher import Cipher

    mcp_config = coerce_mcp_config(
        {
            "github": {
                "command": "uvx",
                "args": ["mcp-server-github"],
                "env": {"GITHUB_TOKEN": "ghp-mcp-secret"},
            },
            "fetch": {
                "url": "https://example.com/mcp",
                "headers": {"X-API-Token": "tok-mcp-secret"},
            },
        }
    )
    settings = OpenHandsAgentSettings(mcp_config=mcp_config)
    cipher = Cipher(secret_key="test-encryption-key")

    dumped = settings.model_dump(mode="json", context={"cipher": cipher})

    servers = dumped["mcp_config"]
    assert isinstance(servers, dict)
    github = servers["github"]
    fetch = servers["fetch"]
    assert isinstance(github, dict)
    assert isinstance(fetch, dict)
    github_env = github["env"]
    fetch_headers = fetch["headers"]
    assert isinstance(github_env, dict)
    assert isinstance(fetch_headers, dict)
    enc_token = github_env["GITHUB_TOKEN"]
    enc_auth = fetch_headers["X-API-Token"]
    assert isinstance(enc_token, str)
    assert isinstance(enc_auth, str)

    # 纯文本值必须不出现在磁盘上。
    serialized = json.dumps(dumped)
    assert "ghp-mcp-secret" not in serialized
    assert "tok-mcp-secret" not in serialized
    assert "**********" not in serialized

    # 值必须是 Fernet 密文（base64； 以“gAAAA”开头）。
    assert enc_token.startswith("gAAAA")
    assert enc_auth.startswith("gAAAA")
    # 非机密结构必须保持明文。
    assert servers["github"]["command"] == "uvx"
    assert servers["github"]["args"] == ["mcp-server-github"]
    assert servers["fetch"]["url"] == "https://example.com/mcp"

    # 往返：使用相同的密码解密恢复原始数据。
    restored = OpenHandsAgentSettings.model_validate(dumped, context={"cipher": cipher})
    restored_dump = dump_mcp_config(restored.mcp_config)
    restored_github_env = restored_dump["github"]["env"]
    restored_fetch_headers = restored_dump["fetch"]["headers"]
    assert isinstance(restored_github_env, dict)
    assert isinstance(restored_fetch_headers, dict)
    assert restored_github_env["GITHUB_TOKEN"] == "ghp-mcp-secret"
    assert restored_fetch_headers["X-API-Token"] == "tok-mcp-secret"


def test_mcp_config_encrypts_bearer_auth_with_cipher() -> None:
    from openhands.sdk.utils.cipher import Cipher

    mcp_config = coerce_mcp_config(
        {
            "linear": {
                "url": "https://mcp.linear.app/mcp",
                "auth": {"strategy": "bearer", "value": "lin-api-secret"},
            },
            "superhuman": {
                "url": "https://mcp.mail.superhuman.com/mcp",
                "auth": {"strategy": "oauth2"},
            },
        }
    )
    settings = OpenHandsAgentSettings(mcp_config=mcp_config)
    cipher = Cipher(secret_key="test-encryption-key")

    dumped = settings.model_dump(mode="json", context={"cipher": cipher})
    servers = dumped["mcp_config"]

    assert servers["linear"]["auth"]["strategy"] == "bearer"
    assert servers["linear"]["auth"]["value"].startswith("gAAAA")
    assert servers["linear"]["auth"]["value"] != "lin-api-secret"
    assert servers["superhuman"]["auth"] == {"strategy": "oauth2"}

    redacted = settings.model_dump(mode="json")
    assert redacted["mcp_config"]["linear"]["auth"] == {
        "strategy": "bearer",
        "value": "**********",
    }
    assert redacted["mcp_config"]["superhuman"]["auth"] == {"strategy": "oauth2"}

    restored = OpenHandsAgentSettings.model_validate(dumped, context={"cipher": cipher})
    restored_servers = dump_mcp_config(restored.mcp_config)
    assert restored_servers["linear"]["auth"] == {
        "strategy": "bearer",
        "value": "lin-api-secret",
    }
    assert restored_servers["superhuman"]["auth"] == {
        "strategy": "oauth2",
    }


def test_openhands_agent_settings_create_agent_preserves_mcp_auth_model() -> None:
    mcp_config = coerce_mcp_config(
        {
            "linear": {
                "url": "https://mcp.linear.app/mcp",
                "auth": {"strategy": "bearer", "value": "lin-api-secret"},
            },
            "superhuman": {
                "url": "https://mcp.mail.superhuman.com/mcp",
                "auth": {
                    "strategy": "oauth2",
                    "authentication": {
                        "type": "oauth",
                        "client_auth_method": "none",
                    },
                },
            },
        }
    )

    agent = OpenHandsAgentSettings(mcp_config=mcp_config).create_agent()

    servers = dump_mcp_config(agent.mcp_config)
    assert servers["linear"]["auth"] == {
        "strategy": "bearer",
        "value": "lin-api-secret",
    }
    assert servers["superhuman"]["auth"] == {
        "strategy": "oauth2",
        "authentication": {
            "type": "oauth",
            "client_auth_method": "none",
        },
    }


def test_openhands_agent_settings_mcp_config_decrypt_legacy_plaintext_on_disk() -> None:
    """加载早于按值加密的设置文件 (env /
    必须不删除这些值：除了有效的 Fernet token 之外，每个值都保持不变，以便下次保存时
    可以重新加密它。
    """
    from openhands.sdk.utils.cipher import Cipher

    cipher = Cipher(secret_key="test-encryption-key")
    legacy_payload = {
        "mcp_config": {
            "github": {
                "command": "uvx",
                "args": ["mcp-server-github"],
                # 明文，如先前（预加密）构建所写
                "env": {"GITHUB_TOKEN": "ghp-legacy-plaintext"},
            }
        }
    }

    restored = OpenHandsAgentSettings.model_validate(
        legacy_payload, context={"cipher": cipher}
    )
    restored_env = dump_mcp_config(restored.mcp_config)["github"]["env"]
    assert isinstance(restored_env, dict)
    assert restored_env["GITHUB_TOKEN"] == "ghp-legacy-plaintext"


def test_openhands_agent_settings_mcp_config_expose_encrypted_requires_cipher() -> None:
    """``expose_secrets="encrypted"`` 没有密码必须提出 — 镜像
    用于各个 ``SecretStr`` 字段的合约
    :func:`serialize_secret`。 Pydantic 包裹内层
    ``PydanticSerializationError`` 中的 ``MissingCipherError``； 智能体-服务器的
    ``translate_missing_cipher`` 遍历原因链以显示 503。
    """
    from pydantic_core import PydanticSerializationError

    from openhands.sdk.utils.pydantic_secrets import MissingCipherError

    settings = OpenHandsAgentSettings(
        mcp_config=coerce_mcp_config(
            {
                "github": {
                    "command": "uvx",
                    "args": ["mcp-server-github"],
                    "env": {"GITHUB_TOKEN": "ghp-secret"},
                }
            }
        )
    )
    with pytest.raises(PydanticSerializationError) as exc_info:
        settings.model_dump(mode="json", context={"expose_secrets": "encrypted"})
    assert MissingCipherError.__name__ in str(exc_info.value)


def test_openhands_agent_settings_mcp_config_expose_plaintext_passes_through() -> None:
    """``expose_secrets="plaintext"`` 必须返回原始环境/标头值
    即使密码也在上下文 (e.g. 具有明确明文暴露的管理员 GET）。
    """
    from openhands.sdk.utils.cipher import Cipher

    settings = OpenHandsAgentSettings(
        mcp_config=coerce_mcp_config(
            {
                "github": {
                    "command": "uvx",
                    "args": ["mcp-server-github"],
                    "env": {"GITHUB_TOKEN": "ghp-secret"},
                }
            }
        )
    )
    cipher = Cipher(secret_key="test-encryption-key")

    dumped = settings.model_dump(
        mode="json",
        context={"cipher": cipher, "expose_secrets": "plaintext"},
    )
    assert dumped["mcp_config"]["github"]["env"]["GITHUB_TOKEN"] == "ghp-secret"


def test_openhands_agent_settings_create_agent_keeps_real_mcp_secrets() -> None:
    # create_agent 必须传递运行时真实环境/标头（字段序列化器编辑 mcp_config 仅用于传输）
    # 。
    #
    mcp_config = coerce_mcp_config(
        {
            "leaky": {
                "command": "echo",
                "args": ["mcp"],
                "env": {"API_KEY": "sk-mcp-secret"},
            }
        }
    )
    agent = OpenHandsAgentSettings(mcp_config=mcp_config).create_agent()

    env = dump_mcp_config(agent.mcp_config)["leaky"]["env"]
    assert isinstance(env, dict)
    assert env["API_KEY"] == "sk-mcp-secret"


def test_acp_agent_settings_mcp_config_redacts_env_and_headers() -> None:
    mcp_config = coerce_mcp_config(
        {
            "leaky": {
                "command": "echo",
                "args": ["mcp"],
                "env": {"API_KEY": "sk-mcp-secret"},
                "headers": {"X-API-Token": "tok-mcp-secret"},
            }
        }
    )
    settings = ACPAgentSettings(acp_command=["echo"], mcp_config=mcp_config)

    blob = settings.model_dump_json()
    assert "sk-mcp-secret" not in blob
    assert "tok-mcp-secret" not in blob

    exposed = settings.model_dump(context={"expose_secrets": True})
    leaky = exposed["mcp_config"]["leaky"]
    env = leaky["env"]
    headers = leaky["headers"]
    assert isinstance(env, dict)
    assert isinstance(headers, dict)
    assert env["API_KEY"] == "sk-mcp-secret"
    assert headers["X-API-Token"] == "tok-mcp-secret"


def test_acp_agent_settings_create_agent_keeps_real_mcp_secrets() -> None:
    # create_agent 必须提供子进程真实环境/标头（字段序列化器编辑 mcp_config 仅用于传输/
    # 存储）。
    #
    mcp_config = coerce_mcp_config(
        {
            "leaky": {
                "command": "echo",
                "args": ["mcp"],
                "env": {"API_KEY": "sk-mcp-secret"},
                "headers": {"X-API-Token": "tok-mcp-secret"},
            }
        }
    )
    agent = ACPAgentSettings(acp_command=["echo"], mcp_config=mcp_config).create_agent()

    assert isinstance(agent, ACPAgent)
    dumped = dump_mcp_config(agent.mcp_config)["leaky"]
    env = dumped["env"]
    headers = dumped["headers"]
    assert isinstance(env, dict)
    assert isinstance(headers, dict)
    assert env["API_KEY"] == "sk-mcp-secret"
    assert headers["X-API-Token"] == "tok-mcp-secret"


# ---------------------------------------------------------------------------
# AgentSettingsBase — 共享接口
# ---------------------------------------------------------------------------


def test_agent_settings_base_is_parent_of_both_variants() -> None:
    assert issubclass(OpenHandsAgentSettings, AgentSettingsBase)
    assert issubclass(ACPAgentSettings, AgentSettingsBase)


def test_agent_settings_base_schema_version_inherited() -> None:
    openhands = OpenHandsAgentSettings()
    acp = ACPAgentSettings(acp_command=["x"])
    assert openhands.schema_version == AGENT_SETTINGS_SCHEMA_VERSION
    assert acp.schema_version == AGENT_SETTINGS_SCHEMA_VERSION


def test_agent_settings_base_export_schema_works_on_both_variants() -> None:
    openhands_schema = OpenHandsAgentSettings.export_schema()
    acp_schema = ACPAgentSettings.export_schema()
    assert openhands_schema.model_name == "OpenHandsAgentSettings"
    assert acp_schema.model_name == "ACPAgentSettings"


def test_agent_settings_base_create_agent_is_callable_via_interface() -> None:
    """两种变体都通过共享基类型公开 create_agent()。"""
    settings: AgentSettingsBase = OpenHandsAgentSettings(llm=LLM(model="test-model"))
    agent = settings.create_agent()
    assert isinstance(agent, Agent)

    acp_settings: AgentSettingsBase = ACPAgentSettings(acp_command=["x"])
    from openhands.sdk.agent.acp_agent import ACPAgent

    acp_agent = acp_settings.create_agent()
    assert isinstance(acp_agent, ACPAgent)


# ---------------------------------------------------------------------------
# ACPAgentSettings — 提供商注册表集成
# ---------------------------------------------------------------------------


def test_acp_settings_provider_info_returns_registry_entry() -> None:
    settings = ACPAgentSettings(acp_server="claude-code")
    info = settings.provider_info
    assert info is not None
    assert info.key == "claude-code"
    assert info.display_name == "Claude Code"


def test_acp_settings_provider_info_returns_none_for_custom() -> None:
    settings = ACPAgentSettings(acp_server="custom", acp_command=["x"])
    assert settings.provider_info is None


def test_acp_settings_api_key_env_var_from_registry() -> None:
    assert (
        ACPAgentSettings(acp_server="claude-code").api_key_env_var
        == "ANTHROPIC_API_KEY"
    )
    assert ACPAgentSettings(acp_server="codex").api_key_env_var == "OPENAI_API_KEY"
    assert ACPAgentSettings(acp_server="gemini-cli").api_key_env_var == "GEMINI_API_KEY"
    # Kimi 没有 env-var API 键； 凭据是 config.toml。
    assert ACPAgentSettings(acp_server="kimi-code").api_key_env_var is None
    assert (
        ACPAgentSettings(acp_server="custom", acp_command=["x"]).api_key_env_var is None
    )


def test_acp_settings_base_url_env_var_from_registry() -> None:
    assert (
        ACPAgentSettings(acp_server="claude-code").base_url_env_var
        == "ANTHROPIC_BASE_URL"
    )
    assert ACPAgentSettings(acp_server="codex").base_url_env_var == "OPENAI_BASE_URL"
    assert (
        ACPAgentSettings(acp_server="gemini-cli").base_url_env_var == "GEMINI_BASE_URL"
    )
    assert ACPAgentSettings(acp_server="kimi-code").base_url_env_var == "KIMI_BASE_URL"
    assert (
        ACPAgentSettings(acp_server="custom", acp_command=["x"]).base_url_env_var
        is None
    )


def test_acp_resolve_command_uses_registry_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from openhands.sdk.settings.acp_install_catalog import (
        PI_ACP_VERSION,
        PI_CODING_AGENT_VERSION,
    )
    from openhands.sdk.settings.acp_providers import ACP_PROVIDERS

    # PATH → 注册表上没有固定的二进制文件，默认情况下会逐字返回。
    monkeypatch.setattr(shutil, "which", lambda _: None)
    for server_key in (
        "claude-code",
        "codex",
        "gemini-cli",
        "kimi-code",
        "pi",
        "opencode",
    ):
        settings = ACPAgentSettings(acp_server=server_key)
        expected = list(ACP_PROVIDERS[server_key].default_command)
        assert settings.resolve_acp_command() == expected
    # Pi 是唯一一个默认安装两个软件包的提供商：pi-ACP 适配器和它生成的 `pi` 引擎 PATH。
    #
    pi_settings = ACPAgentSettings(acp_server="pi")
    assert pi_settings.resolve_acp_command() == [
        "npx",
        "-y",
        "--prefer-offline",
        f"--package=pi-acp@{PI_ACP_VERSION}",
        f"--package=@earendil-works/pi-coding-agent@{PI_CODING_AGENT_VERSION}",
        "pi-acp",
    ]


# ---------------------------------------------------------------------------
# 智能体能力助手
# ---------------------------------------------------------------------------


def test_regular_agent_supports_all_capabilities() -> None:
    agent = OpenHandsAgentSettings(llm=LLM(model="test-model")).create_agent()
    assert agent.supports_openhands_tools is True
    assert agent.supports_condenser is True
    assert agent.agent_kind == "openhands"


def test_acp_agent_reports_no_openhands_capabilities() -> None:
    from openhands.sdk.agent.acp_agent import ACPAgent

    agent = ACPAgent(acp_command=["x"])
    assert agent.supports_openhands_tools is False
    assert agent.supports_condenser is False
    assert agent.agent_kind == "acp"


def test_llm_subscription_fields_roundtrip() -> None:
    settings = validate_agent_settings(
        {
            "llm": {
                "model": "gpt-5.6",
                "auth_type": "subscription",
                "subscription_vendor": "openai",
            }
        }
    )

    assert isinstance(settings, OpenHandsAgentSettings)
    assert settings.llm.auth_type == "subscription"
    assert settings.llm.subscription_vendor == "openai"
    dumped = settings.model_dump(mode="json", exclude_none=True)
    assert dumped["llm"]["auth_type"] == "subscription"
    assert dumped["llm"]["subscription_vendor"] == "openai"
    assert "api_key" not in dumped["llm"]


def test_llm_create_agent_resolves_subscription_llm(monkeypatch) -> None:
    from openhands.sdk.llm.auth import openai

    original_llm = LLM(
        model="gpt-5.6",
        auth_type="subscription",
        subscription_vendor="openai",
    )
    runtime_llm = LLM(model="openai/gpt-5.6")
    runtime_llm.is_subscription = True

    def fake_create_subscription_llm_from_config(llm: LLM) -> LLM:
        assert llm is original_llm
        return runtime_llm

    monkeypatch.setattr(
        openai,
        "create_subscription_llm_from_config",
        fake_create_subscription_llm_from_config,
    )

    agent = OpenHandsAgentSettings(llm=original_llm).create_agent()

    assert agent.llm is runtime_llm
    assert agent.llm.is_subscription is True


def test_llm_from_persisted_rehydrates_subscription_runtime(monkeypatch) -> None:
    from openhands.sdk.llm.auth import openai

    runtime_llm = LLM(model="openai/gpt-5.6", auth_type="subscription")
    runtime_llm.is_subscription = True

    def fake_create_subscription_llm_from_config(llm: LLM) -> LLM:
        assert llm.auth_type == "subscription"
        assert llm.subscription_vendor == "openai"
        return runtime_llm

    monkeypatch.setattr(
        openai,
        "create_subscription_llm_from_config",
        fake_create_subscription_llm_from_config,
    )

    loaded = LLM.from_persisted(
        {
            "model": "gpt-5.6",
            "auth_type": "subscription",
            "subscription_vendor": "openai",
            "schema_version": 1,
        }
    )

    assert loaded is runtime_llm
    assert loaded.is_subscription is True


def test_llm_load_from_env_rehydrates_subscription_runtime(monkeypatch) -> None:
    from openhands.sdk.llm.auth import openai

    runtime_llm = LLM(model="openai/gpt-5.6", auth_type="subscription")
    runtime_llm.is_subscription = True

    def fake_create_subscription_llm_from_config(llm: LLM) -> LLM:
        assert llm.auth_type == "subscription"
        assert llm.subscription_vendor == "openai"
        assert llm.model == "gpt-5.6"
        return runtime_llm

    monkeypatch.setenv("LLM_MODEL", "gpt-5.6")
    monkeypatch.setenv("LLM_AUTH_TYPE", "subscription")
    monkeypatch.setenv("LLM_SUBSCRIPTION_VENDOR", "openai")
    monkeypatch.setattr(
        openai,
        "create_subscription_llm_from_config",
        fake_create_subscription_llm_from_config,
    )

    loaded = LLM.load_from_env()

    assert loaded is runtime_llm
    assert loaded.is_subscription is True


def test_create_subscription_llm_from_config_preserves_runtime_llm(monkeypatch) -> None:
    import openhands.sdk.llm.auth.openai as openai_auth
    from openhands.sdk.llm.auth.credentials import OAuthCredentials

    class UnexpectedAuth:
        def __init__(self, *args, **kwargs):
            raise AssertionError("runtime subscription LLM should not be rehydrated")

    monkeypatch.setattr(openai_auth, "OpenAISubscriptionAuth", UnexpectedAuth)
    runtime_llm = LLM(
        model="openai/gpt-5.6",
        auth_type="subscription",
        subscription_vendor="openai",
    )
    runtime_llm.is_subscription = True
    runtime_llm._subscription_credentials = OAuthCredentials(
        vendor="openai",
        access_token="access-token",
        refresh_token="refresh-token",
        expires_at=4_102_444_800_000,
    )

    assert openai_auth.create_subscription_llm_from_config(runtime_llm) is runtime_llm


def test_llm_from_persisted_rebuilds_serialized_subscription_runtime(
    monkeypatch,
) -> None:
    import openhands.sdk.llm.auth.openai as openai_auth
    from openhands.sdk.llm.auth.credentials import OAuthCredentials
    from openhands.sdk.llm.auth.openai import OpenAISubscriptionAuth

    credentials = OAuthCredentials(
        vendor="openai",
        access_token="access-token",
        refresh_token="refresh-token",
        expires_at=4_102_444_800_000,
    )
    monkeypatch.setattr(openai_auth, "_extract_chatgpt_account_id", lambda _: None)
    monkeypatch.setattr(
        OpenAISubscriptionAuth,
        "refresh_if_needed_sync",
        lambda self: credentials,
    )

    source = OpenAISubscriptionAuth().create_llm(
        model="gpt-5.6-sol",
        credentials=credentials,
    )
    persisted = source.to_persisted()

    assert persisted["is_subscription"] is True
    assert "base_url" not in persisted

    loaded = LLM.from_persisted(persisted)

    assert loaded is not source
    assert loaded.model == "openai/gpt-5.6-sol"
    assert loaded.base_url == "https://chatgpt.com/backend-api/codex"
    assert loaded.is_subscription is True
    assert loaded.extra_headers is not None
    assert loaded.extra_headers["originator"] == "codex_cli_rs"
    assert loaded.extra_headers["OpenAI-Beta"] == "responses=experimental"
    assert loaded._subscription_credentials is credentials
    assert loaded._get_litellm_api_key_value() == "access-token"


@pytest.mark.asyncio
async def test_async_subscription_api_key_uses_async_refresh(monkeypatch) -> None:
    import openhands.sdk.llm.auth.openai as openai_auth
    from openhands.sdk.llm.auth.credentials import OAuthCredentials

    credentials = OAuthCredentials(
        vendor="openai",
        access_token="access-token",
        refresh_token="refresh-token",
        expires_at=4_102_444_800_000,
    )

    class FakeAuth:
        def __init__(self, credential_store=None):
            self.credential_store = credential_store

        async def refresh_if_needed(self):
            return credentials

        def refresh_if_needed_sync(self):
            raise AssertionError("async transport must not sync-refresh credentials")

        def extract_chatgpt_account_id(self, refreshed_credentials):
            assert refreshed_credentials is credentials
            return "account-id"

    monkeypatch.setattr(openai_auth, "OpenAISubscriptionAuth", FakeAuth)
    llm = LLM(
        model="openai/gpt-5.6",
        auth_type="subscription",
        subscription_vendor="openai",
    )
    llm.is_subscription = True

    api_key, extra_headers = await llm._aget_litellm_auth_values()
    assert api_key == "access-token"
    assert extra_headers["chatgpt-account-id"] == "account-id"
    assert llm.extra_headers is None


def test_sync_subscription_api_key_uses_valid_runtime_credentials(
    monkeypatch,
) -> None:
    import openhands.sdk.llm.auth.openai as openai_auth
    from openhands.sdk.llm.auth.credentials import OAuthCredentials

    credentials = OAuthCredentials(
        vendor="openai",
        access_token="access-token",
        refresh_token="refresh-token",
        expires_at=4_102_444_800_000,
    )

    class FakeAuth:
        def __init__(self, credential_store=None):
            self.credential_store = credential_store

        def refresh_if_needed_sync(self):
            raise AssertionError("valid runtime credentials should not sync-refresh")

        def extract_chatgpt_account_id(self, refreshed_credentials):
            assert refreshed_credentials is credentials
            return "account-id"

    monkeypatch.setattr(openai_auth, "OpenAISubscriptionAuth", FakeAuth)
    llm = LLM(
        model="openai/gpt-5.6",
        auth_type="subscription",
        subscription_vendor="openai",
    )
    llm.is_subscription = True
    llm._subscription_credentials = credentials

    api_key, extra_headers = llm._get_litellm_auth_values()
    assert api_key == "access-token"
    assert extra_headers["chatgpt-account-id"] == "account-id"
    assert llm.extra_headers is None


def test_openai_subscription_create_llm_serializes_subscription_auth(
    monkeypatch,
) -> None:
    import openhands.sdk.llm.auth.openai as openai_auth
    from openhands.sdk.llm.auth.credentials import OAuthCredentials
    from openhands.sdk.llm.auth.openai import OpenAISubscriptionAuth

    monkeypatch.setattr(openai_auth, "_extract_chatgpt_account_id", lambda _: None)

    llm = OpenAISubscriptionAuth().create_llm(
        model="gpt-5.6-sol",
        credentials=OAuthCredentials(
            vendor="openai",
            access_token="access-token",
            refresh_token="refresh-token",
            expires_at=4_102_444_800_000,
        ),
        usage_id="profile:test",
    )

    assert llm.auth_type == "subscription"
    assert llm.subscription_vendor == "openai"
    assert llm.api_key is None
    assert llm.to_persisted()["auth_type"] == "subscription"
    assert llm.to_persisted()["subscription_vendor"] == "openai"
    assert "api_key" not in llm.to_persisted(context={"expose_secrets": "plaintext"})
    assert "base_url" not in llm.to_persisted()


def test_create_subscription_llm_from_config_preserves_non_auth_options(
    monkeypatch,
) -> None:
    import openhands.sdk.llm.auth.openai as openai_auth
    from openhands.sdk.llm.auth.credentials import OAuthCredentials

    captured: dict[str, object] = {}

    class FakeAuth:
        def refresh_if_needed_sync(self):
            return OAuthCredentials(
                vendor="openai",
                access_token="access-token",
                refresh_token="refresh-token",
                expires_at=4_102_444_800_000,
            )

        def create_llm(self, **kwargs):
            captured.update(kwargs)
            return LLM(
                model=f"openai/{kwargs['model']}",
                auth_type="subscription",
                subscription_vendor="openai",
                usage_id=kwargs["usage_id"],
                timeout=kwargs["timeout"],
            )

    monkeypatch.setattr(openai_auth, "OpenAISubscriptionAuth", FakeAuth)
    source = LLM(
        model="gpt-5.6",
        auth_type="subscription",
        subscription_vendor="openai",
        usage_id="profile:test",
        timeout=123,
    )

    runtime = openai_auth.create_subscription_llm_from_config(source)

    assert runtime.usage_id == "profile:test"
    assert runtime.timeout == 123
    assert captured["usage_id"] == "profile:test"
    assert captured["timeout"] == 123
    assert "api_key" not in captured
    assert "base_url" not in captured
    assert "is_subscription" not in captured


@pytest.mark.parametrize("tools", [None, [], [{"name": "terminal"}]])
def test_saved_v8_retired_switches_are_discarded_without_crashing(tools) -> None:
    settings = OpenHandsAgentSettings.from_persisted(
        {
            "schema_version": 8,
            "llm": {"model": "m"},
            "tools": tools,
            "enable_sub_agents": True,
            "enable_switch_llm_tool": False,
        }
    )
    dumped = settings.model_dump(mode="json")
    assert dumped["tools"] == (
        None
        if tools is None
        else [{"name": tool["name"], "params": {}} for tool in tools]
    )
    assert (
        OpenHandsAgentSettings.from_persisted(dumped).model_dump(mode="json") == dumped
    )
    assert "enable_sub_agents" not in dumped
    assert "enable_switch_llm_tool" not in dumped
    with pytest.raises(AttributeError):
        getattr(settings, "enable_sub_agents")


@pytest.mark.parametrize("schema_version", [None, 6, 7, 8])
def test_saved_acp_llm_is_discarded_without_leaking_credentials(schema_version) -> None:
    settings = ACPAgentSettings.from_persisted(
        {
            "schema_version": schema_version,
            "agent_kind": "acp",
            "acp_model": "sonnet",
            "llm": {"model": "ignored", "api_key": "sk-old"},
            "enable_sub_agents": True,
        }
    )
    assert settings.acp_model == "sonnet"
    assert "sk-old" not in settings.model_dump_json(context={"expose_secrets": True})
    assert settings.create_agent().llm.usage_id == ACP_SENTINEL_USAGE_ID
