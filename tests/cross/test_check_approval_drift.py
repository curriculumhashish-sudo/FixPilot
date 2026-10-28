"""测试批准漂移 (TOCTOU) 发布检查。

聚焦于确定性、网络无感的表面：如何合并-PR 主题映射到 PR 数字（最重要的是，哪些是 *不*
 映射并必须呈现为盲点)，以及机器人检测。 的 GitHub  REST c
alls in
``audit_pr``/``main``此处不执行。

``merged_pr_numbers`` 向 ``git log`` 发起攻击； 我们通过对模块的 ``run_git`` 进行猴子
修补来返回预设日志来确定性地驱动它，因
此不需要真正的存储库历史记录。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module(name: str):
    repo_root = Path(__file__).resolve().parents[2]
    scripts_dir = repo_root / ".github" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = scripts_dir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_drift = _load_script_module("check_approval_drift")

_US = "\x1f"  # git Pretty-format 中使用的单位分隔符


def _fake_log(*subjects: str) -> str:
    """从主题构建 ``%H\\x1f%s`` git 日志正文（sha 不相关）。"""
    return "\n".join(f"deadbeef{i}{_US}{s}" for i, s in enumerate(subjects))


def test_matched_and_unmapped_are_split(monkeypatch):
    log = _fake_log(
        "feat: add a thing (#4001)",
        "fix: a merge commit with no PR suffix",
        "chore: bump deps (#4002)",
        "Merge branch 'main' into feature",
    )
    monkeypatch.setattr(_drift, "run_git", lambda *a, **k: log)

    matched, unmapped = _drift.merged_pr_numbers("v1.0.0")

    assert matched == [
        (4001, "feat: add a thing (#4001)"),
        (4002, "chore: bump deps (#4002)"),
    ]
    assert unmapped == [
        "fix: a merge commit with no PR suffix",
        "Merge branch 'main' into feature",
    ]


def test_all_mapped_leaves_no_blind_spot(monkeypatch):
    log = _fake_log("a (#1)", "b (#2)", "c (#3)")
    monkeypatch.setattr(_drift, "run_git", lambda *a, **k: log)

    matched, unmapped = _drift.merged_pr_numbers("v1.0.0")

    assert [n for n, _ in matched] == [1, 2, 3]
    assert unmapped == []


def test_trailing_whitespace_after_pr_number_still_matches(monkeypatch):
    monkeypatch.setattr(_drift, "run_git", lambda *a, **k: _fake_log("x (#42)  "))
    matched, unmapped = _drift.merged_pr_numbers("v1.0.0")
    assert matched == [(42, "x (#42)  ")]
    assert unmapped == []


def test_pr_ref_not_at_end_is_unmapped(monkeypatch):
    # 不是尾随 token 的“(#N)”不是挤压合并 PR id。
    monkeypatch.setattr(
        _drift, "run_git", lambda *a, **k: _fake_log("revert of (#7) change")
    )
    matched, unmapped = _drift.merged_pr_numbers("v1.0.0")
    assert matched == []
    assert unmapped == ["revert of (#7) change"]


def test_is_bot_detects_type_and_suffix():
    assert _drift._is_bot({"type": "Bot"}) is True
    assert _drift._is_bot({"login": "dependabot[bot]"}) is True
    assert _drift._is_bot({"login": "octocat", "type": "User"}) is False
