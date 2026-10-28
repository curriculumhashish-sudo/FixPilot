"""测试夹具用于工作区测试。"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock

import httpx
import pytest

from openhands.sdk.workspace.models import CommandResult, FileOperationResult


@pytest.fixture
def mock_httpx_client():
    """创建模拟对象 httpx.Client 进行测试。"""
    return MagicMock(spec=httpx.Client)


@pytest.fixture
def mock_httpx_async_client():
    """创建模拟对象 httpx.AsyncClient 进行测试。"""
    return MagicMock(spec=httpx.AsyncClient)


@pytest.fixture
def mock_httpx_response():
    """创建模拟对象 httpx.Response 进行测试。"""
    response = Mock(spec=httpx.Response)
    response.raise_for_status = Mock()
    response.json = Mock()
    response.content = b"test content"
    return response


@pytest.fixture
def sample_command_result():
    """创建样本 CommandResult 进行测试。"""
    return CommandResult(
        command="echo 'hello'",
        exit_code=0,
        stdout="hello\n",
        stderr="",
        timeout_occurred=False,
    )


@pytest.fixture
def sample_file_operation_result():
    """创建样本 FileOperationResult 进行测试。"""
    return FileOperationResult(
        success=True,
        source_path="/tmp/source.txt",
        destination_path="/tmp/dest.txt",
        file_size=100,
        error=None,
    )


@pytest.fixture
def temp_file():
    """创建一个临时文件用于测试。"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("test content")
        temp_path = Path(f.name)

    yield temp_path

    # 清理
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def temp_dir():
    """创建一个临时目录用于测试。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)
