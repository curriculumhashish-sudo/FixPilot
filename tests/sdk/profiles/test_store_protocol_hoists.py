"""云 AgentProfiles 表面的与存储无关的先决条件 (#3730)。

证明 FK 帮助程序 (``profile_refs``)、id/revision 生命周期 (
``save_profile_preserving_identity``)
和 Seed/422 提升机可以对抗
**非文件**存储 - i.e。 满足``AgentProfileStoreProtocol``的后端
没有 ``base_dir`` / ``_atomic_write``，就像云数据库支持的存储一样。
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from openhands.sdk.profiles import (
    SEED_PROFILE_NAME,
    ACPAgentProfile,
    AgentProfileStoreProtocol,
    OpenHandsAgentProfile,
    ProfileLimitExceeded,
    ProfileReferenced,
    ProfileVerificationSettings,
    build_profile_verification,
    build_seed_profile,
    cascade_rename,
    delete_llm_profile,
    find_referrers,
    rename_llm_profile,
    safe_validation_error_detail,
    save_profile_preserving_identity,
    validate_agent_profile,
)
from openhands.sdk.settings.model import VerificationSettings, validate_agent_settings


class InMemoryAgentProfileStore:
    """最小非文件 ``AgentProfileStoreProtocol`` impl（云信封）。

    它存储名称键的字典，提供元数据和写操作的 SDK FK / 身份辅助工具需要的接口，以及提
    供一个可重入的无操作 ``lock``（云存储的路由器会持有行事务）。
    """

    def __init__(self) -> None:
        self._profiles: dict[str, OpenHandsAgentProfile | ACPAgentProfile] = {}

    @contextmanager
    def lock(self, timeout: float = 30.0):
        yield  # 可重入空操作

    def list(self) -> list[str]:
        return [f"{name}.json" for name in self._profiles]

    def list_summaries(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name, p in self._profiles.items():
            d = p.model_dump(mode="json")
            kind = d.get("agent_kind", "openhands")
            out.append(
                {
                    "id": d.get("id"),
                    "name": name,
                    "agent_kind": kind,
                    "revision": d.get("revision"),
                    "llm_profile_ref": (
                        d.get("llm_profile_ref") if kind == "openhands" else None
                    ),
                    "mcp_server_refs": d.get("mcp_server_refs"),
                }
            )
        return out

    def save(self, profile, *, max_profiles=None) -> None:
        if (
            max_profiles is not None
            and profile.name not in self._profiles
            and len(self._profiles) >= max_profiles
        ):
            raise ProfileLimitExceeded(f"Profile limit reached ({max_profiles}).")
        self._profiles[profile.name] = profile

    def load(self, name):
        if name not in self._profiles:
            raise FileNotFoundError(name)
        return self._profiles[name]

    def delete(self, name) -> None:
        self._profiles.pop(name, None)

    def rename(self, old_name, new_name) -> None:
        if old_name not in self._profiles:
            raise FileNotFoundError(old_name)
        if new_name in self._profiles:
            raise FileExistsError(new_name)
        p = self._profiles.pop(old_name)
        self._profiles[new_name] = p.model_copy(update={"name": new_name})

    def set_llm_profile_ref(self, name, new_ref) -> None:
        p = self._profiles.get(name)
        if isinstance(p, OpenHandsAgentProfile):
            self._profiles[name] = p.model_copy(update={"llm_profile_ref": new_ref})

    def name_for_id(self, profile_id) -> str | None:
        target = str(profile_id)
        for name, p in self._profiles.items():
            if str(p.id) == target:
                return name
        return None


class FakeLLMStore:
    """存根 LLM 存储仅公开 ``delete`` / ``rename`` 的 FK 助手。"""

    def __init__(self, names: list[str]) -> None:
        self.names = list(names)

    def delete(self, name: str) -> None:
        if name in self.names:
            self.names.remove(name)

    def rename(self, old_name: str, new_name: str) -> None:
        if old_name not in self.names:
            raise FileNotFoundError(old_name)
        self.names[self.names.index(old_name)] = new_name


def _seed(store: InMemoryAgentProfileStore) -> None:
    save_profile_preserving_identity(
        store, OpenHandsAgentProfile(name="reviewer", llm_profile_ref="gpt")
    )
    save_profile_preserving_identity(
        store, OpenHandsAgentProfile(name="coder", llm_profile_ref="gpt")
    )
    save_profile_preserving_identity(
        store, OpenHandsAgentProfile(name="cheap", llm_profile_ref="haiku")
    )
    save_profile_preserving_identity(
        store, ACPAgentProfile(name="claude", acp_server="claude-code")
    )


def test_inmemory_store_satisfies_protocol():
    # runtime_checkable：非文件后端在结构上是可互换的。
    assert isinstance(InMemoryAgentProfileStore(), AgentProfileStoreProtocol)


def test_find_referrers_over_protocol_store():
    store = InMemoryAgentProfileStore()
    _seed(store)
    assert sorted(find_referrers(store, "gpt")) == ["coder", "reviewer"]
    assert find_referrers(store, "haiku") == ["cheap"]
    # ACP 配置文件不包含 llm_profile_ref 并且从不匹配。
    assert find_referrers(store, "claude-code") == []
    assert find_referrers(store, "missing") == []


def test_cascade_rename_over_protocol_store():
    store = InMemoryAgentProfileStore()
    _seed(store)
    rewritten = cascade_rename(store, "gpt", "gpt-5")
    assert sorted(rewritten) == ["coder", "reviewer"]
    assert find_referrers(store, "gpt") == []
    assert sorted(find_referrers(store, "gpt-5")) == ["coder", "reviewer"]
    # 不相关的参考保持不变。
    assert find_referrers(store, "haiku") == ["cheap"]


def test_delete_llm_profile_blocks_on_referrers():
    store = InMemoryAgentProfileStore()
    _seed(store)
    llm_store = FakeLLMStore(["gpt", "haiku"])
    # “gpt”被审阅者 + 编码器引用 -> 被阻止，llm 配置文件未受影响。
    with pytest.raises(ProfileReferenced) as exc:
        delete_llm_profile(store, llm_store, "gpt")
    assert sorted(exc.value.referrers) == ["coder", "reviewer"]
    assert "gpt" in llm_store.names

    # 分离引荐来源网址； 然后删除就完成了。
    store.delete("reviewer")
    store.delete("coder")
    delete_llm_profile(store, llm_store, "gpt")
    assert "gpt" not in llm_store.names


def test_rename_llm_profile_cascades_over_protocol_store():
    store = InMemoryAgentProfileStore()
    _seed(store)
    llm_store = FakeLLMStore(["gpt", "haiku"])
    rewritten = rename_llm_profile(store, llm_store, "gpt", "gpt-5")
    assert sorted(rewritten) == ["coder", "reviewer"]
    assert "gpt-5" in llm_store.names and "gpt" not in llm_store.names
    assert sorted(find_referrers(store, "gpt-5")) == ["coder", "reviewer"]


def test_save_preserving_identity_mints_then_keeps_id_and_bumps_revision():
    store = InMemoryAgentProfileStore()
    created = save_profile_preserving_identity(
        store, OpenHandsAgentProfile(name="p", llm_profile_ref="gpt")
    )
    assert created.revision == 0
    first_id = created.id

    # 覆盖保留 id 和凹凸版本； 客户端提供的 ID 会被忽略。
    again = save_profile_preserving_identity(
        store, OpenHandsAgentProfile(name="p", llm_profile_ref="haiku")
    )
    assert again.id == first_id
    assert again.revision == 1
    reloaded = store.load("p")
    assert isinstance(reloaded, OpenHandsAgentProfile)
    assert reloaded.llm_profile_ref == "haiku"

    # 不同的名字会创造一个新的身份。
    other = save_profile_preserving_identity(
        store, OpenHandsAgentProfile(name="q", llm_profile_ref="gpt")
    )
    assert other.id != first_id
    assert other.revision == 0


def test_save_preserving_identity_enforces_limit():
    store = InMemoryAgentProfileStore()
    save_profile_preserving_identity(
        store, OpenHandsAgentProfile(name="a", llm_profile_ref="gpt"), max_profiles=1
    )
    with pytest.raises(ProfileLimitExceeded):
        save_profile_preserving_identity(
            store,
            OpenHandsAgentProfile(name="b", llm_profile_ref="gpt"),
            max_profiles=1,
        )
    # 上限允许覆盖现有的。
    save_profile_preserving_identity(
        store, OpenHandsAgentProfile(name="a", llm_profile_ref="haiku"), max_profiles=1
    )


def test_build_seed_profile_openhands_branch():
    settings = validate_agent_settings({"agent_kind": "openhands"})
    profile = build_seed_profile(settings, active_llm_profile="my-llm")
    assert isinstance(profile, OpenHandsAgentProfile)
    assert profile.name == SEED_PROFILE_NAME
    assert profile.llm_profile_ref == "my-llm"
    assert profile.mcp_server_refs is None
    # 默认设置携带tools=None -> 种子继承服务器默认值。
    assert profile.tools is None
    # 种子不会禁用任何内容 -> 默认配置文件会启动所有已发现的技能（拒绝列表模型； 没有任
    # 何东西被冻结，没有任何东西可以悬挂）。
    #
    assert profile.disabled_skills == []
    # 机密-无验证投影（配置文件类型上没有 critic_api_key）。
    assert "critic_api_key" not in type(profile.verification).model_fields

    # 没有活动的 LLM 配置文件 -> 软回退方案到 SEED_PROFILE_NAME。
    fallback = build_seed_profile(settings, active_llm_profile=None)
    assert isinstance(fallback, OpenHandsAgentProfile)
    assert fallback.llm_profile_ref == SEED_PROFILE_NAME
    assert fallback.persona is None


def test_build_seed_profile_copies_persona():
    settings = validate_agent_settings(
        {"agent_kind": "openhands", "persona": "You triage issues."}
    )
    profile = build_seed_profile(settings, active_llm_profile="my-llm")
    assert isinstance(profile, OpenHandsAgentProfile)
    assert profile.persona == "You triage issues."


def test_build_seed_profile_disables_nothing_even_with_inline_global_skills():
    """种子永远不会冻结全球技能的名字——它设置了一个空的
    拒绝列表，因此迁移的默认配置文件将随所有发现的技能一起启动。 冻结的名字是 #4017
    启动中断：启动目录中缺少的内联全局技能将会悬而未决。 参见test_reso
    lver.py中的seed->resolve 回归。
    """
    settings = validate_agent_settings(
        {
            "agent_kind": "openhands",
            "agent_context": {
                "skills": [
                    {"name": "alpha", "content": "x"},
                    {"name": "beta", "content": "y"},
                ]
            },
        }
    )
    profile = build_seed_profile(settings, active_llm_profile="my-llm")
    assert isinstance(profile, OpenHandsAgentProfile)
    assert profile.disabled_skills == []


def test_build_seed_profile_copies_explicit_tools():
    """具有显式工具集的全局配置（e.g. 浏览器）种子 a
    行为保留配置文件 - 工具被逐字复制，而不是重置为服务器默认值（#3978）。
    """
    settings = validate_agent_settings(
        {
            "agent_kind": "openhands",
            "tools": [{"name": "terminal"}, {"name": "browser_use"}],
        }
    )
    profile = build_seed_profile(settings, active_llm_profile="my-llm")
    assert isinstance(profile, OpenHandsAgentProfile)
    assert profile.tools is not None
    assert [t.name for t in profile.tools] == ["terminal", "browser_use"]


def test_build_seed_profile_acp_branch():
    settings = validate_agent_settings(
        {"agent_kind": "acp", "acp_server": "claude-code"}
    )
    profile = build_seed_profile(settings, active_llm_profile="ignored")
    assert isinstance(profile, ACPAgentProfile)
    assert profile.name == SEED_PROFILE_NAME
    assert profile.acp_server == "claude-code"
    assert profile.mcp_server_refs is None
    # ACP 个人资料没有技能选择字段——他们拥有自己的工具。
    assert not hasattr(profile, "skill_refs")
    assert not hasattr(profile, "disabled_skills")
    assert not hasattr(profile, "llm_profile_ref")


def test_build_profile_verification_drops_critic_api_key():
    v = VerificationSettings(
        critic_enabled=True,
        critic_threshold=0.9,
        critic_model_name="some-model",
    )
    projected = build_profile_verification(v)
    assert isinstance(projected, ProfileVerificationSettings)
    assert projected.critic_enabled is True
    assert projected.critic_threshold == 0.9
    assert projected.critic_model_name == "some-model"
    assert "critic_api_key" not in ProfileVerificationSettings.model_fields


def test_safe_validation_error_detail_surfaces_msg_without_input():
    secret = "sk-super-secret-value"
    with pytest.raises(Exception) as exc_info:
        # extra=forbid -> the unexpected key (carrying a value) triggers a
        # ValidationError，其 ``input`` 回显被拒绝的值。
        validate_agent_profile({"name": "p", "llm_profile_ref": "gpt", "leak": secret})
    from pydantic import ValidationError

    assert isinstance(exc_info.value, ValidationError)
    detail = safe_validation_error_detail(exc_info.value)
    assert detail, "expected at least one error entry"
    # loc/type/msg 会显示出来，以便客户端可以了解*为什么*保存失败；
    # ``input``（与整个被拒绝的载荷相呼应）被删除。
    for entry in detail:
        assert set(entry.keys()) == {"loc", "type", "msg"}
    # 被拒绝的值位于 ``input`` 中，该值已被删除 - 因此在意外字段中传递的值永远不会出现在
    # 详细信息中。
    #
    assert secret not in repr(detail)
