"""从实时设置构建默认的：class:`~openhands.sdk.profiles.AgentProfile`。

逆函数：func`~openhands.sdk.profiles.resolve_agent_profile` 将当前
``AgentSettingsConfig``转换为一
次性的迁移（本地智能体服务器懒加载，云服务器 eager 回填）所使用的单个配置。
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

from openhands.sdk.profiles.agent_profile import (
    ACPAgentProfile,
    OpenHandsAgentProfile,
    build_profile_verification,
)


if TYPE_CHECKING:
    from openhands.sdk.settings import AgentSettingsConfig


# 懒加载默认/迁移配置的名称和软 LLM 反射回退方案（一个“默认” LLM 配置，解析器在材料化时
# 检查）。
#
SEED_PROFILE_NAME = "default"


def build_seed_profile(
    agent_settings: AgentSettingsConfig,
    active_llm_profile: str | None,
    *,
    name: str = SEED_PROFILE_NAME,
) -> OpenHandsAgentProfile | ACPAgentProfile:
    """从 ``agent_settings`` 构建一个行为保留 ``AgentProfile``。

    ``agent_kind`` 上的分支，因此 ACP 设置种子 ACP 配置文件。
    ``mcp_server_refs=None``公开用户的所有MCP服务器； OpenHands 配置文件参考
    ``active_llm_profile``，回落到
    ``SEED_PROFILE_NAME``（解析器在实现时检查的软引用）。
    """
    if agent_settings.agent_kind == "acp":
        return ACPAgentProfile(
            name=name,
            acp_server=agent_settings.acp_server,
            acp_model=agent_settings.acp_model,
            acp_session_mode=agent_settings.acp_session_mode,
            acp_prompt_timeout=agent_settings.acp_prompt_timeout,
            acp_startup_timeout=agent_settings.acp_startup_timeout,
            # 设置将命令存储为 token 列表； 配置文件包含一个（可重新解析的）字符串。 空
            # 列表 => 使用服务器默认值。
            #
            acp_command=(
                shlex.join(agent_settings.acp_command)
                if agent_settings.acp_command
                else None
            ),
            acp_args=list(agent_settings.acp_args) or None,
            mcp_server_refs=None,
            # ACP 个人资料不包含技能领域 - 子进程拥有其上下文。
        )
    context = agent_settings.agent_context
    return OpenHandsAgentProfile(
        name=name,
        llm_profile_ref=active_llm_profile or SEED_PROFILE_NAME,
        agent=agent_settings.agent,
        tools=agent_settings.tools,
        disabled_skills=list(context.disabled_skills),
        persona=agent_settings.persona,
        system_message_suffix=context.system_message_suffix,
        condenser=agent_settings.condenser,
        verification=build_profile_verification(agent_settings.verification),
        enable_classify_and_switch_llm_tool=(
            agent_settings.enable_classify_and_switch_llm_tool
        ),
        meta_profile_ref=agent_settings.active_meta_profile,
        tool_concurrency_limit=agent_settings.tool_concurrency_limit,
        mcp_server_refs=None,
    )
