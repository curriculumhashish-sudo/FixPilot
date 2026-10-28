import asyncio
import atexit
import contextlib
import copy
import json
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePath
from typing import Any, Final, TypeGuard, cast

from openhands.sdk.agent.acp_agent import ACPAgent
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.agent.stream_context import StreamProgressCallbackType
from openhands.sdk.context.condenser import CondenserBase, LLMSummarizingCondenser
from openhands.sdk.context.memory import load_memory
from openhands.sdk.context.prompts.prompt import render_template
from openhands.sdk.conversation.base import BaseConversation
from openhands.sdk.conversation.cancellation import CancellationToken
from openhands.sdk.conversation.event_store import EventLog
from openhands.sdk.conversation.exceptions import ConversationRunError
from openhands.sdk.conversation.secret_registry import SecretValue
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.conversation.stuck_detector import StuckDetector
from openhands.sdk.conversation.title_utils import generate_conversation_title
from openhands.sdk.conversation.types import (
    ConversationCallbackType,
    ConversationID,
    ConversationTokenCallbackType,
    StuckDetectionThresholds,
    TraceMetadataValue,
)
from openhands.sdk.conversation.visualizer import (
    ConversationVisualizerBase,
    DefaultConversationVisualizer,
)
from openhands.sdk.credential import CredentialBindingError
from openhands.sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    CondensationRequest,
    Event,
    EventID,
    InterruptEvent,
    MessageEvent,
    ObservationEvent,
    PauseEvent,
    UserRejectObservation,
)
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.event.error_classification import AGENT_OUTCOME
from openhands.sdk.hooks import HookConfig, HookEventProcessor, create_hook_callback
from openhands.sdk.io import FileStore, LocalFileStore
from openhands.sdk.llm import LLM, Message, TextContent, content_to_str
from openhands.sdk.llm.auth.openai import create_subscription_llm_from_config
from openhands.sdk.llm.call_context import LLMCallContext, llm_call_context_scope
from openhands.sdk.llm.exceptions import LLMAuthenticationError
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.llm.llm_registry import LLMRegistry
from openhands.sdk.logger import get_logger
from openhands.sdk.marketplace.registry import MarketplaceRegistry
from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.config import (
    MCPServer,
    enabled_mcp_servers,
)
from openhands.sdk.mcp.tool import MCPToolDefinition
from openhands.sdk.mcp.utils import (
    DefaultMCPToolProvider,
    MCPToolProvider,
    ToolsChangedCallback,
    ToolsReconciledCallback,
    provider_supports_on_tools_reconciled,
)
from openhands.sdk.observability.laminar import (
    OPERATION_METADATA_KEY,
    observe,
    record_tool_result,
)
from openhands.sdk.observability.utils import extract_action_name
from openhands.sdk.plugin import (
    Plugin,
    PluginSource,
    ResolvedPluginSource,
    fetch_plugin_with_resolution,
    load_available_plugins,
)
from openhands.sdk.secret import StaticSecret
from openhands.sdk.security.analyzer import SecurityAnalyzerBase
from openhands.sdk.security.confirmation_policy import (
    ConfirmationPolicyBase,
)
from openhands.sdk.skills import (
    Skill,
    load_available_skills,
    load_marketplace_standalone_skills,
    merge_skills_by_name,
)
from openhands.sdk.skills.utils import (
    expand_mcp_servers,
    expand_variable_references,
)
from openhands.sdk.subagent import (
    AgentDefinition,
    register_file_agents,
    register_plugin_agents,
)
from openhands.sdk.tool import ToolDefinition
from openhands.sdk.tool.builtins import InvokeSkillTool
from openhands.sdk.tool.client_tool import ClientToolSpec
from openhands.sdk.tool.schema import Action, Observation
from openhands.sdk.utils.cipher import Cipher
from openhands.sdk.utils.deprecation import warn_deprecated
from openhands.sdk.workspace import LocalWorkspace


logger = get_logger(__name__)

ACP_LAST_PROMPT_USER_MESSAGE_ID = "acp_last_prompt_user_message_id"
ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID = "acp_inflight_prompt_user_message_id"
ACP_SUPERSEDE_INFLIGHT_PROMPT = "acp_supersede_inflight_prompt"
_RUNTIME_MCP_TIMEOUT_SECS = 30

ACP_STOP_HOOK_FEEDBACK_PREFIX = "[Stop hook feedback]"

ASK_AGENT_LLM_USAGE_ID: Final[str] = "ask-agent-llm"


def _agent_already_surfaced_error(events: Sequence[Event], since: int = 0) -> bool:
    """智能体自己的步骤是否已发出类型化的 ConversationErrorEvent。

    ACPAgent 详细且分类的 ``ConversationErrorEvent`` (``source="agent"``从其 step/
    init 后重新抛出，从
    而导致运行循环被销毁。 缺少这个守卫，运行循环的通用性就会受到影响 ``except`` 将发
    出一个第二轮，不那么具象的事件（
    ``code=type(exc).__name__``, ``detail=str(exc)``) 作为 *最新* 错误 —— 重写入智能
    体最频繁出现错误的客户端。
     Regular 智能体永远不要自我上报（它们的所有错误事件都已经被上报）
    ``source="environment"``)，因此仅抑制 ACP 重复项。

    ``since`` 应该是当前开始时存在的事件数
    ``run()``/``arun()`` call. 将扫描限定为添加的事件 *在本次运行中* 阻止了源="的过时
    源智能体在同一个对话中，从先前运行中抑制无关异常的
    错误事件。
    """
    latest = _latest_conversation_error(events, since)
    return latest is not None and latest.source == "agent"


def _latest_conversation_error(
    events: Sequence[Event], since: int = 0
) -> ConversationErrorEvent | None:
    """返回当前运行期间发出的最新对话错误。"""
    for i in range(len(events) - 1, since - 1, -1):
        event = events[i]
        if isinstance(event, ConversationErrorEvent):
            return event
    return None


def _is_acp_prompt_message(event: Event) -> TypeGuard[MessageEvent]:
    if not isinstance(event, MessageEvent):
        return False
    if event.source == "user":
        return True
    if event.source != "environment" or event.llm_message.role != "user":
        return False
    return any(
        part.startswith(ACP_STOP_HOOK_FEEDBACK_PREFIX)
        for part in content_to_str(event.llm_message.content)
    )


def _copy_event_for_fork(event: Event) -> Event:
    # 镜像已持久化事件加载并跳过仅运行时的字段，例如执行器。
    return Event.model_validate_json(event.model_dump_json(exclude_none=True))


def _same_llm_config(a: LLM, b: LLM) -> bool:
    """返回是否两个 LLMs  序列化相同的配置， 机密 included."""
    if a is b:
        return True
    context = {"expose_secrets": True}
    return a.model_dump(mode="json", context=context) == b.model_dump(
        mode="json", context=context
    )


class LocalConversation(BaseConversation):
    agent: AgentBase
    workspace: LocalWorkspace
    _state: ConversationState
    _visualizer: ConversationVisualizerBase | None
    _on_event: ConversationCallbackType
    _on_token: ConversationTokenCallbackType | None
    _on_stream: StreamProgressCallbackType | None
    max_iteration_per_run: int
    _stuck_detector: StuckDetector | None
    llm_registry: LLMRegistry
    _cleanup_initiated: bool
    _cleanup_complete: bool
    _hook_processor: HookEventProcessor | None
    delete_on_close: bool = True
    _arun_task: asyncio.Task[None] | None
    _cancel_token: CancellationToken | None
    # True while run()/arun() 在保持状态锁的同时执行智能体步骤。 状态突变工具（e.g.
    # switch_llm) 在工作线程线程上运行，因此它必须跳过重新获取运行循环在等待该工具时被阻
    # 止的锁 (#3485)。
    #
    _step_holds_state_lock: bool
    # 插件延迟加载状态
    _plugin_specs: list[PluginSource] | None
    _resolved_plugins: list[ResolvedPluginSource] | None
    _plugins_loaded: bool
    _pending_hook_config: HookConfig | None  # 钩子配置与插件钩子结合
    _mcp_tool_provider: MCPToolProvider
    _mcp_config_from_parent: bool
    _llm_call_context: LLMCallContext

    def __init__(
        self,
        agent: AgentBase | None,
        workspace: str | Path | LocalWorkspace,
        plugins: list[PluginSource] | None = None,
        persistence_dir: str | Path | None = None,
        conversation_id: ConversationID | None = None,
        callbacks: list[ConversationCallbackType] | None = None,
        token_callbacks: list[ConversationTokenCallbackType] | None = None,
        hook_config: HookConfig | None = None,
        max_iteration_per_run: int = 500,
        stuck_detection: bool = True,
        stuck_detection_thresholds: (
            StuckDetectionThresholds | Mapping[str, int] | None
        ) = None,
        visualizer: (
            type[ConversationVisualizerBase] | ConversationVisualizerBase | None
        ) = DefaultConversationVisualizer,
        secrets: Mapping[str, SecretValue] | None = None,
        delete_on_close: bool = True,
        cipher: Cipher | None = None,
        tags: dict[str, str] | None = None,
        user_id: str | None = None,
        client_tools: list[ClientToolSpec] | None = None,
        observability_metadata: dict[str, TraceMetadataValue] | None = None,
        observability_tags: list[str] | None = None,
        # 添加到末尾以避免改变任何现有位置参数的位置。
        #
        max_budget_per_run: float | None = None,
        observability_span_name: str = "conversation",
        observability_parent_span_context: str | None = None,
        prompt_cache_key: str | None = None,
        file_store: FileStore | None = None,
        mcp_tool_provider: MCPToolProvider | None = None,
        profile_store_dir: str | Path | None = None,
        stream_callbacks: list[StreamProgressCallbackType] | None = None,
        _parent_llm_call_context: LLMCallContext | None = None,
        _mcp_config_from_parent: bool = False,
        **_: object,
    ):
        """初始化对话。

        Args:
            agent: 用于对话的智能体。
            workspace: 工作目录用于智能体操作和工具执行。
                可以是字符串路径、Path 对象或 LocalWorkspace 实例。
            plugins: 要加载的可选插件列表。 每个插件都有指定
                带有源（GitHub：所有者/存储库、git URL 或本地路径）、可选引用（分支/
                标签/提交）和用于 monorepos 的可选
                repo_path。 插件按照这些合并的顺序加载
                semantics: 按名称覆盖技能（最后获胜），MCP 配置
                按键覆盖（最后获胜），挂钩连接（全部运行）。
            persistence_dir: 用于持久会话状态和事件的目录。
                可以是字符串路径或 Path 对象。 当提供 file_store 时，该值仍用于派生环
                境观测结果路径。
            conversation_id: 对话的可选 ID。 如果提供，将
                      用于识别对话。 用户可能希望为其持久文件存储添加此 ID 的后缀。
            callbacks: 用于处理事件的回调函数的可选列表
            token_callbacks: 为流式传输增量调用的回调的可选列表
            stream_callbacks: 使用回调调用的可选列表
                由 ``StreamContext`` 生成的流进度帧。
            hook_config: 用于自动连接会话挂钩的可选挂钩配置。
                如果加载插件，它们的钩子将与此配置结合起来。
            max_iteration_per_run: 每次运行的最大迭代次数
            visualizer: 可视化配置。 可以是：
                       - ConversationVisualizerBase 子类：要实例化的类（默认值：
                       ConversationVisualizer）
                       - ConversationVisualizerBase 实例：使用自定义可视化工具
                       - None: 无可视化
            stuck_detection: 是否启用卡顿检测
            stuck_detection_thresholds: 卡住检测的可选配置
                      阈值。 可以是 StuckDetectionThresholds 实例或带有键的字典：“
                      action_observation”、
                      “action_error”、“monologue”、“alternating_pattern”。 值是表示触
                      发前重复次数的整数
                      。
            cipher: 用于加密/解密已持久化中的机密的可选密码
                   状态。 如果提供，则机密在保存时加密，在加载时解密。 如果未提供，机
                   密将在序列化上为已脱敏（丢失）。
            tags: 对话的可选键值标签。 钥匙必须是
                  小写字母数字，值最多 256 个字符。
            user_id: 与可观察性跟踪关联的可选用户 ID
            client_tools: 客户定义的工具规格的可选列表。 各规格
                  已注册并注入到智能体中，以便它可以调用该工具； 执行器返回一个确认，
                  真正的执行预计由回调/消费者（e.g. 前端）观察发出的Action
                  Event。
            observability_metadata: 可观察性后端的可选跟踪元数据。
            observability_tags: 用于可观察性后端的可选根跨度标签。
            observability_span_name: 用于可观察性的可选子跨度名称
                  后端。 根跨度仍命名为“conversation”。
            prompt_cache_key: 覆盖提示词-缓存分片键。 默认值
                到对话自己的 ID。 子对话将其设置为父对话的 ID 以共享相同的缓存分片。
            file_store: 可选 FileStore 用于对话状态，EventLog
                持久化。 如果提供，则其优先于状态 persistence_dir 和存储 EventLog。
            _parent_llm_call_context: 由内部继承的运行时 LLM 上下文
                孩子的谈话。 会话本地身份始终会被替换。
            _mcp_config_from_parent: 智能体的``mcp_config``已解决
                委托父级的配置。 它按原样使用：没有插件 MCP 服务器合并到其中，也没有
                ``${VAR}`` 再次扩展。
            profile_store_dir: 包含已保存的 LLM 配置文件的可选目录。
                默认为 ``~/.openhands/profiles``。
        """
        super().__init__()  # 使用跨度跟踪进行初始化
        # 将清理标记为尽早启动，以避免在解释器关闭期间发生争用或部分初始化的实例。
        #
        self._cleanup_initiated = False
        self._cleanup_complete = False
        self._arun_task = None
        self._cancel_token = None
        self._step_holds_state_lock = False

        # 存储延迟加载的插件规范（构造函数中没有 IO） 插件将在第一次 run() 或
        # send_message() 调用时加载
        #
        self._plugin_specs = plugins
        self._resolved_plugins = None
        self._plugins_loaded = False
        self._pending_hook_config = hook_config  # 将与插件挂钩结合
        self._agent_ready = False  # 智能体插件加载后延迟初始化
        self._mcp_tool_provider = mcp_tool_provider or DefaultMCPToolProvider()
        self._mcp_config_from_parent = _mcp_config_from_parent

        # 创建或恢复：工厂检查 BASE_STATE 来决定
        desired_id = conversation_id or uuid.uuid4()
        self._llm_call_context = (
            _parent_llm_call_context or LLMCallContext()
        ).for_conversation(
            str(desired_id),
            prompt_cache_key=prompt_cache_key,
        )

        # 解析客户端定义的工具，然后注册它们并将匹配的工具规范注入到智能体中，以便智能体
        # 可以调用它们。 执行被推迟到发出的 ActionEvent (e.g. 前端）； 执行者仅确认。 规
        # 格来自呼叫者 (`client_tools`)，或者在恢复已持久化对话而不重新提供规格时，
        #
        # from the persisted agent's tool specs — mirroring the server resume
        # 路径，以便新进程可以重新注册动态工具。 客户端工具被注入到调用者提供的智能体中
        # 。 当
        # ``agent`` 是 None 是智能体从 base_state.json 恢复的（该已持久化已携带工具规格
        # ），所以这里没有什么需要注入的——但 ``ClientTool`` 类仍然需要重新注册
        #
        # from those persisted specs (done below, after the agent is loaded).
        resolved_client_tools = list(client_tools or [])
        if agent is None and resolved_client_tools:
            # 在恢复客户端工具时，它们从已持久化智能体中恢复（请参阅以下部分），因此，不
            # 能将 ``client_tools`` 注入到智能体中。应警告而不是无声地丢弃它们。
            #
            logger.warning(
                "client_tools were passed with agent=None (resume); the "
                "caller-supplied specs are not re-injected — the conversation's "
                "client tools are recovered from the persisted agent in "
                "base_state.json instead, so they remain executable."
            )
        if (
            agent is not None
            and not resolved_client_tools
            and persistence_dir is not None
        ):
            resolved_client_tools = self._recover_persisted_client_tools(
                persistence_dir, desired_id
            )
        if agent is not None and resolved_client_tools:
            from openhands.sdk.tool.client_tool import register_client_tools

            client_tool_specs = register_client_tools(resolved_client_tools)
            existing_names = {t.name for t in agent.tools}
            new_tools = [
                ts for ts in client_tool_specs if ts.name not in existing_names
            ]
            if new_tools:
                agent = agent.model_copy(update={"tools": [*agent.tools, *new_tools]})
        if isinstance(workspace, (str, Path)):
            # LocalWorkspace 通过 BeforeValidator 接受 str 和 Path
            workspace = LocalWorkspace(working_dir=workspace)
        assert isinstance(workspace, LocalWorkspace), (
            "workspace must be a LocalWorkspace instance"
        )
        self.workspace = workspace
        ws_path = Path(self.workspace.working_dir)
        if not ws_path.exists():
            ws_path.mkdir(parents=True, exist_ok=True)
        self._state = ConversationState.create(
            id=desired_id,
            agent=agent,
            workspace=self.workspace,
            persistence_dir=self.get_persistence_dir(persistence_dir, desired_id)
            if persistence_dir
            else None,
            file_store=file_store,
            max_iterations=max_iteration_per_run,
            stuck_detection=stuck_detection,
            cipher=cipher,
            tags=tags,
        )
        # base_state.json 是智能体的事实来源。 简历上有
        # ``agent=None``国家持有已持久化智能体； 在这里采用它
        # ``self.agent`` 和 ``self._state.agent`` 是同一个对象。
        if agent is None:
            agent = self._state.agent
            # 已持久化智能体带有客户端工具 ``Tool`` 规范，但在新的过程中，
            # ``ClientTool`` * 类 * 不存在于全局注册表中。 根据已持久化规范重新注册它们
            # ，以便客户端工具在此恢复路径上保持可执行状态（智能体服务器也通过
            # ``stored.client_tools`` 执行此操作； 这涵盖了直接 SDK
            # ``LocalConversation(agent=None)`` 简历）。 ``register_client_tools`` 是幂
            # 等的，因此双寄存器是无害的。
            #
            from openhands.sdk.tool.client_tool import (
                extract_client_tool_specs,
                register_client_tools,
            )

            recovered_specs = extract_client_tool_specs(agent.tools)
            if recovered_specs:
                register_client_tools(recovered_specs)
        self.agent = agent

        # 默认回调：持久化每个要说明的事件
        def _default_callback(e):
            # 此回调在保持对话状态的锁的同时运行（请参阅 `with self._state:` 区域内的
            # BaseConversation.compose_callbacks 用法），因此此处更新状态为线程安全。 单
            # 一阻塞点：标记 parent_id（捕获 _tree_stamping 下游钩子交换的任何事件）并前
            # 进 HEAD。
            #
            self._state.append_event(e)

        def _track_last_user_message(e):
            # 跟踪用户 MessageEvent 这里提供ID，用于钩子回调 (这些信息可能被合成或修改)
            # 都集中在一处。 这在调用方提供的之后运行回调设置该字段可以发出一个
            # ConversationStateUpdateEvent 通过 on_state_change (the) Agent Server 它连
            # 接到这个链上)，并且该更新必须在导致该消息的更新之后到达订阅者。
            #
            if isinstance(e, MessageEvent) and e.source == "user":
                # 跟踪最新的真实用户消息 ID 以进行钩子阻止检查。 停止挂钩反馈是通过
                # source="environment" 发出的。
                #
                self._state.last_user_message_id = e.id

        callback_list = list(callbacks) if callbacks else []
        # _default_callback (持久化) 在调用者提供的回调 (e.g. a PubSub 发布），因此订阅
        # 者不会被告知尚未在磁盘上的事件。 compose_callbacks' 普通的 for 循环没有
        #
        # try/except, so if persist raises here, the callbacks after it in the
        # 列表从未运行。 可视化工具位于下面，因此仍然在持久化之前渲染 - 这是本地终端输出
        # ，而不是客户端可以执行操作的公告。
        #
        composed_list = [_default_callback] + callback_list + [_track_last_user_message]
        # 处理可视化配置
        if isinstance(visualizer, ConversationVisualizerBase):
            # 使用自定义可视化工具实例
            self._visualizer = visualizer
            # 使用对话状态初始化可视化工具
            self._visualizer.initialize(self._state)
            composed_list = [self._visualizer.on_event] + composed_list
            # 可视化应该首先发生以提高可见性
        elif isinstance(visualizer, type) and issubclass(
            visualizer, ConversationVisualizerBase
        ):
            # 使用适当的参数实例化可视化工具类
            self._visualizer = visualizer()
            # 用状态初始化
            self._visualizer.initialize(self._state)
            composed_list = [self._visualizer.on_event] + composed_list
            # 可视化应该首先发生以提高可见性
        else:
            # 无可视化（可视化工具为 None）
            self._visualizer = None

        # 组成基本回调链（可视化工具 -> 默认 -> 用户回调）
        base_callback = BaseConversation.compose_callbacks(composed_list)
        self._base_callback = base_callback  # 存储为 _ensure_plugins_loaded

        # 为了保持一致性，将所有挂钩设置推迟到 _ensure_plugins_loaded() 这在第一个 run()
        # /send_message() 调用上运行，并在一个地方处理显式挂钩和插件挂钩
        #
        self._hook_processor = None
        self._on_event = self._tree_stamping(self._rules_injecting(base_callback))
        self._on_token = (
            BaseConversation.compose_callbacks(token_callbacks)
            if token_callbacks
            else None
        )
        self._on_stream = (
            cast(
                StreamProgressCallbackType,
                BaseConversation.compose_callbacks(stream_callbacks),  # type: ignore[arg-type]
            )
            if stream_callbacks
            else None
        )

        self.max_iteration_per_run = max_iteration_per_run
        # 一次运行的硬成本上限 (USD)； None 禁用预算检查。
        self.max_budget_per_run = max_budget_per_run

        # 初始化卡住检测器
        if stuck_detection:
            # 如果需要，将 dict 转换为 StuckDetectionThresholds
            if isinstance(stuck_detection_thresholds, Mapping):
                threshold_config = StuckDetectionThresholds(
                    **stuck_detection_thresholds
                )
            else:
                threshold_config = stuck_detection_thresholds
            self._stuck_detector = StuckDetector(
                self._state,
                thresholds=threshold_config,
            )
        else:
            self._stuck_detector = None

        # 智能体初始化被推迟到 _ensure_agent_ready() 以进行延迟加载这确保插件在智能体初
        # 始化之前加载
        #
        self.llm_registry = LLMRegistry()
        self._profile_store = LLMProfileStore(profile_store_dir)
        self._cipher = cipher

        # 对于每个智能体（常规和 ACP），将 agent_context.secrets 播种到注册表中，覆盖跳
        # 过 create_request() — canvas / TypeScript 或服务器端 agent_settings ->
        # create_agent 折叠的调用者。 与 create_request() 提升幂等； 优先级低于request.
        # secrets（如下）。 在恢复时，如果缺席则填写，因此已持久化值永远不会降级（或丢失
        # 为已编辑/无密码序列化）。
        #
        if self.agent is not None and self.agent.agent_context is not None:
            ctx_secrets = self.agent.agent_context.secrets
            if ctx_secrets:
                existing_sources = self._state.secret_registry.secret_sources
                fill_secrets: dict[str, SecretValue] = {}
                for name, secret in ctx_secrets.items():
                    existing = existing_sources.get(name)
                    # 仅当不存在时或当 StaticSecret 的值丢失为已编辑/无密码序列化（值为
                    # None）时才重新填充。 其他 SecretSource 类型 (e.g. LookupSecret）即
                    # 使具有 None 值也保持原样 - 这是它们的已解决状态，而不是要覆盖的陈
                    # 旧占位符。
                    #
                    if existing is None or (
                        isinstance(existing, StaticSecret) and existing.value is None
                    ):
                        fill_secrets[name] = secret
                if fill_secrets:
                    self.update_secrets(fill_secrets)

        # 更高优先级：request.secrets 覆盖上面的重复键。
        if secrets:
            secret_values: dict[str, SecretValue] = {k: v for k, v in secrets.items()}
            self.update_secrets(secret_values)

        atexit.register(self.close)
        self._start_observability_span(
            str(desired_id),
            span_name=observability_span_name,
            user_id=user_id,
            metadata=observability_metadata,
            tags=observability_tags,
            conversation_tags=tags,
            parent_span_context=observability_parent_span_context,
        )
        self.delete_on_close = delete_on_close

    def _tree_stamping(
        self, inner: ConversationCallbackType
    ) -> ConversationCallbackType:
        """将回调包裹起来，以便进行中的订阅者看到谱系承载事件。

        仅为方便起见：权威印章是
        ``ConversationState.append_event``，它会重新标记下游钩子交换的任何内容。 HEAD
         进展在附加站点，而不是这里。
        """

        def wrapped(event: Event) -> None:
            inner(self._state._stamp_parent_id(event))

        return cast(ConversationCallbackType, wrapped)

    def _rules_injecting(
        self, inner: ConversationCallbackType
    ) -> ConversationCallbackType:
        """包裹回调，以便在文件触摸、镜像上注入路径规则
        :meth:`send_message` 中的技能注入。 它运行在状态锁（见运行循环），因此修改
        dedup 集是安全的。
        """

        def wrapped(event: Event) -> None:
            inner(self._maybe_inject_path_rules(event))

        return cast(ConversationCallbackType, wrapped)

    def _maybe_inject_path_rules(self, event: Event) -> Event:
        """返回具有匹配路径规则内容的 ``event``，或保持不变。

        仅考虑携带文件路径的 ``ObservationEvent``。 已在此对话中注入的匹配规则将被跳
        过
        ``state.activated_path_rules``.
        """
        if not isinstance(event, ObservationEvent):
            return event

        if (agent_context := self.agent.agent_context) is None:
            return event

        if (file_path := self._touched_rule_path(event)) is None:
            return event

        result = agent_context.get_tool_use_suffix(
            file_path=file_path,
            skip_skill_names=self._state.activated_path_rules,
        )
        if result is None:
            return event

        content, activated_rule_names = result
        self._state.activated_path_rules.extend(activated_rule_names)
        return event.model_copy(
            update={"extended_content": list(event.extended_content) + [content]}
        )

    def _touched_rule_path(self, event: ObservationEvent) -> str | None:
        """返回工具观测结果触摸的工作区相对 POSIX 路径。

        将观测结果与其 ``ActionEvent`` 相关联并读取操作的
        一般 ``path`` 字段（不依赖于工具包）。 当操作没有文件 ``path`` 或路径位于工作
        区之外时，返回 None。
        """
        action_event: Event | None = None
        with contextlib.suppress(KeyError):
            idx = self._state.events.get_index(event.action_id)
            action_event = self._state.events[idx]
        if not isinstance(action_event, ActionEvent) or action_event.action is None:
            return None
        # 直接读取字段而不是 model_dump()：避免复制大型编辑载荷 (file_text/old_str/
        # new_str) 只是为了读取路径。
        #
        raw_path = getattr(action_event.action, "path", None)
        if not isinstance(raw_path, str) or not raw_path:
            return None

        # 使用本机路径风格，以便 Windows 驱动器路径 (e.g. ``D:\\...``) 被认为是绝对的；
        # 发出一个 POSIX 字符串进行全局匹配。
        #
        raw = PurePath(raw_path)
        if not raw.is_absolute():
            return raw.as_posix()
        root = PurePath(self.workspace.working_dir)
        with contextlib.suppress(ValueError):
            return raw.relative_to(root).as_posix()
        # 回退到文件系统解析，因此符号链接的工作区根 (e.g. macOS /tmp -> /private/tmp)
        # 仍然匹配； strict=False 保留尚未创建的叶子。
        #
        with contextlib.suppress(ValueError, OSError):
            resolved = Path(raw_path).resolve()
            resolved_root = Path(self.workspace.working_dir).resolve()
            return resolved.relative_to(resolved_root).as_posix()
        return None  # 触及工作区之外的文件； 规则是repo范围的

    def _recover_persisted_client_tools(
        self,
        persistence_base_dir: str | Path,
        conversation_id: ConversationID,
    ) -> list[ClientToolSpec]:
        """从已持久化对话的基本状态恢复客户端工具规格。

        当在新进程中重新开始一个已持久化对话时，动态客户端工具将不出现在全局注册表中
        ，且发起者可能无法重新提供 ``client_tools``。 如果没有恢复，已
        持久化智能体的客户端工具将显示为“已删除”并且恢复将失败。 我们阅读了已持久化智
        能体工具规范并提取了嵌入的 ``ClientToolSpec``，以便可以重
        新注册和重新注入它们。 当还没有已持久化状态时返回一个空列表（新对话）。
        """
        from pydantic import ValidationError

        from openhands.sdk.conversation.persistence_const import BASE_STATE
        from openhands.sdk.tool.client_tool import extract_client_tool_specs
        from openhands.sdk.tool.spec import Tool

        base_path = (
            Path(self.get_persistence_dir(persistence_base_dir, conversation_id))
            / BASE_STATE
        )
        try:
            data = json.loads(base_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        raw_tools = (data.get("agent") or {}).get("tools") or []
        tools: list[Tool] = []
        for raw_tool in raw_tools:
            try:
                tools.append(Tool.model_validate(raw_tool))
            except ValidationError:
                continue
        return extract_client_tool_specs(tools)

    @property
    def id(self) -> ConversationID:
        """获取对话的唯一 ID。"""
        return self._state.id

    @property
    def state(self) -> ConversationState:
        """获取对话状态。

        它返回一个具有 ConversationState 方法和属性子集的协议。 我们将能够访问远程会
        话对象上ConversationState的相同属性。 但我
        们将无法访问改变状态的方法。
        """
        return self._state

    @property
    def conversation_stats(self):
        return self._state.stats

    def _latest_acp_prompt_message_id(self) -> str | None:
        """最近的 ACP 提示词消息的 ID，如果有 None，则为 None。"""
        acp_prompt_messages = [
            event
            for event in self._state.active_branch()
            if _is_acp_prompt_message(event)
        ]
        return acp_prompt_messages[-1].id if acp_prompt_messages else None

    def _budget_exceeded_detail(self) -> str | None:
        """如果运行已达到其成本预算，则错误详细信息，否则 None。

        涵盖所有运行的LLMs（智能体、上下文压缩器...）的总花费，补充迭代上限，只限制步
        骤数量。
        """
        if self.max_budget_per_run is None:
            return None
        spent = self.conversation_stats.get_combined_metrics().accumulated_cost
        if spent < self.max_budget_per_run:
            return None
        return (
            f"Agent reached maximum budget limit "
            f"(${self.max_budget_per_run:.4f}); accumulated cost ${spent:.4f}."
        )

    def _emit_run_limit_error(self, code: str, detail: str) -> None:
        """使用运行限制 ConversationErrorEvent 标记运行失败。"""
        logger.error(detail)
        self._state.execution_status = ConversationExecutionStatus.ERROR
        self._on_event(
            ConversationErrorEvent(source="environment", code=code, detail=detail)
        )

    def _check_stuck_or_nudge(self) -> bool:
        """在重复的动作错误连续中微移一次，否则应用 is_stuck()。

        如果设置了 STUCK，则返回 True，并且运行循环应停止。
        """
        if not self._stuck_detector:
            return False

        nudge = self._stuck_detector.get_action_error_nudge()
        if nudge is not None:
            self._on_event(
                MessageEvent(
                    source="environment",
                    llm_message=Message(role="user", content=[TextContent(text=nudge)]),
                )
            )
            return False

        if self._stuck_detector.is_stuck():
            logger.warning("Stuck pattern detected.")
            self._state.execution_status = ConversationExecutionStatus.STUCK
            return True

        return False

    @property
    def stuck_detector(self) -> StuckDetector | None:
        """获取卡住的检测器实例（如果启用）。"""
        return self._stuck_detector

    @property
    def cancel_token(self) -> CancellationToken | None:
        """当前运行处于活动状态取消 token，或 ``None``。

        需要协作取消的工具可以在
        执行：:

            if conversation and conversation.cancel_token:
                if conversation.cancel_token.is_cancelled:
                    return Observation(output="Cancelled")
        """
        return self._cancel_token

    @property
    def resolved_plugins(self) -> list[ResolvedPluginSource] | None:
        """加载插件后获取已解析的插件源。

        如果插件尚未加载，或者未指定插件，则返回 None。 将其用于持久化以确保对话恢复
        使用完全相同的插件版本。
        """
        return self._resolved_plugins

    def fork(
        self,
        *,
        conversation_id: ConversationID | None = None,
        agent: AgentBase | None = None,
        title: str | None = None,
        tags: dict[str, str] | None = None,
        reset_metrics: bool = True,
        from_event_id: EventID | None = None,
    ) -> "LocalConversation":
        """使用新 ID 深度复制此对话。

        事件被复制，因此源保持不变。 分叉从``execution_status='idle'``开始； 调用
        ``run()`` 从复制状态恢复 — 这意味着智能
        体具有源的完整事件内存。

        Args:
            conversation_id: 分叉对话的 ID（自动生成
                if ``None``).
            agent: 智能体为叉子。 默认为深层复制
                来源智能体。
            title: 已弃用。 ``LocalConversation``没有标题字段；
                ``ConversationState`` 不存储标题（它们存在于
                ``StoredConversation`` 在智能体-服务器层）。 向后兼容性接受传递值，但
                没有效果。
            tags: 分叉对话的可选标签。
            reset_metrics: 如果 ``True``（默认），成本/代币统计开始
                新鲜的在叉子上。
            from_event_id: 如果设置，则仅复制到此事件的分支
                (``path_to_root``) 并将叉子的 HEAD 设置在那里。 如果是 ``None``（默认
                ），则复制整个日志并保留源的
                HEAD。

        Returns:
            一个新的 ``LocalConversation`` 共享相同的事件历史，但具有自己的身份和独立
            的状态。

        Raises:
            ValueError: 如果 ``from_event_id`` 不是此对话中的事件。
        """
        if title is not None:
            warn_deprecated(
                "LocalConversation.fork() title parameter",
                deprecated_in="1.54.0",
                removed_in="1.60.0",
                details=(
                    "LocalConversation has no title field; titles are managed by "
                    "StoredConversation in the agent-server layer."
                ),
                stacklevel=2,
            )
        fork_id = conversation_id or uuid.uuid4()
        # 始终深度复制智能体（提供的或源代码），以便分支拥有自己的对象图。 必须如此，因
        # 为 __init__ 会在 LLM 上绑定每个对话的调用上下文（#2917、#3443）；共享或通过别
        # 名复用智能体会覆盖源对话的上下文。 通过 JSON 的往返避免了线程-锁酸洗问题
        #
        # with model_copy(deep=True).
        source_agent = agent if agent is not None else self.agent
        agent_cls = type(source_agent)
        fork_agent = agent_cls.model_validate(
            source_agent.model_dump(context={"expose_secrets": True}),
        )

        # 从源会话中读取可变状态时保持状态锁，以避免在 run() 并发执行时出现撕裂读取。
        #
        with self._state:
            # 在构建分支之前进行验证，以便未知的分支点不会留下孤立的持久化目录。
            #
            if from_event_id is not None and from_event_id not in self._state.events:
                raise ValueError(f"Unknown from_event_id: {from_event_id}")

            # 确定叉子的 persistence_dir。 仅传递 *base* 目录 - __init__ 调用
            # get_persistence_dir() 附加会话 ID 十六进制，因此我们不能在这里这样做。
            #
            source_persistence = self._state.persistence_dir
            fork_persistence: str | None = None
            if source_persistence is not None:
                source_path = Path(source_persistence)
                fork_persistence = str(source_path.parent)

            # 建立分叉对话（空——还没有事件）
            fork_conv = LocalConversation(
                agent=fork_agent,
                workspace=self.workspace,
                plugins=self._plugin_specs,
                persistence_dir=fork_persistence,
                conversation_id=fork_id,
                max_iteration_per_run=self.max_iteration_per_run,
                stuck_detection=self._stuck_detector is not None,
                visualizer=type(self._visualizer) if self._visualizer else None,
                delete_on_close=self.delete_on_close,
                tags=tags,
                _parent_llm_call_context=self._llm_call_context,
            )

            # 分支切片副本 path_to_root(event)（根优先，可重新根）； 完整的分叉复制整个
            # 日志并继承源的HEAD。
            #
            if from_event_id is not None:
                source_events: list[Event] = self._state.events.path_to_root(
                    from_event_id
                )
                fork_leaf: EventID | None = from_event_id
            else:
                source_events = list(self._state.events)
                fork_leaf = self._state.leaf_event_id

            for event in source_events:
                fork_conv._state.events.append(_copy_event_for_fork(event))
            fork_conv._state.leaf_event_id = fork_leaf
            # 完整的分叉继承源的空HEAD状态； 分支切片根 HEAD 位于真实事件 (from_event_id
            # )，因此它永远不会为空。
            #
            fork_conv._state.head_is_empty = (
                self._state.head_is_empty if from_event_id is None else False
            )
            # 完全重建：复制的事件可能需要属性强制（与冷加载相同的姿势）。
            #
            fork_conv._state.rebuild_view()

            # 复制源会话期间累积的运行时状态。 activated_knowledge_skills 是 list[str] –
            #  字符串是不可变的，因此浅表副本就足够了。 agent_state 可以保存任意可变值，
            # 因此可以对其进行深度复制。
            #
            fork_conv._state.activated_knowledge_skills = list(
                self._state.activated_knowledge_skills
            )
            fork_conv._state.activated_path_rules = list(
                self._state.activated_path_rules
            )
            fork_conv._state.agent_state = copy.deepcopy(self._state.agent_state)

            # 重置或复制指标
            if not reset_metrics:
                fork_conv._state.stats = self._state.stats.model_copy(deep=True)

            event_count = len(source_events)

        logger.info(
            f"Forked conversation {self.id} → {fork_id} "
            f"({event_count} events copied, "
            f"reset_metrics={reset_metrics}, "
            f"from_event_id={from_event_id})"
        )
        return fork_conv

    def navigate_to(self, event_id: EventID | None) -> None:
        """在此对话中移动对话 HEAD（无新分叉）。

        重新定位活动分支：智能体的下一个上下文变为
        ``path_to_root(event_id)``. 所有分支都保留在磁盘上 - 导航后追加会创建同级分支
        ； 废弃的事件保留在日志中，但从
        ``state.view`` 中删除。

        Args:
            event_id: 为空树创建新的 HEAD 或 ``None`` 的事件。

        Raises:
            ValueError: 如果 ``event_id`` 不是 ``None`` 并且不在其中
                谈话。
        """
        with self._state:
            if event_id is not None and event_id not in self._state.events:
                raise ValueError(f"Unknown event_id: {event_id}")
            self._state.leaf_event_id = event_id  # 自动保存 base_state.json
            # 标记一个显式的空 HEAD，这样它就不会被误读为遗留/未设置的叶子（这将解析回最
            # 后一个事件）。 参见ConversationState._resolve_active_leaf。
            #
            self._state.head_is_empty = event_id is None
            self._state.rebuild_view()

    def _ensure_plugins_loaded(self) -> None:
        """延迟加载插件并在首次使用时设置挂钩。

        该方法在 run() 和 send_message() 之前自动调用。 它在一处处理插件加载和钩子初
        始化
        for consistency.

        方法：
        1. 从源获取插件（远程源的网络 IO）
        2. SHAs 重定向到提交
        3. 加载插件内容（技能、MCP 配置、挂钩）
        4. 将插件内容合并到智能体
        5. 使用组合钩子设置钩子处理器（显式+插件）
        6. 运行 session_start 个挂钩
        """
        if self._plugins_loaded:
            return

        all_plugin_hooks: list[HookConfig] = []
        all_plugin_agents: list[AgentDefinition] = []
        # 显式附加插件的名称（在下面的循环中填充）。 用于保持对环境安装/本地插件的显式附
        # 加权威（并避免双重注册其挂钩/代理）。
        #
        explicit_plugin_names: set[str] = set()

        merged_context = self.agent.agent_context
        merged_mcp = dict(self.agent.mcp_config) if self.agent.mcp_config else {}

        # 跟踪我们是否有插件或 MCP 配置要处理
        has_mcp_config = bool(merged_mcp)
        marketplace_skills_loaded = False

        plugins_to_load: list[tuple[PluginSource, bool]] = []
        if merged_context is not None and merged_context.registered_marketplaces:
            registrations = [
                registration.model_copy(
                    update={
                        "source": self._expand_plugin_source_ref(registration.source),
                        "ref": self._expand_plugin_source_ref(registration.ref)
                        if registration.ref
                        else None,
                    }
                )
                for registration in merged_context.registered_marketplaces
            ]
            registry = MarketplaceRegistry(registrations)
            marketplace_skills: list[Skill] = []
            for registration in registry.get_auto_load_registrations():
                try:
                    marketplace, marketplace_path = registry.get_marketplace(
                        registration.name
                    )
                except Exception:
                    logger.warning(
                        "Failed to load marketplace '%s'; continuing without it",
                        registration.name,
                        exc_info=True,
                    )
                    continue
                for entry in marketplace.plugins:
                    if not registration.auto_loads_plugin(entry.name):
                        continue
                    source, ref, repo_path = marketplace.resolve_plugin_source(entry)
                    plugins_to_load.append(
                        (
                            PluginSource(source=source, ref=ref, repo_path=repo_path),
                            True,
                        )
                    )
                # Standalone skills. 下面合并为低优先级； 随后加载的插件会覆盖同名技能，
                # 与目录相匹配。
                #
                marketplace_skills.extend(
                    load_marketplace_standalone_skills(
                        marketplace, marketplace_path, registration
                    )
                )
            if marketplace_skills:
                merged_context = merged_context.model_copy(
                    update={
                        "skills": merge_skills_by_name(
                            merged_context.skills, marketplace_skills
                        )
                    }
                )
                marketplace_skills_loaded = True

        if self._plugin_specs:
            plugins_to_load.extend((spec, False) for spec in self._plugin_specs)

        # 加载插件（如果指定或注册为自动加载）
        if plugins_to_load:
            logger.info(f"Loading {len(plugins_to_load)} plugin(s)...")
            self._resolved_plugins = []

            for spec, source_refs_expanded in plugins_to_load:
                if source_refs_expanded:
                    fetch_source = spec.source
                    fetch_ref = spec.ref
                else:
                    fetch_source = self._expand_plugin_source_ref(spec.source)
                    fetch_ref = (
                        self._expand_plugin_source_ref(spec.ref)
                        if spec.ref
                        else spec.ref
                    )

                # 获取插件并获得已解决的提交 SHA
                path, resolved_ref = fetch_plugin_with_resolution(
                    source=fetch_source,
                    ref=fetch_ref,
                    repo_path=spec.repo_path,
                )

                # 存储持久化的解析参考。 根据 ORIGINAL 规范（而不是扩展值）构建此记录，
                # 因此已持久化记录保留 ${VAR} 占位符而不是原始机密。 from_plugin_source(
                # ) 另外编辑了任何内联凭据。 通过已解析的提交恢复重新获取 SHA。
                #
                resolved = ResolvedPluginSource.from_plugin_source(spec, resolved_ref)
                self._resolved_plugins.append(resolved)

                # 加载插件
                plugin = Plugin.load(path)
                logger.debug(
                    f"Loaded plugin '{plugin.manifest.name}'"
                    + (f" @ {resolved_ref[:8]}" if resolved_ref else "")
                )
                explicit_plugin_names.add(plugin.name)

                # 合并插件内容
                merged_context = plugin.add_skills_to(merged_context)
                merged_mcp = plugin.add_mcp_config_to(merged_mcp)
                has_mcp_config = has_mcp_config or bool(merged_mcp)

                # 收集钩子
                if plugin.hooks and not plugin.hooks.is_empty():
                    all_plugin_hooks.append(plugin.hooks)

                # 收集智能体个定义
                if plugin.agents:
                    all_plugin_agents.extend(plugin.agents)

            logger.info(f"Loaded {len(plugins_to_load)} plugin(s) via Conversation")

        # 环境插件：启用已安装的插件以及本地用户/项目插件，镜像已安装/本地技能的自动加载
        # 方式。 这些是对上面显式插件的补充，通过插件名称进行重复删除。 显式附加获胜：跳
        # 过名称已附加在上面的环境插件（这也避免了双重注册其钩子/代理）。 尽力而为——这里
        # 的失败不能阻止对话的开始。
        #
        # 环境插件没有固定提交 SHA，因此（与显式附加不同）它们有意不记录在
        # self._resolved_plugins 中。 在恢复时，它们会从磁盘/当前启用状态重新发现，就像
        # 项目技能一样。 自动化/沙箱运行缺少用户的安装目录和主目录，因此发现自然不会产生
        # 任何结果。
        #
        ambient_plugins_loaded = False
        try:
            ambient_plugins = load_available_plugins(
                work_dir=self.workspace.working_dir,
                include_user=True,
                include_project=True,
            )
        except Exception:
            logger.warning(
                "Failed to load ambient (installed/local) plugins; "
                "continuing without them",
                exc_info=True,
            )
            ambient_plugins = {}

        for plugin in ambient_plugins.values():
            if plugin.name in explicit_plugin_names:
                logger.debug(
                    f"Skipping ambient plugin '{plugin.name}' "
                    "(explicitly attached to this conversation)"
                )
                continue

            merged_context = plugin.add_skills_to(merged_context)
            merged_mcp = plugin.add_mcp_config_to(merged_mcp)
            has_mcp_config = has_mcp_config or bool(merged_mcp)

            if plugin.hooks and not plugin.hooks.is_empty():
                all_plugin_hooks.append(plugin.hooks)
            if plugin.agents:
                all_plugin_agents.extend(plugin.agents)

            ambient_plugins_loaded = True
            logger.debug(f"Loaded ambient plugin '{plugin.name}'")

        # 解决项目技能来自工作区。 AgentContext 本身无法执行此操作（工作区路径在验证时间
        # 未知），因此在此处完成，路径已知。 项目技能优先于上下文中已有的同名技能。
        #
        project_skills_loaded = False
        if merged_context is not None and merged_context.load_project_skills:
            # 尽力而为：加载项目技能失败不得阻止对话的开始。 (load_available_skills已在
            # 内部保护项目源； 这是腰带和吊带。）
            #
            try:
                project_skills = load_available_skills(
                    work_dir=self.workspace.working_dir,
                    include_user=False,
                    include_project=True,
                    include_public=False,
                )
            except Exception:
                logger.warning(
                    "Failed to load project skills; continuing without them",
                    exc_info=True,
                )
                project_skills = {}
            if project_skills:
                # 项目技能比同名的上下文技能具有权威性。
                merged_skills = merge_skills_by_name(
                    project_skills.values(), merged_context.skills
                )
                # 这里也尊重上下文拒绝列表：下面的 model_copy 绕过 AgentContext 的验证器
                # ，并且项目技能可以匹配禁用的名称（缺少名称 => 无害的无操作）。
                #
                if merged_context.disabled_skills:
                    disabled = set(merged_context.disabled_skills)
                    merged_skills = [s for s in merged_skills if s.name not in disabled]
                merged_context = merged_context.model_copy(
                    update={"skills": merged_skills}
                )
                project_skills_loaded = True

        # 从磁盘解析持久内存。 与项目技能一样，AgentContext 本身无法做到这一点（工作区路
        # 径在验证时未知）。
        #
        memory_loaded = False
        if merged_context is not None and merged_context.load_memory:
            # 尽力而为：读取内存失败不得阻止启动。
            try:
                memory_context = load_memory(self.workspace.working_dir)
            except Exception:
                logger.warning(
                    "Failed to load memory; continuing without it",
                    exc_info=True,
                )
                memory_context = None
            if memory_context:
                merged_context = merged_context.model_copy(
                    update={"memory_context": memory_context}
                )
                memory_loaded = True

        # 使用每个对话扩展 MCP 配置变量机密这处理 ${VAR} 和 ${VAR:-default} 占位符：
        # - 通过 API 注入的引用机密的变量被扩展为机密值
        # - 具有默认值但没有机密的变量将回退到其默认值
        # - 这是应用默认值的仅位置（插件加载使用 expand_defaults=False 保留占位符以避免
        # 双重扩展）
        # 智能体插件服务器保留文字（参见 expand_mcp_servers）。
        if self._mcp_config_from_parent:
            merged_mcp = dict(self.agent.mcp_config)
        elif merged_mcp:
            # 传递注册表的查找方法，因为回调 - 机密被延迟检索，一次一个，仅在配置中实际
            # 引用时
            #
            merged_mcp = expand_mcp_servers(
                merged_mcp, self._state.secret_registry.get_secret_value
            )
            logger.debug("Expanded MCP config variables")

        # 仅当发生更改时才使用合并内容更新智能体。 否则跳过更新以避免不必要的智能体状态
        # 突变。
        #
        if (
            plugins_to_load
            or has_mcp_config
            or project_skills_loaded
            or ambient_plugins_loaded
            or marketplace_skills_loaded
            or memory_loaded
        ):
            self.agent = self.agent.model_copy(
                update={
                    "agent_context": merged_context,
                    "mcp_config": merged_mcp,
                }
            )

            # 同时更新 _state 中的智能体，以便 API 响应反映已加载的插件
            with self._state:
                self._state.agent = self.agent

        # 注册插件中定义的基于文件的智能体
        if all_plugin_agents:
            register_plugin_agents(
                agents=all_plugin_agents,
                work_dir=self.workspace.working_dir,
            )

        # 将显式 hook_config 与插件挂钩相结合显式挂钩首先运行（在插件挂钩之前）
        #
        final_hook_config = self._pending_hook_config
        if all_plugin_hooks:
            plugin_hooks = HookConfig.merge(all_plugin_hooks)
            if plugin_hooks is not None:
                if final_hook_config is not None:
                    final_hook_config = HookConfig.merge(
                        [final_hook_config, plugin_hooks]
                    )
                else:
                    final_hook_config = plugin_hooks

        # 使用组合配置设置挂钩处理器
        if final_hook_config is not None:
            # 将最终的 hook_config 存储在状态中以实现可观察性
            self._state.hook_config = final_hook_config
            hook_persistence_dir = (
                str(Path(self._state.persistence_dir).parent)
                if self._state.persistence_dir is not None
                else None
            )

            self._hook_processor, raw_on_event = create_hook_callback(
                hook_config=final_hook_config,
                working_dir=str(self.workspace.working_dir),
                session_id=str(self._state.id),
                original_callback=self._base_callback,
                # 惰性解析：switch_llm()/switch_profile()重新绑定self.agent，因此智能体
                # 钩子必须在执行时读取当前的LLM。
                #
                llm_getter=lambda: self.agent.llm,
                llm_call_context=self._llm_call_context,
                persistence_dir=hook_persistence_dir,
                visualizer=self._visualizer,
                conversation_stats=self._state.stats,
            )
            self._on_event = self._tree_stamping(self._rules_injecting(raw_on_event))
            self._hook_processor.set_conversation_state(self._state)
            self._hook_processor.run_session_start()

        self._plugins_loaded = True

    def _expand_plugin_source_ref(self, value: str) -> str:
        return expand_variable_references(
            value,
            get_secret=self._state.secret_registry.get_secret_value,
            check_env=False,
            support_unbraced=False,
            expand_defaults=False,
        )

    def _marketplace_registry_from_context(self) -> MarketplaceRegistry:
        agent_context = self.agent.agent_context
        if agent_context is None:
            raise ValueError(
                "No agent context available. Configure agent_context with "
                "registered_marketplaces to use load_plugin()."
            )
        registrations = agent_context.registered_marketplaces
        if not registrations:
            raise ValueError(
                "No marketplaces registered. Configure registered_marketplaces "
                "in AgentContext to use load_plugin()."
            )
        return MarketplaceRegistry(
            [
                registration.model_copy(
                    update={
                        "source": self._expand_plugin_source_ref(registration.source),
                        "ref": self._expand_plugin_source_ref(registration.ref)
                        if registration.ref
                        else None,
                    }
                )
                for registration in registrations
            ]
        )

    def _merge_runtime_plugin_hooks(self, plugin_hooks: HookConfig) -> None:
        existing_config = self._state.hook_config
        merged_config = (
            HookConfig.merge([existing_config, plugin_hooks])
            if existing_config is not None
            else plugin_hooks
        )
        if merged_config is None:
            return

        hook_persistence_dir = (
            str(Path(self._state.persistence_dir).parent)
            if self._state.persistence_dir is not None
            else None
        )
        previous_processor = self._hook_processor
        if previous_processor is not None:
            previous_processor.run_session_end()

        self._state.hook_config = merged_config
        self._pending_hook_config = merged_config
        self._hook_processor, raw_on_event = create_hook_callback(
            hook_config=merged_config,
            working_dir=str(self.workspace.working_dir),
            session_id=str(self._state.id),
            original_callback=self._base_callback,
            llm_getter=lambda: self.agent.llm,
            llm_call_context=self._llm_call_context,
            persistence_dir=hook_persistence_dir,
            visualizer=self._visualizer,
            conversation_stats=self._state.stats,
        )
        self._on_event = self._tree_stamping(self._rules_injecting(raw_on_event))
        self._hook_processor.set_conversation_state(self._state)
        self._hook_processor.run_session_start()

    def _runtime_mcp_tools(
        self,
        mcp_config: dict[str, MCPServer],
        *,
        on_tools_changed: ToolsChangedCallback | None = None,
        on_tools_reconciled: ToolsReconciledCallback | None = None,
    ) -> list[ToolDefinition]:
        # 用户关闭的服务器保留在设置映射中，但不得连接到。 在空性检查之前进行过滤，以便
        # 全部禁用的配置是普通的无操作而不是零服务器 MCP 客户端。
        #
        mcp_config = enabled_mcp_servers(mcp_config)
        if not mcp_config:
            return []
        create_kwargs: dict[str, Any] = {"on_tools_changed": on_tools_changed}
        if provider_supports_on_tools_reconciled(self._mcp_tool_provider):
            create_kwargs["on_tools_reconciled"] = on_tools_reconciled
        elif on_tools_reconciled is not None:
            logger.debug(
                "%s does not accept on_tools_reconciled; dynamic MCP tool "
                "removals/updates won't reach the agent for this provider",
                type(self._mcp_tool_provider).__name__,
            )
        try:
            client = self._mcp_tool_provider.create_tools(
                mcp_config, _RUNTIME_MCP_TIMEOUT_SECS, **create_kwargs
            )
        except Exception as exc:
            logger.warning(
                "MCP server startup failed for %s; continuing without its tools: %s",
                ", ".join(sorted(mcp_config)),
                exc,
            )
            return []
        return list(client.tools)

    def _on_mcp_tools_reconciled(
        self,
        client: MCPClient,
        tools: Sequence[MCPToolDefinition],
    ) -> None:
        self.agent._on_mcp_tools_reconciled(client, tools)

    def _runtime_mcp_tools_for_agent(self) -> list[ToolDefinition]:
        if not self.agent.supports_openhands_tools or not self.agent.mcp_config:
            return []
        return self._runtime_mcp_tools(
            self.agent.mcp_config,
            on_tools_changed=lambda tools: self.agent._on_mcp_tools_changed(tools),
            on_tools_reconciled=self._on_mcp_tools_reconciled,
        )

    def _runtime_skill_tools_for_agent(self) -> list[ToolDefinition]:
        agent_context = self.agent.agent_context
        has_invocable_skills = bool(
            agent_context
            and any(
                skill.is_agentskills_format and not skill.disable_model_invocation
                for skill in agent_context.skills
            )
        )
        if has_invocable_skills and InvokeSkillTool.name not in self.agent.tools_map:
            return list(InvokeSkillTool.create(self._state))
        return []

    def _close_runtime_tools(self, tools: Sequence[ToolDefinition]) -> None:
        for tool in tools:
            try:
                tool.as_executable().executor.close()
            except NotImplementedError:
                continue
            except Exception as exc:
                logger.warning(
                    "Error closing runtime tool executor for tool '%s': %s",
                    tool.name,
                    exc,
                )

    def load_plugin(self, plugin_ref: str) -> None:
        """从对话的注册市场加载插件。"""
        self._ensure_plugins_loaded()
        spec = self._marketplace_registry_from_context().resolve_plugin(plugin_ref)

        fetch_source = self._expand_plugin_source_ref(spec.source)
        fetch_ref = self._expand_plugin_source_ref(spec.ref) if spec.ref else spec.ref
        path, resolved_ref = fetch_plugin_with_resolution(
            source=fetch_source,
            ref=fetch_ref,
            repo_path=spec.repo_path,
        )
        plugin = Plugin.load(path)
        logger.info(
            f"Loaded plugin '{plugin.manifest.name}'"
            + (f" @ {resolved_ref[:8]}" if resolved_ref else "")
        )

        get_secret = self._state.secret_registry.get_secret_value
        runtime_plugin_mcp: dict[str, MCPServer] = {}
        if plugin.mcp_config:
            runtime_plugin_mcp = expand_mcp_servers(plugin.mcp_config, get_secret)
        merged_context = plugin.add_skills_to(self.agent.agent_context)
        merged_mcp = plugin.add_mcp_config_to(
            dict(self.agent.mcp_config) if self.agent.mcp_config else {}
        )
        if merged_mcp:
            merged_mcp = expand_mcp_servers(merged_mcp, get_secret)
        runtime_mcp_tools = (
            self._runtime_mcp_tools(
                runtime_plugin_mcp,
                on_tools_changed=lambda tools: self.agent._on_mcp_tools_changed(tools),
                on_tools_reconciled=self._on_mcp_tools_reconciled,
            )
            if self._agent_ready
            else []
        )

        with self._state:
            self.agent = self.agent.model_copy(
                update={
                    "agent_context": merged_context,
                    "mcp_config": merged_mcp,
                }
            )

            if plugin.agents:
                register_plugin_agents(
                    agents=plugin.agents,
                    work_dir=self.workspace.working_dir,
                )
            if plugin.hooks and not plugin.hooks.is_empty():
                self._merge_runtime_plugin_hooks(plugin.hooks)

            resolved = ResolvedPluginSource.from_plugin_source(spec, resolved_ref)
            if self._resolved_plugins is None:
                self._resolved_plugins = []
            self._resolved_plugins.append(resolved)

            self._state.agent = self.agent
            if self._agent_ready:
                runtime_tools = [
                    *runtime_mcp_tools,
                    *self._runtime_skill_tools_for_agent(),
                ]
                try:
                    self.agent.add_runtime_tools(runtime_tools)
                except Exception:
                    self._close_runtime_tools(runtime_mcp_tools)
                    raise

    def _register_file_based_agents(self) -> None:
        """发现基于文件的智能体并将其注册到智能体注册表中。

        智能体从 Markdown 定义文件加载并通过
        `register_agent_if_absent`，因此它们永远不会覆盖已经以编程方式或插件注册的智
        能体。

        注册顺序（优先级从高到低）：
          1. 编程 `register_agent()` 调用（已在注册表中）
          2. 插件智能体（在插件加载期间注册，i.e.，在 _ensure_plugins_loaded() 中）
          3. 项目级文件智能体（`{project}/.agents/agents/*.md`，然后
          `{project}/.openhands/agents/*.md`）
          4. 用户级文件智能体（`~/.agents/agents/*.md`，然后
          `~/.openhands/agents/*.md`）
        """
        # 注册项目级，然后基于用户级文件智能体
        register_file_agents(self.workspace.working_dir)

    def _ensure_agent_ready(self) -> None:
        """确保智能体已使用插件完全初始化并已加载智能体。

        在第一个 `send_message()` 或 `run()` 调用时执行一次性延迟初始化。 执行的步骤
        （按顺序）是：

        1. 加载插件（合并技能、MCP 配置和挂钩）。
        2. 将基于文件的智能体注册到智能体注册表中。
        3. 使用完整的插件配置和挂钩初始化智能体。
        4. LLMs 注册表 LLM。

        这保留了构造函数不应执行 I/O 操作或易出错操作的设计原则，同时消除双重初始化。

        线程安全：对会话状态使用双重检查锁以防止并发初始化。
        """
        # 快速路径：如果已经初始化，则完全跳过锁采集。 这对于 run() 期间的并发
        # send_message() 调用至关重要，它在 agent.step() 期间保持状态锁。 如果没有此检查
        # ，即使不需要初始化，send_message() 也会阻塞等待锁。
        #
        if self._agent_ready:
            return

        with self._state:
            # 获取锁后重新检查，以防另一个线程初始化
            if self._agent_ready:
                return

            # 首先加载插件（合并技能、MCP 配置、挂钩）
            self._ensure_plugins_loaded()

            # 基于寄存器文件智能体
            self._register_file_based_agents()

            runtime_mcp_tools: list[ToolDefinition] = []
            try:
                if self.agent.supports_openhands_tools:
                    self.agent._initialize(self._state)
                    runtime_mcp_tools = self._runtime_mcp_tools_for_agent()
                    self.agent.add_runtime_tools(runtime_mcp_tools)

                self.agent.init_state(
                    self._state,
                    on_event=self._on_event,
                )

                # 既然 init_state() 已发出 SystemPromptEvent，则交付任何 SessionStart
                # additional_context，因此系统提示词在 LLM 请求中保持第一个位置。 钩子处
                # 理器在_ensure_plugins_loaded()期间早些时候收集了它。
                #
                if self._hook_processor is not None:
                    self._hook_processor.inject_pending_additional_context()
            except Exception:
                self._close_runtime_tools(runtime_mcp_tools)
                raise

            # LLMs 注册到注册表（仍然持有锁）。
            # `registered` 在每次添加后更新，以便默默地跳过同一批次中的重复 usage_ids（
            # 先写胜出），从而防止 e.g 时出现 ValueError。 智能体和上下文压缩器 LLMs 都
            # 被序列化为 usage_id="default"。
            #
            self.llm_registry.subscribe(self._state.stats.register_llm)
            registered = set(self.llm_registry.list_usage_ids())
            for llm in list(self.agent.get_all_llms()):
                if llm.usage_id not in registered:
                    self.llm_registry.add(llm)
                    registered.add(llm.usage_id)

            self._agent_ready = True

    def _should_initialize_agent_on_send_message(self) -> bool:
        """返回 send_message() 是否应该立即初始化智能体。

        ACPAgent 启动程序比常规程序要重得多智能体初始化，因为它会启动并与外部进行握手
         ACP  子进程。 将那项工作推迟到 run() keeps
        send_message() 快且避免 HTTP 客户端读取超时在远程对话中端点。
        """
        return not isinstance(self.agent, ACPAgent)

    def get_llm_call_context(self) -> LLMCallContext:
        """返回此对话拥有的不可变 LLM 调用上下文。

        ``prompt_cache_key`` 使用构造时提供的覆盖（用于子智能体缓存分片共享）或默认为
        会话自己的 ID。 ``session_id`` 始终是对
        话的 ID。
        """
        return self._llm_call_context

    def _condenser_for_switched_llm(
        self,
        current_llm: LLM,
        new_llm: LLM,
    ) -> CondenserBase | None:
        condenser = self.agent.condenser
        if not isinstance(condenser, LLMSummarizingCondenser):
            return condenser

        current_config = current_llm.model_dump(
            mode="json",
            context={"expose_secrets": True},
            exclude={"usage_id"},
        )
        condenser_config = condenser.llm.model_dump(
            mode="json",
            context={"expose_secrets": True},
            exclude={"usage_id"},
        )
        if condenser_config != current_config:
            return condenser

        condenser_llm = new_llm.model_copy(
            update={"usage_id": condenser.llm.usage_id},
        )
        condenser_llm.reset_metrics()
        return condenser.model_copy(update={"llm": condenser_llm})

    def switch_llm(self, llm: LLM) -> None:
        """将智能体的 LLM 交换到给定的对象。

        调用者拥有``llm.usage_id``； 这是注册表键。 如果具有该键的条目已存在并且具有
        相同的配置，则将重用缓存的 LLM。 如果其配置不同 (e.g
        . ``default``，即智能体初始化注册，与另一个模型一起提交的，传递的``llm``替换
        并接管了在该``usage_id``下记录的指标。

        Args:
            llm: LLM 安装在智能体上。
        """
        usage_id = llm.usage_id
        try:
            registered = self.llm_registry.get(usage_id)
        except KeyError:
            registered = None
        if registered is not None and _same_llm_config(registered, llm):
            new_llm = registered
        else:
            new_llm = create_subscription_llm_from_config(llm)
            if registered is not None:
                self.llm_registry.remove(usage_id)
            self.llm_registry.add(new_llm)
            if registered is not None:
                # 每个 usage_id 保留一个指标对象：ConversationStats 跟踪已注册的 LLM，因
                # 此保留了应计使用量。
                #
                new_llm.restore_metrics(registered.metrics)
        # A switch_llm 工具运行在工作节点上线程 while run()/arun() 持有状态锁在智能体踩
        # 在另一只脚上线程已被阻止，等待这个工具。 在这里重新获取 _state 将会死锁所以跳
        # 过它：运行循环被挂起，没有其他变种可以运行，所以交换是安全的锁 (#3485). 只有在
        # 时才跳过锁由不同的持有线程 (运行循环) 当调用者已经拥有它（a 同步步骤，或切换端
        # 点重新进入事件循环线程正常获取 — FIFOLock 是可重入 for the owning 线程。
        #
        skip_lock = self._step_holds_state_lock and not self._state.owned()
        lock = contextlib.nullcontext() if skip_lock else self._state
        with lock:
            update: dict[str, object] = {"llm": new_llm}
            update["condenser"] = self._condenser_for_switched_llm(
                self.agent.llm,
                new_llm,
            )
            self.agent = self.agent.model_copy(update=update)
            self._state.agent = self.agent
            # 使缓存的ask-智能体LLM无效，因此它会重新克隆。
            self.llm_registry.remove(ASK_AGENT_LLM_USAGE_ID)

    def switch_profile(self, profile_name: str) -> None:
        """将智能体的 LLM 切换到从磁盘加载的配置文件。

        从：class:`LLMProfileStore` 加载配置文件（首次加载后缓存在
        ``profile:{profile_name}`` 下的注册表中）并将
        交换委托给：meth:`switch_llm`。

        Args:
            profile_name: 之前通过 LLMProfileStore 保存的用户头像名。

        Raises:
            FileNotFoundError: 如果配置文件不存在。
            ValueError: 如果配置文件已损坏或无效。
        """
        usage_id = f"profile:{profile_name}"
        try:
            cached = self.llm_registry.get(usage_id)
        except KeyError:
            loaded = self._profile_store.load(profile_name, cipher=self._cipher)
            cached = loaded.model_copy(update={"usage_id": usage_id})
        self.switch_llm(cached)

    def get_or_create_profile_llm(self, profile_name: str, usage_id: str) -> LLM:
        """返回为此对话注册的已保存配置文件 LLM。

        与：meth:`switch_profile` 不同，这不会替换活动的智能体模型。 它旨在用于从工具
        进行辅助一次性模型调用，同时仍然通过
        ``llm_registry`` 路由 token 和成本核算
        ``ConversationStats``.
        """
        try:
            return self.llm_registry.get(usage_id)
        except KeyError:
            loaded = self._profile_store.load(profile_name, cipher=self._cipher)
            llm = loaded.model_copy(update={"usage_id": usage_id})
            llm = create_subscription_llm_from_config(llm)
            self.llm_registry.add(llm)
            return llm

    def switch_acp_model(self, model: str) -> None:
        """在 ACP 对话中切换模型。

        与：meth:`switch_llm` 不同，它交换 OpenHands 自己的 LLM 对象，它的目标是 ACP
        子进程运行的模型。
        ``switch_llm`` 不会影响 ACP 对话，因为子进程拥有自己的模型。

        根据实时会话是否存在而表现不同：

        * **实时会话**（第一个``run()``之后）：发出协议级
          ``session/set_model`` 调用，以便新模型适用于 * 相同 * 会话的后续轮次，保留
          对话上下文。
        * **还没有直播会话** （已创建但尚未运行）：没有需要切换为实时的，所以新值只是
        已持久化。 在第一次创建会话 ``run()`` 那么，它就尊重它
        ``_maybe_set_session_model`` 发出一次请求 ``set_session_model`` 对于每个内置
        提供者（codex、gemi
        ni和claude-code）——因此，第一轮运行在切换模型上，而不是默默地使用构建时间的模
        型。

        Args:
            model: 要切换到的特定于提供商的模型 ID。

        Raises:
            ValueError: 如果对话的智能体不是：class:`ACPAgent`，
                如果 ``model`` 为空或仅包含空白字符（在线或离线），或者（对于在线切换
                ）提供商不支持运行时模型切换，或者 ACP 服务器拒绝切换。
            TimeoutError: 如果实时开关的 ``session/set_model`` 往返
                超过 ``acp_prompt_timeout`` 秒。
        """
        if not isinstance(self.agent, ACPAgent):
            raise ValueError(
                "switch_acp_model is only supported for ACP conversations."
            )
        # 检查此处，不仅在 set_acp_model 中：下面的预运行路径会跳过该调用，并会持久化取
        # 消选中空白模型。
        #
        if not model or not model.strip():
            raise ValueError("model must be a non-empty string")
        with self._state:
            # 对于直播会话，先进行协议切换； 如果失败，我们将保持已持久化状态不变。 如果
            # 没有一个（第一个 run() 之前），则无需进行实时切换 - 跳过呼叫，只需持久化；
            #  会话创建应用该值（请参阅文档字符串）。
            #
            live = self.agent.has_live_acp_session
            if live:
                self.agent.set_acp_model(model)
            # 持久化以切换模型为权威值。 ``acp_model`` 被冻结，因此我们用带有新值的副本
            # 替换智能体。 这在原地突变错过的两个方面很重要：
            # 1. 新的对象标识使自动保存路径实际上写入 base_state.json（重新分配同一对象
            # 是无操作，因为旧的 == 新的）。
            # 2. model_post_init / _start_acp_server 在重新加载时从 ``acp_model`` 派生出
            # 哨兵值模型和恢复的会话模型，因此它必须保存切换后的值，而不是构造时的值。
            #
            # model_copy 因此，一个活的副本共享了  ACP 运行时 (_conn/_executor/_process)
            #  旧版智能体。 disarm the old 智能体在丢弃它之前，先执行最终化操作：否则
            # ACPAgent.__del__ -> close() 废弃的智能体会摧毁当前复制拥有的会话，让下一次
            # 轮次指向一个断开的连接。 在预会话阶段没有运行时来接管 release_runtime 是不
            # 必要的（已弃用的） 智能体's close() 已经是无操作。
            #
            old_agent = self.agent
            new_agent = old_agent.model_copy(update={"acp_model": model})
            if live:
                new_agent._register_atexit_cleanup(replace=True)
                new_agent._bind_file_credential_masking()
                old_agent.release_runtime()
            # ``self.agent`` 是后续 ``step()`` 调用使用的实时引用；
            # ``self._state.agent`` 是自动保存路径序列化为 base_state.json 的内容。 更新
            # 两者，以便正在运行的对话和已持久化状态在切换模型上达成一致。
            #
            self.agent = new_agent
            self._state.agent = new_agent
            # 保持已持久化模型提示同步 with the switch. 直播智能体's
            # ``current_model_id`` (a PrivateAttr) 已经反映了新模型，并在暖读中获胜，但
            # 在进程重启后冷读会回落到 ``agent_state`` — 该预切换模型将仍然命名，直到下
            # 一次恢复。 写明：成功的切换对任何报告没有的旧/自定义服务器都是权威的
            # ``models`` 在初始化时（因此键可能尚未存在）。
            #
            self._state.agent_state = {
                **self._state.agent_state,
                "acp_current_model_id": model,
            }

    @observe(name="conversation.send_message")
    def send_message(self, message: str | Message, sender: str | None = None) -> None:
        """发送消息至智能体。

        Args:
            message: 一个字符串（将被转换为用户消息）
                    或消息对象
            sender: 发件人的可选标识符。 可用于追踪
                   多智能体场景中的消息来源。 例如，当一个智能体委托给另一个时，可以
                   将发送者设置为识别哪个智能体正在发送消息。
        """
        # ACPAgent 启动时间可能比正常的 send_message() 圆圈往返时间长得多，因为会启动并
        # 初始化一个子进程-支持的会话。 将该工作推迟到 run()，这样远程调用者发送用户消息
        # 的速度就不会变慢。
        #
        if self._should_initialize_agent_on_send_message():
            self._ensure_agent_ready()

        if isinstance(message, str):
            message = Message(role="user", content=[TextContent(text=message)])

        assert message.role == "user", (
            "Only user messages are allowed to be sent to the agent."
        )
        with self._state:
            if self._state.execution_status in (
                ConversationExecutionStatus.FINISHED,
                ConversationExecutionStatus.STUCK,
            ):
                self._state.execution_status = (
                    ConversationExecutionStatus.IDLE
                )  # 新消息重置终端状态

            activated_skill_names: list[str] = []
            extended_content: list[TextContent] = []

            # 处理每轮用户消息（i.e.，知识智能体触发器）
            if self.agent.agent_context:
                ctx = self.agent.agent_context.get_user_message_suffix(
                    user_message=message,
                    # 我们跳过已经激活的技能
                    skip_skill_names=self._state.activated_knowledge_skills,
                )
                # TODO(calvin)：我们需要更新
                # self._state.activated_knowledge_skills所以上下文压缩器可以工作
                #
                if ctx:
                    content, activated_skill_names = ctx
                    logger.debug(
                        f"Got augmented user message content: {content}, "
                        f"activated skills: {activated_skill_names}"
                    )
                    extended_content.append(content)
                    self._state.activated_knowledge_skills.extend(activated_skill_names)

            user_msg_event = MessageEvent(
                source="user",
                llm_message=message,
                activated_skills=activated_skill_names,
                extended_content=extended_content,
                sender=sender,
            )
            self._on_event(user_msg_event)

    def _on_event_with_state_lock(self, event: Event) -> None:
        """保持对话状态锁时发出事件。"""
        with self._state:
            self._on_event(event)

    @contextlib.asynccontextmanager
    async def _released_state_lock_during_io(self):
        """通过等待的 LLM 网络调用释放运行循环的状态锁。

        ``arun()`` 在整个步骤中保持状态锁； 仅在网络等待期间释放它，以保持
        ``send_message()`` 和状态快照的响应。 除非此线程持有锁，
        否则无操作，因此直接 ``astep`` 调用不受影响。 死锁-安全：``arun``是跨过
        ``await``的唯一持有者； 其他所有持有者都只是短暂地接受
        它。
        """
        lock = self._state._lock
        if not lock.owned():
            yield
            return
        held_flag = self._step_holds_state_lock
        depth = lock.release_all()
        # 在释放时保持标志诚实，以便并发 switch_llm（在事件循环线程上）采用现在空闲的锁
        # 而不是竞争突变器。
        #
        self._step_holds_state_lock = False
        try:
            yield
        finally:
            lock.reacquire(depth)
            self._step_holds_state_lock = held_flag

    @observe(name="conversation.run")
    def run(self) -> None:
        """运行对话直到智能体完成。

        在确认模式下：
        - 第一次调用：创建操作但不执行它们，停止并等待
        - 第二次调用：执行待处理的操作（隐式确认）

        正常模式下：
        - 立即创建并执行操作

        步骤之间可以暂停
        """
        with llm_call_context_scope(self._llm_call_context):
            self._run()

    def _run(self) -> None:
        """在活动的 LLM 上下文范围内实现：meth:`run`。"""
        # 确保智能体已完全初始化（加载插件并初始化智能体）
        self._ensure_agent_ready()
        self._cancel_token = CancellationToken()

        with self._state:
            if self._state.execution_status in [
                ConversationExecutionStatus.IDLE,
                ConversationExecutionStatus.PAUSED,
                ConversationExecutionStatus.ERROR,
                ConversationExecutionStatus.STUCK,
            ]:
                self._state.execution_status = ConversationExecutionStatus.RUNNING

        iteration = 0
        _run_start_event_count = len(self._state.events)
        try:
            while True:
                logger.debug(f"Conversation run iteration {iteration}")
                with self._state:
                    # 暂停尝试在锁前修改值之前获取状态。确保在锁已获取时检查步骤条件
                    #
                    if self._state.execution_status in [
                        ConversationExecutionStatus.PAUSED,
                        ConversationExecutionStatus.STUCK,
                    ]:
                        break

                    # FINISHED 上的手柄止动钩
                    if (
                        self._state.execution_status
                        == ConversationExecutionStatus.FINISHED
                    ):
                        if self._hook_processor is not None:
                            should_stop, feedback = self._hook_processor.run_stop(
                                reason="agent_finished"
                            )
                            if not should_stop:
                                logger.info("Stop hook denied agent stopping")
                                if feedback:
                                    prefixed = (
                                        f"{ACP_STOP_HOOK_FEEDBACK_PREFIX} {feedback}"
                                    )
                                    feedback_msg = MessageEvent(
                                        source="environment",
                                        llm_message=Message(
                                            role="user",
                                            content=[TextContent(text=prefixed)],
                                        ),
                                    )
                                    self._on_event(feedback_msg)
                                self._state.execution_status = (
                                    ConversationExecutionStatus.RUNNING
                                )
                                continue
                        # 无钩或钩不允许停
                        break

                    # 检查卡住的模式（如果启用）
                    if self._check_stuck_or_nudge():
                        continue

                    # 在调用 agent.step() 之前清除标志（用户批准）
                    if (
                        self._state.execution_status
                        == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
                    ):
                        self._state.execution_status = (
                            ConversationExecutionStatus.RUNNING
                        )

                    # 将步骤标记为保持状态锁，以便状态突变工具 (e.g. switch_llm) 在工作
                    # 线程上运行线程跳过重新获取它而不是死锁 (#3485)。
                    #
                    self._step_holds_state_lock = True
                    try:
                        self.agent.step(
                            self, on_event=self._on_event, on_token=self._on_token
                        )
                    finally:
                        self._step_holds_state_lock = False
                    iteration += 1

                    # 检查未完成的终端条件
                    # 注意：我们特意在此处执行不检查 FINISHED 状态。
                    # 这允许处理并发个用户消息：
                    # 1. 智能体完成并将状态设置为 FINISHED
                    # 2. 用户通过 send_message() 同时发送消息
                    # 3. send_message() 等待 FIFO 锁，然后将状态设置为 IDLE
                    # 4. 运行循环继续下一次迭代并处理消息
                    # 5. 如果没有这种设计，并发条消息将会丢失
                    if (
                        self.state.execution_status
                        == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
                    ):
                        break

                    budget_detail = self._budget_exceeded_detail()
                    if budget_detail and (
                        self._state.execution_status
                        != ConversationExecutionStatus.FINISHED
                    ):
                        self._emit_run_limit_error("MaxBudgetReached", budget_detail)
                        break

                    if iteration >= self.max_iteration_per_run:
                        # 如果智能体完成了最后一次迭代，则保留 FINISHED 状态而不是用
                        # ERROR 覆盖它。
                        #
                        if (
                            self._state.execution_status
                            == ConversationExecutionStatus.FINISHED
                        ):
                            break
                        error_msg = (
                            f"Agent reached maximum iterations limit "
                            f"({self.max_iteration_per_run})."
                        )
                        logger.error(error_msg)
                        self._state.execution_status = ConversationExecutionStatus.ERROR
                        self._on_event(
                            ConversationErrorEvent(
                                source="environment",
                                code="MaxIterationsReached",
                                detail=error_msg,
                            )
                        )
                        break
        except LLMAuthenticationError as e:
            with self._state:
                self._state.execution_status = ConversationExecutionStatus.ERROR
                self._on_event(
                    ConversationErrorEvent(
                        source="environment",
                        code="LLMAuthenticationError",
                        detail=(
                            "Your LLM API key appears to be invalid or has expired."
                        ),
                    )
                )
            raise ConversationRunError(
                self._state.id, e, persistence_dir=self._state.persistence_dir
            ) from e
        except Exception as e:
            with self._state:
                self._state.execution_status = ConversationExecutionStatus.ERROR

                # 添加一个错误事件 - 除非智能体已经出现了针对此故障的键入的详细事件 (e.g
                # . ACPAgent._emit_turn_error)，否则通用的 str(e) 副本会破坏它。
                #
                if not _agent_already_surfaced_error(
                    self._state.events, _run_start_event_count
                ):
                    self._on_event(
                        ConversationErrorEvent(
                            source="environment",
                            code=e.__class__.__name__,
                            detail=str(e),
                        )
                    )

            # 使用对话 ID 和持久化目录重新提出以获得更好的用户体验
            raise ConversationRunError(
                self._state.id,
                e,
                persistence_dir=self._state.persistence_dir,
                conversation_error=_latest_conversation_error(
                    self._state.events, _run_start_event_count
                ),
            ) from e
        finally:
            self._cancel_token = None

    @observe(name="conversation.arun")
    async def arun(self) -> None:
        """异步：meth:`run` 的变体。

        使用 ``agent.astep()`` 进行非阻塞 LLM I/O，同时保持相同的控制流语义（确认模式
        、卡住检测、停止挂钩、迭代上限）。

        正在运行的任务在 ``_arun_task`` 中跟踪，以便
        :meth:`interrupt` 可以在 LLM 通话中取消它。 开
        ``CancelledError`` 对话转换到 ``PAUSED`` 并发出：class:`InterruptEvent`。

        每次运行都会创建一个新的：class:`CancellationToken` ，以便
        ``interrupt()`` 可以在飞行中发出信号工具调用中止。 之后
        ``CancelledError`` 任何没有匹配观测结果的 ``ActionEvent`` 都会用合成的
        ``AgentErrorEvent`` 进行修补
        ，因此 LLM 对话历史记录保持一致。
        """
        with llm_call_context_scope(self._llm_call_context):
            await self._arun()

    async def _arun(self) -> None:
        """在活动的 LLM 上下文范围内实现：meth:`arun`。"""
        self._arun_task = asyncio.current_task()
        self._cancel_token = CancellationToken()
        # 将延迟初始化卸载到工作线程线程：init_state 可能会阻塞循环（ACP 智能体通过同步
        # LookupSecret httpx.get 解析凭据）。 当智能体-服务器在arun()上运行时，如果事件
        # 循环的查找结果指向同一个单进程服务器，那么直接执行会冻结循环，导致查找永远无法
        # 被服务——一个自我死锁的ReadTimeouts，在30秒后（智能体-canvas#1072）。
        # _ensure_agent_ready是线程安全并且已经在run()中离线运行。
        #
        await asyncio.to_thread(self._ensure_agent_ready)

        with self._state:
            if isinstance(self.agent, ACPAgent) and self._state.execution_status in (
                ConversationExecutionStatus.FINISHED,
                ConversationExecutionStatus.IDLE,
            ):
                updated_agent_state = dict(self._state.agent_state)
                inflight_prompt_user_message_id = updated_agent_state.get(
                    ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID
                )
                if inflight_prompt_user_message_id is not None:
                    updated_agent_state[ACP_LAST_PROMPT_USER_MESSAGE_ID] = (
                        inflight_prompt_user_message_id
                    )
                    updated_agent_state.pop(ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID, None)
                    self._state.agent_state = updated_agent_state

            if self._state.execution_status in [
                ConversationExecutionStatus.IDLE,
                ConversationExecutionStatus.PAUSED,
                ConversationExecutionStatus.ERROR,
                ConversationExecutionStatus.STUCK,
            ]:
                self._state.execution_status = ConversationExecutionStatus.RUNNING
            last_acp_prompt_user_message_id = self._state.agent_state.get(
                ACP_LAST_PROMPT_USER_MESSAGE_ID
            )

        iteration = 0
        _run_start_event_count = len(self._state.events)
        try:
            while True:
                logger.debug(f"Conversation arun iteration {iteration}")
                acp_step_user_message_id: str | None = None
                acp_step_user_message: MessageEvent | None = None
                with self._state:
                    if self._state.execution_status in [
                        ConversationExecutionStatus.PAUSED,
                        ConversationExecutionStatus.STUCK,
                    ]:
                        break

                    if (
                        self._state.execution_status
                        == ConversationExecutionStatus.FINISHED
                    ):
                        if self._hook_processor is not None:
                            should_stop, feedback = self._hook_processor.run_stop(
                                reason="agent_finished"
                            )
                            if not should_stop:
                                logger.info("Stop hook denied agent stopping")
                                if feedback:
                                    prefixed = (
                                        f"{ACP_STOP_HOOK_FEEDBACK_PREFIX} {feedback}"
                                    )
                                    feedback_msg = MessageEvent(
                                        source="environment",
                                        llm_message=Message(
                                            role="user",
                                            content=[TextContent(text=prefixed)],
                                        ),
                                    )
                                    self._on_event(feedback_msg)
                                self._state.execution_status = (
                                    ConversationExecutionStatus.RUNNING
                                )
                                continue
                        break

                    if self._check_stuck_or_nudge():
                        continue

                    if (
                        self._state.execution_status
                        == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
                    ):
                        self._state.execution_status = (
                            ConversationExecutionStatus.RUNNING
                        )

                    if isinstance(self.agent, ACPAgent):
                        # 每次需要最新的尾部时，重新扫描锁下的提示词条消息； 该列表通常
                        # 很小，并且正确性比缓存陈旧的提示词快照更重要。
                        #

                        acp_prompt_messages = [
                            event
                            for event in self._state.active_branch()
                            if _is_acp_prompt_message(event)
                        ]
                        if last_acp_prompt_user_message_id is None:
                            acp_step_user_message = (
                                acp_prompt_messages[0] if acp_prompt_messages else None
                            )
                        else:
                            last_prompt_index = next(
                                (
                                    index
                                    for index, event in enumerate(acp_prompt_messages)
                                    if event.id == last_acp_prompt_user_message_id
                                ),
                                None,
                            )
                            if last_prompt_index is None:
                                logger.info(
                                    "ACP prompt cursor %s no longer exists; "
                                    "restarting from first available prompt",
                                    last_acp_prompt_user_message_id,
                                )
                                acp_step_user_message = (
                                    acp_prompt_messages[0]
                                    if acp_prompt_messages
                                    else None
                                )
                            else:
                                acp_step_user_message = (
                                    acp_prompt_messages[last_prompt_index + 1]
                                    if last_prompt_index + 1 < len(acp_prompt_messages)
                                    else None
                                )
                        acp_step_user_message_id = (
                            acp_step_user_message.id
                            if acp_step_user_message is not None
                            else None
                        )
                    else:
                        # 状态锁在此等待期间保持。 astep() 内部执行的突变（包括在事件循
                        # 环线程上突变的本机异步 Agent.astep / ACPAgent.astep）是有意的
                        # ，并且是此关键部分的一部分。 不变量只是没有
                        # *不相关的*状态突变器可以同时运行
                        # 锁举行：因为 FIFOLock 是线程-（不是任务-）可重入，在该事件循环
                        # 线程上等待的任何无关紧要的状态改变协程会悄无声息地重新进入锁并
                        # 破坏历史。 这些无关的修改器必须通过 run_in_executor 发送到一个
                        # 工人线程。 将步骤标记为持有状态锁，并使用状态修改工具（e.g）。
                        #  switch_llm）在 worker 线程上运行，跳过重新获取它，而是在
                        # await 持有它时死锁 (#3485)。
                        #
                        self._step_holds_state_lock = True
                        last_user_message_id = self._state.last_user_message_id
                        try:
                            await self.agent.astep(
                                self,
                                on_event=self._on_event,
                                on_token=self._on_token,
                            )
                        finally:
                            self._step_holds_state_lock = False
                        iteration += 1

                        # astep 释放 LLM 调用的状态锁，因此消息可以在状态仍为 RUNNING 的
                        # 情况下到达中间，并且不会被记录； 如果没有这个重扫，循环会中断
                        # （或者落后于一个陈旧的待确认）智能体-canvas#1900。 镜像下面的
                        # ACP 分支的重新扫描。 step_finished 是在此重新扫描之前捕获的，
                        # 可以将状态翻转回 RUNNING，因此下面的预算分配仍然可以看到该步骤
                        # 的实际结果。
                        #
                        step_finished = (
                            self._state.execution_status
                            == ConversationExecutionStatus.FINISHED
                        )
                        step_awaiting_confirmation = (
                            self._state.execution_status
                            == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
                        )
                        new_message_arrived = (
                            self._state.last_user_message_id != last_user_message_id
                        )
                        if new_message_arrived and (
                            step_finished or step_awaiting_confirmation
                        ):
                            if step_awaiting_confirmation:
                                # 预先拒绝，无论我们是否
                                # continue running or go IDLE below: astep()
                                # 它会执行它发现的任何在途操作，作为隐式确认，因此不匹配
                                # 它会继续运行在下一次调用中，悄无声息地覆盖新的消息。
                                #
                                logger.info(
                                    "User message arrived while awaiting "
                                    "confirmation; rejecting the pending action"
                                )
                                self.reject_pending_actions(
                                    "Superseded by a new user message"
                                )
                            if iteration >= self.max_iteration_per_run:
                                logger.info(
                                    "User message arrived during final iteration; "
                                    "leaving conversation idle for a follow-up run"
                                )
                                self._state.execution_status = (
                                    ConversationExecutionStatus.IDLE
                                )
                                break
                            if not step_awaiting_confirmation:
                                logger.info(
                                    "User message arrived during step; continuing run"
                                )
                            self._state.execution_status = (
                                ConversationExecutionStatus.RUNNING
                            )

                        if (
                            self.state.execution_status
                            == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
                        ):
                            break

                        budget_detail = self._budget_exceeded_detail()
                        if budget_detail and not step_finished:
                            self._emit_run_limit_error(
                                "MaxBudgetReached", budget_detail
                            )
                            break

                        if iteration >= self.max_iteration_per_run:
                            if (
                                self._state.execution_status
                                == ConversationExecutionStatus.FINISHED
                            ):
                                break
                            error_msg = (
                                f"Agent reached maximum iterations limit "
                                f"({self.max_iteration_per_run})."
                            )
                            logger.error(error_msg)
                            self._state.execution_status = (
                                ConversationExecutionStatus.ERROR
                            )
                            self._on_event(
                                ConversationErrorEvent(
                                    source="environment",
                                    code="MaxIterationsReached",
                                    detail=error_msg,
                                )
                            )
                            break

                        continue

                # ACP 提示词往返可以运行几分钟。 在等待时保持状态锁空闲，以便传入的用户
                # 消息可以立即已持久化； 事件回调仅针对每个单独的突变采用锁。
                #
                if acp_step_user_message is None:
                    with self._state:
                        latest_acp_prompt_message_id = (
                            self._latest_acp_prompt_message_id()
                        )
                        acp_prompt_message_changed = (
                            latest_acp_prompt_message_id is not None
                            and latest_acp_prompt_message_id
                            != last_acp_prompt_user_message_id
                        )
                        if acp_prompt_message_changed:
                            if iteration >= self.max_iteration_per_run:
                                logger.info(
                                    "User message arrived before ACP finish; "
                                    "leaving conversation idle for a follow-up run"
                                )
                                self._state.execution_status = (
                                    ConversationExecutionStatus.IDLE
                                )
                                break
                            logger.info(
                                "User message arrived before ACP finish; continuing run"
                            )
                            self._state.execution_status = (
                                ConversationExecutionStatus.RUNNING
                            )
                            continue
                        self._state.execution_status = (
                            ConversationExecutionStatus.FINISHED
                        )
                    break

                acp_step_start_event_count = 0
                with self._state:
                    if self._state.execution_status in (
                        ConversationExecutionStatus.PAUSED,
                        ConversationExecutionStatus.STUCK,
                    ):
                        break
                    acp_step_start_event_count = len(self._state.events)
                    if acp_step_user_message_id is not None:
                        self._state.agent_state = {
                            **self._state.agent_state,
                            ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID: (
                                acp_step_user_message_id
                            ),
                        }

                await self.agent.astep(
                    self,
                    on_event=self._on_event_with_state_lock,
                    on_token=self._on_token,
                    prompt_message=acp_step_user_message,
                )
                with self._state:
                    iteration += 1
                    pause_requested_during_acp_step = any(
                        isinstance(event, PauseEvent)
                        for event in self._state.events[acp_step_start_event_count:]
                    )
                    updated_agent_state = dict(self._state.agent_state)
                    if (
                        updated_agent_state.get(ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID)
                        == acp_step_user_message_id
                    ):
                        updated_agent_state.pop(
                            ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID, None
                        )
                    updated_agent_state.pop(ACP_SUPERSEDE_INFLIGHT_PROMPT, None)
                    if (
                        acp_step_user_message_id is not None
                        and self._state.execution_status
                        not in (
                            ConversationExecutionStatus.ERROR,
                            ConversationExecutionStatus.STUCK,
                            ConversationExecutionStatus.PAUSED,
                        )
                    ):
                        last_acp_prompt_user_message_id = acp_step_user_message_id
                        updated_agent_state[ACP_LAST_PROMPT_USER_MESSAGE_ID] = (
                            acp_step_user_message_id
                        )
                    self._state.agent_state = updated_agent_state

                    if self._state.execution_status in (
                        ConversationExecutionStatus.ERROR,
                        ConversationExecutionStatus.STUCK,
                    ):
                        break
                    if pause_requested_during_acp_step:
                        self._state.execution_status = (
                            ConversationExecutionStatus.PAUSED
                        )
                        break

                    latest_acp_prompt_message_id = self._latest_acp_prompt_message_id()
                    acp_prompt_message_changed = (
                        latest_acp_prompt_message_id is not None
                        and latest_acp_prompt_message_id
                        != last_acp_prompt_user_message_id
                    )
                    if acp_prompt_message_changed and self._state.execution_status in (
                        ConversationExecutionStatus.FINISHED,
                        ConversationExecutionStatus.IDLE,
                    ):
                        if iteration >= self.max_iteration_per_run:
                            logger.info(
                                "User message arrived during final ACP iteration; "
                                "leaving conversation idle for a follow-up run"
                            )
                            self._state.execution_status = (
                                ConversationExecutionStatus.IDLE
                            )
                            break
                        logger.info(
                            "User message arrived during ACP step; continuing run"
                        )
                        self._state.execution_status = (
                            ConversationExecutionStatus.RUNNING
                        )

                    if (
                        self.state.execution_status
                        == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
                    ):
                        break

                    budget_detail = self._budget_exceeded_detail()
                    if budget_detail and (
                        self._state.execution_status
                        != ConversationExecutionStatus.FINISHED
                    ):
                        self._emit_run_limit_error("MaxBudgetReached", budget_detail)
                        break

                    if iteration >= self.max_iteration_per_run:
                        if (
                            self._state.execution_status
                            == ConversationExecutionStatus.FINISHED
                        ):
                            break
                        error_msg = (
                            f"Agent reached maximum iterations limit "
                            f"({self.max_iteration_per_run})."
                        )
                        logger.error(error_msg)
                        self._state.execution_status = ConversationExecutionStatus.ERROR
                        self._on_event(
                            ConversationErrorEvent(
                                source="environment",
                                code="MaxIterationsReached",
                                detail=error_msg,
                            )
                        )
                        break
        except asyncio.CancelledError:
            # CancelledError 被故意重新加注不。 ``interrupt()`` 使用
            # ``asyncio.Task.cancel()`` 来突破 ``arun()``，并期望任务完全终止。 重新加注
            # 会将取消传播到 EventService/调用者，这会将其显示为意外错误。 相反，我们过
            # 渡到 PAUSED，以便稍后可以恢复对话。
            #
            logger.info("arun() interrupted via task cancellation")
            with self._state:
                updated_agent_state = dict(self._state.agent_state)
                inflight_prompt_user_message_id = updated_agent_state.pop(
                    ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID, None
                )
                superseded_by_new_message = bool(
                    updated_agent_state.pop(ACP_SUPERSEDE_INFLIGHT_PROMPT, False)
                )
                completed_cancelled_prompt = (
                    self._state.execution_status == ConversationExecutionStatus.FINISHED
                )
                if (
                    superseded_by_new_message or completed_cancelled_prompt
                ) and inflight_prompt_user_message_id is not None:
                    updated_agent_state[ACP_LAST_PROMPT_USER_MESSAGE_ID] = (
                        inflight_prompt_user_message_id
                    )
                self._state.agent_state = updated_agent_state

                # 对于中断到达时正在运行的任何 ActionEvents，发出综合错误观测结果。 如果
                # 没有这些，LLM 历史记录将包含没有工具结果的工具调用请求，这会导致下一次
                # 完成调用时提供程序错误。
                #
                self._emit_orphaned_action_errors()

                self._state.execution_status = ConversationExecutionStatus.PAUSED
                self._on_event(InterruptEvent())
        except LLMAuthenticationError as e:
            with self._state:
                self._state.execution_status = ConversationExecutionStatus.ERROR
                self._on_event(
                    ConversationErrorEvent(
                        source="environment",
                        code="LLMAuthenticationError",
                        detail=(
                            "Your LLM API key appears to be invalid or has expired."
                        ),
                    )
                )
            raise ConversationRunError(
                self._state.id, e, persistence_dir=self._state.persistence_dir
            ) from e
        except Exception as e:
            with self._state:
                updated_agent_state = dict(self._state.agent_state)
                updated_agent_state.pop(ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID, None)
                updated_agent_state.pop(ACP_SUPERSEDE_INFLIGHT_PROMPT, None)
                self._state.agent_state = updated_agent_state
                self._state.execution_status = ConversationExecutionStatus.ERROR
                # 如果智能体已经针对此故障显示了键入的详细事件，请跳过一般事件（请参阅
                # _agent_already_surfaced_error）。
                #
                if not _agent_already_surfaced_error(
                    self._state.events, _run_start_event_count
                ):
                    self._on_event(
                        ConversationErrorEvent(
                            source="environment",
                            code=e.__class__.__name__,
                            detail=str(e),
                        )
                    )
            raise ConversationRunError(
                self._state.id,
                e,
                persistence_dir=self._state.persistence_dir,
                conversation_error=_latest_conversation_error(
                    self._state.events, _run_start_event_count
                ),
            ) from e
        finally:
            # 已取消的 token 必须保持可观察：中断的工具调用在工作程序线程中运行，可以比
            # arun() 存活并仍然轮询它。 在下一个 run() 上创建新的 token。
            #
            if self._cancel_token is not None and not self._cancel_token.is_cancelled:
                self._cancel_token = None
            self._arun_task = None

    def set_confirmation_policy(self, policy: ConfirmationPolicyBase) -> None:
        """设置确认策略并保存在会话状态。"""
        with self._state:
            self._state.confirmation_policy = policy
        logger.info(f"Confirmation policy set to: {policy}")

    @property
    def on_stream(self) -> StreamProgressCallbackType | None:
        """流进度帧的接收器，如果没有任何消耗它们，则为 ``None``。

        由智能体读取而不是传递给 ``step``：新的 ``step`` 参数会破坏每个第三方
        ``AgentBase`` 子类。
        """
        return self._on_stream

    def set_token_callbacks(
        self, token_callbacks: list[ConversationTokenCallbackType] | None
    ) -> None:
        """施工完成后更换token-流式传输回调。

        恢复时，智能体在构造时未知（它是从
        ``base_state.json``），因此调用者只能了解解析后的智能体是否可以随后发出 token
         增量。 使用此选项可在此时启用或禁用 token 流
        式传输。 传递 ``None`` 或空列表会禁用它。
        """
        self._on_token = (
            BaseConversation.compose_callbacks(token_callbacks)
            if token_callbacks
            else None
        )

    def reject_pending_actions(self, reason: str = "User rejected the action") -> None:
        """拒绝来自智能体的所有待处理操作。

        这是一种拒绝 run() 调用之间的操作的非侵入性方法。 还清除
        agent_waiting_for_confirmation 标志。
        """
        pending_actions = ConversationState.get_unmatched_actions(
            self._state.active_branch()
        )

        with self._state:
            # 始终清除 agent_waiting_for_confirmation 标志
            if (
                self._state.execution_status
                == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
            ):
                self._state.execution_status = ConversationExecutionStatus.IDLE

            if not pending_actions:
                logger.warning("No pending actions to reject")
                return

            for action_event in pending_actions:
                # 创建拒绝观测结果
                rejection_event = UserRejectObservation(
                    action_id=action_event.id,
                    tool_name=action_event.tool_name,
                    tool_call_id=action_event.tool_call_id,
                    rejection_reason=reason,
                )
                record_tool_result(
                    self,
                    name=extract_action_name(action_event),
                    tool_call_id=action_event.tool_call_id,
                    tool_input=action_event.action,
                    tool_output=rejection_event.to_llm_message(),
                )
                self._on_event(rejection_event)
                logger.info(f"Rejected pending action: {action_event} - {reason}")

    def _emit_orphaned_action_errors(self) -> None:
        """对于没有观测结果的操作发出 ``AgentErrorEvent``。

        中断后，正在飞行的工具调用可能有他们的
        ``ActionEvent`` 已在历史记录中但没有对应的
        ``ObservationEvent``. LLM 提供商拒绝带有孤立工具调用请求的对话历史记录，因此
        我们用合成错误回填它们。

        必须在按住 ``self._state`` 的情况下调用。
        """
        orphans = ConversationState.get_unmatched_actions(self._state.active_branch())
        for ae in orphans:
            logger.info(
                "Emitting synthetic error for orphaned action %s (%s)",
                ae.id,
                ae.tool_name,
            )
            self._on_event(
                AgentErrorEvent(
                    error=(
                        "Tool call interrupted before completion. "
                        "The conversation was paused."
                    ),
                    tool_name=ae.tool_name,
                    tool_call_id=ae.tool_call_id,
                    classification=AGENT_OUTCOME,
                )
            )

    def pause(self) -> None:
        """暂停智能体执行。

        可以从任何线程调用此方法来请求智能体暂停执行。 暂停将在运行循环的下一次迭代时
        生效（在智能体个步骤之间）。

        Note: 如果在 LLM 完成期间调用，则不会暂停
        直到当前 LLM 调用完成为止。
        """

        if self._state.execution_status == ConversationExecutionStatus.PAUSED:
            return

        with self._state:
            # 仅在运行或闲置时暂停
            if (
                self._state.execution_status == ConversationExecutionStatus.IDLE
                or self._state.execution_status == ConversationExecutionStatus.RUNNING
            ):
                self._state.execution_status = ConversationExecutionStatus.PAUSED
                pause_event = PauseEvent()
                self._on_event(pause_event)
                logger.info("Agent execution pause requested")

    def interrupt(self) -> None:
        """立即取消飞行中的 ``arun()``，包括通话中的 LLM。

        如果异步运行正在进行，则基础 ``asyncio.Task`` 将被取消； ``arun()`` 捕获结果
        ``CancelledError``，将执行状态
        设置为 ``PAUSED``，并发出一个
        ：类：`~openhands.sdk.event.InterruptEvent`。

        取消 token 在 * 取消任务之前设置 *，以便：class:`ParallelToolExecutor` 可以跳
        过挂起的工具调用，并且各个工具可以检查
        是否提前退出。

        如果没有跟踪异步任务 (e.g. 同步 ``run()`` 处于活动状态）调用回退到：meth:
        `pause`。

        从信号处理程序和其他线程调用此方法是安全的（取消安排在任务的事件循环上）。
        """
        # 首先设置取消 token，以便线程池工作线程在取消 asyncio 任务之前看到它。
        #
        token = self._cancel_token
        if token is not None:
            token.cancel()

        task = self._arun_task
        if task is not None and not task.done():
            # 将取消编组到任务的事件循环上，以便从任何线程 (e.g. 信号处理程序，智能体-服
            # 务器的 HTTP 线程）。
            #
            loop = task.get_loop()
            loop.call_soon_threadsafe(task.cancel)
            logger.info("interrupt(): cancelled in-flight arun() task")
        else:
            self.pause()

    def update_secrets(self, secrets: Mapping[str, SecretValue]) -> None:
        """将机密添加到对话的机密注册表中。

        机密存储在对话的 secret_registry 中，其中：
        1. 在命令执行期间提供环境变量注入
        2. 在构建系统提示词 (dynamic_context) 时由智能体读取

        智能体在 init_state() 期间通过 get_dynamic_context() 从注册表中拉出机密，确保
        机密名称和描述出现在提示词中。

        Args:
            secrets: 字典将机密键映射到值或无参数可调用对象。
                     SecretValue = str | Callable[[], str]. Callables are invoked lazily
                     当命令引用机密键时。
        """
        with self._state:
            self._state.secret_registry.update_secrets(secrets)
        logger.info(f"Added {len(secrets)} secrets to conversation")

    def set_security_analyzer(self, analyzer: SecurityAnalyzerBase | None) -> None:
        """设置对话的安全分析器。"""
        with self._state:
            self._state.security_analyzer = analyzer

    def close(self) -> None:
        """关闭对话并清理所有工具执行器。"""
        if self._cleanup_complete:
            return
        first_attempt = not self._cleanup_initiated
        if first_attempt:
            self._cleanup_initiated = True

            # 尽力而为：将累积的 LLM 成本交给工作区，以便将其包含在自动化完成回调中。 这
            # 里的状态是进程内的，因此与RemoteConversation不同的是，没有缓存可供查询，也
            # 没有可能阻止死服务器的获取。
            #
            try:
                cost = self._state.stats.get_combined_metrics().accumulated_cost
                self.workspace.register_cost(cost)
            except Exception as e:
                logger.debug(f"Could not register accumulated cost: {e}")

            logger.debug("Closing conversation and cleaning up tool executors")
            hook_processor = self._hook_processor
            if hook_processor is not None:
                hook_processor.run_session_end()
            try:
                self._end_observability_span()
            except AttributeError:
                pass
        # 清理智能体资源(e.g., ACPAgent 子进程)
        agent_error: Exception | None = None
        try:
            self.agent.close()
        except Exception as e:
            logger.warning(f"Error closing agent: {e}")
            agent_error = e
        # 始终关闭工具执行器——它们持有运行时资源子进程必须释放的连接、会话等数据，无论对
        # 话数据是否保留delete_on_close).
        #
        if first_attempt:
            with contextlib.suppress(AttributeError, RuntimeError):
                for tool in self.agent.tools_map.values():
                    with contextlib.suppress(NotImplementedError):
                        try:
                            executable_tool = tool.as_executable()
                            executable_tool.executor.close()
                        except Exception as e:
                            logger.warning(
                                f"Error closing executor for tool '{tool.name}': {e}"
                            )
        if isinstance(agent_error, CredentialBindingError):
            raise agent_error
        self._cleanup_complete = True
        atexit.unregister(self.close)

    @observe(
        name="conversation.ask_agent",
        metadata={OPERATION_METADATA_KEY: "ask_agent"},
    )
    def ask_agent(self, question: str) -> str:
        """向智能体提出一个简单的、无状态的问题，并获得直接的 LLM 响应。

        这绕过了正常的对话流程，并且 ** 不 ** 修改持久化或成为对话状态的一部分。 主程
        序智能体不会记住该请求，不会记录任何事件，并且执行状态不变。 它也是线
        程安全，并且可以在 `conversation.run()` 在另一个线程中执行时被调用。

        Args:
            question: 一个简单的字符串问题要问智能体

        Returns:
            来自智能体的字符串响应
        """
        # 确保智能体已初始化（需要 tools_map）
        self._ensure_agent_ready()

        # 尝试智能体特定的覆盖选项 (e.g. ACPAgent 使用 fork_session)
        agent_response = self.agent.ask_agent(question)
        if agent_response is not None:
            return agent_response

        # 在这里导入以避免循环导入
        from openhands.sdk.agent.utils import prepare_llm_messages

        template_dir = (
            Path(__file__).parent.parent.parent / "context" / "prompts" / "templates"
        )

        question_text = render_template(
            str(template_dir), "ask_agent_template.j2", question=question
        )

        # 创建包含上下文感知问题的用户消息
        user_message = Message(
            role="user",
            content=[TextContent(text=question_text)],
        )

        messages = prepare_llm_messages(
            self.state.enforced_view_snapshot(), additional_messages=[user_message]
        )

        # 获取或创建专门的询问-智能体 LLM
        try:
            question_llm = self.llm_registry.get(ASK_AGENT_LLM_USAGE_ID)
        except KeyError:
            # stream=False: the reply is consumed whole with no on_token
            # 回调，流式传输LLM 需要。
            question_llm = self.agent.llm.model_copy(
                update={
                    "usage_id": ASK_AGENT_LLM_USAGE_ID,
                    "stream": False,
                },
            )
            self.llm_registry.add(question_llm)

        # 传递智能体工具，以便 LLM 可以理解对话历史记录中的 tool_calls
        response = question_llm.generate(
            messages=messages,
            tools=list(self.agent.tools_map.values()),
            store=False,
            call_context=self._llm_call_context,
        )

        message = response.message

        # 从LLMResponse消息中提取文本内容
        if message.content and len(message.content) > 0:
            # 查找响应中的第一个 TextContent
            for content in response.message.content:
                if isinstance(content, TextContent):
                    return content.text

        raise Exception("Failed to generate summary")

    @observe(
        name="conversation.generate_title",
        ignore_inputs=["llm"],
        metadata={OPERATION_METADATA_KEY: "title_generation"},
    )
    def generate_title(self, llm: LLM | None = None, max_length: int = 50) -> str:
        """根据第一条用户消息生成对话标题。

        如果提供了明确的 LLM，则优先。 否则使用智能体的 LLM。 如果两者都不可用，则标
        题将退回到简单的消息截断。

        Args:
            llm: 可选 LLM 用于标题生成。 优先
                 超过智能体的 LLM（如果提供）。
            max_length: 生成的标题的最大长度。

        Returns:
            为对话生成的标题。

        Raises:
            ValueError: 如果在对话中没有找到用户消息。
        """
        effective_llm = llm if llm is not None else self.agent.llm
        return generate_conversation_title(
            events=self._state.active_branch(),
            llm=effective_llm,
            max_length=max_length,
            call_context=self._llm_call_context,
        )

    def condense(self) -> None:
        """同步强制压缩对话历史记录。

        如果智能体当前正在运行，`condense()` 将等待正在进行的步骤完成后再继续。

        如果不存在兼容的上下文压缩器，则引发 ValueError。
        """
        with llm_call_context_scope(self._llm_call_context):
            self._condense()

    def _condense(self) -> None:
        """在活动的 LLM 上下文范围内实现：meth:`condense`。"""

        # 检查上下文压缩器是否已配置并处理上下文压缩请求
        if (
            self.agent.condenser is None
            or not self.agent.condenser.handles_condensation_requests()
        ):
            condenser_info = (
                "No condenser configured"
                if self.agent.condenser is None
                else (
                    f"Condenser {type(self.agent.condenser).__name__} does not handle "
                    "condensation requests"
                )
            )
            raise ValueError(
                f"Cannot condense conversation: {condenser_info}. "
                "To enable manual condensation, configure an "
                "LLMSummarizingCondenser:\n\n"
                "from openhands.sdk.context.condenser import LLMSummarizingCondenser\n"
                "agent = Agent(\n"
                "    llm=your_llm,\n"
                "    condenser=LLMSummarizingCondenser(\n"
                "        llm=your_llm,\n"
                "        max_size=120,\n"
                "        keep_first=4\n"
                "    )\n"
                ")"
            )

        # 添加上下文压缩请求事件
        condensation_request = CondensationRequest()
        self._on_event(condensation_request)

        # 力的智能体单步处理以下内容上下文压缩请求。这会触发上下文压缩器如果它能处理上下
        # 文压缩请求
        #
        with self._state:
            # 一步处理上下文压缩请求
            self.agent.step(self, on_event=self._on_event, on_token=self._on_token)

        logger.info("Condensation request processed")

    def rerun_actions(
        self,
        rerun_log_path: str | Path | None = None,
    ) -> bool:
        """重新执行对话事件历史记录中的所有操作。

        此方法迭代对话中的所有 ActionEvents 并使用其原始操作参数重新执行它们。 如果任
        何工具调用失败，执行将立即停止。

        WARNING: 这是一项针对特定用例的高级功能
        例如从保存的对话中再现环境状态。 许多工具操作都是不幂等的：

        - 如果文件已存在或已删除，文件操作可能会失败
        - 终端命令可能会对更改后的状态产生不同的影响
        - API 调用可能会产生副作用或返回不同的结果
        - 浏览器状态可能与原始会话不同

        仅当您了解以下情况时才使用此方法：
        1. 结果可能与原始对话不同
        2. 由于环境状态发生变化，某些操作可能会失败
        3. 工作区通常应在重新运行之前重置

        Args:
            rerun_log_path: 用于保存重新运行事件日志的可选目录路径。
                如果提供，事件将使用 EventLog 增量写入磁盘，避免大型对话的内存堆积。

        Returns:
            True 如果所有操作均成功执行，False 如果任何操作失败。

        Raises:
            KeyError: 如果原始对话中的工具不可用。
                这是配置错误（与执行失败不同）。
        """
        # 确保智能体已初始化（加载插件并初始化工具）
        self._ensure_agent_ready()

        # 如果提供路径，则设置重新运行日志
        rerun_log: EventLog | None = None
        if rerun_log_path is not None:
            log_dir = Path(rerun_log_path)
            log_dir.mkdir(parents=True, exist_ok=True)
            file_store = LocalFileStore(str(log_dir))
            rerun_log = EventLog(file_store, dir_path="events")

        action_count = 0

        for event in self._state.events:
            if not isinstance(event, ActionEvent):
                continue
            if event.action is None:
                # 跳过原始运行期间失败验证的操作
                continue

            action_count += 1
            tool_name = event.tool_name

            # 从智能体的tools_map获取工具
            tool = self.agent.tools_map.get(tool_name)
            if tool is None:
                available_tools = list(self.agent.tools_map.keys())
                raise KeyError(
                    f"Tool '{tool_name}' not found during rerun. "
                    f"Available tools: {available_tools}. "
                    f"Ensure the agent is configured with the same tools as the "
                    f"original conversation."
                )

            if not tool.executor:
                logger.warning(
                    f"Skipping action {action_count}: "
                    f"tool '{tool_name}' has no executor"
                )
                continue

            # 使用原始操作执行工具
            try:
                logger.info(f"Rerunning action {action_count}: {tool_name}")
                observation = tool(event.action, self)

                # 增量记录操作和观测结果
                if rerun_log is not None:
                    # 附加操作事件（从原始副本复制）
                    rerun_log.append(event)
                    # 追加观测结果事件
                    obs_event = ObservationEvent(
                        source="environment",
                        tool_name=tool_name,
                        tool_call_id=event.tool_call_id,
                        observation=observation,
                        action_id=event.id,
                    )
                    rerun_log.append(obs_event)
            except Exception as e:
                logger.error(
                    f"Action {action_count} ({tool_name}) failed during rerun: {e}"
                )
                # 日志已经增量写入，直接返回失败
                return False

        logger.info(f"Rerun complete: {action_count} actions processed successfully")
        return True

    def execute_tool(self, tool_name: str, action: Action) -> Observation:
        """直接执行工具，无需经过智能体循环。

        此方法允许在正常 conversation.run() 流程之前或之外执行工具。 它自动处理智能体
        初始化，因此可以在第一次 run() 调用之前执行工具。

        Note: 该方法绕过智能体循环，包括确认
        策略和安全分析器检查。 调用者有责任在执行潜在破坏性工具之前应用任何保护措施。

        这对于：
        - 预运行设置操作（e.g.，索引存储库）
        - 用于环境设置的手动工具执行
        - 测试智能体循环之外的工具行为

        Args:
            tool_name: 要执行的工具的名称（e.g.，“sleeptime_compute”）
            action: 传递给工具执行器的操作

        Returns:
            工具执行返回的观测结果

        Raises:
            KeyError: 如果在智能体的工具中没有找到该工具
            NotImplementedError: 如果该工具没有执行器
        """
        # 确保智能体已初始化（加载插件并初始化工具）
        self._ensure_agent_ready()

        # 从智能体的tools_map获取工具
        tool = self.agent.tools_map.get(tool_name)
        if tool is None:
            available_tools = list(self.agent.tools_map.keys())
            raise KeyError(
                f"Tool '{tool_name}' not found. Available tools: {available_tools}"
            )

        # 执行工具
        if not tool.executor:
            raise NotImplementedError(f"Tool '{tool_name}' has no executor")
        return tool(action, self)

    def __del__(self) -> None:
        """确保在对话被破坏时进行清理。"""
        try:
            self.close()
        except Exception as e:
            logger.warning(f"Error during conversation cleanup: {e}", exc_info=True)
