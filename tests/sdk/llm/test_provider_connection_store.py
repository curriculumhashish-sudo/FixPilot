"""测试 for ProviderConnectionStore 及其分辨率在 LLMProfileStore."""

import json
import time

import pytest
from pydantic import SecretStr

from openhands.sdk.llm import LLM
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.llm.provider_connection_store import (
    PROVIDER_CONNECTIONS_SCHEMA_VERSION,
    ProviderConnection,
    ProviderConnectionNotFound,
    ProviderConnectionStore,
)
from openhands.sdk.utils.cipher import Cipher


def _connection(**overrides) -> ProviderConnection:
    now = int(time.time())
    data = {
        "id": "conn1",
        "display_name": "Anthropic",
        "provider": "anthropic",
        "api_key": "sk-shared",
        "base_url": "https://api.anthropic.com",
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return ProviderConnection(**data)


def test_provider_connection_not_found_is_value_error():
    """智能体-服务器依赖于这个子类，所以通用 ``ValueError``
    处理程序（OpenAI 网关、配置文件解析器）将悬空引用降级为 4xx，而不是不透明的 500。
    """
    assert issubclass(ProviderConnectionNotFound, ValueError)


def test_crud_roundtrip(tmp_path):
    store = ProviderConnectionStore(base_dir=tmp_path)
    assert store.list() == []

    store.create(_connection())
    got = store.get("conn1")
    assert got is not None
    assert got.api_key_value() == "sk-shared"

    store.update(_connection(display_name="Renamed", api_key="sk-new"))
    renamed = store.get("conn1")
    assert renamed is not None
    assert renamed.display_name == "Renamed"
    assert renamed.api_key_value() == "sk-new"

    store.delete("conn1")
    assert store.get("conn1") is None
    with pytest.raises(ProviderConnectionNotFound):
        store.delete("conn1")


def test_api_key_encrypted_at_rest(tmp_path):
    cipher = Cipher("unit-test-secret-key")
    store = ProviderConnectionStore(base_dir=tmp_path)
    store.create(_connection(), cipher=cipher)

    raw = json.loads((tmp_path / "provider_connections.json").read_text())
    stored_key = raw["connections"][0]["api_key"]
    assert stored_key != "sk-shared"  # 不是明文
    assert raw["schema_version"] == PROVIDER_CONNECTIONS_SCHEMA_VERSION

    # 使用相同的密码往返返回明文。
    loaded = store.get("conn1", cipher=cipher)
    assert loaded is not None
    assert loaded.api_key_value() == "sk-shared"


def test_corrupted_file_raises_not_clobbers(tmp_path):
    path = tmp_path / "provider_connections.json"
    path.write_text("{ not valid json")
    store = ProviderConnectionStore(base_dir=tmp_path)
    with pytest.raises(ValueError):
        store.list()
    # 损坏的文件原封不动地保留下来，而不是默默地被替换。
    assert path.read_text() == "{ not valid json"


# ── LLMProfileStore 的解决方案 ──────────────────────────────────────────


def test_load_without_provider_is_unchanged(tmp_path):
    """规则 1/4：无提供者引用 -> 字节相同的旧行为。"""
    store = LLMProfileStore(base_dir=tmp_path / "profiles")
    store.save("p", LLM(model="gpt-4o", api_key="sk-own"), include_secrets=True)
    llm = store.load("p")
    assert isinstance(llm.api_key, SecretStr)
    assert llm.api_key.get_secret_value() == "sk-own"


def test_save_clears_inline_credentials_when_linked(tmp_path):
    """规则 5c：链接的配置文件不保留内联 api_key / base_url。"""
    provider = ProviderConnectionStore(base_dir=tmp_path / "conns")
    profiles = LLMProfileStore(base_dir=tmp_path / "profiles", provider_store=provider)
    profiles.save(
        "p",
        LLM(
            model="anthropic/claude-sonnet-4",
            api_key="sk-should-be-dropped",
            base_url="https://should.drop",
            provider_connection_id="conn1",
        ),
        include_secrets=True,
    )
    raw = json.loads((tmp_path / "profiles" / "p.json").read_text())
    assert raw.get("api_key") in (None, "")
    assert raw.get("base_url") is None
    assert raw["provider_connection_id"] == "conn1"


def test_load_resolves_provider_credentials(tmp_path):
    """规则 5：连接 api_key / base_url 在负载时应用（使用时读取）。"""
    provider = ProviderConnectionStore(base_dir=tmp_path / "conns")
    provider.create(_connection())
    profiles = LLMProfileStore(base_dir=tmp_path / "profiles", provider_store=provider)
    profiles.save(
        "p",
        LLM(model="anthropic/claude-sonnet-4", provider_connection_id="conn1"),
    )

    llm = profiles.load("p")
    assert isinstance(llm.api_key, SecretStr)
    assert llm.api_key.get_secret_value() == "sk-shared"
    assert llm.base_url == "https://api.anthropic.com"

    # 旋转在下一次加载时生效，不缓存任何内容。
    provider.update(_connection(api_key="sk-rotated"))
    rotated = profiles.load("p")
    assert isinstance(rotated.api_key, SecretStr)
    assert rotated.api_key.get_secret_value() == "sk-rotated"


def test_load_base_url_authoritative_including_none(tmp_path):
    provider = ProviderConnectionStore(base_dir=tmp_path / "conns")
    provider.create(_connection(base_url=None))
    profiles = LLMProfileStore(base_dir=tmp_path / "profiles", provider_store=provider)
    profiles.save(
        "p",
        LLM(
            model="openai/gpt-5.5",
            base_url="https://profile.example",
            provider_connection_id="conn1",
        ),
    )
    assert profiles.load("p").base_url is None


def test_load_missing_connection_raises(tmp_path):
    """规则 5b：没有内联键的悬空引用会严重失败。"""
    provider = ProviderConnectionStore(base_dir=tmp_path / "conns")
    profiles = LLMProfileStore(base_dir=tmp_path / "profiles", provider_store=provider)
    profiles.save(
        "p",
        LLM(model="anthropic/claude-sonnet-4", provider_connection_id="ghost"),
    )
    with pytest.raises(ProviderConnectionNotFound):
        profiles.load("p")

    # resolve_provider=False inspects the stored profile without resolving.
    llm = profiles.load("p", resolve_provider=False)
    assert llm.provider_connection_id == "ghost"


def test_list_summaries_reports_linked_key_presence(tmp_path):
    provider = ProviderConnectionStore(base_dir=tmp_path / "conns")
    provider.create(_connection())
    profiles = LLMProfileStore(base_dir=tmp_path / "profiles", provider_store=provider)
    profiles.save(
        "p",
        LLM(model="anthropic/claude-sonnet-4", provider_connection_id="conn1"),
    )
    summary = profiles.list_summaries()[0]
    assert summary["provider_connection_id"] == "conn1"
    assert summary["api_key_set"] is True
    assert summary["provider_connection_broken"] is False


def test_list_summaries_marks_broken_when_connection_deleted(tmp_path):
    """Fix (enyst): 删除提供者连接必须表现为
    ``provider_connection_broken=True`` 在引用它的每个配置文件上，因此 UI 可以显示“损
    坏的链接”指示器，而不是在激活时默默失败。
    """
    provider = ProviderConnectionStore(base_dir=tmp_path / "conns")
    provider.create(_connection())
    profiles = LLMProfileStore(base_dir=tmp_path / "profiles", provider_store=provider)
    profiles.save(
        "p", LLM(model="anthropic/claude-sonnet-4", provider_connection_id="conn1")
    )

    # 删除前确认没有损坏。
    assert profiles.list_summaries()[0]["provider_connection_broken"] is False

    # 删除连接； 磁盘上的配置文件仍然引用它。
    provider.delete("conn1")

    summary = profiles.list_summaries()[0]
    assert summary["provider_connection_broken"] is True
    assert summary["provider_connection_id"] == "conn1"
    # api_key_set 也必须是 False（无内联键，无连接）。
    assert summary["api_key_set"] is False


def test_bare_profile_store_auto_wires_provider_store(tmp_path):
    """Fix: bare LLMProfileStore() 自动创建了一个 ProviderConnectionStore 所以
    独立的 SDK 路径（LocalConversation、FallbackStrategy、switch_llm）可以解析智能体
    服务器保存的链接配置文件。

    自动装配的商店位于  ``provider-connections`` 目录兄弟节点到 [profile store] 的
    ``base_dir`` （不在范围内）
     ``$HOME``), 因此，自定义目录存储读取其凭据从同一位置。
    """
    # 自动连接的提供者存储是 base_dir 的同级。
    provider = ProviderConnectionStore(base_dir=tmp_path / "provider-connections")
    provider.create(_connection())

    # 仅使用 base_dir 进行构造 — 无显式 provider_store 参数。
    profiles = LLMProfileStore(base_dir=tmp_path / "profiles")
    profiles.save("p", LLM(model="gpt-4o", provider_connection_id="conn1"))

    llm = profiles.load("p")
    assert isinstance(llm.api_key, SecretStr)
    assert llm.api_key.get_secret_value() == "sk-shared"
    assert llm.base_url == "https://api.anthropic.com"


def test_wrong_cipher_update_raises_not_destroys_key(tmp_path):
    """Fix: 密码错误的读取-修改-写入必须引发 ValidationError，
    不要默默地持久化api_key=null并销毁存储的密文。"""
    from pydantic import ValidationError

    cipher_a = Cipher("key-a")
    cipher_b = Cipher("key-b")
    store = ProviderConnectionStore(base_dir=tmp_path)
    store.create(_connection(), cipher=cipher_a)

    # 在任何写入之前尝试使用错误的密码进行更新必定会失败。
    with pytest.raises((ValidationError, ValueError)):
        store.update(_connection(display_name="updated"), cipher=cipher_b)

    # 存储的密钥必须仍然完好无损——可以用原始密码读取。
    restored = store.get("conn1", cipher=cipher_a)
    assert restored is not None
    assert restored.api_key_value() == "sk-shared"
