"""测试 agent_profiles_router 端点。

镜像 ``test_profiles_router`` (LLM) 套件，加上 AgentProfile 特定的
contracts: 一个单独的 ``active_agent_profile_id`` 指针，仅指针
通过 id 激活（无 ``agent_settings`` 写入），以及惰性迁移种子。
"""

import concurrent.futures
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from openhands.agent_server import agent_profiles_router as router_module
from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config
from openhands.agent_server.persistence import reset_stores
from openhands.agent_server.profiles_router import MAX_PROFILES
from openhands.sdk.llm import LLM
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.profiles import (
    ACPAgentProfile,
    AgentProfileStore,
    OpenHandsAgentProfile,
)


@pytest.fixture
def temp_agent_profiles_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = Path(tmpdir) / "agent-profiles"
        agent_dir.mkdir(parents=True, exist_ok=True)
        yield agent_dir


@pytest.fixture
def temp_settings_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings_dir = Path(tmpdir) / "settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        yield settings_dir


@pytest.fixture
def client(temp_agent_profiles_dir, temp_settings_dir, monkeypatch):
    """使用隔离的智能体-配置文件/设置目录测试客户端，无密码。"""
    reset_stores()
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(temp_settings_dir))
    config = Config(static_files_path=None, session_api_keys=[], secret_key=None)
    app = create_app(config)
    with patch(
        "openhands.agent_server.agent_profiles_router.get_agent_profile_store",
        lambda: AgentProfileStore(base_dir=temp_agent_profiles_dir),
    ):
        yield TestClient(app)
    reset_stores()


@pytest.fixture
def store(temp_agent_profiles_dir):
    return AgentProfileStore(base_dir=temp_agent_profiles_dir)


@pytest.fixture
def default_llm_profile_store(temp_settings_dir):
    """真实的（未修补的）LLM 配置文件存储 ``client`` 测试夹具的
    ``get_llm_profile_store()`` 解析为，给定 ``OH_PERSISTENCE_DIR`` — 参见
    ``_get_profile_persistence_dir`` (``<dir>/profiles``)。
    """
    return LLMProfileStore(base_dir=temp_settings_dir / "profiles")


# ── 懒惰迁移种子──────────────────────────────────────────────────────


def test_first_list_seeds_default_profile(client):
    """空商店上的第一个 GET 正好种子一个默认配置文件。"""
    response = client.get("/api/agent-profiles")

    assert response.status_code == 200
    body = response.json()
    assert len(body["profiles"]) == 1
    seeded = body["profiles"][0]
    assert seeded["name"] == "default"
    assert seeded["agent_kind"] == "openhands"
    assert seeded["llm_profile_ref"] == "default"
    assert seeded["mcp_server_refs"] is None
    # 活动指针设置为种子配置文件的 ID。
    assert body["active_agent_profile_id"] == seeded["id"]

    # 并且它是已持久化进入设置。
    settings = client.get("/api/settings").json()
    assert settings["active_agent_profile_id"] == seeded["id"]


def test_seed_is_idempotent(client):
    """第二个 GET 不会再次播种。"""
    first = client.get("/api/agent-profiles").json()
    second = client.get("/api/agent-profiles").json()

    assert len(second["profiles"]) == 1
    assert second["active_agent_profile_id"] == first["active_agent_profile_id"]


def test_seed_references_active_llm_profile(client, default_llm_profile_store):
    """设置后，种子会引用活动的 LLM 配置文件。"""
    default_llm_profile_store.save("my-llm", LLM(model="gpt-4o-mini"))
    client.patch("/api/settings", json={"active_profile": "my-llm"})

    body = client.get("/api/agent-profiles").json()
    assert body["profiles"][0]["llm_profile_ref"] == "my-llm"


def test_seed_acp_when_settings_acp(client):
    """ACP agent_settings 创建一个 ACP 信息（llm_profile_ref）。"""
    client.patch(
        "/api/settings",
        json={"agent_settings_diff": {"agent_kind": "acp", "acp_server": "codex"}},
    )

    body = client.get("/api/agent-profiles").json()
    seeded = body["profiles"][0]
    assert seeded["agent_kind"] == "acp"
    assert seeded["llm_profile_ref"] is None

    detail = client.get("/api/agent-profiles/default").json()
    assert detail["profile"]["acp_server"] == "codex"


def test_seed_backfills_default_llm_profile_when_real_config(
    client, default_llm_profile_store
):
    """没有活动的 LLM 配置文件，但有 *真实的 * 实时的 LLM 配置：种子回填
    可解析的“默认”LLM 配置文件。

    回归测试 #3933 — 之前 ``llm_profile_ref`` 回退到字面“默认”，没有任何内容创建该
    LLM 配置文件，因此种子（和活动）智能体配置文件在
    对话启动时为 404。 只有当活的 ``agent_settings.llm`` 是真实的，预存在配置（这里：
    自定义 ``base_url``）——即遗留/云迁移场
    景——才触发补丁，而不是新账户的裸 SDK 默认设置（见下面的鬼魂配置测试，#4031）。
    """
    # 提供实时 LLM 真实配置，以便回填是有保证的。
    client.patch(
        "/api/settings",
        json={"agent_settings_diff": {"llm": {"base_url": "https://proxy.example/v1"}}},
    )

    body = client.get("/api/agent-profiles").json()
    seeded = body["profiles"][0]
    assert seeded["llm_profile_ref"] == "default"
    assert "default.json" in default_llm_profile_store.list()

    materialized = client.post("/api/agent-profiles/default/materialize").json()
    assert materialized["valid"] is True
    assert materialized["llm_profile_resolved"] is True


def test_seed_skips_ghost_llm_profile_for_bare_defaults(
    client, default_llm_profile_store
):
    """一个全新的、从未配置过的帐户必须不获得无密钥的“默认”LLM
    配置文件已持久化 (#4031)。

    在裸 SDK 默认情况下（``model="gpt-5.5"``，无 api_key），回填为
    skipped: 没有写入 ``default.json``，因此 LLM 配置文件列表保持不变
    空的，而不是显示一个无法解释的、无功能的“幽灵”配置文件。 智能体配置的
    ``llm_profile_ref``保留为*软* '默认'引用 — 这种引用在报告中表现为
    悬空（从不触发），而在用户保存实际LLM配置时则解决现实问题。
    """
    body = client.get("/api/agent-profiles").json()
    seeded = body["profiles"][0]
    # 智能体配置文件仍然是种子，带有软（未解析）引用。
    assert seeded["llm_profile_ref"] == "default"
    # ...but no ghost LLM profile is left behind.
    assert "default.json" not in default_llm_profile_store.list()
    assert default_llm_profile_store.list() == []

    # 软参考表面在实现时悬空，而不是 500。
    materialized = client.post("/api/agent-profiles/default/materialize").json()
    assert materialized["valid"] is False
    assert materialized["llm_profile_resolved"] is False
    assert "LLM profile 'default' not found" in materialized["errors"]
    # 只有发布的 422 详细信息在此字段中命名了 ref (#5871)。
    assert "dangling_llm_profile_ref" not in materialized


def test_seed_does_not_clobber_existing_default_llm_profile(
    client, default_llm_profile_store
):
    """预先存在的“默认”LLM 配置文件不会受到种子的影响。"""
    default_llm_profile_store.save("default", LLM(model="existing/model"))

    client.get("/api/agent-profiles")

    reloaded = default_llm_profile_store.load("default")
    assert reloaded.model == "existing/model"


def test_seed_does_not_clobber_differently_cased_default_llm_profile(
    client, default_llm_profile_store
):
    """预先存在的不同大小写的“默认”LLM 配置文件永远不会
    被覆盖。

    回归测试：存在性检查必须以相同的方式解析名称
    ``save()`` 通过商店自身的路径解析，而不是通过敏感的 ``list()`` 成员资格检查 —— 在
    不区分大小写的文件系统（macOS/Windows）中，
    'default' 和 'Default' 是同一个路径，所以简单的检查会忽略碰撞，``save()`` 会默默
    地覆盖现有的配置。
    """
    default_llm_profile_store.save("Default", LLM(model="existing/model"))

    client.get("/api/agent-profiles")

    reloaded = default_llm_profile_store.load("Default")
    assert reloaded.model == "existing/model"


def test_seed_llm_profile_limit_reached_does_not_500(client, default_llm_profile_store):
    """在回填期间达到 LLM 配置文件上限会发出警告并继续
    而不是500。

    回归测试：回填必须抓住LLM商店自己的
    ``ProfileLimitExceeded`` (``openhands.sdk.llm.llm_profile_store``)，而不是来自智
    能体-profil
    e store (``openhands.sdk.profiles``） — 捕获到错误的类会导致真实类以未处理的 500
    状态码传播。
    """
    for i in range(MAX_PROFILES):
        default_llm_profile_store.save(f"other-{i}", LLM(model="x"))

    response = client.get("/api/agent-profiles")

    assert response.status_code == 200
    seeded = response.json()["profiles"][0]
    assert seeded["llm_profile_ref"] == "default"
    assert "default.json" not in default_llm_profile_store.list()


def test_seed_backfills_when_active_profile_is_empty_string(
    client, default_llm_profile_store, temp_settings_dir
):
    """空字符串（不是 ``None``）``active_profile`` 仍然会触发
    回填。

    回归 test：触发条件必须是falsy check，匹配
    ``build_seed_profile`` 自己的 ``active_llm_profile or SEED_PROFILE_NAME`` 回退方
    案 —
    ``is None`` 检查将跳过 ``""`` 的回填，而
    ``build_seed_profile`` 仍然退回到无法解析的文字
    ``"default"`` 复制第 3933 号悬空引用。 的 HTTP  PATCH  载荷'的模式验证器阻止客户
    端设置 `""`, 但存储的
    ``PersistedSettings`` 该字段没有这样的约束，所以可能是手工编辑的或遗留的
    settings.json 它仍然可以包含它。

    实时 LLM 带有自定义 ``base_url``，因此它算作真实配置，而回填实际上保留了一个配置
    文件（#4031 在真实配置上对其进行门控）。
    """
    (temp_settings_dir / "settings.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "agent_settings": {
                    "agent_kind": "openhands",
                    "llm": {"model": "gpt-5.5", "base_url": "https://proxy.example/v1"},
                },
                "conversation_settings": {},
                "active_profile": "",
                "active_agent_profile_id": None,
                "misc_settings": {},
            }
        )
    )

    body = client.get("/api/agent-profiles").json()
    assert body["profiles"][0]["llm_profile_ref"] == "default"
    assert "default.json" in default_llm_profile_store.list()

    materialized = client.post("/api/agent-profiles/default/materialize").json()
    assert materialized["valid"] is True


def test_seed_acp_does_not_backfill_llm_profile(client, default_llm_profile_store):
    """ACP 种子没有 ``llm_profile_ref``，因此不会创建 LLM 配置文件。"""
    client.patch(
        "/api/settings",
        json={"agent_settings_diff": {"agent_kind": "acp", "acp_server": "codex"}},
    )

    client.get("/api/agent-profiles")

    assert default_llm_profile_store.list() == []


@pytest.mark.parametrize(
    "llm, expected",
    [
        # 裸 SDK 默认在从未配置的帐户上 -> 不是真正的配置。
        (LLM(model="gpt-5.5"), False),
        (LLM(model="gpt-5.5", base_url=""), False),
        (LLM(model="gpt-5.5", base_url="   "), False),
        # 真正的 API 键。
        (LLM(model="gpt-5.5", api_key=SecretStr("sk-real")), True),
        # 空白 API 键不算数。
        (LLM(model="gpt-5.5", api_key=SecretStr("  ")), False),
        # 自定义端点（代理/自托管）很重要。
        (LLM(model="gpt-5.5", base_url="https://proxy.example/v1"), True),
        # 即使没有 api_key，订阅身份验证也有效。
        (LLM(model="gpt-5.5", auth_type="subscription"), True),
    ],
)
def test_llm_has_real_config(llm, expected):
    """``_llm_has_real_config`` 控制种子，因此只有真实的、预先存在的
    配置被镜像到已持久化“默认”LLM 配置文件中 (#4031)。"""
    assert router_module._llm_has_real_config(llm) is expected


def _ids(body: dict) -> dict[str, str]:
    return {p["name"]: p["id"] for p in body["profiles"]}


def test_without_an_active_profile_a_seeded_default_is_activated(client, store):
    store.save(OpenHandsAgentProfile(name="mine", llm_profile_ref="x"))

    body = client.get("/api/agent-profiles").json()

    assert set(_ids(body)) == {"mine", "default"}
    assert body["active_agent_profile_id"] == _ids(body)["default"]


def test_an_existing_default_is_activated_rather_than_reseeded(client, store):
    store.save(OpenHandsAgentProfile(name="default", llm_profile_ref="kept"))
    store.save(OpenHandsAgentProfile(name="mine", llm_profile_ref="x"))

    body = client.get("/api/agent-profiles").json()

    assert set(_ids(body)) == {"mine", "default"}
    assert body["active_agent_profile_id"] == _ids(body)["default"]
    assert store.load("default").llm_profile_ref == "kept"


def test_a_full_store_without_default_activates_an_existing_profile(
    client, store, monkeypatch
):
    monkeypatch.setattr(router_module, "MAX_AGENT_PROFILES", 2)
    store.save(OpenHandsAgentProfile(name="beta", llm_profile_ref="x"))
    store.save(OpenHandsAgentProfile(name="alpha", llm_profile_ref="x"))

    response = client.get("/api/agent-profiles")

    assert response.status_code == 200
    body = response.json()
    assert set(_ids(body)) == {"alpha", "beta"}
    assert body["active_agent_profile_id"] == _ids(body)["alpha"]


def test_a_corrupt_default_is_kept_and_another_profile_activated(
    client, store, temp_agent_profiles_dir
):
    corrupt = temp_agent_profiles_dir / "default.json"
    corrupt.write_text("{ not valid json")
    store.save(OpenHandsAgentProfile(name="mine", llm_profile_ref="x"))

    response = client.get("/api/agent-profiles")

    assert response.status_code == 200
    body = response.json()
    assert body["active_agent_profile_id"] == _ids(body)["mine"]
    assert corrupt.read_text() == "{ not valid json"


def test_a_corrupt_default_alone_leaves_no_profile_active(
    client, temp_agent_profiles_dir
):
    (temp_agent_profiles_dir / "default.json").write_text("{ not valid json")

    response = client.get("/api/agent-profiles")

    assert response.status_code == 200
    assert response.json() == {"profiles": [], "active_agent_profile_id": None}


def test_a_dangling_pointer_moves_to_a_seeded_default(client, store):
    # PATCH /api/settings 拒绝未知 ID (#5847)，因此激活真实的配置文件，然后将其文件从带
    # 外删除。
    #
    profile = OpenHandsAgentProfile(name="gone", llm_profile_ref="x")
    store.save(profile)
    stale = str(profile.id)
    assert client.post(f"/api/agent-profiles/{stale}/activate").status_code == 200
    (store.base_dir / "gone.json").unlink()

    body = client.get("/api/agent-profiles").json()

    assert set(_ids(body)) == {"default"}
    assert body["active_agent_profile_id"] == _ids(body)["default"]


def test_concurrent_first_list_seeds_once(client, store):
    """并发首先，GETs 仅保留一个元数据。 指针是一致的。

    种子储存着锁 across check + save + pointer write，因此失去请求看到一个非空存储，
    活跃指针始终与单个值匹配已持久化 profile
     id (never a dangling/overwritten id).
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(
            ex.map(lambda _: client.get("/api/agent-profiles").status_code, range(8))
        )

    assert all(code == 200 for code in codes)
    summaries = store.list_summaries()
    assert len(summaries) == 1  # 只播种一次
    pointer = client.get("/api/settings").json()["active_agent_profile_id"]
    assert pointer == summaries[0]["id"]  # 指针解析为真实轮廓


# ── CRUD ─────────────────────────────────────────────────────────────────────


def test_save_creates_new(client, store):
    response = client.post(
        "/api/agent-profiles/new-profile",
        json={"llm_profile_ref": "base-llm"},
    )

    assert response.status_code == 201
    assert "saved" in response.json()["message"].lower()
    loaded = store.load("new-profile")
    assert loaded.llm_profile_ref == "base-llm"


def test_save_overwrites_existing(client, store):
    store.save(OpenHandsAgentProfile(name="existing", llm_profile_ref="old"))

    response = client.post(
        "/api/agent-profiles/existing",
        json={"llm_profile_ref": "new"},
    )

    assert response.status_code == 201
    assert store.load("existing").llm_profile_ref == "new"


def test_overwrite_preserves_id_and_pointer(client, store):
    """覆盖配置文件可以保持其 id 稳定（并且可以修改版本）。

    省略 ``id``/``revision`` 的创建样式主体不得创建新的 UUID — 这会使旧 id 上键入的活
    动指针悬空。
    """
    store.save(OpenHandsAgentProfile(name="p", llm_profile_ref="base"))
    pid = client.get("/api/agent-profiles/p").json()["profile"]["id"]
    client.post(f"/api/agent-profiles/{pid}/activate")
    assert client.get("/api/settings").json()["active_agent_profile_id"] == pid

    response = client.post("/api/agent-profiles/p", json={"llm_profile_ref": "changed"})
    assert response.status_code == 201

    detail = client.get("/api/agent-profiles/p").json()["profile"]
    assert detail["id"] == pid  # 保留稳定的 ID
    assert detail["revision"] == 1  # 单调碰撞
    assert detail["llm_profile_ref"] == "changed"
    # 活动指针仍解析为（相同 ID）配置文件。
    assert client.get("/api/settings").json()["active_agent_profile_id"] == pid


def test_create_mints_fresh_id_ignoring_client_id(client):
    """创建新名称绝不会重复使用客户端提供的 ID（ID 保持唯一）。

    重复的ID会使ID键激活指针变得模糊——删除一个用户可能会清除激活选择，而另一个ID仍然
    存在。
    """
    client.post("/api/agent-profiles/a", json={"llm_profile_ref": "x"})
    a_id = client.get("/api/agent-profiles/a").json()["profile"]["id"]

    # 尝试重用 a 的 id 创建 'b'； 服务器必须铸造一个新的。
    client.post("/api/agent-profiles/b", json={"llm_profile_ref": "y", "id": a_id})
    b_id = client.get("/api/agent-profiles/b").json()["profile"]["id"]
    assert b_id != a_id

    # 激活b，删除a：指针必须存活（id 不同）。
    client.post(f"/api/agent-profiles/{b_id}/activate")
    client.delete("/api/agent-profiles/a")
    assert client.get("/api/settings").json()["active_agent_profile_id"] == b_id


def test_concurrent_create_same_name_converges_on_one_id(client, store):
    """并发创建相同的新名称会产生一个具有一个 ID 的配置文件。

    保存路径锁用于跨读取 + id-铸造 + 写入操作，因此第二个写入者会看到同名并保留其 id
    而不是用一个新 id 来覆盖它（这将丢失活跃指针）。
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(
            ex.map(
                lambda _: (
                    client.post(
                        "/api/agent-profiles/dup", json={"llm_profile_ref": "x"}
                    ).status_code
                ),
                range(8),
            )
        )

    assert all(code == 201 for code in codes)
    summaries = store.list_summaries()
    assert len(summaries) == 1
    assert len({s["id"] for s in summaries}) == 1


def test_save_path_name_is_authoritative(client, store):
    """路径名覆盖正文中的任何 ``name``。"""
    response = client.post(
        "/api/agent-profiles/path-name",
        json={"name": "body-name", "llm_profile_ref": "x"},
    )

    assert response.status_code == 201
    assert store.load("path-name").name == "path-name"
    with pytest.raises(FileNotFoundError):
        store.load("body-name")


def test_save_acp_profile(client, store):
    response = client.post(
        "/api/agent-profiles/acp-one",
        json={"agent_kind": "acp", "acp_server": "codex", "acp_model": "gpt-5.5"},
    )

    assert response.status_code == 201
    loaded = store.load("acp-one")
    assert loaded.agent_kind == "acp"
    assert loaded.acp_server == "codex"


def test_save_missing_required_ref_returns_422(client):
    """缺少的必填字段将被拒绝，并显示字段位置。

    ``detail`` 镜像 FastAPI 的请求-验证形状：错误对象列表（此处修剪为 loc/type 以避免
    泄漏机密轴承输入）。
    """
    response = client.post("/api/agent-profiles/bad", json={})
    assert response.status_code == 422
    detail = response.json()["detail"]
    # 判别联合用变体（“OpenHands”）标记位置。
    assert any("llm_profile_ref" in err["loc"] for err in detail)


def test_save_schemaless_body_with_stray_skills_key_rejected(client):
    """拒绝从未版本控制的请求中删除的 ``skills`` 字段。"""
    response = client.post(
        "/api/agent-profiles/legacy",
        json={
            "llm_profile_ref": "base",
            "skills": [{"name": "old", "content": "x"}],
        },
    )
    assert response.status_code == 422


def test_save_current_schema_version_rejects_stray_skills_key(client):
    """使用杂散的 ``skills`` 键声明当前模式版本的主体
    是真正的额外='禁止'违规（422）。"""
    from openhands.sdk.profiles.agent_profile import AGENT_PROFILE_SCHEMA_VERSION

    response = client.post(
        "/api/agent-profiles/bad",
        json={
            "schema_version": AGENT_PROFILE_SCHEMA_VERSION,
            "llm_profile_ref": "base",
            "skills": [{"name": "old", "content": "x"}],
        },
    )
    assert response.status_code == 422


def test_save_extra_field_returns_422(client):
    """extra='forbid' rejects unknown fields."""
    response = client.post(
        "/api/agent-profiles/bad",
        json={"llm_profile_ref": "x", "bogus": 1},
    )
    assert response.status_code == 422


def test_save_invalid_name_returns_422(client):
    response = client.post(
        "/api/agent-profiles/.hidden",
        json={"llm_profile_ref": "x"},
    )
    assert response.status_code in (400, 404, 422)


def test_get_returns_profile(client, store):
    store.save(OpenHandsAgentProfile(name="p", llm_profile_ref="base"))

    response = client.get("/api/agent-profiles/p")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "p"
    assert body["profile"]["llm_profile_ref"] == "base"
    assert body["profile"]["agent_kind"] == "openhands"


def test_get_not_found(client):
    response = client.get("/api/agent-profiles/nonexistent")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_ignores_expose_secrets_header(client, store):
    """REST 处的配置文件是机密自由的 (#4017)； GET 没有 ``X-Expose-Secrets``
    行为 - 与 LLM ``/api/profiles`` 路由器不同，标头被简单地忽略而不是更改响应。
    """
    store.save(OpenHandsAgentProfile(name="p", llm_profile_ref="base"))

    plain = client.get("/api/agent-profiles/p").json()
    encrypted = client.get(
        "/api/agent-profiles/p", headers={"X-Expose-Secrets": "encrypted"}
    ).json()
    assert plain == encrypted


def test_get_corrupted_returns_400(client, temp_agent_profiles_dir):
    (temp_agent_profiles_dir / "broken.json").write_text("{ not valid json")
    response = client.get("/api/agent-profiles/broken")
    assert response.status_code == 400


def test_delete_removes_existing(client, store):
    store.save(OpenHandsAgentProfile(name="to-delete", llm_profile_ref="x"))

    response = client.delete("/api/agent-profiles/to-delete")

    assert response.status_code == 200
    with pytest.raises(FileNotFoundError):
        store.load("to-delete")


def test_delete_idempotent(client):
    response = client.delete("/api/agent-profiles/nonexistent")
    assert response.status_code == 200


def test_json_suffix_name_keeps_identity_and_delete_moves_pointer(client, store):
    """带 ``.json`` 后缀的名称是裸名称 (#5873)。

    商店会从文件名中去除 ``.json``，因此 ``x.json`` 和 ``x`` 是同一个配置：覆盖保留
    ID 并增加修订版本，而删除时活动则会将指针移到
    ``default``。
    """
    assert (
        client.post(
            "/api/agent-profiles/suffixed.json", json={"llm_profile_ref": "a"}
        ).status_code
        == 201
    )
    first = client.get("/api/agent-profiles/suffixed.json").json()["profile"]
    assert first["name"] == "suffixed"
    assert first["revision"] == 0
    client.post(f"/api/agent-profiles/{first['id']}/activate")

    client.post("/api/agent-profiles/suffixed.json", json={"llm_profile_ref": "b"})
    second = client.get("/api/agent-profiles/suffixed").json()["profile"]
    assert second["id"] == first["id"]
    assert second["revision"] == 1
    assert second["llm_profile_ref"] == "b"
    assert [
        p["name"] for p in client.get("/api/agent-profiles").json()["profiles"]
    ] == ["suffixed"]

    assert client.delete("/api/agent-profiles/suffixed.json").status_code == 200
    default_id = client.get("/api/agent-profiles/default").json()["profile"]["id"]
    assert client.get("/api/settings").json()["active_agent_profile_id"] == default_id


def test_deleting_the_active_profile_activates_default(client, store):
    store.save(OpenHandsAgentProfile(name="active-one", llm_profile_ref="x"))
    profile_id = client.get("/api/agent-profiles/active-one").json()["profile"]["id"]
    client.post(f"/api/agent-profiles/{profile_id}/activate")
    assert client.get("/api/settings").json()["active_agent_profile_id"] == profile_id

    client.delete("/api/agent-profiles/active-one")

    default_id = client.get("/api/agent-profiles/default").json()["profile"]["id"]
    assert client.get("/api/settings").json()["active_agent_profile_id"] == default_id


def test_deleting_an_active_default_reseeds_it(client):
    seeded = client.get("/api/agent-profiles").json()
    old_id = seeded["active_agent_profile_id"]

    client.delete("/api/agent-profiles/default")

    body = client.get("/api/agent-profiles").json()
    assert set(_ids(body)) == {"default"}
    assert body["active_agent_profile_id"] == _ids(body)["default"] != old_id


def test_delete_active_acp_profile_resets_agent_settings(client, store):
    """重现 bug #5205：agent_settings.agent_kind 删除后仍保留“ACP”。

    该测试演示了 agent_settings 中包含 ACP 配置已过期的问题，删除了活动 ACP 角色后，
    验证了修复程序正确重置了它。
    """
    # 保存并激活 ACP 配置文件
    store.save(
        ACPAgentProfile(name="codex-test", acp_server="codex", acp_model="gpt-5.5")
    )
    profile_id = client.get("/api/agent-profiles/codex-test").json()["profile"]["id"]
    client.post(f"/api/agent-profiles/{profile_id}/activate")

    # 验证配置文件是否处于活动状态
    settings = client.get("/api/settings").json()
    assert settings["active_agent_profile_id"] == profile_id

    # 手动设置 agent_settings 到 ACP 状态以重现 bug 场景在生产环境中，这种状态可以从多种
    # 路径（如对话创建、手动 PATCH /api/settings 等）发生。
    #
    response = client.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "agent_kind": "acp",
                "acp_server": "codex",
                "acp_model": "gpt-5.5",
            }
        },
    )
    assert response.status_code == 200

    # 验证 agent_settings 现在具有 ACP 配置（错误状态设置）
    settings_with_acp = client.get("/api/settings").json()
    assert settings_with_acp["agent_settings"]["agent_kind"] == "acp"
    assert settings_with_acp["agent_settings"]["acp_server"] == "codex"
    assert settings_with_acp["agent_settings"]["acp_model"] == "gpt-5.5"

    # 删除 ACP 个人资料
    # BUG（修复前）：agent_settings 将保持不变，agent_kind="ACP"
    # FIX（之后）：agent_settings重置为默认值OpenHands
    response = client.delete("/api/agent-profiles/codex-test")
    assert response.status_code == 200

    # 验证修复：agent_settings 已重置为默认值 (agent_kind="OpenHands")
    settings_after = client.get("/api/settings").json()
    assert settings_after["active_agent_profile_id"] not in (None, profile_id)
    assert settings_after["agent_settings"]["agent_kind"] == "openhands"
    # 验证 ACP 特定字段已清除
    assert settings_after["agent_settings"].get("acp_server") is None
    assert settings_after["agent_settings"].get("acp_model") is None


def test_delete_active_openhands_profile_does_not_reset_agent_settings(client, store):
    """删除活动的 OpenHands 配置文件只会清除指针，而不是 agent_settings。"""
    # 保存并激活 OpenHands 配置文件
    store.save(OpenHandsAgentProfile(name="custom-oh", llm_profile_ref="x"))
    profile_id = client.get("/api/agent-profiles/custom-oh").json()["profile"]["id"]
    client.post(f"/api/agent-profiles/{profile_id}/activate")

    # 全面重置会破坏非默认状态。 单独 ``agent_kind`` 无法检测到，因为完全重置也会产生“
    # OpenHands”。
    #
    assert (
        client.post(
            "/api/settings/mcp/github",
            json={"transport": "http", "url": "https://github.example/mcp"},
        ).status_code
        == 201
    )
    agent_settings_before = client.get("/api/settings").json()["agent_settings"]
    assert agent_settings_before["mcp_config"].keys() == {"github"}

    # 删除 OpenHands 个人资料
    client.delete("/api/agent-profiles/custom-oh")

    # 验证指针已清除，但 agent_settings 未更改（仍为 OpenHands）
    settings_after = client.get("/api/settings").json()
    assert settings_after["active_agent_profile_id"] not in (None, profile_id)
    assert settings_after["agent_settings"] == agent_settings_before


def test_delete_active_acp_profile_keeps_openhands_settings_intact(client, store):
    """ACP配置文件是一个指针； 它不拥有``agent_settings``。

    ``activate_agent_profile`` 永远不会写入 ``agent_settings``，因此删除 ACP 配置文件
    一定不会影响正常的
    OpenHands 配置。
    """
    client.post(
        "/api/profiles/my-profile",
        json={
            "llm": {
                "model": "anthropic/claude-sonnet-4",
                "api_key": "sk-secret",
                "usage_id": "my-profile",
            },
            "include_secrets": True,
        },
    )
    client.post("/api/profiles/my-profile/activate")
    client.post(
        "/api/settings/mcp/github",
        json={"transport": "http", "url": "https://github.example/mcp"},
    )

    store.save(
        ACPAgentProfile(name="codex-test", acp_server="codex", acp_model="gpt-5.5")
    )
    profile_id = client.get("/api/agent-profiles/codex-test").json()["profile"]["id"]
    client.post(f"/api/agent-profiles/{profile_id}/activate")

    before = client.get("/api/settings").json()
    assert client.delete("/api/agent-profiles/codex-test").status_code == 200
    after = client.get("/api/settings").json()

    assert after["agent_settings"] == before["agent_settings"]
    assert after["agent_settings"]["llm"]["model"] == "anthropic/claude-sonnet-4"
    assert after["agent_settings"]["mcp_config"].keys() == {"github"}
    assert after["active_profile"] == "my-profile"


def test_delete_active_acp_profile_keeps_mcp_registry(client, store):
    """重置会清除 ACP 状态，但不会清除服务器范围的 MCP 注册表。

    ``mcp_config`` 是所有其他配置文件解析其 ``mcp_server_refs`` 的对象，因此删除它会
    使不相关的配置文件悬空。
    """
    store.save(
        ACPAgentProfile(name="codex-test", acp_server="codex", acp_model="gpt-5.5")
    )
    profile_id = client.get("/api/agent-profiles/codex-test").json()["profile"]["id"]
    client.post(f"/api/agent-profiles/{profile_id}/activate")
    client.patch(
        "/api/settings",
        json={"agent_settings_diff": {"agent_kind": "acp", "acp_server": "codex"}},
    )
    assert (
        client.post(
            "/api/settings/mcp/github",
            json={"transport": "http", "url": "https://github.example/mcp"},
        ).status_code
        == 201
    )

    assert client.delete("/api/agent-profiles/codex-test").status_code == 200

    agent_settings = client.get("/api/settings").json()["agent_settings"]
    assert agent_settings["agent_kind"] == "openhands"
    assert agent_settings.get("acp_server") is None
    assert agent_settings["mcp_config"].keys() == {"github"}


def test_delete_active_openhands_profile_clears_stale_acp_settings(client, store):
    """重置键关闭 ``agent_settings``，而不是已删除配置文件的类型。"""
    store.save(OpenHandsAgentProfile(name="custom-oh", llm_profile_ref="x"))
    profile_id = client.get("/api/agent-profiles/custom-oh").json()["profile"]["id"]
    client.post(f"/api/agent-profiles/{profile_id}/activate")
    client.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "agent_kind": "acp",
                "acp_server": "codex",
                "acp_model": "gpt-5.5",
            }
        },
    )
    assert client.get("/api/settings").json()["agent_settings"]["agent_kind"] == "acp"

    assert client.delete("/api/agent-profiles/custom-oh").status_code == 200

    assert (
        client.get("/api/settings").json()["agent_settings"]["agent_kind"]
        == "openhands"
    )


def test_rename_success(client, store):
    store.save(OpenHandsAgentProfile(name="old-name", llm_profile_ref="x"))

    response = client.post(
        "/api/agent-profiles/old-name/rename",
        json={"new_name": "new-name"},
    )

    assert response.status_code == 200
    assert "renamed" in response.json()["message"].lower()
    with pytest.raises(FileNotFoundError):
        store.load("old-name")
    assert store.load("new-name").llm_profile_ref == "x"


def test_rename_not_found(client):
    response = client.post(
        "/api/agent-profiles/ghost/rename",
        json={"new_name": "new-name"},
    )
    assert response.status_code == 404


def test_rename_conflict(client, store):
    store.save(OpenHandsAgentProfile(name="source", llm_profile_ref="a"))
    store.save(OpenHandsAgentProfile(name="target", llm_profile_ref="b"))

    response = client.post(
        "/api/agent-profiles/source/rename",
        json={"new_name": "target"},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


def test_rename_invalid_new_name_returns_422(client, store):
    store.save(OpenHandsAgentProfile(name="valid", llm_profile_ref="x"))
    response = client.post(
        "/api/agent-profiles/valid/rename",
        json={"new_name": "../etc/passwd"},
    )
    assert response.status_code == 422


def test_rename_preserves_active_pointer(client, store):
    """id 键控的活动指针在重命名后仍然存在（id 是稳定的）。"""
    store.save(OpenHandsAgentProfile(name="before", llm_profile_ref="x"))
    profile_id = client.get("/api/agent-profiles/before").json()["profile"]["id"]
    client.post(f"/api/agent-profiles/{profile_id}/activate")

    client.post("/api/agent-profiles/before/rename", json={"new_name": "after"})

    # 相同的 ID，仍然有效。
    assert client.get("/api/settings").json()["active_agent_profile_id"] == profile_id
    assert client.get("/api/agent-profiles/after").json()["profile"]["id"] == profile_id


# ── 激活（仅限指针，通过id） ──────────────────────────────────────────


def test_activate_sets_pointer_without_mutating_agent_settings(client, store):
    store.save(OpenHandsAgentProfile(name="p", llm_profile_ref="x"))
    # 首先设置一次持久化，以便快照已经往返（默认的 un-已持久化与已持久化形式的差异无害）
    # 。
    #
    client.patch(
        "/api/settings",
        json={"agent_settings_diff": {"llm": {"model": "gpt-4o"}}},
    )
    before = client.get("/api/settings").json()["agent_settings"]
    profile_id = client.get("/api/agent-profiles/p").json()["profile"]["id"]

    response = client.post(f"/api/agent-profiles/{profile_id}/activate")

    assert response.status_code == 200
    assert response.json()["agent_settings_applied"] is False
    after = client.get("/api/settings").json()
    assert after["active_agent_profile_id"] == profile_id
    # agent_settings 未受影响——仅限创建时间的合约。
    assert after["agent_settings"] == before


def test_activate_unknown_id_returns_404(client, store):
    store.save(OpenHandsAgentProfile(name="p", llm_profile_ref="x"))
    unknown = "00000000-dead-beef-0000-000000000000"
    response = client.post(f"/api/agent-profiles/{unknown}/activate")
    assert response.status_code == 404


def test_activate_settings_corruption_returns_500(client, store, monkeypatch):
    """损坏/错误键入的设置文件是服务器端故障 (500)。"""
    from openhands.agent_server.persistence.store import FileSettingsStore

    store.save(OpenHandsAgentProfile(name="p", llm_profile_ref="x"))
    profile_id = client.get("/api/agent-profiles/p").json()["profile"]["id"]

    def boom(self, *args, **kwargs):
        raise RuntimeError("settings file corrupted")

    monkeypatch.setattr(FileSettingsStore, "update", boom)
    response = client.post(f"/api/agent-profiles/{profile_id}/activate")
    assert response.status_code == 500


# ── 种子保真度（迁移保留用户的启动配置）────────────


def test_seed_preserves_openhands_fields(client):
    """OpenHands 种子携带重叠的发射字段，而不仅仅是参考。"""
    client.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "tools": [{"name": "terminal"}, {"name": "task_tool_set"}],
                "tool_concurrency_limit": 3,
                "agent_context": {"system_message_suffix": "be terse"},
                "verification": {
                    "critic_enabled": True,
                    "critic_model_name": "x-critic",
                },
            }
        },
    )
    client.get("/api/agent-profiles")  # 触发种子

    prof = client.get("/api/agent-profiles/default").json()["profile"]
    assert [tool["name"] for tool in prof["tools"]] == ["terminal", "task_tool_set"]
    assert "enable_sub_agents" not in prof
    assert "enable_switch_llm_tool" not in prof
    assert prof["tool_concurrency_limit"] == 3
    assert prof["system_message_suffix"] == "be terse"
    # 种子不会禁用任何内容 - 默认配置文件会启动所有已发现的技能（拒绝列表模型）。
    #
    assert prof["disabled_skills"] == []
    assert prof["verification"]["critic_enabled"] is True
    assert prof["verification"]["critic_model_name"] == "x-critic"
    # 配置文件验证是无机密的 — 没有 critic_api_key 预计。
    assert "critic_api_key" not in prof["verification"]


def test_seed_disables_nothing_even_with_inline_global_skills(client):
    """种子永远不会冻结全球技能的名字——它设置了一个空的
    拒绝列表，因此迁移的默认配置文件将随所有发现的技能一起启动。 冻结的名字是 #4017
    启动中断（启动目录中缺少的内联全局技能会悬而未决）。
    """
    client.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "agent_context": {
                    "skills": [
                        {"name": "alpha", "content": "x"},
                        {"name": "beta", "content": "y"},
                    ]
                }
            }
        },
    )
    client.get("/api/agent-profiles")  # 触发种子

    prof = client.get("/api/agent-profiles/default").json()["profile"]
    assert prof["disabled_skills"] == []


def test_seed_preserves_acp_fields(client):
    """ACP 种子携带 acp_server/model/args，而不仅仅是类型。"""
    client.patch(
        "/api/settings",
        json={
            "agent_settings_diff": {
                "agent_kind": "acp",
                "acp_server": "codex",
                "acp_model": "gpt-5.5",
                "acp_args": ["--foo", "--bar"],
            }
        },
    )
    client.get("/api/agent-profiles")  # 触发种子

    prof = client.get("/api/agent-profiles/default").json()["profile"]
    assert prof["agent_kind"] == "acp"
    assert prof["acp_server"] == "codex"
    assert prof["acp_model"] == "gpt-5.5"
    assert prof["acp_args"] == ["--foo", "--bar"]
    # ACP 个人资料根本不包含技能选择字段。
    assert "skill_refs" not in prof
    assert "disabled_skills" not in prof


# ── 储存错误 → HTTP ──────────────────────────────────────────────────────


def test_list_timeout_returns_503(client, monkeypatch):
    def boom(self, timeout=0):
        raise TimeoutError("locked")

    monkeypatch.setattr(AgentProfileStore, "lock", boom)
    response = client.get("/api/agent-profiles")
    assert response.status_code == 503


def test_save_timeout_returns_503(client, monkeypatch):
    def boom(self, profile, *, max_profiles=None):
        raise TimeoutError("locked")

    monkeypatch.setattr(AgentProfileStore, "save", boom)
    response = client.post("/api/agent-profiles/x", json={"llm_profile_ref": "y"})
    assert response.status_code == 503


def test_save_at_limit_returns_409(client, store, monkeypatch):
    monkeypatch.setattr(router_module, "MAX_AGENT_PROFILES", 1)
    store.save(OpenHandsAgentProfile(name="first", llm_profile_ref="x"))

    response = client.post("/api/agent-profiles/second", json={"llm_profile_ref": "y"})
    assert response.status_code == 409
    assert "limit" in response.json()["detail"].lower()


# ── 实现（解决空跑）────────────────────────────────────────────


@pytest.fixture
def temp_llm_profiles_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        llm_dir = Path(tmpdir) / "llm-profiles"
        llm_dir.mkdir(parents=True, exist_ok=True)
        yield llm_dir


@pytest.fixture
def client_with_llm_store(
    temp_agent_profiles_dir, temp_settings_dir, temp_llm_profiles_dir, monkeypatch
):
    """使用隔离的智能体-profile/settings/llm-profile 目录测试客户端，无密码。"""
    reset_stores()
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(temp_settings_dir))
    config = Config(static_files_path=None, session_api_keys=[], secret_key=None)
    app = create_app(config)

    def agent_profiles() -> AgentProfileStore:
        return AgentProfileStore(base_dir=temp_agent_profiles_dir)

    def llm_profiles() -> LLMProfileStore:
        return LLMProfileStore(base_dir=temp_llm_profiles_dir)

    with (
        patch(
            "openhands.agent_server.agent_profiles_router.get_agent_profile_store",
            agent_profiles,
        ),
        patch(
            "openhands.agent_server.agent_profiles_router.get_llm_profile_store",
            llm_profiles,
        ),
        patch("openhands.agent_server.launch.get_agent_profile_store", agent_profiles),
        patch("openhands.agent_server.launch.get_llm_profile_store", llm_profiles),
    ):
        yield TestClient(app)
    reset_stores()


@pytest.fixture
def llm_store(temp_llm_profiles_dir):
    return LLMProfileStore(base_dir=temp_llm_profiles_dir)


def test_materialize_valid_openhands_profile(client_with_llm_store, store, llm_store):
    """已解析 LLM 的有效 OpenHands 配置文件返回 200 + valid=True。"""
    llm_store.save("base-llm", LLM(model="gpt-4o"), include_secrets=True)
    store.save(OpenHandsAgentProfile(name="p", llm_profile_ref="base-llm"))

    response = client_with_llm_store.post("/api/agent-profiles/p/materialize")

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["agent_kind"] == "openhands"
    assert body["llm_profile_ref"] == "base-llm"
    assert body["llm_profile_resolved"] is True
    assert body["errors"] == []
    assert body["resolved_settings"] is not None
    assert body["dangling_mcp_server_refs"] == []


def test_materialize_rejects_an_unwrapped_draft(client_with_llm_store, store):
    store.save(OpenHandsAgentProfile(name="p", llm_profile_ref="base-llm"))

    response = client_with_llm_store.post(
        "/api/agent-profiles/p/materialize",
        json={"llm_profile_ref": "other", "tools": []},
    )

    assert response.status_code == 422


def test_materialize_valid_acp_profile(client_with_llm_store, store):
    """有效 ACP 配置文件返回 200 + valid=True（不需要 LLM 引用）。"""
    store.save(ACPAgentProfile(name="acp-p", acp_server="codex", acp_model="gpt-5.5"))

    response = client_with_llm_store.post("/api/agent-profiles/acp-p/materialize")

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["agent_kind"] == "acp"
    assert body["errors"] == []
    assert body["resolved_settings"] is not None


def test_materialize_dangling_llm_ref(client_with_llm_store, store):
    """引用缺失 LLM 配置文件的配置文件返回 200，有效=False。"""
    store.save(OpenHandsAgentProfile(name="p", llm_profile_ref="nonexistent"))

    response = client_with_llm_store.post("/api/agent-profiles/p/materialize")

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["llm_profile_ref"] == "nonexistent"
    assert body["llm_profile_resolved"] is False
    assert body["resolved_settings"] is None
    assert any("nonexistent" in e for e in body["errors"])


def test_materialize_dangling_mcp_ref(client_with_llm_store, store, llm_store):
    """缺少 MCP 服务器引用的配置文件返回 200，有效=False。"""
    llm_store.save("base-llm", LLM(model="gpt-4o"), include_secrets=True)
    store.save(
        OpenHandsAgentProfile(
            name="p",
            llm_profile_ref="base-llm",
            mcp_server_refs=["missing-server"],
        )
    )

    response = client_with_llm_store.post("/api/agent-profiles/p/materialize")

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["dangling_mcp_server_refs"] == ["missing-server"]
    assert body["resolved_settings"] is None


def test_materialize_reports_disabled_and_resolved_skills(
    client_with_llm_store, store, llm_store
):
    """物化试运行报告拒绝列表和已解决的集
    （目录减去禁用）。 目录中不存在的已禁用名称是无操作，并且不会使配置文件无效 - 拒
    绝列表无法悬挂 (#4017)。
    """
    from openhands.sdk.skills import Skill

    llm_store.save("base-llm", LLM(model="gpt-4o"), include_secrets=True)
    store.save(
        OpenHandsAgentProfile(
            name="p",
            llm_profile_ref="base-llm",
            disabled_skills=["beta", "not-in-catalog"],
        )
    )

    with patch(
        "openhands.agent_server.launch.discover_profile_skills",
        return_value=[
            Skill(name="alpha", content="x"),
            Skill(name="beta", content="y"),
        ],
    ):
        response = client_with_llm_store.post("/api/agent-profiles/p/materialize")

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["disabled_skills"] == ["beta", "not-in-catalog"]
    assert body["resolved_skills"] == ["alpha"]
    assert body["resolved_settings"] is not None


_BROWSER_PROBE = "openhands.agent_server.launch.is_tool_usable"
_DISCOVER = "openhands.agent_server.launch.discover_profile_skills"


def test_materialize_reports_the_tools_a_launch_would_build(
    client_with_llm_store, store, llm_store
):
    llm_store.save("base-llm", LLM(model="gpt-4o"), include_secrets=True)
    store.save(OpenHandsAgentProfile(name="p", llm_profile_ref="base-llm"))

    with (
        patch(_BROWSER_PROBE, return_value=True),
        patch(_DISCOVER, return_value=[]),
    ):
        body = client_with_llm_store.post("/api/agent-profiles/p/materialize").json()

    assert [t["name"] for t in body["resolved_settings"]["tools"]] == [
        "terminal",
        "file_editor",
        "task_tracker",
        "browser_tool_set",
        "switch_llm",
    ]


def test_materialize_evaluates_a_draft_without_saving_it(
    client_with_llm_store, store, llm_store
):
    llm_store.save("base-llm", LLM(model="gpt-4o"), include_secrets=True)
    draft = {
        "name": "ignored",
        "agent_kind": "openhands",
        "llm_profile_ref": "base-llm",
        "tools": [{"name": "glob"}],
    }

    with (
        patch(_BROWSER_PROBE, return_value=True),
        patch(_DISCOVER, return_value=[]),
    ):
        response = client_with_llm_store.post(
            "/api/agent-profiles/draft/materialize", json={"profile": draft}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert [t["name"] for t in body["resolved_settings"]["tools"]] == ["glob"]
    assert store.list() == []


def test_materialize_draft_takes_precedence_over_the_stored_profile(
    client_with_llm_store, store, llm_store
):
    llm_store.save("base-llm", LLM(model="gpt-4o"), include_secrets=True)
    store.save(OpenHandsAgentProfile(name="p", llm_profile_ref="base-llm"))

    with (
        patch(_DISCOVER, return_value=[]),
        patch(_BROWSER_PROBE, return_value=False),
    ):
        drafted = client_with_llm_store.post(
            "/api/agent-profiles/p/materialize",
            json={"profile": {"name": "p", "llm_profile_ref": "base-llm", "tools": []}},
        ).json()
        stored = client_with_llm_store.post(
            "/api/agent-profiles/p/materialize", json={}
        ).json()

    assert drafted["resolved_settings"]["tools"] == []
    assert [t["name"] for t in stored["resolved_settings"]["tools"]] == [
        "terminal",
        "file_editor",
        "task_tracker",
        "switch_llm",
    ]


def test_materialize_invalid_draft_returns_422(client_with_llm_store):
    response = client_with_llm_store.post(
        "/api/agent-profiles/p/materialize",
        json={
            "profile": {
                "name": "p",
                "llm_profile_ref": "base-llm",
                "tools": "terminal",
            }
        },
    )

    assert response.status_code == 422


def test_materialize_unknown_name_returns_404(client_with_llm_store):
    """实现未知的配置文件名称会返回 404。"""
    response = client_with_llm_store.post("/api/agent-profiles/ghost/materialize")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_materialize_no_raw_secrets_in_resolved_settings(
    client_with_llm_store, store, llm_store
):
    """resolved_settings 不得包含原始 API 键值。"""
    raw_key = "sk-secret-key-should-not-appear"

    llm_store.save(
        "base-llm",
        LLM(model="gpt-4o", api_key=SecretStr(raw_key)),
        include_secrets=True,
    )
    store.save(OpenHandsAgentProfile(name="p", llm_profile_ref="base-llm"))

    response = client_with_llm_store.post("/api/agent-profiles/p/materialize")

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert raw_key not in response.text


def test_materialize_migrates_an_old_draft_like_save(
    client_with_llm_store, store, llm_store
):
    llm_store.save("base-llm", LLM(model="gpt-4o"), include_secrets=True)
    draft = {
        "schema_version": 2,
        "agent_kind": "openhands",
        "llm_profile_ref": "base-llm",
        "enable_sub_agents": True,
    }

    with (
        patch(_BROWSER_PROBE, return_value=False),
        patch(_DISCOVER, return_value=[]),
    ):
        previewed = client_with_llm_store.post(
            "/api/agent-profiles/p/materialize", json={"profile": draft}
        )
        saved = client_with_llm_store.post("/api/agent-profiles/p", json=draft)

    assert previewed.status_code == 200
    assert saved.status_code == 201
    tools = [t["name"] for t in previewed.json()["resolved_settings"]["tools"]]
    assert "task_tool_set" in tools


def test_materialize_rejects_a_draft_newer_than_save_accepts(client_with_llm_store):
    draft = {
        "name": "p",
        "schema_version": 99,
        "agent_kind": "openhands",
        "llm_profile_ref": "x",
    }

    previewed = client_with_llm_store.post(
        "/api/agent-profiles/p/materialize", json={"profile": draft}
    )
    saved = client_with_llm_store.post("/api/agent-profiles/p", json=draft)

    assert previewed.status_code == 422
    assert saved.status_code == 422


def test_save_migrates_a_v2_profile_carrying_retired_switches(client):
    response = client.post(
        "/api/agent-profiles/v2-profile",
        json={
            "schema_version": 2,
            "agent_kind": "openhands",
            "llm_profile_ref": "default",
            "enable_sub_agents": False,
            "enable_switch_llm_tool": True,
        },
    )

    assert response.status_code == 201
    prof = client.get("/api/agent-profiles/v2-profile").json()["profile"]
    assert prof["tools"] is None
    assert "enable_sub_agents" not in prof
    assert "enable_switch_llm_tool" not in prof


def test_save_rejects_removed_tool_switches(client):
    response = client.post(
        "/api/agent-profiles/p",
        json={"llm_profile_ref": "default", "enable_switch_llm_tool": False},
    )

    assert response.status_code == 422


def test_save_rejects_params_on_a_parameterless_builtin(client):
    response = client.post(
        "/api/agent-profiles/p",
        json={
            "llm_profile_ref": "default",
            "tools": [{"name": "switch_llm", "params": {"a": 1}}],
        },
    )

    assert response.status_code == 422


def _tool_names(client, name: str) -> list[str]:
    prof = client.get(f"/api/agent-profiles/{name}").json()["profile"]
    return [tool["name"] for tool in prof["tools"] or []]


def test_saving_a_copy_under_a_new_name_keeps_its_tools(client):
    client.post("/api/agent-profiles/p", json={"llm_profile_ref": "default"})
    stored = client.get("/api/agent-profiles/p").json()["profile"]

    client.post(
        "/api/agent-profiles/copy",
        json={**stored, "tools": [{"name": "terminal"}, {"name": "glob"}]},
    )

    assert _tool_names(client, "copy") == ["terminal", "glob"]


def test_new_client_spreading_stale_switches_keeps_its_tools_edit(client):
    client.post(
        "/api/agent-profiles/p",
        json={
            "llm_profile_ref": "default",
            "tools": [{"name": "terminal"}, {"name": "switch_llm"}],
        },
    )
    stored = client.get("/api/agent-profiles/p").json()["profile"]

    client.post(
        "/api/agent-profiles/p",
        json={**stored, "tools": [{"name": "terminal"}, {"name": "task_tool_set"}]},
    )

    assert _tool_names(client, "p") == ["terminal", "task_tool_set"]


@pytest.mark.parametrize(
    ("tools", "valid"),
    [([{"name": "terminal"}], True), ([{"name": "not_a_registered_tool"}], False)],
)
def test_materialize_is_invalid_when_a_selected_tool_cannot_run(
    client_with_llm_store, llm_store, tools, valid
):
    llm_store.save("base-llm", LLM(model="gpt-4o"), include_secrets=True)
    draft = {"agent_kind": "openhands", "llm_profile_ref": "base-llm", "tools": tools}

    with patch(_DISCOVER, return_value=[]):
        response = client_with_llm_store.post(
            "/api/agent-profiles/p/materialize", json={"profile": draft}
        )

    assert response.status_code == 200
    assert response.json()["valid"] is valid
