from __future__ import annotations

import pathlib
from collections.abc import Mapping
from datetime import datetime
from typing import Any, NamedTuple

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from openhands.sdk.context.prompts import render_template
from openhands.sdk.context.prompts.presets import create_registry
from openhands.sdk.context.prompts.section import PromptContext
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.llm.utils.model_prompt_spec import get_model_prompt_spec
from openhands.sdk.logger import get_logger
from openhands.sdk.marketplace.registration import MarketplaceRegistration
from openhands.sdk.secret import SecretSource, SecretValue
from openhands.sdk.settings.metadata import SettingProminence, field_meta
from openhands.sdk.skills import (
    Skill,
    SkillKnowledge,
    load_available_skills,
    merge_skills_by_name,
    to_prompt,
)
from openhands.sdk.skills.skill import DEFAULT_MARKETPLACE_PATH
from openhands.sdk.utils.pydantic_secrets import (
    serialize_secret,
    validate_secret_dict,
)


logger = get_logger(__name__)

PROMPT_DIR = pathlib.Path(__file__).parent / "prompts" / "templates"


class ResolvedDynamicData(NamedTuple):
    """动态层输入解析一次，送入部分注册表
    （由模型系列控制的技能，机密合并）。"""

    repo_skills: list[Skill]
    available_skills_prompt: str
    secret_infos: list[dict[str, str | None]]
    formatted_datetime: str | None


class AgentContext(BaseModel):
    """用于管理提示词扩展的中央结构。

    AgentContext 统一了塑造系统如何扩展和解释用户的所有上下文输入提示词。 它结合了静
    态环境细节和动态的、用户激活的技能扩展。

    具体来说，它规定：
    - **存储库上下文/存储库技能**：有关存储库技能贡献的活动代码库、分支和存储库特定指
    令的信息。
    - **运行时上下文**：当前执行环境（主机、工作目录、机密、日期等）。
    - **对话说明**：可选的特定于任务或渠道的规则，用于限制或指导智能体在整个会话中的
    行为。
    - **知识技能**：可通过用户输入触发的可扩展组件，以注入知识或特定领域的指导。

    这些元素一起工作 AgentContext 负责组装、格式化和注入所有内容的主要容器提示词-
    relevant 上下文 into LLM 交互。
    """  # noqa: E501

    skills: list[Skill] = Field(
        default_factory=list,
        description="List of available skills that can extend the user's input.",
        json_schema_extra={"acp_compatible": True},
    )
    system_message_suffix: str | None = Field(
        default=None,
        description="Optional suffix to append to the system prompt.",
        json_schema_extra={"acp_compatible": True},
    )
    user_message_suffix: str | None = Field(
        default=None,
        description="Optional suffix to append to the user's message.",
        json_schema_extra={"acp_compatible": True},
    )
    load_user_skills: bool = Field(
        default=False,
        description=(
            "Whether to automatically load user skills from ~/.openhands/skills/ "
            "and ~/.openhands/microagents/ (for backward compatibility). "
        ),
        json_schema_extra={"acp_compatible": True},
    )
    load_public_skills: bool = Field(
        default=False,
        description=(
            "Whether to automatically load skills from the public OpenHands "
            "skills repository at https://github.com/OpenHands/extensions. "
            "This allows you to get the latest skills without SDK updates."
        ),
        json_schema_extra={"acp_compatible": True},
    )
    marketplace_path: str | None = Field(
        default=DEFAULT_MARKETPLACE_PATH,
        description=(
            "Relative marketplace JSON path within the public skills repository. "
            "Set to None to load all public skills without marketplace filtering."
        ),
        json_schema_extra={"acp_compatible": True},
    )
    registered_marketplaces: list[MarketplaceRegistration] = Field(
        default_factory=list,
        description=(
            "Marketplace registrations for plugin resolution. Registrations with "
            "auto_load=True or a list of plugin names are resolved by "
            "LocalConversation at startup."
        ),
        json_schema_extra={"acp_compatible": True},
    )
    load_project_skills: bool = Field(
        default=False,
        description=(
            "Whether to automatically load project skills from the conversation "
            "workspace (e.g. .openhands/skills/, AGENTS.md). Unlike "
            "load_user_skills / load_public_skills, this flag is not resolved by "
            "AgentContext itself (the workspace path is unknown at validation "
            "time); LocalConversation resolves it lazily on the first "
            "send_message() / run(), when the workspace is known. Also unlike "
            "load_user_skills / load_public_skills (which yield to explicit "
            "skills on a name conflict), resolved project skills are "
            "authoritative: a project skill overrides a same-named skill already "
            "present in `skills`."
        ),
        json_schema_extra={"acp_compatible": True},
    )
    load_memory: bool = Field(
        default=False,
        description=(
            "Whether to load persistent agent memory (MEMORY.md indexes under "
            "~/.openhands/memory/ and <workspace>/.openhands/memory/) into the "
            "system prompt. Like load_project_skills, this flag is not "
            "resolved by AgentContext itself (the workspace path is unknown "
            "at validation time); LocalConversation resolves it lazily on the "
            "first send_message() / run() and stores the result in "
            "memory_context."
        ),
        json_schema_extra={
            "acp_compatible": True,
            **field_meta(SettingProminence.MAJOR, label="Persistent memory"),
        },
    )
    memory_context: str | None = Field(
        default=None,
        exclude=True,
        description=(
            "Resolved memory-index text rendered into the <MEMORY_CONTEXT> "
            "prompt block. Populated via model_copy by LocalConversation when "
            "load_memory is set; excluded from serialization because it is "
            "re-resolved from disk each session and must not bloat persisted "
            "conversation state."
        ),
        json_schema_extra={"acp_compatible": True},
    )
    disabled_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Names of skills to EXCLUDE from this context — a deny-list applied "
            "after every skill source is loaded (auto-loaded user/public, "
            "explicit, and lazily-loaded project skills). A listed name absent "
            "from the loaded set is a harmless no-op. [] (the default) keeps "
            "every skill. This is the single, drift-tolerant skill-selection "
            "mechanism (agent profiles set it from their own deny-list; #4017)."
        ),
        json_schema_extra={"acp_compatible": True},
    )
    secrets: Mapping[str, SecretValue] | None = Field(
        default=None,
        description=(
            "Dictionary mapping secret keys to values or secret sources. "
            "Secrets are used for authentication and sensitive data handling. "
            "Values can be either strings or SecretSource instances "
            "(str | SecretSource)."
        ),
        json_schema_extra={"acp_compatible": True},
    )
    current_datetime: datetime | str | None = Field(
        # 时区感知的本地“现在”； get_formatted_datetime 将其呈现为提示词的分钟。
        #
        default_factory=lambda: datetime.now().astimezone(),
        description=(
            "Current date and time information to provide to the agent. "
            "Can be a datetime object (which will be formatted as ISO 8601) "
            "or a pre-formatted string. When provided, this information is "
            "included in the system prompt to give the agent awareness of "
            "the current time context. Defaults to the current "
            "(timezone-aware) datetime."
        ),
        json_schema_extra={"acp_compatible": True},
    )

    @field_validator("secrets", mode="before")
    @classmethod
    def _decrypt_secrets(cls, value: Any, info: ValidationInfo) -> Any:
        """当密码时解密已持久化原始字符串 ``secrets`` 值
        位于上下文中。

        ``_serialize_secrets`` 通过写入每个原始字符串值
        :func:`serialize_secret`，在下面生成 Fernet 密文
        密码上下文。 如果没有匹配的 ``mode='before'`` 解密验证器，该密文将在往返中幸
        存下来
        :class:`StartConversationRequest` （其
        ``_populate_agent_from_settings`` 验证器运行 *，不带 * 密码上下文) 并按原样注
        入到智能体的系统提示词 — 与任何在没
        有匹配解密的情况下往返的机密承载字典字段相同的 bug 类验证器 (e.g. MCP
        ``env`` / ``headers``).

        ``SecretSource`` 条目在线路上呈字典形状（Pydantic 型号），因此它们会被：func:
        `validate_secret_dict` 跳
        过
        ``isinstance(value, str)``门并通过自己的验证器继续正常构建。
        """
        return validate_secret_dict(value, info, description="AgentContext secrets")

    @field_serializer("secrets", when_used="always")
    def _serialize_secrets(
        self, value: Mapping[str, SecretValue] | None, info
    ) -> dict[str, Any] | None:
        """通过：func:`serialize_secret` 屏蔽原始字符串 ``secrets`` 值。"""
        if value is None:
            return None
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(v, SecretSource):
                out[k] = v.model_dump(mode=info.mode, context=info.context)
            else:
                out[k] = serialize_secret(SecretStr(v), info)
        return out

    @field_validator("skills")
    @classmethod
    def _validate_skills(cls, v: list[Skill], _info):
        if not v:
            return v
        # 检查技能名称是否重复
        seen_names = set()
        for skill in v:
            if skill.name in seen_names:
                raise ValueError(f"Duplicate skill name found: {skill.name}")
            seen_names.add(skill.name)
        return v

    @model_validator(mode="after")
    def _load_auto_skills(self):
        """如果启用，则加载用户/旧公共技能，然后应用 ``disabled_skills``。"""
        return self.resolve_auto_skills()

    def resolve_auto_skills(self) -> AgentContext:
        """将 ``load_*_skills`` 解析为 ``skills`` 并应用 ``disabled_skills``。

        由于 ``model_copy`` 跳过验证器而暴露：以这种方式重建上下文的调用者必须重新运
        行此命令，否则静默拒绝列表将不适用。
        """
        include_public = self.load_public_skills
        if self.load_user_skills or include_public:
            auto_skills = load_available_skills(
                work_dir=None,
                include_user=self.load_user_skills,
                include_project=False,
                include_public=include_public,
                marketplace_path=self.marketplace_path,
            )

            # 显性的技能具有权威性； 自动加载的技能只能填补空白。
            explicit_names = {skill.name for skill in self.skills}
            for name in auto_skills:
                if name in explicit_names:
                    logger.debug(
                        f"Skipping auto-loaded skill '{name}' "
                        "(already in explicit skills)"
                    )
            self.skills = merge_skills_by_name(self.skills, auto_skills.values())

        # 拒绝列表：从最终加载的内容中删除禁用的技能（明确
        # + 自动）。 不存在的禁用名称是无害的无操作 - 这
        # 是取代允许列表引用的漂移容忍选择模型。
        if self.disabled_skills:
            disabled = set(self.disabled_skills)
            self.skills = [s for s in self.skills if s.name not in disabled]
        return self

    def get_secret_infos(self) -> list[dict[str, str | None]]:
        """从机密字段获取机密信息（名称和描述）。

        Returns:
            带有“名称”和“描述”键的字典列表。 如果未配置机密，则返回空列表。 如果不可
            用，说明将为 None。
        """
        if not self.secrets:
            return []
        secret_infos: list[dict[str, str | None]] = []
        for name, secret_value in self.secrets.items():
            description = None
            if isinstance(secret_value, SecretSource):
                description = secret_value.description
            secret_infos.append({"name": name, "description": description})
        return secret_infos

    def get_formatted_datetime(self) -> str | None:
        """获取包含在提示词中的格式化日期时间字符串。

        Returns:
            格式化的日期时间字符串，如果未设置 current_datetime，则为 None。 如果
            current_datetime 是日期时间对象，则其
            格式为“YYYY-MM-DDTHH:MM”（无秒、微秒或 UTC 偏移​​量）。 如果
            current_datetime 已经是字符串，则按原样返回
            。
        """
        if self.current_datetime is None:
            return None
        if isinstance(self.current_datetime, datetime):
            # 本地挂钟精确到分钟：滴秒、微秒、偏移。
            return self.current_datetime.replace(tzinfo=None).isoformat(
                timespec="minutes"
            )
        return self.current_datetime

    def _partition_skills(self) -> tuple[list[Skill], list[Skill]]:
        """将技能分为 repo-上下文和可用技能列表。

        分类规则（由系统消息和 ACP 适配器共享）：
        - AgentSkills-格式：available_skills，除非禁用直接模型调用。 触发器仍然通过
        ``get_user_message_suffix`` 自动注入。
        - ``trigger=None`` 的旧版：REPO_CONTEXT 中的完整内容（始终有效）。
        - 传统的触发器：在 available_skills 中列出，除非禁用直接模型调用，在触发器上
        注入。

        Returns:
            ``(repo_skills, available_skills)`` 元组。
        """
        repo_skills: list[Skill] = []
        available_skills: list[Skill] = []
        for s in self.skills:
            if s.is_agentskills_format or s.trigger is not None:
                # 路径规则强制 disable_model_invocation（技能验证器），因此它们在这里掉
                # 落 - 仅在文件触摸时注入，从未列出。
                #
                if not s.disable_model_invocation:
                    available_skills.append(s)
            else:
                repo_skills.append(s)
        return repo_skills, available_skills

    def get_system_message_suffix(
        self,
        llm_model: str | None = None,
        llm_model_canonical: str | None = None,
        additional_secret_infos: list[dict[str, str | None]] | None = None,
    ) -> str | None:
        """获取带有仓库技能内容和自定义后缀的系统消息。

        自定义后缀通常可以包括：
        - 存储库信息（存储库名称、分支名称、PR编号等）
        - 运行时信息（e.g.、可用主机、当前日期）
        - 对话说明（e.g.、用户首选项、任务详细信息）
        - 存储库特定指令（从存储库技能收集）
        - 可用技能列表（适用于 AgentSkills 格式和触发技能）

        Args:
            llm_model: 用于特定于供应商的技能过滤的可选 LLM 型号名称。
            llm_model_canonical: 可选的规范 LLM 模型名称。
            additional_secret_infos: 附加机密信息字典的可选列表
                （使用“名称”和“描述”键）与 agent_context 机密合并。 通常从对话的
                secret_registry 中传递。

        技能分类：
        - AgentSkills-格式 (SKILL.md)：始终采用 <available_skills>（渐进式公开）。 如
        果有触发器，则内容会在用户提示词中
        的触发器上自动注入 ALSO。
        - 带有触发器=None的旧版：<REPO_CONTEXT>中的完整内容（始终处于活动状态）
        - 带有触发器的旧版本：列在 <available_skills> 中，在触发器上注入
        """
        data = self._resolve_dynamic_data(
            llm_model, llm_model_canonical, additional_secret_infos
        )
        ctx = PromptContext(
            now=data.formatted_datetime,
            repo_skills=tuple((s.name, s.content) for s in data.repo_skills),
            available_skills_prompt=data.available_skills_prompt or None,
            custom_suffix=self.system_message_suffix or None,
            memory_context=self.memory_context or None,
            secret_infos=tuple(
                (info["name"] or "", info["description"]) for info in data.secret_infos
            ),
        )
        return create_registry().build(ctx).dynamic

    def _resolve_dynamic_data(
        self,
        llm_model: str | None = None,
        llm_model_canonical: str | None = None,
        additional_secret_infos: list[dict[str, str | None]] | None = None,
    ) -> ResolvedDynamicData:
        """解析：meth:`get_system_message_suffix` 共享的动态层输入
        以及部分注册表：模型门控回购技能、可用技能提示词、合并的机密信息和格式化的日
        期时间。 纯（无渲染）。
        """
        repo_skills, available_skills = self._partition_skills()

        # 根据模型系列控制供应商特定的回购技能。
        if llm_model or llm_model_canonical:
            spec = get_model_prompt_spec(llm_model or "", llm_model_canonical)
            family = (spec.family or "").lower()
            if family:
                filtered: list[Skill] = []
                for s in repo_skills:
                    n = (s.name or "").lower()
                    if n == "claude" and not (
                        "anthropic" in family or "claude" in family
                    ):
                        continue
                    if n == "gemini" and not (
                        "gemini" in family or "google_gemini" in family
                    ):
                        continue
                    filtered.append(s)
                repo_skills = filtered

        logger.debug(f"Loaded {len(repo_skills)} repository skills: {repo_skills}")

        available_skills_prompt = ""
        if available_skills:
            available_skills_prompt = to_prompt(available_skills)
            logger.debug(
                f"Generated available skills prompt for {len(available_skills)} skills"
            )

        # 将 agent_context 机密与注册表中的附加机密合并（按名称附加覆盖）。
        #
        secret_infos = self.get_secret_infos()
        if additional_secret_infos:
            secret_dict = {s["name"]: s for s in secret_infos}
            for additional in additional_secret_infos:
                secret_dict[additional["name"]] = additional
            secret_infos = list(secret_dict.values())

        return ResolvedDynamicData(
            repo_skills=repo_skills,
            available_skills_prompt=available_skills_prompt,
            secret_infos=secret_infos,
            formatted_datetime=self.get_formatted_datetime(),
        )

    def validate_acp_compatibility(self) -> None:
        """如果此上下文使用 ACP 提示词模式不支持的字段，则引发该错误。

        兼容性由每个字段的 ``json_schema_extra`` 中的 ``acp_compatible`` 标记确定。
        """
        acp_compatible = {
            name
            for name, info in type(self).model_fields.items()
            if isinstance(info.json_schema_extra, dict)
            and info.json_schema_extra.get("acp_compatible") is True
        }
        unsupported = set(self.model_fields_set) - acp_compatible
        if unsupported:
            fields = ", ".join(sorted(unsupported))
            raise NotImplementedError(
                f"ACP prompt context does not support AgentContext field(s): {fields}"
            )

    def to_acp_prompt_context(
        self,
        additional_secret_infos: list[dict[str, str | None]] | None = None,
    ) -> str | None:
        """返回 ACP 可以用作提示词文本的 AgentContext 字段。

        ACP 服务器拥有自己的工具、MCP 服务器、挂钩和执行模型，因此此适配器仅发出提示
        词-only 上下文。 不支持的 AgentContext 字段被：me
        th:`validate_acp_compatibility` 拒绝。

        渲染使用了 `get_system_message_suffix` 这个方法，它通过共享提示词注册表来组装
        动态层级部分，因此 ACP 智能体接收到与常规智能
        体相同的提示词布局。 这包括
        ``<CUSTOM_SECRETS>`` 当机密存在时阻止，通知 ACP 子进程哪个环境变量可用。 实际
        的机密值通过以下方式注入到子进程环境中
        ``ACPAgent._start_acp_server``; 提示词块仅公布它们的名称，以便智能体知道使用
        它们。

        ``user_message_suffix`` 是一个兼容字段，但此处未发出，因为
        ``LocalConversation`` 已通过
        ``event.to_llm_message()``; 包括它会重复它。

        Args:
            additional_secret_infos: 附加机密信息字典的可选列表
                from the conversation's secret_registry, matching the interface of
                ：方法：`get_system_message_suffix`。 当提供时，这些机密是
                与 AgentContext 上已有的任何机密合并，因此渲染的
                ``<CUSTOM_SECRETS>`` 块与常规智能体发出的内容匹配。
        """
        self.validate_acp_compatibility()
        # ACP 没有特定于模型的技能过滤 - 委托给共享构建器，其动态层部分也从机密发出
        # <CUSTOM_SECRETS> 块。
        #
        return self.get_system_message_suffix(
            additional_secret_infos=additional_secret_infos
        )

    def get_user_message_suffix(
        self, user_message: Message, skip_skill_names: list[str]
    ) -> tuple[TextContent, list[str]] | None:
        """利用从技能中回忆起的知识来丰富用户的信息。

        这是通过以下方式实现的：
        - 提取用户消息的文本内容
        - 根据查询匹配技能触发器
        - 如果触发了相关技能，则返回格式化的知识和触发的技能名称
        """  # noqa: E501

        user_message_suffix = None
        if self.user_message_suffix and self.user_message_suffix.strip():
            user_message_suffix = self.user_message_suffix.strip()

        query = "\n".join(
            c.text for c in user_message.content if isinstance(c, TextContent)
        ).strip()
        recalled_knowledge: list[SkillKnowledge] = []
        # 跳过空查询，但如果存在则仍返回 user_message_suffix
        if not query:
            if user_message_suffix:
                return TextContent(text=user_message_suffix), []
            return None
        # 在查询中搜索技能触发器
        for skill in self.skills:
            if not isinstance(skill, Skill):
                continue
            trigger = skill.match_trigger(query)
            if trigger and skill.name not in skip_skill_names:
                logger.info(
                    "Skill '%s' triggered by keyword '%s'",
                    skill.name,
                    trigger,
                )
                recalled_knowledge.append(
                    SkillKnowledge(
                        name=skill.name,
                        trigger=trigger,
                        content=skill.content,
                        location=skill.source,
                    )
                )
        if recalled_knowledge:
            formatted_skill_text = render_template(
                prompt_dir=str(PROMPT_DIR),
                template_name="skill_knowledge_info.j2",
                triggered_agents=recalled_knowledge,
            )
            if user_message_suffix:
                formatted_skill_text += "\n" + user_message_suffix
            return TextContent(text=formatted_skill_text), [
                k.name for k in recalled_knowledge
            ]

        if user_message_suffix:
            return TextContent(text=user_message_suffix), []
        return None

    def get_tool_use_suffix(
        self, file_path: str, skip_skill_names: list[str]
    ) -> tuple[TextContent, list[str]] | None:
        """将 ``PathTrigger`` 技能（“规则”）与所触及的文件路径匹配。

        :meth:`get_user_message_suffix` 基于路径的对应项。 返回渲染的规则内容和触发的
        规则，或None。
        ``skip_skill_names`` 抑制已注入的规则（重复数据删除）。
        """
        if not file_path:
            return None

        recalled_knowledge: list[SkillKnowledge] = []
        for skill in self.skills:
            if not isinstance(skill, Skill) or skill.name in skip_skill_names:
                continue
            if pattern := skill.match_path_trigger(file_path):
                logger.info(
                    "Rule '%s' triggered by path match '%s' for '%s'",
                    skill.name,
                    pattern,
                    file_path,
                )
                recalled_knowledge.append(
                    SkillKnowledge(
                        name=skill.name,
                        trigger=pattern,
                        content=skill.content,
                        location=skill.source,
                    )
                )

        if not recalled_knowledge:
            return None

        blocks = [
            "<EXTRA_INFO>\n"
            "The following rule applies because a file you touched matches "
            f'"{k.trigger}". Follow it when working with matching files.\n'
            + (f"Rule location: {k.location}\n" if k.location else "")
            + f"\n{k.content}\n</EXTRA_INFO>"
            for k in recalled_knowledge
        ]
        return TextContent(text="\n".join(blocks)), [k.name for k in recalled_knowledge]
