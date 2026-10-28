"""测试 list_directory 工具。"""

import threading

import pytest

from openhands.sdk.tool.tool import DeclaredResources
from openhands.tools.gemini.list_directory.definition import (
    ListDirectoryAction,
    ListDirectoryObservation,
    ListDirectoryTool,
)
from openhands.tools.gemini.list_directory.impl import ListDirectoryExecutor


def test_list_directory_basic(tmp_path):
    """测试列出目录内容。"""
    # 创建一些文件和目录
    (tmp_path / "file1.txt").write_text("content")
    (tmp_path / "file2.py").write_text("code")
    (tmp_path / "subdir").mkdir()

    executor = ListDirectoryExecutor(workspace_root=str(tmp_path))
    action = ListDirectoryAction(dir_path=".")
    obs = executor(action)

    assert not obs.is_error
    assert obs.total_count == 3
    assert not obs.is_truncated

    # 检查条目
    names = [e.name for e in obs.entries]
    assert "file1.txt" in names
    assert "file2.py" in names
    assert "subdir" in names

    # 检查子目录是否被标记为目录
    subdir_entry = next(e for e in obs.entries if e.name == "subdir")
    assert subdir_entry.is_directory


def test_list_directory_empty(tmp_path):
    """测试列出空目录。"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    executor = ListDirectoryExecutor(workspace_root=str(tmp_path))
    action = ListDirectoryAction(dir_path="empty")
    obs = executor(action)

    assert not obs.is_error
    assert obs.total_count == 0
    assert len(obs.entries) == 0


def test_list_directory_recursive(tmp_path):
    """测试递归目录列表。"""
    # 创建嵌套结构
    (tmp_path / "file1.txt").write_text("content")
    (tmp_path / "subdir1").mkdir()
    (tmp_path / "subdir1" / "file2.txt").write_text("content")
    (tmp_path / "subdir1" / "subdir2").mkdir()
    (tmp_path / "subdir1" / "subdir2" / "file3.txt").write_text("content")

    executor = ListDirectoryExecutor(workspace_root=str(tmp_path))
    action = ListDirectoryAction(dir_path=".", recursive=True)
    obs = executor(action)

    assert not obs.is_error
    # 应包括深度为2的文件和目录。Level 0: . (tmp_path) Level 1: file1.txt, subdir1 Level
    #  2: file2.txt (在 subdir1), subdir2 (在 subdir1) file3.txt 在 level 3 (在 subdir2)
    #  位置，因此不会被包括
    #
    names = [e.name for e in obs.entries]
    assert "file1.txt" in names
    assert "subdir1" in names
    assert "file2.txt" in names
    assert "subdir2" in names
    # file3.txt 处于 3 级，超出了我们的 2 级限制
    assert "file3.txt" not in names


def test_list_directory_not_found(tmp_path):
    """测试列出不存在的目录。"""
    executor = ListDirectoryExecutor(workspace_root=str(tmp_path))
    action = ListDirectoryAction(dir_path="nonexistent")
    obs = executor(action)

    assert obs.is_error
    assert "not found" in obs.text.lower()


def test_list_directory_not_a_directory(tmp_path):
    """测试列出文件而不是目录。"""
    test_file = tmp_path / "file.txt"
    test_file.write_text("content")

    executor = ListDirectoryExecutor(workspace_root=str(tmp_path))
    action = ListDirectoryAction(dir_path="file.txt")
    obs = executor(action)

    assert obs.is_error
    assert "not a directory" in obs.text.lower()


def test_list_directory_file_metadata(tmp_path):
    """测试是否包含文件元数据。"""
    # 创建文件
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")

    executor = ListDirectoryExecutor(workspace_root=str(tmp_path))
    action = ListDirectoryAction(dir_path=".")
    obs = executor(action)

    assert not obs.is_error
    assert len(obs.entries) == 1

    entry = obs.entries[0]
    assert entry.name == "test.txt"
    assert not entry.is_directory
    assert entry.size == 11
    assert entry.modified_time is not None


def test_list_directory_absolute_path(tmp_path):
    """使用绝对路径测试列表。"""
    (tmp_path / "file.txt").write_text("content")

    executor = ListDirectoryExecutor(workspace_root=str(tmp_path))
    action = ListDirectoryAction(dir_path=str(tmp_path))
    obs = executor(action)

    assert not obs.is_error
    assert obs.total_count == 1
    assert obs.entries[0].name == "file.txt"


@pytest.mark.parametrize(
    "dir_path, recursive",
    [
        (".", False),
        ("/some/absolute/path", False),
        (".", True),
        ("relative/path", True),
    ],
    ids=[
        "default-non-recursive",
        "absolute-path-non-recursive",
        "default-recursive",
        "relative-path-recursive",
    ],
)
def test_list_directory_declared_resources(tmp_path, dir_path, recursive):
    """测试 ListDirectoryTool 声明并行安全资源。"""
    executor = ListDirectoryExecutor(workspace_root=str(tmp_path))
    tool = ListDirectoryTool(
        action_type=ListDirectoryAction,
        observation_type=ListDirectoryObservation,
        description="test",
        executor=executor,
    )

    action = ListDirectoryAction(dir_path=dir_path, recursive=recursive)
    resources = tool.declared_resources(action)

    assert isinstance(resources, DeclaredResources)
    assert resources.declared is True
    assert resources.keys == ()


def test_list_directory_executor_concurrent(tmp_path):
    """测试并发 list_directory 调用是否返回正确的结果。

    每个调用都使用独立的只读文件系统操作，因此并发调用本质上是线程安全。
    """
    dir_a = tmp_path / "dir_a"
    dir_a.mkdir()
    for i in range(5):
        (dir_a / f"alpha_{i}.txt").write_text(f"content {i}")

    dir_b = tmp_path / "dir_b"
    dir_b.mkdir()
    for i in range(3):
        (dir_b / f"beta_{i}.py").write_text(f"code {i}")

    executor = ListDirectoryExecutor(workspace_root=str(tmp_path))

    results: list[tuple[str, int]] = []
    results_lock = threading.Lock()
    errors: list[Exception] = []

    def list_dir(name: str, path: str):
        try:
            action = ListDirectoryAction(dir_path=path)
            obs = executor(action)
            with results_lock:
                results.append((name, obs.total_count))
        except Exception as e:
            errors.append(e)

    threads = []
    for _ in range(4):
        t_a = threading.Thread(target=list_dir, args=("a", str(dir_a)))
        t_b = threading.Thread(target=list_dir, args=("b", str(dir_b)))
        threads.extend([t_a, t_b])

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent list_directory calls raised errors: {errors}"
    assert len(results) == 8, f"Expected 8 results, got {len(results)}"
    results_a = [count for name, count in results if name == "a"]
    results_b = [count for name, count in results if name == "b"]
    assert len(results_a) == 4
    assert len(results_b) == 4
    assert all(count == 5 for count in results_a)
    assert all(count == 3 for count in results_b)
