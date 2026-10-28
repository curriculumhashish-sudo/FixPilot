"""测试 workspaces_router 端点。

工作区已持久化在智能体-服务器（workspace/.openhands/workspaces.json）上替换之前的浏览
器本地 Zustand 存储，这样连接到同一服务器
的所有客户端都会看到相同的列表。 这些测试涵盖 GUI 消耗的 HTTP 表面以及其下方的文件锁
定持久化。
"""

import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config
from openhands.agent_server.persistence import reset_stores


@pytest.fixture
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        reset_stores()
        monkeypatch.setenv("OH_PERSISTENCE_DIR", str(Path(tmpdir) / "persist"))
        config = Config(static_files_path=None, session_api_keys=[], secret_key=None)
        app = create_app(config)
        yield TestClient(app)
        reset_stores()


@pytest.fixture
def client_with_auth(monkeypatch):
    """与 ``client`` 相同，但配置了 ``session_api_keys``，因此
    ``/api`` 仅标头身份验证依赖项处于活动状态。 用于证明工作区路由器继承了与 ``/api``
     的 REST 相同的身份验证。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        reset_stores()
        monkeypatch.setenv("OH_PERSISTENCE_DIR", str(Path(tmpdir) / "persist"))
        config = Config(
            static_files_path=None,
            session_api_keys=["test-key-123"],
            secret_key=None,
        )
        app = create_app(config)
        yield TestClient(app, raise_server_exceptions=False)
        reset_stores()


def test_list_workspaces_empty_when_no_file(client):
    # 法案
    response = client.get("/api/workspaces")

    # 断言
    assert response.status_code == 200
    assert response.json() == {"workspaces": [], "workspaceParents": []}


def test_add_workspaces_persists_camelcase_parent_path_and_dedupes_by_path(client):
    # 安排
    payload = {
        "workspaces": [
            {"id": "/a", "name": "a", "path": "/a"},
            {
                "id": "/b",
                "name": "b",
                "path": "/b",
                "parentPath": "/parents/root",
            },
        ]
    }

    # 做法：先添加种子列表； 第二个具有重叠路径的添加是无操作
    first = client.post("/api/workspaces", json=payload)
    second = client.post(
        "/api/workspaces",
        json={"workspaces": [{"id": "/a", "name": "a", "path": "/a"}]},
    )
    listed = client.get("/api/workspaces")

    # 断言
    assert first.status_code == 200
    assert second.status_code == 200
    assert listed.status_code == 200
    body = listed.json()
    assert [w["path"] for w in body["workspaces"]] == ["/a", "/b"]
    # camelCase 线路格式保留 — TS LocalWorkspace 形状不变。
    assert body["workspaces"][1]["parentPath"] == "/parents/root"


def test_delete_workspace_returns_404_when_path_absent(client):
    # 安排
    client.post(
        "/api/workspaces",
        json={"workspaces": [{"id": "/a", "name": "a", "path": "/a"}]},
    )

    # 法案
    removed_present = client.delete("/api/workspaces", params={"path": "/a"})
    removed_missing = client.delete("/api/workspaces", params={"path": "/nope"})
    remaining = client.get("/api/workspaces").json()

    # 断言
    assert removed_present.status_code == 200
    assert removed_present.json() == {"deleted": True}
    assert removed_missing.status_code == 404
    assert remaining["workspaces"] == []


def test_workspace_parents_add_and_remove_independent_of_workspaces(client):
    # 安排：种子一工作区和一位父母，这样我们就可以证明他们没有
    # 独立突变时发生碰撞。
    client.post(
        "/api/workspaces",
        json={"workspaces": [{"id": "/w", "name": "w", "path": "/w"}]},
    )

    # 法案
    added = client.post(
        "/api/workspaces/parents",
        json={"parents": [{"id": "/p", "name": "p", "path": "/p"}]},
    )
    after_add = client.get("/api/workspaces").json()
    removed = client.delete("/api/workspaces/parents", params={"path": "/p"})
    missing = client.delete("/api/workspaces/parents", params={"path": "/p"})
    after_remove = client.get("/api/workspaces").json()

    # 断言
    assert added.status_code == 200
    assert [p["path"] for p in after_add["workspaceParents"]] == ["/p"]
    assert [w["path"] for w in after_add["workspaces"]] == ["/w"]
    assert removed.status_code == 200
    assert missing.status_code == 404
    assert after_remove["workspaceParents"] == []
    # 工作区在父级被移除后仍然存在。
    assert [w["path"] for w in after_remove["workspaces"]] == ["/w"]


def test_workspaces_survive_across_requests_via_disk_persistence(client):
    # 整理：写一些东西
    client.post(
        "/api/workspaces",
        json={"workspaces": [{"id": "/keep", "name": "keep", "path": "/keep"}]},
    )

    # 行动：确认它在磁盘上，然后重置内存中的单例（模拟
    # 服务器重新启动）并重新读取。
    persist_dir = Path(os.environ["OH_PERSISTENCE_DIR"])
    assert (persist_dir / "workspaces.json").exists()

    reset_stores()
    listed_again = client.get("/api/workspaces").json()

    # 断言
    assert [w["path"] for w in listed_again["workspaces"]] == ["/keep"]


def test_add_workspaces_dedupes_duplicate_paths_within_single_payload(client):
    """具有相同 ``path`` 两次的单个 POST 主体必须仅持久化一次。

    回归用于仅根据预先存在的列表计算重复数据删除集的情况，因此传入载荷内的重复项会被
    漏掉。
    """
    # 安排
    payload = {
        "workspaces": [
            {"id": "first", "name": "first", "path": "/dup"},
            {"id": "second", "name": "second", "path": "/dup"},
        ]
    }

    # 法案
    response = client.post("/api/workspaces", json=payload)
    listed = client.get("/api/workspaces")

    # 断言
    assert response.status_code == 200
    body = listed.json()
    assert [w["path"] for w in body["workspaces"]] == ["/dup"]
    # 第一次出现获胜。
    assert body["workspaces"][0]["id"] == "first"


def test_add_workspace_parents_dedupes_duplicate_paths_within_single_payload(client):
    """``/parents`` 端点的重复数据删除合同相同。"""
    # 安排
    payload = {
        "parents": [
            {"id": "first", "name": "first", "path": "/p"},
            {"id": "second", "name": "second", "path": "/p"},
        ]
    }

    # 法案
    response = client.post("/api/workspaces/parents", json=payload)
    listed = client.get("/api/workspaces")

    # 断言
    assert response.status_code == 200
    body = listed.json()
    assert [p["path"] for p in body["workspaceParents"]] == ["/p"]
    assert body["workspaceParents"][0]["id"] == "first"


def test_workspace_with_id_equal_to_long_path_is_accepted(client):
    """GUI发送``id == path``； 比旧的 512 字符更长的路径
    ``id`` cap 现在仍必须验证 cap 是否匹配 ``path`` (4096)。 涵盖``WorkspaceItem``和
    ``WorkspaceParentItem``。
    """
    # 安排：1024 个字符的路径 — 轻松超过旧的 512 字符上限，很好
    # 低于与 ``path`` 共享的 4096 上限。
    long_path = "/" + ("a" * 1023)

    # 法案
    add_workspace = client.post(
        "/api/workspaces",
        json={"workspaces": [{"id": long_path, "name": "deep", "path": long_path}]},
    )
    add_parent = client.post(
        "/api/workspaces/parents",
        json={"parents": [{"id": long_path, "name": "deep", "path": long_path}]},
    )
    listed = client.get("/api/workspaces").json()

    # 断言
    assert add_workspace.status_code == 200, add_workspace.text
    assert add_parent.status_code == 200, add_parent.text
    assert [w["path"] for w in listed["workspaces"]] == [long_path]
    assert [p["path"] for p in listed["workspaceParents"]] == [long_path]
    assert listed["workspaces"][0]["id"] == long_path


def test_unset_parent_path_is_omitted_from_response_and_on_disk_json(client):
    """没有 ``parentPath`` 的工作区必须序列化作为缺席键，
    不是``"parentPath": null``。

    线路格式和 ``workspaces.json`` 都必须与 GUI 匹配
    ``LocalWorkspace.parentPath?: string`` 形状 — 发射 ``null`` 违反合同并破坏严格的
    TS 客户端。
    """
    # 安排
    client.post(
        "/api/workspaces",
        json={
            "workspaces": [
                {"id": "/no-parent", "name": "no-parent", "path": "/no-parent"},
                {
                    "id": "/has-parent",
                    "name": "has-parent",
                    "path": "/has-parent",
                    "parentPath": "/parents/root",
                },
            ]
        },
    )

    # 法案
    listed = client.get("/api/workspaces").json()
    on_disk_path = Path(os.environ["OH_PERSISTENCE_DIR"]) / "workspaces.json"
    on_disk = json.loads(on_disk_path.read_text(encoding="utf-8"))

    # 断言：有线格式
    no_parent_wire = next(w for w in listed["workspaces"] if w["path"] == "/no-parent")
    has_parent_wire = next(
        w for w in listed["workspaces"] if w["path"] == "/has-parent"
    )
    assert "parentPath" not in no_parent_wire
    assert has_parent_wire["parentPath"] == "/parents/root"

    # 断言：磁盘格式反映了线的形状。
    no_parent_disk = next(w for w in on_disk["workspaces"] if w["path"] == "/no-parent")
    has_parent_disk = next(
        w for w in on_disk["workspaces"] if w["path"] == "/has-parent"
    )
    assert "parentPath" not in no_parent_disk
    assert has_parent_disk["parentPath"] == "/parents/root"


def test_list_workspaces_returns_409_when_persisted_file_is_corrupted(client):
    """损坏的 ``workspaces.json`` 必须将不默默地屏蔽为空。

    在损坏时返回空列表将使后续的 POST 用默认值覆盖仍在磁盘上（可能可恢复）的数据。
    """
    # 安排：播种真实的工作区，然后用垃圾破坏文件。
    client.post(
        "/api/workspaces",
        json={"workspaces": [{"id": "/a", "name": "a", "path": "/a"}]},
    )
    persist_dir = Path(os.environ["OH_PERSISTENCE_DIR"])
    (persist_dir / "workspaces.json").write_text("{not valid json", encoding="utf-8")
    # 强制下一个请求从磁盘而不是内存中重新读取。
    reset_stores()

    # 法案
    response = client.get("/api/workspaces")

    # 断言
    assert response.status_code == 409
    assert "corrupt" in response.json()["detail"].lower()


# ── 认证──────────────────────────────────────────────────────────────────
#
# /api 路由器在以下情况下应用仅标头 ``X-Session-API-Key`` 依赖项：
# ``session_api_keys``已配置。 这些测试证明工作区路由器继承了该门 — i.e。 未经身份验证的
# 客户端无法读取或改变服务器端工作区状态。
#


def test_workspaces_endpoints_require_session_api_key_when_configured(
    client_with_auth,
):
    # 行为：击中每个状态改变的端点加GET，不带标题。
    no_header_get = client_with_auth.get("/api/workspaces")
    no_header_post = client_with_auth.post(
        "/api/workspaces",
        json={"workspaces": [{"id": "/a", "name": "a", "path": "/a"}]},
    )
    no_header_delete = client_with_auth.delete("/api/workspaces", params={"path": "/a"})
    no_header_parents_post = client_with_auth.post(
        "/api/workspaces/parents",
        json={"parents": [{"id": "/p", "name": "p", "path": "/p"}]},
    )
    no_header_parents_delete = client_with_auth.delete(
        "/api/workspaces/parents", params={"path": "/p"}
    )
    bad_header = client_with_auth.get(
        "/api/workspaces", headers={"X-Session-API-Key": "wrong-key"}
    )

    # 断言
    assert no_header_get.status_code == 401
    assert no_header_post.status_code == 401
    assert no_header_delete.status_code == 401
    assert no_header_parents_post.status_code == 401
    assert no_header_parents_delete.status_code == 401
    assert bad_header.status_code == 401


def test_workspaces_endpoints_accept_valid_session_api_key(client_with_auth):
    """有效的 ``X-Session-API-Key`` 可以让相同的端点正常服务。"""
    # 安排
    headers = {"X-Session-API-Key": "test-key-123"}

    # 法案
    listed = client_with_auth.get("/api/workspaces", headers=headers)
    added = client_with_auth.post(
        "/api/workspaces",
        headers=headers,
        json={"workspaces": [{"id": "/a", "name": "a", "path": "/a"}]},
    )
    deleted = client_with_auth.delete(
        "/api/workspaces", headers=headers, params={"path": "/a"}
    )

    # 断言
    assert listed.status_code == 200
    assert added.status_code == 200
    assert deleted.status_code == 200


def test_refused_deletes_on_fresh_directory_create_no_workspaces_file(client):
    # 安排
    persist_dir = Path(os.environ["OH_PERSISTENCE_DIR"])

    # 法案
    workspace = client.delete("/api/workspaces", params={"path": "/never"})
    parent = client.delete("/api/workspaces/parents", params={"path": "/never"})

    # 断言：两者都是404，并且像读、写没有注册表文件一样。
    assert workspace.status_code == 404
    assert workspace.json()["detail"] == "Workspace not found"
    assert parent.status_code == 404
    assert parent.json()["detail"] == "Workspace parent not found"
    assert not (persist_dir / "workspaces.json").exists()


def test_noop_writes_do_not_save_and_keep_their_answer(client, monkeypatch):
    # 安排：种子一工作区和一个父级，然后使每次保存失败，
    # 代表服务器无法写入的存储。
    from openhands.agent_server.persistence.store import FileWorkspacesStore

    workspace = {"id": "/a", "name": "a", "path": "/a"}
    parent = {"id": "/p", "name": "p", "path": "/p"}
    assert client.post("/api/workspaces", json={"workspaces": [workspace]}).is_success
    assert client.post("/api/workspaces/parents", json={"parents": [parent]}).is_success
    ws_file = Path(os.environ["OH_PERSISTENCE_DIR"]) / "workspaces.json"
    stamp = (ws_file.stat().st_ino, ws_file.stat().st_mtime_ns)

    def failing_save(self, workspaces):
        raise OSError("read-only file system")

    monkeypatch.setattr(FileWorkspacesStore, "save", failing_save)

    # 法案
    readd = client.post("/api/workspaces", json={"workspaces": [workspace]})
    readd_parent = client.post("/api/workspaces/parents", json={"parents": [parent]})
    delete_unknown = client.delete("/api/workspaces", params={"path": "/never"})
    delete_unknown_parent = client.delete(
        "/api/workspaces/parents", params={"path": "/never"}
    )
    real_add = client.post(
        "/api/workspaces",
        json={"workspaces": [{"id": "/b", "name": "b", "path": "/b"}]},
    )

    # 断言：只有真正的改变才尝试写入。
    assert readd.status_code == 200
    assert [w["path"] for w in readd.json()["workspaces"]] == ["/a"]
    assert readd_parent.status_code == 200
    assert [p["path"] for p in readd_parent.json()["workspaceParents"]] == ["/p"]
    assert delete_unknown.status_code == 404
    assert delete_unknown_parent.status_code == 404
    assert real_add.status_code == 500
    assert "Failed to save workspaces" in real_add.json()["exception"]
    assert (ws_file.stat().st_ino, ws_file.stat().st_mtime_ns) == stamp
