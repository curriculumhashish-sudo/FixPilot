"""拒绝 SDK 源文件中的新动态属性访问。

现有的``getattr``/``setattr``和``obj.__dict__.get``调用会被记录在一个已提交的基线中，
以便在清理工作（跟踪在#4903, #490
4, #4905）完成后引入钩子。 仅报告基线中存在的*不*的调用。

一个违规行为通过其文件路径（相对于仓库根目录）、调用名称以及完整调用源段的哈希值（而
不是仅限于第一个物理行）来识别。 基于完整的表达，当无关的编辑移动行号时，保持基准稳定
；
同时，仍然标记对现有调用的真正编辑——包括后续行中的参数更改。

基线是 *multiset*（保留出现计数），因此添加已基线调用的另一个副本仍会被标记。

使用以下命令删除现有调用后重新生成基线：

    uv run python scripts/check_forbidden_dynamic_attributes.py \\
        --update-baseline $(查找 OpenHands-SDK -name '*.py')
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


FORBIDDEN = {"getattr", "setattr"}
DICT_GET = "__dict__.get"
BASELINE_FILE = Path(__file__).with_name("forbidden_dynamic_attributes_baseline.json")


def _forbidden_call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN:
        return node.func.id
    if (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "__dict__"
    ):
        return DICT_GET
    return None


def _segment_hash(source: str, node: ast.Call) -> str:
    """对 *node* 的完整源段进行哈希处理，而不仅仅是其第一行。"""
    segment = ast.get_source_segment(source, node)
    if segment is not None:
        text = segment
    else:
        # 回退方案：连接节点跨越的所有物理线。
        lines = source.splitlines()
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        text = "\n".join(lines[node.lineno - 1 : end])
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def violations(path: Path) -> list[tuple[int, str, str]]:
    """对于 *path* 中的每个禁止调用返回 ``(lineno, name, segment_hash)``。"""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    result: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _forbidden_call_name(node)
        if name is not None:
            result.append((node.lineno, name, _segment_hash(source, node)))
    return result


Baseline = Counter[tuple[str, str, str]]


def _parse_baseline(content: str) -> Baseline:
    data = json.loads(content)
    return Counter((entry["file"], entry["name"], entry["hash"]) for entry in data)


def _load_baseline() -> Baseline:
    if not BASELINE_FILE.exists():
        return Counter()
    return _parse_baseline(BASELINE_FILE.read_text(encoding="utf-8"))


def _load_baseline_from_git(ref: str) -> Baseline:
    root = Path(__file__).resolve().parent.parent
    relative_path = BASELINE_FILE.resolve().relative_to(root)
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative_path.as_posix()}"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return _parse_baseline(result.stdout)


def _baseline_additions(reference: Baseline, current: Baseline) -> Baseline:
    return current - reference


def _write_baseline(entries: list[tuple[str, str, str]]) -> None:
    payload = [
        {"file": file, "name": name, "hash": digest}
        for file, name, digest in sorted(entries)
    ]
    BASELINE_FILE.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")


SDK_ROOT = "openhands-sdk"


def _discover_sdk_files() -> list[str]:
    """返回 SDK 根目录下相对于存储库根目录的所有 Python 文件。"""
    root = Path(__file__).resolve().parent.parent
    return [
        p.relative_to(root).as_posix() for p in sorted(root.glob(f"{SDK_ROOT}/**/*.py"))
    ]


def _current_entries(
    paths: list[str],
) -> list[tuple[str, str, str, int]]:
    """将 * 路径 * 上的所有当前违规返回为 ``(file, name, hash, line)``。"""
    entries: list[tuple[str, str, str, int]] = []
    for raw_path in paths:
        posix_path = Path(raw_path).as_posix()
        for line, name, digest in violations(Path(raw_path)):
            entries.append((posix_path, name, digest, line))
    return entries


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Python files to check")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite the baseline from the current violations and exit 0.",
    )
    parser.add_argument(
        "--baseline-ref",
        help="Reject baseline entries not present at this Git reference.",
    )
    args = parser.parse_args(argv)

    if args.update_baseline and args.baseline_ref:
        parser.error("--update-baseline cannot be combined with --baseline-ref")

    if args.baseline_ref:
        baseline = _load_baseline()
        additions = _baseline_additions(
            _load_baseline_from_git(args.baseline_ref), baseline
        )
        if additions:
            for (file, name, _digest), count in sorted(additions.items()):
                print(f"{file}: baseline adds {count} forbidden {name} allowance(s)")
            print("error: the forbidden dynamic attributes baseline may only shrink")
            return 1

    # 当没有给出路径时（e.g. 通过使用 pass_filenames: False 进行预提交，自动发现所有 SDK
    #  Python 文件，以便捕获删除。
    #
    paths = args.paths if args.paths else _discover_sdk_files()

    current = _current_entries(paths)

    if args.update_baseline:
        _write_baseline([(file, name, digest) for file, name, digest, _ in current])
        print(f"Baseline updated: {len(current)} existing violations recorded.")
        return 0

    baseline = _load_baseline()
    current_counter = Counter((file, name, digest) for file, name, digest, _ in current)
    checked_files = {Path(p).as_posix() for p in paths}

    # 新违规：超出每个键的基线计数的发生次数。
    new_violations: list[tuple[str, int, str]] = []
    for file, name, digest, line in current:
        key = (file, name, digest)
        if current_counter[key] > baseline.get(key, 0):
            new_violations.append((file, line, name))
            current_counter[key] -= 1  # 仅将多余的部分视为新的

    # 过时：当前代码中不再存在基线条目。 当
    # 检查器在所有 SDK 文件上运行（自动发现），已删除文件的条目也会被标记； 子集仅运行他
    # 们检查的文件的报告偏差。
    #
    stale = {
        key
        for key, count in (baseline - current_counter).items()
        if key[0] in checked_files or not Path(key[0]).exists()
    }

    for file, line, name in sorted(new_violations):
        print(f"{file}:{line}: forbidden dynamic attribute call: {name}")
    if stale:
        count = len(stale)
        unit = "entry is" if count == 1 else "entries are"
        print(f"error: {count} baseline {unit} stale; run --update-baseline to refresh")
    if new_violations or stale:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
