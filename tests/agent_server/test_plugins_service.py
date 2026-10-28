"""测试仅插件市场目录 (plugins_service / plugins_router)。

该服务针对受控市场运行真正的过滤+解析逻辑； 仅网络绑定的 ``update_skills_repository``
 被存根。
"""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openhands.agent_server import plugins_service
from openhands.agent_server.plugins_router import plugins_router
from openhands.agent_server.plugins_service import (
    MarketplacePluginInfo,
    service_get_plugins_marketplace_catalog,
)
from openhands.sdk.plugin import install_plugin


@pytest.fixture(autouse=True)
def _reset_catalog_cache():
    """重置模块级 TTL 缓存，以便测试不会相互泄漏条目。"""
    plugins_service._plugin_catalog_cache = None
    yield
    plugins_service._plugin_catalog_cache = None


def _write_marketplace(repo_dir: Path, plugins: list[dict]) -> Path:
    """写入市场 JSON 并返回存储库目录。"""
    mp_file = repo_dir / "marketplaces" / "default.json"
    mp_file.parent.mkdir(parents=True, exist_ok=True)
    mp_file.write_text(
        json.dumps({"name": "test-mp", "owner": {"name": "Test"}, "plugins": plugins})
    )
    return repo_dir


def _write_manifest_marketplace(repo_dir: Path, plugins: list[dict]) -> Path:
    """将目录写入 ``.plugin/marketplace.json`` 清单。

    镜像真实的 OpenHands/扩展布局，其中目录是通过 ``Marketplace.load`` (
    ``.plugin/marketplace.json``) 发
    现的，
    ``marketplaces/default.json`` 不存在。
    """
    mp_file = repo_dir / ".plugin" / "marketplace.json"
    mp_file.parent.mkdir(parents=True, exist_ok=True)
    mp_file.write_text(
        json.dumps({"name": "test-mp", "owner": {"name": "Test"}, "plugins": plugins})
    )
    return repo_dir


def _make_installable_plugin(plugin_dir: Path, name: str) -> Path:
    """创建一个最小的可安装插件目录。"""
    manifest_dir = plugin_dir / ".plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "plugin.json").write_text(
        json.dumps({"name": name, "version": "1.0.0", "description": name})
    )
    return plugin_dir


def test_catalog_returns_only_true_plugins(tmp_path: Path, monkeypatch):
    # 安排：一个混合 True 插件（./plugins/) 和技能
    # （./skills/)，就像真实的 OpenHands 市场一样。
    repo = _write_marketplace(
        tmp_path / "ext",
        [
            {"name": "local-plugin", "source": "./plugins/local-plugin"},
            {"name": "a-skill", "source": "./skills/a-skill"},
        ],
    )
    monkeypatch.setattr(
        plugins_service, "update_skills_repository", lambda *a, **k: repo
    )
    installed = tmp_path / "installed"
    installed.mkdir()

    # 法案
    catalog = service_get_plugins_marketplace_catalog(installed_dir=installed)

    # 断言：仅 ./plugins/ 条目，解析为本地 PluginSource 坐标。
    assert [p.name for p in catalog] == ["local-plugin"]
    assert catalog[0].source.endswith("plugins/local-plugin")
    assert catalog[0].ref is None
    assert catalog[0].repo_path is None


def test_catalog_loads_from_plugin_manifest_layout(tmp_path: Path, monkeypatch):
    # 回归：真正的扩展存储库将目录作为
    # .plugin/marketplace.json（由Marketplace.load发现）并且没有市场/default.json。 服务
    # 不得提前返回缺失的 default.json 并将目录清空。
    #
    repo = _write_manifest_marketplace(
        tmp_path / "ext",
        [
            {"name": "city-weather", "source": "./plugins/city-weather"},
            {"name": "a-skill", "source": "./skills/a-skill"},
        ],
    )
    assert not (repo / "marketplaces" / "default.json").exists()
    monkeypatch.setattr(
        plugins_service, "update_skills_repository", lambda *a, **k: repo
    )
    installed = tmp_path / "installed"
    installed.mkdir()

    # 法案
    catalog = service_get_plugins_marketplace_catalog(installed_dir=installed)

    # 断言：返回 True 插件（不是空目录），不包括技能。
    assert [p.name for p in catalog] == ["city-weather"]
    assert catalog[0].source.endswith("plugins/city-weather")


def test_catalog_resolves_structured_source_and_excludes_structured_skills(
    tmp_path: Path, monkeypatch
):
    # 排列：结构化 (GitHub) 源 — 一个在插件/下，一个在技能/下。
    repo = _write_marketplace(
        tmp_path / "ext",
        [
            {
                "name": "gh-plugin",
                "source": {
                    "source": "github",
                    "repo": "owner/repo",
                    "ref": "v1.0.0",
                    "path": "plugins/gh-plugin",
                },
            },
            {
                "name": "gh-skill",
                "source": {
                    "source": "github",
                    "repo": "owner/repo",
                    "path": "skills/gh-skill",
                },
            },
        ],
    )
    monkeypatch.setattr(
        plugins_service, "update_skills_repository", lambda *a, **k: repo
    )
    installed = tmp_path / "installed"
    installed.mkdir()

    # 法案
    catalog = service_get_plugins_marketplace_catalog(installed_dir=installed)

    # 断言：排除结构化技能； 该插件保留其坐标。
    assert [p.name for p in catalog] == ["gh-plugin"]
    assert catalog[0].source == "github:owner/repo"
    assert catalog[0].ref == "v1.0.0"
    assert catalog[0].repo_path == "plugins/gh-plugin"


def test_catalog_marks_installed_plugins(tmp_path: Path, monkeypatch):
    # 排列：两个目录插件； 一个是本地安装的。
    repo = _write_marketplace(
        tmp_path / "ext",
        [
            {"name": "installed-plugin", "source": "./plugins/installed-plugin"},
            {"name": "available-plugin", "source": "./plugins/available-plugin"},
        ],
    )
    monkeypatch.setattr(
        plugins_service, "update_skills_repository", lambda *a, **k: repo
    )
    store = tmp_path / "installed"
    store.mkdir()
    install_plugin(
        str(_make_installable_plugin(tmp_path / "src", "installed-plugin")),
        installed_dir=store,
    )

    # 法案
    catalog = service_get_plugins_marketplace_catalog(installed_dir=store)

    # 断言：安装状态反映本地安装存储。
    installed_by_name = {p.name: p.installed for p in catalog}
    assert installed_by_name["installed-plugin"] is True
    assert installed_by_name["available-plugin"] is False


def test_catalog_enriches_local_plugin_entries_with_contents(
    tmp_path: Path, monkeypatch
):
    # 排列：目录条目的 ./plugins/ 源存在于存储库内
    # 克隆，具有捆绑的技能和文档文件。
    repo = _write_marketplace(
        tmp_path / "ext",
        [{"name": "local-plugin", "source": "./plugins/local-plugin"}],
    )
    plugin_dir = _make_installable_plugin(
        repo / "plugins" / "local-plugin", "local-plugin"
    )
    skill_dir = plugin_dir / "skills" / "hello"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: hello\ndescription: Say hello politely\n---\nGreet the user."
    )
    (plugin_dir / "README.md").write_text("# Local plugin")
    monkeypatch.setattr(
        plugins_service, "update_skills_repository", lambda *a, **k: repo
    )
    installed = tmp_path / "installed"
    installed.mkdir()

    # 法案
    catalog = service_get_plugins_marketplace_catalog(installed_dir=installed)

    # 断言：该条目携带其本地可加载的内容。
    entry = catalog[0]
    assert entry.path is not None
    assert entry.path.endswith("plugins/local-plugin")
    assert [(s.name, s.description) for s in entry.skills or []] == [
        ("hello", "Say hello politely")
    ]
    assert entry.files == [
        ".plugin/plugin.json",
        "README.md",
        "skills/hello/SKILL.md",
    ]


def test_catalog_leaves_contents_unset_for_remote_sources(tmp_path: Path, monkeypatch):
    # 安排：结构化的 GitHub 源 - 插件位于另一个源中
    # 存储库，因此没有本地副本可从中加载内容。
    repo = _write_marketplace(
        tmp_path / "ext",
        [
            {
                "name": "gh-plugin",
                "source": {
                    "source": "github",
                    "repo": "owner/repo",
                    "ref": "v1.0.0",
                    "path": "plugins/gh-plugin",
                },
            }
        ],
    )
    monkeypatch.setattr(
        plugins_service, "update_skills_repository", lambda *a, **k: repo
    )
    installed = tmp_path / "installed"
    installed.mkdir()

    # 法案
    catalog = service_get_plugins_marketplace_catalog(installed_dir=installed)

    # 断言
    assert catalog[0].path is None
    assert catalog[0].skills is None
    assert catalog[0].files is None


class TestPluginsMarketplaceRoute:
    def test_marketplace_route_returns_plugins_payload(self, monkeypatch):
        # 安排
        sample = [
            MarketplacePluginInfo(
                name="p",
                description="d",
                source="github:o/r",
                ref="v1",
                repo_path="plugins/p",
                installed=True,
            )
        ]
        monkeypatch.setattr(
            "openhands.agent_server.plugins_router."
            "service_get_plugins_marketplace_catalog",
            lambda: sample,
        )
        app = FastAPI()
        app.include_router(plugins_router)
        client = TestClient(app)

        # 法案
        resp = client.get("/plugins/marketplace")

        # 断言：响应被包装为带有完整坐标的 {"plugins": [...]} 。
        assert resp.status_code == 200
        assert resp.json() == {
            "plugins": [
                {
                    "name": "p",
                    "description": "d",
                    "source": "github:o/r",
                    "ref": "v1",
                    "repo_path": "plugins/p",
                    "installed": True,
                    "path": None,
                    "skills": None,
                    "files": None,
                }
            ]
        }
