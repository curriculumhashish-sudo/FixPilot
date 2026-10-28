import json
import logging
import os
from pathlib import Path
from typing import Any, ClassVar, Final, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    PrivateAttr,
    SecretStr,
    field_validator,
    model_validator,
)

from openhands.agent_server.conversation_lease import DEFAULT_LEASE_TTL_SECONDS
from openhands.agent_server.env_parser import (
    MISSING,
    _get_default_parsers,
    from_env,  # noqa: F401 - compatibility re-export
    get_env_parser,
    merge,
)
from openhands.agent_server.telemetry_types import DeploymentKind
from openhands.sdk.marketplace.registration import MarketplaceRegistration
from openhands.sdk.utils.cipher import Cipher


# 环境变量常数
V0_SESSION_API_KEY_ENV = "SESSION_API_KEY"
V1_SESSION_API_KEY_ENV = "OH_SESSION_API_KEYS_0"
ENVIRONMENT_VARIABLE_PREFIX = "OH"
CONFIG_PATH_ENV = "OPENHANDS_AGENT_SERVER_CONFIG_PATH"
DEFAULT_CONFIG_PATH = Path("workspace/openhands_agent_server_config.json")
# 20 分钟，与 OpenHands Cloud 使用的空闲超时匹配。
DEFAULT_CONVERSATION_IDLE_TTL_SECONDS: Final[float] = 20 * 60.0
ACPSkillSourcing = Literal["native", "openhands_managed"]
_logger = logging.getLogger(__name__)


def _default_session_api_keys():
    """
    该函数作为使用旧 V0 环境变量的回退方案存在。 如果 new V1_SESSION_API_KEYS_0 环境
    变量存在，它会被 EnvParser 自动读取，并且
    永远不会调用该函数。
    """
    result = []
    session_api_key = os.getenv(V0_SESSION_API_KEY_ENV)
    if session_api_key:
        result.append(session_api_key)
    return result


def _default_secret_key() -> SecretStr | None:
    """
    如果 OH_SECRET_KEY 环境变量存在，则由 EnvParser 读取它，并且永远不会调用此函数。
    否则，我们会转而使用第一个可用的
    session_api_key - 我们从环境中读取。 我们为此检查 V0 和 V1 变量。
    """
    session_api_key = os.getenv(V0_SESSION_API_KEY_ENV)
    if session_api_key:
        return SecretStr(session_api_key)
    session_api_key = os.getenv(V1_SESSION_API_KEY_ENV)
    if session_api_key:
        return SecretStr(session_api_key)
    return None


def _is_blank_secret(value: object) -> bool:
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    return isinstance(value, str) and not value.strip()


def _default_web_url() -> str | None:
    web_url = os.getenv("OH_WEB_URL")
    if web_url:
        return web_url

    return None


DEFAULT_CONVERSATION_IMAGE = "ghcr.io/openhands/agent-server:latest-python"


class WebhookSpec(BaseModel):
    """规范创建 Webhook。 所有 Webhook 请求都使用 POST 方法。"""

    # 一般参数
    event_buffer_size: int = Field(
        default=5,
        ge=1,
        description=(
            "The number of events to buffer locally before posting to the webhook"
        ),
    )
    base_url: str = Field(
        description="The base URL of the webhook service. Event batches are sent "
        "to {base_url}/events/{conversation_id.hex} (the conversation id without "
        "dashes) and conversation info to {base_url}/conversations"
    )
    headers: dict[str, str] = Field(default_factory=dict)
    flush_delay: float = Field(
        default=30.0,
        gt=0,
        description=(
            "The delay in seconds after which buffered events will be flushed to "
            "the webhook, even if the buffer is not full. The timer starts when "
            "the first event is queued and is not reset by later events."
        ),
    )

    # 重试参数
    num_retries: int = Field(
        default=3,
        ge=0,
        description="The number of times to retry if the post operation fails",
    )
    retry_delay: int = Field(default=5, ge=0, description="The delay between retries")

    # 背压参数
    max_queue_size: int = Field(
        default=1000,
        ge=1,
        description=(
            "Upper bound on the number of events buffered for delivery. The oldest "
            "events are dropped past this bound to prevent unbounded memory growth."
        ),
    )
    max_batch_bytes: int = Field(
        default=5 * 1024 * 1024,
        ge=1,
        description=(
            "Upper bound on the serialized size of each webhook request. A single "
            "event larger than this limit is sent by itself."
        ),
    )
    max_queue_bytes: int = Field(
        default=50 * 1024 * 1024,
        ge=1,
        description=(
            "Upper bound on the serialized size of events buffered for delivery. "
            "The oldest events are dropped when the queue exceeds this bound."
        ),
    )


TelemetryExporterKind = Literal["none", "posthog", "http"]
"""哪个导出器发送诊断事件（如果有）。"""


class TelemetrySpec(BaseModel):
    """部署提供的产品分析传输层设置。

    它带有传输层以及非识别部署标签。 是否可以提供遥测数据由同意决定（
    ``misc_settings.telemetry.consent``，可选地由
    ``OH_TELEMETRY_CONSENT``).
    """

    deployment_kind: DeploymentKind = Field(
        default="local",
        description=(
            "Deployment kind attached to diagnostic events. Use 'remote' for "
            "hosted OpenHands and 'local' for self-hosted or developer runs."
        ),
    )
    exporter: TelemetryExporterKind = Field(
        default="none",
        description=(
            "Exporter to use. 'none' (the default) never delivers, and is what "
            "library and headless consumers get. 'posthog' requires the "
            "[posthog] extra. 'http' POSTs sanitized batches to "
            "telemetry_http_endpoint."
        ),
    )
    posthog_api_key: SecretStr | None = Field(
        default=None,
        description=(
            "PostHog project API key. Required by the 'posthog' exporter; "
            "without it telemetry stays inactive."
        ),
    )
    posthog_host: str = Field(
        default="https://us.i.posthog.com",
        description="PostHog ingestion host.",
    )
    http_endpoint: str | None = Field(
        default=None,
        description=(
            "Endpoint the 'http' exporter POSTs sanitized event batches to. "
            "Intended to front a backend that revalidates auth and consent "
            "before forwarding onward."
        ),
    )
    http_token: SecretStr | None = Field(
        default=None,
        description="Bearer token sent by the 'http' exporter, if required.",
    )
    salt: SecretStr | None = Field(
        default=None,
        description=(
            "Key used to pseudonymize conversation identifiers. Falls back to "
            "the server's secret key (OH_SECRET_KEY, which defaults to the "
            "first session API key), so pseudonyms stay stable and linkable "
            "across restarts until that key changes. Only when there is no "
            "secret key either is a random key generated per process, which "
            "makes pseudonyms unlinkable across runs."
        ),
    )
    max_queue_size: int = Field(
        default=1000,
        ge=1,
        description=(
            "Upper bound on buffered diagnostic events. The queue is bounded "
            "on ingest: past this many events the oldest are dropped, so a "
            "failing exporter cannot grow memory without limit."
        ),
    )
    event_buffer_size: int = Field(
        default=20, ge=1, description="Maximum events per delivery batch."
    )
    flush_delay: float = Field(
        default=30.0,
        gt=0,
        description="Seconds to wait before flushing a partial batch.",
    )
    num_retries: int = Field(
        default=2, ge=0, description="Retries before a batch is dropped."
    )
    retry_delay: float = Field(
        default=5.0, ge=0, description="Base seconds between delivery retries."
    )


class Config(BaseModel):
    """
    以本地模式运行的服务器的不可变配置。 （通常在沙箱内）。
    """

    session_api_keys: list[str] = Field(
        default_factory=_default_session_api_keys,
        description=(
            "List of valid session API keys used to authenticate incoming requests. "
            "Empty list implies the server will be unsecured. Any key in this list "
            "will be accepted for authentication. Multiple keys are supported to "
            "enable key rotation without service disruption - new keys can be added "
            "to the list, then clients are updated with the new key, and finally the "
            "old key is removed from the list. "
        ),
    )
    allow_cors_origins: list[str] = Field(
        default_factory=list,
        description=(
            "CORS origins permitted by this server. Localhost / 127.0.0.1 "
            "and ``DOCKER_HOST_ADDR`` are always allowed. Does not apply to "
            "the workspace cookie routes, which accept any origin — see "
            "``middleware.py``."
        ),
    )
    allow_cors_origin_regex: str | None = Field(
        default=None,
        description=(
            "Regular expression matching additional CORS origins permitted by "
            "this server. Localhost / 127.0.0.1 and ``DOCKER_HOST_ADDR`` are "
            "always allowed. Does not apply to the workspace cookie routes, "
            "which accept any origin — see ``middleware.py``."
        ),
    )
    conversations_path: Path = Field(
        default=Path("workspace/conversations"),
        description=(
            "The location of the directory where conversations and events are stored."
        ),
    )
    workspace_path: Path = Field(
        default=Path("workspace/project"),
        description=(
            "Default workspace directory for conversations created by the server."
        ),
    )
    conversation_worktree_root: Path = Field(
        default=Path("/tmp/conversation-worktrees"),
        description=(
            "Root directory for conversation git worktrees. Each conversation gets a "
            "subdirectory under this root when using git-backed workspaces with "
            "worktree=True."
        ),
    )
    bash_events_dir: Path = Field(
        default=Path("workspace/bash_events"),
        description=(
            "The location of the directory where bash events are stored as files. "
            "Defaults to 'workspace/bash_events'."
        ),
    )
    bash_events_retention_seconds: int | None = Field(
        default=None,
        gt=0,
        description=(
            "How long bash event files are retained on disk, in seconds. "
            "A background task purges events older than this window on a "
            "rolling basis. None (default) retains events indefinitely. "
            "Should be set higher than the longest expected command timeout: "
            "a command whose BashCommand file is purged mid-execution will "
            "complete normally, but its on-disk event history will be "
            "incomplete. A value >= 2x max command timeout avoids this."
        ),
    )
    static_files_path: Path | None = Field(
        default=None,
        description=(
            "The location of the directory containing static files to serve. "
            "If specified and the directory exists, static files will be served "
            "at the /static/ endpoint."
        ),
    )
    webhooks: list[WebhookSpec] = Field(
        default_factory=list,
        description="Webhooks to invoke in response to events",
    )
    enable_vscode: bool = Field(
        default=True,
        description="Whether to enable VSCode server functionality",
    )
    vscode_port: int = Field(
        default=8001,
        ge=1,
        le=65535,
        description="Port on which VSCode server should run",
    )
    vscode_base_path: str | None = Field(
        default=None,
        description=(
            "Base path for VSCode server (used in path-based routing). "
            "For example, '/{runtime_id}/vscode' when using path-based routing."
        ),
    )
    preload_tools: bool = Field(
        default=True,
        description="Whether to preload tools",
    )
    max_concurrent_runs: int = Field(
        default=10,
        ge=1,
        description=(
            "Maximum number of conversations that can execute agent steps "
            "concurrently, across native async runs and synchronous runs. "
            "Creating a conversation also reserves capacity during initialization. "
            "When full, create and run requests are rejected with HTTP 429."
        ),
    )
    secret_key: SecretStr | None = Field(
        default_factory=_default_secret_key,
        description=(
            "Secret key used for encrypting sensitive values in all serialized data. "
            "If missing, any sensitive data is redacted, meaning full state cannot"
            "be restored between restarts."
        ),
    )
    previous_secret_keys: list[SecretStr] = Field(
        default_factory=list,
        description=(
            "Earlier values of secret_key, used only to decrypt. Values saved "
            "under one of them stay readable and are re-encrypted under "
            "secret_key when next saved (the settings and secrets stores are "
            "re-encrypted at startup). To rotate, set the new key as "
            "secret_key and put the old one here. Prefer setting OH_SECRET_KEY "
            "explicitly: while secret_key falls back to the first session API "
            "key, rotating that session key also rotates the encryption key, "
            "so the old session key must go here. Set with "
            "OH_PREVIOUS_SECRET_KEYS as a JSON list, or "
            "OH_PREVIOUS_SECRET_KEYS_0, OH_PREVIOUS_SECRET_KEYS_1, ..."
        ),
    )
    web_url: str | None = Field(
        default_factory=_default_web_url,
        description=(
            "The URL where this agent server instance is available externally"
        ),
    )
    app_backend_public_url: str | None = Field(
        default=None,
        description=(
            "Separate browser origin that exposes authenticated Canvas App backends"
        ),
    )
    trust_forwarded_headers: bool = Field(
        default=False,
        description=(
            "Trust X-Forwarded-Proto/X-Forwarded-Host from the immediate peer "
            "when deriving a request origin or secure-context decision. Enable "
            "only when a reverse proxy or load balancer terminates TLS in front "
            "of this server and strips client-supplied values for those headers. "
            "Left disabled, a client can spoof them to assert an origin the "
            "server did not actually receive."
        ),
    )
    conversation_runtime: Literal["local", "docker"] = "local"
    conversation_runtime_selectable: bool = Field(
        default=False,
        description=(
            "Serve both the local and the docker runtime and let each start "
            "request pick one with `conversation_runtime`; requests that leave "
            "it unset use this server's `conversation_runtime`. Requires a "
            "Docker daemon and "
            "`OH_SECRET_KEY`."
        ),
    )
    conversation_image: str = DEFAULT_CONVERSATION_IMAGE
    conversation_image_has_browser: bool | None = Field(
        default=None,
        description=(
            "Whether conversation_image ships the browser (chromium) stack. "
            "Unset means true for any tag or digest of the stock agent-server "
            "image except its -minimal flavor, and false for other images."
        ),
    )
    enable_browser: bool = Field(
        default=True,
        description=(
            "Whether conversations may get the browser tool set. When false, "
            "launches leave it out even where chromium is available."
        ),
    )
    conversation_container_memory: str | None = "4g"
    conversation_container_cpus: float | None = Field(default=2.0, gt=0)
    conversation_container_pids_limit: int | None = Field(default=512, gt=0)
    conversation_container_startup_timeout: float = Field(default=120, gt=0)
    conversation_storage_disk_budget: float | None = Field(
        default=None,
        gt=0,
        lt=1,
        description=(
            "Fraction of the conversation-storage filesystem that may be in use "
            "before stopped conversations shed the gitignored directories of "
            "their workspaces (node_modules, .venv, build output), least "
            "recently active first. Tracked files, untracked work, ignored "
            "files and nested checkouts are kept; a resumed conversation "
            "reinstalls what was shed. Only workspaces the server created are "
            "touched. Unset (the default) disables it."
        ),
    )
    conversation_storage_retention_days: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Days a stopped conversation may stay inactive before its runtime "
            "(sandbox home and workspace) is deleted and the conversation is "
            "archived: its history and encryption identity are kept, so it "
            "stays readable but can no longer be resumed. A workspace the "
            "server did not create is never deleted. Unset (the default) keeps "
            "runtimes until the conversation is deleted. Leave it unset when "
            "the server runs in a sandbox that its provider pauses: no pass "
            "runs while paused, so the first pass after a resume archives "
            "every conversation that crossed the limit in the meantime."
        ),
    )

    acp_skill_sourcing: ACPSkillSourcing = Field(
        default="native",
        description=(
            "Who supplies an ACP agent's skills. 'native' (the default, for a "
            "host-local agent-server): nobody but the ACP CLI — it reads the "
            "user's own home configuration and the repository, so OpenHands "
            "injects none of its managed skills. 'openhands_managed' (for "
            "container runtimes, where that host configuration is absent): also "
            "inject the user/org/public/marketplace skills the server "
            "discovers. Project/repository skills are never injected either way "
            "— the CLI reads AGENTS.md itself (#4019). Skills a client supplies "
            "at launch are kept in both modes. Set explicitly per "
            "deployment; the agent-server image sets 'openhands_managed'."
        ),
    )
    registered_marketplaces: list[MarketplaceRegistration] = Field(
        default_factory=list,
        description=(
            "Default marketplace registrations for plugin and skill loading. "
            "Can be configured with OH_REGISTERED_MARKETPLACES as a JSON list."
        ),
    )
    deferred_init: bool = Field(
        default=False,
        description=(
            "When True, the server starts in dormant mode. Stateless services "
            "(VSCode, tool preload, etc.) start as usual, but the conversation, "
            "event, and bash routers return 503 until POST /api/init is called with "
            "the runtime configuration. This is intended for warm-pool deployments "
            "where pods are pre-warmed before a user is matched and per-user "
            "configuration is delivered later."
        ),
    )
    lease_ttl_seconds: float = Field(
        default=DEFAULT_LEASE_TTL_SECONDS,
        ge=0.0,
        description=(
            "How long (in seconds) a conversation ownership lease remains valid "
            "without renewal. The lease prevents two server instances from "
            "concurrently owning the same conversation when storage is shared "
            "across instances. Set to 0 to disable leasing entirely, which is "
            "appropriate for single-instance deployments where concurrent "
            "ownership is impossible. Values between 0 and "
            "LEASE_RENEW_INTERVAL_SECONDS (15 s) are valid but cause the lease "
            "to expire before the first renewal, effectively making it one-shot."
        ),
    )
    conversation_idle_ttl_seconds: float | None = Field(
        default=DEFAULT_CONVERSATION_IDLE_TTL_SECONDS,
        gt=0,
        description=(
            "Seconds an idle conversation stays in memory before a background "
            "task evicts it; evicted conversations re-hydrate from disk on next "
            "access. Defaults to 20 minutes. Conversations that are running, "
            "have a pending rerun, or have an attached websocket subscriber are "
            "never evicted. Set to null to keep conversations in memory until "
            "they are deleted or the server restarts."
        ),
    )
    telemetry: TelemetrySpec = Field(
        default_factory=TelemetrySpec,
        description=(
            "Product-analytics policy. Disabled by default; see TelemetrySpec. "
            "Distinct from LLM completion logging and from Laminar/OTel tracing."
        ),
    )
    model_config: ClassVar[ConfigDict] = {"frozen": True}
    _secret_key_was_blank: bool = PrivateAttr(default=False)

    @field_validator("session_api_keys")
    @classmethod
    def _drop_empty_session_api_keys(cls, value: list[str]) -> list[str]:
        # 空键 (e.g. ``OH_SESSION_API_KEYS_0=``) 永远不是真实的凭据； 保留它将使空字符串
        # 进行身份验证。
        #
        return [key for key in value if key]

    @field_validator("secret_key")
    @classmethod
    def _empty_secret_key_is_unset(cls, value: SecretStr | None) -> SecretStr | None:
        """处理空白机密键 (e.g. ``OH_SECRET_KEY=`` 或仅限空格）
        由于未设置，因此应用会话密钥回退方案，而不是使用任何人都可以猜到的密钥进行加
        密。
        """
        if _is_blank_secret(value):
            return _default_secret_key()
        return value

    @model_validator(mode="wrap")
    @classmethod
    def _remember_blank_secret_key(
        cls, data: Any, handler: ModelWrapValidatorHandler[Self]
    ) -> Self:
        config = handler(data)
        if isinstance(data, dict) and _is_blank_secret(data.get("secret_key")):
            config._secret_key_was_blank = True
        return config

    @property
    def secret_key_was_blank(self) -> bool:
        """是否配置了空白机密键（因此被视为未设置）。"""
        return self._secret_key_was_blank

    @property
    def cipher(self) -> Cipher | None:
        if self.secret_key is None:
            if getattr(self, "_cipher", None) is not False:
                _logger.warning(
                    "⚠️ OH_SECRET_KEY was not defined. Secrets will not "
                    "be persisted between restarts."
                )
                setattr(self, "_cipher", False)
            return None
        keys = (
            self.secret_key.get_secret_value(),
            tuple(key.get_secret_value() for key in self.previous_secret_keys),
        )
        cipher = getattr(self, "_cipher", None)
        # ``model_copy`` 携带缓存的密码，因此当副本被赋予其他密钥时重建它（e.g. 由
        # ``POST /api/init``）。
        #
        if (
            not isinstance(cipher, Cipher)
            or getattr(self, "_cipher_keys", None) != keys
        ):
            cipher = Cipher(keys[0], previous_keys=keys[1])
            setattr(self, "_cipher", cipher)
            setattr(self, "_cipher_keys", keys)
        return cipher


_default_config: Config | None = None


def _read_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a JSON object: {path}")
    return data


def export_session_api_key(config: Config) -> None:
    """将服务器的第一个会话密钥发布到进程环境。

    ``start_child_conversation`` 工具和 LLM 管理的 ``OH_SESSION_API_KEYS_0`` 和
    ``SESSION_API_KEY`` 读取该服务器的密钥，这些密钥在服务器启动之前由 Docker 和远程
    运行时设置。 通过配置文件或
    ``POST /api/init`` 传递的密钥仅存在于：class:`Config` 中，直到在此处导出为止。 有
    效密钥总是占优势，因此一个启动时用一个密钥，初始
    化时用另一个密钥的休眠进程最终会用它认证的密钥。
    """
    if config.session_api_keys:
        os.environ[V1_SESSION_API_KEY_ENV] = config.session_api_keys[0]


def load_config(config_path: Path | None = None) -> Config:
    """从 JSON 文件和环境变量加载智能体-服务器配置。

    ``OH_*`` 环境变量中的值会覆盖 JSON 配置文件中的值，以便特定于部署的环境覆盖继续有
    效。
    """
    resolved_path = config_path
    if resolved_path is None:
        resolved_path = Path(os.getenv(CONFIG_PATH_ENV, DEFAULT_CONFIG_PATH))

    file_data = _read_config_file(resolved_path)
    parser = get_env_parser(Config, _get_default_parsers())
    env_data = parser.from_env(ENVIRONMENT_VARIABLE_PREFIX)

    if env_data is MISSING:
        data = file_data
    else:
        # 显式环境 null (OH_<FIELD>_IS_NONE=1) 清除文件值。
        data = merge(file_data, env_data, none_overrides=True)

    if not data:
        return Config()
    return Config.model_validate(data)


def get_default_config() -> Config:
    """获取跨服务器共享的默认本地服务器配置"""
    global _default_config
    if _default_config is None:
        _default_config = load_config()
        assert _default_config is not None
    return _default_config
