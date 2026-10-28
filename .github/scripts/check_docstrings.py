#!/usr/bin/env python3
"""验证文档字符串符合 MDX 兼容的格式指南。

此脚本检查 SDK 中的文档字符串使用的模式在 Mintlify MDX 文档中正确呈现。 它验证：

1. 没有 REPL 样式的示例 (>>>) - 应该使用隔离代码块
2. Shell/config 示例使用受隔离的代码块（防止 # 成为标头）

运行时：Python scripts/check_docstrings.py 退出码0表示所有检查通过，1表示发现违规
"""

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


# 需要检查的目录
SDK_PATHS = [
    "openhands-sdk/openhands/sdk",
]

# 要跳过的文件/目录
SKIP_PATTERNS = [
    "__pycache__",
    ".pyc",
    "test_",
    "_test.py",
]

# 要严格检查的核心公共 API 文件（这些文件已在网站上记录）其他文件将被检查，但仅发出警告
# ，而不发出失败
#
STRICT_CHECK_FILES = [
    "agent/agent.py",
    "llm/llm.py",
    "conversation/conversation.py",
    "tool/tool.py",
    "workspace/base.py",
    "observability/laminar.py",
]


@dataclass
class Violation:
    """文档字符串格式违规。"""

    file: Path
    line: int
    name: str
    rule: str
    message: str
    is_strict: bool = False  # True 如果这是在严格检查的文件中


def should_skip(path: Path) -> bool:
    """检查是否应跳过路径。"""
    path_str = str(path)
    return any(pattern in path_str for pattern in SKIP_PATTERNS)


def check_repl_examples(
    docstring: str, name: str, lineno: int, file: Path
) -> list[Violation]:
    """检查 REPL 样式的示例 (>>>)。

    这些应该替换为受隔离的代码块，以获得更好的 MDX 渲染。
    """
    violations = []
    lines = docstring.split("\n")

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(">>>"):
            violations.append(
                Violation(
                    file=file,
                    line=lineno + i,
                    name=name,
                    rule="no-repl-examples",
                    message=(
                        "Use fenced code blocks (```python) instead of >>> REPL style. "
                        "REPL examples don't render well in MDX documentation."
                    ),
                )
            )
            # 每个文档字符串仅报告一次
            break

    return violations


def check_unfenced_shell_config(
    docstring: str, name: str, lineno: int, file: Path
) -> list[Violation]:
    """检查不在受保护代码块中的 shell/配置示例。

    以 # 开头的外部代码块行成为 Markdown 标头。
    """
    violations = []
    lines = docstring.split("\n")
    in_code_block = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 跟踪代码块状态
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        # 如果在代码块内则跳过
        if in_code_block:
            continue

        # 检查类似于 config 的 shell 风格注释
        # 模式：行以 # 开头，上一行有 = （配置模式）
        if stripped.startswith("#") and not stripped.startswith("# "):
            # 这可能是一个没有空格的 shell 注释（在散文中不太常见）
            continue

        # 检查不受保护的配置：KEY=VALUE 后跟 # 注释
        if i > 0:
            prev_line = lines[i - 1].strip() if i > 0 else ""
            # 如果上一行看起来像 config (VAR=value) 并且这是 # 注释
            if "=" in prev_line and prev_line.split("=")[0].isupper():
                if stripped.startswith("# "):
                    violations.append(
                        Violation(
                            file=file,
                            line=lineno + i,
                            name=name,
                            rule="fenced-shell-config",
                            message=(
                                "Shell/config examples with # comments should be "
                                "in ```bash code blocks. Otherwise # becomes a "
                                "markdown header."
                            ),
                        )
                    )
                    # 每个文档字符串仅报告一次
                    break

    return violations


def check_docstring(
    docstring: str, name: str, lineno: int, file: Path
) -> list[Violation]:
    """对文档字符串运行所有检查。"""
    if not docstring:
        return []

    violations = []
    violations.extend(check_repl_examples(docstring, name, lineno, file))
    violations.extend(check_unfenced_shell_config(docstring, name, lineno, file))
    return violations


def get_docstrings_from_file(file: Path) -> list[tuple[str, str, int]]:
    """从 Python 文件中提取所有文档字符串。

    返回 (name, 文档字符串，lineno) 元组列表。
    """
    try:
        source = file.read_text()
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"Warning: Could not parse {file}: {e}", file=sys.stderr)
        return []

    docstrings = []

    for node in ast.walk(tree):
        name = None
        lineno = 0
        docstring = None

        if isinstance(node, ast.Module):
            docstring = ast.get_docstring(node)
            name = file.stem
            lineno = 1
        elif isinstance(node, ast.ClassDef):
            docstring = ast.get_docstring(node)
            name = node.name
            lineno = node.lineno
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            docstring = ast.get_docstring(node)
            name = node.name
            lineno = node.lineno

        if docstring and name:
            docstrings.append((name, docstring, lineno))

    return docstrings


def is_strict_file(file: Path, repo_root: Path) -> bool:
    """检查文件是否在严格检查列表中。"""
    try:
        rel_path = file.relative_to(repo_root / "openhands-sdk/openhands/sdk")
        return any(str(rel_path) == strict for strict in STRICT_CHECK_FILES)
    except ValueError:
        return False


def check_file(file: Path, repo_root: Path) -> list[Violation]:
    """检查文件中的所有文档字符串。"""
    violations = []
    is_strict = is_strict_file(file, repo_root)

    for name, docstring, lineno in get_docstrings_from_file(file):
        file_violations = check_docstring(docstring, name, lineno, file)
        for v in file_violations:
            v.is_strict = is_strict
        violations.extend(file_violations)

    return violations


def main() -> int:
    """对所有 SDK 个文件运行文档字符串检查。"""
    repo_root = Path(__file__).parent.parent.parent

    all_violations: list[Violation] = []
    files_checked = 0

    for sdk_path in SDK_PATHS:
        path = repo_root / sdk_path
        if not path.exists():
            print(f"Warning: Path not found: {path}", file=sys.stderr)
            continue

        for py_file in path.rglob("*.py"):
            if should_skip(py_file):
                continue

            files_checked += 1
            violations = check_file(py_file, repo_root)
            all_violations.extend(violations)

    # 将严格违规（错误）与警告分开
    strict_violations = [v for v in all_violations if v.is_strict]
    warning_violations = [v for v in all_violations if not v.is_strict]

    # 报告警告（非严格文件）
    if warning_violations:
        count = len(warning_violations)
        print(f"\n⚠️  Found {count} docstring warning(s) in non-core files:\n")

        by_file: dict[Path, list[Violation]] = {}
        for v in warning_violations:
            by_file.setdefault(v.file, []).append(v)

        for file, violations in sorted(by_file.items()):
            rel_path = file.relative_to(repo_root)
            print(f"📄 {rel_path}")
            for v in violations:
                print(f"   Line {v.line}: {v.name} ({v.rule})")
        print()

    # 报告错误（严格文件）
    if strict_violations:
        count = len(strict_violations)
        print(f"\n❌ Found {count} docstring error(s) in core API files:\n")

        by_file: dict[Path, list[Violation]] = {}
        for v in strict_violations:
            by_file.setdefault(v.file, []).append(v)

        for file, violations in sorted(by_file.items()):
            rel_path = file.relative_to(repo_root)
            print(f"📄 {rel_path}")
            for v in violations:
                print(f"   Line {v.line}: {v.name}")
                print(f"   Rule: {v.rule}")
                print(f"   {v.message}")
                print()

        print("=" * 60)
        print("To fix these issues:")
        print("  1. Replace >>> examples with ```python code blocks")
        print("  2. Wrap shell/config examples in ```bash code blocks")
        print("=" * 60)
        return 1

    if warning_violations:
        count = len(warning_violations)
        print(f"✅ Core API files pass. {count} warnings in other files.")
    else:
        print(f"✅ All {files_checked} files pass docstring checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
