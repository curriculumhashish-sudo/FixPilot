"""共享平台敏感的测试助手。"""

import os
from collections.abc import Callable
from pathlib import Path

import pytest


def symlink_or_skip(source: Path, link_name: Path) -> None:
    """创建符号链接或在环境缺乏支持时跳过。"""
    try:
        link_name.symlink_to(source, target_is_directory=source.is_dir())
    except OSError as exc:
        pytest.skip(f"symlinks are not available in this environment: {exc}")


def require_case_sensitive_fs(tmp_path: Path) -> None:
    """碰撞测试需要区分大小写的 ``tmp_path`` 来验证
    确定性获胜者； 跳过不会发生冲突的不区分大小写的文件系统。
    """
    probe = tmp_path / "CaseProbe.tmp"
    probe.write_text("x")
    try:
        if (tmp_path / "caseprobe.tmp").exists():
            pytest.skip("filesystem is case-insensitive; case-collision cannot occur")
    finally:
        probe.unlink()


def supports_posix_execute_bits() -> bool:
    """返回当前环境是否具有 POSIX 执行位语义。"""
    return os.name != "nt"


def can_fork_test_process() -> bool:
    """返回 pytest-forked 是否可以安全地隔离当前测试。"""
    return hasattr(os, "fork") and not os.environ.get("PYTEST_XDIST_WORKER")


def maybe_mark_forked[F: Callable[..., object]](test_func: F) -> F:
    """仅当当前工作人员可以使用它时才应用pytest-forked。"""
    if can_fork_test_process():
        return pytest.mark.forked(test_func)
    return test_func


def set_address_space_limit_if_available(memory_limit: int) -> bool:
    """当平台公开 RLIMIT_AS 时应用地址空间限制。"""
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    except Exception:
        return False
    return True
