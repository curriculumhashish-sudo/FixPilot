#!/usr/bin/env python3
"""
检查示例目录中是否有重复的示例编号。

此脚本确保每个示例子目录内的文件或文件夹没有相同的数字前缀（e.g，两个文件都以 "04_"
开头）。

退出代码：
    0 - 未找到重复项 1 - 找到重复项
"""

import re
import sys
from collections import defaultdict
from pathlib import Path


def find_duplicate_numbers(examples_dir: Path) -> dict[str, list[str]]:
    """
    在每个子目录中查找重复的示例编号。

    Returns:
        将子目录路径映射到重复条目列表的字典。 仅包含具有重复项的子目录。
    """
    duplicates: dict[str, list[str]] = {}

    # 从文件名/目录名 e.g., "04_foo.py" 中提取前导数字的模式
    #
    number_pattern = re.compile(r"^(\d+)_")

    for subdir in sorted(examples_dir.iterdir()):
        if not subdir.is_dir():
            continue

        # 跳过隐藏目录
        if subdir.name.startswith("."):
            continue

        # 按数字前缀对条目进行分组
        number_to_entries: dict[str, list[str]] = defaultdict(list)

        for entry in subdir.iterdir():
            # 跳过隐藏文件/目录
            if entry.name.startswith("."):
                continue

            match = number_pattern.match(entry.name)
            if match:
                number = match.group(1)
                number_to_entries[number].append(entry.name)

        # 查找包含多个条目的数字
        subdir_duplicates = []
        for number, entries in sorted(number_to_entries.items()):
            if len(entries) > 1:
                subdir_duplicates.extend(sorted(entries))

        if subdir_duplicates:
            relative_subdir = str(subdir.relative_to(examples_dir.parent))
            duplicates[relative_subdir] = subdir_duplicates

    return duplicates


def main() -> None:
    # 找到与此脚本相关的示例目录
    script_file = Path(__file__).resolve()
    repo_root = script_file.parent.parent.parent
    examples_dir = repo_root / "examples"

    if not examples_dir.exists():
        print(f"Error: Examples directory not found: {examples_dir}")
        sys.exit(1)

    print("=" * 60)
    print("Checking for duplicate example numbers...")
    print("=" * 60)
    print(f"\n📁 Scanning: {examples_dir}\n")

    duplicates = find_duplicate_numbers(examples_dir)

    if duplicates:
        print("❌ Found duplicate example numbers:\n")
        for subdir, entries in sorted(duplicates.items()):
            print(f"  {subdir}/")
            for entry in entries:
                print(f"    - {entry}")
            print()

        print("=" * 60)
        print("⚠️  Please renumber the examples to remove duplicates.")
        print("   Each example should have a unique number within its folder.")
        print("=" * 60)
        sys.exit(1)
    else:
        print("✅ No duplicate example numbers found!")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
