"""测试 OpenHandsCloudWorkspace 设置方法。

测试 get_llm()、get_secrets() 和 get_mcp_config()。

get_llm() 返回一个实数 LLM 以及来自 SaaS 的原始 api_key。 get_secrets() 返回
LookupSecret 引用 — 原始值仅流向
SaaS→沙箱，从不流向 SDK 客户端。 get_mcp_config() 以 SDK 智能体格式返回 MCP 服务器配
置。
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from openhands.sdk.mcp.config import dump_mcp_config
from openhands.sdk.secret import LookupSecret
from openhands.workspace.cloud.workspace import OpenHandsCloudWorkspace


SANDBOX_ID = "sb-test-123"
SESSION_KEY = "session-key-abc"
CLOUD_URL = "https://app.all-hands.dev"


@pytest.fixture
def mock_workspace():
    """创建具有模拟的沙箱生命周期的工作区实例。"""
    with patch.object(
        OpenHandsCloudWorkspace, "model_post_init", lambda self, ctx: None
    ):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url=CLOUD_URL,
            cloud_api_key="test-api-key",
            host="http://localhost:8000",
        )
    # 模拟运行的沙箱
    workspace._sandbox_id = SANDBOX_ID
    workspace._session_api_key = SESSION_KEY
    yield workspace
    workspace._sandbox_id = None
    workspace._session_api_key = None


class TestGetLLM:
    """测试 OpenHandsCloudWorkspace.get_llm()。"""

    def test_get_llm_returns_usable_llm(self, mock_workspace):
        """get_llm 获取 SaaS 配置并返回可用的 LLM。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "llm_model": "anthropic/claude-sonnet-4-20250514",
            "llm_api_key": "sk-test-key-123",
            "llm_base_url": "https://litellm.example.com",
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_api_request", return_value=mock_response
        ) as mock_req:
            llm = mock_workspace.get_llm()

        mock_req.assert_called_once_with(
            "GET",
            f"{CLOUD_URL}/api/v1/users/me",
            params={"expose_secrets": "true"},
            headers={"X-Session-API-Key": SESSION_KEY},
        )
        assert llm.model == "anthropic/claude-sonnet-4-20250514"
        # api_key 是实数 SecretStr（LLM 验证器转换为 str → SecretStr）
        assert isinstance(llm.api_key, SecretStr)
        assert llm.api_key.get_secret_value() == "sk-test-key-123"
        assert llm.base_url == "https://litellm.example.com"

    def test_get_llm_allows_overrides(self, mock_workspace):
        """用户提供的 kwargs 覆盖 SaaS 设置。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "llm_model": "anthropic/claude-sonnet-4-20250514",
            "llm_api_key": "sk-test-key",
            "llm_base_url": None,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_api_request", return_value=mock_response
        ):
            llm = mock_workspace.get_llm(model="gpt-4o", temperature=0.5)

        assert llm.model == "gpt-4o"
        assert llm.temperature == 0.5
        assert isinstance(llm.api_key, SecretStr)

    def test_get_llm_with_profile_name(self, mock_workspace):
        """get_llm 可以从 SaaS 元数据加载命名配置文件。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "llm_model": "anthropic/claude-sonnet-4-20250514",
            "llm_api_key": "sk-default-key",
            "llm_base_url": None,
            "llm_profiles": {
                "profiles": {
                    "fast": {
                        "model": "openai/gpt-4o",
                        "api_key": "sk-profile-key",
                        "base_url": "https://litellm.example.com",
                        "usage_id": "default",
                    }
                },
                "active_profile": "fast",
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_api_request", return_value=mock_response
        ) as mock_req:
            llm = mock_workspace.get_llm(profile_name="fast", temperature=0.3)

        mock_req.assert_called_once_with(
            "GET",
            f"{CLOUD_URL}/api/v1/users/me",
            params={"expose_secrets": "true"},
            headers={"X-Session-API-Key": SESSION_KEY},
        )
        assert llm.model == "openai/gpt-4o"
        assert llm.temperature == 0.3
        assert isinstance(llm.api_key, SecretStr)
        assert llm.api_key.get_secret_value() == "sk-profile-key"
        assert llm.base_url == "https://litellm.example.com"
        assert llm.usage_id == "profile:fast"

        with patch.object(
            mock_workspace, "_send_api_request", return_value=mock_response
        ):
            llm_with_override = mock_workspace.get_llm(
                profile_name="fast", usage_id="custom-usage"
            )

        assert llm_with_override.usage_id == "custom-usage"

    def test_get_llm_missing_profile_raises(self, mock_workspace):
        """get_llm 针对未知的 SaaS 配置文件提出 FileNotFoundError。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "llm_profiles": {"profiles": {"fast": {"model": "gpt-4o"}}}
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_api_request", return_value=mock_response
        ):
            with pytest.raises(FileNotFoundError, match="missing"):
                mock_workspace.get_llm(profile_name="missing")

    def test_get_llm_no_api_key_still_works(self, mock_workspace):
        """如果没有配置API键，则LLM得到api_key=None。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "llm_model": "gpt-4o",
            "llm_api_key": None,
            "llm_base_url": None,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_api_request", return_value=mock_response
        ):
            llm = mock_workspace.get_llm()

        assert llm.model == "gpt-4o"
        assert llm.api_key is None

    def test_get_llm_raises_when_no_sandbox(self, mock_workspace):
        """当沙箱未运行时，get_llm 引发 RuntimeError。"""
        mock_workspace._sandbox_id = None
        with pytest.raises(RuntimeError, match="Sandbox is not running"):
            mock_workspace.get_llm()


class TestGetSecrets:
    """测试 OpenHandsCloudWorkspace.get_secrets()。"""

    def test_get_all_secrets_returns_lookup_secrets(self, mock_workspace):
        """get_secrets 返回 LookupSecret 个实例，而不是原始值。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "secrets": [
                {"name": "GITHUB_TOKEN", "description": "GitHub token"},
                {"name": "MY_API_KEY", "description": None},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_settings_request", return_value=mock_response
        ) as mock_req:
            secrets = mock_workspace.get_secrets()

        mock_req.assert_called_once_with(
            "GET",
            f"{CLOUD_URL}/api/v1/sandboxes/{SANDBOX_ID}/settings/secrets",
        )

        assert len(secrets) == 2
        assert "GITHUB_TOKEN" in secrets
        assert "MY_API_KEY" in secrets

        gh_secret = secrets["GITHUB_TOKEN"]
        assert isinstance(gh_secret, LookupSecret)
        assert gh_secret.url == (
            f"{CLOUD_URL}/api/v1/sandboxes/{SANDBOX_ID}/settings/secrets/GITHUB_TOKEN"
        )
        assert gh_secret.headers == {"X-Session-API-Key": SESSION_KEY}
        assert gh_secret.description == "GitHub token"

    def test_get_secrets_filters_by_name(self, mock_workspace):
        """get_secrets(names=[...]) 过滤客户端。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "secrets": [
                {"name": "GITHUB_TOKEN", "description": "GitHub token"},
                {"name": "MY_API_KEY", "description": None},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_settings_request", return_value=mock_response
        ):
            secrets = mock_workspace.get_secrets(names=["GITHUB_TOKEN"])

        assert len(secrets) == 1
        assert "GITHUB_TOKEN" in secrets
        assert "MY_API_KEY" not in secrets

    def test_get_secrets_requests_agent_profile_scope(self, mock_workspace):
        mock_response = MagicMock()
        mock_response.json.return_value = {"secrets": [{"name": "GITHUB_TOKEN"}]}

        with patch.object(
            mock_workspace, "_send_settings_request", return_value=mock_response
        ) as mock_req:
            secrets = mock_workspace.get_secrets(agent_profile_id="profile-id")

        assert list(secrets) == ["GITHUB_TOKEN"]
        mock_req.assert_called_once_with(
            "GET",
            f"{CLOUD_URL}/api/v1/sandboxes/{SANDBOX_ID}/settings/secrets",
            params={"agent_profile_id": "profile-id"},
        )

    def test_get_secrets_empty(self, mock_workspace):
        """空机密列表返回空字典。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"secrets": []}
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_settings_request", return_value=mock_response
        ):
            secrets = mock_workspace.get_secrets()

        assert secrets == {}

    def test_get_secrets_raises_when_no_sandbox(self, mock_workspace):
        """当沙箱未运行时，get_secrets 引发 RuntimeError。"""
        mock_workspace._sandbox_id = None
        with pytest.raises(RuntimeError, match="Sandbox is not running"):
            mock_workspace.get_secrets()


class TestGetMcpServers:
    """测试 OpenHandsCloudWorkspace.get_mcp_config()。"""

    def test_get_mcp_config_returns_empty_when_no_config(self, mock_workspace):
        """当未设置 MCP 服务器时，get_mcp_config 返回空字典。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "llm_model": "gpt-4o",
            "mcp_config": None,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_api_request", return_value=mock_response
        ):
            mcp_config = mock_workspace.get_mcp_config()

        assert mcp_config == {}

    def test_get_mcp_config_transforms_sse_servers(self, mock_workspace):
        """get_mcp_config 正确转换 SSE 服务器。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "mcp_config": {
                "sse_servers": [
                    {"url": "https://sse.example.com/mcp", "api_key": "sse-key-123"},
                    {"url": "https://sse2.example.com/mcp", "api_key": None},
                ],
                "shttp_servers": [],
                "stdio_servers": [],
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_api_request", return_value=mock_response
        ) as mock_req:
            mcp_config = mock_workspace.get_mcp_config()

        mock_req.assert_called_once_with(
            "GET",
            f"{CLOUD_URL}/api/v1/users/me",
            headers={"X-Session-API-Key": SESSION_KEY},
        )

        servers = dump_mcp_config(mcp_config)
        assert len(servers) == 2

        # 第一个具有 API 密钥的 SSE 服务器
        assert servers["sse_0"]["url"] == "https://sse.example.com/mcp"
        assert servers["sse_0"]["transport"] == "sse"
        sse_headers = servers["sse_0"]["headers"]
        assert isinstance(sse_headers, dict)
        assert sse_headers["Authorization"] == "Bearer sse-key-123"

        # 第二个 SSE 服务器没有 API 密钥
        assert servers["sse_1"]["url"] == "https://sse2.example.com/mcp"
        assert servers["sse_1"]["transport"] == "sse"
        assert "headers" not in servers["sse_1"]

    def test_get_mcp_config_transforms_shttp_servers(self, mock_workspace):
        """get_mcp_config 正确转换 SHTTP 服务器。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "mcp_config": {
                "sse_servers": [],
                "shttp_servers": [
                    {
                        "url": "https://shttp.example.com/mcp",
                        "api_key": "shttp-key",
                        "timeout": 120,
                    },
                ],
                "stdio_servers": [],
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_api_request", return_value=mock_response
        ):
            mcp_config = mock_workspace.get_mcp_config()

        servers = dump_mcp_config(mcp_config)
        assert len(servers) == 1

        assert servers["shttp_0"]["url"] == "https://shttp.example.com/mcp"
        assert servers["shttp_0"]["transport"] == "streamable-http"
        shttp_headers = servers["shttp_0"]["headers"]
        assert isinstance(shttp_headers, dict)
        assert shttp_headers["Authorization"] == "Bearer shttp-key"
        assert servers["shttp_0"]["timeout"] == 120

    def test_get_mcp_config_transforms_stdio_servers(self, mock_workspace):
        """get_mcp_config 正确转换 STDIO 服务器。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "mcp_config": {
                "sse_servers": [],
                "shttp_servers": [],
                "stdio_servers": [
                    {
                        "name": "my-stdio-server",
                        "command": "npx",
                        "args": ["-y", "mcp-server-fetch"],
                        "env": {"MY_VAR": "value"},
                    },
                ],
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_api_request", return_value=mock_response
        ):
            mcp_config = mock_workspace.get_mcp_config()

        servers = dump_mcp_config(mcp_config)
        assert len(servers) == 1

        # STDIO 服务器使用其显式名称
        assert "my-stdio-server" in servers
        assert servers["my-stdio-server"]["command"] == "npx"
        assert servers["my-stdio-server"]["args"] == ["-y", "mcp-server-fetch"]
        assert servers["my-stdio-server"]["env"] == {"MY_VAR": "value"}

    def test_get_mcp_config_mixed_server_types(self, mock_workspace):
        """get_mcp_config 正确处理混合服务器类型。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "mcp_config": {
                "sse_servers": [
                    {"url": "https://sse.example.com/mcp", "api_key": None},
                ],
                "shttp_servers": [
                    {"url": "https://shttp.example.com/mcp", "api_key": None},
                ],
                "stdio_servers": [
                    {"name": "fetch", "command": "uvx", "args": ["mcp-server-fetch"]},
                ],
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_api_request", return_value=mock_response
        ):
            mcp_config = mock_workspace.get_mcp_config()

        servers = dump_mcp_config(mcp_config)
        assert len(servers) == 3
        assert "sse_0" in servers
        assert "shttp_0" in servers
        assert "fetch" in servers

    def test_get_mcp_config_raises_when_no_sandbox(self, mock_workspace):
        """当沙箱未运行时，get_mcp_config 引发 RuntimeError。"""
        mock_workspace._sandbox_id = None
        with pytest.raises(RuntimeError, match="Sandbox is not running"):
            mock_workspace.get_mcp_config()

    def test_get_mcp_config_returns_empty_when_all_lists_empty(self, mock_workspace):
        """当所有服务器列表为空时，get_mcp_config 返回空字典。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "mcp_config": {
                "sse_servers": [],
                "shttp_servers": [],
                "stdio_servers": [],
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_api_request", return_value=mock_response
        ):
            mcp_config = mock_workspace.get_mcp_config()

        assert mcp_config == {}

    def test_get_mcp_config_is_native_settings_compatible(self, mock_workspace):
        """get_mcp_config 返回本机 SDK MCP 服务器映射。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "mcp_config": {
                "sse_servers": [
                    {"url": "https://sse.example.com/mcp", "api_key": "key123"},
                ],
                "shttp_servers": [
                    {"url": "https://shttp.example.com/mcp", "api_key": None},
                ],
                "stdio_servers": [
                    {"name": "fetch", "command": "uvx", "args": ["mcp-server-fetch"]},
                ],
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace, "_send_api_request", return_value=mock_response
        ):
            mcp_config_dict = mock_workspace.get_mcp_config()

        config = mcp_config_dict
        assert len(config) == 3
        assert "sse_0" in config
        assert "shttp_0" in config
        assert "fetch" in config


class TestRetry:
    """测试 get_llm 和 get_secrets 上的重试行为。"""

    def test_get_llm_retries_on_server_error(self, mock_workspace):
        """5xx 上的 get_llm 重试并在下一次尝试中成功。"""
        error_response = httpx.Response(
            status_code=502, request=httpx.Request("GET", "http://x")
        )
        ok_response = MagicMock()
        ok_response.json.return_value = {
            "llm_model": "gpt-4o",
            "llm_api_key": "sk-ok",
            "llm_base_url": None,
        }
        ok_response.raise_for_status = MagicMock()

        with patch.object(
            mock_workspace,
            "_send_api_request",
            side_effect=[
                httpx.HTTPStatusError(
                    "Bad Gateway",
                    request=error_response.request,
                    response=error_response,
                ),
                ok_response,
            ],
        ):
            llm = mock_workspace.get_llm()

        assert llm.model == "gpt-4o"

    def test_get_llm_no_retry_on_client_error(self, mock_workspace):
        """get_llm 对 4xx 错误执行不重试。"""
        error_response = httpx.Response(
            status_code=401, request=httpx.Request("GET", "http://x")
        )

        with patch.object(
            mock_workspace,
            "_send_api_request",
            side_effect=httpx.HTTPStatusError(
                "Unauthorized",
                request=error_response.request,
                response=error_response,
            ),
        ):
            with pytest.raises(httpx.HTTPStatusError):
                mock_workspace.get_llm()

    def test_get_secrets_retries_on_server_error(self, mock_workspace):
        """get_secrets 的 5xx 上的 _send_settings_request 重试。"""
        ok_response = MagicMock()
        ok_response.json.return_value = {
            "secrets": [{"name": "TOK", "description": None}]
        }
        ok_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.request.side_effect = [
                httpx.Response(
                    status_code=503,
                    request=httpx.Request("GET", "http://x"),
                ),
                ok_response,
            ]
            # 第一个调用在 raise_for_status 上加注，第二个调用成功
            secrets = mock_workspace.get_secrets()

        assert "TOK" in secrets
