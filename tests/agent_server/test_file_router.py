"""测试 file_router.py 端点。"""

import asyncio
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, unquote
from uuid import UUID, uuid4

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from openhands.agent_server import (
    bash_service as bash_mod,
    conversation_service as cs_mod,
    file_router as file_router_module,
)
from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config
from openhands.agent_server.file_router import ARCHIVE_MANIFEST_NAME, _upload_file
from openhands.sdk.utils.pydantic_secrets import REDACTED_SECRET_VALUE


@pytest.fixture
def client():
    """为没有身份验证的 FastAPI 应用程序创建一个测试客户端。"""
    config = Config(session_api_keys=[])  # 禁用身份验证
    return TestClient(create_app(config), raise_server_exceptions=False)


@pytest.fixture
def temp_file(tmp_path):
    """创建一个临时文件用于下载测试。"""
    test_file = tmp_path / "test_download.txt"
    test_file.write_text("test file content")
    return test_file


# =============================================================================
# 上传测试 - 查询参数（首选方法）
# =============================================================================


def test_upload_file_query_param_success(client, tmp_path):
    """使用查询参数测试文件上传是否成功。"""
    target_path = tmp_path / "uploaded_file.txt"
    file_content = b"test content for upload"

    response = client.post(
        "/api/file/upload",
        params={"path": str(target_path)},
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "file_size": len(file_content)}
    assert target_path.exists()
    assert target_path.read_bytes() == file_content


def test_upload_file_query_param_creates_parent_dirs(client, tmp_path):
    """测试上传是否创建父目录（如果不存在）。"""
    target_path = tmp_path / "nested" / "dirs" / "file.txt"
    file_content = b"nested file content"

    response = client.post(
        "/api/file/upload",
        params={"path": str(target_path)},
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
    )

    assert response.status_code == 200
    assert target_path.exists()
    assert target_path.read_bytes() == file_content


def test_upload_file_query_param_relative_path_fails(client):
    """测试使用相对路径上传返回400。"""
    response = client.post(
        "/api/file/upload",
        params={"path": "relative/path/file.txt"},
        files={"file": ("test.txt", io.BytesIO(b"content"), "text/plain")},
    )

    assert response.status_code == 400
    assert "must be absolute" in response.json()["detail"]


@pytest.mark.parametrize(
    ("relative_target", "detail"),
    [
        ("is-a-dir", "Path is a directory"),
        ("a-file.txt/child.txt", "A parent of the path is not a directory"),
        ("a-file.txt/nested/child.txt", "A parent of the path is not a directory"),
    ],
)
def test_upload_onto_directory_or_under_file_is_400(
    client, tmp_path, relative_target, detail
):
    """上传到目录上，或文件下，是调用者的路径错误。"""
    (tmp_path / "is-a-dir").mkdir()
    (tmp_path / "a-file.txt").write_bytes(b"keep me")

    response = client.post(
        "/api/file/upload",
        params={"path": str(tmp_path / relative_target)},
        files={"file": ("test.txt", io.BytesIO(b"content"), "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == detail
    assert (tmp_path / "is-a-dir").is_dir()
    assert (tmp_path / "a-file.txt").read_bytes() == b"keep me"


def test_upload_file_query_param_missing_path(client):
    """测试不带路径参数上传返回422。"""
    response = client.post(
        "/api/file/upload",
        files={"file": ("test.txt", io.BytesIO(b"content"), "text/plain")},
    )

    assert response.status_code == 422


def test_upload_file_query_param_missing_file(client, tmp_path):
    """测试无文件上传返回422。"""
    target_path = tmp_path / "missing_file.txt"

    response = client.post(
        "/api/file/upload",
        params={"path": str(target_path)},
    )

    assert response.status_code == 422


# =============================================================================
# 下载测试 - 查询参数（首选方法）
# =============================================================================


def test_download_file_query_param_success(client, temp_file):
    """使用查询参数测试文件下载是否成功。"""
    response = client.get(
        "/api/file/download",
        params={"path": str(temp_file)},
    )

    assert response.status_code == 200
    assert response.content == b"test file content"
    assert response.headers["content-type"] == "application/octet-stream"


def test_download_file_query_param_not_found(client, tmp_path):
    """测试下载返回404，因为文件不存在。"""
    nonexistent_path = tmp_path / "nonexistent.txt"

    response = client.get(
        "/api/file/download",
        params={"path": str(nonexistent_path)},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_download_file_query_param_relative_path_fails(client):
    """测试使用相对路径下载返回400。"""
    response = client.get(
        "/api/file/download",
        params={"path": "relative/path/file.txt"},
    )

    assert response.status_code == 400
    assert "must be absolute" in response.json()["detail"]


def test_download_file_query_param_directory_fails(client, tmp_path):
    """测试目录下载返回400。"""
    response = client.get(
        "/api/file/download",
        params={"path": str(tmp_path)},
    )

    assert response.status_code == 400
    assert "not a file" in response.json()["detail"]


def test_download_file_query_param_missing_path(client):
    """测试不带路径参数下载返回422。"""
    response = client.get("/api/file/download")

    assert response.status_code == 422


# =============================================================================
# 创建目录测试 - POST /api/file/create_directory
# =============================================================================


def test_create_directory_success(client, tmp_path):
    """测试目录创建是否成功。"""
    target_path = tmp_path / "new_directory"

    response = client.post(
        "/api/file/create_directory",
        params={"path": str(target_path)},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert target_path.is_dir()


def test_create_directory_creates_missing_parents(client, tmp_path):
    """测试是否创建了中间目录。"""
    target_path = tmp_path / "parent" / "child" / "grandchild"

    response = client.post(
        "/api/file/create_directory",
        params={"path": str(target_path)},
    )

    assert response.status_code == 200
    assert target_path.is_dir()


def test_create_directory_existing_directory_succeeds(client, tmp_path):
    """测试创建现有目录是否幂等。"""
    target_path = tmp_path / "already_here"
    target_path.mkdir()
    (target_path / "keep.txt").write_text("untouched")

    response = client.post(
        "/api/file/create_directory",
        params={"path": str(target_path)},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert (target_path / "keep.txt").read_text() == "untouched"


def test_create_directory_relative_path_fails(client):
    """测试使用相对路径创建返回 400。"""
    response = client.post(
        "/api/file/create_directory",
        params={"path": "relative/path/dir"},
    )

    assert response.status_code == 400
    assert "must be absolute" in response.json()["detail"]


def test_create_directory_existing_file_fails(client, tmp_path):
    """测试在现有文件上创建是否返回 400，而不是 500。"""
    target_path = tmp_path / "a_file.txt"
    target_path.write_text("do not clobber me")

    response = client.post(
        "/api/file/create_directory",
        params={"path": str(target_path)},
    )

    assert response.status_code == 400
    assert "not a directory" in response.json()["detail"].lower()
    assert target_path.read_text() == "do not clobber me"


@pytest.mark.skipif(
    getattr(os, "geteuid", lambda: -1)() == 0,
    reason="root bypasses directory write permissions",
)
def test_create_directory_permission_denied(client, tmp_path):
    """测试不可写的父级返回 403。"""
    parent = tmp_path / "readonly"
    parent.mkdir()
    parent.chmod(0o500)
    try:
        response = client.post(
            "/api/file/create_directory",
            params={"path": str(parent / "child")},
        )

        assert response.status_code == 403
        assert "permission denied" in response.json()["detail"].lower()
    finally:
        parent.chmod(0o700)


def test_create_directory_missing_path(client):
    """测试不带路径参数的创建返回 422。"""
    response = client.post("/api/file/create_directory")

    assert response.status_code == 422


# =============================================================================
# 边缘情况测试
# =============================================================================


def test_upload_large_file_chunked(client, tmp_path):
    """测试大文件是否正确上传（分块读取）。"""
    target_path = tmp_path / "large_file.bin"
    # 创建大于 8KB 块大小的文件
    large_content = b"x" * (8192 * 3 + 100)  # 约24.5KB

    response = client.post(
        "/api/file/upload",
        params={"path": str(target_path)},
        files={
            "file": ("large.bin", io.BytesIO(large_content), "application/octet-stream")
        },
    )

    assert response.status_code == 200
    assert response.json()["file_size"] == len(large_content)
    assert target_path.exists()
    assert target_path.read_bytes() == large_content


def test_upload_overwrites_existing_file(client, tmp_path):
    """测试上传到现有路径是否会覆盖文件。"""
    target_path = tmp_path / "existing.txt"
    target_path.write_text("original content")

    new_content = b"new content"
    response = client.post(
        "/api/file/upload",
        params={"path": str(target_path)},
        files={"file": ("test.txt", io.BytesIO(new_content), "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["file_size"] == len(new_content)
    assert target_path.read_bytes() == new_content


def test_download_preserves_filename(client, tmp_path):
    """测试下载响应是否包含正确的文件名。"""
    test_file = tmp_path / "my_document.pdf"
    test_file.write_bytes(b"pdf content")

    response = client.get(
        "/api/file/download",
        params={"path": str(test_file)},
    )

    assert response.status_code == 200
    assert "my_document.pdf" in response.headers.get("content-disposition", "")


def test_upload_file_with_special_characters_in_path(client, tmp_path):
    """使用路径中的特殊字符测试上传（通过查询参数）。"""
    target_path = tmp_path / "file with spaces.txt"
    file_content = b"content with special path"

    response = client.post(
        "/api/file/upload",
        params={"path": str(target_path)},
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
    )

    assert response.status_code == 200
    assert target_path.exists()
    assert target_path.read_bytes() == file_content


def _use_conversations_path(client, conversations_path: Path) -> None:
    """将应用程序的请求时间配置指向 ``conversations_path``。

    轨迹下载解析对话目录
    ``request.app.state.config`` — 在延迟初始化服务器上​​替换相同的配置
    ``POST /api/init``。
    """
    client.app.state.config = Config(
        session_api_keys=[], conversations_path=conversations_path
    )


def test_download_trajectory_uses_python_zipfile(client, monkeypatch, tmp_path):
    """轨迹下载不应依赖于操作系统级别的 zip 命令。"""
    conversations_path = tmp_path / "conversations"
    conversation_id = uuid4()
    conversation_dir = conversations_path / conversation_id.hex
    nested_dir = conversation_dir / "nested"
    nested_dir.mkdir(parents=True)
    (conversation_dir / "meta.json").write_text("{}")
    (nested_dir / "event.json").write_text('{"id": "event-1"}')

    _use_conversations_path(client, conversations_path)

    async def fail_if_shell_zip_is_used(*_args, **_kwargs):
        raise AssertionError("download_trajectory must not shell out to zip")

    monkeypatch.setattr(
        file_router_module,
        "bash_event_service",
        SimpleNamespace(start_bash_command=fail_if_shell_zip_is_used),
        raising=False,
    )

    response = client.get(f"/api/file/download-trajectory/{conversation_id}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.read(f"{conversation_id.hex}/meta.json") == b"{}"
        assert archive.read(f"{conversation_id.hex}/nested/event.json") == (
            b'{"id": "event-1"}'
        )

    assert not (conversations_path / f"{conversation_id.hex}.zip").exists()


def test_download_trajectory_omits_acp_credential_dir(client, monkeypatch, tmp_path):
    conversations_path = tmp_path / "conversations"
    conversation_id = uuid4()
    conversation_dir = conversations_path / conversation_id.hex
    acp_dir = conversation_dir / "acp" / "codex"
    acp_dir.mkdir(parents=True)
    (conversation_dir / "meta.json").write_text("{}")
    (conversation_dir / "acp_notes.json").write_text("{}")
    (acp_dir / "auth.json").write_text('{"refresh_token": "rt-secret-123"}')

    _use_conversations_path(client, conversations_path)

    response = client.get(f"/api/file/download-trajectory/{conversation_id}")
    assert response.status_code == 200

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        blob = b"\n".join(archive.read(n) for n in names if not n.endswith("/"))

    assert f"{conversation_id.hex}/meta.json" in names
    assert f"{conversation_id.hex}/acp_notes.json" in names
    assert not any("/acp/" in n or n.endswith("/acp") for n in names)
    assert b"rt-secret-123" not in blob


def test_download_trajectory_redacts_llm_and_condenser_secrets(
    client, monkeypatch, tmp_path
):
    """下载的轨迹绝不能携带 LLM/condenser API 键。

    涵盖明文密钥（未配置 ``OH_SECRET_KEY``）和加密的 Fernet blob（已配置密码）——两者
    都不属于可共享存档。
    """
    conversations_path = tmp_path / "conversations"
    conversation_id = uuid4()
    conversation_dir = conversations_path / conversation_id.hex
    events_dir = conversation_dir / "events"
    events_dir.mkdir(parents=True)

    plaintext_key = "sk-plaintext-main-0123456789"
    condenser_key = "sk-plaintext-condenser-987654321"
    encrypted_blob = "gAAAAABencrypted_condenser_blob_value"
    encrypted_custom_secret = "gAAAAABencrypted_custom_registry_secret"

    # meta.json：明文主密钥+加密上下文压缩器密钥
    meta = {
        "id": conversation_id.hex,
        "agent": {
            "llm": {"model": "gpt-4o", "api_key": plaintext_key},
            "condenser": {"llm": {"model": "gpt-4o-mini", "api_key": encrypted_blob}},
        },
    }
    (conversation_dir / "meta.json").write_text(json.dumps(meta))

    # base_state.json 与智能体配置文件中的上下文压缩器明文密钥对齐，还包括一个加密的自定
    # 义机密，其字段名 ("value") 不在 LLM 机密字段列表中。
    #
    base_state = {
        "agent": {
            "llm": {"model": "gpt-4o", "api_key": plaintext_key},
            "condenser": {"llm": {"model": "gpt-4o-mini", "api_key": condenser_key}},
        },
        "secret_registry": {
            "secret_sources": {
                "MY_TOKEN": {"kind": "StaticSecret", "value": encrypted_custom_secret}
            }
        },
    }
    (conversation_dir / "base_state.json").write_text(json.dumps(base_state))

    # 嵌入整个智能体的 full_state 事件 (JSONL)，明文密钥
    event = {
        "kind": "ConversationStateUpdateEvent",
        "key": "full_state",
        "value": {
            "agent": {
                "llm": {"model": "gpt-4o", "api_key": plaintext_key},
                "condenser": {
                    "llm": {"model": "gpt-4o-mini", "api_key": condenser_key}
                },
            }
        },
    }
    (events_dir / "event-00000.json").write_text(json.dumps(event))

    _use_conversations_path(client, conversations_path)

    response = client.get(f"/api/file/download-trajectory/{conversation_id}")
    assert response.status_code == 200

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        blob = b"\n".join(archive.read(name) for name in archive.namelist())

    # 任何类型的机密材料都没有保存到档案中。
    for secret in (
        plaintext_key,
        condenser_key,
        encrypted_blob,
        encrypted_custom_secret,
    ):
        assert secret.encode() not in blob

    # 脱敏标记出现在原来的键所在的位置，并且保留非机密内容（模型名称）。
    #
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        meta_out = json.loads(archive.read(f"{conversation_id.hex}/meta.json"))
    assert meta_out["agent"]["llm"]["api_key"] == "**********"
    assert meta_out["agent"]["condenser"]["llm"]["api_key"] == "**********"
    assert meta_out["agent"]["llm"]["model"] == "gpt-4o"


def _trajectory_dir(client, tmp_path):
    """创建一个由 download-trajectory 提供服务的对话目录。"""
    conversations_path = tmp_path / "conversations"
    conversation_id = uuid4()
    conversation_dir = conversations_path / conversation_id.hex
    (conversation_dir / "events").mkdir(parents=True)
    (conversation_dir / "base_state.json").write_text('{"v": 1}')
    (conversation_dir / "events" / "event-00000.json").write_text('{"id": "e0"}')
    _use_conversations_path(client, conversations_path)
    return conversation_id, conversation_dir


def _mutate_after_listing(monkeypatch, directory: Path, mutate) -> None:
    """在 ``directory.rglob`` 列出其条目之后立即运行 ``mutate``。

    再现一个并发 writer 在列表和它返回的条目的读取之间更改目录。
    """
    original_rglob = Path.rglob

    def rglob(self, pattern, *args, **kwargs):
        entries = list(original_rglob(self, pattern, *args, **kwargs))
        if self == directory:
            mutate()
        return iter(entries)

    monkeypatch.setattr(Path, "rglob", rglob)


def test_download_trajectory_redacts_json_and_jsonl_files_only(
    client, monkeypatch, tmp_path
):
    """``.json`` 和 ``.jsonl`` 文件，无论字母大小写，都是已脱敏。

    其他文件会逐字节存档，即使它们保存为 JSON。
    """
    conversation_id, conversation_dir = _trajectory_dir(client, tmp_path)
    line = json.dumps({"llm": {"api_key": "sk-plaintext-main-0123456789"}})
    jsonl_names = ("events.jsonl", "MORE.JSONL")
    for name in jsonl_names:
        (conversation_dir / name).write_text(f"{line}\n{line}\n")
    (conversation_dir / "STATE.JSON").write_text(line)
    (conversation_dir / "notes.txt").write_text(line)

    response = client.get(f"/api/file/download-trajectory/{conversation_id}")

    assert response.status_code == 200
    root = conversation_id.hex
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        jsonl = {
            name: archive.read(f"{root}/{name}").decode().splitlines()
            for name in jsonl_names
        }
        state = json.loads(archive.read(f"{root}/STATE.JSON"))
        notes = archive.read(f"{root}/notes.txt")
    for rows in jsonl.values():
        assert [json.loads(row)["llm"]["api_key"] for row in rows] == [
            REDACTED_SECRET_VALUE,
            REDACTED_SECRET_VALUE,
        ]
    assert state["llm"]["api_key"] == REDACTED_SECRET_VALUE
    assert notes == line.encode()


def test_download_trajectory_survives_state_save_during_zip(
    client, monkeypatch, tmp_path
):
    """到达中间的原子基态保存不得导致 500。"""
    conversation_id, conversation_dir = _trajectory_dir(client, tmp_path)
    temp_file = conversation_dir / ".base_state.json.4867ztqe.tmp"
    temp_file.write_text('{"v": 2}')

    _mutate_after_listing(
        monkeypatch,
        conversation_dir,
        lambda: os.replace(temp_file, conversation_dir / "base_state.json"),
    )

    response = client.get(f"/api/file/download-trajectory/{conversation_id}")

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.read(f"{conversation_id.hex}/base_state.json") == b'{"v": 2}'
        assert f"{conversation_id.hex}/.base_state.json.4867ztqe.tmp" not in (
            archive.namelist()
        )


def test_download_trajectory_skips_entries_removed_while_zipping(
    client, monkeypatch, tmp_path
):
    """列出后删除的文件和目录将被排除，而不是 500。"""
    conversation_id, conversation_dir = _trajectory_dir(client, tmp_path)
    (conversation_dir / "gone.txt").write_text("gone")
    (conversation_dir / "gone_dir").mkdir()
    (conversation_dir / "gone_dir" / "inner.json").write_text("{}")

    def remove_entries():
        (conversation_dir / "gone.txt").unlink()
        shutil.rmtree(conversation_dir / "gone_dir")

    _mutate_after_listing(monkeypatch, conversation_dir, remove_entries)

    response = client.get(f"/api/file/download-trajectory/{conversation_id}")

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
    root = conversation_id.hex
    assert f"{root}/base_state.json" in names
    assert f"{root}/events/event-00000.json" in names
    assert not [name for name in names if "gone" in name]


def test_download_trajectory_omits_tmp_files(client, monkeypatch, tmp_path):
    """仍在写入的文件 (``*.tmp``) 不会被存档。

    这涵盖了 ``atomic_write_text`` 临时文件和会话租约
    ``owner_lease.tmp``. 它们可能写了一半，并且它们的名字不以``.json``结尾，所以它们
    也会绕过机密脱敏。
    """
    conversation_id, conversation_dir = _trajectory_dir(client, tmp_path)
    secret = "sk-in-progress-save-0123456789"
    (conversation_dir / ".base_state.json.4867ztqe.tmp").write_text(
        '{"agent": {"llm": {"api_key": "' + secret + '"'
    )
    events_dir = conversation_dir / "events"
    (events_dir / ".event-00001-abc.json.k2_9xq0z.tmp").write_text("{")
    (conversation_dir / "owner_lease.tmp").write_text('{"owner_instance_id": "')

    response = client.get(f"/api/file/download-trajectory/{conversation_id}")

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        blob = b"\n".join(archive.read(name) for name in names)
    root = conversation_id.hex
    assert sorted(names) == [
        f"{root}/",
        f"{root}/base_state.json",
        f"{root}/events/",
        f"{root}/events/event-00000.json",
    ]
    assert secret.encode() not in blob


def test_download_trajectory_keeps_dotfiles_that_are_not_tmp_files(
    client, monkeypatch, tmp_path
):
    """仅遗漏``*.tmp``个文件； 其他点文件已存档。"""
    conversation_id, conversation_dir = _trajectory_dir(client, tmp_path)
    kept = [".env.template", ".cache.metadata", "events/.eventlog-len-1.marker"]
    for name in kept:
        (conversation_dir / name).write_text(name)

    response = client.get(f"/api/file/download-trajectory/{conversation_id}")

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        for name in kept:
            assert archive.read(f"{conversation_id.hex}/{name}") == name.encode()


def test_download_trajectory_archives_the_json_bytes_it_checked_for_secrets(
    client, monkeypatch, tmp_path
):
    """读取 JSON 文件后进行的保存无法滑入机密。

    ``base_state.json`` 在被读取时不包含机密，并且随后被包含 Fernet token 的版本替换
    。 存档必须包含已读取的内容，而不是较新的文件。
    """
    conversation_id, conversation_dir = _trajectory_dir(client, tmp_path)
    base_state = conversation_dir / "base_state.json"
    first_save = b'{"secret_registry": {"secret_sources": {}}}'
    base_state.write_bytes(first_save)
    token = "gAAAAABnewly-saved-fernet-token"
    replaced = False

    def replace_after_first_read(read):
        def read_then_save(self, *args, **kwargs):
            nonlocal replaced
            content = read(self, *args, **kwargs)
            if self == base_state and not replaced:
                replaced = True
                newer = conversation_dir / ".base_state.json.newsave0.tmp"
                newer.write_text(
                    '{"secret_registry": {"secret_sources": '
                    '{"GITHUB_TOKEN": "' + token + '"}}}'
                )
                os.replace(newer, base_state)
            return content

        return read_then_save

    # 挂钩两种读取方法，以便测试不依赖于使用哪一种。
    monkeypatch.setattr(Path, "read_bytes", replace_after_first_read(Path.read_bytes))
    monkeypatch.setattr(Path, "read_text", replace_after_first_read(Path.read_text))

    response = client.get(f"/api/file/download-trajectory/{conversation_id}")

    assert response.status_code == 200
    assert replaced
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        archived = archive.read(f"{conversation_id.hex}/base_state.json")
        blob = b"\n".join(archive.read(name) for name in archive.namelist())
    assert archived == first_save
    assert token.encode() not in blob


def test_download_trajectory_resolves_dir_from_request_config(
    client, monkeypatch, tmp_path
):
    """提供的目录来自``request.app.state.config``。

    deferred-init 服务器上的 ``POST /api/init`` 仅替换该配置； 启动时配置查找不得决定
    路由的查找位置。
    """
    request_path = tmp_path / "request-conversations"
    conversation_id = uuid4()
    conversation_dir = request_path / conversation_id.hex
    (conversation_dir / "events").mkdir(parents=True)
    (conversation_dir / "meta.json").write_text("{}")
    (conversation_dir / "events" / "event-00000.json").write_text('{"id": "e0"}')

    monkeypatch.setattr(
        "openhands.agent_server.config.get_default_config",
        lambda: Config(session_api_keys=[], conversations_path=tmp_path / "elsewhere"),
    )
    _use_conversations_path(client, request_path)

    response = client.get(f"/api/file/download-trajectory/{conversation_id}")

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.read(f"{conversation_id.hex}/meta.json") == b"{}"


def test_deferred_init_trajectory_downloads_follow_init_conversations_path(tmp_path):
    """两条轨迹路线在 ``/api/init`` 移动存储后起作用。

    回归测试一个延迟初始化（热池）服务器： ``/api/init`` 安装用户特定的
    ``conversations_path`` 在
    ``app.state.config``因此，无论是扁平下载路由还是基于对话的下载路由，都必须从该目
    录中提供对话，而不是默认的启动时间。
    """
    cs_mod._conversation_service = None
    bash_mod._bash_event_service = None
    boot_conversations = tmp_path / "boot-conversations"
    user_conversations = tmp_path / "user" / "conversations"
    app = create_app(
        Config(
            deferred_init=True,
            conversations_path=boot_conversations,
            bash_events_dir=tmp_path / "boot-bash-events",
        )
    )
    headers = {"X-Session-API-Key": "init-key"}
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/init",
                json={
                    "session_api_keys": ["init-key"],
                    "conversations_path": str(user_conversations),
                    "bash_events_dir": str(tmp_path / "user" / "bash_events"),
                },
            )
            assert response.status_code == 200, response.text

            response = client.post(
                "/api/conversations",
                headers=headers,
                json={
                    "workspace": {"working_dir": str(tmp_path / "workspace")},
                    "agent": {
                        "kind": "Agent",
                        "llm": {"model": "openai/test", "usage_id": "test"},
                    },
                },
            )
            assert response.status_code == 201, response.text
            conversation_id = UUID(response.json()["id"])
            assert (user_conversations / conversation_id.hex).is_dir()
            assert not (boot_conversations / conversation_id.hex).exists()

            flat = client.get(
                f"/api/file/download-trajectory/{conversation_id}", headers=headers
            )
            scoped = client.get(
                f"/api/conversations/{conversation_id}/file/download-trajectory/"
                f"{conversation_id}",
                headers=headers,
            )

            assert flat.status_code == 200, flat.text
            assert scoped.status_code == 200, scoped.text

            root = conversation_id.hex
            with zipfile.ZipFile(io.BytesIO(flat.content)) as archive:
                flat_names = set(archive.namelist())
            with zipfile.ZipFile(io.BytesIO(scoped.content)) as archive:
                scoped_names = set(archive.namelist())
            assert flat_names == scoped_names
            assert f"{root}/meta.json" in flat_names
            assert f"{root}/base_state.json" in flat_names

            # 两条路由上已解析的配置 → 404 下都没有对话目录。 重新绑定配置代表其存储已远
            # 离初始化路径的对话。
            #
            app.state.config = app.state.config.model_copy(
                update={"conversations_path": tmp_path / "elsewhere"}
            )
            for url in (
                f"/api/file/download-trajectory/{conversation_id}",
                f"/api/conversations/{conversation_id}/file/download-trajectory/"
                f"{conversation_id}",
            ):
                missing = client.get(url, headers=headers)
                assert missing.status_code == 404, missing.text
                assert missing.json()["detail"] == "Conversation not found"

            # 重复下载不会留下任何 zip 残留物。
            assert list(user_conversations.glob("*.zip")) == []
    finally:
        cs_mod._conversation_service = None
        bash_mod._bash_event_service = None


def test_download_file_with_special_characters_in_path(client, tmp_path):
    """在路径中使用特殊字符测试下载（通过查询参数）。"""
    test_file = tmp_path / "file with spaces.txt"
    test_file.write_text("special path content")

    response = client.get(
        "/api/file/download",
        params={"path": str(test_file)},
    )

    assert response.status_code == 200
    assert response.content == b"special path content"


def test_file_legacy_routes_are_removed_from_openapi(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200

    openapi_paths = response.json()["paths"]
    assert "/api/file/upload/{path}" not in openapi_paths
    assert "/api/file/download/{path}" not in openapi_paths


# =============================================================================
# search_subdirs 测试
# =============================================================================


def test_search_subdirs_returns_only_directories_with_absolute_paths(client, tmp_path):
    """返回具有绝对路径的子目录； 跳过文件和隐藏条目。"""
    (tmp_path / "repo1").mkdir()
    (tmp_path / "repo2").mkdir()
    (tmp_path / ".hidden_dir").mkdir()
    (tmp_path / "README.md").write_text("hi")

    response = client.get("/api/file/search_subdirs", params={"path": str(tmp_path)})

    assert response.status_code == 200
    body = response.json()
    names = [entry["name"] for entry in body["items"]]
    paths = [entry["path"] for entry in body["items"]]
    assert names == ["repo1", "repo2"]
    assert paths == [str(tmp_path / "repo1"), str(tmp_path / "repo2")]
    assert body["next_page_id"] is None


def test_search_subdirs_include_hidden_lists_dot_directories(client, tmp_path):
    """当 include_hidden=True 时，列出点目录（仍跳过文件）。"""
    (tmp_path / "repo1").mkdir()
    (tmp_path / ".hidden_dir").mkdir()
    (tmp_path / "README.md").write_text("hi")

    response = client.get(
        "/api/file/search_subdirs",
        params={"path": str(tmp_path), "include_hidden": "true"},
    )

    assert response.status_code == 200
    body = response.json()
    names = [entry["name"] for entry in body["items"]]
    # 排序时不区分大小写； '.'在字母数字之前排序。
    assert names == [".hidden_dir", "repo1"]


def test_search_subdirs_relative_path_returns_400(client):
    response = client.get("/api/file/search_subdirs", params={"path": "relative/path"})
    assert response.status_code == 400
    assert "must be absolute" in response.json()["detail"]


def test_search_subdirs_missing_directory_returns_404(client, tmp_path):
    response = client.get(
        "/api/file/search_subdirs",
        params={"path": str(tmp_path / "does-not-exist")},
    )
    assert response.status_code == 404


def test_search_subdirs_path_is_a_file_returns_400(client, tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("hi")
    response = client.get("/api/file/search_subdirs", params={"path": str(file_path)})
    assert response.status_code == 400
    assert "not a directory" in response.json()["detail"]


def test_search_subdirs_paginates_with_limit_and_page_id(client, tmp_path):
    """limit 限制页面大小； next_page_id 从下一项继续。"""
    for name in ["alpha", "Bravo", "charlie", "Delta", "echo"]:
        (tmp_path / name).mkdir()

    first = client.get(
        "/api/file/search_subdirs",
        params={"path": str(tmp_path), "limit": 2},
    )
    assert first.status_code == 200
    first_body = first.json()
    assert [e["name"] for e in first_body["items"]] == ["alpha", "Bravo"]
    assert first_body["next_page_id"] == "charlie"

    second = client.get(
        "/api/file/search_subdirs",
        params={
            "path": str(tmp_path),
            "limit": 2,
            "page_id": first_body["next_page_id"],
        },
    )
    assert second.status_code == 200
    second_body = second.json()
    assert [e["name"] for e in second_body["items"]] == ["charlie", "Delta"]
    assert second_body["next_page_id"] == "echo"

    third = client.get(
        "/api/file/search_subdirs",
        params={
            "path": str(tmp_path),
            "limit": 2,
            "page_id": second_body["next_page_id"],
        },
    )
    assert third.status_code == 200
    third_body = third.json()
    assert [e["name"] for e in third_body["items"]] == ["echo"]
    assert third_body["next_page_id"] is None


def test_search_subdirs_pages_past_case_only_twins(client, tmp_path):
    """接下来的 next_page_id 到达两个大小写不同的名称中的每一个。"""
    (tmp_path / "foo").mkdir()
    if (tmp_path / "Foo").exists():
        pytest.skip("filesystem does not distinguish case-only directory names")
    for name in ["Foo", "bar"]:
        (tmp_path / name).mkdir()

    seen: list[str] = []
    page_id: str | None = None
    for _ in range(5):
        params: dict[str, str | int] = {"path": str(tmp_path), "limit": 1}
        if page_id is not None:
            params["page_id"] = page_id
        response = client.get("/api/file/search_subdirs", params=params)
        assert response.status_code == 200
        body = response.json()
        seen.extend(e["name"] for e in body["items"])
        page_id = body["next_page_id"]
        if page_id is None:
            break

    assert seen == ["bar", "Foo", "foo"]
    assert page_id is None


def test_search_subdirs_accepts_lowercase_cursor(client, tmp_path):
    """来自较旧服务器的小写光标仍会在其条目处恢复。"""
    for name in ["Alpha", "Bravo"]:
        (tmp_path / name).mkdir()

    response = client.get(
        "/api/file/search_subdirs",
        params={"path": str(tmp_path), "limit": 1, "page_id": "bravo"},
    )
    assert response.status_code == 200
    assert [e["name"] for e in response.json()["items"]] == ["Bravo"]


def test_search_subdirs_limit_too_low_returns_422(client, tmp_path):
    response = client.get(
        "/api/file/search_subdirs",
        params={"path": str(tmp_path), "limit": 0},
    )
    assert response.status_code == 422


def test_get_home_returns_user_home(client):
    response = client.get("/api/file/home")
    assert response.status_code == 200
    assert response.json()["home"] == str(Path.home())


def test_get_home_returns_dynamic_favorites_and_locations(
    client, tmp_path, monkeypatch
):
    # 排列：假设用户的家是 tmp_path，混合填充
    # 可见目录、隐藏目录和文件。 收藏夹应仅包括按字母顺序排列的可见目录。 位置应报告
    # POSIX 根。
    #
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "projects").mkdir()
    (tmp_path / "Documents").mkdir()
    (tmp_path / ".cache").mkdir()
    (tmp_path / "readme.txt").write_text("ignored")

    # 法案
    response = client.get("/api/file/home")

    # 断言
    assert response.status_code == 200
    body = response.json()
    assert body["home"] == str(tmp_path)
    assert body["favorites"] == [
        {"label": "Documents", "path": str(tmp_path / "Documents")},
        {"label": "projects", "path": str(tmp_path / "projects")},
    ]
    assert body["locations"] == [{"label": "/", "path": "/"}]


def test_get_home_include_hidden_lists_hidden_favorites(client, tmp_path, monkeypatch):
    # 当 include_hidden=True 时，隐藏的顶级目录出现在收藏夹中（文件仍被排除）。
    #
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "projects").mkdir()
    (tmp_path / ".cache").mkdir()
    (tmp_path / "readme.txt").write_text("ignored")

    response = client.get("/api/file/home", params={"include_hidden": "true"})

    assert response.status_code == 200
    body = response.json()
    assert body["favorites"] == [
        {"label": ".cache", "path": str(tmp_path / ".cache")},
        {"label": "projects", "path": str(tmp_path / "projects")},
    ]


@pytest.mark.timeout(20)
async def test_upload_does_not_block_event_loop_on_slow_storage(tmp_path, monkeypatch):
    # 直接驱动 _upload_file，而不是通过 ASGI：进程内 ASGI 交错得如此干净，以至于竞争的
    # /health 请求适合写入之间，从而屏蔽了阻塞。 同一循环上的背景行情自动收录器测量饥饿
    # 。
    #
    real_open = open

    class _SlowWriteFile:
        def __init__(self, real_file):
            self._f = real_file

        def write(self, data):
            time.sleep(0.1)  # 型号 NFS / FUSE / 加密 FS 写入延迟
            return self._f.write(data)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return self._f.close()

    def _slow_open(path, mode="r", *args, **kwargs):
        f = real_open(path, mode, *args, **kwargs)
        return _SlowWriteFile(f) if "w" in mode and "b" in mode else f

    monkeypatch.setattr(file_router_module, "open", _slow_open, raising=False)

    spooled = tempfile.SpooledTemporaryFile()
    spooled.write(b"x" * 64 * 1024)  # 8 × 8 KB 块 → 约 800 毫秒的阻塞
    spooled.seek(0)
    # SpooledTemporaryFile 满足 BinaryIO 协议，但不是名义上的子类； UploadFile 在运行时
    # 接受它。
    #
    upload = UploadFile(file=spooled, filename="uploaded.bin")  # pyright: ignore[reportArgumentType]

    ticks: list[float] = []
    stop = asyncio.Event()

    async def ticker():
        while not stop.is_set():
            ticks.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.05)

    ticker_task = asyncio.create_task(ticker())
    await asyncio.sleep(0.2)
    pre_ticks = len(ticks)

    upload_start = asyncio.get_event_loop().time()
    await _upload_file(str(tmp_path / "uploaded.bin"), upload)
    upload_end = asyncio.get_event_loop().time()

    await asyncio.sleep(0)
    stop.set()
    await ticker_task

    elapsed = upload_end - upload_start
    during_upload = sum(1 for t in ticks[pre_ticks:] if upload_start <= t < upload_end)
    expected_min = int((elapsed / 0.05) * 0.5)
    assert during_upload >= expected_min, (
        f"ticker logged {during_upload} ticks during {elapsed * 1000:.0f}ms "
        f"upload (expected ≥ {expected_min}); event loop is blocked by "
        f"sync f.write() at file_router.py:65."
    )


# =============================================================================
# 存档测试 - GET /api/file/archive (AGE-1871)
# =============================================================================


@pytest.fixture
def workspace(tmp_path):
    """``tmp_path/project`` 下的一个小型嵌套工作区树。"""
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (root / "README.md").write_text("# project\n", encoding="utf-8")
    (root / "empty").mkdir()
    return root


def _git(args, cwd):
    subprocess.run(
        ["git", "-c", "user.email=t@t.dev", "-c", "user.name=t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def test_archive_missing_path_returns_404(client, tmp_path):
    resp = client.get("/api/file/archive", params={"path": str(tmp_path / "nope")})
    assert resp.status_code == 404


def test_archive_file_path_returns_400(client, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")

    resp = client.get("/api/file/archive", params={"path": str(f)})

    assert resp.status_code == 400
    assert "not a directory" in resp.json()["detail"].lower()


def test_archive_relative_path_returns_400(client):
    resp = client.get("/api/file/archive", params={"path": "relative/dir"})
    assert resp.status_code == 400
    assert "absolute" in resp.json()["detail"].lower()


def test_archive_rejects_dashed_base_ref(client, workspace):
    resp = client.get(
        "/api/file/archive",
        params={"path": str(workspace), "format": "git-delta", "base_ref": "-x"},
    )
    assert resp.status_code == 400


def test_archive_cleans_up_temp_file(client, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], repo)
    (repo / "a.txt").write_text("x\n", encoding="utf-8")

    resp = client.get("/api/file/archive", params={"path": str(repo)})

    assert resp.status_code == 200
    # 工作区该临时存储区是建立在目标的父级卷（即系统临时目录）上，而不是系统临时目录，
    # BackgroundTask 一旦响应完全发送，就将其删除，因此不会留下任何东西在仓库旁边。
    #
    leftovers = [p for p in repo.parent.iterdir() if p.name != "repo"]
    assert leftovers == []


def test_git_delta_new_repo_lists_files_as_additions(client, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init"], root)
    (root / "new_file.py").write_text("x = 1\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive", params={"path": str(root), "format": "git-delta"}
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/x-patch")
    patch = resp.content.decode("utf-8")
    assert "new_file.py" in patch
    assert "new file mode" in patch


def test_git_delta_captures_modifications_and_untracked_vs_head(client, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init"], root)
    (root / "a.txt").write_text("original\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-m", "init"], root)
    # 更改已跟踪的文件并在提交后添加未跟踪的文件。
    (root / "a.txt").write_text("changed\n", encoding="utf-8")
    (root / "b.txt").write_text("brand new\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive",
        params={"path": str(root), "format": "git-delta", "base_ref": "HEAD"},
    )

    assert resp.status_code == 200, resp.text
    patch = resp.content.decode("utf-8")
    assert "a.txt" in patch
    assert "b.txt" in patch
    assert "changed" in patch


def test_git_delta_excludes_node_modules_even_when_not_gitignored(client, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init"], root)
    # 新的源文件（应该在增量中）+一个重的未跟踪的node_modules，没有.gitignore（应该被默
    # 认排除）。
    #
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / "node_modules" / "pkg" / "big.js").write_text(
        "// huge\n" * 100, encoding="utf-8"
    )

    resp = client.get(
        "/api/file/archive", params={"path": str(root), "format": "git-delta"}
    )

    assert resp.status_code == 200, resp.text
    patch = resp.content.decode("utf-8")
    assert "app.py" in patch
    assert "node_modules" not in patch


def test_git_delta_can_disable_default_excludes(client, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init"], root)
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / "node_modules" / "pkg" / "big.js").write_text(
        "// intentionally captured\n", encoding="utf-8"
    )

    resp = client.get(
        "/api/file/archive",
        params={
            "path": str(root),
            "format": "git-delta",
            "use_default_excludes": "false",
        },
    )

    assert resp.status_code == 200, resp.text
    patch = resp.content.decode("utf-8")
    assert "app.py" in patch
    assert "node_modules/pkg/big.js" in patch


def test_git_delta_scoped_to_requested_subdirectory(client, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init"], root)
    (root / "outside.txt").write_text("base\n", encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "inside.txt").write_text("base\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-m", "init"], root)
    # 提交后，更改子目录 AND 内部的文件和其外部的文件。
    (root / "outside.txt").write_text("changed-outside\n", encoding="utf-8")
    (sub / "inside.txt").write_text("changed-inside\n", encoding="utf-8")

    # 归档子目录必须仅产生子目录的增量，而不是存储库的增量。
    resp = client.get(
        "/api/file/archive",
        params={"path": str(sub), "format": "git-delta", "base_ref": "HEAD"},
    )

    assert resp.status_code == 200, resp.text
    patch = resp.content.decode("utf-8")
    assert "inside.txt" in patch
    assert "outside.txt" not in patch


def test_git_delta_invalid_base_ref_returns_400(client, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init"], root)
    (root / "a.txt").write_text("x\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-m", "init"], root)

    resp = client.get(
        "/api/file/archive",
        params={
            "path": str(root),
            "format": "git-delta",
            "base_ref": "does-not-exist-ref",
        },
    )

    # bad base_ref 是客户端错误，而不是 500。
    assert resp.status_code == 400


def test_git_delta_on_non_repo_returns_400(client, workspace):
    resp = client.get(
        "/api/file/archive", params={"path": str(workspace), "format": "git-delta"}
    )
    assert resp.status_code == 400
    assert "git repositor" in resp.json()["detail"].lower()


def test_git_delta_response_includes_base_commit_header(client, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init"], root)
    (root / "a.txt").write_text("original\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-m", "init"], root)
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    # 工作树发生变化，因此增量非空。
    (root / "a.txt").write_text("changed\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive",
        params={"path": str(root), "format": "git-delta", "base_ref": "HEAD"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers["x-archive-base-commit"] == head_sha
    assert resp.headers["x-archive-base-ref"] == "HEAD"


def test_git_delta_new_repo_has_no_base_commit_header(client, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init"], root)
    (root / "new_file.py").write_text("x = 1\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive", params={"path": str(root), "format": "git-delta"}
    )

    assert resp.status_code == 200, resp.text
    # 空树基（无提交）不是可重播的提交，因此没有标头。
    assert "x-archive-base-commit" not in resp.headers


def _repo_with_remote(root: Path, remote_url: str, branch: str = "feature-x") -> str:
    """使用一次提交、一个 ``origin`` 远程和一个命名分支来初始化一个存储库。

    返回 HEAD 提交 sha。
    """
    root.mkdir()
    _git(["init"], root)
    _git(["remote", "add", "origin", remote_url], root)
    (root / "a.txt").write_text("original\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-m", "init"], root)
    _git(["checkout", "-b", branch], root)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_git_delta_response_includes_repo_metadata_headers(client, tmp_path):
    head_sha = _repo_with_remote(
        tmp_path / "repo", "https://github.com/example/repo.git"
    )
    (tmp_path / "repo" / "a.txt").write_text("changed\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive",
        params={"path": str(tmp_path / "repo"), "format": "git-delta"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers["x-archive-repo-remote"] == quote(
        "https://github.com/example/repo.git", safe=""
    )
    assert resp.headers["x-archive-branch"] == "feature-x"
    assert resp.headers["x-archive-head-commit"] == head_sha


def test_tar_gz_response_includes_repo_metadata_headers(client, tmp_path):
    # 新的 repo-identity 标头也使 tar.gz 快照具有自描述性，即使它不包含 base_commit/
    # base_ref。
    #
    head_sha = _repo_with_remote(
        tmp_path / "repo", "https://github.com/example/repo.git"
    )

    resp = client.get(
        "/api/file/archive",
        params={"path": str(tmp_path / "repo"), "format": "tar.gz"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers["x-archive-repo-remote"] == quote(
        "https://github.com/example/repo.git", safe=""
    )
    assert resp.headers["x-archive-branch"] == "feature-x"
    assert resp.headers["x-archive-head-commit"] == head_sha
    assert "x-archive-base-commit" not in resp.headers


def test_archive_redacts_remote_credentials_in_header(client, tmp_path):
    _repo_with_remote(
        tmp_path / "repo",
        "https://user:ghp_secrettoken@github.com/example/repo.git",
    )

    resp = client.get(
        "/api/file/archive",
        params={"path": str(tmp_path / "repo"), "format": "tar.gz"},
    )

    assert resp.status_code == 200, resp.text
    remote = resp.headers["x-archive-repo-remote"]
    assert "ghp_secrettoken" not in remote
    assert remote == quote("https://****@github.com/example/repo.git", safe="")


def test_archive_redacts_mixed_case_remote_credentials_in_header(client, tmp_path):
    _repo_with_remote(
        tmp_path / "repo",
        "HTTPS://user:ghp_secrettoken@github.com/example/repo.git",
    )

    resp = client.get(
        "/api/file/archive",
        params={"path": str(tmp_path / "repo"), "format": "tar.gz"},
    )

    assert resp.status_code == 200, resp.text
    remote = resp.headers["x-archive-repo-remote"]
    assert "ghp_secrettoken" not in remote
    assert remote == quote("HTTPS://****@github.com/example/repo.git", safe="")


def test_archive_redacts_remote_query_credentials_in_header(client, tmp_path):
    _repo_with_remote(
        tmp_path / "repo",
        "https://github.com/example/repo.git?access_token=SECRET&depth=1",
    )

    resp = client.get(
        "/api/file/archive",
        params={"path": str(tmp_path / "repo"), "format": "tar.gz"},
    )

    assert resp.status_code == 200, resp.text
    remote = unquote(resp.headers["x-archive-repo-remote"])
    assert "SECRET" not in remote
    assert "access_token=%3Credacted%3E" in remote
    assert "depth=1" in remote


def test_archive_literal_percent_is_encoded(client, tmp_path):
    _repo_with_remote(
        tmp_path / "repo",
        "https://github.com/example/feature%2Frepo.git",
    )

    resp = client.get(
        "/api/file/archive",
        params={"path": str(tmp_path / "repo"), "format": "tar.gz"},
    )

    assert resp.status_code == 200, resp.text
    assert "%252F" in resp.headers["x-archive-repo-remote"]


def test_archive_redacts_multiline_remote_credentials_in_header(client, tmp_path):
    _repo_with_remote(
        tmp_path / "repo",
        "https://user:ghp_secrettoken@github.com/example/repo.git\nextra",
    )

    resp = client.get(
        "/api/file/archive",
        params={"path": str(tmp_path / "repo"), "format": "tar.gz"},
    )

    assert resp.status_code == 200, resp.text
    remote = resp.headers["x-archive-repo-remote"]
    assert "ghp_secrettoken" not in remote
    assert remote == quote("https://****@github.com/example/repo.git\nextra", safe="")


def test_archive_detached_head_reports_detached_branch(client, tmp_path):
    head_sha = _repo_with_remote(
        tmp_path / "repo", "https://github.com/example/repo.git"
    )
    # 在提交处分离 HEAD（SWE-工作台式固定结帐）。
    _git(["checkout", head_sha], tmp_path / "repo")

    resp = client.get(
        "/api/file/archive",
        params={"path": str(tmp_path / "repo"), "format": "tar.gz"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers["x-archive-branch"] == "DETACHED"
    assert resp.headers["x-archive-head-commit"] == head_sha


def test_archive_non_git_directory_has_no_repo_metadata_headers(client, workspace):
    resp = client.get(
        "/api/file/archive", params={"path": str(workspace), "format": "tar.gz"}
    )

    assert resp.status_code == 200, resp.text
    assert "x-archive-repo-remote" not in resp.headers
    assert "x-archive-branch" not in resp.headers
    assert "x-archive-head-commit" not in resp.headers


def test_archive_format_description_matches_single_nested_repo(client, tmp_path):
    # 恰好包含一个存储库的非存储库目录将被归档为该存储库，因此它旁边的文件将被忽略； 的
    # 公开描述
    # ``format`` 必须这样说，而不是承诺“整个目录”。
    parent = tmp_path / "parent"
    repo = parent / "group" / "proj"
    repo.mkdir(parents=True)
    _git(["init", "-q"], repo)
    (repo / "README.md").write_text("# proj\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-qm", "init"], repo)
    (parent / "top.txt").write_text("top\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive", params={"path": str(parent), "format": "tar.gz"}
    )
    assert resp.status_code == 200, resp.text
    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        names = tar.getnames()
    assert "proj/README.md" in names
    assert not any(name.endswith("top.txt") for name in names)

    paths = client.get("/openapi.json").json()["paths"]
    for route in (
        "/api/file/archive",
        "/api/conversations/{runtime_conversation_id}/file/archive",
    ):
        params = paths[route]["get"]["parameters"]
        descriptions = {p["name"]: p.get("description", "") for p in params}
        assert "entire directory" not in descriptions["format"]
        for name in ("format", "path"):
            assert "exactly one git repository" in descriptions[name]


def test_archive_remote_with_embedded_control_char_is_percent_encoded(client, tmp_path):
    # 远程 URL 是自由格式的文本（与引用名称不同），因此它可以直接将文字控制字符携带到成
    # 为标头值的内容中。
    #
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], repo)
    _git(["config", "remote.origin.url", "https://example.com/repo\nline-two"], repo)
    _git(["commit", "--allow-empty", "-m", "init"], repo)

    resp = client.get(
        "/api/file/archive", params={"path": str(repo), "format": "tar.gz"}
    )

    assert resp.status_code == 200, resp.text
    remote = resp.headers["x-archive-repo-remote"]
    assert "\n" not in remote
    assert remote == quote("https://example.com/repo\nline-two", safe="")


def test_archive_non_ascii_branch_is_percent_encoded_not_dropped(client, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], repo)
    _git(["commit", "--allow-empty", "-m", "init"], repo)
    _git(["checkout", "-b", "café-branch"], repo)

    resp = client.get(
        "/api/file/archive", params={"path": str(repo), "format": "tar.gz"}
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers["x-archive-branch"] == quote("café-branch", safe="")


# =============================================================================
# 存档测试 - 格式=tar.gz（完整工作区存档）
# =============================================================================


def _tar_members(content: bytes) -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
        return tar.getnames()


def test_tar_gz_on_non_git_directory_succeeds(client, workspace):
    # 关键区别在于：非 git 目录上的 git-delta 400s，tar.gz 捕获整个树。
    #
    resp = client.get(
        "/api/file/archive", params={"path": str(workspace), "format": "tar.gz"}
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/gzip")
    names = _tar_members(resp.content)
    assert f"{workspace.name}/src/main.py" in names
    assert f"{workspace.name}/README.md" in names
    assert f"{workspace.name}/archive_manifest.json" in names


def test_tar_gz_default_excludes_drop_node_modules(client, tmp_path):
    root = tmp_path / "plain"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_text("x = 1\n", encoding="utf-8")
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / "node_modules" / "pkg" / "junk.js").write_text("// big\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive", params={"path": str(root), "format": "tar.gz"}
    )

    assert resp.status_code == 200, resp.text
    names = _tar_members(resp.content)
    assert f"{root.name}/src/main.py" in names
    assert not any("node_modules" in n for n in names)


def test_tar_gz_can_disable_default_excludes(client, tmp_path):
    root = tmp_path / "plain"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_text("x = 1\n", encoding="utf-8")
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / "node_modules" / "pkg" / "junk.js").write_text("// big\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive",
        params={
            "path": str(root),
            "format": "tar.gz",
            "use_default_excludes": "false",
        },
    )

    assert resp.status_code == 200, resp.text
    names = _tar_members(resp.content)
    assert f"{root.name}/src/main.py" in names
    assert f"{root.name}/node_modules/pkg/junk.js" in names

    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        member = tar.extractfile(f"{root.name}/archive_manifest.json")
        assert member is not None
        manifest = json.loads(member.read().decode("utf-8"))
    assert "node_modules/" not in manifest["excludes"]


def test_tar_gz_exclude_param_extends_defaults(client, tmp_path):
    root = tmp_path / "plain"
    (root / "keep").mkdir(parents=True)
    (root / "keep" / "a.txt").write_text("keep\n", encoding="utf-8")
    (root / "secrets").mkdir()
    (root / "secrets" / "token.txt").write_text("shh\n", encoding="utf-8")
    # 用于确认默认值的默认排除目录仍然与参数一起应用。
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_text("bytecode\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive",
        params={"path": str(root), "format": "tar.gz", "exclude": "secrets"},
    )

    assert resp.status_code == 200, resp.text
    names = _tar_members(resp.content)
    assert f"{root.name}/keep/a.txt" in names
    assert not any("secrets" in n for n in names)
    # 默认值仍然与额外模式一起应用。
    assert not any("__pycache__" in n for n in names)


def test_tar_gz_captures_gitignored_and_non_repo_files(client, tmp_path):
    # tar.gz 是逐字节的：它捕获 git-delta 会错过的文件，包括 gitignored 创作的文件（目录
    # 甚至不需要是 git 存储库）。
    #
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init"], root)
    (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (root / "ignored.txt").write_text("authored but gitignored\n", encoding="utf-8")
    (root / "tracked.py").write_text("x = 1\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive", params={"path": str(root), "format": "tar.gz"}
    )

    assert resp.status_code == 200, resp.text
    names = _tar_members(resp.content)
    assert f"{root.name}/ignored.txt" in names
    assert f"{root.name}/tracked.py" in names


def test_tar_gz_manifest_records_format_and_excludes(client, workspace):
    resp = client.get(
        "/api/file/archive",
        params={"path": str(workspace), "format": "tar.gz", "exclude": "*.bin"},
    )

    assert resp.status_code == 200, resp.text
    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        member = tar.extractfile(f"{workspace.name}/archive_manifest.json")
        assert member is not None
        manifest = json.loads(member.read().decode("utf-8"))

    assert manifest["format"] == "tar.gz"
    assert manifest["source"] == workspace.name
    assert manifest["file_count"] >= 2
    # 应用的排除 = 默认值 + 调用者提供的模式。
    assert "*.bin" in manifest["excludes"]
    assert "node_modules/" in manifest["excludes"]


def test_tar_gz_ignores_base_ref_without_error(client, workspace):
    # base_ref 仅适用于 git-delta； tar.gz一定不能出错。
    resp = client.get(
        "/api/file/archive",
        params={"path": str(workspace), "format": "tar.gz", "base_ref": "HEAD"},
    )

    assert resp.status_code == 200, resp.text
    assert "x-archive-base-commit" not in resp.headers


def test_tar_gz_multi_segment_exclude_drops_nested_dir(client, tmp_path):
    # 多段排除（包含 '/') 必须遵守 tar.gz，就像 git-delta 通过 core.excludesFile 遵守它
    # 一样。 ``secrets/prod`` 应该只删除该嵌套目录，而其他同名目录应保留。
    #
    root = tmp_path / "plain"
    (root / "secrets" / "prod").mkdir(parents=True)
    (root / "secrets" / "prod" / "token.txt").write_text("shh\n", encoding="utf-8")
    (root / "secrets" / "dev").mkdir(parents=True)
    (root / "secrets" / "dev" / "token.txt").write_text("ok\n", encoding="utf-8")
    (root / "prod").mkdir()  # 相同的基本名称，不同的路径：必须保留
    (root / "prod" / "keep.txt").write_text("keep\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive",
        params={"path": str(root), "format": "tar.gz", "exclude": "secrets/prod"},
    )

    assert resp.status_code == 200, resp.text
    names = _tar_members(resp.content)
    # 嵌套的 Secret/prod 子树消失了......
    assert not any("secrets/prod" in n for n in names)
    # ...but the sibling secrets/dev and the unrelated top-level prod survive.
    assert f"{root.name}/secrets/dev/token.txt" in names
    assert f"{root.name}/prod/keep.txt" in names


def test_tar_gz_bare_name_exclude_still_matches_any_component(client, tmp_path):
    # 裸名排除（没有 '/') 必须在任何深度保持匹配任何路径组件，因此多段支持不会回归
    # node_modules 式修剪。
    #
    root = tmp_path / "plain"
    (root / "a" / "node_modules").mkdir(parents=True)
    (root / "a" / "node_modules" / "junk.js").write_text("// big\n", encoding="utf-8")
    (root / "keep.py").write_text("x = 1\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive",
        params={
            "path": str(root),
            "format": "tar.gz",
            "use_default_excludes": "false",
            "exclude": "node_modules",
        },
    )

    assert resp.status_code == 200, resp.text
    names = _tar_members(resp.content)
    assert not any("node_modules" in n for n in names)
    assert f"{root.name}/keep.py" in names


def test_tar_gz_preserves_user_archive_manifest_file(client, tmp_path, caplog):
    # 如果工作区本身包含顶级 archive_manifest.json，则合成捕获清单必须不破坏它：用户的字
    # 节获胜并记录警告。
    #
    root = tmp_path / "plain"
    root.mkdir()
    user_payload = b'{"this": "is the user\'s real file"}'
    (root / "archive_manifest.json").write_bytes(user_payload)
    (root / "other.txt").write_text("x\n", encoding="utf-8")

    with caplog.at_level("WARNING"):
        resp = client.get(
            "/api/file/archive", params={"path": str(root), "format": "tar.gz"}
        )

    assert resp.status_code == 200, resp.text
    arcname = f"{root.name}/archive_manifest.json"
    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        # 路径上只有一个成员（无阴影重复）。
        assert [n for n in tar.getnames() if n == arcname] == [arcname]
        member = tar.extractfile(arcname)
        assert member is not None
        assert member.read() == user_payload

    assert any(ARCHIVE_MANIFEST_NAME in record.message for record in caplog.records), (
        "expected a warning about the archive_manifest.json collision"
    )


# =============================================================================
# 存档测试 - git-delta 自动下降到工作区基础下的存储库 (AGE-1871 / infra#1444 H1)。 回购
# 支持的对话克隆到
#
# {base}/{repo_name}, so archiving the base itself must resolve down to the repo
# 而不是对非 repo 父级进行 400-ing 并且什么也不捕获。
# =============================================================================


def test_git_delta_auto_descends_to_single_repo_under_base(client, tmp_path):
    # 存档 PATH 指向工作区基础，但 git 存储库位于 {base}/{repo_name}. 的下一级，git-
    # delta 必须解析它。
    #
    base = tmp_path / "project"
    repo = base / "my-repo"
    repo.mkdir(parents=True)
    _git(["init"], repo)
    (repo / "app.py").write_text("x = 1\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive", params={"path": str(base), "format": "git-delta"}
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/x-patch")
    assert unquote(resp.headers["x-archive-repo-root"]) == str(repo)
    assert "app.py" in resp.content.decode("utf-8")


def test_git_delta_auto_descends_two_levels_for_grouped_workspace(client, tmp_path):
    # 在沙箱分组下，存储库位于 {base}/{group}/{repo_name} — 比静态基本路径运行时-API 通
    # 道低两级。 分辨率是有限深度的，所以它仍然可以找到它。
    #
    base = tmp_path / "project"
    repo = base / "deadbeef" / "my-repo"
    repo.mkdir(parents=True)
    _git(["init"], repo)
    (repo / "app.py").write_text("y = 2\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive", params={"path": str(base), "format": "git-delta"}
    )

    assert resp.status_code == 200, resp.text
    assert "app.py" in resp.content.decode("utf-8")


def test_git_delta_uses_base_directly_when_base_is_a_repo(client, tmp_path):
    # 如果基础本身是一个存储库，则直接使用它而不使用降序（解析器短路），因此它下面的同级
    # 子目录是不相关的。
    #
    base = tmp_path / "project"
    base.mkdir()
    _git(["init"], base)
    (base / "top.py").write_text("a = 1\n", encoding="utf-8")
    (base / "docs").mkdir()
    (base / "docs" / "guide.md").write_text("# guide\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive", params={"path": str(base), "format": "git-delta"}
    )

    assert resp.status_code == 200, resp.text
    patch = resp.content.decode("utf-8")
    assert "top.py" in patch
    assert "guide.md" in patch


def test_git_delta_ambiguous_multiple_repos_still_400s(client, tmp_path):
    # 基地下的两个候选回购协议是不明确的——不要猜测； 退回到现有的 not-a-git-repo 行为 (
    # 400)，而不是随机归档。
    #
    base = tmp_path / "project"
    for name in ("repo-a", "repo-b"):
        r = base / name
        r.mkdir(parents=True)
        _git(["init"], r)
        (r / "f.py").write_text("x = 1\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive", params={"path": str(base), "format": "git-delta"}
    )

    assert resp.status_code == 400


def test_git_delta_no_repo_under_base_still_400s(client, tmp_path):
    base = tmp_path / "project"
    (base / "src").mkdir(parents=True)
    (base / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive", params={"path": str(base), "format": "git-delta"}
    )

    assert resp.status_code == 400


# =============================================================================
# 存档测试 - tar.gz 永远不会泄漏 .git 凭据 (infra#1444 H2)
# =============================================================================


def test_tar_gz_default_excludes_drop_dot_git(client, tmp_path):
    # token 全部档案默认排除会删除整个 .git 树，因此在 .git/config 中的克隆永远不会进入
    # 共享、无限保留的档案桶（对象数据库不会因为档案大小而膨胀）。
    #
    root = tmp_path / "project"
    root.mkdir()
    _git(["init"], root)
    (root / "README.md").write_text("# p\n", encoding="utf-8")
    # 通过 git 模拟标记化克隆远程已持久化。
    _git(
        ["remote", "add", "origin", "https://x-access-token:ghs_SECRET@github.com/o/r"],
        root,
    )

    resp = client.get(
        "/api/file/archive", params={"path": str(root), "format": "tar.gz"}
    )

    assert resp.status_code == 200, resp.text
    names = _tar_members(resp.content)
    assert not any("/.git/" in n or n.endswith("/.git") for n in names)
    assert b"ghs_SECRET" not in resp.content
    assert f"{root.name}/README.md" in names


def test_tar_gz_full_capture_still_strips_git_credentials(client, tmp_path):
    # 即使 use_default_excludes=False （故意的完整捕获），包含凭据的 git 内部结构也绝不
    # 能是已持久化。
    #
    root = tmp_path / "project"
    root.mkdir()
    _git(["init"], root)
    (root / "README.md").write_text("# p\n", encoding="utf-8")
    _git(
        ["remote", "add", "origin", "https://x-access-token:ghs_SECRET@github.com/o/r"],
        root,
    )

    resp = client.get(
        "/api/file/archive",
        params={
            "path": str(root),
            "format": "tar.gz",
            "use_default_excludes": "false",
        },
    )

    assert resp.status_code == 200, resp.text
    names = _tar_members(resp.content)
    # 完整捕获保留大部分 .git（历史/对象）以保证保真度......
    assert any("/.git/" in n for n in names)
    # ...but never the secrets.
    assert not any(n.endswith("/.git/config") for n in names)
    assert not any("/.git/logs/" in n for n in names)
    assert b"ghs_SECRET" not in resp.content


def test_tar_gz_strips_credentials_file_and_reflog_with_tokens(client, tmp_path):
    # 在 .git/config 之后：一个合成的 .git/ 包含一个 token 在 .git/credentials 和 .git/
    # logs/ reflog 中，必须永远避免达到档案字节，无论进行何种完整捕获。 手工构建（不是自
    # 动化） `git init`) .git/credentials 和 .git/logs/ — git 在初始化时不写入的文件 —
    # 直接被使用。
    #
    root = tmp_path / "project"
    git_dir = root / ".git"
    (git_dir / "logs").mkdir(parents=True)
    (root / "README.md").write_text("# p\n", encoding="utf-8")
    (git_dir / "config").write_text(
        '[remote "origin"]\n'
        "\turl = https://x-access-token:ghs_CONFIGTOK@github.com/o/r\n",
        encoding="utf-8",
    )
    (git_dir / "credentials").write_text(
        "https://x-access-token:ghs_CREDTOK@github.com\n", encoding="utf-8"
    )
    (git_dir / "logs" / "HEAD").write_text(
        "0 1 t <t@t.dev> 0 +0000\tclone: from "
        "https://x-access-token:ghs_LOGTOK@github.com/o/r\n",
        encoding="utf-8",
    )
    # 非凭据 .git 内部必须生存：证明凭据文件被专门删除，而不是整个 .git 树。
    #
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive",
        params={
            "path": str(root),
            "format": "tar.gz",
            "use_default_excludes": "false",
        },
    )

    assert resp.status_code == 200, resp.text
    names = _tar_members(resp.content)
    assert not any(n.endswith("/.git/config") for n in names)
    assert not any(n.endswith("/.git/credentials") for n in names)
    assert not any("/.git/logs/" in n for n in names)
    assert any(n.endswith("/.git/HEAD") for n in names)
    for token in (b"ghs_CONFIGTOK", b"ghs_CREDTOK", b"ghs_LOGTOK"):
        assert token not in resp.content


def test_tar_gz_strips_fetch_head_and_submodule_credentials(client, tmp_path):
    # #3867: strip 也必须覆盖 .git/ FETCH_HEAD (git 会写入 fetched URL — token 和所有 ——
    #  以及 .git/modules/<name> 下的 submodule git 目录，而不是只覆盖顶级 .git/config)。
    #  手工构建，以便在完全捕获中运用这些精确的泄漏表面。
    #
    root = tmp_path / "project"
    git_dir = root / ".git"
    sub = git_dir / "modules" / "libfoo"
    (sub / "logs").mkdir(parents=True)
    (root / "README.md").write_text("# p\n", encoding="utf-8")
    (git_dir / "FETCH_HEAD").write_text(
        "abc\tbranch 'main' of https://x-access-token:ghs_FETCHTOK@github.com/o/r\n",
        encoding="utf-8",
    )
    (sub / "config").write_text(
        '[remote "origin"]\n'
        "\turl = https://x-access-token:ghs_SUBCFGTOK@github.com/o/sub\n",
        encoding="utf-8",
    )
    (sub / "FETCH_HEAD").write_text(
        "def\tbranch 'main' of "
        "https://x-access-token:ghs_SUBFETCHTOK@github.com/o/sub\n",
        encoding="utf-8",
    )
    (sub / "logs" / "HEAD").write_text(
        "0 1 t <t@t.dev> 0 +0000\tclone: from "
        "https://x-access-token:ghs_SUBLOGTOK@github.com/o/sub\n",
        encoding="utf-8",
    )
    # 非凭据 .git 内部必须仍能在剥离中幸存下来。
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive",
        params={
            "path": str(root),
            "format": "tar.gz",
            "use_default_excludes": "false",
        },
    )

    assert resp.status_code == 200, resp.text
    names = _tar_members(resp.content)
    assert not any(n.endswith("/.git/FETCH_HEAD") for n in names)
    assert not any("/.git/modules/" in n and n.endswith("/config") for n in names)
    assert not any("/.git/modules/" in n and n.endswith("/FETCH_HEAD") for n in names)
    assert not any("/.git/modules/libfoo/logs/" in n for n in names)
    assert any(n.endswith("/.git/HEAD") for n in names)
    for token in (
        b"ghs_FETCHTOK",
        b"ghs_SUBCFGTOK",
        b"ghs_SUBFETCHTOK",
        b"ghs_SUBLOGTOK",
    ):
        assert token not in resp.content


# =============================================================================
# 存档测试 - tar.gz 空目录往返 + 每个段排除（infra#1444 L4 / L5）
# =============================================================================


def test_tar_gz_preserves_empty_directories(client, tmp_path):
    # 已创作但为空的目录必须往返（逐字节捕获）。
    root = tmp_path / "project"
    (root / "outputs").mkdir(parents=True)  # 空，没有文件
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("x = 1\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive", params={"path": str(root), "format": "tar.gz"}
    )

    assert resp.status_code == 200, resp.text
    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        outputs = tar.getmember(f"{root.name}/outputs")
        assert outputs.isdir()


def test_tar_gz_multi_segment_exclude_does_not_cross_slash(client, tmp_path):
    # 多段排除中的“*”不得与“/'”交叉（gitignore 语义，匹配 git-delta）。 '*/secret.txt'
    # 放弃了深度 2 的匹配，但保留了更深的匹配。
    #
    root = tmp_path / "project"
    (root / "a").mkdir(parents=True)
    (root / "a" / "secret.txt").write_text("drop\n", encoding="utf-8")
    (root / "a" / "b").mkdir()
    (root / "a" / "b" / "secret.txt").write_text("keep\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive",
        params={
            "path": str(root),
            "format": "tar.gz",
            "exclude": "*/secret.txt",
        },
    )

    assert resp.status_code == 200, resp.text
    names = _tar_members(resp.content)
    assert f"{root.name}/a/secret.txt" not in names
    assert f"{root.name}/a/b/secret.txt" in names


def test_exact_size_reader_pads_short_and_caps_long():
    """_ExactSizeReader 产生 EXACTLY 声明的大小：pad 短，cap 长。"""
    reader = file_router_module._ExactSizeReader
    short = reader(io.BytesIO(b"abc"), 5)
    chunks = []
    while chunk := short.read(2):
        chunks.append(chunk)
    assert b"".join(chunks) == b"abc\x00\x00"
    long = reader(io.BytesIO(b"abcdefgh"), 4)
    assert long.read(100) == b"abcd"
    assert long.read(100) == b""


def test_tar_stream_stays_aligned_when_source_shrinks(tmp_path):
    """在添加过程中截断的文件不得损坏 tar 流的 REST。

    回归在捕获OSError-并继续的 bug： tar.addfile 在复制主体之前写入头部（声明的大小）
    ，因此，短读取会破坏每个后续成员，默默地发送一个损坏的归档
    。_ExactSizeReader 会填充源短，确保写入的字节与头部和归档保持一致，从而保持完全可
    读。
    """
    out = tmp_path / "a.tar.gz"
    body2 = b"second member intact"
    with tarfile.open(out, "w:gz") as tar:
        # 成员一：标头声称有 10 个字节，但源仅产生 3 个字节（文件在获取其大小后被截断）
        # 。 读者将其填充到 10。
        #
        info1 = tarfile.TarInfo("one")
        info1.size = 10
        tar.addfile(info1, file_router_module._ExactSizeReader(io.BytesIO(b"abc"), 10))
        info2 = tarfile.TarInfo("two")
        info2.size = len(body2)
        tar.addfile(
            info2, file_router_module._ExactSizeReader(io.BytesIO(body2), len(body2))
        )
    # 完整读回必须成功（无 ReadError）并且成员 2 必须完好无损。
    with tarfile.open(out, "r:gz") as tar:
        assert tar.getnames() == ["one", "two"]
        member_two = tar.extractfile("two")
        assert member_two is not None
        assert member_two.read() == body2
        member_one = tar.extractfile("one")
        assert member_one is not None
        assert member_one.read() == b"abc" + b"\x00" * 7


def test_git_delta_dir_only_exclude_keeps_same_named_file(client, tmp_path):
    """“build/”默认排除会删除 build/ 目录，但 KEEPS 名为的文件
    'build' - git-delta 必须与仅 tar.gz 目录的剥离相匹配。"""
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init"], root)
    # 字面上名为“build”的常规文件必须是 KEPT...
    (root / "build").write_text("authored marker\n", encoding="utf-8")
    # ...while an actual build/ directory (the default 'build/' exclude) is dropped.
    (root / "sub" / "build").mkdir(parents=True)
    (root / "sub" / "build" / "out.o").write_text("compiled\n", encoding="utf-8")

    resp = client.get(
        "/api/file/archive", params={"path": str(root), "format": "git-delta"}
    )

    assert resp.status_code == 200, resp.text
    patch = resp.content.decode("utf-8")
    assert "diff --git a/build b/build" in patch  # 文件被保留
    assert "authored marker" in patch
    assert "sub/build/out.o" not in patch  # 该目录被排除
