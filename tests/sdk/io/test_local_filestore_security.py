"""测试 LocalFileStore 路径遍历安全性。"""

import os
import tempfile

import pytest

from openhands.sdk.io.local import LocalFileStore


def test_path_traversal_attacks_blocked():
    """测试各种路径遍历攻击是否被正确阻止。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        root_dir = os.path.join(temp_dir, "filestore_root")
        store = LocalFileStore(root_dir)

        # 在根目录之外创建敏感文件
        sensitive_file = os.path.join(temp_dir, "sensitive.txt")
        with open(sensitive_file, "w") as f:
            f.write("SENSITIVE DATA")

        # 测试各种路径遍历攻击向量
        attack_vectors = [
            "../sensitive.txt",
            "../../sensitive.txt",
            "../../../etc/passwd",
            "subdir/../../../sensitive.txt",
            "..\\sensitive.txt",  # Windows风格
            "subdir/../../sensitive.txt",
            "./../sensitive.txt",
            "a/../../../sensitive.txt",
        ]

        for attack_path in attack_vectors:
            with pytest.raises(ValueError, match="path escapes filestore root"):
                store.get_full_path(attack_path)


def test_legitimate_paths_allowed():
    """测试是否允许根目录内的合法路径。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        root_dir = os.path.join(temp_dir, "filestore_root")
        store = LocalFileStore(root_dir)

        legitimate_paths = [
            "file.txt",
            "subdir/file.txt",
            "deep/nested/path/file.txt",
            "file_with_dots.txt",
            ".hidden_file",
            "subdir/.hidden",
        ]

        for legit_path in legitimate_paths:
            full_path = store.get_full_path(legit_path)
            # 验证路径是否在根目录内
            assert full_path.startswith(root_dir)
            assert os.path.commonpath([root_dir, full_path]) == root_dir


def test_edge_cases():
    """测试边缘情况，例如空路径和根路径。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        root_dir = os.path.join(temp_dir, "filestore_root")
        store = LocalFileStore(root_dir)

        # 测试空路径
        full_path = store.get_full_path("")
        assert full_path == root_dir

        # 测试根路径
        full_path = store.get_full_path("/")
        assert full_path == root_dir

        # 测试当前目录
        full_path = store.get_full_path(".")
        assert full_path == root_dir


def test_root_normalization():
    """测试根路径在初始化期间是否已正确规范化。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 使用波形符扩展进行测试
        if os.path.expanduser("~") != "~":
            store = LocalFileStore("~/test_root")
            assert not store.root.startswith("~")

        # 使用相对路径测试
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            store = LocalFileStore("./relative_root")
            assert os.path.isabs(store.root)

            # 防止某些mac环境下测试出错
            if store.root.startswith("/private/") and not temp_dir.startswith(
                "/private/"
            ):
                temp_dir = f"/private{temp_dir}"

            assert store.root.startswith(temp_dir)
        finally:
            os.chdir(original_cwd)


def test_file_operations_with_security():
    """通过安全修复测试文件操作是否正常工作。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        root_dir = os.path.join(temp_dir, "filestore_root")
        store = LocalFileStore(root_dir)

        # 测试写入和读取合法文件
        test_content = "Hello, World!"
        store.write("test.txt", test_content)
        assert store.read("test.txt") == test_content

        # 测试我们不能在root之外写入
        with pytest.raises(ValueError, match="path escapes filestore root"):
            store.write("../outside.txt", "malicious content")

        # 测试我们无法读取root之外的内容
        with pytest.raises(ValueError, match="path escapes filestore root"):
            store.read("../outside.txt")
