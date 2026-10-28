"""对 ``AgentProfile`` 类型歧视联合的测试。

镜像 ``AgentSettingsConfig`` 测试 union ``tests/sdk/test_settings.py``确认两种变体的
往返传输
``agent_kind``确认交叉变异字段被拒绝，并确认  ``mcp_server_refs`` null/[] 区分。 添加
了针对特定配置文件的合同： 机密免费的
REST.
"""

import json
from uuid import UUID, uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from openhands.sdk.profiles import (
    AGENT_PROFILE_SCHEMA_VERSION,
    ACPAgentProfile,
    AgentProfile,
    AgentProfileInfo,
    AgentProfileListResponse,
    OpenHandsAgentProfile,
    validate_agent_profile,
)
from openhands.sdk.profiles.agent_profile import (
    AgentProfileBase,
    _agent_profile_discriminator,
)


_ADAPTER: TypeAdapter[OpenHandsAgentProfile | ACPAgentProfile] = TypeAdapter(
    AgentProfile
)


def test_agent_profile_info_agent_kind_schema_stays_string_compatible() -> None:
    schema = AgentProfileInfo.model_json_schema()

    agent_kind_schema = schema["properties"]["agent_kind"]
    assert agent_kind_schema["type"] == "string"
    assert "enum" not in agent_kind_schema


def test_agent_profile_info_accepts_acp_summary_with_null_llm_ref() -> None:
    summary = AgentProfileInfo.model_validate(
        {
            "id": str(uuid4()),
            "name": "codex",
            "agent_kind": "acp",
            "revision": 7,
            "llm_profile_ref": None,
            "mcp_server_refs": ["github"],
        }
    )

    assert summary.name == "codex"
    assert summary.agent_kind == "acp"
    assert summary.llm_profile_ref is None
    assert summary.mcp_server_refs == ["github"]


def test_agent_profile_list_response_validates_profile_summaries() -> None:
    response = AgentProfileListResponse.model_validate(
        {
            "profiles": [
                {
                    "id": str(uuid4()),
                    "name": "default",
                    "agent_kind": "openhands",
                    "llm_profile_ref": "default",
                }
            ],
            "active_agent_profile_id": None,
        }
    )

    assert response.profiles[0].name == "default"
    assert response.profiles[0].llm_profile_ref == "default"


# ---------------------------------------------------------------------------
# 施工+往返
# ---------------------------------------------------------------------------


def test_openhands_profile_round_trips() -> None:
    profile = OpenHandsAgentProfile(
        name="my-openhands",
        llm_profile_ref="default",
        revision=3,
        mcp_server_refs=["fetch"],
        disabled_skills=["pdf-tools"],
        system_message_suffix="be terse",
        tool_concurrency_limit=4,
    )
    reloaded = validate_agent_profile(profile.model_dump(mode="json"))

    assert isinstance(reloaded, OpenHandsAgentProfile)
    assert reloaded == profile
    assert reloaded.agent_kind == "openhands"
    assert reloaded.agent == "CodeActAgent"
    assert reloaded.llm_profile_ref == "default"
    assert reloaded.revision == 3
    assert reloaded.mcp_server_refs == ["fetch"]
    assert reloaded.disabled_skills == ["pdf-tools"]
    assert reloaded.tool_concurrency_limit == 4


def test_openhands_profile_new_field_defaults() -> None:
    """``enable_switch_llm_tool`` 默认值 True（全局奇偶校验）； ``disabled_skills``
    默认值 ``[]`` — 拒绝列表从空开始，因此未设置的字段意味着“所有发现的技能”(#4017)。
     技能是通过排除来选择的，而不是可能悬而未决的允许名单。
    """
    profile = OpenHandsAgentProfile(name="oh", llm_profile_ref="default")
    assert profile.disabled_skills == []
    reloaded = validate_agent_profile(
        {"agent_kind": "openhands", "name": "oh", "llm_profile_ref": "default"}
    )
    assert isinstance(reloaded, OpenHandsAgentProfile)
    assert reloaded.disabled_skills == []


def test_default_profile_preserves_explicit_empty_tools() -> None:
    profile = OpenHandsAgentProfile(
        name="default", llm_profile_ref="default", revision=0, tools=[]
    )

    assert profile.tools == []


def test_disabled_skills_round_trips() -> None:
    """非空拒绝列表在 JSON 往返中逐字保留。"""
    profile = validate_agent_profile(
        OpenHandsAgentProfile(
            name="oh", llm_profile_ref="default", disabled_skills=["a", "b"]
        ).model_dump(mode="json")
    )
    assert isinstance(profile, OpenHandsAgentProfile)
    assert profile.disabled_skills == ["a", "b"]


def test_acp_profile_has_no_skill_field() -> None:
    """ACP 个人资料根本不包含技能选择字段 — 子进程拥有
    它的工具和提示词上下文 (#4017)。 ``extra="forbid"`` 拒绝流浪者
    ``skill_refs``/``disabled_skills`` 上的 ACP 载荷。"""
    from openhands.sdk.profiles import ACPAgentProfile

    profile = ACPAgentProfile(name="acp", acp_server="claude-code")
    assert not hasattr(profile, "skill_refs")
    assert not hasattr(profile, "disabled_skills")
    with pytest.raises(ValidationError):
        validate_agent_profile(
            {
                "agent_kind": "acp",
                "name": "acp",
                "acp_server": "claude-code",
                "disabled_skills": ["x"],
            }
        )


def test_persona_round_trips_and_defaults_to_none() -> None:
    assert OpenHandsAgentProfile(name="oh", llm_profile_ref="d").persona is None
    profile = validate_agent_profile(
        OpenHandsAgentProfile(
            name="oh", llm_profile_ref="d", persona="You are a reviewer."
        ).model_dump(mode="json")
    )
    assert isinstance(profile, OpenHandsAgentProfile)
    assert profile.persona == "You are a reviewer."


@pytest.mark.parametrize("persona", ["", "x" * 65537])
def test_persona_rejects_empty_and_oversized(persona: str) -> None:
    with pytest.raises(ValidationError):
        OpenHandsAgentProfile(name="oh", llm_profile_ref="d", persona=persona)


def test_acp_profile_rejects_persona() -> None:
    with pytest.raises(ValidationError):
        validate_agent_profile(
            {
                "agent_kind": "acp",
                "name": "acp",
                "acp_server": "claude-code",
                "persona": "x",
            }
        )


def test_acp_profile_round_trips() -> None:
    profile = ACPAgentProfile(
        name="my-acp",
        acp_server="codex",
        acp_model="gpt-5.5/medium",
        acp_session_mode="full-access",
        acp_prompt_timeout=600.0,
        acp_command="codex-acp",
        acp_args=["--flag"],
        mcp_server_refs=None,
    )
    reloaded = validate_agent_profile(profile.model_dump(mode="json"))

    assert isinstance(reloaded, ACPAgentProfile)
    assert reloaded == profile
    assert reloaded.agent_kind == "acp"
    assert reloaded.acp_server == "codex"
    assert reloaded.acp_model == "gpt-5.5/medium"
    assert reloaded.acp_command == "codex-acp"
    assert reloaded.acp_args == ["--flag"]
    assert reloaded.mcp_server_refs is None


def test_acp_profile_minimal_defaults() -> None:
    profile = validate_agent_profile({"agent_kind": "acp", "name": "minimal"})

    assert isinstance(profile, ACPAgentProfile)
    assert profile.acp_server == "claude-code"
    assert profile.acp_model is None
    assert profile.acp_session_mode is None
    assert profile.acp_prompt_timeout == 1800.0
    assert profile.acp_command is None
    assert profile.acp_args is None


# ---------------------------------------------------------------------------
# 鉴别器 + 验证
# ---------------------------------------------------------------------------


def test_agent_profile_discriminator_declared_on_base():
    """AgentProfileBase 声明 agent_kind。

    判别器直接访问它，无需 getattr。
    """
    base = AgentProfileBase(name="test-profile")
    assert base.agent_kind == "openhands"
    assert _agent_profile_discriminator(base) == "openhands"

    openhands_profile = OpenHandsAgentProfile(
        name="test-openhands", llm_profile_ref="default"
    )
    assert openhands_profile.agent_kind == "openhands"
    assert _agent_profile_discriminator(openhands_profile) == "openhands"

    acp_profile = ACPAgentProfile(name="test-acp")
    assert acp_profile.agent_kind == "acp"
    assert _agent_profile_discriminator(acp_profile) == "acp"


def test_validate_dispatches_on_agent_kind() -> None:
    openhands = validate_agent_profile(
        {"agent_kind": "openhands", "name": "oh", "llm_profile_ref": "default"}
    )
    assert isinstance(openhands, OpenHandsAgentProfile)
    assert openhands.agent_kind == "openhands"

    acp = validate_agent_profile(
        {"agent_kind": "acp", "name": "acp", "acp_model": "claude-opus-4-8"}
    )
    assert isinstance(acp, ACPAgentProfile)
    assert acp.agent_kind == "acp"


def test_missing_discriminator_defaults_to_openhands() -> None:
    profile = validate_agent_profile({"name": "oh", "llm_profile_ref": "default"})
    assert isinstance(profile, OpenHandsAgentProfile)
    assert profile.agent_kind == "openhands"


def test_type_adapter_narrows_directly() -> None:
    """裸 ``TypeAdapter(AgentProfile)``（无迁移）正确缩小。"""
    acp = _ADAPTER.validate_python({"agent_kind": "acp", "name": "acp"})
    assert isinstance(acp, ACPAgentProfile)


def test_validate_passes_through_instances() -> None:
    profile = OpenHandsAgentProfile(name="oh", llm_profile_ref="default")
    assert validate_agent_profile(profile) is profile


def test_validate_rejects_non_mapping() -> None:
    with pytest.raises(TypeError, match="must be a mapping or BaseModel"):
        validate_agent_profile(["not", "a", "mapping"])


# ---------------------------------------------------------------------------
# 跨变体字段拒绝（extra=“forbid”）
# ---------------------------------------------------------------------------


def test_acp_rejects_llm_profile_ref() -> None:
    with pytest.raises(ValidationError):
        validate_agent_profile(
            {"agent_kind": "acp", "name": "acp", "llm_profile_ref": "default"}
        )


def test_openhands_rejects_acp_fields() -> None:
    for acp_field, value in (
        ("acp_server", "codex"),
        ("acp_model", "gpt-5.5/medium"),
        ("acp_command", "codex-acp"),
        ("acp_args", ["--flag"]),
        ("acp_session_mode", "full-access"),
        ("acp_prompt_timeout", 600.0),
    ):
        with pytest.raises(ValidationError):
            validate_agent_profile(
                {
                    "agent_kind": "openhands",
                    "name": "oh",
                    "llm_profile_ref": "default",
                    acp_field: value,
                }
            )


def test_openhands_requires_llm_profile_ref() -> None:
    with pytest.raises(ValidationError):
        validate_agent_profile({"agent_kind": "openhands", "name": "oh"})


def test_acp_rejects_unknown_acp_server() -> None:
    with pytest.raises(ValidationError):
        validate_agent_profile(
            {"agent_kind": "acp", "name": "acp", "acp_server": "not-a-provider"}
        )


# ---------------------------------------------------------------------------
# mcp_server_refs: null 与 [] 不同
# ---------------------------------------------------------------------------


def test_mcp_server_refs_null_vs_empty_are_distinct() -> None:
    use_all = validate_agent_profile(
        {"name": "a", "llm_profile_ref": "d", "mcp_server_refs": None}
    )
    use_none = validate_agent_profile(
        {"name": "b", "llm_profile_ref": "d", "mcp_server_refs": []}
    )
    subset = validate_agent_profile(
        {"name": "c", "llm_profile_ref": "d", "mcp_server_refs": ["fetch"]}
    )

    assert use_all.mcp_server_refs is None
    assert use_none.mcp_server_refs == []
    assert subset.mcp_server_refs == ["fetch"]

    # 该区别必须在序列化 → 重新加载往返过程中保持不变。
    assert (
        validate_agent_profile(use_all.model_dump(mode="json")).mcp_server_refs is None
    )
    assert (
        validate_agent_profile(use_none.model_dump(mode="json")).mcp_server_refs == []
    )


def test_mcp_server_refs_default_is_null() -> None:
    profile = OpenHandsAgentProfile(name="oh", llm_profile_ref="d")
    assert profile.mcp_server_refs is None


# ---------------------------------------------------------------------------
# schema_version + 迁移
# ---------------------------------------------------------------------------


def test_schema_version_defaults_to_current() -> None:
    profile = OpenHandsAgentProfile(name="oh", llm_profile_ref="d")
    assert profile.schema_version == AGENT_PROFILE_SCHEMA_VERSION


def test_payload_missing_schema_version_canonicalizes() -> None:
    payload = {"agent_kind": "acp", "name": "acp"}
    assert "schema_version" not in payload
    profile = validate_agent_profile(payload)
    assert profile.schema_version == AGENT_PROFILE_SCHEMA_VERSION


def test_schemaless_default_preserves_explicit_empty_tools() -> None:
    profile = validate_agent_profile(
        {
            "name": "default",
            "llm_profile_ref": "default",
            "revision": 0,
            "tools": [],
        }
    )
    assert isinstance(profile, OpenHandsAgentProfile)
    assert profile.tools == []


def test_v1_untouched_default_migrates_empty_tools_to_null() -> None:
    profile = validate_agent_profile(
        {
            "schema_version": 1,
            "name": "default",
            "llm_profile_ref": "default",
            "revision": 0,
            "tools": [],
        }
    )
    assert isinstance(profile, OpenHandsAgentProfile)
    assert profile.schema_version == AGENT_PROFILE_SCHEMA_VERSION
    assert profile.tools is None


@pytest.mark.parametrize(
    "skills",
    [[], [{"name": "old-skill", "content": "do stuff"}]],
)
def test_v1_profile_migrates_legacy_embedded_skills(skills: list[object]) -> None:
    profile = validate_agent_profile(
        {
            "schema_version": 1,
            "name": "default",
            "llm_profile_ref": "default",
            "revision": 0,
            "skills": skills,
        }
    )

    assert isinstance(profile, OpenHandsAgentProfile)
    assert profile.schema_version == AGENT_PROFILE_SCHEMA_VERSION
    assert profile.disabled_skills == []


@pytest.mark.parametrize("schema_version", [1, 2])
@pytest.mark.parametrize(
    ("switches", "expected"),
    [
        ({}, None),
        ({"enable_switch_llm_tool": True}, None),
        (
            {"enable_sub_agents": True},
            [
                "terminal",
                "file_editor",
                "task_tracker",
                "browser_tool_set",
                "task_tool_set",
                "switch_llm",
            ],
        ),
        (
            {"enable_switch_llm_tool": False},
            ["terminal", "file_editor", "task_tracker", "browser_tool_set"],
        ),
    ],
)
def test_legacy_empty_tools_migrate_as_the_standard_set(
    schema_version, switches, expected
) -> None:
    profile = validate_agent_profile(
        {
            "schema_version": schema_version,
            "name": "default",
            "llm_profile_ref": "default",
            "tools": [],
            **switches,
        }
    )
    assert isinstance(profile, OpenHandsAgentProfile)
    assert (
        None if profile.tools is None else [tool.name for tool in profile.tools]
    ) == expected


def test_v2_sub_agents_switch_pins_the_standard_set_plus_delegation() -> None:
    profile = validate_agent_profile(
        {
            "schema_version": 2,
            "name": "default",
            "llm_profile_ref": "default",
            "revision": 0,
            "enable_sub_agents": True,
        }
    )
    assert isinstance(profile, OpenHandsAgentProfile)
    assert profile.schema_version == AGENT_PROFILE_SCHEMA_VERSION
    assert [tool.name for tool in profile.tools or []] == [
        "terminal",
        "file_editor",
        "task_tracker",
        "browser_tool_set",
        "task_tool_set",
        "switch_llm",
    ]


def test_v2_sub_agents_switch_does_not_reach_an_explicit_list() -> None:
    """该交换机仅馈送默认设置。"""
    profile = validate_agent_profile(
        {
            "schema_version": 2,
            "name": "default",
            "llm_profile_ref": "default",
            "revision": 0,
            "tools": [{"name": "glob", "params": {}}],
            "enable_sub_agents": True,
        }
    )
    assert isinstance(profile, OpenHandsAgentProfile)
    assert [tool.name for tool in profile.tools or []] == ["glob", "switch_llm"]


def test_v2_default_switch_llm_needs_no_pinned_list() -> None:
    """默认集带有 switch_llm，因此无需固定任何内容。"""
    profile = validate_agent_profile(
        {
            "schema_version": 2,
            "name": "default",
            "llm_profile_ref": "default",
            "revision": 0,
            "enable_switch_llm_tool": True,
        }
    )
    assert isinstance(profile, OpenHandsAgentProfile)
    assert profile.tools is None


def test_v2_fold_recognises_the_switch_llm_class_alias() -> None:
    """按类名命名内置函数的存储列表已经包含该工具。"""
    profile = validate_agent_profile(
        {
            "schema_version": 2,
            "name": "default",
            "llm_profile_ref": "default",
            "revision": 0,
            "tools": [{"name": "SwitchLLMTool", "params": {}}],
        }
    )
    assert isinstance(profile, OpenHandsAgentProfile)
    assert [tool.name for tool in profile.tools or []] == ["switch_llm"]


def test_v2_switch_llm_turned_off_pins_a_list_without_it() -> None:
    """关闭不是默认值，因此必须明确说明。"""
    profile = validate_agent_profile(
        {
            "schema_version": 2,
            "name": "default",
            "llm_profile_ref": "default",
            "revision": 0,
            "enable_switch_llm_tool": False,
        }
    )
    assert isinstance(profile, OpenHandsAgentProfile)
    assert [tool.name for tool in profile.tools or []] == [
        "terminal",
        "file_editor",
        "task_tracker",
        "browser_tool_set",
    ]


def test_v2_sub_agents_switch_leaves_acp_profiles_alone() -> None:
    profile = validate_agent_profile(
        {
            "schema_version": 2,
            "agent_kind": "acp",
            "name": "acp",
            "enable_sub_agents": True,
        }
    )
    assert profile.schema_version == AGENT_PROFILE_SCHEMA_VERSION
    assert not hasattr(profile, "tools")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (False, ["glob"]),
        ("false", ["glob"]),
        (0, ["glob"]),
        ("1", ["glob", "switch_llm"]),
    ],
)
def test_v2_switches_coerce_like_booleans(value: object, expected: list[str]) -> None:
    profile = validate_agent_profile(
        {
            "schema_version": 2,
            "name": "oh",
            "llm_profile_ref": "d",
            "tools": [{"name": "glob"}],
            "enable_switch_llm_tool": value,
        }
    )
    assert isinstance(profile, OpenHandsAgentProfile)
    assert [tool.name for tool in profile.tools or []] == expected


def test_v2_rejects_a_non_boolean_switch() -> None:
    with pytest.raises(ValidationError):
        validate_agent_profile(
            {
                "schema_version": 2,
                "name": "oh",
                "llm_profile_ref": "d",
                "enable_sub_agents": "sometimes",
            }
        )


_PINNED_WITH_SUB_AGENTS = [
    "terminal",
    "file_editor",
    "task_tracker",
    "browser_tool_set",
    "task_tool_set",
    "switch_llm",
]


@pytest.mark.parametrize("schema_version", [3])
@pytest.mark.parametrize(
    ("switch", "value", "tools", "expected"),
    [
        ("enable_sub_agents", True, None, _PINNED_WITH_SUB_AGENTS),
        (
            "enable_sub_agents",
            True,
            [{"name": "terminal"}],
            ["terminal", "task_tool_set"],
        ),
        (
            "enable_sub_agents",
            False,
            [{"name": "terminal"}, {"name": "task_tool_set"}],
            ["terminal"],
        ),
        (
            "enable_switch_llm_tool",
            False,
            [{"name": "terminal"}, {"name": "switch_llm"}],
            ["terminal"],
        ),
        (
            "enable_switch_llm_tool",
            True,
            [{"name": "terminal"}],
            ["terminal", "switch_llm"],
        ),
    ],
)
def test_v3_persisted_payload_discards_retired_switches(
    schema_version, switch, value, tools, expected
) -> None:
    payload = {"name": "oh", "llm_profile_ref": "d", "tools": tools, switch: value}
    if schema_version is not None:
        payload["schema_version"] = schema_version
    profile = validate_agent_profile(payload)

    assert isinstance(profile, OpenHandsAgentProfile)
    assert [tool.name for tool in profile.tools or []] == [
        tool["name"] for tool in tools or []
    ]
    assert switch not in profile.model_dump(mode="json")


def test_current_payload_without_retired_switches_keeps_tools_unset() -> None:
    profile = validate_agent_profile({"name": "oh", "llm_profile_ref": "d"})

    assert isinstance(profile, OpenHandsAgentProfile)
    assert profile.tools is None


@pytest.mark.parametrize("name", ["switch_llm", "SwitchLLMTool", "think", "finish"])
def test_params_on_a_parameterless_builtin_are_rejected(name) -> None:
    with pytest.raises(ValidationError, match="does not accept parameters"):
        validate_agent_profile(
            _current_payload(tools=[{"name": name, "params": {"a": 1}}])
        )


def test_v2_params_on_a_parameterless_builtin_are_rejected() -> None:
    with pytest.raises(ValidationError, match="does not accept parameters"):
        validate_agent_profile(
            {
                "schema_version": 2,
                "name": "oh",
                "llm_profile_ref": "d",
                "tools": [{"name": "switch_llm", "params": {"a": 1}}],
            }
        )


@pytest.mark.parametrize(
    "tools", [None, [], [{"name": "terminal"}, {"name": "task_tool_set"}]]
)
def test_written_profile_round_trips_without_retired_switches(tools) -> None:
    profile = validate_agent_profile(_current_payload(tools=tools))
    written = profile.model_dump(mode="json")

    assert written["schema_version"] == AGENT_PROFILE_SCHEMA_VERSION
    assert "enable_sub_agents" not in written
    assert "enable_switch_llm_tool" not in written
    assert validate_agent_profile(written) == profile


def test_saving_a_copy_under_a_new_name_keeps_the_selected_tools() -> None:
    stored = validate_agent_profile(_current_payload())
    copy = {
        **stored.model_dump(mode="json"),
        "name": "copy",
        "tools": [{"name": "terminal"}, {"name": "glob"}],
    }

    profile = validate_agent_profile(copy)

    assert isinstance(profile, OpenHandsAgentProfile)
    assert [tool.name for tool in profile.tools or []] == ["terminal", "glob"]


def _current_payload(**fields: object) -> dict[str, object]:
    return {
        "schema_version": AGENT_PROFILE_SCHEMA_VERSION,
        "name": "oh",
        "llm_profile_ref": "d",
        **fields,
    }


def test_tools_canonicalize_builtin_spellings_once() -> None:
    profile = validate_agent_profile(
        _current_payload(
            tools=[
                {"name": "FinishTool"},
                {"name": "terminal"},
                {"name": "finish", "params": {"response_schema": {"type": "object"}}},
                {"name": "SwitchLLMTool"},
            ]
        )
    )

    assert isinstance(profile, OpenHandsAgentProfile)
    assert [(tool.name, tool.params) for tool in profile.tools or []] == [
        ("finish", {"response_schema": {"type": "object"}}),
        ("terminal", {}),
        ("switch_llm", {}),
    ]


def test_retired_switch_does_not_mask_malformed_tools() -> None:
    with pytest.raises(ValidationError):
        validate_agent_profile(
            _current_payload(
                schema_version=2, tools="terminal", enable_switch_llm_tool=False
            )
        )


def test_rejects_newer_schema_version() -> None:
    with pytest.raises(ValueError, match="newer than supported"):
        validate_agent_profile(
            {
                "name": "oh",
                "llm_profile_ref": "d",
                "schema_version": AGENT_PROFILE_SCHEMA_VERSION + 1,
            }
        )


def test_rejects_non_integer_schema_version() -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        validate_agent_profile(
            {"name": "oh", "llm_profile_ref": "d", "schema_version": "1"}
        )


def test_rejects_negative_schema_version() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        validate_agent_profile(
            {"name": "oh", "llm_profile_ref": "d", "schema_version": -1}
        )


# ---------------------------------------------------------------------------
# 身份：id（稳定UUID）与名称（可重命名）
# ---------------------------------------------------------------------------


def test_id_is_uuid_and_autogenerated() -> None:
    profile = OpenHandsAgentProfile(name="oh", llm_profile_ref="d")
    assert isinstance(profile.id, UUID)
    other = OpenHandsAgentProfile(name="oh", llm_profile_ref="d")
    assert profile.id != other.id


def test_explicit_id_is_preserved_across_round_trip() -> None:
    fixed = uuid4()
    profile = validate_agent_profile(
        {"name": "oh", "llm_profile_ref": "d", "id": str(fixed)}
    )
    assert profile.id == fixed
    assert validate_agent_profile(profile.model_dump(mode="json")).id == fixed


def test_name_is_required() -> None:
    with pytest.raises(ValidationError):
        validate_agent_profile({"llm_profile_ref": "d"})


# ---------------------------------------------------------------------------
# 机密-免费，位于 REST
# ---------------------------------------------------------------------------


def test_openhands_profile_persists_no_secret_fields() -> None:
    dumped = OpenHandsAgentProfile(name="oh", llm_profile_ref="default").model_dump(
        mode="json"
    )
    # 配置文件带有 * 引用 *，而不是凭据本身。
    assert "llm" not in dumped
    assert "api_key" not in dumped
    assert "llm_profile_ref" in dumped


def test_acp_profile_persists_no_secret_fields() -> None:
    dumped = ACPAgentProfile(name="acp", acp_server="claude-code").model_dump(
        mode="json"
    )
    # 型材上没有嵌入凭据且没有机密包。
    for key in ("llm", "api_key", "secrets", "agent_context"):
        assert key not in dumped


def test_verification_field_cannot_carry_a_secret() -> None:
    """验证块是机密-free：``critic_api_key``不是一个字段，
    因此提供它的载荷被剥离并且永远不会暴露在 REST 处。"""
    profile = validate_agent_profile(
        {
            "name": "oh",
            "llm_profile_ref": "default",
            "verification": {
                "critic_enabled": True,
                "critic_model_name": "gpt-5.5",
                "critic_api_key": "sk-real-secret-value",
            },
        }
    )
    assert isinstance(profile, OpenHandsAgentProfile)
    assert not hasattr(profile.verification, "critic_api_key")
    assert profile.verification.critic_enabled is True
    assert profile.verification.critic_model_name == "gpt-5.5"

    # 即使强制机密曝光也不得显示该值（不存储该值）。
    exposed = profile.model_dump(mode="json", context={"expose_secrets": True})
    assert "critic_api_key" not in exposed["verification"]
    assert "sk-real-secret-value" not in json.dumps(exposed)


def test_openhands_profile_has_no_embedded_skills_field() -> None:
    """配置文件不再带有嵌入的 ``skills`` (#4017)：该字段消失了，
    ``extra="forbid"`` 拒绝流浪者，而不是默默地接受或丢弃它。 这就是使配置文件在 REST
     处真正摆脱机密的原因——唯一可以携带机密 (
    ``skills[].mcp_tools``) 的字段消失了。
    """
    with pytest.raises(ValidationError):
        validate_agent_profile(
            {
                "agent_kind": "openhands",
                "name": "oh",
                "llm_profile_ref": "default",
                "schema_version": AGENT_PROFILE_SCHEMA_VERSION,
                "skills": [],
            }
        )


# ---------------------------------------------------------------------------
# 当前版本中仍保留无效字段载荷。 ``skills`` 这是 v1 版本的例外载荷因为 v1 到 v2 迁移明确
# 退役了它。
# ---------------------------------------------------------------------------


def test_current_profile_with_skills_field_is_rejected() -> None:
    """v2 载荷不得保留已停用的嵌入 ``skills`` 字段。"""
    with pytest.raises(ValidationError):
        validate_agent_profile(
            {
                "schema_version": AGENT_PROFILE_SCHEMA_VERSION,
                "agent_kind": "openhands",
                "name": "oh",
                "llm_profile_ref": "default",
                "skills": [{"name": "old-skill", "content": "do stuff"}],
            }
        )


def test_removed_skill_refs_field_is_rejected() -> None:
    """允许列表 ``skill_refs`` 已替换为 ``disabled_skills``
    拒绝列表并且从未发货，因此携带它的载荷被拒绝。"""
    with pytest.raises(ValidationError):
        validate_agent_profile(
            {
                "schema_version": 1,
                "agent_kind": "openhands",
                "name": "oh",
                "llm_profile_ref": "default",
                "skill_refs": ["pdf-tools"],
            }
        )


def test_payload_without_disabled_skills_adopts_empty_default() -> None:
    """一个载荷会忽略 ``disabled_skills``，然后会使用模型默认值
    ``[]``（所有已发现的技能）。"""
    profile = validate_agent_profile(
        {
            "schema_version": 1,
            "agent_kind": "openhands",
            "name": "oh",
            "llm_profile_ref": "default",
        }
    )
    assert isinstance(profile, OpenHandsAgentProfile)
    assert profile.disabled_skills == []
    assert profile.disabled_skills == []


@pytest.mark.parametrize("switch", ["enable_sub_agents", "enable_switch_llm_tool"])
@pytest.mark.parametrize("schema_version", [None, AGENT_PROFILE_SCHEMA_VERSION])
def test_current_profile_rejects_removed_switches(switch, schema_version) -> None:
    with pytest.raises(ValidationError, match="Retired tool switches were removed"):
        validate_agent_profile(
            {
                "schema_version": schema_version,
                "name": "oh",
                "llm_profile_ref": "d",
                switch: True,
            }
        )
