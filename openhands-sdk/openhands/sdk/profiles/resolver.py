"""与：mod:`openhands.sdk.launch` 共享的配置文件解析构建块。

``resolve_agent_profile()``和``resolve_agent_profile_dry_run()``是已弃用支持
``openhands.sdk.launch.resolve``和``preview_launch``。

配置文件包含 *references* (``llm_profile_ref`` / ``mcp_server_refs``) 以及
``disabled_skills`` 拒绝列表，并且在 REST 处不受机密限制； 一个
:data:`~openhands.sdk.settings.model.AgentSettingsConfig` 嵌入已解析的
``llm``/``mcp_config``/技能。 该模块将前者解析为后者，因此 ``create_agent`` /
``apply_agent_settings_diff`` /
``validate_agent_settings`` 保持不变。 参见史诗#3713。

技能*不是*像MCP服务器那样建模。 ``mcp_server_refs`` 是安全的允许列表，因为
``mcp_config`` 是完整的、已持久化、用户创作的地图。 技
能目录是从许多不完整、漂移的来源（用户/公共/组织/项目/市场）中发现的，因此，每当作者
目录与发布目录不同，就会悬空一个允许列表。 调用者应该传递发现的目录（
``load_all_skills``），而解析器则保留所有内容，除了``disabled_skills``中的名称——一个
永远挂不住的拒绝列表（#4017）。

资源特定的机密通道：

- **LLM key** → 从 LLM 配置文件存储加载到已解析的 ``llm`` 中。
- **MCP env/headers** → 乘坐过滤后的 ``mcp_config`` （由调用者解密）。
- **ACP 提供商信用** → 从未触及此处； 他们骑
  ``state.secret_registry`` ← ``request.secrets`` 在对话开始时连线 (#3720)。 解析器仅
   * 枚举 * 所需的提供程
  序机密名称（通过试运行），以便编辑器 / ``/materialize`` (#3719) 可以显示设置/缺失。
"""

from __future__ import annotations

import shlex
from collections.abc import Collection, Container, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, SecretStr

from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.llm.meta_profile_store import MetaProfile
from openhands.sdk.mcp.config import MCPServer
from openhands.sdk.profiles.agent_profile import (
    ACPAgentProfile,
    OpenHandsAgentProfile,
)
from openhands.sdk.settings.acp_providers import get_acp_provider
from openhands.sdk.settings.model import (
    AGENT_SETTINGS_SCHEMA_VERSION,
    AgentSettingsConfig,
    validate_agent_settings,
)
from openhands.sdk.skills import Skill
from openhands.sdk.subagent.scope import SubAgentScope, scope_delegation_tools
from openhands.sdk.tool.defaults import BROWSER_TOOL_NAME, launch_tool_specs
from openhands.sdk.tool.registry import is_tool_available
from openhands.sdk.tool.spec import Tool
from openhands.sdk.utils.deprecation import deprecated
from openhands.sdk.utils.pydantic_secrets import REDACTED_SECRET_VALUE


if TYPE_CHECKING:
    from openhands.sdk.llm.llm import LLM
    from openhands.sdk.llm.llm_profile_store import LLMProfileLoader
    from openhands.sdk.utils.cipher import Cipher


class ProfileNotFound(Exception):
    """引用的配置文件 (e.g. ``llm_profile_ref``) 不存在。

    路由器 (#3719) 将其映射到 HTTP 404。
    """


class DanglingMcpServerRef(Exception):
    """``mcp_server_refs`` 条目命名 ``mcp_config`` 中不存在的服务器。

    路由器 (#3719) 将其映射到 HTTP 422。:attr:`missing` 携带有问题的 key(s)。
    """

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        joined = ", ".join(repr(m) for m in missing)
        super().__init__(
            f"MCP server ref(s) not present in the user's MCP config: {joined}"
        )


class AgentProfileDiagnostics(BaseModel):
    """关于：func:`resolve_agent_profile` 会做什么的无副作用报告。

    由 ``POST /{id}/materialize`` (#3719) 和画布编辑器使用。 判决 (:attr:`valid`) 和
    悬垂引用列表与一个真实解决产生
    的完全一致； :attr:`resolved_settings` 是已脱敏设置的 dumps（只有在：attr:`valid`
     时才存在）。
    """

    agent_kind: str
    valid: bool = False
    errors: list[str] = Field(default_factory=list)
    unusable_tools: list[str] = Field(
        default_factory=list,
        description=(
            "Selected tools the runtime cannot run. An unavailable browser is "
            "left out of the launch; any other such tool fails the launch or "
            "fails when the agent uses it."
        ),
    )

    # OpenHands LLM 参考。
    llm_profile_ref: str | None = None
    llm_profile_resolved: bool = False
    llm_api_key_set: bool = False

    # MCP 组成（两种变体）。
    mcp_server_refs: list[str] | None = None
    resolved_mcp_config_keys: list[str] = Field(default_factory=list)
    dangling_mcp_server_refs: list[str] = Field(default_factory=list)

    # 技能选择（仅OpenHands）。 与``mcp_server_refs``不同，它永远不能
    # 悬挂：目录中缺少的名称是无害的空操作。
    # ``resolved_skills`` 是实际到达智能体的值。
    disabled_skills: list[str] = Field(default_factory=list)
    public_skills: list[str] | None = None
    resolved_skills: list[str] = Field(default_factory=list)

    # 机密范围（两种变体）。 ``None`` = 每机密次对话开始； 列表 = 仅那些名称，不添加任何
    # 内容。 没有悬而未决的报告：这是一个关于发布所提供内容的允许列表，因此不匹配的名称
    # 是无效的。
    #
    secret_refs: list[str] | None = None

    # ACP 提供者凭据引导编辑器/具体化检查（仅 ACP）。 这些是不共同需要的：身份验证需要
    # API密钥*或*文件内容凭据之一，并且基础URL是可选的代理路由。 将它们保留在单独的字段
    # 中可以让编辑者诚实地标记已设置/缺失，而不是将有效的仅 API 键设置视为不完整。
    #
    acp_api_key_secret_name: str | None = None
    acp_base_url_secret_name: str | None = None
    acp_file_secret_names: list[str] = Field(default_factory=list)

    # 元配置文件路由（仅限 OpenHands）。
    meta_profile_ref: str | None = None
    dangling_meta_profile_ref: str | None = None
    dangling_meta_profile_llm_refs: list[str] = Field(default_factory=list)

    # 已脱敏已解决的设置，当前 iff ``valid``。
    resolved_settings: dict[str, Any] | None = None


def _server_names(mcp_config: dict[str, MCPServer]) -> list[str]:
    return list(mcp_config)


def _partition_refs(
    refs: list[str], available: Container[str]
) -> tuple[list[str], list[str]]:
    """根据 ``available`` 中的成员资格将 ``refs`` 拆分为 ``(resolved, dangling)``。

    保留顺序和去重复：在 ``refs`` 中重复的名称在第一个位置保留一次。 由 MCP 和技能过
    滤器共享，确保两个分区完全相同 —— 特别是两个都合并重复的引用，
    ACP 技能路径需要 (``AgentContext`` 拒绝重复的技能名称)。
    """
    seen: set[str] = set()
    resolved: list[str] = []
    dangling: list[str] = []
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        (resolved if ref in available else dangling).append(ref)
    return resolved, dangling


def _compute_mcp_filter(
    mcp_config: dict[str, MCPServer],
    refs: list[str] | None,
) -> tuple[dict[str, MCPServer], list[str], list[str]]:
    """针对用户的 ``mcp_config`` 解决 ``mcp_server_refs``。

    ``None`` → 直通（所有服务器）； 非 null 列表过滤到指定的键。 返回
    ``(filtered_servers, resolved_names, dangling_names)``。
    """
    if refs is None:
        return mcp_config, _server_names(mcp_config), []
    resolved, dangling = _partition_refs(refs, mcp_config)
    return {k: mcp_config[k] for k in resolved}, resolved, dangling


def _select_skills(
    available_skills: Sequence[Skill] | None,
    disabled: Collection[str],
    public_skills: Collection[str] | None = None,
    public_skill_names: Collection[str] | None = None,
) -> list[Skill]:
    """按配置文件的技能选择过滤发现的技能目录。

    ``disabled`` 是每项技能的拒绝列表。 ``public_skills`` 是仅公共层上的允许列表（
    ``None`` = 整个层），因此用户技能会在出现时
    保留。 ``public_skill_names`` 该层的名称； ``None`` 将每个目录技能视为公共技能。
    目录中缺少的名称是无操作的，因此当目录漂移时，两
    个列表都不会导致启动失败 (#4017)。

    目录按名称进行重复数据删除（最后出现的获胜，匹配的
    ``load_all_skills`` 的后续源覆盖优先级），因此冲突目录无法妨碍 ``AgentContext``
    的重复名称验证器。 一个空的或
    ``None`` 目录不产生任何技能。
    """
    if not available_skills:
        return []
    by_name = {s.name: s for s in available_skills}
    denied = set(disabled)
    allowed = None if public_skills is None else set(public_skills)

    def keep(name: str) -> bool:
        if name in denied:
            return False
        if allowed is None or name in allowed:
            return True
        return public_skill_names is not None and name not in public_skill_names

    return [s for s in by_name.values() if keep(s.name)]


def _profile_skills(
    profile: OpenHandsAgentProfile,
    available_skills: Sequence[Skill] | None,
    public_skill_names: Collection[str] | None,
) -> list[Skill]:
    return _select_skills(
        available_skills,
        profile.disabled_skills,
        profile.public_skills,
        public_skill_names,
    )


def _api_key_set(llm: LLM) -> bool:
    """``True`` 当解析的 LLM 携带非空、非已脱敏密钥时。"""
    api_key = llm.api_key
    if api_key is None:
        return False
    value = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
    return bool(value.strip()) and value != REDACTED_SECRET_VALUE


def _acp_credential_channels(
    acp_server: str,
) -> tuple[str | None, str | None, list[str]]:
    """通过 ``ACP_PROVIDERS`` 为 ``acp_server`` 提供凭据频道。

    返回按角色分开的 ``(api_key_env_var, base_url_env_var, file_secret_names)``：API-
    key 环境变量和文
    件内容凭据是
    *替代*身份验证机制（一个就足够了），基础URL是可选的
    代理路由 —— 不是共同要求的。 ``'custom'`` 服务器的所有空/``None``，其信用由用户直
    接管理。
    """
    info = get_acp_provider(acp_server)
    if info is None:
        return None, None, []
    file_names = [spec.secret_name for spec in info.file_secrets]
    return info.api_key_env_var, info.base_url_env_var, file_names


def _build_openhands_settings(
    profile: OpenHandsAgentProfile,
    llm: LLM,
    mcp_config: dict[str, MCPServer],
    filtered_skills: list[Skill],
    *,
    browser_available: bool | None,
    meta_profile: MetaProfile | None = None,
    meta_profile_llms: Mapping[str, LLM] | None = None,
    critic_api_key: SecretStr | None = None,
) -> AgentSettingsConfig:
    """从配置文件 + LLM 组成已解决的 ``OpenHandsAgentSettings``。

    ``filtered_skills``（发现的目录减去 ``disabled_skills``）是唯一的用户/公共技能源
    （配置文件不再嵌入技能）。
    ``load_project_skills=True`` 让 ``LocalConversation`` 延迟加载 repo 范围的项目技
    能，这里无法解决（还没有工
    作区）；
    ``disabled_skills`` 被携带到上下文上，以便延迟加载应用相同的拒绝列表。
    ``load_user_skills`` /
    ``load_public_skills`` 保持 False 开启
    purpose: 用户/公共技能已经通过 ``filtered_skills`` 到达，因此
    启用标志会双重加载它们。
    """
    payload = {
        "schema_version": AGENT_SETTINGS_SCHEMA_VERSION,
        "agent_kind": "openhands",
        "agent": profile.agent,
        "llm": llm,
        "mcp_config": mcp_config,
        "tools": _scope_sub_agents(
            profile,
            profile.tools
            if browser_available is None
            else launch_tool_specs(profile.tools, browser_available=browser_available),
        ),
        "persona": profile.persona,
        "agent_context": AgentContext(
            skills=filtered_skills,
            system_message_suffix=profile.system_message_suffix,
            load_project_skills=True,
            disabled_skills=profile.disabled_skills,
        ),
        "condenser": profile.condenser,
        "verification": {
            **profile.verification.model_dump(),
            "critic_api_key": critic_api_key,
        },
        "enable_classify_and_switch_llm_tool": (
            profile.enable_classify_and_switch_llm_tool
        ),
        "active_meta_profile": profile.meta_profile_ref,
        "meta_profile": meta_profile,
        "meta_profile_llms": dict(meta_profile_llms or {}),
        "tool_concurrency_limit": profile.tool_concurrency_limit,
    }
    return validate_agent_settings(payload)


def _scope_sub_agents(
    profile: OpenHandsAgentProfile, tools: list[Tool] | None
) -> list[Tool] | None:
    if tools is None:
        return None
    return scope_delegation_tools(tools, SubAgentScope(tools=profile.tools is not None))


def _unusable_tools(
    tools: list[Tool] | None, *, browser_available: bool | None, check_usable: bool
) -> list[str]:
    if tools is None:
        return [] if browser_available is not False else [BROWSER_TOOL_NAME]
    return [
        tool.name
        for tool in tools
        if not (
            browser_available is not False
            if tool.name == BROWSER_TOOL_NAME
            else is_tool_available(tool.name, check_usable=check_usable)
        )
    ]


def _build_acp_settings(
    profile: ACPAgentProfile,
    mcp_config: dict[str, MCPServer],
    managed_skills: list[Skill],
) -> AgentSettingsConfig:
    """从配置文件中编写已解决的 ``ACPAgentSettings``。

    ``acp_command`` 存储为 shell 字符串并拆分到设置的 token 列表中。 未设置凭据 — 提
    供者信用
    ``state.secret_registry``.

    ``load_project_skills`` 保持 ``False``：ACP CLI 变为 ``AGENTS.md`` /
    ``CLAUDE.md`` 及其自己的项目技能来自会话 cwd，因此在此处加载它们会复制提示词中的
    内容 (#4019)。
    ``managed_skills`` 就是那个 *部署* 选择注入 — 当  ACP  CLI 它可以访问自己的主机配
    置，[在容器中]非空。
    ``current_datetime=None`` matches ACP没有时间戳约定。 A ``custom`` 服务器没有默认
    命令，因此必须提供一个。
    """
    command = shlex.split(profile.acp_command) if profile.acp_command else []
    if profile.acp_server == "custom" and not command:
        raise ValueError(
            "acp_command is required when acp_server='custom' — there is no "
            "default launch command to fall back to"
        )
    agent_context = AgentContext(
        skills=managed_skills, current_datetime=None, load_project_skills=False
    )
    payload = {
        "schema_version": AGENT_SETTINGS_SCHEMA_VERSION,
        "agent_kind": "acp",
        "acp_server": profile.acp_server,
        "acp_model": profile.acp_model,
        "acp_session_mode": profile.acp_session_mode,
        "acp_prompt_timeout": profile.acp_prompt_timeout,
        "acp_startup_timeout": profile.acp_startup_timeout,
        "acp_command": command,
        "acp_args": list(profile.acp_args) if profile.acp_args else [],
        "mcp_config": mcp_config,
        "agent_context": agent_context,
    }
    return validate_agent_settings(payload)


@deprecated(
    deprecated_in="1.55.0",
    removed_in="1.60.0",
    details=(
        "Use openhands.sdk.launch.resolve, which also resolves meta-profiles "
        "and reports every dangling reference at once."
    ),
)
def resolve_agent_profile(
    profile: OpenHandsAgentProfile | ACPAgentProfile,
    *,
    llm_store: LLMProfileLoader,
    mcp_config: dict[str, MCPServer],
    available_skills: list[Skill] | None,
    public_skill_names: Collection[str] | None = None,
    critic_api_key: SecretStr | None = None,
    cipher: Cipher | None = None,
    browser_available: bool | None = None,
) -> AgentSettingsConfig:
    """将配置文件的引用解析为经过验证的 ``AgentSettingsConfig``。

    ``mcp_config`` 是用户的全局配置的 MCP 服务器映射，已由调用者解密（智能体服务器在
    调用之前运行设置解密）。
    ``available_skills``是服务器发现的技能目录（智能体-服务器调用者传递
    ``load_all_skills``的结果）； OpenHands 配置文
    件保留该部分的 ``public_skills`` 和 ``disabled_skills`` 选择，ACP 配置文件保留其
    全部（没有选择）。
    ``public_skill_names`` 命名公共层 ``public_skills`` 过滤器；
    ``None`` 将每个可用技能视为公共技能。 ``None`` 技能意味着调用者没有注入任何目录 -
     发现未运行、失败，或者，对于 ACP，部署将技能来源留给
    CLI。 与 ``mcp_server_refs`` 允许列表不同，技能选择永远不会悬而未决，因此永远不会
    提高技能。 ``cipher`` 解密引用的 LLM 配置
    文件。
    ``browser_available``表示智能体运行的运行时是否可以使用浏览器工具集； 调用者对其
    进行探测。 ``None`` 离开 ``tools``，因为配
    置文件存储它们。

    Raises:
        ProfileNotFound: ``llm_profile_ref`` 不存在（OpenHands 路径）。
        DanglingMcpServerRef: ``mcp_server_refs`` 条目不在 ``mcp_config`` 中。
    """
    filtered_mcp, _, dangling = _compute_mcp_filter(mcp_config, profile.mcp_server_refs)
    if dangling:
        raise DanglingMcpServerRef(dangling)

    if isinstance(profile, OpenHandsAgentProfile):
        filtered_skills = _profile_skills(profile, available_skills, public_skill_names)
        try:
            llm = llm_store.load(profile.llm_profile_ref, cipher=cipher)
        except FileNotFoundError as e:
            raise ProfileNotFound(
                f"LLM profile {profile.llm_profile_ref!r} not found"
            ) from e
        return _build_openhands_settings(
            profile,
            llm,
            filtered_mcp,
            filtered_skills,
            browser_available=browser_available,
            critic_api_key=critic_api_key,
        )

    return _build_acp_settings(
        profile, filtered_mcp, _select_skills(available_skills, [])
    )


@deprecated(
    deprecated_in="1.55.0",
    removed_in="1.60.0",
    details="Use openhands.sdk.launch.preview_launch.",
)
def resolve_agent_profile_dry_run(
    profile: OpenHandsAgentProfile | ACPAgentProfile,
    *,
    llm_store: LLMProfileLoader,
    mcp_config: dict[str, MCPServer],
    available_skills: list[Skill] | None,
    public_skill_names: Collection[str] | None = None,
    critic_api_key: SecretStr | None = None,
    cipher: Cipher | None = None,
    browser_available: bool | None = None,
    check_usable: bool = True,
) -> AgentProfileDiagnostics:
    """计算：class:`AgentProfileDiagnostics` 而不产生任何提升或副作用。

    `resolve_agent_profile` 的组合，但记录 dangling LLM / MCP ref 作为诊断，而不是抛
    出错误，因此编辑器 /
    ``/materialize`` (#3719) 可以显示忠实的集合/缺失报告，机密已脱敏。 技能选择不能悬
    空，所以没有技能错误可报——
    ``resolved_skills`` 是从目录中保留的选择。
    ``available_skills=None``（发现已跳过或失败）表示没有用户/公共技能解析。

    ``check_usable=False`` 跳过可用性探测，对于运行时此进程无法探测。
    """
    filtered_mcp, resolved, dangling = _compute_mcp_filter(
        mcp_config, profile.mcp_server_refs
    )
    diagnostics = AgentProfileDiagnostics(
        agent_kind=profile.agent_kind,
        mcp_server_refs=profile.mcp_server_refs,
        resolved_mcp_config_keys=resolved,
        dangling_mcp_server_refs=dangling,
        secret_refs=profile.secret_refs,
    )
    if dangling:
        diagnostics.errors.append(
            "MCP server(s) not configured: " + ", ".join(dangling)
        )

    # 技能选择报告。 拒绝列表语义：目录减去禁用名称，从不悬空。 安 ACP 该用户没有自己的
    # 拒绝列表 — 它的目录就是部署注入的（除非调用者传递一个）；从不包含项目技能（#4019）
    # 。
    #
    if isinstance(profile, OpenHandsAgentProfile):
        filtered_skills = _profile_skills(profile, available_skills, public_skill_names)
        diagnostics.disabled_skills = profile.disabled_skills
        diagnostics.public_skills = profile.public_skills
        diagnostics.unusable_tools = _unusable_tools(
            profile.tools,
            browser_available=browser_available,
            check_usable=check_usable,
        )
        failing = [n for n in diagnostics.unusable_tools if n != BROWSER_TOOL_NAME]
        if failing:
            diagnostics.errors.append(
                "Tool(s) this server cannot run: " + ", ".join(failing)
            )
    else:
        filtered_skills = _select_skills(available_skills, [])
    diagnostics.resolved_skills = [s.name for s in filtered_skills]

    llm: LLM | None = None
    if isinstance(profile, OpenHandsAgentProfile):
        diagnostics.llm_profile_ref = profile.llm_profile_ref
        try:
            llm = llm_store.load(profile.llm_profile_ref, cipher=cipher)
            diagnostics.llm_profile_resolved = True
            diagnostics.llm_api_key_set = _api_key_set(llm)
        except FileNotFoundError:
            diagnostics.errors.append(
                f"LLM profile {profile.llm_profile_ref!r} not found"
            )
        except Exception as e:
            # 保持干运行总和：商店在自己的处理器运行之前，可以提高 filelock.TimeoutError
            #  (锁冲突)，OSError，或验证错误。 将这些作为诊断而不是使编辑器预览崩溃（#
            # 3719）——与上面明确缺失的配置文件不同。
            #
            diagnostics.errors.append(
                f"Could not load LLM profile {profile.llm_profile_ref!r}: {e}"
            )
    else:
        (
            diagnostics.acp_api_key_secret_name,
            diagnostics.acp_base_url_secret_name,
            diagnostics.acp_file_secret_names,
        ) = _acp_credential_channels(profile.acp_server)

    diagnostics.valid = not diagnostics.errors
    if diagnostics.valid:
        # 对于通过配置文件验证 (e.g. 带有不平衡 shell 引号的 acp_command，shlex.split 拒
        # 绝）。 保持空运行总数：将诸如诊断之类的故障暴露出来，而不是提高，以匹配API合同
        # 。
        #
        try:
            if isinstance(profile, OpenHandsAgentProfile):
                # 这里有效意味着上面的LLM加载成功； 显式地设置门而不是通过断言（在
                # Python -O 下剥离）。
                #
                if llm is None:
                    raise RuntimeError(
                        "OpenHands profile marked valid without a resolved LLM"
                    )
                settings = _build_openhands_settings(
                    profile,
                    llm,
                    filtered_mcp,
                    filtered_skills,
                    browser_available=browser_available,
                    critic_api_key=critic_api_key,
                )
            else:
                settings = _build_acp_settings(profile, filtered_mcp, filtered_skills)
            # 不暴露上下文 => 机密已脱敏 (MCP env/headers, llm api_key)。
            diagnostics.resolved_settings = settings.model_dump(mode="json")
        except Exception as e:
            diagnostics.valid = False
            diagnostics.errors.append(f"Failed to build agent settings: {e}")

    return diagnostics
