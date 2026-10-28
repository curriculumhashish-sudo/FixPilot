"""测试 meta_profiles_router 端点。"""

import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config
from openhands.agent_server.persistence import get_settings_store, reset_stores
from openhands.sdk.llm.meta_profile_store import MetaProfile, MetaProfileStore
from openhands.sdk.settings.model import OpenHandsAgentSettings


@pytest.fixture
def temp_settings_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings_dir = Path(tmpdir) / "settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        yield settings_dir


@pytest.fixture
def temp_meta_profiles_dir(temp_settings_dir):
    # 路由器解析 ``OH_PERSISTENCE_DIR/meta-profiles`` 处的元配置文件，客户端测试夹具将
    # OH_PERSISTENCE_DIR 设置为 temp_settings_dir，因此存储测试夹具必须播种路由器读取的
    # 相同目录。
    #
    meta_dir = temp_settings_dir / "meta-profiles"
    meta_dir.mkdir(parents=True, exist_ok=True)
    yield meta_dir


@pytest.fixture
def client(temp_meta_profiles_dir, temp_settings_dir, monkeypatch):
    reset_stores()
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(temp_settings_dir))
    config = Config(static_files_path=None, session_api_keys=[], secret_key=None)
    app = create_app(config)
    # 不需要 MetaProfileStore 补丁：路由器现在支持 OH_PERSISTENCE_DIR 并解析存储测试夹具
    # 种子的相同目录。
    #
    yield TestClient(app)
    reset_stores()


@pytest.fixture
def store(temp_meta_profiles_dir):
    return MetaProfileStore(base_dir=temp_meta_profiles_dir)


def _meta(classifier="minimax", classes=None) -> dict:
    return MetaProfile.model_validate(
        {
            "classifier_model": classifier,
            "classes": classes or [{"description": "UI", "model": "deepseek"}],
        }
    ).model_dump(mode="json")


# ── 持久化-dir 分辨率 (回归 for #3835) ────────────────────────


def test_meta_profile_store_honors_persistence_dir(monkeypatch, tmp_path):
    """路由器解析 OH_PERSISTENCE_DIR 下的元配置文件，而不是主机
    ~/.openhands/meta-profiles，所以隔离智能体-服务器保持隔离。"""
    from openhands.agent_server.meta_profiles_router import _get_meta_profile_store

    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path))
    store = _get_meta_profile_store()
    assert store.base_dir == tmp_path / "meta-profiles"


def test_meta_profile_store_falls_back_to_home(monkeypatch, tmp_path):
    """如果没有 OH_PERSISTENCE_DIR，则回退到 ~/.openhands/meta-profiles 所以
    元配置文件与它们按名称引用的 LLM 配置文件保持在同一位置（而不是工作区相对目录）。
    """
    from openhands.agent_server.meta_profiles_router import _get_meta_profile_store

    monkeypatch.delenv("OH_PERSISTENCE_DIR", raising=False)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    store = _get_meta_profile_store()
    assert store.base_dir == fake_home / ".openhands" / "meta-profiles"


# ── 名单────────────────────────────────────────────────────────────────────


def test_list_empty(client):
    response = client.get("/api/meta-profiles")
    assert response.status_code == 200
    body = response.json()
    assert body["meta_profiles"] == []
    assert body["active_meta_profile"] is None


def test_list_returns_summaries(client, store):
    store.save("balanced", MetaProfile.model_validate(_meta()))
    response = client.get("/api/meta-profiles")
    assert response.status_code == 200
    body = response.json()
    assert body["meta_profiles"] == [
        {
            "name": "balanced",
            "classifier_model": "minimax",
            "num_classes": 1,
        }
    ]


# ── 获取────────────────────────────────────────────────────────────────────


def test_get_meta_profile(client, store):
    store.save("balanced", MetaProfile.model_validate(_meta()))
    response = client.get("/api/meta-profiles/balanced")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "balanced"
    assert body["config"]["classifier_model"] == "minimax"
    assert body["config"]["classes"][0]["model"] == "deepseek"


def test_get_missing_returns_404(client):
    response = client.get("/api/meta-profiles/nope")
    assert response.status_code == 404


# ── 保存──────────────────────────────────────────────────────────────────────


def test_save_creates_meta_profile(client, store):
    response = client.post("/api/meta-profiles/balanced", json=_meta())
    assert response.status_code == 201
    assert store.load("balanced").classifier_model == "minimax"


def test_save_overwrites(client, store):
    client.post("/api/meta-profiles/p", json=_meta(classifier="a"))
    response = client.post("/api/meta-profiles/p", json=_meta(classifier="c"))
    assert response.status_code == 201
    assert store.load("p").classifier_model == "c"


def test_save_invalid_body_returns_422(client):
    response = client.post("/api/meta-profiles/p", json={"classes": []})
    assert response.status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"classifier_model": "minimax"},
        {"classifier_model": "minimax", "classes": [], "prompt_template": None},
        {"classifier_model": "minimax", "model_table": "a: cheap"},
    ],
)
def test_save_router_without_route_returns_422(client, store, body):
    """既没有类也没有 prompt_template 的主体永远无法路由。"""
    response = client.post("/api/meta-profiles/empty", json=body)
    assert response.status_code == 422
    assert "classes or a prompt_template" in response.text
    assert store.list() == []


def test_save_direct_mode_without_classes_is_accepted(client, store):
    body = {"classifier_model": "minimax", "prompt_template": "{{ instance_text }}"}
    response = client.post("/api/meta-profiles/direct", json=body)
    assert response.status_code == 201
    assert store.load("direct").classes == []


def test_stored_router_without_route_still_loads(client, store):
    """422 存在之前保存的文件仍然可读且可激活。"""
    store.save("legacy", MetaProfile(classifier_model="minimax"))
    assert client.get("/api/meta-profiles/legacy").status_code == 200
    assert client.post("/api/meta-profiles/legacy/activate").status_code == 200
    assert client.get("/api/meta-profiles").status_code == 200


def test_save_invalid_name_returns_422(client):
    response = client.post("/api/meta-profiles/..bad..", json=_meta())
    assert response.status_code == 422


def test_save_timeout_returns_503(client, monkeypatch):
    """保存表面将锁 TimeoutError 存储为可重试的 503，而不是 500。"""

    def boom(self, name, meta_profile, *, max_profiles=None):
        raise TimeoutError("locked")

    monkeypatch.setattr(MetaProfileStore, "save", boom)

    response = client.post("/api/meta-profiles/anything", json=_meta())
    assert response.status_code == 503


# ── 删除────────────────────────────────────────────────────────────────────


def test_delete_meta_profile(client, store):
    store.save("p", MetaProfile.model_validate(_meta()))
    response = client.delete("/api/meta-profiles/p")
    assert response.status_code == 200
    assert store.list() == []


def test_delete_is_idempotent(client):
    response = client.delete("/api/meta-profiles/nope")
    assert response.status_code == 200


def test_delete_timeout_returns_503(client, monkeypatch):
    """删除表面将锁 TimeoutError 存储为可重试的 503，而不是 500。"""

    def boom(self, name):
        raise TimeoutError("locked")

    monkeypatch.setattr(MetaProfileStore, "delete", boom)

    response = client.delete("/api/meta-profiles/anything")
    assert response.status_code == 503


def test_delete_active_clears_active(client, store):
    store.save("p", MetaProfile.model_validate(_meta()))
    activate = client.post("/api/meta-profiles/p/activate")
    assert activate.status_code == 200

    client.delete("/api/meta-profiles/p")

    listed = client.get("/api/meta-profiles").json()
    assert listed["active_meta_profile"] is None


def test_delete_active_clears_nested_agent_settings(client, store):
    """删除活动元配置文件必须清除 * 嵌套 * 智能体设置。

    否则，路由工具将保持启用状态，指向现已删除的配置文件，这会中断下一个对话。 防止顶
    级/嵌套漂移。
    """
    store.save("p", MetaProfile.model_validate(_meta()))
    client.post("/api/meta-profiles/p/activate")

    client.delete("/api/meta-profiles/p")

    persisted = get_settings_store().load()
    assert persisted is not None
    agent = persisted.agent_settings
    assert isinstance(agent, OpenHandsAgentSettings)
    assert agent.active_meta_profile is None
    assert agent.enable_classify_and_switch_llm_tool is False
    assert agent.meta_profile is None


# ── 启动──────────────────────────────────────────────────────────────────


def test_activate_sets_active_meta_profile(client, store):
    store.save("p", MetaProfile.model_validate(_meta()))
    response = client.post("/api/meta-profiles/p/activate")
    assert response.status_code == 200
    assert response.json()["name"] == "p"

    listed = client.get("/api/meta-profiles").json()
    assert listed["active_meta_profile"] == "p"


def test_activate_propagates_into_agent_settings(client, store):
    """激活必须连接 * 嵌套 * 智能体设置，而不仅仅是外观。

    ``enable_classify_and_switch_llm_tool`` / ``active_meta_profile`` 开
    ``agent_settings`` 是实际附加布线工具的内容； 如果仅设置了顶级字段，激活会报告成
    功但不执行任何操作。
    """
    store.save("p", MetaProfile.model_validate(_meta()))
    response = client.post("/api/meta-profiles/p/activate")
    assert response.status_code == 200

    persisted = get_settings_store().load()
    assert persisted is not None
    assert persisted.active_meta_profile == "p"
    agent = persisted.agent_settings
    assert isinstance(agent, OpenHandsAgentSettings)
    assert agent.active_meta_profile == "p"
    assert agent.enable_classify_and_switch_llm_tool is True
    assert agent.meta_profile == MetaProfile.model_validate(_meta())


def test_activate_reports_applied_on_openhands_settings(client, store):
    store.save("p", MetaProfile.model_validate(_meta()))
    response = client.post("/api/meta-profiles/p/activate")
    assert response.status_code == 200
    assert response.json() == {
        "name": "p",
        "message": "Meta-profile 'p' activated",
        "applied": True,
    }


def test_activate_on_acp_settings_reports_not_applied(client, store):
    """ACP 设置无法附加布线工具，因此指针被丢弃。

    响应必须如此说明（如 LLM-配置文件激活的 ``llm_applied``），而不是声明元配置文件已
    激活。
    """
    store.save("p", MetaProfile.model_validate(_meta()))
    patched = client.patch(
        "/api/settings", json={"agent_settings_diff": {"agent_kind": "acp"}}
    )
    assert patched.status_code == 200

    response = client.post("/api/meta-profiles/p/activate")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "name": "p",
        "message": (
            "Meta-profile 'p' not activated: the current agent settings "
            "cannot route between models"
        ),
        "applied": False,
    }

    assert client.get("/api/meta-profiles").json()["active_meta_profile"] is None
    persisted = get_settings_store().load()
    assert persisted is not None
    assert persisted.active_meta_profile is None


def test_activate_missing_returns_404(client):
    response = client.post("/api/meta-profiles/nope/activate")
    assert response.status_code == 404


def test_activate_with_corrupted_settings_returns_409(client, store, temp_settings_dir):
    """不可读的 settings.json 被拒绝并返回 409，如 LLM-profile
    激活不会泄漏设置路径或触及文件。"""
    store.save("p", MetaProfile.model_validate(_meta()))
    store.save("q", MetaProfile.model_validate(_meta()))
    assert client.post("/api/meta-profiles/p/activate").status_code == 200
    settings_path = temp_settings_dir / "settings.json"
    valid = settings_path.read_bytes()
    settings_path.write_bytes(b'{"agent_settings": ')

    response = client.post("/api/meta-profiles/q/activate")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Settings file is corrupted or encrypted with a different key"
    }
    assert str(settings_path) not in response.text
    assert settings_path.read_bytes() == b'{"agent_settings": '

    settings_path.write_bytes(valid)
    assert client.get("/api/meta-profiles").json()["active_meta_profile"] == "p"


def test_activate_settings_io_error_returns_500(client, store, monkeypatch):
    """文件系统错误保留 500，与损坏的文件不同。"""
    store.save("p", MetaProfile.model_validate(_meta()))

    def fail(self, update_fn):
        raise OSError("disk full")

    monkeypatch.setattr(type(get_settings_store()), "update", fail)

    response = client.post("/api/meta-profiles/p/activate")

    assert response.status_code == 500
    assert "disk full" not in response.text


def test_concurrent_delete_and_activate_keep_settings_consistent(client, store):
    """delete(active) 与 activate(other) 竞赛不得损坏设置。

    ``delete`` 清除活动元配置文件并 ``activate`` 设置新的元配置文件； 两者都通过文件
    锁定设置存储。 无论重排序如何，已持久化状态必须保持一致：
    活动的配置文件永远不会是刚刚删除的那个，嵌套的``agent_settings``也永远不会偏离顶
    层的``active_meta_profile``。
    """
    store.save("q", MetaProfile.model_validate(_meta()))

    for _ in range(15):
        # 在每场比赛前重新建立“p”作为活动配置文件。
        store.save("p", MetaProfile.model_validate(_meta()))
        client.post("/api/meta-profiles/p/activate")

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(client.delete, "/api/meta-profiles/p"),
                pool.submit(client.post, "/api/meta-profiles/q/activate"),
            ]
            for future in futures:
                assert future.result().status_code == 200

        persisted = get_settings_store().load()
        assert persisted is not None
        active = persisted.active_meta_profile
        # “p”已被删除，因此它绝不能保持活动状态； 结果是“q”或None，具体取决于最后提交的
        # 写入。
        #
        assert active in (None, "q")

        agent = persisted.agent_settings
        assert isinstance(agent, OpenHandsAgentSettings)
        # 嵌套智能体设置必须与顶层外观一致。
        assert agent.active_meta_profile == active
        assert agent.enable_classify_and_switch_llm_tool is (active is not None)
