import asyncio
import importlib
import json
import logging
import os
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4
from weakref import WeakValueDictionary

import httpx
from pydantic import BaseModel

from openhands.agent_server.config import ACPSkillSourcing, Config, WebhookSpec
from openhands.agent_server.conversation_lease import (
    DEFAULT_LEASE_TTL_SECONDS,
    ConversationLeaseHeldError,
)
from openhands.agent_server.event_service import (
    LEASE_RENEW_INTERVAL_SECONDS,
    EventService,
    RunSlot,
)
from openhands.agent_server.launch import (
    is_codex_source,
    launch_source,
    live_launch_runtime,
    scoped_secrets,
    server_launch_stores,
)
from openhands.agent_server.local_storage import (
    conversation_worktree_dir,
    remove_conversation_worktree,
)
from openhands.agent_server.models import (
    ConversationInfo,
    ConversationPage,
    ConversationSortOrder,
    LaunchedAgentProfile,
    StartChildConversationRequest,
    StartChildConversationResponse,
    StartConversationRequest,
    StoredConversation,
    UpdateConversationRequest,
)
from openhands.agent_server.persistence import FileSecretsStore
from openhands.agent_server.pub_sub import Subscriber
from openhands.agent_server.server_details_router import update_last_execution_time
from openhands.agent_server.telemetry import (
    ConversationTelemetryContext,
    DiagnosticEventFactory,
    TelemetrySubscriber,
    get_event_factory,
    get_telemetry_sink,
)
from openhands.agent_server.telemetry.sanitizer import model_family, safe_token
from openhands.agent_server.utils import safe_rmtree, utc_now
from openhands.sdk import LLM, Event, Message, TextContent
from openhands.sdk.agent import ACPAgent
from openhands.sdk.agent.acp_file_credentials import CODEX_AUTH_SECRET_NAME
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.persistence_const import BASE_STATE
from openhands.sdk.conversation.request import ConversationWorktreeOptions
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.conversation.title_utils import (
    extract_message_text,
    generate_title_from_message,
)
from openhands.sdk.credential import (
    CredentialAuthorizationRejected,
    CredentialBindingError,
    VersionedCredentialBinding,
)
from openhands.sdk.event import MessageEvent
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from openhands.sdk.git.exceptions import GitCommandError, GitRepositoryError
from openhands.sdk.git.utils import run_git_command, validate_git_repository
from openhands.sdk.launch import LaunchedAgent, finalize
from openhands.sdk.llm.call_context import LLMCallContext
from openhands.sdk.mcp.utils import MCPToolProvider
from openhands.sdk.observability import OPERATION_METADATA_KEY, observe
from openhands.sdk.tool.client_tool import register_client_tools
from openhands.sdk.tool.registry import get_tool_module_qualnames, is_tool_available
from openhands.sdk.utils.cipher import Cipher
from openhands.sdk.workspace import LocalWorkspace


if TYPE_CHECKING:
    from openhands.sdk.subagent.schema import AgentDefinition


_AUTOMATION_TAG_KEYS = ("automationtrigger", "automationid", "automationrunid")


class CredentialBindingActivationRequired(RuntimeError):
    pass


def _build_worktree_guidance(
    *,
    source_workspace: Path,
    worktree_root: Path,
    workspace_dir: Path,
    branch: str,
    options: ConversationWorktreeOptions,
) -> str:
    base_ref = {
        "head": "the original workspace's current HEAD",
        "ref": f"`{options.ref}`",
    }.get(options.base, "the main/master branch")
    return (
        "This conversation uses a dedicated git worktree.\n"
        f"- Original workspace: {source_workspace}\n"
        f"- Worktree root: {worktree_root}\n"
        f"- Active workspace: {workspace_dir}\n"
        f"- Branch: {branch}\n"
        "Do all file and git work inside this worktree. Do your work on a new, "
        f"appropriately-named branch, based off {base_ref}, "
        "and do not switch back to the original workspace."
    )


def _has_git_remote(repo_root: Path, remote: str = "origin") -> bool:
    try:
        run_git_command(["git", "remote", "get-url", remote], repo_root)
    except GitCommandError:
        return False
    return True


def _local_branch_exists(repo_root: Path, branch: str) -> bool:
    try:
        run_git_command(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            repo_root,
        )
    except GitCommandError:
        return False
    return True


def _fetch_origin(repo_root: Path) -> None:
    """刷新 ``origin`` 的参考以获取工作树起点； 保持缓存的开启
    失败。"""
    try:
        run_git_command(["git", "fetch", "origin"], repo_root, timeout=60)
    except GitCommandError as exc:
        logger.warning(
            "git fetch origin failed while choosing worktree start point "
            "for %s; using cached refs. Error: %s",
            repo_root,
            exc,
        )


def _get_worktree_start_point(repo_root: Path) -> str:
    """解析应从中创建新对话工作树的基本引用。

    政策（按顺序）：
      1. 如果配置了 ``origin`` 遥控器，则为 ``origin/<default_branch>``。
         ``git fetch origin`` 首先运行，因此工作树从最新的远程提示开始； 默认分支通过
         以下方式解析
         ``refs/remotes/origin/HEAD``.
      2. 如果没有可用的远程默认值，则本地 ``main``，但本地存在 ``main``。
      3. 如果远程默认值和本地 ``main`` 都不可用，则本地 ``master``。
      4. 仅当上述 None 适用时才回退到 ``HEAD``。 规划器检查所选引用是否解析为提交。
    """
    if _has_git_remote(repo_root):
        _fetch_origin(repo_root)
        try:
            ref = run_git_command(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                repo_root,
            )
        except GitCommandError:
            ref = ""
        prefix = "refs/remotes/origin/"
        if ref.startswith(prefix):
            return f"origin/{ref[len(prefix) :]}"

    if _local_branch_exists(repo_root, "main"):
        return "main"
    if _local_branch_exists(repo_root, "master"):
        return "master"
    return "HEAD"


@dataclass(frozen=True)
class _WorktreePlan:
    repo_root: Path
    source_workspace: Path
    worktree_root: Path
    workspace_dir: Path
    branch: str
    options: ConversationWorktreeOptions
    start_point: str

    @property
    def guidance(self) -> str:
        return _build_worktree_guidance(
            source_workspace=self.source_workspace,
            worktree_root=self.worktree_root,
            workspace_dir=self.workspace_dir,
            branch=self.branch,
            options=self.options,
        )


def _plan_conversation_worktree(
    workspace: LocalWorkspace,
    conversation_id: UUID,
    conversation_worktree_root: Path,
    options: ConversationWorktreeOptions | None,
) -> _WorktreePlan | None:
    options = options or ConversationWorktreeOptions()
    source_workspace = Path(workspace.working_dir).resolve()
    try:
        validate_git_repository(source_workspace)
        repo_root = Path(
            run_git_command(
                ["git", "--no-pager", "rev-parse", "--show-toplevel"],
                source_workspace,
            )
        ).resolve()
    except (GitCommandError, GitRepositoryError):
        return None

    start_ref = _worktree_start_point(repo_root, options)
    try:
        run_git_command(
            ["git", "rev-parse", "--verify", "--quiet", f"{start_ref}^{{commit}}"],
            repo_root,
            expected_failure=True,
        )
    except GitCommandError as exc:
        if exc.exit_code == 1 and options.base != "ref":
            return None
        raise

    worktree_root = conversation_worktree_root / str(conversation_id) / repo_root.name
    return _WorktreePlan(
        repo_root=repo_root,
        source_workspace=source_workspace,
        worktree_root=worktree_root,
        workspace_dir=worktree_root / source_workspace.relative_to(repo_root),
        branch=f"{options.branch_prefix}{conversation_id}",
        options=options,
        # 保留引用，以便 Git 保留远程分支跟踪配置。
        start_point=start_ref,
    )


def _worktree_start_point(repo_root: Path, options: ConversationWorktreeOptions) -> str:
    if options.base == "head":
        return "HEAD"
    if options.base == "ref" and options.ref:
        if _has_git_remote(repo_root):
            _fetch_origin(repo_root)
        return options.ref
    return _get_worktree_start_point(repo_root)


def _create_conversation_worktree(plan: _WorktreePlan) -> LocalWorkspace:
    repo_root = plan.repo_root
    plan.worktree_root.parent.mkdir(parents=True, exist_ok=True)

    if plan.worktree_root.exists():
        try:
            run_git_command(
                ["git", "worktree", "remove", "--force", str(plan.worktree_root)],
                repo_root,
            )
        except GitCommandError:
            safe_rmtree(plan.worktree_root)

    run_git_command(["git", "worktree", "prune"], repo_root)

    if run_git_command(["git", "branch", "--list", plan.branch], repo_root):
        run_git_command(["git", "branch", "-D", plan.branch], repo_root)

    run_git_command(
        [
            "git",
            "worktree",
            "add",
            "-b",
            plan.branch,
            str(plan.worktree_root),
            plan.start_point,
        ],
        repo_root,
    )

    plan.workspace_dir.mkdir(parents=True, exist_ok=True)
    return LocalWorkspace(working_dir=plan.workspace_dir)


logger = logging.getLogger(__name__)


class InvalidParentConversation(ValueError):
    """``parent_conversation_id`` 未知、自指或处于
    不同的工作区。"""


class UnavailableAgentTool(ValueError):
    """智能体命名一个工具，其 ``tool_module_qualnames`` 模块为服务器
    无法导入，因此永远无法构建智能体。"""


def _same_workspace(a: LocalWorkspace, b: LocalWorkspace) -> bool:
    return Path(a.working_dir).resolve() == Path(b.working_dir).resolve()


def _compose_conversation_info(
    stored: StoredConversation,
    state: ConversationState,
    sub_conversation_ids: list[UUID] | None = None,
) -> ConversationInfo:
    # 在嵌套结构中使用 mode='JSON' 因此 SecretStr (e.g. LookupSecret.headers,
    # agent.agent_context.secrets) 序列化到字符串。 如果没有它，验证就会失败，因为
    # ConversationInfo 需要 dict[str、str]，但收到 SecretStr。
    #
    # ACP 模型状态被提升到顶层 ConversationInfo 字段，因为智能体控制住它 PrivateAttrs (
    # ACPAgent 已冻结的，无法生存的
    # ``model_dump``. ``getattr`` 保持非 ACP 智能体为空操作。 我们阅读了现场直播智能体（
    # 在会话中新鲜）并通过 ``ACPAgent._init`` 回退到 ``state.agent_state`` — 已持久化到
    # ``base_state.json``（并通过同步保存）
    # ``switch_acp_model``) - 所以冷列表读取，其中 PrivateAttrs 仍然为空，因为
    # ``init_state`` 尚未触发，仍然显示最后已知的状态。 已持久化
    # ``acp_available_models`` 是一个字典列表
    # ``ConversationInfo`` 强制返回 ``ACPModelInfo``。
    agent_state = getattr(state, "agent_state", {}) or {}
    agent = state.agent
    # current_model_id：实时PrivateAttr（运行时切换后新鲜）→
    # 已持久化提示→权威``acp_model``智能体在简历上运行。
    #
    # 的 ``acp_model``  回退方案仅限于智能体不是一个活的、初始化的。 Once ``init_state``
    #  已经发起了 ``current_model_id`` 权威解析值 — 包括 ``None`` 当无法应用重写（未知提
    # 供者，或者服务器拒绝了模型选择调用的续订）时，就 fallback到 ``acp_model`` 会重新启
    # 用一个覆盖正在运行的实时会话。 的回退方案仅用于
    # *Cold* 读取（``init_state`` 尚未触发，PrivateAttrs 仍为空），其中
    # 已序列化 ``acp_model`` 是最后已知的最佳提示。 已持久化
    # ``acp_current_model_id`` 提示由 ``ACPAgent.init_state`` 保持诚实（只要未应用覆盖，
    # 它就会清除该值），因此在这两种情况下都是安全的。
    #
    agent_initialized = bool(getattr(agent, "_initialized", False))
    current_model_id = (
        getattr(agent, "current_model_id", None)
        or agent_state.get("acp_current_model_id")
        or (None if agent_initialized else getattr(agent, "acp_model", None))
    )
    # available_models：对于 *both* a，该属性返回 ``[]``（从不 ``None``）
    # 冷读智能体 (PrivateAttr 默认，init_state 没有触发) 和一个活生生的智能体模型都没有
    # 的 ``is None`` 检查无法区分它们——而且在每次冷读已持久化选择器载荷上都会被丢弃。
    # ``or``链是有意为之：一个空的活跃列表会回退到已持久化快照，这正好适用于冷读（表面显
    # 示最后已知列表）以及对活跃空会话来说是安全的（已持久化值本身为空/缺席）。
    #
    available_models = (
        getattr(agent, "available_models", None)
        or agent_state.get("acp_available_models")
        or []
    )
    # 静态提供者能力。 与上述两个字段不同，它没有有意义的“活的” vs. 已持久化的区别——它是
    # 从稳定的身份提供商中推导出来的，并在会话初始化时只写一次——因此我们直接读取已持久化
    # 的值。 对于非 ACP 智能体和尚未开始会话的对话，默认为 False。
    #
    supports_runtime_model_switch = bool(
        agent_state.get("acp_supports_runtime_model_switch", False)
    )
    return ConversationInfo(
        **state.model_dump(mode="json"),
        title=stored.title,
        metrics=stored.metrics,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
        forked_from_conversation_id=stored.forked_from_conversation_id,
        forked_from_event_id=stored.forked_from_event_id,
        parent_conversation_id=stored.parent_conversation_id,
        sub_conversation_ids=sub_conversation_ids or [],
        current_model_id=current_model_id,
        available_models=available_models,
        supports_runtime_model_switch=supports_runtime_model_switch,
        client_tools=stored.client_tools,
        tool_module_qualnames=dict(stored.tool_module_qualnames),
        launched_agent_profile=stored.launched_agent_profile,
    )


def _compose_conversation_info_sync(
    stored: StoredConversation,
    state: ConversationState,
    sub_conversation_ids: list[UUID] | None = None,
) -> ConversationInfo:
    with state:
        return _compose_conversation_info(stored, state, sub_conversation_ids)


def _compose_webhook_conversation_info(
    stored: StoredConversation, state: ConversationState
) -> ConversationInfo:
    return _compose_conversation_info(stored, state)


def _update_state_tags_sync(
    state: ConversationState, tags: dict[str, str]
) -> ConversationState:
    with state:
        state.tags = tags
    return state


def _compose_webhook_conversation_info_sync(
    stored: StoredConversation, state: ConversationState
) -> ConversationInfo:
    return _compose_conversation_info_sync(stored, state)


def _register_agent_definitions(
    agent_defs: list["AgentDefinition"],
    *,
    context: str,
) -> None:
    """将智能体定义注册到子智能体注册表中。

    在创建新对话（从客户端转发的定义）和恢复已持久化对话（存储在 meta.json 中的定义）
    时使用。
    """
    from openhands.sdk.subagent.registry import (
        agent_definition_to_factory,
        register_agent_if_absent,
    )

    registered = 0
    for agent_def in agent_defs:
        try:
            factory = agent_definition_to_factory(agent_def)
            register_agent_if_absent(
                name=agent_def.name,
                factory_func=factory,
                description=agent_def,
            )
            registered += 1
        except Exception as e:
            logger.warning(
                f"Failed to register agent definition "
                f"'{agent_def.name}' ({context}): {e}"
            )
    logger.debug(
        f"Registered {registered}/{len(agent_defs)} agent definition(s) ({context})"
    )


def _state_signature(base_state_path: str) -> tuple[int, int] | None:
    """``base_state.json`` 的变更检测 token。 ``None`` 如果无法阅读。

    ``str`` + ``os.stat`` 而不是 ``Path``：这在每个状态过滤查询的每个对话上运行，并且
     ``Path`` 的成本比系统调用更高。
    """
    with suppress(OSError):
        stat = os.stat(base_state_path)
        return (stat.st_mtime_ns, stat.st_size)
    return None


def _stored_metadata_signature(stored: StoredConversation) -> int:
    """缓存行上 ``stored`` 元数据的更改检测指纹。

    ``cached_info`` 由 ``base_state.json`` 键控，但也嵌入
    ``StoredConversation`` 可以通过以下方式独立更改的元数据
    ``meta.json``（尤其是自动标题）。 准确地对字段进行指纹识别
    ``_compose_conversation_info`` 从 ``stored`` 提升，因此仅元数据更新会使缓存失效。
     使用该功能将集合保留在同步中。
    """
    metadata = stored.model_dump(
        mode="json",
        include={
            "title",
            "metrics",
            "created_at",
            "updated_at",
            "forked_from_conversation_id",
            "forked_from_event_id",
            "parent_conversation_id",
            "client_tools",
            "launched_agent_profile",
        },
    )
    return hash(json.dumps(metadata, sort_keys=True, default=str))


def _read_execution_status_sync(
    base_state_path: str,
) -> ConversationExecutionStatus | None:
    """只读 ``execution_status`` 从已持久化基本状态。

    验证完整的 ``ConversationState`` 需要智能体、LLM 配置、工作区、机密注册表和统计
    blob 才能到达一个枚举字段。
    """
    with suppress(OSError, ValueError):
        with open(base_state_path, "rb") as f:
            payload = json.loads(f.read())
        return ConversationExecutionStatus(
            payload.get("execution_status", ConversationExecutionStatus.IDLE.value)
        )
    return None


@dataclass
class _ConversationRecord:
    stored: StoredConversation
    execution_status: ConversationExecutionStatus
    # 上次读取 execution_status 时的签名。 None = 未验证，重新阅读。
    state_signature: tuple[int, int] | None = None
    # 由_base_state_path记忆。
    base_state_path: str | None = None
    # 完整的 ConversationInfo 由已持久化状态组成
    # ``state_signature``. 侧边栏轮询重复请求相同的行； 保留经过验证的对象，直到
    # base_state.json 发生更改，而不是在每个请求上重新解析大型嵌套 ConversationState。
    #
    cached_info: ConversationInfo | None = None
    # 截至最后一个作品的 ``stored`` 元数据（标题、指标等）的指纹。 ``cached_info`` 仅由
    # ``state_signature`` 键入，因此仅元数据更新 (``meta.json``, e.g. 自动标题）也必须使
    # 其无效。
    #
    stored_signature: int | None = None


@dataclass
class ConversationService:
    """管理已持久化对话及其实时运行时间。

    启动时仅加载轻量级元数据。 当对话需要实时运行时时，``EventService`` 及其事件历史
    记录会被水化。
    """

    conversations_dir: Path = field()
    webhook_specs: list[WebhookSpec] = field(default_factory=list)
    session_api_key: str | None = field(default=None)
    cipher: Cipher | None = None
    runtime_cipher_resolver: Callable[[UUID], Cipher] | None = None
    mcp_tool_provider: MCPToolProvider | None = None
    secrets_store: FileSecretsStore | None = None
    owner_instance_id: str = field(default_factory=lambda: uuid4().hex)
    max_concurrent_runs: int = 10
    lease_ttl_seconds: float = DEFAULT_LEASE_TTL_SECONDS
    conversation_idle_ttl_seconds: float | None = None
    conversation_worktree_root: Path = field(
        default=Path("/tmp/conversation-worktrees")
    )
    acp_skill_sourcing: ACPSkillSourcing = "native"
    enable_browser: bool = True
    _event_services: dict[UUID, EventService] | None = field(default=None, init=False)
    _conversation_records: dict[UUID, _ConversationRecord] = field(
        default_factory=dict, init=False
    )
    _lifecycle_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _lifecycle_condition: asyncio.Condition = field(
        default_factory=asyncio.Condition, init=False
    )
    _active_lifecycle_operations: int = field(default=0, init=False)
    _exclusive_lifecycle_pending: bool = field(default=False, init=False)
    _conversation_locks: WeakValueDictionary[UUID, asyncio.Lock] = field(
        default_factory=WeakValueDictionary, init=False
    )
    _conversation_webhook_subscribers: list["ConversationWebhookSubscriber"] = field(
        default_factory=list, init=False
    )
    _lease_renewal_task: asyncio.Task | None = field(default=None, init=False)
    _eviction_task: asyncio.Task | None = field(default=None, init=False)
    _run_executor: ThreadPoolExecutor | None = field(default=None, init=False)
    _run_semaphore: asyncio.Semaphore | None = field(default=None, init=False)
    _credential_bindings: dict[UUID, dict[str, VersionedCredentialBinding]] = field(
        default_factory=dict, init=False
    )

    def _load_catalog_sync(
        self, conversation_id: UUID | None = None
    ) -> dict[UUID, _ConversationRecord]:
        records: dict[UUID, _ConversationRecord] = {}
        directories = (
            [self.conversations_dir / conversation_id.hex]
            if conversation_id is not None
            else self.conversations_dir.iterdir()
        )
        for conversation_dir in directories:
            meta_file = conversation_dir / "meta.json"
            if not meta_file.exists():
                continue
            try:
                stored = StoredConversation.model_validate_json(
                    meta_file.read_text(),
                    context={"cipher": self._cipher_for(UUID(conversation_dir.name))},
                )
                execution_status = ConversationExecutionStatus.IDLE
                base_state_file = conversation_dir / BASE_STATE
                base_state_path = str(base_state_file)
                # 在读取之前签名，因此竞速写入会留下陈旧的签名，并且下一个查询会重新读取
                # 而不是信任它。
                #
                signature = _state_signature(base_state_path)
                if base_state_file.exists():
                    # 有意严格：损坏的基本状态仍然会从下面的目录和日志中删除对话。
                    #
                    payload = json.loads(base_state_file.read_text())
                    execution_status = ConversationExecutionStatus(
                        payload.get(
                            "execution_status", ConversationExecutionStatus.IDLE.value
                        )
                    )
                else:
                    signature = None
                records[stored.id] = _ConversationRecord(
                    stored=stored,
                    execution_status=execution_status,
                    state_signature=signature,
                    base_state_path=base_state_path,
                )
            except Exception:
                logger.exception(
                    "error_loading_conversation_catalog:%s",
                    conversation_dir,
                    stack_info=True,
                )
        return records

    def _base_state_path(
        self, conversation_id: UUID, record: _ConversationRecord
    ) -> str:
        """记忆的对话路径 ``base_state.json``。"""
        path = record.base_state_path
        if path is None:
            path = str(self.conversations_dir / conversation_id.hex / BASE_STATE)
            record.base_state_path = path
        return path

    def _cipher_for(self, conversation_id: UUID) -> Cipher | None:
        if self.runtime_cipher_resolver is not None:
            return self.runtime_cipher_resolver(conversation_id)
        return self.cipher

    def _load_persisted_state_sync(
        self, conversation_id: UUID
    ) -> ConversationState | None:
        base_state_file = self.conversations_dir / conversation_id.hex / BASE_STATE
        if not base_state_file.exists():
            return None
        cipher = self._cipher_for(conversation_id)
        context = {"cipher": cipher} if cipher else None
        return ConversationState.model_validate_json(
            base_state_file.read_text(), context=context
        )

    def _agent_from_base_state(self, conversation_id: UUID) -> AgentBase | None:
        """从 ``base_state.json`` 返回已持久化智能体（其单一来源
        的真值），如果还没有已持久化状态，则为 ``None``。

        由冷路径检查使用（e.g. codex-智能体检测）用于在智能体被删除之前从
        ``meta.json`` 读取智能体。
        """
        state = self._load_persisted_state_sync(conversation_id)
        return state.agent if state is not None else None

    def _children_index(self) -> dict[UUID, list[UUID]]:
        """反向映射 parent_id -> 子 id； 每次调用都会重建，因为
        目录从多个地方发生变异，缓存可能会过时。"""
        index: dict[UUID, list[UUID]] = {}
        for child_id, record in self._conversation_records.items():
            parent_id = record.stored.parent_conversation_id
            if parent_id is not None:
                index.setdefault(parent_id, []).append(child_id)
        return index

    def _children_of(self, conversation_id: UUID) -> list[UUID]:
        return [
            child_id
            for child_id, record in self._conversation_records.items()
            if record.stored.parent_conversation_id == conversation_id
        ]

    async def activate_credential_binding(
        self,
        conversation_id: UUID,
        secret_name: str,
        binding: VersionedCredentialBinding,
    ) -> None:
        async with self._conversation_lifecycle(conversation_id):
            event_services = self._event_services
            event_service = (
                event_services.get(conversation_id)
                if event_services is not None
                else None
            )
            record = self._conversation_records.get(conversation_id)
            stored = (
                event_service.stored
                if event_service is not None
                else (record.stored if record is not None else None)
            )
            if stored is not None and not self._profile_allows_secret(
                stored, secret_name
            ):
                raise CredentialAuthorizationRejected(
                    "The launched agent profile excludes this credential"
                )
            if event_service is not None and event_service.is_open():
                await event_service.activate_credential_binding(secret_name, binding)
                record = self._conversation_records.get(conversation_id)
                if record is not None:
                    record.stored = event_service.stored
                    record.cached_info = None
                return
            self._credential_bindings.setdefault(conversation_id, {})[secret_name] = (
                binding
            )

    async def prepare_for_sandbox_pause(self) -> None:
        async with self._exclusive_lifecycle():
            event_services = self._event_services
            if event_services is None:
                raise ValueError("inactive_service")
            active_services = tuple(event_services.items())
            results = await asyncio.gather(
                *(
                    event_service.__aexit__(None, None, None)
                    for _, event_service in active_services
                ),
                return_exceptions=True,
            )
            first_error: BaseException | None = None
            for (conversation_id, event_service), result in zip(
                active_services, results, strict=True
            ):
                if isinstance(result, BaseException):
                    if first_error is None:
                        first_error = result
                    continue
                record = self._conversation_records.get(conversation_id)
                if record is not None:
                    record.stored = event_service.stored
                    record.cached_info = None
                event_services.pop(conversation_id, None)
            if first_error is not None:
                raise first_error
            self._credential_bindings = {}

    @staticmethod
    def _profile_allows_secret(stored: StoredConversation, name: str) -> bool:
        profile = stored.launched_agent_profile
        return profile is None or profile.allows_secret(name)

    @staticmethod
    def _is_codex_agent(agent: AgentBase | None) -> bool:
        return isinstance(agent, ACPAgent) and agent.acp_server == "codex"

    async def _has_local_codex_credential(self) -> bool:
        if self.secrets_store is None:
            return False
        value = await asyncio.to_thread(
            self.secrets_store.get_secret,
            CODEX_AUTH_SECRET_NAME,
        )
        return value is not None

    async def _resolve_credential_bindings(
        self,
        stored: StoredConversation,
        agent: AgentBase | None = None,
    ) -> dict[str, VersionedCredentialBinding]:
        # 智能体不再存在于 ``stored`` (meta.json) 上。 调用者显式传递智能体（新对话请求
        # 智能体或实时智能体）； 否则回到已持久化 base_state.json 智能体。 从事件循环中
        # 读取它 — 它会阻塞文件 I/O，镜像
        # ``_load_persisted_state_sync`` 其他地方的用法。
        if agent is None:
            agent = await asyncio.to_thread(self._agent_from_base_state, stored.id)
        bindings = {
            name: binding
            for name, binding in self._credential_bindings.pop(stored.id, {}).items()
            if self._profile_allows_secret(stored, name)
        }
        if not isinstance(agent, ACPAgent):
            # 仅 ACP 智能体使用文件凭据绑定； 活动路径拒绝将它们用于任何其他智能体 (
            # CredentialBindingActivationTooLate)。 删除挂起的绑定，以便常规对话不再需要
            # 绑定。
            #
            return {}
        if (
            self._profile_allows_secret(stored, CODEX_AUTH_SECRET_NAME)
            and CODEX_AUTH_SECRET_NAME not in bindings
            and self._is_codex_agent(agent)
            and await self._has_local_codex_credential()
        ):
            assert self.secrets_store is not None
            from openhands.agent_server.credential_binding import (
                LocalVersionedCredentialBinding,
            )

            bindings[CODEX_AUTH_SECRET_NAME] = LocalVersionedCredentialBinding(
                self.secrets_store,
                CODEX_AUTH_SECRET_NAME,
            )
        return bindings

    async def _conversation_info(
        self,
        conversation_id: UUID,
        record: _ConversationRecord,
        children_index: dict[UUID, list[UUID]] | None = None,
    ) -> ConversationInfo | None:
        event_services = self._event_services
        if event_services is None:
            raise ValueError("inactive_service")

        children = (
            children_index.get(conversation_id, [])
            if children_index is not None
            else self._children_of(conversation_id)
        )

        event_service = event_services.get(conversation_id)
        if event_service is not None and event_service.is_open():
            live = True
            # 不要为了列出侧边栏行而获取活的ConversationState的FIFOLock。 OpenHands
            # arun() 有意将锁持久化到整个 LLM/工具步骤中，该步骤可能持续数分钟。 通过多
            # 个并行运行，编写每个活动行会在每个活动步骤后面等待并序列化对话搜索。
            # base_state.json 是已保存的会话列表，具有与闲聊会话相同的签名-键缓存。 端点
            # 实时详情和事件对单个开放对话保持权威。
            #
            record.stored = event_service.stored
        else:
            live = False

        signature = _state_signature(self._base_state_path(conversation_id, record))
        if signature is None and event_service is not None and event_service.is_open():
            # 直接嵌入器/测试可以注入实时 EventService，而无需已持久化状态文件。 在这种
            # 情况下，没有要列出的磁盘快照，因此请保留活动状态回退方案。
            #
            state = await event_service.get_state()
            conversation_info = await asyncio.to_thread(
                _compose_conversation_info_sync, event_service.stored, state, children
            )
            record.execution_status = conversation_info.execution_status
            return conversation_info

        # ``record.stored`` 在上方刷新以进行实时对话； 空闲行保留目录副本。 只有实时对话
        # 才能通过仅元数据更新来改变内存中的对象（e.g. 自动标题，其中写道
        # ``meta.json`` 不需要接触 ``base_state.json``，因此只在实际刷新时指纹它——这样可
        # 以保持热已持久化-行侧边栏路径的空闲，避免每次请求时的dump+hash。
        #
        stored_signature = _stored_metadata_signature(record.stored) if live else None
        cached = record.cached_info
        if (
            cached is not None
            and signature == record.state_signature
            and (not live or stored_signature == record.stored_signature)
        ):
            # 父/子关系是源自目录的，并且可以在不触及此对话的 base_state.json 的情况下进
            # 行更改。
            #
            if cached.sub_conversation_ids != children:
                cached = cached.model_copy(update={"sub_conversation_ids": children})
                record.cached_info = cached
            return cached

        state = await asyncio.to_thread(
            self._load_persisted_state_sync, conversation_id
        )
        if state is None:
            return None
        conversation_info = await asyncio.to_thread(
            _compose_conversation_info, record.stored, state, children
        )
        record.state_signature = signature
        record.stored_signature = stored_signature
        record.cached_info = conversation_info
        record.execution_status = conversation_info.execution_status
        return conversation_info

    @staticmethod
    def _refresh_persisted_statuses_sync(
        targets: list[tuple[UUID, str, tuple[int, int] | None]],
    ) -> dict[UUID, tuple[ConversationExecutionStatus | None, tuple[int, int] | None]]:
        """重新阅读 ``execution_status`` 中已更改的已持久化个对话。

        ``targets``为``(conversation_id, base_state_path, cached_signature)``； 签名
        仍然匹配的条
        目将被跳过而不读取。 采用简单值，因为它在工作线程中运行线程。 结果，一个
        ``None`` 状态表示“保留缓存的”，``None`` 签名标记该条目未经验证。
        """
        refreshed: dict[
            UUID, tuple[ConversationExecutionStatus | None, tuple[int, int] | None]
        ] = {}
        for conversation_id, base_state_path, cached_signature in targets:
            signature = _state_signature(base_state_path)
            if signature is not None and signature == cached_signature:
                continue
            if signature is None:
                # 不可读（从未启动或中间删除）：保留缓存
                # 状态，未验证，所以稍后查询重试。
                refreshed[conversation_id] = (None, None)
                continue
            status = _read_execution_status_sync(base_state_path)
            refreshed[conversation_id] = (
                (None, None) if status is None else (status, signature)
            )
        return refreshed

    async def _refresh_execution_statuses(self) -> None:
        """使每个缓存的 ``execution_status`` 保持最新。

        过滤状态搜索和计数后的索引。 现场对话凭记忆回答； 已持久化个每个花费
        ``stat()``，并且在更改时重新只读，而不是完整的
        ``ConversationState``。
        """
        event_services = self._event_services
        if event_services is None:
            raise ValueError("inactive_service")

        targets: list[tuple[UUID, str, tuple[int, int] | None]] = []
        for conversation_id, record in list(self._conversation_records.items()):
            event_service = event_services.get(conversation_id)
            if event_service is not None and event_service.is_open():
                # 权威：我们拥有它，所以磁盘只能更陈旧。
                state = await event_service.get_state()
                record.execution_status = state.execution_status
                # 自动保存将使我们持有的任何签名和缓存信息失效。
                record.state_signature = None
                record.cached_info = None
                continue
            targets.append(
                (
                    conversation_id,
                    self._base_state_path(conversation_id, record),
                    record.state_signature,
                )
            )

        if not targets:
            return

        # 目录的一线程跳，而不是每个对话一跳。
        refreshed = await asyncio.to_thread(
            self._refresh_persisted_statuses_sync, targets
        )
        for conversation_id, (status, signature) in refreshed.items():
            record = self._conversation_records.get(conversation_id)
            if record is None:
                continue
            event_service = event_services.get(conversation_id)
            if event_service is not None and event_service.is_open():
                # 当我们读盘时上线； 记忆获胜。
                continue
            if status is not None:
                record.execution_status = status
            # 已持久化更改（或移动到不可读状态）会使从先前快照派生的任何缓存
            # ConversationInfo 无效。
            #
            record.cached_info = None
            record.state_signature = signature

    async def refresh_persisted_conversation(self, conversation_id: UUID) -> None:
        """刷新由外部运行时更改的一项目录记录。"""
        event_services = self._event_services
        if event_services is None:
            raise ValueError("inactive_service")
        disk_records = await asyncio.to_thread(self._load_catalog_sync, conversation_id)
        if conversation_id not in disk_records:
            event_service = event_services.get(conversation_id)
            if event_service is None or not event_service.is_open():
                self._conversation_records.pop(conversation_id, None)
            return
        record = disk_records[conversation_id]
        event_service = event_services.get(conversation_id)
        if event_service is not None and event_service.is_open():
            return
        existing = self._conversation_records.setdefault(conversation_id, record)
        if existing.stored != record.stored:
            existing.stored = record.stored
            existing.cached_info = None

    async def _reconcile_active_records(self) -> None:
        """将注入的实时服务添加到内存目录中。"""
        event_services = self._event_services
        if event_services is None:
            raise ValueError("inactive_service")
        for conversation_id, event_service in event_services.items():
            if conversation_id in self._conversation_records:
                continue
            state = await event_service.get_state()
            self._conversation_records[conversation_id] = _ConversationRecord(
                stored=event_service.stored,
                execution_status=state.execution_status,
            )

    def _prepare_persisted_runtime(self, stored: StoredConversation) -> None:
        if stored.tool_module_qualnames:
            for tool_name, module_qualname in stored.tool_module_qualnames.items():
                try:
                    importlib.import_module(module_qualname)
                    logger.debug(
                        "Tool '%s' registered via module '%s' when resuming %s",
                        tool_name,
                        module_qualname,
                        stored.id,
                    )
                except ImportError as exc:
                    logger.warning(
                        "Failed to import module '%s' for tool '%s' when resuming "
                        "%s: %s. Tool will not be available.",
                        module_qualname,
                        tool_name,
                        stored.id,
                        exc,
                    )
        if stored.client_tools:
            register_client_tools(stored.client_tools)
        if stored.agent_definitions:
            _register_agent_definitions(
                stored.agent_definitions,
                context=f"resuming conversation {stored.id}",
            )

    def _get_conversation_lock(self, conversation_id: UUID) -> asyncio.Lock:
        lock = self._conversation_locks.get(conversation_id)
        if lock is None:
            lock = asyncio.Lock()
            self._conversation_locks[conversation_id] = lock
        return lock

    @asynccontextmanager
    async def _conversation_lifecycle(self, conversation_id: UUID):
        async with self._lifecycle_condition:
            await self._lifecycle_condition.wait_for(
                lambda: not self._exclusive_lifecycle_pending
            )
            self._active_lifecycle_operations += 1
        try:
            async with self._get_conversation_lock(conversation_id):
                yield
        finally:
            async with self._lifecycle_condition:
                self._active_lifecycle_operations -= 1
                if self._active_lifecycle_operations == 0:
                    self._lifecycle_condition.notify_all()

    @asynccontextmanager
    async def _exclusive_lifecycle(self):
        async with self._lifecycle_lock:
            try:
                async with self._lifecycle_condition:
                    self._exclusive_lifecycle_pending = True
                    await self._lifecycle_condition.wait_for(
                        lambda: self._active_lifecycle_operations == 0
                    )
                yield
            finally:
                async with self._lifecycle_condition:
                    self._exclusive_lifecycle_pending = False
                    self._lifecycle_condition.notify_all()

    async def _get_or_load_event_service(
        self, conversation_id: UUID
    ) -> EventService | None:
        event_services = self._event_services
        if event_services is None:
            raise ValueError("inactive_service")
        if (
            conversation_id not in event_services
            and conversation_id not in self._conversation_records
        ):
            return None
        async with self._conversation_lifecycle(conversation_id):
            return await self._get_or_load_event_service_locked(conversation_id)

    async def _get_or_load_event_service_locked(
        self,
        conversation_id: UUID,
        *,
        require_runtime_bindings: bool = True,
        agent: AgentBase | None = None,
    ) -> EventService | None:
        event_services = self._event_services
        if event_services is None:
            raise ValueError("inactive_service")

        event_service = event_services.get(conversation_id)
        if event_service is not None and event_service.is_open():
            # 访问算作活动，推迟闲置驱逐。
            event_service.touch()
            return event_service

        record = self._conversation_records.get(conversation_id)
        if record is None:
            return None

        pending_bindings = self._credential_bindings.get(conversation_id, {})
        missing_bindings = (
            record.stored.required_runtime_credential_bindings - pending_bindings.keys()
        )
        if require_runtime_bindings and missing_bindings:
            raise CredentialBindingActivationRequired(
                "credential_binding_activation_required"
            )

        await asyncio.to_thread(self._prepare_persisted_runtime, record.stored)
        try:
            return await self._start_event_service(record.stored, persisted_agent=agent)
        except ConversationLeaseHeldError as exc:
            logger.debug(
                "Skipping active conversation %s owned by %s until %s",
                conversation_id,
                exc.owner_instance_id,
                exc.expires_at,
            )
            return None

    async def get_conversation(self, conversation_id: UUID) -> ConversationInfo | None:
        if self._event_services is None:
            raise ValueError("inactive_service")
        record = self._conversation_records.get(conversation_id)
        if record is None:
            event_service = self._event_services.get(conversation_id)
            if event_service is None:
                return None
            state = await event_service.get_state()
            record = _ConversationRecord(
                stored=event_service.stored,
                execution_status=state.execution_status,
            )
            self._conversation_records[conversation_id] = record
            return _compose_conversation_info(
                event_service.stored, state, self._children_of(conversation_id)
            )
        return await self._conversation_info(conversation_id, record)

    async def get_acp_conversation(
        self, conversation_id: UUID
    ) -> ConversationInfo | None:
        return await self.get_conversation(conversation_id)

    async def search_conversations(
        self,
        page_id: str | None = None,
        limit: int = 100,
        execution_status: ConversationExecutionStatus | None = None,
        sort_order: ConversationSortOrder = ConversationSortOrder.CREATED_AT_DESC,
    ) -> ConversationPage:
        items, next_page_id = await self._search_conversations(
            page_id=page_id,
            limit=limit,
            execution_status=execution_status,
            sort_order=sort_order,
        )
        return ConversationPage(
            items=items,
            next_page_id=next_page_id,
        )

    async def search_acp_conversations(
        self,
        page_id: str | None = None,
        limit: int = 100,
        execution_status: ConversationExecutionStatus | None = None,
        sort_order: ConversationSortOrder = ConversationSortOrder.CREATED_AT_DESC,
    ) -> ConversationPage:
        items, next_page_id = await self._search_conversations(
            page_id=page_id,
            limit=limit,
            execution_status=execution_status,
            sort_order=sort_order,
        )
        return ConversationPage(
            items=items,
            next_page_id=next_page_id,
        )

    async def _search_conversations(
        self,
        page_id: str | None,
        limit: int,
        execution_status: ConversationExecutionStatus | None,
        sort_order: ConversationSortOrder,
    ) -> tuple[list[ConversationInfo], str | None]:
        if self._event_services is None:
            raise ValueError("inactive_service")
        await self._reconcile_active_records()

        if execution_status is not None:
            # 在快照之前刷新：这等待着，一个正在运行的对话会替换其目录记录，因此首先进行
            # 快照会过滤掉被取代的那个。 仍仅为页面项目加载完整状态。
            #
            await self._refresh_execution_statuses()

        records = [
            (conversation_id, record)
            for conversation_id, record in self._conversation_records.items()
            if execution_status is None or record.execution_status == execution_status
        ]
        if sort_order in (
            ConversationSortOrder.CREATED_AT,
            ConversationSortOrder.CREATED_AT_DESC,
        ):
            records.sort(
                key=lambda item: item[1].stored.created_at,
                reverse=sort_order == ConversationSortOrder.CREATED_AT_DESC,
            )
        else:
            records.sort(
                key=lambda item: item[1].stored.updated_at,
                reverse=sort_order == ConversationSortOrder.UPDATED_AT_DESC,
            )

        start_index = 0
        if page_id:
            for i, (conversation_id, _) in enumerate(records):
                if conversation_id.hex == page_id:
                    start_index = i
                    break

        items: list[ConversationInfo] = []
        next_page_id = None
        children_index = self._children_index()
        for conversation_id, record in records[start_index:]:
            if len(items) >= limit:
                next_page_id = conversation_id.hex
                break
            conversation_info = await self._conversation_info(
                conversation_id, record, children_index
            )
            if conversation_info is not None:
                items.append(conversation_info)

        return items, next_page_id

    async def count_conversations(
        self,
        execution_status: ConversationExecutionStatus | None = None,
    ) -> int:
        return await self._count_conversations(execution_status=execution_status)

    async def _count_conversations(
        self,
        execution_status: ConversationExecutionStatus | None,
    ) -> int:
        """计算与给定过滤器匹配的对话数量。"""
        if self._event_services is None:
            raise ValueError("inactive_service")
        await self._reconcile_active_records()

        if execution_status is None:
            return len(self._conversation_records)

        await self._refresh_execution_statuses()
        return sum(
            1
            for record in self._conversation_records.values()
            if record.execution_status == execution_status
        )

    async def batch_get_conversations(
        self, conversation_ids: list[UUID]
    ) -> list[ConversationInfo | None]:
        """给定一个id列表，获取一批对话信息，返回
        None 对于任何未找到的。"""
        results = await asyncio.gather(
            *[
                self.get_conversation(conversation_id)
                for conversation_id in conversation_ids
            ]
        )
        return results

    async def batch_get_acp_conversations(
        self, conversation_ids: list[UUID]
    ) -> list[ConversationInfo | None]:
        results = await asyncio.gather(
            *[
                self.get_conversation(conversation_id)
                for conversation_id in conversation_ids
            ]
        )
        return results

    async def _notify_conversation_webhooks(self, conversation_info: BaseModel):
        """通知所有对话 Webhook 订阅者对话更改。"""
        if not self._conversation_webhook_subscribers:
            return

        # 在后台向所有对话 Webhook 订阅者发送通知
        async def _notify_and_log_errors():
            results = await asyncio.gather(
                *[
                    subscriber.post_conversation_info(conversation_info)
                    for subscriber in self._conversation_webhook_subscribers
                ],
                return_exceptions=True,  # 如果其中一个 Webhook 失败，也不会失败
            )

            # 记录发生的任何异常
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    subscriber = self._conversation_webhook_subscribers[i]
                    logger.error(
                        (
                            f"Failed to notify conversation webhook "
                            f"{subscriber.spec.base_url}: {result}"
                        ),
                        exc_info=result,
                    )

        # 创建任务在后台运行，无需等待
        asyncio.create_task(_notify_and_log_errors())

    # 编写方法

    def _has_conversation(self, conversation_id: UUID) -> bool:
        """服务是否已知此 ID。

        用于选择重用或创建路径的廉价、非等待提示。 创建路径会在生命周期锁下重新检查，
        因为同一 id 的并发创建可以在其间提交。
        """
        event_services = self._event_services
        if event_services is None:
            return False
        existing_record = self._conversation_records.get(conversation_id)
        existing_event_service = event_services.get(conversation_id)
        return existing_record is not None or (
            existing_event_service is not None and existing_event_service.is_open()
        )

    async def _reuse_existing_conversation_locked(
        self,
        conversation_id: UUID,
        request: StartConversationRequest,
    ) -> tuple[ConversationInfo, bool]:
        """重用现有对话而不重新创建它。

        调用者必须保留此会话的生命周期锁，因此目录在存在检查和重用之间不能更改。
        """
        if self._event_services is None:
            raise ValueError("inactive_service")
        existing_record = self._conversation_records.get(conversation_id)
        existing_event_service = self._event_services.get(conversation_id)
        stored = (
            existing_event_service.stored
            if existing_event_service is not None
            else existing_record.stored
            if existing_record is not None
            else None
        )
        if stored is not None:
            request = request.model_copy(
                update={
                    "secrets": {
                        name: value
                        for name, value in request.secrets.items()
                        if self._profile_allows_secret(stored, name)
                    }
                }
            )
        if existing_event_service is not None and existing_event_service.is_open():
            # ``is_open()`` 上面保证了实时对话，因此公共获取器在这里不会触发。
            #
            existing_agent = existing_event_service.get_conversation().agent
            if (
                self._is_codex_agent(existing_agent)
                and CODEX_AUTH_SECRET_NAME
                not in existing_event_service.credential_bindings
            ):
                # 重用我们上面已经解决的实时智能体，而不是让
                # _resolve_credential_bindings 回退到同步 base_state.json 读取。
                #
                late_bindings = await self._resolve_credential_bindings(
                    existing_event_service.stored, agent=existing_agent
                )
                try:
                    for secret_name, binding in late_bindings.items():
                        await existing_event_service.activate_credential_binding(
                            secret_name,
                            binding,
                        )
                except Exception:
                    pending = self._credential_bindings.setdefault(conversation_id, {})
                    for secret_name, binding in late_bindings.items():
                        pending.setdefault(secret_name, binding)
                    raise
            if (
                CODEX_AUTH_SECRET_NAME in request.secrets
                and CODEX_AUTH_SECRET_NAME
                not in existing_event_service.credential_bindings
            ):
                await existing_event_service.apply_resume_secrets(
                    {CODEX_AUTH_SECRET_NAME: request.secrets[CODEX_AUTH_SECRET_NAME]}
                )
            state = await existing_event_service.get_state()
            self._conversation_records[conversation_id] = _ConversationRecord(
                stored=existing_event_service.stored,
                execution_status=state.execution_status,
            )
            return (
                _compose_conversation_info(
                    existing_event_service.stored,
                    state,
                    self._children_of(conversation_id),
                ),
                False,
            )
        if existing_record is None:
            raise ValueError(f"Persisted conversation {conversation_id} has no record")
        # 从事件循环中读取 base_state.json，与在其他地方（_resolve_credential_bindings、
        # _conversation_info）进行相同读取时使用的 asyncio.to_thread 模式相匹配。
        #
        reattach_agent = await asyncio.to_thread(
            self._agent_from_base_state, conversation_id
        )
        managed_codex_credential = self._is_codex_agent(reattach_agent) and (
            CODEX_AUTH_SECRET_NAME in self._credential_bindings.get(conversation_id, {})
            or await self._has_local_codex_credential()
        )
        fallback_secret = request.secrets.get(CODEX_AUTH_SECRET_NAME)
        if managed_codex_credential or fallback_secret is not None:
            original_stored = existing_record.stored
            injected_fallback = (
                not managed_codex_credential and fallback_secret is not None
            )
            if injected_fallback:
                existing_record.stored = original_stored.model_copy(
                    update={
                        "secrets": {
                            **original_stored.secrets,
                            CODEX_AUTH_SECRET_NAME: fallback_secret,
                        }
                    }
                )
            try:
                # 重用我们已经从上面的 base_state.json 解析的智能体，这样加载路径就不会
                # 再次读取和解析它。
                #
                event_service = await self._get_or_load_event_service_locked(
                    conversation_id, agent=reattach_agent
                )
            finally:
                if injected_fallback:
                    existing_record.stored = original_stored
            if event_service is not None:
                state = await event_service.get_state()
                return (
                    _compose_conversation_info(
                        event_service.stored,
                        state,
                        self._children_of(conversation_id),
                    ),
                    False,
                )
        conversation_info = await self._conversation_info(
            conversation_id, existing_record
        )
        if conversation_info is None:
            raise ValueError(
                f"Persisted conversation {conversation_id} has no base state"
            )
        return conversation_info, False

    async def start_conversation(
        self, request: StartConversationRequest
    ) -> tuple[ConversationInfo, bool]:
        return await self._start_conversation(request)

    async def start_acp_conversation(
        self, request: StartConversationRequest
    ) -> tuple[ConversationInfo, bool]:
        return await self._start_conversation(request)

    async def _start_conversation(
        self,
        request: StartConversationRequest,
    ) -> tuple[ConversationInfo, bool]:
        """启动本地 event_service 并返回其 id。"""
        if self._event_services is None:
            raise ValueError("inactive_service")
        conversation_id = request.conversation_id or uuid4()
        if self._has_conversation(conversation_id):
            async with self._conversation_lifecycle(conversation_id):
                return await self._reuse_existing_conversation_locked(
                    conversation_id, request
                )

        with await RunSlot.acquire(self._run_semaphore) as run_slot:
            return await self._create_conversation(request, conversation_id, run_slot)

    async def _create_conversation(
        self,
        request: StartConversationRequest,
        conversation_id: UUID,
        run_slot: RunSlot,
    ) -> tuple[ConversationInfo, bool]:
        # 该链接在创建后是不可变的，因此超出自父级的循环是不可能的； 允许重新养育需要真
        # 正的祖先行走。
        #
        if request.parent_conversation_id is not None:
            if request.parent_conversation_id == conversation_id:
                raise InvalidParentConversation(
                    "A conversation cannot be its own parent"
                )
            parent_record = self._conversation_records.get(
                request.parent_conversation_id
            )
            if parent_record is None:
                raise InvalidParentConversation(
                    f"Parent conversation {request.parent_conversation_id} not found"
                )
            if not _same_workspace(parent_record.stored.workspace, request.workspace):
                raise InvalidParentConversation(
                    f"Parent conversation {request.parent_conversation_id} belongs "
                    f"to a different workspace"
                )

        runtime_profile = os.getenv("OH_RUNTIME_LAUNCHED_PROFILE")
        runtime_launched_profile = (
            LaunchedAgentProfile.model_validate_json(runtime_profile)
            if runtime_profile
            else None
        )

        from openhands.agent_server.persistence import (
            PersistedSettings,
            get_settings_store,
        )

        # get_settings_store() 在这里是安全的：get_instance() 在任何对话开始之前使用服务
        # 器密码初始化单例。 FileSettingsStore.load 旨在重置 PermissionError/OSError。
        # 既然每次启动都会读取它，那么错误的文件模式一定不会删除不需要设置的请求形状。
        #
        try:
            settings = await asyncio.to_thread(
                lambda: get_settings_store().load() or PersistedSettings()
            )
        except (PermissionError, OSError):
            logger.warning(
                "Cannot read settings; starting without the stored agent preferences",
                exc_info=True,
            )
            settings = PersistedSettings()
        # ``ACPAgentSettings.agent_context`` 可以为空，因此有守卫。
        stored_context = settings.agent_settings.agent_context
        load_memory = bool(stored_context and stored_context.load_memory)

        source = await asyncio.to_thread(
            launch_source,
            request,
            lambda: server_launch_stores(settings, self.cipher),
            self.cipher,
        )
        secrets = scoped_secrets(request.secrets, source)
        managed_codex_credential = is_codex_source(source) and (
            CODEX_AUTH_SECRET_NAME in self._credential_bindings.get(conversation_id, {})
            or await self._has_local_codex_credential()
        )
        if managed_codex_credential:
            secrets.pop(CODEX_AUTH_SECRET_NAME, None)

        # 从客户端动态注册工具注册表
        unimportable_tools: dict[str, str] = {}
        if request.tool_module_qualnames:
            for tool_name, module_qualname in request.tool_module_qualnames.items():
                try:
                    # 导入模块触发工具自动注册
                    importlib.import_module(module_qualname)
                    logger.debug(
                        f"Tool '{tool_name}' registered via module '{module_qualname}'"
                    )
                except ImportError as e:
                    logger.warning(
                        f"Failed to import module '{module_qualname}' for tool "
                        f"'{tool_name}': {e}. Tool will not be available."
                    )
                    # 客户端注册表列出它知道的所有工具，不仅包括智能体's：只有智能体使用
                    # 其工具时，模块才致命（在智能体启动后检查）。
                    #
                    unimportable_tools[tool_name] = f"{module_qualname}: {e}"
            logger.info(
                "Dynamically registered %d tools for conversation %s",
                len(request.tool_module_qualnames),
                conversation_id,
            )

        # 注册客户端定义的工具（JSON 规范，无 Python 代码）。 ClientTool*class*是无状态
        # 注册的； 每个工具的模式通过返回的 Tool.params 与对话一起传输，因此并发对话永远
        # 不会破坏彼此的模式。
        #
        client_tools = (
            register_client_tools(request.client_tools) if request.client_tools else []
        )

        worktree = (
            _plan_conversation_worktree(
                request.workspace,
                conversation_id,
                self.conversation_worktree_root,
                request.worktree_options,
            )
            if request.worktree
            else None
        )
        launched = await asyncio.to_thread(
            lambda: finalize(
                source,
                live_launch_runtime(
                    self.acp_skill_sourcing, enable_browser=self.enable_browser
                ),
                additions=request.agent_launch_additions,
                extra_suffixes=[worktree.guidance] if worktree else (),
                client_tools=client_tools,
                load_memory=load_memory,
                managed_secrets=(
                    [CODEX_AUTH_SECRET_NAME] if managed_codex_credential else ()
                ),
            )
        )
        # 构建智能体会在第一条消息上引发 KeyError，因此在调用者仍然可以对其进行操作时拒
        # 绝创建。
        #
        missing_tools = [
            f"'{tool.name}' ({unimportable_tools[tool.name]})"
            for tool in launched.agent.tools
            if tool.name in unimportable_tools
            and not is_tool_available(tool.name, check_usable=False)
        ]
        if missing_tools:
            raise UnavailableAgentTool(
                "The agent uses tools whose modules the agent server cannot "
                f"import: {', '.join(missing_tools)}"
            )
        workspace = (
            _create_conversation_worktree(worktree)
            if worktree is not None
            else request.workspace
        )

        # 服务器可能会解析创建客户端无法解析的内置工具
        # import, as happens when a lightweight orchestrator starts a runtime
        # 谈话。 持久化这些服务器解析的模块，以便另一个客户端可以附加和反序列化生成的工
        # 具事件。
        #
        registered_tool_modules = get_tool_module_qualnames()
        tool_module_qualnames = dict(request.tool_module_qualnames)
        client_tool_names = {tool.name for tool in client_tools}
        for tool in launched.agent.tools:
            module_qualname = registered_tool_modules.get(tool.name)
            if module_qualname is not None and tool.name not in client_tool_names:
                tool_module_qualnames.setdefault(tool.name, module_qualname)

        # 注册从客户端转发的子智能体定义
        if request.agent_definitions:
            _register_agent_definitions(
                request.agent_definitions,
                context=f"conversation {conversation_id}",
            )

        # 插件加载是通过懒加载 LocalConversation 处理的，它在第一次 run()/send_message()
        #  时加载插件，将引用固定到提交 SHAs，并将插件技能/MCP/钩子合并到智能体。
        #
        # 在嵌套结构中使用 mode='JSON' 因此 SecretStr (e.g. LookupSecret.headers) 序列化
        # 到纯字符串。 传递 expose_secrets=True，因此 StaticSecret 值在往返过程中得以保
        # 留； 该字典仅在构建过程中使用StoredConversation，而不是通过网络发送。
        #
        request_data = request.model_copy(
            update={
                "secrets": secrets,
                "workspace": workspace,
                "tool_module_qualnames": tool_module_qualnames,
            }
        ).model_dump(
            mode="json",
            context={"expose_secrets": True},
            exclude={
                "agent",
                "agent_settings",
                "agent_profile_id",
                "agent_launch_additions",
            },
        )
        launched_agent_profile = launched.profile or runtime_launched_profile
        if request.secrets_encrypted:
            stored = StoredConversation.model_validate(
                {
                    "id": conversation_id,
                    **request_data,
                    "launched_agent_profile": (
                        launched_agent_profile.model_dump(mode="json")
                        if launched_agent_profile is not None
                        else None
                    ),
                },
                context={"cipher": self.cipher},
            )
        else:
            stored = StoredConversation(
                id=conversation_id,
                launched_agent_profile=launched_agent_profile,
                **request_data,
            )
        initial_message = request.initial_message
        return await self._launch_prepared_conversation(
            stored,
            launched,
            run_slot=run_slot,
            initial_message=(
                Message(role=initial_message.role, content=initial_message.content)
                if initial_message
                else None
            ),
            reuse_request=request,
        )

    async def _launch_prepared_conversation(
        self,
        stored: StoredConversation,
        launched: LaunchedAgent,
        *,
        run_slot: RunSlot,
        initial_message: Message | None,
        reuse_request: StartConversationRequest | None = None,
    ) -> tuple[ConversationInfo, bool]:
        """持久化准备好的对话，发送第一条消息并通知。

        正常启动和子启动共享的启动尾部：智能体和 ``stored`` 配置之后的所有内容都已准
        备好。 调用者在准备任何内容之前获取 ``run_slot``，因此
        完整服务器在工作树或持久化目录存在之前拒绝启动； 该插槽将交给第一次运行。

        如果在生命周期锁持有后，id已经存在（一个客户端选择的id被一个并发创建的id抢先
        ），则现有的会话将被 ``reuse_request`` 重用，而
        ``start_conversation`` 会继续。 如果没有请求，则碰撞是一个错误。
        """
        async with self._conversation_lifecycle(stored.id):
            # 重新检查锁下。 准备 ``stored`` 等待，因此自调用者检查以来可以提交为同一 ID
            #  创建的并发。 如果没有这个，失败者将为已经存在的 id 启动第二个
            # EventService，重新运行其初始消息。
            #
            if self._has_conversation(stored.id):
                if reuse_request is None:
                    raise ValueError(f"Conversation with id {stored.id} already exists")
                return await self._reuse_existing_conversation_locked(
                    stored.id, reuse_request
                )
            # 新对话：智能体写入 base_state.json（其唯一事实来源），而不是 meta.json。
            # 明确地传递它。
            #
            event_service = await self._start_event_service(
                stored, is_new_conversation=True, launched=launched
            )
        if initial_message is not None:
            await event_service.send_message(initial_message, False)
            await event_service.run(run_slot=run_slot)

        state = await event_service.get_state()
        conversation_info = _compose_conversation_info(event_service.stored, state)

        # 通知对话 Webhook 对话已开始
        await self._notify_conversation_webhooks(
            _compose_webhook_conversation_info(event_service.stored, state)
        )

        return conversation_info, True

    async def pause_conversation(self, conversation_id: UUID) -> bool:
        event_service = await self._get_or_load_event_service(conversation_id)
        if event_service:
            await event_service.pause()
            # 通知对话 Webhook 有关暂停的对话
            state = await event_service.get_state()
            conversation_info = _compose_webhook_conversation_info(
                event_service.stored, state
            )
            await self._notify_conversation_webhooks(conversation_info)
        return bool(event_service)

    async def interrupt_conversation(self, conversation_id: UUID) -> bool:
        """立即取消飞行中的 LLM 通话。

        与等待当前 LLM 请求完成的：meth:`pause_conversation` 不同，这会取消正在运行的
         ``arun()`` 任务，因此中断会在中途生
        效。
        """
        event_service = await self._get_or_load_event_service(conversation_id)
        if event_service:
            await event_service.interrupt()
            state = await event_service.get_state()
            conversation_info = _compose_webhook_conversation_info(
                event_service.stored, state
            )
            await self._notify_conversation_webhooks(conversation_info)
        return bool(event_service)

    async def resume_conversation(self, conversation_id: UUID) -> bool:
        return bool(await self._get_or_load_event_service(conversation_id))

    def _worktree_dir(self, stored: StoredConversation) -> Path | None:
        return conversation_worktree_dir(
            self.conversation_worktree_root, stored.workspace.working_dir
        )

    async def delete_conversation(self, conversation_id: UUID) -> bool:
        event_services = self._event_services
        if event_services is None:
            raise ValueError("inactive_service")
        if (
            conversation_id not in event_services
            and conversation_id not in self._conversation_records
        ):
            return False
        async with self._conversation_lifecycle(conversation_id):
            event_service = await self._get_or_load_event_service_locked(
                conversation_id,
                require_runtime_bindings=False,
            )
            if event_service is None:
                return False

            # 在关闭之前通知对话 Webhook 有关已停止的对话
            try:
                state = await event_service.get_state()
                conversation_info = _compose_webhook_conversation_info(
                    event_service.stored, state
                )
                conversation_info.execution_status = (
                    ConversationExecutionStatus.DELETING
                )
                await self._notify_conversation_webhooks(conversation_info)
            except Exception as e:
                logger.warning(
                    f"Failed to notify webhooks for conversation {conversation_id}: {e}"
                )

            # 关闭事件服务
            try:
                await event_service.close()
            except CredentialBindingError:
                raise
            except Exception as e:
                logger.warning(
                    f"Failed to close event service for conversation "
                    f"{conversation_id}: {e}"
                )
            event_services.pop(conversation_id, None)
            # 子级是孤立的，而不是级联的：parent_conversation_id 悬空，就像源删除上的
            # forked_from_conversation_id 一样。
            #
            self._conversation_records.pop(conversation_id, None)
            self._credential_bindings.pop(conversation_id, None)

            # 仅安全删除对话目录（保留工作区）。 此操作可能会因权限问题而失败，但我们不
            # 希望这阻止对话被标记为已删除。
            #
            safe_rmtree(
                event_service.conversation_dir,
                f"conversation directory for {conversation_id}",
            )
            worktree_dir = self._worktree_dir(event_service.stored)
            # 叉子共享其来源的工作树； 最后删除的一项将其删除。
            if worktree_dir is not None and not any(
                self._worktree_dir(record.stored) == worktree_dir
                for record in self._conversation_records.values()
            ):
                await asyncio.to_thread(remove_conversation_worktree, worktree_dir)

            logger.info(f"Successfully deleted conversation {conversation_id}")
            return True

    async def update_conversation(
        self, conversation_id: UUID, request: UpdateConversationRequest
    ) -> bool:
        """更新对话元数据。

        Args:
            conversation_id: 要更新的对话 ID
            request: 包含要更新字段的请求对象（e.g.、标题、标签）

        Returns:
            bool: True 如果对话已成功更新，False 如果未找到
        """
        event_service = await self._get_or_load_event_service(conversation_id)
        if event_service is None:
            return False

        loop = asyncio.get_running_loop()
        state = await event_service.get_state()
        update: dict[str, Any] = {"updated_at": utc_now()}
        if request.title is not None:
            update["title"] = request.title.strip()
        if request.tags is not None:
            update["tags"] = request.tags
        # 持久化第一个：拒绝写入 (e.g. 丢失租约所有权）必须保持内存中的元数据和状态不变
        # 。
        #
        await event_service.save_meta(event_service.stored.model_copy(update=update))
        if request.tags is not None:
            # 将已持久化 ConversationState 更新保持在状态锁下，以便自动保存和状态更改回
            # 调观察到一致的突变。
            #
            state = await loop.run_in_executor(
                None, _update_state_tags_sync, state, request.tags
            )
        record = self._conversation_records.get(conversation_id)
        if record is not None:
            record.stored = event_service.stored
            record.cached_info = None

        # 通知对话 Webhook 有关更新的对话。 在状态锁下构建全状态快照，但同步在工作线程线
        # 程中等待，以便元数据更新不会阻塞 FastAPI 事件循环。
        #
        conversation_info = await loop.run_in_executor(
            None, _compose_webhook_conversation_info_sync, event_service.stored, state
        )
        await self._notify_conversation_webhooks(conversation_info)

        updated_fields = []
        if request.title is not None:
            updated_fields.append("title")
        if request.tags is not None:
            updated_fields.append("tags")
        logger.info(
            "Successfully updated conversation %s (%s)",
            conversation_id,
            ", ".join(updated_fields),
        )
        return True

    async def get_event_service(self, conversation_id: UUID) -> EventService | None:
        return await self._get_or_load_event_service(conversation_id)

    async def get_persisted_event_service(
        self, conversation_id: UUID
    ) -> EventService | None:
        """打开仅附加事件历史记录，无需获取运行时租用。"""
        if self._event_services is None:
            raise ValueError("inactive_service")
        record = self._conversation_records.get(conversation_id)
        if record is None:
            return None
        return EventService.for_persisted_events(record.stored, self.conversations_dir)

    async def generate_conversation_title(
        self, conversation_id: UUID, max_length: int = 50, llm: LLM | None = None
    ) -> str | None:
        """使用 LLM 生成对话的标题。"""
        event_service = await self._get_or_load_event_service(conversation_id)
        if event_service is None:
            return None

        # 委托给 EventService 以避免访问私人对话内部
        title = await event_service.generate_title(llm=llm, max_length=max_length)
        return title

    async def ask_agent(self, conversation_id: UUID, question: str) -> str | None:
        """向智能体询问一个简单的问题，而不影响对话状态。"""
        event_service = await self._get_or_load_event_service(conversation_id)
        if event_service is None:
            return None

        # 委托给 EventService 以避免访问私人对话内部
        response = await event_service.ask_agent(question)
        return response

    async def condense(self, conversation_id: UUID) -> bool:
        """强制对话历史记录上下文压缩。"""
        event_service = await self._get_or_load_event_service(conversation_id)
        if event_service is None:
            return False

        # 委托给 EventService 以避免访问私人对话内部
        await event_service.condense()
        return True

    async def fork_conversation(
        self,
        source_id: UUID,
        *,
        fork_id: UUID | None = None,
        title: str | None = None,
        tags: dict[str, str] | None = None,
        reset_metrics: bool = True,
        from_event_id: str | None = None,
    ) -> ConversationInfo | None:
        """分叉现有对话，深度复制其事件历史记录。

        分叉是已持久化到磁盘，然后作为新的 EventService 加载，因此分叉的对话完全独立
        于源。

        当设置 *from_event_id* 时，仅复制直到并包括该事件的分支，并在那里设置分叉的
        HEAD； 否则整个对话都会被复制（今天的行为）。

        当 *source_id* 不存在时返回 ``None``。

        Raises:
            ValueError: 如果 *fork_id* 已被活动的
                对话，或者如果 *from_event_id* 不在源对话中。
        """
        if self._event_services is None:
            raise ValueError("inactive_service")

        # 在 fork() 写入其持久化目录之前拒绝重复的分叉 ID。 该目录包括实时对话和卸载对话
        # 。
        #
        if fork_id is not None and fork_id in self._conversation_records:
            raise ValueError(f"Conversation with id {fork_id} already exists")

        source_service = await self._get_or_load_event_service(source_id)
        if source_service is None:
            return None

        source_conversation = source_service.get_conversation()
        fork_conv_id = fork_id or uuid4()

        fork_dir = self.conversations_dir / fork_conv_id.hex
        async with self._conversation_lifecycle(fork_conv_id):
            # 在锁重新检查一下，确保fork()在``fork_dir``写入之前，没有并发同id的分支已经
            # 提交，那么fork()和清理操作之后，都会触及获胜者的已持久化数据。
            #
            if self._has_conversation(fork_conv_id):
                raise ValueError(f"Conversation with id {fork_id} already exists")

            # fork() 将事件和状态深度复制到 ``fork_dir`` 中。
            fork_conv = await asyncio.to_thread(
                source_conversation.fork,
                conversation_id=fork_conv_id,
                tags=tags,
                reset_metrics=reset_metrics,
                from_event_id=from_event_id,
            )
            # 提取已持久化数据，然后丢弃临时会话。
            fork_agent = cast(AgentBase, fork_conv.agent)
            fork_workspace = fork_conv.workspace
            fork_conv.delete_on_close = False
            fork_conv.close()

            # _start_event_service 将从已持久化 fork 目录恢复。 复制源的存储元数据，这样
            # 请求级别的配置（client_tools，tool_module_qualnames，agent_definitions，插
            # 件，机密…）在分支上保留，然后只覆盖分支特定的字段。 Without this, e.g. 客
            # 户端工具对话的分支将丢失meta.json中的``client_tools``，并且在服务器重新启
            # 动后无法重新注册其工具。
            # 注意：智能体是存储在 meta.json (StoredConversation) 中的不 —
            # 叉子的智能体已经是已持久化到叉子的 base_state.json
            # ``source_conversation.fork`` 上面。 它被传递到
            # ``_start_event_service`` 通过 ``agent=`` 作为新对话路径。
            #
            fork_overrides: dict[str, Any] = {
                "id": fork_conv_id,
                "workspace": fork_workspace,
                "title": title,
                "tags": tags or {},
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "forked_from_conversation_id": source_id,
                "forked_from_event_id": from_event_id,
            }
            if reset_metrics:
                fork_overrides["metrics"] = None
            fork_stored = source_service.stored.model_copy(update=fork_overrides)
            try:
                # 如果服务无法启动，请清理孤立的持久化目录，这样我们就不会在磁盘上留下过
                # 时的状态。
                #
                fork_event_service = await self._start_event_service(
                    fork_stored, is_new_conversation=True, persisted_agent=fork_agent
                )
            except Exception:
                safe_rmtree(fork_dir)
                raise

        state = await fork_event_service.get_state()
        return _compose_conversation_info(
            fork_event_service.stored, state, self._children_of(fork_conv_id)
        )

    async def start_child_conversation(
        self,
        parent_id: UUID,
        request: StartChildConversationRequest,
    ) -> StartChildConversationResponse | None:
        """在此服务器上启动源自 *parent_id* 的子对话。

        就像：meth:`fork_conversation`，子类继承了父类的存储配置 (机密，客户端工具、
        插件、钩子、标签、...) 和其解析智能体，但其事件历
        史从头开始：``task`` 作为子类的第一个用户消息被传递。 与
        ``isolation="worktree"`` 当工作区是一个具有可用基本提交的 git 存储库时，子级
        在从父级工作区中分离出来的 git 工作树中运行；
         否则（或使用``isolation="shared"``）它共享父目录。 该链接是通过记录的
        ``parent_conversation_id``.

        当 *parent_id* 不存在时返回 ``None``。

        Raises:
            ConversationRunLimitExceeded: 如果所有服务器运行槽都被占用。
                在这种情况下，什么都不是已持久化。
        """
        if self._event_services is None:
            raise ValueError("inactive_service")

        parent_service = await self._get_or_load_event_service(parent_id)
        if parent_service is None:
            return None

        # 首先入场，就像正常启动一样：完整服务器在工作树或子目录持久化目录存在之前拒绝启
        # 动。
        #
        with await RunSlot.acquire(self._run_semaphore) as run_slot:
            parent_stored = parent_service.stored
            parent_agent = cast(AgentBase, parent_service.get_conversation().agent)
            child_id = uuid4()

            # 重用常规启动的工作树机制：计划工作树（并将其附在子进程智能体中），只有当父
            # 进程工作区有一个可用的 git 基本提交时。 否则，子节点会共享它。
            #
            worktree = (
                _plan_conversation_worktree(
                    parent_stored.workspace,
                    child_id,
                    self.conversation_worktree_root,
                    None,
                )
                if request.isolation == "worktree"
                else None
            )
            launched = await asyncio.to_thread(
                lambda: finalize(
                    parent_agent,
                    live_launch_runtime(
                        self.acp_skill_sourcing, enable_browser=self.enable_browser
                    ),
                    extra_suffixes=[worktree.guidance] if worktree else (),
                )
            )
            workspace = (
                _create_conversation_worktree(worktree)
                if worktree is not None
                else parent_stored.workspace
            )
            now = utc_now()
            child_stored = parent_stored.model_copy(
                update={
                    "id": child_id,
                    "workspace": workspace,
                    "worktree": request.isolation == "worktree",
                    "title": request.title,
                    "metrics": None,
                    "created_at": now,
                    "updated_at": now,
                    "parent_conversation_id": parent_id,
                    "forked_from_conversation_id": None,
                    "forked_from_event_id": None,
                }
            )
            info, _ = await self._launch_prepared_conversation(
                child_stored,
                launched,
                run_slot=run_slot,
                initial_message=Message(
                    role="user", content=[TextContent(text=request.task)]
                ),
            )

        return StartChildConversationResponse(
            conversation_id=child_id,
            parent_conversation_id=parent_id,
            status=info.execution_status.value,
            title=info.title,
            workspace=str(workspace.working_dir),
            isolation="worktree" if worktree is not None else "shared",
        )

    async def navigate_conversation(
        self, conversation_id: UUID, *, event_id: str | None = None
    ) -> ConversationInfo | None:
        """将对话的 HEAD 移至现有事件（就地重新根）。

        所有分支都保留在磁盘上； 只有智能体运行的活动分支发生变化。 新的 HEAD 通过对
        话自身的状态自动保存而保留。 当 *conversation_id* 不
        存在时返回 ``None``。

        Raises:
            ValueError: 如果 *event_id* 不是 ``None`` 并且不存在于
                谈话。
        """
        event_service = await self._get_or_load_event_service(conversation_id)
        if event_service is None:
            return None

        await event_service.navigate_to(event_id)
        state = await event_service.get_state()
        return _compose_conversation_info(
            event_service.stored, state, self._children_of(conversation_id)
        )

    async def __aenter__(self):
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        self._run_executor = ThreadPoolExecutor(
            max_workers=self.max_concurrent_runs,
            thread_name_prefix="conversation-run",
        )
        self._run_semaphore = asyncio.Semaphore(self.max_concurrent_runs)
        self._event_services = {}
        self._conversation_records = await asyncio.to_thread(self._load_catalog_sync)

        # 初始化对话 Webhook 个订阅者
        self._conversation_webhook_subscribers = [
            ConversationWebhookSubscriber(
                spec=webhook_spec,
                session_api_key=self.session_api_key,
            )
            for webhook_spec in self.webhook_specs
        ]

        # 保留崩溃恢复语义，而不需要补充每个空闲对话。 RUNNING记录可能包含中断的工具调用
        # ； EventService.start() 将这些记录标记为 ERROR 并附加相应的恢复事件。 实时租赁
        # 仍然可以防止接管。
        #
        running_ids = [
            conversation_id
            for conversation_id, record in self._conversation_records.items()
            if record.execution_status == ConversationExecutionStatus.RUNNING
        ]
        for conversation_id in running_ids:
            try:
                await self._get_or_load_event_service(conversation_id)
            except Exception:
                # 一个中断的对话不得阻止服务器启动或使每个正常的对话不可用。
                #
                logger.exception(
                    "error_recovering_running_conversation:%s",
                    conversation_id,
                    stack_info=True,
                )

        self._lease_renewal_task = asyncio.create_task(self._renew_all_leases_loop())
        if self.conversation_idle_ttl_seconds:
            self._eviction_task = asyncio.create_task(
                self._evict_idle_conversations_loop()
            )

        return self

    async def _renew_all_leases_loop(self) -> None:
        """为所有活动对话续订租约的单一后台任务。

        用一个集中循环替换 N 个每次会话更新任务，从而减少异步任务开销。 每次更新都涉
        及同步文件 I/O（FileLock + 读 + 写），因此各个调用通过
        ``asyncio.to_thread`` 卸载，以避免阻塞事件循环。
        """
        try:
            while True:
                await asyncio.sleep(LEASE_RENEW_INTERVAL_SECONDS)
                event_services = self._event_services
                if event_services is None:
                    return
                for event_service in list(event_services.values()):
                    await asyncio.to_thread(event_service.renew_lease)
        except asyncio.CancelledError:
            raise

    async def _evict_idle_conversations_loop(self) -> None:
        """定期驱逐超出 TTL 的空闲对话。"""
        ttl = self.conversation_idle_ttl_seconds
        if not ttl or ttl <= 0:
            return
        interval = max(60.0, ttl / 2)
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await self._evict_idle_conversations(ttl)
                except Exception:
                    logger.exception(
                        "error_evicting_idle_conversations", stack_info=True
                    )
        except asyncio.CancelledError:
            raise

    async def _evict_idle_conversations(self, ttl_seconds: float) -> None:
        """驱逐闲置的对话，保留记录，以便它们在访问时重新补充水分。

        正在运行的或外部订阅的对话将被跳过。
        """
        async with self._exclusive_lifecycle():
            event_services = self._event_services
            if event_services is None:
                return
            to_evict = [
                conversation_id
                for conversation_id, event_service in event_services.items()
                if event_service.is_open()
                and event_service.idle_seconds() >= ttl_seconds
                and event_service.is_idle_evictable()
            ]
            for conversation_id in to_evict:
                event_service = event_services.pop(conversation_id, None)
                if event_service is None:
                    continue
                # 保留只在运行时使用的状态，以确保重新加载时状态忠实：同步链表应更新为当
                # 前存储的（switch_acp_model / 机密更新替换它）并返回凭据绑定（close()
                # 清除它们）。
                #
                record = self._conversation_records.get(conversation_id)
                if record is not None:
                    record.stored = event_service.stored
                    record.cached_info = None
                bindings = dict(event_service.credential_bindings)
                try:
                    await event_service.__aexit__(None, None, None)
                except Exception:
                    logger.warning(
                        "Failed to evict idle conversation %s",
                        conversation_id,
                        exc_info=True,
                    )
                else:
                    logger.info(
                        "Evicted idle conversation %s (idle >= %.0fs)",
                        conversation_id,
                        ttl_seconds,
                    )
                if bindings:
                    pending = self._credential_bindings.setdefault(conversation_id, {})
                    for secret_name, binding in bindings.items():
                        pending.setdefault(secret_name, binding)

    async def __aexit__(self, exc_type, exc_value, traceback):
        if self._eviction_task is not None:
            self._eviction_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._eviction_task
            self._eviction_task = None

        if self._lease_renewal_task is not None:
            self._lease_renewal_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._lease_renewal_task
            self._lease_renewal_task = None

        async with self._exclusive_lifecycle():
            event_services = self._event_services
            if event_services is None:
                return
            services = tuple(event_services.items())
            results = await asyncio.gather(
                *[
                    event_service.__aexit__(exc_type, exc_value, traceback)
                    for _, event_service in services
                ],
                return_exceptions=True,
            )
            failed_ids = {
                conversation_id
                for (conversation_id, _), result in zip(services, results, strict=True)
                if isinstance(result, BaseException)
            }
            failures = [
                result for result in results if isinstance(result, BaseException)
            ]
            if failed_ids:
                self._event_services = {
                    conversation_id: event_service
                    for conversation_id, event_service in services
                    if conversation_id in failed_ids
                }
                self._conversation_records = {
                    conversation_id: record
                    for conversation_id, record in self._conversation_records.items()
                    if conversation_id in failed_ids
                }
                self._credential_bindings = {
                    conversation_id: bindings
                    for conversation_id, bindings in self._credential_bindings.items()
                    if conversation_id in failed_ids
                }
            else:
                self._event_services = None
                self._conversation_records = {}
                self._credential_bindings = {}
        if self._run_executor is not None:
            self._run_executor.shutdown(wait=False)
            self._run_executor = None
        if failures:
            assert self._event_services is not None
            for event_service in self._event_services.values():
                await asyncio.to_thread(event_service.renew_lease)
            self._lease_renewal_task = asyncio.create_task(
                self._renew_all_leases_loop()
            )
            credential_failure = next(
                (
                    failure
                    for failure in failures
                    if isinstance(failure, CredentialBindingError)
                ),
                None,
            )
            raise credential_failure or failures[0]

    @classmethod
    def get_instance(cls, config: Config) -> "ConversationService":
        # 在任何会话处理程序可以在没有配置的情况下调用 get_settings_store() 之前，使用服
        # 务器密码初始化设置存储单例。
        #
        from openhands.agent_server.mcp_oauth_store import (
            create_settings_backed_mcp_tool_provider,
        )
        from openhands.agent_server.persistence import (
            get_secrets_store,
            get_settings_store,
        )

        get_settings_store(config)
        return ConversationService(
            conversations_dir=config.conversations_path,
            webhook_specs=config.webhooks,
            session_api_key=(
                config.session_api_keys[0] if config.session_api_keys else None
            ),
            cipher=config.cipher,
            mcp_tool_provider=create_settings_backed_mcp_tool_provider(config),
            secrets_store=get_secrets_store(config),
            max_concurrent_runs=config.max_concurrent_runs,
            lease_ttl_seconds=config.lease_ttl_seconds,
            conversation_idle_ttl_seconds=config.conversation_idle_ttl_seconds,
            conversation_worktree_root=config.conversation_worktree_root,
            acp_skill_sourcing=config.acp_skill_sourcing,
            enable_browser=config.enable_browser,
        )

    async def _start_event_service(
        self,
        stored: StoredConversation,
        *,
        is_new_conversation: bool = False,
        launched: LaunchedAgent | None = None,
        persisted_agent: AgentBase | None = None,
    ) -> EventService:
        event_services = self._event_services
        if event_services is None:
            raise ValueError("inactive_service")

        # 新对话以 ``launched`` 智能体开始（meta.json 不包含它）。 否则从
        # base_state.json 读取智能体，并且
        # ``persisted_agent``仅保留读取的凭据检查。
        agent = launched.agent if launched is not None else persisted_agent
        credential_bindings = await self._resolve_credential_bindings(
            stored, agent=agent
        )
        event_service = EventService(
            stored=stored,
            conversations_dir=self.conversations_dir,
            agent=launched.agent if launched is not None else None,
            cipher=self._cipher_for(stored.id),
            mcp_tool_provider=self.mcp_tool_provider,
            credential_bindings=credential_bindings,
            owner_instance_id=self.owner_instance_id,
            lease_ttl_seconds=self.lease_ttl_seconds,
        )
        # 租约续订由 ConversationService 上的集中 _renew_all_leases_loop 任务处理。
        #
        event_service._external_lease_renewal = True
        event_service._run_executor = self._run_executor
        event_service._run_semaphore = self._run_semaphore

        try:
            await event_service.start()
            # start()后注册订阅者，以便subscribe_to_events同步运行其初始状态推送，并将任
            # 何失败上报给调用者，而不是在稍后推送时默默记录。
            #
            await event_service.subscribe_to_events(
                _EventSubscriber(service=event_service)
            )
            if stored.autotitle and stored.title is None:
                await event_service.subscribe_to_events(
                    AutoTitleSubscriber(service=event_service)
                )
            await self._maybe_subscribe_telemetry(
                event_service, stored, is_new_conversation=is_new_conversation
            )
            await asyncio.gather(
                *[
                    event_service.subscribe_to_events(
                        WebhookSubscriber(
                            conversation_id=stored.id,
                            service=event_service,
                            spec=webhook_spec,
                            session_api_key=self.session_api_key,
                        )
                    )
                    for webhook_spec in self.webhook_specs
                ]
            )
            # 将它们标记为内部，以便空闲驱逐仅计算外部客户端。
            event_service.mark_subscription_baseline()
            # 成功启动后立即保存元数据，以确保持久化即使系统未正常关闭
            #
            await event_service.save_meta()
            if self._event_services is not event_services:
                raise ValueError("inactive_service")
        except Exception:
            try:
                await event_service.close()
            except Exception as close_error:
                logger.warning(
                    "Failed to close conversation %s after startup failure: %s",
                    stored.id,
                    close_error,
                )
            finally:
                pending = self._credential_bindings.setdefault(stored.id, {})
                for secret_name, binding in credential_bindings.items():
                    pending.setdefault(secret_name, binding)
            raise

        event_services[stored.id] = event_service
        state = await event_service.get_state()
        self._conversation_records[stored.id] = _ConversationRecord(
            stored=event_service.stored,
            execution_status=state.execution_status,
        )
        return event_service

    async def _maybe_subscribe_telemetry(
        self,
        event_service: EventService,
        stored: StoredConversation,
        *,
        is_new_conversation: bool,
    ) -> None:
        """如果遥测处于活动状态，请附加遥测订阅者。

        订户连接到 * 每 * 路径，包括补液，因此错误和终端结果始终会被捕获。 但是
        ``conversation_created`` 仅针对真正全新的产品而发出
        conversation: ``_start_event_service`` 空闲时也运行
        对话懒加载，重启后 RUNNING 个会话被恢复，这些会话会被计为创建，这将导致每台服
        务器重启时的指标膨胀。

        故意全面：遥测绝不能导致对话启动失败。 ``enabled`` 检查首先出现，因此禁用的路
        径根本不执行清理工作。
        """
        # 懒惰地解决流程汇，而不是相信在构建时捕获的值。 ``ConversationService`` 在导入
        # 时被实例化``sockets.py`` 在生命周期之前，模块作用域），在构建 sink 之前，所以
        # 总是缓存引用是预初始化 NoOp — 无论是否同意，都会沉默对话追踪。 在这里读取当前
        # 接收器使对话尊重实时决策，就像服务器生命周期和请求失败路径已经做的那样。
        #
        sink = get_telemetry_sink()
        if not sink.enabled:
            return
        try:
            factory = get_event_factory()
            if factory is None:
                return

            live_conversation = event_service._conversation
            live_agent = (
                live_conversation.agent if live_conversation is not None else None
            )
            subscriber = TelemetrySubscriber(
                conversation_id=stored.id,
                sink=sink,
                factory=factory,
                context=_build_telemetry_context(stored, factory, agent=live_agent),
            )
            await event_service.subscribe_to_events(subscriber)
            if is_new_conversation:
                subscriber.emit_started()
        except Exception:
            logger.debug("Could not attach telemetry subscriber", exc_info=True)


def _build_telemetry_context(
    stored: StoredConversation,
    factory: DiagnosticEventFactory,
    agent: AgentBase | None = None,
) -> ConversationTelemetryContext:
    """将存储的对话简化为经过净化的遥测事实。

    每次读取都是防御性的：上游的形状变化应该将属性降级为 ``unknown``，永远不会引发对
    话启动。

    智能体不再存储在meta.json上； 调用者显式传递实时/持久智能体。 当 ``agent`` 为
    ``None``（无实时对话）时，由智能体派生的字段将简单降级
    为 ``unknown``。
    """
    tags = getattr(stored, "tags", None)
    is_automation = isinstance(tags, dict) and any(
        bool(tags.get(key)) for key in _AUTOMATION_TAG_KEYS
    )

    llm = getattr(agent, "llm", None)

    workspace = getattr(stored, "workspace", None)
    workspace_kind = safe_token(
        type(workspace).__name__.lower() if workspace is not None else None
    )

    tools = getattr(agent, "tools", None)
    tool_count = len(tools) if isinstance(tools, (list, tuple)) else 0

    return ConversationTelemetryContext(
        conversation_ref=factory.conversation_ref(stored.id),
        user_id=getattr(stored, "user_id", None),
        llm_model_family=model_family(getattr(llm, "model", None)),
        agent_kind=safe_token(type(agent).__name__.lower() if agent else None),
        tool_count=tool_count,
        is_fork=getattr(stored, "forked_from_conversation_id", None) is not None,
        has_agent_profile=getattr(stored, "launched_agent_profile", None) is not None,
        workspace_kind=workspace_kind,
        # 政策类型，而不是布尔值：布尔值会崩溃ConfirmRisky。
        confirmation_policy=safe_token(
            type(getattr(stored, "confirmation_policy", None)).__name__.lower()
        ),
        is_automation=is_automation,
    )


@dataclass
class _EventSubscriber(Subscriber):
    service: EventService

    async def __call__(self, _event: Event):
        # 任何事件都是活动； 刷新空闲驱逐时钟。
        self.service.touch()
        # 跳过更新 ConversationStateUpdateEvent 的时间戳，该时间戳在启动/状态更改期间发
        # 布，并不代表实际的对话活动。 这可以防止 updated_at 在每次服务器重新启动时重置
        # 。
        #
        if isinstance(_event, ConversationStateUpdateEvent):
            return
        self.service.stored.updated_at = utc_now()
        update_last_execution_time()


@observe(
    name="conversation.generate_title",
    ignore_inputs=["conversation", "llm", "on_error"],
    metadata={OPERATION_METADATA_KEY: "title_generation"},
)
def _generate_title_traced(
    # 必须保持第一个位置：``observe`` 重新附加它所携带的根跨度，并且这在无上下文的执行器
    # 线程上运行。
    #
    conversation: LocalConversation | None,
    message: str,
    llm: LLM | None,
    max_length: int,
    on_error: Callable[[Exception], None] | None = None,
    prompt: str | None = None,
) -> str:
    call_context = (
        conversation.get_llm_call_context() if conversation else LLMCallContext()
    )
    return generate_title_from_message(
        message,
        llm,
        max_length,
        call_context=call_context,
        on_error=on_error,
        prompt=prompt,
    )


@dataclass
class AutoTitleSubscriber(Subscriber):
    service: EventService

    async def __call__(self, event: Event) -> None:
        # 仅对传入的用户消息进行操作
        if not isinstance(event, MessageEvent) or event.source != "user":
            return
        # Guard：如果已经设置了标题则跳过 (e.g. 通过并发任务）
        if self.service.stored.title is not None:
            return

        # 现在提取消息文本，以免在后台任务启动之前，导致事件尚未已持久化到事件列表时，标
        # 题生成尝试读取它。
        #
        message_text = extract_message_text(event)
        if not message_text:
            return

        # 优先级：title_llm_profile（如果已配置并加载）→ agent.llm →
        # 截断。 对于未配置 title_llm_profile 的消费者来说，这可以保证自动标题不会中断。
        #
        conversation = self.service._conversation
        title_llm = self._load_title_llm()
        if title_llm is None:
            title_llm = conversation.agent.llm if conversation else None

        # 在 UI 自动标题期间出现 LLM 失败（问题 #16686）； 生成本身保持非致命状态并退回
        # 到截断状态。
        #
        def _on_title_error(exc: Exception) -> None:
            self.service._publish_error_event_sync(exc)

        async def _generate_and_save() -> None:
            try:
                loop = asyncio.get_running_loop()
                title = await loop.run_in_executor(
                    None,
                    _generate_title_traced,
                    conversation,
                    message_text,
                    title_llm,
                    50,
                    _on_title_error,
                    self.service.stored.prompt,
                )
                if title and self.service.stored.title is None:
                    await self.service.save_meta(
                        self.service.stored.model_copy(
                            update={"title": title, "updated_at": utc_now()}
                        )
                    )
            except Exception:
                logger.warning(
                    f"Auto-title generation failed for "
                    f"conversation {self.service.stored.id}",
                    exc_info=True,
                )

        asyncio.create_task(_generate_and_save())

    def _load_title_llm(self) -> LLM | None:
        """从配置文件存储加载用于标题生成的 LLM。

        Returns:
            如果 title_llm_profile 配置并成功加载，则为 LLM 实例，否则为 None。 当返
            回 None 时，调用者回退到智能体的 LLM
            （然后到消息截断）。
        """
        profile_name = self.service.stored.title_llm_profile
        if not profile_name:
            return None

        try:
            from openhands.agent_server.persistence.store import (
                get_llm_profile_store,
            )

            profile_store = get_llm_profile_store()
            return profile_store.load(profile_name, cipher=self.service.cipher)
        except (FileNotFoundError, ValueError) as e:
            logger.warning(
                f"Failed to load title LLM profile '{profile_name}': {e}. "
                "Falling back to the agent's LLM."
            )
            return None


@dataclass
class WebhookSubscriber(Subscriber):
    conversation_id: UUID
    service: EventService
    spec: WebhookSpec
    session_api_key: str | None = None
    queue: list[Event] = field(default_factory=list)
    _flush_timer: asyncio.Task | None = field(default=None, init=False)
    _post_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _queue_sizes: list[int] = field(default_factory=list, init=False)
    _queue_bytes: int = field(default=0, init=False)
    _dropped_events: int = field(default=0, init=False)
    _closed: bool = field(default=False, init=False)
    # 每个实例的睡眠接缝因此测试会覆盖延迟而无需修补全局 asyncio.sleep。 default_factory
    # （非默认）将其保留为实例属性，否则该函数将作为方法被描述符绑定。
    #
    _sleep: Callable[[float], Awaitable[None]] = field(
        default_factory=lambda: asyncio.sleep, init=False
    )

    def _buffer_full(self) -> bool:
        return (
            len(self.queue) >= self.spec.event_buffer_size
            or self._queue_bytes >= self.spec.max_batch_bytes
        )

    async def __call__(self, event: Event):
        """将事件添加到队列并在达到缓冲区大小时发布到 Webhook。"""
        self._enqueue(event)

        if self._buffer_full():
            if self._post_lock.locked():
                # 运行中的 _post_events 会在完成后重新检查缓冲区，并在发布失败时重新启动
                # 计时器。
                #
                self._start_flush_timer()
                return
            # 取消计时器，因为我们由于缓冲区大小而正在刷新
            self._cancel_flush_timer()
            await self._post_events()
        elif self.queue:
            self._start_flush_timer()

    async def close(self):
        """将队列中的所有剩余项目发送到 Webhook。"""
        self._closed = True
        # 取消任何挂起的刷新计时器
        self._cancel_flush_timer()

        if self.queue:
            await self._post_events()

    async def _post_events(self):
        """连续发布有界批次，直到队列为空或发布失败。"""
        async with self._post_lock:
            self._sync_queue_sizes()
            self._trim_queue()
            events_remaining = len(self.queue)
            while events_remaining:
                events_to_post, event_data = self._take_batch(events_remaining)
                if not await self._post_batch(event_data):
                    self._requeue(events_to_post)
                    # 在 POST 期间触发的计时器看到一个空队列并退出，因此为重新排队的事件
                    # 准备一个。
                    #
                    self._start_flush_timer()
                    return
                events_remaining -= len(events_to_post)
                if not events_remaining and self._buffer_full():
                    # POST期间发布的事件再次填满了缓冲区。
                    events_remaining = len(self.queue)
            # 在 POST 期间启动的计时器没有剩余内容可以刷新。
            if not self.queue and self._flush_timer is not asyncio.current_task():
                self._cancel_flush_timer()

    async def _post_batch(self, event_data: list[dict[str, Any]]) -> bool:
        """使用重试逻辑发布一批已序列化批次。"""

        # 准备标头
        headers = self.spec.headers.copy()
        if self.session_api_key:
            headers["X-Session-API-Key"] = self.session_api_key

        # 构建事件 URL
        events_url = (
            f"{self.spec.base_url.rstrip('/')}/events/{self.conversation_id.hex}"
        )

        # 重试逻辑
        for attempt in range(self.spec.num_retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method="POST",
                        url=events_url,
                        json=event_data,
                        headers=headers,
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    logger.debug(
                        f"Successfully posted {len(event_data)} events "
                        f"to webhook {events_url}"
                    )
                    return True
            except Exception as e:
                logger.warning(f"Webhook post attempt {attempt + 1} failed: {e}")
                if attempt < self.spec.num_retries:
                    await self._sleep(self.spec.retry_delay)
                else:
                    logger.error(
                        f"Failed to post events to webhook {events_url} "
                        f"after {self.spec.num_retries + 1} attempts"
                    )
        return False

    @staticmethod
    def _event_data(event: Event) -> dict[str, Any]:
        # mode="json" makes types such as set and SecretStr JSON-safe.
        if hasattr(event, "model_dump"):
            return event.model_dump(mode="json")
        return event.__dict__

    @classmethod
    def _event_size(cls, event: Event) -> int:
        return len(
            json.dumps(
                cls._event_data(event),
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        )

    def _sync_queue_sizes(self):
        """调用者直接替换公共队列后刷新大小统计。"""
        if len(self._queue_sizes) != len(self.queue):
            self._queue_sizes = [self._event_size(event) for event in self.queue]
            self._queue_bytes = sum(self._queue_sizes)

    def _enqueue(self, event: Event):
        self._sync_queue_sizes()
        event_size = self._event_size(event)
        self.queue.append(event)
        self._queue_sizes.append(event_size)
        self._queue_bytes += event_size
        self._trim_queue()

    def _requeue(self, events: list[Event]):
        sizes = [self._event_size(event) for event in events]
        self.queue[:0] = events
        self._queue_sizes[:0] = sizes
        self._queue_bytes += sum(sizes)
        self._trim_queue()

    def _trim_queue(self):
        dropped = 0
        while self.queue and (
            len(self.queue) > self.spec.max_queue_size
            or self._queue_bytes > self.spec.max_queue_bytes
        ):
            del self.queue[0]
            self._queue_bytes -= self._queue_sizes.pop(0)
            dropped += 1
        if dropped:
            previous_dropped = self._dropped_events
            self._dropped_events += dropped
            if (
                previous_dropped == 0
                or self._dropped_events // 100 > previous_dropped // 100
            ):
                logger.warning(
                    "Webhook queue exceeded its configured count or byte limit; "
                    f"dropped {self._dropped_events} event(s) so far for conversation "
                    f"{self.conversation_id.hex}."
                )

    def _take_batch(self, max_events: int) -> tuple[list[Event], list[dict[str, Any]]]:
        self._sync_queue_sizes()
        batch_size = 2  # JSON 数组括号
        batch_count = 0
        event_data: list[dict[str, Any]] = []

        for event, event_size in zip(self.queue, self._queue_sizes, strict=True):
            next_size = batch_size + event_size + (1 if batch_count else 0)
            if batch_count and next_size > self.spec.max_batch_bytes:
                break
            event_data.append(self._event_data(event))
            batch_size = next_size
            batch_count += 1
            if batch_count >= min(self.spec.event_buffer_size, max_events):
                break

        events = self.queue[:batch_count]
        del self.queue[:batch_count]
        removed_sizes = self._queue_sizes[:batch_count]
        del self._queue_sizes[:batch_count]
        self._queue_bytes -= sum(removed_sizes)
        return events, event_data

    def _start_flush_timer(self):
        if not self._closed and not self._flush_timer:
            self._flush_timer = asyncio.create_task(self._flush_after_delay())

    def _cancel_flush_timer(self):
        """取消当前的刷新计时器（如果存在）。"""
        if self._flush_timer and not self._flush_timer.done():
            self._flush_timer.cancel()
        self._flush_timer = None

    async def _flush_after_delay(self):
        """等待 flush_delay 秒，然后刷新事件（如果存在）。"""
        current_task = asyncio.current_task()
        should_reschedule = False
        try:
            await self._sleep(self.spec.flush_delay)
            # 仅当队列中有事件时才刷新
            if self.queue:
                await self._post_events()
                should_reschedule = bool(self.queue)
        except asyncio.CancelledError:
            # 计时器被取消，这是预期的行为
            pass
        finally:
            if self._flush_timer is current_task:
                self._flush_timer = None
            if should_reschedule:
                self._start_flush_timer()


@dataclass
class ConversationWebhookSubscriber:
    """Webhook 对话生命周期事件（开始、暂停、停止）的订阅者。"""

    spec: WebhookSpec
    session_api_key: str | None = None
    # 实例级睡眠缝参见WebhookSubscriber._sleep。
    _sleep: Callable[[float], Awaitable[None]] = field(
        default_factory=lambda: asyncio.sleep, init=False
    )

    async def post_conversation_info(self, conversation_info: BaseModel):
        """立即将对话信息发布到 Webhook（无批处理）。"""
        # 准备标头
        headers = self.spec.headers.copy()
        if self.session_api_key:
            headers["X-Session-API-Key"] = self.session_api_key

        # 构建对话 URL
        conversations_url = f"{self.spec.base_url.rstrip('/')}/conversations"

        # 将对话信息转换为可序列化格式
        conversation_data = conversation_info.model_dump(mode="json")

        # 重试逻辑
        response = None
        for attempt in range(self.spec.num_retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method="POST",
                        url=conversations_url,
                        json=conversation_data,
                        headers=headers,
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    logger.debug(
                        f"Successfully posted conversation info "
                        f"to webhook {conversations_url}"
                    )
                    return
            except Exception as e:
                logger.warning(
                    f"Conversation webhook post attempt {attempt + 1} failed: {e}"
                )
                if attempt < self.spec.num_retries:
                    await self._sleep(self.spec.retry_delay)
                else:
                    # 记录调试失败的响应内容
                    response_content = (
                        response.text if response is not None else "No response"
                    )
                    logger.error(
                        f"Failed to post conversation info to webhook "
                        f"{conversations_url} after {self.spec.num_retries + 1} "
                        f"attempts. Response: {response_content}"
                    )


_conversation_service: ConversationService | None = None


def get_default_conversation_service() -> ConversationService:
    global _conversation_service
    if _conversation_service:
        return _conversation_service

    from openhands.agent_server.config import (
        get_default_config,
    )

    config = get_default_config()
    _conversation_service = ConversationService.get_instance(config)
    return _conversation_service
