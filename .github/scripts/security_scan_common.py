"""用于发布安全扫描检查的共享助手。

设计上是确定性的：这些助手只读取 git 历史并查询只读 HTTP APIs (GitHub REST, OSV)。 他
们从不执行正在审查的代码。 这就是安全门的全部意义—
—一个扫描器（或要求一个 LLM 进行推理）处理未经验证的 PR 内容本身就是一个注入目标。
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field


GITHUB_API = "https://api.github.com"


def run_git(*args: str) -> str:
    """运行 git 命令并返回剥离的标准输出。"""
    result = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def last_release_tag() -> str | None:
    """可从 HEAD 或 None（如果有 None）访问的最新 ``vX.Y.Z`` 标签。

    发布扫描将“现在发布的内容”与最后发布的内容进行比较，因此之前的发布标签是自然的、
    不可变的基线。
    """
    try:
        # --merged HEAD 让我们保持在这条历史线上； 按版本排序。
        tags = run_git(
            "tag", "--list", "v*", "--merged", "HEAD", "--sort=-v:refname"
        ).splitlines()
    except subprocess.CalledProcessError:
        return None
    return tags[0].strip() if tags and tags[0].strip() else None


def _github_get(url: str, token: str | None) -> tuple[object, str | None]:
    """GET GitHub REST 页； 返回``(parsed_json, link_header)``。"""
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8")), resp.headers.get("Link")


def github_request(path_or_url: str, token: str | None) -> object:
    """GETaGitHubREST端点并解析JSON。 引发 HTTP 错误。"""
    url = path_or_url
    if url.startswith("/"):
        url = f"{GITHUB_API}{url}"
    body, _ = _github_get(url, token)
    return body


def _next_link(link_header: str | None) -> str | None:
    """REST ``Link`` 标头中的 ``rel="next"`` URL 或 None。"""
    if not link_header:
        return None
    for part in link_header.split(","):
        segments = part.split(";")
        if len(segments) < 2:
            continue
        url_part = segments[0].strip().lstrip("<").rstrip(">")
        if any('rel="next"' in seg.strip() for seg in segments[1:]):
            return url_part
    return None


def github_request_all(path_or_url: str, token: str | None) -> list[object]:
    """GET 分页的 GitHub REST 列表端点，位于 ``Link: next`` 之后。

    将每一页连接到一个列表中。 必须 * 识别所有 * 评论 — 如果人类 APPROVED 坐过第一页
    ，会将 PR 误判为未通过（一个 False-正的块）。 返回一
    个非列表响应，包装成一个包含单个元素的列表。
    """
    url = path_or_url
    if url.startswith("/"):
        url = f"{GITHUB_API}{url}"
    items: list[object] = []
    while url:
        page, link = _github_get(url, token)
        if isinstance(page, list):
            items.extend(page)
        else:
            return [page]
        url = _next_link(link)
    return items


def osv_query_batch(
    queries: list[dict[str, object]],
) -> list[dict[str, object]] | None:
    """查询OSV批量漏洞API。 网络故障时返回 None。

    OSV 是公开的，无需身份验证。 None 返回意味着无法针对已知漏洞验证版本差异； 依赖差
    异调用者将它视为阻塞（失败关闭 —— 不能检查的发布不应发布），而实际已
    知漏洞的发现同样被视为硬发现。
    """
    payload = json.dumps({"queries": queries}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.osv.dev/v1/querybatch",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    results = data.get("results")
    return results if isinstance(results, list) else []


@dataclass
class Report:
    """累积 Markdown 报告以及阻止/正常判决。"""

    title: str
    lines: list[str] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add(self, line: str = "") -> None:
        self.lines.append(line)

    def block(self, reason: str) -> None:
        self.blocking.append(reason)

    def warn(self, reason: str) -> None:
        self.warnings.append(reason)

    def render(self) -> str:
        if self.blocking:
            status = f"❌ {len(self.blocking)} finding(s)"
        elif self.warnings:
            status = f"⚠️ {len(self.warnings)} warning(s), nothing blocking"
        else:
            status = "✅ no findings"
        out = [f"### {self.title}", "", f"**{status}**", ""]
        out.extend(self.lines)
        return "\n".join(out).rstrip() + "\n"


def resolve_repo() -> str:
    """`owner/name` 从 GITHUB_REPOSITORY，回落到 git 远程。"""
    env_repo = os.environ.get("GITHUB_REPOSITORY")
    if env_repo:
        return env_repo
    url = run_git("config", "--get", "remote.origin.url")
    slug = url.rsplit("github.com", 1)[-1].lstrip(":/")
    if slug.endswith(".git"):
        slug = slug[:-4]
    return slug
