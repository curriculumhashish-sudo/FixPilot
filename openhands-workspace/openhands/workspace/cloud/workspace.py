"""OpenHands 云工作区使用云 API 实现。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.request import urlopen

import httpx
import tenacity
from pydantic import Field, PrivateAttr, SecretStr

from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.config import MCPServer, MCPTransport
from openhands.sdk.workspace.remote.base import RemoteWorkspace
from openhands.sdk.workspace.repo import CloneResult, RepoMapping, RepoSource


if TYPE_CHECKING:
    from openhands.sdk.context import AgentContext
    from openhands.sdk.llm.llm import LLM
    from openhands.sdk.secret import LookupSecret
    from openhands.sdk.skills import Skill


logger = get_logger(__name__)

# 来自 OpenHands 云的标准公开 URL 名称
AGENT_SERVER = "AGENT_SERVER"

# 短暂 API 次失败的尝试次数重试
_MAX_RETRIES = 3

# 智能体-服务器在 Cloud Runtime 内侦听的默认端口
DEFAULT_AGENT_SERVER_PORT = 60000


def _mcp_api_key_headers(api_key: object) -> dict[str, SecretStr] | None:
    if not api_key:
        return None
    return {"Authorization": SecretStr(f"Bearer {api_key}")}


def _is_retryable_error(error: BaseException) -> bool:
    """对于值得重试的暂时性错误，返回 True。"""
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code >= 500
    return isinstance(error, (httpx.ConnectError, httpx.TimeoutException))


class OpenHandsCloudWorkspace(RemoteWorkspace):
    """使用 OpenHands 云 API 进行远程工作区。

    此工作区连接到 OpenHands 云 (app.all-hands.dev) 以配置和管理用于智能体执行的沙盒
    环境。

    当 ``local_agent_server_mode=True`` 时，工作区假定它已经在 OpenHands Cloud
    Runtime 沙箱内运行。 它不是通
    过云 API 创建或管理沙箱，而是直接连接到 ``http://localhost:<agent_server_port>``
    处的本地智能体服务器。

    Example:
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://app.all-hands.dev",
            cloud_api_key="your-api-key",
        )

        # 具有自定义沙箱规范
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://app.all-hands.dev",
            cloud_api_key="your-api-key",
            sandbox_spec_id="ghcr.io/openhands/agent-server:main-python",
        )

        # 在 OpenHands Cloud Runtime 内运行（本地智能体-服务器模式）
        workspace = OpenHandsCloudWorkspace(
            local_agent_server_mode=True,
            cloud_api_url="https://app.all-hands.dev",
            cloud_api_key=os.environ["OPENHANDS_API_KEY"],
        )
    """

    # 父字段
    working_dir: str = Field(
        default="/workspace/project",
        description="Working directory inside the sandbox",
    )
    host: str = Field(
        default="undefined",
        description=("The agent server URL. Set automatically after sandbox starts."),
    )

    # 本地智能体-服务器模式
    local_agent_server_mode: bool = Field(
        default=False,
        description=(
            "When True, assume the SDK is running inside an OpenHands Cloud "
            "Runtime and connect to the local agent-server instead of "
            "provisioning a sandbox via the Cloud API."
        ),
    )
    agent_server_port: int = Field(
        default=DEFAULT_AGENT_SERVER_PORT,
        description=(
            "Port of the local agent-server. "
            "Only used when local_agent_server_mode=True."
        ),
    )

    # 云 API 字段
    cloud_api_url: str = Field(
        description=(
            "Base URL of OpenHands Cloud API "
            "(e.g., https://app.all-hands.dev). "
            "Required in all modes — used for get_llms / get_secrets."
        ),
    )
    cloud_api_key: str = Field(
        description=(
            "API key for authenticating with OpenHands Cloud. "
            "Required in all modes — used for get_llms / get_secrets."
        ),
    )
    sandbox_spec_id: str | None = Field(
        default=None,
        description=("Optional sandbox specification ID (e.g., container image)"),
    )

    # 生命周期选项
    init_timeout: float = Field(
        default=300.0,
        description="Sandbox initialization timeout in seconds",
    )
    api_timeout: float = Field(
        default=60.0, description="API request timeout in seconds"
    )
    keep_alive: bool = Field(
        default=False,
        description=("If True, keep sandbox alive on cleanup instead of deleting"),
    )

    # 沙箱 ID - 可以提供以恢复现有沙箱
    sandbox_id: str | None = Field(
        default=None,
        description=(
            "Optional sandbox ID to resume. If provided, the workspace will "
            "attempt to resume the existing sandbox instead of creating a "
            "new one."
        ),
    )

    # 私人国家
    _sandbox_id: str | None = PrivateAttr(default=None)
    _session_api_key: str | None = PrivateAttr(default=None)
    _exposed_urls: list[dict[str, Any]] | None = PrivateAttr(default=None)
    _automation_callback_url: str | None = PrivateAttr(default=None)
    _automation_run_id: str | None = PrivateAttr(default=None)
    _conversation_id: str | None = PrivateAttr(default=None)

    @property
    def default_conversation_tags(self) -> dict[str, str]:
        """从自动化环境变量构建默认标签以创建对话。

        使用沙箱范围扩展 ``RemoteWorkspace.default_conversation_tags``（源自调度程序
        注入的自动化环境变量）
        ``_automation_run_id`` 回退方案在本地智能体-服务器模式下捕获。

        Note: 技能/插件包含在此处不 - 它们在创建时传递
        RemoteConversation 并在该级别合并。

        这些标签会自动合并到通过此工作区创建的对话中，从而允许云平台跟踪自动化上下文
        。
        """
        tags = dict(super().default_conversation_tags or {})
        if "automationrunid" not in tags and self._automation_run_id:
            tags["automationrunid"] = self._automation_run_id
        return tags

    @property
    def client(self) -> httpx.Client:
        """覆盖客户端属性以将 api_timeout 用于 HTTP 请求。"""
        client = self._client
        if client is None:
            timeout = httpx.Timeout(
                connect=10.0,
                read=self.api_timeout,
                write=10.0,
                pool=10.0,
            )
            client = httpx.Client(
                base_url=self.host, timeout=timeout, headers=self._headers
            )
            self._client = client
        return client

    @property
    def _api_headers(self) -> dict[str, str]:
        """Cloud API 请求的标头。

        根据 OpenHands 云 API 使用持有者令牌身份验证。
        """
        return {"Authorization": f"Bearer {self.cloud_api_key}"}

    def model_post_init(self, context: Any) -> None:
        """设置沙箱并初始化工作区。"""
        self.cloud_api_url = self.cloud_api_url.rstrip("/")

        if self.local_agent_server_mode:
            self._init_local_agent_server_mode()
        else:
            try:
                self._start_sandbox()
                super().model_post_init(context)
            except Exception:
                self.cleanup()
                raise

    def _init_local_agent_server_mode(self) -> None:
        """在本地智能体服务器模式下初始化 — 连接到本地智能体服务器。

        从环境变量读取沙箱身份和自动化回调设置，以便 ``get_llm()`` 和
        ``get_secrets()`` 可以调用云 API 的沙箱范围设置端点。

        预期的环境变量（由自动化调度程序注入）：
          ``SANDBOX_ID`` — 此沙箱的 Cloud API 标识符
          ``SESSION_API_KEY`` — 沙箱设置身份验证的会话密钥
          ``AUTOMATION_CALLBACK_URL`` — 完成回调端点（可选）
          ``AUTOMATION_RUN_ID`` — 回调载荷的运行 ID（可选）

        如果 ``SESSION_API_KEY`` 不存在，则回退到 ``OH_SESSION_API_KEYS_0``（由运行时
        设置）。
        """
        port = os.environ.get("AGENT_SERVER_PORT", str(self.agent_server_port))
        self.host = f"http://localhost:{port}"
        logger.info(
            f"Local agent-server mode: connecting to agent-server at {self.host}"
        )

        # 从环境变量中发现沙箱身份
        self._sandbox_id = self.sandbox_id or os.environ.get("SANDBOX_ID")
        self._session_api_key = os.environ.get(
            "SESSION_API_KEY", os.environ.get("OH_SESSION_API_KEYS_0")
        )

        # 环境变量中的自动化回调设置
        self._automation_callback_url = os.environ.get("AUTOMATION_CALLBACK_URL")
        self._automation_run_id = os.environ.get("AUTOMATION_RUN_ID")

        if not self._sandbox_id:
            logger.warning(
                "SANDBOX_ID env var not set — get_llm()/get_secrets() "
                "will not work. Set SANDBOX_ID or pass sandbox_id= to "
                "the constructor."
            )
        if not self._session_api_key:
            logger.warning(
                "SESSION_API_KEY env var not set — sandbox settings "
                "API calls will fail."
            )

        # 传播到 RemoteWorkspaceMixin.api_key，以便共享 HTTP 客户端（由
        # RemoteConversation 使用）包含 X-Session-API-Key。
        #
        self.api_key = self._session_api_key

        self.reset_client()
        # 触发父 mixin init （去除尾部斜杠等）
        super().model_post_init(None)

    def _start_sandbox(self) -> None:
        """通过云 API 启动一个新的沙箱或恢复现有的沙箱。

        如果提供 sandbox_id，则尝试恢复现有沙箱。 否则，创建一个新的沙箱。
        """
        if self.sandbox_id:
            self._resume_existing_sandbox()
        else:
            self._create_new_sandbox()

        # 等待沙箱变成RUNNING
        self._wait_until_sandbox_ready()

        # 从 exposed_urls 中提取 Agent Server URL
        agent_server_url = self._get_agent_server_url()
        if not agent_server_url:
            raise ValueError(
                f"Agent server URL not found in sandbox {self._sandbox_id}"
            )

        logger.info(f"Sandbox ready at {agent_server_url}")

        # 设置主机和 api_key 进行 RemoteWorkspace 操作
        self.host = agent_server_url.rstrip("/")
        self.api_key = self._session_api_key

        # 使用新主机和 API 密钥重置 HTTP 客户端
        self.reset_client()

        # 验证客户端是否正确初始化
        assert self.client is not None
        assert self.client.base_url == self.host

    def _create_new_sandbox(self) -> None:
        """通过云创建一个新的沙箱 API。"""
        logger.info("Starting sandbox via OpenHands Cloud API...")

        # 构建请求参数
        params: dict[str, str] = {}
        if self.sandbox_spec_id:
            params["sandbox_spec_id"] = self.sandbox_spec_id

        # POST /api/v1/sandboxes 启动一个新的沙箱
        resp = self._send_api_request(
            "POST",
            f"{self.cloud_api_url}/api/v1/sandboxes",
            params=params if params else None,
            timeout=self.init_timeout,
        )
        data = resp.json()

        self._sandbox_id = data["id"]
        self._session_api_key = data.get("session_api_key")
        logger.info(
            f"Sandbox {self._sandbox_id} created, waiting for it to be ready..."
        )

    def _resume_existing_sandbox(self) -> None:
        """通过 ID 恢复现有沙箱。

        设置内部沙箱ID，直接调用resume端点。
        """
        assert self.sandbox_id is not None
        self._sandbox_id = self.sandbox_id
        logger.info(f"Resuming existing sandbox {self._sandbox_id}...")
        self._resume_sandbox()

    @tenacity.retry(
        stop=tenacity.stop_after_delay(300),
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
        retry=tenacity.retry_if_exception_type(RuntimeError),
        reraise=True,
    )
    def _wait_until_sandbox_ready(self) -> None:
        """等待沙箱变为 RUNNING 并响应。"""
        logger.debug("Checking sandbox status...")

        # GET /api/v1/sandboxes?id=<sandbox_id>
        resp = self._send_api_request(
            "GET",
            f"{self.cloud_api_url}/api/v1/sandboxes",
            params={"id": self._sandbox_id},
        )
        sandboxes = resp.json()

        if not sandboxes or sandboxes[0] is None:
            raise RuntimeError(f"Sandbox {self._sandbox_id} not found")

        sandbox = sandboxes[0]
        status = sandbox.get("status")
        logger.info(f"Sandbox status: {status}")

        if status == "RUNNING":
            # 从响应中更新 session_api_key 和 exposed_urls
            self._session_api_key = sandbox.get("session_api_key")
            self._exposed_urls = sandbox.get("exposed_urls") or []

            # 验证 Agent Server 可以访问
            agent_server_url = self._get_agent_server_url()
            if agent_server_url:
                self._check_agent_server_health(agent_server_url)
            return

        elif status == "STARTING":
            raise RuntimeError("Sandbox still starting")

        elif status in ("ERROR", "MISSING"):
            raise ValueError(f"Sandbox failed with status: {status}")

        elif status == "PAUSED":
            # 尝试恢复沙箱
            logger.info("Sandbox is paused, attempting to resume...")
            self._resume_sandbox()
            raise RuntimeError("Sandbox resuming, waiting for RUNNING status")

        else:
            logger.warning(f"Unknown sandbox status: {status}")
            raise RuntimeError(f"Unknown sandbox status: {status}")

    def _check_agent_server_health(self, agent_server_url: str) -> None:
        """检查Agent Server是否健康。"""
        health_url = f"{agent_server_url.rstrip('/')}/health"
        logger.debug(f"Checking agent server health at: {health_url}")
        try:
            with urlopen(health_url, timeout=5.0) as resp:
                status = getattr(resp, "status", 200)
                if 200 <= status < 300:
                    logger.debug("Agent server is healthy")
                    return
                raise RuntimeError(f"Health check failed with status: {status}")
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            raise RuntimeError(f"Agent server health check failed: {e}")

    def _resume_sandbox(self) -> None:
        """恢复暂停的沙箱。"""
        if not self._sandbox_id:
            return

        logger.info(f"Resuming sandbox {self._sandbox_id}...")
        self._send_api_request(
            "POST",
            f"{self.cloud_api_url}/api/v1/sandboxes/{self._sandbox_id}/resume",
            timeout=self.init_timeout,
        )

    def _get_agent_server_url(self) -> str | None:
        """从 exposed_urls 中提取 Agent Server URL。"""
        if not self._exposed_urls:
            return None

        for url_info in self._exposed_urls:
            if url_info.get("name") == AGENT_SERVER:
                return url_info.get("url")

        return None

    def pause(self) -> None:
        """暂停沙箱以节省资源。

        Note: OpenHands Cloud 目前不支持暂停沙箱。
        此方法会引发 NotImplementedError，直到 API 可用。

        Raises:
            NotImplementedError: 云 API 暂停端点尚不可用。
        """
        raise NotImplementedError(
            "OpenHandsCloudWorkspace.pause() is not yet supported - "
            "Cloud API pause endpoint not available"
        )

    def resume(self) -> None:
        """恢复暂停的沙箱。

        调用云端API上的/resume端点恢复沙箱。

        Raises:
            RuntimeError: 如果沙箱没有运行。
        """
        if not self._sandbox_id:
            raise RuntimeError("Cannot resume: sandbox is not running")

        logger.info(f"Resuming sandbox {self._sandbox_id}")
        self._resume_sandbox()
        self._wait_until_sandbox_ready()
        logger.info(f"Sandbox resumed: {self._sandbox_id}")

    def _send_api_request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """向云 API 发送 API 请求并进行错误处理。"""
        logger.debug(f"Sending {method} request to {url}")

        # 确保标头包含 API 键
        headers = kwargs.pop("headers", {})
        headers.update(self._api_headers)

        # 对 API 请求使用单独的客户端（不是 Agent Server 客户端）
        timeout = kwargs.pop("timeout", self.api_timeout)
        with httpx.Client(timeout=timeout) as api_client:
            response = api_client.request(method, url, headers=headers, **kwargs)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            try:
                error_detail = response.json()
                logger.error(f"Cloud API request failed: {error_detail}")
            except Exception:
                logger.error(f"Cloud API request failed: {response.text}")
            raise

        return response

    def cleanup(self) -> None:
        """通过删除沙箱来清理它。

        在本地智能体-服务器模式下，沙箱由外部管理，因此仅关闭 HTTP 客户端。
        """
        # 防止部分构造的实例上的 __del__ (e.g. 当验证在所有字段初始化之前失败时）。
        #
        try:
            local_mode = self.local_agent_server_mode
        except AttributeError:
            return

        if local_mode:
            try:
                if self._client:
                    self._client.close()
            except Exception:
                pass
            return

        if not self._sandbox_id:
            return

        try:
            if self.keep_alive:
                logger.info(f"Keeping sandbox {self._sandbox_id} alive")
                return

            logger.info(f"Deleting sandbox {self._sandbox_id}...")
            self._send_api_request(
                "DELETE",
                f"{self.cloud_api_url}/api/v1/sandboxes/{self._sandbox_id}",
                params={"sandbox_id": self._sandbox_id},
                timeout=30.0,
            )
            logger.info(f"Sandbox {self._sandbox_id} deleted")
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
        finally:
            self._sandbox_id = None
            self._session_api_key = None
            self._exposed_urls = None
            try:
                if self._client:
                    self._client.close()
            except Exception:
                pass

    # -----------------------------------------------------------------
    # 设置助手
    # -----------------------------------------------------------------

    @property
    def _settings_base_url(self) -> str:
        """沙箱范围设置端点的基础 URL。"""
        return f"{self.cloud_api_url}/api/v1/sandboxes/{self._sandbox_id}/settings"

    @property
    def _session_headers(self) -> dict[str, str]:
        """设置请求的标头（SESSION_API_KEY auth）。"""
        return {"X-Session-API-Key": self._session_api_key or ""}

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(_MAX_RETRIES),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=5),
        retry=tenacity.retry_if_exception(_is_retryable_error),
        reraise=True,
    )
    def get_llm(self, profile_name: str | None = None, **llm_kwargs: Any) -> LLM:
        """从用户的 SaaS 帐户获取 LLM 设置并返回 LLM。

        调用 ``GET /api/v1/users/me?expose_secrets=true`` 以检索用户的 LLM 配置或命名
        的 LLM 配置文件，并返回
        完全可用的 ``LLM`` 实例。 重试暂时性错误（网络问题、服务器 5xx）最多 3 次。

        Args:
            profile_name: 可选的 LLM 配置文件名称。 当提供时，加载
                命名配置文件而不是默认的 SaaS LLM 字段。
            **llm_kwargs: 传递给 LLM 的附加关键字参数
                构造函数，允许覆盖任何 LLM 参数 (e.g. ``model``, ``temperature``).

        Returns:
            使用用户的 SaaS 凭据配置的 LLM 实例。

        Raises:
            FileNotFoundError: 如果``profile_name``不存在。
            httpx.HTTPStatusError：如果API请求失败。
            RuntimeError: 如果沙箱没有运行。

        Example:
            >>> with OpenHandsCloudWorkspace(...) as workspace:
            ...     llm = workspace.get_llm(profile_name="fast")
            ...     agent = Agent(llm=llm, tools=get_default_tools())
        """
        from openhands.sdk.llm.llm import LLM

        if not self._sandbox_id:
            raise RuntimeError("Sandbox is not running")

        resp = self._send_api_request(
            "GET",
            f"{self.cloud_api_url}/api/v1/users/me",
            params={"expose_secrets": "true"},
            headers={"X-Session-API-Key": self._session_api_key or ""},
        )
        data = resp.json()

        if profile_name:
            profiles_payload = data.get("llm_profiles") or {}
            profiles = (
                profiles_payload.get("profiles")
                if isinstance(profiles_payload, dict)
                else None
            )
            profile_config = (
                profiles.get(profile_name) if isinstance(profiles, dict) else None
            )
            if not isinstance(profile_config, dict):
                raise FileNotFoundError(f"LLM profile '{profile_name}' not found")
            kwargs = dict(profile_config)
            kwargs["usage_id"] = f"profile:{profile_name}"
        else:
            kwargs = {}
            if data.get("llm_model"):
                kwargs["model"] = data["llm_model"]
            if data.get("llm_api_key"):
                kwargs["api_key"] = data["llm_api_key"]
            if data.get("llm_base_url"):
                kwargs["base_url"] = data["llm_base_url"]

        # 用户提供的 kwargs 优先
        kwargs.update(llm_kwargs)

        return LLM(**kwargs)

    def get_secrets(
        self,
        names: list[str] | None = None,
        *,
        agent_profile_id: str | None = None,
    ) -> dict[str, LookupSecret]:
        """为用户的 SaaS 机密构建 ``LookupSecret`` 引用。

        获取可用的列表机密  **names** 从的 SaaS (无原始值) 并返回一个字典
        ``LookupSecret`` 具有的对象 URLs 点到 per
        -机密端点。 的智能体-server 解析每个
        ``LookupSecret`` 是惰性的，因此原始值 ** 永远不会 ** 通过 SDK 客户端传输。

        返回的字典与``conversation.update_secrets()``兼容。

        Args:
            names: 要包含的机密名称的可选列表。 如果``None``，
                返回所有可用的机密。
            agent_profile_id: 可选智能体配置文件，其 ``secret_refs``
                限制 Agent Server 返回的名称。

        Returns:
            将机密名称映射到 ``LookupSecret`` 实例的字典。

        Raises:
            httpx.HTTPStatusError：如果API请求失败。
            RuntimeError: 如果沙箱没有运行。

        Example:
            >>> with OpenHandsCloudWorkspace(...) as workspace:
            ...     secrets = workspace.get_secrets()
            ...     conversation.update_secrets(secrets)
            ...
            ...     # 或子集
            ...     gh = workspace.get_secrets(names=["GITHUB_TOKEN"])
            ...     conversation.update_secrets(gh)
        """
        from openhands.sdk.secret import LookupSecret

        if not self._sandbox_id:
            raise RuntimeError("Sandbox is not running")

        request_kwargs: dict[str, Any] = {}
        if agent_profile_id is not None:
            request_kwargs["params"] = {"agent_profile_id": agent_profile_id}
        resp = self._send_settings_request(
            "GET", f"{self._settings_base_url}/secrets", **request_kwargs
        )
        data = resp.json()

        result: dict[str, LookupSecret] = {}
        for item in data.get("secrets", []):
            name = item["name"]
            if names is not None and name not in names:
                continue
            result[name] = LookupSecret(
                url=f"{self._settings_base_url}/secrets/{name}",
                headers={"X-Session-API-Key": self._session_api_key or ""},
                description=item.get("description"),
            )

        return result

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(_MAX_RETRIES),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=5),
        retry=tenacity.retry_if_exception(_is_retryable_error),
        reraise=True,
    )
    def get_mcp_config(self) -> dict[str, MCPServer]:
        """从用户的 SaaS 帐户获取 MCP 服务器。

        调用 ``GET /api/v1/users/me`` 检索用户的 MCP 配置并将其转换为 SDK 智能体所需
        的本机服务器映射。

        Returns:
            将服务器名称映射到服务器配置的字典，如果没有配置 MCP 服务器，则为空字典。

        Raises:
            httpx.HTTPStatusError：如果API请求失败。
            RuntimeError: 如果沙箱没有运行。

        Example:
            >>> with OpenHandsCloudWorkspace(...) as workspace:
            ...     llm = workspace.get_llm()
            ...     mcp_config = workspace.get_mcp_config()
            ...     agent = Agent(llm=llm, mcp_config=mcp_config, tools=...)
        """
        if not self._sandbox_id:
            raise RuntimeError("Sandbox is not running")

        resp = self._send_api_request(
            "GET",
            f"{self.cloud_api_url}/api/v1/users/me",
            headers={"X-Session-API-Key": self._session_api_key or ""},
        )
        data = resp.json()

        cloud_mcp_config = data.get("mcp_config")
        if not isinstance(cloud_mcp_config, Mapping):
            return {}

        mcp_config: dict[str, MCPServer] = {}

        server_sources: tuple[tuple[str, str | None, MCPTransport | None], ...] = (
            ("sse_servers", "sse", "sse"),
            ("shttp_servers", "shttp", "streamable-http"),
            ("stdio_servers", None, None),
        )
        for source, name_prefix, transport in server_sources:
            for index, server in enumerate(cloud_mcp_config.get(source) or []):
                if transport is None:
                    mcp_config[server["name"]] = MCPServer(
                        command=server["command"],
                        args=server.get("args", []),
                        env=server.get("env"),
                    )
                    continue

                assert name_prefix is not None
                mcp_config[f"{name_prefix}_{index}"] = MCPServer(
                    url=server["url"],
                    transport=transport,
                    headers=_mcp_api_key_headers(server.get("api_key")),
                    timeout=server.get("timeout")
                    if transport == "streamable-http"
                    else None,
                )

        return mcp_config

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(_MAX_RETRIES),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=5),
        retry=tenacity.retry_if_exception(_is_retryable_error),
        reraise=True,
    )
    def _send_settings_request(
        self, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        """向沙箱设置端点 (SESSION_API_KEY auth) 发送请求。

        重试暂时性错误最多 3 次（网络问题、服务器 5xx）。
        """
        headers = kwargs.pop("headers", {})
        headers.update(self._session_headers)

        timeout = kwargs.pop("timeout", self.api_timeout)
        with httpx.Client(timeout=timeout) as api_client:
            response = api_client.request(method, url, headers=headers, **kwargs)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            try:
                error_detail = response.json()
                logger.error(f"Settings request failed: {error_detail}")
            except Exception:
                logger.error(f"Settings request failed: {response.text}")
            raise

        return response

    def register_conversation(self, conversation_id: str) -> None:
        """使用此工作区注册对话 ID。

        创建后由 RemoteConversation 调用，将对话与工作区关联。 对话ID包含在发送到自动
        化服务的完成回调中。

        Args:
            conversation_id: 要注册的对话 ID
        """
        self._conversation_id = conversation_id
        logger.debug(f"Registered conversation: {conversation_id}")

    @property
    def conversation_id(self) -> str | None:
        """获取注册的会话ID。

        Returns:
            如果已注册，则为对话 ID，否则为 None。
        """
        return self._conversation_id

    def __del__(self) -> None:
        self.cleanup()

    def __enter__(self) -> OpenHandsCloudWorkspace:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._send_completion_callback(exc_type, exc_val)
        self.cleanup()

    def _send_completion_callback(
        self, exc_type: type | None, exc_val: BaseException | None
    ) -> None:
        """POST 自动化服务的完成状态（尽力而为）。

        由 ``__exit__`` 在 ``cleanup()`` 之前调用。 当
        ``AUTOMATION_CALLBACK_URL`` 环境变量未设置。

        如果通过以下方式注册，则在载荷中包含 ``conversation_id``
        ``register_conversation()`` 和 ``cost``（如果是通过以下方式注册的）
        ``register_cost()``.
        """
        try:
            callback_url = self._automation_callback_url
        except AttributeError:
            return

        if not callback_url:
            return

        status = "COMPLETED" if exc_type is None else "FAILED"
        payload: dict[str, Any] = {"status": status}
        if self._automation_run_id:
            payload["run_id"] = self._automation_run_id
        if exc_val is not None:
            payload["error"] = str(exc_val)

        # 如果已注册，请包含 conversation_id
        if self._conversation_id is not None:
            payload["conversation_id"] = self._conversation_id

        # 如果已注册，则包括累计 LLM 费用
        if self._accumulated_cost is not None:
            payload["cost"] = self._accumulated_cost

        try:
            headers = {"Authorization": f"Bearer {self.cloud_api_key}"}
            with httpx.Client(timeout=10.0) as cb_client:
                resp = cb_client.post(callback_url, json=payload, headers=headers)
                logger.info(f"Completion callback sent ({status}): {resp.status_code}")
        except Exception as e:
            logger.warning(f"Completion callback failed: {e}")

    # --- 存储库克隆方法 ---

    def _get_secret_value(self, name: str) -> str | None:
        """直接从沙箱设置 API 获取机密值。

        与返回 LookupSecret 引用的 get_secrets() 不同，此方法获取实际的机密值以用于
        git 克隆等操作。 重试瞬时故障最多 3 次。

        Args:
            name: 要获取的机密的名称（e.g.、“github_token”、“gitlab_token”）

        Returns:
            作为字符串的机密值，如果未找到或发生错误，则为 None。
        """
        if not self._sandbox_id or not self._session_api_key:
            return None

        # 验证机密名称以防止路径遍历
        if not name or "/" in name or ".." in name:
            logger.warning(f"Invalid secret name: {name}")
            return None

        # 使用重试逻辑处理暂时性故障
        @tenacity.retry(
            stop=tenacity.stop_after_attempt(_MAX_RETRIES),
            wait=tenacity.wait_exponential(multiplier=1, min=1, max=5),
            retry=tenacity.retry_if_exception(_is_retryable_error),
            reraise=True,
        )
        def _fetch_secret() -> httpx.Response:
            return self._send_settings_request(
                "GET", f"{self._settings_base_url}/secrets/{name}"
            )

        try:
            resp = _fetch_secret()
            return resp.text
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug(f"Secret '{name}' not found")
            else:
                logger.warning(f"Failed to fetch secret '{name}': {e}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching secret '{name}': {e}")
            return None

    # --- 存储库克隆和技能加载方法 ---
    # 这些方法委托给 RemoteWorkspace，但在这里明确定义以保持 API 兼容性（griffe 在检测子
    # 类方法移除时，即使方法被继承时，也会将其视为不兼容变更）。
    #

    def clone_repos(
        self,
        repos: list[RepoSource | dict[str, Any] | str],
        target_dir: str | Path | None = None,
    ) -> CloneResult:
        """将存储库克隆到工作区目录。

        请参阅 RemoteWorkspace.clone_repos 获取完整文档。
        """
        return super().clone_repos(repos, target_dir)

    def get_repos_context(self, repo_mappings: dict[str, RepoMapping]) -> str:
        """生成描述克隆存储库的上下文字符串。

        请参阅 RemoteWorkspace.get_repos_context 获取完整文档。
        """
        return super().get_repos_context(repo_mappings)

    def load_skills_from_agent_server(
        self,
        project_dirs: list[str | Path] | None = None,
        load_public: bool = True,
        load_user: bool = True,
        load_project: bool = True,
        load_org: bool = True,
        timeout: float = 60.0,
        base_context: AgentContext | None = None,
    ) -> tuple[list[Skill], AgentContext]:
        """从Agent Server加载技能。

        请参阅 RemoteWorkspace.load_skills_from_agent_server 获取完整文档。
        """
        return super().load_skills_from_agent_server(
            project_dirs=project_dirs,
            load_public=load_public,
            load_user=load_user,
            load_project=load_project,
            load_org=load_org,
            timeout=timeout,
            base_context=base_context,
        )

    def _call_skills_api(
        self,
        project_dir: str,
        load_public: bool = False,
        load_user: bool = False,
        load_project: bool = False,
        load_org: bool = False,
        timeout: float = 60.0,
    ) -> list[dict[str, Any]]:
        """调用智能体-服务器 /api/skills 端点。

        返回技能指令列表，或出错时返回空列表。 重试瞬时故障最多 3 次。
        """
        payload = {
            "load_public": load_public,
            "load_user": load_user,
            "load_project": load_project,
            "load_org": load_org,
            "project_dir": project_dir,
            "sandbox_config": None,
        }

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._session_api_key:
            headers["X-Session-API-Key"] = self._session_api_key

        # 使用重试逻辑处理暂时性故障
        @tenacity.retry(
            stop=tenacity.stop_after_attempt(_MAX_RETRIES),
            wait=tenacity.wait_exponential(multiplier=1, min=1, max=5),
            retry=tenacity.retry_if_exception(_is_retryable_error),
            reraise=True,
        )
        def _fetch_skills() -> httpx.Response:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    f"{self.host}/api/skills",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                return resp

        try:
            resp = _fetch_skills()
            data = resp.json()
            logger.debug(f"Agent-server sources: {data.get('sources', {})}")
            return data.get("skills", [])
        except httpx.HTTPStatusError as e:
            logger.error(f"Agent-server HTTP error {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Failed to connect to agent-server: {e}")
            return []
