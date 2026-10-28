"""模式用于基于 Markdown 的智能体定义文件。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

import frontmatter
from pydantic import BaseModel, Field

from openhands.sdk.context.condenser import CondenserBase, NoOpCondenser
from openhands.sdk.hooks.config import HookConfig
from openhands.sdk.mcp.config import MCPServer, coerce_mcp_config
from openhands.sdk.utils.path import to_posix_path


if TYPE_CHECKING:
    from openhands.sdk.security.confirmation_policy import ConfirmationPolicyBase


# 发现智能体的范围。 在发现过程中设置，而不是从前置元数据中设置。
AgentDefinitionLevel = Literal["project", "user", "builtin", "plugin", "programmatic"]


KNOWN_FIELDS: Final[set[str]] = {
    "name",
    "description",
    "model",
    "color",
    "tools",
    "skills",
    "max_iteration_per_run",
    "max_budget_per_run",
    "hooks",
    "profile_store_dir",
    "mcp_config",
    "mcp_servers",
    "permission_mode",
    "condenser",
}

_VALID_PERMISSION_MODES: Final[set[str]] = {
    "always_confirm",
    "never_confirm",
    "confirm_risky",
}


def _extract_color(fm: dict[str, object]) -> str | None:
    """从前置元数据中提取颜色。"""
    color_raw = fm.get("color")
    color: str | None = str(color_raw) if color_raw is not None else None
    return color


def _extract_tools(fm: dict[str, object]) -> list[str]:
    """从前置元数据中提取工具。"""
    tools_raw = fm.get("tools", [])

    # 确保工具是字符串列表
    tools: list[str]
    if isinstance(tools_raw, str):
        tools = [tools_raw]
    elif isinstance(tools_raw, list):
        tools = [str(t) for t in tools_raw]
    else:
        tools = []
    return tools


def _extract_skills(fm: dict[str, object]) -> list[str]:
    """从前置元数据中提取技能名称。"""
    skills_raw = fm.get("skills", [])
    skills: list[str]
    if isinstance(skills_raw, str):
        skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
    elif isinstance(skills_raw, list):
        skills = [str(s) for s in skills_raw]
    else:
        skills = []
    return skills


def _extract_mcp_config(fm: dict[str, object]) -> dict[str, MCPServer] | None:
    """从前置元数据中提取 MCP 个服务器。

    当智能体运行时，变量占位符（``${VAR}`` 和 ``${VAR:-default}``）会被保留并在稍后扩
    展，从而允许在运行时注入每个会话机密。 当处理智能体
    的 mcp_config 时，扩展发生在 LocalConversation 中。

    Note: 不支持旧的 ``$VAR`` 语法（不带大括号）。
    使用 ``${VAR}`` 作为环境变量和机密。
    """
    mcp_config_raw = fm.get("mcp_config", fm.get("mcp_servers"))
    if mcp_config_raw is None:
        return None
    if not isinstance(mcp_config_raw, dict):
        raise ValueError(
            f"mcp_config must be a mapping of server names to configs, "
            f"got {type(mcp_config_raw)}"
        )
    return coerce_mcp_config(mcp_config_raw)


def _extract_profile_store_dir(fm: dict[str, object]) -> str | None:
    """从前置元数据中提取配置文件存储目录。"""
    profile_store_dir_raw = fm.get("profile_store_dir")
    if profile_store_dir_raw is None:
        return None
    if isinstance(profile_store_dir_raw, str):
        return profile_store_dir_raw
    raise ValueError(
        f"profile_store_dir must be a scalar value, got {type(profile_store_dir_raw)}"
    )


def _extract_examples(description: str) -> list[str]:
    """从智能体触发的描述中提取 <example> 标签。"""
    pattern = r"<example>(.*?)</example>"
    matches = re.findall(pattern, description, re.DOTALL | re.IGNORECASE)
    return [m.strip() for m in matches if m.strip()]


def _extract_permission_mode(fm: dict[str, object]) -> str | None:
    """从前置元数据中提取permission_mode，默认为None（继承父级）。"""
    raw = fm.get("permission_mode")
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if value not in _VALID_PERMISSION_MODES:
        raise ValueError(
            f"Invalid permission_mode '{raw}'. "
            f"Must be one of: {', '.join(sorted(_VALID_PERMISSION_MODES))}"
        )
    return value


def _extract_max_iteration_per_run(fm: dict[str, object]) -> int | None:
    """从前置元数据文件中提取每次运行的最大迭代次数。"""
    max_iter_raw = fm.get("max_iteration_per_run")
    if isinstance(max_iter_raw, str):
        return int(max_iter_raw)
    if isinstance(max_iter_raw, int):
        return max_iter_raw
    return None


def _extract_max_budget_per_run(fm: dict[str, object]) -> float | None:
    """从前置元数据文件中提取每次运行成本预算 (USD)。"""
    raw = fm.get("max_budget_per_run")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        return float(raw)
    return None


def _extract_hooks(fm: dict[str, object]) -> HookConfig | None:
    # 解析钩子配置
    hooks_raw = fm.get("hooks")
    hooks: HookConfig | None = None
    if hooks_raw is not None and isinstance(hooks_raw, dict):
        hooks = HookConfig.model_validate(hooks_raw)
    return hooks


def _extract_condenser(fm: dict[str, Any]) -> CondenserBase | None:
    """从前置元数据中提取上下文压缩器配置。

    不存在/“默认”/None -> None（出厂时应用默认汇总上下文压缩器）。 'None'/'off'/false
     -> NoOpCondenser（禁用上下文压
    缩）。 映射 -> 针对可区分联合进行验证的完整上下文压缩器规范。
    """
    raw = fm.get("condenser")
    if raw is None or isinstance(raw, CondenserBase):
        return raw
    if isinstance(raw, bool):
        return None if raw else NoOpCondenser()
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in ("", "default", "inherit"):
            return None
        if value in ("none", "off", "false", "no", "disable", "disabled"):
            return NoOpCondenser()
        raise ValueError(
            f"Invalid condenser value: {raw!r}. Use 'default', 'none', "
            "or a mapping with a condenser config."
        )
    if isinstance(raw, dict):
        return CondenserBase.model_validate(raw)
    raise ValueError(f"Invalid condenser value: {raw!r}")


class AgentDefinition(BaseModel):
    """从 Markdown 文件加载智能体定义。

    智能体是可以根据用户输入模式触发的专用配置。 他们定义自定义系统提示词和工具访问。
    """

    name: str = Field(description="Agent name (from frontmatter or filename)")
    description: str = Field(default="", description="Agent description")
    model: str = Field(
        default="inherit", description="Model to use ('inherit' uses parent model)"
    )
    color: str | None = Field(default=None, description="Display color for the agent")
    tools: list[str] = Field(
        default_factory=list, description="List of allowed tools for this agent"
    )
    skills: list[str] = Field(
        default_factory=list,
        description="List of skill names for this agent. "
        "Resolved from project/user directories.",
    )
    system_prompt: str = Field(default="", description="System prompt content")
    source: str | None = Field(
        default=None, description="Source file path for this agent"
    )
    level: AgentDefinitionLevel | None = Field(
        default=None,
        description="Scope where the agent was discovered. "
        "Set during discovery; None when loaded directly from a file.",
    )
    when_to_use_examples: list[str] = Field(
        default_factory=list,
        description="Examples of when to use this agent (for triggering)",
    )
    hooks: HookConfig | None = Field(
        default=None, description="Hook configuration for this agent"
    )
    permission_mode: str | None = Field(
        default=None,
        description="How the subagent handles permissions. "
        "None inherits the parent policy, 'always_confirm' requires "
        "confirmation for every action, 'never_confirm' skips all confirmations, "
        "'confirm_risky' only confirms actions above a risk threshold.",
    )
    max_iteration_per_run: int | None = Field(
        default=None,
        description="Maximum iterations per run. "
        "It must be strictly positive, or None for default.",
        gt=0,
    )
    max_budget_per_run: float | None = Field(
        default=None,
        description="Maximum accumulated cost (USD) per run for this sub-agent. "
        "Must be strictly positive, or None for no budget.",
        gt=0,
    )
    mcp_config: dict[str, MCPServer] | None = Field(
        default=None,
        description=(
            "MCP servers for this agent. Ignored when it runs as a delegated "
            "sub-agent, which always inherits its parent's MCP servers."
        ),
        examples=[
            {
                "fetch": {
                    "command": "uvx",
                    "args": [
                        "--with",
                        "mcp==1.29.0",
                        "mcp-server-fetch==2026.7.10",
                    ],
                }
            }
        ],
    )
    profile_store_dir: str | None = Field(
        default=None,
        description="Path to the directory where LLM profiles are stored. "
        "If None, the default profile store directory is used.",
    )
    condenser: CondenserBase | None = Field(
        default=None,
        description="Context condenser for the sub-agent. None applies a default "
        "summarizing condenser; set a NoOpCondenser to disable condensation.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata from frontmatter"
    )

    def get_confirmation_policy(self) -> ConfirmationPolicyBase | None:
        """将 permission_mode 转换为 ConfirmationPolicyBase 实例。

        当 permission_mode 为 None 时返回 None（继承父策略）。
        """
        if self.permission_mode is None:
            return None

        match self.permission_mode:
            case "always_confirm":
                from openhands.sdk.security.confirmation_policy import AlwaysConfirm

                return AlwaysConfirm()
            case "never_confirm":
                from openhands.sdk.security.confirmation_policy import NeverConfirm

                return NeverConfirm()
            case "confirm_risky":
                from openhands.sdk.security.confirmation_policy import ConfirmRisky

                return ConfirmRisky()
            case _:
                # 由于 _extract_permission_mode() 中的验证，永远不应该到达这里
                #
                raise AssertionError(
                    f"Unexpected permission_mode: {self.permission_mode}"
                )

    @classmethod
    def load(cls, agent_path: Path) -> AgentDefinition:
        """从Markdown文件加载智能体定义。

        智能体 Markdown 文件的 YAML 前置元数据包含：
        - name: 智能体姓名
        - description: 带有用于触发的可选 <example> 标签的描述
        - tools (optional): 允许的工具列表
        - skills (optional): 以逗号分隔的技能名称或技能名称列表
        - mcp_config (optional): MCP 服务器配置映射
        - model (optional): 要使用的模型配置文件（默认值：“继承”）
        - color (optional): 显示颜色
        - permission_mode (optional): 子智能体如何处理权限（“always_confirm”、“
        never_confirm”、“
        confirm_risky”）。 None 继承父级。
        - max_iterations_per_run: 每次运行的最大迭代次数
        - hooks (optional): 适用钩子列表

        Markdown的主体是系统提示词。

        Args:
            agent_path: 智能体 Markdown 文件的路径。

        Returns:
            已加载 AgentDefinition 实例。
        """
        with open(agent_path, encoding="utf-8") as f:
            post = frontmatter.load(f)

        fm = post.metadata
        content = post.content.strip()

        # 使用正确的类型处理提取前置元数据字段
        name: str = str(fm.get("name", agent_path.stem))
        description: str = str(fm.get("description", ""))
        model: str = str(fm.get("model", "inherit"))
        color: str | None = _extract_color(fm)
        tools: list[str] = _extract_tools(fm)
        skills: list[str] = _extract_skills(fm)
        permission_mode: str | None = _extract_permission_mode(fm)
        max_iteration_per_run: int | None = _extract_max_iteration_per_run(fm)
        max_budget_per_run: float | None = _extract_max_budget_per_run(fm)
        mcp_config: dict[str, MCPServer] | None = _extract_mcp_config(fm)
        profile_store_dir: str | None = _extract_profile_store_dir(fm)
        hooks: HookConfig | None = _extract_hooks(fm)
        condenser: CondenserBase | None = _extract_condenser(fm)

        # 从描述中提取 whenToUse 个示例
        when_to_use_examples = _extract_examples(description)

        # 从元数据中删除已知字段以获得额外内容
        metadata = {k: v for k, v in fm.items() if k not in KNOWN_FIELDS}

        return cls(
            name=name,
            description=description,
            model=model,
            color=color,
            tools=tools,
            skills=skills,
            permission_mode=permission_mode,
            max_iteration_per_run=max_iteration_per_run,
            max_budget_per_run=max_budget_per_run,
            mcp_config=mcp_config,
            hooks=hooks,
            profile_store_dir=profile_store_dir,
            condenser=condenser,
            system_prompt=content,
            source=to_posix_path(agent_path),
            when_to_use_examples=when_to_use_examples,
            metadata=metadata,
        )
