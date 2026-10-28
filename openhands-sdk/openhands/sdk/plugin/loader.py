"""用于多插件支持的插件加载实用程序。

该模块提供了加载多个插件并将它们合并到智能体中的规范函数。 它的使用者：
- LocalConversation（对于 SDK-直接用户）
- ConversationService（对于智能体-服务器用户）
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from openhands.sdk.hooks import HookConfig
from openhands.sdk.logger import get_logger
from openhands.sdk.plugin.plugin import Plugin
from openhands.sdk.plugin.types import PluginSource
from openhands.sdk.skills.utils import SecretLookup, expand_mcp_servers
from openhands.sdk.utils.redact import redact_url_credentials


if TYPE_CHECKING:
    from openhands.sdk.agent.base import AgentBase
    from openhands.sdk.context import AgentContext


logger = get_logger(__name__)


def load_plugins(
    plugin_specs: list[PluginSource],
    agent: AgentBase,
    max_skills: int = 100,
    get_secret: SecretLookup | None = None,
) -> tuple[AgentBase, HookConfig | None]:
    """加载多个插件并将它们合并到智能体中。

    这是插件加载的规范函数，使用者：
    - LocalConversation（对于 SDK-直接用户）
    - ConversationService（对于智能体-服务器用户）

    插件按顺序加载，并与这些语义合并：
    - Skills: 按名称覆盖（最后一个插件获胜）
    - MCP 配置：按键覆盖（最后一个插件获胜）
    - Hooks: 连接（所有钩子运行）

    Args:
        plugin_specs: 要加载的插件源列表。
        agent: 智能体将插件合并到。
        max_skills: 允许的最大总技能（纵深防御限制）。
        get_secret: 可选回调用于查找每个对话机密。
            用于扩展 MCP 配置文件中的 ${VAR} 占位符。 有关为什么这是回调的详细信息，
            请参阅 expand_mcp_variables()。

    Returns:
        (updated_agent, merged_hook_config) 的元组。 智能体更新了 agent_context（具有
        合并技能）和
        mcp_config。 hook_config 包含所有连接的插件的所有钩子。

    Raises:
        PluginFetchError: 如果任何插件无法获取。
        FileNotFoundError: 如果任何插件无法加载（e.g.，未找到路径）。
        ValueError: 如果超出 max_skills 限制。

    Example:
        >>> from openhands.sdk.plugin import PluginSource
        >>> plugins = [
        ...     PluginSource(source="github:owner/security-plugin", ref="v1.0.0"),
        ...     PluginSource(source="/local/custom-plugin"),
        ... ]
        >>> updated_agent, hooks = load_plugins(plugins, agent)
    """
    if not plugin_specs:
        return agent, None

    # 从智能体现有的上下文和 MCP 配置开始
    merged_context: AgentContext | None = agent.agent_context
    merged_mcp_config = agent.mcp_config
    all_hooks: list[HookConfig] = []

    for spec in plugin_specs:
        logger.info(f"Loading plugin from {redact_url_credentials(spec.source)}")

        # 获取（如果需要则下载，返回缓存路径）
        path = Plugin.fetch(
            source=spec.source,
            ref=spec.ref,
            repo_path=spec.repo_path,
        )
        plugin = Plugin.load(path)

        logger.info(
            f"Loaded plugin '{plugin.name}': "
            f"{len(plugin.skills)} skills, "
            f"hooks={'yes' if plugin.hooks else 'no'}, "
            f"mcp_config={'yes' if plugin.mcp_config else 'no'}"
        )

        # 分别合并技能和MCP配置
        merged_context = plugin.add_skills_to(merged_context, max_skills=max_skills)
        merged_mcp_config = plugin.add_mcp_config_to(merged_mcp_config)

        # 收集钩子以供以后组合
        if plugin.hooks and not plugin.hooks.is_empty():
            all_hooks.append(plugin.hooks)

    # 使用每个会话扩展 MCP 服务器变量机密这处理通过 API 注入的引用机密的 ${VAR} 占位符
    #
    if merged_mcp_config and get_secret:
        merged_mcp_config = expand_mcp_servers(merged_mcp_config, get_secret)
        logger.debug("Expanded MCP config variables")

    # 组合所有钩子配置（串联语义）
    combined_hooks = HookConfig.merge(all_hooks)

    # 使用合并的内容创建更新的智能体
    updated_agent = agent.model_copy(
        update={
            "agent_context": merged_context,
            "mcp_config": merged_mcp_config,
        }
    )

    return updated_agent, combined_hooks
