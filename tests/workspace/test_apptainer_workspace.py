"""测试 ApptainerWorkspace 导入和 GPU 直通行为。"""

from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def mock_apptainer_workspace(tmp_path):
    """测试夹具以最少的设置创建模拟的 ApptainerWorkspace。"""
    from openhands.workspace import ApptainerWorkspace

    sif_path = tmp_path / "test.sif"
    sif_path.write_text("fake sif")

    with (
        patch("openhands.workspace.apptainer.workspace.execute_command") as mock_exec,
        patch(
            "openhands.workspace.apptainer.workspace.check_port_available",
            return_value=True,
        ),
    ):
        mock_exec.return_value = Mock(returncode=0, stdout="", stderr="")

        def _create_workspace(
            *, enable_gpu: bool = False, extra_bind_mounts: list[str] | None = None
        ):
            with (
                patch.object(ApptainerWorkspace, "_start_container"),
                patch.object(ApptainerWorkspace, "_wait_for_health"),
            ):
                workspace = ApptainerWorkspace(
                    sif_file=str(sif_path),
                    host_port=8000,
                    detach_logs=False,
                    enable_gpu=enable_gpu,
                    extra_bind_mounts=extra_bind_mounts or [],
                )

            return workspace, mock_exec

        yield _create_workspace


def test_apptainer_workspace_import():
    """测试是否可以从包中导入 ApptainerWorkspace。"""
    from openhands.workspace import ApptainerWorkspace

    assert ApptainerWorkspace is not None
    assert hasattr(ApptainerWorkspace, "__init__")


def test_apptainer_workspace_inheritance():
    """测试 ApptainerWorkspace 是否继承自 RemoteWorkspace。"""
    from openhands.sdk.workspace import RemoteWorkspace
    from openhands.workspace import ApptainerWorkspace

    assert issubclass(ApptainerWorkspace, RemoteWorkspace)


def test_apptainer_workspace_has_gpu_field():
    """测试 ApptainerWorkspace 是否公开 GPU 直通选项。"""
    from openhands.workspace import ApptainerWorkspace

    assert "enable_gpu" in ApptainerWorkspace.model_fields


@pytest.mark.parametrize("enable_gpu", [False, True])
def test_apptainer_workspace_gpu_passthrough_flag(
    mock_apptainer_workspace, enable_gpu: bool
):
    """测试 GPU 直通是否切换 Apptainer --nv 标志。"""
    workspace, _ = mock_apptainer_workspace(enable_gpu=enable_gpu)

    fake_process = Mock(stdout=None)
    with patch(
        "openhands.workspace.apptainer.workspace.subprocess.Popen",
        return_value=fake_process,
    ) as mock_popen:
        workspace._start_container()

    run_cmd = mock_popen.call_args.args[0]

    assert run_cmd[:2] == ["apptainer", "run"]
    assert ("--nv" in run_cmd) is enable_gpu
    assert workspace._sif_path in run_cmd

    workspace._process = None
    workspace._instance_name = None


def test_apptainer_workspace_extra_bind_mounts(mock_apptainer_workspace, monkeypatch):
    """测试显式和环境提供的绑定安装是否达到 Apptainer。"""
    monkeypatch.setenv("OPENHANDS_APPTAINER_EXTRA_BINDS", "/env/src:/env/dst:ro")
    workspace, _ = mock_apptainer_workspace(
        extra_bind_mounts=["/host/tokenizer:/host/tokenizer:ro"]
    )

    fake_process = Mock(stdout=None)
    with patch(
        "openhands.workspace.apptainer.workspace.subprocess.Popen",
        return_value=fake_process,
    ) as mock_popen:
        workspace._start_container()

    run_cmd = mock_popen.call_args.args[0]

    assert "--bind" in run_cmd
    assert "/host/tokenizer:/host/tokenizer:ro" in run_cmd
    assert "/env/src:/env/dst:ro" in run_cmd

    workspace._process = None
    workspace._instance_name = None
