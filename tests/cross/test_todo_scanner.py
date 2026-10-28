"""测试简化的 TODO 扫描仪功能。"""

import sys
import tempfile
from pathlib import Path


# 导入扫描仪功能
todo_mgmt_path = (
    Path(__file__).parent.parent.parent
    / "examples"
    / "03_github_workflows"
    / "03_todo_management"
)
sys.path.append(str(todo_mgmt_path))
from scanner import (  # noqa: E402  # type: ignore[import-not-found]
    scan_directory,
    scan_file_for_todos,
)


def test_scan_python_file_with_todos():
    """测试扫描包含 TODO 条注释的 Python 文件。"""
    content = """#!/usr/bin/env python3
def function1():
    # TODO(openhands): Add input validation
    return "hello"

def function2():
    # TODO(openhands): Implement error handling
    pass
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(content)
        f.flush()

        todos = scan_file_for_todos(Path(f.name))

    Path(f.name).unlink()

    assert len(todos) == 2
    assert todos[0]["description"] == "Add input validation"
    assert todos[1]["description"] == "Implement error handling"


def test_scan_typescript_file():
    """测试扫描 TypeScript 文件。"""
    content = """function processData(): string {
    // TODO(openhands): Add validation
    return data;
}
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
        f.write(content)
        f.flush()

        todos = scan_file_for_todos(Path(f.name))

    Path(f.name).unlink()

    assert len(todos) == 1
    assert todos[0]["description"] == "Add validation"


def test_scan_java_file():
    """测试扫描 Java 文件。"""
    content = """public class Test {
    public void method() {
        // TODO(openhands): Implement this method
        System.out.println("Hello");
    }
}
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
        f.write(content)
        f.flush()

        todos = scan_file_for_todos(Path(f.name))

    Path(f.name).unlink()

    assert len(todos) == 1
    assert todos[0]["description"] == "Implement this method"


def test_scan_rust_file():
    """测试扫描 Rust 文件。"""
    content = """fn main() {
    // TODO(openhands): Add error handling
    println!("Hello, world!");
}"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".rs", delete=False) as f:
        f.write(content)
        f.flush()

        todos = scan_file_for_todos(Path(f.name))

    Path(f.name).unlink()

    assert len(todos) == 1
    assert todos[0]["description"] == "Add error handling"


def test_scan_unsupported_file_extension():
    """测试是否忽略不支持的文件扩展名。"""
    content = """// TODO(openhands): This should be ignored"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write(content)
        f.flush()

        todos = scan_file_for_todos(Path(f.name))

    Path(f.name).unlink()

    assert len(todos) == 0


def test_scan_all_todos():
    """测试是否找到所有 TODO(OpenHands) 评论。"""
    content = """def test():
    # TODO(openhands): This should be found
    # TODO(openhands): This should also be found
    # TODO(openhands): https://github.com/owner/repo/pull/123
    pass
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(content)
        f.flush()

        todos = scan_file_for_todos(Path(f.name))

    Path(f.name).unlink()

    assert len(todos) == 3
    assert todos[0]["description"] == "This should be found"
    assert todos[1]["description"] == "This should also be found"
    assert todos[2]["description"] == "https://github.com/owner/repo/pull/123"


def test_scan_directory():
    """测试扫描包含多个文件的目录。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # 使用 TODO 创建 Python 文件（避免文件名中包含“test”）
        py_file = temp_path / "main.py"
        py_file.write_text("# TODO(openhands): Python todo\nprint('hello')")

        # 使用 TODO 创建 TypeScript 文件（避免文件名中包含“test”）
        ts_file = temp_path / "app.ts"
        ts_file.write_text("// TODO(openhands): TypeScript todo\nconsole.log('hello');")

        # 创建不受支持的文件（应忽略）
        js_file = temp_path / "script.js"
        js_file.write_text("// TODO(openhands): Should be ignored")

        todos = scan_directory(temp_path)

        assert len(todos) == 2
        descriptions = [todo["description"] for todo in todos]
        assert "Python todo" in descriptions
        assert "TypeScript todo" in descriptions


def test_todo_with_continuation_lines():
    """使用连续注释行测试 TODO。"""
    content = """def test():
    # TODO(openhands): Add error handling
    # This should handle network timeouts
    # and retry failed requests
    # with exponential backoff
    pass
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(content)
        f.flush()

        todos = scan_file_for_todos(Path(f.name))

    Path(f.name).unlink()

    assert len(todos) == 1
    expected_desc = (
        "Add error handling This should handle network timeouts "
        "and retry failed requests with exponential backoff"
    )
    assert todos[0]["description"] == expected_desc


def test_todo_without_description():
    """测试 TODO 没有初始描述，但有连续行。"""
    content = """def test():
    # TODO(openhands)
    # Implement user authentication
    # with proper session management
    pass
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(content)
        f.flush()

        todos = scan_file_for_todos(Path(f.name))

    Path(f.name).unlink()

    assert len(todos) == 1
    expected_desc = "Implement user authentication with proper session management"
    assert todos[0]["description"] == expected_desc


def test_empty_file():
    """测试扫描空文件。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("")
        f.flush()

        todos = scan_file_for_todos(Path(f.name))

    Path(f.name).unlink()

    assert len(todos) == 0


def test_custom_todo_identifier():
    """使用自定义 TODO 标识符测试扫描。"""
    content = """def test():
    # TODO(myteam): Custom identifier test
    # This should be found with custom identifier
    pass
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(content)
        f.flush()

        # 使用自定义标识符进行测试
        todos = scan_file_for_todos(Path(f.name), "TODO(myteam)")

    Path(f.name).unlink()

    assert len(todos) == 1
    assert todos[0]["description"] == (
        "Custom identifier test This should be found with custom identifier"
    )


def test_custom_identifier_with_special_chars():
    """使用正则表达式特殊字符测试自定义标识符。"""
    content = """def test():
    # TODO[urgent]: Special chars in identifier
    pass
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(content)
        f.flush()

        # 使用包含正则表达式特殊字符的标识符进行测试
        todos = scan_file_for_todos(Path(f.name), "TODO[urgent]")

    Path(f.name).unlink()

    assert len(todos) == 1
    assert todos[0]["description"] == "Special chars in identifier"
