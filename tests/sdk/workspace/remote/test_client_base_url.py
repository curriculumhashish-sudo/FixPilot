"""测试客户端 base_url 配置（问题 #800）。

验证RemoteWorkspace和AsyncRemoteWorkspace创建了带有base_url的httpx客户端，并解决了
UnsupportedProtocol错误
，使用相对URLs。
"""

import httpx

from openhands.sdk.workspace.remote.async_remote_workspace import (
    AsyncRemoteWorkspace,
)
from openhands.sdk.workspace.remote.base import RemoteWorkspace


def test_remote_workspace_client_has_base_url():
    """测试 RemoteWorkspace 创建带有 base_url 设置的客户端。"""
    workspace = RemoteWorkspace(host="http://localhost:8000", working_dir="/workspace")
    client = workspace.client

    assert isinstance(client, httpx.Client)
    assert client.base_url is not None
    assert str(client.base_url) == "http://localhost:8000"


def test_async_remote_workspace_client_has_base_url():
    """测试 AsyncRemoteWorkspace 创建带有 base_url 设置的客户端。"""
    workspace = AsyncRemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace"
    )
    client = workspace.client

    assert isinstance(client, httpx.AsyncClient)
    assert client.base_url is not None
    assert str(client.base_url) == "http://localhost:8000"
