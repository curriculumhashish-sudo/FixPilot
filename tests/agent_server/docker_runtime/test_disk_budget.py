import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr

from openhands.agent_server.config import Config
from openhands.agent_server.docker_runtime.registry import (
    ConversationContainer,
    DockerConversationRegistry,
)
from openhands.agent_server.storage import reclaimer as reclaimer_module, selectors


def registry(tmp_path, monkeypatch) -> DockerConversationRegistry:
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path / "persistence"))
    return DockerConversationRegistry(
        Config(
            conversations_path=tmp_path / "conversations",
            workspace_path=tmp_path / "workspaces",
            secret_key=SecretStr("outer-key"),
            conversation_storage_disk_budget=0.8,
        )
    )


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(repo: Path) -> tuple[list[Path], list[Path]]:
    """安装了 deps 的结帐； 返回（可重建的目录，保留的文件）。"""
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q")
    files = {
        ".gitignore": "node_modules/\n.venv/\n.env\n",
        "main.py": "print('hi')",
        "node_modules/left-pad/index.js": "module.exports = 1",
        ".venv/pyvenv.cfg": "home = /usr",
        # 未被追踪，未被忽视：智能体自己的作品。
        "notes.md": "todo",
        # 已忽略，但文件：可能保存无人可以重建的设置。
        ".env": "TOKEN=x",
    }
    for name, content in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(content)
    git(repo, "add", ".gitignore", "main.py")
    shed = [repo / "node_modules", repo / ".venv"]
    kept = [repo / ".gitignore", repo / "main.py", repo / "notes.md", repo / ".env"]
    return shed, kept


def provision(
    runtime: DockerConversationRegistry, age: float, workspace: Path | None = None
) -> tuple[UUID, Path]:
    conversation_id = uuid4()
    identity = runtime.provisioning.create(conversation_id, workspace)
    # 启动的容器已创建其持久化目录，无论工作区是什么。
    persistence = runtime.provisioning.runtime_dir(conversation_id) / "persistence"
    persistence.mkdir(parents=True, exist_ok=True)
    state = runtime.conversation_dir(conversation_id) / "base_state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("{}")
    os.utime(state, (age, age))
    return conversation_id, identity.workspace_path


@pytest.fixture
def usage(monkeypatch) -> Iterator[list[float]]:
    """磁盘使用情况读数，每次检查一个； 最后一个重复。"""
    readings: list[float] = []

    def read(_path: Path) -> float:
        return readings.pop(0) if len(readings) > 1 else readings[0]

    monkeypatch.setattr(reclaimer_module, "disk_usage", read)
    yield readings


@pytest.mark.asyncio
async def test_under_budget_sheds_nothing(tmp_path, monkeypatch, usage):
    runtime = registry(tmp_path, monkeypatch)
    _, workspace = provision(runtime, age=1)
    shed, _ = make_repo(workspace)
    usage.append(0.5)

    await runtime.reclaimer.run_pass()

    assert all(path.is_dir() for path in shed)


@pytest.mark.asyncio
async def test_over_budget_sheds_oldest_stopped_runtime_first(
    tmp_path, monkeypatch, usage
):
    runtime = registry(tmp_path, monkeypatch)
    _, new_workspace = provision(runtime, age=2_000)
    _, old_workspace = provision(runtime, age=1_000)
    new_shed, _ = make_repo(new_workspace)
    old_shed, old_kept = make_repo(old_workspace)
    # 超出预算，然后在最旧的运行时间结束后恢复预算。
    usage.extend([0.95, 0.7])

    await runtime.reclaimer.run_pass()

    assert not any(path.exists() for path in old_shed)
    assert all(path.is_file() for path in old_kept)
    assert all(path.is_dir() for path in new_shed)
    assert list(runtime.reclaimer.trash.dir.iterdir()) == []


@pytest.mark.asyncio
async def test_live_runtime_keeps_its_files(tmp_path, monkeypatch, usage):
    runtime = registry(tmp_path, monkeypatch)
    conversation_id, workspace = provision(runtime, age=1)
    shed, _ = make_repo(workspace)
    runtime._containers[conversation_id] = ConversationContainer(
        host="http://127.0.0.1", api_key="k", container_id="c"
    )
    usage.append(0.95)

    await runtime.reclaimer.run_pass()

    assert all(path.is_dir() for path in shed)


@pytest.mark.asyncio
async def test_caller_supplied_workspace_is_never_touched(tmp_path, monkeypatch, usage):
    runtime = registry(tmp_path, monkeypatch)
    _, workspace = provision(runtime, age=1, workspace=tmp_path / "user-checkout")
    shed, _ = make_repo(workspace)
    usage.append(0.95)

    await runtime.reclaimer.run_pass()

    assert all(path.is_dir() for path in shed)


@pytest.mark.asyncio
async def test_nested_checkouts_are_shed_but_ignored_repos_kept(
    tmp_path, monkeypatch, usage
):
    runtime = registry(tmp_path, monkeypatch)
    _, workspace = provision(runtime, age=1)
    (workspace).mkdir(parents=True, exist_ok=True)
    nested_shed, nested_kept = make_repo(workspace / "project")
    # 忽略克隆存储库的工作区不得丢失克隆。
    make_repo(workspace / "vendor-clone")
    git(workspace, "init", "-q")
    (workspace / ".gitignore").write_text("vendor-clone/\n")
    usage.append(0.95)

    await runtime.reclaimer.run_pass()

    assert not any(path.exists() for path in nested_shed)
    assert all(path.is_file() for path in nested_kept)
    assert (workspace / "vendor-clone" / "main.py").is_file()


@pytest.mark.asyncio
async def test_nested_ignore_matches_shed_only_the_top_dir(
    tmp_path, monkeypatch, usage, caplog
):
    runtime = registry(tmp_path, monkeypatch)
    _, workspace = provision(runtime, age=1)
    make_repo(workspace)
    # git lists public/, public/locales/ and every language dir for this.
    (workspace / ".gitignore").write_text("public/locales/**/*\n")
    for lang in ("ar", "de"):
        (workspace / "public" / "locales" / lang).mkdir(parents=True)
        (workspace / "public" / "locales" / lang / "t.json").write_text("{}")
    usage.append(0.95)

    assert selectors.git_ignored_dirs(workspace) == [workspace / "public"]
    await runtime.reclaimer.run_pass()

    assert not (workspace / "public").exists()
    assert (workspace / "main.py").is_file()
    assert "Failed to shed" not in caplog.text


@pytest.mark.asyncio
async def test_repo_config_cannot_run_commands_on_the_host(
    tmp_path, monkeypatch, usage
):
    runtime = registry(tmp_path, monkeypatch)
    _, workspace = provision(runtime, age=1)
    make_repo(workspace)
    marker = tmp_path / "pwned"
    hook = tmp_path / "fsmonitor.sh"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
    hook.chmod(0o755)
    git(workspace, "config", "core.fsmonitor", str(hook))
    usage.append(0.95)

    await runtime.reclaimer.run_pass()

    assert not marker.exists()


@pytest.mark.asyncio
async def test_non_git_workspace_is_skipped(tmp_path, monkeypatch, usage):
    runtime = registry(tmp_path, monkeypatch)
    _, workspace = provision(runtime, age=1)
    deps = workspace / "node_modules" / "left-pad"
    deps.mkdir(parents=True)
    usage.append(0.95)

    await runtime.reclaimer.run_pass()

    assert deps.is_dir()


@pytest.mark.asyncio
async def test_disk_budget_loop_runs_only_when_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(reclaimer_module, "MAINTENANCE_INTERVAL", 3600)
    runtime = registry(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime, "cleanup_stale_containers", lambda: None)

    await runtime.start()
    assert runtime.reclaimer._maintenance is not None
    await runtime.shutdown()
    assert runtime.reclaimer._maintenance is None

    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path / "persistence"))
    unset = DockerConversationRegistry(
        Config(
            conversations_path=tmp_path / "conversations",
            secret_key=SecretStr("outer-key"),
        )
    )
    monkeypatch.setattr(unset, "cleanup_stale_containers", lambda: None)
    await unset.start()
    assert unset.reclaimer._maintenance is None
    await unset.shutdown()


@pytest.mark.asyncio
async def test_ignored_dir_holding_a_clone_is_kept(tmp_path, monkeypatch, usage):
    runtime = registry(tmp_path, monkeypatch)
    _, workspace = provision(runtime, age=1)
    shed, _ = make_repo(workspace)
    (workspace / ".gitignore").write_text("node_modules/\n.venv/\nvendor/\n")
    # 在被忽略的目录中向下两级克隆不是构建输出。
    clone = workspace / "vendor" / "libs" / "upstream"
    make_repo(clone)
    usage.append(0.95)

    await runtime.reclaimer.run_pass()

    assert not any(path.exists() for path in shed)
    assert (clone / "main.py").is_file()


def test_storage_budget_is_read_from_nested_env(monkeypatch):
    from openhands.agent_server.config import load_config

    monkeypatch.setenv("OH_CONVERSATION_STORAGE_DISK_BUDGET", "0.8")

    assert load_config().conversation_storage_disk_budget == 0.8
