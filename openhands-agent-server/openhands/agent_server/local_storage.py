"""主机本地对话的存储：他们的 git 工作树。"""

import subprocess
from pathlib import Path

from openhands.agent_server.utils import safe_rmtree
from openhands.sdk.logger import get_logger
from openhands.sdk.utils.command import sanitized_env


logger = get_logger(__name__)


def conversation_worktree_dir(root: Path, working_dir: str) -> Path | None:
    """``root`` 下的目录包含工作区的工作树（如果有）。

    并不总是 ``root/<id>``：分叉共享其源的工作区。
    """
    try:
        rel = Path(working_dir).resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return root / rel.parts[0] if rel.parts else None


def remove_conversation_worktree(conversation_dir: Path) -> None:
    """删除对话目录中的工作树； 他们的枝条留下来。"""
    if conversation_dir.is_symlink() or not conversation_dir.is_dir():
        return
    repos = [
        repo for worktree in _worktrees(conversation_dir) if (repo := _repo(worktree))
    ]
    if not safe_rmtree(conversation_dir, f"conversation worktrees {conversation_dir}"):
        return
    # 删除 git 丢失的工作树记录； 分支未受影响。
    for repo in repos:
        _git(repo, "worktree", "prune")


def _worktrees(conversation_dir: Path) -> list[Path]:
    # A 工作树的 .git 是指向主存储库的文件。
    return [
        child
        for child in conversation_dir.iterdir()
        if not child.is_symlink() and (child / ".git").is_file()
    ]


def _repo(worktree: Path) -> Path | None:
    common = _git(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(common) if common else None


def _git(cwd: Path, *args: str) -> str | None:
    result = subprocess.run(
        # 存储库的配置是智能体-可写； fsmonitor 会运行它。
        [
            "git",
            "--no-optional-locks",
            "-c",
            "core.fsmonitor=false",
            "-C",
            str(cwd),
            *args,
        ],
        env=sanitized_env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        logger.warning("git %s failed in %s: %s", " ".join(args), cwd, result.stderr)
        return None
    return result.stdout.strip()
