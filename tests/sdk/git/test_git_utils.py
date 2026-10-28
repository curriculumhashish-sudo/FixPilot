"""测试 git utils base-ref 分辨率 (``get_valid_ref``)。"""

import subprocess
import tempfile
from pathlib import Path

from openhands.sdk.git.utils import GIT_EMPTY_TREE_HASH, get_valid_ref


def run_bash_command(command: str, cwd: str) -> subprocess.CompletedProcess:
    """在指定目录下运行bash命令。"""
    return subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_get_valid_ref_purposes_diverge_for_committed_no_remote_repo():
    """显示目的解析 HEAD 为已提交的存储库，但没有
    远程（因此 Diff 视图获取 git-status 语义），而默认值
    export purpose keeps resolving the empty tree — workspace-export patches
    必须保持可从新克隆重建，因此显示策略不得泄漏到其中。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排 — 一个有提交但没有远程的存储库。
        run_bash_command("git init -b main", temp_dir)
        run_bash_command("git config user.name 'Test User'", temp_dir)
        run_bash_command("git config user.email 'test@example.com'", temp_dir)
        (Path(temp_dir) / "a.txt").write_text("a")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'base'", temp_dir)
        head_sha = run_bash_command("git rev-parse HEAD", temp_dir).stdout.strip()

        # 法案
        export_ref = get_valid_ref(temp_dir)
        display_ref = get_valid_ref(temp_dir, purpose="display")

        # 断言
        assert export_ref == GIT_EMPTY_TREE_HASH
        assert display_ref == head_sha
