"""命名为：class:`PromptRegistry` 预设 - 即用型部分合成。

``create_registry()`` 选择同一引擎上的部分组合。 的
``"default"`` 预设以确切的顺序注册静态层部分
``agent/prompts/system_prompt.j2`` 发出它们，因此 ``registry.build(ctx).static`` 再现
``AgentBase.static_system_message``。 ``"planning"`` 预设是一个独特的独立组合（从
``system_prompt_planning.j2`` 移植），省略了默认的 OpenHands 部分。 动态层级部分 **共
享 ** -- repo/skills/s
uffix/secrets/datetime 预设独立 -- 因此，一个智能体规划 ``agent_context``仍然可以获取
其动态块。
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from openhands.sdk.context.prompts.registry import PromptRegistry
from openhands.sdk.context.prompts.section import (
    CacheTier,
    PromptContext,
    PromptSection,
)
from openhands.sdk.context.prompts.sections.dynamic import (
    AvailableSkillsSection,
    CustomSecretsSection,
    CustomSuffixSection,
    DateTimeSection,
    MemoryContextSection,
    RepoContextSection,
)
from openhands.sdk.context.prompts.sections.planning import PlanningSection
from openhands.sdk.context.prompts.sections.static import (
    CodeQualitySection,
    EfficiencySection,
    EnvironmentSetupSection,
    ExternalServicesSection,
    FileSystemSection,
    MemorySection,
    ModelSpecificSection,
    PersonaSection,
    ProblemSolvingSection,
    ProcessManagementSection,
    PullRequestsSection,
    RoleSection,
    SecurityRiskAssessmentSection,
    SecuritySection,
    SelfDocumentationSection,
    SoulSection,
    ToolGuidanceSection,
    TroubleshootingSection,
    VersionControlSection,
)


__all__ = ["PromptPreset", "create_registry"]


class PromptPreset(StrEnum):
    """命名：func:`create_registry` 节组合。"""

    DEFAULT = "default"
    PLANNING = "planning"


@dataclass(frozen=True, slots=True)
class _ReplacedByPersona:
    """角色层部分：当智能体提供自己的角色时被删除。"""

    section: PromptSection
    name: str = field(init=False)
    cache_tier: CacheTier = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.section.name)
        object.__setattr__(self, "cache_tier", self.section.cache_tier)

    def guard(self, ctx: PromptContext) -> bool:
        return ctx.persona is None and self.section.guard(ctx)

    def render(self, ctx: PromptContext) -> str | None:
        return self.section.render(ctx)


_DEFAULT_STATIC_SECTIONS: Final[tuple[PromptSection, ...]] = (
    PersonaSection(),  # guard: persona set
    _ReplacedByPersona(SoulSection()),
    _ReplacedByPersona(RoleSection()),
    MemorySection(),
    _ReplacedByPersona(EfficiencySection()),
    _ReplacedByPersona(FileSystemSection()),
    _ReplacedByPersona(CodeQualitySection()),
    _ReplacedByPersona(VersionControlSection()),
    _ReplacedByPersona(PullRequestsSection()),
    _ReplacedByPersona(ProblemSolvingSection()),
    _ReplacedByPersona(SelfDocumentationSection()),
    SecuritySection(),  # 守卫：security_policy_filename设置
    SecurityRiskAssessmentSection(),  # 守卫：llm_security_analyzer
    ToolGuidanceSection(),  # 守卫：装载工具供应prompt_guidance
    ExternalServicesSection(),
    _ReplacedByPersona(EnvironmentSetupSection()),
    _ReplacedByPersona(TroubleshootingSection()),
    ProcessManagementSection(),
    ModelSpecificSection(),  # 守卫：model_family已解决
)
_PLANNING_STATIC_SECTIONS: Final[tuple[PromptSection, ...]] = (
    PersonaSection(),
    PlanningSection(),
)

_DYNAMIC_SECTIONS: Final[tuple[PromptSection, ...]] = (
    RepoContextSection(),  # 守卫：存在门控回购技能
    MemoryContextSection(),  # 守卫：已解决的内存存在
    AvailableSkillsSection(),  # 守卫：available_skills_prompt
    CustomSuffixSection(),  # 守卫：system_message_suffix
    CustomSecretsSection(),  # 守卫：secret_infos 存在
    # DateTimeSection 故意放在最后：它是唯一的每个会话易失值，因此稳定的动态内容仍然是缓
    # 存友好的前缀。
    #
    DateTimeSection(),
)


def create_registry(preset: PromptPreset = PromptPreset.DEFAULT) -> PromptRegistry:
    """为 ``preset`` 构建部分注册表。

    ``DEFAULT``为标准OpenHands成分； ``PLANNING`` 是只读分析成分（无 ``<SECURITY>``
    /``<SOUL>``/``
    <MEMORY>`` ...）。 两者共享动态层。 部分是无状态的，因此每个预设序列可以在调用之
    间重复使用。
    """
    match preset:
        case PromptPreset.PLANNING:
            static_sections = _PLANNING_STATIC_SECTIONS
        case PromptPreset.DEFAULT:
            static_sections = _DEFAULT_STATIC_SECTIONS
        case _:
            raise ValueError(f"Unknown prompt preset: {preset!r}")

    r = PromptRegistry()
    for section in (*static_sections, *_DYNAMIC_SECTIONS):
        r.register(section)
    return r
