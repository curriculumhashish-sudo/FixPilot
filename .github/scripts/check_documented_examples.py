#!/usr/bin/env python3
"""
检查智能体-SDK 中的所有示例是否都记录在文档存储库中。

这个脚本：
1. 扫描文档存储库以获取示例文件的引用
2. 列出智能体-SDK 存储库中的所有示例 Python 文件
3. 比较两组以查找未记录的示例
4. 如果发现未记录的示例，则退出并显示错误代码 1
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def find_documented_examples(docs_path: Path) -> set[str]:
    """
    在文档存储库中查找所有示例文件引用。

    搜索类似以下的模式：
    - examples/01_standalone_sdk/02_custom_tools.py
    - examples/02_remote_agent_server/06_custom_tool/custom_tools/log_data.py
    在 MDX 个文件中。

    Returns:
        规范化示例文件路径集（相对于智能体-SDK 根）
    """
    documented_examples: set[str] = set()

    # 用于将示例文件引用与任意嵌套深度相匹配的模式。
    # 匹配：examples/<dir>/.../<file>.py
    pattern = r"examples/(?:[-\w]+/)+[-\w]+\.py"

    for root, _, files in os.walk(docs_path):
        for file in files:
            if file.endswith(".mdx") or file.endswith(".md"):
                file_path = Path(root) / file
                try:
                    content = file_path.read_text(encoding="utf-8")
                    matches = re.findall(pattern, content)
                    for match in matches:
                        # 标准化路径
                        documented_examples.add(match)
                except Exception as e:
                    print(f"Warning: Error reading {file_path}: {e}")
                    continue

    return documented_examples


def find_agent_sdk_examples(agent_sdk_path: Path) -> set[str]:
    """
    查找智能体-SDK 存储库中的所有示例 Python 文件。

    排除 examples/03_github_workflows/，因为这些示例是 YAML 文件，而不是 Python 文件
    。

    Returns:
        示例文件路径集（相对于智能体-SDK 根目录）
    """
    examples: set[str] = set()
    examples_dir = agent_sdk_path / "examples"

    if not examples_dir.exists():
        print(f"Error: Examples directory not found: {examples_dir}")
        sys.exit(1)

    # 查找examples/下的所有Python个文件
    for root, _, files in os.walk(examples_dir):
        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file
                # 获取从智能体-SDK root 的相对路径
                relative_path = file_path.relative_to(agent_sdk_path)
                relative_path_str = str(relative_path)

                # 跳过 GitHub 个工作流程示例（这些是 YAML 个文件，Python 个文件，只有帮
                # 助程序）
                #
                if relative_path_str.startswith("examples/03_github_workflows/"):
                    continue

                # 跳过 LLM 特定工具示例：文档检查故意不强制执行这些工具示例。 请参阅 PR
                # #1486 中的讨论。
                #
                if relative_path_str.startswith("examples/04_llm_specific_tools/"):
                    continue

                # 跳过 __init__.py 个文件，因为它们通常不需要文档
                if file == "__init__.py":
                    continue

                # 跳过支持示例但本身不是独立示例的支持脚本。
                #
                if "/scripts/" in relative_path_str:
                    continue

                examples.add(relative_path_str)

    return examples


def find_changed_examples_for_pull_request(agent_sdk_path: Path) -> set[str] | None:
    """
    返回当前拉取请求更改的示例路径（如果可用）。

    文档存储库可能会短暂落后于主存储库。 在 pull_request 运行中，仅对于属于 PR 差异一
    部分的示例，使 PR 失败； 手动和其他运行继续验证完整的示例集
    。
    """
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return None

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("⚠️  GITHUB_EVENT_PATH is unavailable; checking all examples.")
        return None

    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        base_sha = event["pull_request"]["base"]["sha"]
    except (KeyError, OSError, json.JSONDecodeError) as e:
        print(f"⚠️  Could not read pull request base SHA: {e}")
        print("   Checking all examples instead.")
        return None

    try:
        diff = subprocess.run(
            [
                "git",
                "-C",
                str(agent_sdk_path),
                "diff",
                "--name-only",
                f"{base_sha}...HEAD",
                "--",
                "examples",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Could not determine changed examples: {e}")
        print("   Checking all examples instead.")
        return None

    return {line for line in diff.stdout.splitlines() if line.endswith(".py")}


def resolve_paths() -> tuple[Path, Path]:
    """
    确定智能体-SDK 根和文档路径。

    文档路径的优先级：
      1) DOCS_PATH（环境覆盖）
      2) $GITHUB_WORKSPACE/文档
      3) agent_sdk_root/'文档'
      4) agent_sdk_root.parent/'文档'

    Returns:
        (agent_sdk_root, docs_path) 的元组
    """
    # 智能体-SDK 仓库根目录（脚本位于智能体-sdk/.github/scripts/...)
    script_file = Path(__file__).resolve()
    agent_sdk_root = script_file.parent.parent.parent

    candidates: list[Path] = []

    # 1) 显式环境覆盖
    env_override = os.environ.get("DOCS_PATH")
    if env_override:
        candidates.append(Path(env_override).expanduser().resolve())

    # 2) 标准 GitHub 工作区同级
    gh_ws = os.environ.get("GITHUB_WORKSPACE")
    if gh_ws:
        candidates.append(Path(gh_ws).resolve() / "docs")

    # 3) 智能体-SDK 存储库根目录中的同级
    candidates.append(agent_sdk_root / "docs")

    # 4) 智能体-SDK-根布局的父级
    candidates.append(agent_sdk_root.parent / "docs")

    print(f"🔍 Agent SDK root: {agent_sdk_root}")
    print("🔎 Trying docs paths (in order):")
    for p in candidates:
        print(f"   - {p}")

    for p in candidates:
        if p.exists():
            print(f"📁 Using docs path: {p}")
            return agent_sdk_root, p

    # 如果 None 存在，则失败并显示有用的消息
    print("❌ Docs path not found in any of the expected locations.")
    print("   Set DOCS_PATH, or checkout the repo to one of the tried paths above.")
    sys.exit(1)


def main() -> None:
    agent_sdk_root, docs_path = resolve_paths()

    print("\n" + "=" * 60)
    print("Checking documented examples...")
    print("=" * 60)

    # 查找智能体-SDK 中的所有示例
    print("\n📋 Scanning agent-sdk examples...")
    agent_examples = find_agent_sdk_examples(agent_sdk_root)
    print(f"   Found {len(agent_examples)} example file(s)")

    changed_examples = find_changed_examples_for_pull_request(agent_sdk_root)
    if changed_examples is not None:
        agent_examples &= changed_examples
        print(
            "   Pull request mode: checking "
            f"{len(agent_examples)} changed example file(s)"
        )

    # 在文档中查找所有记录的示例
    print("\n📄 Scanning docs repository...")
    documented_examples = find_documented_examples(docs_path)
    print(f"   Found {len(documented_examples)} documented example(s)")

    # 计算差异
    undocumented = agent_examples - documented_examples

    print("\n" + "=" * 60)
    if undocumented:
        print(f"❌ Found {len(undocumented)} undocumented example(s):")
        print("=" * 60)
        for example in sorted(undocumented):
            print(f"   - {example}")
        print("\n⚠️  Please add documentation for these examples in the docs repo.")
        print("=" * 60)
        print("\n📚 How to Document Examples:")
        print("=" * 60)
        print("1. Clone the docs repository:")
        print("   git clone https://github.com/OpenHands/docs.git")
        print()
        print("2. Create a new .mdx file in sdk/guides/ directory")
        print("   (e.g., sdk/guides/my-feature.mdx)")
        print()
        print("3. Add the example code block with this format:")
        print('   ```python icon="python" expandable examples/path/to/file.py')
        print("   <code will be auto-synced>")
        print("   ```")
        print()
        print("4. See the format documentation at:")
        print(
            "   https://github.com/OpenHands/docs/blob/main/.github/scripts/README.md"
        )
        print()
        print("5. Example documentation files can be found in:")
        print("   https://github.com/OpenHands/docs/tree/main/sdk/guides")
        print()
        print("6. After creating the PR in docs repo, reference it in your")
        print("   agent-sdk PR description.")
        print("=" * 60)
        sys.exit(1)
    else:
        print("✅ All examples are documented!")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
