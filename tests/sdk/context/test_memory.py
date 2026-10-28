"""单元测试用于两层持久内存加载器 (``context/memory.py``)。"""

import re
from pathlib import Path

import pytest

from openhands.sdk.agent import Agent
from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.context.memory import MEMORY_INDEX_RELPATH, load_memory
from openhands.sdk.llm import LLM


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """将用户内存层 (``~/.openhands/memory/``) 指向临时主目录。

    USERPROFILE 是 ``Path.home()`` 在 Windows 上读取的内容，其中 HOME 是无操作。
    ``OH_PERSISTENCE_DIR`` 也被清除：它会覆盖相对于 home 的基数，因此导出它的开发人员
    将运行不同的测试。
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("OH_PERSISTENCE_DIR", raising=False)
    return home


def _write_index(root: Path, text: str) -> None:
    index = root / MEMORY_INDEX_RELPATH
    index.parent.mkdir(parents=True)
    index.write_text(text)


def test_load_memory_returns_none_without_index_files(tmp_path: Path) -> None:
    assert load_memory(tmp_path / "workspace") is None


def test_load_memory_reads_project_index(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_index(workspace, "- run tests with `uv run pytest`\n")

    assert load_memory(workspace) == (
        "# Project memory (.openhands/memory/MEMORY.md)\n"
        "- run tests with `uv run pytest`"
    )


def test_load_memory_reads_user_index(isolated_home: Path, tmp_path: Path) -> None:
    _write_index(isolated_home, "- prefers uv over pip\n")

    assert load_memory(tmp_path / "workspace") == (
        "# User memory (~/.openhands/memory/MEMORY.md)\n- prefers uv over pip"
    )


def test_load_memory_orders_user_before_project(
    isolated_home: Path, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    _write_index(isolated_home, "user fact")
    _write_index(workspace, "project fact")

    text = load_memory(workspace)

    assert text is not None
    assert text.index("user fact") < text.index("project fact")


def test_load_memory_truncates_whole_lines_from_top_of_tier(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_index(workspace, "OLD\n" + ("x" * 40 + "\n") * 4 + "NEW")

    text = load_memory(workspace, char_budget=160)

    assert text is not None
    lines = text.splitlines()
    assert lines[0] == "# Project memory (.openhands/memory/MEMORY.md)"
    assert lines[1] == "[earlier memory truncated]"
    assert text.endswith("NEW")
    assert "OLD" not in text
    assert len(text) <= 160


def test_load_memory_truncation_keeps_both_tier_headers(
    isolated_home: Path, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    _write_index(isolated_home, "- prefers tabs")
    _write_index(workspace, "OLD-PROJECT\n" + ("y" * 40 + "\n") * 5 + "NEW-PROJECT")

    text = load_memory(workspace, char_budget=260)

    assert text is not None
    lines = text.splitlines()
    assert "# User memory (~/.openhands/memory/MEMORY.md)" in lines
    assert "# Project memory (.openhands/memory/MEMORY.md)" in lines
    # 较短的用户层适合其份额，因此其内容不会受到影响。
    assert "- prefers tabs" in lines
    assert text.endswith("NEW-PROJECT")
    assert "OLD-PROJECT" not in text
    assert lines.count("[earlier memory truncated]") == 1
    assert len(text) <= 260


def test_load_memory_truncation_drops_no_partial_lines(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    original_lines = [f"memory fact number {i:02d} padded {'z' * i}" for i in range(12)]
    _write_index(workspace, "\n".join(original_lines))

    text = load_memory(workspace, char_budget=180)

    assert text is not None
    assert "[earlier memory truncated]" in text
    allowed = {
        "# Project memory (.openhands/memory/MEMORY.md)",
        "[earlier memory truncated]",
        *original_lines,
    }
    assert set(text.splitlines()) <= allowed
    assert len(text) <= 180


def test_load_memory_treats_empty_index_as_absent(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_index(workspace, "   \n\n")

    assert load_memory(workspace) is None


def test_load_memory_treats_unreadable_index_as_absent(
    isolated_home: Path, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    # read_text 应该 OSError。
    (workspace / MEMORY_INDEX_RELPATH).mkdir(parents=True)
    _write_index(isolated_home, "user fact")

    text = load_memory(workspace)

    assert text is not None
    assert "user fact" in text
    assert "Project memory" not in text


# --- 读/写对齐：写引导和加载器在路径上达成一致 ----

# 静态 <MEMORY> 块呈现的用户层项目符号 e.g。 “* 用户记忆：`/persist/memory/` — 知识和偏
# 好......”。
#
_USER_MEMORY_RE = re.compile(r"\* User memory: `([^`]+)`")


def _advertised_user_memory_dir(agent: Agent) -> Path:
    """智能体被指示写入的用户内存目录。

    从渲染的静态 ``<MEMORY>`` 块中解析出来 - i.e。 模型看到的确切文本，而不是内部助手
    ——因此测试证明指示的写入路径与
    ``load_memory`` 的读取路径保持一致。 前导 ``~`` 被扩展，因此返回的路径与加载程序
    的解析路径相当。
    """
    static = agent.static_system_message
    match = _USER_MEMORY_RE.search(static)
    assert match, f"no user-memory bullet in static <MEMORY> block:\n{static}"
    return Path(match.group(1)).expanduser()


def _memory_agent() -> Agent:
    return Agent(
        llm=LLM(model="claude-sonnet-4-5", usage_id="memory-align"),
        tools=[],
        agent_context=AgentContext(load_memory=True),
    )


def test_instructed_write_path_matches_loader_read_path_with_persistence_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """设置 OH_PERSISTENCE_DIR 后，智能体被告知要写入的目录
    正是 ``load_memory`` 看起来的地方——所以用户内存在恢复后仍然存在。"""
    persistence = tmp_path / "persistent"
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(persistence))

    write_dir = _advertised_user_memory_dir(_memory_agent())
    # 该指令指向 OH_PERSISTENCE_DIR，而不是临时的 $HOME。
    assert write_dir == persistence / "memory"
    assert str(tmp_path / "home") not in str(write_dir)

    # 模拟指令后的智能体，然后确认加载程序读取该写回（未对齐的往返的两半）。
    #
    memory_md = write_dir / "MEMORY.md"
    memory_md.parent.mkdir(parents=True)
    memory_md.write_text("- prefers ruff over flake8\n")

    loaded = load_memory(tmp_path / "workspace")
    assert loaded is not None
    assert "- prefers ruff over flake8" in loaded
    assert "# User memory" in loaded


def test_instructed_write_path_matches_loader_read_path_home_fallback(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """如果没有 OH_PERSISTENCE_DIR，两半都会回落到 ~/.openhands/memory."""
    monkeypatch.delenv("OH_PERSISTENCE_DIR", raising=False)

    write_dir = _advertised_user_memory_dir(_memory_agent())
    assert write_dir == isolated_home / ".openhands" / "memory"

    memory_md = write_dir / "MEMORY.md"
    memory_md.parent.mkdir(parents=True)
    memory_md.write_text("- home fallback fact\n")

    loaded = load_memory(tmp_path / "workspace")
    assert loaded is not None
    assert "- home fallback fact" in loaded


def test_load_memory_user_header_reflects_persistence_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """设置 OH_PERSISTENCE_DIR 后，加载的用户层标头将命名真实的
    读取路径 - 不是过时的 ``~/.openhands/memory/`` - 因此它与 <MEMORY> 指南中公布的写
    入位置匹配。
    """
    persistence = tmp_path / "persistent"
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(persistence))
    user_memory = persistence / "memory"
    user_memory.mkdir(parents=True)
    (user_memory / "MEMORY.md").write_text("- prefers ruff\n")

    loaded = load_memory(tmp_path / "workspace")

    assert loaded is not None
    expected = user_memory / "MEMORY.md"
    assert loaded.startswith(f"# User memory ({expected})")
    assert "~/.openhands/memory/MEMORY.md" not in loaded


def test_load_memory_user_header_uses_tilde_without_persistence_dir(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """如果没有 OH_PERSISTENCE_DIR，标头将保持普通波形符形式，并且永远不会
    泄漏扩展的每用户主路径。"""
    monkeypatch.delenv("OH_PERSISTENCE_DIR", raising=False)
    _write_index(isolated_home, "- prefers uv over pip\n")

    loaded = load_memory(tmp_path / "workspace")

    assert loaded is not None
    assert loaded.startswith("# User memory (~/.openhands/memory/MEMORY.md)")
    assert str(isolated_home) not in loaded


def test_user_memory_line_absent_when_memory_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """除非启用内存，否则不会公布用户内存目录。"""
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path / "persistent"))
    agent = Agent(
        llm=LLM(model="claude-sonnet-4-5", usage_id="memory-off"),
        tools=[],
        agent_context=AgentContext(load_memory=False),
    )
    assert "* User memory:" not in agent.static_system_message


def test_instructed_write_path_resolved_at_call_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """每次渲染都会解析路径，因此在之后设置 OH_PERSISTENCE_DIR
    智能体仍然被构造（匹配 get_user_persistence_dir）。"""
    agent = _memory_agent()

    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path / "late"))
    assert _advertised_user_memory_dir(agent) == tmp_path / "late" / "memory"

    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path / "later"))
    assert _advertised_user_memory_dir(agent) == tmp_path / "later" / "memory"
