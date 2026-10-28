"""测试 GlobExecutor 实施。"""

import os
import tempfile
import threading
from pathlib import Path

import pytest

from openhands.tools.glob import GlobAction
from openhands.tools.glob.impl import GlobExecutor


def test_glob_executor_initialization():
    """测试 GlobExecutor 初始化是否正确。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        executor = GlobExecutor(working_dir=temp_dir)
        assert executor.working_dir == Path(temp_dir).resolve()


def test_glob_executor_basic_pattern():
    """测试基本的全局模式匹配。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建测试文件
        (Path(temp_dir) / "test1.py").write_text("# Test 1")
        (Path(temp_dir) / "test2.py").write_text("# Test 2")
        (Path(temp_dir) / "readme.md").write_text("# README")

        executor = GlobExecutor(working_dir=temp_dir)
        action = GlobAction(pattern="*.py")
        observation = executor(action)

        assert observation.is_error is False
        assert len(observation.files) == 2
        assert all(f.endswith(".py") for f in observation.files)
        assert observation.pattern == "*.py"
        assert observation.search_path == str(Path(temp_dir).resolve())


def test_glob_executor_recursive_pattern():
    """测试递归 glob 模式。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建嵌套目录结构
        src_dir = Path(temp_dir) / "src"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("# App")

        tests_dir = Path(temp_dir) / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text("# Test")

        executor = GlobExecutor(working_dir=temp_dir)
        action = GlobAction(pattern="**/*.py")
        observation = executor(action)

        assert observation.is_error is False
        assert len(observation.files) == 2
        assert all(f.endswith(".py") for f in observation.files)


def test_glob_executor_custom_path():
    """使用自定义搜索路径测试 glob。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建包含文件的子目录
        sub_dir = Path(temp_dir) / "subdir"
        sub_dir.mkdir()
        (sub_dir / "file1.txt").write_text("Content 1")
        (sub_dir / "file2.txt").write_text("Content 2")

        # 在主目录中创建文件（不应找到）
        (Path(temp_dir) / "main.txt").write_text("Main content")

        executor = GlobExecutor(working_dir=temp_dir)
        action = GlobAction(pattern="*.txt", path=str(sub_dir))
        observation = executor(action)

        assert observation.is_error is False
        assert len(observation.files) == 2
        assert observation.search_path == str(sub_dir.resolve())
        assert all(str(sub_dir.resolve()) in f for f in observation.files)


def test_glob_executor_invalid_path():
    """使用无效的搜索路径测试 glob。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        executor = GlobExecutor(working_dir=temp_dir)
        action = GlobAction(pattern="*.py", path="/nonexistent/path")
        observation = executor(action)

        assert observation.is_error is True
        assert "is not a valid directory" in observation.text
        assert len(observation.files) == 0


def test_glob_executor_no_matches():
    """测试 glob 没有匹配的文件。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建不匹配的文件
        (Path(temp_dir) / "readme.md").write_text("# README")
        (Path(temp_dir) / "config.json").write_text("{}")

        executor = GlobExecutor(working_dir=temp_dir)
        action = GlobAction(pattern="*.py")
        observation = executor(action)

        assert observation.is_error is False
        assert len(observation.files) == 0
        assert not observation.truncated


def test_glob_executor_directories_excluded():
    """测试目录是否从结果中排除。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建目录和文件
        (Path(temp_dir) / "src").mkdir()
        (Path(temp_dir) / "tests").mkdir()
        (Path(temp_dir) / "file.txt").write_text("Content")

        executor = GlobExecutor(working_dir=temp_dir)
        action = GlobAction(pattern="*")
        observation = executor(action)

        assert observation.is_error is False
        # 应该只查找文件，而不是目录
        assert len(observation.files) == 1
        assert observation.files[0].endswith("file.txt")


def test_glob_executor_sorting():
    """测试文件是否按修改时间排序。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建具有不同修改时间的文件
        import time

        file1 = Path(temp_dir) / "file1.txt"
        file1.write_text("First")
        time.sleep(0.1)

        file2 = Path(temp_dir) / "file2.txt"
        file2.write_text("Second")
        time.sleep(0.1)

        file3 = Path(temp_dir) / "file3.txt"
        file3.write_text("Third")

        executor = GlobExecutor(working_dir=temp_dir)
        action = GlobAction(pattern="*.txt")
        observation = executor(action)

        assert observation.is_error is False
        assert len(observation.files) == 3

        # 文件应按修改时间排序（最新的在前） file3 应该在前（最新的）
        #
        assert "file3.txt" in observation.files[0]


def test_glob_executor_truncation():
    """测试结果是否被截断为 100 个文件。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建超过 100 个文件
        for i in range(150):
            (Path(temp_dir) / f"file_{i:03d}.txt").write_text(f"Content {i}")

        executor = GlobExecutor(working_dir=temp_dir)
        action = GlobAction(pattern="*.txt")
        observation = executor(action)

        assert observation.is_error is False
        assert len(observation.files) == 100
        assert observation.truncated is True


def test_glob_executor_complex_patterns():
    """测试复杂的全局模式。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建具有各种扩展名的文件
        files = [
            "config.json",
            "config.yaml",
            "config.yml",
            "config.toml",
            "readme.md",
            "app.py",
        ]

        for file_name in files:
            (Path(temp_dir) / file_name).write_text(f"Content of {file_name}")

        executor = GlobExecutor(working_dir=temp_dir)

        # 测试配置文件的通配符模式
        action = GlobAction(pattern="config.*")
        observation = executor(action)

        assert observation.is_error is False
        assert len(observation.files) == 4  # 所有配置文件
        extensions = {Path(f).suffix for f in observation.files}
        assert extensions == {".json", ".yaml", ".yml", ".toml"}


def test_glob_executor_exception_handling():
    """测试执行器是否优雅地处理异常。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        executor = GlobExecutor(working_dir=temp_dir)

        # 使用可能导致问题的有问题的路径创建操作这测试了执行器中的一般异常处理
        #
        action = GlobAction(pattern="*.py", path=temp_dir)
        observation = executor(action)

        # 即使没有匹配项，也不应该引发异常
        assert observation.is_error is False or isinstance(observation.content, str)
        assert isinstance(observation.files, list)


def test_glob_executor_absolute_paths():
    """测试执行器返回绝对路径。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建测试文件
        (Path(temp_dir) / "test.py").write_text("# Test")

        executor = GlobExecutor(working_dir=temp_dir)
        action = GlobAction(pattern="*.py")
        observation = executor(action)

        assert observation.is_error is False
        assert len(observation.files) == 1

        # 检查返回的路径是否是绝对路径
        file_path = observation.files[0]
        assert Path(file_path).is_absolute()
        assert Path(file_path).exists()


def test_glob_executor_preserves_symlink_paths():
    """测试 Python glob 回退方案是否保留符号链接路径。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        real_dir = Path(temp_dir) / "real"
        real_dir.mkdir()
        target = real_dir / "target.data"
        target.write_text("target")

        link = Path(temp_dir) / "link.txt"
        try:
            link.symlink_to(target)
        except (NotImplementedError, OSError) as exc:
            pytest.skip(f"symlink creation unavailable: {exc}")

        executor = GlobExecutor(working_dir=temp_dir)
        executor._ripgrep_available = False
        action = GlobAction(pattern="*.txt")
        observation = executor(action)

        assert observation.is_error is False
        assert len(observation.files) == 1
        assert Path(observation.files[0]).is_absolute()
        assert Path(observation.files[0]).name == link.name
        assert os.path.islink(observation.files[0])


def test_glob_executor_empty_directory():
    """在空目录中测试 glob。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        executor = GlobExecutor(working_dir=temp_dir)
        action = GlobAction(pattern="*")
        observation = executor(action)

        assert observation.is_error is False
        assert len(observation.files) == 0
        assert not observation.truncated


def test_extract_search_path_from_pattern_absolute_with_recursive():
    """使用绝对路径和 ** 测试 _extract_search_path_from_pattern。"""
    search_path, pattern = GlobExecutor._extract_search_path_from_pattern(
        "/path/to/dir/**/*.py"
    )

    assert search_path == Path("/path/to/dir").resolve()
    assert pattern == "**/*.py"


def test_extract_search_path_from_pattern_absolute_without_recursive():
    """使用绝对路径测试 _extract_search_path_from_pattern，不使用 **。"""
    search_path, pattern = GlobExecutor._extract_search_path_from_pattern(
        "/path/to/dir/*.py"
    )

    assert search_path == Path("/path/to/dir").resolve()
    assert pattern == "*.py"


def test_extract_search_path_from_pattern_relative():
    """使用相对模式测试 _extract_search_path_from_pattern。"""
    search_path, pattern = GlobExecutor._extract_search_path_from_pattern("**/*.py")

    assert search_path is None
    assert pattern == "**/*.py"


def test_extract_search_path_from_pattern_relative_simple():
    """使用简单的相对模式测试 _extract_search_path_from_pattern。"""
    search_path, pattern = GlobExecutor._extract_search_path_from_pattern("*.py")

    assert search_path is None
    assert pattern == "*.py"


def test_extract_search_path_from_pattern_empty():
    """使用空模式测试 _extract_search_path_from_pattern。"""
    search_path, pattern = GlobExecutor._extract_search_path_from_pattern("")

    assert search_path is None
    assert pattern == "**/*"


def test_extract_search_path_from_pattern_home_directory():
    """使用 ~（主目录）测试 _extract_search_path_from_pattern。"""
    home = Path.home()
    search_path, pattern = GlobExecutor._extract_search_path_from_pattern(
        "~/documents/**/*.txt"
    )

    assert search_path == (home / "documents").resolve()
    assert pattern == "**/*.txt"


def test_extract_search_path_from_pattern_root_glob():
    """在根级别使用 glob 测试 _extract_search_path_from_pattern。"""
    search_path, pattern = GlobExecutor._extract_search_path_from_pattern("/*/*.py")

    assert search_path == Path("/").resolve()
    assert pattern == "*/*.py"


def test_extract_search_path_from_pattern_nested_glob():
    """在路径中间使用 glob 测试 _extract_search_path_from_pattern。"""
    search_path, pattern = GlobExecutor._extract_search_path_from_pattern(
        "/path/to/*/subdir/*.py"
    )

    assert search_path == Path("/path/to").resolve()
    assert pattern == "*/subdir/*.py"


def test_extract_search_path_from_pattern_deep_nesting():
    """使用深度嵌套的绝对路径测试 _extract_search_path_from_pattern。"""
    search_path, pattern = GlobExecutor._extract_search_path_from_pattern(
        "/usr/local/lib/python3.13/**/*.so"
    )

    assert search_path == Path("/usr/local/lib/python3.13").resolve()
    assert pattern == "**/*.so"


def test_glob_executor_concurrent_with_ripgrep():
    """测试并发基于 ripgrep 的 glob 调用是否返回正确的结果。

    Ripgrep 生成独立的子进程及其自己的工作目录，因此并发调用本质上是线程安全。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        dir_a = Path(temp_dir) / "dir_a"
        dir_a.mkdir()
        for i in range(5):
            (dir_a / f"alpha_{i}.py").write_text(f"# alpha {i}")

        dir_b = Path(temp_dir) / "dir_b"
        dir_b.mkdir()
        for i in range(5):
            (dir_b / f"beta_{i}.txt").write_text(f"# beta {i}")

        executor = GlobExecutor(working_dir=temp_dir)
        if not executor.is_parallel_safe():
            pytest.skip("ripgrep not installed")

        results: list[tuple[str, list[str]]] = []
        results_lock = threading.Lock()
        errors: list[Exception] = []

        def search_dir(name: str, path: str, pattern: str):
            try:
                action = GlobAction(pattern=pattern, path=path)
                obs = executor(action)
                with results_lock:
                    results.append((name, obs.files))
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(4):
            t_a = threading.Thread(target=search_dir, args=("a", str(dir_a), "*.py"))
            t_b = threading.Thread(target=search_dir, args=("b", str(dir_b), "*.txt"))
            threads.extend([t_a, t_b])

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent glob calls raised errors: {errors}"
        assert len(results) == 8, f"Expected 8 results, got {len(results)}"
        results_a = [files for name, files in results if name == "a"]
        results_b = [files for name, files in results if name == "b"]
        assert len(results_a) == 4
        assert len(results_b) == 4
        assert all(len(files) == 5 for files in results_a)
        assert all(len(files) == 5 for files in results_b)
        assert all(all("alpha_" in Path(f).name for f in files) for files in results_a)
        assert all(all("beta_" in Path(f).name for f in files) for files in results_b)
