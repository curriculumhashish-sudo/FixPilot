from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load(name: str, script_name: str):
    script_path = (
        Path(__file__).resolve().parents[2] / ".github" / "scripts" / script_name
    )
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# 首先导入 markdown_sections 和 check_pr_description，以便脚本可以根据我们上面加载的模块
# 解析它们的导入。
#
_load("markdown_sections", "markdown_sections.py")
_load("check_pr_description", "check_pr_description.py")
_prod = _load("refresh_linked_pr_checks", "refresh_linked_pr_checks.py")


def _event(action="labeled", label="ready-for-dev", number=12):
    return {
        "action": action,
        "issue": {"number": number},
        "label": {"name": label},
        "repository": {"full_name": "org/repo"},
    }


def _write_event(monkeypatch, payload, tmp_path):
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(payload))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))


class _FakeProc:
    def __init__(self, stdout: str = ""):
        self.returncode = 0
        self.stdout = stdout
        self.stderr = ""


def _recording_run(calls):
    def _call(args):
        calls.append(args)
        # 列出运行返回一次运行； 重新运行是无操作成功。
        if any("/actions/runs" in a for a in args):
            return _FakeProc("8675309 2026-08-13T00:00:00Z\n")
        return _FakeProc()

    return _call


def _fail_on_call(value):
    def _call(*args, **kwargs):
        raise AssertionError(value)

    return _call


def test_noop_for_unrelated_label(monkeypatch, tmp_path):
    _write_event(monkeypatch, _event(label="bug"), tmp_path)
    monkeypatch.setattr(_prod, "_linked_open_prs", _fail_on_call("unexpected"))
    assert _prod.main() == 0


def test_noop_for_unrelated_action(monkeypatch, tmp_path):
    _write_event(monkeypatch, _event(action="edited"), tmp_path)
    monkeypatch.setattr(_prod, "_linked_open_prs", _fail_on_call("unexpected"))
    assert _prod.main() == 0


def test_reruns_linked_pr_check_when_readiness_label_changes(monkeypatch, tmp_path):
    _write_event(monkeypatch, _event(), tmp_path)
    monkeypatch.setattr(
        _prod,
        "_linked_open_prs",
        lambda repo, num: [{"number": 7, "headRefOid": "abc123"}],
    )
    monkeypatch.setattr(_prod, "_run", lambda args: _FakeProc("Fixes #12"))
    seen = []
    monkeypatch.setattr(
        _prod,
        "_rerun_pr_description_check",
        lambda repo, sha: (seen.append((repo, sha)) or True),
    )
    assert _prod.main() == 0
    assert seen == [("org/repo", "abc123")]


def test_reruns_linked_pr_check_when_readiness_label_removed(monkeypatch, tmp_path):
    """丢失 `ready-for-dev` 还必须刷新链接的 PR 门（未标记）。"""
    _write_event(monkeypatch, _event(action="unlabeled"), tmp_path)
    monkeypatch.setattr(
        _prod,
        "_linked_open_prs",
        lambda repo, num: [{"number": 7, "headRefOid": "abc123"}],
    )
    monkeypatch.setattr(_prod, "_run", lambda args: _FakeProc("Fixes #12"))
    seen = []
    monkeypatch.setattr(
        _prod,
        "_rerun_pr_description_check",
        lambda repo, sha: (seen.append((repo, sha)) or True),
    )
    assert _prod.main() == 0
    assert seen == [("org/repo", "abc123")]


def test_skips_cross_referenced_pr_that_does_not_link_issue(monkeypatch, tmp_path):
    _write_event(monkeypatch, _event(), tmp_path)
    monkeypatch.setattr(
        _prod,
        "_linked_open_prs",
        lambda repo, num: [{"number": 7, "headRefOid": "abc123"}],
    )
    # 正文提到了#99（交叉引用），但没有提到事件的问题#12。
    monkeypatch.setattr(_prod, "_run", lambda args: _FakeProc("Fixes #99"))
    seen = []
    monkeypatch.setattr(
        _prod,
        "_rerun_pr_description_check",
        lambda repo, sha: (seen.append((repo, sha)) or True),
    )
    assert _prod.main() == 0
    assert seen == []


def test_rerun_pr_description_check_lists_runs_with_get(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(_prod, "_run", _recording_run(calls))
    assert _prod._rerun_pr_description_check("org/repo", "abc123") is True
    # 列出运行必须是显式的 GET: `-f` args 单独切换 `gh api` 到 POST，这会在运行集合端点
    # 上发生 404 错误（在野外可见）。
    #
    list_call = next(a for a in calls if "repos/org/repo/actions/runs" in a)
    assert "-X" in list_call
    assert list_call[list_call.index("-X") + 1] == "GET"
    # 然后通过显式 POST 重新运行所选的运行。
    rerun_call = next(a for a in calls if any("/rerun" in arg for arg in a))
    assert rerun_call[rerun_call.index("api") + 1 : rerun_call.index("api") + 3] == [
        "-X",
        "POST",
    ]
