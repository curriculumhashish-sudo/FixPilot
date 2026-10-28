import io
import json
import os
import re
import threading
import time
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, ClassVar, Final, Literal, Union
from xml.sax.saxutils import escape as xml_escape

import frontmatter
import yaml
from pydantic import (
    BaseModel,
    Field,
    SerializationInfo,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.config import MCPServer, coerce_mcp_config, dump_mcp_config
from openhands.sdk.skills.exceptions import SkillError, SkillValidationError
from openhands.sdk.skills.execute import render_content_with_commands
from openhands.sdk.skills.trigger import (
    KeywordTrigger,
    PathTrigger,
    TaskTrigger,
)
from openhands.sdk.skills.types import InputMetadata
from openhands.sdk.skills.utils import (
    discover_skill_resources,
    find_mcp_config,
    find_nested_third_party_files,
    find_regular_md_files,
    find_skill_md_directories,
    find_third_party_files,
    get_skills_cache_dir,
    is_skills_repo_pinned,
    load_and_categorize,
    load_mcp_config,
    update_skills_repository,
    validate_skill_name,
)
from openhands.sdk.utils import DEFAULT_TRUNCATE_NOTICE, maybe_truncate
from openhands.sdk.utils.path import get_user_persistence_dir, to_posix_path


logger = get_logger(__name__)


# 每场比赛一球 token； 最长的运算符优先，因此 `**/` 和 `**` 击败 `*`。
_GLOB_TOKENS: Final[re.Pattern[str]] = re.compile(r"\*\*/|\*\*|\*|\?|[^*?]+")
_GLOB_TO_REGEX: Final[dict[str, str]] = {
    "**/": "(?:.*/)?",  # 任意数量的引导路径段（包括零）
    "**": ".*",  # 任何内容，跨越 `/` 分隔符
    "*": "[^/]*",  # 单个段内的任何运行
    "?": "[^/]",  # 单个非分隔符
}


@lru_cache(maxsize=512)
def _compile_path_glob(pattern: str) -> re.Pattern[str]:
    """将 gitignore 风格的路径 glob 编译为锚定的正则表达式。

    支持的语法（与 POSIX 路径匹配）：
    - ``**`` 匹配任意数量的路径段（包括零）。
    - ``*`` 匹配单个段内的任何字符串。
    - ``?`` 匹配单个非分隔符。
    - 不带 ``/`` 的模式与任意深度的基本名称 e.g 匹配。
      ``*.py`` 的行为类似于 ``**/*.py``（gitignore 语义）。

    匹配区分大小写。 结果按模式字符串进行缓存。
    """
    # 无斜线模式在任何深度都匹配。
    if "/" not in pattern:
        pattern = "**/" + pattern
    tokens: list[str] = _GLOB_TOKENS.findall(pattern)
    body = "".join(_GLOB_TO_REGEX.get(t, re.escape(t)) for t in tokens)
    return re.compile(f"(?s:{body})\\Z")


def path_matches_glob(file_path: str, pattern: str) -> bool:
    """如果 ``file_path`` 与 gitignore 样式的 glob ``pattern`` 匹配，则返回 True。

    ``file_path`` 预计是 POSIX 路径（通常是工作区相关路径）。
    """
    if not pattern:
        return False
    return _compile_path_glob(pattern).fullmatch(file_path) is not None


class SkillInfo(BaseModel):
    """技能基本信息的轻量级表示。

    此类为技能元数据提供标准化、可序列化的格式，可在系统的不同组件中使用。
    """

    name: str
    type: Literal["repo", "knowledge", "agentskills"]
    content: str
    triggers: list[str] = Field(default_factory=list)
    source: str | None = None
    description: str | None = None
    is_agentskills_format: bool = False
    disable_model_invocation: bool = False


class SkillResources(BaseModel):
    """技能的资源目录（AgentSkills 标准）。

    根据 AgentSkills 规范，技能可以包括：
    - scripts/: 智能体可以运行的可执行脚本
    - References/：参考文档和示例
    - asset/：静态资产（图像、数据文件等）
    """

    skill_root: str = Field(description="Root directory of the skill (absolute path)")
    scripts: list[str] = Field(
        default_factory=list,
        description="List of script files in scripts/ directory (relative paths)",
    )
    references: list[str] = Field(
        default_factory=list,
        description="List of reference files in references/ directory (relative paths)",
    )
    assets: list[str] = Field(
        default_factory=list,
        description="List of asset files in assets/ directory (relative paths)",
    )

    def has_resources(self) -> bool:
        """检查是否有可用资源。"""
        return bool(self.scripts or self.references or self.assets)

    def get_scripts_dir(self) -> Path | None:
        """获取脚本目录路径（如果存在）。"""
        scripts_dir = Path(self.skill_root) / "scripts"
        return scripts_dir if scripts_dir.is_dir() else None

    def get_references_dir(self) -> Path | None:
        """获取引用目录路径（如果存在）。"""
        refs_dir = Path(self.skill_root) / "references"
        return refs_dir if refs_dir.is_dir() else None

    def get_assets_dir(self) -> Path | None:
        """获取资产目录路径（如果存在）。"""
        assets_dir = Path(self.skill_root) / "assets"
        return assets_dir if assets_dir.is_dir() else None


# 所有触发器类型的联合类型
TriggerType = Annotated[
    KeywordTrigger | TaskTrigger | PathTrigger,
    Field(discriminator="type"),
]


def _keyword_matches(keyword: str, message_lower: str) -> bool:
    """如果 ``keyword`` 在 ``message_lower`` 中作为整体 token 出现，则返回 True。

    使用数字和字母边界（不包括 ``\\b``），因此 ``git`` 不会触发
    ``github`` 而斜杠前缀的关键字（如 ``/linear``）仍然匹配。
    ``message_lower`` 预计由调用者小写。
    """
    keyword_lower = keyword.lower()
    if not keyword_lower:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(keyword_lower)}(?![a-z0-9])"
    return re.search(pattern, message_lower) is not None


class Skill(BaseModel):
    """技能提供专业知识或功能。

    技能行为取决于格式（is_agentskills_format）和触发器：

    AgentSkills 格式（SKILL.md 个文件）：
    - 始终在 <available_skills> 中列出，并包含名称、描述、位置
    - 智能体按需阅读完整内容（渐进式披露）
    - 如果有触发器：触发时内容会自动注入 ALSO

    旧版 OpenHands 格式：
    - 使用触发器：在 <available_skills> 中列出，在触发器上注入内容
    - 无触发器 (None)：<REPO_CONTEXT> 中的完整内容，始终处于活动状态

    该模型支持 OpenHands 特定字段和 AgentSkills 标准字段 (
    https://agentskills.io/specification ) 以实
    现跨平台兼容性。
    """

    name: str
    content: str
    trigger: TriggerType | None = Field(
        default=None,
        description=(
            "Trigger determines when skill content is auto-injected. "
            "None = no auto-injection (for AgentSkills: agent reads on demand; "
            "for legacy: full content always in system prompt). "
            "KeywordTrigger = auto-inject when keywords appear in user messages. "
            "TaskTrigger = auto-inject for specific tasks, may require user input."
        ),
    )
    source: str | None = Field(
        default=None,
        description=(
            "The source path or identifier of the skill. "
            "When it is None, it is treated as a programmatically defined skill."
        ),
    )
    mcp_tools: dict[str, MCPServer] | None = Field(
        default=None,
        description=("MCP servers for the skill (repo skills only)."),
    )
    inputs: list[InputMetadata] = Field(
        default_factory=list,
        description="Input metadata for the skill (task skills only)",
    )
    is_agentskills_format: bool = Field(
        default=False,
        description=(
            "Whether this skill was loaded from a SKILL.md file following the "
            "AgentSkills standard. AgentSkills-format skills use progressive "
            "disclosure: always listed in <available_skills> with name, "
            "description, and location. If the skill also has triggers, content "
            "is auto-injected when triggered AND agent can read file anytime."
        ),
    )

    # AgentSkills规范：描述必须为1-1024个字符。
    MAX_DESCRIPTION_LENGTH: ClassVar[int] = 1024

    # AgentSkills 标准字段 ( https://agentskills.io/specification )
    version: str = Field(
        default="1.0.0",
        description="Skill version (AgentSkills standard field).",
    )
    description: str | None = Field(
        default=None,
        description=(
            "A brief description of what the skill does and when to use it. "
            "Descriptions exceeding MAX_DESCRIPTION_LENGTH are truncated "
            "with a notice pointing to the skill's source path."
        ),
    )
    license: str | None = Field(
        default=None,
        description=(
            "The license under which the skill is distributed. "
            "AgentSkills standard field (e.g., 'Apache-2.0', 'MIT')."
        ),
    )
    compatibility: str | None = Field(
        default=None,
        description=(
            "Environment requirements or compatibility notes for the skill. "
            "AgentSkills standard field (e.g., 'Requires git and docker')."
        ),
    )
    metadata: dict[str, str] | None = Field(
        default=None,
        description=(
            "Arbitrary key-value metadata for the skill. "
            "AgentSkills standard field for extensibility."
        ),
    )
    allowed_tools: list[str] | None = Field(
        default=None,
        description=(
            "List of pre-approved tools for this skill. "
            "AgentSkills standard field (parsed from space-delimited string)."
        ),
    )
    disable_model_invocation: bool = Field(
        default=False,
        description=(
            "Whether this skill can only be activated by trigger matching and "
            "should not be advertised to the model for direct invocation."
        ),
    )
    resources: SkillResources | None = Field(
        default=None,
        description=(
            "Resource directories for the skill (scripts/, references/, assets/). "
            "AgentSkills standard field. Only populated for SKILL.md directory format."
        ),
    )

    _DESCRIPTION_TRUNCATE_NOTICE = (
        "<response clipped><NOTE>Due to the max output limit, only part of "
        "the full description is shown. You can view the complete skill "
        "content at {source}.</NOTE>"
    )

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def _parse_allowed_tools(cls, v: str | list | None) -> list[str] | None:
        """从空格分隔的字符串或列表中解析 allowed_tools。"""
        if v is None:
            return None
        if isinstance(v, str):
            return v.split()
        if isinstance(v, list):
            return [str(t) for t in v]
        raise SkillValidationError("allowed-tools must be a string or list")

    @field_validator("metadata", mode="before")
    @classmethod
    def _convert_metadata_values(cls, v: dict | None) -> dict[str, str] | None:
        """将元数据值转换为字符串。"""
        if v is None:
            return None
        if isinstance(v, dict):
            return {str(k): str(val) for k, val in v.items()}
        raise SkillValidationError("metadata must be a dictionary")

    @field_validator("mcp_tools", mode="before")
    @classmethod
    def _validate_mcp_tools(
        cls, v: object, info: ValidationInfo
    ) -> dict[str, MCPServer] | None:
        """验证技能 MCP 工具作为本机 MCP 服务器模型。"""
        if v is None:
            return None
        if not isinstance(v, Mapping):
            raise SkillValidationError("mcp_tools must be a dictionary or None")
        try:
            return coerce_mcp_config(v, context=info.context)
        except Exception as e:
            raise SkillValidationError(f"Invalid MCP config dictionary: {e}") from e

    @field_serializer("mcp_tools")
    def _serialize_mcp_tools(
        self, value: dict[str, MCPServer] | None, info: SerializationInfo
    ) -> dict[str, dict[str, Any]] | None:
        if value is None:
            return None
        if not value:
            return {}
        return dump_mcp_config(value, context=info.context or {})

    PATH_TO_THIRD_PARTY_SKILL_NAME: ClassVar[dict[str, str]] = {
        ".cursorrules": "cursorrules",
        "agents.md": "agents",
        "agent.md": "agents",
        "claude.md": "claude",
        "gemini.md": "gemini",
    }

    @classmethod
    def load(
        cls,
        path: str | Path,
        skill_base_dir: Path | None = None,
        strict: bool = True,
        skip_mcp: bool = False,
    ) -> "Skill":
        """使用前置元数据从 Markdown 文件加载技能。

        智能体的名称源自其相对于 skill_base_dir 的路径，或者源自 AgentSkills 样式
        SKILL.md 文件的目录名称。

        支持 OpenHands 特定前置元数据字段和 AgentSkills 标准字段 (
        https://agentskills.io/specification )。

        Args:
            path: 技能文件的路径。
            skill_base_dir: 技能的基本目录（用于派生相对名称）。
            strict: 如果为 True，则强制执行严格的 AgentSkills 名称验证。
                如果为 False，则允许宽松的命名（e.g.，用于插件兼容性）。
            skip_mcp: 如果是 True，则跳过从 .mcp.json 加载 MCP 配置。
                在加载根插件技能时使用，其中 MCP 配置已在插件级别加载以避免双重加载。
        """
        path = Path(path) if isinstance(path, str) else path

        with open(path, encoding="utf-8") as f:
            file_content = f.read()

        if path.name.lower() == "skill.md":
            return cls._load_agentskills_skill(
                path, file_content, strict=strict, skip_mcp=skip_mcp
            )
        else:
            return cls._load_legacy_openhands_skill(path, file_content, skill_base_dir)

    @classmethod
    def _load_agentskills_skill(
        cls, path: Path, file_content: str, strict: bool = True, skip_mcp: bool = False
    ) -> "Skill":
        """从 AgentSkills 格式的 SKILL.md 文件加载技能。

        Args:
            path: SKILL.md 文件的路径。
            file_content: 文件的内容。
            strict: 如果为 True，则强制执行严格的 AgentSkills 名称验证。
            skip_mcp: 如果是 True，则跳过从 .mcp.json 加载 MCP 配置。
        """
        # 对于 SKILL.md 个文件，使用父目录名称作为技能名称
        directory_name = path.parent.name
        skill_root = path.parent

        file_io = io.StringIO(file_content)
        loaded = frontmatter.load(file_io)
        content = loaded.content
        metadata_dict = loaded.metadata or {}

        # 如果提供的话，使用前置元数据中的名称，否则使用目录名称
        agent_name = str(metadata_dict.get("name", directory_name))

        # 验证技能名称（仅在严格模式下）
        if strict:
            name_errors = validate_skill_name(agent_name, directory_name)
            if name_errors:
                raise SkillValidationError(
                    f"Invalid skill name '{agent_name}': {'; '.join(name_errors)}"
                )

        # 从.mcp.json加载MCP配置（agent_skills仅使用.mcp.json）
        mcp_tools: dict[str, MCPServer] | None = None
        if not skip_mcp:
            mcp_json_path = find_mcp_config(skill_root)
            if mcp_json_path:
                mcp_config = load_mcp_config(mcp_json_path, skill_root)
                mcp_tools = coerce_mcp_config(mcp_config.get("mcpServers", {}))

        # 发现资源目录
        resources: SkillResources | None = None
        discovered_resources = discover_skill_resources(skill_root)
        if discovered_resources.has_resources():
            resources = discovered_resources

        return cls._create_skill_from_metadata(
            agent_name,
            content,
            path,
            metadata_dict,
            mcp_tools,
            resources=resources,
            is_agentskills_format=True,
        )

    @classmethod
    def _load_legacy_openhands_skill(
        cls, path: Path, file_content: str, skill_base_dir: Path | None
    ) -> "Skill":
        """从旧的 OpenHands 格式文件加载技能。

        Args:
            path: 技能文件的路径。
            file_content: 文件的内容。
            skill_base_dir: 技能的基本目录（用于派生相对名称）。
        """
        # 处理第三方智能体指令文件
        third_party_agent = cls._handle_third_party(path, file_content)
        if third_party_agent is not None:
            return third_party_agent

        # 从路径计算派生名称
        if skill_base_dir is not None:
            skill_name = cls.PATH_TO_THIRD_PARTY_SKILL_NAME.get(
                path.name.lower()
            ) or to_posix_path(path.relative_to(skill_base_dir).with_suffix(""))
        else:
            skill_name = path.stem

        file_io = io.StringIO(file_content)
        loaded = frontmatter.load(file_io)
        content = loaded.content
        metadata_dict = loaded.metadata or {}

        # 如果提供，则使用前置元数据中的名称，否则使用派生名称
        agent_name = str(metadata_dict.get("name", skill_name))

        # 旧技能仅使用前置元数据中的 mcp_tools（不是 .mcp.json）
        mcp_tools = metadata_dict.get("mcp_tools")
        if mcp_tools is not None and not isinstance(mcp_tools, dict):
            raise SkillValidationError("mcp_tools must be a dictionary or None")
        mcp_tools = coerce_mcp_config(mcp_tools) if mcp_tools is not None else None

        return cls._create_skill_from_metadata(
            agent_name, content, path, metadata_dict, mcp_tools
        )

    @staticmethod
    def _parse_paths(v: object) -> list[str] | None:
        """将 ``paths`` 前置元数据 （逗号分隔的字符串或列表）解析为
        非空的 glob 列表，或 None。 镜像克劳德代码/AgentSkills。"""
        if v is None:
            return None
        if isinstance(v, str):
            v = v.split(",")
        elif not isinstance(v, list):
            raise SkillValidationError("paths must be a string or list")
        return [s for p in v if (s := str(p).strip())] or None

    @classmethod
    def _create_skill_from_metadata(
        cls,
        agent_name: str,
        content: str,
        path: Path,
        metadata_dict: dict[str, object],
        mcp_tools: dict[str, MCPServer] | None = None,
        resources: SkillResources | None = None,
        is_agentskills_format: bool = False,
    ) -> "Skill":
        """从解析的元数据创建技能对象。

        Args:
            agent_name: 技能的名称。
            content: Markdown 内容（不含前置元数据）。
            path: 技能文件的路径。
            metadata_dict: 已解析前置元数据元数据。
            mcp_tools: MCP 工具配置（来自.mcp.json 或前置元数据）。
            resources: 发现资源目录。
            is_agentskills_format: 该技能是否遵循AgentSkills标准。
        """
        # 提取 AgentSkills 个标准字段（Pydantic 验证器句柄转换）。 处理“allowed-tools”到
        # “allowed_tools”键映射。
        #
        allowed_tools_value = metadata_dict.get(
            "allowed-tools", metadata_dict.get("allowed_tools")
        )
        disable_model_invocation_value = metadata_dict.get(
            "disable-model-invocation",
            metadata_dict.get("disable_model_invocation"),
        )
        agentskills_fields = {
            "description": metadata_dict.get("description"),
            "license": metadata_dict.get("license"),
            "compatibility": metadata_dict.get("compatibility"),
            "metadata": metadata_dict.get("metadata"),
            "allowed_tools": allowed_tools_value,
            "disable_model_invocation": disable_model_invocation_value,
        }
        # 删除 None 值以避免传递不必要的 kwargs
        agentskills_fields = {
            k: v for k, v in agentskills_fields.items() if v is not None
        }

        # 从元数据中获取触发关键字
        keywords = metadata_dict.get("triggers", [])
        if not isinstance(keywords, list):
            raise SkillValidationError("Triggers must be a list of strings")

        # 解析路径 glob（“规则”）：以逗号分隔的字符串或 YAML 列表。
        paths = cls._parse_paths(metadata_dict.get("paths"))

        # 推断触发类型：
        # 1. 如果路径存在 -> PathTrigger（确定性文件触摸注入）
        # 2. 如果输入存在 -> TaskTrigger
        # 3. 如果关键字存在 -> KeywordTrigger
        # 4. Else（无关键字）-> None（始终有效）
        if paths:
            # 技能要么是路径触发的，要么是模型调用的，不能同时是两者。
            # `paths:` 获胜，任何 `triggers:`/`inputs:` 都将被忽略。 发出警告，以便发现
            # 丢弃的字段，而不是默默地消失。
            #
            ignored = []
            if keywords:
                ignored.append(f"'triggers': {keywords}")
            if "inputs" in metadata_dict:
                ignored.append("'inputs'")
            if ignored:
                logger.warning(
                    "Skill '%s' declares 'paths:' together with %s; 'paths:' "
                    "takes precedence (path-triggered rule) and %s will be "
                    "ignored. A skill can be either path-triggered OR "
                    "model-invocable, not both.",
                    agent_name,
                    " and ".join(ignored),
                    " and ".join(ignored),
                )
            return Skill(
                name=agent_name,
                content=content,
                source=to_posix_path(path),
                trigger=PathTrigger(paths=paths),
                mcp_tools=mcp_tools,
                resources=resources,
                is_agentskills_format=is_agentskills_format,
                **agentskills_fields,
            )
        elif "inputs" in metadata_dict:
            # 为智能体名称添加触发器（如果尚不存在）
            trigger_keyword = f"/{agent_name}"
            if trigger_keyword not in keywords:
                keywords.append(trigger_keyword)
            inputs_raw = metadata_dict.get("inputs", [])
            if not isinstance(inputs_raw, list):
                raise SkillValidationError("inputs must be a list")
            inputs: list[InputMetadata] = [
                InputMetadata.model_validate(i) for i in inputs_raw
            ]
            return Skill(
                name=agent_name,
                content=content,
                source=to_posix_path(path),
                trigger=TaskTrigger(triggers=keywords),
                inputs=inputs,
                mcp_tools=mcp_tools,
                resources=resources,
                is_agentskills_format=is_agentskills_format,
                **agentskills_fields,
            )

        elif metadata_dict.get("triggers", None):
            return Skill(
                name=agent_name,
                content=content,
                source=to_posix_path(path),
                trigger=KeywordTrigger(keywords=keywords),
                mcp_tools=mcp_tools,
                resources=resources,
                is_agentskills_format=is_agentskills_format,
                **agentskills_fields,
            )
        else:
            # 无触发器，默认为 None（始终处于活动状态）
            return Skill(
                name=agent_name,
                content=content,
                source=to_posix_path(path),
                trigger=None,
                mcp_tools=mcp_tools,
                resources=resources,
                is_agentskills_format=is_agentskills_format,
                **agentskills_fields,
            )

    @classmethod
    def _handle_third_party(cls, path: Path, file_content: str) -> Union["Skill", None]:
        """处理第三方技能文件（e.g.、.cursorrules、AGENTS.md）。

        如果文件类型被识别，则创建具有 None 触发器的技能（始终处于活动状态）。
        """
        skill_name = cls.PATH_TO_THIRD_PARTY_SKILL_NAME.get(path.name.lower())

        if skill_name is not None:
            return Skill(
                name=skill_name,
                content=file_content,
                source=to_posix_path(path),
                trigger=None,
            )

        return None

    @classmethod
    def _handle_nested_third_party(
        cls, path: Path, file_content: str, rel_dir: PurePosixPath
    ) -> Union["Skill", None]:
        """从嵌套构建范围为 ``rel_dir`` 的 ``PathTrigger`` 规则
        第三方文件，因此只有当该目录下的文件被触及时才会注入它的指导。 ``rel_dir`` 是
        工作区相关的（匹配器的基数）。
        """
        skill_name = cls.PATH_TO_THIRD_PARTY_SKILL_NAME.get(path.name.lower())
        if skill_name is None:
            return None
        # 对名称中的目录进行编码，以便多个嵌套文件（全部映射到 e.g. “智能体”）在重复数据
        # 删除和激活跟踪方面保持独特。
        #
        return Skill(
            name=f"{skill_name}:{rel_dir.as_posix()}",
            content=file_content,
            source=to_posix_path(path),
            trigger=PathTrigger(paths=[f"{rel_dir.as_posix()}/**"]),
        )

    @model_validator(mode="after")
    def _truncate_long_description(self):
        """通过 maybe_truncate 将描述截断为 MAX_DESCRIPTION_LENGTH。

        使用model_validator（而不是field_validator），因此截断通知可以引用self.source
        ，告诉智能体在哪里可以找到完整的技能内
        容。
        """
        if (
            self.description is not None
            and len(self.description) > self.MAX_DESCRIPTION_LENGTH
        ):
            logger.warning(
                "Skill '%s' description truncated from %d to %d characters",
                self.name,
                len(self.description),
                self.MAX_DESCRIPTION_LENGTH,
            )
            notice = DEFAULT_TRUNCATE_NOTICE
            if self.source:
                notice = self._DESCRIPTION_TRUNCATE_NOTICE.format(source=self.source)
            self.description = maybe_truncate(
                self.description,
                truncate_after=self.MAX_DESCRIPTION_LENGTH,
                truncate_notice=notice,
            )
        return self

    @model_validator(mode="after")
    def _append_missing_variables_prompt(self):
        """在模型构建后附加提示词以询问缺失的变量。"""
        # 仅适用于任务技能
        if not isinstance(self.trigger, TaskTrigger):
            return self

        # 如果没有变量和输入，则无需执行任何操作
        if not self.requires_user_input() and not self.inputs:
            return self

        prompt = (
            "\n\nIf the user didn't provide any of these variables, ask the user to "
            "provide them first before the agent can proceed with the task."
        )

        # 如果内容已包含提示词，请避免重复它
        if self.content and prompt not in self.content:
            self.content += prompt

        return self

    @model_validator(mode="after")
    def _path_rules_are_trigger_only(self):
        """对路径规则强制 ``disable_model_invocation``：它们仅注入
        file-touch，因此该标志的每个使用者（目录、invoke_skill、工具附加）都使它们不
        被广告且不可调用。
        """
        if isinstance(self.trigger, PathTrigger):
            self.disable_model_invocation = True
        return self

    def match_trigger(self, message: str) -> str | None:
        """匹配消息中的触发器。

        返回与消息匹配的第一个触发器，如果​​不匹配则返回 None。 仅适用于
        KeywordTrigger 和 TaskTrigger 类型。

        匹配是完整的-token 并且不区分大小写：关键字只有在非字母数字字符包围时才会触发
        ，所以 ``git`` 不匹配 ``github`` 和
        ``issue`` 不匹配 ``tissue``. 参见
        :func:`_keyword_matches` 了解详细信息。
        """
        if isinstance(self.trigger, KeywordTrigger):
            keywords = self.trigger.keywords
        elif isinstance(self.trigger, TaskTrigger):
            keywords = self.trigger.triggers
        else:
            return None

        message_lower = message.lower()
        for keyword in keywords:
            if _keyword_matches(keyword, message_lower):
                return keyword
        return None

    def match_path_trigger(self, file_path: str) -> str | None:
        """返回第一个匹配 ``file_path`` 的 PathTrigger glob (a POSIX,
        通常为工作区相对路径）或 None。 对于非 PathTrigger 技能无效。
        """
        if isinstance(self.trigger, PathTrigger):
            for pattern in self.trigger.paths:
                if path_matches_glob(file_path, pattern):
                    return pattern
        return None

    def extract_variables(self, content: str) -> list[str]:
        """从内容中提取变量。

        变量的格式为 ${variable_name}。
        """
        pattern = r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}"
        matches = re.findall(pattern, content)
        return matches

    def requires_user_input(self) -> bool:
        """检查该技能是否需要用户输入。

        如果内容包含格式为 ${variable_name} 的变量，则返回 True。
        """
        # 检查内容是否包含变量
        variables = self.extract_variables(self.content)
        logger.debug(f"This skill requires user input: {variables}")
        return len(variables) > 0

    def get_skill_type(self) -> Literal["repo", "knowledge", "agentskills"]:
        """确定该技能的类型。

        Returns:
            “agentskills”表示 AgentSkills 格式，“repo”表示始终激活的技能，“knowledge”
            表示基于触发的技能。
        """
        if self.is_agentskills_format:
            return "agentskills"
        elif self.trigger is None:
            return "repo"
        else:
            return "knowledge"

    def get_triggers(self) -> list[str]:
        """从此技能中提取触发关键字。

        Returns:
            触发器字符串列表，如果没有触发器则为空列表。
        """
        if isinstance(self.trigger, KeywordTrigger):
            return self.trigger.keywords
        elif isinstance(self.trigger, TaskTrigger):
            return self.trigger.triggers
        return []

    def to_skill_info(self) -> SkillInfo:
        """将此技能转换为SkillInfo。

        Returns:
            SkillInfo包含技能的基本信息。
        """
        return SkillInfo(
            name=self.name,
            type=self.get_skill_type(),
            content=self.content,
            triggers=self.get_triggers(),
            source=self.source,
            description=self.description,
            is_agentskills_format=self.is_agentskills_format,
            disable_model_invocation=self.disable_model_invocation,
        )

    def render_content(
        self,
        working_dir: Path | None = None,
    ) -> str:
        """渲染技能内容，执行内联 !`command` 块。

        内容中的内联 !`command` 模式被执行并替换为其标准输出。 代码块（隔离的和内联的
        ）被保留。 未封闭的围栏块被视为延伸至 EOF。 使用 \\!
        `cmd` 生成文字 !`cmd` 文本。

        Args:
            working_dir: 运行命令的目录。

        Returns:
            用命令输出替换的处理内容。
        """
        return render_content_with_commands(self.content, working_dir)


def load_skills_from_dir(
    skill_dir: str | Path,
    strict: bool = True,
    recursive: bool = True,
    root: Path | None = None,
    exclude_dirs: set[Path] | None = None,
) -> tuple[dict[str, Skill], dict[str, Skill], dict[str, Skill]]:
    """从给定目录加载所有技能。

    支持两种格式：
    - OpenHands格式：技能/*.md文件
    - AgentSkills格式：技能/技能名称/SKILL.md目录

    请注意，此处不会加载旧版存储库指令。

    加载失败的技能会被记录并跳过； 它永远不会中止其他的。

    Args:
        skill_dir: 技能目录的路径（e.g. .openhands/skills）
        strict: 如果为 True，则强制执行严格的 AgentSkills 名称验证。
        recursive: 如果为 False，则仅加载即时的常规 .md 文件
            skill_dir 的孩子。
        root: 如果给出，则在其外部解析的技能路径（e.g. 通过一个
            符号链接）被跳过。 插件在这里传递它们的根。
        exclude_dirs: 常规 .md 文件未加载的目录
            技能（e.g. 在用户技能目录中管理已安装的软件包）。

    Returns:
        (repo_skills, knowledge_skills, agent_skills) 字典的元组。
        - repo_skills: 触发技能=None（永久上下文）
        - knowledge_skills: 技能为 KeywordTrigger 或 TaskTrigger（渐进）
        - agent_skills: AgentSkills 标准 SKILL.md 文件（单独类别）
    """
    if isinstance(skill_dir, str):
        skill_dir = Path(skill_dir)

    repo_skills: dict[str, Skill] = {}
    knowledge_skills: dict[str, Skill] = {}
    agent_skills: dict[str, Skill] = {}
    logger.debug(f"Loading agents from {skill_dir}")

    # 发现技能目录中的技能文件
    # 注意：第三方文件（AGENTS.md等）由单独加载
    # load_project_skills() 以确保即使该目录不存在也能加载它们。
    #
    skill_md_files = find_skill_md_directories(skill_dir, root)
    skill_md_dirs = {skill_md.parent for skill_md in skill_md_files}
    # 将排除重新设置为 skill_dir，以便当通过符号链接到达 skill_dir 时它们仍然匹配 (e.g.
    # ~/.agents/skills -> ~/.openhands/skills).
    #
    real_skill_dir = skill_dir.resolve()
    rebased_exclude_dirs = {
        skill_dir / real.relative_to(real_skill_dir)
        for d in exclude_dirs or ()
        if (real := d.resolve()).is_relative_to(real_skill_dir)
    }
    regular_md_files = find_regular_md_files(
        skill_dir, skill_md_dirs | rebased_exclude_dirs, recursive, root
    )

    # 加载 SKILL.md 个文件（在 Skill.load 中自动检测和验证）将每个加载包装在 try/ except
    #  中，以确保一项糟糕的技能不会破坏所有加载
    #
    for skill_md_path in skill_md_files:
        try:
            load_and_categorize(
                skill_md_path,
                skill_dir,
                repo_skills,
                knowledge_skills,
                agent_skills,
                strict=strict,
                root=root,
            )
        except Exception as e:
            logger.warning(f"Failed to load skill from {skill_md_path}: {e}")

    # 加载常规 .md 文件
    for path in regular_md_files:
        try:
            load_and_categorize(
                path,
                skill_dir,
                repo_skills,
                knowledge_skills,
                agent_skills,
                strict=strict,
                root=root,
            )
        except Exception as e:
            logger.warning(f"Failed to load skill from {path}: {e}")

    total = len(repo_skills) + len(knowledge_skills) + len(agent_skills)
    logger.debug(
        f"Loaded {total} skills: "
        f"repo={list(repo_skills.keys())}, "
        f"knowledge={list(knowledge_skills.keys())}, "
        f"agent={list(agent_skills.keys())}"
    )
    return repo_skills, knowledge_skills, agent_skills


# 默认用户技能目录（按优先级顺序）
USER_SKILLS_DIRS = [
    Path.home() / ".agents" / "skills",
    get_user_persistence_dir() / "skills",
    get_user_persistence_dir() / "microagents",  # 旧版支持
]


def load_user_skills() -> list[Skill]:
    """从用户的主目录加载技能。

    搜索 ~/.agents/skills/、~/.openhands/skills/ 中的技能，以及
    ~/.openhands/microagents/（旧版）。 所有目录中的技能都会合并，USER_SKILLS_DIRS 中
    较早的条目优先处理重复的名称。

    还从 ~/.openhands/skills/installed/ 加载已启用的已安装技能（通过 install_skill/
    uninstall_skill 管理）
    。 安装的技能的优先级低于上述目录中的用户技能。

    Returns:
        从用户目录加载的技能对象列表。 如果未找到技能或加载失败，则返回空列表。
    """
    from openhands.sdk.skills.installed import get_installed_skills_dir

    all_skills: list[Skill] = []
    seen_names: set[str] = set()

    _load_and_merge_from_dirs(
        USER_SKILLS_DIRS,
        seen_names,
        all_skills,
        "user skills",
        exclude_dirs={get_installed_skills_dir()},
    )

    # 加载已启用的已安装技能（优先级低于用户技能）
    try:
        from openhands.sdk.skills.installed import load_installed_skills

        for skill in load_installed_skills():
            if skill.name not in seen_names:
                seen_names.add(skill.name)
                all_skills.append(skill)
    except Exception as e:
        logger.warning(f"Failed to load installed skills: {e}")

    logger.debug(
        f"Loaded {len(all_skills)} user skills: {[s.name for s in all_skills]}"
    )
    return all_skills


def _find_git_repo_root(path: Path) -> Path | None:
    """查找看起来像 Git 存储库根的最近的祖先目录。

    我们故意不向 `git` 支付费用，因此即使未安装 git 也可以使用。 如果目录包含 `.git`
    条目（目录 * 或 * 文件，以支持工作树/子模块），则该目录
    被视为 git 根。
    """

    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _merge_loaded_skills(
    *,
    source_dir: Path,
    loaded_skills: list[dict[str, Skill]],
    seen_names: set[str],
    all_skills: list[Skill],
) -> None:
    for skills_dict in loaded_skills:
        for name, skill in skills_dict.items():
            if name not in seen_names:
                all_skills.append(skill)
                seen_names.add(name)
            else:
                logger.warning(f"Skipping duplicate skill '{name}' from {source_dir}")


def _load_and_merge_from_dirs(
    dirs: list[Path],
    seen_names: set[str],
    all_skills: list[Skill],
    source_label: str,
    exclude_dirs: set[Path] | None = None,
) -> None:
    """从多个目录加载技能，与重复数据删除合并。

    对于每个存在的目录，通过 load_skills_from_dir() 加载所有技能并将它们合并到
    all_skills 中，根据 seen_names 跳过重复项
    。 对于重复的名称，较早的目录优先。

    Args:
        dirs: 用于搜索技能的目录列表。
        seen_names: 一组已经见过的技能名称（就地变异）。
        all_skills: 技能的累加器列表（就地变异）。
        source_label: 日志消息的人类可读标签 (e.g. “用户技能”）。
        exclude_dirs: 传递到load_skills_from_dir()。
    """
    for skills_dir in dirs:
        if not skills_dir.exists():
            logger.debug(f"{source_label} directory does not exist: {skills_dir}")
            continue

        try:
            logger.debug(f"Loading {source_label} from {skills_dir}")
            repo_skills, knowledge_skills, agent_skills = load_skills_from_dir(
                skills_dir, exclude_dirs=exclude_dirs
            )
            _merge_loaded_skills(
                source_dir=skills_dir,
                loaded_skills=[repo_skills, knowledge_skills, agent_skills],
                seen_names=seen_names,
                all_skills=all_skills,
            )
        except Exception as e:
            logger.warning(f"Failed to load {source_label} from {skills_dir}: {str(e)}")


def load_project_skills(work_dir: str | Path) -> list[Skill]:
    """从特定于项目的目录加载技能。

    搜索 {work_dir}/.agents/skills/、{work_dir}/.openhands/skills/ 和 {work_dir}
    /.openhands/microagents/（旧版）中的技能。

    如果工作目录位于 Git 仓库中，该函数还会从 Git 仓库根目录加载技能，因此从子目录运
    行仍然会获取仓库级别的指导 (e.g., AGENTS.md)。

    技能按优先顺序合并，当存在重复项时，*工作目录* 优先于 Git 存储库根。

    使用 .agents/skills 创建新技能。openhands/skills 是旧版 OpenHands 地址，
    openhands/microagents 是已
    弃用。

    Example: 如果“my-skill”在 .agents/skills/ 和 .openhands/skills/ 中都存在
    使用 .agents/skills/ 中的版本。

    还从工作目录和（如果不同）git repo 根加载第三方技能文件（AGENTS.md、.cursorrules
    等）。

    Args:
        work_dir: 项目/工作目录的路径。

    Returns:
        从项目目录加载的技能对象列表。 如果未找到技能或加载失败，则返回空列表。
    """
    if isinstance(work_dir, str):
        work_dir = Path(work_dir)

    all_skills = []
    seen_names: set[str] = set()

    git_root = _find_git_repo_root(work_dir)

    # 工作目录优先（更多本地规则覆盖存储库根规则）
    search_roots: list[Path] = [work_dir]
    if git_root is not None and git_root != work_dir:
        search_roots.append(git_root)

    # 首先，从每个搜索根加载第三方技能文件（AGENTS.md、.cursorrules 等）。 这确保它们即
    # 使不存在 openhands/skills 也能加载。
    #
    for root in search_roots:
        third_party_files = find_third_party_files(
            root, Skill.PATH_TO_THIRD_PARTY_SKILL_NAME
        )
        for path in third_party_files:
            try:
                skill = Skill.load(path)
                if skill.name not in seen_names:
                    all_skills.append(skill)
                    seen_names.add(skill.name)
                    logger.debug(f"Loaded third-party skill: {skill.name} from {path}")
            except (SkillError, OSError, yaml.YAMLError) as e:
                logger.warning(f"Failed to load third-party skill from {path}: {e}")

    # 加载嵌套的第三方文件 (e.g. server/AGENTS.md) 作为目录范围的路径规则，关闭 work_dir
    #  （匹配器的基础）。
    #
    for path, rel_dir in find_nested_third_party_files(
        work_dir, Skill.PATH_TO_THIRD_PARTY_SKILL_NAME
    ):
        try:
            content = path.read_text(encoding="utf-8")
            rule = Skill._handle_nested_third_party(path, content, rel_dir)
            if rule is not None and rule.name not in seen_names:
                all_skills.append(rule)
                seen_names.add(rule.name)
                logger.debug(f"Loaded nested path rule: {rule.name} from {path}")
        except (SkillError, OSError, UnicodeDecodeError, yaml.YAMLError) as e:
            logger.warning(f"Failed to load nested third-party file {path}: {e}")

    # 加载项目特定的技能从 .agents/skills，openhands/skills，以及遗留微代理（优先顺序：
    # 重复者先胜）
    #
    for root in search_roots:
        project_skills_dirs = [
            root / ".agents" / "skills",
            root / ".openhands" / "skills",
            root / ".openhands" / "microagents",  # 旧版支持
        ]

        _load_and_merge_from_dirs(
            project_skills_dirs, seen_names, all_skills, "project skills"
        )

    logger.debug(
        f"Loaded {len(all_skills)} project skills: {[s.name for s in all_skills]}"
    )
    return all_skills


# 公共技能库配置
PUBLIC_SKILLS_REPO = "https://github.com/OpenHands/extensions"
# 允许通过 EXTENSIONS_REF 环境变量覆盖 ref。 接受分支名称、标签 (e.g. “v1.0.0”），或完整
# 的 40 个字符提交 SHA。
#
PUBLIC_SKILLS_REF = os.environ.get("EXTENSIONS_REF", "main")
DEFAULT_MARKETPLACE_PATH = "marketplaces/default.json"
# 公共存储库的本地签出或包，读取而不是 git 克隆。
PUBLIC_SKILLS_PATH_ENV = "EXTENSIONS_PATH"

# load_public_skills 的进程级缓存。 会话创建会多次重新验证 AgentContext，并且每次验证都
# 会重新运行 load_public_skills（git fetch + parse ~40 md 文件 ≈ 1 秒）。 缓存会短路 TTL
#  内的重复调用，同时仍能在一分钟内获取新技能。
#
# 缓存值：（时间戳，技能）对于可变引用（分支），写入时时间戳为 time.monotonic()，条目在
# _PUBLIC_SKILLS_CACHE_TTL_SECONDS 之后过期。 对于 pinned ref（标签和提交 SHAs），时间戳
# 是 float("inf")，因此 TTL 检查永远不会满足，该条目会一直存在直到进程生命周期结束。
#
_PUBLIC_SKILLS_CACHE: dict[
    tuple[str, str, str | None], tuple[float, list["Skill"]]
] = {}
_PUBLIC_SKILLS_CACHE_TTL_SECONDS = 60.0
_PUBLIC_SKILLS_CACHE_LOCK = threading.Lock()


def _invalidate_public_skills_cache() -> None:
    """清除内存中的公共技能缓存。

    由 ``sync_public_skills`` 调用，因此强制刷新会立即重新解析，而不是等待 TTL。
    """
    with _PUBLIC_SKILLS_CACHE_LOCK:
        _PUBLIC_SKILLS_CACHE.clear()


def load_marketplace_skill_names(
    repo_path: Path, marketplace_path: str
) -> set[str] | None:
    """从市场清单文件加载技能名称列表。

    使用 openhands.sdk.plugin 中的现有市场模型来解析市场 JSON 文件并提取插件名称。

    Args:
        repo_path: 本地存储库的路径。
        marketplace_path: 存储库内市场 JSON 文件的相对路径。

    Returns:
        要加载的技能名称集，如果未找到市场文件或无效，则为 None。
    """
    from openhands.sdk.marketplace import Marketplace

    marketplace_file = repo_path / marketplace_path
    if not marketplace_file.exists():
        logger.debug(f"Marketplace file not found: {marketplace_file}")
        return None

    try:
        with open(marketplace_file, encoding="utf-8") as f:
            data = json.load(f)

        # 使用 Marketplace 模型进行验证和解析
        marketplace = Marketplace.model_validate(
            {**data, "path": to_posix_path(repo_path)}
        )

        skill_names = {plugin.name for plugin in marketplace.plugins}

        logger.debug(
            f"Loaded {len(skill_names)} skill names from marketplace: "
            f"{marketplace_path}"
        )
        return skill_names

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse marketplace JSON {marketplace_file}: {e}")
        return None
    except OSError as e:
        logger.warning(f"Failed to read marketplace file {marketplace_file}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to load marketplace {marketplace_file}: {e}")
        return None


def _local_public_skills_path(repo_url: str) -> Path | None:
    path = os.environ.get(PUBLIC_SKILLS_PATH_ENV)
    if not path or repo_url != PUBLIC_SKILLS_REPO:
        return None
    return Path(path).expanduser()


def load_public_skills(
    repo_url: str = PUBLIC_SKILLS_REPO,
    ref: str = PUBLIC_SKILLS_REF,
    marketplace_path: str | None = DEFAULT_MARKETPLACE_PATH,
) -> list[Skill]:
    """从公共 OpenHands 技能存储库加载技能。

    此功能维护公共技能注册表的本地 git 克隆，位于
    https://github.com/OpenHands/extensions.  第一次运行时，它会克隆存储库
    to ~/.openhands/skills-cache/. 在同一进程中的后续运行中，它返回缓存的结果。 对于
    分支引用，它会在缓存 TTL 之后重新获取； 对于
    pinned 标签和提交 SHAs，缓存永远不会过期。 加载器不会对这些引用进行进一步的网络调
    用。

    当 ``EXTENSIONS_PATH`` 命名默认存储库的本地副本（例如已安装的
    ``@openhands/extensions`` 包）时，将从其中读取技能，并
    且不会克隆任何内容。

    默认情况下，仅加载默认市场 (marketplaces/default.json) 中列出的技能。 传递不同的
    亲属 marketplace_path 来加载另一个市
    场，或 None 加载所有公共技能而不进行市场过滤。

    Note: 当技能目录包含SKILL.md文件（AgentSkills格式）时，
    该目录或其子目录中的任何其他 Markdown 文件都被视为该技能的参考资料，不被视为单独
    的技能。

    Args:
        repo_url: 技能库的URL。 默认为官方
            OpenHands 技能库。
        ref: 分支名称、标签 (e.g. ``"v1.0.0"``)，或完整的 40 个字符提交
            SHA 从中加载技能。 默认为 ``'main'``。 加载后，标签和提交 SHAs 已被锁定。
             结果在进程的生命周期内保持缓存，无需进一步远程轮询
            。
        marketplace_path: 市场 JSON 文件的相对路径
            存储库。 通过None加载所有公共技能，不进行过滤。

    Returns:
        从公共存储库加载的技能对象列表。 如果加载失败则返回空列表。

    Example:
        >>> from openhands.sdk.context import AgentContext
        >>> from openhands.sdk.skills import load_public_skills
        >>>
        >>> # 加载公共技能
        >>> public_skills = load_public_skills()
        >>>
        >>> # 使用 AgentContext
        >>> context = AgentContext(skills=public_skills)
    """
    local_path = _local_public_skills_path(repo_url)
    cache_key = (str(local_path or repo_url), ref, marketplace_path)
    with _PUBLIC_SKILLS_CACHE_LOCK:
        cached = _PUBLIC_SKILLS_CACHE.get(cache_key)
        if (
            cached is not None
            and time.monotonic() - cached[0] < _PUBLIC_SKILLS_CACHE_TTL_SECONDS
        ):
            return list(cached[1])

    all_skills: list[Skill] = []
    is_pinned = False

    try:
        if local_path is not None:
            repo_path = local_path
        else:
            # 获取或更新本地存储库
            cache_dir = get_skills_cache_dir()
            repo_path = update_skills_repository(repo_url, ref, cache_dir)

            if repo_path is None:
                logger.warning("Failed to access public skills repository")
                return all_skills

            is_pinned = is_skills_repo_pinned(repo_path, ref)

        # 从本地存储库加载技能
        skills_dir = repo_path / "skills"
        if not skills_dir.exists():
            logger.warning(f"Skills directory not found in repository: {skills_dir}")
            return all_skills

        # 确定要加载哪些技能文件
        if marketplace_path is None:
            marketplace_skill_names = None
        else:
            marketplace_skill_names = load_marketplace_skill_names(
                repo_path, marketplace_path
            )
            if (
                marketplace_skill_names is None
                and marketplace_path != DEFAULT_MARKETPLACE_PATH
            ):
                logger.warning(
                    "Configured marketplace path could not be loaded: %s",
                    marketplace_path,
                )
                return all_skills

        if marketplace_skill_names is not None:
            all_skill_files: list[Path] = []
            for skill_name in marketplace_skill_names:
                skill_md = skills_dir / skill_name / "SKILL.md"
                if skill_md.exists():
                    all_skill_files.append(skill_md)
                    continue

                legacy_md = skills_dir / f"{skill_name}.md"
                if legacy_md.exists():
                    all_skill_files.append(legacy_md)
                    continue

                logger.debug(
                    "Skill '%s' from marketplace '%s' not found in skills dir",
                    skill_name,
                    marketplace_path,
                )
        else:
            skill_md_files = find_skill_md_directories(skills_dir)
            skill_md_dirs = {skill_md.parent for skill_md in skill_md_files}
            regular_md_files = find_regular_md_files(skills_dir, skill_md_dirs)
            all_skill_files = list(skill_md_files) + list(regular_md_files)

        logger.info(
            f"Found {len(all_skill_files)} skill files in public skills repository"
        )

        # 加载各个技能文件
        for skill_file in all_skill_files:
            try:
                skill = Skill.load(
                    path=skill_file,
                    skill_base_dir=repo_path,
                )
                if skill is None:
                    continue
                all_skills.append(skill)
                logger.debug(f"Loaded public skill: {skill.name}")
            except Exception as e:
                logger.warning(f"Failed to load skill from {skill_file.name}: {str(e)}")
                continue

    except Exception as e:
        logger.warning(f"Failed to load public skills from {repo_url}: {str(e)}")

    logger.info("Loaded %d public skills", len(all_skills))

    # 仅缓存非空结果，因此瞬态错误不会破坏整个 TTL 窗口的缓存。
    #
    if all_skills:
        timestamp = float("inf") if is_pinned else time.monotonic()
        with _PUBLIC_SKILLS_CACHE_LOCK:
            _PUBLIC_SKILLS_CACHE[cache_key] = (timestamp, list(all_skills))

    return all_skills


def load_available_skills(
    work_dir: str | Path | None = None,
    *,
    include_user: bool = False,
    include_project: bool = False,
    include_public: bool = False,
    marketplace_path: str | None = DEFAULT_MARKETPLACE_PATH,
) -> dict[str, Skill]:
    """以一致的优先级从 SDK 级来源加载和合并技能。

    优先级（稍后通过字典更新覆盖之前的内容）：
        公共（最低）→用户→项目（最高）

    这是从三个 SDK 发布的源构建合并技能目录的单一入口点。 仅服务器源（沙箱、组织）由
    调用者分层。

    Args:
        work_dir: 项目技能的项目/工作目录。 当None时，
            无论*include_project*如何，都会跳过项目技能。
        include_user: 加载用户级技能（~/.agents/skills等）。
        include_project: 加载项目级技能（需要 *work_dir*）。
        include_public: 从 OpenHands 扩展存储库加载公共技能。
        marketplace_path: 用于公共技能的相对市场 JSON 路径。
            通过 None 加载所有公共技能，无需市场过滤。

    Returns:
        字典映射技能名称 → 技能，优先级较高的来源优先于较低优先级的来源。
    """
    available: dict[str, Skill] = {}

    if include_public:
        try:
            for s in load_public_skills(marketplace_path=marketplace_path):
                available[s.name] = s
        except Exception as e:
            logger.warning(f"Failed to load public skills: {e}")

    if include_user:
        try:
            for s in load_user_skills():
                available[s.name] = s
        except Exception as e:
            logger.warning(f"Failed to load user skills: {e}")

    if include_project and work_dir:
        try:
            for s in load_project_skills(work_dir):
                available[s.name] = s
        except Exception as e:
            logger.warning(f"Failed to load project skills: {e}")

    return available


def merge_skills_by_name(
    primary: Iterable[Skill], secondary: Iterable[Skill]
) -> list[Skill]:
    """按名称合并两个技能集合。

    ``primary`` 技能具有权威性：它们优先处理名称冲突并保持顺序。 仅当 ``primary`` 尚
    未提供每个 ``secondary`` 技能的名称时才会附
    加该技能。
    """
    merged = list(primary)
    seen = {skill.name for skill in merged}
    for skill in secondary:
        if skill.name not in seen:
            seen.add(skill.name)
            merged.append(skill)
    return merged


def to_prompt(skills: list[Skill], max_description_length: int = 1024) -> str:
    """为可用技能生成 XML 提示词块。

    创建一个适合包含在系统提示词中的 `<available_skills>` XML 块，遵循技能参考中的
    AgentSkills 格式。

    Args:
        skills: 要包含在提示词中的技能列表
        max_description_length: 描述的最大长度（默认 1024）

    Returns:
        XML 格式为 AgentSkills 的字符串，包含名称和说明。 的
        `<location>` 字段被故意省略，因此智能体无法通过直接读取文件来绕过
        `invoke_skill` 工具。

    Example:
        >>> skills = [Skill(name="pdf-tools", content="...",
        ...                 description="Extract text from PDF files.",
        ...                 source="/path/to/skill")]
        >>> print(to_prompt(skills))
        <available_skills>
          <skill>
            <name>pdf-tools</name> <description>从 PDF 个文件中提取文本。
            </description>
          </skill>
        </available_skills>
    """
    if not skills:
        return "<available_skills>\n  no available skills\n</available_skills>"

    lines = ["<available_skills>"]
    for skill in skills:
        # 如果有的话使用描述，否则使用第一行内容
        description = skill.description
        content_truncated = 0
        if not description:
            # 从内容中提取第一个非空、非标题行作为回退方案跟踪位置以计算描述后的截断内容
            #
            chars_before_desc = 0
            for line in skill.content.split("\n"):
                stripped = line.strip()
                # 跳过 Markdown 个标题和空行
                if not stripped or stripped.startswith("#"):
                    chars_before_desc += len(line) + 1  # +1 换行
                    continue
                description = stripped
                # 计算此行被截断后的剩余内容
                desc_end_pos = chars_before_desc + len(line)
                content_truncated = max(0, len(skill.content) - desc_end_pos)
                break
        description = description or ""

        # 计算截断字符总数
        total_truncated = content_truncated

        # 如果需要，截断描述并添加截断指示符
        if len(description) > max_description_length:
            total_truncated += len(description) - max_description_length
            description = description[:max_description_length]

        if total_truncated > 0:
            truncation_msg = (
                f"... [{total_truncated} characters truncated. "
                f'Call invoke_skill(name="{skill.name}") to load the full skill]'
            )
            description = description + truncation_msg

        # 使用标准库转义 XML 特殊字符
        description = xml_escape(description.strip())
        name = xml_escape(skill.name.strip())

        # 构建技能元素。 注意：<location>被故意省略，因此智能体无法通过直接读取文件来绕
        # 过`invoke_skill`；
        # `invoke_skill` 是唯一受支持的调用路径。
        lines.append("  <skill>")
        lines.append(f"    <name>{name}</name>")
        lines.append(f"    <description>{description}</description>")
        lines.append("  </skill>")

    lines.append("</available_skills>")
    return "\n".join(lines)
