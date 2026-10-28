#!/usr/bin/env python3
"""
检查 OpenHands 个包之间的导入依赖关系规则。

规则：
1. openhands.sdk 应该不导入自：
   - openhands.tools
   - openhands.workspace
   - openhands.agent_server

2. openhands.tools 可以从以下位置导入：
   - openhands.sdk
   BUT 不来自：
   - openhands.workspace
   - openhands.agent_server

3. openhands.workspace 可以从以下位置导入：
   - openhands.sdk
   - openhands.tools
   BUT 不来自：
   - openhands.agent_server

4. openhands.agent_server 可以从以下位置导入：
   - openhands.sdk
   - openhands.tools
   BUT 不来自：
   - openhands.workspace
"""

import ast
import sys
from pathlib import Path


class ImportChecker(ast.NodeVisitor):
    """AST 访问者提取导入语句。"""

    def __init__(self):
        self.imports: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.add(node.module)
        self.generic_visit(node)


def get_imports_from_file(file_path: Path) -> set[str]:
    """从 Python 文件中提取所有导入模块名称。"""
    try:
        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
        checker = ImportChecker()
        checker.visit(tree)
        return checker.imports
    except SyntaxError as e:
        print(f"Warning: Could not parse {file_path}: {e}", file=sys.stderr)
        return set()
    except Exception as e:
        print(f"Warning: Error reading {file_path}: {e}", file=sys.stderr)
        return set()


def check_sdk_imports(sdk_path: Path) -> list[tuple[Path, str]]:
    """检查 openhands.sdk 是否未从 tools/workspace/agent_server 导入。"""  # noqa: E501
    violations = []
    forbidden = ["openhands.tools", "openhands.workspace", "openhands.agent_server"]

    for py_file in sdk_path.rglob("*.py"):
        imports = get_imports_from_file(py_file)
        for imp in imports:
            for forbidden_module in forbidden:
                if imp == forbidden_module or imp.startswith(f"{forbidden_module}."):
                    violations.append((py_file, imp))

    return violations


def check_tools_imports(tools_path: Path) -> list[tuple[Path, str]]:
    """检查 openhands.tools 是否未从工作区或 agent_server 导入。"""
    violations = []
    forbidden = ["openhands.workspace", "openhands.agent_server"]

    for py_file in tools_path.rglob("*.py"):
        imports = get_imports_from_file(py_file)
        for imp in imports:
            for forbidden_module in forbidden:
                if imp == forbidden_module or imp.startswith(f"{forbidden_module}."):
                    violations.append((py_file, imp))

    return violations


def check_agent_server_imports(agent_server_path: Path) -> list[tuple[Path, str]]:
    """检查 openhands.agent_server 是否未从工作区导入。"""
    violations = []
    forbidden = ["openhands.workspace"]

    for py_file in agent_server_path.rglob("*.py"):
        imports = get_imports_from_file(py_file)
        for imp in imports:
            for forbidden_module in forbidden:
                if imp == forbidden_module or imp.startswith(f"{forbidden_module}."):
                    violations.append((py_file, imp))

    return violations


def main(files: list[str] | None = None) -> int:
    """
    Main 入口用于导入规则检查。

    Args:
        files: 要检查的特定文件的可选列表。 如果 None，则检查所有文件。

    Returns:
        如果没有发现违规行为，则为 0，否则为 1。
    """
    repo_root = Path(__file__).parent.parent
    sdk_path = repo_root / "openhands-sdk" / "openhands" / "sdk"
    tools_path = repo_root / "openhands-tools" / "openhands" / "tools"
    agent_server_path = (
        repo_root / "openhands-agent-server" / "openhands" / "agent_server"
    )

    # 如果提供了特定文件，则过滤器仅检查这些目录
    if files:
        # 将文件路径转换为绝对路径以进行比较
        abs_files = [str(Path(f).resolve()) for f in files]
        check_sdk = any(str(sdk_path) in f for f in abs_files)
        check_tools = any(str(tools_path) in f for f in abs_files)
        check_agent_server = any(str(agent_server_path) in f for f in abs_files)
    else:
        # 如果没有指定文件，则检查所有包
        check_sdk = True
        check_tools = True
        check_agent_server = True

    all_violations = []

    # 检查SDK进口
    if check_sdk and sdk_path.exists():
        violations = check_sdk_imports(sdk_path)
        if violations:
            print("[ERROR] Violations in openhands.sdk:")
            for file, imp in violations:
                rel_path = file.relative_to(repo_root)
                print(
                    f"  {rel_path}: imports {imp} "
                    "(sdk should not import tools/workspace/agent_server)"
                )
            all_violations.extend(violations)

    # 检查工具导入
    if check_tools and tools_path.exists():
        violations = check_tools_imports(tools_path)
        if violations:
            print("[ERROR] Violations in openhands.tools:")
            for file, imp in violations:
                rel_path = file.relative_to(repo_root)
                print(
                    f"  {rel_path}: imports {imp} "
                    "(tools should not import workspace/agent_server)"
                )
            all_violations.extend(violations)

    # 检查agent_server进口
    if check_agent_server and agent_server_path.exists():
        violations = check_agent_server_imports(agent_server_path)
        if violations:
            print("[ERROR] Violations in openhands.agent_server:")
            for file, imp in violations:
                rel_path = file.relative_to(repo_root)
                print(
                    f"  {rel_path}: imports {imp} "
                    "(agent_server should not import workspace)"
                )
            all_violations.extend(violations)

    if all_violations:
        print(
            "\nImport dependency rules:\n"
            "  - openhands.sdk: Cannot import tools/workspace/agent_server\n"
            "  - openhands.tools: Cannot import workspace/agent_server "
            "(can import sdk)\n"
            "  - openhands.agent_server: Cannot import workspace "
            "(can import sdk/tools)\n"
            "  - openhands.workspace: Can import sdk/tools"
        )
        return 1

    print("All import dependency rules satisfied!")
    return 0


if __name__ == "__main__":
    # 从命令行参数获取文件（从预提交）
    files = sys.argv[1:] if len(sys.argv) > 1 else None
    sys.exit(main(files))
