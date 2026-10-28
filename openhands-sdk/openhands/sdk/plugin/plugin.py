"""用于加载和管理插件的插件类。

``Plugin`` 是格式中立的内存模型加上其与格式无关的行为（将技能 / MCP 配置合并到智能体
中）。 从磁盘读取插件目录被委托给：class:
`~openhands.sdk.plugin.format.PluginFormat` 策略（参见 ``format.py``）；
``Plugin.load()`` 是一
个精简调度程序，用于检测磁盘格式并返回标准化的 ``Plugin``。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from openhands.sdk.hooks import HookConfig
from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.config import MCPServer
from openhands.sdk.plugin.fetch import fetch_plugin
from openhands.sdk.plugin.format import detect_format
from openhands.sdk.plugin.types import (
    CommandDefinition,
    PluginManifest,
)
from openhands.sdk.skills.skill import Skill
from openhands.sdk.subagent.schema import AgentDefinition


if TYPE_CHECKING:
    from openhands.sdk.context import AgentContext

logger = get_logger(__name__)


class Plugin(BaseModel):
    """一个捆绑技能、挂钩、MCP 配置、智能体和命令的插件。

    插件遵循 Claude Code 插件结构以实现兼容性：

    ```
    plugin-name/
    ├── .claude-plugin/           # 或.plugin/
    │   └── plugin.json          # 插件元数据
    ├── commands/                # 斜线命令（可选）
    ├── agents/                  # 专业智能体（可选）
    ├── skills/                  # 智能体技能（可选）
    ├── hooks/                   # 事件处理程序（可选）
    │   └── hooks.json
    ├── .mcp.json                # 外部工具配置（可选）
    └── README.md                # 插件文档
    ```
    """

    manifest: PluginManifest = Field(description="Plugin manifest from plugin.json")
    path: str = Field(description="Path to the plugin directory")
    skills: list[Skill] = Field(
        default_factory=list, description="Skills loaded from skills/ directory"
    )
    hooks: HookConfig | None = Field(
        default=None, description="Hook configuration from hooks/hooks.json"
    )
    mcp_config: dict[str, MCPServer] = Field(
        default_factory=dict, description="MCP servers from .mcp.json"
    )
    agents: list[AgentDefinition] = Field(
        default_factory=list, description="Agent definitions from agents/ directory"
    )
    commands: list[CommandDefinition] = Field(
        default_factory=list, description="Command definitions from commands/ directory"
    )

    @property
    def name(self) -> str:
        """获取插件名称。"""
        return self.manifest.name

    @property
    def version(self) -> str:
        """获取插件版本。"""
        return self.manifest.version

    @property
    def description(self) -> str:
        """获取插件说明。"""
        return self.manifest.description

    @property
    def entry_slash_command(self) -> str | None:
        """获取入口的完整斜杠命令（如果已定义）。

        返回格式为 /<plugin-name>:<command-name> 的斜杠命令，如果清单中未定义
        entry_command，则返回 None。

        Example:
            >>> plugin = Plugin.load(path)
            >>> plugin.entry_slash_command
            '/city-weather:now'
        """
        if not self.manifest.entry_command:
            return None
        return f"/{self.name}:{self.manifest.entry_command}"

    def get_all_skills(self) -> list[Skill]:
        """获得所有技能，包括从命令转换而来的技能。

        从技能/目录和命令/目录返回技能。 命令使用 /<plugin-name>:<command-name> 格式
        转换为关键字触发技能。

        Returns:
            技能组合列表（原始+命令衍生技能）。
        """
        all_skills = list(self.skills)

        # 使用关键字触发器将命令转换为技能
        for command in self.commands:
            skill = command.to_skill(self.name)
            all_skills.append(skill)

        return all_skills

    def add_skills_to(
        self,
        agent_context: AgentContext | None = None,
        max_skills: int | None = None,
    ) -> AgentContext:
        """将这个插件的技能添加到智能体上下文。

        插件技能会覆盖同名的现有技能。 包括显性技能和命令衍生技能。

        Args:
            agent_context: 现有智能体上下文（或 None 创建新的）
            max_skills: 可选的最大总技能（如果超过则提高 ValueError）

        Returns:
            新增 AgentContext 并添加了此插件的技能

        Raises:
            ValueError: 如果超出 max_skills 限制

        Example:
            >>> plugin = Plugin.load(Plugin.fetch("github:owner/plugin"))
            >>> new_context = plugin.add_skills_to(agent.agent_context, max_skills=100)
            >>> agent = agent.model_copy(update={"agent_context": new_context})
        """
        # 在运行时导入以避免循环导入
        from openhands.sdk.context import AgentContext

        existing_skills = agent_context.skills if agent_context else []

        # 获得所有技能，包括命令衍生技能
        all_skills = self.get_all_skills()

        skills_by_name = {s.name: s for s in existing_skills}
        for skill in all_skills:
            if skill.name in skills_by_name:
                logger.warning(f"Plugin skill '{skill.name}' overrides existing skill")
            skills_by_name[skill.name] = skill

        if max_skills is not None and len(skills_by_name) > max_skills:
            raise ValueError(
                f"Total skills ({len(skills_by_name)}) exceeds maximum ({max_skills})"
            )

        merged_skills = list(skills_by_name.values())

        if agent_context:
            return agent_context.model_copy(update={"skills": merged_skills})
        return AgentContext(skills=merged_skills)

    def add_mcp_config_to(
        self,
        mcp_config: dict[str, MCPServer] | None = None,
    ) -> dict[str, MCPServer]:
        """将此插件的 MCP 配置添加到 MCP 配置映射中。

        插件 MCP 服务器覆盖具有相同名称的现有服务器。

        合并语义：服务器按服务器名称合并，当两个配置中存在相同的服务器时，插件获胜。

        Args:
            mcp_config: 现有 MCP 个服务器（或 None 个服务器来创建新地图）

        Returns:
            添加了此插件服务器的新 MCP 服务器地图

        Example:
            >>> plugin = Plugin.load(Plugin.fetch("github:owner/plugin"))
            >>> new_mcp = plugin.add_mcp_config_to(agent.mcp_config)
            >>> agent = agent.model_copy(update={"mcp_config": new_mcp})
        """
        existing_servers = mcp_config or {}
        plugin_servers = self.mcp_config
        for server_name in plugin_servers:
            if server_name in existing_servers:
                logger.warning(
                    f"Plugin MCP server '{server_name}' overrides existing server"
                )
        return {**existing_servers, **plugin_servers}

    @classmethod
    def fetch(
        cls,
        source: str,
        cache_dir: Path | None = None,
        ref: str | None = None,
        update: bool = True,
        repo_path: str | None = None,
    ) -> Path:
        """从远程源获取插件并返回本地缓存路径。

        此方法从远程源（GitHub 仓库，URLs Git）获取插件，并本地缓存它们。 使用返回的
        路径 Plugin.load() 加载插件。

        Args:
            source: 插件源 - 可以是：
                - 任何 git URL（GitHub、GitLab、Bitbucket、Codeberg、自托管等）e.g.,
                "
                https://gitlab.com/org/repo",  "git@bitbucket.org:team/repo.git"
                - "GitHub:owner/repo" - GitHub 简写（方便语法）
                - “/local/path" - 本地路径（按原样返回）
            cache_dir: 用于缓存的目录。 默认为~/.openhands/cache/plugins/
            ref: 可选分支、标记或提交结账。
            update: 如果True和缓存存在，则更新它。 如果 False，则按原样使用缓存。
            repo_path: git 存储库中的子目录路径
                （e.g., 'plugins/my-plugin' 用于 monorepos）。 仅与 git 源相关，与本
                地路径无关。 如果指定，返回的
                路径将指向该子目录而不是存储库根目录。

        Returns:
            本地插件目录的路径（为 Plugin.load() 做好准备）。 如果指定 repo_path，则
            返回该子目录的路径。

        Raises:
            PluginFetchError: 如果获取失败或者repo_path不存在。

        Example:
            >>> path = Plugin.fetch("github:owner/my-plugin")
            >>> plugin = Plugin.load(path)

            >>> # 带有特定版本
            >>> path = Plugin.fetch("github:owner/my-plugin", ref="v1.0.0")
            >>> plugin = Plugin.load(path)

            >>> # 从子目录中获取插件单体仓库
            >>> path = Plugin.fetch("github:owner/monorepo", repo_path="plugins/sub")
            >>> plugin = Plugin.load(path)

            >>> # 一步到位，Fetch 和 load
            >>> plugin = Plugin.load(Plugin.fetch("github:owner/my-plugin"))
        """
        return fetch_plugin(
            source, cache_dir=cache_dir, ref=ref, update=update, repo_path=repo_path
        )

    @classmethod
    def load(cls, plugin_path: str | Path) -> Plugin:
        """从目录加载插件。

        Args:
            plugin_path: 插件目录的路径。

        Returns:
            已加载的插件实例。

        Raises:
            FileNotFoundError: 如果插件目录不存在。
            ValueError: 如果插件清单无效。
        """
        plugin_dir = Path(plugin_path).resolve()
        if not plugin_dir.is_dir():
            raise FileNotFoundError(f"Plugin directory not found: {plugin_dir}")

        return detect_format(plugin_dir).load(plugin_dir)

    @classmethod
    def load_all(cls, plugins_dir: str | Path) -> list[Plugin]:
        """从目录加载所有插件。

        Args:
            plugins_dir: 包含插件子目录的目录路径。

        Returns:
            已加载插件实例的列表。
        """
        plugins_path = Path(plugins_dir).resolve()
        if not plugins_path.is_dir():
            logger.warning(f"Plugins directory not found: {plugins_path}")
            return []

        plugins: list[Plugin] = []
        for item in sorted(plugins_path.iterdir()):
            if item.is_dir():
                try:
                    plugin = cls.load(item)
                    plugins.append(plugin)
                    logger.debug(f"Loaded plugin: {plugin.name} from {item}")
                except Exception as e:
                    logger.warning(f"Failed to load plugin from {item}: {e}")

        return plugins
