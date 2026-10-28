"""防止重复或漂移的硬编码数据。

遥测包故意重复使用其他地方已经存在的定义，而不是重述它们。 如果副本再次出现，或者硬编
码名称默默地停止与其来源的库匹配，这些测试就会失败。
"""

import builtins

import pytest

from openhands.agent_server.telemetry import models as m
from openhands.agent_server.telemetry.factory import build_runtime_properties
from openhands.agent_server.telemetry.sanitizer import (
    _FIRST_PARTY_ROOT,
    _MODEL_FAMILY_HINTS,
    _known_providers,
)
from openhands.agent_server.telemetry.subscriber import (
    _FAILURE_STATUSES,
    _TERMINAL_STATUSES,
)
from openhands.sdk.conversation.state import ConversationExecutionStatus


# ── 单一定义────────────────────────────────────────────────────


# ── 派生的，非硬编码的────────────────────────────────────────────────


def test_terminal_statuses_come_from_the_sdk_enum():
    """新的终端状态不得悄然停止报告。"""
    expected = {s.value for s in ConversationExecutionStatus if s.is_terminal()}
    assert _TERMINAL_STATUSES == expected
    assert _FAILURE_STATUSES == expected - {ConversationExecutionStatus.FINISHED.value}


def test_full_state_key_comes_from_the_sdk():
    import openhands.agent_server.telemetry.subscriber as sub
    from openhands.sdk.event.conversation_state import FULL_STATE_KEY

    assert "_FULL_STATE_KEY" not in vars(sub), (
        "the full_state key is defined in the SDK; do not restate it here"
    )
    assert FULL_STATE_KEY == "full_state"


def test_first_party_root_is_derived_not_hardcoded():
    """它必须跟踪它所在的包，而不是可能会过时的字面意思。"""
    import openhands.agent_server.telemetry.sanitizer as sanitizer

    assert _FIRST_PARTY_ROOT == sanitizer.__name__.split(".", 1)[0]
    assert _FIRST_PARTY_ROOT == "openhands"  # 当前值，为了可读性


def test_consent_literal_has_one_definition():
    """由于不存在键入的设置字段，策略拥有 TelemetryConsent。"""
    from openhands.agent_server.persistence import models as persisted

    assert not hasattr(persisted, "TelemetryConsent"), (
        "consent lives in misc_settings.telemetry; there is no typed field"
    )
    assert "telemetry_consent" not in persisted.PersistedSettings.model_fields


def test_no_deployment_mode_concept_remains():
    """后续从SDK和智能体-服务器中删除了云模式。"""
    import openhands.agent_server.config as config_mod

    assert not hasattr(config_mod, "TelemetryMode")
    assert "mode" not in config_mod.TelemetrySpec.model_fields
    assert "deployment_mode" not in m.EXPECTED_PROPERTY_NAMES
    assert "deployment_mode" not in m.RuntimeProperties.model_fields


def test_deployment_kind_is_a_runtime_property_not_a_mode():
    import openhands.agent_server.config as config_mod

    assert (
        config_mod.TelemetrySpec(deployment_kind="remote").deployment_kind == "remote"
    )
    assert m.RuntimeProperties.model_fields["deployment_kind"].default == "local"
    assert (
        build_runtime_properties(
            deferred_init=False, deployment_kind="remote"
        ).deployment_kind
        == "remote"
    )


def test_versions_match_server_info():
    """遥测和 /server_info 决不能对正在运行的内容产生分歧。"""
    from openhands.agent_server.server_details_router import ServerInfo

    info = ServerInfo(uptime=0.0, idle_time=0.0)
    runtime = build_runtime_properties(deferred_init=False)

    assert runtime.server_version == info.version
    assert runtime.sdk_version == info.sdk_version
    assert runtime.tools_version == info.tools_version
    assert runtime.build_git_sha == info.build_git_sha
    assert runtime.build_git_ref == info.build_git_ref


# ── 硬编码的名称仍然与其来源相符──────────────────────────────

_LITELLM_NAMES = {
    "APIConnectionError",
    "APIError",
    "AuthenticationError",
    "BadRequestError",
    "ContextWindowExceededError",
    "InternalServerError",
    "PermissionDeniedError",
    "RateLimitError",
    "ServiceUnavailableError",
    "Timeout",
    "UnprocessableEntityError",
}
_HTTPX_NAMES = {"ConnectError", "ReadTimeout", "HTTPStatusError"}


@pytest.mark.parametrize("name", sorted(_LITELLM_NAMES))
def test_litellm_error_names_still_exist(name: str):
    """LiteLLM 重命名会默默地将错误放入“未知”。"""
    import litellm.exceptions

    assert hasattr(litellm.exceptions, name)
    assert name in m.ERROR_CATEGORY_BY_CLASS_NAME


@pytest.mark.parametrize("name", sorted(_HTTPX_NAMES))
def test_httpx_error_names_still_exist(name: str):
    import httpx

    assert hasattr(httpx, name)
    assert name in m.ERROR_CATEGORY_BY_CLASS_NAME


def test_builtin_error_names_still_exist():
    named = set(m.ERROR_CATEGORY_BY_CLASS_NAME) & set(dir(builtins))
    assert named, "expected some builtin exceptions in the category table"
    for name in named:
        assert issubclass(getattr(builtins, name), BaseException)


def test_model_family_hints_target_real_providers():
    """每个提示都必须解析为实际知道的提供者 LiteLLM。"""
    providers = _known_providers()
    unknown = sorted({family for _, family in _MODEL_FAMILY_HINTS} - providers)
    assert unknown == [], f"model family hints not in litellm.provider_list: {unknown}"


def test_provider_list_is_sourced_from_litellm():
    import litellm

    assert _known_providers() >= {"anthropic", "openai"}
    assert len(_known_providers()) == len(
        {str(getattr(p, "value", p)).lower() for p in litellm.provider_list}
    )
