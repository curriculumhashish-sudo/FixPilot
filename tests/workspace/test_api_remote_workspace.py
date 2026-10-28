"""测试 APIRemoteWorkspace 超时配置。"""

import os
from unittest.mock import MagicMock, patch

import httpx


def test_api_timeout_is_used_in_client():
    """测试 api_timeout 参数是否用于 HTTP 客户端超时。"""
    from openhands.workspace import APIRemoteWorkspace

    # 模拟对象整个初始化过程
    with patch.object(APIRemoteWorkspace, "_start_or_attach_to_runtime") as mock_init:
        mock_init.return_value = None

        # 使用自定义 api_timeout 创建工作区
        custom_timeout = 300.0
        workspace = APIRemoteWorkspace(
            runtime_api_url="https://example.com",
            runtime_api_key="test-key",
            server_image="test-image",
            api_timeout=custom_timeout,
        )

        # 需要设置客户端初始化的运行时属性
        workspace._runtime_id = "test-runtime-id"
        workspace._runtime_url = "https://test-runtime.com"
        workspace._session_api_key = "test-session-key"
        workspace.host = workspace._runtime_url

        # 访问客户端属性触发初始化
        client = workspace.client

        # 验证客户端的超时使用自定义的api_timeout
        assert isinstance(client, httpx.Client)
        assert client.timeout.read == custom_timeout
        assert client.timeout.connect == 10.0
        assert client.timeout.write == 10.0
        assert client.timeout.pool == 10.0

        # 清理
        workspace._runtime_id = None  # 防止清理尝试停止运行时
        workspace.cleanup()


def test_api_timeout_default_value():
    """测试默认 api_timeout 是否为 60 秒。"""
    from openhands.workspace import APIRemoteWorkspace

    with patch.object(APIRemoteWorkspace, "_start_or_attach_to_runtime") as mock_init:
        mock_init.return_value = None

        workspace = APIRemoteWorkspace(
            runtime_api_url="https://example.com",
            runtime_api_key="test-key",
            server_image="test-image",
        )

        # 需要设置客户端初始化的运行时属性
        workspace._runtime_id = "test-runtime-id"
        workspace._runtime_url = "https://test-runtime.com"
        workspace._session_api_key = "test-session-key"
        workspace.host = workspace._runtime_url

        # 访问客户端属性触发初始化
        client = workspace.client

        # 验证默认值超时是否为 60 秒
        assert client.timeout.read == 60.0

        # 清理
        workspace._runtime_id = None
        workspace.cleanup()


def test_different_timeout_values():
    """测试是否正确应用了不同的 api_timeout 值。"""
    from openhands.workspace import APIRemoteWorkspace

    test_timeouts = [30.0, 120.0, 600.0]

    for timeout_value in test_timeouts:
        with patch.object(
            APIRemoteWorkspace, "_start_or_attach_to_runtime"
        ) as mock_init:
            mock_init.return_value = None

            workspace = APIRemoteWorkspace(
                runtime_api_url="https://example.com",
                runtime_api_key="test-key",
                server_image="test-image",
                api_timeout=timeout_value,
            )

            workspace._runtime_id = "test-runtime-id"
            workspace._runtime_url = "https://test-runtime.com"
            workspace._session_api_key = "test-session-key"
            workspace.host = workspace._runtime_url

            client = workspace.client

            assert client.timeout.read == timeout_value, (
                f"Expected timeout {timeout_value}, got {client.timeout.read}"
            )

            workspace._runtime_id = None
            workspace.cleanup()


def test_startup_wait_timeout_default_and_override():
    """确保startup_wait_timeout可以配置。"""
    from openhands.workspace import APIRemoteWorkspace

    with patch.object(APIRemoteWorkspace, "_start_or_attach_to_runtime") as mock_init:
        mock_init.return_value = None
        default_ws = APIRemoteWorkspace(
            runtime_api_url="https://example.com",
            runtime_api_key="test-key",
            server_image="test-image",
        )
        assert default_ws.startup_wait_timeout == 300.0
        default_ws._runtime_id = None
        default_ws.cleanup()

    with patch.object(APIRemoteWorkspace, "_start_or_attach_to_runtime") as mock_init:
        mock_init.return_value = None
        custom_ws = APIRemoteWorkspace(
            runtime_api_url="https://example.com",
            runtime_api_key="test-key",
            server_image="test-image",
            startup_wait_timeout=600.0,
        )
        assert custom_ws.startup_wait_timeout == 600.0
        custom_ws._runtime_id = None
        custom_ws.cleanup()


def test_forward_env_default_is_empty():
    """测试 forward_env 默认为空列表。"""
    from openhands.workspace import APIRemoteWorkspace

    with patch.object(APIRemoteWorkspace, "_start_or_attach_to_runtime") as mock_init:
        mock_init.return_value = None

        workspace = APIRemoteWorkspace(
            runtime_api_url="https://example.com",
            runtime_api_key="test-key",
            server_image="test-image",
        )

        assert workspace.forward_env == []

        workspace._runtime_id = None
        workspace.cleanup()


def test_forward_env_is_included_in_start_runtime_payload():
    """测试 forward_env 变量是否包含在运行时启动载荷中。"""
    from openhands.workspace import APIRemoteWorkspace

    # 设置测试环境变量
    test_env = {
        "TEST_VAR_1": "value1",
        "TEST_VAR_2": "value2",
        "UNSET_VAR": None,  # 这个不会出现在 os.environ 中
    }

    with patch.dict(os.environ, {k: v for k, v in test_env.items() if v is not None}):
        with patch.object(
            APIRemoteWorkspace, "_start_or_attach_to_runtime"
        ) as mock_attach:
            mock_attach.return_value = None

            workspace = APIRemoteWorkspace(
                runtime_api_url="https://example.com",
                runtime_api_key="test-key",
                server_image="test-image",
                forward_env=["TEST_VAR_1", "TEST_VAR_2", "UNSET_VAR"],
            )

            # 模拟对象API请求方法捕获载荷
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "runtime_id": "test-id",
                "url": "https://test-runtime.com",
                "session_api_key": "test-key",
            }

            with patch.object(
                workspace, "_send_api_request", return_value=mock_response
            ) as mock_request:
                workspace._start_runtime()

                # 验证使用正确的载荷调用 API
                mock_request.assert_called_once()
                call_kwargs = mock_request.call_args
                payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")

                # 检查环境是否包含转发的变量
                assert "environment" in payload
                assert payload["environment"]["TEST_VAR_1"] == "value1"
                assert payload["environment"]["TEST_VAR_2"] == "value2"
                # UNSET_VAR 不应该在环境中，因为它不在 os.environ 中
                assert "UNSET_VAR" not in payload["environment"]

            workspace._runtime_id = None
            workspace.cleanup()


def test_forward_env_empty_list_results_in_empty_environment():
    """测试空的 forward_env 是否会导致空的环境字典。"""
    from openhands.workspace import APIRemoteWorkspace

    with patch.object(APIRemoteWorkspace, "_start_or_attach_to_runtime") as mock_attach:
        mock_attach.return_value = None

        workspace = APIRemoteWorkspace(
            runtime_api_url="https://example.com",
            runtime_api_key="test-key",
            server_image="test-image",
            forward_env=[],
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "runtime_id": "test-id",
            "url": "https://test-runtime.com",
            "session_api_key": "test-key",
        }

        with patch.object(
            workspace, "_send_api_request", return_value=mock_response
        ) as mock_request:
            workspace._start_runtime()

            call_kwargs = mock_request.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")

            assert payload["environment"] == {}

        workspace._runtime_id = None
        workspace.cleanup()


def test_start_runtime_logs_environment_keys_without_values(caplog):
    """测试启动运行时日志不包含转发的环境值。"""
    from openhands.workspace import APIRemoteWorkspace

    with patch.dict(
        os.environ,
        {
            "SECRET_TOKEN": "super-secret-value",
            "ANOTHER_SECRET": "another-secret-value",
        },
    ):
        with patch.object(
            APIRemoteWorkspace, "_start_or_attach_to_runtime"
        ) as mock_attach:
            mock_attach.return_value = None

            workspace = APIRemoteWorkspace(
                runtime_api_url="https://example.com",
                runtime_api_key="test-key",
                server_image="test-image",
                forward_env=["SECRET_TOKEN", "ANOTHER_SECRET"],
            )

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "runtime_id": "test-id",
                "url": "https://test-runtime.com",
                "session_api_key": "test-key",
            }

            with patch.object(
                workspace, "_send_api_request", return_value=mock_response
            ):
                with caplog.at_level("INFO"):
                    workspace._start_runtime()

            log_text = "\n".join(record.getMessage() for record in caplog.records)
            assert "super-secret-value" not in log_text
            assert "another-secret-value" not in log_text
            assert "Runtime start payload:" in log_text
            assert "environment_keys=['ANOTHER_SECRET', 'SECRET_TOKEN']" in log_text

            workspace._runtime_id = None
            workspace.cleanup()


# --- 回调集成测试 ---


def _make_workspace():
    """创建工作区，而不启动回调测试的运行时。"""
    from openhands.workspace import APIRemoteWorkspace

    with patch.object(APIRemoteWorkspace, "_start_or_attach_to_runtime"):
        ws = APIRemoteWorkspace(
            runtime_api_url="https://example.com",
            runtime_api_key="test-key",
            server_image="test-image",
        )
        ws._runtime_id = None  # 防止清理进行 API 调用
        return ws


def test_api_remote_workspace_exit_sends_callback(monkeypatch):
    """测试 APIRemoteWorkspace.__exit__ 发送完成回调。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    monkeypatch.setenv("AUTOMATION_CALLBACK_API_KEY", "test-api-key")
    ws = _make_workspace()

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
        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["status"] == "COMPLETED"
