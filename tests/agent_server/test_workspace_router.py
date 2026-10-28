"""测试 workspace_router.py – 会话工作区静态服务器。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.dependencies import get_conversation_service
from openhands.agent_server.event_service import EventService
from openhands.agent_server.workspace_router import (
    conversation_workspace_url_path,
    workspace_router,
)
from openhands.sdk.workspace import LocalWorkspace


@pytest.fixture
def client_factory(tmp_path):
    """构建一个 TestClient，其会话服务指向 ``tmp_path``。"""

    def _build(
        *,
        conversation_id: UUID,
        workspace_dir=None,
    ) -> TestClient:
        app = FastAPI()
        app.include_router(workspace_router, prefix="/api")

        ws = workspace_dir if workspace_dir is not None else tmp_path
        event_service = AsyncMock(spec=EventService)
        event_service.stored = SimpleNamespace(
            workspace=LocalWorkspace(working_dir=str(ws))
        )

        conversation_service = AsyncMock(spec=ConversationService)

        async def _get_event_service(cid: UUID):
            if cid == conversation_id:
                return event_service
            return None

        conversation_service.get_event_service.side_effect = _get_event_service
        app.dependency_overrides[get_conversation_service] = (
            lambda: conversation_service
        )
        return TestClient(app, raise_server_exceptions=False)

    return _build


def test_url_path_helper_includes_conversation_id():
    cid = uuid4()
    assert conversation_workspace_url_path(cid) == (
        f"/api/conversations/{cid}/workspace/"
    )


def test_serve_file_at_workspace_root(client_factory, tmp_path):
    cid = uuid4()
    (tmp_path / "hello.txt").write_text("hi from workspace")
    client = client_factory(conversation_id=cid)

    resp = client.get(f"/api/conversations/{cid}/workspace/hello.txt")

    assert resp.status_code == 200
    assert resp.text == "hi from workspace"


def test_serve_file_in_subdirectory_with_inferred_content_type(
    client_factory, tmp_path
):
    cid = uuid4()
    nested = tmp_path / "reports"
    nested.mkdir()
    (nested / "report.html").write_text("<h1>ok</h1>")
    client = client_factory(conversation_id=cid)

    resp = client.get(f"/api/conversations/{cid}/workspace/reports/report.html")

    assert resp.status_code == 200
    assert resp.text == "<h1>ok</h1>"
    assert resp.headers["content-type"].startswith("text/html")


def test_root_serves_index_html_when_present(client_factory, tmp_path):
    cid = uuid4()
    (tmp_path / "index.html").write_text("<title>root</title>")
    client = client_factory(conversation_id=cid)

    resp_no_slash = client.get(
        f"/api/conversations/{cid}/workspace", follow_redirects=False
    )
    # FastAPI 的默认 redirect_slashes 点击了没有尾随斜杠的形式，但我们的端点没有尾随斜杠
    # ，所以应该直接命中路由。
    #
    assert resp_no_slash.status_code == 200
    assert resp_no_slash.text == "<title>root</title>"


def test_directory_serves_index_html(client_factory, tmp_path):
    cid = uuid4()
    sub = tmp_path / "site"
    sub.mkdir()
    (sub / "index.html").write_text("<title>sub</title>")
    client = client_factory(conversation_id=cid)

    resp = client.get(f"/api/conversations/{cid}/workspace/site/")
    assert resp.status_code == 200
    assert resp.text == "<title>sub</title>"


def test_directory_without_index_returns_404(client_factory, tmp_path):
    cid = uuid4()
    (tmp_path / "site").mkdir()
    client = client_factory(conversation_id=cid)

    resp = client.get(f"/api/conversations/{cid}/workspace/site/")
    assert resp.status_code == 404


def test_missing_file_returns_404(client_factory, tmp_path):
    cid = uuid4()
    client = client_factory(conversation_id=cid)

    resp = client.get(f"/api/conversations/{cid}/workspace/missing.txt")
    assert resp.status_code == 404


def test_path_traversal_is_rejected(client_factory, tmp_path):
    cid = uuid4()
    # 将同级文件放置在工作区目录之外
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret")

    workspace = tmp_path / "ws"
    workspace.mkdir()
    client = client_factory(conversation_id=cid, workspace_dir=workspace)

    # ``../outside.txt`` 将转义工作区根。
    resp = client.get(
        f"/api/conversations/{cid}/workspace/../outside.txt",
        # 在发送之前不要让测试客户端标准化“..”。
        follow_redirects=False,
    )
    # 要么 URL 永远不会到达我们的处理程序（Starlette/HTTPX 可能会删除“..”段），要么我们
    # 的处理程序明确拒绝它。 这两种结果都意味着机密文件* 未* 被送达。
    #
    assert resp.status_code in {400, 404}
    assert "secret" not in resp.text


def test_unknown_conversation_returns_404(client_factory, tmp_path):
    cid = uuid4()
    other = uuid4()
    client = client_factory(conversation_id=cid)

    resp = client.get(f"/api/conversations/{other}/workspace/anything.txt")
    assert resp.status_code == 404


def test_symlink_pointing_outside_workspace_is_rejected(client_factory, tmp_path):
    """不得提供目标位于工作区之外的符号链接。"""
    cid = uuid4()
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("secret data")

    workspace = tmp_path / "ws"
    workspace.mkdir()
    symlink = workspace / "link"
    symlink.symlink_to(outside)

    client = client_factory(conversation_id=cid, workspace_dir=workspace)

    resp = client.get(f"/api/conversations/{cid}/workspace/link")

    # ``resolve()`` 遵循符号链接，因此解析的路径位于工作区根之外，并且处理程序拒绝它。
    #
    assert resp.status_code == 400
    assert "secret data" not in resp.text


def test_symlink_pointing_inside_workspace_is_served(client_factory, tmp_path):
    """仍提供目标位于工作区内的符号链接。"""
    cid = uuid4()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "real.txt"
    target.write_text("hello via symlink")
    link = workspace / "alias.txt"
    link.symlink_to(target)

    client = client_factory(conversation_id=cid, workspace_dir=workspace)

    resp = client.get(f"/api/conversations/{cid}/workspace/alias.txt")
    assert resp.status_code == 200
    assert resp.text == "hello via symlink"


def test_non_local_workspace_returns_404(tmp_path):
    """无法提供由非本地工作区支持的对话。"""
    from openhands.sdk.workspace.remote.base import RemoteWorkspace

    cid = uuid4()
    app = FastAPI()
    app.include_router(workspace_router, prefix="/api")

    event_service = AsyncMock(spec=EventService)
    event_service.stored = SimpleNamespace(
        workspace=RemoteWorkspace(
            host="https://example.invalid", working_dir="/workspace"
        )
    )
    conversation_service = AsyncMock(spec=ConversationService)

    async def _get_event_service(found_cid: UUID):
        return event_service if found_cid == cid else None

    conversation_service.get_event_service.side_effect = _get_event_service
    app.dependency_overrides[get_conversation_service] = lambda: conversation_service
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get(f"/api/conversations/{cid}/workspace/anything.txt")

    assert resp.status_code == 404
    assert "not local" in resp.json()["detail"].lower()
