"""单元测试对应 AsyncRemoteWorkspace 类。"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from openhands.sdk.workspace.models import CommandResult, FileOperationResult
from openhands.sdk.workspace.remote.async_remote_workspace import AsyncRemoteWorkspace


def test_async_remote_workspace_initialization():
    """测试 AsyncRemoteWorkspace 可以使用所需参数进行初始化。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", api_key="test-key", working_dir="workspace"
    )

    assert workspace.host == "http://localhost:8000"
    assert workspace.api_key == "test-key"


def test_async_remote_workspace_initialization_without_api_key():
    """无需API键即可初始化测试AsyncRemoteWorkspace。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    assert workspace.host == "http://localhost:8000"
    assert workspace.api_key is None


def test_async_remote_workspace_host_normalization():
    """通过删除尾部斜杠来测试主机 URL 是否已标准化。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000/", working_dir="workspace"
    )

    assert workspace.host == "http://localhost:8000"


def test_async_client_property_lazy_initialization():
    """测试客户端属性是否延迟创建 httpx.AsyncClient。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    # 客户端最初应为 None
    assert workspace._client is None

    # 访问客户端应该创建它
    client = workspace.client
    assert isinstance(client, httpx.AsyncClient)
    assert workspace._client is client

    # 后续访问应返回相同的客户端
    assert workspace.client is client


def test_async_headers_property_with_api_key():
    """测试 _headers 属性包含 API 键（如果存在）。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", api_key="test-key", working_dir="workspace"
    )

    headers = workspace._headers
    assert headers == {"X-Session-API-Key": "test-key"}


def test_async_headers_property_without_api_key():
    """当没有API键时测试_headers属性为空。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    headers = workspace._headers
    assert headers == {}


@pytest.mark.asyncio
async def test_async_execute_method():
    """测试 _execute 方法正确处理异步生成器协议。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    # 模拟对象异步客户端
    mock_client = AsyncMock()
    mock_response = Mock()
    mock_client.request.return_value = mock_response
    workspace._client = mock_client

    # 创建一个简单的生成器，生成请求 kwargs 并返回结果
    def test_generator():
        yield {"method": "GET", "url": "http://test.com"}
        return "test_result"

    result = await workspace._execute(test_generator())

    assert result == "test_result"
    mock_client.request.assert_called_once_with(method="GET", url="http://test.com")


@pytest.mark.asyncio
@patch(
    "openhands.sdk.workspace.remote.async_remote_workspace.AsyncRemoteWorkspace._execute"
)
async def test_async_execute_command(mock_execute):
    """测试 execute_command 方法使用正确的生成器调用 _execute。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    expected_result = CommandResult(
        command="echo hello",
        exit_code=0,
        stdout="hello\n",
        stderr="",
        timeout_occurred=False,
    )
    mock_execute.return_value = expected_result

    result = await workspace.execute_command("echo hello", cwd="/tmp", timeout=30.0)

    assert result == expected_result
    mock_execute.assert_called_once()

    # 验证生成器是否正确创建
    generator_arg = mock_execute.call_args[0][0]
    assert hasattr(generator_arg, "__next__")


@pytest.mark.asyncio
@patch(
    "openhands.sdk.workspace.remote.async_remote_workspace.AsyncRemoteWorkspace._execute"
)
async def test_async_file_upload(mock_execute):
    """测试 file_upload 方法使用正确的生成器调用 _execute。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    expected_result = FileOperationResult(
        success=True,
        source_path="/local/file.txt",
        destination_path="/remote/file.txt",
        file_size=100,
    )
    mock_execute.return_value = expected_result

    result = await workspace.file_upload("/local/file.txt", "/remote/file.txt")

    assert result == expected_result
    mock_execute.assert_called_once()

    # 验证生成器是否正确创建
    generator_arg = mock_execute.call_args[0][0]
    assert hasattr(generator_arg, "__next__")


@pytest.mark.asyncio
@patch(
    "openhands.sdk.workspace.remote.async_remote_workspace.AsyncRemoteWorkspace._execute"
)
async def test_async_file_download(mock_execute):
    """测试 file_download 方法使用正确的生成器调用 _execute。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    expected_result = FileOperationResult(
        success=True,
        source_path="/remote/file.txt",
        destination_path="/local/file.txt",
        file_size=100,
    )
    mock_execute.return_value = expected_result

    result = await workspace.file_download("/remote/file.txt", "/local/file.txt")

    assert result == expected_result
    mock_execute.assert_called_once()

    # 验证生成器是否正确创建
    generator_arg = mock_execute.call_args[0][0]
    assert hasattr(generator_arg, "__next__")


@pytest.mark.asyncio
async def test_async_execute_command_with_path_objects():
    """测试 execute_command 适用于 cwd 的 Path 对象。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    with patch.object(workspace, "_execute") as mock_execute:
        expected_result = CommandResult(
            command="ls",
            exit_code=0,
            stdout="file1.txt\n",
            stderr="",
            timeout_occurred=False,
        )
        mock_execute.return_value = expected_result

        result = await workspace.execute_command("ls", cwd=Path("/tmp/test"))

        assert result == expected_result
        mock_execute.assert_called_once()


@pytest.mark.asyncio
async def test_async_file_operations_with_path_objects():
    """测试文件操作使用 Path 对象。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    with patch.object(workspace, "_execute") as mock_execute:
        expected_result = FileOperationResult(
            success=True,
            source_path="/local/file.txt",
            destination_path="/remote/file.txt",
            file_size=100,
        )
        mock_execute.return_value = expected_result

        # 使用 Path 对象测试上传
        result = await workspace.file_upload(
            Path("/local/file.txt"), Path("/remote/file.txt")
        )
        assert result == expected_result

        # 使用 Path 对象测试下载
        result = await workspace.file_download(
            Path("/remote/file.txt"), Path("/local/file.txt")
        )
        assert result == expected_result


def test_async_inheritance():
    """测试AsyncRemoteWorkspace继承自正确的基类。"""
    from openhands.sdk.workspace.remote.remote_workspace_mixin import (
        RemoteWorkspaceMixin,
    )

    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    assert isinstance(workspace, RemoteWorkspaceMixin)


@pytest.mark.asyncio
async def test_async_execute_with_exception_handling():
    """测试 _execute 方法正确处理生成器中的异常。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    # 模拟对象异步客户端提出异常
    mock_client = AsyncMock()
    mock_client.request.side_effect = httpx.RequestError("Connection failed")
    workspace._client = mock_client

    def failing_generator():
        yield {"method": "GET", "url": "http://test.com"}
        return "should_not_reach_here"

    # 生成器应该处理异常，并不返回结果，因为异常发生在 client.request()，生成器将不能正
    # 常完成
    #
    with pytest.raises(httpx.RequestError):
        await workspace._execute(failing_generator())


@pytest.mark.asyncio
async def test_async_execute_generator_completion():
    """测试 _execute 方法正确处理 StopIteration 以获取返回值。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    # 模拟对象异步客户端
    mock_client = AsyncMock()
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

    result = await workspace._execute(test_generator())

    assert result == "final_result"
    assert mock_client.request.call_count == 2
    mock_client.request.assert_any_call(method="GET", url="http://test1.com")
    mock_client.request.assert_any_call(method="POST", url="http://test2.com")


@pytest.mark.asyncio
async def test_async_execute_multiple_yields():
    """测试 _execute 方法正确处理多个收益。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    # 模拟对象异步客户端
    mock_client = AsyncMock()
    responses = [Mock(), Mock(), Mock()]
    mock_client.request.side_effect = responses
    workspace._client = mock_client

    def multi_yield_generator():
        # 多个产量来模拟复杂的 API 相互作用
        yield {"method": "POST", "url": "http://start.com"}
        yield {"method": "GET", "url": "http://poll.com"}
        yield {"method": "GET", "url": "http://result.com"}
        return "complex_result"

    result = await workspace._execute(multi_yield_generator())

    assert result == "complex_result"
    assert mock_client.request.call_count == 3
    mock_client.request.assert_any_call(method="POST", url="http://start.com")
    mock_client.request.assert_any_call(method="GET", url="http://poll.com")
    mock_client.request.assert_any_call(method="GET", url="http://result.com")


@pytest.mark.asyncio
async def test_async_concurrent_operations():
    """测试多个异步操作是否可以同时运行。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    with patch.object(workspace, "_execute") as mock_execute:
        # 模拟对象不同操作结果不同
        command_result = CommandResult(
            command="echo test",
            exit_code=0,
            stdout="test\n",
            stderr="",
            timeout_occurred=False,
        )
        upload_result = FileOperationResult(
            success=True,
            source_path="/local/file1.txt",
            destination_path="/remote/file1.txt",
            file_size=50,
        )
        download_result = FileOperationResult(
            success=True,
            source_path="/remote/file2.txt",
            destination_path="/local/file2.txt",
            file_size=75,
        )

        mock_execute.side_effect = [command_result, upload_result, download_result]

        # 同时运行操作
        tasks = [
            workspace.execute_command("echo test"),
            workspace.file_upload("/local/file1.txt", "/remote/file1.txt"),
            workspace.file_download("/remote/file2.txt", "/local/file2.txt"),
        ]

        results = await asyncio.gather(*tasks)

        assert results[0] == command_result
        assert results[1] == upload_result
        assert results[2] == download_result
        assert mock_execute.call_count == 3


class MockHTTPResponse:
    """模拟对象 HTTP urlopen 响应。"""

    def __init__(self, status: int = 200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@patch("openhands.sdk.workspace.remote.async_remote_workspace.urlopen")
def test_async_alive_returns_true_on_successful_health_check(mock_urlopen):
    """当运行状况端点返回 2xx 状态时，测试活动属性返回 True。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    mock_urlopen.return_value = MockHTTPResponse(status=200)

    result = workspace.alive

    assert result is True
    mock_urlopen.assert_called_once_with("http://localhost:8000/health", timeout=5.0)


@patch("openhands.sdk.workspace.remote.async_remote_workspace.urlopen")
def test_async_alive_returns_true_on_204_status(mock_urlopen):
    """当运行状况端点返回 204 无内容时，测试活动属性返回 True。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    mock_urlopen.return_value = MockHTTPResponse(status=204)

    result = workspace.alive

    assert result is True


@patch("openhands.sdk.workspace.remote.async_remote_workspace.urlopen")
def test_async_alive_returns_false_on_server_error(mock_urlopen):
    """当运行状况端点返回 5xx 状态时，测试活动属性返回 False。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    mock_urlopen.return_value = MockHTTPResponse(status=500)

    result = workspace.alive

    assert result is False


@patch("openhands.sdk.workspace.remote.async_remote_workspace.urlopen")
def test_async_alive_returns_false_on_client_error(mock_urlopen):
    """当运行状况端点返回 4xx 状态时，测试活动属性返回 False。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    mock_urlopen.return_value = MockHTTPResponse(status=404)

    result = workspace.alive

    assert result is False


@patch("openhands.sdk.workspace.remote.async_remote_workspace.urlopen")
def test_async_alive_returns_false_on_connection_error(mock_urlopen):
    """当连接失败时，测试活动属性返回 False。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    mock_urlopen.side_effect = Exception("Connection refused")

    result = workspace.alive

    assert result is False


@patch("openhands.sdk.workspace.remote.async_remote_workspace.urlopen")
def test_async_alive_returns_false_on_timeout(mock_urlopen):
    """当请求超时时，测试活动属性返回 False。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="workspace"
    )

    from urllib.error import URLError

    mock_urlopen.side_effect = URLError("timed out")

    result = workspace.alive

    assert result is False


@patch("openhands.sdk.workspace.remote.async_remote_workspace.urlopen")
def test_async_alive_constructs_correct_health_url(mock_urlopen):
    """测试活动属性从主机构造正确的运行状况 URL。"""
    workspace = AsyncRemoteWorkspace(
        host="https://my-agent-server.example.com", working_dir="workspace"
    )

    mock_urlopen.return_value = MockHTTPResponse(status=200)

    _ = workspace.alive

    mock_urlopen.assert_called_once_with(
        "https://my-agent-server.example.com/health", timeout=5.0
    )


@patch("openhands.sdk.workspace.remote.async_remote_workspace.urlopen")
def test_async_alive_with_normalized_host(mock_urlopen):
    """当主机规范化时，测试活动属性可以正常工作。"""
    # 带有尾部斜杠的主机在 model_post_init 中标准化
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000/", working_dir="workspace"
    )

    mock_urlopen.return_value = MockHTTPResponse(status=200)

    result = workspace.alive

    assert result is True
    # 不应有双斜杠
    mock_urlopen.assert_called_once_with("http://localhost:8000/health", timeout=5.0)


def test_async_alive_is_property():
    """测试live是一个属性，而不是一个方法。"""
    assert isinstance(AsyncRemoteWorkspace.alive, property)
