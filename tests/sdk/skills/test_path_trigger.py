"""测试路径范围的技能（“规则”）：PathTrigger、全局匹配、加载、分区排除和 AgentContext
工具使用注入匹配器。
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.skills import (
    KeywordTrigger,
    PathTrigger,
    Skill,
    load_project_skills,
    utils as skills_utils,
)
from openhands.sdk.skills.exceptions import SkillValidationError
from openhands.sdk.skills.skill import path_matches_glob


_HAS_GIT = shutil.which("git") is not None


@pytest.mark.parametrize(
    ("file_path", "pattern", "expected"),
    [
        # ** 跨越任意深度（包括零）的目录分隔符。
        ("src/api/x.ts", "src/api/**/*.ts", True),
        ("src/api/v1/deep/x.ts", "src/api/**/*.ts", True),
        ("x.test.tsx", "**/*.test.tsx", True),
        ("a/b/x.test.tsx", "**/*.test.tsx", True),
        # 无斜线模式与任意深度的基本名称匹配 (gitignore)。
        ("a/b/x.ts", "*.ts", True),
        ("x.ts", "*.ts", True),
        ("pkg/Makefile", "Makefile", True),
        # * 停留在单个路径段内。
        ("src/api/x.ts", "src/*/x.ts", True),
        ("src/api/v1/x.ts", "src/*/x.ts", False),
        # 不匹配。
        ("README.md", "*.ts", False),
        ("a/b/x.ts", "src/**", False),
        ("src/a", "src/**", True),
        ("", "**/*.ts", False),
        # `?` 恰好匹配一个非分隔符（绝不会与 `/` 交叉）。
        ("ab.ts", "a?.ts", True),
        ("abc.ts", "a?.ts", False),
        ("a/b.ts", "a?.ts", False),
        # 即使有显式前缀，`*` 仍保留在一个段内。
        ("a/b.ts", "a/*.ts", True),
        ("a/b/c.ts", "a/*.ts", False),
        # Glob 元字符是文字，而不是正则表达式： `.` 只匹配一个点并且
        # `+`/parens 匹配自身（防止未转义的正则表达式错误）。
        ("a.b.ts", "*.b.ts", True),
        ("fileXname.ts", "file.name.ts", False),
        ("a+b.ts", "a+b.ts", True),
        ("aaab.ts", "a+b.ts", False),
        ("a(b).ts", "a(b).ts", True),
        # 匹配区分大小写。
        ("README.md", "readme.md", False),
        # `*` 匹配前导点文件（gitignore 语义，与 shell glob 不同）。
        ("src/.env", "src/*", True),
    ],
)
def test_path_matches_glob(file_path: str, pattern: str, expected: bool) -> None:
    assert path_matches_glob(file_path, pattern) is expected


def test_empty_pattern_never_matches() -> None:
    assert path_matches_glob("anything.ts", "") is False


def _write_rule(directory: Path, name: str, frontmatter: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(f"---\n{frontmatter}\n---\n{body}\n")
    return path


def test_paths_frontmatter_yaml_list_creates_path_trigger(tmp_path: Path) -> None:
    path = _write_rule(
        tmp_path,
        "api.md",
        'paths:\n  - "src/api/**/*.ts"\n  - "**/*.test.tsx"',
        "Use zod for API validation.",
    )
    skill = Skill.load(path)
    assert isinstance(skill.trigger, PathTrigger)
    assert skill.trigger.paths == ["src/api/**/*.ts", "**/*.test.tsx"]
    assert skill.content.strip() == "Use zod for API validation."


def test_paths_frontmatter_comma_string_creates_path_trigger(tmp_path: Path) -> None:
    path = _write_rule(tmp_path, "r.md", "paths: src/**/*.py, tests/**/*.py", "body")
    skill = Skill.load(path)
    assert isinstance(skill.trigger, PathTrigger)
    assert skill.trigger.paths == ["src/**/*.py", "tests/**/*.py"]


def test_match_path_trigger_returns_matched_pattern(tmp_path: Path) -> None:
    skill = Skill(name="r", content="c", trigger=PathTrigger(paths=["src/**/*.ts"]))
    assert skill.match_path_trigger("src/api/x.ts") == "src/**/*.ts"
    assert skill.match_path_trigger("README.md") is None


def test_path_trigger_is_inert_on_text_matching() -> None:
    """PathTrigger 永远不会在用户消息文本上触发（仅在文件路径上）。"""
    skill = Skill(name="r", content="c", trigger=PathTrigger(paths=["src/**/*.ts"]))
    assert skill.match_trigger("please edit src/api/x.ts and src/**/*.ts") is None


def test_keyword_skill_does_not_match_paths() -> None:
    from openhands.sdk.skills import KeywordTrigger

    skill = Skill(name="k", content="c", trigger=KeywordTrigger(keywords=["deploy"]))
    assert skill.match_path_trigger("src/api/x.ts") is None


def test_path_rule_loads_from_skills_dir(tmp_path: Path) -> None:
    """路径规则只是技能目录中具有 ``paths:`` 前置元数据的技能。"""
    _write_rule(
        tmp_path / ".openhands" / "skills",
        "api.md",
        'paths:\n  - "src/api/**/*.ts"',
        "API rule",
    )
    skills = load_project_skills(tmp_path)
    by_name = {s.name: s for s in skills}
    assert "api" in by_name
    assert isinstance(by_name["api"].trigger, PathTrigger)


def test_partition_excludes_path_rules_from_catalog_and_repo_context() -> None:
    """路径规则既不在 <available_skills> 也不在 <REPO_CONTEXT> 中。"""
    ctx = AgentContext(
        skills=[
            Skill(name="rule", content="c", trigger=PathTrigger(paths=["**/*.ts"])),
            Skill(name="repo", content="always"),  # trigger=None => repo context
        ]
    )
    repo_skills, available_skills = ctx._partition_skills()
    assert [s.name for s in repo_skills] == ["repo"]
    assert [s.name for s in available_skills] == []


def test_get_tool_use_suffix_match_nomatch_and_dedup() -> None:
    ctx = AgentContext(
        skills=[
            Skill(
                name="api",
                content="Use zod.",
                trigger=PathTrigger(paths=["src/api/**/*.ts"]),
            )
        ]
    )
    # 匹配路径注入内容并报告激活的规则。
    result = ctx.get_tool_use_suffix("src/api/users.ts", skip_skill_names=[])
    assert result is not None
    content, activated = result
    assert activated == ["api"]
    assert "Use zod." in content.text

    # 不匹配的路径不会注入任何内容。
    assert ctx.get_tool_use_suffix("README.md", skip_skill_names=[]) is None

    # 已激活的规则将被跳过（重复数据删除）。
    assert ctx.get_tool_use_suffix("src/api/users.ts", skip_skill_names=["api"]) is None


def test_get_tool_use_suffix_empty_path_returns_none() -> None:
    ctx = AgentContext(
        skills=[Skill(name="r", content="c", trigger=PathTrigger(paths=["**/*.ts"]))]
    )
    assert ctx.get_tool_use_suffix("", skip_skill_names=[]) is None


def test_multiple_rules_match_one_path_all_injected() -> None:
    ctx = AgentContext(
        skills=[
            Skill(name="ts", content="TS rule", trigger=PathTrigger(paths=["**/*.ts"])),
            Skill(
                name="api",
                content="API rule",
                trigger=PathTrigger(paths=["src/api/**"]),
            ),
            Skill(name="py", content="PY rule", trigger=PathTrigger(paths=["**/*.py"])),
        ]
    )
    result = ctx.get_tool_use_suffix("src/api/users.ts", skip_skill_names=[])
    assert result is not None
    content, activated = result
    assert activated == ["ts", "api"]  # 两者都匹配，py 被排除
    assert "TS rule" in content.text and "API rule" in content.text
    assert "PY rule" not in content.text


def test_path_rule_forces_disable_model_invocation() -> None:
    """路径规则不得公布或调用； 旗帜被强制
    无论构建路径如何（直接或前置元数据）。"""
    direct = Skill(name="r", content="c", trigger=PathTrigger(paths=["**/*.ts"]))
    assert direct.disable_model_invocation is True


def test_path_rule_serialization_round_trip() -> None:
    skill = Skill(
        name="api",
        content="Use zod.",
        source="/repo/.openhands/skills/api.md",
        trigger=PathTrigger(paths=["src/api/**/*.ts", "**/*.test.ts"]),
    )
    back = Skill.model_validate_json(skill.model_dump_json())
    assert isinstance(back.trigger, PathTrigger)
    assert back.trigger.paths == ["src/api/**/*.ts", "**/*.test.ts"]
    assert back.disable_model_invocation is True


def test_paths_and_triggers_frontmatter_paths_wins(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """同时具有 `paths:` 和 `triggers:` 的文件成为 PathTrigger 规则，并且
    删除的 `triggers:` 通过警告浮出水面。"""
    path = _write_rule(
        tmp_path, "both.md", 'paths:\n  - "**/*.ts"\ntriggers:\n  - "deploy"', "body"
    )
    with caplog.at_level("WARNING"):
        skill = Skill.load(path)
    assert isinstance(skill.trigger, PathTrigger)
    assert "paths" in caplog.text and "'triggers'" in caplog.text
    assert "deploy" in caplog.text


def test_paths_and_inputs_frontmatter_warns_inputs_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """`paths:` 与 `inputs:` 一起获胜并警告 `inputs:` 被忽略。"""
    path = _write_rule(
        tmp_path,
        "both.md",
        'paths:\n  - "**/*.ts"\ninputs:\n  - name: x\n    description: d',
        "body",
    )
    with caplog.at_level("WARNING"):
        skill = Skill.load(path)
    assert isinstance(skill.trigger, PathTrigger)
    assert "'inputs'" in caplog.text


def test_paths_only_frontmatter_does_not_warn(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """加载不带 `triggers:`/`inputs:` 的路径规则时不会发出警告。"""
    path = _write_rule(tmp_path, "r.md", 'paths:\n  - "**/*.ts"', "body")
    with caplog.at_level("WARNING"):
        skill = Skill.load(path)
    assert isinstance(skill.trigger, PathTrigger)
    assert "will be ignored" not in caplog.text


@pytest.mark.parametrize("value", ["", "[]"])
def test_empty_paths_is_not_a_path_trigger(tmp_path: Path, value: str) -> None:
    """空 `paths:` 前置元数据会导致触发=None（不是规则）。"""
    path = _write_rule(tmp_path, "r.md", f"paths: {value}", "body")
    skill = Skill.load(path)
    assert not isinstance(skill.trigger, PathTrigger)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a/**, **/*.ts", ["a/**", "**/*.ts"]),  # 逗号字符串，删除空格
        (["a/**", " b ", ""], ["a/**", "b"]),  # 列表，修剪+清空丢弃
        ("  ,  ", None),  # 仅分隔符/空格 -> None
        ([], None),
        (None, None),
    ],
)
def test_parse_paths(value, expected) -> None:
    assert Skill._parse_paths(value) == expected


def test_invalid_paths_type_raises() -> None:
    with pytest.raises(SkillValidationError, match="paths must be a string or list"):
        Skill._parse_paths(5)  # type: ignore[arg-type]


def test_match_path_trigger_none_for_non_path_triggers() -> None:
    kw = Skill(name="k", content="c", trigger=KeywordTrigger(keywords=["deploy"]))
    repo = Skill(name="r", content="c")  # trigger=None
    assert kw.match_path_trigger("src/api/x.ts") is None
    assert repo.match_path_trigger("src/api/x.ts") is None


# ---------------------------------------------------------------------------
# 嵌套AGENTS.md/第三方文件->目录范围的路径规则。 根 AGENTS.md 始终保持在线状态； 嵌套的
# 仅当智能体触及其目录下的文件时才注入。
# ---------------------------------------------------------------------------


def _make_agents_workspace(tmp_path: Path) -> Path:
    """根AGENTS.md加上两个嵌套的（一浅一深）。"""
    (tmp_path / "AGENTS.md").write_text("ROOT guidance.\n")
    server = tmp_path / "server"
    server.mkdir()
    (server / "AGENTS.md").write_text("SERVER rule: validate inputs.\n")
    deep = tmp_path / "pkg" / "sub"
    deep.mkdir(parents=True)
    (deep / "AGENTS.md").write_text("SUB rule.\n")
    return tmp_path


def _force_walk_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """使用 filesystem-walk 路径进行发现（无 git）。"""
    monkeypatch.setattr(skills_utils, "_git_worktree_relpaths", lambda _wd: None)


def _assert_nested_rules(skills_by_name: dict[str, Skill]) -> None:
    # 根保持始终在线（完整内容，无路径触发）。
    assert skills_by_name["agents"].trigger is None

    server = skills_by_name["agents:server"]
    assert isinstance(server.trigger, PathTrigger)
    assert server.trigger.paths == ["server/**"]
    assert server.disable_model_invocation is True  # 强制路径规则
    assert "SERVER rule" in server.content

    sub = skills_by_name["agents:pkg/sub"]
    assert isinstance(sub.trigger, PathTrigger)
    assert sub.trigger.paths == ["pkg/sub/**"]


def test_nested_agents_md_become_path_rules_walk_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_walk_fallback(monkeypatch)
    _make_agents_workspace(tmp_path)
    skills = {s.name: s for s in load_project_skills(tmp_path)}
    _assert_nested_rules(skills)


@pytest.mark.skipif(not _HAS_GIT, reason="git not available")
def test_nested_agents_md_become_path_rules_git(tmp_path: Path) -> None:
    _make_agents_workspace(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    skills = {s.name: s for s in load_project_skills(tmp_path)}
    _assert_nested_rules(skills)


def test_find_nested_excludes_top_level_and_prunes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_walk_fallback(monkeypatch)
    (tmp_path / "AGENTS.md").write_text("root")  # 顶层：不嵌套
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "AGENTS.md").write_text("a")
    vendored = tmp_path / "node_modules" / "pkg"
    vendored.mkdir(parents=True)
    (vendored / "AGENTS.md").write_text("vendored")  # node_modules：修剪
    hidden = tmp_path / ".venv" / "pkg"
    hidden.mkdir(parents=True)
    (hidden / "AGENTS.md").write_text("hidden")  # 隐藏目录：修剪

    found = skills_utils.find_nested_third_party_files(
        tmp_path, Skill.PATH_TO_THIRD_PARTY_SKILL_NAME
    )
    rel_dirs = {rel_dir.as_posix() for _path, rel_dir in found}
    assert rel_dirs == {"a"}


def test_nested_rule_injection_and_dedup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_walk_fallback(monkeypatch)
    _make_agents_workspace(tmp_path)
    rules = [
        s for s in load_project_skills(tmp_path) if isinstance(s.trigger, PathTrigger)
    ]
    ctx = AgentContext(skills=rules)

    # 触摸 server/ 下的文件会注入服务器规则一次。
    result = ctx.get_tool_use_suffix(file_path="server/app.py", skip_skill_names=[])
    assert result is not None
    _content, activated = result
    assert activated == ["agents:server"]

    # 已激活的规则不会被重新注入。
    assert (
        ctx.get_tool_use_suffix(file_path="server/other.py", skip_skill_names=activated)
        is None
    )

    # 不匹配嵌套规则的文件不会注入任何内容。
    assert ctx.get_tool_use_suffix(file_path="README.md", skip_skill_names=[]) is None


def test_nested_overlapping_rules_both_inject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_walk_fallback(monkeypatch)
    # 子目录的 glob (pkg/sub/**) 是其父目录 (pkg/**) 的子集，因此子目录下的文件匹配 BOTH
    #  嵌套规则（“继承树”）。
    #
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "AGENTS.md").write_text("PARENT rule.\n")
    (tmp_path / "pkg" / "sub").mkdir()
    (tmp_path / "pkg" / "sub" / "AGENTS.md").write_text("CHILD rule.\n")
    rules = [
        s for s in load_project_skills(tmp_path) if isinstance(s.trigger, PathTrigger)
    ]
    ctx = AgentContext(skills=rules)

    result = ctx.get_tool_use_suffix(file_path="pkg/sub/foo.py", skip_skill_names=[])
    assert result is not None
    content, activated = result
    assert sorted(activated) == ["agents:pkg", "agents:pkg/sub"]  # 两者，各一次
    assert "PARENT rule." in content.text
    assert "CHILD rule." in content.text


@pytest.mark.skipif(not _HAS_GIT, reason="git not available")
def test_nested_discovery_includes_untracked_excludes_gitignored(
    tmp_path: Path,
) -> None:
    """未提交的AGENTS.md仍然算数； .gitignore 的则不会。"""
    (tmp_path / "kept").mkdir()
    (tmp_path / "kept" / "AGENTS.md").write_text("kept")  # 未被追踪，未被忽视
    (tmp_path / ".gitignore").write_text("skipped/\n")
    (tmp_path / "skipped").mkdir()
    (tmp_path / "skipped" / "AGENTS.md").write_text("nope")  # 忽略
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, check=True)
    # AGENTS.md 文件故意未提交。

    found = skills_utils.find_nested_third_party_files(
        tmp_path, Skill.PATH_TO_THIRD_PARTY_SKILL_NAME
    )
    rel_dirs = {rel_dir.as_posix() for _path, rel_dir in found}
    assert rel_dirs == {"kept"}


def test_nested_non_agents_third_party_name_scoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """嵌套的 CLAUDE.md 成为目录范围的 ``claude:<dir>`` 规则。"""
    _force_walk_fallback(monkeypatch)
    svc = tmp_path / "svc"
    svc.mkdir()
    (svc / "CLAUDE.md").write_text("claude guidance")
    skills = {s.name: s for s in load_project_skills(tmp_path)}
    rule = skills["claude:svc"]
    assert isinstance(rule.trigger, PathTrigger)
    assert rule.trigger.paths == ["svc/**"]


def test_nested_unreadable_file_skipped_without_aborting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """跳过非UTF-8嵌套文件； 其他规则仍然加载。"""
    _force_walk_fallback(monkeypatch)
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "AGENTS.md").write_text("good rule")
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "AGENTS.md").write_bytes(b"\xff\xfe not utf-8 \x80")
    skills = {s.name: s for s in load_project_skills(tmp_path)}
    assert "agents:good" in skills  # 不受坏兄弟姐妹的影响
    assert "agents:bad" not in skills  # 跳过，无一例外


def test_find_nested_nonexistent_workdir_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    assert (
        skills_utils.find_nested_third_party_files(
            missing, Skill.PATH_TO_THIRD_PARTY_SKILL_NAME
        )
        == []
    )


def test_git_worktree_relpaths_none_when_git_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """git absent -> None, so the caller falls back to a filesystem walk."""

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git not installed")

    monkeypatch.setattr(skills_utils.subprocess, "run", _raise)
    assert skills_utils._git_worktree_relpaths(tmp_path) is None


def test_nested_symlink_deduped_by_real_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AGENTS.md 和一个 CLAUDE.md 符号链接解析为一个文件 -> 一个条目。"""
    _force_walk_fallback(monkeypatch)
    d = tmp_path / "dir"
    d.mkdir()
    (d / "AGENTS.md").write_text("real")
    try:
        (d / "CLAUDE.md").symlink_to(d / "AGENTS.md")
    except OSError:
        pytest.skip("symlinks not supported on this platform")

    found = skills_utils.find_nested_third_party_files(
        tmp_path, Skill.PATH_TO_THIRD_PARTY_SKILL_NAME
    )
    assert len(found) == 1
