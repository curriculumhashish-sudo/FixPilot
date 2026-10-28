import json
import os
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote
from urllib.request import urlopen

import httpx
import tenacity
from pydantic import PrivateAttr, ValidationError

from openhands.sdk.git.models import GitChange, GitDiff
from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.config import MCPServer
from openhands.sdk.settings import SecretsListResponse, SettingsResponse
from openhands.sdk.workspace.base import BaseWorkspace
from openhands.sdk.workspace.models import CommandResult, FileOperationResult
from openhands.sdk.workspace.remote.remote_workspace_mixin import RemoteWorkspaceMixin
from openhands.sdk.workspace.repo import (
    CloneResult,
    RepoMapping,
    RepoSource,
    clone_repos as _clone_repos_helper,
    get_repos_context as _get_repos_context_helper,
)


if TYPE_CHECKING:
    from openhands.sdk.context import AgentContext
    from openhands.sdk.llm.llm import LLM
    from openhands.sdk.secret import LookupSecret
    from openhands.sdk.settings import OpenHandsAgentSettings
    from openhands.sdk.settings.model import ACPAgentSettings, LLMAgentSettings
    from openhands.sdk.skills import Skill


logger = get_logger(__name__)

# 短暂 API 次失败的尝试次数重试
_MAX_RETRIES = 3


def _is_retryable_error(error: BaseException) -> bool:
    """对于值得重试的暂时性错误，返回 True。"""
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code >= 500
    return isinstance(error, (httpx.ConnectError, httpx.TimeoutException))


class RemoteWorkspace(RemoteWorkspaceMixin, BaseWorkspace):
    """连接到 OpenHands Agent Server 的远程工作区实现。

    RemoteWorkspace 提供对远程 OpenHands Agent Server 上运行的沙盒环境的访问。 这是生
    产部署的推荐方法，因为它提供了更好的隔离和
    安全性。

    支持通过环境变量退出时可选的完成回调：
      - ``AUTOMATION_CALLBACK_URL`` — URL 至 POST 完成状态至
      - ``AUTOMATION_CALLBACK_API_KEY`` — 持有者令牌用于回调身份验证（可选）
      - ``AUTOMATION_RUN_ID`` — 要包含在回调载荷中的运行 ID（可选）

    Example:
        >>> workspace = RemoteWorkspace(
        ...     host="https://agent-server.example.com",
        ...     working_dir="/workspace"
        ... )
        >>> with workspace:
        ...     result = workspace.execute_command("ls -la")
        ...     content = workspace.read_file("README.md")
    """

    _client: httpx.Client | None = PrivateAttr(default=None)

    def reset_client(self) -> None:
        """重置 HTTP 客户端以强制重新初始化。

        当连接参数（主机，api_key）发生更改并且需要使用新值重新创建客户端时，这非常有
        用。
        """
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None

    @property
    def client(self) -> httpx.Client:
        client = self._client
        if client is None:
            # 为HTTP个请求配置合理的超时
            # - 连接：10秒建立连接
            # - 读取：600 秒（10 分钟）读取响应（对于 LLM 操作）
            # - write: 10秒发送请求
            # - 池：从池中获取连接需要 10 秒
            timeout = httpx.Timeout(
                connect=10.0, read=self.read_timeout, write=10.0, pool=10.0
            )
            client = httpx.Client(
                base_url=self.host,
                timeout=timeout,
                headers=self._headers,
                limits=httpx.Limits(max_connections=self.max_connections),
            )
            self._client = client
        return client

    def _execute(self, generator: Generator[dict[str, Any], httpx.Response, Any]):
        try:
            kwargs = next(generator)
            while True:
                response = self.client.request(**kwargs)
                kwargs = generator.send(response)
        except StopIteration as e:
            return e.value

    def get_server_info(self) -> dict[str, Any]:
        """从智能体-服务器返回服务器元数据。

        这对于调试本地 SDK 和远程智能体服务器映像之间的版本不匹配非常有用。

        Returns:
            GET /server_info. 返回的 JSON 可序列化字典
        """
        response = self.client.get("/server_info")
        response.raise_for_status()
        data = response.json()
        assert isinstance(data, dict)
        return data

    def start_command(
        self,
        command: str,
        cwd: str | Path | None = None,
        timeout: float = 30,
    ) -> str:
        """启动命令并返回其 ID，无需等待完成。"""
        return self._execute(self._start_command_generator(command, cwd, timeout))

    def get_command_output(
        self, command_id: str | None = None
    ) -> dict[str, Any] | None:
        """读取最新输出； 缺少退出代码意味着它仍在运行。"""
        return self._execute(self._get_command_output_generator(command_id))

    def stop_command(self, command_id: str) -> None:
        """通过 id 停止正在运行的 bash 命令。

        未知或已经完成的 id 是无操作的，与服务器的幂等性契约相匹配。
        """
        self._execute(self._stop_command_generator(command_id))

    def get_runtime_session_key(self) -> str:
        """获取此对话运行时的作用域工作人员凭据。"""
        return self._execute(self._runtime_lifecycle_generator(release=False))

    def release_runtime(self) -> None:
        """释放执行资源，同时保留对话历史记录。"""
        self._execute(self._runtime_lifecycle_generator(release=True))

    def execute_command(
        self,
        command: str,
        cwd: str | Path | None = None,
        timeout: float = 30.0,
    ) -> CommandResult:
        """在远程系统上执行 bash 命令。

        此方法通过远程 Agent Server API 启动 bash 命令，然后轮询输出，直到命令完成。

        Args:
            command: 要执行的 bash 命令
            cwd: 工作目录（可选）
            timeout: 超时以秒为单位

        Returns:
            CommandResult: 包含 stdout、stderr、exit_code 和其他元数据的结果
        """
        generator = self._execute_command_generator(command, cwd, timeout)
        result = self._execute(generator)
        return result

    def file_upload(
        self,
        source_path: str | Path | bytes,
        destination_path: str | Path,
    ) -> FileOperationResult:
        """将文件上传到远程系统。

        读取本地文件并通过HTTPAPI发送到远程系统。

        Args:
            source_path: 本地文件路径或内存中字节
            destination_path: 文件应上传到远程系统的路径

        Returns:
            FileOperationResult: 包含成功状态和元数据的结果
        """
        generator = self._file_upload_generator(source_path, destination_path)
        result = self._execute(generator)
        return result

    def file_download(
        self,
        source_path: str | Path,
        destination_path: str | Path,
    ) -> FileOperationResult:
        """从远程系统下载文件。

        通过HTTPAPI从远程系统请求文件并将其保存在本地。

        Args:
            source_path: 远程系统上源文件的路径
            destination_path: 文件应保存在本地的路径

        Returns:
            FileOperationResult: 包含成功状态和元数据的结果
        """
        generator = self._file_download_generator(source_path, destination_path)
        result = self._execute(generator)
        return result

    def git_changes(self, path: str | Path) -> list[GitChange]:
        """在给定的路径中获取存储库的 git 更改。

        Args:
            path: git 存储库的路径

        Returns:
            list[GitChange]：更改列表

        Raises:
            Exception: 如果路径不是 git 存储库或获取更改失败
        """
        generator = self._git_changes_generator(path)
        result = self._execute(generator)
        return result

    def git_diff(self, path: str | Path) -> GitDiff:
        """获取给定路径中文件的 git diff。

        Args:
            path: 文件路径

        Returns:
            GitDiff: git diff

        Raises:
            Exception: 如果路径不是 git 存储库或获取 diff 失败
        """
        generator = self._git_diff_generator(path)
        result = self._execute(generator)
        return result

    @property
    def alive(self) -> bool:
        """通过查询运行状况端点来检查远程工作区是否处于活动状态。

        Returns:
            如果运行状况端点返回成功响应，则为 True，否则为 False。
        """
        try:
            health_url = f"{self.host}/health"
            with urlopen(health_url, timeout=5.0) as resp:
                status = getattr(resp, "status", 200)
                return 200 <= status < 300
        except Exception:
            return False

    @property
    def default_conversation_tags(self) -> dict[str, str] | None:
        """应用于使用此工作区创建的对话的默认标签。

        从环境变量由自动化调度器注入的自动化元数据中导出，因此任何远程工作区（包括本
        地智能体服务器）都会在它创建的对话中为自动化上下文打上标签。

        标签包括（根据 API 要求，键为小写字母数字）：
          - automationtrigger: 触发器类型（e.g.、'cron'、'Webhook'、'手动'）
          - automationid: 自动化的唯一标识符
          - automationname: 人类可读的自动化名称
          - automationrunid: 特定的运行标识符

        Returns:
            标签键值对的字典（当不存在自动化环境变量时为空）。 子类 (e.g.,
            OpenHandsCloudWorkspace) 可以通过附加上下文来扩展它
            。
        """
        tags: dict[str, str] = {}

        # 解析AUTOMATION_EVENT_PAYLOAD（由调度程序注入）
        payload_str = os.environ.get("AUTOMATION_EVENT_PAYLOAD")
        if payload_str:
            try:
                payload = json.loads(payload_str)
                if isinstance(payload, dict):
                    if payload.get("trigger"):
                        tags["automationtrigger"] = str(payload["trigger"])
                    if payload.get("automation_id"):
                        tags["automationid"] = str(payload["automation_id"])
                    if payload.get("automation_name"):
                        tags["automationname"] = str(payload["automation_name"])
            except (json.JSONDecodeError, TypeError):
                logger.error("Failed to parse AUTOMATION_EVENT_PAYLOAD")

        run_id = os.environ.get("AUTOMATION_RUN_ID")
        if run_id:
            tags["automationrunid"] = run_id

        return tags

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
        """获取最近注册的会话 ID。

        Returns:
            如果已注册，则为对话 ID，否则为 None。
        """
        return self._conversation_id

    def __exit__(
        self, exc_type: type | None, exc_val: BaseException | None, exc_tb: Any
    ) -> None:
        """退出工作区上下文，发送完成回调，并清理。

        在调用父清理之前发送完成回调（如果通过环境变量配置）。 覆盖 ``__exit__`` 的子
        类应该调用
        ``super().__exit__(...)`` 以确保回调已发送。
        """
        self._send_completion_callback(exc_type, exc_val)
        super().__exit__(exc_type, exc_val, exc_tb)

    # ── 设置方法──────────────────────────────────────────────── 这些方法从智能体服务器
    # 的已持久化设置端点中获取配置。 像 OpenHandsCloudWorkspace 这样的子类可以覆盖以使用
    # 替代端点 (e.g., Cloud API)。
    #

    def _fetch_settings_response(
        self, *, expose_secrets: bool = True
    ) -> SettingsResponse:
        """调用 ``GET /api/settings`` 并返回经过验证的响应。"""
        headers = dict(self._headers)
        if expose_secrets:
            headers["X-Expose-Secrets"] = "plaintext"

        response = self.client.get("/api/settings", headers=headers)
        response.raise_for_status()
        return SettingsResponse.model_validate(response.json())

    def _fetch_agent_settings(
        self,
    ) -> "OpenHandsAgentSettings | LLMAgentSettings | ACPAgentSettings":
        """从 ``GET /api/settings`` 返回已验证的智能体设置。

        使用 ``X-Expose-Secrets: plaintext`` 所以机密字段 (e.g. LLM api_key) 以纯字符
        串形式返回。 经验证的
        ``SettingsResponse`` 被缩小到
        :meth:`SettingsResponse.get_agent_settings`，选择正确的
        受歧视联合变体。
        """
        return self._fetch_settings_response().get_agent_settings()

    def _fetch_llm_profile_config(self, profile_name: str) -> dict[str, Any]:
        """调用 ``GET /api/profiles/{name}`` 并返回明文 LLM 配置。"""
        headers = dict(self._headers)
        headers["X-Expose-Secrets"] = "plaintext"

        response = self.client.get(
            f"/api/profiles/{quote(profile_name, safe='')}",
            headers=headers,
        )
        if response.status_code == 404:
            raise FileNotFoundError(f"LLM profile '{profile_name}' not found")
        response.raise_for_status()

        config = response.json().get("config")
        if not isinstance(config, dict):
            raise ValueError(f"LLM profile '{profile_name}' has invalid config")
        return dict(config)

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(_MAX_RETRIES),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=5),
        retry=tenacity.retry_if_exception(_is_retryable_error),
        reraise=True,
    )
    def get_llm(self, profile_name: str | None = None, **llm_kwargs: Any) -> "LLM":
        """获取活动的或明确命名的 LLM 配置文件。

        当未给出 ``profile_name`` 时，首先解析已持久化 ``active_profile`` 指针（因此
        遵循 UI 通告的默认值）。 如果没有配置
        ``active_profile``，则旧版
        ``agent_settings.llm`` 载荷用作回退方案（为未采用命名配置文件的服务器保留向后
        兼容性）。

        Args:
            profile_name: 可选的 LLM 配置文件名称。 当提供时，加载
                命名配置文件而不是解析活动配置文件。
            **llm_kwargs: 覆盖配置文件的附加关键字参数
                值（e.g.、``model``、``temperature``）。

        Returns:
            使用活动或命名配置文件配置的 LLM 实例。

        Raises:
            FileNotFoundError: 如果``profile_name``不存在。
            httpx.HTTPStatusError：如果API请求失败。
            RuntimeError: 如果工作区主机未设置。
            ValueError: 如果没有活动配置文件且智能体设置适用于
                一个 ACP 智能体，没有 LLM。

        Example:
            >>> with DockerWorkspace(...) as workspace:
            ...     llm = workspace.get_llm(profile_name="fast")
            ...     agent = Agent(llm=llm, tools=get_default_tools())
        """
        from openhands.sdk.llm.llm import LLM
        from openhands.sdk.settings import OpenHandsAgentSettings

        if not self.host or self.host == "undefined":
            raise RuntimeError("Workspace host is not set")

        if profile_name is None:
            settings_response = self._fetch_settings_response(expose_secrets=False)
            resolved_profile_name = settings_response.active_profile
            if resolved_profile_name in (None, ""):
                settings_response = self._fetch_settings_response()
                agent_settings = settings_response.get_agent_settings()
                if not isinstance(agent_settings, OpenHandsAgentSettings):
                    raise ValueError(
                        "No LLM profile is active and the agent settings are for "
                        "an ACP agent, which has no LLM; pass profile_name."
                    )
                if not llm_kwargs:
                    return agent_settings.llm
                llm_data = agent_settings.llm.model_dump(
                    context={"expose_secrets": "plaintext"}
                )
            else:
                llm_data = self._fetch_llm_profile_config(resolved_profile_name)
                llm_data["usage_id"] = f"profile:{resolved_profile_name}"
        else:
            llm_data = self._fetch_llm_profile_config(profile_name)
            llm_data["usage_id"] = f"profile:{profile_name}"

        llm_data.update(llm_kwargs)
        return LLM(**llm_data)

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(_MAX_RETRIES),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=5),
        retry=tenacity.retry_if_exception(_is_retryable_error),
        reraise=True,
    )
    def get_secrets(
        self,
        names: list[str] | None = None,
        *,
        agent_profile_id: str | None = None,
    ) -> dict[str, "LookupSecret"]:
        """为智能体服务器的机密构建 ``LookupSecret`` 引用。

        获取可用的列表机密  **names** 从的智能体-server (no raw values) and returns a
         dict of
        ``LookupSecret`` 具有的对象 URLs 点到 per-机密端点。 的智能体-server 解析每个
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
            RuntimeError: 如果工作区主机未设置。

        Example:
            >>> with DockerWorkspace(...) as workspace:
            ...     secrets = workspace.get_secrets()
            ...     conversation.update_secrets(secrets)
            ...
            ...     # 或子集
            ...     gh = workspace.get_secrets(names=["GITHUB_TOKEN"])
            ...     conversation.update_secrets(gh)
        """
        from openhands.sdk.secret import LookupSecret

        if not self.host or self.host == "undefined":
            raise RuntimeError("Workspace host is not set")

        request_kwargs: dict[str, Any] = {"headers": self._headers}
        if agent_profile_id is not None:
            request_kwargs["params"] = {"agent_profile_id": agent_profile_id}
        response = self.client.get("/api/settings/secrets", **request_kwargs)
        response.raise_for_status()

        # 使用共享 SDK 模型验证响应
        data = SecretsListResponse.model_validate(response.json())

        result: dict[str, LookupSecret] = {}
        for item in data.secrets:
            if names is not None and item.name not in names:
                continue
            result[item.name] = LookupSecret(
                url=f"{self.host}/api/settings/secrets/{item.name}",
                headers=dict(self._headers),
                description=item.description,
            )

        return result

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(_MAX_RETRIES),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=5),
        retry=tenacity.retry_if_exception(_is_retryable_error),
        reraise=True,
    )
    def get_mcp_config(self) -> dict[str, MCPServer]:
        """从智能体服务器的已持久化设置中获取 MCP 服务器。

        使用 ``X-Expose-Secrets: plaintext`` 标头调用 ``GET /api/settings`` 以检索
        MCP 服务器并返回与
        ``Agent(mcp_config=...)`` 夸格。

        Returns:
            将服务器名称映射到服务器配置的字典，如果没有配置 MCP 服务器，则为空字典。

        Raises:
            httpx.HTTPStatusError：如果API请求失败。
            RuntimeError: 如果工作区主机未设置。

        Example:
            >>> with DockerWorkspace(...) as workspace:
            ...     llm = workspace.get_llm()
            ...     mcp_config = workspace.get_mcp_config()
            ...     agent = Agent(llm=llm, mcp_config=mcp_config, tools=...)
        """
        from openhands.sdk.settings import OpenHandsAgentSettings

        if not self.host or self.host == "undefined":
            raise RuntimeError("Workspace host is not set")

        settings = self._fetch_agent_settings()

        # 运行时 MCP 工具只有在 OpenHandsAgentSettings, not ACPAgentSettings.
        if not isinstance(settings, OpenHandsAgentSettings):
            return {}

        return settings.mcp_config

    # ── 存储库克隆方法──────────────────────────────────────────

    def _get_secret_value(self, name: str) -> str | None:
        """直接从 Agent Server 的设置 API 获取机密值。

        与返回 LookupSecret 引用的 get_secrets() 不同，此方法获取实际的机密值以用于
        git 克隆等操作。 重试瞬时故障最多 3 次。

        Args:
            name: 要获取的机密的名称（e.g.、“github_token”、“gitlab_token”）

        Returns:
            作为字符串的机密值，如果未找到或发生错误，则为 None。
        """
        if not self.host or self.host == "undefined":
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
            resp = self.client.get(
                f"/api/settings/secrets/{name}",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp

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

    def clone_repos(
        self,
        repos: list[RepoSource | dict[str, Any] | str],
        target_dir: str | Path | None = None,
    ) -> CloneResult:
        """将存储库克隆到工作区目录。

        将指定存储库克隆到有意义的目录名称（e.g.、“OpenHands-CLI”而不是“repo_0”）。
        自动从 Agent Server 的机密中获取
        GitHub、GitLab、Bitbucket 和 Azure DevOps token 作为身份验证。

        Args:
            repos: 要克隆的存储库列表。 可以是：
                - RepoSource 个对象列表
                - 带有“url”、可选“ref”和“provider”键的字典列表
                - 完整 URL 字符串列表 (e.g., " https://github.com/owner/repo" )
                Note: URLs（所有者/仓库）需要明确的 'provider' 字段。
            target_dir: 要克隆到的目录。 默认为 self.working_dir。

        Returns:
            CloneResult 包含：
                - success_count: 成功克隆的存储库数量
                - failed_repos: URLs 个未能克隆的仓库列表
                - repo_mappings: 字典，键为URLs，值为RepoMapping的对象

        Example:
            >>> with RemoteWorkspace(...) as workspace:
            ...     # URLs 全部克隆（自动检测提供商）
            ...     result = workspace.clone_repos([
            ...         "https://github.com/owner/repo1",
            ...         {"url": "https://gitlab.com/owner/repo2", "ref": "main"},
            ...     ])
            ...
            ...     # 使用短 URLs (提供者必填)
            ...     result = workspace.clone_repos([
            ...         {"url": "owner/repo1", "provider": "github"},
            ...         {"url": "owner/repo2", "provider": "gitlab", "ref": "v1.0"},
            ...     ])
            ...
            ...     # 访问克隆的仓库路径
            ...     for url, mapping in result.repo_mappings.items():
            ...         print(f"{url} -> {mapping.local_path}")
        """
        # 使用 model_validate 将存储库规范化为 RepoSource 对象，这确保了所有输入格式的一
        # 致性验证
        #
        normalized_repos: list[RepoSource] = []
        try:
            for repo in repos:
                if isinstance(repo, RepoSource):
                    normalized_repos.append(repo)
                else:
                    # model_validate 通过 model_validator 处理字典和字符串
                    normalized_repos.append(RepoSource.model_validate(repo))
        except ValidationError as e:
            raise ValueError(f"Invalid repository specification: {e}") from e

        # 确定目标目录
        if target_dir is None:
            target_path = Path(self.working_dir)
        elif isinstance(target_dir, str):
            target_path = Path(target_dir)
        else:
            target_path = target_dir

        # 使用 _get_secret_value 作为 token 获取器克隆存储库这会根据每个存储库的提供者延
        # 迟获取 token
        #
        return _clone_repos_helper(
            repos=normalized_repos,
            target_dir=target_path,
            token_fetcher=self._get_secret_value,
        )

    def get_repos_context(self, repo_mappings: dict[str, RepoMapping]) -> str:
        """生成描述智能体克隆存储库的上下文字符串。

        此方法生成一个 Markdown 格式的字符串，可以将其添加到智能体提示词之前，以通知
        智能体有关可用存储库的信息。

        Args:
            repo_mappings: 字典 URLs 对应 RepoMapping 对象，通常
                调用 clone_repos() 后从 CloneResult.repo_mappings 获得。

        Returns:
            Markdown 格式的上下文字符串，如果没有存储库则为空字符串。

        Example:
            >>> with RemoteWorkspace(...) as workspace:
            ...     result = workspace.clone_repos(["owner/repo"])
            ...     context = workspace.get_repos_context(result.repo_mappings)
            ...     prompt = f"{context}\\n\\n{user_prompt}"
        """
        return _get_repos_context_helper(repo_mappings)

    # ── 技能加载方式──────────────────────────────────────────────

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
        headers.update(self._headers)

        # 使用重试逻辑处理暂时性故障
        @tenacity.retry(
            stop=tenacity.stop_after_attempt(_MAX_RETRIES),
            wait=tenacity.wait_exponential(multiplier=1, min=1, max=5),
            retry=tenacity.retry_if_exception(_is_retryable_error),
            reraise=True,
        )
        def _fetch_skills() -> httpx.Response:
            resp = self.client.post(
                f"{self.host}/api/skills",
                json=payload,
                headers=headers,
                timeout=timeout,
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

    def _add_skills_to_dict(
        self,
        skills_by_name: dict[str, dict[str, Any]],
        skill_list: list[dict[str, Any]],
    ) -> None:
        """将技能添加到字典中，按名称键入（稍后的值覆盖）。"""
        for skill_data in skill_list:
            name = skill_data.get("name", "unknown")
            skills_by_name[name] = skill_data

    def _load_skills_multi_dir(
        self,
        project_dirs: list[str],
        load_public: bool,
        load_user: bool,
        load_project: bool,
        load_org: bool,
        timeout: float,
    ) -> dict[str, dict[str, Any]]:
        """指定多个项目目录时加载技能。"""
        skills_by_name: dict[str, dict[str, Any]] = {}

        # 加载全局技能（公共/用户/组织）一次
        logger.debug("Loading public/user/org skills...")
        global_skills = self._call_skills_api(
            project_dir=self.working_dir,
            load_public=load_public,
            load_user=load_user,
            load_project=False,
            load_org=load_org,
            timeout=timeout,
        )
        self._add_skills_to_dict(skills_by_name, global_skills)

        # 从每个目录加载项目技能
        if not load_project:
            return skills_by_name

        for dir_path in project_dirs:
            logger.debug(f"Loading project skills from {dir_path}...")
            proj_skills = self._call_skills_api(
                project_dir=dir_path,
                load_project=True,
                timeout=timeout,
            )
            self._add_skills_to_dict(skills_by_name, proj_skills)

        return skills_by_name

    def _load_skills_single_dir(
        self,
        load_public: bool,
        load_user: bool,
        load_project: bool,
        load_org: bool,
        timeout: float,
    ) -> dict[str, dict[str, Any]]:
        """从工作目录加载所有技能。"""
        logger.debug("Loading all skills from working_dir...")
        all_skills = self._call_skills_api(
            project_dir=self.working_dir,
            load_public=load_public,
            load_user=load_user,
            load_project=load_project,
            load_org=load_org,
            timeout=timeout,
        )

        skills_by_name: dict[str, dict[str, Any]] = {}
        self._add_skills_to_dict(skills_by_name, all_skills)
        return skills_by_name

    def _convert_skills_dict_to_list(
        self, skills_by_name: dict[str, dict[str, Any]]
    ) -> list["Skill"]:
        """将技能指令转换为 SDK 技能对象。"""
        loaded_skills: list[Skill] = []
        for skill_data in skills_by_name.values():
            try:
                skill = self._convert_skill_data_to_skill(skill_data)
                loaded_skills.append(skill)
            except Exception as e:
                skill_name = skill_data.get("name", "unknown")
                logger.warning(f"Failed to convert skill {skill_name}: {e}")
        return loaded_skills

    def _convert_skill_data_to_skill(self, skill_data: dict[str, Any]) -> "Skill":
        """将技能字典从 API 响应转换为 SDK 技能对象。

        Args:
            skill_data: 包含名称、内容、触发器、来源、描述等的字典。

        Returns:
            技能对象
        """
        from openhands.sdk.skills import KeywordTrigger, Skill, TaskTrigger

        trigger = None
        triggers = skill_data.get("triggers", [])

        if triggers:
            # 根据内容判断触发类型（与OpenHands逻辑相同）
            # 注意：在调用 .startswith() 之前验证元素是否为字符串
            if any(isinstance(t, str) and t.startswith("/") for t in triggers):
                trigger = TaskTrigger(triggers=triggers)
            else:
                trigger = KeywordTrigger(keywords=triggers)

        return Skill(
            name=skill_data.get("name", "unknown"),
            content=skill_data.get("content", ""),
            trigger=trigger,
            source=skill_data.get("source"),
            description=skill_data.get("description"),
            is_agentskills_format=skill_data.get("is_agentskills_format", False),
            disable_model_invocation=skill_data.get("disable_model_invocation", False),
        )

    def load_skills_from_agent_server(
        self,
        project_dirs: list[str | Path] | None = None,
        load_public: bool = True,
        load_user: bool = True,
        load_project: bool = True,
        load_org: bool = True,
        timeout: float = 60.0,
        base_context: "AgentContext | None" = None,
    ) -> tuple[list["Skill"], "AgentContext"]:
        """通过智能体服务器的/api/skills端点加载技能。

        该方法调用沙箱内部运行的智能体服务器，从所有配置的来源加载技能，这与V1会话如
        何从OpenHands加载技能的方式相同。

        当提供 project_dirs 时（e.g.，克隆存储库的目录），项目技能将从每个目录单独加
        载并合并。 技能按名称进行重复数据删除，较晚的目录优先于较早的
        目录。

        Args:
            project_dirs: 从中加载项目技能的目录列表。
                如果 None，则仅使用 self.working_dir。
            load_public: 从 OpenHands/extension 存储库加载公共技能。
            load_user: 从 ~/.openhands/skills/. 加载用户技能
            load_project: 从工作区目录加载项目技能。
            load_org: 加载组织级别的技能。
            timeout: 请求超时（以秒为单位）。
            base_context: 现有的AgentContext要保留。 其所有的
                除 `skills` 和 `load_public_skills` 之外的字段均保留，此方法始终根据
                是否找到技能来设置这两个字段。 默认为
                None，它从新的 AgentContext 开始——今天的行为。

        Returns:
            （技能对象列表，AgentContext）的元组。 AgentContext 预先配置了加载的技能
            和
            load_public_skills=False to avoid duplicates (or True if no skills loaded).

        Example:
            >>> with RemoteWorkspace(...) as workspace:
            ...     # 使用 working_dir 加载所有技能
            ...     skills, context = workspace.load_skills_from_agent_server()
            ...
            ...     # 加载克隆仓库中的技能
            ...     result = workspace.clone_repos(["owner/repo1", "owner/repo2"])
            ...     repo_dirs = [m.local_path for m in result.repo_mappings.values()]
            ...     skills, context = workspace.load_skills_from_agent_server(
            ...         project_dirs=repo_dirs
            ...     )
            ...
            ...     # 使用智能体
            ...     agent = agent.model_copy(update={"agent_context": context})
        """
        from openhands.sdk.context import AgentContext

        # 验证工作区已准备好进行 API 次呼叫
        # 注意：self.host 默认为“未定义”，因此也请检查一下
        if not self.host or self.host == "undefined":
            raise RuntimeError(
                "Workspace not initialized. Ensure the workspace is started "
                "before loading skills."
            )

        logger.info("Loading skills via agent-server...")
        logger.debug(f"Agent-server URL: {self.host}")

        # 根据是否指定多个项目目录加载技能
        if project_dirs:
            dirs = [str(d) if isinstance(d, Path) else d for d in project_dirs]
            skills_by_name = self._load_skills_multi_dir(
                dirs, load_public, load_user, load_project, load_org, timeout
            )
        else:
            skills_by_name = self._load_skills_single_dir(
                load_public, load_user, load_project, load_org, timeout
            )

        # 转换为 SDK 技能对象
        loaded_skills = self._convert_skills_dict_to_list(skills_by_name)

        logger.info(f"Loaded {len(loaded_skills)} skills")
        if loaded_skills:
            logger.debug(f"Skills: {[s.name for s in loaded_skills]}")

        # 使用新加载的技能更新 `base_context`（或者如果给出 None，则重新开始）——保留调用
        # 者配置的所有其他字段。 如果 None 已加载，则退回到公共技能。
        #
        base = base_context if base_context is not None else AgentContext()
        if loaded_skills:
            agent_context = base.model_copy(
                update={"skills": loaded_skills, "load_public_skills": False}
            )
        else:
            logger.warning("No skills loaded, falling back to public skills")
            agent_context = base.model_copy(
                update={"skills": [], "load_public_skills": True}
            )

        # ``model_copy`` 跳过验证器，因此重新运行应用 ``load_*_skills`` 和
        # ``disabled_skills`` 拒绝列表的解决方案。
        #
        return loaded_skills, agent_context.resolve_auto_skills()
