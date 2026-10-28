from __future__ import annotations

import os
import re
import sys
import threading
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Generator, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.context.condenser import CondenserBase
from openhands.sdk.context.prompts.presets import PromptPreset, create_registry
from openhands.sdk.context.prompts.prompt import render_template
from openhands.sdk.context.prompts.section import Platform, PromptContext
from openhands.sdk.critic.base import CriticBase
from openhands.sdk.llm import LLM
from openhands.sdk.llm.utils.model_prompt_spec import get_model_prompt_spec
from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.config import MCPServer
from openhands.sdk.mcp.tool import MCPToolDefinition, MCPToolExecutor
from openhands.sdk.tool import (
    BUILT_IN_TOOL_CLASSES,
    BUILT_IN_TOOLS,
    Tool,
    ToolDefinition,
    resolve_tool,
)
from openhands.sdk.tool.builtins import InvokeSkillTool
from openhands.sdk.tool.builtins.vision_inspect import (
    VisionInspectTool,
    has_vision_profile_available,
)
from openhands.sdk.utils.models import DiscriminatedUnionMixin
from openhands.sdk.utils.path import get_user_persistence_dir


if TYPE_CHECKING:
    from openhands.sdk.conversation import ConversationState, LocalConversation
    from openhands.sdk.conversation.types import (
        ConversationCallbackType,
        ConversationTokenCallbackType,
    )

logger = get_logger(__name__)


# -- SOUL.md 装载机 ------------------------------------------------------------------
# SOUL.md 是智能体的身份文件，``SOUL.md`` 在用户持久化目录下（~/.openhands/SOUL.md 不存
# 在 OH_PERSISTENCE_DIR）。 当存在时，它会替换系统中的默认身份提示词。
#

_SOUL_PATH = get_user_persistence_dir() / "SOUL.md"
_DEFAULT_SOUL = (
    "You are OpenHands agent, a helpful AI assistant that can interact"
    " with a computer to solve tasks."
)

# 内置提示词目录。 这里的注册表仅代表内置的提示词； 具有自己的提示的子类/保留 Jinja 渲染
# 路径。
#
_BUILTIN_PROMPT_DIR = os.path.realpath(
    os.path.join(os.path.dirname(__file__), "prompts")
)

# 内置 ``system_prompt_filename`` 值向后兼容哨兵值（.j2 文件已删除），用于选择注册表预设
# 。 ``system_prompt_planning.j2`` 保留其历史名称，因此 ``get_planning_agent`` 无需更改
# 。 任何其他文件名——或者子类自己的``prompt_dir``——都会落入 Jinja 逃生舱口。
#
_PRESET_BY_FILENAME: dict[str, PromptPreset] = {
    "system_prompt.j2": PromptPreset.DEFAULT,
    "system_prompt_planning.j2": PromptPreset.PLANNING,
}


def _load_soul_md() -> str:
    """从用户持久化目录加载 ``SOUL.md``，否则使用内置默认值。"""
    try:
        with open(_SOUL_PATH, encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            return content
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.debug("Could not read SOUL.md from %s: %s", _SOUL_PATH, exc)
    return _DEFAULT_SOUL


class AgentBase(DiscriminatedUnionMixin, ABC):
    """OpenHands 智能体的抽象基类。

    智能体是无状态的，应该由它们的配置完全定义。 该基类提供所有智能体实现都必须遵循的
    通用接口和功能。
    """

    model_config = ConfigDict(
        frozen=True,
        arbitrary_types_allowed=True,
    )

    llm: LLM = Field(
        ...,
        description="LLM configuration for the agent.",
        examples=[
            {
                "model": "litellm_proxy/openai/gpt-5.5",
                "base_url": "https://llm-proxy.eval.all-hands.dev",
                "api_key": "your_api_key_here",
            }
        ],
    )
    tools: list[Tool] = Field(
        default_factory=list,
        description="List of tools to initialize for the agent.",
        examples=[
            {"name": "TerminalTool", "params": {}},
            {"name": "FileEditorTool", "params": {}},
            {
                "name": "TaskTrackerTool",
                "params": {},
            },
        ],
    )
    mcp_config: dict[str, MCPServer] = Field(
        default_factory=dict,
        description="Optional MCP servers to expose as tools.",
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
    filter_tools_regex: str | None = Field(
        default=None,
        description="Optional regex to filter the tools available to the agent by name."
        " This is applied after any tools provided in `tools` and any MCP tools are"
        " added.",
        examples=["^(?!repomix)(.*)|^repomix.*pack_codebase.*$"],
    )
    include_default_tools: list[str] = Field(
        default_factory=lambda: [tool.__name__ for tool in BUILT_IN_TOOLS],
        description=(
            "List of default tool class names to include. By default, the agent "
            "includes 'FinishTool' and 'ThinkTool'. Set to an empty list to disable "
            "all default tools, or provide a subset to include only specific ones. "
            "Example: include_default_tools=['FinishTool'] to only include FinishTool, "
            "or include_default_tools=[] to disable all default tools."
        ),
        examples=[["FinishTool", "ThinkTool"], ["FinishTool"], []],
    )
    agent_context: AgentContext | None = Field(
        default=None,
        description="Optional AgentContext to initialize "
        "the agent with specific context.",
        examples=[
            {
                "skills": [
                    {
                        "name": "AGENTS.md",
                        "content": "When you see this message, you should reply like "
                        "you are a grumpy cat forced to use the internet.",
                        "type": "repo",
                    },
                    {
                        "name": "flarglebargle",
                        "content": (
                            "IMPORTANT! The user has said the magic word "
                            '"flarglebargle". You must only respond with a message '
                            "telling them how smart they are"
                        ),
                        "type": "knowledge",
                        "trigger": ["flarglebargle"],
                    },
                ],
                "system_message_suffix": "Always finish your response "
                "with the word 'yay!'",
                "user_message_prefix": "The first character of your "
                "response should be 'I'",
            }
        ],
    )
    system_prompt: str | None = Field(
        default=None,
        description=(
            "Inline system prompt string.  When provided, the agent uses this "
            "text verbatim as the system message instead of rendering from "
            "`system_prompt_filename`.  Mutually exclusive with a non-default "
            "`system_prompt_filename`.\n\n"
            "**Warning**: This is not recommended unless you know what you are "
            "doing (e.g. customising agent behaviour for a completely different "
            "task).  Setting this will override OpenHands' built-in system "
            "instructions that govern default agent behaviour."
        ),
    )
    system_prompt_filename: str = Field(
        default="system_prompt.j2",
        description=(
            "System prompt template filename. Can be either:\n"
            "- A relative filename (e.g., 'system_prompt.j2') loaded from the "
            "agent's prompts directory\n"
            "- An absolute path (e.g., '/path/to/custom_prompt.j2')"
        ),
    )
    security_policy_filename: str = Field(
        default="security_policy.j2",
        description=(
            "Security policy filename. The default 'security_policy.j2' is a "
            "back-compat sentinel (the file was removed) that selects the built-in "
            "default policy from the prompt registry -- it is not loaded from disk. "
            "Any other value names a custom policy file whose contents are inserted "
            "verbatim (NOT rendered as a Jinja template). Can be either:\n"
            "- A relative filename (e.g., 'custom_security_policy.md') loaded from "
            "the agent's prompts directory\n"
            "- An absolute path (e.g., '/path/to/custom_security_policy.md')\n"
            "- Empty string to disable security policy"
        ),
    )
    system_prompt_kwargs: dict[str, object] = Field(
        default_factory=dict,
        description="Optional kwargs to pass to the system prompt Jinja2 template.",
        examples=[{"cli_mode": True}],
    )

    @model_validator(mode="before")
    @classmethod
    def _validate_system_prompt_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if (
            "security_policy_filename" in data
            and data["security_policy_filename"] is None
        ):
            data["security_policy_filename"] = ""
        has_inline = data.get("system_prompt") is not None
        has_custom_filename = (
            "system_prompt_filename" in data
            and data["system_prompt_filename"] != "system_prompt.j2"
        )
        if has_inline and has_custom_filename:
            raise ValueError(
                "Cannot set both 'system_prompt' and a non-default "
                "'system_prompt_filename'. Use one or the other."
            )
        return data

    @field_validator("system_prompt_kwargs")
    @classmethod
    def _drop_retired_enable_browser(
        cls, value: dict[str, object]
    ) -> dict[str, object]:
        """旧保存的对话可能仍带有此已停用的提示词标志。"""
        return {key: item for key, item in value.items() if key != "enable_browser"}

    condenser: CondenserBase | None = Field(
        default=None,
        description="Optional condenser to use for condensing conversation history.",
        examples=[
            {
                "kind": "LLMSummarizingCondenser",
                "llm": {
                    "model": "litellm_proxy/openai/gpt-5.5",
                    "base_url": "https://llm-proxy.eval.all-hands.dev",
                    "api_key": "your_api_key_here",
                },
                "max_size": 80,
                "keep_first": 10,
            }
        ],
    )

    critic: CriticBase | None = Field(
        default=None,
        description=(
            "EXPERIMENTAL: Optional critic to evaluate agent actions and messages "
            "in real-time. API and behavior may change without notice. "
            "May impact performance, especially in 'all_actions' mode."
        ),
        examples=[{"kind": "AgentFinishedCritic"}],
    )

    tool_concurrency_limit: int = Field(
        default=1,
        ge=1,
        description=(
            "Maximum number of tool calls to execute concurrently within a single "
            "agent step. Default is 1 (sequential). Values > 1 enable parallel "
            "execution; concurrent tools share the conversation object, filesystem, "
            "and working directory, so mutations to shared state may race."
        ),
    )

    # 运行时物化工具； 私有且不可序列化
    _tools: dict[str, ToolDefinition] = PrivateAttr(default_factory=dict)
    _tools_lock: threading.RLock = PrivateAttr(default_factory=threading.RLock)
    _initialized: bool = PrivateAttr(default=False)

    @property
    def prompt_dir(self) -> str:
        """返回该类的模块文件所在的目录。"""
        module = sys.modules[self.__class__.__module__]
        module_file = module.__file__  # e.g. ".../mypackage/mymodule.py"
        if module_file is None:
            raise ValueError(f"Module file for {module} is None")
        return os.path.join(os.path.dirname(module_file), "prompts")

    @property
    def name(self) -> str:
        """返回智能体的名称。"""
        return self.__class__.__name__

    @property
    def _prompt_preset(self) -> PromptPreset | None:
        """注册表预设为此智能体的内置提示词。

        ``None`` 表示“乘坐 Jinja 逃生舱口”：具有自己的子类
        ``prompt_dir``，或不是已知内置哨兵值的 ``system_prompt_filename`` (e.g. 自定
        义相对名称或绝对路径）。
        """
        if os.path.realpath(self.prompt_dir) != _BUILTIN_PROMPT_DIR:
            return None
        return _PRESET_BY_FILENAME.get(self.system_prompt_filename)

    @property
    def static_system_message(self) -> str:
        """计算系统消息的静态部分。

        这仅返回基本系统提示词模板，没有任何动态的每次对话上下文。 该静态部分可以在对
        话中缓存和重用，以提高提示词缓存效率。

        内置提示词（``default`` 和 ``planning`` 预设）是从键入的部分注册表组装而成，
        这也解决了自定义
        ``security_policy_filename``. 逃生舱口保持神社路径：内联
        ``system_prompt`` 逐字使用，后面是加载工具的指导； 自定义
        ``system_prompt_filename`` 或子类
        ``prompt_dir`` 呈现其自己的模板。

        Returns:
            没有动态系统上下文的静态系统提示词。
        """
        if self.system_prompt is not None:
            return "\n\n".join((self.system_prompt, *self._tool_guidance()))

        # 逃生舱口：自定义文件名或子类自己的 prompt_dir 渲染自己的 Jinja 模板； 其他一切
        # （包括 custom policies) 使用注册表。
        #
        preset = self._prompt_preset
        if preset is None:
            return render_template(
                prompt_dir=self.prompt_dir,
                template_name=self.system_prompt_filename,
                **self._resolved_template_kwargs(),
            )

        return create_registry(preset).build(self._build_prompt_context()).static

    def _tool_guidance(self) -> tuple[str, ...]:
        """已加载工具的不同 ``prompt_guidance`` 文本（按工具顺序）。"""
        with self._tools_lock:
            tools = list(self._tools.values())
        return tuple(
            dict.fromkeys(t.prompt_guidance for t in tools if t.prompt_guidance)
        )

    def _resolved_template_kwargs(self) -> dict[str, object]:
        """解决 system-提示词模板 kwargs。

        共享者：pyattr:`static_system_message` 和
        :meth:`_build_prompt_context` 所以两者不能漂移。
        """
        template_kwargs = dict(self.system_prompt_kwargs)

        # 如果尚未提供，则加载 SOUL.md 身份
        if "soul_content" not in template_kwargs:
            template_kwargs["soul_content"] = _load_soul_md()

        template_kwargs.setdefault(
            "memory_enabled",
            self.agent_context is not None and self.agent_context.load_memory,
        )
        template_kwargs["security_policy_filename"] = self.security_policy_filename
        template_kwargs.setdefault("model_name", self.llm.model)
        if (
            "model_family" not in template_kwargs
            or "model_variant" not in template_kwargs
        ):
            spec = get_model_prompt_spec(self.llm.model, self.llm.model_canonical_name)
            if "model_family" not in template_kwargs and spec.family:
                template_kwargs["model_family"] = spec.family
            if "model_variant" not in template_kwargs and spec.variant:
                template_kwargs["model_variant"] = spec.variant
        return template_kwargs

    def _read_custom_security_policy(self) -> str | None:
        """自定义安全策略文件的原始内容——逐字插入，不
        渲染为 Jinja 模板。

        返回 ``None`` - 因此 ``SecuritySection`` 保留其内置默认策略
        -- 当 ``security_policy_filename`` 为默认哨兵值时
        ``"security_policy.j2"``（仅字符串； 该文件已被删除，因此永远不会被读取）或
        ``""``（空的*文件名*，这会禁用该策略）。 其内容
        为空的配置文件仍返回 ``""``（空的自定义策略），而不是 ``None``。

        相对名称解析为 ``prompt_dir``； 绝对路径按原样使用。
        """
        filename = self.security_policy_filename
        if not filename or filename == "security_policy.j2":
            return None
        return (Path(self.prompt_dir) / filename).read_text(encoding="utf-8")

    def _build_prompt_context(
        self,
        additional_secret_infos: list[dict[str, str | None]] | None = None,
    ) -> PromptContext:
        """冻结此智能体的：class:`PromptContext` 快照。

        ``template_kwargs`` 已通过共享解决
        ：方法：`_resolved_template_kwargs`； 其他字段快照
        每个对话信号。 动态层字段重用
        ``AgentContext._resolve_dynamic_data`` 因此技能是模型门控的，并且机密与
        ``get_system_message_suffix`` 完全一样地合并；
        ``additional_secret_infos`` 镜子 ``get_dynamic_context(state)``。
        """
        agent_context = self.agent_context
        # 镜像 get_dynamic_context'temp-上下文路径：无 agent_context 但对话机密目前，旧
        # 版渲染器默认解析 AgentContext()（默认情况下携带） current_datetime), 因此，其
        # 动态块通告了机密  *和* a <CURRENT_DATETIME>. 在这里解决相同的默认值，以便注册
        # 表复制两个块，而不是一个机密。
        #
        if agent_context is None and additional_secret_infos:
            agent_context = AgentContext()

        now: str | None = None
        skill_names: tuple[str, ...] = ()
        secret_names: tuple[str, ...] = ()
        repo_skills: tuple[tuple[str, str], ...] = ()
        available_skills_prompt: str | None = None
        custom_suffix: str | None = None
        memory_context: str | None = None
        secret_infos: tuple[tuple[str, str | None], ...] = ()

        if agent_context is not None:
            data = agent_context._resolve_dynamic_data(
                self.llm.model,
                self.llm.model_canonical_name,
                additional_secret_infos,
            )
            # 重用共享解析器的格式化日期时间而不是重新派生
            # it: get_system_message_suffix 渲染这个确切的字符串，所以注册表
            # 也必须（对于传递日期时间对象而不是预格式化字符串的调用者来说，四舍五入的副
            # 本会破坏字节对字节的奇偶校验）。
            #
            now = data.formatted_datetime
            skill_names = tuple(skill.name for skill in agent_context.skills)
            repo_skills = tuple((s.name, s.content) for s in data.repo_skills)
            available_skills_prompt = data.available_skills_prompt or None
            custom_suffix = agent_context.system_message_suffix or None
            memory_context = agent_context.memory_context or None
            secret_infos = tuple(
                (info["name"] or "", info["description"]) for info in data.secret_infos
            )
            # 从解析器的合并 secret_infos 派生名称，而不是第二个 get_secret_infos() 遍历
            # ； 现在包括注册表提供的机密 (additional_secret_infos)，与 <CUSTOM_SECRETS>
            #  显示的内容相匹配。
            #
            secret_names = tuple(name for name, _ in secret_infos if name)

        template_kwargs = self._resolved_template_kwargs()
        # SecuritySection 的自定义安全策略内容（仅限注册表路径）。
        policy_content = self._read_custom_security_policy()
        if policy_content is not None:
            template_kwargs = {
                **template_kwargs,
                "security_policy_content": policy_content,
            }

        return PromptContext(
            template_kwargs=template_kwargs,
            tool_names=tuple(t.name for t in self.tools),
            tool_guidance=self._tool_guidance(),
            platform=Platform.current(),
            working_dir=None,
            now=now,
            skill_names=skill_names,
            secret_names=secret_names,
            repo_skills=repo_skills,
            available_skills_prompt=available_skills_prompt,
            custom_suffix=custom_suffix,
            memory_context=memory_context,
            secret_infos=secret_infos,
        )

    @property
    def dynamic_context(self) -> str | None:
        """获取会话级别的动态上下文。

        这将返回在对话之间变化的上下文，例如：
        - 存储库信息和技能
        - 运行时信息（主机，工作目录）
        - 用户特定的机密和设置
        - 对话说明

        此内容应不包含在缓存系统提示词中，以启用跨会话缓存共享。 相反，它作为系统消息
        内的第二个内容块（没有缓存标记）发送。

        从默认注册表的动态层部分组装。

        Returns:
            动态上下文字符串，如果未配置上下文，则为 None。
        """
        if not self.agent_context:
            return None
        # 动态层是独立于预设的，因此自定义 Jinja 模板（预设 None）仍然获得默认动态块，与
        # 以前完全相同。
        #
        preset = self._prompt_preset or PromptPreset.DEFAULT
        return create_registry(preset).build(self._build_prompt_context()).dynamic

    def init_state(
        self,
        state: ConversationState,
        on_event: ConversationCallbackType,  # noqa: ARG002
    ) -> None:
        """初始化空对话状态，为用户准备智能体
        消息。

        通常这涉及添加系统消息

        NOTE: 状态将就地突变。
        """
        self._initialize(state)

    def _initialize(
        self,
        state: ConversationState,
    ):
        """从 AgentSpec 创建一个 AgentBase 实例。"""

        if self._initialized:
            return

        tools: list[ToolDefinition] = []

        # 使用 ThreadPoolExecutor 并行化工具解析
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []

            # 提交工具解析任务
            for tool_spec in self.tools:
                future = executor.submit(resolve_tool, tool_spec, state)
                futures.append(future)

            # 完成后收集结果
            for future in futures:
                result = future.result()
                tools.extend(result)

        logger.info("Loaded %d tools from spec", len(tools))
        if self.filter_tools_regex:
            pattern = re.compile(self.filter_tools_regex)
            tools = [tool for tool in tools if pattern.match(tool.name)]
            logger.info("Filtered to %d tools after applying regex filter", len(tools))

        # 包括include_default_tools中的默认工具； 不受正则表达式过滤的影响。 使用显式映
        # 射来解析工具类名称。 自动附加 `InvokeSkillTool` 当且仅当 AgentSkills 格式的技
        # 能可直接调用并且用户尚未明确选择加入。
        #
        has_invocable_agentskills = bool(
            self.agent_context
            and any(
                s.is_agentskills_format and not s.disable_model_invocation
                for s in self.agent_context.skills
            )
        )
        default_tool_names = list(self.include_default_tools)
        if (
            has_invocable_agentskills
            and InvokeSkillTool.__name__ not in default_tool_names
        ):
            default_tool_names.append(InvokeSkillTool.__name__)
            logger.debug(
                "Auto-attached %s (invocable AgentSkills-format skill present)",
                InvokeSkillTool.__name__,
            )
        if (
            not self.llm.vision_is_active()
            and VisionInspectTool.__name__ not in default_tool_names
            and has_vision_profile_available()
        ):
            default_tool_names.append(VisionInspectTool.__name__)
            logger.debug(
                "Auto-attached %s (vision profile available for non-vision model)",
                VisionInspectTool.__name__,
            )

        for tool_name in default_tool_names:
            tool_class = BUILT_IN_TOOL_CLASSES.get(tool_name)
            if tool_class is None:
                raise ValueError(
                    f"Unknown built-in tool class: '{tool_name}'. "
                    f"Expected one of: {list(BUILT_IN_TOOL_CLASSES.keys())}"
                )
            tool_instances = tool_class.create(state)
            tools.extend(tool_instances)

        # 检查工具类型
        for tool in tools:
            if not isinstance(tool, ToolDefinition):
                raise ValueError(
                    f"Tool {tool} is not an instance of 'ToolDefinition'. "
                    f"Got type: {type(tool)}"
                )

        # 检查姓名重复
        tool_names = [tool.name for tool in tools]
        if len(tool_names) != len(set(tool_names)):
            duplicates = set(name for name in tool_names if tool_names.count(name) > 1)
            raise ValueError(f"Duplicate tool names found: {duplicates}")

        # 将工具存储在字典中以便于访问
        self._tools = {tool.name: tool for tool in tools}
        self._initialized = True

    @abstractmethod
    def step(
        self,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
        on_token: ConversationTokenCallbackType | None = None,
    ) -> None:
        """谈话中迈出了一步。

        通常这涉及：
        1. 拨打 LLM 电话
        2. 执行工具
        3. 使用 LLM 调用 (role="assistant") 和工具结果 (role="tool") 更新对话状态
        4.1 如果对话结束，将state.execution_status设置为FINISHED 4.2 否则，返回，对话
        将开始下一步

        如果底层 LLM 支持流式传输，则部分增量将转发到
        ``on_token`` 在返回完整响应之前。

        NOTE: 状态将就地突变。
        """

    async def astep(
        self,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
        on_token: ConversationTokenCallbackType | None = None,
    ) -> None:
        """异步：meth:`step` 的变体。

        默认实现通过：func:`asyncio.loop.run_in_executor` 在线程中运行同步 ``step()``
        ，以便阻塞工具 I/O 不会导致
        事件循环匮乏。 执行异步 LLM 调用的子类应该覆盖它。
        """
        import asyncio

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.step, conversation, on_event, on_token)

    def verify(
        self,
        persisted: AgentBase,
        events: Sequence[Any] | None = None,  # noqa: ARG002
    ) -> AgentBase:
        """验证我们是否可以从已持久化状态恢复此智能体。

        我们不会合并已持久化和运行时智能体实例之间的配置。 相反，我们验证兼容性要求，
        然后
        continue with the runtime-provided Agent.

        兼容性要求：
        - 智能体类别/类型必须匹配。
        - 工具只能添加，不能删除。

        删除工具会破坏向后兼容性，因为 LLM 可能已经被告知它们。 添加新工具是安全的 -
        LLM 只是在下一轮获得新功能。

        所有其他配置（LLM、agent_context、上下文压缩器等）都可以在会话之间自由更改。

        Args:
            persisted: 智能体从已持久化状态加载。
            events: 未使用，保留用于 API 兼容性。

        Returns:
            如果验证通过，则运行时智能体（自身）。

        Raises:
            ValueError: 如果智能体类或工具不匹配。
        """
        if persisted.__class__ is not self.__class__:
            raise ValueError(
                "Cannot load from persisted: persisted agent is of type "
                f"{persisted.__class__.__name__}, but self is of type "
                f"{self.__class__.__name__}."
            )

        # 收集明确的工具名称
        runtime_names = {tool.name for tool in self.tools}
        persisted_names = {tool.name for tool in persisted.tools}

        # 从 include_default_tools 添加内置工具名称这些是运行时名称，例如“finish”、“
        # think”
        #
        for tool_class_name in self.include_default_tools:
            tool_class = BUILT_IN_TOOL_CLASSES.get(tool_class_name)
            if tool_class is not None:
                runtime_names.add(tool_class.name)

        for tool_class_name in persisted.include_default_tools:
            tool_class = BUILT_IN_TOOL_CLASSES.get(tool_class_name)
            if tool_class is not None:
                persisted_names.add(tool_class.name)

        # 删除工具会破坏向后兼容性，因为 LLM 可能已经被告知它们。 添加新工具是安全的 -
        # LLM 只是在下一轮获得新功能。
        #
        missing_in_runtime = persisted_names - runtime_names
        if missing_in_runtime:
            raise ValueError(
                f"Cannot resume conversation: tools were removed mid-conversation "
                f"(removed: {sorted(missing_in_runtime)}). "
                f"To use different tools, start a new conversation."
            )

        return self

    def get_all_llms(self) -> Generator[LLM]:
        """递归地生成可从 `self` 访问的唯一 * 基类 * LLM 对象。

        - 返回实际对象引用（而不是副本）。
        - 按 `id(LLM)` 进行重复数据删除。
        - 通过 *all* 遍历对象的访问集实现循环安全。
        - 只返回类型为 `LLM`（无子类）的对象。
        - 不处理数据类。
        """
        yielded_ids: set[int] = set()
        visited: set[int] = set()

        def _walk(obj: object) -> Iterable[LLM]:
            oid = id(obj)
            # 防止我们可能递归的任何事情发生循环
            if oid in visited:
                return ()
            visited.add(oid)

            # 遍历 LLM 类及其字段 e.g，LLMRouter 是 LLM 的子类，但其字段中包含 LLM
            #
            if isinstance(obj, LLM):
                llm_out: list[LLM] = []

                # 仅产生 *raw* 基类 LLM（不包括子类）
                if type(obj) is LLM and oid not in yielded_ids:
                    yielded_ids.add(oid)
                    llm_out.append(obj)

                # 遍历LLM个对象的所有字段
                for name in type(obj).model_fields:
                    try:
                        val = getattr(obj, name)
                    except Exception:
                        continue
                    llm_out.extend(_walk(val))
                return llm_out

            # Pydantic 模型：迭代声明的字段
            if isinstance(obj, BaseModel):
                model_out: list[LLM] = []
                for name in type(obj).model_fields:
                    try:
                        val = getattr(obj, name)
                    except Exception:
                        continue
                    model_out.extend(_walk(val))
                return model_out

            # 内置容器
            if isinstance(obj, dict):
                dict_out: list[LLM] = []
                for k, v in obj.items():
                    dict_out.extend(_walk(k))
                    dict_out.extend(_walk(v))
                return dict_out

            if isinstance(obj, (list, tuple, set, frozenset)):
                container_out: list[LLM] = []
                for item in obj:
                    container_out.extend(_walk(item))
                return container_out

            # 未知对象类型：无事可做
            return ()

        # 从 self 驱动遍历
        yield from _walk(self)

    def _close_tool_executor(self, tool: ToolDefinition) -> None:
        try:
            executable_tool = tool.as_executable()
            executable_tool.executor.close()
        except NotImplementedError:
            return
        except Exception as exc:
            logger.warning("Error closing executor for tool '%s': %s", tool.name, exc)

    def add_runtime_tools(self, tools: Sequence[ToolDefinition]) -> None:
        """注册运行时实现的工具（e.g. MCP 工具）。

        工具受`filter_tools_regex`约束； 内置默认工具是豁免的，与 `_initialize()` 的
        行为相匹配。
        """
        if not self._initialized:
            logger.warning(
                "add_runtime_tools called before agent initialization; "
                "tools will not be registered"
            )
            return
        for tool in tools:
            if not isinstance(tool, ToolDefinition):
                raise ValueError(
                    f"Tool {tool} is not an instance of 'ToolDefinition'. "
                    f"Got type: {type(tool)}"
                )

        if self.filter_tools_regex:
            pattern = re.compile(self.filter_tools_regex)
            builtin_classes = tuple(BUILT_IN_TOOL_CLASSES.values())
            num_tools = len(tools)
            tools = [
                tool
                for tool in tools
                if isinstance(tool, builtin_classes) or pattern.match(tool.name)
            ]
            if len(tools) != num_tools:
                logger.info(
                    "Filtered runtime tools from %d to %d after applying regex filter",
                    num_tools,
                    len(tools),
                )

        tool_names = [tool.name for tool in tools]
        if len(tool_names) != len(set(tool_names)):
            duplicates = {
                name for name, count in Counter(tool_names).items() if count > 1
            }
            raise ValueError(f"Duplicate runtime tool names found: {duplicates}")
        with self._tools_lock:
            # 工具/list_changed 通知可能会与调用者发生竞争：如果通知在提供者的初始请求期
            # 间到达 create_tools() 仍然在进行中 _on_mcp_tools_changed/
            # _on_mcp_tools_reconciled 可能之前通过同一个客户端已经安装了相同的工具
            # add_runtime_tools() 调用 (使用客户端返回的快照) 到这里。 将它视为刷新，而
            # 不是冲突，与使用的同一客户端豁免一致 _on_mcp_tools_changed/
            # _on_mcp_tools_reconciled.
            #
            conflicts: set[str] = set()
            for tool in tools:
                existing_tool = self._tools.get(tool.name)
                if existing_tool is None:
                    continue
                existing_executor = existing_tool.executor
                replacement_executor = tool.executor
                if (
                    isinstance(existing_executor, MCPToolExecutor)
                    and isinstance(replacement_executor, MCPToolExecutor)
                    and existing_executor.client is replacement_executor.client
                ):
                    continue
                conflicts.add(tool.name)
            if conflicts:
                raise ValueError(f"Duplicate tool names found: {conflicts}")

            # AgentBase 已冻结； 替换工具图而不是就地改变它，因此 Agent.model_copy() 快
            # 照不共享状态。
            #
            updated = {**self._tools, **{tool.name: tool for tool in tools}}
            object.__setattr__(self, "_tools", updated)

    def _on_mcp_tools_changed(self, tools: Sequence[ToolDefinition]) -> None:
        """处理动态广告的 MCP 工具。

        当 MCP 服务器发送 ``notifications/tools/list_changed``（渐进式披露，e.g）时，
        在 MCP 客户端的后台事件循环线
        程上调用。 Datadog 的托管 MCP 服务器）。 注册新工具并刷新删除后返回的同客户端
        工具。
        """
        if not self._initialized:
            logger.warning(
                "MCP tools/list_changed received before agent initialization; "
                "skipping registration of %d tools",
                len(tools),
            )
            return
        tool_names = [tool.name for tool in tools]
        if len(tool_names) != len(set(tool_names)):
            duplicates = {
                name for name, count in Counter(tool_names).items() if count > 1
            }
            raise ValueError(f"Duplicate MCP tool names found: {duplicates}")

        with self._tools_lock:
            additions: list[ToolDefinition] = []
            replacements: list[ToolDefinition] = []
            conflicts: set[str] = set()
            for tool in tools:
                existing = self._tools.get(tool.name)
                if existing is None:
                    additions.append(tool)
                    continue

                existing_executor = existing.executor
                replacement_executor = tool.executor
                if (
                    isinstance(existing_executor, MCPToolExecutor)
                    and isinstance(replacement_executor, MCPToolExecutor)
                    and existing_executor.client is replacement_executor.client
                ):
                    replacements.append(tool)
                else:
                    conflicts.add(tool.name)

            if conflicts:
                raise ValueError(
                    "Dynamically advertised MCP tools conflict with existing runtime "
                    f"tools: {sorted(conflicts)}"
                )

            self.add_runtime_tools(additions)
            if replacements:
                updated = {
                    **self._tools,
                    **{tool.name: tool for tool in replacements},
                }
                object.__setattr__(self, "_tools", updated)

        if additions:
            logger.info(
                "Registered %d dynamically advertised MCP tools: %s",
                len(additions),
                ", ".join(tool.name for tool in additions),
            )
        if replacements:
            logger.info(
                "Refreshed %d dynamically advertised MCP tools: %s",
                len(replacements),
                ", ".join(tool.name for tool in replacements),
            )

    def _on_mcp_tools_reconciled(
        self,
        client: MCPClient,
        tools: Sequence[MCPToolDefinition],
    ) -> None:
        """将此 MCP 客户端的工具替换为其当前服务器快照。"""
        tool_names = [tool.name for tool in tools]
        if len(tool_names) != len(set(tool_names)):
            duplicates = {
                name for name, count in Counter(tool_names).items() if count > 1
            }
            raise ValueError(f"Duplicate MCP tool names found: {duplicates}")

        if self.filter_tools_regex:
            pattern = re.compile(self.filter_tools_regex)
            tools = [tool for tool in tools if pattern.match(tool.name)]
            tool_names = [tool.name for tool in tools]

        with self._tools_lock:
            owned_names = {
                name
                for name, tool in self._tools.items()
                if isinstance(tool.executor, MCPToolExecutor)
                and tool.executor.client is client
            }
            conflicts = (set(tool_names) & set(self._tools)) - owned_names
            if conflicts:
                raise ValueError(
                    "Dynamically advertised MCP tools conflict with existing runtime "
                    f"tools: {sorted(conflicts)}"
                )

            reconciled = {
                name: tool
                for name, tool in self._tools.items()
                if name not in owned_names
            }
            reconciled.update((tool.name, tool) for tool in tools)
            object.__setattr__(self, "_tools", reconciled)

    @property
    def tools_map(self) -> dict[str, ToolDefinition]:
        """获取初始化的工具图。
        Raises:
            RuntimeError: 如果智能体尚未初始化。
        """
        if not self._initialized:
            raise RuntimeError("Agent not initialized; call _initialize() before use")
        # 将读者与后台 MCP 工具更新隔离。
        with self._tools_lock:
            return dict(self._tools)

    # -- 能力帮手 -----------------------------------------------------------
    # 下游代码应该在这些属性上分支而不是这样做
    # ``isinstance(agent, ACPAgent)`` 检查。 这使得常规/ACP代码路径与具体的类层次结构分
    # 离。
    #

    @property
    def supports_openhands_tools(self) -> bool:
        """``True`` 如果 OpenHands 可以向此智能体注入工具。

        ``False`` for :class:`~openhands.sdk.agent.acp_agent.ACPAgent` — ACP 服务器管
        理自己的工
        具集。
        """
        return True

    @property
    def supports_openhands_mcp(self) -> bool:
        """``True`` 如果 OpenHands 可以为此智能体创建进程内 MCP 工具。

        ``False`` for :class:`~openhands.sdk.agent.acp_agent.ACPAgent` — ACP 智能体将
        配置的
        MCP 服务器传递到 ACP 子进程。
        """
        return True

    @property
    def supports_condenser(self) -> bool:
        """``True`` 如果智能体支持 OpenHands 上下文压缩。

        ``False`` for :class:`~openhands.sdk.agent.acp_agent.ACPAgent` — ACP 服务器管
        理它自己的
        上下文窗口。
        """
        return True

    @property
    def agent_kind(self) -> Literal["openhands", "acp"]:
        """智能体类型，与 ``agent_kind`` 设置鉴别器匹配。"""
        return "openhands"

    def ask_agent(self, question: str) -> str | None:  # noqa: ARG002
        """无状态问答的可选覆盖。

        子类 (e.g. ACPAgent 可以在此处进行修改，以提供自己的实现 ask_agent，该实现绕
        过了默认的 LLM 基于路径。

        Returns:
            响应字符串，或 ``None`` 以使用默认的基于 LLM 的方法。
        """
        return None

    def close(self) -> None:
        """清理智能体资源。

        默认无操作； ACPAgent 会终止子进程。
        """
        pass
