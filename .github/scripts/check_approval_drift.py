"""发布安全检查 #1 — 批准漂移（TOCTOU 警卫）。

我们关心的窗口：一个人在看 PR (时间检查)，但实际合并和发布的（时间使用）与他们审查的
并不一样——因为提交是在批准之后进行的，或者提交是在批准之后进行的 PR 未经任何
人工审核就合并了e.g. 自动合并，或智能体根据注入的评论执行。

对于自上一个发布标签以来合并进来的每一条PR，该比较PR的合并头与它的最后*人类* APPROVED
评审：

  * 与 ** 未经人工批准 ** 合并 -> 阻止
  * 提交推 **之后** 最后的批准 -> 阻塞（审查的差异不是已发布的差异）

Deterministic: 读取合并的 PR 列表的 ``git log`` 和只读
GitHub REST API 进行评论。 它从不运行 PR 的代码。

环境：
  GITHUB_TOKEN（推荐； 提高利率限制，读取私人回购）GITHUB_REPOSITORY（所有者/名称；
  回落到原始远程）
  SECURITY_SCAN_BASELINE_TAG（可选； 覆盖自动检测到的最后一个标签）
  SECURITY_SCAN_TRUSTED_BOTS（机器人登录的可选
  CSV，其合并为
                               未经人类批准即可允许，e.g。 依赖机器人）
"""

from __future__ import annotations

import os
import re
import sys

from security_scan_common import (
    Report,
    github_request,
    github_request_all,
    last_release_tag,
    resolve_repo,
    run_git,
)


# 此存储库中的挤压合并主题以“(#1234)”结尾； 那是 PR 数字。
_PR_NUM_RE = re.compile(r"\(#(\d+)\)\s*$")

# GitHub 将这些关联值标记为来自项目外部。
_OUTSIDE_ASSOC = {"NONE", "FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR", "MANNEQUIN"}


def merged_pr_numbers(baseline: str) -> tuple[list[tuple[int, str]], list[str]]:
    """PR 在 ``baseline..HEAD`` 中命名，加上映射到 None 的主题。

    对于主题以 ``(#N)`` 结尾的第一个父提交，返回 ``(matched, unmapped)``，其中
    ``matched`` 是
    ``(pr_number, subject)``，并且
    ``unmapped`` 是那些不做的事情——因此调用者可以突出盲点（一个跳过了 squash 规则的合
    并恰好是批准漂移警报者必须无声忽略的那一个）而不是丢弃它。
    """
    log = run_git(
        "log", "--first-parent", "--pretty=format:%H%x1f%s", f"{baseline}..HEAD"
    )
    matched: list[tuple[int, str]] = []
    unmapped: list[str] = []
    for line in log.splitlines():
        if "\x1f" not in line:
            continue
        _, subject = line.split("\x1f", 1)
        match = _PR_NUM_RE.search(subject)
        if match:
            matched.append((int(match.group(1)), subject))
        else:
            unmapped.append(subject)
    return matched, unmapped


def _is_bot(user: dict[str, object]) -> bool:
    return user.get("type") == "Bot" or str(user.get("login", "")).endswith("[bot]")


def audit_pr(
    repo: str, number: int, token: str | None, trusted_bots: set[str]
) -> tuple[str, str | None]:
    """返回一 PR 的（状态、详细信息）。

    状态是以下之一：“确定”、“无人批准”、“批准后更改”、“可信机器人”、“错误”。
    """
    try:
        pr = github_request(f"/repos/{repo}/pulls/{number}", token)
        # 分页：评论端点返回每条评论（也返回 COMMENTED），
        # 因此，大量讨论的 PR 可能会超过一页。 绝不能错过首页之后的人类 APPROVED，否则
        # PR 会被错误分类为未经批准并阻止干净发布。
        #
        reviews = github_request_all(
            f"/repos/{repo}/pulls/{number}/reviews?per_page=100", token
        )
    except Exception as exc:  # noqa: BLE001 - report, do not crash the gate
        return "error", str(exc)

    merge_sha = pr.get("merge_commit_sha")
    head_sha = (pr.get("head") or {}).get("sha")
    author = (pr.get("user") or {}).get("login", "?")

    approvals = [
        r
        for r in reviews
        if r.get("state") == "APPROVED"
        and not _is_bot(r.get("user") or {})
        and (r.get("author_association") or "NONE") not in _OUTSIDE_ASSOC
    ]

    if not approvals:
        merged_by = pr.get("merged_by") or {}
        if _is_bot(merged_by) and merged_by.get("login") in trusted_bots:
            return "trusted-bot", f"merged by trusted bot {merged_by.get('login')}"
        return (
            "no-human-approval",
            f"author @{author}; merged={_short(merge_sha)}; no human APPROVED review",
        )

    # 已审查的提交是每个批准提交的标题。
    approved_shas = {r.get("commit_id") for r in approvals if r.get("commit_id")}
    reviewed_head = head_sha in approved_shas
    if not reviewed_head:
        latest = approvals[-1]
        reviewer = (latest.get("user") or {}).get("login", "?")
        approved_sha = latest.get("commit_id")
        approved_on = _short(approved_sha)
        merged_head = _short(head_sha)
        diff_link = _compare_link(repo, approved_sha, head_sha, merged_head)
        return (
            "changed-after-approval",
            (
                f"last approval by @{reviewer} was on {approved_on}, but merged "
                f"head was {diff_link} — commits landed after review"
            ),
        )

    return "ok", None


def _short(sha: object) -> str:
    return str(sha)[:9] if sha else "?"


def _compare_link(repo: str, base: object, head: object, label: str) -> str:
    """Markdown 与 GitHub 比较页面之间的 *base* 和 *head* 的链接。

    如果缺少任一 SHA，则返回纯文本，因此报告不会因稀疏的 API 响应而中断。
    """
    if not base or not head:
        return label
    return f"[{label}](https://github.com/{repo}/compare/{base}...{head})"


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repo = resolve_repo()
    baseline = os.environ.get("SECURITY_SCAN_BASELINE_TAG") or last_release_tag()
    trusted_bots = {
        b.strip()
        for b in os.environ.get("SECURITY_SCAN_TRUSTED_BOTS", "").split(",")
        if b.strip()
    }

    report = Report("🔒 Approval drift (time-of-check vs time-of-use)")

    if not baseline:
        report.add("No previous `v*` release tag found; nothing to compare against.")
        print(report.render())
        return 0

    try:
        run_git("rev-parse", "--verify", f"{baseline}^{{commit}}")
    except Exception:  # noqa: BLE001
        report.warn("baseline unavailable")
        report.add(
            f"Baseline tag `{baseline}` is not present locally "
            "(fetch tags with `fetch-depth: 0`). Skipping."
        )
        print(report.render())
        return 0

    prs, unmapped = merged_pr_numbers(baseline)
    report.add(f"Baseline: `{baseline}` — {len(prs)} merged PR(s) in range.")
    if unmapped:
        report.warn(f"{len(unmapped)} commit(s) not mapped to a PR")
        report.add(
            f"> ⚠️ {len(unmapped)} first-parent commit(s) in range did not match "
            "the `(#N)` squash convention and were **not** audited (a merge/rebase "
            "merge, or a lost `(#N)` suffix). These are a blind spot — inspect them:"
        )
        for subject in unmapped[:20]:
            report.add(f">   - {subject}")
        if len(unmapped) > 20:
            report.add(f">   - …and {len(unmapped) - 20} more")
    report.add("")

    blocking_rows: list[str] = []
    ok = 0
    errors = 0
    for number, _subject in prs:
        status, detail = audit_pr(repo, number, token, trusted_bots)
        if status == "ok":
            ok += 1
        elif status == "trusted-bot":
            ok += 1
        elif status == "error":
            errors += 1
            report.warn(f"could not audit #{number}")
        else:
            blocking_rows.append(f"| #{number} | `{status}` | {detail} |")
            report.block(f"#{number}: {status}")

    if blocking_rows:
        report.add("| PR | finding | detail |")
        report.add("| -- | ------- | ------ |")
        report.lines.extend(blocking_rows)
        report.add("")
    report.add(
        f"Audited {len(prs)} PR(s): {ok} clean, {len(blocking_rows)} flagged, "
        f"{errors} un-auditable."
    )
    if errors:
        report.add(
            "\n> Un-auditable PRs are reported as warnings, not blockers, so a "
            "transient API error does not wedge a release."
        )

    sys.stdout.write(report.render())
    _emit_summary_file(report)
    return 1 if report.blocking else 0


def _emit_summary_file(report: Report) -> None:
    out = os.environ.get("SECURITY_SCAN_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(report.render())
            handle.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
