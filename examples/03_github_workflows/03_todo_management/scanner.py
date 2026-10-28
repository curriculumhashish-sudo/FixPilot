#!/usr/bin/env python3
"""
TODO 用于 OpenHands 自动化 TODO 管理的扫描仪

扫描 Python、TypeScript、Java 和 Rust 文件中的可配置 TODO 注释。 默认标识符：TODO(
OpenHands)
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path


# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        # 将日志输出到标准错误以避免干扰 JSON
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger(__name__)


def scan_file_for_todos(
    file_path: Path, todo_identifier: str = "TODO(openhands)"
) -> list[dict]:
    """扫描单个文件以获取可配置的 TODO 注释。"""
    # 仅扫描特定文件扩展名
    if file_path.suffix.lower() not in {".py", ".ts", ".java", ".rs"}:
        logger.debug(f"Skipping file {file_path} (unsupported extension)")
        return []

    # 跳过包含模拟对象 TODOs 的测试文件和示例文件
    file_str = str(file_path)
    if (
        "/test" in file_str
        or "/tests/" in file_str
        or "test_" in file_path.name
        # 跳过示例
        or "examples/03_github_workflows/03_todo_management/" in file_str
    ):
        logger.debug(f"Skipping test/example file: {file_path}")
        return []

    logger.debug(f"Scanning file: {file_path}")

    try:
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"Failed to read file {file_path}: {e}")
        return []

    todos = []
    # 转义标识符中的特殊正则表达式字符
    escaped_identifier = re.escape(todo_identifier)
    todo_pattern = re.compile(rf"{escaped_identifier}(?::\s*(.*))?", re.IGNORECASE)

    for line_num, line in enumerate(lines, 1):
        match = todo_pattern.search(line)
        if match:
            # 从 TODO 行提取初始描述
            description = match.group(1).strip() if match.group(1) else ""

            # 向前查找同时也是注释的延续行
            continuation_lines = []
            for next_line_idx in range(line_num, len(lines)):
                next_line = lines[next_line_idx]
                next_stripped = next_line.strip()

                # 检查此行是否是注释延续
                if (
                    next_stripped.startswith("#")
                    and not next_stripped.startswith(f"# {todo_identifier}")
                    # 跳过空注释行
                    and next_stripped != "#"
                    # #后必须有内容
                    and len(next_stripped) > 1
                ):
                    # 提取评论内容（删除#和前导空格）
                    comment_content = next_stripped[1:].strip()

                    if comment_content:  # 只添加非空内容
                        continuation_lines.append(comment_content)
                elif next_stripped == "#":
                    # 空评论行 - 继续寻找
                    continue
                else:
                    # 在第一个非注释行处停止
                    break

            # 将描述与连续线结合起来
            if continuation_lines:
                if description:
                    full_description = description + " " + " ".join(continuation_lines)
                else:
                    full_description = " ".join(continuation_lines)
            else:
                full_description = description

            todo_item = {
                "file": str(file_path),
                "line": line_num,
                "description": full_description,
            }
            todos.append(todo_item)
            logger.info(f"Found TODO in {file_path}:{line_num}: {full_description}")

    if todos:
        logger.info(f"Found {len(todos)} TODO(s) in {file_path}")
    return todos


def scan_directory(
    directory: Path, todo_identifier: str = "TODO(openhands)"
) -> list[dict]:
    """递归扫描目录中的可配置 TODO 注释。"""
    logger.info(f"Scanning directory: {directory}")
    all_todos = []

    for root, dirs, files in os.walk(directory):
        # 跳过隐藏和常见的忽略目录
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".")
            and d
            not in {
                "__pycache__",
                "node_modules",
                ".venv",
                "venv",
                "build",
                "dist",
            }
        ]

        for file in files:
            file_path = Path(root) / file
            todos = scan_file_for_todos(file_path, todo_identifier)
            all_todos.extend(todos)

    return all_todos


def main():
    """主函数用于扫描 TODOs 并输出结果。"""
    parser = argparse.ArgumentParser(
        description="Scan codebase for configurable TODO comments"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan (default: current directory)",
    )
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    parser.add_argument(
        "--identifier",
        "-i",
        default="TODO(openhands)",
        help="TODO identifier to search for (default: TODO(openhands))",
    )

    args = parser.parse_args()

    path = Path(args.directory)
    if not path.exists():
        logger.error(f"Path '{path}' does not exist")
        return 1

    if path.is_file():
        logger.info(f"Starting TODO scan on file: {path}")
        todos = scan_file_for_todos(path, args.identifier)
    else:
        logger.info(f"Starting TODO scan in directory: {path}")
        todos = scan_directory(path, args.identifier)
    logger.info(f"Scan complete. Found {len(todos)} total TODO(s)")
    output = json.dumps(todos, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Found {len(todos)} TODO(s), written to {args.output}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    exit(main())
