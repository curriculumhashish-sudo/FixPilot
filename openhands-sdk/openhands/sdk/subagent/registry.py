"""
简单API供用户注册自定义智能体。

用法示例：
    from openhands.sdk import register_agent, Agent, AgentContext
    from openhands.sdk.tool.spec import Tool

    # 定义自定义安全专家工厂
    def create_security_expert(llm):
        tools = [Tool(name="TerminalTool")]
        agent_context = AgentContext(
            system_message_suffix=(
                “你是一名网络安全专家。 始终考虑安全影响。”
            ),
        )
        return Agent(llm=llm, tools=tools, agent_context=agent_context)

    # 使用简单描述进行注册（仅限本地，无远程元数据）
    register_agent(
        name="security_expert",
        factory_func=create_security_expert,
        description="Expert in security analysis and vulnerability assessment",
    )
"""

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, NamedTuple

from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.logger import get_logger
from openhands.sdk.subagent.load import (
    load_project_agents,
    load_user_agents,
)
from openhands.sdk.subagent.schema import AgentDefinition
from openhands.sdk.utils.deprecation import warn_deprecated


if TYPE_CHECKING:
    from openhands.sdk.agent.agent import Agent
    from openhands.sdk.llm.llm import LLM

logger = get_logger(__name__)


class AgentFactory(NamedTuple):
    """智能体工厂函数及其定义的容器。"""

    factory_func: Callable[["LLM"], "Agent"]
    definition: AgentDefinition


# 全局注册表用于用户注册的智能体工厂
_agent_factories: dict[str, AgentFactory] = {}
_registry_lock = RLock()


def _resolve_agent_definition(
    name: str,
    description: str | AgentDefinition,
) -> AgentDefinition:
    """构建或规范化 `AgentDefinition` 以进行注册。

    当描述是纯字符串时，将创建最小定义
    from name and description.  When it is already an
    `AgentDefinition` 按原样返回。

    Args:
        name: 智能体名称用作注册表键。
        description: 人类可读的描述字符串（最小
            `AgentDefinition` 将被创建）或完整
            `AgentDefinition` 实例。

    Returns:
        `AgentDefinition` 已准备好存储。
    """
    if isinstance(description, AgentDefinition):
        return description
    return AgentDefinition(name=name, description=description)


def register_agent(
    name: str,
    factory_func: Callable[["LLM"], "Agent"],
    description: str | AgentDefinition,
) -> None:
    """全局注册自定义智能体。

    factory_func 是本地执行的真实来源 - 它接收 `LLM` 并且必须返回完全配置的 `Agent`。

    描述参数接受纯字符串或完整字符串
    `AgentDefinition`. 普通字符串创建最小定义
    from name and description; this is fine for local-only agents but
    意味着远程服务器将不知道工具或系统提示词。 当智能体需要在远程工作区中工作时，传递
     `AgentDefinition`。定义的元数据（工具、
    system_prompt、模型、技能等）会被序列化并转发到智能体-服务器。

    Args:
        name: 智能体的唯一名称（用作注册表键）。
        factory_func: 接受 LLM 并返回智能体的函数。
        description: 人类可读的描述字符串，或完整的
            `AgentDefinition` 携带工具、system_prompt 模型和其它远程执行所需的元数据
            。

    Raises:
        ValueError: 如果同名的智能体已存在。
    """
    definition = _resolve_agent_definition(name, description)

    with _registry_lock:
        if name in _agent_factories:
            raise ValueError(f"Agent '{name}' already registered")

        _agent_factories[name] = AgentFactory(
            factory_func=factory_func, definition=definition
        )


def register_agent_if_absent(
    name: str,
    factory_func: Callable[["LLM"], "Agent"],
    description: str | AgentDefinition,
) -> bool:
    """如果尚不存在具有该名称的智能体，请注册自定义智能体。

    行为与 `register_agent` 相同，只是当具有 *name* 的智能体已注册时，它会静默无操作
    ，而不是引发 `ValueError`。 基于文件和基于插
    件的智能体加载使用它来优雅地跳过与以编程方式注册的智能体的冲突。

    有关完整参数文档，请参阅 `register_agent`。

    Returns:
        `True`（如果智能体已注册）；`False`（如果具有该名称的智能体已存在）。
    """
    definition = _resolve_agent_definition(name, description)

    with _registry_lock:
        if name in _agent_factories:
            return False

        _agent_factories[name] = AgentFactory(
            factory_func=factory_func, definition=definition
        )
        return True


@lru_cache(maxsize=32)
def _get_profile_store(profile_store_dir: str | None) -> LLMProfileStore:
    return LLMProfileStore(profile_store_dir)


def agent_definition_to_factory(
    agent_def: AgentDefinition,
    work_dir: str | Path | None = None,
) -> Callable[["LLM"], "Agent"]:
    """从 `AgentDefinition` 创建一个智能体工厂闭包。

    返回的可调用对象接受父级智能体的 LLM 并生成完全配置的 `Agent`。

    - `agent_def.tools` 中的工具名称映射到 `Tool` 对象。
    - `agent_def.skills` 中的技能名称解析为 `Skill` 对象
      from project and user skill directories (project takes priority).
    - 系统提示词被设置为 `system_message_suffix` 在
      `AgentContext`.
    - `model: inherit` 保留父级 LLM； 明确的模型名称通过 `model_copy(update=...)` 创
    建一个副本。

    Note: 来电者 (e.g. TaskManager) 负责
    禁用流式传输并重置结果智能体的 LLM 的指标。

    Args:
        agent_def: 要转换的智能体定义。
        work_dir: 用于解析技能名称的项目目录。 如果None，
            仅搜索用户级别的技能。

    Raises:
        ValueError: 如果找不到工具或技能。
    """
    # 在工厂创建时急切地解决技能问题。
    # 优先级：项目技能优先于用户技能（由 load_available_skills 处理）。
    resolved_skills: list = []
    if agent_def.skills:
        from openhands.sdk.skills import load_available_skills

        available = load_available_skills(
            work_dir, include_user=True, include_project=True, include_public=False
        )

        for name in agent_def.skills:
            if name not in available:
                raise ValueError(
                    f"Skill '{name}' not found but was given to agent "
                    f"'{agent_def.name}'."
                )
            resolved_skills.append(available[name])

    def _factory(llm: "LLM") -> "Agent":
        from openhands.sdk.agent.agent import Agent
        from openhands.sdk.context.agent_context import AgentContext
        from openhands.sdk.context.condenser import (
            LLMSummarizingCondenser,
            default_condenser,
        )
        from openhands.sdk.tool.registry import list_registered_tools
        from openhands.sdk.tool.spec import Tool

        # 如果 agent_def.model 不同于“继承”且为空字符串，则加载 LLM 配置文件
        #
        if agent_def.model and agent_def.model != "inherit":
            store = _get_profile_store(agent_def.profile_store_dir)
            available_profiles = [name.removesuffix(".json") for name in store.list()]
            profile_name = agent_def.model.removesuffix(".json")
            if profile_name not in available_profiles:
                raise ValueError(
                    f"Profile {agent_def.model} not found in profile store.\n"
                    f"Available profiles: {available_profiles}"
                )

            llm = store.load(profile_name)

        # 子智能体的系统提示词被添加为主系统提示词的后缀
        #
        has_context = agent_def.system_prompt or resolved_skills
        agent_context = (
            AgentContext(
                system_message_suffix=agent_def.system_prompt or None,
                skills=resolved_skills,
            )
            if has_context
            else None
        )

        # 解决工具
        tools: list[Tool] = []
        registered_tools: set[str] = set(list_registered_tools())
        for tool_name in agent_def.tools:
            if tool_name not in registered_tools:
                raise ValueError(
                    f"Tool '{tool_name}' not registered"
                    f"but was given to agent {agent_def.name}."
                )
            tools.append(Tool(name=tool_name))

        # 子智能体默认情况下得到一个总结上下文压缩器（与顶级智能体相同），因此深度运行自
        # 动压缩，而不是在上下文溢出时出错。 上下文压缩器 LLM 需要一个不同的 usage_id 或
        # 其 token 从对话统计数据中删除重复数据。 NoOpCondenser 禁用上下文压缩。
        #
        if agent_def.condenser is not None:
            condenser = agent_def.condenser
            if isinstance(condenser, LLMSummarizingCondenser):
                # 每 spawn 时刷新：LLM 有其自身的指标（因此子智能体不会共享/重复计费上下
                # 文压缩器成本）；usage_id 与智能体's 不同，否则 token 的重复会被删除。
                #
                cond_llm = condenser.llm
                usage_id = (
                    cond_llm.usage_id
                    if cond_llm.usage_id != llm.usage_id
                    else "condenser"
                )
                fresh_llm = cond_llm.model_copy(update={"usage_id": usage_id})
                fresh_llm.reset_metrics()
                condenser = condenser.model_copy(update={"llm": fresh_llm})
        else:
            condenser = default_condenser(
                llm.model_copy(update={"usage_id": "condenser"})
            )

        return Agent(
            llm=llm,
            tools=tools,
            agent_context=agent_context,
            mcp_config=agent_def.mcp_config or {},
            condenser=condenser,
        )

    return _factory


def register_file_agents(work_dir: str | Path) -> list[str]:
    """从项目级 `.agents/agents` 加载并注册基于文件的智能体和
    `.openhands/agents` 以及用户级 `~/.agents/agents` 和 `~/.openhands/agents` 目录。

    项目级定义优先于用户级定义，并且在每个级别内 `.agents/` 优先于 `.openhands/`。

    不会覆盖已通过编程或插件注册的智能体。

    Returns:
        实际注册的智能体个名称列表。
    """
    project_agents = load_project_agents(work_dir)
    user_agents = load_user_agents()

    # 重复数据删除：项目赢得用户
    seen_names: set[str] = set()
    deduplicated: list[AgentDefinition] = []

    for agent_def in project_agents:
        if agent_def.name not in seen_names:
            seen_names.add(agent_def.name)
            deduplicated.append(agent_def)

    for agent_def in user_agents:
        if agent_def.name not in seen_names:
            seen_names.add(agent_def.name)
            deduplicated.append(agent_def)

    registered: list[str] = []
    for agent_def in deduplicated:
        if _register_definition(agent_def, work_dir, kind="file-based"):
            registered.append(agent_def.name)

    return registered


def _register_definition(
    agent_def: AgentDefinition,
    work_dir: str | Path | None,
    kind: str,
) -> bool:
    """注册一个智能体定义； 如果无效则跳过并发出警告。

    一个无法转换为工厂的定义（例如，一个命名了一个不存在的技能）会被跳过，以防止它破
    坏加载它或其旁边注册的其他智能体对话。
    """
    source = f" from {agent_def.source}" if agent_def.source else ""
    try:
        factory = agent_definition_to_factory(agent_def, work_dir=work_dir)
    except ValueError as e:
        logger.warning(f"Skipping {kind} agent '{agent_def.name}'{source}: {e}")
        return False
    was_registered = register_agent_if_absent(
        name=agent_def.name,
        factory_func=factory,
        description=agent_def,
    )
    if was_registered:
        logger.info(f"Registered {kind} agent '{agent_def.name}'{source}")
    return was_registered


def register_plugin_agents(
    agents: list[AgentDefinition],
    work_dir: str | Path | None = None,
) -> list[str]:
    """将插件提供的智能体定义注册到委托注册表中。

    插件智能体的优先级高于基于文件的智能体，但低于编程 ``register_agent()`` 调用。 该
    功能桥接了现有的
    ``Plugin.agents`` 列表（已加载但当前未注册）到委托注册表中。

    Args:
        agents: 智能体从加载的插件收集的定义。
        work_dir: 智能体中技能名称的解决项目目录
            定义。 如果 None，则仅搜索用户级技能。

    Returns:
        实际注册的智能体个名称列表。
    """
    registered: list[str] = []
    for agent_def in agents:
        if _register_definition(agent_def, work_dir, kind="plugin"):
            registered.append(agent_def.name)

    return registered


def get_agent_factory(name: str | None) -> AgentFactory:
    """
    按名称获取已注册的智能体工厂。

    Args:
        name: 要检索的智能体工厂的名称。 如果 None、空或“默认”，
            返回默认的智能体工厂。

    Returns:
        AgentFactory: 工厂功能及定义

    Raises:
        ValueError: 如果未找到具有给定名称的智能体工厂
    """
    # 将向后兼容性的旧名称映射到新名称
    _DEPRECATED_NAMES = {
        "default": "general-purpose",
        "default cli mode": "general-purpose",
        "explore": "code-explorer",
        "bash": "bash-runner",
    }

    if name in _DEPRECATED_NAMES:
        new_name = _DEPRECATED_NAMES[name]
        warn_deprecated(
            f"Agent name '{name}'",
            deprecated_in="1.12.0",
            removed_in="2.0.0",
            details=f"Use '{new_name}' instead.",
        )
        factory_name = new_name
    else:
        factory_name = "general-purpose" if not name else name

    with _registry_lock:
        factory = _agent_factories.get(factory_name)
        available = sorted(_agent_factories.keys())

    if factory is None:
        available_list = ", ".join(available) if available else "none registered"
        raise ValueError(
            f"Unknown agent '{name}'. Available types: {available_list}. "
            "Use register_agent() to add custom agent types."
        )

    return factory


def get_factory_info(
    include: Callable[[AgentDefinition], bool] | None = None,
) -> str:
    """获取有关可用智能体工厂的格式化信息。"""
    with _registry_lock:
        user_factories = {
            name: factory
            for name, factory in _agent_factories.items()
            if include is None or include(factory.definition)
        }

    if not user_factories:
        return "- No user-registered agents yet. Call register_agent(...) to add custom agents."  # noqa: E501

    def get_agent_info(name, factory):
        defn = factory.definition
        tools = f" (tools: {', '.join(defn.tools)})" if defn.tools else ""
        return f"- **{name}**: {defn.description}{tools}"

    return "\n".join(
        get_agent_info(name, f) for name, f in sorted(user_factories.items())
    )


def get_registered_agent_definitions() -> list[AgentDefinition]:
    """返回所有已注册的智能体的定义。

    用于将智能体元数据转发到远程智能体服务器。
    """
    with _registry_lock:
        return [f.definition for f in _agent_factories.values()]


def _reset_registry_for_tests() -> None:
    """清除测试的注册表以避免交叉测试污染。"""
    with _registry_lock:
        _agent_factories.clear()
