"""测试 DockerWorkspace 导入和基本功能。"""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from pydantic import ValidationError

from openhands.workspace import (
    ApptainerWorkspace,
    DockerDevWorkspace,
    DockerWorkspace,
)


@pytest.fixture
def mock_docker_workspace():
    """测试夹具以最少的设置创建模拟的 DockerWorkspace。"""

    with patch("openhands.workspace.docker.workspace.execute_command") as mock_exec:
        # 模拟对象execute_command返回成功
        mock_exec.return_value = Mock(returncode=0, stdout="", stderr="")

        def _create_workspace(cleanup_image=False, network=None):
            # 创建工作区而不触发初始化
            with patch.object(DockerWorkspace, "_start_container"):
                workspace = DockerWorkspace(
                    server_image="test:latest",
                    cleanup_image=cleanup_image,
                    network=network,
                )

            # 手动设置通常在启动期间设置的状态
            workspace._container_id = "container_id_123"
            workspace._image_name = "test:latest"
            workspace._stop_logs = MagicMock()
            workspace._logs_thread = None

            return workspace, mock_exec

        yield _create_workspace


def test_docker_workspace_import():
    """测试是否可以从新包导入 DockerWorkspace。"""

    assert DockerWorkspace is not None
    assert hasattr(DockerWorkspace, "__init__")


def test_docker_workspace_inheritance():
    """测试 DockerWorkspace 是否继承自 RemoteWorkspace。"""
    from openhands.sdk.workspace import RemoteWorkspace

    assert issubclass(DockerWorkspace, RemoteWorkspace)


def test_docker_dev_workspace_import():
    """测试是否可以从新包导入 DockerDevWorkspace。"""

    assert DockerDevWorkspace is not None
    assert hasattr(DockerDevWorkspace, "__init__")


def test_docker_dev_workspace_inheritance():
    """测试 DockerDevWorkspace 是否继承自 DockerWorkspace。"""

    assert issubclass(DockerDevWorkspace, DockerWorkspace)


def test_docker_workspace_no_build_import():
    """DockerWorkspace 导入不应引入构建时依赖项。"""
    code = (
        "import importlib, sys\n"
        "importlib.import_module('openhands.workspace')\n"
        "print('1' if 'openhands.agent_server.docker.build' in sys.modules else '0')\n"
    )

    env = os.environ.copy()
    root = Path(__file__).resolve().parents[2]
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(root) if not pythonpath else f"{root}{os.pathsep}{pythonpath}"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        cwd=root,
    )
    assert result.stdout.strip() == "0"

    assert "server_image" in DockerWorkspace.model_fields
    assert "base_image" not in DockerWorkspace.model_fields


def test_docker_dev_workspace_has_build_fields():
    """测试 DockerDevWorkspace 是否同时具有 base_image 和 server_image 字段。"""

    # DockerDevWorkspace 应具有两个字段以提高灵活性
    assert "server_image" in DockerDevWorkspace.model_fields
    assert "base_image" in DockerDevWorkspace.model_fields
    assert "target" in DockerDevWorkspace.model_fields


def test_removed_mount_dir_input_fails_loudly():
    with pytest.raises(ValidationError, match="mount_dir has been removed"):
        DockerWorkspace.model_validate(
            {"server_image": "test:latest", "mount_dir": "/tmp/old"}
        )


def test_cleanup_without_image_deletion(mock_docker_workspace):
    """测试使用 cleanup_image=False 进行清理不会删除图像。"""
    workspace, mock_exec = mock_docker_workspace(cleanup_image=False)

    # 调用清理
    workspace.cleanup()

    # 验证 Docker rmi 被不调用
    calls = mock_exec.call_args_list
    rmi_calls = [c for c in calls if c[0] and "rmi" in str(c[0])]
    assert len(rmi_calls) == 0


def test_cleanup_with_image_deletion(mock_docker_workspace):
    """测试使用 cleanup_image=True 进行清理会删除 Docker 图像。"""
    workspace, mock_exec = mock_docker_workspace(cleanup_image=True)

    # 调用清理
    workspace.cleanup()

    # 验证 Docker rmi 是否使用正确的参数调用
    calls = mock_exec.call_args_list
    rmi_calls = [c for c in calls if c[0] and "rmi" in str(c[0])]
    assert len(rmi_calls) == 1

    # 验证命令包含 -f 标志和正确的映像名称
    rmi_call_args = rmi_calls[0][0][0]
    assert "docker" in rmi_call_args
    assert "rmi" in rmi_call_args
    assert "-f" in rmi_call_args
    assert "test:latest" in rmi_call_args


def test_docker_network(mock_docker_workspace):
    """测试指定 `network` 是否将值传递给 Docker。"""

    # 我们需要模拟对象 _start_container 在 Docker 运行之前和之后调用的东西
    with (
        patch(
            "openhands.workspace.docker.workspace.check_port_available",
            return_value=True,
        ),
        patch(
            "openhands.workspace.docker.workspace.find_available_tcp_port",
            return_value=8000,
        ),
        patch.object(DockerWorkspace, "_wait_for_health"),
    ):
        # 使用自定义网络名称
        network_name = "my-custom-network"
        workspace, mock_exec = mock_docker_workspace(network=network_name)

        # 清除 mock_exec 并确保 Docker 运行返回容器 ID
        mock_exec.reset_mock()
        mock_exec.return_value = Mock(returncode=0, stdout="container_123", stderr="")

        # 触发容器启动（通常在 model_post_init 中调用，但在测试夹具模拟对象中调用以允许
        # 手动测试）
        #
        workspace._start_container("test:latest", None)

        # 验证 Docker run 是通过 --network 调用的
        all_calls = [call[0][0] for call in mock_exec.call_args_list]
        run_cmd = next(cmd for cmd in all_calls if "run" in cmd)

        assert "--network" in run_cmd
        network_index = run_cmd.index("--network")
        assert run_cmd[network_index + 1] == network_name


def test_docker_workspace_publishes_ports_on_loopback(mock_docker_workspace):
    with (
        patch(
            "openhands.workspace.docker.workspace.check_port_available",
            return_value=True,
        ),
        patch.object(DockerWorkspace, "_wait_for_health"),
    ):
        with patch.object(DockerWorkspace, "_start_container"):
            workspace = DockerWorkspace(
                server_image="test:latest",
                host_port=8010,
                extra_ports=True,
                detach_logs=False,
            )
        workspace, mock_exec = workspace, mock_docker_workspace()[1]
        mock_exec.reset_mock()
        mock_exec.return_value = Mock(returncode=0, stdout="container_123", stderr="")

        workspace._start_container("test:latest", None)

        run_cmd = next(
            call[0][0] for call in mock_exec.call_args_list if "run" in call[0][0]
        )
        assert "127.0.0.1:8010:8000" in run_cmd
        assert "127.0.0.1:8011:8001" in run_cmd
        assert run_cmd[run_cmd.index("--host") + 1] == "0.0.0.0"


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, None),
        ({"SESSION_API_KEY": "legacy-key"}, "legacy-key"),
        ({"OH_SESSION_API_KEYS_0": "current-key"}, "current-key"),
        (
            {
                "SESSION_API_KEY": "legacy-key",
                "OH_SESSION_API_KEYS_0": "current-key",
            },
            "current-key",
        ),
    ],
)
def test_docker_workspace_uses_forwarded_session_key(
    mock_docker_workspace, monkeypatch, env, expected
):
    """客户端密钥必须与该容器中的服务器接受的密钥匹配。

    `forward_env` 转发两个变量，服务器解析V1
    `OH_SESSION_API_KEYS_0` 首先（V0 `SESSION_API_KEY` 只是一个回退方案），因此两者都
    设置后，工作区必须发送 V1 密钥，否
    则容器会拒绝它。
    """
    monkeypatch.delenv("SESSION_API_KEY", raising=False)
    monkeypatch.delenv("OH_SESSION_API_KEYS_0", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    with (
        patch(
            "openhands.workspace.docker.workspace.check_port_available",
            return_value=True,
        ),
        patch.object(DockerWorkspace, "_wait_for_health"),
    ):
        workspace, mock_exec = mock_docker_workspace()
        workspace.host_port = 8010
        workspace.detach_logs = False
        mock_exec.reset_mock()
        mock_exec.return_value = Mock(returncode=0, stdout="container_123", stderr="")

        workspace._start_container("test:latest", None)

    assert workspace.api_key == expected


# ===========================================================================
# health_check_timeout 测试 DockerWorkspace 和 ApptainerWorkspace
# ===========================================================================


@pytest.mark.parametrize("cls", [DockerWorkspace, ApptainerWorkspace])
def test_health_check_timeout_default(cls):
    """测试 health_check_timeout 默认为 120.0 秒。"""
    assert cls.model_fields["health_check_timeout"].default == 120.0


@pytest.mark.parametrize("cls", [DockerWorkspace, ApptainerWorkspace])
def test_health_check_timeout_rejects_non_positive(cls):
    """测试 health_check_timeout 拒绝零和负值。"""
    with pytest.raises(ValidationError, match="greater than 0"):
        # 尝试使用无效的超时创建 - 我们需要模拟对象启动
        with patch.object(cls, "model_post_init"):
            cls.model_validate(
                {"server_image": "test:latest", "health_check_timeout": 0}
            )

    with pytest.raises(ValidationError, match="greater than 0"):
        with patch.object(cls, "model_post_init"):
            cls.model_validate(
                {"server_image": "test:latest", "health_check_timeout": -10.0}
            )


def test_docker_workspace_startup_uses_health_check_timeout():
    """测试 _start_container 通过 health_check_timeout 到 _wait_for_health。"""
    with (
        patch(
            "openhands.workspace.docker.workspace.check_port_available",
            return_value=True,
        ),
        patch(
            "openhands.workspace.docker.workspace.find_available_tcp_port",
            return_value=8000,
        ),
        patch("openhands.workspace.docker.workspace.execute_command") as mock_exec,
        patch.object(DockerWorkspace, "_wait_for_health") as mock_wait,
        patch("openhands.workspace.docker.workspace.RemoteWorkspace.model_post_init"),
    ):
        mock_exec.return_value = Mock(returncode=0, stdout="container_123", stderr="")
        DockerWorkspace(server_image="test:latest", health_check_timeout=60.0)
        mock_wait.assert_called_once_with(timeout=60.0)


def test_docker_workspace_resume_uses_health_check_timeout():
    """测试 resume() 通过 health_check_timeout 到 _wait_for_health。"""
    with patch.object(DockerWorkspace, "_start_container"):
        with patch("openhands.workspace.docker.workspace.execute_command") as mock_exec:
            mock_exec.return_value = Mock(returncode=0, stdout="", stderr="")
            workspace = DockerWorkspace(
                server_image="test:latest", health_check_timeout=30.0
            )

    workspace._container_id = "container_id_123"

    with (
        patch("openhands.workspace.docker.workspace.execute_command") as mock_exec,
        patch.object(workspace, "_wait_for_health") as mock_wait,
    ):
        mock_exec.return_value = Mock(returncode=0, stdout="", stderr="")
        workspace.resume()
        mock_wait.assert_called_once_with(timeout=30.0)


def test_apptainer_workspace_startup_uses_health_check_timeout():
    """测试 model_post_init 通过 health_check_timeout 到 _wait_for_health。"""
    with (
        patch("openhands.workspace.apptainer.workspace.execute_command") as mock_exec,
        patch(
            "openhands.workspace.apptainer.workspace.check_port_available",
            return_value=True,
        ),
        patch(
            "openhands.workspace.apptainer.workspace.find_available_tcp_port",
            return_value=8000,
        ),
        patch.object(
            ApptainerWorkspace, "_prepare_sif_image", return_value="/fake/image.sif"
        ),
        patch.object(ApptainerWorkspace, "_start_container"),
        patch.object(ApptainerWorkspace, "_wait_for_health") as mock_wait,
        patch(
            "openhands.workspace.apptainer.workspace.RemoteWorkspace.model_post_init"
        ),
    ):
        mock_exec.return_value = Mock(returncode=0, stdout="", stderr="")
        ApptainerWorkspace(server_image="test:latest", health_check_timeout=45.0)
        mock_wait.assert_called_once_with(timeout=45.0)
