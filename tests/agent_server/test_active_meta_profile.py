"""测试 active_meta_profile 持久化和传播（选项 A）。"""

from openhands.agent_server.persistence.models import PersistedSettings
from openhands.sdk.settings.model import ACPAgentSettings, OpenHandsAgentSettings


def test_update_sets_top_level_and_propagates_into_agent_settings() -> None:
    settings = PersistedSettings()

    settings.update({"active_meta_profile": "balanced"})

    assert settings.active_meta_profile == "balanced"
    # OpenHandsAgentSettings（默认）获取路由工具配置。
    agent = settings.agent_settings
    assert isinstance(agent, OpenHandsAgentSettings)
    assert agent.active_meta_profile == "balanced"
    assert agent.enable_classify_and_switch_llm_tool is True


def test_update_clearing_disables_tool() -> None:
    settings = PersistedSettings()
    settings.update({"active_meta_profile": "balanced"})

    settings.update({"active_meta_profile": None})

    assert settings.active_meta_profile is None
    agent = settings.agent_settings
    assert isinstance(agent, OpenHandsAgentSettings)
    assert agent.active_meta_profile is None
    assert agent.enable_classify_and_switch_llm_tool is False


def test_update_without_active_meta_profile_leaves_it_unchanged() -> None:
    settings = PersistedSettings()
    settings.update({"active_meta_profile": "balanced"})

    # 不相关的更新不得重置元配置文件。
    settings.update({"active_profile": "fast"})

    assert settings.active_meta_profile == "balanced"
    agent = settings.agent_settings
    assert isinstance(agent, OpenHandsAgentSettings)
    assert agent.active_meta_profile == "balanced"


def test_activate_on_acp_agent_does_not_set_facade() -> None:
    """ACP 智能体无法附加布线工具，因此立面必须保持清晰。

    否则，``GET /api/meta-profiles`` 将报告一个活动路由器，根据已持久化 ACP 设置构建
    的会话实际上无法使用该路由器。
    """
    settings = PersistedSettings(agent_settings=ACPAgentSettings())

    settings.update({"active_meta_profile": "balanced"})

    # 请求被丢弃：未设置外观并且变体未受影响。
    assert settings.active_meta_profile is None
    assert isinstance(settings.agent_settings, ACPAgentSettings)


def test_switching_to_acp_clears_active_meta_profile() -> None:
    """当元配置文件处于活动状态时将智能体类型切换为 ACP 将清除它。"""
    settings = PersistedSettings()
    settings.update({"active_meta_profile": "balanced"})
    assert settings.active_meta_profile == "balanced"

    # 通过智能体设置差异将智能体类型切换为 ACP（无元配置文件密钥）。
    settings.update({"agent_settings_diff": {"agent_kind": "acp"}})

    assert settings.active_meta_profile is None
    assert isinstance(settings.agent_settings, ACPAgentSettings)


def test_switching_back_to_openhands_can_reactivate() -> None:
    """经过 ACP 次往返后，OpenHands 智能体可以再次激活路由。"""
    settings = PersistedSettings(agent_settings=ACPAgentSettings())
    settings.update({"active_meta_profile": "balanced"})
    assert settings.active_meta_profile is None

    # 切换回 OpenHands 智能体并激活。
    settings.update({"agent_settings_diff": {"agent_kind": "openhands"}})
    settings.update({"active_meta_profile": "balanced"})

    assert settings.active_meta_profile == "balanced"
    agent = settings.agent_settings
    assert isinstance(agent, OpenHandsAgentSettings)
    assert agent.active_meta_profile == "balanced"
    assert agent.enable_classify_and_switch_llm_tool is True


def test_active_meta_profile_round_trips_through_serialization() -> None:
    settings = PersistedSettings()
    settings.update({"active_meta_profile": "balanced"})

    dumped = settings.model_dump(mode="json")
    assert dumped["active_meta_profile"] == "balanced"

    reloaded = PersistedSettings.from_persisted(dumped)
    assert reloaded.active_meta_profile == "balanced"
    agent = reloaded.agent_settings
    assert isinstance(agent, OpenHandsAgentSettings)
    assert agent.active_meta_profile == "balanced"
