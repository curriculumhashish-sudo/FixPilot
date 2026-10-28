"""``PluginFormat`` 策略基类和共享组件助手。

包含抽象：class:`PluginFormat` 合约以及每种格式共享的发现逻辑（技能发现和最终组装）。
 具体策略存在于它们自己的模块中（e.g.
``claude_code.py``).

请参阅 ``openhands.sdk.plugin.format`` 包文档字符串了解设计概述和添加新格式的方法。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from openhands.sdk.hooks import HookConfig
from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.config import MCPServer
from openhands.sdk.plugin.types import CommandDefinition, PluginManifest
from openhands.sdk.skills.skill import Skill, SkillResources, load_skills_from_dir
from openhands.sdk.skills.utils import find_skill_md
from openhands.sdk.subagent.schema import AgentDefinition
from openhands.sdk.utils.path import resolves_within, to_posix_path


if TYPE_CHECKING:
    from openhands.sdk.plugin.plugin import Plugin

logger = get_logger(__name__)

_SCHEMAS_DIR = Path(__file__).parent / "schemas"


@cache
def _load_schema(filename: str) -> dict[str, Any]:
    """阅读供应商模式。 已缓存； 从未通过网络获取。"""
    return json.loads((_SCHEMAS_DIR / filename).read_text(encoding="utf-8"))


class PluginFormat(ABC):
    """将插件目录读入规范化的 ``Plugin`` 的策略。

    子类实现特定于格式的部分（清单、MCP 配置和客户端扩展）。 技能发现和最终组装在：
    meth:`load` 中共享，因为技能规则在格式之间是相同的，输出模型也是格式
    无关的。
    """

    # ：日志中和``detect_format``使用的稳定标识符。
    name: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        # 在类定义时强制执行 ``name`` 合约。 如果没有这个，省略 ``name`` 的子类会干净地
        # 实例化，并且只会在第一次读取 ``.name`` 时失败并显示 AttributeError (e.g. 在
        # ``detect_format``'s debug log).
        super().__init_subclass__(**kwargs)
        if "name" not in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must define a class-level 'name' attribute"
            )

    @classmethod
    @abstractmethod
    def detect(cls, plugin_dir: Path) -> bool:
        """如果应使用此格式加载 ``plugin_dir``，则返回 True。"""

    @abstractmethod
    def load_manifest(self, plugin_dir: Path) -> PluginManifest:
        """加载并验证插件清单。"""

    @abstractmethod
    def load_mcp_config(self, plugin_dir: Path) -> dict[str, MCPServer]:
        """加载插件的 MCP 服务器配置。"""

    @abstractmethod
    def load_hooks(self, plugin_dir: Path) -> HookConfig | None:
        """加载插件的钩子配置（如果不存在则加载None）。"""

    @abstractmethod
    def load_agents(self, plugin_dir: Path) -> list[AgentDefinition]:
        """加载插件的智能体定义。"""

    @abstractmethod
    def load_commands(self, plugin_dir: Path) -> list[CommandDefinition]:
        """加载插件的命令定义。"""

    def load_skills(self, plugin_dir: Path) -> list[Skill]:
        """发现插件的技能。

        跨格式共享：``skills/<name>/SKILL.md`` 发现规则对于 Claude Code 和智能体插件
        是相同的。 支持两种布局：

        - 多技能：每个技能包含一个 ``<name>/SKILL.md`` 个 ``skills/`` 目录（或单个
        ``.md`` 个文件）。
        - 单技能：当没有插件时，在插件根目录下有一个``SKILL.md``
          ``skills/`` 目录。 Claude Code加载这样的插件作为单技能插件（v2.1.142+）；
          这反映了这种行为如此独立智能体作为插件加载发
          布的技能，无需额外的嵌套级别。

        Note: 插件技能加载宽松验证（严格=False）
        支持可能使用不同命名约定的 Claude Code 插件。
        """
        skills_dir = plugin_dir / "skills"
        if skills_dir.exists(follow_symlinks=False):
            if not resolves_within(skills_dir, plugin_dir):
                return []
            if not skills_dir.is_dir():
                logger.warning(f"Ignoring skills: {skills_dir} is not a directory")
                return []
            # 根据智能体插件 §5 非递归：嵌套 .md 文件是技能资源 (e.g. 参考文献/），而不
            # 是额外的技能。
            #
            repo, knowledge, agent = load_skills_from_dir(
                skills_dir, strict=False, recursive=False, root=plugin_dir
            )
            skills = [*repo.values(), *knowledge.values(), *agent.values()]
            # 按类型对技能进行分类； 恢复磁盘顺序。
            return [
                _without_escaping_resources(skill, plugin_dir)
                for skill in sorted(skills, key=lambda s: Path(s.source or ""))
            ]

        root_skill_md = find_skill_md(plugin_dir)
        if root_skill_md is not None and resolves_within(root_skill_md, plugin_dir):
            return _load_root_skill(plugin_dir, root_skill_md)

        return []

    def load(self, plugin_dir: Path) -> Plugin:
        """从 ``plugin_dir`` 组装归一化的 ``Plugin``。

        这种编排是共享的：每种格式都会生成相同的内存中模型，因此下游合并/应用逻辑永远
        不需要知道格式。

        ``plugin_dir`` 按原样使用（它成为加载的 ``Plugin.path``）； 这个方法并不能解
        决这个问题。 ``Plugin.load()``
         在此处调度之前解析路径，因此直接调用者
        如果 ``detect_format(path).load(path)`` 想要 ``Plugin.path`` 完全解析，则应传
        递已解析的路径。

        Raises:
            FileNotFoundError: 如果 ``plugin_dir`` 不是现有目录。
        """
        # 延迟导入以避免 plugin.py 的模块级导入循环，它导入 detect_format() 的格式包。
        #
        from openhands.sdk.plugin.plugin import Plugin

        if not plugin_dir.is_dir():
            raise FileNotFoundError(f"Plugin directory not found: {plugin_dir}")

        manifest = self.load_manifest(plugin_dir)
        skills = self.load_skills(plugin_dir)
        hooks = self.load_hooks(plugin_dir)
        mcp_config = self.load_mcp_config(plugin_dir)
        agents = self.load_agents(plugin_dir)
        commands = self.load_commands(plugin_dir)

        return Plugin(
            manifest=manifest,
            path=to_posix_path(plugin_dir),
            skills=skills,
            hooks=hooks,
            mcp_config=mcp_config,
            agents=agents,
            commands=commands,
        )


def _read_hooks_config(root: Path, plugin_dir: Path | None = None) -> HookConfig | None:
    """读取 ``root`` 下的 ``hooks/hooks.json``，如果不存在则读取 None。

    由具体策略共享：钩子、智能体和命令都使用相同的磁盘布局，只是它们根目录不同（
    Claude Code 的插件根目录，智能体插件的客户端扩展目录）。
    """
    hooks_json = root / "hooks" / "hooks.json"
    if not hooks_json.exists() or not resolves_within(hooks_json, plugin_dir or root):
        return None

    try:
        hook_config = HookConfig.load(path=hooks_json)
        # 解析但声明没有钩子的 hooks.json 会产生一个空配置。 使其与“文件不存在”(None) 区
        # 分开来。 无法解析或模式无效的文件从 load() 中引发并在下面捕获。
        #
        if hook_config.is_empty():
            logger.info(f"No hooks configured in {hooks_json}")
            return HookConfig()
        logger.info(f"Loaded hooks from {hooks_json}")
        return hook_config
    except Exception as e:
        logger.warning(f"Failed to load hooks from {hooks_json}: {e}")
        return None


def _read_command_definitions(
    root: Path, plugin_dir: Path | None = None
) -> list[CommandDefinition]:
    """从``root``下的``commands/``目录读取命令定义。

    命令没有与：func:`load_agents_from_dir` 对应的命令，因此这是插件格式仍然拥有的三
    个加载器中的一个。 它应用相同的文件谓词，因此
    ``commands/`` 和 ``agents/`` 保持对称。
    """
    plugin_dir = plugin_dir or root
    commands_dir = root / "commands"
    if not commands_dir.is_dir() or not resolves_within(commands_dir, plugin_dir):
        return []

    commands: list[CommandDefinition] = []
    for item in sorted(commands_dir.iterdir()):
        if (
            not item.is_dir()
            and item.suffix.lower() == ".md"
            and item.name
            not in (
                "README.md",
                "readme.md",
            )
            and resolves_within(item, plugin_dir)
        ):
            try:
                command = CommandDefinition.load(item)
                commands.append(command)
                logger.debug(f"Loaded command: {command.name} from {item}")
            except Exception as e:
                logger.warning(f"Failed to load command from {item}: {e}")

    return commands


def _without_escaping_resources(skill: Skill, plugin_dir: Path) -> Skill:
    """删除在根目录之外解析的资源文件（``scripts/`` 等）。"""
    res = skill.resources
    if res is None:
        return skill
    root = Path(res.skill_root)

    def kept(kind: str, files: list[str]) -> list[str]:
        return [f for f in files if resolves_within(root / kind / f, plugin_dir)]

    contained = SkillResources(
        skill_root=res.skill_root,
        scripts=kept("scripts", res.scripts),
        references=kept("references", res.references),
        assets=kept("assets", res.assets),
    )
    if contained == res:
        return skill
    resources = contained if contained.has_resources() else None
    return skill.model_copy(update={"resources": resources})


def _load_root_skill(plugin_dir: Path, skill_md: Path) -> list[Skill]:
    """加载一个单技能插件，其 ``SKILL.md`` 位于插件根目录。

    对于根技能，插件目录是技能根，因此插件级别的 .mcp.json 与 Skill.load() 尝试加载的
    文件相同。 我们通过
    skip_mcp=True to avoid double-loading with different semantics (plugin-level
    使用 expand_defaults=False 进行延迟机密扩展； 技能级别将使用 expand_defaults=True
     并提高验证错误）。
    """
    try:
        # skip_mcp=True: Plugin-level MCP already loaded
        # Skill.load()发现资源，无需重复
        skill = Skill.load(skill_md, plugin_dir, strict=False, skip_mcp=True)
        logger.debug(f"Loaded single-skill plugin: {skill.name} from {skill_md}")
        return [_without_escaping_resources(skill, plugin_dir)]
    except Exception as e:
        logger.warning(f"Failed to load root skill from {plugin_dir}: {e}")
        return []
