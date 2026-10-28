import concurrent.futures
import json
import re
import threading
from pathlib import Path

import pytest
from pydantic import SecretStr

from openhands.sdk.llm import LLM, LLM_PROFILE_SCHEMA_VERSION
from openhands.sdk.llm.llm_profile_store import (
    LLMProfileStore,
    ProfileLimitExceeded,
)


@pytest.fixture
def profile_store(tmp_path: Path) -> LLMProfileStore:
    """使用临时目录创建配置文件存储。"""
    return LLMProfileStore(base_dir=tmp_path)


@pytest.fixture
def sample_llm() -> LLM:
    """创建示例 LLM 实例进行测试。"""
    return LLM(
        usage_id="test-llm",
        model="gpt-4-turbo",
        temperature=0.7,
        max_output_tokens=2000,
    )


@pytest.fixture
def sample_llm_with_secrets() -> LLM:
    """创建一个 LLM 实例机密用于测试。"""
    return LLM(
        usage_id="test-llm-secrets",
        model="gpt-4-turbo",
        temperature=0.5,
        api_key=SecretStr("secret-api-key-12345"),
    )


def test_init_creates_directory(tmp_path: Path) -> None:
    """测试初始化是否创建基目录。"""
    profile_dir = tmp_path / "profiles"
    assert not profile_dir.exists()

    LLMProfileStore(base_dir=profile_dir)

    assert profile_dir.exists()
    assert profile_dir.is_dir()


def test_init_with_string_path(tmp_path: Path) -> None:
    """使用字符串路径测试初始化​​。"""
    profile_dir = str(tmp_path / "profiles")
    store = LLMProfileStore(base_dir=profile_dir)

    assert store.base_dir == Path(profile_dir)
    assert store.base_dir.exists()


def test_init_with_path_object(tmp_path: Path) -> None:
    """使用 Path 对象测试初始化。"""
    profile_dir = tmp_path / "profiles"
    store = LLMProfileStore(base_dir=profile_dir)

    assert store.base_dir == profile_dir
    assert store.base_dir.exists()


def test_init_with_existing_directory(tmp_path: Path) -> None:
    """使用现有目录测试初始化​​。"""
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()

    store = LLMProfileStore(base_dir=profile_dir)

    assert store.base_dir == profile_dir


def test_list_empty_store(profile_store: LLMProfileStore) -> None:
    """在空商店中测试列出配置文件。"""
    profiles = profile_store.list()
    assert profiles == []


def test_list_with_profiles(profile_store: LLMProfileStore, sample_llm: LLM) -> None:
    """保存一些后测试列出配置文件。"""
    profile_store.save("profile1", sample_llm)
    profile_store.save("profile2", sample_llm)

    profiles = profile_store.list()

    assert len(profiles) == 2
    assert "profile1.json" in profiles
    assert "profile2.json" in profiles


def test_list_excludes_non_json_files(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    """测试 list() 仅返回 .JSON 个文件。"""
    profile_store.save("valid", sample_llm)

    # 创建非JSON文件
    (profile_store.base_dir / "not_a_profile.txt").write_text("hello")

    profiles = profile_store.list()

    assert profiles == ["valid.json"]


def test_save_creates_file(profile_store: LLMProfileStore, sample_llm: LLM) -> None:
    """测试保存会创建一个配置文件。"""
    profile_store.save("my_profile", sample_llm)

    profile_path = profile_store.base_dir / "my_profile.json"
    assert profile_path.exists()


def test_save_writes_profile_schema_version(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    profile_store.save("my_profile", sample_llm)

    profile_path = profile_store.base_dir / "my_profile.json"
    data = json.loads(profile_path.read_text())

    assert data["schema_version"] == LLM_PROFILE_SCHEMA_VERSION


def test_load_rejects_newer_profile_schema_version(
    profile_store: LLMProfileStore,
) -> None:
    profile_path = profile_store.base_dir / "future.json"
    profile_path.write_text(
        json.dumps(
            {"schema_version": LLM_PROFILE_SCHEMA_VERSION + 1, "model": "test-model"}
        )
    )

    with pytest.raises(ValueError, match="newer than supported"):
        profile_store.load("future")


def test_load_migrates_legacy_openhands_proxy_profile(
    profile_store: LLMProfileStore,
) -> None:
    profile_path = profile_store.base_dir / "legacy.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model": "litellm_proxy/claude-opus-5",
                "base_url": "https://llm-proxy.app.all-hands.dev/",
            }
        )
    )

    loaded = profile_store.load("legacy")

    assert loaded.model == "openhands/claude-opus-5"
    assert loaded.base_url is None


def test_list_summaries_migrates_legacy_openhands_proxy_profile(
    profile_store: LLMProfileStore,
) -> None:
    profile_path = profile_store.base_dir / "legacy.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model": "litellm_proxy/claude-opus-5",
                "base_url": "https://llm-proxy.app.all-hands.dev/",
            }
        )
    )

    summaries = profile_store.list_summaries()

    assert summaries == [
        {
            "name": "legacy",
            "model": "openhands/claude-opus-5",
            "base_url": None,
            "provider_connection_id": None,
            "provider_connection_broken": False,
            "api_key_set": False,
        }
    ]


def test_load_preserves_third_party_litellm_proxy_profile(
    profile_store: LLMProfileStore,
) -> None:
    profile_path = profile_store.base_dir / "custom.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model": "litellm_proxy/custom-alias",
                "base_url": "https://proxy.example.com/",
            }
        )
    )

    loaded = profile_store.load("custom")

    assert loaded.model == "litellm_proxy/custom-alias"
    assert loaded.base_url == "https://proxy.example.com/"


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".json",
        ".",
        "..",
        "my/profile",
        "my//profile",
        ".leading-dot",
        "-leading-dash",
        "_leading_under",
        "name with space",
        "name@symbol",
        "name$dollar",
        "a" * 65,
    ],
)
def test_save_with_invalid_profile_name(
    name: str, profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    with pytest.raises(ValueError, match=re.escape(f"Invalid profile name: {name!r}.")):
        profile_store.save(name, sample_llm)


def test_save_writes_valid_json(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    """测试保存的文件是否包含有效的 JSON。"""
    profile_store.save("my_profile", sample_llm)

    profile_path = profile_store.base_dir / "my_profile.json"
    content = profile_path.read_text()
    data = json.loads(content)

    assert data["model"] == "gpt-4-turbo"
    assert data["temperature"] == 0.7


def test_save_with_json_extension(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    """测试名称中带有 .JSON 扩展名的保存。"""
    profile_store.save("my_profile.json", sample_llm)

    # 不应创建 my_profile.json.json
    assert (profile_store.base_dir / "my_profile.json").exists()
    assert not (profile_store.base_dir / "my_profile.json.json").exists()


def test_save_overwrites_existing(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    """测试保存是否会覆盖现有配置文件。"""
    profile_store.save("my_profile", sample_llm)

    # 修改并再次保存
    modified_llm = LLM(
        usage_id="modified",
        model="gpt-3.5-turbo-16k",
        temperature=0.3,
    )
    profile_store.save("my_profile", modified_llm)

    # 加载并验证
    loaded = profile_store.load("my_profile")
    assert loaded.model == "gpt-3.5-turbo-16k"
    assert loaded.temperature == 0.3


def test_save_without_secrets(
    profile_store: LLMProfileStore, sample_llm_with_secrets: LLM
) -> None:
    """测试默认情况下不保存机密。"""
    profile_store.save("with_secrets", sample_llm_with_secrets)

    profile_path = profile_store.base_dir / "with_secrets.json"
    content = profile_path.read_text()

    # 机密应被屏蔽
    assert "secret-api-key-12345" not in content


def test_save_with_secrets(
    profile_store: LLMProfileStore, sample_llm_with_secrets: LLM
) -> None:
    """测试当include_secrets=True时机密是否被保存。"""
    profile_store.save("with_secrets", sample_llm_with_secrets, include_secrets=True)

    profile_path = profile_store.base_dir / "with_secrets.json"
    content = profile_path.read_text()

    # 机密应该存在
    assert "secret-api-key-12345" in content


@pytest.mark.parametrize("name", ["my_profile", "my_profile.json"])
def test_load_existing_profile(
    name: str, profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    """测试加载现有配置文件。"""
    profile_store.save(name, sample_llm)

    loaded = profile_store.load(name)

    assert loaded.usage_id == sample_llm.usage_id
    assert loaded.model == sample_llm.model
    assert loaded.temperature == sample_llm.temperature
    assert loaded.max_output_tokens == sample_llm.max_output_tokens


def test_load_nonexistent_profile(profile_store: LLMProfileStore) -> None:
    """测试加载不存在的配置文件。"""
    with pytest.raises(FileNotFoundError) as exc_info:
        profile_store.load("nonexistent")

    assert "nonexistent" in str(exc_info.value)
    assert "not found" in str(exc_info.value)


def test_load_nonexistent_shows_available(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    """测试错误消息是否显示可用的配置文件。"""
    profile_store.save("available1", sample_llm)
    profile_store.save("available2", sample_llm)

    with pytest.raises(FileNotFoundError) as exc_info:
        profile_store.load("nonexistent")

    error_msg = str(exc_info.value)
    assert "available1.json" in error_msg
    assert "available2.json" in error_msg


def test_load_corrupted_profile(profile_store: LLMProfileStore) -> None:
    """测试加载损坏的配置文件会引发 ValueError。"""
    # 创建损坏的配置文件
    profile_path = profile_store.base_dir / "corrupted.json"
    profile_path.write_text("{ invalid json }")

    with pytest.raises(ValueError) as exc_info:
        profile_store.load("corrupted")

    assert "Failed to load profile" in str(exc_info.value)
    assert "corrupted" in str(exc_info.value)


@pytest.mark.parametrize("name", ["to_delete", "to_delete.json"])
def test_delete_existing_profile(
    name: str, profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    """测试删除现有配置文件。"""
    profile_store.save(name, sample_llm)
    profile_filename = f"{name}.json" if not name.endswith(".json") else name
    assert profile_filename in profile_store.list()

    profile_store.delete(name)
    assert profile_filename not in profile_store.list()


def test_delete_nonexistent_profile(profile_store: LLMProfileStore) -> None:
    """测试删除不存在的配置文件不会引发错误。"""
    profile_store.delete("nonexistent")


def test_concurrent_saves(tmp_path: Path) -> None:
    """测试并发保存不会损坏数据。"""
    store = LLMProfileStore(base_dir=tmp_path)
    num_threads = 10
    results: list[int] = []
    errors: list[tuple[int, Exception]] = []

    def save_profile(index: int) -> None:
        try:
            llm = LLM(
                usage_id=f"test-{index}",
                model=f"model-{index}",
                temperature=0.1 * index,
            )
            store.save(f"profile_{index}", llm)
            results.append(index)
        except Exception as e:
            errors.append((index, e))

    threads = [
        threading.Thread(target=save_profile, args=(i,)) for i in range(num_threads)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert len(results) == num_threads

    # 验证所有配置文件均已正确保存
    profiles = store.list()
    assert len(profiles) == num_threads


def test_concurrent_reads_and_writes(tmp_path: Path) -> None:
    """测试并发读取和写入不会导致问题。"""
    store = LLMProfileStore(base_dir=tmp_path)

    # 预先创建一些配置文件
    for i in range(5):
        llm = LLM(usage_id=f"test-{i}", model=f"model-{i}")
        store.save(f"profile_{i}", llm)

    errors: list[tuple[str, str | int, Exception]] = []
    read_results: list[str] = []
    write_results: list[int] = []

    def read_profile(name: str) -> None:
        try:
            loaded = store.load(name)
            read_results.append(loaded.model)
        except Exception as e:
            errors.append(("read", name, e))

    def write_profile(index: int) -> None:
        try:
            llm = LLM(usage_id=f"new-{index}", model=f"new-model-{index}")
            store.save(f"new_profile_{index}", llm)
            write_results.append(index)
        except Exception as e:
            errors.append(("write", index, e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        # 提交阅读任务
        for i in range(5):
            futures.append(executor.submit(read_profile, f"profile_{i}"))
        # 提交写任务
        for i in range(5):
            futures.append(executor.submit(write_profile, i))

        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert len(read_results) == 5
    assert len(write_results) == 5


def test_full_workflow(profile_store: LLMProfileStore) -> None:
    """测试完整的保存-列表-加载-删除工作流程。"""
    llm = LLM(
        usage_id="workflow-test",
        model="claude-3-opus",
        temperature=0.8,
        max_output_tokens=4096,
    )

    # 保存
    profile_store.save("workflow_profile", llm)

    # 列表
    profiles = profile_store.list()
    assert "workflow_profile.json" in profiles

    # 负载
    loaded = profile_store.load("workflow_profile")
    assert loaded.usage_id == llm.usage_id
    assert loaded.model == llm.model
    assert loaded.temperature == llm.temperature
    assert loaded.max_output_tokens == llm.max_output_tokens

    # 删除
    profile_store.delete("workflow_profile")
    assert "workflow_profile.json" not in profile_store.list()


# ── 重命名────────────────────────────────────────────────────────────────


def test_rename_moves_file(profile_store: LLMProfileStore, sample_llm: LLM) -> None:
    profile_store.save("old", sample_llm)
    profile_store.rename("old", "new")

    assert (profile_store.base_dir / "new.json").exists()
    assert not (profile_store.base_dir / "old.json").exists()
    assert profile_store.load("new").model == sample_llm.model


def test_rename_preserves_secrets(
    profile_store: LLMProfileStore, sample_llm_with_secrets: LLM
) -> None:
    profile_store.save("old", sample_llm_with_secrets, include_secrets=True)
    profile_store.rename("old", "new")

    loaded = profile_store.load("new")
    assert isinstance(loaded.api_key, SecretStr)
    assert loaded.api_key.get_secret_value() == "secret-api-key-12345"


def test_rename_source_missing_raises(profile_store: LLMProfileStore) -> None:
    with pytest.raises(FileNotFoundError, match="missing"):
        profile_store.rename("missing", "anywhere")


def test_rename_target_exists_raises(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    profile_store.save("old", sample_llm)
    profile_store.save("taken", sample_llm)

    with pytest.raises(FileExistsError, match="taken"):
        profile_store.rename("old", "taken")

    # 两个文件仍然存在（无部分状态）
    assert (profile_store.base_dir / "old.json").exists()
    assert (profile_store.base_dir / "taken.json").exists()


def test_rename_same_name_is_noop(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    profile_store.save("same", sample_llm)
    profile_store.rename("same", "same")
    assert profile_store.list() == ["same.json"]


def test_rename_same_name_missing_raises(profile_store: LLMProfileStore) -> None:
    """同名重命名仍会验证配置文件是否存在。"""
    with pytest.raises(FileNotFoundError, match="ghost"):
        profile_store.rename("ghost", "ghost")


def test_rename_invalid_name_raises(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    profile_store.save("ok", sample_llm)
    with pytest.raises(ValueError, match="Invalid profile name"):
        profile_store.rename("ok", "../escape")
    with pytest.raises(ValueError, match="Invalid profile name"):
        profile_store.rename(".hidden", "ok2")


# ── list_summaries ────────────────────────────────────────────────────────


def test_list_summaries_empty(profile_store: LLMProfileStore) -> None:
    assert profile_store.list_summaries() == []


def test_list_summaries_returns_metadata(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    profile_store.save("a", sample_llm)
    profile_store.save("b", sample_llm)

    summaries = profile_store.list_summaries()
    assert len(summaries) == 2
    by_name = {s["name"]: s for s in summaries}
    assert by_name["a"]["model"] == sample_llm.model
    assert by_name["a"]["base_url"] == sample_llm.base_url
    assert by_name["a"]["api_key_set"] is False


def test_list_summaries_api_key_set_with_secrets(
    profile_store: LLMProfileStore, sample_llm_with_secrets: LLM
) -> None:
    profile_store.save("with_key", sample_llm_with_secrets, include_secrets=True)

    [summary] = profile_store.list_summaries()
    assert summary["api_key_set"] is True


def test_list_summaries_api_key_redacted_means_not_set(
    profile_store: LLMProfileStore, sample_llm_with_secrets: LLM
) -> None:
    """不带机密保存的配置文件会将“**********”存储在磁盘上； 不是“设置”。"""
    profile_store.save("no_key", sample_llm_with_secrets, include_secrets=False)

    [summary] = profile_store.list_summaries()
    assert summary["api_key_set"] is False


def test_list_summaries_skips_corrupted(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    profile_store.save("good", sample_llm)
    (profile_store.base_dir / "bad.json").write_text("{ not valid json")

    summaries = profile_store.list_summaries()
    assert [s["name"] for s in summaries] == ["good"]


def test_list_summaries_skips_non_dict(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    """顶级值不是对象的 JSON 文件将被跳过，而不是引发。"""
    profile_store.save("good", sample_llm)
    (profile_store.base_dir / "list.json").write_text("[1, 2, 3]")
    (profile_store.base_dir / "string.json").write_text('"plain"')

    summaries = profile_store.list_summaries()
    assert [s["name"] for s in summaries] == ["good"]


def test_list_summaries_skips_invalid_filename(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    """名称与 PROFILE_NAME_REGEX 不匹配的文件将被跳过。"""
    profile_store.save("good", sample_llm)
    (profile_store.base_dir / ".hidden.json").write_text('{"model": "x"}')
    (profile_store.base_dir / "bad@name.json").write_text('{"model": "x"}')

    summaries = profile_store.list_summaries()
    assert [s["name"] for s in summaries] == ["good"]


# ── 以max_profiles保存──────────────────────────────────────────────────


def test_save_with_max_profiles_blocks_over_limit(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    profile_store.save("a", sample_llm)
    profile_store.save("b", sample_llm)

    with pytest.raises(ProfileLimitExceeded, match="2"):
        profile_store.save("c", sample_llm, max_profiles=2)


def test_save_with_max_profiles_allows_overwrite(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    """即使达到限制，也允许覆盖现有配置文件。"""
    profile_store.save("a", sample_llm)
    profile_store.save("b", sample_llm)

    profile_store.save("a", sample_llm, max_profiles=2)
    assert len(profile_store.list()) == 2


def test_save_with_max_profiles_allows_under_limit(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    profile_store.save("a", sample_llm, max_profiles=5)
    profile_store.save("b", sample_llm, max_profiles=5)
    assert len(profile_store.list()) == 2


def test_save_cleans_up_tmp_on_replace_failure(
    profile_store: LLMProfileStore,
    sample_llm: LLM,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """如果 Path.replace 失败，则不应留下任何 .tmp 文件。"""

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", boom)

    with pytest.raises(OSError, match="disk full"):
        profile_store.save("doomed", sample_llm)

    leftovers = list(profile_store.base_dir.glob("*.tmp"))
    assert leftovers == []


def test_save_with_max_profiles_ignores_invalid_filenames(
    profile_store: LLMProfileStore, sample_llm: LLM
) -> None:
    """具有无效名称的流浪 .JSON 文件不得占用限制槽。"""
    profile_store.save("real", sample_llm)
    (profile_store.base_dir / ".hidden.json").write_text('{"model": "x"}')
    (profile_store.base_dir / "bad@name.json").write_text('{"model": "x"}')

    # 只有“真实”才算数，因此保存到 2 的限制应该会成功。
    profile_store.save("another", sample_llm, max_profiles=2)
    assert "another.json" in profile_store.list()


def test_list_summaries_does_not_mutate_env(
    profile_store: LLMProfileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """列表摘要不得运行 LLM 验证器（设置环境变量）。"""
    llm = LLM(
        usage_id="t",
        model="bedrock/test",
        aws_access_key_id="from-profile",
    )
    profile_store.save("aws", llm, include_secrets=True)

    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    profile_store.list_summaries()

    import os

    assert os.environ.get("AWS_ACCESS_KEY_ID") is None


# ── 杂项──────────────────────────────────────────────────────────────────


def test_multiple_profiles(profile_store: LLMProfileStore) -> None:
    """测试管理多个配置文件。"""
    profiles_data = [
        ("gpt4", "gpt-4-turbo", 0.7),
        ("gpt35", "gpt-3.5-turbo-16k", 0.5),
        ("claude", "claude-3-opus", 0.9),
    ]

    # 全部保存
    for name, model, temp in profiles_data:
        llm = LLM(usage_id=name, model=model, temperature=temp)
        profile_store.save(name, llm)

    # 验证全部存在
    stored = profile_store.list()
    assert len(stored) == 3

    # 加载并验证每个
    for name, expected_model, expected_temp in profiles_data:
        loaded = profile_store.load(name)
        assert loaded.model == expected_model
        assert loaded.temperature == expected_temp

    # 删除一个
    profile_store.delete("gpt4")
    assert len(profile_store.list()) == 2
    assert "gpt4.json" not in profile_store.list()


def test_default_provider_store_is_sibling_of_base_dir(tmp_path: Path) -> None:
    """自定义目录配置文件存储在其自己的 base_dir 下解析连接。

    Regression: 默认 ProviderConnectionStore 必须源自
    ``base_dir``（同级 ``provider-connections`` 目录），不是来自
    ``$HOME``. 否则，自定义目录配置文件存储将从中读取配置文件
    ``base_dir`` 但来自 ``~/.openhands`` 的凭据 — 来源错误。
    """
    from openhands.sdk.llm.provider_connection_store import (
        ProviderConnection,
        ProviderConnectionStore,
    )

    store = LLMProfileStore(base_dir=tmp_path)

    provider_store = store._provider_store
    assert provider_store is not None
    assert provider_store.base_dir == tmp_path.parent / "provider-connections"
    assert Path.home() not in provider_store.base_dir.parents

    connections = ProviderConnectionStore(
        base_dir=tmp_path.parent / "provider-connections"
    )
    now = 1_000
    connections.create(
        ProviderConnection(
            id="conn1",
            display_name="Anthropic",
            provider="anthropic",
            api_key=SecretStr("sk-shared"),
            created_at=now,
            updated_at=now,
        )
    )
    llm = LLM(
        usage_id="linked",
        model="anthropic/claude-sonnet-4",
        provider_connection_id="conn1",
    )
    store.save("linked", llm)

    resolved = store.load("linked")
    assert isinstance(resolved.api_key, SecretStr)
    assert resolved.api_key.get_secret_value() == "sk-shared"
