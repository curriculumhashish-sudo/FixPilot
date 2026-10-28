"""用于技能加载和管理的实用功能。"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from fastmcp.mcp_config import MCPConfig

from openhands.sdk.git.cached_repo import GitHelper, try_cached_clone_or_update
from openhands.sdk.logger import get_logger
from openhands.sdk.skills.exceptions import SkillValidationError
from openhands.sdk.utils.path import (
    get_user_persistence_dir,
    resolves_within,
    to_posix_path,
)


if TYPE_CHECKING:
    from openhands.sdk.mcp.config import MCPServer
    from openhands.sdk.skills.skill import Skill, SkillResources

# 机密查找函数的类型别名
SecretLookup = Callable[[str], str | None]

logger = get_logger(__name__)

# 用于变量扩展的正则表达式模式仅花括号：${VAR} 或 ${VAR:-default}
#
_BRACED_VAR_PATTERN = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)(?::-([^}]*))?\}")
# 带花括号和不带花括号：$VAR、${VAR} 或 ${VAR:-default}
_ALL_VAR_PATTERN = re.compile(
    r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)(?::-([^}]*))?\}|\$([a-zA-Z_][a-zA-Z0-9_]*)"
)


def expand_variable_references(
    data: Any,
    *,
    variables: dict[str, str] | None = None,
    get_secret: SecretLookup | None = None,
    check_env: bool = False,
    expand_defaults: bool = True,
    support_unbraced: bool = False,
) -> Any:
    """扩展数据结构中的变量引用。

    这是MCP配置扩展和运行时工具参数扩展所使用的核心扩展函数。

    支持变量扩展模式：
    - ${VAR} - 花括号变量引用（始终支持）
    - ${VAR:-default} - 使用默认值（始终支持）
    - $VAR - 无括号变量引用（仅当 support_unbraced=True 时）

    解决顺序（仅在提供/启用时检查每个源）：
    1. 提供变量字典
    2. 机密 (via get_secret 回调)
    3. 环境变量（仅当 check_env=True 时）
    4. 默认值（仅当 expand_defaults=True 时）

    Args:
        data: 要扩展的数据（字符串、字典、列表或其他）。
        variables: 变量名到值的字典。
        get_secret: 回调查找一个机密按名称。
        check_env: 如果为 True，则检查 os.environ 是否有未解析的变量。
        expand_defaults: 如果为 True，则对未解析的变量应用默认值。
        support_unbraced: 如果是True，除了${VAR}之外还支持$VAR语法。

    Returns:
        具有变量引用的数据已扩展。
    """
    pattern = _ALL_VAR_PATTERN if support_unbraced else _BRACED_VAR_PATTERN

    def replace_var(match: re.Match) -> str:
        # 对于支撑模式：group(1) = var_name、group(2) = 默认对于所有模式：group(1)=支撑
        # 、group(2)=默认、group(3)=不支撑
        #
        if support_unbraced:
            braced_var = match.group(1)
            default_value = match.group(2)
            unbraced_var = match.group(3)
            var_name = braced_var or unbraced_var
        else:
            var_name = match.group(1)
            default_value = match.group(2)

        # 解析顺序：变量 -> 机密 -> env -> 默认值
        if variables is not None and var_name in variables:
            return variables[var_name]

        if get_secret is not None:
            secret_value = get_secret(var_name)
            if secret_value is not None:
                return secret_value

        if check_env and var_name in os.environ:
            return os.environ[var_name]

        # 仅当 expand_defaults 为 True 并且我们有默认值时才应用默认值
        if expand_defaults and default_value is not None:
            return default_value

        # 如果未找到则返回原始内容（保留占位符）
        return match.group(0)

    def expand_value(value: Any) -> Any:
        match value:
            case str():
                return pattern.sub(replace_var, value)
            case dict():
                return {
                    expand_value(k) if isinstance(k, str) else k: expand_value(v)
                    for k, v in value.items()
                }
            case list():
                return [expand_value(item) for item in value]
            case _:
                return value

    return expand_value(data)


# 每个 AgentSkills 规范的标准资源目录名称
RESOURCE_DIRECTORIES = ("scripts", "references", "assets")

# 有效 AgentSkills 名称的正则表达式模式
# - 1-64 个字符
# - 仅小写字母数字 + 连字符（a-z、0-9、-）
# - 不得以连字符开头或结尾
# - 不得包含连续的连字符 (--)
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def find_skill_md(skill_dir: Path) -> Path | None:
    """在目录中查找 SKILL.md 文件（不区分大小写）。

    Args:
        skill_dir: 要搜索的技能目录的路径。

    Returns:
        如果找到则指向 SKILL.md 的路径，否则为 None。
    """
    if not skill_dir.is_dir():
        return None
    # sorted() 确保确定性案例碰撞获胜者 (SKILL.md < skill.md)。
    for item in sorted(skill_dir.iterdir()):
        if item.is_file() and item.name.lower() == "skill.md":
            return item
    return None


def find_mcp_config(skill_dir: Path) -> Path | None:
    """在技能目录中查找 .mcp.json 文件。

    Args:
        skill_dir: 要搜索的技能目录的路径。

    Returns:
        如果找到，则指向 .mcp.json 的路径，否则为 None。
    """
    if not skill_dir.is_dir():
        return None
    mcp_json = skill_dir / ".mcp.json"
    if mcp_json.exists() and mcp_json.is_file():
        return mcp_json
    return None


def expand_mcp_variables(
    config: dict,
    variables: dict[str, str],
    get_secret: SecretLookup | None = None,
    *,  # 此后仅包含关键字 (PEP 3102)
    expand_defaults: bool = True,
) -> dict:
    """展开 MCP 配置中的变量。

    支持类似于 Claude Code 的变量扩展：
    - ${VAR} - 环境变量，提供的变量，或机密
    - ${VAR:-default} - 使用默认值

    决议顺序：
    1. 提供的变量 (e.g., SKILL_ROOT)
    2. 机密（通过 get_secret 回调，如果提供）
    3. 环境变量
    4. 默认值（如果指定且 expand_defaults=True）

    Args:
        config: MCP配置字典。
        variables: 变量名到值的字典 (e.g., SKILL_ROOT)。
        get_secret: 回调查找一个机密按名称。 我们使用了一个回调
            而不是字典以避免将所有机密提取为纯文本。 通过
            `secret_registry.get_secret_value` 或
            `{"K": "V"}.get` 进行测试。
        expand_defaults: 如果为 True，则对未解析的变量应用默认值。
            如果为 False，则按原样保留 ${VAR:-default} 以供以后扩展。 当机密尚不可用
            时，这允许延迟扩展。

    Returns:
        变量扩展的配置。
    """
    # 通过 MCP 配置设置使用共享扩展功能：
    # - check_env=True（检查环境变量）
    # - support_unbraced=False（配置文件仅使用 ${VAR} 语法）
    expanded_config = expand_variable_references(
        config,
        variables=variables,
        get_secret=get_secret,
        check_env=True,
        expand_defaults=expand_defaults,
        support_unbraced=False,
    )

    if not isinstance(expanded_config, dict):
        raise TypeError("expanded MCP config must be a dictionary")
    return expanded_config


def expand_mcp_servers(
    servers: Mapping[str, MCPServer],
    get_secret: SecretLookup | None = None,
) -> dict[str, MCPServer]:
    """展开 MCP 服务器中的 ``${VAR}`` 占位符，应用默认值。

    ``literal_values`` 服务器返回原样：它们来自一个智能体插件包，其加载器已经扩展了标
    准允许的两个占位符，而 §9.2 不允许扩展其他内容
    -- 包不能将机密拉入其自己的子进程中。
    """
    # 延迟导入：openhands.sdk.mcp 导入该模块。
    from openhands.sdk.mcp.config import coerce_mcp_config, dump_mcp_config

    expandable = {name: s for name, s in servers.items() if not s.literal_values}
    if not expandable:
        return dict(servers)
    expanded = expand_mcp_variables(
        {"mcpServers": dump_mcp_config(expandable)},
        {},
        get_secret=get_secret,
        expand_defaults=True,
    )
    return {**servers, **coerce_mcp_config(expanded["mcpServers"])}


def load_mcp_config(
    mcp_json_path: Path,
    skill_root: Path | None = None,
    get_secret: SecretLookup | None = None,
    *,  # 此后仅包含关键字 (PEP 3102)
    expand_defaults: bool = True,
) -> dict:
    """使用变量扩展加载并解析 .mcp.json。

    Args:
        mcp_json_path: .mcp.json 文件的路径。
        skill_root: 技能的根目录（用于${SKILL_ROOT}扩展）。
        get_secret: 可选回调用于查找每个对话机密。
            有关为什么这是回调的详细信息，请参阅 expand_mcp_variables()。
        expand_defaults: 如果为 True，则对未解析的变量应用默认值。
            如果为 False，则按原样保留 ${VAR:-default} 以供以后扩展。 在插件加载期间
            使用 False 来推迟，直到机密可用。

    Returns:
        已解析的MCP配置字典。

    Raises:
        SkillValidationError: 如果文件无法解析或无效。
    """
    try:
        with open(mcp_json_path, encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise SkillValidationError(f"Invalid JSON in {mcp_json_path}: {e}") from e
    except OSError as e:
        raise SkillValidationError(f"Cannot read {mcp_json_path}: {e}") from e

    if not isinstance(config, dict):
        raise SkillValidationError(
            f"Invalid .mcp.json format: expected object, got {type(config).__name__}"
        )

    # 准备扩展变量
    variables: dict[str, str] = {}
    if skill_root:
        variables["SKILL_ROOT"] = str(skill_root)

    # 展开变量（包括机密（如果提供））
    config = expand_mcp_variables(
        config, variables, get_secret=get_secret, expand_defaults=expand_defaults
    )

    # 使用 FastMCP 的配置模型验证外部 .mcp.json 形状。
    try:
        MCPConfig.model_validate(config)
    except Exception as e:
        raise SkillValidationError(f"Invalid MCP configuration: {e}") from e

    return config


def validate_skill_name(name: str, directory_name: str | None = None) -> list[str]:
    """根据 AgentSkills 规范验证技能名称。

    Args:
        name: 要验证的技能名称。
        directory_name: 用于检查匹配的可选目录名称。

    Returns:
        验证错误消息列表（如果有效则为空）。
    """
    errors = []

    if not name:
        errors.append("Name cannot be empty")
        return errors

    if len(name) > 64:
        errors.append(f"Name exceeds 64 characters: {len(name)}")

    if not SKILL_NAME_PATTERN.match(name):
        errors.append(
            "Name must be lowercase alphanumeric with single hyphens "
            "(e.g., 'my-skill', 'pdf-tools')"
        )

    if directory_name and name != directory_name:
        errors.append(f"Name '{name}' does not match directory '{directory_name}'")

    return errors


def find_third_party_files(
    repo_root: Path, third_party_skill_names: dict[str, str]
) -> list[Path]:
    """在存储库根目录中查找第三方技能文件。

    搜索 .cursorrules、AGENTS.md、CLAUDE.md 等文件。 不区分大小写的匹配。

    解析符号链接以便 e.g。 ``CLAUDE.md -> AGENTS.md`` 被检测为重复文件，并且仅返回规
    范（非符号链接）文件。

    Args:
        repo_root: 存储库根目录的路径。
        third_party_skill_names: 小写文件名到技能名称的映射。

    Returns:
        找到的第三方技能文件的路径列表。
    """
    if not repo_root.exists():
        return []

    # 构建一组目标文件名（小写）以进行不区分大小写的匹配
    target_names = {name.lower() for name in third_party_skill_names}

    files: list[Path] = []
    seen_names: set[str] = set()
    seen_real_paths: set[Path] = set()
    # sorted() 因此 AGENTS.md/agents.md 冲突和顺序是确定性的。
    for item in sorted(repo_root.iterdir()):
        if item.is_file() and item.name.lower() in target_names:
            # 避免重复（e.g.、AGENTS.md 和 agents.md 在同一目录中）
            name_lower = item.name.lower()
            if name_lower in seen_names:
                logger.warning(
                    f"Duplicate third-party skill file ignored: {item} "
                    f"(already found a file with name '{name_lower}')"
                )
                continue

            # 解析符号链接以检测 e.g。 CLAUDE.md -> AGENTS.md
            real_path = item.resolve()
            if real_path in seen_real_paths:
                logger.debug(
                    f"Symlinked third-party skill file ignored: {item} "
                    f"(resolves to already-loaded {real_path})"
                )
                continue

            files.append(item)
            seen_names.add(name_lower)
            seen_real_paths.add(real_path)
    return files


def _git_worktree_relpaths(work_dir: Path) -> list[PurePosixPath] | None:
    """返回``work_dir``下的工作树个文件路径（相对于它）：已跟踪
    加上 ``.gitignore`` 不排除的未跟踪文件，因此新写入（未提交）的文件仍然有效。 None
     当 git 不可用时，调用者可以步行代替。
    """
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(work_dir),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            return None
        text = proc.stdout.decode("utf-8", "surrogateescape")
        return [PurePosixPath(p) for p in text.split("\0") if p]
    return None


def _walk_relpaths(work_dir: Path) -> list[PurePosixPath]:
    """filesystem-walk 回退方案：``work_dir``下的文件路径（相对于它），
    跳过隐藏目录和 ``node_modules`` 目录。 仅当 git 不可用时使用（git 路径依赖于
    ``.gitignore``）。
    """
    results: list[PurePosixPath] = []
    for dirpath, dirnames, filenames in os.walk(work_dir):
        # 就地修剪，使 os.walk 不会下降到跳过的目录。
        dirnames[:] = [
            d for d in dirnames if not d.startswith(".") and d != "node_modules"
        ]
        rel_dir = Path(dirpath).relative_to(work_dir)
        for filename in filenames:
            results.append(PurePosixPath((rel_dir / filename).as_posix()))
    return results


def find_nested_third_party_files(
    work_dir: Path, third_party_skill_names: dict[str, str]
) -> list[tuple[Path, PurePosixPath]]:
    """在``work_dir``（顶层）下查找第三方指令文件*嵌套*
    由：func:`find_third_party_files`) 处理，因此每个都可以成为目录范围的路径规则。
    如果可用，则使用 ``git ls-files``，
    否则使用修剪过的步行。 返回 ``(absolute_path, relative_dir)`` 个元组
    ``relative_dir``POSIX-相对于``work_dir``。"""
    if not work_dir.exists():
        return []

    target_names = {name.lower() for name in third_party_skill_names}
    rel_paths = _git_worktree_relpaths(work_dir)
    if rel_paths is None:
        rel_paths = _walk_relpaths(work_dir)

    results: list[tuple[Path, PurePosixPath]] = []
    seen_real_paths: set[Path] = set()
    for rel in rel_paths:
        if rel.name.lower() not in target_names:
            continue
        rel_dir = rel.parent
        # 跳过顶级文件：那些属于 find_third_party_files 的文件。
        if rel_dir == PurePosixPath("."):
            continue
        abs_path = work_dir / rel
        if not abs_path.is_file():
            continue
        real_path = abs_path.resolve()
        if real_path in seen_real_paths:
            continue
        seen_real_paths.add(real_path)
        results.append((abs_path, rel_dir))
    return sorted(results, key=lambda pair: pair[1].as_posix())


def find_skill_md_directories(skill_dir: Path, root: Path | None = None) -> list[Path]:
    """查找包含 SKILL.md 个文件的 AgentSkills 样式目录。

    Args:
        skill_dir: 技能目录的路径。
        root: 如果给定，则在其外部解析的目录和 SKILL.md 文件
            被跳过，并且转义目录永远不会列出。

    Returns:
        SKILL.md 文件的路径列表。
    """
    results: list[Path] = []
    if not skill_dir.exists():
        return results
    for subdir in sorted(skill_dir.iterdir()):
        if root is not None and not resolves_within(subdir, root):
            continue
        if subdir.is_dir():
            skill_md = find_skill_md(subdir)
            if skill_md and (root is None or resolves_within(skill_md, root)):
                results.append(skill_md)
    return results


def find_regular_md_files(
    skill_dir: Path,
    exclude_dirs: set[Path],
    recursive: bool = True,
    root: Path | None = None,
) -> list[Path]:
    """查找常规 .md 技能文件，不包括 SKILL.md 和排除目录中的文件。

    Args:
        skill_dir: 技能目录的路径。
        exclude_dirs: 要排除的目录集（e.g.、SKILL.md 目录）。
        recursive: 如果是False，则仅扫描skill_dir的直接子级，
            其中除 README 之外的每个 .md 文件都是一项技能。
        root: 如果给出，则跳过在其外部解析的文件。

    Returns:
        常规 .md 技能文件的路径列表。
    """
    files: list[Path] = []
    if not skill_dir.exists():
        return files
    if not recursive:
        return [
            f
            for f in sorted(skill_dir.glob("*.md"))
            if f.is_file()
            and f.name.lower() != "readme.md"
            and (root is None or resolves_within(f, root))
        ]
    for f in sorted(skill_dir.rglob("*.md")):
        is_readme = f.name == "README.md"
        is_skill_md = f.name.lower() == "skill.md"
        is_in_excluded_dir = any(f.is_relative_to(d) for d in exclude_dirs)
        if not is_readme and not is_skill_md and not is_in_excluded_dir:
            if root is None or resolves_within(f, root):
                files.append(f)
    return files


def load_and_categorize(
    path: Path,
    skill_base_dir: Path,
    repo_skills: dict[str, Skill],
    knowledge_skills: dict[str, Skill],
    agent_skills: dict[str, Skill],
    strict: bool = True,
    root: Path | None = None,
) -> None:
    """加载技能并对其进行分类。

    分类为 repo_skills、knowledge_skills 或 agent_skills。

    Args:
        path: 技能文件的路径。
        skill_base_dir: 技能的基本目录（用于派生相对名称）。
        repo_skills: 触发器=None（永久上下文）的技能词典。
        knowledge_skills: 带触发器的技能词典（渐进）。
        agent_skills: AgentSkills 标准 SKILL.md 文件的字典。
        strict: 如果为 True，则强制执行严格的 AgentSkills 名称验证。
        root: 如果给定，则在其之外解析的技能级别 ``.mcp.json`` 是
            未加载。
    """
    # 此处导入以避免循环依赖
    from openhands.sdk.skills.skill import Skill

    skip_mcp = False
    if root is not None:
        mcp_json = find_mcp_config(path.parent)
        skip_mcp = mcp_json is not None and not resolves_within(mcp_json, root)
    skill = Skill.load(path, skill_base_dir, strict=strict, skip_mcp=skip_mcp)

    # AgentSkills（SKILL.md 目录）是与 OpenHands 技能不同的类别。 它们遵循 AgentSkills
    # 标准，应该以不同的方式处理。
    #
    is_skill_md = path.name.lower() == "skill.md"
    if is_skill_md:
        agent_skills[skill.name] = skill
    elif skill.trigger is None:
        repo_skills[skill.name] = skill
    else:
        knowledge_skills[skill.name] = skill


def get_skills_cache_dir() -> Path:
    """获取公共技能库本地缓存目录。

    Returns:
        用户持久化目录的 ``cache/skills`` 子目录的路径（``~/.openhands/cache/skills``
         不存在
        OH_PERSISTENCE_DIR）。
    """
    cache_dir = get_user_persistence_dir() / "cache" / "skills"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def update_skills_repository(
    repo_url: str,
    ref: str,
    cache_dir: Path,
    strict: bool = False,
) -> Path | None:
    """克隆或更新本地技能存储库。

    共享的 Git 缓存将 ``ref`` 解析为提交并使用分离的签出。

    Args:
        repo_url: 技能库的URL。
        ref: 分支名称、标签或要签出的完整提交 SHA。
        cache_dir: 应缓存存储库的目录。
        strict: 如果为 True，则当无法更新现有克隆时返回 None
            (e.g. 获取离线失败）而不是过时的克隆。

    Returns:
        如果成功，则为本地存储库的路径，否则为 None。
    """
    repo_path = cache_dir / "public-skills"
    return try_cached_clone_or_update(
        repo_url, repo_path, ref=ref, update=True, strict=strict
    )


def is_skills_repo_pinned(repo_path: Path, ref: str | None = None) -> bool:
    """返回 ``ref`` 是否是缓存标签或对象 ID。

    公共技能将标签和对象 ID 视为固定的。 分支和其他命名引用保持可刷新。 如果没有
    ``ref``，请使用旧版 detached-HEAD 检查。 当 ref 无法
    分类时返回 False。
    """
    try:
        if ref is None:
            return GitHelper().get_current_branch(repo_path) is None
        return GitHelper().requested_ref_is_pinned(repo_path, ref)
    except Exception:
        return False


def discover_skill_resources(skill_dir: Path) -> SkillResources:
    """发现技能目录中的资源目录。

    扫描标准 AgentSkills 资源目录：
    - 脚本/：可执行脚本
    - 参考文献/：参考文档
    - 资产/：静态资产

    Args:
        skill_dir: 技能目录的路径。

    Returns:
        SkillResources 包含每个资源目录中的文件列表。
    """
    # 此处导入以避免循环依赖
    from openhands.sdk.skills.skill import SkillResources

    collected: dict[str, list[str]] = {}
    for resource_type in RESOURCE_DIRECTORIES:
        resource_dir = skill_dir / resource_type
        if resource_dir.is_dir():
            collected[resource_type] = _list_resource_files(resource_dir, resource_type)

    return SkillResources(
        skill_root=to_posix_path(skill_dir.resolve()),
        scripts=collected.get("scripts", []),
        references=collected.get("references", []),
        assets=collected.get("assets", []),
    )


def _list_resource_files(
    resource_dir: Path,
    resource_type: str,
) -> list[str]:
    """列出资源目录中的文件。

    Args:
        resource_dir: 资源目录的路径。
        resource_type: 资源类型（脚本、参考文献、资产）。

    Returns:
        资源目录中的相对文件路径列表。
    """
    files: list[str] = []
    try:
        for item in resource_dir.rglob("*"):
            if item.is_file():
                # 存储资源目录的相对路径
                rel_path = item.relative_to(resource_dir)
                files.append(to_posix_path(rel_path))
    except OSError as e:
        logger.warning(f"Error listing {resource_type} directory: {e}")
    return sorted(files)
