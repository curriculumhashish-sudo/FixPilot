"""测试验证 ripgrep 和 Python 回退方案之间的一致性。"""

import tempfile
from pathlib import Path

import pytest

from openhands.tools.grep.definition import GrepAction
from openhands.tools.grep.impl import GrepExecutor
from openhands.tools.utils import _check_ripgrep_available


# ruff: noqa


@pytest.mark.skipif(
    not _check_ripgrep_available(),
    reason="ripgrep not available - consistency tests require ripgrep",
)
class TestGrepConsistency:
    """测试 ripgrep 和 Python 回退方案保持一致。"""

    @pytest.fixture
    def temp_dir_with_content(self):
        """创建一个临时目录，其中包含包含可搜索内容的测试文件。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建内容更复杂的测试文件
            test_files = {
                # 根级文件
                "app.py": "def main():\n    print('Hello World')\n    return 0\n# TODO: add error handling",
                "main.py": "import sys\ndef hello():\n    print('Hello from main')\n# FIXME: refactor this",
                "test.py": (
                    "import unittest\nclass TestApp(unittest.TestCase):\n    # TODO: write tests\n    pass"
                ),
                "setup.py": "from setuptools import setup\n# Configuration for package",
                "config.json": '{"name": "test", "version": "1.0", "hello": "world", "debug": true}',
                "config.yaml": "name: test\nversion: 1.0\nhello: world\n",
                "readme.md": "# Hello World\nThis is a test project.\n## TODO\n- Add features",
                "README.MD": "# Alternative README\nHELLO WORLD\n",
                ".env": "API_KEY=secret123\nDEBUG=true\n",
                ".gitignore": "*.pyc\n__pycache__/\n.env\n",
                # 源码目录
                "src/utils.py": "def helper():\n    return 'Hello from helper'\n\ndef error_handler():\n    raise Exception('Error!')",
                "src/models.py": (
                    "class User:\n    def __init__(self, name):\n"
                    "        self.name = name\n\nclass Admin(User):\n    pass"
                ),
                "src/api.py": "import requests\n\ndef fetch_data():\n    # TODO: add retry logic\n    return requests.get('http://example.com')",
                "src/__init__.py": "# Package initialization\n",
                "src/core/engine.py": "class Engine:\n    def __init__(self):\n        self.running = False\n    # FIXME: memory leak",
                "src/core/parser.py": "import re\n\ndef parse(text):\n    # TODO: handle edge cases\n    return re.findall(r'\\w+', text)",
                "src/core/__init__.py": "",
                "src/plugins/auth.py": "def authenticate(user, password):\n    # Security: hash passwords\n    return user == 'admin'",
                "src/plugins/db.py": "class Database:\n    def connect(self):\n        # TODO: add connection pooling\n        pass",
                "src/plugins/__init__.py": "",
                # 测试目录
                "tests/test_utils.py": "def test_helper():\n    # TODO: add assertions\n    pass",
                "tests/test_models.py": "def test_user():\n    assert True  # FIXME: real test",
                "tests/integration/test_api.py": "def test_api():\n    # Integration test\n    pass",
                "tests/integration/__init__.py": "",
                "tests/unit/test_engine.py": "def test_engine():\n    # Unit test for engine\n    pass",
                "tests/unit/test_parser.py": "def test_parser():\n    # TODO: test edge cases\n    pass",
                "tests/unit/__init__.py": "",
                # 文档
                "docs/guide.md": "# User Guide\nSay hello to get started.\n\n## Examples\nTODO: add examples",
                "docs/api.md": "# API Reference\n\n## Authentication\nUse API keys for auth.",
                "docs/tutorial.rst": "Tutorial\n========\n\nHello from tutorial\n\nTODO: complete sections",
                "docs/CHANGELOG.md": "# Changelog\n\n## v1.0.0\n- Initial release\n\n## TODO\n- Add v2.0 features",
                # 配置文件
                "config/settings.json": '{"debug": true, "timeout": 30, "retries": 3}',
                "config/database.yaml": "host: localhost\nport: 5432\nuser: admin\n",
                "config/logging.ini": "[loggers]\nkeys=root\n\n[handlers]\nkeys=console",
                "config/secrets.env": "API_KEY=secret\nDB_PASSWORD=pass123\n",
                # 脚本
                "scripts/deploy.sh": "#!/bin/bash\necho 'Deploying...'\n# TODO: add validation",
                "scripts/build.py": "import subprocess\n# Build script\nsubprocess.run(['make', 'build'])",
                "scripts/test.py": "import pytest\n# Run tests\npytest.main(['-v'])",
                # 构建工件
                "build/output.js": "console.log('Hello from build');\n// TODO: minify",
                "build/styles.css": "body { margin: 0; }\n/* TODO: add dark mode */",
                # 隐藏目录
                ".github/workflows/ci.yml": "name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest",
                ".github/workflows/deploy.yml": "name: Deploy\n# TODO: add production deploy",
                # 深度嵌套
                "deep/level1/level2/level3/file.py": "# Deep nested file\ndef deep_function():\n    return 'hello from deep'",
                "deep/level1/level2/level3/data.json": '{"deep": "nested", "hello": "world"}',
                # 内容中的特殊字符
                "special.txt": "Line with ERROR: something failed\nLine with WARNING: be careful\nLine with INFO: all good",
                "patterns.txt": "email@example.com\n192.168.1.1\nhttp://example.com\n",
                # 类似二进制文件（不会匹配文本搜索）
                "data.bin": "\x00\x01\x02\x03\x04",
                # 空文件
                "empty.txt": "",
            }

            for file_path, content in test_files.items():
                full_path = Path(temp_dir) / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content)

            yield temp_dir

    def test_basic_search_consistency(self, temp_dir_with_content):
        """测试 ripgrep 和 Python 回退方案是否为基本搜索返回一致的结果。"""
        executor = GrepExecutor(temp_dir_with_content)
        action = GrepAction(pattern="hello")

        # 从 ripgrep 和 Python 回退方案获取结果
        ripgrep_result = executor._execute_with_ripgrep(
            action, Path(temp_dir_with_content)
        )
        python_result = executor._execute_with_python_search(
            action, Path(temp_dir_with_content)
        )

        # 两者都应该成功
        assert not ripgrep_result.is_error
        assert not python_result.is_error

        # 转换为匹配文件集以进行精确比较
        ripgrep_matches = set(ripgrep_result.matches)
        python_matches = set(python_result.matches)

        # Ripgrep 和 Python 回退方案必须返回完全相同的文件
        assert ripgrep_matches == python_matches, (
            f"Ripgrep found: {ripgrep_matches}\n"
            f"Python fallback found: {python_matches}\n"
            f"Difference (ripgrep - Python fallback): {ripgrep_matches - python_matches}\n"
            f"Difference (Python fallback - ripgrep): {python_matches - ripgrep_matches}"
        )

    def test_case_insensitive_consistency(self, temp_dir_with_content):
        """测试 ripgrep 和 Python 回退方案是否一致地处理不区分大小写的搜索。"""
        executor = GrepExecutor(temp_dir_with_content)
        action = GrepAction(pattern="HELLO")  # 大写模式

        # 从 ripgrep 和 Python 回退方案获取结果
        ripgrep_result = executor._execute_with_ripgrep(
            action, Path(temp_dir_with_content)
        )
        python_result = executor._execute_with_python_search(
            action, Path(temp_dir_with_content)
        )

        # 两者都应该成功
        assert not ripgrep_result.is_error
        assert not python_result.is_error

        # 转换为集合以进行精确比较
        ripgrep_matches = set(ripgrep_result.matches)
        python_matches = set(python_result.matches)

        # Ripgrep 和 Python 回退方案必须返回完全相同的文件
        assert ripgrep_matches == python_matches, (
            f"Ripgrep found: {ripgrep_matches}\n"
            f"Python fallback found: {python_matches}\n"
            f"Difference (ripgrep - Python fallback): {ripgrep_matches - python_matches}\n"
            f"Difference (Python fallback - ripgrep): {python_matches - ripgrep_matches}"
        )

    def test_include_pattern_consistency(self, temp_dir_with_content):
        """测试 ripgrep 和 Python 回退方案句柄是否一致地包含模式。"""
        executor = GrepExecutor(temp_dir_with_content)
        action = GrepAction(pattern="hello", include="*.py")

        # 从 ripgrep 和 Python 回退方案获取结果
        ripgrep_result = executor._execute_with_ripgrep(
            action, Path(temp_dir_with_content)
        )
        python_result = executor._execute_with_python_search(
            action, Path(temp_dir_with_content)
        )

        # 两者都应该成功
        assert not ripgrep_result.is_error
        assert not python_result.is_error

        # 转换为集合以进行精确比较
        ripgrep_matches = set(ripgrep_result.matches)
        python_matches = set(python_result.matches)

        # Ripgrep 和 Python 回退方案必须返回完全相同的文件
        assert ripgrep_matches == python_matches, (
            f"Ripgrep found: {ripgrep_matches}\n"
            f"Python fallback found: {python_matches}\n"
            f"Difference (ripgrep - Python fallback): {ripgrep_matches - python_matches}\n"
            f"Difference (Python fallback - ripgrep): {python_matches - ripgrep_matches}"
        )

        # 验证所有匹配项都是 Python 个文件
        for match in ripgrep_matches:
            assert match.endswith(".py"), f"Non-Python file found: {match}"

    def test_no_matches_consistency(self, temp_dir_with_content):
        """测试 ripgrep 和 Python 回退方案是否一致地处理不匹配的情况。"""
        executor = GrepExecutor(temp_dir_with_content)
        action = GrepAction(pattern="nonexistentpattern12345")

        # 从 ripgrep 和 Python 回退方案获取结果
        ripgrep_result = executor._execute_with_ripgrep(
            action, Path(temp_dir_with_content)
        )
        python_result = executor._execute_with_python_search(
            action, Path(temp_dir_with_content)
        )

        # 两者都应该成功并获得相同的空结果
        assert not ripgrep_result.is_error
        assert not python_result.is_error

        # 转换为集合以进行精确比较
        ripgrep_matches = set(ripgrep_result.matches)
        python_matches = set(python_result.matches)

        # 两者必须返回完全相同的（空）集
        assert ripgrep_matches == python_matches == set()

    def test_regex_pattern_consistency(self, temp_dir_with_content):
        """测试 ripgrep 和 Python 回退方案是否一致地处理简单的正则表达式模式。"""
        executor = GrepExecutor(temp_dir_with_content)
        action = GrepAction(pattern="def ")  # 应该适用于两者的简单模式

        # 从 ripgrep 和 Python 回退方案获取结果
        ripgrep_result = executor._execute_with_ripgrep(
            action, Path(temp_dir_with_content)
        )
        python_result = executor._execute_with_python_search(
            action, Path(temp_dir_with_content)
        )

        # 两者都应该成功
        assert not ripgrep_result.is_error
        assert not python_result.is_error

        # 转换为集合以进行精确比较
        ripgrep_matches = set(ripgrep_result.matches)
        python_matches = set(python_result.matches)

        # Ripgrep 和 Python 回退方案必须返回完全相同的文件
        assert ripgrep_matches == python_matches, (
            f"Ripgrep found: {ripgrep_matches}\n"
            f"Python fallback found: {python_matches}\n"
            f"Difference (ripgrep - Python fallback): {ripgrep_matches - python_matches}\n"
            f"Difference (Python fallback - ripgrep): {python_matches - ripgrep_matches}"
        )

    def test_todo_comments_consistency(self, temp_dir_with_content):
        """测试 ripgrep 和 Python 回退方案 find TODO 注释是否一致。"""
        executor = GrepExecutor(temp_dir_with_content)
        action = GrepAction(pattern="TODO")

        # 从 ripgrep 和 Python 回退方案获取结果
        ripgrep_result = executor._execute_with_ripgrep(
            action, Path(temp_dir_with_content)
        )
        python_result = executor._execute_with_python_search(
            action, Path(temp_dir_with_content)
        )

        # 两者都应该成功
        assert not ripgrep_result.is_error
        assert not python_result.is_error

        # 转换为集合以进行精确比较
        ripgrep_matches = set(ripgrep_result.matches)
        python_matches = set(python_result.matches)

        # Ripgrep 和 Python 回退方案必须返回完全相同的文件
        assert ripgrep_matches == python_matches, (
            f"Ripgrep found: {ripgrep_matches}\n"
            f"Python fallback found: {python_matches}\n"
            f"Difference (ripgrep - Python fallback): {ripgrep_matches - python_matches}\n"
            f"Difference (Python fallback - ripgrep): {python_matches - ripgrep_matches}"
        )

    def test_error_patterns_consistency(self, temp_dir_with_content):
        """测试 ripgrep 和 Python 回退方案是否一致地找到错误模式。"""
        executor = GrepExecutor(temp_dir_with_content)
        action = GrepAction(pattern="ERROR:")

        # 从 ripgrep 和 Python 回退方案获取结果
        ripgrep_result = executor._execute_with_ripgrep(
            action, Path(temp_dir_with_content)
        )
        python_result = executor._execute_with_python_search(
            action, Path(temp_dir_with_content)
        )

        # 两者都应该成功
        assert not ripgrep_result.is_error
        assert not python_result.is_error

        # 转换为集合以进行精确比较
        ripgrep_matches = set(ripgrep_result.matches)
        python_matches = set(python_result.matches)

        # Ripgrep 和 Python 回退方案必须返回完全相同的文件
        assert ripgrep_matches == python_matches, (
            f"Ripgrep found: {ripgrep_matches}\n"
            f"Python fallback found: {python_matches}\n"
            f"Difference (ripgrep - Python fallback): {ripgrep_matches - python_matches}\n"
            f"Difference (Python fallback - ripgrep): {python_matches - ripgrep_matches}"
        )

    def test_import_statements_consistency(self, temp_dir_with_content):
        """测试 ripgrep 和 Python 回退方案是否一致地查找导入语句。"""
        executor = GrepExecutor(temp_dir_with_content)
        action = GrepAction(pattern="import ", include="*.py")

        # 从 ripgrep 和 Python 回退方案获取结果
        ripgrep_result = executor._execute_with_ripgrep(
            action, Path(temp_dir_with_content)
        )
        python_result = executor._execute_with_python_search(
            action, Path(temp_dir_with_content)
        )

        # 两者都应该成功
        assert not ripgrep_result.is_error
        assert not python_result.is_error

        # 转换为集合以进行精确比较
        ripgrep_matches = set(ripgrep_result.matches)
        python_matches = set(python_result.matches)

        # Ripgrep 和 Python 回退方案必须返回完全相同的文件
        assert ripgrep_matches == python_matches, (
            f"Ripgrep found: {ripgrep_matches}\n"
            f"Python fallback found: {python_matches}\n"
            f"Difference (ripgrep - Python fallback): {ripgrep_matches - python_matches}\n"
            f"Difference (Python fallback - ripgrep): {python_matches - ripgrep_matches}"
        )

    def test_class_definitions_consistency(self, temp_dir_with_content):
        """测试 ripgrep 和 Python 回退方案查找类定义是否一致。"""
        executor = GrepExecutor(temp_dir_with_content)
        action = GrepAction(pattern="class ")

        # 从 ripgrep 和 Python 回退方案获取结果
        ripgrep_result = executor._execute_with_ripgrep(
            action, Path(temp_dir_with_content)
        )
        python_result = executor._execute_with_python_search(
            action, Path(temp_dir_with_content)
        )

        # 两者都应该成功
        assert not ripgrep_result.is_error
        assert not python_result.is_error

        # 转换为集合以进行精确比较
        ripgrep_matches = set(ripgrep_result.matches)
        python_matches = set(python_result.matches)

        # Ripgrep 和 Python 回退方案必须返回完全相同的文件
        assert ripgrep_matches == python_matches, (
            f"Ripgrep found: {ripgrep_matches}\n"
            f"Python fallback found: {python_matches}\n"
            f"Difference (ripgrep - Python fallback): {ripgrep_matches - python_matches}\n"
            f"Difference (Python fallback - ripgrep): {python_matches - ripgrep_matches}"
        )

    def test_deep_nested_search_consistency(self, temp_dir_with_content):
        """测试 ripgrep 和 Python 回退方案搜索深度嵌套文件的一致性。"""
        executor = GrepExecutor(temp_dir_with_content)
        action = GrepAction(pattern="deep")

        # 从 ripgrep 和 Python 回退方案获取结果
        ripgrep_result = executor._execute_with_ripgrep(
            action, Path(temp_dir_with_content)
        )
        python_result = executor._execute_with_python_search(
            action, Path(temp_dir_with_content)
        )

        # 两者都应该成功
        assert not ripgrep_result.is_error
        assert not python_result.is_error

        # 转换为集合以进行精确比较
        ripgrep_matches = set(ripgrep_result.matches)
        python_matches = set(python_result.matches)

        # Ripgrep 和 Python 回退方案必须返回完全相同的文件
        assert ripgrep_matches == python_matches, (
            f"Ripgrep found: {ripgrep_matches}\n"
            f"Python fallback found: {python_matches}\n"
            f"Difference (ripgrep - Python fallback): {ripgrep_matches - python_matches}\n"
            f"Difference (Python fallback - ripgrep): {python_matches - ripgrep_matches}"
        )

    def test_config_file_search_consistency(self, temp_dir_with_content):
        """测试 ripgrep 和 Python 回退方案一致地搜索各种配置文件格式。"""
        executor = GrepExecutor(temp_dir_with_content)

        for pattern, file_type in [
            ("debug", "*.json"),
            ("localhost", "*.yaml"),
            ("secret", "*.env"),
        ]:
            action = GrepAction(pattern=pattern, include=file_type)

            # 从 ripgrep 和 Python 回退方案获取结果
            ripgrep_result = executor._execute_with_ripgrep(
                action, Path(temp_dir_with_content)
            )
            python_result = executor._execute_with_python_search(
                action, Path(temp_dir_with_content)
            )

            # 两者都应该成功
            assert not ripgrep_result.is_error
            assert not python_result.is_error

            # 转换为集合以进行精确比较
            ripgrep_matches = set(ripgrep_result.matches)
            python_matches = set(python_result.matches)

            # Ripgrep 和 Python 回退方案必须返回完全相同的文件
            assert ripgrep_matches == python_matches, (
                f"Pattern: {pattern}, File type: {file_type}\n"
                f"Ripgrep found: {ripgrep_matches}\n"
                f"Python fallback found: {python_matches}\n"
                f"Difference (ripgrep - Python fallback): {ripgrep_matches - python_matches}\n"
                f"Difference (Python fallback - ripgrep): {python_matches - ripgrep_matches}"
            )

    def test_hidden_files_search_consistency(self, temp_dir_with_content):
        """测试 ripgrep 和 Python 回退方案搜索隐藏文件的一致性。"""
        executor = GrepExecutor(temp_dir_with_content)
        action = GrepAction(pattern="API_KEY")

        # 从 ripgrep 和 Python 回退方案获取结果
        ripgrep_result = executor._execute_with_ripgrep(
            action, Path(temp_dir_with_content)
        )
        python_result = executor._execute_with_python_search(
            action, Path(temp_dir_with_content)
        )

        # 两者都应该成功
        assert not ripgrep_result.is_error
        assert not python_result.is_error

        # 转换为集合以进行精确比较
        ripgrep_matches = set(ripgrep_result.matches)
        python_matches = set(python_result.matches)

        # Ripgrep 和 Python 回退方案必须返回完全相同的文件
        assert ripgrep_matches == python_matches, (
            f"Ripgrep found: {ripgrep_matches}\n"
            f"Python fallback found: {python_matches}\n"
            f"Difference (ripgrep - Python fallback): {ripgrep_matches - python_matches}\n"
            f"Difference (Python fallback - ripgrep): {python_matches - ripgrep_matches}"
        )
