#!/usr/bin/env python3
"""
检查所有工具子类是否在导入时自动注册。

规则：
1. 所有 ToolDefinition 子类应在模块级别调用 register_tool()
2. register_tool() 调用应该位于模块的末尾
3. 注册应使用以下模式：register_tool(ToolName.name, ToolName)
"""

import ast
import sys
from pathlib import Path


class ToolChecker(ast.NodeVisitor):
    """AST 访客检查工具注册。"""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.tool_classes: set[str] = set()
        self.registered_tools: set[str] = set()
        self.imports_register_tool = False

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """检查是否导入了register_tool。"""
        if node.module and "openhands.sdk.tool" in node.module:
            for alias in node.names:
                if alias.name == "register_tool":
                    self.imports_register_tool = True
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """查找所有 ToolDefinition 子类。"""
        # 检查这个类是否继承自ToolDefinition
        for base in node.bases:
            base_name = self._get_name(base)
            # 检查直接继承还是泛型继承
            if "ToolDefinition" in base_name:
                self.tool_classes.add(node.name)
                break
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        """Find register_tool() calls."""
        if isinstance(node.value, ast.Call):
            func = node.value
            if isinstance(func.func, ast.Name) and func.func.id == "register_tool":
                # 检查第二个参数是否是工具类名称
                if len(func.args) >= 2:
                    tool_arg = func.args[1]
                    if isinstance(tool_arg, ast.Name):
                        self.registered_tools.add(tool_arg.id)
        self.generic_visit(node)

    def _get_name(self, node: ast.expr) -> str:
        """从 AST 节点提取名称（处理名称、属性、下标）。"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            return self._get_name(node.value)
        return ""


def check_tool_registration(
    file_path: Path, is_special_file: bool = False
) -> list[str]:
    """检查文件中的所有 Tool 子类是否已注册。

    Args:
        file_path: 要检查的 Python 文件的路径
        is_special_file: 如果为 True，则仅检查是否至少注册了一个工具
                        （对于具有工具集模式的文件）

    Returns:
        错误消息列表（如果未发现问题则为空）
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except SyntaxError as e:
        return [f"Syntax error: {e}"]
    except Exception as e:
        return [f"Error reading file: {e}"]

    checker = ToolChecker(file_path)
    checker.visit(tree)

    errors = []

    # 检查文件是否定义了任何工具类
    if not checker.tool_classes:
        return []  # 没有定义工具，无需检查

    # 对于特殊文件（如browser_use），只需检查SOME工具是否已注册
    if is_special_file:
        if checker.tool_classes and not checker.registered_tools:
            errors.append(
                "File defines Tool classes but none are registered. "
                "At least one tool should be registered."
            )
        return errors

    # 检查定义工具时是否导入了register_tool
    if checker.tool_classes and not checker.imports_register_tool:
        errors.append(
            "File defines Tool classes but does not import register_tool "
            "from openhands.sdk.tool"
        )

    # 检查所有定义的工具是否已注册
    unregistered = checker.tool_classes - checker.registered_tools
    if unregistered:
        for tool in sorted(unregistered):
            errors.append(
                f"Tool '{tool}' is defined but not registered. "
                f"Add: register_tool({tool}.name, {tool})"
            )

    return errors


def main(files: list[str] | None = None) -> int:
    """
    Main 入口用于工具注册检查。

    Args:
        files: 要检查的特定文件的可选列表。 如果 None，则检查所有文件。

    Returns:
        如果没有发现违规行为，则为 0，否则为 1。
    """
    repo_root = Path(__file__).parent.parent
    tools_path = repo_root / "openhands-tools" / "openhands" / "tools"

    # 跳过检查某些文件/目录
    skip_patterns = {
        "__init__.py",
        "preset",  # 预设模块不定义工具，只是使用它们
        "impl.py",  # 执行者的实施文件
        "executor.py",  # 执行器文件
    }

    # 具有特殊模式的文件 (e.g., 注册多个工具的工具集。这些文件手动检查以确保至少有一个工
    # 具被注册
    #
    special_files = {
        "browser_use/definition.py",  # 为所有浏览器工具注册 BrowserToolSet
        "delegate/definition.py",  # 可能有特殊的注册模式
    }

    if files:
        # 过滤以仅检查工具目录中的文件
        files_to_check = [
            Path(f).resolve()
            for f in files
            if str(tools_path) in str(Path(f).resolve())
            and Path(f).name.endswith(".py")
        ]
    else:
        # 检查tools目录下的所有Python个文件
        files_to_check = list(tools_path.rglob("*.py"))

    # 过滤掉与跳过模式匹配的文件
    files_to_check = [
        f
        for f in files_to_check
        if not any(pattern in str(f) for pattern in skip_patterns)
    ]

    all_errors = []

    for file_path in files_to_check:
        # 检查这是否是一个特殊文件
        rel_path = file_path.relative_to(repo_root)
        rel_path_posix = rel_path.as_posix()
        is_special = any(special in rel_path_posix for special in special_files)

        errors = check_tool_registration(file_path, is_special_file=is_special)
        if errors:
            print(f"[ERROR] Tool registration issues in {rel_path}:")
            for error in errors:
                print(f"  {error}")
            all_errors.extend(errors)

    if all_errors:
        print(
            "\nTool registration rules:\n"
            "  - All ToolDefinition subclasses must be registered using "
            "register_tool()\n"
            "  - Add at module level: register_tool(ToolName.name, ToolName)\n"
            "  - Import register_tool from openhands.sdk.tool"
        )
        return 1

    print("All Tool subclasses are properly registered!")
    return 0


if __name__ == "__main__":
    # 从命令行参数获取文件（从预提交）
    files = sys.argv[1:] if len(sys.argv) > 1 else None
    sys.exit(main(files))
