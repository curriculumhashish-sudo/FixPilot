"""测试以验证 ripgrep 和回退方案实现之间的一致性。"""

import tempfile
from pathlib import Path

import pytest

from openhands.tools.glob.definition import GlobAction
from openhands.tools.glob.impl import GlobExecutor
from openhands.tools.utils import _check_ripgrep_available


@pytest.mark.skipif(
    not _check_ripgrep_available(),
    reason="ripgrep not available - consistency tests require ripgrep",
)
class TestGlobConsistency:
    """测试 ripgrep 和回退方案方法产生一致的结果。"""

    @pytest.fixture
    def temp_dir_with_files(self):
        """创建一个包含测试文件的临时目录。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建结构更复杂的测试文件
            test_files = {
                # 根级文件
                "app.py": "print('hello world')",
                "main.py": "def main(): pass",
                "test.py": "import unittest",
                "config.json": '{"name": "test"}',
                "config.yaml": "name: test",
                "readme.md": "# Test Project",
                "README.MD": "# Alternate README",
                ".gitignore": "*.pyc\n__pycache__/",
                "setup.py": "from setuptools import setup",
                # 源码目录
                "src/utils.py": "def helper(): pass",
                "src/models.py": "class User: pass",
                "src/api.py": "def api_handler(): pass",
                "src/__init__.py": "",
                "src/core/engine.py": "class Engine: pass",
                "src/core/parser.py": "def parse(): pass",
                "src/core/__init__.py": "",
                "src/plugins/auth.py": "def authenticate(): pass",
                "src/plugins/db.py": "class Database: pass",
                "src/plugins/__init__.py": "",
                # 测试目录
                "tests/test_utils.py": "def test_helper(): pass",
                "tests/test_models.py": "def test_user(): pass",
                "tests/integration/test_api.py": "def test_api(): pass",
                "tests/integration/__init__.py": "",
                "tests/unit/test_engine.py": "def test_engine(): pass",
                "tests/unit/test_parser.py": "def test_parser(): pass",
                "tests/unit/__init__.py": "",
                # 文档
                "docs/guide.md": "# Guide",
                "docs/api.md": "# API Reference",
                "docs/tutorial.rst": "Tutorial",
                "docs/images/diagram.png": b"\x89PNG",  # 最小 PNG 标头
                "docs/examples/example1.py": "# Example 1",
                "docs/examples/example2.py": "# Example 2",
                # 各种格式的配置文件
                "config/settings.json": '{"debug": true}',
                "config/database.yaml": "host: localhost",
                "config/logging.ini": "[loggers]",
                "config/secrets.env": "API_KEY=secret",
                # 脚本
                "scripts/deploy.sh": "#!/bin/bash\necho 'deploying'",
                "scripts/build.py": "import subprocess",
                "scripts/test.py": "import pytest",
                # 构建工件（应按模式匹配）
                "build/output.js": "console.log('built')",
                "build/styles.css": "body { margin: 0; }",
                "dist/bundle.js": "// bundled code",
                # 隐藏目录
                ".github/workflows/ci.yml": "name: CI",
                ".github/workflows/deploy.yml": "name: Deploy",
                # 深度嵌套
                "deep/level1/level2/level3/file.py": "# Deep file",
                "deep/level1/level2/level3/data.json": "{}",
                # 多种扩展
                "data.tar.gz": "archive",
                "backup.2024.tar.gz": "backup",
                "script.test.py": "# Test script",
                # 名字中的特殊字符
                "file-with-dashes.py": "# Dashes",
                "file_with_underscores.py": "# Underscores",
                "file.backup.py": "# Backup",
                # 空目录（添加标记文件）
                "empty_dir/.keep": "",
                "another_empty/.gitkeep": "",
            }

            for file_path, content in test_files.items():
                full_path = Path(temp_dir) / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, bytes):
                    full_path.write_bytes(content)
                else:
                    full_path.write_text(content)

            yield temp_dir

    def test_basic_pattern_consistency(self, temp_dir_with_files):
        """测试这两种方法是否为基本模式返回一致的结果。"""
        executor = GlobExecutor(temp_dir_with_files)
        action = GlobAction(pattern="*.py")

        # 从两种方法获取结果
        ripgrep_files, _ = executor._execute_with_ripgrep(
            action.pattern, Path(temp_dir_with_files)
        )
        fallback_files, _ = executor._execute_with_glob(
            action.pattern, Path(temp_dir_with_files)
        )

        # 转换为集合以进行精确比较
        ripgrep_files = set(ripgrep_files)
        fallback_files = set(fallback_files)

        # 两种方法必须返回完全相同的文件
        assert ripgrep_files == fallback_files, (
            f"Ripgrep found: {ripgrep_files}\n"
            f"Fallback found: {fallback_files}\n"
            f"Difference (ripgrep - fallback): {ripgrep_files - fallback_files}\n"
            f"Difference (fallback - ripgrep): {fallback_files - ripgrep_files}"
        )

    def test_recursive_pattern_consistency(self, temp_dir_with_files):
        """测试这两种方法是否一致地处理递归模式。"""
        executor = GlobExecutor(temp_dir_with_files)
        action = GlobAction(pattern="**/*.py")

        # 从两种方法获取结果
        ripgrep_files, _ = executor._execute_with_ripgrep(
            action.pattern, Path(temp_dir_with_files)
        )
        fallback_files, _ = executor._execute_with_glob(
            action.pattern, Path(temp_dir_with_files)
        )

        # 转换为集合以进行精确比较
        ripgrep_files = set(ripgrep_files)
        fallback_files = set(fallback_files)

        # 两种方法必须返回完全相同的文件
        assert ripgrep_files == fallback_files, (
            f"Ripgrep found: {ripgrep_files}\n"
            f"Fallback found: {fallback_files}\n"
            f"Difference (ripgrep - fallback): {ripgrep_files - fallback_files}\n"
            f"Difference (fallback - ripgrep): {fallback_files - ripgrep_files}"
        )

    def test_no_matches_consistency(self, temp_dir_with_files):
        """测试这两种方法是否一致地处理不匹配的情况。"""
        executor = GlobExecutor(temp_dir_with_files)
        action = GlobAction(pattern="*.nonexistent")

        # 从两种方法获取结果
        ripgrep_files, _ = executor._execute_with_ripgrep(
            action.pattern, Path(temp_dir_with_files)
        )
        fallback_files, _ = executor._execute_with_glob(
            action.pattern, Path(temp_dir_with_files)
        )

        # 转换为集合以进行精确比较
        ripgrep_files = set(ripgrep_files)
        fallback_files = set(fallback_files)

        # 两者必须返回完全相同的（空）集
        assert ripgrep_files == fallback_files == set()

    def test_hidden_files_consistency(self, temp_dir_with_files):
        """测试这两种方法是否一致地处理隐藏文件。"""
        executor = GlobExecutor(temp_dir_with_files)
        action = GlobAction(pattern=".*")

        # 从两种方法获取结果
        ripgrep_files, _ = executor._execute_with_ripgrep(
            action.pattern, Path(temp_dir_with_files)
        )
        fallback_files, _ = executor._execute_with_glob(
            action.pattern, Path(temp_dir_with_files)
        )

        # 转换为集合以进行精确比较
        ripgrep_files = set(ripgrep_files)
        fallback_files = set(fallback_files)

        # 两种方法必须返回完全相同的文件
        assert ripgrep_files == fallback_files, (
            f"Ripgrep found: {ripgrep_files}\n"
            f"Fallback found: {fallback_files}\n"
            f"Difference (ripgrep - fallback): {ripgrep_files - fallback_files}\n"
            f"Difference (fallback - ripgrep): {fallback_files - ripgrep_files}"
        )

    def test_multiple_extensions_consistency(self, temp_dir_with_files):
        """测试这两种方法是否一致地处理多个扩展。"""
        executor = GlobExecutor(temp_dir_with_files)
        action = GlobAction(pattern="*.tar.gz")

        # 从两种方法获取结果
        ripgrep_files, _ = executor._execute_with_ripgrep(
            action.pattern, Path(temp_dir_with_files)
        )
        fallback_files, _ = executor._execute_with_glob(
            action.pattern, Path(temp_dir_with_files)
        )

        # 转换为集合以进行精确比较
        ripgrep_files = set(ripgrep_files)
        fallback_files = set(fallback_files)

        # 两种方法必须返回完全相同的文件
        assert ripgrep_files == fallback_files, (
            f"Ripgrep found: {ripgrep_files}\n"
            f"Fallback found: {fallback_files}\n"
            f"Difference (ripgrep - fallback): {ripgrep_files - fallback_files}\n"
            f"Difference (fallback - ripgrep): {fallback_files - ripgrep_files}"
        )

    def test_deep_nesting_consistency(self, temp_dir_with_files):
        """测试这两种方法是否一致地处理深度嵌套文件。"""
        executor = GlobExecutor(temp_dir_with_files)
        action = GlobAction(pattern="**/level3/*.py")

        # 从两种方法获取结果
        ripgrep_files, _ = executor._execute_with_ripgrep(
            action.pattern, Path(temp_dir_with_files)
        )
        fallback_files, _ = executor._execute_with_glob(
            action.pattern, Path(temp_dir_with_files)
        )

        # 转换为集合以进行精确比较
        ripgrep_files = set(ripgrep_files)
        fallback_files = set(fallback_files)

        # 两种方法必须返回完全相同的文件
        assert ripgrep_files == fallback_files, (
            f"Ripgrep found: {ripgrep_files}\n"
            f"Fallback found: {fallback_files}\n"
            f"Difference (ripgrep - fallback): {ripgrep_files - fallback_files}\n"
            f"Difference (fallback - ripgrep): {fallback_files - ripgrep_files}"
        )

    def test_wildcard_directory_consistency(self, temp_dir_with_files):
        """测试这两种方法是否一致地处理通配符目录。"""
        executor = GlobExecutor(temp_dir_with_files)
        action = GlobAction(pattern="**/test*.py")

        # 从两种方法获取结果
        ripgrep_files, _ = executor._execute_with_ripgrep(
            action.pattern, Path(temp_dir_with_files)
        )
        fallback_files, _ = executor._execute_with_glob(
            action.pattern, Path(temp_dir_with_files)
        )

        # 转换为集合以进行精确比较
        ripgrep_files = set(ripgrep_files)
        fallback_files = set(fallback_files)

        # 两种方法必须返回完全相同的文件
        assert ripgrep_files == fallback_files, (
            f"Ripgrep found: {ripgrep_files}\n"
            f"Fallback found: {fallback_files}\n"
            f"Difference (ripgrep - fallback): {ripgrep_files - fallback_files}\n"
            f"Difference (fallback - ripgrep): {fallback_files - ripgrep_files}"
        )

    def test_config_files_consistency(self, temp_dir_with_files):
        """测试这两种方法是否一致地找到各种配置文件格式。"""
        executor = GlobExecutor(temp_dir_with_files)

        for pattern in ["*.json", "*.yaml", "*.yml", "*.ini", "*.env"]:
            action = GlobAction(pattern=pattern)

            # 从两种方法获取结果
            ripgrep_files, _ = executor._execute_with_ripgrep(
                action.pattern, Path(temp_dir_with_files)
            )
            fallback_files, _ = executor._execute_with_glob(
                action.pattern, Path(temp_dir_with_files)
            )

            # 转换为集合以进行精确比较
            ripgrep_files = set(ripgrep_files)
            fallback_files = set(fallback_files)

            # 两种方法必须返回完全相同的文件
            assert ripgrep_files == fallback_files, (
                f"Pattern: {pattern}\n"
                f"Ripgrep found: {ripgrep_files}\n"
                f"Fallback found: {fallback_files}\n"
                f"Difference (ripgrep - fallback): {ripgrep_files - fallback_files}\n"
                f"Difference (fallback - ripgrep): {fallback_files - ripgrep_files}"
            )

    def test_special_characters_consistency(self, temp_dir_with_files):
        """
        测试这两种方法是否一致地处理文件名中的特殊字符。
        """
        executor = GlobExecutor(temp_dir_with_files)
        action = GlobAction(pattern="*-with-*.py")

        # 从两种方法获取结果
        ripgrep_files, _ = executor._execute_with_ripgrep(
            action.pattern, Path(temp_dir_with_files)
        )
        fallback_files, _ = executor._execute_with_glob(
            action.pattern, Path(temp_dir_with_files)
        )

        # 转换为集合以进行精确比较
        ripgrep_files = set(ripgrep_files)
        fallback_files = set(fallback_files)

        # 两种方法必须返回完全相同的文件
        assert ripgrep_files == fallback_files, (
            f"Ripgrep found: {ripgrep_files}\n"
            f"Fallback found: {fallback_files}\n"
            f"Difference (ripgrep - fallback): {ripgrep_files - fallback_files}\n"
            f"Difference (fallback - ripgrep): {fallback_files - ripgrep_files}"
        )

    def test_case_sensitivity_consistency(self, temp_dir_with_files):
        """测试这两种方法是否一致地处理区分大小写。"""
        executor = GlobExecutor(temp_dir_with_files)
        action = GlobAction(pattern="*.md")

        # 从两种方法获取结果
        ripgrep_files, _ = executor._execute_with_ripgrep(
            action.pattern, Path(temp_dir_with_files)
        )
        fallback_files, _ = executor._execute_with_glob(
            action.pattern, Path(temp_dir_with_files)
        )

        # 转换为集合以进行精确比较
        ripgrep_files = set(ripgrep_files)
        fallback_files = set(fallback_files)

        # 两种方法必须返回完全相同的文件
        assert ripgrep_files == fallback_files, (
            f"Ripgrep found: {ripgrep_files}\n"
            f"Fallback found: {fallback_files}\n"
            f"Difference (ripgrep - fallback): {ripgrep_files - fallback_files}\n"
            f"Difference (fallback - ripgrep): {fallback_files - ripgrep_files}"
        )
