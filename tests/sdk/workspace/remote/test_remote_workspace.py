"""单元测试对应 RemoteWorkspace 类。"""

from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest

from openhands.sdk.context import AgentContext
from openhands.sdk.mcp.config import dump_mcp_config
from openhands.sdk.workspace.models import CommandResult, FileOperationResult
from openhands.sdk.workspace.remote.base import RemoteWorkspace


class MockHTTPResponse:
    """模拟对象 HTTP urlopen 响应。"""

    def __init__(self, status: int = 200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def test_remote_workspace_initialization():
    """测试 RemoteWorkspace 可以使用所需参数进行初始化。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )

    assert workspace.host == "http://localhost:8000"
    assert workspace.working_dir == "/tmp"
    assert workspace.api_key == "test-key"


def test_remote_workspace_initialization_without_api_key():
    """无需API键即可初始化测试RemoteWorkspace。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    assert workspace.host == "http://localhost:8000"
    assert workspace.working_dir == "/tmp"
    assert workspace.api_key is None


def test_remote_workspace_host_normalization():
    """通过删除尾部斜杠来测试主机 URL 是否已标准化。"""
    workspace = RemoteWorkspace(host="http://localhost:8000/", working_dir="/tmp")

    assert workspace.host == "http://localhost:8000"


def test_client_property_lazy_initialization():
    """测试客户端属性是否延迟创建 httpx.Client。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    # 客户端最初应为 None
    assert workspace._client is None

    # 访问客户端应该创建它
    client = workspace.client
    assert isinstance(client, httpx.Client)
    assert workspace._client is client

    # 后续访问应返回相同的客户端
    assert workspace.client is client


def test_headers_property_with_api_key():
    """测试 _headers 属性包含 API 键（如果存在）。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )

    headers = workspace._headers
    assert headers == {"X-Session-API-Key": "test-key"}


def test_headers_property_without_api_key():
    """当没有API键时测试_headers属性为空。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    headers = workspace._headers
    assert headers == {}


def test_execute_method():
    """测试 _execute 方法正确处理生成器协议。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    # 模拟对象客户端
    mock_client = MagicMock()
    mock_response = Mock()
    mock_client.request.return_value = mock_response
    workspace._client = mock_client

    # 创建一个简单的生成器，生成请求 kwargs 并返回结果
    def test_generator():
        yield {"method": "GET", "url": "http://test.com"}
        return "test_result"

    result = workspace._execute(test_generator())

    assert result == "test_result"
    mock_client.request.assert_called_once_with(method="GET", url="http://test.com")


@patch("openhands.sdk.workspace.remote.base.RemoteWorkspace._execute")
def test_execute_command(mock_execute):
    """测试 execute_command 方法使用正确的生成器调用 _execute。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    expected_result = CommandResult(
        command="echo hello",
        exit_code=0,
        stdout="hello\n",
        stderr="",
        timeout_occurred=False,
    )
    mock_execute.return_value = expected_result

    result = workspace.execute_command("echo hello", cwd="/tmp", timeout=30.0)

    assert result == expected_result
    mock_execute.assert_called_once()

    # 验证生成器是否正确创建
    generator_arg = mock_execute.call_args[0][0]
    assert hasattr(generator_arg, "__next__")


@patch("openhands.sdk.workspace.remote.base.RemoteWorkspace._execute")
def test_file_upload(mock_execute):
    """测试 file_upload 方法使用正确的生成器调用 _execute。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    expected_result = FileOperationResult(
        success=True,
        source_path="/local/file.txt",
        destination_path="/remote/file.txt",
        file_size=100,
    )
    mock_execute.return_value = expected_result

    result = workspace.file_upload("/local/file.txt", "/remote/file.txt")

    assert result == expected_result
    mock_execute.assert_called_once()

    # 验证生成器是否正确创建
    generator_arg = mock_execute.call_args[0][0]
    assert hasattr(generator_arg, "__next__")


@patch("openhands.sdk.workspace.remote.base.RemoteWorkspace._execute")
def test_file_download(mock_execute):
    """测试 file_download 方法使用正确的生成器调用 _execute。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    expected_result = FileOperationResult(
        success=True,
        source_path="/remote/file.txt",
        destination_path="/local/file.txt",
        file_size=100,
    )
    mock_execute.return_value = expected_result

    result = workspace.file_download("/remote/file.txt", "/local/file.txt")

    assert result == expected_result
    mock_execute.assert_called_once()

    # 验证生成器是否正确创建
    generator_arg = mock_execute.call_args[0][0]
    assert hasattr(generator_arg, "__next__")


def test_execute_command_with_path_objects():
    """测试 execute_command 适用于 cwd 的 Path 对象。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    with patch.object(workspace, "_execute") as mock_execute:
        expected_result = CommandResult(
            command="ls",
            exit_code=0,
            stdout="file1.txt\n",
            stderr="",
            timeout_occurred=False,
        )
        mock_execute.return_value = expected_result

        result = workspace.execute_command("ls", cwd=Path("/tmp/test"))

        assert result == expected_result
        mock_execute.assert_called_once()


def test_file_operations_with_path_objects():
    """测试文件操作使用 Path 对象。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    with patch.object(workspace, "_execute") as mock_execute:
        expected_result = FileOperationResult(
            success=True,
            source_path="/local/file.txt",
            destination_path="/remote/file.txt",
            file_size=100,
        )
        mock_execute.return_value = expected_result

        # 使用 Path 对象测试上传
        result = workspace.file_upload(
            Path("/local/file.txt"), Path("/remote/file.txt")
        )
        assert result == expected_result

        # 使用 Path 对象测试下载
        result = workspace.file_download(
            Path("/remote/file.txt"), Path("/local/file.txt")
        )
        assert result == expected_result


def test_context_manager_protocol():
    """测试RemoteWorkspace支持上下文管理器协议。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    # 测试输入上下文
    with workspace as ctx:
        assert ctx is workspace

    # 测试 __exit__ 不会引发异常（RemoteWorkspace 不会覆盖 __exit__，因此它使用
    # BaseWorkspace 的无操作实现）
    #


def test_inheritance():
    """测试RemoteWorkspace继承自正确的基类。"""
    from openhands.sdk.workspace.base import BaseWorkspace
    from openhands.sdk.workspace.remote.remote_workspace_mixin import (
        RemoteWorkspaceMixin,
    )

    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    assert isinstance(workspace, BaseWorkspace)
    assert isinstance(workspace, RemoteWorkspaceMixin)


def test_execute_with_exception_handling():
    """测试 _execute 方法正确处理生成器中的异常。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    # 模拟对象客户端提出异常
    mock_client = MagicMock()
    mock_client.request.side_effect = httpx.RequestError("Connection failed")
    workspace._client = mock_client

    def failing_generator():
        yield {"method": "GET", "url": "http://test.com"}
        return "should_not_reach_here"

    # 生成器应该处理异常，并不返回结果，因为异常发生在 client.request()，生成器将不能正
    # 常完成
    #
    with pytest.raises(httpx.RequestError):
        workspace._execute(failing_generator())


def test_execute_generator_completion():
    """测试 _execute 方法正确处理 StopIteration 以获取返回值。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    # 模拟对象客户端
    mock_client = MagicMock()
    mock_response = Mock()
    mock_client.request.return_value = mock_response
    workspace._client = mock_client

    def test_generator():
        # 首次产出 - 获得响应
        yield {"method": "GET", "url": "http://test1.com"}
        # 第二次产量 - 得到另一个回应
        yield {"method": "POST", "url": "http://test2.com"}
        # 返回最终结果
        return "final_result"

    result = workspace._execute(test_generator())

    assert result == "final_result"
    assert mock_client.request.call_count == 2
    mock_client.request.assert_any_call(method="GET", url="http://test1.com")
    mock_client.request.assert_any_call(method="POST", url="http://test2.com")


@patch("openhands.sdk.workspace.remote.base.urlopen")
def test_alive_returns_true_on_successful_health_check(mock_urlopen):
    """当运行状况端点返回 2xx 状态时，测试活动属性返回 True。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    mock_urlopen.return_value = MockHTTPResponse(status=200)

    result = workspace.alive

    assert result is True
    mock_urlopen.assert_called_once_with("http://localhost:8000/health", timeout=5.0)


@patch("openhands.sdk.workspace.remote.base.urlopen")
def test_alive_returns_true_on_204_status(mock_urlopen):
    """当运行状况端点返回 204 无内容时，测试活动属性返回 True。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    mock_urlopen.return_value = MockHTTPResponse(status=204)

    result = workspace.alive

    assert result is True


@patch("openhands.sdk.workspace.remote.base.urlopen")
def test_alive_returns_false_on_server_error(mock_urlopen):
    """当运行状况端点返回 5xx 状态时，测试活动属性返回 False。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    mock_urlopen.return_value = MockHTTPResponse(status=500)

    result = workspace.alive

    assert result is False


@patch("openhands.sdk.workspace.remote.base.urlopen")
def test_alive_returns_false_on_client_error(mock_urlopen):
    """当运行状况端点返回 4xx 状态时，测试活动属性返回 False。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    mock_urlopen.return_value = MockHTTPResponse(status=404)

    result = workspace.alive

    assert result is False


@patch("openhands.sdk.workspace.remote.base.urlopen")
def test_alive_returns_false_on_connection_error(mock_urlopen):
    """当连接失败时，测试活动属性返回 False。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    mock_urlopen.side_effect = Exception("Connection refused")

    result = workspace.alive

    assert result is False


@patch("openhands.sdk.workspace.remote.base.urlopen")
def test_alive_returns_false_on_timeout(mock_urlopen):
    """当请求超时时，测试活动属性返回 False。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    from urllib.error import URLError

    mock_urlopen.side_effect = URLError("timed out")

    result = workspace.alive

    assert result is False


@patch("openhands.sdk.workspace.remote.base.urlopen")
def test_alive_constructs_correct_health_url(mock_urlopen):
    """测试活动属性从主机构造正确的运行状况 URL。"""
    workspace = RemoteWorkspace(
        host="https://my-agent-server.example.com", working_dir="/tmp"
    )

    mock_urlopen.return_value = MockHTTPResponse(status=200)

    _ = workspace.alive

    mock_urlopen.assert_called_once_with(
        "https://my-agent-server.example.com/health", timeout=5.0
    )


@patch("openhands.sdk.workspace.remote.base.urlopen")
def test_alive_with_normalized_host(mock_urlopen):
    """当主机规范化时，测试活动属性可以正常工作。"""
    # 带有尾部斜杠的主机在 model_post_init 中标准化
    workspace = RemoteWorkspace(host="http://localhost:8000/", working_dir="/tmp")

    mock_urlopen.return_value = MockHTTPResponse(status=200)

    result = workspace.alive

    assert result is True
    # 不应有双斜杠
    mock_urlopen.assert_called_once_with("http://localhost:8000/health", timeout=5.0)


def test_alive_is_property():
    """测试live是一个属性，而不是一个方法。"""
    assert isinstance(RemoteWorkspace.alive, property)


# ── 设置方法测试────────────────────────────────────────────────


def test_get_llm_returns_configured_llm(monkeypatch):
    """测试 get_llm 返回带有已持久化设置的 LLM。"""
    from pydantic import SecretStr

    # 允许短上下文窗口进行测试
    monkeypatch.setenv("ALLOW_SHORT_CONTEXT_WINDOWS", "true")

    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )

    mock_client = MagicMock()
    mock_response = Mock()
    mock_response.json.return_value = {
        "agent_settings": {
            "llm": {
                "model": "gpt-4",
                "api_key": "sk-test-key",
                "base_url": "https://api.openai.com/v1",
            }
        },
        "conversation_settings": {},
        "llm_api_key_is_set": True,
        "active_profile": "default",
    }
    mock_response.raise_for_status = Mock()
    profile_response = Mock()
    profile_response.status_code = 200
    profile_response.raise_for_status = Mock()
    profile_response.json.return_value = {
        "name": "default",
        "config": {
            "model": "gpt-4",
            "api_key": "sk-test-key",
            "base_url": "https://api.openai.com/v1",
        },
    }
    mock_client.get.side_effect = [mock_response, profile_response]
    workspace._client = mock_client

    llm = workspace.get_llm()

    # 验证 LLM 是使用正确的设置创建的
    assert llm.model == "gpt-4"
    # api_key 可以是 str | SecretStr | None
    assert llm.api_key is not None
    if isinstance(llm.api_key, SecretStr):
        assert llm.api_key.get_secret_value() == "sk-test-key"
    else:
        assert llm.api_key == "sk-test-key"
    assert llm.base_url == "https://api.openai.com/v1"

    assert [call.args[0] for call in mock_client.get.call_args_list] == [
        "/api/settings",
        "/api/profiles/default",
    ]


def test_get_llm_without_name_resolves_active_profile(monkeypatch):
    """默认分辨率采用 active_profile，而不是过时的智能体设置。"""
    from pydantic import SecretStr

    monkeypatch.setenv("ALLOW_SHORT_CONTEXT_WINDOWS", "true")
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )

    settings_response = Mock()
    settings_response.json.return_value = {
        "agent_settings": {
            "llm": {"model": "gpt-5.5", "api_key": None},
        },
        "conversation_settings": {},
        "llm_api_key_is_set": False,
        "active_profile": "glm-default",
    }
    settings_response.raise_for_status = Mock()
    profile_response = Mock()
    profile_response.status_code = 200
    profile_response.json.return_value = {
        "name": "glm-default",
        "config": {
            "model": "openhands/glm-5.2",
            "api_key": "sk-glm-key",
            "usage_id": "default",
        },
        "api_key_set": True,
    }
    profile_response.raise_for_status = Mock()

    client = MagicMock()
    client.get.side_effect = [settings_response, profile_response]
    workspace._client = client

    llm = workspace.get_llm()

    assert llm.model == "openhands/glm-5.2"
    assert isinstance(llm.api_key, SecretStr)
    assert llm.api_key.get_secret_value() == "sk-glm-key"
    assert llm.usage_id == "profile:glm-default"
    assert [call.args[0] for call in client.get.call_args_list] == [
        "/api/settings",
        "/api/profiles/glm-default",
    ]


@pytest.mark.parametrize("active_profile", [None, ""])
def test_get_llm_without_active_profile_falls_back_to_legacy(
    monkeypatch, active_profile
):
    """Falsy active_profile 值使用旧版 agent_settings.llm 回退方案。"""
    from pydantic import SecretStr

    monkeypatch.setenv("ALLOW_SHORT_CONTEXT_WINDOWS", "true")
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )

    settings_response = Mock()
    settings_response.json.return_value = {
        "agent_settings": {
            "llm": {"model": "gpt-4", "api_key": "sk-legacy"},
        },
        "conversation_settings": {},
        "llm_api_key_is_set": True,
        "active_profile": active_profile,
    }
    settings_response.raise_for_status = Mock()

    client = MagicMock()
    client.get.return_value = settings_response
    workspace._client = client

    llm = workspace.get_llm()

    assert llm.model == "gpt-4"
    assert isinstance(llm.api_key, SecretStr)
    assert llm.api_key.get_secret_value() == "sk-legacy"

    # 发现避免暴露遗产凭据； 仅当 active_profile 不存在时，回退方案才会获取它们。
    #
    assert [call.args[0] for call in client.get.call_args_list] == [
        "/api/settings",
        "/api/settings",
    ]
    assert client.get.call_args_list[0].kwargs["headers"] == {
        "X-Session-API-Key": "test-key"
    }
    assert client.get.call_args_list[1].kwargs["headers"] == {
        "X-Session-API-Key": "test-key",
        "X-Expose-Secrets": "plaintext",
    }


def test_get_llm_without_active_profile_rejects_acp_settings():
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )
    settings_response = Mock()
    settings_response.json.return_value = {
        "agent_settings": {"agent_kind": "acp", "acp_server": "claude-code"},
        "conversation_settings": {},
        "llm_api_key_is_set": False,
        "active_profile": None,
    }
    settings_response.raise_for_status = Mock()
    client = MagicMock()
    client.get.return_value = settings_response
    workspace._client = client

    with pytest.raises(ValueError, match="ACP agent"):
        workspace.get_llm()


def test_get_llm_with_kwargs_override(monkeypatch):
    """测试 get_llm 允许 kwargs 覆盖已持久化设置。"""
    from pydantic import SecretStr

    # 允许短上下文窗口进行测试
    monkeypatch.setenv("ALLOW_SHORT_CONTEXT_WINDOWS", "true")

    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )

    mock_client = MagicMock()
    mock_response = Mock()
    mock_response.json.return_value = {
        "agent_settings": {
            "llm": {
                "model": "gpt-3.5-turbo",
                "api_key": "sk-persisted-key",
            }
        },
        "conversation_settings": {},
        "llm_api_key_is_set": True,
        "active_profile": "default",
    }
    mock_response.raise_for_status = Mock()
    profile_response = Mock()
    profile_response.status_code = 200
    profile_response.raise_for_status = Mock()
    profile_response.json.return_value = {
        "name": "default",
        "config": {
            "model": "gpt-3.5-turbo",
            "api_key": "sk-persisted-key",
        },
    }
    mock_client.get.side_effect = [mock_response, profile_response]
    workspace._client = mock_client

    # 覆盖模型但使用活动配置文件 API 键
    llm = workspace.get_llm(model="gpt-4o")

    assert llm.model == "gpt-4o"  # 被覆盖
    # api_key 可以是 str | SecretStr | None
    assert llm.api_key is not None
    if isinstance(llm.api_key, SecretStr):
        assert llm.api_key.get_secret_value() == "sk-persisted-key"
    else:
        assert llm.api_key == "sk-persisted-key"


def test_get_llm_with_profile_name(monkeypatch):
    """测试 get_llm 可以加载命名的 LLM 配置文件。"""
    from pydantic import SecretStr

    monkeypatch.setenv("ALLOW_SHORT_CONTEXT_WINDOWS", "true")

    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )

    mock_client = MagicMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "name": "fast-model",
        "config": {
            "model": "openai/gpt-4o",
            "api_key": "sk-profile-key",
            "base_url": "https://litellm.example.com",
            "usage_id": "default",
        },
        "api_key_set": True,
    }
    mock_response.raise_for_status = Mock()
    mock_client.get.return_value = mock_response
    workspace._client = mock_client

    llm = workspace.get_llm(profile_name="fast-model", temperature=0.3)

    assert llm.model == "openai/gpt-4o"
    assert llm.temperature == 0.3
    assert isinstance(llm.api_key, SecretStr)
    assert llm.api_key.get_secret_value() == "sk-profile-key"
    assert llm.base_url == "https://litellm.example.com"
    assert llm.usage_id == "profile:fast-model"

    mock_client.get.assert_called_once()
    call_args = mock_client.get.call_args
    assert call_args[0][0] == "/api/profiles/fast-model"
    assert call_args[1]["headers"]["X-Expose-Secrets"] == "plaintext"
    assert call_args[1]["headers"]["X-Session-API-Key"] == "test-key"

    llm_with_override = workspace.get_llm(
        profile_name="fast-model", usage_id="custom-usage"
    )

    assert llm_with_override.usage_id == "custom-usage"


def test_get_llm_with_missing_profile_raises(monkeypatch):
    """测试 get_llm 引发 FileNotFoundError 缺少配置文件。"""
    monkeypatch.setenv("ALLOW_SHORT_CONTEXT_WINDOWS", "true")

    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )

    mock_client = MagicMock()
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.raise_for_status = Mock()
    mock_client.get.return_value = mock_response
    workspace._client = mock_client

    with pytest.raises(FileNotFoundError, match="missing"):
        workspace.get_llm(profile_name="missing")


def test_get_llm_raises_on_undefined_host():
    """当主机未定义时，测试 get_llm 引发 RuntimeError。"""
    workspace = RemoteWorkspace(host="undefined", working_dir="/tmp")

    with pytest.raises(RuntimeError, match="Workspace host is not set"):
        workspace.get_llm()


def test_get_secrets_returns_lookup_secrets():
    """测试 get_secrets 返回 LookupSecret 引用。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )

    mock_client = MagicMock()
    mock_response = Mock()
    mock_response.json.return_value = {
        "secrets": [
            {"name": "GITHUB_TOKEN", "description": "GitHub personal access token"},
            {"name": "OPENAI_API_KEY", "description": None},
        ]
    }
    mock_response.raise_for_status = Mock()
    mock_client.get.return_value = mock_response
    workspace._client = mock_client

    secrets = workspace.get_secrets()

    assert len(secrets) == 2
    assert "GITHUB_TOKEN" in secrets
    assert "OPENAI_API_KEY" in secrets

    # 检查LookupSecret结构
    gh_secret = secrets["GITHUB_TOKEN"]
    assert gh_secret.url == "http://localhost:8000/api/settings/secrets/GITHUB_TOKEN"
    assert gh_secret.headers == {"X-Session-API-Key": "test-key"}
    assert gh_secret.description == "GitHub personal access token"

    openai_secret = secrets["OPENAI_API_KEY"]
    assert openai_secret.description is None


def test_get_secrets_filters_by_names():
    """测试 get_secrets 按提供的名称过滤机密。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )

    mock_client = MagicMock()
    mock_response = Mock()
    mock_response.json.return_value = {
        "secrets": [
            {"name": "GITHUB_TOKEN", "description": "GitHub token"},
            {"name": "OPENAI_API_KEY", "description": "OpenAI key"},
            {"name": "AWS_ACCESS_KEY", "description": "AWS key"},
        ]
    }
    mock_response.raise_for_status = Mock()
    mock_client.get.return_value = mock_response
    workspace._client = mock_client

    # 仅请求特定的机密
    secrets = workspace.get_secrets(names=["GITHUB_TOKEN", "AWS_ACCESS_KEY"])

    assert len(secrets) == 2
    assert "GITHUB_TOKEN" in secrets
    assert "AWS_ACCESS_KEY" in secrets
    assert "OPENAI_API_KEY" not in secrets


def test_get_secrets_requests_agent_profile_scope():
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )
    mock_client = MagicMock()
    mock_response = Mock()
    mock_response.json.return_value = {"secrets": [{"name": "GITHUB_TOKEN"}]}
    mock_response.raise_for_status = Mock()
    mock_client.get.return_value = mock_response
    workspace._client = mock_client

    secrets = workspace.get_secrets(agent_profile_id="profile-id")

    assert list(secrets) == ["GITHUB_TOKEN"]
    mock_client.get.assert_called_once_with(
        "/api/settings/secrets",
        headers={"X-Session-API-Key": "test-key"},
        params={"agent_profile_id": "profile-id"},
    )


def test_get_secrets_returns_empty_dict_when_no_secrets():
    """当不存在机密时，测试 get_secrets 返回空字典。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    mock_client = MagicMock()
    mock_response = Mock()
    mock_response.json.return_value = {"secrets": []}
    mock_response.raise_for_status = Mock()
    mock_client.get.return_value = mock_response
    workspace._client = mock_client

    secrets = workspace.get_secrets()

    assert secrets == {}


def test_get_secrets_raises_on_undefined_host():
    """当主机未定义时，测试 get_secrets 引发 RuntimeError。"""
    workspace = RemoteWorkspace(host="undefined", working_dir="/tmp")

    with pytest.raises(RuntimeError, match="Workspace host is not set"):
        workspace.get_secrets()


def test_get_mcp_config_returns_config():
    """测试 get_mcp_config 返回 MCP 个服务器。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )

    mock_client = MagicMock()
    mock_response = Mock()
    mock_response.json.return_value = {
        "agent_settings": {
            "mcp_config": {
                "shttp_0": {
                    "url": "https://mcp.example.com/api",
                    "transport": "streamable-http",
                }
            }
        },
        "conversation_settings": {},
        "llm_api_key_is_set": True,
    }
    mock_response.raise_for_status = Mock()
    mock_client.get.return_value = mock_response
    workspace._client = mock_client

    config = workspace.get_mcp_config()
    dumped = dump_mcp_config(config)

    assert "shttp_0" in dumped
    assert dumped["shttp_0"]["url"] == "https://mcp.example.com/api"

    # 验证使用正确的标头调用 API
    call_args = mock_client.get.call_args
    assert call_args[1]["headers"]["X-Expose-Secrets"] == "plaintext"


def test_get_mcp_config_returns_empty_dict_when_no_config(monkeypatch):
    """当不存在 MCP 服务器时，测试 get_mcp_config 返回空字典。"""
    monkeypatch.setenv("ALLOW_SHORT_CONTEXT_WINDOWS", "true")
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/tmp")

    mock_client = MagicMock()
    mock_response = Mock()
    mock_response.json.return_value = {
        "agent_settings": {"llm": {"model": "gpt-4"}},
        "conversation_settings": {},
        "llm_api_key_is_set": True,
    }
    mock_response.raise_for_status = Mock()
    mock_client.get.return_value = mock_response
    workspace._client = mock_client

    config = workspace.get_mcp_config()

    assert config == {}


def test_get_mcp_config_raises_on_undefined_host():
    """当主机未定义时，测试 get_mcp_config 引发 RuntimeError。"""
    workspace = RemoteWorkspace(host="undefined", working_dir="/tmp")

    with pytest.raises(RuntimeError, match="Workspace host is not set"):
        workspace.get_mcp_config()


# ── 存储库克隆方法测试──────────────────────────────


def test_get_secret_value_returns_secret():
    """测试 _get_secret_value 从 Agent Server 获取机密。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )

    mock_client = MagicMock()
    mock_response = Mock()
    mock_response.text = "secret-token-value"
    mock_response.raise_for_status = Mock()
    mock_client.get.return_value = mock_response
    workspace._client = mock_client

    result = workspace._get_secret_value("github_token")

    assert result == "secret-token-value"
    mock_client.get.assert_called_once_with(
        "/api/settings/secrets/github_token",
        headers={"X-Session-API-Key": "test-key"},
    )


def test_get_secret_value_returns_none_on_404():
    """当未找到机密时，测试 _get_secret_value 返回 None。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )

    mock_client = MagicMock()
    mock_response = Mock()
    mock_response.status_code = 404
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "Not Found", request=Mock(), response=mock_response
    )
    workspace._client = mock_client

    result = workspace._get_secret_value("nonexistent_secret")

    assert result is None


def test_get_secret_value_returns_none_when_host_undefined():
    """当主机未定义时，测试 _get_secret_value 返回 None。"""
    workspace = RemoteWorkspace(host="undefined", working_dir="/tmp")

    result = workspace._get_secret_value("github_token")

    assert result is None


def test_get_secret_value_validates_secret_name():
    """测试 _get_secret_value 验证机密名称以防止路径遍历。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/tmp", api_key="test-key"
    )

    # 带有斜线的名字应该被拒绝
    assert workspace._get_secret_value("../etc/passwd") is None
    assert workspace._get_secret_value("secrets/github") is None

    # 空名应被拒绝
    assert workspace._get_secret_value("") is None


def test_clone_repos_calls_helper():
    """测试 clone_repos 委托辅助函数。"""
    from openhands.sdk.workspace.repo import CloneResult, RepoMapping

    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace", api_key="test-key"
    )

    with patch("openhands.sdk.workspace.remote.base._clone_repos_helper") as mock_clone:
        expected_result = CloneResult(
            success_count=1,
            failed_repos=[],
            repo_mappings={
                "https://github.com/owner/repo": RepoMapping(
                    url="https://github.com/owner/repo",
                    dir_name="repo",
                    local_path="/workspace/repo",
                )
            },
        )
        mock_clone.return_value = expected_result

        result = workspace.clone_repos(["https://github.com/owner/repo"])

        assert result == expected_result
        mock_clone.assert_called_once()

        # 验证 token_fetcher 是工作区的 _get_secret_value
        call_kwargs = mock_clone.call_args[1]
        assert call_kwargs["token_fetcher"] == workspace._get_secret_value


def test_clone_repos_normalizes_input_formats():
    """测试 clone_repos 接受字符串、字典和 RepoSource 对象。"""
    from openhands.sdk.workspace.repo import CloneResult, RepoSource

    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace", api_key="test-key"
    )

    with patch("openhands.sdk.workspace.remote.base._clone_repos_helper") as mock_clone:
        mock_clone.return_value = CloneResult(0, [], {})

        # 混合输入格式
        workspace.clone_repos(
            [
                "https://github.com/owner/repo1",  # 字符串
                {"url": "https://gitlab.com/owner/repo2", "ref": "main"},  # 词典
                RepoSource(url="https://bitbucket.org/owner/repo3"),  # RepoSource
            ]
        )

        # 验证所有输入均已标准化为 RepoSource
        call_kwargs = mock_clone.call_args[1]
        repos = call_kwargs["repos"]
        assert len(repos) == 3
        assert all(isinstance(r, RepoSource) for r in repos)


def test_clone_repos_uses_custom_target_dir():
    """测试 clone_repos 尊重自定义目标目录。"""
    from openhands.sdk.workspace.repo import CloneResult

    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace", api_key="test-key"
    )

    with patch("openhands.sdk.workspace.remote.base._clone_repos_helper") as mock_clone:
        mock_clone.return_value = CloneResult(0, [], {})

        workspace.clone_repos(
            ["https://github.com/owner/repo"],
            target_dir="/custom/path",
        )

        call_kwargs = mock_clone.call_args[1]
        assert call_kwargs["target_dir"] == Path("/custom/path")


def test_get_repos_context_delegates_to_helper():
    """测试 get_repos_context 委托辅助函数。"""
    from openhands.sdk.workspace.repo import RepoMapping

    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace", api_key="test-key"
    )

    mappings = {
        "https://github.com/owner/repo": RepoMapping(
            url="https://github.com/owner/repo",
            dir_name="repo",
            local_path="/workspace/repo",
            ref="main",
        )
    }

    context = workspace.get_repos_context(mappings)

    assert "## Cloned Repositories" in context
    assert "https://github.com/owner/repo" in context
    assert "/workspace/repo" in context


def test_get_repos_context_empty_mappings():
    """测试 get_repos_context 对于空映射返回空字符串。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace", api_key="test-key"
    )

    context = workspace.get_repos_context({})

    assert context == ""


# ── 技能加载方式测试──────────────────────────────────


def test_load_skills_from_agent_server_raises_when_not_initialized():
    """当未设置主机时，测试 load_skills_from_agent_server 会引发。"""
    workspace = RemoteWorkspace(host="undefined", working_dir="/workspace")

    with pytest.raises(RuntimeError, match="Workspace not initialized"):
        workspace.load_skills_from_agent_server()


def test_load_skills_from_agent_server_calls_api():
    """测试 load_skills_from_agent_server 调用 Agent Server API。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace", api_key="test-key"
    )

    mock_response = Mock()
    mock_response.json.return_value = {
        "skills": [
            {
                "name": "test-skill",
                "content": "Test content",
                "description": "A test skill",
                "triggers": ["test"],
                "is_agentskills_format": True,
                "disable_model_invocation": True,
            }
        ],
        "sources": {"public": 1},
    }
    mock_response.raise_for_status = Mock()

    with patch.object(workspace.client, "post", return_value=mock_response):
        skills, context = workspace.load_skills_from_agent_server()

        assert len(skills) == 1
        assert skills[0].name == "test-skill"
        assert skills[0].content == "Test content"
        assert skills[0].is_agentskills_format is True
        assert skills[0].disable_model_invocation is True
        assert context.load_public_skills is False  # 技能加载成功


def test_load_skills_from_agent_server_falls_back_when_no_skills():
    """加载 None 后，测试 load_skills 会退回到公共技能。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace", api_key="test-key"
    )

    mock_response = Mock()
    mock_response.json.return_value = {"skills": [], "sources": {}}
    mock_response.raise_for_status = Mock()

    with patch.object(workspace.client, "post", return_value=mock_response):
        skills, context = workspace.load_skills_from_agent_server()

        assert len(skills) == 0
        assert context.load_public_skills is True  # 回归公众视野


def test_load_skills_from_agent_server_with_project_dirs():
    """测试 load_skills_from_agent_server 从多个目录加载技能。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace", api_key="test-key"
    )

    # 不同的调用返回不同的技能
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        response = Mock()
        if call_count == 1:
            # 全球技能召唤
            response.json.return_value = {
                "skills": [{"name": "global-skill", "content": "Global"}],
                "sources": {},
            }
        else:
            # 项目具体调用
            response.json.return_value = {
                "skills": [
                    {"name": f"project-skill-{call_count}", "content": "Project"}
                ],
                "sources": {},
            }
        response.raise_for_status = Mock()
        return response

    with patch.object(workspace.client, "post", side_effect=side_effect) as mock_post:
        skills, context = workspace.load_skills_from_agent_server(
            project_dirs=["/workspace/repo1", "/workspace/repo2"]
        )

        # 应该已加载全局技能 + 2 个项目目录 = 3 个调用
        assert mock_post.call_count == 3
        assert len(skills) >= 1  # 至少有全局技能


def test_load_skills_from_agent_server_preserves_base_context_when_found():
    """测试 load_skills_from_agent_server 保留调用者的 AgentContext 字段。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace", api_key="test-key"
    )
    base_context = AgentContext(
        marketplace_path="internal/marketplace.json",
        disabled_skills=["risky-skill"],
        user_message_suffix="Follow the client's policy.",
    )
    mock_response = Mock()
    mock_response.json.return_value = {
        "skills": [{"name": "test-skill", "content": "Test content"}],
        "sources": {"public": 1},
    }
    mock_response.raise_for_status = Mock()

    with patch.object(workspace.client, "post", return_value=mock_response):
        skills, context = workspace.load_skills_from_agent_server(
            base_context=base_context
        )
        assert len(skills) == 1
        assert context.marketplace_path == "internal/marketplace.json"
        assert context.disabled_skills == ["risky-skill"]
        assert context.user_message_suffix == "Follow the client's policy."
        assert context.load_public_skills is False


def test_load_skills_from_agent_server_preserves_base_context_on_fallback():
    """即使没有找到技能，测试基地上下文字段也会存在。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace", api_key="test-key"
    )
    base_context = AgentContext(
        marketplace_path="internal/marketplace.json",
        disabled_skills=["risky-skill"],
    )
    mock_response = Mock()
    mock_response.json.return_value = {"skills": [], "sources": {}}
    mock_response.raise_for_status = Mock()

    with patch.object(workspace.client, "post", return_value=mock_response):
        skills, context = workspace.load_skills_from_agent_server(
            base_context=base_context
        )
        assert len(skills) == 0
        assert context.marketplace_path == "internal/marketplace.json"
        assert context.disabled_skills == ["risky-skill"]
        assert context.load_public_skills is True


def test_load_skills_from_agent_server_without_base_context_matches_legacy():
    """测试省略 base_context 与今天的默认行为相匹配。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace", api_key="test-key"
    )
    mock_response = Mock()
    mock_response.json.return_value = {
        "skills": [{"name": "test-skill", "content": "Test content"}],
        "sources": {"public": 1},
    }
    mock_response.raise_for_status = Mock()

    with patch.object(workspace.client, "post", return_value=mock_response):
        skills, context = workspace.load_skills_from_agent_server()
        assert context.marketplace_path == AgentContext().marketplace_path
        assert context.disabled_skills == AgentContext().disabled_skills
        assert context.user_message_suffix == AgentContext().user_message_suffix


def test_load_skills_from_agent_server_preserves_current_datetime():
    """来自基上下文的测试 current_datetime 不会重新生成。"""
    from datetime import datetime

    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace", api_key="test-key"
    )
    fixed_time = datetime(2020, 1, 1, tzinfo=UTC)
    base_context = AgentContext(current_datetime=fixed_time)
    mock_response = Mock()
    mock_response.json.return_value = {
        "skills": [{"name": "test-skill", "content": "Test content"}],
        "sources": {"public": 1},
    }
    mock_response.raise_for_status = Mock()

    with patch.object(workspace.client, "post", return_value=mock_response):
        _, context = workspace.load_skills_from_agent_server(base_context=base_context)
        assert context.current_datetime == fixed_time


def test_load_skills_from_agent_server_applies_disabled_skills():
    """测试disabled_skills中命名的技能是否被过滤掉，而不是仅仅携带。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace", api_key="test-key"
    )
    base_context = AgentContext(disabled_skills=["risky-skill"])
    mock_response = Mock()
    mock_response.json.return_value = {
        "skills": [
            {"name": "risky-skill", "content": "Denied"},
            {"name": "ok-skill", "content": "Allowed"},
        ],
        "sources": {"public": 2},
    }
    mock_response.raise_for_status = Mock()

    with patch.object(workspace.client, "post", return_value=mock_response):
        _, context = workspace.load_skills_from_agent_server(base_context=base_context)
        assert [s.name for s in context.skills] == ["ok-skill"]
        assert context.disabled_skills == ["risky-skill"]


def test_load_skills_from_agent_server_fallback_resolves_public_skills():
    """测试空技能回退方案具体化公共技能，如前。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace", api_key="test-key"
    )
    legacy = AgentContext(skills=[], load_public_skills=True)
    mock_response = Mock()
    mock_response.json.return_value = {"skills": [], "sources": {}}
    mock_response.raise_for_status = Mock()

    with patch.object(workspace.client, "post", return_value=mock_response):
        _, context = workspace.load_skills_from_agent_server()
        assert context.load_public_skills is True
        assert [s.name for s in context.skills] == [s.name for s in legacy.skills]


# --- 完成回调测试 ---


def test_register_conversation_stores_id():
    """测试 register_conversation 存储对话 ID。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")

    workspace.register_conversation("conv-123")

    assert workspace._conversation_id == "conv-123"
    assert workspace.conversation_id == "conv-123"


def test_conversation_id_property_returns_none_initially():
    """未注册时，测试 conversation_id 属性返回 None。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")

    assert workspace.conversation_id is None


def test_send_completion_callback_on_success(monkeypatch):
    """测试 _send_completion_callback POSTs COMPLETED 状态。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    monkeypatch.setenv("AUTOMATION_CALLBACK_API_KEY", "test-api-key")
    monkeypatch.setenv("AUTOMATION_RUN_ID", "run-42")

    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        workspace._send_completion_callback(None, None)

        mock_client.post.assert_called_once()
        (url,) = mock_client.post.call_args.args
        payload = mock_client.post.call_args.kwargs["json"]
        headers = mock_client.post.call_args.kwargs["headers"]
        assert url == "https://svc.test/complete"
        assert payload["status"] == "COMPLETED"
        assert payload["run_id"] == "run-42"
        assert "error" not in payload
        assert headers["Authorization"] == "Bearer test-api-key"


def test_send_completion_callback_includes_observability_headers(monkeypatch):
    """测试 _send_completion_callback 传播通用可观察性上下文。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    monkeypatch.setenv("AUTOMATION_CALLBACK_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENHANDS_OBSERVABILITY_METADATA", '{"automation.id":"auto-1"}')
    monkeypatch.setenv(
        "OPENHANDS_OBSERVABILITY_TAGS", "automation,automation.trigger:cron"
    )
    monkeypatch.setenv("OPENHANDS_OBSERVABILITY_SPAN_NAME", "automation.conversation")
    monkeypatch.setenv(
        "OPENHANDS_OBSERVABILITY_PARENT_SPAN_CONTEXT", "serialized-parent-context"
    )

    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        workspace._send_completion_callback(None, None)

        headers = mock_client.post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer test-api-key"
        assert headers["X-OpenHands-Observability-Metadata"] == (
            '{"automation.id":"auto-1"}'
        )
        assert headers["X-OpenHands-Observability-Tags"] == (
            "automation,automation.trigger:cron"
        )
        assert headers["X-OpenHands-Observability-Span-Name"] == (
            "automation.conversation"
        )
        assert headers["X-OpenHands-Observability-Parent-Span-Context"] == (
            "serialized-parent-context"
        )


def test_send_completion_callback_on_failure(monkeypatch):
    """测试 _send_completion_callback POSTs FAILED 状态并添加错误。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    monkeypatch.setenv("AUTOMATION_RUN_ID", "run-99")

    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        exc = RuntimeError("script crashed")
        workspace._send_completion_callback(RuntimeError, exc)

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["status"] == "FAILED"
        assert payload["run_id"] == "run-99"
        assert payload["error"]["detail"] == "script crashed"
        assert payload["error"]["code"] == "RuntimeError"


def test_send_completion_callback_no_op_without_url(monkeypatch):
    """当 URL 未设置时，测试 _send_completion_callback 不执行任何操作。"""
    monkeypatch.delenv("AUTOMATION_CALLBACK_URL", raising=False)

    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")

    with patch("httpx.Client") as MockClient:
        workspace._send_completion_callback(None, None)
        MockClient.assert_not_called()


def test_send_completion_callback_swallows_errors(monkeypatch):
    """测试 _send_completion_callback 不会引发 HTTP 错误。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")

    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        # 不应该提高
        workspace._send_completion_callback(None, None)


def test_send_completion_callback_without_api_key(monkeypatch):
    """当没有按键时，测试 _send_completion_callback 不发送授权。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    monkeypatch.delenv("AUTOMATION_CALLBACK_API_KEY", raising=False)

    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        workspace._send_completion_callback(None, None)

        headers = mock_client.post.call_args.kwargs["headers"]
        assert "Authorization" not in headers


def test_send_completion_callback_includes_conversation_id(monkeypatch):
    """注册时测试 _send_completion_callback 包括 conversation_id。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    monkeypatch.setenv("AUTOMATION_RUN_ID", "run-42")

    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")
    workspace.register_conversation("conv-xyz")

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        workspace._send_completion_callback(None, None)

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["status"] == "COMPLETED"
        assert payload["run_id"] == "run-42"
        assert payload["conversation_id"] == "conv-xyz"


def test_send_completion_callback_omits_conversation_id_when_not_registered(
    monkeypatch,
):
    """未注册时，测试 _send_completion_callback 会省略 conversation_id。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")

    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        workspace._send_completion_callback(None, None)

        payload = mock_client.post.call_args.kwargs["json"]
        assert "conversation_id" not in payload


def test_register_cost_stores_cost():
    """测试 register_cost 存储累积的 LLM 成本。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")

    workspace.register_cost(0.4213)

    assert workspace.accumulated_cost == 0.4213


def test_send_completion_callback_includes_registered_cost(monkeypatch):
    """测试 _send_completion_callback 报告注册成本。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")

    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")
    workspace.register_cost(0.4213)

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        workspace._send_completion_callback(None, None)

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["cost"] == 0.4213


def test_send_completion_callback_omits_cost_when_not_registered(monkeypatch):
    """测试 _send_completion_callback 在注册 None 时忽略了成本。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")

    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        workspace._send_completion_callback(None, None)

        payload = mock_client.post.call_args.kwargs["json"]
        assert "cost" not in payload


def test_send_completion_callback_serializes_conversation_error(monkeypatch):
    """A ConversationRunError 发送其权威 ConversationErrorEvent。"""
    from openhands.sdk.conversation.exceptions import ConversationRunError
    from openhands.sdk.event.conversation_error import ConversationErrorEvent

    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")
    error = ConversationErrorEvent(
        source="environment",
        code="LLMAuthenticationError",
        detail="invalid api key",
    )
    import uuid

    exc = ConversationRunError(
        uuid.uuid4(), RuntimeError("wrapper"), conversation_error=error
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        workspace._send_completion_callback(type(exc), exc)

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["error"] == error.model_dump(mode="json")
        assert payload["error"]["classification"]["kind"] == "auth"


def test_send_completion_callback_creates_fallback_error(monkeypatch):
    """非对话异常将转换为分类错误事件。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        exc = ValueError("bad configuration")
        workspace._send_completion_callback(type(exc), exc)

        error = mock_client.post.call_args.kwargs["json"]["error"]
        assert error["code"] == "ValueError"
        assert error["detail"] == "bad configuration"
        assert error["classification"]["kind"] == "unknown"
