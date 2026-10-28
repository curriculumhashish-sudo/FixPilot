"""从 Markdown 文件加载智能体定义并将它们注册为委托智能体。

智能体定义是 Markdown 个带有 YAML 前置元数据的文件，位于
项目或用户级别的 `.agents/agents` 或 `.openhands/agents` 目录。 它们会自动注册到委托
中智能体注册表，以便在委托期间可以通过名称调用它
们。

目录约定（按优先顺序）：

    {project}/                      # 项目级别的，主要（最高文件优先级）
        .代理/
            代理/
                code-reviewer.md # 智能体定义 security-expert.md # 智能体定义

    {project}/
        .openhands/
            代理/
                code-reviewer.md

    ~/.agents/ # 用户级别，主要
        代理/
            my-global-agent.md

    ~/.openhands/ # 用户级，遗留（最低文件优先级）
        代理/
            my-global-agent.md

优先级（从最高到最低）：
  1. 编程 `register_agent()` 调用（永不覆盖）
  2. 插件智能体 (`Plugin.agents`)
  3. 项目级 `.agents/agents/*.md`
  4. 项目级 `.openhands/agents/*.md`
  5. 用户级别 `~/.agents/agents/*.md`
  6. 用户级别 `~/.openhands/agents/*.md`
"""

from pathlib import Path
from typing import Final

from openhands.sdk.logger import get_logger
from openhands.sdk.subagent.schema import AgentDefinition
from openhands.sdk.utils.path import get_user_persistence_dir, resolves_within


logger = get_logger(__name__)


# 按优先级顺序扫描智能体定义的目录。 当相同的智能体名称出现在多个目录中时，第一个匹配获
# 胜。
#
_FILE_BASED_AGENTS_DIR: Final[list[str]] = [
    ".agents/agents",
    ".openhands/agents",
]
# 搜索智能体时跳过分析的文件
_SKIP_FILES: Final[set[str]] = {"README.md", "readme.md"}


def load_project_agents(project_dir: str | Path) -> list[AgentDefinition]:
    """从项目级目录加载智能体定义。

    搜索次数
        - project_dir/.代理/代理和
        - project_dir / openhands/agents（按顺序）。
    请注意，对于重复名称，`.agents/agents` 定义优先。

    只读取顶级`.md`文件； 子目录（如 `skills/`）将被跳过。 `README.md` 文件也会被跳过
    。

    Args:
        project_dir: 项目目录

    Returns:
        ``AgentDefinition`` 对象的列表，如果不存在目录则为空列表。
    """
    project_dir = Path(project_dir)
    return _load_agents_from_dirs([project_dir / d for d in _FILE_BASED_AGENTS_DIR])


def load_user_agents() -> list[AgentDefinition]:
    """从用户级目录加载智能体定义。

    搜索次数
        - 〜/.agents/agents 和
        - ~/.openhands/agents（按顺序）。
    请注意，对于重复名称，`.agents/agents` 定义优先。

    与 `load_project_agents` 相同的文件级规则。

    Returns:
        ``AgentDefinition`` 对象的列表，如果不存在目录则为空列表。
    """
    return _load_agents_from_dirs([_user_agents_dir(d) for d in _FILE_BASED_AGENTS_DIR])


def _user_agents_dir(relative: str) -> Path:
    """将基于文件的智能体目录映射到其用户级别基础上。

    ``.openhands/agents`` 位于持久化目录下，它取代了
    ``~/.openhands`` 基础； 所有其他条目都与家庭相关。
    """
    base, _, rest = relative.partition("/")
    if base == ".openhands":
        return get_user_persistence_dir() / rest
    return Path.home() / relative


def _load_agents_from_dirs(dirs: list[Path]) -> list[AgentDefinition]:
    """通过先胜重复数据删除从多个目录加载智能体。

    按顺序扫描目录； 如果相同的智能体名称出现在后面的目录中，则会默默地跳过。
    """
    seen_names: set[str] = set()
    result: list[AgentDefinition] = []
    for agents_dir in dirs:
        for agent_def in load_agents_from_dir(agents_dir):
            if agent_def.name not in seen_names:
                seen_names.add(agent_def.name)
                result.append(agent_def)
            else:
                logger.debug(
                    f"Skipping duplicate agent '{agent_def.name}' from {agents_dir}"
                )
    return result


def discover_agents(
    project_dir: str | Path | None,
    *,
    include_project: bool = True,
    include_user: bool = True,
) -> list[AgentDefinition]:
    """发现基于项目/用户文件的智能体，而无需注册它们。

    非修改版本的 ``register_file_agents``返回发现的定义 ``level``/``source`` 设置，留
    下全局注册表 untouched (
    注册表暂停会话。 内置插件住在
    ``openhands-tools``（不是 SDK 依赖项），因此希望它们添加的调用者
    ``discover_builtin_agents`` 分别。

    优先级匹配 ``register_file_agents``：项目胜过用户。

    Args:
        project_dir: 要扫描的项目目录，或 None 跳过项目智能体。
        include_project: 包括项目级别智能体。
        include_user: 包括用户级别智能体。

    Returns:
        按名称删除重复的定义（先胜）。
    """
    discovered: list[AgentDefinition] = []
    if include_project and project_dir is not None:
        discovered.extend(
            agent_def.model_copy(update={"level": "project"})
            for agent_def in load_project_agents(project_dir)
        )
    if include_user:
        discovered.extend(
            agent_def.model_copy(update={"level": "user"})
            for agent_def in load_user_agents()
        )

    seen_names: set[str] = set()
    result: list[AgentDefinition] = []
    for agent_def in discovered:
        if agent_def.name not in seen_names:
            seen_names.add(agent_def.name)
            result.append(agent_def)
    return result


def load_agents_from_dir(
    agents_dir: Path, root: Path | None = None
) -> list[AgentDefinition]:
    """扫描目录中基于 Markdown 的智能体定义。

    遍历所提供目录的顶层，尝试将任何 `.md` 文件加载为 AgentDefinitions。 请注意，默认
    情况下会跳过 README.md 个文件。

    Args:
        agents_dir: 包含智能体个文件的目录的文件系统路径。
        root: 如果给出，则解析此目录之外的文件 (e.g. 通过
            符号链接）被跳过。 插件在这里传递它们的根。

    Returns:
        成功实例化的 AgentDefinition 对象的列表。 如果目录不存在或不包含有效的智能体
        ，则返回空列表。

    Note:
        加载单个文件失败会被记录为带有堆栈跟踪的警告，但不会停止整个加载过程。
    """
    if not agents_dir.is_dir():
        return []

    definitions: list[AgentDefinition] = []
    for md_file in sorted(agents_dir.iterdir()):
        # 仅顶级 .md 文件； 跳过子目录和 README
        if (
            md_file.is_dir()
            or md_file.suffix.lower() != ".md"
            or md_file.name in _SKIP_FILES
        ):
            continue
        if root is not None and not resolves_within(md_file, root):
            continue

        try:
            agent_def = AgentDefinition.load(md_file)
            definitions.append(agent_def)
            logger.debug(f"Loaded agent definition '{agent_def.name}' from {md_file}")
        except Exception:
            logger.warning(
                f"Failed to load agent definition from {md_file}", exc_info=True
            )

    return definitions
