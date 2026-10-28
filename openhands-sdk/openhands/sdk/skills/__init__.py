"""OpenHands SDK 的技能管理。

该模块提供了统一的API来使用技能：

**核心技能模型及加载：**
- `Skill` - 技能数据模型
- `SkillResources` - 技能的资源目录（scripts/、references/、assets/）
- `load_skills_from_dir` - 从目录加载技能
- `load_project_skills` - 从项目的 .agents/skills/ 加载技能
- `load_user_skills` - 从 ~/.openhands/skills/ 加载技能
- `load_public_skills` - 从公共 OpenHands 扩展存储库加载技能
- `load_available_skills` - 从多个来源加载和合并技能
- `merge_skills_by_name` - 按名称合并两个技能集合（主要获胜）

**触发器：**
- `BaseTrigger`、`KeywordTrigger`、`TaskTrigger`、`PathTrigger` - 激活触发器

**已安装的技能管理：**
- `install_skill` - 从源安装技能
- `uninstall_skill` - 卸载技能
- `list_installed_skills` - 列出所有已安装的技能
- `load_installed_skills` - 加载已启用的已安装技能
- `enable_skill`、`disable_skill` - 切换技能启用状态
- `update_skill` - 更新已安装的技能

**类型：**
- `SkillKnowledge` - 代表来自触发技能的知识
- `InputMetadata` - 任务技能输入的元数据

**公用事业：**
- `discover_skill_resources` - 发现技能中的资源目录
- `validate_skill_name` - 根据 AgentSkills 规范验证技能名称
- `to_prompt` - 生成可用技能的 XML 提示词块
"""

# 例外情况
from openhands.sdk.skills.exceptions import SkillError, SkillValidationError

# 获取实用程序
from openhands.sdk.skills.fetch import SkillFetchError, fetch_skill_with_resolution

# 已安装技能管理
from openhands.sdk.skills.installed import (
    InstalledSkillInfo,
    disable_skill,
    enable_skill,
    get_installed_skill,
    get_installed_skills_dir,
    install_skill,
    install_skills_from_marketplace,
    list_installed_skills,
    load_installed_skills,
    load_marketplace_standalone_skills,
    uninstall_skill,
    update_skill,
)

# 核心技能模型及加载
from openhands.sdk.skills.skill import (
    Skill,
    SkillInfo,
    SkillResources,
    load_available_skills,
    load_project_skills,
    load_public_skills,
    load_skills_from_dir,
    load_user_skills,
    merge_skills_by_name,
    to_prompt,
)

# 触发器
from openhands.sdk.skills.trigger import (
    BaseTrigger,
    KeywordTrigger,
    PathTrigger,
    TaskTrigger,
)

# 类型
from openhands.sdk.skills.types import (
    InputMetadata,
    SkillContentResponse,
    SkillKnowledge,
    SkillResponse,
)

# 公用事业
from openhands.sdk.skills.utils import (
    RESOURCE_DIRECTORIES,
    discover_skill_resources,
    validate_skill_name,
)


__all__ = [
    # 例外情况
    "SkillError",
    "SkillValidationError",
    # 获取
    "SkillFetchError",
    "fetch_skill_with_resolution",
    # 已安装技能管理
    "InstalledSkillInfo",
    "install_skill",
    "install_skills_from_marketplace",
    "load_marketplace_standalone_skills",
    "uninstall_skill",
    "list_installed_skills",
    "load_installed_skills",
    "get_installed_skills_dir",
    "get_installed_skill",
    "enable_skill",
    "disable_skill",
    "update_skill",
    # 核心技能模型及加载
    "Skill",
    "SkillInfo",
    "SkillResources",
    "load_skills_from_dir",
    "load_project_skills",
    "load_user_skills",
    "load_public_skills",
    "load_available_skills",
    "merge_skills_by_name",
    "to_prompt",
    # 触发器
    "BaseTrigger",
    "KeywordTrigger",
    "PathTrigger",
    "TaskTrigger",
    # 类型
    "SkillKnowledge",
    "InputMetadata",
    "SkillResponse",
    "SkillContentResponse",
    # 公用事业
    "discover_skill_resources",
    "RESOURCE_DIRECTORIES",
    "validate_skill_name",
]
