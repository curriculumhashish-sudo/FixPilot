"""单元测试对应 RemoteWorkspaceMixin 类。"""

import logging
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import httpx
import pytest

from openhands.sdk.workspace.models import CommandResult, FileOperationResult
from openhands.sdk.workspace.remote.remote_workspace_mixin import RemoteWorkspaceMixin


class RemoteWorkspaceMixinHelper(RemoteWorkspaceMixin):
    """出于测试目的测试 RemoteWorkspaceMixin 的实现。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


def test_remote_workspace_mixin_initialization():
    """测试 RemoteWorkspaceMixin 可以使用所需参数进行初始化。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", api_key="test-key", working_dir="workspace"
    )

    assert mixin.host == "http://localhost:8000"
    assert mixin.api_key == "test-key"


def test_remote_workspace_mixin_initialization_without_api_key():
    """无需API键即可初始化测试RemoteWorkspaceMixin。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )

    assert mixin.host == "http://localhost:8000"
    assert mixin.api_key is None


def test_host_normalization_in_post_init():
    """通过删除尾随斜杠来测试主机 URL 是否已标准化
    model_post_init."""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000/", working_dir="workspace"
    )

    assert mixin.host == "http://localhost:8000"


def test_headers_property_with_api_key():
    """测试 _headers 属性包含 API 键（如果存在）。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", api_key="test-key", working_dir="workspace"
    )

    headers = mixin._headers
    assert headers == {"X-Session-API-Key": "test-key"}


def test_headers_property_without_api_key():
    """当没有API键时测试_headers属性为空。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )

    headers = mixin._headers
    assert headers == {}


def test_headers_property_includes_observability_context(monkeypatch):
    monkeypatch.setenv(
        "OPENHANDS_OBSERVABILITY_METADATA",
        '{"automation.id":"automation-1","automation.run.trigger_source":"manual"}',
    )
    monkeypatch.setenv("OPENHANDS_OBSERVABILITY_TAGS", "automation, manual")
    monkeypatch.setenv("OPENHANDS_OBSERVABILITY_PARENT_SPAN_CONTEXT", "parent-context")
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", api_key="test-key", working_dir="workspace"
    )

    headers = mixin._headers

    assert headers["X-Session-API-Key"] == "test-key"
    assert (
        '"automation.id":"automation-1"'
        in headers["X-OpenHands-Observability-Metadata"]
    )
    assert (
        '"automation.run.trigger_source":"manual"'
        in headers["X-OpenHands-Observability-Metadata"]
    )
    assert headers["X-OpenHands-Observability-Tags"] == "automation,manual"
    assert headers["X-OpenHands-Observability-Parent-Span-Context"] == "parent-context"


def test_execute_command_generator_basic_flow():
    """测试_execute_command_generator流程基本成功。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", api_key="test-key", working_dir="workspace"
    )

    # 模拟对象回复
    start_response = Mock()
    start_response.raise_for_status = Mock()
    start_response.json.return_value = {"id": "cmd-123"}

    poll_response = Mock()
    poll_response.raise_for_status = Mock()
    poll_response.json.return_value = {
        "items": [
            {"kind": "BashOutput", "stdout": "hello\n", "stderr": "", "exit_code": 0}
        ]
    }

    generator = mixin._execute_command_generator("echo hello", "/tmp", 30.0)

    # 第一个yield - 启动命令
    start_kwargs = next(generator)
    assert start_kwargs["method"] == "POST"
    assert start_kwargs["url"] == "http://localhost:8000/api/bash/start_bash_command"
    assert start_kwargs["json"]["command"] == "echo hello"
    assert start_kwargs["json"]["cwd"] == "/tmp"
    assert start_kwargs["json"]["timeout"] == 30
    assert start_kwargs["headers"] == {"X-Session-API-Key": "test-key"}

    # 发送开始响应
    poll_kwargs = generator.send(start_response)
    assert poll_kwargs["method"] == "GET"
    assert poll_kwargs["url"] == "http://localhost:8000/api/bash/bash_events/search"

    # 发送民意调查响应并获取结果
    try:
        generator.send(poll_response)
        assert False, "Generator should have stopped"
    except StopIteration as e:
        result = e.value
        assert isinstance(result, CommandResult)
        assert result.command == "echo hello"
        assert result.exit_code == 0
        assert result.stdout == "hello\n"
        assert result.stderr == ""
        assert result.timeout_occurred is False


def test_execute_command_generator_without_cwd():
    """测试 _execute_command_generator 在没有 cwd 参数的情况下工作。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )

    generator = mixin._execute_command_generator("echo hello", None, 30.0)

    # 第一个yield - 启动命令
    start_kwargs = next(generator)
    assert "cwd" not in start_kwargs["json"]


def test_execute_command_generator_with_path_cwd():
    """测试 _execute_command_generator 适用于 cwd 的 Path 对象。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )

    generator = mixin._execute_command_generator("echo hello", Path("/tmp/test"), 30.0)

    # 第一个yield - 启动命令
    start_kwargs = next(generator)
    assert start_kwargs["json"]["cwd"] == "/tmp/test"


@patch("time.sleep")
@patch("time.time")
def test_execute_command_generator_polling_loop(mock_time, mock_sleep):
    """测试 _execute_command_generator 轮询循环行为。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )

    # 模拟对象时间进程
    mock_time.side_effect = [0, 0.1, 0.2, 0.3]  # 模拟时间流逝

    # 模拟对象回复
    start_response = Mock()
    start_response.raise_for_status = Mock()
    start_response.json.return_value = {"id": "cmd-123"}

    # 第一次民意调查 - 还没有退出代码
    poll_response_1 = Mock()
    poll_response_1.raise_for_status = Mock()
    poll_response_1.json.return_value = {
        "items": [
            {
                "kind": "BashOutput",
                "stdout": "processing...\n",
                "stderr": "",
                "exit_code": None,
            }
        ]
    }

    # 第二次轮询 - 命令已完成
    poll_response_2 = Mock()
    poll_response_2.raise_for_status = Mock()
    poll_response_2.json.return_value = {
        "items": [
            {"kind": "BashOutput", "stdout": "done\n", "stderr": "", "exit_code": 0}
        ]
    }

    generator = mixin._execute_command_generator("long_command", None, 30.0)

    # 启动命令
    next(generator)

    # 第一次民意调查
    generator.send(start_response)

    # 第二次民意调查
    generator.send(poll_response_1)

    # 最终结果
    try:
        generator.send(poll_response_2)
        assert False, "Generator should have stopped"
    except StopIteration as e:
        result = e.value
        assert result.stdout == "processing...\ndone\n"
        assert result.exit_code == 0

    # 验证轮询之间是否调用了睡眠
    mock_sleep.assert_called_with(0.1)


@patch("openhands.sdk.workspace.remote.remote_workspace_mixin.time")
def test_execute_command_generator_timeout(mock_time, caplog):
    """测试 _execute_command_generator 正确处理超时。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )
    secret = "ghp_" + "b" * 36
    caplog.set_level(logging.DEBUG)

    # 模拟对象模拟时间超时
    mock_time.time.side_effect = [
        0,
        0,
        35,
    ]  # 从 0 开始，然后跳转到 35（过去 30 秒超时）

    # 模拟对象回复
    start_response = Mock()
    start_response.raise_for_status = Mock()
    start_response.json.return_value = {"id": "cmd-123"}

    poll_response = Mock()
    poll_response.raise_for_status = Mock()
    poll_response.json.return_value = {
        "items": [
            {
                "kind": "BashOutput",
                "stdout": "still running...\n",
                "stderr": "",
                "exit_code": None,  # 无退出代码 - 仍在运行
            }
        ]
    }

    generator = mixin._execute_command_generator(
        f"curl -H 'Authorization: Bearer {secret}' example.test",
        None,
        30.0,
    )

    # 启动命令
    next(generator)

    # 投票一次
    generator.send(start_response)

    # 发送轮询响应并获取超时结果
    try:
        generator.send(poll_response)
        assert False, "Generator should have stopped"
    except StopIteration as e:
        result = e.value
        assert result.exit_code == -1
        assert result.timeout_occurred is True
        assert "timed out" in result.stderr
    assert "Command timed out" in caplog.text
    assert secret not in caplog.text


def test_execute_command_generator_exception_handling(
    caplog: pytest.LogCaptureFixture,
):
    """测试 _execute_command_generator 正确处理异常。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )
    secret = "ghp_" + "f" * 36
    caplog.set_level(logging.DEBUG)

    # 模拟对象引发异常的响应
    start_response = Mock()
    start_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        f"Server rejected command containing {secret}",
        request=Mock(),
        response=Mock(),
    )

    generator = mixin._execute_command_generator(
        f"curl -H 'Authorization: Bearer {secret}' example.test",
        None,
        30.0,
    )

    # 启动命令
    next(generator)

    # 发送失败响应
    try:
        generator.send(start_response)
        assert False, "Generator should have stopped"
    except StopIteration as e:
        result = e.value
        assert result.exit_code == -1
        assert "Remote execution error" in result.stderr
        assert result.timeout_occurred is False
    assert "Remote command execution failed" in caplog.text
    assert secret not in caplog.text


def test_file_upload_generator_basic_flow(temp_file):
    """测试_file_upload_generator流程基本成功。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", api_key="test-key", working_dir="workspace"
    )

    # 模拟对象成功回复
    upload_response = Mock()
    upload_response.raise_for_status = Mock()
    upload_response.json.return_value = {"success": True, "file_size": 12}

    destination = "/remote/file.txt"
    generator = mixin._file_upload_generator(temp_file, "/remote/file.txt")

    # 获取上传请求
    upload_kwargs = next(generator)
    assert upload_kwargs["method"] == "POST"
    assert upload_kwargs["url"] == "http://localhost:8000/api/file/upload"
    assert upload_kwargs["params"] == {"path": destination}
    assert "file" in upload_kwargs["files"]
    assert upload_kwargs["headers"] == {"X-Session-API-Key": "test-key"}

    # 发送响应并获取结果
    try:
        generator.send(upload_response)
        assert False, "Generator should have stopped"
    except StopIteration as e:
        result = e.value
        assert isinstance(result, FileOperationResult)
        assert result.success is True
        assert result.source_path == str(temp_file)
        assert result.destination_path == "/remote/file.txt"
        assert result.file_size == 12


def test_file_upload_generator_with_path_objects(temp_file):
    """测试 _file_upload_generator 适用于 Path 对象。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )

    upload_response = Mock()
    upload_response.raise_for_status = Mock()
    upload_response.json.return_value = {"success": True}

    generator = mixin._file_upload_generator(Path(temp_file), Path("/remote/file.txt"))

    upload_kwargs = next(generator)
    assert upload_kwargs["params"] == {"path": "/remote/file.txt"}


def test_file_upload_generator_file_not_found():
    """测试 _file_upload_generator 处理文件未找到错误。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )

    generator = mixin._file_upload_generator(
        "/nonexistent/file.txt", "/remote/file.txt"
    )

    # 应该处理 FileNotFoundError
    try:
        next(generator)
        assert False, "Generator should have stopped"
    except StopIteration as e:
        result = e.value
        assert result.success is False
        assert (
            "No such file or directory" in result.error or "[Errno 2]" in result.error
        )


def test_file_upload_generator_http_error():
    """测试 _file_upload_generator 处理 HTTP 错误。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )

    with patch("builtins.open", mock_open(read_data="test content")):
        upload_response = Mock()
        upload_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Upload failed", request=Mock(), response=Mock()
        )

        generator = mixin._file_upload_generator("/local/file.txt", "/remote/file.txt")

        # 获取上传请求
        next(generator)

        # 发送失败响应
        try:
            generator.send(upload_response)
            assert False, "Generator should have stopped"
        except StopIteration as e:
            result = e.value
            assert result.success is False
            assert "Upload failed" in result.error


def test_file_download_generator_basic_flow(temp_dir):
    """测试_file_download_generator流程基本成功。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", api_key="test-key", working_dir="workspace"
    )

    # 模拟对象成功回复
    download_response = Mock()
    download_response.raise_for_status = Mock()
    download_response.content = b"downloaded content"

    destination = temp_dir / "downloaded_file.txt"
    generator = mixin._file_download_generator("/remote/file.txt", destination)

    # 获取下载请求
    download_kwargs = next(generator)
    assert download_kwargs["method"] == "GET"
    assert download_kwargs["url"] == "/api/file/download"
    assert download_kwargs["params"] == {"path": "/remote/file.txt"}
    assert download_kwargs["headers"] == {"X-Session-API-Key": "test-key"}

    # 发送响应并获取结果
    try:
        generator.send(download_response)
        assert False, "Generator should have stopped"
    except StopIteration as e:
        result = e.value
        assert isinstance(result, FileOperationResult)
        assert result.success is True
        assert result.source_path == "/remote/file.txt"
        assert result.destination_path == str(destination)
        assert result.file_size == len(b"downloaded content")

        # 验证文件已写入
        assert destination.exists()
        assert destination.read_bytes() == b"downloaded content"


def test_file_download_generator_with_path_objects(temp_dir):
    """测试 _file_download_generator 适用于 Path 对象。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )

    download_response = Mock()
    download_response.raise_for_status = Mock()
    download_response.content = b"test content"

    destination = temp_dir / "test_file.txt"
    generator = mixin._file_download_generator(Path("/remote/file.txt"), destination)

    download_kwargs = next(generator)
    assert download_kwargs["url"] == "/api/file/download"
    assert download_kwargs["params"] == {"path": "/remote/file.txt"}


def test_file_download_generator_creates_directories(temp_dir):
    """测试 _file_download_generator 创建父目录。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )

    download_response = Mock()
    download_response.raise_for_status = Mock()
    download_response.content = b"test content"

    # 不存在的嵌套路径
    destination = temp_dir / "nested" / "dirs" / "file.txt"
    generator = mixin._file_download_generator("/remote/file.txt", destination)

    next(generator)

    try:
        generator.send(download_response)
    except StopIteration as e:
        result = e.value
        assert result.success is True

        # 验证目录已创建
        assert destination.parent.exists()
        assert destination.exists()


def test_file_download_generator_http_error():
    """测试 _file_download_generator 处理 HTTP 错误。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )

    download_response = Mock()
    download_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "File not found", request=Mock(), response=Mock()
    )

    generator = mixin._file_download_generator(
        "/remote/nonexistent.txt", "/local/file.txt"
    )

    # 获取下载请求
    next(generator)

    # 发送失败响应
    try:
        generator.send(download_response)
        assert False, "Generator should have stopped"
    except StopIteration as e:
        result = e.value
        assert result.success is False
        assert "File not found" in result.error


def test_multiple_bash_output_events():
    """测试在轮询中处理多个 BashOutput 事件。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )

    # 模拟对象回复
    start_response = Mock()
    start_response.raise_for_status = Mock()
    start_response.json.return_value = {"id": "cmd-123"}

    # 单个轮询响应中的多个事件
    poll_response = Mock()
    poll_response.raise_for_status = Mock()
    poll_response.json.return_value = {
        "items": [
            {
                "kind": "BashOutput",
                "stdout": "line 1\n",
                "stderr": "",
                "exit_code": None,
            },
            {
                "kind": "BashOutput",
                "stdout": "line 2\n",
                "stderr": "warning\n",
                "exit_code": None,
            },
            {"kind": "BashOutput", "stdout": "line 3\n", "stderr": "", "exit_code": 0},
        ]
    }

    generator = mixin._execute_command_generator("multi_output_command", None, 30.0)

    # 启动命令
    next(generator)

    # 投票并获得结果
    generator.send(start_response)

    try:
        generator.send(poll_response)
        assert False, "Generator should have stopped"
    except StopIteration as e:
        result = e.value
        assert result.stdout == "line 1\nline 2\nline 3\n"
        assert result.stderr == "warning\n"
        assert result.exit_code == 0


def test_non_bash_output_events_ignored():
    """测试轮询期间是否忽略非 BashOutput 事件。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", working_dir="workspace"
    )

    # 模拟对象回复
    start_response = Mock()
    start_response.raise_for_status = Mock()
    start_response.json.return_value = {"id": "cmd-123"}

    # 事件类型混合
    poll_response = Mock()
    poll_response.raise_for_status = Mock()
    poll_response.json.return_value = {
        "items": [
            {"kind": "SomeOtherEvent", "data": "should be ignored"},
            {
                "kind": "BashOutput",
                "stdout": "actual output\n",
                "stderr": "",
                "exit_code": 0,
            },
            {"kind": "AnotherEvent", "info": "also ignored"},
        ]
    }

    generator = mixin._execute_command_generator("test_command", None, 30.0)

    # 启动命令
    next(generator)

    # 投票并获得结果
    generator.send(start_response)

    try:
        generator.send(poll_response)
        assert False, "Generator should have stopped"
    except StopIteration as e:
        result = e.value
        assert result.stdout == "actual output\n"
        assert result.exit_code == 0


def test_start_bash_command_endpoint_used():
    """测试是否使用了正确的 /api/bash/start_bash_command 端点。

    这是针对问题 #866 的回归测试，其中使用了错误的端点（/api/bash/terminal_command)，
    导致命令超时。 正确的端点是
    /api/bash/start_bash_command，它异步启动命令并立即返回可轮询的命令 ID。
    """
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000", api_key="test-key", working_dir="workspace"
    )

    # 模拟对象命令启动成功的响应
    start_response = Mock()
    start_response.raise_for_status = Mock()
    start_response.json.return_value = {"id": "cmd-456"}

    # 模拟对象投票回复
    poll_response = Mock()
    poll_response.raise_for_status = Mock()
    poll_response.json.return_value = {
        "items": [
            {
                "kind": "BashOutput",
                "stdout": "Hello from sandboxed environment!\n/workspace\n",
                "stderr": "",
                "exit_code": 0,
            }
        ]
    }

    # 为类似于问题 #866 中的命令创建生成器
    command = "echo 'Hello from sandboxed environment!' && pwd"
    generator = mixin._execute_command_generator(command, None, 30.0)

    # 验证是否使用正确的端点来启动命令
    start_kwargs = next(generator)
    assert start_kwargs["method"] == "POST"
    # 这是关键检查 - 必须使用 start_bash_command，而不是 terminal_command
    #
    assert start_kwargs["url"] == "http://localhost:8000/api/bash/start_bash_command"
    assert "start_bash_command" in start_kwargs["url"], (
        "Must use /api/bash/start_bash_command endpoint. "
        "The /api/bash/terminal_command endpoint does not exist and causes "
        "timeouts."
    )
    assert start_kwargs["json"]["command"] == command
    assert start_kwargs["json"]["timeout"] == 30
    assert start_kwargs["headers"] == {"X-Session-API-Key": "test-key"}
    # 验证 HTTP 超时已添加缓冲区
    assert start_kwargs["timeout"] == 35.0

    # 验证轮询是否正常工作
    poll_kwargs = generator.send(start_response)
    assert poll_kwargs["method"] == "GET"
    assert poll_kwargs["url"] == "http://localhost:8000/api/bash/bash_events/search"

    # 验证命令成功完成
    try:
        generator.send(poll_response)
        assert False, "Generator should have stopped"
    except StopIteration as e:
        result = e.value
        assert isinstance(result, CommandResult)
        assert result.exit_code == 0
        assert "Hello from sandboxed environment!" in result.stdout
        assert result.timeout_occurred is False


def test_git_changes_generator_uses_query_param_with_posix_paths():
    """测试 git 更改请求使用带有斜杠规范化路径的查询参数。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000",
        api_key="test-key",
        working_dir=r"C:\workspace\repo",
    )

    generator = mixin._git_changes_generator(r"subdir\file.py")
    request_kwargs = next(generator)

    assert request_kwargs["method"] == "GET"
    assert request_kwargs["url"] == "/api/git/changes"
    assert request_kwargs["params"] == {"path": "C:/workspace/repo/subdir/file.py"}
    assert request_kwargs["headers"] == {"X-Session-API-Key": "test-key"}


def test_git_diff_generator_uses_query_param_with_posix_paths():
    """测试 git diff 请求使用具有斜杠标准化路径的查询参数。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000",
        working_dir=r"C:\workspace\repo",
    )

    generator = mixin._git_diff_generator(Path("nested") / "file.py")
    request_kwargs = next(generator)

    assert request_kwargs["method"] == "GET"
    assert request_kwargs["url"] == "/api/git/diff"
    assert request_kwargs["params"] == {"path": "C:/workspace/repo/nested/file.py"}
    assert request_kwargs["headers"] == {}


def test_git_changes_generator_preserves_absolute_paths():
    """测试 git 更改请求保留绝对路径而不是加入它们。"""
    mixin = RemoteWorkspaceMixinHelper(
        host="http://localhost:8000",
        working_dir=r"C:\workspace\repo",
    )

    windows_generator = mixin._git_changes_generator(r"D:\other\file.py")
    windows_request_kwargs = next(windows_generator)
    assert windows_request_kwargs["params"] == {"path": "D:/other/file.py"}

    posix_generator = mixin._git_changes_generator("/var/tmp/file.py")
    posix_request_kwargs = next(posix_generator)
    assert posix_request_kwargs["params"] == {"path": "/var/tmp/file.py"}
