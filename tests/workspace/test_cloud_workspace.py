"""测试OpenHandsCloudWorkspace实施。"""

from unittest.mock import MagicMock, patch

import httpx


def test_api_timeout_is_used_in_client():
    """测试 api_timeout 参数是否用于 HTTP 客户端超时。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        custom_timeout = 300.0
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="test-api-key",
            api_timeout=custom_timeout,
        )

        # 设置客户端初始化
        workspace._sandbox_id = "sandbox-123"
        workspace._session_api_key = "session-key"
        workspace.host = "https://agent.example.com"
        workspace.api_key = "session-key"

        client = workspace.client

        assert isinstance(client, httpx.Client)
        assert client.timeout.read == custom_timeout
        assert client.timeout.connect == 10.0
        assert client.timeout.write == 10.0
        assert client.timeout.pool == 10.0

        # 清理
        workspace._sandbox_id = None
        workspace.cleanup()


def test_api_timeout_default_value():
    """测试默认 api_timeout 是否为 60 秒。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="test-api-key",
        )

        # 设置客户端初始化
        workspace._sandbox_id = "sandbox-123"
        workspace._session_api_key = "session-key"
        workspace.host = "https://agent.example.com"
        workspace.api_key = "session-key"

        client = workspace.client

        assert client.timeout.read == 60.0

        # 清理
        workspace._sandbox_id = None
        workspace.cleanup()


def test_api_headers_uses_bearer_token():
    """测试 _api_headers 使用持有者令牌身份验证。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="test-api-key",
        )

        headers = workspace._api_headers
        assert headers == {"Authorization": "Bearer test-api-key"}

        # 清理
        workspace._sandbox_id = None
        workspace.cleanup()


def test_get_agent_server_url_extracts_correct_url():
    """测试 _get_agent_server_url 提取 AGENT_SERVER URL。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="test-api-key",
        )

        workspace._exposed_urls = [
            {"name": "OTHER_SERVICE", "url": "https://other.example.com", "port": 9000},
            {"name": "AGENT_SERVER", "url": "https://agent.example.com", "port": 8080},
        ]

        url = workspace._get_agent_server_url()
        assert url == "https://agent.example.com"

        # 清理
        workspace._sandbox_id = None
        workspace.cleanup()


def test_get_agent_server_url_returns_none_when_not_found():
    """测试当未找到 AGENT_SERVER 时 _get_agent_server_url 返回 None。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="test-api-key",
        )

        workspace._exposed_urls = [
            {"name": "OTHER_SERVICE", "url": "https://other.example.com", "port": 9000},
        ]

        url = workspace._get_agent_server_url()
        assert url is None

        # 清理
        workspace._sandbox_id = None
        workspace.cleanup()


def test_get_agent_server_url_returns_none_when_empty():
    """测试当 exposed_urls 为空时 _get_agent_server_url 返回 None。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="test-api-key",
        )

        workspace._exposed_urls = None

        url = workspace._get_agent_server_url()
        assert url is None

        # 清理
        workspace._sandbox_id = None
        workspace.cleanup()


def test_cleanup_deletes_sandbox():
    """测试清理是否会删除沙箱。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="api-key",
            keep_alive=False,
        )

        workspace._sandbox_id = "sandbox-123"
        workspace._session_api_key = "session-key"
        workspace._exposed_urls = []

        with patch.object(workspace, "_send_api_request") as mock_request:
            workspace.cleanup()

            mock_request.assert_called_once_with(
                "DELETE",
                "https://cloud.example.com/api/v1/sandboxes/sandbox-123",
                params={"sandbox_id": "sandbox-123"},
                timeout=30.0,
            )
            assert workspace._sandbox_id is None
            assert workspace._session_api_key is None


def test_cleanup_keeps_sandbox_alive_when_configured():
    """测试当 keep_alive 为 True 时清理是否使沙箱保持活动状态。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="api-key",
            keep_alive=True,
        )

        workspace._sandbox_id = "sandbox-123"
        workspace._session_api_key = "session-key"
        workspace._exposed_urls = []

        with patch.object(workspace, "_send_api_request") as mock_request:
            workspace.cleanup()

            # 当 keep_alive 为 True 时不应调用 DELETE
            mock_request.assert_not_called()


def test_cleanup_handles_missing_sandbox_id():
    """测试清理是否优雅地处理缺失的 sandbox_id。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="api-key",
            keep_alive=False,
        )

        workspace._sandbox_id = None
        workspace._session_api_key = None
        workspace._exposed_urls = None

        with patch.object(workspace, "_send_api_request") as mock_request:
            # 不应引发异常
            workspace.cleanup()
            mock_request.assert_not_called()


def test_send_api_request_includes_bearer_token():
    """测试 _send_api_request 是否包含持有者令牌标头。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="test-api-key",
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client

            workspace._send_api_request("GET", "https://cloud.example.com/api/v1/test")

            mock_client.request.assert_called_once()
            call_kwargs = mock_client.request.call_args
            assert call_kwargs[1]["headers"]["Authorization"] == "Bearer test-api-key"

        # 清理
        workspace._sandbox_id = None
        workspace.cleanup()


def test_context_manager_calls_cleanup():
    """测试上下文管理器在退出时调用清理。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="api-key",
            keep_alive=False,
        )

        workspace._sandbox_id = "sandbox-123"
        workspace._session_api_key = "session-key"
        workspace._exposed_urls = []

        with patch.object(workspace, "_send_api_request"):
            with workspace:
                pass

            assert workspace._sandbox_id is None


def test_cloud_api_url_trailing_slash_removed():
    """测试尾部斜杠是否已从 cloud_api_url 中删除。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com/",
            cloud_api_key="test-api-key",
        )

        assert workspace.cloud_api_url == "https://cloud.example.com"

        # 清理
        workspace._sandbox_id = None
        workspace.cleanup()


def test_sandbox_id_field_is_public():
    """测试 sandbox_id 是一个可以设置的公共字段。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="test-api-key",
            sandbox_id="existing-sandbox-123",
        )

        assert workspace.sandbox_id == "existing-sandbox-123"

        # 清理
        workspace._sandbox_id = None
        workspace.cleanup()


def test_sandbox_id_triggers_resume_instead_of_create():
    """测试提供 sandbox_id 调用恢复端点而不是创建。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="test-api-key",
            sandbox_id="existing-sandbox-123",
        )

    # 模拟对象方法 - 使用类级补丁 reset_client
    with (
        patch.object(workspace, "_resume_sandbox") as mock_resume,
        patch.object(workspace, "_create_new_sandbox") as mock_create,
        patch.object(workspace, "_wait_until_sandbox_ready"),
        patch.object(workspace, "_get_agent_server_url") as mock_get_url,
        patch.object(OpenHandsCloudWorkspace, "reset_client"),
    ):
        mock_get_url.return_value = "https://agent.example.com"
        workspace._start_sandbox()

        # 应该调用resume，而不是create
        mock_resume.assert_called_once()
        mock_create.assert_not_called()
        assert workspace._sandbox_id == "existing-sandbox-123"

    # 清理
    workspace._sandbox_id = None
    workspace.cleanup()


def test_no_sandbox_id_creates_new_sandbox():
    """测试没有 sandbox_id，会创建一个新的沙箱。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="test-api-key",
        )

    # 模拟对象方法 - 使用类级补丁 reset_client
    with (
        patch.object(workspace, "_resume_sandbox") as mock_resume,
        patch.object(workspace, "_create_new_sandbox") as mock_create,
        patch.object(workspace, "_wait_until_sandbox_ready"),
        patch.object(workspace, "_get_agent_server_url") as mock_get_url,
        patch.object(OpenHandsCloudWorkspace, "reset_client"),
    ):
        mock_get_url.return_value = "https://agent.example.com"
        workspace._start_sandbox()

        # 应该调用create，而不是resume
        mock_create.assert_called_once()
        mock_resume.assert_not_called()

    # 清理
    workspace._sandbox_id = None
    workspace.cleanup()


def test_resume_existing_sandbox_sets_internal_id():
    """测试 _resume_existing_sandbox 是否设置 sandbox_id 中的 _sandbox_id。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
        workspace = OpenHandsCloudWorkspace(
            cloud_api_url="https://cloud.example.com",
            cloud_api_key="test-api-key",
            sandbox_id="my-sandbox-id",
        )

    with patch.object(workspace, "_send_api_request"):
        workspace._resume_existing_sandbox()

        assert workspace._sandbox_id == "my-sandbox-id"

    # 清理
    workspace._sandbox_id = None
    workspace.cleanup()


# --- local_agent_server_mode 测试 ---

_CLOUD_URL = "https://app.all-hands.dev"
_CLOUD_KEY = "test-key"


def _make_local_workspace(**overrides):
    """帮助程序在 local_agent_server_mode 中创建 OpenHandsCloudWorkspace。"""
    from openhands.workspace import OpenHandsCloudWorkspace

    kwargs = {
        "local_agent_server_mode": True,
        "cloud_api_url": _CLOUD_URL,
        "cloud_api_key": _CLOUD_KEY,
        **overrides,
    }
    return OpenHandsCloudWorkspace(**kwargs)


def test_local_agent_server_mode_skips_sandbox_creation():
    """在local_agent_server_mode中，没有创建或恢复沙箱。"""
    workspace = _make_local_workspace()

    assert workspace.local_agent_server_mode is True
    assert workspace.host == "http://localhost:60000"
    # 如果没有 SANDBOX_ID 环境变量或构造函数参数，_sandbox_id 就是 None
    assert workspace._sandbox_id is None

    workspace.cleanup()


def test_local_agent_server_mode_sandbox_id_from_constructor():
    """sandbox_id 构造函数参数填充 local_agent_server_mode 中的 _sandbox_id。"""
    workspace = _make_local_workspace(sandbox_id="sb-123")

    assert workspace._sandbox_id == "sb-123"
    workspace.cleanup()


def test_local_agent_server_mode_sandbox_id_from_env(monkeypatch):
    """SANDBOX_ID 环境变量填充 local_agent_server_mode 中的 _sandbox_id。"""
    monkeypatch.setenv("SANDBOX_ID", "sb-env-456")
    workspace = _make_local_workspace()

    assert workspace._sandbox_id == "sb-env-456"
    workspace.cleanup()


def test_local_agent_server_mode_session_key_from_env(monkeypatch):
    """SESSION_API_KEY 填充 _session_api_key 和 api_key。"""
    monkeypatch.setenv("SESSION_API_KEY", "sess-key-abc")
    workspace = _make_local_workspace()

    assert workspace._session_api_key == "sess-key-abc"
    # 还必须设置 api_key，以便共享 HTTP 客户端包含 X-Session-API-Key
    assert workspace.api_key == "sess-key-abc"
    workspace.cleanup()


def test_local_agent_server_mode_session_key_fallback(monkeypatch):
    """如果 SESSION_API_KEY 未设置，则返回到 OH_SESSION_API_KEYS_0。"""
    monkeypatch.delenv("SESSION_API_KEY", raising=False)
    monkeypatch.setenv("OH_SESSION_API_KEYS_0", "oh-key-xyz")
    workspace = _make_local_workspace()

    assert workspace._session_api_key == "oh-key-xyz"
    assert workspace.api_key == "oh-key-xyz"
    workspace.cleanup()


def test_local_agent_server_mode_custom_port():
    """自定义 agent_server_port 反映在主机 URL 中。"""
    workspace = _make_local_workspace(agent_server_port=9999)

    assert workspace.host == "http://localhost:9999"
    workspace.cleanup()


def test_local_agent_server_mode_port_from_env(monkeypatch):
    """AGENT_SERVER_PORT 环境变量覆盖 agent_server_port。"""
    monkeypatch.setenv("AGENT_SERVER_PORT", "7777")
    workspace = _make_local_workspace()

    assert workspace.host == "http://localhost:7777"
    workspace.cleanup()


def test_local_agent_server_mode_cloud_credentials_available():
    """云 API 字段可用于 get_llms / get_secrets。"""
    workspace = _make_local_workspace(
        cloud_api_url="https://app.all-hands.dev/",
        cloud_api_key="my-key",
    )

    assert workspace.cloud_api_url == "https://app.all-hands.dev"
    assert workspace._api_headers == {"Authorization": "Bearer my-key"}
    workspace.cleanup()


def test_local_agent_server_mode_cleanup_does_not_delete_sandbox():
    """local_agent_server_mode 中的 cleanup() 不应调用任何 Cloud API。"""
    workspace = _make_local_workspace()

    with patch.object(workspace, "_send_api_request") as mock_req:
        workspace.cleanup()
        mock_req.assert_not_called()


def test_local_agent_server_mode_context_manager():
    """上下文管理器适用于 local_agent_server_mode，没有副作用。"""
    with _make_local_workspace() as ws:
        assert ws.host == "http://localhost:60000"


# --- 完成回调测试 ---


def test_callback_on_successful_exit(monkeypatch):
    """__退出__ POSTs COMPLETED状态回调 URL在正常退出时。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    monkeypatch.setenv("AUTOMATION_RUN_ID", "run-42")
    ws = _make_local_workspace()

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        ws.__exit__(None, None, None)

        mock_client.post.assert_called_once()
        (url,) = mock_client.post.call_args.args
        payload = mock_client.post.call_args.kwargs["json"]
        assert url == "https://svc.test/complete"
        assert payload["status"] == "COMPLETED"
        assert payload["run_id"] == "run-42"
        assert "error" not in payload


def test_callback_on_exception_exit(monkeypatch):
    """__退出__ POSTs FAILED状态，包含异常详情。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    monkeypatch.setenv("AUTOMATION_RUN_ID", "run-99")
    ws = _make_local_workspace()

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        exc = RuntimeError("script crashed")
        ws.__exit__(RuntimeError, exc, None)

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["status"] == "FAILED"
        assert payload["run_id"] == "run-99"
        assert "script crashed" in payload["error"]


def test_no_callback_when_url_not_set():
    """当 AUTOMATION_CALLBACK_URL 环境变量未设置时，不会调用 HTTP。"""
    ws = _make_local_workspace()
    assert ws._automation_callback_url is None

    with patch("httpx.Client") as MockClient:
        ws.__exit__(None, None, None)
        MockClient.assert_not_called()


def test_callback_failure_does_not_raise(monkeypatch):
    """回调错误被吞掉 - 清理仍在运行。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    ws = _make_local_workspace()

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        # 不应该提高
        ws.__exit__(None, None, None)


# --- conversation_id 注册测试 ---


def test_register_conversation_sets_conversation_id():
    """register_conversation 设置 _conversation_id 属性。"""
    ws = _make_local_workspace()

    ws.register_conversation("conv-123")

    assert ws._conversation_id == "conv-123"
    assert ws.conversation_id == "conv-123"


def test_conversation_id_property_returns_none_initially():
    """当未注册任何对话时，conversation_id 属性返回 None。"""
    ws = _make_local_workspace()

    assert ws.conversation_id is None


def test_callback_includes_conversation_id_when_registered(monkeypatch):
    """注册时，回调载荷包括 conversation_id。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    monkeypatch.setenv("AUTOMATION_RUN_ID", "run-42")
    ws = _make_local_workspace()

    # 注册对话
    ws.register_conversation("conv-xyz")

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        ws.__exit__(None, None, None)

        # 检查POST载荷包含conversation_id
        mock_client.post.assert_called_once()
        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["status"] == "COMPLETED"
        assert payload["run_id"] == "run-42"
        assert payload["conversation_id"] == "conv-xyz"


def test_callback_omits_conversation_id_when_not_registered(monkeypatch):
    """回调载荷未注册时省略 conversation_id。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    monkeypatch.setenv("AUTOMATION_RUN_ID", "run-42")
    ws = _make_local_workspace()

    # 不注册对话

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        ws.__exit__(None, None, None)

        # 检查POST载荷不是否包含conversation_id
        mock_client.post.assert_called_once()
        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["status"] == "COMPLETED"
        assert "conversation_id" not in payload


def test_callback_includes_registered_cost(monkeypatch):
    """回调载荷报告注册时累计的 LLM 费用。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    monkeypatch.setenv("AUTOMATION_RUN_ID", "run-42")
    ws = _make_local_workspace()
    ws.register_cost(1.25)

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        ws.__exit__(None, None, None)

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["cost"] == 1.25
