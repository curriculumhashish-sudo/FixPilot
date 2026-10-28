"""ACPAgent — 一个 AgentBase 子类，该子类调用 ACP 服务器。

的智能体客户端协议 (ACP) lets OpenHands 使用电力进行对话 ACP兼容服务器（Claude Code，
Gemini） CLI而是通过间接的方式 LLM
calls. 的 ACP 服务器管理自己 LLM工具和执行的 ACPAgent 转发用户消息并收集响应。
OpenHands 仍然可以追加提示词-only 上下文例如，技能
目录，发送到用户消息之前 ACP server.

不像内置的智能体，一个 ACP ``step()`` 对应一个完整的远程助手轮次。 ACPAgent 因此，在
每个步骤的末尾发出一个终端 ``FinishAction``
来标记完成的回合，供下游消费者使用。

参见 https://agentclientprotocol.com/protocol/overview
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import inspect
import json
import os
import re
import shutil
import threading
import time
import uuid
import weakref
from collections.abc import (
    Awaitable,
    Callable,
    Collection,
    Generator,
    Sequence,
)
from concurrent.futures import Future
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple

from acp.client.connection import ClientSideConnection
from acp.exceptions import RequestError as ACPRequestError
from acp.helpers import image_block, text_block
from acp.meta import AGENT_METHODS
from acp.schema import (
    AcpMcpServer,
    AgentMessageChunk,
    AgentThoughtChunk,
    AllowedOutcome,
    CreateElicitationResponse,
    CreateTerminalResponse,
    DeclineElicitationResponse,
    ElicitationMode,
    EnvVariable,
    HttpHeader,
    HttpMcpServer,
    ImageContentBlock,
    KillTerminalResponse,
    McpServerStdio,
    NewSessionRequest,
    NewSessionResponse,
    PermissionOption,
    PromptResponse,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    SseMcpServer,
    TerminalOutputResponse,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
    UsageUpdate,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
)
from acp.transports import default_environment
from acp.utils import request_model
from pydantic import (
    Field,
    PrivateAttr,
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_serializer,
    field_validator,
)

from openhands.sdk.agent.acp_contracts import (
    ACPLegacySessionModels,
    extract_session_models,
    is_model_dumpable,
    normalize_acp_error,
    normalize_auth_method,
    normalize_mcp_capabilities,
    supports_legacy_model_switch,
)
from openhands.sdk.agent.acp_file_credentials import (
    ACPFileCredentialLifecycle,
    ACPFileCredentialNeedsReauthError,
    ACPFileCredentialSyncError,
    codex_auth_file,
    codex_auth_file_is_chatgpt,
    create_file_credential_lifecycle,
    file_credential_looks_usable,
    write_secret_file,
)
from openhands.sdk.agent.acp_models import ACPModelInfo
from openhands.sdk.agent.acp_skills import render_skill_catalog, write_skill_files
from openhands.sdk.agent.acp_tracing import ACPTurnTrace
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.agent.stream_context import StreamContext
from openhands.sdk.context import AgentContext
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.credential import (
    CredentialBindingError,
    CredentialSyncError,
    VersionedCredentialBinding,
)
from openhands.sdk.event import (
    ACPToolCallEvent,
    ActionEvent,
    MessageEvent,
    ObservationEvent,
    SystemPromptEvent,
)
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.llm import LLM, ImageContent, Message, MessageToolCall, TextContent
from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.config import MCPOAuthAuthCredential, MCPServer
from openhands.sdk.observability.laminar import maybe_init_laminar, observe
from openhands.sdk.settings.acp_providers import (
    ACP_PROVIDERS,
    ACPEnvConflictSpec,
    ACPFileSecretSpec,
    ACPProviderInfo,
    build_session_model_meta,
    default_acp_file_secrets,
    detect_acp_provider_by_agent_name,
    detect_acp_provider_by_command,
    get_acp_provider,
)
from openhands.sdk.tool import Tool  # noqa: TC002
from openhands.sdk.tool.builtins.finish import FinishAction, FinishObservation
from openhands.sdk.utils import maybe_truncate
from openhands.sdk.utils.pydantic_secrets import (
    serialize_secret,
    validate_secret,
)
from openhands.sdk.utils.redact import redact_text_secrets


logger = get_logger(__name__)

_codex_auth_file = codex_auth_file
_codex_auth_file_is_chatgpt = codex_auth_file_is_chatgpt
_write_secret_file = write_secret_file
maybe_init_laminar()


if TYPE_CHECKING:
    from openhands.sdk.conversation import (
        ConversationCallbackType,
        ConversationState,
        ConversationTokenCallbackType,
        LocalConversation,
    )
    from openhands.sdk.conversation.secret_registry import SecretRegistry
# prompt() 返回后等待 UsageUpdate 通知的最大秒数。 ACP 服务器在 PromptResponse 之前将
# UsageUpdate 写入线路，因此在正常情况下，通知处理程序几乎立即完成。 这个超时是针对慢速
# 或远程服务器的安全网。
#
_USAGE_UPDATE_TIMEOUT: float = float(os.environ.get("ACP_USAGE_UPDATE_TIMEOUT", "2.0"))

# 重试短暂 ACP 连接错误的配置。 当连接在会话中断开但会话状态在服务器端仍然有效时，可能会
# 发生这些错误。
#
_ACP_PROMPT_MAX_RETRIES: int = int(os.environ.get("ACP_PROMPT_MAX_RETRIES", "3"))

# 超时/取消后，短暂等待 ACP 提示词任务对会话/取消做出反应，然后重新连接回调进行下一轮。
#
_ACP_CANCEL_DRAIN_TIMEOUT: float = float(
    os.environ.get("ACP_CANCEL_DRAIN_TIMEOUT", "2.0")
)

_ACP_AUTH_TIMEOUT: float = float(os.environ.get("ACP_AUTH_TIMEOUT", "30.0"))
_ACP_NPX_CACHE_WARM_TIMEOUT: float = float(
    os.environ.get("ACP_NPX_CACHE_WARM_TIMEOUT", "300")
)
_ACP_VERSION_RE = re.compile(r"v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)")

_ACP_PROMPT_RETRY_DELAYS: tuple[float, ...] = (5.0, 15.0, 30.0)  # 秒

# 指示值得重试的瞬时连接问题的异常类型
_RETRIABLE_CONNECTION_ERRORS = (OSError, ConnectionError, BrokenPipeError, EOFError)

# ``npm run`` 将包/生命周期配置导出到后代中。 ACP 通过 ``npx`` 启动的提供者必须不能继承
# 那个上下文，否则 npm 可以尝试与父包而不是请求的包进行解析。
#
_INHERITED_NPM_ENV_EXACT: frozenset[str] = frozenset({"INIT_CWD"})
_INHERITED_NPM_ENV_PREFIXES: tuple[str, ...] = ("npm_", "NPM_")

# 来自 ACP 服务器的 JSON-RPC 错误代码是暂时的且值得重试。 这些映射到服务器端故障（HTTP
# 500 等效项），其中会话状态仍然有效但请求失败。
#
# -32603 = "Internal error" (JSON-RPC spec) — covers ACP server crashes,
#          上游模型 500 和瞬时基础设施错误。
_RETRIABLE_SERVER_ERROR_CODES: frozenset[int] = frozenset({-32603})


# ACP 工具调用内容的最大字符数 — 与终端工具使用的 MAX_CMD_OUTPUT_SIZE 和 LLM 配置中的默
# 认 max_message_chars 匹配。
#
MAX_ACP_CONTENT_CHARS: int = 30_000
_ACP_SUBPROCESS_LOG_LINE_CHARS = 4_000

# 日志行中保留的 ACP 会话 ID 的尾随字符数以进行关联。 ACP 会话 ID 是服务器发出的 token，
# 仅拥有它就足以调用 ``session/load`` — 它们实际上是承载者 token。 ``model_dump`` /
# ``model_dump_json`` 已编辑
# ``acp_resume_session_id`` 字段； 日志聚合器（Datadog、CloudWatch、...）是另一个序列化
# 边界，它会将行保留数周，因此同样的脱敏也适用于此。 八个尾随字符提供了足够的熵来关联一
# 次对话的日志行，但不足以暴力破解完整 ID。
#
_SESSION_ID_LOG_SUFFIX_LEN: Final[int] = 8


def _fingerprint_session_id(session_id: str | None) -> str:
    """将 ACP 会话 ID 呈现为短的、不可逆的指纹。

    ACP 会话ID实际上相当于 token （持有任何会话ID的人都可以对 ``session/load`` 服务器
    发起 ACP），因此日志中不应出现完整的值——请参
    阅：data:`_SESSION_ID_LOG_SUFFIX_LEN`。

    对于 ``None`` 返回 ``"<none>"``，对于短于或等于后缀长度的 id 返回 ``"<short>"`` (
    e.g. 测试测试夹具），否则为
    ``"...<last-N>"``。
    """
    if session_id is None:
        return "<none>"
    if len(session_id) <= _SESSION_ID_LOG_SUFFIX_LEN:
        return "<short>"
    return f"...{session_id[-_SESSION_ID_LOG_SUFFIX_LEN:]}"


def _strip_inherited_npm_env(env: dict[str, str]) -> None:
    """删除从父堆栈继承的 npm 生命周期/配置变量。"""
    for key in list(env):
        if key in _INHERITED_NPM_ENV_EXACT or key.startswith(
            _INHERITED_NPM_ENV_PREFIXES
        ):
            env.pop(key, None)


# 限制 asyncio.StreamReader 使用的缓冲区 ACP  子进程管道。 默认值（64） KiB)太小了
# session_update 包含大量工具调用输出的通知e.g. 文件内容、测试结果）。 当我单身时 JSON-
# RPC 线超过极限， readline() 提出了 LimitOverrunError，使过滤和接收流水线静默终止，并留
# 下 prompt() 未来永远无法解决 MiB 这是一个当前兼容性的实用限度 ACP 服务器，而不是对大型
# 的 [endorsement] 的支持 JSON-RPC  载荷; 长期解决方案是针对大型工具输出的协议级分块/流
# 式传输。
#
_STREAM_READER_LIMIT: int = 100 * 1024 * 1024  # 100 MiB

# on_activity 心跳信号之间的最小间隔（秒）。 进行限制以避免过多的调用，同时仍将空闲计时
# 器保持在远低于约 20 分钟的运行时-API 终止阈值。 与智能体-服务器的流式传输-delta 心跳共
# 享，因此两条路径保持相同的速度。
#
ACTIVITY_SIGNAL_INTERVAL: Final[float] = 30.0

# ACP 代表最终结果的工具调用状态。 ``pending``和``in_progress``表示调用仍在进行中，如果
# 在到达终端状态之前state.events上的活发事件被终止，那么该事件将永远被遗弃。
#
_TERMINAL_TOOL_CALL_STATUSES: frozenset[str] = frozenset({"completed", "failed"})


class _PromptDrainResult(NamedTuple):
    drained: bool
    completed: bool
    response: PromptResponse | None
    error: BaseException | None


# 稳定的标识符印在哨兵值  LLM 所以下游代码（e.g. title_utils) 可以检测 "this" LLM 不能不
# 依赖模型名称调用它——我们会在实际模型上覆盖掉它 ``acp_model`` 已知，因此日志和已序列化
# 状态显示实际模型，而不是 [ ]ACP-managed".
#
ACP_SENTINEL_USAGE_ID = "acp-managed"


def _make_dummy_llm() -> LLM:
    """创建一个永远不应该直接调用的虚拟 LLM。"""
    return LLM(model="acp-managed", usage_id=ACP_SENTINEL_USAGE_ID)


# ---------------------------------------------------------------------------
# ACP 客户端实现
# ---------------------------------------------------------------------------


# ACP 身份验证方法 ID → 环境变量提供凭据。 当服务器报告 auth_methods 时，我们选择第一个
# 存在所需凭据源的方法。
# 注意：故意包含 claude-login 不，因为 Claude 代码 ACP
# 使用 bypassPermissions 模式而不是 API 键身份验证。
_AUTH_METHOD_ENV_MAP: dict[str, str] = {
    "gemini-api-key": "GEMINI_API_KEY",
}
# Gemini CLI 个人 (Google OAuth) 登录，由 ``gemini login`` / 缓存
# ``gemini --acp``. 它的存在让我们可以选择服务器的 ``oauth-personal`` 身份验证方法，而无
# 需 API 密钥（镜像 ChatGPT 订阅路径）。
#
_GEMINI_OAUTH_PATH = Path(".gemini") / "oauth_creds.json"


def _preconfigured_credentials(
    provider: ACPProviderInfo | None,
    specs: Sequence[ACPFileSecretSpec],
    env: dict[str, str],
) -> list[str]:
    """凭据来源已就位，按提供时的名称命名。

    我们无法执行其所宣传的身份验证方法的服务器仍可能通过带外身份验证 — 从植入到磁盘上
    的凭据文件，或者
    from the provider key it reads straight out of its environment. Both make
    “没有凭据可用”是错误的说法。 读取注册表记录而不是提供者名称，因此这适用于任何提供
    者。
    """
    present: list[str] = []
    for spec in specs:
        location = env.get(spec.env_var)
        if not location:
            continue
        path = Path(location)
        if spec.env_points_to == "dir":
            path = path / spec.filename
        if not path.is_file():
            continue
        # 存在但无法验证的文件是最需要警告的情况，因此在 SDK 知道格式的情况下，仅存在是
        # 不够的。
        #
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if file_credential_looks_usable(spec.secret_name, text):
            present.append(spec.secret_name)
    api_key_var = provider.api_key_env_var if provider is not None else None
    if api_key_var and env.get(api_key_var):
        present.append(api_key_var)
    return present


def _select_auth_method(
    auth_methods: list[Any],
    env: dict[str, str],
) -> str | None:
    """选择存在所需凭据的身份验证方法。

    返回第一个匹配方法的 ``id``，如果没有支持的凭据源可用（服务器可能不需要身份验证）
    ，则返回 ``None``。

    首先检查文件支持的订阅/SA 登录，因此它们优先于显式的 API 键，后者充当回退方案：

    - ``chat-gpt``（法典-ACP）— ``$CODEX_HOME/auth.json`` 或
      ``~/.codex/auth.json``
    - ``vertex-ai`` (gemini-CLI) — 服务帐户 JSON 位于
      ``GOOGLE_APPLICATION_CREDENTIALS``（可部署的 Gemini 路径； 优于个人 OAuth，后者
      是主机绑定且不可部署的）
    - ``oauth-personal``（双子座-CLI）—``~/.gemini/oauth_creds.json``

    在服务器映像中，交互式登录文件不存在，因此 API-键回退方案 (e.g. 使用
    ``GEMINI_API_KEY``) 来代替。
    """
    method_ids = {m.id for m in auth_methods}
    # 当凭据文件存在时，首选文件支持的订阅/服务帐户登录。
    #
    if "chat-gpt" in method_ids and codex_auth_file_is_chatgpt(env):
        return "chat-gpt"
    gac = env.get("GOOGLE_APPLICATION_CREDENTIALS")
    if "vertex-ai" in method_ids and gac and Path(gac).is_file():
        return "vertex-ai"
    if "oauth-personal" in method_ids and (Path.home() / _GEMINI_OAUTH_PATH).is_file():
        return "oauth-personal"
    # 维护的 Codex ACP 适配器公开一个 API-key 方法，并首先从其子进程环境读取
    # CODEX_API_KEY，然后读取 OPENAI_API_KEY。
    #
    if "api-key" in method_ids and any(
        env.get(name) for name in ("CODEX_API_KEY", "OPENAI_API_KEY")
    ):
        return "api-key"
    # 回退到显式 API 键环境变量。
    for method_id, env_var in _AUTH_METHOD_ENV_MAP.items():
        if method_id in method_ids and env_var in env:
            return method_id
    return None


def _auth_selection_failure_reason(
    auth_methods: list[Any],
    env: dict[str, str],
    provider: ACPProviderInfo | None = None,
) -> str:
    method_ids = {m.id for m in auth_methods}
    reasons: list[str] = []
    if "chat-gpt" in method_ids:
        auth_path = codex_auth_file(env)
        if auth_path.is_file():
            reasons.append(f"Codex auth file {auth_path} is not valid ChatGPT auth")
        else:
            reasons.append(f"Codex auth file {auth_path} is missing")
    if "api-key" in method_ids and not any(
        env.get(name) for name in ("CODEX_API_KEY", "OPENAI_API_KEY")
    ):
        reasons.append("CODEX_API_KEY and OPENAI_API_KEY are unset")
    if provider is not None and provider.api_key_env_var:
        if not env.get(provider.api_key_env_var):
            reasons.append(f"{provider.api_key_env_var} is unset")
    # ``type: "terminal"`` 标记只有交互式 TTY 才能完成的登录，这是运行时不具备的。 如此
    # 命名的日志说明了为什么该方法从未成为候选方法，而不是暗示缺失凭据。
    #
    terminal_ids = sorted(
        m.id
        for m in (normalize_auth_method(raw) for raw in auth_methods)
        if m.type == "terminal"
    )
    if terminal_ids:
        reasons.append(
            f"{', '.join(terminal_ids)} needs an interactive terminal, which the "
            "headless runtime cannot provide"
        )
    return "; ".join(reasons) or "no supported credential source is available"


def _warn_auth_selection_failure(
    auth_methods: list[Any],
    env: dict[str, str],
    provider: ACPProviderInfo | None = None,
) -> None:
    logger.warning(
        "ACP server offers auth methods %s but no matching credential is available "
        "(%s) — session creation may fail",
        [m.id for m in auth_methods],
        _auth_selection_failure_reason(auth_methods, env, provider),
    )


def _log_acp_provider_version(agent_name: str, agent_version: str) -> None:
    try:
        provider = detect_acp_provider_by_agent_name(agent_name)
        if provider is None:
            return
        pinned_version = None
        for command_part in provider.default_command:
            package, separator, version = command_part.rpartition("@")
            if separator and package:
                pinned_version = version
                break
        reported_version = next(
            (
                match.group(1)
                for value in (agent_version, agent_name)
                if (match := _ACP_VERSION_RE.search(value)) is not None
            ),
            None,
        )
        logger.info(
            "ACP provider version: provider=%s, pinned_version=%r, "
            "agent_name=%r, agent_version=%r, reported_version=%r",
            provider.key,
            pinned_version,
            agent_name,
            agent_version,
            reported_version,
        )
        if reported_version is None:
            logger.warning(
                "Could not parse ACP provider version: provider=%s, "
                "pinned_version=%r, agent_name=%r, agent_version=%r",
                provider.key,
                pinned_version,
                agent_name,
                agent_version,
            )
        elif pinned_version is not None and reported_version != pinned_version:
            logger.warning(
                "ACP provider version mismatch: provider=%s, pinned_version=%r, "
                "reported_version=%r; provider was probably installed at runtime "
                "via the npx fallback rather than preinstalled in the image",
                provider.key,
                pinned_version,
                reported_version,
            )
    except Exception:
        logger.warning(
            "Could not verify ACP provider version: agent_name=%r, agent_version=%r",
            agent_name,
            agent_version,
        )


def _npx_packages(command: list[str]) -> list[str]:
    """固定 npm 规格 ``npx`` 命令安装，用于缓存预热。

    ``--package=<spec>`` 当存在时，标志 —— pi 将其 ACP 适配器和生成的引擎分开，并且其
    位置参数是裸的二进制名称，这将唤醒一个未挂载的包。
     否则是第一个位置，它是单包提供商的包。
    """
    if not command or command[0] != "npx":
        return []
    pinned = [
        arg.removeprefix("--package=")
        for arg in command[1:]
        if arg.startswith("--package=")
    ]
    if pinned:
        return pinned
    for arg in command[1:]:
        if not arg.startswith("-"):
            return [arg]
    return []


def _with_codex_base_url(
    command: str, args: list[str], env: dict[str, str]
) -> dict[str, str]:
    """返回已配置代理的 Codex 子进程环境。

    不同于克莱尔（Claude-）智能体-ACP （该端点已弃用） ``ANTHROPIC_BASE_URL``) and
    gemini-CLI (whose base
     URL 通过提供 ``authenticate`` gateway) **codex 不读取  ``OPENAI_BASE_URL`` 环境
     变量** — 其支持的
    基础—URL 配置文件在  ``config.toml`` （请参阅“高级配置”文档）。 其内置的
    ``openai`` 其他提供商的目标
    ``https://api.openai.com``所以，一个指向网关/代理的调用者（eval LiteLLM 通过代理
    、企业出口等
    ``OPENAI_BASE_URL`` 独自一人，每一个转角都会遇到真实的自己 OpenAI  API 使用错误的
    密钥并失败
    ``401 invalid_api_key`` — 隐隐约约浮现出来 ACP  ``-32603 Internal error``.

    ``@agentclientprotocol/codex-acp`` 从 ``CODEX_CONFIG`` 读取 JSON 对象。 现有的配
    置值将被保留，并且显式配
    置的基础 URL 或模型提供程序将获胜。

    输入映射永远不会被修改。 仅当子进程需要合成的 ``CODEX_CONFIG`` 值时，才会返回新的
    映射。
    """
    if not any("codex-acp" in tok for tok in (command, *args)):
        return env
    base_url = env.get("OPENAI_BASE_URL")
    if not base_url:
        return env
    raw_config = env.get("CODEX_CONFIG")
    try:
        config = json.loads(raw_config) if raw_config else {}
    except (TypeError, ValueError):
        # 保持无效的调用者拥有的配置不变。 适配器将显示其自己的配置错误，而不是我们隐藏
        # 它。
        #
        return env
    if not isinstance(config, dict):
        return env
    if (
        "openai_base_url" in config
        or "model_provider" in config
        or env.get("MODEL_PROVIDER")
    ):
        return env

    configured_env = env.copy()
    config["openai_base_url"] = base_url
    configured_env["CODEX_CONFIG"] = json.dumps(config, separators=(",", ":"))
    return configured_env


# ACP 服务器上选择模型的会话配置选项 ``configOptions`` / ``session/set_config_option``（
# codex-ACP，claude-智能体-ACP 0.44+）而不是 UNSTABLE ``models`` 能力 +
# ``session/set_model``（gemini-CLI，更旧的 codex/claude）。
#
_MODEL_CONFIG_OPTION_ID = "model"
_CODEX_REASONING_EFFORTS: Final[frozenset[str]] = frozenset(
    {"low", "medium", "high", "xhigh"}
)


def _codex_model_config_options(model: str) -> tuple[tuple[str, str], ...]:
    """将组合的 Canvas Codex 模型 ID 映射到 codex-ACP 配置选项。"""
    base_model, sep, effort = model.rpartition("/")
    if sep and base_model and effort in _CODEX_REASONING_EFFORTS:
        return (
            (_MODEL_CONFIG_OPTION_ID, base_model),
            ("reasoning_effort", effort),
        )
    return ((_MODEL_CONFIG_OPTION_ID, model),)


def _model_config_options(
    agent_name: str | None,
    model: str,
) -> tuple[tuple[str, str], ...]:
    provider = detect_acp_provider_by_agent_name(agent_name or "")
    if provider is not None and provider.key == "codex":
        return _codex_model_config_options(model)
    return ((_MODEL_CONFIG_OPTION_ID, model),)


async def _apply_acp_model(
    conn: ClientSideConnection,
    session_id: str,
    model: str,
    *,
    agent_name: str | None = None,
    via_config_option: bool,
) -> None:
    """通过会话机制将 ``model`` 应用于实时 ACP 会话
    advertised: ``set_config_option(configId="model")`` for configOptions-based
    服务器（codex-ACP、claude-智能体-ACP 0.44+），其他 ``set_session_model``。

    模型 ID 通常是服务器列出的裸预设 ID。 对于 Codex，调用者仍然可以传递组合的 Canvas
     id，例如 ``gpt-5.5/high``； codex-
    ACP 将推理工作公开为单独的配置选项，因此仅在配置选项机制上拆分它。

    智能体-客户端协议 0.12.1 已删除 ``ClientSideConnection.set_session_model``；
    :class:`_ACPClientConnection` 恢复它，以及没有它的连接
    无操作而不是提高 ``AttributeError``。
    """
    if via_config_option:
        for config_id, value in _model_config_options(agent_name, model):
            await conn.set_config_option(
                config_id=config_id, value=value, session_id=session_id
            )
    elif supports_legacy_model_switch(conn):
        await conn.set_session_model(model_id=model, session_id=session_id)  # type: ignore[attr-defined]


def _extract_session_models(
    response: Any,
    *,
    default_via_config_option: bool = False,
) -> tuple[str | None, list[ACPModelInfo] | None, bool]:
    """在一次扫描中从会话响应中提取模型状态。

    返回 ``(current_model_id, available_models, via_config_option)``，尽最大努力。
    ``available_models`` 被标准化为我们自己的稳定
    :class:`ACPModelInfo` 在此边界键入，因此下游不依赖任何内容
    出售的 ``acp.schema`` 形状。 读取会话的任何机制
    advertised: UNSTABLE ``models`` 功能，或 ``model``
    ``configOptions``选择（codex-ACP，claude-智能体-ACP 0.44+）。

    ``available_models`` 区分 **absent** 和 **empty** — 这对于恢复持久化很重要（当服
    务器未报告列表时，保留最后已知的列表；
     当服务器明确表示它有None时清除它）：

    - ``None`` — 响应中不存在这两种机制（较旧的智能体、选择退出或 ``load_session`` 不
    执行）。
    - ``[]`` — 服务器报告了一种机制，但没有提供（可用）模型。
    - ``[...]`` — 报告的模型，减去任何不可用的 ``model_id``。

    ``via_config_option`` 是选择机制：``True`` 表示 configOptions 选择，``False`` 表
    示 ``models`` 功
    能，并且
    ``default_via_config_option`` 当响应两者都不携带时（省略模型块的 ``load_session``
     的恢复路径默认值）。
    """
    state = extract_session_models(
        response, default_via_config_option=default_via_config_option
    )
    return state.current_model_id, state.available_models, state.via_config_option


# new_session() / load_session() 接受的 ACP MCP 服务器联合。
_ACPMcpServer = HttpMcpServer | SseMcpServer | McpServerStdio | AcpMcpServer


def _oauth_bearer_header(auth: MCPOAuthAuthCredential, name: str) -> dict[str, str]:
    """将存储的 OAuth2 访问令牌作为 ``Authorization`` 标头转发。

    的 ACP  子进程拥有自己的 MCP  传输层并且没有访问权限到 FastMCP  token 存储原生路
    径，以便  token  已持久化在连接的
    ``auth.state`` 这是唯一的凭据在这里可用。 没有这一点，服务器将被转发为裸机 URL 和
     ACP  智能体报告未登录
    ``codex mcp login ...``).

    丢失或过期的 token 仍然会转发存在的内容：来自服务器的 401 比未经身份验证的 URL 更
    可操作。 这两种情况都会被记录下来，因此掉落并不是无声的。
    """
    state = auth.state
    token = state.tokens.access_token if state is not None and state.tokens else None
    if token is None:
        logger.warning(
            "ACP MCP server %r has an OAuth2 connection with no stored access "
            "token; forwarding it unauthenticated",
            name,
        )
        return {}
    if (
        state is not None
        and state.token_expires_at is not None
        and state.token_expires_at <= time.time()
    ):
        logger.warning(
            "ACP MCP server %r has an expired OAuth2 access token; the ACP path "
            "cannot refresh it, forwarding it as-is",
            name,
        )
    return {"Authorization": f"Bearer {token.get_secret_value()}"}


def _remote_mcp_headers(server: MCPServer, name: str) -> list[HttpHeader]:
    """将远程 MCP 标头/身份验证转换为 ACP 的仅标头表示形式。

    标头兼容的身份验证（API 密钥/承载/基本/显式标头）直接转换。 OAuth2 不
    ``to_http_headers()`` 返回 ``None``，因为 to
    ken 通过 FastMCP's token 存储实现访问令牌。
    """
    headers = [
        HttpHeader(name=name, value=value.get_secret_value())
        for name, value in (server.headers or {}).items()
    ]

    auth = server.auth
    if isinstance(auth, MCPOAuthAuthCredential):
        auth_headers = _oauth_bearer_header(auth, name)
    else:
        auth_headers = auth.to_http_headers() if auth is not None else {}
    if auth_headers is None:
        logger.warning(
            "ACP MCP server %r uses unsupported remote MCP auth type %r; "
            "only header-compatible auth can be forwarded",
            name,
            type(auth).__name__,
        )
        return headers
    headers.extend(
        HttpHeader(name=name, value=value) for name, value in auth_headers.items()
    )
    return headers


def _mcp_config_to_acp_servers(
    mcp_config: dict[str, MCPServer],
    mcp_capabilities: Any,
) -> list[_ACPMcpServer]:
    """将 OpenHands MCP 服务器转换为 ACP MCP 服务器对象。

    将本机服务器映射转换为传递给的 ACP 协议对象
    ``new_session()`` / ``load_session()`` 因此 ACP 子进程连接到这些服务器本身。 与内
    置的智能体不同，这些*不是*被转换成在
    进程中的SDK MCP工具——服务器拥有ACP连接并通过自己的MCP方式暴露工具。

    具有 ``enabled=False`` 完全跳过 ACP  子进程拥有连接，因此唯一的方法是阻止一个被禁
    用的服务器进入。

    每个条目由传输层映射：

    - ``command`` 存在 → :class:`McpServerStdio` （始终转发； 该协议仅对能力标志后面
    的远程传输层进行门控）。
    - ``url`` 存在，传输层 ``sse`` → :class:`SseMcpServer`，仅在服务器通告
    ``mcp_capabilities.sse``
    时转发。
    - ``url`` 存在，任何其他/不存在传输层 → :class:`HttpMcpServer`（涵盖 ``http`` 和
    ``streamable-http``），仅在服务器通告 ``mcp_capabilities.http`` 时转发。

    远程服务器的传输层的 ACP 服务器没有广告的会以警告的方式丢弃，而不是失败初始化。一
    个配置错误的服务器不应该沉没整个对话。 ``env`` /
    ``headers`` 地图转换为协议的 ``[{name, value}]`` 列表表单。 兼容头的认证凭据，and
     the stored 访问令牌 OAuth2
    连接中的所有参数也都转换为头部。
    """
    caps = normalize_mcp_capabilities(mcp_capabilities)
    http_ok = caps.http
    sse_ok = caps.sse
    result: list[_ACPMcpServer] = []
    for name, server in mcp_config.items():
        if not server.enabled:
            continue
        if server.command:
            env = [
                EnvVariable(name=name, value=value.get_secret_value())
                for name, value in (server.env or {}).items()
            ]
            result.append(
                McpServerStdio(
                    name=name,
                    command=server.command,
                    args=list(server.args or []),
                    env=env,
                )
            )
        elif server.url:
            headers = _remote_mcp_headers(server, name)
            is_sse = server.effective_transport == "sse"
            if not (sse_ok if is_sse else http_ok):
                logger.warning(
                    "ACP server does not advertise %s MCP support; "
                    "dropping MCP server %r (%s)",
                    "SSE" if is_sse else "HTTP",
                    name,
                    server.url,
                )
                continue
            # 显式构造每个传输层，以便 ``type`` 文字保持狭窄（联合的两个分支需要不同的
            # ``Literal``）。
            #
            if is_sse:
                result.append(
                    SseMcpServer(type="sse", name=name, url=server.url, headers=headers)
                )
            else:
                result.append(
                    HttpMcpServer(
                        type="http", name=name, url=server.url, headers=headers
                    )
                )
        else:
            logger.warning(
                "Skipping ACP MCP server %r: needs a 'command' (stdio) or "
                "'url' (http/sse)",
                name,
            )
    return result


async def _maybe_set_session_model(
    conn: ClientSideConnection,
    agent_name: str,
    session_id: str,
    acp_model: str | None,
    *,
    via_config_option: bool,
) -> bool:
    """会话创建后立即应用 *initial* 会话模型。

    仅会话创建路径，门控
    ``ACPProviderInfo.supports_set_session_model``. 该模型通过会话宣传的机制应用（
    ``via_config_option``）：
    ``set_config_option(configId="model")`` 用于基于 configOptions 的服务器（codex-
    ACP、claude-智
    能体-ACP 0.44+），其他为 ``set_session_model``。 的
    ``_meta`` model 载荷被锁定的忽略 CLIs因此，这个协议调用实际上应用了模型（#3654）
    。 对于任何提供者，都容忍拒绝 —— 专家模型列表是一个预
    会建议，而不是访问检查（服务器的模型菜单是动态/账户相关的，因此会保持服务器默认设
    置，而不是失败启动）。 运行时开关通过：meth：
    `ACPAgent.set_acp_model`.

    仅当模型设置调用成功（覆盖到达服务器）时才返回 ``True``； ``False`` 当没有什么可
    申请的或呼叫被拒绝时，因此呼叫者知道实时会话是否运行
    ``acp_model``。
    """
    if not acp_model:
        return False
    provider = detect_acp_provider_by_agent_name(agent_name)
    # 已知提供商的门控为 supports_set_session_model； 未知/自定义服务器总是尝试（尽力而
    # 为）。
    #
    if provider is not None and not provider.supports_set_session_model:
        return False
    # 拒绝是被容忍的，以确保会话创建不会中断：精选模型列表只是一个建议，而不是访问检查——
    # 服务器的模型菜单是动态/账户相关的（claude-）智能体-ACP 验证 set_config_option 在时
    # ，会拒绝一个缺席的 ，因此，一个在的模型将降级为服务器默认值，而不是失败。
    #
    try:
        await _apply_acp_model(
            conn,
            session_id,
            acp_model,
            agent_name=agent_name,
            via_config_option=via_config_option,
        )
        return True
    except ACPRequestError as e:
        logger.warning(
            "Could not set model %r on ACP server %s (%s); "
            "the session will use the server default",
            acp_model,
            agent_name,
            e,
        )
        return False


async def _reapply_session_model_on_resume(
    conn: ClientSideConnection,
    agent_name: str,
    session_id: str,
    acp_model: str | None,
    *,
    via_config_option: bool,
) -> bool:
    """将已持久化模型重新应用到 * 已恢复的 * 会话。

    ``load_session()`` 不携带模型 ``_meta``，因此在运行时切换（或使用任何已持久化
    ``acp_model``）之后恢复的会话将在 ACP
    服务器的默认值上运行。
    这通过该会话恢复机制应用模型
    (``via_config_option``: ``set_config_option`` for codex-acp/claude-智能体
    -ACP 0.44+，否则 ``set_session_model``)
    ，使得实时会话与已序列化 ``acp_model``匹配。 调用者得出
    ``via_config_option`` 来自 ``load_session`` 响应，当该响应省略模型块时，回退到已
    持久化机制提示。

    对运行时切换支持进行门控（仅跳过不支持的已知提供程序）； 拒绝呼叫的服务器是可以容
    忍的（记录）——就像
    ``load_session`` 回退方案 — 因此恢复不会中断，会话将保持服务器默认状态，直到下一
    次切换。

    仅当发出并接受模型设置调用时才返回 ``True``，因此调用者知道恢复的实时会话实际上正
    在运行 ``acp_model``。
    ``False`` 当没有什么可以重新申请时，提供者不支持切换，或者服务器拒绝了调用（吞掉
    ）。
    """
    if not acp_model:
        return False
    provider = detect_acp_provider_by_agent_name(agent_name)
    if provider is not None and not provider.supports_runtime_model_switch:
        return False
    try:
        await _apply_acp_model(
            conn,
            session_id,
            acp_model,
            agent_name=agent_name,
            via_config_option=via_config_option,
        )
        return True
    except ACPRequestError as e:
        logger.warning(
            "Could not reapply model %r on resumed session %s (%s); the live "
            "session may run on the server default until the next switch",
            acp_model,
            _fingerprint_session_id(session_id),
            e,
        )
        return False


def _extract_token_usage(
    response: Any,
) -> tuple[int, int, int, int, int]:
    """从 ACP PromptResponse 中提取词元用量。

    返回 (input_tokens, output_tokens, cache_read, cache_write, 推理)。

    检查两个位置：
    - claude-智能体-ACP，codex-ACP：``response.usage``（标准 ACP 字段）
    - gemini-CLI: ``response._meta.quota.token_count``（非标准）
    """
    if response is not None and response.usage is not None:
        u = response.usage
        return (
            u.input_tokens,
            u.output_tokens,
            u.cached_read_tokens or 0,
            u.cached_write_tokens or 0,
            u.thought_tokens or 0,
        )
    if response is not None and response.field_meta is not None:
        quota = response.field_meta.get("quota") or {}
        tc = quota.get("token_count") or {}
        return (tc.get("input_tokens", 0), tc.get("output_tokens", 0), 0, 0, 0)
    return (0, 0, 0, 0, 0)


def _estimate_cost_from_tokens(
    model: str, input_tokens: int, output_tokens: int
) -> float:
    """使用 LiteLLM 的定价数据库根据 token 计数估算成本。

    如果模型的定价不可用，则返回 0.0。
    """
    try:
        import litellm

        cost_map = litellm.model_cost
        info = cost_map.get(model, {})
        input_cost = info.get("input_cost_per_token", 0) or 0
        output_cost = info.get("output_cost_per_token", 0) or 0
        return input_tokens * input_cost + output_tokens * output_cost
    except Exception:
        return 0.0


def _image_url_to_acp_block(url: str) -> ImageContentBlock | None:
    """将图像 URL（数据 URI 或纯文本 URL）转换为 ACP ImageContentBlock。

    URIs (``data:<mime>;base64,<data>``) 数据直接解析。 URLs 通过通用类型 MIME 的
    ``uri`` 字段传递。 返回
    ``None``，如果 URL 无法转换。
    """
    if url.startswith("data:"):
        # 解析数据URI：data:<mime>;base64,<data>
        try:
            header, data = url.split(",", 1)
            mime_type = header.split(":", 1)[1].split(";", 1)[0]
            return image_block(data=data, mime_type=mime_type)
        except (ValueError, IndexError):
            logger.warning("Failed to parse data URI for ACP image block")
            return None
    # Plain URL — 使用通用 MIME 类型作为 uri 传递； ACP 服务器可以获取并检测实际类型。
    #
    return image_block(data="", mime_type="image/png", uri=url)


def _mask_json_value(value: Any, mask: Callable[[str], str]) -> Any:
    """递归地将 *mask* 应用于类似 JSON 值的每个字符串叶子。

    ACP 工具调用 ``raw_input`` / ``raw_output`` / ``content`` 块是任意的 JSON（裸字符
    串、参数字典、内容块列表）。
     ``SecretRegistry.mask_secrets_in_output`` 将字符串映射到字符串，因此遍历结构并掩
     盖每个叶子字符串。 非字符串叶子（整数、
    布尔值、``None``）不变地通过。 它会在首次使用时解析未缓存的源，因此这不是免费的。
    """
    if isinstance(value, str):
        return mask(value)
    if isinstance(value, dict):
        return {k: _mask_json_value(v, mask) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_json_value(v, mask) for v in value]
    return value


def _serialize_tool_content(content: list[Any] | None) -> list[dict[str, Any]] | None:
    """序列化 ACP 工具调用内容块到普通字典以进行 JSON 存储。"""
    if not content:
        return None
    result = []
    for content_block in content:
        block_dict = (
            content_block.model_dump(mode="json")
            if is_model_dumpable(content_block)
            else content_block
        )
        if (
            isinstance(block_dict, dict)
            and block_dict.get("type") == "text"
            and isinstance(block_dict.get("text"), str)
        ):
            block_dict = {
                **block_dict,
                "text": maybe_truncate(
                    block_dict["text"], truncate_after=MAX_ACP_CONTENT_CHARS
                ),
            }
        result.append(block_dict)
    return result


class _NewSessionResponse(NewSessionResponse):
    models: ACPLegacySessionModels | None = None

    @field_validator("models", mode="before")
    @classmethod
    def _drop_malformed_models(cls, value: Any) -> Any:
        try:
            return ACPLegacySessionModels.model_validate(value)
        except ValidationError:
            return None


# ``@final`` 仅限打字； 除了这两个调用之外，什么都没有被覆盖。
class _ACPClientConnection(ClientSideConnection):  # pyright: ignore[reportGeneralTypeIssues]
    """恢复 UNSTABLE 模型调用 ACP 0.12 丢弃； 双子座-CLI需要它们。"""

    async def new_session(  # type: ignore[override]
        self,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        return await request_model(
            self._conn,
            AGENT_METHODS["session_new"],
            NewSessionRequest(
                cwd=cwd,
                additional_directories=additional_directories,
                mcp_servers=mcp_servers or [],
                field_meta=kwargs or None,
            ),
            _NewSessionResponse,
        )

    async def set_session_model(self, *, model_id: str, session_id: str) -> None:
        await self._conn.send_request(
            "session/set_model", {"sessionId": session_id, "modelId": model_id}
        )


async def _filter_jsonrpc_lines(source: Any, dest: Any) -> None:
    """从 *source* 读取行并仅将 JSON-RPC 行转发到 *dest*。

    一些 ACP 服务器 (e.g. ``claude-code-acp`` v0.1.x) 将类似于 ``[ACP] ...`` 的日志消
    息与 JSON-RPC 流量
    一起发送到标准输出。 此协程去除了那些非协议行，因此 JSON-RPC 连接不会混淆。
    """
    try:
        while True:
            line = await source.readline()
            if not line:
                dest.feed_eof()
                break
            # JSON-RPC 消息是包含“jsonrpc”的单行 JSON 对象。 从同样以“{”开头的调试日志中
            # 过滤掉多行漂亮打印的 JSON。
            #
            stripped = line.lstrip()
            if stripped.startswith(b"{") and b'"jsonrpc"' in line:
                dest.feed_data(line)
            else:
                logger.info(
                    "ACP stdout (non-JSON): %s",
                    maybe_truncate(
                        redact_text_secrets(line.decode(errors="replace").rstrip()),
                        truncate_after=_ACP_SUBPROCESS_LOG_LINE_CHARS,
                    ),
                )
    except Exception:
        logger.debug("_filter_jsonrpc_lines stopped", exc_info=True)
        dest.feed_eof()


async def _log_acp_subprocess_stderr(source: Any) -> None:
    try:
        while line := await source.readline():
            logger.info(
                "ACP stderr: %s",
                maybe_truncate(
                    redact_text_secrets(line.decode(errors="replace").rstrip()),
                    truncate_after=_ACP_SUBPROCESS_LOG_LINE_CHARS,
                ),
            )
    except Exception:
        logger.debug("_log_acp_subprocess_stderr stopped", exc_info=True)


# 将通用 ``-32603 Internal error`` 标记为真正的凭据失败的子字符串。 ACP 服务器将上游 401
# /403 崩溃为 -32603 而不是 -32000（codex-ACP 吞噬其线程-启动错误； Claude SDK 有一个兜
# 底的，将所有东西都重新包装成内部的，所以代码本身并不是一个可靠的认证信号——除了消息和数
# 据，还需要进行扫描。 作为整个单词匹配，因此“4031ms”或“model-id-401b”不会触发。
#
_ACP_AUTH_HTTP_CODES_RE = re.compile(r"\b(401|403)\b")

_ACP_AUTH_ERROR_MARKERS: tuple[str, ...] = (
    "unauthorized",
    "invalid api key",
    "invalid_api_key",
    "invalid x-api-key",
    "expired",
    "please run /login",
    "authentication required",
    "oauth token",
    "credential",
)


def _stringify_acp_error_data(data: Any) -> str:
    """将 ACP ``RequestError.data`` 载荷渲染为紧凑字符串。

    服务器将真正的原因放在这里：codex 发送 ``{"message", "codex_error_info"}`` 或裸字
    符串； 克劳德 SDK 包罗万象发送
    ``{"details": ...}``。 将人类可读的字段拉到前面； 否则回退到紧凑的 JSON 转储。
    """
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("message", "details", "detail", "error"):
            val = data.get(key)
            if isinstance(val, str) and val:
                extra = data.get("codex_error_info")
                return f"{val} ({extra})" if extra else val
    try:
        return json.dumps(data, default=str)
    except (TypeError, ValueError):
        return str(data)


def _acp_error_text(exc: BaseException) -> str:
    """小写消息 + 用于子字符串分类的数据文本。"""
    info = normalize_acp_error(exc)
    if isinstance(exc, ACPRequestError):
        data_str = _stringify_acp_error_data(info.data)
        return f"{info.message} {data_str}".lower()
    return info.message.lower()


def _acp_error_indicates_auth(exc: BaseException) -> bool:
    """True 当故障是（或确实是）凭据问题时。

    ``-32000`` 是显式授权码； a ``-32603`` 其消息/数据带有 auth 标记，是上游 401/403
    ，服务器崩溃为一般内部错误。 无论哪种方式，
    客户都应该重新提供身份验证。
    """
    if isinstance(exc, ACPRequestError):
        info = normalize_acp_error(exc)
        if info.code == -32000:
            return True
    text = _acp_error_text(exc)
    return any(marker in text for marker in _ACP_AUTH_ERROR_MARKERS) or bool(
        _ACP_AUTH_HTTP_CODES_RE.search(text)
    )


def _acp_error_detail(
    exc: BaseException, secret_registry: SecretRegistry | None = None
) -> str:
    """为 ACP 失败编写一个人类可读的、无机密的 ``detail``。

    ``acp.exceptions.RequestError.__str__`` 仅返回其 ``message`` — 因此，当调用者使用
     ``str(exc)``
    时，JSON-RPC ``code`` 和 ``data`` 载荷（服务器存储真正原因：上游 401 主体、未找到
    模型的字符串、
    ``codex_error_info``）会丢失，这就是为什么 ``-32603`` 失败作为纯粹的“内部错误”到
    达用户。 这三个都保留了。 ``data`` 可以
    回显基础 URL 或者认证头，因此结果是已脱敏（模式通过）并被掩码（精确跟踪机密的值）
    在离开之前，被限制为 500 字符事件限制。
    """
    if isinstance(exc, ACPRequestError):
        info = normalize_acp_error(exc)
        code = info.code
        message = info.message
        data_str = _stringify_acp_error_data(info.data)
        detail = f"[{code}] {message}" if code is not None else message
        if data_str and data_str != message:
            detail = f"{detail}: {data_str}"
    else:
        detail = str(exc)
    detail = redact_text_secrets(detail)
    if secret_registry is not None:
        detail = secret_registry.mask_secrets_in_output(detail)
    return detail[:500]


def _classify_acp_init_error(exc: BaseException) -> str:
    """将冷启动故障映射到结构化 ``ConversationErrorEvent`` 代码。

    ACP 的 spawn + auth + ``session/new`` 在：meth:`ACPAgent.init_state` 中运行，其中
    ``LocalConversation.run()``/``arun()`` 在 * 的 try 块之前调用 *（通过
    ``_ensure_agent_ready()``）。 这些冷启动故障在云上比在本地更常见，因此绕过了运行
    循环的错误发射，因此
    ``init_state`` 表面它们本身。 该代码告诉客户端 * 发生了哪个 * 故障，以便他们可以
    做出反应 (e.g. 提示词重新验证与重新验证报告丢失的二进制
    文件）：

    - ``ACPAuthRequired``：凭据失败 — 显式 ``-32000`` 身份验证代码，或 ``-32603``，其
    消息/数据显示上游 401/403（
    请参阅
      :func:`_acp_error_indicates_auth`)。 最可操作的云失败。
    - ``ACPStartupTimeout``：启动未在时间内完成
      ``acp_startup_timeout`` — e.g. 服务器挂在 ``authenticate()`` 上而没有返回错误（
      请参阅：meth：
      `ACPAgent._start_acp_server`）。
    - ``ACPSpawnError``：无法启动子进程 — CLI 二进制文件丢失或不可执行（
    ``FileNotFoundError`` /
    ``PermissionError`` 来自
      ``create_subprocess_exec``).
    - ``ACPInitError``：协议握手或会话创建期间的任何其他内容（传输层丢失、意外协议错
    误、服务器出现的 cwd 不匹配）。
    """
    if isinstance(exc, ACPFileCredentialSyncError):
        return "ACPInitError"
    if isinstance(exc, ACPFileCredentialNeedsReauthError):
        return "ACPAuthRequired"
    if _acp_error_indicates_auth(exc):
        return "ACPAuthRequired"
    if isinstance(exc, TimeoutError):
        return "ACPStartupTimeout"
    if isinstance(exc, (FileNotFoundError, PermissionError)):
        return "ACPSpawnError"
    return "ACPInitError"


def _classify_acp_turn_error(exc: BaseException) -> str:
    """将提示词匝故障映射到结构化 ``ConversationErrorEvent`` 代码。

    `_classify_acp_init_error`函数的转环对应体：凭据失败映射到``ACPAuthRequired``（因
    此客户端可以提供重新认证），其余情况为
    通用``ACPPromptError``。
    """
    if isinstance(exc, ACPFileCredentialSyncError):
        return "ACPPromptError"
    if isinstance(exc, ACPFileCredentialNeedsReauthError):
        return "ACPAuthRequired"
    text = _acp_error_text(exc)
    if "usage policy" in text or "content policy" in text:
        return "UsagePolicyRefusal"
    if _acp_error_indicates_auth(exc):
        return "ACPAuthRequired"
    return "ACPPromptError"


class _OpenHandsACPBridge:
    """OpenHands 和 ACP 之间的桥梁，用于累积会话更新。

    实现 ``agent_client_protocol`` 中的 ``Client`` 协议。

    并发模型 — ``on_event`` / ``on_token`` / ``on_activity`` 从 ``session_update`` 同
    步触发，运行在
    ``AsyncExecutor``门户网站线程。 在单回合内保持回调已序列化的保证依赖于两个因素的
    组合，而不是单独的 GIL：

    1. ``LocalConversation.run()`` 按住可重入 ``ConversationState`` 锁 (a
    ``FIFOLock``) 的同时调
    用 ``agent.step(...)`` — 请参阅
       ``local_conversation.py`` 其中 ``self.agent.step(...)`` 位于内部
       ``with self._state:``. 调用者线程在 ``step()`` 的整个持续时间内拥有该锁，因此
       没有其他线程可以附加到
       ``state.events`` 回合期间。
    2. ``portal.call(_prompt)`` 阻塞调用者线程，直到 ``prompt()`` 返回。 实时
    ``on_event`` 呼叫发生在门户线程上
    ，而呼叫者线程停在 ``portal.call()`` 内，仍然拥有状态锁； ``prompt()`` 返回后，最
    终的 ``MessageEvent`` /
    ``FinishAction`` 在调用者线程上运行。 两个阶段的时间不会重叠。

    调用者的状态-锁所有权排除了*其他* 线程（钩子工人、远程对话推送层、其他 spawned的
    可视化器）与其他阶段进行竞争。 两个阶段之间的顺序是保持单个消费者的跨回
    调状态 (e.g. 挂钩处理器（读然后写）一致。

    两个不变量调用者依赖：

    * ``on_event`` handlers 必须不获取会话状态锁 (``with conversation.state:``). 桥上
    放火线程在调用者线程位于内
    部 ``portal.call()`` 拥有那个锁，and ``FIFOLock`` 是线程-bound - a 锁-在门户上获
    取线程 would 死锁而不是重新输
    入。
    * 工具调用→最终消息排序取决于ACP服务器在提示词响应返回之前*轮*耗尽每个
    ``session_update``通知。 已验证
      ``claude-agent-acp@0.29.0``; 交错尾随的服务器
      ``ToolCallProgress`` 在提示词响应之后，消费者会看到的顺序会被颠倒，且 "dedupe-
      by-id+"last-seen wins" 会将消
      息发布事件视为权威。
    """

    def __init__(self) -> None:
        self.accumulated_text: list[str] = []
        self.accumulated_thoughts: list[str] = []
        self.accumulated_tool_calls: list[dict[str, Any]] = []
        # 发出 LLM/TOOL 跨度 ACP 圈，否则永远不会产生。
        self.trace = ACPTurnTrace(acp_server=None, model_id=None)
        self.on_token: Any = None  # ConversationTokenCallbackType | None
        # 直播事件汇流点 —— 从 session_update 接收到 ACP 工具调用更新时触发，因此事件流
        # 反映的是真实的子进程进展，而不是单个结束回合的爆发。 由 ACPAgent.step() 设置一
        # 次 prompt() 往返的持续时间。
        #
        self.on_event: ConversationCallbackType | None = None
        # 活动心跳 — 在 session_update 期间调用（节流）以表明 ACP 子进程仍在积极工作。
        # 由 ACPAgent.step() 设置以保持智能体-服务器的空闲计时器处于活动状态。
        #
        self.on_activity: Any = None  # [[]，None] | None
        # 机密遮罩 —— 每回合由 ACPAgent 设置
        # ``state.secret_registry.mask_secrets_in_output``. 应用于流式文本块和工具调用
        # raw_input/raw_output/内容，然后它们到达 ``on_token`` / ``on_event``，因此回显
        # 注入的凭据的子进程永远不会以明文形式降落在（已持久化，网络中继）事件流中。
        # ``None`` ⇒ 无操作（桥接器独立使用）。
        #
        self.mask: Callable[[str], str] | None = None
        self.before_mask: Callable[[], None] | None = None
        self._masking_error: CredentialBindingError | None = None
        self._last_activity_signal: float = float("-inf")
        # 最近的单调时间戳``session_update``。 与节流 ``_last_activity_signal`` 不同，在
        #  * 每次 * 更新时更新，因此提示词空闲超时看门狗可以看到真正的进展。 每回合武装
        # 通过
        # ``arm_activity_clock``.
        self._last_activity_monotonic: float = float("-inf")
        # 来自 UsageUpdate 的遥测状态（跨回合持续存在）
        self._last_cost: float = 0.0  # 最后看到的累计成本
        self._last_cost_by_session: dict[str, float] = {}
        self._context_window: int = 0  # 最后看到上下文窗口
        self._context_window_by_session: dict[str, int] = {}
        # UsageUpdate 通知的每回合同步。
        self._turn_usage_updates: dict[str, Any] = {}
        self._usage_received: dict[str, asyncio.Event] = {}
        # ask_agent() 的分叉会话状态 — 由 _fork_lock 保护，以防止并发 ask_agent() 调用发
        # 生冲突。
        #
        self._fork_lock = threading.Lock()
        self._fork_session_id: str | None = None
        self._fork_accumulated_text: list[str] = []

    def reset(self) -> None:
        self.accumulated_text.clear()
        self.accumulated_thoughts.clear()
        self.accumulated_tool_calls.clear()
        self.on_token = None
        self.on_event = None
        self.on_activity = None
        self._turn_usage_updates.clear()
        self._usage_received.clear()
        self._masking_error = None
        # 注：遥测状态(_last_cost,_context_window,_last_activity_signal,
        # 等）被故意清除不——它会在回合中累积。

    def arm_activity_clock(self) -> None:
        """将“现在”标记为空闲超时看门狗的最后一个活动。

        在每个提示词（和每个重试）开始时调用，因此空闲窗口是从发送提示词的那一刻开始
        测量的，而不是
        from a stale value — a server that legitimately takes a while before
        它的第一个 ``session_update`` 一定不能被过早地杀死。
        """
        self._last_activity_monotonic = time.monotonic()

    def seconds_since_last_activity(self) -> float:
        """自上次 ``session_update``（或 ``arm_activity_clock``）以来的秒数。

        驱动提示词 idle-超时任何流的 token, 想到，工具调用 start/progress 或者使用更
        新从  ACP 服务器重置时钟，因此是逐步前进的智
        能体无论一个真正沉默（静默）的服务器是否真的静默，它都从未错过截止日期。
        """
        return time.monotonic() - self._last_activity_monotonic

    def prepare_usage_sync(self, session_id: str) -> asyncio.Event:
        """为会话准备每回合 UsageUpdate 同步。"""
        event = asyncio.Event()
        self._usage_received[session_id] = event
        self._turn_usage_updates.pop(session_id, None)
        return event

    def get_turn_usage_update(self, session_id: str) -> Any:
        """返回当前回合观察到的最新 UsageUpdate。"""
        return self._turn_usage_updates.get(session_id)

    def pop_turn_usage_update(self, session_id: str) -> Any:
        """消耗会话的每回合 UsageUpdate 同步状态。"""
        self._usage_received.pop(session_id, None)
        return self._turn_usage_updates.pop(session_id, None)

    def _mask_value(self, value: Any) -> Any:
        """掩码在 *value*（字符串或类似 JSON）中注入机密，如果未设置则无操作。

        Defensive: 掩码失败时，返回原始值不变，并且
        DEBUG 的日志 —— 这可能会暂时泄露凭据，但防止崩溃，符合常规终端工具的掩码合同
        。 (掩码会内部吞咽机密分辨率错误，因此在实践中它不应该出现。)
        """
        if self.mask is None:
            return value
        try:
            if self.before_mask is not None:
                self.before_mask()
            return _mask_json_value(value, self.mask)
        except CredentialBindingError as exc:
            if self._masking_error is None:
                self._masking_error = exc
            raise
        except Exception:
            logger.debug("secret masking failed", exc_info=True)
            return value

    def _mask_tool_call_entry(self, entry: dict[str, Any]) -> None:
        """屏蔽工具调用条目的标题/raw_input/raw_output/内容。

        在接收数据时（``session_update``）就地处理，使累加器自身从不持有明文机密，同
        时确保所有下游输出方（
        ``_emit_tool_call_event`` 以及其中的替代路径
        ``_cancel_inflight_tool_calls``) 免费携带屏蔽值。
        ``title`` 通常是一个良性的服务器设置标签，但行为不当的 ACP 服务器可能会在那里
        回显凭据 (e.g.
        ``Running: curl -H 'Authorization: Bearer <token>'``)，所以它也被屏蔽了。
        """
        for key in ("title", "raw_input", "raw_output", "content"):
            if entry.get(key) is not None:
                entry[key] = self._mask_value(entry[key])

    def _raise_masking_error(self) -> None:
        if self._masking_error is not None:
            raise self._masking_error

    # -- 客户端协议方法 ------------------------------------------------------

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **kwargs: Any,  # noqa: ARG002
    ) -> None:
        logger.debug("ACP session_update: type=%s", type(update).__name__)

        # 任何更新 — token、想法、工具调用开始/进度、用法 — 都是
        # 进度：重置空闲时钟，以便提示词不活动看门狗
        # 保持稳定工作的智能体存活（不受限制，与 ``_maybe_signal_activity`` 中的心跳不同
        # ）。
        #
        self._last_activity_monotonic = time.monotonic()

        # 将分叉会话更新路由到分叉累加器。 ask_agent() 会将这段文本返回给调用者（用户界
        # 面/网络汇接点），因此像主要路径一样对其进行遮蔽 —— 一个机密在 fork 会话中，
        # echo 应该不泄露为明文。
        #
        if self._fork_session_id is not None and session_id == self._fork_session_id:
            if isinstance(update, AgentMessageChunk):
                if isinstance(update.content, TextContentBlock):
                    self._fork_accumulated_text.append(
                        self._mask_value(update.content.text)
                    )
            return

        if isinstance(update, AgentMessageChunk):
            if isinstance(update.content, TextContentBlock):
                # 屏蔽一次，然后将屏蔽的块用于已持久化累积和实时 ``on_token`` 中继。 分
                # 成两个块的机密会从这里滑过（每个块单独不匹配）； 连接的响应在
                # ``_finalize_successful_turn`` 中的持久化边界处被重新屏蔽以捕获该响应。
                #
                text = self._mask_value(update.content.text)
                self.accumulated_text.append(text)
                if self.on_token is not None:
                    try:
                        self.on_token(text)
                    except Exception:
                        logger.debug("on_token callback failed", exc_info=True)
            self._maybe_signal_activity()
        elif isinstance(update, AgentThoughtChunk):
            if isinstance(update.content, TextContentBlock):
                self.accumulated_thoughts.append(self._mask_value(update.content.text))
        elif isinstance(update, UsageUpdate):
            # 将 step()/ask_agent() 的更新存储在一处进行处理。
            self._context_window = update.size
            self._context_window_by_session[session_id] = update.size
            self._turn_usage_updates[session_id] = update
            event = self._usage_received.get(session_id)
            if event is not None:
                event.set()
        elif isinstance(update, ToolCallStart):
            entry = {
                "tool_call_id": update.tool_call_id,
                "title": update.title,
                "tool_kind": update.kind,
                "status": update.status,
                "raw_input": update.raw_input,
                "raw_output": update.raw_output,
                "content": _serialize_tool_content(update.content),
            }
            self._mask_tool_call_entry(entry)
            self.accumulated_tool_calls.append(entry)
            self.trace.tool_started(entry)
            if entry.get("status") in _TERMINAL_TOOL_CALL_STATUSES:
                # 此调用不会再有任何后续转换到达，因此现在关闭其跨度； 将其保持打开状态
                # 将向其计费REST。
                #
                self.trace.tool_finished(entry)
            logger.debug("ACP tool call start: %s", update.tool_call_id)
            # 发出一个早期的“开始”事件——动作的半部分->观测结果对中的动作->观测结果。 下
            # 面匹配的终端转换保护会抑制任何冗余的重新发射。）
            #
            self._emit_tool_call_event(entry)
            self._maybe_signal_activity()
        elif isinstance(update, ToolCallProgress):
            # 查找现有的工具调用条目并合并更新。 跟踪此帧之前 * * 看到的状态，以便我们可
            # 以检测到最终状态的单个转换。
            #
            target: dict[str, Any] | None = None
            prev_status: str | None = None
            for index, tc in enumerate(self.accumulated_tool_calls):
                if tc["tool_call_id"] == update.tool_call_id:
                    prev_status = tc.get("status")
                    updated = dict(tc)
                    if update.title is not None:
                        updated["title"] = update.title
                    if update.kind is not None:
                        updated["tool_kind"] = update.kind
                    if update.status is not None:
                        updated["status"] = update.status
                    if update.raw_input is not None:
                        updated["raw_input"] = update.raw_input
                    if update.raw_output is not None:
                        updated["raw_output"] = update.raw_output
                    if update.content is not None:
                        updated["content"] = _serialize_tool_content(update.content)
                    self._mask_tool_call_entry(updated)
                    self.accumulated_tool_calls[index] = updated
                    target = updated
                    break
            logger.debug("ACP tool call progress: %s", update.tool_call_id)
            # 持久化每个工具调用恰好有一个终止事件。 每个中间进度帧都携带 * 完整累积 *
            # 输出； 每帧发出一个是 O(n^2) 存储 + WebSocket 中继（此方法修复的错误）。
            # 我们默默地将它们累积到``target``，只在状态变为终端状态时才发出，因此终端事
            # 件仍然携带完整的最终输出。 这是动作->观测结果对的观测结果一半。
            #
            became_terminal = (
                target is not None
                and target.get("status") in _TERMINAL_TOOL_CALL_STATUSES
                and prev_status not in _TERMINAL_TOOL_CALL_STATUSES
            )
            if target is not None and became_terminal:
                self.trace.tool_finished(target)
                self._emit_tool_call_event(target)
            self._maybe_signal_activity()
        else:
            logger.debug("ACP session update: %s", type(update).__name__)

    def _emit_tool_call_event(self, tc: dict[str, Any]) -> None:
        """ACPToolCallEvent 反映 ``tc`` 当前状态。

        从每个 ``ToolCallStart`` 上的 ``session_update`` 调用 /
        ``ToolCallProgress`` 因此下游消费者会看到工具卡随着子进程的运行而出现并更新。
         同一个 ``tool_call_id`` 在每次发射中都
        被重复使用——消费者应该通过 ID 去重，并将最后看到的事件视为权威。
        """
        if self.on_event is None:
            return
        try:
            raw_output = tc.get("raw_output")
            if isinstance(raw_output, str):
                raw_output = maybe_truncate(
                    raw_output, truncate_after=MAX_ACP_CONTENT_CHARS
                )
            event = ACPToolCallEvent(
                tool_call_id=tc["tool_call_id"],
                title=tc["title"],
                status=tc.get("status"),
                tool_kind=tc.get("tool_kind"),
                raw_input=tc.get("raw_input"),
                raw_output=raw_output,
                content=tc.get("content"),
                is_error=tc.get("status") == "failed",
            )
            self.on_event(event)
        except Exception:
            logger.debug("on_event callback failed", exc_info=True)

    def _maybe_signal_activity(self) -> None:
        """向智能体-服务器的空闲跟踪器发出活动信号（受到限制）。

        在 conn.prompt() 期间，ACP 工具调用在子进程内部运行，并且永远不会到达智能体服
        务器的 HTTP 端点。 如果没有此心跳，服务器的
        idle_time 会无限增长，并且运行时 API 会杀死 pod（默认空闲阈值约 20 分钟）。

        限制为最多每 ACTIVITY_SIGNAL_INTERVAL 秒一次，以避免在繁忙的 ACP 服务器上产生
        过多的开销。
        """
        if self.on_activity is None:
            return
        now = time.monotonic()
        if now - self._last_activity_signal >= ACTIVITY_SIGNAL_INTERVAL:
            self._last_activity_signal = now
            try:
                self.on_activity()
            except Exception:
                logger.debug("on_activity callback failed", exc_info=True)

    async def request_permission(
        self,
        session_id: str,  # noqa: ARG002
        tool_call: ToolCallUpdate,
        options: list[PermissionOption],
        **kwargs: Any,  # noqa: ARG002
    ) -> RequestPermissionResponse:
        """自动批准来自 ACP 服务器的所有权限请求。"""
        # 选择第一个选项（通常“允许一次”）
        option_id = options[0].option_id if options else "allow_once"
        logger.info(
            "ACP auto-approving permission: %s (option: %s)",
            tool_call,
            option_id,
        )
        return RequestPermissionResponse(
            outcome=AllowedOutcome(outcome="selected", option_id=option_id),
        )

    async def create_elicitation(
        self,
        message: str,  # noqa: ARG002
        mode: ElicitationMode,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> CreateElicitationResponse:
        """拒绝启发请求； 无头桥没有用户可问。

        添加到智能体-client-protocol 0.12.x 中的 ``Client`` 协议。 固定的 ACP 提供者
        的 None 在无头转向期间引发，因此
        这是防御性默认设置，而不是执行的代码路径。
        """
        return DeclineElicitationResponse(action="decline")

    async def complete_elicitation(
        self,
        elicitation_id: str,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> None:
        """桥接的引出的无操作完成总是拒绝。"""
        return None

    # fs/终端方法 — raise NotImplementedError; ACP 服务器自己处理
    async def write_text_file(
        self, session_id: str, path: str, content: str, **kwargs: Any
    ) -> WriteTextFileResponse | None:
        raise NotImplementedError("ACP server handles file operations")

    async def read_text_file(
        self,
        session_id: str,
        path: str,
        line: int | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> ReadTextFileResponse:
        raise NotImplementedError("ACP server handles file operations")

    async def create_terminal(
        self,
        session_id: str,
        command: str,
        args: list[str] | None = None,
        env: list[EnvVariable] | None = None,
        cwd: str | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> CreateTerminalResponse:
        raise NotImplementedError("ACP server handles terminal operations")

    async def terminal_output(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> TerminalOutputResponse:
        raise NotImplementedError("ACP server handles terminal operations")

    async def release_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> ReleaseTerminalResponse | None:
        raise NotImplementedError("ACP server handles terminal operations")

    async def wait_for_terminal_exit(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> WaitForTerminalExitResponse:
        raise NotImplementedError("ACP server handles terminal operations")

    async def kill_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> KillTerminalResponse | None:
        raise NotImplementedError("ACP server handles terminal operations")

    async def ext_method(
        self,
        method: str,  # noqa: ARG002
        params: dict[str, Any],  # noqa: ARG002
    ) -> dict[str, Any]:
        return {}

    async def ext_notification(
        self,
        method: str,  # noqa: ARG002
        params: dict[str, Any],  # noqa: ARG002
    ) -> None:
        pass

    def on_connect(self, conn: Any) -> None:  # noqa: ARG002
        pass


# ---------------------------------------------------------------------------
# ACPAgent
# ---------------------------------------------------------------------------


class ACPAgent(AgentBase):
    """智能体委托给 ACP 兼容的子进程服务器。"""

    # 使用 ACP 相应的默认值覆盖必填字段
    llm: LLM = Field(default_factory=_make_dummy_llm)
    tools: list[Tool] = Field(default_factory=list)
    include_default_tools: list[str] = Field(default_factory=list)

    # ACP-具体配置
    acp_command: list[str] = Field(
        ...,
        description=(
            "Command to start the ACP server, e.g."
            " ['npx', '-y', '@agentclientprotocol/claude-agent-acp']"
        ),
    )
    acp_server: str | None = Field(
        default=None,
        description=(
            "Provider registry key identifying which ACP CLI this agent runs "
            "(any ACP_PROVIDERS key, or 'custom'); None when the agent is "
            "built directly rather than via ACPAgentSettings. Set by "
            "ACPAgentSettings.create_agent() from ACPAgentSettings.acp_server so "
            "the authoritative key survives onto the agent — and thus onto "
            "ConversationInfo.agent — because the launch command in acp_command "
            "does not reliably reverse-map to a provider. Informational only: "
            "consumers use it to resolve a provider brand label / model list; "
            "the subprocess is still launched from acp_command."
        ),
    )
    acp_args: list[str] = Field(
        default_factory=list,
        description="Additional arguments for the ACP server command",
    )
    acp_session_mode: str | None = Field(
        default=None,
        description=(
            "Session mode ID to set after creating a session. "
            "If None (default), auto-detected from the ACP server type: "
            "'bypassPermissions' for claude-agent-acp, "
            "'agent-full-access' for codex-acp; a provider with no such mode "
            "(pi-acp) skips the call."
        ),
    )
    acp_prompt_timeout: float = Field(
        default=1800.0,
        description=(
            "Inactivity timeout in seconds for a single ACP prompt() call. "
            "The deadline resets on every update from the ACP server (token, "
            "thought, tool-call progress, usage), so a steadily-progressing "
            "agent runs as long as it keeps making progress; the prompt is "
            "only aborted after this many seconds with no activity at all. "
            "Prevents indefinite hangs when the ACP server stops responding "
            "without killing legitimately long-running work."
        ),
    )
    acp_startup_timeout: float = Field(
        default=90.0,
        description=(
            "Timeout in seconds for ACP server startup: spawning the "
            "subprocess, the initialize/authenticate handshake, and "
            "new_session()/load_session(). Unlike acp_prompt_timeout, this "
            "is a hard deadline rather than an idle deadline, since startup "
            "has no intermediate progress signal to reset it against. "
            "Prevents an indefinite hang when the ACP server blocks on "
            "authentication (e.g. an expired token) without ever raising."
        ),
    )
    acp_model: str | None = Field(
        default=None,
        description=(
            "Model for the ACP server to use (e.g. 'sonnet' or 'gpt-5.5'). "
            "Applied via the protocol — set_config_option(model) for "
            "configOptions-based servers (codex, claude), else "
            "set_session_model. If None, the server picks its default."
        ),
    )
    acp_resume_session_id: str | None = Field(
        default=None,
        description=(
            "Optional explicit ACP session id to resume. When set, takes "
            "precedence over the id persisted in ``state.agent_state`` and "
            "is used to call ``session/load`` on the ACP server. Designed "
            "for environments where the per-conversation filesystem (and "
            "therefore ``base_state.json``) does not survive across restarts "
            "(e.g. cloud sandbox recycles), but the id has been mirrored "
            "into durable storage elsewhere. Falls back to a fresh session "
            "if the server cannot load the id. Treated as a secret on the "
            "wire — possession of the id is enough to resume the underlying "
            "ACP session, so default serialization redacts it; pass "
            "``expose_secrets='plaintext'`` (trusted backend) or "
            "``expose_secrets='encrypted'`` plus a cipher (frontend round-"
            "trip) when the value must cross a serialization boundary."
        ),
    )

    @field_serializer("acp_resume_session_id", when_used="always")
    def _serialize_acp_resume_session_id(self, value: str | None, info):
        """通过：func:`serialize_secret` 掩码 ``acp_resume_session_id``。

        默认 ``model_dump`` / ``model_dump_json`` 会编辑 ID，以便它不会泄漏到日志、跟
        踪导出或 PR 审阅附件中。 受信任的
        后端调用者通过 Pydantic 的上下文 (``expose_secrets='plaintext'``) 选择明文；
        前端往返使用
        ``"encrypted"`` 模式，密码在上下文中。
        """
        if value is None:
            return None
        return serialize_secret(SecretStr(value), info)

    @field_validator("acp_resume_session_id", mode="before")
    @classmethod
    def _validate_acp_resume_session_id(
        cls, value: Any, info: ValidationInfo
    ) -> str | None:
        """加载时反转：meth:`_serialize_acp_resume_session_id`。

        如果没有这个验证器，先前的已序列化智能体的 ``model_validate_json`` 会将垃圾放
        入 ``acp_resume_session_id``
         中：

        - 已脱敏默认的``"**********"`` 哨兵值会重新加载，因为``session/load`` 会失败
        ，因为我们每次都会切换到一个新的会话，这破坏
        了持久镜像的初衷。
        - 加密转储（前端往返）将作为原始 Fernet 密文重新加载 - 相同的故障模式，加上密
        文位于磁盘上的 ``state.agent_state`` 中。

        :func:`validate_secret` 对于空/编辑值返回 ``None``
        并在验证上下文中存在密码时进行解密。 我们解开返回的 ``SecretStr``，因此该字段
        的运行时类型保持为 ``str | None``（SDK 的
        REST 直接读取它）。
        """
        secret = validate_secret(value, info)
        return secret.get_secret_value() if secret is not None else None

    acp_file_secrets: list[ACPFileSecretSpec] = Field(
        default_factory=lambda: list(default_acp_file_secrets()),
        description=(
            "Reserved 'file-content' credential secrets to materialise to disk "
            "before launching the subprocess (e.g. Codex auth.json, Gemini "
            "Vertex SA JSON). The SDK owns the mechanism (write the file in the "
            "runtime pod, set the env var, seed-if-absent); these specs are the "
            "policy. Defaults to the built-in supported providers; a downstream "
            "application may override or extend this to support other ACP "
            "servers with different file-auth schemes."
        ),
    )
    acp_isolate_data_dir: bool = Field(
        default=False,
        description=(
            "Give the ACP subprocess a per-conversation CLI data/config root "
            "instead of the shared user ``HOME``. When True and the provider is "
            "recognised, point its data-dir env var "
            "(``CODEX_HOME`` / ``CLAUDE_CONFIG_DIR`` / ``HOME``; see "
            "``ACPProviderInfo.data_dir_env_var``) at "
            "``<persistence_dir>/acp/<provider>`` — the same per-conversation "
            "tree materialised file-secrets use. Required for correctness when "
            "several of a user's conversations share one sandbox "
            "(``SandboxGroupingStrategy != NO_GROUPING``), where they would "
            "otherwise race on one set of CLI auth/config/cache/lock files "
            "(see #1019). Off by default: with one sandbox per conversation the "
            "shared HOME is already private, and relocating it would hide a "
            "pre-existing interactive login. Downstream policy decides when to "
            "enable it; the SDK owns where the root lives."
        ),
    )

    @field_validator("agent_context")
    @classmethod
    def _drop_project_skills(cls, value: AgentContext | None) -> AgentContext | None:
        """``load_project_skills`` — ACP CLIs 请自行阅读仓库。

        Claude Code、Codex 和 Gemini 已经从会话 cwd 中读取 ``AGENTS.md`` 和
        ``CLAUDE.md``，所以在这里重复
        加载这些内容会把内容加载两次到提示词。 标准化而不是
        rejected: 调用者合法地在共享上下文上设置标志，他们也
        用于 OpenHands 智能体 (#4019)。
        """
        if value is None or not value.load_project_skills:
            return value
        return value.model_copy(update={"load_project_skills": False})

    def model_post_init(self, __context: object) -> None:
        super().model_post_init(__context)
        # 将实际模型名称传播到哨兵值  LLM 以及其指标，以便于日志已序列化状态和成本/令牌
        # 条目显示的是实际模型，而不是"ACP-managed" placeholder。 的 ACP-哨兵值标记永生
        # ``llm.usage_id`` 并且与模型名称无关。
        #
        if self.acp_model:
            self.llm.model = self.acp_model
            self.llm.metrics.model_name = self.acp_model
            if self.llm.metrics.accumulated_token_usage is not None:
                self.llm.metrics.accumulated_token_usage.model = self.acp_model

    # 私有运行时状态
    _executor: Any = PrivateAttr(default=None)
    _conn: ClientSideConnection | None = PrivateAttr(default=None)
    _session_id: str | None = PrivateAttr(default=None)
    _process: Any = PrivateAttr(default=None)  # 异步子进程
    _client: Any = PrivateAttr(default=None)  # _OpenHandsACPBridge
    _filtered_reader: Any = PrivateAttr(default=None)  # StreamReader
    _stdout_filter_task: Any = PrivateAttr(default=None)  # asyncio.Task
    _stderr_log_task: Any = PrivateAttr(default=None)  # asyncio.Task
    _closed: bool = PrivateAttr(default=False)
    _working_dir: str = PrivateAttr(default="")
    _agent_name: str = PrivateAttr(
        default=""
    )  # ACP 来自 InitializeResponse 的服务器名称
    _agent_version: str = PrivateAttr(
        default=""
    )  # ACP 服务器版本来自 InitializeResponse
    # 此会话使用哪个协议来选择模型：``True`` ⇒
    # ``session/set_config_option(configId="model")``（法典-ACP，克劳德-智能体-ACP 0.44+
    # ）； ``False`` ⇒ ``session/set_model``（双子座-CLI 和较旧的法典/克劳德）。 在 init
    #  时从会话/新（或 load_session）响应中检测到并由运行时 ``set_acp_model`` 开关重用。
    #
    _model_via_config_option: bool = PrivateAttr(default=False)
    # ACP 服务器报告为此会话处于活动状态的模型，已捕获
    # from ``models.currentModelId`` on the new_session / load_session
    # 回应。 当调用者明确选择一个（通过 ``set_session_model`` 或通过会话 ``_meta``）时，
    # 被 ``self.acp_model`` 覆盖。
    # ``None`` 当服务器不显示模型状态时 - 该字段在 ACP 规范中标记为 UNSTABLE，因此较旧的
    # 智能体可能会省略它。
    #
    # 保留为 PrivateAttr（不是 Pydantic 字段），因为 ``AgentBase`` 已冻结，并且这是每个
    # 会话运行时状态，而不是配置。 智能体-服务器将其提升到 ``ConversationInfo``，因此该
    # 值可以跨越 API 边界，即使智能体本身不序列化它。
    #
    _current_model_id: str | None = PrivateAttr(default=None)
    # ``models.availableModels`` 来自同一会话响应，标准化为我们的稳定 ``ACPModelInfo``
    # 类型。 通过逐字逐句浮出水面
    # ``available_models`` 属性（和 ``ConversationInfo.available_models``），以便客户端
    # 可以渲染选择器并将 ``current_model_id`` 解析为自己的显示标签 - SDK 不进行名称管理
    # 。
    # ``None`` 编码“服务器没有报告本次启动的 ``models`` 块”（与 ``[]`` =“报告，但没有模
    # 型”不同）； ``init_state`` 中的持久化逻辑使用这种区别来保留和清除恢复时存储的列表
    # 。 公共``available_models``财产强制``[]``。
    #
    _available_models: list[ACPModelInfo] | None = PrivateAttr(default=None)
    # 调用者的 ``acp_model`` 是否实际上在最近的会话初始化中推送到服务器（通过会话
    # ``_meta`` 或 ``set_session_model``）。
    # ``False`` 当没有进行覆盖时，提供者无法应用它（在新会话中，未知服务器），或者在恢复
    # 时服务器拒绝了调用——在这种情况下，活会话会运行自己的默认，所以两者都不适用
    # ``_current_model_id`` 和 ``ConversationInfo`` 回退方案都不会出现
    # ``acp_model`` 作为活动模型。 由``init_state``读取来决定是否必须清除陈旧的已持久化
    # ``acp_current_model_id``。
    #
    _model_override_applied: bool = PrivateAttr(default=False)
    # 回调表示 ACP 子进程正在积极工作。 由智能体-服务器注入以调用
    # update_last_execution_time()。
    #
    _on_activity: Any = PrivateAttr(default=None)  # [[]，None] | None
    # 后缀在会话开始时渲染一次，从 agent_context + secret_registry 开始。 "unused" — 无
    # agent_context 或空后缀 "pending_first_prompt" — 新会话； 注入第一个用户消息“已安装
    # ”——已经在子进程历史记录中； 跳过进一步注射
    #
    _suffix_install_state: str = PrivateAttr(default="unused")
    _installed_suffix: str | None = PrivateAttr(default=None)
    # 写入磁盘并在提示词中按路径列出的技能，未内联。
    _skill_locations: dict[str, Path] = PrivateAttr(default_factory=dict)
    _skills_root: Path | None = PrivateAttr(default=None)
    _additional_directories_supported: bool = PrivateAttr(default=False)
    _restart_session_on_next_turn: bool = PrivateAttr(default=False)
    # 飞行中转弯的流身份； 参见stream_context.py。 保留在智能体上而不是通过终结器线程，
    # 因为 ACP 回合已经通过其中四个终结器解析。
    #
    _stream: StreamContext | None = PrivateAttr(default=None)
    _resumed_existing_session: bool = PrivateAttr(default=False)
    _file_credential_lifecycles: dict[str, ACPFileCredentialLifecycle] = PrivateAttr(
        default_factory=dict
    )
    _file_credential_bindings: dict[str, VersionedCredentialBinding] = PrivateAttr(
        default_factory=dict
    )
    _file_credential_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _file_credential_close_lock: threading.Lock = PrivateAttr(
        default_factory=threading.Lock
    )
    _replace_file_credentials_on_next_materialisation: set[str] = PrivateAttr(
        default_factory=set
    )
    _atexit_callback: Callable[[], None] | None = PrivateAttr(default=None)

    # -- 帮手 --------------------------------------------------------------------------
    # --------

    def activate_file_credential_binding(
        self,
        secret_name: str,
        binding: VersionedCredentialBinding,
    ) -> None:
        with self._file_credential_lock:
            if self._initialized or self._closed:
                raise RuntimeError(
                    "ACP credential bindings must be activated before use"
                )
            self._file_credential_bindings[secret_name] = binding

    def restart_for_updated_credentials(self, secret_names: Collection[str]) -> None:
        configured = {spec.secret_name for spec in self._active_file_secrets()}
        with self._file_credential_lock:
            self._replace_file_credentials_on_next_materialisation.update(
                configured.intersection(secret_names)
            )
        if self._initialized:
            self._restart_session_on_next_turn = True

    def _has_runtime_resources(self) -> bool:
        return (
            self._executor is not None
            or self._process is not None
            or self._conn is not None
            or bool(self._file_credential_lifecycles)
        )

    def _register_atexit_cleanup(self, *, replace: bool = False) -> None:
        if self._atexit_callback is not None:
            if not replace:
                return
            atexit.unregister(self._atexit_callback)
        agent_ref = weakref.ref(self)

        def cleanup() -> None:
            agent = agent_ref()
            if agent is not None:
                agent._finalize()

        self._atexit_callback = cleanup
        atexit.register(cleanup)

    def _unregister_atexit_cleanup(self) -> None:
        callback = self._atexit_callback
        if callback is not None:
            atexit.unregister(callback)
            self._atexit_callback = None

    def _record_usage(
        self,
        response: PromptResponse | None,
        session_id: str,
        elapsed: float | None = None,
        usage_update: UsageUpdate | None = None,
    ) -> None:
        """记录成本、词元用量、延迟，并通知统计数据回调一次。

        Args:
            response: ACP PromptResponse（可以携带 ``usage`` 字段）。
            session_id: 会话标识符用作指标的 response_id。
            elapsed: 此提示词往返的挂钟秒数（可选）。
            usage_update: 本回合同步的 ACP UsageUpdate（如果有）。
        """
        # -- 成本记录----------------------------------------------------------------
        # claude-智能体-ACP，codex-ACP：通过 UsageUpdate 通知报告成本 Gemini-CLI：不发送
        #  UsageUpdate（成本源自下面的 token）
        #
        cost_recorded = False
        if usage_update is not None and usage_update.cost is not None:
            last_cost = self._client._last_cost_by_session.get(session_id, 0.0)
            delta = usage_update.cost.amount - last_cost
            if delta > 0:
                self.llm.metrics.add_cost(delta)
                cost_recorded = True
            self._client._last_cost_by_session[session_id] = usage_update.cost.amount
            self._client._last_cost = usage_update.cost.amount

        # -- 词元用量录音 --------------------------------------------------------
        input_tokens, output_tokens, cache_read, cache_write, reasoning = (
            _extract_token_usage(response)
        )
        if input_tokens or output_tokens:
            self.llm.metrics.add_token_usage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
                reasoning_tokens=reasoning,
                context_window=self._client._context_window_by_session.get(
                    session_id, self._client._context_window
                ),
                response_id=session_id,
            )

        # -- 成本推导自 token --------------------------------------------------
        # gemini-CLI：没有 UsageUpdate 成本，因此使用 LiteLLM 的模型定价数据库（与代理使
        # 用的来源相同）从 token 计数得出。 claude-智能体-ACP，codex-ACP：跳过，因为
        # cost_recorded 是 True。
        #
        if not cost_recorded and (input_tokens or output_tokens) and self.acp_model:
            cost = _estimate_cost_from_tokens(
                self.acp_model, input_tokens, output_tokens
            )
            if cost > 0:
                self.llm.metrics.add_cost(cost)

        if not cost_recorded and not input_tokens and not output_tokens:
            # gemini-CLI 当前返回 response.usage=None 并且
            # response.field_meta=None (ACP SDK strips _meta during
            # 序列化). 在 google-gemini/gemini-CLI#24280 中跟踪。
            logger.debug(
                "No usage data from ACP server %s — token/cost tracking unavailable",
                self._agent_name or "unknown",
            )

        if elapsed is not None:
            self.llm.metrics.add_response_latency(elapsed, session_id)

        if self.llm.telemetry._stats_update_callback is not None:
            try:
                self.llm.telemetry._stats_update_callback()
            except Exception:
                logger.debug("Stats update callback failed", exc_info=True)

    # -- 能力帮手------------------------------------------------

    @property
    def supports_openhands_tools(self) -> bool:
        """``False`` — ACP 服务器管理自己的工具集。"""
        return False

    @property
    def supports_openhands_mcp(self) -> bool:
        """``False`` — OpenHands 此处不创建进程内 MCP 工具。

        ACP 智能体仍然通过在会话创建时将配置的服务器转发到 ACP 子进程来尊重
        ``mcp_config``。
        """
        return False

    @property
    def supports_condenser(self) -> bool:
        """``False`` — ACP 服务器管理自己的上下文窗口。"""
        return False

    @property
    def agent_kind(self) -> Literal["acp"]:
        """ACP 智能体有 ``agent_kind == "acp"``。"""
        return "acp"

    # -- ACP 特定的运行时属性 --------------------------------------------------

    @property
    def agent_name(self) -> str:
        """ACP 服务器的名称（来自 InitializeResponse.agent_info）。"""
        return self._agent_name

    @property
    def agent_version(self) -> str:
        """ACP 服务器的版本（来自 InitializeResponse.agent_info）。"""
        return self._agent_version

    @property
    def current_model_id(self) -> str | None:
        """ACP 服务器当前用于此会话的模型。

        摘自 ``models.currentModelId``
        当服务器显示它时 ``new_session`` / ``load_session`` 响应（UNSTABLE ACP 功能）
        ，或当调用者明确选择其中之一时
         ``self.acp_model``。 ``None`` 对于不报告模型状态并且未设置覆盖的旧服务器 -
         调用者应将该值视为尽力而为。

        Note: 这是进程内运行时状态； 它不往返
        通过``model_dump()``。 需要跨 API 边界读取它的消费者应该查看
        ``ConversationInfo.current_model_id``，智能体服务器将智能体提升到响应中。

        这个（协议报告的会话模型）是权威模型 ID——相信它而不是模型本身所说的内容。 提
        供者模型不可靠地内省自己的身份：gemini-CLI 报告过时
        ``gemini-1.5-flash-latest`` 无论活动模型如何，codex 都不会命名其层级。 经过所
        有三个提供商的验证； 即使模型的自我描述不一
        致，这种转换也会得到尊重。
        """
        return self._current_model_id

    @property
    def available_models(self) -> list[ACPModelInfo]:
        """对 ACP 服务器为此会话提供的模型进行建模。

        从 ``models.availableModels`` 上逐字捕获
        ``new_session`` / ``load_session`` 响应（UNSTABLE ACP 能力）； 对于不显示它的
        服务器为空。 每个条目都带有服
        务器的 ``model_id`` 加上可选的 ``name``/``description`` — 足以让客户端渲染模
        型选择器并解析
        ``current_model_id`` 到没有任何服务器端管理的显示标签。 ``current_model_id``
        是传回服务器以切换到该模型的值。

        与 ``current_model_id`` 相同的生命周期和序列化警告：进程内运行时状态，提升到
        ``ConversationInfo.available_models`` 由跨进程消费者的智能体服务器提供。 始终
        是一个列表（内部 ``None``“未报
        告”哨兵值在此被强制为 ``[]``）。
        """
        return list(self._available_models or [])

    @property
    def supports_runtime_model_switch(self) -> bool:
        """是否尝试进行实时对话模式切换。

        告诉客户是否提供内联选择器的实时切换控制。
        ``True`` 仅适用于明确声明支持运行时模型切换的已知提供程序。
        ``set_config_option`` 未知/自定义提供者使用 * 选择初始 *
        模型，但 RPC 这是一个通用配置写入，而不是一个保证的实时切换原语，因此选择器对
        他们是隐藏的。
        ``False`` 在会话存在之前（尚未切换）。

        参见
        ：方法：
        `~openhands.sdk.conversation.impl.local_conversation.LocalConversation.switch_acp_model`
        。
        """  # noqa: E501
        if self._session_id is None:
            return False
        provider = detect_acp_provider_by_agent_name(self._agent_name)
        return provider is not None and provider.supports_runtime_model_switch

    @property
    def has_live_acp_session(self) -> bool:
        """是否存在可立即执行的实时 ACP 会话。

        ``True`` 只有在子进程- 被后端会话完全连接 - 连接、会话 ID 和执行器都存在 - 这
        发生在第一次 ``run()`` (请参阅：
        `see :meth:`)`init_state`). ``False`` 在创建但尚未运行之前，以及 teardown之后
        。

        让调用者在会话状态上分支而不是捕获
        ``RuntimeError`` :meth:`set_acp_model` 提出会前或进入 ``_conn`` /
        ``_session_id`` /
        ``_executor`` PrivateAttrs。 特别是
        ：甲基：
        `~openhands.sdk.conversation.impl.local_conversation.LocalConversation.switch_acp_model`
        使用它来决定下一个会话启动应用的实时就地切换和延迟持久化。
        """  # noqa: E501
        return (
            self._conn is not None
            and self._session_id is not None
            and self._executor is not None
        )

    def get_all_llms(self) -> Generator[LLM]:
        yield self.llm

    # -- 生命周期---------------------------------------------------------------------

    def init_state(
        self,
        state: ConversationState,
        on_event: ConversationCallbackType,
    ) -> None:
        """生成 ACP 服务器并初始化会话。"""
        # 验证不支持的执行功能。 agent_context 是允许的，因为它为用户消息提供了仅提示词
        # 的扩展； ACP 服务器工具和上下文窗口管理仍然归服务器所有。 mcp_config IS 支持：
        # 其服务器在会话创建时转发到子进程（参见 _mcp_config_to_acp_servers），而不是转
        # 变为进程内 SDK MCP 工具。
        #
        if self.tools:
            raise NotImplementedError(
                "ACPAgent does not support custom tools; "
                "the ACP server manages its own tools"
            )
        if self.condenser is not None:
            raise NotImplementedError(
                "ACPAgent does not support condenser; "
                "the ACP server manages its own context"
            )
        if self.agent_context:
            self.agent_context.validate_acp_compatibility()

        from openhands.sdk.utils.async_executor import AsyncExecutor

        if self._executor is not None:
            self._cleanup()
        self._executor = AsyncExecutor()

        # 渲染后缀一次，从对话的 secret_registry 中提取机密以匹配常规智能体的
        # get_dynamic_context()。
        #
        self._materialize_skills(state)
        self._installed_suffix = self._render_suffix(state)
        # 先前的会话 ID 意味着我们可能会恢复； 下面的 ``truly_resumed`` 使用它来确定为本
        # 次启动报告的模型状态是描述恢复的会话还是新的会话。 明确的
        # ``acp_resume_session_id`` (e.g. 擦除 base_state.json 后返回 id 的云会话 ID 镜
        # 像）优先于 FS-已持久化 id，与 ``_start_acp_server`` 中的优先级匹配 — 因此
        # 无论恢复的 id 来自 FS 还是显式字段，``truly_resumed`` (
        # ``self._session_id == prior_session_id``) 都保持正确。
        #
        prior_session_id = self.acp_resume_session_id or state.agent_state.get(
            "acp_session_id"
        )
        # ``acp_suffix_installed`` 等于已持久化
        # ``_commit_suffix_installation`` 只有在第一个提示词实际上成功返回之后，所以在恢
        # 复时我们知道 ACP 子进程是否收到了后缀。 ``acp_session_id`` 单独使用并不是一个
        # 可靠的信号——无论第一个提示词是否成功，已持久化在会话创建时间。因此，从会话ID的
        # 存在中推断“安装”会跳过提示词的前一次会话的后缀注入。 升级后，已持久化之前的PR
        # 状态在第一次升级后会重新注入后缀，这是正常的——后缀是LLM-上下文指导。
        #
        suffix_already_installed = bool(state.agent_state.get("acp_suffix_installed"))
        # _resumed_existing_session 的尽力初始值； 一旦 _start_acp_server 返回，真正的起
        # 始路径就会覆盖它。
        #
        self._resumed_existing_session = bool(prior_session_id)

        try:
            self._start_acp_server(state)
        except Exception as e:
            logger.error("Failed to start ACP server: %s", e)
            try:
                self._cleanup()
            except Exception:
                logger.warning("Failed to clean up ACP resources", exc_info=True)
            if self._has_runtime_resources():
                self._register_atexit_cleanup(replace=True)
            # init_state runs *outside*  run()/arun()'s try-block（它通过 try-block 被到
            # 达） _ensure_agent_ready（在循环开始之前），因此冷启动失败 —— 错误/过期的
            # 认证，缺失 CLI 二进制文件与工作目录不匹配——否则会跳过错误的发出，并以通用
            # 的“远程对话以错误结束”形式到达客户端。 发出一个类型化的
            # ConversationErrorEvent 并将状态翻转为 ERROR 这里，镜像常规的智能体 (and)
            # ACPAgent.astep） 在运行循环内部，所以客户端会渲染现有的错误提示框。 尽力而
            # 为：必须确保错误信息不会掩盖原始异常，该异常仍然会传播以保留现有的清理/重
            # 新抛出合同 run()/arun() 依赖。
            #
            try:
                state.execution_status = ConversationExecutionStatus.ERROR
                on_event(
                    ConversationErrorEvent(
                        source="agent",
                        code=_classify_acp_init_error(e),
                        detail=_acp_error_detail(e, state.secret_registry),
                    )
                )
            except Exception:
                logger.exception("Failed to surface ACP init error to client")
            raise

        self._register_atexit_cleanup(replace=True)

        # 一份成功的简历会保留之前的身份； cwd 不匹配和 load_session 失败都会回落到
        # ``new_session``，这会产生一个新的。 会话 ID 比较是唯一的权威信号——决定发生在
        # ``_start_acp_server`` 内部，并且在这里无法观察到。
        #
        # 当 _start_acp_server 在测试中被修补时，self._session_id 保留为 None（从未由模
        # 拟对象设置）。 在这种情况下，请保留上面设置的尽力而为
        # _resumed_existing_session 值； 否则以权威比较结果覆盖。
        #
        if self._session_id is not None:
            truly_resumed = (
                prior_session_id is not None and self._session_id == prior_session_id
            )
            self._resumed_existing_session = truly_resumed
        else:
            truly_resumed = self._resumed_existing_session

        self._initialized = True

        # 持久化智能体信息 +  ACP 会话 ID 和其工作目录 agent_state. 把它们放在这里（而不
        # 是放在冷冻的地方） ACPAgent 模型）是指 ConversationState'现有的'
        # base_state.json  持久化将他们带到目的地智能体服务器重启，和
        # ``_start_acp_server`` 在下一次启动时，它们会被读回并调用 ``load_session`` 不如
        # 从头开始。 我们记录 ``acp_session_cwd`` 除了 id 之外 ACP 服务器钥匙他们的持久
        # 化 by ``cwd``在不同地方继续工作目录最好默默错过之前的会话，最坏加载一个存在于
        # 新工作目录的新会话。
        #
        new_agent_state = {
            **state.agent_state,
            "acp_agent_name": self._agent_name,
            "acp_agent_version": self._agent_version,
            "acp_session_id": self._session_id,
            "acp_session_cwd": self._working_dir,
            # 静态提供者能力 — 已持久化冷读会话列表中的对话可以告诉选择器是否需要提供实
            # 时切换，而无需在服务器侧重新检测提供者。
            #
            "acp_supports_runtime_model_switch": self.supports_runtime_model_switch,
            # 检测到模型选择机制已持久化那么一个简历是  load_session 省略了模型块，而是
            # 通过正确的调用来重新应用模型，而不是默认应用 set_session_model.
            #
            "acp_model_via_config_option": self._model_via_config_option,
        }
        # 启动新会话时，清除过时的后缀标记，以便下次启动时知道重新注入它（PR行为：后缀状
        # 态是每个会话）。
        #
        if not self._resumed_existing_session:
            new_agent_state.pop("acp_suffix_installed", None)
        # 模型状态跟踪（来自 main）：持久化当前模型 ID 和用于冷读对话列表的可用模型列表
        # 。
        #
        override_attempted_not_applied = bool(self.acp_model) and (
            not self._model_override_applied
        )
        if self._current_model_id is not None:
            new_agent_state["acp_current_model_id"] = self._current_model_id
        elif (
            not truly_resumed
            or self._available_models is not None
            or override_attempted_not_applied
        ):
            new_agent_state.pop("acp_current_model_id", None)
        if self._available_models is not None:
            new_agent_state["acp_available_models"] = [
                m.model_dump() for m in self._available_models
            ]
        elif not truly_resumed:
            new_agent_state.pop("acp_available_models", None)
        state.agent_state = new_agent_state

        if self._installed_suffix:
            self._suffix_install_state = (
                "installed"
                if suffix_already_installed and self._resumed_existing_session
                else "pending_first_prompt"
            )

        # 发出占位符系统提示词，以便可视化工具显示一个部分，即使真实系统提示词由 ACP 服
        # 务器管理。 dynamic_context 镜像 agent.py 的 SystemPromptEvent，以便工具（UI、
        # 测试）可以检查安装的后缀。
        #
        on_event(
            SystemPromptEvent(
                source="agent",
                system_prompt=TextContent(
                    text=(
                        "This conversation is powered by an ACP server. "
                        "The system prompt and tools are managed by the "
                        "ACP server and are not available for display."
                    )
                ),
                dynamic_context=TextContent(text=self._installed_suffix)
                if self._installed_suffix
                else None,
                tools=[],
            )
        )

    def _skill_directories(self) -> list[str] | None:
        if self._skills_root and self._additional_directories_supported:
            return [str(self._skills_root)]
        return None

    def _materialize_skills(self, state: ConversationState) -> None:
        self._skill_locations = {}
        self._skills_root = None
        context = self.agent_context
        if context is None or not context.skills:
            return
        _, available = context._partition_skills()
        if not available:
            return
        root = self._acp_file_secret_dir(state, "skills")
        shutil.rmtree(root, ignore_errors=True)
        self._skill_locations = write_skill_files(root, available)
        self._skills_root = root

    def _render_suffix(self, state: ConversationState) -> str | None:
        """渲染一次系统后缀，包括注册表中的机密。

        ``<CUSTOM_SECRETS>`` 块列出了 ACP 子进程将接收的每个机密，因此智能体知道哪些
        环境变量可用，而无需将它们内联到提示词中。 我们渲染它
        来自
        ``state.secret_registry`` 即使 ``agent_context`` 不存在 - 否则对话仅通过机密
        传送
        ``StartConversationRequest.secrets`` 频道（canonical path）会无声地丢弃广告，
        留下智能体无知的机密尽管如此
        ，它们仍将在其环境里着陆
        ``_start_acp_server``.

        保留的文件内容机密（Codex ``auth.json``、Gemini Vertex SA — 请参阅：meth:
        `_materialise_file_secrets`）从
        advertisement: 它们的值被写入磁盘，而不是作为 env 注入
        vars，因此将它们宣传为可用的环境变量会误导智能体。
        """
        # state.secret_registry 单独推广 —— 它现在也包含了 agent_context.secrets（在对话
        # 开始时被种子，包含他们的描述），所以它是 <CUSTOM_SECRETS> 块的唯一来源。 保留
        # 的文件内容机密被写入磁盘，而不是作为环境变量注入，因此将它们从广告中删除。
        #
        file_secret_names = self._present_file_secret_names(state)
        secret_infos = [
            info
            for info in state.secret_registry.get_secret_infos()
            if info.get("name") not in file_secret_names
        ]
        agent_context = self.agent_context
        if agent_context is None:
            # 没有调用方提供的上下文。 只有在实际有时，才为渲染器生成一个空的注册表-机密
            # 广告投放 —— 否则返回 None 所以我们不会开始注入空的其他部分 AgentContext'的
            # 默认值是（current_datetime, …) that the oldagent_context 是 None ⇒ 使用了“
            # 无后缀”规则来抑制。
            #
            if not secret_infos:
                return None
            agent_context = AgentContext(current_datetime=None)
        listed = [s for s in agent_context.skills if s.name in self._skill_locations]
        if listed:
            agent_context = agent_context.model_copy(
                update={"skills": [s for s in agent_context.skills if s not in listed]}
            )
        if agent_context.secrets:
            # 注册表已经包含了这些（及其描述），因此，仅从注册表中清除agent_context的副
            # 本，而不是重新合并冗余的第二个来源。
            #
            agent_context = agent_context.model_copy(update={"secrets": {}})
        rendered = agent_context.to_acp_prompt_context(
            additional_secret_infos=secret_infos
        )
        if not listed:
            return rendered
        catalog = render_skill_catalog(listed, self._skill_locations)
        return f"{rendered}\n\n{catalog}" if rendered else catalog

    def _present_file_secret_names(self, state: ConversationState) -> set[str]:
        """为此对话提供的保留文件内容机密名称。

        如果名称在以下位置配置，则视为存在：
        :attr:`acp_file_secrets` * 和 * 在 ``state.secret_registry`` 中注册
        （它也包含 ``agent_context.secrets``，在对话初始化时播种）。 这些名称被写入磁
        盘，因此不包括普通的环境变量注入和
        ``<CUSTOM_SECRETS>``的广告（它们的值是文件块，而不是环境变量子进程可以按名称
        引用）。
        """
        configured = {spec.secret_name for spec in self._active_file_secrets()}
        if not configured:
            return set()
        return set(state.secret_registry.secret_sources) & configured

    def _acp_file_secret_dir(self, state: ConversationState, subdir: str) -> Path:
        """凭据文件的持久每个对话目录。

        ``<persistence_dir>/acp/{subdir}`` — 同样保留了常规智能体的会话树
        ``base_state.json`` / 事件，因
        此 token 会话树在磁盘上持久化，会话在 pod 重启后 CLI 会刷新，会话在暂停/恢复
        后 ``/workspace`` 持久化。 参见#1018/#
        1019）。 当对话不是已持久化时，回退到工作区下的每个对话目录（e.g. 内存测试）—
        —如果不存在的话仍然是种子，仍然没有
        ``TemporaryDirectory``. 返回绝对值，因此子进程（继承智能体-服务器的 cwd）明确
        地解析它。
        """
        if state.persistence_dir:
            root = Path(state.persistence_dir) / "acp" / subdir
        else:
            root = Path(state.workspace.working_dir) / ".openhands" / "acp" / subdir
        return Path(os.path.abspath(root))

    def _acp_npm_cache_dir(self, state: ConversationState) -> Path:
        if state.persistence_dir:
            root = Path(state.persistence_dir).parent
        else:
            root = Path(state.workspace.working_dir) / ".openhands"
        cache_dir = root / "npm-cache"
        cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        return Path(os.path.abspath(cache_dir))

    async def _warm_npx_cache(
        self,
        packages: Sequence[str],
        provider_key: str,
        env: dict[str, str],
        cwd: str,
    ) -> None:
        logger.info(
            "Warming ACP provider npx cache: provider=%s, packages=%s; "
            "first use may download the provider before session startup",
            provider_key,
            list(packages),
        )
        package_args = [arg for package in packages for arg in ("--package", package)]
        process = await asyncio.create_subprocess_exec(
            "npx",
            "--yes",
            "--prefer-offline",
            *package_args,
            "--",
            "node",
            "-e",
            "",
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(process.wait(), timeout=_ACP_NPX_CACHE_WARM_TIMEOUT)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise RuntimeError(
                "ACP provider cache warm timed out after "
                f"{_ACP_NPX_CACHE_WARM_TIMEOUT:.0f}s for {provider_key}"
            ) from exc
        if process.returncode:
            raise RuntimeError(
                f"ACP provider cache warm failed for {provider_key} "
                f"(exit code {process.returncode})"
            )

    def _isolate_acp_data_dir(
        self, state: ConversationState, env: dict[str, str]
    ) -> None:
        """将 CLI 的 data/config 根目录重新定位到每个对话目录。

        当：attr:`acp_isolate_data_dir` 设置时，将识别的提供者的 data-dir env var (
        ``CODEX_HOME`` /
        ``CLAUDE_CONFIG_DIR`` / ``HOME``) 指向
        ``<persistence_dir>/acp/<provider>`` — 相同的每个对话树
        :meth:`_materialise_file_secrets` 种子验证到，所以重新定位
        ``CODEX_HOME`` 和具体化的 ``auth.json`` 始终同意一个目录。 这会阻止共享沙箱 (
        ``SandboxGroupingStrategy != NO_GROUPING``) 的对话在单个共享 HOME 的 CLI auth
        /config/ca
        che/lock 文件上竞争 (#1019)。 覆盖替换环境值 (e.g. 智能体-服务器自己的
        ``CODEX_HOME``）：每个会话的根是隔离的目的。

        对于无法识别的命令或没有重定位杠杆的提供者，无法执行任何操作。

        Claude 注意：在任何一种身份验证模式下，重新定位 ``CLAUDE_CONFIG_DIR`` 都是安
        全的。 :data:
        `_ENV_CONFLICT_MAP` 是在 OAuth token (``CLAUDE_CODE_OAUTH_TOKEN``) 上键入的，
        而不是在
        ``CLAUDE_CONFIG_DIR`` 上键入的，因此设置用于隔离的配置目录不再剥夺工作
        ``ANTHROPIC_API_KEY`` — API-key Claude 获得与 OAuth Claude 相同的每次对话隔离
        （以及暂停/恢复连续性）（
        #3588）。

        ``HOME``（gemini-CLI 的唯一杠杆，它硬编码 ``~/.gemini`` 并忽略 ``XDG``，以及
        pi-ACP，其会话映射被硬编码为
        ``~/.pi/pi-acp``）具有比外科手术更宽的爆炸半径
        ``CODEX_HOME`` / ``CLAUDE_CONFIG_DIR``：它还会重新定位 CLI 子进程本身生成的任
        何内容所看到的主目录（``git``
        、``npm``、
        ``node``，贝壳 — e.g。 ``~/.gitconfig``、``~/.npmrc``、npm 缓存）。 这被认为
        是孤立双子座的代价； 需要更窄范
        围的呼叫者可以为双子座取消隔离。

        Ordering: 这个运行 *之后* 的 ``secret_registry`` 注射在
        ：方法：`_start_acp_server`。 搬迁现在是凭据-盲目的
        （auth-conflict strip 是在 ``CLAUDE_CODE_OAUTH_TOKEN`` 上键入的，而不是在配置
        目录上），因此它设置的 dat
        a-dir 变量永远不会影响 auth。
        """
        provider = detect_acp_provider_by_command(self.acp_command)
        if provider is None or provider.data_dir_env_var is None:
            return
        env_var = provider.data_dir_env_var
        data_dir = self._acp_file_secret_dir(state, provider.key)
        data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        env[env_var] = str(data_dir)

    def _resolved_provider(self) -> ACPProviderInfo | None:
        """此智能体运行的提供程序，首选权威密钥。

        ``acp_server`` 由 ``ACPAgentSettings.create_agent()`` 设置，并且是在自定义或
        别名
        ``acp_command`` 中幸存下来的唯一身份； 该命令是直接构造的智能体的回退方案。
        """
        return get_acp_provider(
            self.acp_server or ""
        ) or detect_acp_provider_by_command(self.acp_command)

    def _active_file_secrets(self) -> list[ACPFileSecretSpec]:
        """适用于此智能体运行的提供程序的文件机密规范。

        删除了 * 另一个注册提供商的 * 保留凭据，保留其他一切，因此上游添加的 harness
        不能改变这个提供商的对话如何处理机密（见 #4923）。 几个提
        供商共享的名称仍然存在：它也是该提供商的。

        故意不进行溯源测试。 :attr:`acp_file_secrets` 默认为注册表，但是一个已持久化
        对话携带了当时写入时的任何内容，因此与今天的默认值进行
        比较会将一个老的列表视为调用者重写，并在升级后自动终止作用域。 按所有权过滤不
        需要这样的区别，也不需要一个 [spec] CLI outside the 注
        册表它总是由没有人拥有。

        无法识别的服务器保留所有规格，匹配
        :meth:`_strip_conflicting_env`: 没有身份我们无法分辨谁
        凭据属于保留名称。
        """
        provider = self._resolved_provider()
        if provider is None:
            return list(self.acp_file_secrets)
        own = {spec.secret_name for spec in provider.file_secrets}
        owned_elsewhere = {
            spec.secret_name
            for key, info in ACP_PROVIDERS.items()
            if key != provider.key
            for spec in info.file_secrets
        } - own
        return [
            spec
            for spec in self.acp_file_secrets
            if spec.secret_name not in owned_elsewhere
        ]

    def _strip_conflicting_env(self, env: dict[str, str]) -> None:
        """删除会破坏该提供者自己的凭据的环境变量。

        作用域为已解析提供程序的：attr:`ACPProviderInfo.env_conflicts`：同一变量是另
        一个提供程序的 *凭据*（其
        ``api_key_env_var`` 是 ``ANTHROPIC_API_KEY``)，将其剥离后就没有任何可验证的内
        容了。

        一个未识别的服务器保留了保守的集合：没有身份，我们无法分辨谁凭据一个主导变量
        属于，以及一个直接构建的 ``ACPAgent`` 运行Claude
        Code就是指规则(#3588)。
        """
        provider = self._resolved_provider()
        if provider is not None:
            specs: tuple[ACPEnvConflictSpec, ...] = provider.env_conflicts
        else:
            specs = tuple(
                spec for info in ACP_PROVIDERS.values() for spec in info.env_conflicts
            )
        for spec in specs:
            if spec.dominant in env:
                for name in spec.strip:
                    env.pop(name, None)

    def _materialise_file_secrets(
        self, state: ConversationState, env: dict[str, str]
    ) -> None:
        for spec in self._active_file_secrets():
            name = spec.secret_name
            with self._file_credential_lock:
                replace_existing = (
                    name in self._replace_file_credentials_on_next_materialisation
                )
            binding = self._file_credential_bindings.get(name)
            assert self._executor is not None
            lifecycle = create_file_credential_lifecycle(
                name,
                binding,
                self._executor.run_async,
            )
            if lifecycle is not None:
                with self._file_credential_lock:
                    if self._closed:
                        raise CredentialSyncError("Credential binding is closed.")
                try:
                    lifecycle.materialize(state.secret_registry, env)
                    durable_path = (
                        self._acp_file_secret_dir(state, spec.subdir) / spec.filename
                    )
                    try:
                        durable_path.unlink(missing_ok=True)
                    except OSError as exc:
                        raise CredentialSyncError(
                            "Durable credential copy could not be removed."
                        ) from exc
                except BaseException:
                    env.pop("CODEX_HOME", None)
                    lifecycle.discard()
                    raise
                with self._file_credential_lock:
                    closed = self._closed
                    if not closed:
                        self._file_credential_lifecycles[name] = lifecycle
                        self._replace_file_credentials_on_next_materialisation.discard(
                            name
                        )
                if closed:
                    env.pop("CODEX_HOME", None)
                    lifecycle.discard()
                    raise CredentialSyncError("Credential binding is closed.")
                continue

            value = state.secret_registry.get_secret_value(name)
            if not value:
                continue
            directory = self._acp_file_secret_dir(state, spec.subdir)
            target = directory / spec.filename
            self._materialise_file_secret(
                spec,
                env,
                directory,
                target,
                value,
                replace_existing=replace_existing,
            )
            with self._file_credential_lock:
                self._replace_file_credentials_on_next_materialisation.discard(name)

    def _materialise_file_secret(
        self,
        spec: ACPFileSecretSpec,
        env: dict[str, str],
        directory: Path,
        target: Path,
        value: str,
        *,
        replace_existing: bool = False,
    ) -> None:
        name = spec.secret_name
        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            directory.chmod(0o700)
            directory.parent.chmod(0o700)
            preserve_existing = (
                not replace_existing and target.is_file() and target.stat().st_size > 0
            )
            if preserve_existing:
                target.chmod(0o600)
                logger.info(
                    "ACP file-secret %r already present at %s; preserving "
                    "(seed-if-absent)",
                    name,
                    target,
                )
            else:
                write_secret_file(target, value)
                logger.info("Materialised ACP file-secret %r -> %s", name, target)
        except (OSError, UnicodeError):
            logger.exception(
                "Failed to materialise ACP file-secret %r under %s",
                name,
                directory,
            )
            raise
        env[spec.env_var] = str(directory if spec.env_points_to == "dir" else target)
        for companion in spec.warn_if_unset:
            if not env.get(companion):
                logger.warning(
                    "ACP file-secret %r materialised but %s is unset; the "
                    "provider may fail to authenticate until it is configured",
                    name,
                    companion,
                )

    @staticmethod
    def _log_file_credential_failures(
        operation: str, failures: dict[str, Exception]
    ) -> None:
        for name, error in failures.items():
            logger.warning(
                "Failed to %s ACP file credential %r",
                operation,
                name,
                exc_info=(type(error), error, error.__traceback__),
            )

    @staticmethod
    def _raise_first_file_credential_failure(
        operation: str, failures: dict[str, Exception]
    ) -> None:
        if not failures:
            return
        first_name = next(iter(failures))
        remaining = dict(failures)
        first_error = remaining.pop(first_name)
        ACPAgent._log_file_credential_failures(operation, remaining)
        raise first_error

    def _sync_file_credentials_collect(self) -> dict[str, Exception]:
        failures: dict[str, Exception] = {}
        with self._file_credential_lock:
            lifecycles = tuple(self._file_credential_lifecycles.items())
        for name, lifecycle in lifecycles:
            try:
                lifecycle.flush()
            except Exception as error:
                failures[name] = error
        return failures

    def _sync_file_credentials(self) -> None:
        """刷新 ACP 文件凭据。"""
        failures = self._sync_file_credentials_collect()
        self._raise_first_file_credential_failure("sync", failures)

    def _track_file_credentials_for_masking(self) -> None:
        with self._file_credential_lock:
            lifecycles = tuple(self._file_credential_lifecycles.items())
        for name, lifecycle in lifecycles:
            try:
                lifecycle.track_current()
            except CredentialBindingError:
                raise
            except Exception as error:
                raise CredentialSyncError(
                    f"ACP file credential {name!r} could not be synchronized."
                ) from error

    def _bind_file_credential_masking(self) -> None:
        client = self._client
        if client is None:
            return
        agent_ref = weakref.ref(self)

        def track_file_credentials() -> None:
            agent = agent_ref()
            if agent is not None:
                agent._track_file_credentials_for_masking()

        client.before_mask = track_file_credentials

    async def _flush_file_credentials(self) -> None:
        with self._file_credential_lock:
            if not self._file_credential_lifecycles:
                return
        await asyncio.to_thread(self._sync_file_credentials)

    def _flush_file_credentials_blocking(self) -> None:
        self._sync_file_credentials()

    def _release_file_credentials_collect(self) -> dict[str, Exception]:
        failures: dict[str, Exception] = {}
        with self._file_credential_lock:
            lifecycles = tuple(self._file_credential_lifecycles.items())
        for name, lifecycle in lifecycles:
            try:
                lifecycle.close()
            except Exception as error:
                failures[name] = error
            else:
                with self._file_credential_lock:
                    if self._file_credential_lifecycles.get(name) is lifecycle:
                        self._file_credential_lifecycles.pop(name)
        return failures

    def _release_file_credentials(self) -> None:
        """发布范围 ACP 文件凭据源。"""
        failures = self._release_file_credentials_collect()
        self._raise_first_file_credential_failure("release", failures)

    def _startup_timeout_message(self) -> str:
        return (
            f"ACP startup timed out after {self.acp_startup_timeout:.0f}s "
            "waiting for the ACP server to spawn, authenticate, and "
            "create/load a session"
        )

    def _start_acp_server(self, state: ConversationState) -> None:
        """启动 ACP 子进程并初始化会话。"""
        client = _OpenHandsACPBridge()
        self._client = client
        # 在对话的生命周期内绑定机密掩码。 是衍生出来的
        # from state.secret_registry (stable for the conversation) and touches
        # 只有注册表，因此它具有None的跨线程/状态-锁危险，这些危险使得on_event/on_token
        # 严格每回合。 _reset_client_for_turn这里绑定（而不是在每回合AND）保持可用，供
        # ask_agent()分支使用，这些分支运行在共享客户端上，可能在没有step()/astep()回合
        # 活跃时触发。
        #
        client.mask = state.secret_registry.mask_secrets_in_output
        self._bind_file_credential_masking()

        # 构建子进程环境。 优先级，最高的在前：
        #   state.secret_registry > os.environ > default_environment
        #
        # 对话凭据故意的 OVERRIDE ambient os.environ一个明确的每会话/提供者机密必须胜过
        # 同名的变量智能体服务器自身的环境。
        #
        # agent_context.secrets 被植入 secret_registry at LocalConversation.__init__ （
        # 优先级低于） request.secrets, 所以注册表现在是所有内容的唯一渠道机密包括提供者
        # 凭据 （根据提供者的环境变量名称）。
        #
        env = default_environment()
        env.update(os.environ)
        _strip_inherited_npm_env(env)
        # 保留的文件内容凭据机密 （Codex auth.json，Gemini Vertex SA — 见
        # _materialise_file_secrets）写入磁盘，而不是作为环境变量注入，因此在以下的纯环
        # 境注入中排除它们（大块）的名称。 物化仅设置路径环境变量。
        #
        file_secret_names = self._present_file_secret_names(state)
        # 注入整个注册表：ACP CLI是一个我们无法按命令扫描的黑盒子（不像常规智能体的bash
        # 工具），因此凭据必须提前交付。 注册表值覆盖环境 os.environ。 跳过文件机密（具
        # 体化到下面的磁盘）。
        #
        env.update(
            state.secret_registry.get_all_secrets_as_env_vars(exclude=file_secret_names)
        )
        if self.acp_isolate_data_dir:
            self._isolate_acp_data_dir(state, env)

        # 将保留的文件内容机密物化到磁盘并将其数据目录环境变量 (CODEX_HOME /
        # GOOGLE_APPLICATION_CREDENTIALS) 指向写入的文件。
        #
        self._materialise_file_secrets(state, env)
        # 剥离 CLAUDECODE，以便嵌套的 Claude Code 实例不会拒绝启动
        env.pop("CLAUDECODE", None)

        self._strip_conflicting_env(env)

        command = self.acp_command[0]
        args = list(self.acp_command[1:]) + list(self.acp_args)
        # 法典忽略OPENAI_BASE_URL； 将其转换为适配器读取的配置密钥。 帮助器返回一个仅限
        # 子环境，并且永远不会改变上面完全组装的映射。
        #
        env = _with_codex_base_url(command, args, env)

        working_dir = str(state.workspace.working_dir)
        provider = detect_acp_provider_by_command(self.acp_command)
        packages = _npx_packages(self.acp_command)
        if provider is not None and packages:
            env["npm_config_cache"] = str(self._acp_npm_cache_dir(state))
            try:
                self._executor.run_async(
                    self._warm_npx_cache(packages, provider.key, env, working_dir),
                    timeout=_ACP_NPX_CACHE_WARM_TIMEOUT + 5,
                )
            except Exception as error:
                logger.warning(
                    "ACP provider npx cache warm failed: provider=%s; "
                    "continuing with normal startup: %s",
                    provider.key,
                    error,
                )

        # 先前的 ACP 会话 ID — 通常会在智能体后继续存在 - 服务器通过
        # ConversationState.agent_state 重新启动（已序列化进入 base_state.json）。 它的
        # 存在是恢复的信号； 它的缺席意味着新的开始。 ACP 服务器密钥持久化 by ``cwd``；
        # 如果工作区移动，我们会删除 id，这样我们就不会意外恢复（或静默加载）服务器与不
        # 同目录关联的会话。
        #
        # ``acp_resume_session_id``（在智能体配置上设置）优先于 FS-已持久化 id。 这使得
        # 云部署可以将ID镜像到一个持久存储中，并在第一次启动新的沙盒时将其返回，即使
        # ``base_state.json``与之前的沙盒文件系统一起被擦除。
        #
        # 注意工作目录保护中的不对称性：对于 FS-已持久化我们有 cwd，它是在那里创建的，可
        # 以拒绝加载，因为继续加载错误的会话是灾难性的。 对于一个明确的
        # ``acp_resume_session_id`` 我们做 *不* 将该记录保存为 cwd — 合同是“调用者知道他
        # 们正在做什么”（应用服务器只对会话的沙箱总是位于同一位置的会话进行ID映射）
        # ``working_dir``). 因此，我们假设兼容 cwd，并让  ACP 服务器自身
        # ``session/load``  验证成为最后一道防线：服务器端的 cwd 不匹配会返回一个
        # ``ACPRequestError``已经捕获并回退到 ``new_session`` — 与遗失的 ID 同样的恢复路
        # 径。
        #
        fs_session_id: str | None = state.agent_state.get("acp_session_id")
        fs_session_cwd: str | None = state.agent_state.get("acp_session_cwd")
        if self.acp_resume_session_id and self.acp_resume_session_id != fs_session_id:
            logger.info(
                "Using explicit acp_resume_session_id (%s); "
                "filesystem agent_state had id=%s",
                _fingerprint_session_id(self.acp_resume_session_id),
                _fingerprint_session_id(fs_session_id),
            )
            prior_session_id: str | None = self.acp_resume_session_id
            prior_session_cwd: str | None = working_dir
        else:
            prior_session_id = fs_session_id
            prior_session_cwd = fs_session_cwd
        if prior_session_id is not None and prior_session_cwd not in (
            None,
            working_dir,
        ):
            logger.warning(
                "ACP session %s was created with cwd=%s; current cwd=%s differs, "
                "starting a fresh session instead of resuming",
                _fingerprint_session_id(prior_session_id),
                prior_session_cwd,
                working_dir,
            )
            prior_session_id = None

        async def _init() -> tuple[
            str, str, str, str | None, list[ACPModelInfo] | None, bool
        ]:
            # 直接生成子进程，这样我们就可以安装一个过滤阅读器，它会跳过一些 ACP 服务器
            # 的非 JSON-RPC 行（e.g. claude-code-ACP v0.1.x) 写入标准输出。
            #
            process = await asyncio.create_subprocess_exec(
                command,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                limit=_STREAM_READER_LIMIT,
            )
            assert process.stdin is not None
            assert process.stdout is not None
            assert process.stderr is not None

            # 将子进程标准输出包装在过滤读取器中，该读取器仅传递以“{”开头的行（JSON-RPC
            # 消息）。
            #
            filtered_reader = asyncio.StreamReader(limit=_STREAM_READER_LIMIT)
            stdout_filter_task = asyncio.get_event_loop().create_task(
                _filter_jsonrpc_lines(process.stdout, filtered_reader)
            )
            stderr_log_task = asyncio.get_event_loop().create_task(
                _log_acp_subprocess_stderr(process.stderr)
            )

            conn = _ACPClientConnection(
                client,
                process.stdin,  # 写入子进程
                filtered_reader,  # 读取过滤后的输出
            )

            # 立即跟踪自进程/连接，以便如果  *later* 初始化步骤失败了e.g. 简历模型重试超
            # 时或服务器错误)， init_state()'s _cleanup() 他们仍然可以拆卸而不是泄露子进
            # 程/连接。 会话初始化门控键 _session_id (最后分配的，只有在完全成功时才使用
            # )，因此，这里有一个早期的 _conn 不会妨碍智能体在 _init 完成之前看起来就准
            # 备好。
            #
            self._process = process
            self._conn = conn
            self._filtered_reader = filtered_reader
            self._stdout_filter_task = stdout_filter_task
            self._stderr_log_task = stderr_log_task

            # 初始化协议并发现服务器身份
            init_response = await conn.initialize(protocol_version=1)
            agent_name = ""
            agent_version = ""
            if init_response.agent_info is not None:
                agent_name = init_response.agent_info.name or ""
                agent_version = init_response.agent_info.version or ""
            logger.info(
                "ACP server initialized: agent_name=%r, agent_version=%r",
                agent_name,
                agent_version,
            )
            _log_acp_provider_version(agent_name, agent_version)

            # 翻译任何配置的 MCP 服务器到 ACP 协议对象，远程端点（HTTP/SSE） 传输层在初
            # 始化响应中，该服务器所宣称的内容。 同一个列表被传递给两个 new_session 和
            # load_session: load_session 不持久化 prior MCP 设置为服务器端，因此，如果需
            # 要重新发送，或者恢复会话时，会话将无声无息地丢失 MCP 服务器。
            #
            mcp_caps = (
                init_response.agent_capabilities.mcp_capabilities
                if init_response.agent_capabilities is not None
                else None
            )
            session_caps = (
                init_response.agent_capabilities.session_capabilities
                if init_response.agent_capabilities is not None
                else None
            )
            self._additional_directories_supported = (
                session_caps is not None
                and session_caps.additional_directories is not None
            )
            acp_mcp_servers = _mcp_config_to_acp_servers(self.mcp_config, mcp_caps)
            if acp_mcp_servers:
                logger.info(
                    "Forwarding %d MCP server(s) to ACP session: %s",
                    len(acp_mcp_servers),
                    [s.name for s in acp_mcp_servers],
                )

            # 如果服务器需要，则进行身份验证。 一些 ACP 服务器 (e.g. codex-ACP）需要在会
            # 话创建之前进行显式身份验证调用。 我们从进程可用的环境变量中自动检测方法。
            #
            auth_methods = init_response.auth_methods or []
            if auth_methods:
                method_id = _select_auth_method(auth_methods, env)
                if method_id is not None:
                    logger.info("Authenticating with ACP method: %s", method_id)
                    auth_kwargs: dict[str, Any] = {}
                    # gemini-CLI：通过网关 baseUrl 通过 LiteLLM 代理路由 API 呼叫。
                    # claude-智能体-ACP 和 codex-ACP 直接从环境变量读取其提供者库 URL。
                    #
                    if method_id == "gemini-api-key":
                        provider = detect_acp_provider_by_agent_name(agent_name)
                        base_url_var = (
                            provider.base_url_env_var if provider is not None else None
                        )
                        if base_url_var:
                            base_url = env.get(base_url_var)
                            if base_url:
                                auth_kwargs["gateway"] = {"baseUrl": base_url}
                    try:
                        await asyncio.wait_for(
                            conn.authenticate(method_id=method_id, **auth_kwargs),
                            timeout=_ACP_AUTH_TIMEOUT,
                        )
                    except TimeoutError as exc:
                        if method_id == "chat-gpt":
                            raise ACPFileCredentialNeedsReauthError(
                                "ChatGPT authentication did not complete in time. "
                                "Please sign in again."
                            ) from exc
                        raise TimeoutError(
                            f"ACP authentication with {method_id!r} timed out after "
                            f"{_ACP_AUTH_TIMEOUT:g}s."
                        ) from exc
                    except ACPRequestError as exc:
                        if method_id != "chat-gpt" or not _acp_error_indicates_auth(
                            exc
                        ):
                            raise
                        raise ACPFileCredentialNeedsReauthError(
                            "ChatGPT authentication needs to be refreshed."
                        ) from exc
                    await self._flush_file_credentials()
                else:
                    # 我们无法执行的服务器仍可以通过种子认证凭据文件或环境读出的提供者密
                    # 钥 — 因此，当文件或提供者密钥都存在时，我们无法进行的登录警告都是
                    # 无意义的噪音。
                    #
                    auth_provider = (
                        self._resolved_provider()
                        or detect_acp_provider_by_agent_name(agent_name)
                    )
                    configured = _preconfigured_credentials(
                        auth_provider, self._active_file_secrets(), env
                    )
                    if configured:
                        logger.info(
                            "ACP server offers auth methods %s that cannot be "
                            "performed here; using the already-configured "
                            "credential(s) %s instead",
                            [m.id for m in auth_methods],
                            configured,
                        )
                    else:
                        _warn_auth_selection_failure(auth_methods, env, auth_provider)

            # 如果我们有 ID，则恢复之前的 ACP 会话。 如果服务器忘记了它（状态已擦除、新
            # 主机等），则会转到 new_session，因此对话仍然可以干净地开始。
            #
            # 我们只吞咽 ACPRequestError 这里：这是协议级别的“我不认识这个会话”信号，可
            # 以通过重新开始来恢复。 传输层失败（管道已断开） EOF, 超时，子进程崩溃) 传
            # 播 — 没有可以 fallback 的工作连接，外层 init_state 处理器清理了。
            #
            session_id: str | None = None
            reported_model_id: str | None = None
            available_models: list[ACPModelInfo] | None = None
            if prior_session_id is not None:
                try:
                    load_response = await conn.load_session(
                        cwd=working_dir,
                        session_id=prior_session_id,
                        additional_directories=self._skill_directories(),
                        mcp_servers=acp_mcp_servers,
                    )
                    session_id = prior_session_id
                    # load_session经常省略模型块； 已持久化会话创建时检测到的机制作为后
                    # 备方案，确保配置选项会话可以通过正确的调用重新应用，而不是默认使用
                    #  set_session_model 并默默地运行服务器默认。
                    #
                    persisted_via_config_option = bool(
                        state.agent_state.get("acp_model_via_config_option", False)
                    )
                    (
                        reported_model_id,
                        available_models,
                        self._model_via_config_option,
                    ) = _extract_session_models(
                        load_response,
                        default_via_config_option=persisted_via_config_option,
                    )
                    logger.info(
                        "Resumed ACP session %s (cwd=%s)",
                        _fingerprint_session_id(session_id),
                        working_dir,
                    )
                except ACPRequestError as e:
                    logger.warning(
                        "ACP load_session(%s) failed (%s); starting a fresh session",
                        _fingerprint_session_id(prior_session_id),
                        e,
                    )

            # 跟踪 ``acp_model`` 是否确实被推送到服务器，以便
            # ``current_model_id`` 以下部分可以保持诚实：一个未到达服务器的呼叫重定向（
            # 在新会话中，未知提供者，或者一个恢复的会话） ``set_session_model`` 服务器
            # 拒绝的必须不被呈现为实时模型。
            #
            override_applied = False
            if session_id is None:
                # 新的会议。 为会话选项构建 _meta 内容 (e.g. 型号选择）。 new_session()
                # 的额外 kwargs 成为 JSON-RPC 请求中的 _meta 字典 - 将不包装在 _meta= 中
                # （即双嵌套）。
                #
                session_meta = build_session_model_meta(agent_name, self.acp_model)
                response = await conn.new_session(
                    cwd=working_dir,
                    additional_directories=self._skill_directories(),
                    mcp_servers=acp_mcp_servers,
                    **session_meta,
                )
                session_id = response.session_id
                # 检测服务器通告的模型选择协议（在同一扫描中），以便 init 和以后的运行时
                # 开关使用正确的调用。
                #
                (
                    reported_model_id,
                    available_models,
                    self._model_via_config_option,
                ) = _extract_session_models(response)
                # 每个内置提供程序的初始模型协议调用（codex、gemini、claude-code）。
                # CLIs 这个 pinned claude/codex 忽略了 _meta，所以这个协议调用实际上应用
                # 了模型 (#3654) —— 通过 set_config_option 对于基于 configOptions 的服务
                # 器，否则 set_session_model；_meta 仅保留作为向后兼容的旧版 claude CLIs
                # 。
                #
                applied_via_call = await _maybe_set_session_model(
                    conn,
                    agent_name,
                    session_id,
                    self.acp_model,
                    via_config_option=self._model_via_config_option,
                )
                # set_session_model 是 acp_model 到达服务器的权威信号。 _meta 对固定的
                # claude CLI 是无操作的，因此它本身不能声明覆盖已生效。 （对于 claude+
                # acp_model ，两者总是一致的：调用返回 True 或在我们到达这里之前引发。）
                #
                override_applied = applied_via_call
            else:
                # 恢复会议。 load_session() 不携带模型 _meta，因此通过运行时切换能力重新
                # 应用已持久化（可能在运行时切换的）acp_model —— 否则恢复的实时会话将运
                # 行在服务器默认模型上，而已序列化状态则声称切换了模型。
                # ``_model_via_config_option`` 已设定
                #
                # from the load_session response above.
                override_applied = await _reapply_session_model_on_resume(
                    conn,
                    agent_name,
                    session_id,
                    self.acp_model,
                    via_config_option=self._model_via_config_option,
                )

            # 解析智能体将实际使用的模型。
            current_model_id = (
                self.acp_model
                if (self.acp_model and override_applied)
                else reported_model_id
            )

            # 解决权限模式。 每个已知的提供商都有自己的模式 ID； 未知/自定义服务器获取
            # None — 跳过调用，而不是发送他们无法识别的特定于提供者的字符串。
            #
            provider = detect_acp_provider_by_agent_name(agent_name)
            mode_id = self.acp_session_mode or (
                provider.default_session_mode if provider else None
            )
            if mode_id is not None:
                logger.info("Setting ACP session mode: %s", mode_id)
                await conn.set_session_mode(mode_id=mode_id, session_id=session_id)

            return (
                session_id,
                agent_name,
                agent_version,
                current_model_id,
                available_models,
                override_applied,
            )

        # _conn / _process / _filtered_reader 被分配给 _init() 内的实例，因此可以清除中
        # 间初始化故障； 仅返回仅成功的字段（包括已解析的模型状态）。
        #
        try:
            (
                self._session_id,
                self._agent_name,
                self._agent_version,
                self._current_model_id,
                self._available_models,
                self._model_override_applied,
            ) = self._executor.run_async(_init, timeout=self.acp_startup_timeout)
        except TimeoutError:
            # run_async自己的TimeoutError不携带消息(anyio.fail_after)； 提出一个描述性的
            # ，这样 _acp_error_detail (str(exc)) 就不是空白。
            #
            raise TimeoutError(self._startup_timeout_message()) from None
        self._working_dir = working_dir
        self._flush_file_credentials_blocking()

    def _reset_client_for_turn(
        self,
        on_token: ConversationTokenCallbackType | None,
        on_event: ConversationCallbackType,
        prompt: Any = None,
        mask: Callable[[str], str] | None = None,
    ) -> None:
        """重置每轮客户端状态并（重新）实时连接回调。

        在 ``step()`` 开始处调用，并在提示词循环内的每个重试上再次调用，以便三个回调
        (``on_token``, ``on_event``,
        ``on_activity``) 在 ``reset()`` 清除它们后，在新回合中留在同步中。
        ``on_event`` 从内部发射
        ``_OpenHandsACPBridge.session_update`` 作为工具调用通知到达时，消费者会看到
        ACPToolCallEvents 以流
        的形式播放，而不是单个结束回合的爆发。 机密模糊化器绑定一次
        ``_start_acp_server``（对话稳定），不在这里。
        """
        self._client.trace.abandon()
        self._client.reset()
        self._client.trace = ACPTurnTrace(
            acp_server=self.acp_server,
            model_id=self._current_model_id,
            mask=mask,
        )
        self._client.trace.start_turn(prompt)
        self._client.on_token = on_token
        self._client.on_event = on_event
        self._client.on_activity = self._on_activity
        # 为此尝试重新启动空闲超时时钟，以便从发送（或重试）开始测量截止时间，而不是从过
        # 时的值开始测量。
        #
        self._client.arm_activity_clock()

    def _cancel_inflight_tool_calls(self) -> None:
        """对于每个工具调用，发出一个终端 ``failed`` ACPToolCallEvent
        在尚未达到最终状态的累加器中。

        ACP 服务器在重试回合中铸造新的 ``tool_call_id``，因此任何
        ``pending`` / ``in_progress`` 在失败尝试中已经流过的事件将会被弃置
        ``state.events`` — 不晚的通知重用他们的
         ID，以及通过去重的消费者 ``tool_call_id`` [+ "last-seen status wins" would
         keep them spi
        nning forever。] 该方法在擦除内存累加器之前关闭了这些卡片重试 / turn abort.

        捕获桥梁的``on_event`` 回调，然后断开桥梁，发出合成终端事件，以防止废弃门户提
        示词的后续更新落在这些失败之后。 无操作如果
        ``on_event`` 从未设置过 (e.g. 单独运行桥梁的测试）。
        """
        on_event = self._client.on_event
        self._clear_turn_callbacks()
        if on_event is None:
            return
        for tc in self._client.accumulated_tool_calls:
            status = tc.get("status")
            if status in _TERMINAL_TOOL_CALL_STATUSES:
                continue
            try:
                on_event(
                    ACPToolCallEvent(
                        tool_call_id=tc["tool_call_id"],
                        title=tc["title"],
                        status="failed",
                        tool_kind=tc.get("tool_kind"),
                        raw_input=tc.get("raw_input"),
                        raw_output=tc.get("raw_output"),
                        content=tc.get("content"),
                        is_error=True,
                    )
                )
            except Exception:
                logger.debug(
                    "Failed to emit supersede event for %s",
                    tc.get("tool_call_id"),
                    exc_info=True,
                )

    def _flush_inflight_tool_calls_as_completed(self) -> None:
        """每积累一次，发出一个终端 ``completed`` ACPToolCallEvent
        工具调用仍处于非终端状态。

        提示词成功返回，因此服务器打开了一个工具卡但从未关闭（它发送了
        ``ToolCallStart``但没有终端
        ``ToolCallProgress``它被视为已完成。 自今以来持久化恰好一个早期的 ``started``
         事件和每次调用一个终端事件，这保证了动作->
        观测结果  *every* 缺少它时，一个不关闭帧的服务器将留下早期 ``started`` 将事件
        作为最后一个单词，松散的画布渲染门将显示卡片永不停止旋转
        。 重用
        ``_emit_tool_call_event`` 因此截断和错误吞没与实时终端路径匹配。 一旦每次调用
        都已终止，则无操作（常见情况，因为
        ``conn.prompt`` 仅在其工具运行后返回）。
        """
        for tc in self._client.accumulated_tool_calls:
            if tc.get("status") in _TERMINAL_TOOL_CALL_STATUSES:
                continue
            tc["status"] = "completed"
            self._client._emit_tool_call_event(tc)

    async def _arequest_session_cancel(self) -> None:
        """异步等待取消发送的 _request_session_cancel 变体。"""
        if self._conn is None or self._executor is None or self._session_id is None:
            return
        conn = self._conn
        session_id = self._session_id

        async def _cancel() -> None:
            result = conn.cancel(session_id)
            if inspect.isawaitable(result):
                await result

        try:
            future = self._executor.portal.start_task_soon(_cancel)
            await asyncio.wait_for(
                asyncio.shield(asyncio.wrap_future(future)),
                timeout=_ACP_CANCEL_DRAIN_TIMEOUT,
            )
        except TimeoutError:
            logger.warning(
                "Timed out sending ACP session cancel; restarting ACP session"
            )
            self._restart_session_on_next_turn = True
        except Exception:
            logger.warning("Failed to send ACP session cancel", exc_info=True)

    async def _drain_cancelled_prompt(
        self,
        future: Future[PromptResponse | None] | None,
    ) -> _PromptDrainResult:
        """在重新连线之前让已取消/超时的门户提示词停顿。"""
        if future is None:
            return _PromptDrainResult(
                drained=True, completed=False, response=None, error=None
            )
        if future.cancelled():
            return _PromptDrainResult(
                drained=True, completed=False, response=None, error=None
            )
        if future.done():
            try:
                return _PromptDrainResult(
                    drained=True,
                    completed=True,
                    response=future.result(),
                    error=None,
                )
            except BaseException as exc:
                return _PromptDrainResult(
                    drained=True, completed=True, response=None, error=exc
                )
        try:
            response = await asyncio.wait_for(
                asyncio.shield(asyncio.wrap_future(future)),
                timeout=_ACP_CANCEL_DRAIN_TIMEOUT,
            )
            return _PromptDrainResult(
                drained=True, completed=True, response=response, error=None
            )
        except asyncio.CancelledError:
            if future.cancelled():
                return _PromptDrainResult(
                    drained=False, completed=False, response=None, error=None
                )
            raise
        except TimeoutError:
            logger.warning(
                "Timed out waiting for cancelled ACP prompt to drain; "
                "the ACP session will be restarted before the next turn"
            )
            return _PromptDrainResult(
                drained=False, completed=False, response=None, error=None
            )
        except BaseException as exc:
            return _PromptDrainResult(
                drained=future.done(), completed=True, response=None, error=exc
            )

    def _restart_session_after_drain_timeout(
        self,
        state: ConversationState,
        on_event: ConversationCallbackType,
    ) -> None:
        """在提示词取消后无法停顿后重新启动 ACP。"""
        logger.warning("Restarting ACP session after cancelled prompt drain timeout")
        self._clear_turn_callbacks()
        self._cleanup()
        self._initialized = False
        # 本地耗尽超时意味着取消的提示词并未在我们短暂的宽限期内停顿； 它不能证明 ACP 服
        # 务器丢失了其已持久化会话。 保留会话 ID，以便重新启动的子进程可以 load_session(
        # ) 并保留对话内存。
        #
        self.init_state(state, on_event=on_event)
        self._restart_session_on_next_turn = False

    async def _arestart_session_after_drain_timeout(
        self,
        state: ConversationState,
        on_event: ConversationCallbackType,
    ) -> None:
        """重新启动 ACP，而不阻塞异步对话循环。"""
        # 重新启动调用 init_state()，它可以通过 HTTP 环回同步解析 LookupSecret 值到同一
        # Agent Server。 出于同样的原因，使其远离服务器循环，LocalConversation.arun() 卸
        # 载初始 _ensure_agent_ready() 路径。
        #
        await asyncio.to_thread(
            self._restart_session_after_drain_timeout, state, on_event
        )

    def _request_session_cancel(self) -> None:
        """请求 ACP 服务器取消活动会话提示词。"""
        if self._conn is None or self._executor is None or self._session_id is None:
            return
        conn = self._conn
        session_id = self._session_id

        async def _cancel() -> None:
            result = conn.cancel(session_id)
            if inspect.isawaitable(result):
                await result

        try:
            self._executor.portal.start_task_soon(_cancel)
        except Exception:
            logger.warning("Failed to send ACP session cancel", exc_info=True)

    def _build_acp_prompt(
        self, event: MessageEvent
    ) -> list[TextContentBlock | ImageContentBlock] | None:
        """为一个用户回合构建 ACP 内容块。"""
        message = event.to_llm_message()
        blocks: list[TextContentBlock | ImageContentBlock] = []
        for content in message.content:
            if isinstance(content, TextContent) and content.text.strip():
                blocks.append(text_block(content.text))
            elif isinstance(content, ImageContent):
                for url in content.image_urls:
                    acp_block = _image_url_to_acp_block(url)
                    if acp_block is not None:
                        blocks.append(acp_block)
        if (
            self._suffix_install_state == "pending_first_prompt"
            and self._installed_suffix
        ):
            blocks.append(text_block(self._installed_suffix))
            # 注意：在这里将不翻转``_suffix_install_state``。 如果
            # 在 ACP 服务器 ``asyncio.wait_for`` 或 ``task.cancel()`` 之前，异步路径上的
            #  [caller (step/astep)] 取消或失败，本地状态会说“已安装”，而服务器却从未收
            # 到后缀——下一回合会跳过它。 实际的转换发生在
            # ``_commit_suffix_installation`` 中，一旦提示词成功返回，就会从
            # ``_finalize_successful_turn`` 调用。
            #
        if not blocks:
            return None
        return blocks

    def _commit_suffix_installation(self, state: ConversationState) -> None:
        """转弯完成后，将后缀标记为已安装。

        从 ``_finalize_successful_turn`` 调用，因此转换仅在 ACP 服务器实际收到后缀后
        发生。 将
        ``acp_suffix_installed=True`` 保留到 ``state.agent_state`` 中，以便随后的智能
        体服务器重新启动，读回相同
        的内容
        ``ConversationState``，可以判断后缀是否确实已安装（而不是仅从存在来推断）
        ``acp_session_id``，无论第一个提示词是否成功，会话创建时都是已持久化）。 幂等
        ：当已经 ``installed`` 或没有要安装的后缀时可
        以安全调用。
        """
        if self._suffix_install_state == "pending_first_prompt":
            self._suffix_install_state = "installed"
            state.agent_state = {
                **state.agent_state,
                "acp_suffix_installed": True,
            }

    async def _do_acp_prompt(self, prompt_blocks: list[Any]) -> PromptResponse | None:
        """一ACP``conn.prompt``往返+UsageUpdate同步。

        始终在门户循环上运行（``self._conn`` 所在的位置）。 否重试 / 超时 — 调用者使
        用自己的每次尝试策略进行包装，以便他们可以选择
        ``time.sleep`` (同步) 或
        ``asyncio.sleep`` (异步).

        返回类型允许 ``None``，因为 ACP 服务器允许返回空主体（测试模拟对象也可以）；
        下游
        ``_finalize_successful_turn`` 已接受 ``PromptResponse | None``。
        """
        if self._conn is None or self._session_id is None:
            msg = "ACPAgent has no live ACP session; call init_state() first"
            raise RuntimeError(msg)
        conn = self._conn
        session_id = self._session_id
        usage_sync = self._client.prepare_usage_sync(session_id)
        response = await conn.prompt(session_id=session_id, prompt=prompt_blocks)
        if self._client.get_turn_usage_update(session_id) is None:
            try:
                await asyncio.wait_for(usage_sync.wait(), timeout=_USAGE_UPDATE_TIMEOUT)
            except TimeoutError:
                logger.warning(
                    "UsageUpdate not received within %.1fs for session %s",
                    _USAGE_UPDATE_TIMEOUT,
                    _fingerprint_session_id(session_id),
                )
        return response

    def _idle_timeout_message(self) -> str:
        return (
            f"ACP prompt timed out after {self.acp_prompt_timeout:.0f}s "
            "with no activity from the ACP server"
        )

    async def _await_with_idle_deadline(
        self,
        awaitable: Awaitable[PromptResponse | None],
        *,
        cancel_on_exit: bool,
    ) -> PromptResponse | None:
        """Await *awaitable*，仅在一段不活动后才中止。

        截止日期是*空闲* 超时，而不是硬转截止日期：任何
        ``session_update`` 从 ACP 服务器 (token, 想法，工具调用 start/progress, 使用)
         重置
        ``acp_prompt_timeout``，因此一个持续进行的智能体会一直运行，直到它继续进行，
        而一个真正静默（挂起）的服务器在空闲窗口之后仍然被切断。
        这就是使长时间运行的 ACP 命令保持活动状态的原因（问题智能体-canvas#1245）。

        ``asyncio.wait``（不是 ``wait_for``）驱动轮询，因此空闲检查切片的流逝永远不会
        取消底层提示词 — 只有 True 空闲周期会引发
         ``TimeoutError``。 ``cancel_on_exit`` 控制清理：同步路径通过``True`` 传递给
         取消它所拥有的提示词协程。 异步路
        径通过 ``False``，因为门户任务必须在 ``astep`` 的 ``session/cancel`` + 排水处
        理程序中生存。
        """
        idle_limit = self.acp_prompt_timeout
        fut = asyncio.ensure_future(awaitable)
        try:
            while True:
                remaining = idle_limit - self._client.seconds_since_last_activity()
                if remaining <= 0:
                    raise TimeoutError(self._idle_timeout_message())
                # 当提示词完成或切片结束时，wait() 返回，无论哪种方式，fut 都保持不变。
                #
                await asyncio.wait({fut}, timeout=remaining)
                if fut.done():
                    return fut.result()
                # 切片已过：仅当服务器在此期间没有产生任何内容时才放弃，否则循环将重新准
                # 备一个新窗口。
                #
                if self._client.seconds_since_last_activity() >= idle_limit:
                    raise TimeoutError(self._idle_timeout_message())
        finally:
            if cancel_on_exit and not fut.done():
                fut.cancel()

    async def _await_prompt_response_with_timeout(
        self,
        prompt_future: Future[PromptResponse | None],
    ) -> PromptResponse | None:
        """等待具有空闲（不活动）回合截止时间的 ACP 提示词。

        将门户端提示词 future 包装在：meth:`_await_with_idle_deadline` 中，因此提示词
        仅在
        ``acp_prompt_timeout`` 秒后且没有 ACP 活动时才被放弃。 ``astep`` 中的超时处理
        程序发送
        ``session/cancel`` 并关闭所有飞行工具卡。
        """
        # cancel_on_exit=False: the portal task behind ``prompt_future`` must
        # 比空闲超时 / 取消的寿命更长，因此 astep 的排水管可以观察到它。
        return await self._await_with_idle_deadline(
            asyncio.wrap_future(prompt_future), cancel_on_exit=False
        )

    @staticmethod
    def _prompt_response_was_cancelled(response: PromptResponse | None) -> bool:
        return response is not None and response.stop_reason == "cancelled"

    def _finalize_successful_turn(
        self,
        response: PromptResponse | None,
        elapsed: float,
        state: ConversationState,
        on_event: ConversationCallbackType,
    ) -> None:
        """后提示词簿记+FinishAction/观察发射。"""
        self._client._raise_masking_error()
        # ACP服务器已确认提示词； 提交任何挂起的第一回合后缀安装，以便后续回合不会尝试重
        # 新发送它（因此将来的取消无法取消标记它）。
        #
        self._commit_suffix_installation(state)

        session_id = self._session_id or ""
        usage_update = self._client.pop_turn_usage_update(session_id)
        self._record_usage(
            response,
            session_id,
            elapsed=elapsed,
            usage_update=usage_update,
        )

        # 工具卡已从 _OpenHandsACPBridge.session_update 进行直播：每个 ToolCallStart 一
        # 个早期 ``started`` 事件，每个呼叫一个终端事件。 关闭服务器打开但从未终止的任何
        # 卡牌，以便每个 ``started`` 在回合 FinishAction 落地之前都有其匹配的终端观测结
        # 果。
        #
        self._flush_inflight_tool_calls_as_completed()

        # 在持久化边界处重置拼接的文本：由于它们已经单独被重置，所以机密在两个块之间只重
        # 新组装，因此这是它被捕捉的地方，然后进入已持久化事件流。
        #
        self._track_file_credentials_for_masking()
        mask = state.secret_registry.mask_secrets_in_output
        response_text = mask("".join(self._client.accumulated_text))
        thought_text = mask("".join(self._client.accumulated_thoughts))
        if not response_text:
            response_text = "(No response from ACP server)"

        self._client.trace.finish_turn(
            response_text, thought_text, self._client.accumulated_tool_calls
        )

        # ACP step() 边界是完整的远程助理轮流，而不是部分规划步骤。 发出 FinishAction 来
        # 界定 eval/远程消费者的已完成轮次，匹配 #2190。
        #
        finish_action = FinishAction(message=response_text)
        tc_id = str(uuid.uuid4())
        # ACP 回合的流式文本落在此处，而不是 MessageEvent 中，因此这是使流槽失效的事件。
        #
        minted: dict[str, Any] = {}
        if self._stream is not None and (item_id := self._stream.claim()):
            minted["id"] = item_id
        action_event = ActionEvent(
            **minted,
            source="agent",
            thought=[],
            reasoning_content=thought_text or None,
            action=finish_action,
            tool_name="finish",
            tool_call_id=tc_id,
            tool_call=MessageToolCall(
                id=tc_id,
                name="finish",
                arguments=json.dumps({"message": response_text}),
                origin="completion",
            ),
            llm_response_id=str(uuid.uuid4()),
        )
        on_event(action_event)
        if self._stream is not None and minted:
            self._stream.commit()
        on_event(
            ObservationEvent(
                observation=FinishObservation.from_text(text=response_text),
                action_id=action_event.id,
                tool_name="finish",
                tool_call_id=tc_id,
            )
        )
        state.execution_status = ConversationExecutionStatus.FINISHED

    def _emit_turn_timeout(
        self,
        elapsed: float,
        state: ConversationState,
        on_event: ConversationCallbackType,
    ) -> None:
        """当 ``conn.prompt`` 空闲经过 ``acp_prompt_timeout`` 时出现错误路径。"""
        logger.error(
            "ACP prompt timed out after %.1fs with no activity for the last "
            "%.0fs. The ACP server may have stalled or failed to send the "
            "JSON-RPC response. Accumulated %d text chunks, %d tool calls.",
            elapsed,
            self.acp_prompt_timeout,
            len(self._client.accumulated_text),
            len(self._client.accumulated_tool_calls),
        )
        error_message = Message(
            role="assistant",
            content=[
                TextContent(
                    text=(
                        "ACP prompt timed out after "
                        f"{self.acp_prompt_timeout:.0f}s with no activity from "
                        "the agent. The agent may have stalled, or it may have "
                        "completed its work but the response was not received."
                    )
                )
            ],
        )
        # 关闭因超时尝试而剩余的所有工具卡。
        self._cancel_inflight_tool_calls()
        on_event(MessageEvent(source="agent", llm_message=error_message))
        state.execution_status = ConversationExecutionStatus.ERROR

    def _emit_turn_error(
        self,
        exc: BaseException,
        state: ConversationState,
        on_event: ConversationCallbackType,
    ) -> None:
        """从提示词引发的非超时异常的错误路径。"""
        effective_exc = exc
        try:
            self._track_file_credentials_for_masking()
        except CredentialBindingError as tracking_error:
            effective_exc = tracking_error
            logger.warning(
                "Failed to track ACP credentials during error handling",
            )
        error_detail = _acp_error_detail(effective_exc, state.secret_registry)
        logger.error(
            "ACP prompt failed (%s): %s",
            type(effective_exc).__name__,
            error_detail,
        )
        self._cancel_inflight_tool_calls()
        # 将错误作为智能体消息发出（为检查 MessageEvents 的消费者保留）。
        #
        on_event(
            MessageEvent(
                source="agent",
                llm_message=Message(
                    role="assistant",
                    content=[TextContent(text=f"ACP error: {error_detail}")],
                ),
            )
        )
        # 发出键入的 ConversationErrorEvent，以便 RemoteConversation 显示实际细节，而不
        # 是退回到“远程对话因错误而结束”。
        #
        on_event(
            ConversationErrorEvent(
                source="agent",
                code=_classify_acp_turn_error(effective_exc),
                detail=error_detail,
            )
        )
        state.execution_status = ConversationExecutionStatus.ERROR

    def _finalize_successful_turn_guarded(
        self,
        response: PromptResponse | None,
        elapsed: float,
        state: ConversationState,
        on_event: ConversationCallbackType,
    ) -> None:
        try:
            self._finalize_successful_turn(response, elapsed, state, on_event)
        except CredentialBindingError as exc:
            self._emit_turn_error(exc, state, on_event)
            self._restart_session_on_next_turn = True
            raise

    def _handle_cancelled_cleanup_interruption(
        self,
        prompt_future: Future[PromptResponse | None] | None,
        elapsed: float,
        state: ConversationState,
        on_event: ConversationCallbackType,
    ) -> None:
        """取消中断取消/排空清理时修复状态。"""
        if prompt_future is not None and prompt_future.done():
            try:
                response = prompt_future.result()
            except BaseException:
                self._cancel_inflight_tool_calls()
                self._restart_session_on_next_turn = True
            else:
                if self._prompt_response_was_cancelled(response):
                    self._cancel_inflight_tool_calls()
                    self._restart_session_on_next_turn = True
                else:
                    self._finalize_successful_turn_guarded(
                        response,
                        elapsed,
                        state,
                        on_event,
                    )
            return

        self._cancel_inflight_tool_calls()
        if prompt_future is not None:
            self._restart_session_on_next_turn = True

    def _clear_turn_callbacks(self) -> None:
        """取消每匝桥回调的连线，使其尾随 ``session_update``
        在回合之间是一个无操作（在门户线程上触发，没有 FIFOLock 人持有 —— 不断电，一
        个陈旧的 ``on_event`` 会与其他线程的变异
        ``state.events`` 竞争）。
        """
        if self._client is None:
            return
        self._client.trace.abandon()
        self._client.on_event = None
        self._client.on_token = None
        self._client.on_activity = None

    @observe(name="acp_agent.step", ignore_inputs=["conversation", "on_event"])
    def step(
        self,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
        on_token: ConversationTokenCallbackType | None = None,
    ) -> None:
        """将最新的用户消息发送到 ACP 服务器并发出响应。

        同步入口 — 由 ``LocalConversation.run``（同步路径）、CLI 和评估线束使用。
        异步路径(``LocalConversation.arun``)经过：meth:`astep`，这避免了#3348中描述的
        交叉线程状态-锁死锁。
        """
        with StreamContext.open(conversation, on_token) as stream:
            self._stream = stream
            try:
                self._step(conversation, on_event, stream.token_callback)
            finally:
                self._stream = None

    def _step(
        self,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
        on_token: ConversationTokenCallbackType | None = None,
    ) -> None:
        state = conversation.state

        if self._restart_session_on_next_turn:
            # 如果重新启动初始化失败，让会话转换到 ERROR，而不是重用不明确的 ACP 会话。
            #
            self._restart_session_after_drain_timeout(state, on_event)

        # 对话实现已经将每回合 AgentContext 扩展附加到 MessageEvent.extended_content；
        # MessageEvent.to_llm_message() 将这些扩展名与用户文本合并。
        #
        prompt_blocks: list[Any] | None = None
        for event in reversed(list(state.events)):
            if isinstance(event, MessageEvent) and event.source == "user":
                prompt_blocks = self._build_acp_prompt(event)
                if prompt_blocks:
                    break
        if prompt_blocks is None:
            logger.warning("No user message found; finishing conversation")
            state.execution_status = ConversationExecutionStatus.FINISHED
            return

        self._reset_client_for_turn(
            on_token,
            on_event,
            prompt_blocks,
            state.secret_registry.mask_secrets_in_output,
        )

        t0 = time.monotonic()
        try:
            logger.info(
                "Sending ACP prompt (idle_timeout=%.0fs, blocks=%d)",
                self.acp_prompt_timeout,
                len(prompt_blocks),
            )
            response: PromptResponse | None = None
            max_retries = _ACP_PROMPT_MAX_RETRIES

            async def _prompt() -> PromptResponse | None:
                # 薄闭包使得现有的``_executor.run_async``的模拟对象采用单个位置可调用继
                # 续工作。 空闲期限在内部强制执行（cancel_on_exit=True：该路径拥有协程）
                # ，而不是作为硬性run_async超时。
                #
                return await self._await_with_idle_deadline(
                    self._do_acp_prompt(prompt_blocks), cancel_on_exit=True
                )

            for attempt in range(max_retries + 1):
                try:
                    response = self._executor.run_async(_prompt)
                    break
                except TimeoutError:
                    raise
                except _RETRIABLE_CONNECTION_ERRORS as e:
                    if attempt < max_retries:
                        delay = _ACP_PROMPT_RETRY_DELAYS[
                            min(attempt, len(_ACP_PROMPT_RETRY_DELAYS) - 1)
                        ]
                        logger.warning(
                            "ACP prompt failed with retriable error "
                            "(attempt %d/%d), retrying in %.0fs: %s",
                            attempt + 1,
                            max_retries + 1,
                            delay,
                            e,
                        )
                        time.sleep(delay)
                        self._cancel_inflight_tool_calls()
                        if self._stream is not None:
                            self._stream.new_attempt()
                        self._reset_client_for_turn(
                            on_token,
                            on_event,
                            prompt_blocks,
                            state.secret_registry.mask_secrets_in_output,
                        )
                    else:
                        raise
                except ACPRequestError as e:
                    # 重试暂时性服务器错误 (e.g. 来自 Gemini 的“内部服务器错误”）。 JSON
                    # -RPC -32603 = 服务器端故障，而不是客户端错误。
                    #
                    if (
                        e.code in _RETRIABLE_SERVER_ERROR_CODES
                        and attempt < max_retries
                    ):
                        delay = _ACP_PROMPT_RETRY_DELAYS[
                            min(attempt, len(_ACP_PROMPT_RETRY_DELAYS) - 1)
                        ]
                        logger.warning(
                            "ACP prompt failed with server error "
                            "(attempt %d/%d), retrying in %.0fs: [%d] %s",
                            attempt + 1,
                            max_retries + 1,
                            delay,
                            e.code,
                            e,
                        )
                        time.sleep(delay)
                        self._cancel_inflight_tool_calls()
                        if self._stream is not None:
                            self._stream.new_attempt()
                        self._reset_client_for_turn(
                            on_token,
                            on_event,
                            prompt_blocks,
                            state.secret_registry.mask_secrets_in_output,
                        )
                    else:
                        raise

            elapsed = time.monotonic() - t0
            logger.info("ACP prompt returned in %.1fs", elapsed)
            self._finalize_successful_turn(response, elapsed, state, on_event)
        except TimeoutError:
            self._request_session_cancel()
            self._emit_turn_timeout(time.monotonic() - t0, state, on_event)
        except Exception as e:
            self._emit_turn_error(e, state, on_event)
            # 重新引发 LocalConversation.run() 的外部 except 处理程序会中断循环，发出
            # ConversationErrorEvent，并引发 ConversationRunError — 与常规智能体的工作方
            # 式相匹配。
            #
            raise
        finally:
            self._clear_turn_callbacks()
            self._flush_file_credentials_blocking()

    @observe(name="acp_agent.astep", ignore_inputs=["conversation", "on_event"])
    async def astep(
        self,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
        on_token: ConversationTokenCallbackType | None = None,
        prompt_message: MessageEvent | None = None,
    ) -> None:
        """:meth:`step` 的 Native-异步变体。

        通过 ``BlockingPortal.start_task_soon`` 在门户循环（``self._conn`` 所在的位置
        ）上安排 ACP
        ``conn.prompt`` 往返，并通过以下方式在调用者的循环上等待返回结果
        ``asyncio.wrap_future``. 提示词后工作 — ``_record_usage``（及其触发的
        ``stats_callback``）、
        ``on_event(action)``、
        ``on_event(observation)``, ``state.execution_status`` — 完全在调用者的线程上
        运行。

        为什么这很重要：``LocalConversation.arun`` 故意不保持对话状态的可重入
        ``FIFOLock`` 跨长时间 ACP 提示词等待，因
        此远程用户消息可以已持久化
        while the subprocess is still working. The default
        ``AgentBase.astep`` 会将同步 ``step`` 包裹在
        ``loop.run_in_executor(None, self.step, ...)``，将后提示词回调和状态更新移动
        到工作人员线程。 保持此路径为 n
        ative-异步将最终确定留给调用者的循环任务，其中
        ``LocalConversation`` 可以序列化每个具有短状态的发出事件 - 锁获取并避免在 #
        3348 / #3350 中诊断的交叉线程死锁。

        桥 ``session_update`` 通知继续在门户线程上触发（此处没有编组）。
        ``LocalConversation.arun`` 提供的
        ``on_event`` 回调负责获取每个单独事件的状态锁。
        """
        with StreamContext.open(conversation, on_token) as stream:
            self._stream = stream
            try:
                await self._astep(
                    conversation, on_event, stream.token_callback, prompt_message
                )
            finally:
                self._stream = None

    async def _astep(
        self,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
        on_token: ConversationTokenCallbackType | None = None,
        prompt_message: MessageEvent | None = None,
    ) -> None:
        state = conversation.state

        if self._restart_session_on_next_turn:
            # 如果重新启动初始化失败，让会话转换到 ERROR，而不是重用不明确的 ACP 会话。
            #
            await self._arestart_session_after_drain_timeout(state, on_event)

        prompt_blocks: list[Any] | None = None
        if prompt_message is not None:
            prompt_blocks = self._build_acp_prompt(prompt_message)
        else:
            for event in reversed(list(state.events)):
                if isinstance(event, MessageEvent) and event.source == "user":
                    prompt_blocks = self._build_acp_prompt(event)
                    if prompt_blocks:
                        break
        if prompt_blocks is None:
            logger.warning("No user message found; finishing conversation")
            state.execution_status = ConversationExecutionStatus.FINISHED
            return

        self._reset_client_for_turn(
            on_token,
            on_event,
            prompt_blocks,
            state.secret_registry.mask_secrets_in_output,
        )

        t0 = time.monotonic()
        prompt_future: Future[PromptResponse | None] | None = None
        try:
            logger.info(
                "Sending ACP prompt (idle_timeout=%.0fs, blocks=%d, async)",
                self.acp_prompt_timeout,
                len(prompt_blocks),
            )
            portal = self._executor.portal

            response: PromptResponse | None = None
            max_retries = _ACP_PROMPT_MAX_RETRIES
            for attempt in range(max_retries + 1):
                try:
                    # 在门户循环（连接所在的位置）上安排 ACP 提示词； 等待未来回到调用者
                    # 循环。 屏蔽 wait_for 超时任务，以便超时/取消处理器可以发送会话/取
                    # 消，并短暂地清空任务，然后在下一个轮次重新配置回调。
                    #
                    current_prompt_future: Future[PromptResponse | None] = (
                        portal.start_task_soon(
                            self._do_acp_prompt,
                            prompt_blocks,
                        )
                    )
                    prompt_future = current_prompt_future
                    response = await self._await_prompt_response_with_timeout(
                        current_prompt_future
                    )
                    break
                except TimeoutError:
                    raise
                except _RETRIABLE_CONNECTION_ERRORS as e:
                    if attempt < max_retries:
                        delay = _ACP_PROMPT_RETRY_DELAYS[
                            min(attempt, len(_ACP_PROMPT_RETRY_DELAYS) - 1)
                        ]
                        logger.warning(
                            "ACP prompt failed with retriable error "
                            "(attempt %d/%d), retrying in %.0fs: %s",
                            attempt + 1,
                            max_retries + 1,
                            delay,
                            e,
                        )
                        await asyncio.sleep(delay)
                        self._cancel_inflight_tool_calls()
                        if self._stream is not None:
                            self._stream.new_attempt()
                        self._reset_client_for_turn(
                            on_token,
                            on_event,
                            prompt_blocks,
                            state.secret_registry.mask_secrets_in_output,
                        )
                    else:
                        raise
                except ACPRequestError as e:
                    if (
                        e.code in _RETRIABLE_SERVER_ERROR_CODES
                        and attempt < max_retries
                    ):
                        delay = _ACP_PROMPT_RETRY_DELAYS[
                            min(attempt, len(_ACP_PROMPT_RETRY_DELAYS) - 1)
                        ]
                        logger.warning(
                            "ACP prompt failed with server error "
                            "(attempt %d/%d), retrying in %.0fs: [%d] %s",
                            attempt + 1,
                            max_retries + 1,
                            delay,
                            e.code,
                            e,
                        )
                        await asyncio.sleep(delay)
                        self._cancel_inflight_tool_calls()
                        if self._stream is not None:
                            self._stream.new_attempt()
                        self._reset_client_for_turn(
                            on_token,
                            on_event,
                            prompt_blocks,
                            state.secret_registry.mask_secrets_in_output,
                        )
                    else:
                        raise

            elapsed = time.monotonic() - t0
            logger.info("ACP prompt returned in %.1fs (async)", elapsed)
            # ``on_event`` 可能是 LocalConversation._on_event_with_state_lock，这重新获
            # 取了这个 FIFOLock。 这是因为 astep() 的最终化在事件循环线程运行，FIFOLock
            # 是可重入的，线程。
            #
            with state:
                self._finalize_successful_turn(response, elapsed, state, on_event)
        except asyncio.CancelledError:
            # ``asyncio.CancelledError`` 继承自 ``BaseException``，而不是
            # ``Exception`` - 因此它将绕过通用处理程序并仅运行 ``finally``，其中
            # ``_clear_turn_callbacks`` 取消桥接。 如果不关闭此处的飞行工具卡，任何
            # ``pending`` / ``in_progress`` ``ACPToolCallEvent`` 在取消之前流式传输，永
            # 久保留在事件日志中（``LocalConversation._emit_orphaned_action_errors`` 仅
            # 补丁
            # ``ActionEvent``，而不是 ``ACPToolCallEvent``）。 在门户提示词观察到会话/取
            # 消后，取消-emit 在调用者线程上取消。因此，晚取消更新无法覆盖终端的合成失败
            # 。
            #
            try:
                await self._arequest_session_cancel()
                drain_result = await self._drain_cancelled_prompt(prompt_future)
            except asyncio.CancelledError:
                with state:
                    elapsed = time.monotonic() - t0
                    self._handle_cancelled_cleanup_interruption(
                        prompt_future, elapsed, state, on_event
                    )
                raise
            with state:
                elapsed = time.monotonic() - t0
                if drain_result.completed and drain_result.error is None:
                    if self._prompt_response_was_cancelled(drain_result.response):
                        self._cancel_inflight_tool_calls()
                        self._restart_session_on_next_turn = True
                    else:
                        self._finalize_successful_turn_guarded(
                            drain_result.response, elapsed, state, on_event
                        )
                    raise
                if drain_result.completed and drain_result.error is not None:
                    self._cancel_inflight_tool_calls()
                    self._restart_session_on_next_turn = True
                    raise
                self._cancel_inflight_tool_calls()
            if not drain_result.drained:
                self._restart_session_on_next_turn = True
            raise
        except TimeoutError:
            try:
                await self._arequest_session_cancel()
                drain_result = await self._drain_cancelled_prompt(prompt_future)
            except asyncio.CancelledError:
                with state:
                    elapsed = time.monotonic() - t0
                    self._handle_cancelled_cleanup_interruption(
                        prompt_future, elapsed, state, on_event
                    )
                raise
            with state:
                elapsed = time.monotonic() - t0
                if drain_result.completed and drain_result.error is None:
                    if self._prompt_response_was_cancelled(drain_result.response):
                        self._emit_turn_timeout(elapsed, state, on_event)
                        self._restart_session_on_next_turn = True
                    else:
                        self._finalize_successful_turn_guarded(
                            drain_result.response, elapsed, state, on_event
                        )
                elif drain_result.completed and drain_result.error is not None:
                    self._emit_turn_error(drain_result.error, state, on_event)
                    self._restart_session_on_next_turn = True
                else:
                    self._emit_turn_timeout(elapsed, state, on_event)
                    self._restart_session_on_next_turn = True
        except Exception as e:
            with state:
                self._emit_turn_error(e, state, on_event)
            raise
        finally:
            self._clear_turn_callbacks()
            await self._flush_file_credentials()

    def ask_agent(self, question: str) -> str | None:
        """分叉 ACP 会话，分叉提示词，并返回响应。"""
        if self._conn is None:
            msg = "ACPAgent has no ACP connection; call init_state() first"
            raise RuntimeError(msg)
        if self._session_id is None:
            msg = "ACPAgent has no session ID; call init_state() first"
            raise RuntimeError(msg)

        conn = self._conn
        session_id = self._session_id
        client = self._client

        async def _fork_and_prompt() -> str:
            fork_response = await conn.fork_session(
                cwd=self._working_dir,
                session_id=session_id,
            )
            fork_session_id = fork_response.session_id

            client._fork_session_id = fork_session_id
            client._fork_accumulated_text.clear()
            try:
                fork_t0 = time.monotonic()
                usage_sync = client.prepare_usage_sync(fork_session_id)
                response = await conn.prompt(
                    session_id=fork_session_id,
                    prompt=[text_block(question)],
                )
                if client.get_turn_usage_update(fork_session_id) is None:
                    try:
                        await asyncio.wait_for(
                            usage_sync.wait(), timeout=_USAGE_UPDATE_TIMEOUT
                        )
                    except TimeoutError:
                        logger.warning(
                            "UsageUpdate not received within %.1fs for fork session %s",
                            _USAGE_UPDATE_TIMEOUT,
                            _fingerprint_session_id(fork_session_id),
                        )
                fork_elapsed = time.monotonic() - fork_t0

                # 在此返回边界处重新屏蔽连接的分叉文本 — 镜像 _finalize_successful_turn
                # ，捕获跨分叉块的机密分割，而每个块的屏蔽无法匹配。
                #
                result = client._mask_value("".join(client._fork_accumulated_text))
                usage_update = client.pop_turn_usage_update(fork_session_id)
                self._record_usage(
                    response,
                    fork_session_id,
                    elapsed=fork_elapsed,
                    usage_update=usage_update,
                )
                return result
            finally:
                try:
                    await self._flush_file_credentials()
                finally:
                    client._fork_session_id = None
                    client._fork_accumulated_text.clear()

        with client._fork_lock:
            return self._executor.run_async(_fork_and_prompt)

    def set_acp_model(self, model: str) -> None:
        """在正在运行的 ACP 会话（对话中）切换模型。

        在实时连接上发出协议级模型切换调用（会话通告的机制 -
        ``set_config_option(model)`` 或
        ``set_session_model``），因此新模型对 * 相同 * 会话中的后续轮次生效 - 不会子
        进程重新启动，不会丢失对话上下文。 已针对 cla
        ude-智能体-ACP 和 codex-ACP 进行验证。

        这是低级智能体原语； 更喜欢
        :meth:`LocalConversation.switch_acp_model` 作为入口。 那
        包装器 (a) 保持状态锁，因此交换机无法与正在运行的交换机竞争
        ``step()``，并且 (b) 通过交换智能体来保留新值
        ``model_copy`` - ``acp_model`` 被冻结，因此此方法仅更新实时会话和哨兵值
        ``llm.model``/metrics，** 不
         **
        ``self.acp_model``. 因此，直接调用者会使``acp_model``（其中``_record_usage``
        读取成本归因）陈旧并且切换不持
        久； 请改为查看 ``switch_acp_model``。

        Args:
            model: 要切换到的特定于提供商的模型 ID (e.g.
                ``"sonnet"`` 或 ``"gpt-5.6"``）。

        Raises:
            ValueError: 如果 ``model`` 为空或仅有空格，如果
                检测到的提供程序不支持运行时模型切换，或者 ACP 服务器拒绝模型切换调用
                 (e.g. 在自定义服务器上找不到方法，或模型 ID 无效）。
            RuntimeError: 如果ACP会话尚未初始化
                (i.e. 在第一个 ``run()`` 之前）。
            TimeoutError: 如果服务器在时间内没有应答
                ``acp_prompt_timeout`` 秒。

        Note:
            超时表示客户端停止等待，而不是表示切换已完成
            rejected: 切换请求可能已经被写入并且
            仍然可以应用于服务器端。 连接和会话保持活跃，本地哨兵值模型被有意保留不变
            ，因此超时切换使服务器端模型不确定。 保守的选择（本地视作失败）会保留对先
            前已知模型的成本/计数，并在下一次成功切换时自我修复。 智能体本身始终运行
            实时 ACP 会话所拥有的任何模型。

            claude-智能体-ACP 警告：实时切换会更改会话模型和推理目标，但模型命名系统
            上下文是在会话 *start* 处注入的，并且不会在此处刷新，因
            此智能体的自我报告身份可能会滞后（e.g. 切换到十四行诗后仍然说“俳句”）直到
            新的会话。 应用开关本身； 只有模型的自我描述是陈旧的。
        """
        if not model or not model.strip():
            raise ValueError("model must be a non-empty string")
        if not self.has_live_acp_session:
            raise RuntimeError(
                "ACP session is not initialized; the model can only be switched "
                "after the conversation has started (first run())."
            )
        provider = detect_acp_provider_by_agent_name(self._agent_name)
        if provider is not None and not provider.supports_runtime_model_switch:
            raise ValueError(
                f"ACP provider '{provider.key}' does not support runtime model "
                "switching."
            )
        # ``has_live_acp_session`` 以上保证了会话 id； 缩小为
        # type checker.
        assert self._conn is not None
        assert self._session_id is not None
        conn = self._conn
        session_id = self._session_id
        # 有界往返：此脚本运行直到 LocalConversation.switch_acp_model 保持状态锁，因此如
        # 果服务器接受调用但从不回复，那么锁必须被无限期地楔住。 在超时 / 协议错误时，我
        # 们先 *，然后再 * 任何本地状态，因此哨兵值 LLM 只有在实际切换了活会话之后才会更
        # 新。
        #
        try:
            self._executor.run_async(
                _apply_acp_model(
                    conn,
                    session_id,
                    model,
                    agent_name=self._agent_name,
                    via_config_option=self._model_via_config_option,
                ),
                timeout=self.acp_prompt_timeout,
            )
        except ACPRequestError as e:
            # 服务器内部故障 (JSON-RPC -32603) 不是调用者的错误，并且提示词路径已将它们
            # 视为可重试。 让它们传播 (-> 5xx)，而不是将它们错误地标记为 400。
            #
            if e.code in _RETRIABLE_SERVER_ERROR_CODES:
                raise
            # acp.exceptions.RequestError 派生自 Exception（而非 RuntimeError）； 表面一
            # 个 True 客户/协议拒绝（无效模型 ID，或在误检测的服务器上找不到方法）为一个
            #  ValueError 以便调用者和智能体-服务器路由将其视为 400 类客户端错误而不是
            # 500 类无意义错误。 该机制是会话所通告的机制 (``_model_via_config_option``)
            # ，因此消息会命名实际失败的调用。
            #
            method = (
                "set_config_option(model)"
                if self._model_via_config_option
                else "set_session_model"
            )
            raise ValueError(
                f"ACP server rejected {method}(model={model!r}): {e}"
            ) from e
        # 在哨兵值 LLM + 指标上反映实时模型，以便成本/代币核算和已序列化状态显示实际使用
        # 的模型（镜像 model_post_init）。 ``acp_model``领域被冻结，所以目前权威的模型是
        # 已持久化
        # :meth:`LocalConversation.switch_acp_model` 通过智能体 ``model_copy``。
        self.llm.model = model
        self.llm.metrics.model_name = model
        if self.llm.metrics.accumulated_token_usage is not None:
            self.llm.metrics.accumulated_token_usage.model = model
        # 刷新表面模型状态，以便芯片/选择器 (``ConversationInfo.current_model_id``) 反映
        # 切换而不是陈旧的会话开始值。 ``_current_model_id`` 是 PrivateAttr，因此
        # ``switch_acp_model`` 的浅层 ``model_copy`` 将此更新值携带到已持久化智能体上。
        # ``available_models`` 不会因模型切换而发生变化，因此有意将其保留。
        #
        self._current_model_id = model
        logger.info(
            "Switched ACP session model to %s (provider=%s, session=%s)",
            model,
            provider.key if provider else "unknown",
            _fingerprint_session_id(self._session_id),
        )

    def close(self) -> None:
        """终止ACP子进程并清理资源。"""
        with self._file_credential_close_lock:
            with self._file_credential_lock:
                if self._closed and not self._file_credential_lifecycles:
                    return
                self._closed = True
            failures = self._shutdown_runtime(discard_bindings=True)
            if not self._has_runtime_resources():
                self._unregister_atexit_cleanup()
            self._raise_first_file_credential_failure("close", failures)

    def _cleanup(self) -> None:
        failures = self._shutdown_runtime(discard_bindings=False)
        self._raise_first_file_credential_failure("restart", failures)

    def _shutdown_runtime(self, *, discard_bindings: bool) -> dict[str, Exception]:
        failures: dict[str, Exception] = {}
        if self._conn is not None and self._executor is not None:
            conn = self._conn
            try:
                self._executor.run_async(conn.close, timeout=5.0)
            except Exception as e:
                logger.debug("Error closing ACP connection: %s", e)
            self._conn = None

        process = self._process
        if process is not None:
            try:
                if process.returncode is None or not isinstance(
                    process.returncode, int
                ):
                    process.terminate()
                if self._executor is not None:
                    self._executor.run_async(
                        self._wait_for_process,
                        process,
                        timeout=5.0,
                    )
            except Exception as e:
                logger.debug("Error terminating ACP process: %s", e)
                try:
                    process.kill()
                    if self._executor is not None:
                        self._executor.run_async(
                            self._wait_for_process,
                            process,
                            timeout=5.0,
                        )
                except Exception as kill_error:
                    logger.debug("Error killing ACP process: %s", kill_error)
            self._process = None

        for task_name, task in (
            ("stdout filter task", self._stdout_filter_task),
            ("stderr log task", self._stderr_log_task),
        ):
            if task is not None:
                task.cancel()
                if self._executor is not None:
                    try:
                        self._executor.run_async(
                            self._await_cancelled_task, task, timeout=5.0
                        )
                    except Exception as e:
                        logger.debug("Error stopping %s: %s", task_name, e)
        self._stdout_filter_task = None
        self._stderr_log_task = None

        credential_failures = self._release_file_credentials_collect()
        failures.update(credential_failures)
        if discard_bindings:
            with self._file_credential_lock:
                if not credential_failures:
                    self._file_credential_bindings = {}

        if self._executor is not None and not credential_failures:
            try:
                self._executor.close()
            except Exception as e:
                failures["ACP executor"] = e
            self._executor = None
        return failures

    @staticmethod
    async def _wait_for_process(process: asyncio.subprocess.Process) -> None:
        await process.wait()

    @staticmethod
    async def _await_cancelled_task(task: asyncio.Task[Any]) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            await task

    def release_runtime(self) -> None:
        """将其实时 ACP 运行时交给 a 后，解除此智能体的终结器
        浅：方法：`~pydantic.BaseModel.model_copy`。

        该副本共享此智能体的 ``_conn`` / ``_executor`` / ``_process`` 引用（
        ``model_copy`` 是浅的）。 将这
        个现已过时的实例标记为关闭使其 ``__del__`` -> :meth:`close` 成为无操作，因此
        删除它不能破坏副本现在拥有的运行时。

        运行时引用有意保持完整：一个正在运行的
        :meth:`ask_agent` fork — 这是线程安全并且可能仍然保留这个
        预切换智能体 — 保持有效连接直至完成。 拆卸的唯一所有权传递给副本（继续的实时
        ``self.agent``），该副本在会话关闭时关闭。

        请参阅：方法：`LocalConversation.switch_acp_model`。
        """
        with self._file_credential_close_lock:
            self._unregister_atexit_cleanup()
            with self._file_credential_lock:
                self._file_credential_lifecycles = {}
                self._file_credential_bindings = {}
                self._closed = True

    def __del__(self) -> None:
        try:
            has_resources = self._has_runtime_resources()
        except Exception:
            return
        if not has_resources:
            return
        try:
            threading.Thread(
                target=self._finalize,
                name="acp-agent-finalizer",
                daemon=True,
            ).start()
        except Exception:
            self._finalize()

    def _finalize(self) -> None:
        try:
            self.close()
        except Exception:
            logger.warning("Failed to finalize ACPAgent resources", exc_info=True)
