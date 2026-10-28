"""测试已安装的画布扩展管理路由器 (canvas_extensions_router)。

通过 TestClient 驱动端点到临时安装存储（默认安装目录被重定向），因此没有任何内容触及
真实的
~/.openhands.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openhands.agent_server.canvas_extensions.bridge import AppBackendSessionStore
from openhands.agent_server.canvas_extensions.manifest import MANIFEST_FILENAME
from openhands.agent_server.canvas_extensions_router import canvas_extensions_router

from .canvas_extensions.conftest import write_extension


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    """A TestClient，其安装存储是一个独立的临时目录。"""
    store = tmp_path / "installed-store"
    monkeypatch.setattr(
        "openhands.agent_server.canvas_extensions.installed."
        "get_installed_canvas_extensions_dir",
        lambda: store,
    )
    app = FastAPI()
    app.include_router(canvas_extensions_router)
    return TestClient(app)


def test_install_lands_disabled_then_get_by_name(client: TestClient, tmp_path: Path):
    src = write_extension(tmp_path / "src" / "demo-extension", name="demo-extension")

    install = client.post("/canvas-extensions/install", json={"source": str(src)})

    assert install.status_code == 200
    assert install.json()["name"] == "demo-extension"
    assert install.json()["enabled"] is False

    got = client.get("/canvas-extensions/installed/demo-extension")
    assert got.status_code == 200
    assert got.json()["name"] == "demo-extension"
    assert got.json()["enabled"] is False


def test_get_includes_manifest_page_contributions(client: TestClient, tmp_path: Path):
    src = write_extension(
        tmp_path / "src" / "demo-extension",
        name="demo-extension",
        display_name="Demo Extension",
        pages=[
            {"id": "dashboard", "title": "Dashboard", "path": "/dashboard"},
            {"id": "reports", "title": "Reports", "path": "/reports"},
        ],
    )
    client.post("/canvas-extensions/install", json={"source": str(src)})

    resp = client.get("/canvas-extensions/installed/demo-extension")

    assert resp.status_code == 200
    manifest = resp.json()["manifest"]
    assert manifest["display_name"] == "Demo Extension"
    assert manifest["contributes"]["pages"] == [
        {"id": "dashboard", "title": "Dashboard", "path": "/dashboard"},
        {"id": "reports", "title": "Reports", "path": "/reports"},
    ]


def test_list_includes_manifest_page_contributions(client: TestClient, tmp_path: Path):
    src = write_extension(
        tmp_path / "src" / "demo-extension",
        name="demo-extension",
        display_name="Demo Extension",
        pages=[
            {"id": "dashboard", "title": "Dashboard", "path": "/dashboard"},
            {"id": "reports", "title": "Reports", "path": "/reports"},
        ],
    )
    client.post("/canvas-extensions/install", json={"source": str(src)})

    resp = client.get("/canvas-extensions/installed")

    assert resp.status_code == 200
    [ext] = resp.json()["canvas_extensions"]
    assert ext["manifest"]["display_name"] == "Demo Extension"
    assert [p["id"] for p in ext["manifest"]["contributes"]["pages"]] == [
        "dashboard",
        "reports",
    ]


def test_unreadable_manifest_after_install_yields_null_manifest(
    client: TestClient, tmp_path: Path
):
    """其存储的清单不再解析的跟踪扩展必须保留
    使用 ``manifest: null`` 可见——不会破坏端点——因此仍然可以通过 API 禁用或卸载它。
    """
    src = write_extension(tmp_path / "src" / "demo-extension", name="demo-extension")
    install = client.post("/canvas-extensions/install", json={"source": str(src)})
    install_path = Path(install.json()["install_path"])
    (install_path / "canvas-extension.json").write_text("{not json")

    got = client.get("/canvas-extensions/installed/demo-extension")
    listed = client.get("/canvas-extensions/installed")

    assert got.status_code == 200
    assert got.json()["manifest"] is None
    assert [e["manifest"] for e in listed.json()["canvas_extensions"]] == [None]


def test_install_reports_requested_ref(client: TestClient, tmp_path: Path):
    src = write_extension(tmp_path / "src" / "demo-extension", name="demo-extension")

    with patch(
        "openhands.sdk.extensions.installation.manager.fetch_with_resolution",
        return_value=(src, "sha-v1"),
    ):
        install = client.post(
            "/canvas-extensions/install",
            json={"source": "github:org/repo", "ref": "v1"},
        )

    assert install.status_code == 200
    assert install.json()["requested_ref"] == "v1"
    assert install.json()["resolved_ref"] == "sha-v1"
    got = client.get("/canvas-extensions/installed/demo-extension")
    assert got.json()["requested_ref"] == "v1"


def test_patch_toggles_enabled_state(client: TestClient, tmp_path: Path):
    src = write_extension(tmp_path / "src" / "demo-extension", name="demo-extension")
    client.post("/canvas-extensions/install", json={"source": str(src)})

    enabled = client.patch(
        "/canvas-extensions/installed/demo-extension", json={"enabled": True}
    )
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
    assert (
        client.get("/canvas-extensions/installed/demo-extension").json()["enabled"]
        is True
    )

    disabled = client.patch(
        "/canvas-extensions/installed/demo-extension", json={"enabled": False}
    )
    assert disabled.json()["enabled"] is False


@pytest.fixture
def client_with_sessions(tmp_path: Path, monkeypatch) -> tuple[TestClient, object]:
    """附加了应用程序范围的会话存储的 TestClient。"""
    store = tmp_path / "installed-store"
    monkeypatch.setattr(
        "openhands.agent_server.canvas_extensions.installed."
        "get_installed_canvas_extensions_dir",
        lambda: store,
    )
    app = FastAPI()
    app.include_router(canvas_extensions_router)
    sessions = AppBackendSessionStore()
    app.state.app_backend_session_store = sessions
    return TestClient(app), sessions


@pytest.mark.parametrize("revision_route", ["disabled", "uninstalled", "stopped"])
def test_disable_uninstall_and_stop_revoke_app_sessions(
    client_with_sessions, tmp_path: Path, revision_route: str
):
    """一旦应用程序被拆除，实时应用程序 cookie 必须停止授权。

    回归测试：这些处理程序过去直接调用`stop()`，留下
    `revoke_app`（也取消附加的 WebSocket 桥）作为死代码。
    """
    import asyncio

    client, sessions = client_with_sessions
    src = write_extension(tmp_path / "src" / "demo-extension", name="demo-extension")
    client.post("/canvas-extensions/install", json={"source": str(src)})

    endpoint = ("127.0.0.1", 4321)
    token, _ = asyncio.run(sessions.create("demo-extension", endpoint))
    assert asyncio.run(sessions.authorize(token, "demo-extension", endpoint))

    if revision_route == "disabled":
        response = client.patch(
            "/canvas-extensions/installed/demo-extension", json={"enabled": False}
        )
    elif revision_route == "uninstalled":
        response = client.delete("/canvas-extensions/installed/demo-extension")
    else:
        response = client.post(
            "/canvas-extensions/installed/demo-extension/backend/stop"
        )
    assert response.status_code == 200, response.text

    assert asyncio.run(sessions.authorize(token, "demo-extension", endpoint)) is None


def test_uninstall_removes_from_installed_list(client: TestClient, tmp_path: Path):
    src = write_extension(tmp_path / "src" / "demo-extension", name="demo-extension")
    client.post("/canvas-extensions/install", json={"source": str(src)})

    def installed_names() -> list[str]:
        return [
            e["name"]
            for e in client.get("/canvas-extensions/installed").json()[
                "canvas_extensions"
            ]
        ]

    assert "demo-extension" in installed_names()

    deleted = client.delete("/canvas-extensions/installed/demo-extension")
    assert deleted.status_code == 200
    assert "demo-extension" not in installed_names()


def test_install_existing_without_force_returns_409(client: TestClient, tmp_path: Path):
    src = write_extension(tmp_path / "src" / "demo-extension", name="demo-extension")
    assert (
        client.post("/canvas-extensions/install", json={"source": str(src)}).status_code
        == 200
    )

    conflict = client.post("/canvas-extensions/install", json={"source": str(src)})
    assert conflict.status_code == 409


def test_install_invalid_source_returns_400(client: TestClient, tmp_path: Path):
    missing = tmp_path / "does-not-exist"

    resp = client.post("/canvas-extensions/install", json={"source": str(missing)})

    assert resp.status_code == 400


def test_install_invalid_manifest_returns_422(client: TestClient, tmp_path: Path):
    bad = tmp_path / "src" / "bad-extension"
    bad.mkdir(parents=True)
    (bad / "canvas-extension.json").write_text("{not json")

    resp = client.post("/canvas-extensions/install", json={"source": str(bad)})

    assert resp.status_code == 422


def test_install_missing_manifest_returns_422_not_500(
    client: TestClient, tmp_path: Path
):
    """根本没有清单文件的源会引发 FileNotFoundError （
    OSError) load_from_dir()的裸 ``read_text()`` -- 一个非常合理的实际输入 (e.g。
    repo_path错误变成了单体仓库
    ，不只是一个理论上的边缘情况。 这必须映射到端点的自身文档中的422，而不是掉落到一
    个未处理的500，该500泄露了文件系统路径。
    """
    no_manifest = tmp_path / "src" / "no-manifest-extension"
    no_manifest.mkdir(parents=True)
    (no_manifest / "README.md").write_text("no manifest here")

    resp = client.post("/canvas-extensions/install", json={"source": str(no_manifest)})

    assert resp.status_code == 422


def test_missing_extension_returns_404(client: TestClient):
    assert client.get("/canvas-extensions/installed/ghost").status_code == 404
    assert (
        client.patch(
            "/canvas-extensions/installed/ghost", json={"enabled": False}
        ).status_code
        == 404
    )
    assert client.delete("/canvas-extensions/installed/ghost").status_code == 404
    assert client.get("/canvas-extensions/installed/ghost/bundle").status_code == 404


def test_bundle_endpoint_busts_cache_across_revisions(
    client: TestClient, tmp_path: Path
):
    """跨修订版本的缓存清除是指定的具体保证
    #4352: 在强制重安装后，如果新包字节被加载，客户端必须获取新的内容，并且响应的验证
    器（ETag）必须改变，否则，基于它们的中间缓存将继续提供预刷新包，即使成功
    验证往返。
    """
    src = write_extension(
        tmp_path / "src" / "demo-extension",
        name="demo-extension",
        entrypoint="dist/index.js",
    )
    client.post("/canvas-extensions/install", json={"source": str(src)})
    first = client.get("/canvas-extensions/installed/demo-extension/bundle")
    assert first.status_code == 200

    # 不同的长度，而不仅仅是不同的字节——因此下面的断言不能仅依靠文件系统 mtime 解析来通
    # 过。
    #
    (src / "dist" / "index.js").write_text("console.log('updated-bundle-v2')")
    client.post("/canvas-extensions/install", json={"source": str(src), "force": True})
    second = client.get("/canvas-extensions/installed/demo-extension/bundle")

    assert second.status_code == 200
    assert second.text == "console.log('updated-bundle-v2')"
    assert second.text != first.text
    assert second.headers["etag"] != first.headers["etag"]


def test_bundle_endpoint_serves_entrypoint_with_no_cache_header(
    client: TestClient, tmp_path: Path
):
    src = write_extension(
        tmp_path / "src" / "demo-extension",
        name="demo-extension",
        entrypoint="dist/index.js",
    )
    client.post("/canvas-extensions/install", json={"source": str(src)})

    resp = client.get("/canvas-extensions/installed/demo-extension/bundle")

    assert resp.status_code == 200
    assert resp.text == "console.log('ok')"
    assert resp.headers["cache-control"] == "no-cache"
    assert "javascript" in resp.headers["content-type"]


def test_bundle_endpoint_rejects_escaping_entrypoint_installed_out_of_band(
    client: TestClient, tmp_path: Path
):
    """遏制必须在服务时重新检查，而不仅仅是安装时。

    模拟安装后引入的符号链接转义（e.g. 直接篡改安装目录）通过直接写入安装存储，绕过
    install_canvas_extension() 自己的验证。
    """
    src = write_extension(tmp_path / "src" / "demo-extension", name="demo-extension")
    install = client.post("/canvas-extensions/install", json={"source": str(src)})
    install_path = Path(install.json()["install_path"])

    outside = tmp_path / "outside.js"
    outside.write_text("payload")
    (install_path / "dist" / "index.js").unlink()
    (install_path / "dist" / "index.js").symlink_to(outside)

    resp = client.get("/canvas-extensions/installed/demo-extension/bundle")

    assert resp.status_code == 404


def test_bundle_endpoint_returns_404_when_entrypoint_file_deleted(
    client: TestClient, tmp_path: Path
):
    """与符号链接转义情况不同的故障模式：清单是
    仍然有效，但它指向的文件已经消失了。
    """
    src = write_extension(tmp_path / "src" / "demo-extension", name="demo-extension")
    install = client.post("/canvas-extensions/install", json={"source": str(src)})
    install_path = Path(install.json()["install_path"])
    (install_path / "dist" / "index.js").unlink()

    resp = client.get("/canvas-extensions/installed/demo-extension/bundle")

    assert resp.status_code == 404


def test_bundle_endpoint_serves_disabled_extensions_too(
    client: TestClient, tmp_path: Path
):
    """捆绑包端点不在 ``enabled`` 上选通——与 GET 相同
    代码库中其他位置的元数据端点（插件/技能），也不会过滤掉禁用的条目。 每次进行全新
    安装时，都会自动禁用，因此这也是一个常见的场景，即在明确启用之前先安装并预览包的
    调
    用者。
    """
    src = write_extension(tmp_path / "src" / "demo-extension", name="demo-extension")
    install = client.post("/canvas-extensions/install", json={"source": str(src)})
    assert install.json()["enabled"] is False

    resp = client.get("/canvas-extensions/installed/demo-extension/bundle")

    assert resp.status_code == 200


@pytest.mark.parametrize(
    "bad_name",
    ["Bad_Name", "a b", "-leading-hyphen", "trailing-hyphen-", "%2e%2e"],
)
def test_path_parameter_rejects_invalid_names(client: TestClient, bad_name: str):
    """{extension_name} 模式是针对路径的深度防御
    通过URL本身进行遍历/注入——在任何请求到达服务层之前，它必须拒绝坏名称，而不仅仅是
    依赖
    ``validate_extension_name`` 位于堆栈较深处。
    """
    assert client.get(f"/canvas-extensions/installed/{bad_name}").status_code == 422
    assert (
        client.patch(
            f"/canvas-extensions/installed/{bad_name}", json={"enabled": True}
        ).status_code
        == 422
    )
    assert client.delete(f"/canvas-extensions/installed/{bad_name}").status_code == 422
    assert (
        client.get(f"/canvas-extensions/installed/{bad_name}/bundle").status_code == 422
    )


def test_install_ignores_smuggled_enabled_field(client: TestClient, tmp_path: Path):
    """请求模型上没有 ``enabled`` 字段，因此调用者
    尝试强制安装被忽略，而不是接受——这符合默认禁用的保证 HTTP 边界不仅限于服务-功能签
    名。
    """
    src = write_extension(tmp_path / "src" / "demo-extension", name="demo-extension")

    resp = client.post(
        "/canvas-extensions/install",
        json={"source": str(src), "enabled": True},
    )

    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_force_reinstall_preserves_enabled_state(client: TestClient, tmp_path: Path):
    src = write_extension(tmp_path / "src" / "demo-extension", name="demo-extension")
    client.post("/canvas-extensions/install", json={"source": str(src)})
    client.patch("/canvas-extensions/installed/demo-extension", json={"enabled": True})

    reinstalled = client.post(
        "/canvas-extensions/install", json={"source": str(src), "force": True}
    )

    assert reinstalled.status_code == 200
    assert reinstalled.json()["enabled"] is True
    assert (
        client.get("/canvas-extensions/installed/demo-extension").json()["enabled"]
        is True
    )


def test_list_installed_empty_and_multiple(client: TestClient, tmp_path: Path):
    assert client.get("/canvas-extensions/installed").json() == {
        "canvas_extensions": []
    }

    write_extension(tmp_path / "src" / "one", name="ext-one")
    write_extension(tmp_path / "src" / "two", name="ext-two")
    client.post(
        "/canvas-extensions/install", json={"source": str(tmp_path / "src" / "one")}
    )
    client.post(
        "/canvas-extensions/install", json={"source": str(tmp_path / "src" / "two")}
    )

    names = {
        e["name"]
        for e in client.get("/canvas-extensions/installed").json()["canvas_extensions"]
    }
    assert names == {"ext-one", "ext-two"}


@pytest.mark.parametrize(
    "source_suffix,repo_path",
    [
        ("", "demo-extension"),
        ("", "/demo-extension"),
        ("/", "demo-extension"),
        ("/", "/demo-extension"),
    ],
)
def test_install_composes_local_source_and_repo_path(
    client: TestClient, tmp_path: Path, source_suffix: str, repo_path: str
):
    """作为源的父目录加上作为安装路径的扩展目录。"""
    repo = tmp_path / "canvas-extensions"
    write_extension(repo / "demo-extension", name="demo-extension")
    # 一个绝对不能接的兄弟姐妹。
    write_extension(repo / "other-extension", name="other-extension")

    install = client.post(
        "/canvas-extensions/install",
        json={"source": str(repo) + source_suffix, "repo_path": repo_path},
    )

    assert install.status_code == 200, install.json()
    body = install.json()
    assert body["name"] == "demo-extension"
    assert body["repo_path"] == repo_path
    assert body["enabled"] is False


def test_install_with_full_extension_dir_as_source_still_works(
    client: TestClient, tmp_path: Path
):
    """原有的单场流程不变。"""
    src = write_extension(tmp_path / "src" / "demo-extension", name="demo-extension")

    install = client.post("/canvas-extensions/install", json={"source": str(src)})

    assert install.status_code == 200
    assert install.json()["name"] == "demo-extension"


def test_install_reports_which_field_is_wrong_for_bad_repo_path(
    client: TestClient, tmp_path: Path
):
    """错误的 Path 会归咎于 Path，而不是来源（旧消息被错误归因）。"""
    repo = tmp_path / "canvas-extensions"
    write_extension(repo / "demo-extension", name="demo-extension")

    install = client.post(
        "/canvas-extensions/install",
        json={"source": str(repo), "repo_path": "demo-extensio"},
    )

    assert install.status_code == 400
    assert "demo-extensio" in install.json()["detail"]
    assert "not found" in install.json()["detail"]
    # canvas客户端将任何包含“failed to fetch”的消息分类为网络中断，并替换为“Disconnected
    # ”弹窗，这将隐藏我们刚刚报告的原因。
    #
    assert "failed to fetch" not in install.json()["detail"].lower()


def test_install_reports_missing_manifest_at_resolved_location(
    client: TestClient, tmp_path: Path
):
    """将源/路径指向没有清单的目录就是这样说的。"""
    repo = tmp_path / "canvas-extensions"
    (repo / "not-an-extension").mkdir(parents=True)

    install = client.post(
        "/canvas-extensions/install",
        json={"source": str(repo), "repo_path": "not-an-extension"},
    )

    assert install.status_code == 422
    assert "canvas-extension.json" in install.json()["detail"]


def test_install_rejects_repo_path_escaping_the_source(
    client: TestClient, tmp_path: Path
):
    """遍历 Path 会被拒绝，而不是解析外部 Source。"""
    repo = tmp_path / "canvas-extensions"
    write_extension(repo / "demo-extension", name="demo-extension")
    write_extension(tmp_path / "outside-extension", name="outside-extension")

    install = client.post(
        "/canvas-extensions/install",
        json={"source": str(repo), "repo_path": "../outside-extension"},
    )

    assert install.status_code == 400
    assert "escapes" in install.json()["detail"]


_SVG = '<svg xmlns="http://www.w3.org/2000/svg"/>'


def _write_icon_extension(directory: Path, icon: object) -> Path:
    src = write_extension(directory, name="demo-extension")
    manifest_path = src / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["icon"] = icon
    manifest_path.write_text(json.dumps(manifest))
    (src / "assets").mkdir()
    (src / "assets" / "icon.svg").write_text(_SVG)
    return src


def test_icon_endpoint_serves_declared_svg_sandboxed(
    client: TestClient, tmp_path: Path
):
    src = _write_icon_extension(tmp_path / "src" / "demo-extension", "assets/icon.svg")
    client.post("/canvas-extensions/install", json={"source": str(src)})

    got = client.get("/canvas-extensions/installed/demo-extension")
    resp = client.get("/canvas-extensions/installed/demo-extension/icon")

    assert got.json()["manifest"]["icon"] == "assets/icon.svg"
    assert resp.status_code == 200
    assert resp.text == _SVG
    assert resp.headers["content-type"].startswith("image/svg+xml")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in resp.headers["content-security-policy"]


def test_icon_endpoint_returns_404_without_declared_icon(
    client: TestClient, tmp_path: Path
):
    src = write_extension(tmp_path / "src" / "demo-extension", name="demo-extension")
    client.post("/canvas-extensions/install", json={"source": str(src)})

    got = client.get("/canvas-extensions/installed/demo-extension")
    resp = client.get("/canvas-extensions/installed/demo-extension/icon")

    assert "icon" not in got.json()["manifest"]
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "bad_icon", ["../icon.svg", "/etc/icon.svg", "assets/icon.png", "a\\b.svg", 42]
)
def test_invalid_icon_is_not_served_and_does_not_hide_extension(
    client: TestClient, tmp_path: Path, bad_icon: object
):
    src = _write_icon_extension(tmp_path / "src" / "demo-extension", bad_icon)
    install = client.post("/canvas-extensions/install", json={"source": str(src)})

    got = client.get("/canvas-extensions/installed/demo-extension")

    assert install.status_code == 200
    assert got.json()["manifest"] is not None
    assert (
        client.get("/canvas-extensions/installed/demo-extension/icon").status_code
        == 404
    )


def test_icon_endpoint_returns_404_for_missing_or_escaping_icon(
    client: TestClient, tmp_path: Path
):
    src = _write_icon_extension(tmp_path / "src" / "demo-extension", "assets/icon.svg")
    install = client.post("/canvas-extensions/install", json={"source": str(src)})
    icon = Path(install.json()["install_path"]) / "assets" / "icon.svg"

    icon.unlink()
    assert (
        client.get("/canvas-extensions/installed/demo-extension/icon").status_code
        == 404
    )

    outside = tmp_path / "outside.svg"
    outside.write_text(_SVG)
    icon.symlink_to(outside)
    assert (
        client.get("/canvas-extensions/installed/demo-extension/icon").status_code
        == 404
    )
    assert (
        client.get("/canvas-extensions/installed/demo-extension/bundle").status_code
        == 200
    )
