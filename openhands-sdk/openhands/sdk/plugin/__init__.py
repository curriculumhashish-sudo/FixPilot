"""OpenHands SDK 的插件模块。

该模块提供对加载和管理将技能、挂钩、MCP 配置、智能体和命令捆绑在一起的插件的支持。

它还提供对插件市场的支持 - 列出可用插件及其元数据和源位置的目录。

此外，它还提供了用于管理用户主目录（~/.openhands/plugins/installed/).

Note: 市场类位于 ``openhands.sdk.marketplace``。
"""

from openhands.sdk.plugin.discovery import (
    load_available_plugins,
    load_project_plugins,
    load_user_plugins,
)
from openhands.sdk.plugin.fetch import (
    PluginFetchError,
    fetch_plugin_with_resolution,
)
from openhands.sdk.plugin.format import (
    AgentPluginsFormat,
    ClaudeCodePluginFormat,
    PluginFormat,
    detect_format,
)
from openhands.sdk.plugin.format.agent_plugins_mcp import get_plugin_data_dir
from openhands.sdk.plugin.installed import (
    InstalledPluginInfo,
    disable_plugin,
    enable_plugin,
    get_installed_plugin,
    get_installed_plugins_dir,
    install_plugin,
    list_installed_plugins,
    load_installed_plugins,
    uninstall_plugin,
    update_plugin,
)
from openhands.sdk.plugin.loader import load_plugins
from openhands.sdk.plugin.plugin import Plugin
from openhands.sdk.plugin.source import (
    GitHubURLComponents,
    is_local_path,
    parse_github_url,
    resolve_source_path,
    validate_source_path,
)
from openhands.sdk.plugin.strict_fetch import (
    CheckedPlugin,
    PluginSourceError,
    preflight_plugin,
)
from openhands.sdk.plugin.types import (
    CommandDefinition,
    PluginAuthor,
    PluginManifest,
    PluginSource,
    ResolvedPluginSource,
)


__all__ = [
    # 插件类
    "Plugin",
    "PluginFetchError",
    "PluginSourceError",
    "CheckedPlugin",
    "PluginManifest",
    "PluginAuthor",
    "PluginSource",
    "ResolvedPluginSource",
    "CommandDefinition",
    # 插件格式策略
    "PluginFormat",
    "AgentPluginsFormat",
    "ClaudeCodePluginFormat",
    "detect_format",
    # 插件加载
    "load_plugins",
    "fetch_plugin_with_resolution",
    "preflight_plugin",
    # 本地插件发现（环境自动加载）
    "load_user_plugins",
    "load_project_plugins",
    "load_available_plugins",
    # 源路径实用程序
    "GitHubURLComponents",
    "parse_github_url",
    "is_local_path",
    "validate_source_path",
    "resolve_source_path",
    # 已安装插件管理
    "InstalledPluginInfo",
    "install_plugin",
    "uninstall_plugin",
    "list_installed_plugins",
    "load_installed_plugins",
    "get_installed_plugins_dir",
    "get_installed_plugin",
    "get_plugin_data_dir",
    "enable_plugin",
    "disable_plugin",
    "update_plugin",
]
