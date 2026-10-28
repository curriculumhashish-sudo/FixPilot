"""发布安全检查#2——供应链依赖性差异。

比较最后一个版本标签和 HEAD 之间已解决的依赖关系集 (``uv.lock``)，然后对于所有新的或
更新的内容：

  * 在 **OSV** 中查找已知漏洞（命中时阻止），并且
  * 从一个**非PyPI源**获取的标志包 —— git URLs、直接 URLs 或替代索引 —— 是经典的供应
  链和依赖混淆表面（阻止） 一个发布应锁定到可信的注册表
  )。

Deterministic: 从 git 解析两个锁定文件修订并查询
公共OSVAPI。 它从不安装或执行任何依赖项。

环境：
  SECURITY_SCAN_BASELINE_TAG（可选； 覆盖自动检测到的最后一个标签）
  SECURITY_SCAN_OUTPUT（可选； 也将渲染的报告附加到此处）
"""

from __future__ import annotations

import os
import sys
import tomllib
from urllib.parse import urlparse

from security_scan_common import (
    Report,
    last_release_tag,
    osv_query_batch,
    run_git,
)


LOCKFILE = "uv.lock"

# 我们接受的受信任的包的精确主机注册表。 一个精确主机匹配（不是子串），例如
# ``pypi.org.evil.example`` 不能被误认为 PyPI. 任何其他东西——一面镜子、一个替代索引、一
# 个git/url源——都是 *有目的被阻拦*：在发布中发现意外的来源是供应链/依赖混淆信号，而不是
# 要通过的。
#
_TRUSTED_REGISTRY_HOSTS = {"pypi.org", "files.pythonhosted.org"}


def _load_lock(ref: str) -> dict[str, dict[str, object]]:
    """为 ``ref`` 的锁中的每个包返回 {name: {version, source}}。"""
    try:
        raw = run_git("show", f"{ref}:{LOCKFILE}")
    except Exception:  # noqa: BLE001
        return {}
    data = tomllib.loads(raw)
    packages: dict[str, dict[str, object]] = {}
    for pkg in data.get("package", []):
        name = pkg.get("name")
        if not name:
            continue
        packages[name] = {
            "version": pkg.get("version", "?"),
            "source": pkg.get("source", {}),
        }
    return packages


def _source_label(source: object) -> str:
    if not isinstance(source, dict):
        return str(source)
    # uv encodes the source as {registry: ...} | {git: ...} | {url: ...} |
    # {editable: ...} | {virtual: ...} | {path: ...}
    for key in ("git", "url", "path", "editable", "virtual"):
        if key in source:
            return f"{key}:{source[key]}"
    if "registry" in source:
        return f"registry:{source['registry']}"
    return str(source)


def _registry_host(source: dict[str, object]) -> str | None:
    """``{registry: url}`` 源的主机，如果不是注册表，则为 None。"""
    registry = source.get("registry")
    if not isinstance(registry, str):
        return None
    return (urlparse(registry).hostname or "").lower()


def _is_trusted_registry(source: object) -> bool:
    """True 仅适用于第一方工作区成员或 *exact* PyPI 主持人。

    故意严格：镜像、备用索引、git/url源或未识别的源形状不被信任，因此被阻止，并且有人
    查看它。 这是检查发布点的目的——意外的来源是供应链信号，而一个块只是为维护
    者保留（在发布中非常便宜和罕见）PR。
    """
    if not isinstance(source, dict):
        return False
    # 工作区成员/虚拟根是 SDK 自己的包。
    if "virtual" in source or "editable" in source:
        return True
    if "registry" in source:
        return _registry_host(source) in _TRUSTED_REGISTRY_HOSTS
    return False


def main() -> int:
    baseline = os.environ.get("SECURITY_SCAN_BASELINE_TAG") or last_release_tag()
    report = Report("📦 Supply-chain dependency diff")

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

    before = _load_lock(baseline)
    after = _load_lock("HEAD")
    if not after:
        report.warn("no lockfile")
        report.add(f"Could not read `{LOCKFILE}` at HEAD. Skipping.")
        print(report.render())
        return 0

    added = {n: after[n] for n in after.keys() - before.keys()}
    removed = sorted(before.keys() - after.keys())
    bumped = {
        n: (before[n]["version"], after[n]["version"])
        for n in after.keys() & before.keys()
        if before[n]["version"] != after[n]["version"]
    }

    # 第一方 OpenHands-* 软件包在每个版本中都会进行版本更新； 将它们从外部部门计数中排除
    # ，但仍将其显示在下面。
    #
    def _is_openhands(name: str) -> bool:
        return name.lower().startswith("openhands-")

    bumped_external = {n: v for n, v in bumped.items() if not _is_openhands(n)}
    bumped_openhands = {n: v for n, v in bumped.items() if _is_openhands(n)}

    report.add(f"Baseline: `{baseline}`")
    report.add(
        f"Added: **{len(added)}**, bumped: **{len(bumped_external)}**, "
        f"removed: **{len(removed)}**."
    )
    if bumped_openhands:
        report.add(f"_(plus {len(bumped_openhands)} internal `openhands-*` bump(s))_")
    report.add("")

    # --- 新/更改的软件包上的非注册表来源（供应链表面）--
    suspicious_source = []
    for name in list(added) + list(bumped):
        source = after[name]["source"]
        if not _is_trusted_registry(source):
            suspicious_source.append((name, _source_label(source)))
    if suspicious_source:
        report.add("**Non-PyPI sources on new/changed packages:**")
        for name, label in sorted(suspicious_source):
            report.add(f"- `{name}` ← `{label}`")
            report.block(f"{name} resolved from non-registry source ({label})")
        report.add("")

    # --- OSV 新+升级版本的已知漏洞查找 --------------
    to_scan = [(n, str(after[n]["version"])) for n in list(added) + list(bumped)]
    if to_scan:
        queries = [
            {"package": {"ecosystem": "PyPI", "name": n}, "version": v}
            for n, v in to_scan
        ]
        results = osv_query_batch(queries)
        if results is None:
            report.block("OSV lookup failed")
            report.add(
                "> OSV lookup failed (network): could not verify new/bumped "
                "deps against known vulnerabilities. Blocking on purpose — a "
                "release that can't be checked shouldn't ship. Often transient; "
                "re-run to retry, or a maintainer can clear it on the fly."
            )
        else:
            vuln_hits = []
            for (name, version), res in zip(to_scan, results):
                vulns = res.get("vulns") if isinstance(res, dict) else None
                if vulns:
                    ids = ", ".join(v.get("id", "?") for v in vulns)
                    vuln_hits.append((name, version, ids))
            if vuln_hits:
                report.add("**Known vulnerabilities (OSV):**")
                for name, version, ids in vuln_hits:
                    report.add(f"- `{name}=={version}` → {ids}")
                    report.block(f"{name}=={version} has known vuln(s): {ids}")
                report.add("")
            else:
                report.add(
                    f"OSV: no known vulns across {len(to_scan)} new/bumped dep(s)."
                )
                report.add("")

    # --- 可读清单 --------------------------------------------------
    if added:
        report.add("<details><summary>Added dependencies</summary>\n")
        for name in sorted(added):
            report.add(f"- `{name}=={added[name]['version']}`")
        report.add("\n</details>")
    if bumped_external:
        report.add("<details><summary>Bumped dependencies</summary>\n")
        for name in sorted(bumped_external):
            old_v, new_v = bumped_external[name]
            report.add(f"- `{name}`: {old_v} → {new_v}")
        report.add("\n</details>")
    if bumped_openhands:
        report.add("<details><summary>Internal `openhands-*` bumps</summary>\n")
        for name in sorted(bumped_openhands):
            old_v, new_v = bumped_openhands[name]
            report.add(f"- `{name}`: {old_v} → {new_v}")
        report.add("\n</details>")

    sys.stdout.write(report.render())
    out = os.environ.get("SECURITY_SCAN_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(report.render())
            handle.write("\n")
    return 1 if report.blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
