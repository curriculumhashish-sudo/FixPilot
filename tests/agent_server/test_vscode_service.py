"""VSCode 服务的测试。"""

import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, call, patch
from urllib.parse import parse_qs, urlsplit

import pytest

from openhands.agent_server.vscode_service import (
    VSCodeService,
    get_vscode_service,
)


@pytest.fixture
def vscode_service(tmp_path):
    """创建一个 VSCode 服务实例用于测试。"""
    return VSCodeService(
        port=8001,
    )


@pytest.fixture
def mock_openvscode_binary(tmp_path):
    """创建一个模拟对象 VSCode 二进制文件用于测试。"""
    openvscode_root = tmp_path / "openhands" / ".openvscode-server"
    openvscode_root.mkdir(parents=True)

    bin_dir = openvscode_root / "bin"
    bin_dir.mkdir()

    binary = bin_dir / "openvscode-server"
    binary.write_text("#!/bin/bash\necho 'mock vscode server'")
    binary.chmod(0o755)

    return openvscode_root


def test_vscode_service_initialization(tmp_path):
    """测试 VSCode 服务初始化。"""
    service = VSCodeService(port=8002)

    assert service.port == 8002
    assert service.connection_token is None
    assert service.server_base_path is None
    assert service.process is None


def test_vscode_service_initialization_with_server_base_path():
    """测试 VSCode 服务初始化 server_base_path。"""
    service = VSCodeService(port=8002, server_base_path="/test/vscode")

    assert service.port == 8002
    assert service.server_base_path == "/test/vscode"
    assert service.connection_token is None
    assert service.process is None


def test_check_vscode_available_false(vscode_service, tmp_path):
    """Test VSCode 当二进制不存在时的可用性检查。"""
    # 设置不存在的路径
    vscode_service.openvscode_server_root = tmp_path / "nonexistent"
    assert not vscode_service._check_vscode_available()


def test_check_vscode_available_true(vscode_service, mock_openvscode_binary):
    """Test VSCode 存在二进制文件时的可用性检查。"""
    vscode_service.openvscode_server_root = mock_openvscode_binary
    assert vscode_service._check_vscode_available()


@pytest.mark.asyncio
async def test_is_port_available_true(tmp_path):
    """当端口空闲时测试端口可用性检查。"""
    service = VSCodeService(port=0)  # 使用端口 0 获取任何可用端口
    assert await service._is_port_available()


@pytest.mark.asyncio
async def test_is_port_available_false(tmp_path):
    """测试端口可用性，检查端口是否被占用。"""
    # 在特定端口上启动服务器
    server = await asyncio.start_server(lambda r, w: None, "localhost", 0)
    port = server.sockets[0].getsockname()[1]

    service = VSCodeService(port=port)
    assert not await service._is_port_available()

    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
async def test_start_success(vscode_service, mock_openvscode_binary, tmp_path):
    """测试成功 VSCode 服务启动。"""
    vscode_service.openvscode_server_root = mock_openvscode_binary

    with (
        patch.object(vscode_service, "_is_port_available", return_value=True),
        patch.object(vscode_service, "_start_vscode_process") as mock_start,
    ):
        result = await vscode_service.start()

        assert result is True
        assert vscode_service.connection_token is not None
        mock_start.assert_called_once()


@pytest.mark.asyncio
async def test_start_no_binary(vscode_service, tmp_path):
    """当二进制不可用时，测试 VSCode 服务启动。"""
    # 设置不存在的路径
    vscode_service.openvscode_server_root = tmp_path / "nonexistent"
    result = await vscode_service.start()

    assert result is False
    assert vscode_service.connection_token is None


@pytest.mark.asyncio
async def test_start_port_unavailable(vscode_service, mock_openvscode_binary):
    """当端口不可用时，测试 VSCode 服务启动。"""
    vscode_service.openvscode_server_root = mock_openvscode_binary

    with patch.object(vscode_service, "_is_port_available", return_value=False):
        result = await vscode_service.start()

        assert result is False
        assert vscode_service.connection_token is not None  # token 在端口检查之前生成


@pytest.mark.asyncio
async def test_stop_with_process(vscode_service):
    """停止向整个进程组发出信号，因为启动程序脚本
    将节点作为子节点运行。"""
    mock_process = AsyncMock(pid=4321)
    vscode_service.process = mock_process

    with (
        patch("openhands.agent_server.vscode_service.os.killpg") as mock_killpg,
        patch.object(vscode_service, "_is_port_available", return_value=True),
    ):
        await vscode_service.stop()

    mock_killpg.assert_called_once_with(4321, signal.SIGTERM)
    mock_process.wait.assert_called_once()
    assert vscode_service.process is None


@pytest.mark.asyncio
async def test_stop_waits_for_port_release(vscode_service):
    """启动器退出是不够的：一旦节点有stop()返回
    释放了端口，因此重新启动可以绑定它。"""
    vscode_service.process = AsyncMock(pid=4321)

    with (
        patch("openhands.agent_server.vscode_service.os.killpg"),
        patch.object(
            vscode_service, "_is_port_available", side_effect=[False, False, True]
        ) as mock_port_check,
    ):
        await vscode_service.stop()

    assert mock_port_check.call_count == 3
    assert vscode_service.process is None


@pytest.mark.asyncio
async def test_stop_with_timeout(vscode_service):
    """停止 VSCode 服务超时。"""
    mock_process = AsyncMock(pid=4321)
    # 第一次调用 wait() 应该超时，第二次调用应该成功
    mock_process.wait.side_effect = [TimeoutError(), None]
    vscode_service.process = mock_process

    with patch("openhands.agent_server.vscode_service.os.killpg") as mock_killpg:
        await vscode_service.stop()

    assert mock_killpg.call_args_list == [
        call(4321, signal.SIGTERM),
        call(4321, signal.SIGKILL),
    ]
    assert mock_process.wait.call_count == 2


@pytest.mark.asyncio
async def test_stop_after_process_group_is_gone(vscode_service):
    """已退出的服务器将停止且不会出现错误。"""
    vscode_service.process = AsyncMock(pid=4321)

    with (
        patch(
            "openhands.agent_server.vscode_service.os.killpg",
            side_effect=ProcessLookupError,
        ),
        patch.object(vscode_service, "_is_port_available", return_value=True),
        patch("openhands.agent_server.vscode_service.logger") as mock_logger,
    ):
        await vscode_service.stop()

    mock_logger.error.assert_not_called()
    assert vscode_service.process is None


@pytest.mark.asyncio
async def test_stop_no_process(vscode_service):
    """停止 VSCode 服务，该服务没有运行中的进程。"""
    await vscode_service.stop()  # 不应引发任何异常


@pytest.mark.asyncio
async def test_set_connection_token_restarts_running_server(
    vscode_service, mock_openvscode_binary
):
    """openvscode-server 仅在启动时读取其 token，因此正在运行的服务器
    使用新的 token 重新启动。"""
    vscode_service.openvscode_server_root = mock_openvscode_binary
    vscode_service.connection_token = "boot-token"
    vscode_service.process = AsyncMock(pid=4321, returncode=None)
    new_process = AsyncMock(returncode=None)

    with (
        patch("openhands.agent_server.vscode_service.os.killpg") as mock_killpg,
        patch.object(vscode_service, "_is_port_available", return_value=True),
        patch(
            "asyncio.create_subprocess_shell", return_value=new_process
        ) as mock_create,
        patch.object(vscode_service, "_wait_for_startup"),
    ):
        await vscode_service.set_connection_token("session-key")

    mock_killpg.assert_called_once_with(4321, signal.SIGTERM)
    assert vscode_service.process is new_process
    assert "--connection-token session-key " in mock_create.call_args[0][0]
    assert vscode_service.get_vscode_url() == (
        "http://localhost:8001/?tkn=session-key&folder=workspace"
    )


@pytest.mark.asyncio
async def test_set_connection_token_same_token_keeps_server(vscode_service):
    """再次设置当前的 token 将使服务器保持运行。"""
    process = AsyncMock(returncode=None)
    vscode_service.connection_token = "session-key"
    vscode_service.process = process

    with patch.object(vscode_service, "stop") as mock_stop:
        await vscode_service.set_connection_token("session-key")

    mock_stop.assert_not_called()
    assert vscode_service.process is process


@pytest.mark.asyncio
async def test_set_connection_token_without_running_server(vscode_service):
    """未运行的服务器保留其 token，因此不会通告 URL
    对于一个从未启动的 VSCode。"""
    with patch.object(vscode_service, "start") as mock_start:
        await vscode_service.set_connection_token("session-key")

    mock_start.assert_not_called()
    assert vscode_service.connection_token is None
    assert vscode_service.get_vscode_url() is None


def test_get_vscode_url_no_token(vscode_service):
    """测试获取 VSCode  URL without token."""
    url = vscode_service.get_vscode_url()
    assert url is None


def test_get_vscode_url_none_when_not_running(vscode_service):
    """单独的 token 不是服务器：密钥服务器在 token 之前播种
    start() 运行，因此不得公布从未启动的服务器。"""
    vscode_service.connection_token = "session-key"
    assert vscode_service.get_vscode_url() is None

    # 退出的服务器也不会被通告。
    vscode_service.process = MagicMock(returncode=1)
    assert vscode_service.get_vscode_url() is None


@pytest.mark.asyncio
async def test_get_vscode_url_none_after_failed_start(
    vscode_service, mock_openvscode_binary
):
    """start() 在端口检查之前铸造 token； 未能通过该检查必须
    不要留下URL。"""
    vscode_service.openvscode_server_root = mock_openvscode_binary
    with patch.object(vscode_service, "_is_port_available", return_value=False):
        assert await vscode_service.start() is False

    assert vscode_service.connection_token is not None
    assert vscode_service.get_vscode_url() is None


def test_get_vscode_url_with_token(vscode_service):
    """测试 VSCode URL 的获取 token。"""
    vscode_service.connection_token = "test-token-123"
    vscode_service.process = MagicMock(returncode=None)  # 跑步

    # 使用默认 base_url 进行测试（应使用配置的端口）
    url = vscode_service.get_vscode_url()
    expected_url = (
        f"http://localhost:{vscode_service.port}/?tkn=test-token-123&folder=workspace"
    )
    assert url == expected_url

    # 使用自定义测试 base_url
    custom_url = vscode_service.get_vscode_url(base_url="http://example.com:9000")
    assert custom_url == "http://example.com:9000/?tkn=test-token-123&folder=workspace"


@pytest.mark.parametrize(
    "workspace_dir",
    ["/tmp/qa f16&x=1#frag", "/w/a?b=c", "/w/100% +plus", "/workspace"],
)
def test_get_vscode_url_folder_round_trips(vscode_service, workspace_dir):
    """文件夹参数解码回确切的工作区路径。"""
    vscode_service.connection_token = "test-token-123"
    vscode_service.process = MagicMock(returncode=None)  # 跑步

    url = vscode_service.get_vscode_url(workspace_dir=workspace_dir)

    assert url is not None
    parts = urlsplit(url)
    assert parts.fragment == ""
    assert parse_qs(parts.query) == {
        "tkn": ["test-token-123"],
        "folder": [workspace_dir],
    }


def test_get_vscode_url_keeps_slashes_readable(vscode_service):
    """文件夹参数中的路径分隔符不是百分比编码的。"""
    vscode_service.connection_token = "test-token-123"
    vscode_service.process = MagicMock(returncode=None)  # 跑步

    url = vscode_service.get_vscode_url(workspace_dir="/tmp/qa f16&x=1#frag")

    assert url == (
        f"http://localhost:{vscode_service.port}/"
        "?tkn=test-token-123&folder=/tmp/qa%20f16%26x%3D1%23frag"
    )


def test_get_vscode_url_with_custom_port():
    """测试使用自定义端口获取 VSCode URL。"""
    service = VSCodeService(port=9001)
    service.connection_token = "test-token-456"
    service.process = MagicMock(returncode=None)  # 跑步

    url = service.get_vscode_url()
    assert url == "http://localhost:9001/?tkn=test-token-456&folder=workspace"


def test_get_vscode_url_includes_server_base_path():
    """测试配置的 server_base_path 是否出现在 URL 中。

    基本路径作为 ``--server-base-path`` 传递到 openvscode-server，因此服务器仅在该前
    缀下进行响应 - 根 URL 无法解析。
    """
    service = VSCodeService(port=19000, server_base_path="/vscode")
    service.connection_token = "test-token-789"
    service.process = MagicMock(returncode=None)  # 跑步

    assert (
        service.get_vscode_url()
        == "http://localhost:19000/vscode/?tkn=test-token-789&folder=workspace"
    )


def test_get_vscode_url_base_path_with_caller_supplied_base_url():
    """测试基本路径是否附加到调用者提供的 base_url。

    反向代理后面的调用者传递他们自己的公共来源； 他们仍然无法知道服务器的基本路径，因
    此必须在此处应用它。 基本路径已标准化，因此 '/vscode'、'vscode'
     和尾部斜杠 base_url 都会生成相同的单斜杠 URL。
    """
    service = VSCodeService(port=19000, server_base_path="vscode")
    service.connection_token = "test-token-789"
    service.process = MagicMock(returncode=None)  # 跑步

    expected = "https://example.com/vscode/?tkn=test-token-789&folder=/srv/work"
    assert (
        service.get_vscode_url(
            base_url="https://example.com", workspace_dir="/srv/work"
        )
        == expected
    )
    assert (
        service.get_vscode_url(
            base_url="https://example.com/", workspace_dir="/srv/work"
        )
        == expected
    )


def test_get_vscode_url_without_base_path_is_unchanged():
    """URLs 应当在未配置基础路径时视为字节等价。

    未设置的下游客户端（OpenHands-CLI、应用程序服务器、企业）
    ``vscode_base_path`` 必须准确地看到先前的输出。
    """
    service = VSCodeService(port=8001)
    service.connection_token = "test-token-000"
    service.process = MagicMock(returncode=None)  # 跑步

    assert (
        service.get_vscode_url()
        == "http://localhost:8001/?tkn=test-token-000&folder=workspace"
    )
    assert (
        service.get_vscode_url(base_url="http://example.com:9000")
        == "http://example.com:9000/?tkn=test-token-000&folder=workspace"
    )


def test_is_running_false(vscode_service):
    """无进程时测试is_running。"""
    assert not vscode_service.is_running()


def test_is_running_true(vscode_service):
    """使用活动进程测试 is_running。"""
    mock_process = MagicMock()
    mock_process.returncode = None
    vscode_service.process = mock_process

    assert vscode_service.is_running()


def test_is_running_finished_process(vscode_service):
    """使用已完成的流程测试 is_running。"""
    mock_process = MagicMock()
    mock_process.returncode = 0
    vscode_service.process = mock_process

    assert not vscode_service.is_running()


@pytest.mark.asyncio
async def test_start_vscode_process(vscode_service, tmp_path):
    """VSCode 进程测试开始。"""
    vscode_service.connection_token = "test-token"

    mock_process = AsyncMock()
    mock_process.stdout = AsyncMock()

    with (
        patch(
            "asyncio.create_subprocess_shell", return_value=mock_process
        ) as mock_create,
        patch.object(vscode_service, "_wait_for_startup") as mock_wait,
    ):
        await vscode_service._start_vscode_process()

        mock_create.assert_called_once()
        # 它自己的进程组，因此 stop() 可以向启动器发送信号给节点。
        assert mock_create.call_args.kwargs["start_new_session"] is True
        mock_wait.assert_called_once()
        assert vscode_service.process == mock_process


@pytest.mark.asyncio
async def test_start_vscode_process_with_server_base_path():
    """VSCode 正在启动 server_base_path 这个过程包含参数。"""
    service = VSCodeService(
        port=8001, connection_token="test-token", server_base_path="/runtime/vscode"
    )

    mock_process = AsyncMock()
    mock_process.stdout = AsyncMock()

    with (
        patch(
            "asyncio.create_subprocess_shell", return_value=mock_process
        ) as mock_create,
        patch.object(service, "_wait_for_startup"),
    ):
        await service._start_vscode_process()

        # 验证命令包含 --server-base-path
        cmd = mock_create.call_args[0][0]
        assert "--server-base-path /runtime/vscode" in cmd


@pytest.mark.asyncio
async def test_start_vscode_process_without_server_base_path():
    """测试开始 VSCode 翻译：翻译： server_base_path 排除了参数。"""
    service = VSCodeService(port=8001, connection_token="test-token")

    mock_process = AsyncMock()
    mock_process.stdout = AsyncMock()

    with (
        patch(
            "asyncio.create_subprocess_shell", return_value=mock_process
        ) as mock_create,
        patch.object(service, "_wait_for_startup"),
    ):
        await service._start_vscode_process()

        # 验证命令不包含 --server-base-path
        cmd = mock_create.call_args[0][0]
        assert "--server-base-path" not in cmd


@pytest.mark.asyncio
async def test_wait_for_startup_success(vscode_service):
    """测试等待 VSCode 启动，成功消息。"""
    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(
        side_effect=[
            b"Starting server...\n",
            b"Web UI available at http://localhost:8001\n",
            b"",
        ]
    )

    mock_process = AsyncMock()
    mock_process.stdout = mock_stdout
    mock_process.returncode = None
    vscode_service.process = mock_process

    await vscode_service._wait_for_startup()

    assert mock_stdout.readline.call_count >= 2


@pytest.mark.asyncio
async def test_wait_for_startup_timeout(vscode_service):
    """测试等待 VSCode 启动超时。"""
    mock_stdout = AsyncMock()
    # 模拟对象 readline 引发 TimeoutError 几次，然后返回空字节以打破循环
    #
    mock_stdout.readline = AsyncMock(side_effect=[TimeoutError(), TimeoutError(), b""])

    mock_process = AsyncMock()
    mock_process.stdout = mock_stdout
    mock_process.returncode = None
    vscode_service.process = mock_process

    # 不应引发异常，只需返回
    await vscode_service._wait_for_startup()


# 使用 enable_vscode 配置测试 get_vscode_service


def test_get_vscode_service_enabled(tmp_path):
    """当启用时，get_vscode_service 返回 VSCodeService。"""
    with (
        patch("openhands.agent_server.config.get_default_config") as mock_config,
        patch("openhands.agent_server.vscode_service._vscode_service", None),
    ):
        mock_config.return_value.enable_vscode = True
        mock_config.return_value.vscode_port = 8001
        mock_config.return_value.vscode_base_path = None
        mock_config.return_value.session_api_keys = []

        service = get_vscode_service()

        assert isinstance(service, VSCodeService)


def test_get_vscode_service_disabled():
    """禁用时，测试 get_vscode_service 返回 None。"""
    with (
        patch("openhands.agent_server.config.get_default_config") as mock_config,
        patch("openhands.agent_server.vscode_service._vscode_service", None),
    ):
        mock_config.return_value.enable_vscode = False

        service = get_vscode_service()

        assert service is None


def test_get_vscode_service_singleton():
    """测试 get_vscode_service 在多次调用中返回相同的实例。"""
    with (
        patch("openhands.agent_server.config.get_default_config") as mock_config,
        patch("openhands.agent_server.vscode_service._vscode_service", None),
    ):
        mock_config.return_value.enable_vscode = True
        mock_config.return_value.vscode_port = 8001
        mock_config.return_value.vscode_base_path = None
        mock_config.return_value.session_api_keys = []

        service1 = get_vscode_service()
        service2 = get_vscode_service()

        assert service1 is service2
        assert isinstance(service1, VSCodeService)


def test_get_vscode_service_with_custom_port():
    """测试 get_vscode_service 使用配置的端口。"""
    with (
        patch("openhands.agent_server.config.get_default_config") as mock_config,
        patch("openhands.agent_server.vscode_service._vscode_service", None),
    ):
        mock_config.return_value.enable_vscode = True
        mock_config.return_value.vscode_port = 9001
        mock_config.return_value.vscode_base_path = None
        mock_config.return_value.session_api_keys = []

        service = get_vscode_service()

        assert isinstance(service, VSCodeService)
        assert service.port == 9001


def test_get_vscode_service_with_base_path():
    """测试 get_vscode_service 通过了配置中的 vscode_base_path。"""
    with (
        patch("openhands.agent_server.config.get_default_config") as mock_config,
        patch("openhands.agent_server.vscode_service._vscode_service", None),
    ):
        mock_config.return_value.enable_vscode = True
        mock_config.return_value.vscode_port = 8001
        mock_config.return_value.vscode_base_path = "/runtime-123/vscode"
        mock_config.return_value.session_api_keys = []

        service = get_vscode_service()

        assert isinstance(service, VSCodeService)
        assert service.server_base_path == "/runtime-123/vscode"


def test_vscode_service_with_different_ports():
    """Test VSCode 服务初始化使用不同的端口。"""
    service1 = VSCodeService(port=8001)
    service2 = VSCodeService(port=9001)

    assert service1.port == 8001
    assert service2.port == 9001


def test_vscode_port_configuration():
    """测试 vscode_port 配置是否正确使用。"""
    import os

    from openhands.agent_server.config import Config, from_env

    # 测试默认值
    config = Config()
    assert config.vscode_port == 8001

    # Test 环境变量 override
    with patch.dict(os.environ, {"OH_VSCODE_PORT": "9999"}):
        config = from_env(Config, "OH")
        assert config.vscode_port == 9999


def test_vscode_base_path_configuration():
    """测试 vscode_base_path 配置是否正确使用。"""
    import os

    from openhands.agent_server.config import Config, from_env

    # 测试默认值为None
    config = Config()
    assert config.vscode_base_path is None

    # Test 环境变量 override
    with patch.dict(os.environ, {"OH_VSCODE_BASE_PATH": "/runtime-abc/vscode"}):
        config = from_env(Config, "OH")
        assert config.vscode_base_path == "/runtime-abc/vscode"
