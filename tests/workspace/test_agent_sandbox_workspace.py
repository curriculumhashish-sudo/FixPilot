"""测试 AgentSandboxWorkspace（不需要集群）。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def test_agent_sandbox_workspace_import():
    """AgentSandboxWorkspace可以从包中导入。"""
    from openhands.workspace import AgentSandboxWorkspace

    assert AgentSandboxWorkspace is not None


def test_agent_sandbox_workspace_inheritance():
    """AgentSandboxWorkspace是RemoteWorkspace。"""
    from openhands.sdk.workspace import RemoteWorkspace
    from openhands.workspace import AgentSandboxWorkspace

    assert issubclass(AgentSandboxWorkspace, RemoteWorkspace)


def test_agent_sandbox_workspace_fields():
    """键智能体-沙盒旋钮作为字段公开。"""
    from openhands.workspace import AgentSandboxWorkspace

    for field in ("warmpool", "namespace", "server_port", "connection", "host_port"):
        assert field in AgentSandboxWorkspace.model_fields


def test_direct_connection_requires_host():
    """connection='direct' without a host is rejected before any k8s call."""
    from openhands.workspace import AgentSandboxWorkspace

    with pytest.raises(ValueError, match="requires 'host'"):
        AgentSandboxWorkspace(warmpool="pool", connection="direct")


@pytest.fixture
def k8s_mocks():
    """在测试期间安装假的 k8s_agent_sandbox 模块。"""
    fake_handle = MagicMock()
    fake_handle.sandbox_id = "sandbox-abc"
    fake_handle.claim_name = "sandbox-claim-abc"
    fake_handle.get_pod_name.return_value = "sandbox-abc-pod"

    fake_client = MagicMock()
    fake_client.create_sandbox.return_value = fake_handle

    fake_module = MagicMock()
    fake_module.SandboxClient.return_value = fake_client

    # `_patch_operating_mode` 与 `from k8s_agent_sandbox.constants import ...` 相同。
    fake_constants = MagicMock(
        SANDBOX_API_GROUP="agents.x-k8s.io",
        SANDBOX_API_VERSION="v1beta1",
        SANDBOX_PLURAL_NAME="sandboxes",
    )

    with patch.dict(
        "sys.modules",
        {
            "k8s_agent_sandbox": fake_module,
            "k8s_agent_sandbox.constants": fake_constants,
        },
    ):
        yield SimpleNamespace(client=fake_client, handle=fake_handle)


def _make_ws(**overrides):
    """用connection+parent init模拟的构建一个工作区out。"""
    from openhands.workspace import AgentSandboxWorkspace

    kwargs = {"warmpool": "openhands-pool", "detach_logs": False}
    kwargs.update(overrides)
    with (
        patch.object(AgentSandboxWorkspace, "_start_port_forward"),
        patch.object(AgentSandboxWorkspace, "_wait_for_health"),
        # RemoteWorkspace.model_post_init 将打开一个真实的 HTTP 客户端； 跳过它。
        patch(
            "openhands.sdk.workspace.remote.base.RemoteWorkspace.model_post_init",
            return_value=None,
        ),
    ):
        return AgentSandboxWorkspace(**kwargs)


def test_claims_from_warmpool_on_init(k8s_mocks):
    """model_post_init 从配置的热池中声明一个沙箱。"""
    _make_ws(namespace="ns1", shutdown_after_seconds=600)

    k8s_mocks.client.create_sandbox.assert_called_once()
    call = k8s_mocks.client.create_sandbox.call_args
    assert call.kwargs["warmpool"] == "openhands-pool"
    assert call.kwargs["namespace"] == "ns1"
    assert call.kwargs["shutdown_after_seconds"] == 600


def test_pause_and_resume_flip_operating_mode(k8s_mocks):
    """pause()/resume() 修补沙箱 operatingMode。"""
    ws = _make_ws()
    patch_call = (
        k8s_mocks.client.k8s_helper.custom_objects_api.patch_namespaced_custom_object
    )

    with patch.object(type(ws), "_stop_port_forward"):
        ws.pause()
    assert patch_call.call_args.kwargs["body"] == {
        "spec": {"operatingMode": "Suspended"}
    }

    with (
        patch.object(type(ws), "_start_port_forward"),
        patch.object(type(ws), "_wait_for_health"),
    ):
        ws.resume()
    assert patch_call.call_args.kwargs["body"] == {"spec": {"operatingMode": "Running"}}


def test_failed_connect_terminates_claim(k8s_mocks):
    """创建声明后的失败不得泄漏沙箱。"""
    from openhands.workspace import AgentSandboxWorkspace

    with (
        patch.object(
            AgentSandboxWorkspace,
            "_connect_port_forward_with_retry",
            side_effect=RuntimeError("boom"),
        ),
        patch.object(AgentSandboxWorkspace, "_stop_port_forward"),
        pytest.raises(RuntimeError, match="boom"),
    ):
        AgentSandboxWorkspace(warmpool="openhands-pool", detach_logs=False)

    k8s_mocks.handle.terminate.assert_called_once()


def test_resume_reconnects_on_a_fresh_port(k8s_mocks):
    """resume() 不得重复使用先前会话的本地端口。"""
    ws = _make_ws(host_port=45000)

    with (
        patch.object(type(ws), "_stop_port_forward"),
        patch.object(type(ws), "_connect_port_forward_with_retry") as connect,
        patch.object(type(ws), "reset_client"),
    ):
        ws.resume()

    assert connect.call_args.kwargs["preferred_port"] is None


def test_exit_preserves_parent_lifecycle_and_cleanup(k8s_mocks):
    """上下文退出委托给 RemoteWorkspace 并始终进行清理。"""
    from openhands.sdk.workspace import RemoteWorkspace

    ws = _make_ws()
    error = RuntimeError("callback failed")

    with (
        patch.object(RemoteWorkspace, "__exit__", side_effect=error) as parent_exit,
        patch.object(type(ws), "cleanup") as cleanup,
        pytest.raises(RuntimeError, match="callback failed"),
    ):
        ws.__exit__(RuntimeError, error, None)

    parent_exit.assert_called_once_with(RuntimeError, error, None)
    cleanup.assert_called_once()


def test_cleanup_terminates_sandbox(k8s_mocks):
    """cleanup() 通过句柄删除声明并且是幂等的。"""
    ws = _make_ws()

    with patch.object(type(ws), "_stop_port_forward"):
        ws.cleanup()
        ws.cleanup()  # 第二次调用是空操作

    k8s_mocks.handle.terminate.assert_called_once()
