"""测试 LocalWorkspace 自动化完成回调行为。"""

from unittest.mock import MagicMock, patch

from openhands.sdk.workspace import LocalWorkspace


def test_context_exit_sends_registered_cost_in_completion_callback(
    tmp_path, monkeypatch
):
    """留下工作区上下文报告注册成本，因此本地
    运行自动化的计费方式与远程自动化的计费方式相同。"""
    monkeypatch.setenv("AUTOMATION_CALLBACK_URL", "https://svc.test/complete")
    workspace = LocalWorkspace(working_dir=str(tmp_path))
    workspace.register_cost(0.4213)

    with patch("httpx.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_client

        with workspace:
            pass

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["cost"] == 0.4213


def test_context_exit_sends_nothing_without_callback_url(tmp_path, monkeypatch):
    """普通本地使用保持离线：未配置自动化回调，
    所以离开上下文一定不能到达网络。"""
    monkeypatch.delenv("AUTOMATION_CALLBACK_URL", raising=False)
    workspace = LocalWorkspace(working_dir=str(tmp_path))
    workspace.register_cost(0.4213)

    with patch("httpx.Client") as MockClient:
        with workspace:
            pass

        assert MockClient.call_count == 0
