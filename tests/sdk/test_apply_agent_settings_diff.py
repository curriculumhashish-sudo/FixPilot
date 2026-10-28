"""测试：func:`apply_agent_settings_diff` 和 ``llm`` 规范化。

``agent_settings`` 是一个受歧视的工会。 应用稀疏差异必须处理
``agent_kind`` 作为一种单向缩小门：切换变体取代基本的相同变体编辑深度合并。 设置将之
前手动滚动的内容存储在多个位置； 这锻炼了单一SDK所有者。
"""

import pytest
from pydantic import SecretStr

from openhands.sdk import apply_agent_settings_diff, validate_agent_settings
from openhands.sdk.settings.model import (
    AGENT_SETTINGS_SCHEMA_VERSION,
    ACPAgentSettings,
    LLMAgentSettings,
    OpenHandsAgentSettings,
)


# ── agent_kind是缩小门，不是转换旋钮──────────────


def test_switch_openhands_to_acp_replaces_with_fresh_variant() -> None:
    base = {"agent_kind": "openhands", "llm": {"model": "gpt"}}

    result = apply_agent_settings_diff(
        base, {"agent_kind": "acp", "acp_server": "claude-code"}
    )

    assert isinstance(result, ACPAgentSettings)
    assert result.acp_server == "claude-code"
    # ACP的agent_context可以为空； OpenHands llm.model 未被携带。
    assert result.agent_context is None


def test_switch_to_acp_drops_persona() -> None:
    base = {"agent_kind": "openhands", "llm": {"model": "gpt"}, "persona": "x"}

    result = apply_agent_settings_diff(
        base, {"agent_kind": "acp", "acp_server": "claude-code"}
    )

    assert isinstance(result, ACPAgentSettings)
    assert "persona" not in result.model_dump()


def test_none_in_diff_clears_persona() -> None:
    base = {"agent_kind": "openhands", "llm": {"model": "gpt"}, "persona": "x"}

    result = apply_agent_settings_diff(base, {"persona": None})

    assert isinstance(result, OpenHandsAgentSettings)
    assert result.persona is None


def test_switch_acp_to_openhands_replaces_with_fresh_variant() -> None:
    base = {"agent_kind": "acp", "acp_server": "claude-code"}

    result = apply_agent_settings_diff(
        base, {"agent_kind": "openhands", "llm": {"model": "gpt"}}
    )

    assert isinstance(result, OpenHandsAgentSettings)
    assert result.agent_kind == "openhands"
    assert result.llm.model == "gpt"


def test_inline_fields_land_on_fresh_base_during_switch() -> None:
    base = {"agent_kind": "acp", "acp_server": "claude-code"}

    result = apply_agent_settings_diff(
        base, {"agent_kind": "openhands", "llm": {"model": "model-c"}}
    )

    assert isinstance(result, OpenHandsAgentSettings)
    assert result.llm.model == "model-c"


# ── 同变体深度合并────────────────────────────────────────────


def test_same_kind_deep_merges_within_variant() -> None:
    base = {
        "agent_kind": "openhands",
        "llm": {"model": "gpt", "temperature": 0.5},
    }

    result = apply_agent_settings_diff(base, {"llm": {"temperature": 0.9}})

    assert isinstance(result, OpenHandsAgentSettings)
    # 保留未触及的嵌套键； 仅温度变化
    assert result.llm.model == "gpt"
    assert result.llm.temperature == 0.9


def test_diff_without_agent_kind_keeps_base_kind() -> None:
    base = {"agent_kind": "acp", "acp_server": "claude-code"}

    result = apply_agent_settings_diff(base, {"acp_model": "claude-opus-4-6"})

    assert isinstance(result, ACPAgentSettings)
    assert result.acp_server == "claude-code"
    assert result.acp_model == "claude-opus-4-6"


def test_none_in_diff_unsets_key_merge_patch() -> None:
    base = {"agent_kind": "acp", "acp_server": "claude-code", "acp_model": "x"}

    result = apply_agent_settings_diff(base, {"acp_model": None})

    assert isinstance(result, ACPAgentSettings)
    assert result.acp_model is None


def test_empty_diff_returns_validated_base() -> None:
    base = {"agent_kind": "acp", "acp_server": "claude-code"}

    for diff in ({}, None):
        result = apply_agent_settings_diff(base, diff)
        assert isinstance(result, ACPAgentSettings)
        assert result.acp_server == "claude-code"


# ── 接受为字典或实例的基础； 机密 survive ─────────────────


def test_base_may_be_a_settings_instance() -> None:
    base = OpenHandsAgentSettings.model_validate({"llm": {"model": "gpt"}})

    result = apply_agent_settings_diff(base, {"llm": {"model": "claude"}})

    assert isinstance(result, OpenHandsAgentSettings)
    assert result.llm.model == "claude"


def test_secret_in_base_survives_same_kind_merge() -> None:
    base = OpenHandsAgentSettings.model_validate(
        {"llm": {"model": "gpt", "api_key": "sk-SECRET"}}
    )

    # diff 触及不相关的领域； 基数 api_key 不得被掩盖。
    result = apply_agent_settings_diff(base, {"llm": {"model": "claude"}})

    assert isinstance(result, OpenHandsAgentSettings)
    assert isinstance(result.llm.api_key, SecretStr)
    assert result.llm.api_key.get_secret_value() == "sk-SECRET"
    assert result.llm.model == "claude"


# ── llm 标签规范化（关闭 schema_version 门控间隙）──────


def test_validate_canonicalizes_llm_tag_at_current_schema_version() -> None:
    # v1->v2 迁移仅在前进 schema_version 时重命名 'llm'； 当前版本中已有的“llm”载荷仍必
    # 须规范化。
    #
    result = validate_agent_settings(
        {
            "agent_kind": "llm",
            "schema_version": AGENT_SETTINGS_SCHEMA_VERSION,
            "llm": {"model": "legacy"},
        }
    )

    assert type(result) is OpenHandsAgentSettings
    assert result.agent_kind == "openhands"
    assert result.llm.model == "legacy"


def test_apply_diff_on_llm_tagged_base_returns_openhands() -> None:
    base = {
        "agent_kind": "llm",
        "schema_version": AGENT_SETTINGS_SCHEMA_VERSION,
        "llm": {"model": "legacy"},
    }

    result = apply_agent_settings_diff(base, {"llm": {"model": "new"}})

    assert type(result) is OpenHandsAgentSettings
    assert result.agent_kind == "openhands"
    assert result.llm.model == "new"


def test_validate_never_returns_llm_subclass() -> None:
    for version in range(0, AGENT_SETTINGS_SCHEMA_VERSION + 1):
        result = validate_agent_settings(
            {"agent_kind": "llm", "schema_version": version, "llm": {"model": "m"}}
        )
        assert not isinstance(result, LLMAgentSettings)
        assert result.agent_kind == "openhands"


# ── 已弃用类对于向后兼容仍然是可导入的 ──────────────


def test_llm_agent_settings_remains_importable() -> None:
    from openhands.sdk.settings.model import LLMAgentSettings as _LLM

    assert issubclass(_LLM, OpenHandsAgentSettings)


@pytest.mark.parametrize("patch", [{}, {"persona": "updated"}])
def test_diff_loads_unversioned_persisted_openhands_base(patch) -> None:
    result = apply_agent_settings_diff(
        {"agent_kind": "openhands", "enable_sub_agents": True}, patch
    )
    assert isinstance(result, OpenHandsAgentSettings)
    if patch:
        assert result.persona == "updated"


@pytest.mark.parametrize("patch", [{}, {"acp_model": "sonnet"}])
def test_diff_loads_unversioned_persisted_acp_base(patch) -> None:
    result = apply_agent_settings_diff(
        {"agent_kind": "acp", "llm": {"model": "old"}}, patch
    )
    assert isinstance(result, ACPAgentSettings)
    assert result.acp_model == patch.get("acp_model")
    assert "llm" not in result.model_dump()
