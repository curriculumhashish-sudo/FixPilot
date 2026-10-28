"""用于克隆和缓存远程存储库的 Git 操作。

该模块提供了用于将 git 存储库克隆到本地缓存并保持更新的实用程序。 由技能系统和插件获
取使用。
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from filelock import FileLock, Timeout

from openhands.sdk.git.exceptions import GitCommandError
from openhands.sdk.git.utils import run_git_command
from openhands.sdk.logger import get_logger
from openhands.sdk.utils.redact import (
    redact_url_credentials,
    redact_url_credentials_in_text,
)


logger = get_logger(__name__)

# 默认超时获取缓存锁（秒）与SDK中其他锁超时一致（io/local.py,event_store.py）
#
DEFAULT_LOCK_TIMEOUT = 30

# 匹配完整和缩写的 Git 对象 ID。
_FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_ABBREVIATED_SHA_RE = re.compile(r"^[0-9a-fA-F]{4,39}$")
_HEAD_REF_PREFIX: Final[str] = "refs/heads/"
_TAG_REF_PREFIX: Final[str] = "refs/tags/"
_REMOTE_REF_PREFIX: Final[str] = "refs/remotes/origin/"
_REQUESTED_BRANCH_CONFIG: Final[str] = "openhands.requested-branch"
_SYMBOLIC_DEFAULT_REFS: Final[frozenset[str]] = frozenset(
    {
        "HEAD",
        "refs/heads/HEAD",
        "origin/HEAD",
        "refs/remotes/origin/HEAD",
    }
)


@dataclass(frozen=True)
class _RequestedRef:
    source: str
    cached: str | None
    pinned: bool = False


def _requested_ref_candidates(ref: str) -> tuple[list[_RequestedRef], bool]:
    """返回远程候选者以及 ``ref`` 是否可以是对象 ID。"""
    if _FULL_SHA_RE.fullmatch(ref):
        return [], True
    if ref.startswith(_HEAD_REF_PREFIX):
        branch = ref.removeprefix(_HEAD_REF_PREFIX)
        return [_RequestedRef(ref, f"{_REMOTE_REF_PREFIX}{branch}")], False
    if ref.startswith(_TAG_REF_PREFIX):
        return [_RequestedRef(ref, ref, pinned=True)], False
    if ref.startswith(_REMOTE_REF_PREFIX):
        branch = ref.removeprefix(_REMOTE_REF_PREFIX)
        return [_RequestedRef(f"{_HEAD_REF_PREFIX}{branch}", ref)], False
    if ref.startswith("origin/"):
        branch = ref.removeprefix("origin/")
        return [
            _RequestedRef(
                f"{_HEAD_REF_PREFIX}{branch}",
                f"{_REMOTE_REF_PREFIX}{branch}",
            )
        ], False
    if ref.startswith("refs/"):
        return [_RequestedRef(ref, None)], False

    return [
        _RequestedRef(
            f"{_HEAD_REF_PREFIX}{ref}",
            f"{_REMOTE_REF_PREFIX}{ref}",
        ),
        _RequestedRef(
            f"{_TAG_REF_PREFIX}{ref}",
            f"{_TAG_REF_PREFIX}{ref}",
            pinned=True,
        ),
    ], bool(_ABBREVIATED_SHA_RE.fullmatch(ref))


def _match_ref_pattern(pattern: str, ref: str) -> str | None:
    if "*" not in pattern:
        return "" if pattern == ref else None
    if pattern.count("*") != 1:
        return None

    prefix, suffix = pattern.split("*")
    if not ref.startswith(prefix) or not ref.endswith(suffix):
        return None
    end = len(ref) - len(suffix) if suffix else len(ref)
    if end < len(prefix):
        return None
    return ref[len(prefix) : end]


def _refspec_maps_branch(refspec: str, branch: str) -> bool:
    refspec = refspec.removeprefix("+")
    if refspec.startswith("^"):
        return False

    source_pattern, separator, destination_pattern = refspec.partition(":")
    if not separator:
        return False
    source_ref = f"{_HEAD_REF_PREFIX}{branch}"
    wildcard = _match_ref_pattern(source_pattern, source_ref)
    if wildcard is None:
        return False
    destination = destination_pattern.replace("*", wildcard)
    return destination == f"refs/remotes/origin/{branch}"


def _refspec_excludes_branch(refspec: str, branch: str) -> bool:
    refspec = refspec.removeprefix("+")
    if not refspec.startswith("^"):
        return False
    source_ref = f"{_HEAD_REF_PREFIX}{branch}"
    return _match_ref_pattern(refspec.removeprefix("^"), source_ref) is not None


class GitHelper:
    """git 操作的抽象，使测试变得简单模拟。

    此类包装了用于克隆、获取和管理缓存存储库的 git 命令。 所有方法在失败时都会引发
    GitCommandError。
    """

    def clone(
        self,
        url: str,
        dest: Path,
        depth: int | None = 1,
        branch: str | None = None,
        timeout: int = 120,
    ) -> None:
        """克隆 git 存储库。

        Args:
            url: 使用 Git URL 来克隆。
            dest: 目的地路径。
            depth: 克隆深度（None 表示完整克隆，1 表示浅层克隆）。 请注意
                浅克隆最初仅获取选定的分支尖端。
            branch: 克隆期间要签出的分支/标记。
            timeout: 超时以秒为单位。

        Raises:
            GitCommandError: 如果克隆失败。
        """
        cmd = ["git", "clone"]

        if depth is not None:
            cmd.extend(["--depth", str(depth)])

        if branch:
            cmd.extend(["--branch", branch])

        cmd.extend([url, str(dest)])

        run_git_command(cmd, timeout=timeout)

    def fetch(
        self,
        repo_path: Path,
        remote: str = "origin",
        ref: str | None = None,
        timeout: int = 60,
    ) -> None:
        """从远程获取。

        Args:
            repo_path: 存储库的路径。
            remote: 远程名称。
            ref: 要获取的特定参考（可选）。
            timeout: 超时以秒为单位。

        Raises:
            GitCommandError: 如果抓取失败。
        """
        cmd = ["git", "fetch", remote]
        if ref:
            cmd.append(ref)

        run_git_command(cmd, cwd=repo_path, timeout=timeout)

    def fetch_requested_ref(
        self,
        repo_path: Path,
        ref: str,
        timeout: int = 60,
        *,
        follow_tags: bool = False,
        allow_cached: bool = False,
    ) -> str:
        """获取 ``ref`` 并返回其完整提交 ID。

        仅当远程无法刷新具有匹配本地标识的分支、标记或对象 ID 时，``allow_cached`` 才
        允许回退方案。
        """
        candidates, can_be_object_id = self.validate_requested_ref(
            repo_path, ref, timeout
        )
        if candidates:
            try:
                selected = self._select_remote_ref(repo_path, candidates, timeout)
            except GitCommandError as error:
                if error.exit_code != 2:
                    if allow_cached and (
                        cached_commit := self.resolve_local_requested_ref(
                            repo_path, ref, timeout
                        )
                    ):
                        self._log_cached_ref_fallback(ref, error)
                        return cached_commit
                    raise
                if not can_be_object_id:
                    raise
            else:
                try:
                    self._fetch_selected_ref(
                        repo_path,
                        selected,
                        timeout,
                        follow_tags=follow_tags,
                    )
                except GitCommandError as fetch_error:
                    try:
                        self._select_remote_ref(repo_path, [selected], timeout)
                    except GitCommandError as probe_error:
                        if probe_error.exit_code == 2:
                            raise probe_error from fetch_error
                    if (
                        allow_cached
                        and selected.cached is not None
                        and (
                            cached_commit := self._try_resolve_cached_ref(
                                repo_path, selected.cached, timeout
                            )
                        )
                    ):
                        self._log_cached_ref_fallback(ref, fetch_error)
                        return cached_commit
                    raise fetch_error

                try:
                    commit = self._resolve_commit(repo_path, "FETCH_HEAD", timeout)
                    object_id = self._resolve_object(repo_path, "FETCH_HEAD", timeout)
                except GitCommandError as error:
                    if selected.cached is not None:
                        self._delete_cached_ref(repo_path, selected.cached, timeout)
                    raise GitCommandError(
                        "Remote ref did not resolve to a commit",
                        command=[
                            "git",
                            "fetch",
                            "origin",
                            redact_url_credentials_in_text(selected.source),
                        ],
                        exit_code=2,
                    ) from error

                self._cache_selected_ref(
                    repo_path,
                    selected,
                    object_id,
                    timeout,
                )
                return commit

        if can_be_object_id:
            try:
                return self._fetch_object_id(repo_path, ref, timeout)
            except GitCommandError as error:
                if allow_cached and (
                    cached_commit := self._try_resolve_object_id(
                        repo_path, ref, timeout
                    )
                ):
                    self._log_cached_ref_fallback(ref, error)
                    return cached_commit
                raise

        raise GitCommandError(
            "Git remote did not return the requested ref",
            command=["git", "ls-remote", "origin", redact_url_credentials_in_text(ref)],
            exit_code=2,
        )

    def validate_requested_ref(
        self,
        repo_path: Path,
        ref: str,
        timeout: int = 10,
    ) -> tuple[list[_RequestedRef], bool]:
        """验证 ``ref`` 并返回其标准化候选者。"""
        if ref in _SYMBOLIC_DEFAULT_REFS:
            raise GitCommandError(
                "Symbolic default refs are not supported",
                command=["git", "check-ref-format", ref],
                exit_code=1,
            )

        candidates, can_be_object_id = _requested_ref_candidates(ref)
        if _FULL_SHA_RE.fullmatch(ref):
            return candidates, can_be_object_id

        if ref.startswith("refs/"):
            name = candidates[0].source
            command = ["git", "check-ref-format", name]
        elif ref.startswith("origin/"):
            name = ref.removeprefix("origin/")
            command = ["git", "check-ref-format", "--branch", name]
        else:
            command = ["git", "check-ref-format", "--branch", ref]
        run_git_command(
            command,
            cwd=repo_path,
            timeout=timeout,
            expected_failure=True,
        )
        return candidates, can_be_object_id

    def resolve_local_requested_ref(
        self,
        repo_path: Path,
        ref: str,
        timeout: int = 10,
    ) -> str | None:
        """解析精确的缓存引用而不更改结帐。"""
        candidates, can_be_object_id = self.validate_requested_ref(
            repo_path, ref, timeout
        )
        for candidate in candidates:
            if candidate.cached is None:
                continue
            if resolved := self._try_resolve_cached_ref(
                repo_path, candidate.cached, timeout
            ):
                return resolved
        if can_be_object_id:
            return self._try_resolve_object_id(repo_path, ref, timeout)
        return None

    def requested_ref_is_pinned(
        self,
        repo_path: Path,
        ref: str,
        timeout: int = 10,
    ) -> bool:
        """返回缓存的请求引用是否是标签或对象 ID。"""
        candidates, can_be_object_id = self.validate_requested_ref(
            repo_path, ref, timeout
        )
        for candidate in candidates:
            if candidate.cached is None:
                continue
            if self._try_resolve_cached_ref(repo_path, candidate.cached, timeout):
                return candidate.pinned
        return can_be_object_id and bool(
            self._try_resolve_object_id(repo_path, ref, timeout)
        )

    def checkout_detached(
        self,
        repo_path: Path,
        commit: str,
        timeout: int = 30,
    ) -> None:
        """签出一项已验证的提交，无需创建本地分支。"""
        run_git_command(
            ["git", "checkout", "--force", "--detach", commit],
            cwd=repo_path,
            timeout=timeout,
        )

    def remember_requested_ref(
        self,
        repo_path: Path,
        ref: str,
        commit: str,
        timeout: int = 10,
    ) -> None:
        """存储选定的分支，或清除其他引用的标记。"""
        candidates, _ = self.validate_requested_ref(repo_path, ref, timeout)
        for candidate in candidates:
            if (
                candidate.source.startswith(_HEAD_REF_PREFIX)
                and candidate.cached is not None
                and self._try_resolve_cached_ref(repo_path, candidate.cached, timeout)
                == commit
            ):
                run_git_command(
                    [
                        "git",
                        "config",
                        "--local",
                        _REQUESTED_BRANCH_CONFIG,
                        candidate.source,
                    ],
                    cwd=repo_path,
                    timeout=timeout,
                )
                return
        self.clear_requested_branch(repo_path, timeout)

    def get_requested_branch(
        self,
        repo_path: Path,
        timeout: int = 10,
    ) -> str | None:
        """返回最后一个显式引用请求选择的分支。"""
        try:
            return run_git_command(
                ["git", "config", "--get", _REQUESTED_BRANCH_CONFIG],
                cwd=repo_path,
                timeout=timeout,
                expected_failure=True,
            )
        except GitCommandError as error:
            if error.exit_code != 1:
                raise
            return None

    def clear_requested_branch(
        self,
        repo_path: Path,
        timeout: int = 10,
    ) -> None:
        """清除用于无引用更新的分支。"""
        if self.get_requested_branch(repo_path, timeout) is None:
            return
        run_git_command(
            ["git", "config", "--local", "--unset-all", _REQUESTED_BRANCH_CONFIG],
            cwd=repo_path,
            timeout=timeout,
        )

    def _select_remote_ref(
        self,
        repo_path: Path,
        candidates: list[_RequestedRef],
        timeout: int,
    ) -> _RequestedRef:
        command = [
            "git",
            "ls-remote",
            "--exit-code",
            "--refs",
            "origin",
            *(candidate.source for candidate in candidates),
        ]
        try:
            output = run_git_command(
                command,
                cwd=repo_path,
                timeout=timeout,
                expected_failure=True,
            )
        except GitCommandError as error:
            if error.exit_code == 2:
                for candidate in candidates:
                    if candidate.cached is not None:
                        self._delete_cached_ref(repo_path, candidate.cached, timeout)
            raise

        available = {
            line.split("\t", 1)[1] for line in output.splitlines() if "\t" in line
        }
        for candidate in candidates:
            if candidate.cached is not None and candidate.source not in available:
                self._delete_cached_ref(repo_path, candidate.cached, timeout)
        for candidate in candidates:
            if candidate.source in available:
                return candidate

        safe_command = [redact_url_credentials_in_text(part) for part in command]
        raise GitCommandError(
            "Git remote did not return the requested ref",
            command=safe_command,
            exit_code=2,
        )

    def _fetch_selected_ref(
        self,
        repo_path: Path,
        selected: _RequestedRef,
        timeout: int,
        *,
        follow_tags: bool,
    ) -> None:
        command = ["git", "fetch"]
        if not follow_tags:
            command.append("--no-tags")
        if self._is_shallow(repo_path, timeout):
            command.extend(["--depth", "1"])
        if follow_tags and selected.cached is not None:
            if self._is_symbolic_ref(repo_path, selected.cached, timeout):
                self._delete_cached_ref(repo_path, selected.cached, timeout)
            refspec = f"+{selected.source}:{selected.cached}"
        else:
            refspec = selected.source
        command.extend(["origin", refspec])
        run_git_command(
            command,
            cwd=repo_path,
            timeout=timeout,
            expected_failure=True,
        )

    def _cache_selected_ref(
        self,
        repo_path: Path,
        selected: _RequestedRef,
        object_id: str,
        timeout: int,
    ) -> None:
        """缓存经过验证的分支或标签。"""
        if selected.cached is not None:
            run_git_command(
                ["git", "update-ref", "--no-deref", selected.cached, object_id],
                cwd=repo_path,
                timeout=timeout,
            )

    def _log_cached_ref_fallback(
        self,
        ref: str,
        error: GitCommandError,
    ) -> None:
        safe_ref = redact_url_credentials_in_text(ref)
        logger.warning(
            f"Could not refresh requested ref {safe_ref}: {error}. "
            "Using the matching cached ref."
        )

    def _fetch_object_id(
        self,
        repo_path: Path,
        ref: str,
        timeout: int,
    ) -> str:
        command = ["git", "fetch", "--no-tags"]
        if self._is_shallow(repo_path, timeout):
            command.extend(["--depth", "1"])
        command.extend(["origin", ref])
        try:
            run_git_command(
                command,
                cwd=repo_path,
                timeout=timeout,
                expected_failure=True,
            )
        except GitCommandError as fetch_error:
            if fetch_error.exit_code == -1:
                raise
            self.fetch(repo_path, timeout=timeout)
            resolved = self._try_resolve_object_id(repo_path, ref, timeout)
            if resolved is None:
                self._fetch_all_remote_history(repo_path, timeout)
                resolved = self._try_resolve_object_id(repo_path, ref, timeout)
            if resolved is None:
                raise GitCommandError(
                    "Fetched object does not match the requested ID",
                    command=["git", "fetch", "origin", ref],
                    exit_code=1,
                ) from fetch_error
            return resolved

        resolved = self._resolve_commit(repo_path, "FETCH_HEAD", timeout)
        if not resolved.casefold().startswith(ref.casefold()):
            raise GitCommandError(
                "Fetched object does not match the requested ID",
                command=["git", "fetch", "origin", ref],
                exit_code=1,
            )
        return resolved

    def _fetch_all_remote_history(self, repo_path: Path, timeout: int) -> None:
        """获取所有远程分支和标签历史记录。"""
        command = ["git", "fetch"]
        if self._is_shallow(repo_path, timeout):
            command.append("--unshallow")
        command.extend(
            [
                "origin",
                f"+{_HEAD_REF_PREFIX}*:{_REMOTE_REF_PREFIX}*",
                f"+{_TAG_REF_PREFIX}*:{_TAG_REF_PREFIX}*",
            ]
        )
        run_git_command(
            command,
            cwd=repo_path,
            timeout=timeout,
            expected_failure=True,
        )

    def _resolve_commit(
        self,
        repo_path: Path,
        ref: str,
        timeout: int,
    ) -> str:
        return run_git_command(
            [
                "git",
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{ref}^{{commit}}",
            ],
            cwd=repo_path,
            timeout=timeout,
            expected_failure=True,
        )

    def _resolve_object(
        self,
        repo_path: Path,
        ref: str,
        timeout: int,
    ) -> str:
        return run_git_command(
            ["git", "rev-parse", "--verify", "--end-of-options", ref],
            cwd=repo_path,
            timeout=timeout,
            expected_failure=True,
        )

    def _try_resolve_commit(
        self,
        repo_path: Path,
        ref: str,
        timeout: int,
    ) -> str | None:
        try:
            return self._resolve_commit(repo_path, ref, timeout)
        except GitCommandError as error:
            if error.exit_code == -1:
                raise
            return None

    def _try_resolve_cached_ref(
        self,
        repo_path: Path,
        ref: str,
        timeout: int,
    ) -> str | None:
        """仅当缓存身份是直接引用时才解析它。"""
        if self._is_symbolic_ref(repo_path, ref, timeout):
            return None
        return self._try_resolve_commit(repo_path, ref, timeout)

    def _is_symbolic_ref(
        self,
        repo_path: Path,
        ref: str,
        timeout: int,
    ) -> bool:
        try:
            run_git_command(
                ["git", "symbolic-ref", "-q", ref],
                cwd=repo_path,
                timeout=timeout,
                expected_failure=True,
            )
        except GitCommandError as error:
            if error.exit_code != 1:
                raise
            return False
        return True

    def _try_resolve_object_id(
        self,
        repo_path: Path,
        ref: str,
        timeout: int,
    ) -> str | None:
        """仅当提交与其对象 ID 前缀匹配时才解析 ``ref``。"""
        commit = self._try_resolve_commit(repo_path, ref, timeout)
        if commit is None or not commit.casefold().startswith(ref.casefold()):
            return None
        return commit

    def _is_shallow(self, repo_path: Path, timeout: int) -> bool:
        return (
            run_git_command(
                ["git", "rev-parse", "--is-shallow-repository"],
                cwd=repo_path,
                timeout=timeout,
            )
            == "true"
        )

    def _delete_cached_ref(
        self,
        repo_path: Path,
        ref: str,
        timeout: int,
    ) -> None:
        run_git_command(
            ["git", "update-ref", "--no-deref", "-d", ref],
            cwd=repo_path,
            timeout=timeout,
        )

    def needs_explicit_branch_fetch(
        self,
        repo_path: Path,
        branch: str,
        timeout: int = 10,
    ) -> bool:
        """返回分支是否既未映射也未显式排除。"""
        try:
            configured = run_git_command(
                ["git", "config", "--get-all", "remote.origin.fetch"],
                cwd=repo_path,
                timeout=timeout,
                expected_failure=True,
            )
        except GitCommandError as e:
            if e.exit_code == -1:
                raise
            return True

        refspecs = configured.splitlines()
        if any(_refspec_excludes_branch(refspec, branch) for refspec in refspecs):
            return False
        return not any(_refspec_maps_branch(refspec, branch) for refspec in refspecs)

    def checkout(
        self,
        repo_path: Path,
        ref: str,
        timeout: int = 30,
    ) -> None:
        """签出引用（分支、标签或提交）。

        Args:
            repo_path: 存储库的路径。
            ref: 分支、标记或提交结帐。
            timeout: 超时以秒为单位。

        Raises:
            GitCommandError: 如果结帐失败。
        """
        run_git_command(["git", "checkout", ref], cwd=repo_path, timeout=timeout)

    def reset_hard(self, repo_path: Path, ref: str, timeout: int = 30) -> None:
        """硬重置为参考。

        Args:
            repo_path: 存储库的路径。
            ref: 参考重置为 (e.g., "origin/main")。
            timeout: 超时以秒为单位。

        Raises:
            GitCommandError: 如果重置失败。
        """
        run_git_command(["git", "reset", "--hard", ref], cwd=repo_path, timeout=timeout)

    def get_current_branch(self, repo_path: Path, timeout: int = 10) -> str | None:
        """获取当前分支名称。

        Args:
            repo_path: 存储库的路径。
            timeout: 超时以秒为单位。

        Returns:
            分支名称，如果处于分离 HEAD 状态，则为 None。

        Raises:
            GitCommandError: 如果命令失败。
        """
        branch = run_git_command(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            timeout=timeout,
        )
        # “HEAD”表示分离HEAD状态
        return None if branch == "HEAD" else branch

    def get_default_branch(self, repo_path: Path, timeout: int = 10) -> str | None:
        """从远程获取默认分支名称。

        查询 origin/HEAD 以确定远程的默认分支。 这是在克隆期间设置的，并指向默认情况
        下检出的分支。

        Args:
            repo_path: 存储库的路径。
            timeout: 超时以秒为单位。

        Returns:
            默认分支名称（e.g.、“main”或“master”），如果无法确定则为 None（e.g.、未设
            置 origin/HEAD）。

        Raises:
            GitCommandError: 如果 git 命令本身失败（如果缺少 ref 则不会）。
        """
        try:
            # origin/HEAD 是指向默认分支的符号引用
            ref = run_git_command(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                cwd=repo_path,
                timeout=timeout,
            )
            # 输出类似于“refs/remotes/origin/main” - 提取分支名称
            prefix = "refs/remotes/origin/"
            if ref.startswith(prefix):
                return ref[len(prefix) :]
            return None
        except GitCommandError:
            # origin/HEAD 可能未设置（e.g.、裸克隆或从未配置）
            return None

    def get_head_commit(self, repo_path: Path, timeout: int = 10) -> str:
        """获取当前的 HEAD 提交 SHA。

        Args:
            repo_path: 存储库的路径。
            timeout: 超时以秒为单位。

        Returns:
            HEAD 的完整 40 个字符提交 SHA。

        Raises:
            GitCommandError: 如果命令失败。
        """
        return run_git_command(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            timeout=timeout,
        )


def try_cached_clone_or_update(
    url: str,
    repo_path: Path,
    ref: str | None = None,
    update: bool = True,
    git_helper: GitHelper | None = None,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
    strict: bool = False,
) -> Path | None:
    """克隆或更新缓存目录中的 git 存储库。

    这是缓存存储库操作的主要入口。

    行为：
        - 如果存储库不存在：克隆浅层，然后解析可选的引用
        - 如果存储库存在且 update=True：获取并解析可选引用
        - 如果存储库存在并且 update=False with ref：解析缓存的分支、标签或对象 ID
        - 如果存储库存在并且 update=False 没有引用：按原样使用

    请求的引用必须解析为 Git 内容。 确认丢失的远程引用失败。 当 ``strict`` 为 False
    时，不可用的远程可以使用精确匹配的缓存分支、标签或对象 I
    D。

    并发：
        使用基于文件的锁定来防止竞态条件多个进程访问同一缓存目录。 锁文件是在存储库目
        录 (repo_path.lock) 附近创建的。

    Args:
        url: 使用 Git URL 来克隆。
        repo_path: 应缓存存储库的路径。
        ref: 分支、标记或提交结帐。 如果 None，则更新所选的
            分支或恢复到默认分支。
        update: 如果 True 和 repo 存在，则获取并更新它。 如果 False，则跳过获取。
        git_helper: GitHelper git 操作实例。 如果 None，则创建一个。
        lock_timeout: 超时以秒为单位获取锁。 默认值为 30
            秒。
        strict: 如果 True，失败的请求-ref刷新或没有-ref的获取返回
            None 而不是使用缓存的引用。 已解析的完整对象 ID 无需刷新。 确认丢失的请求
            引用总是失败。 尽力重置和默认分支恢复保持宽松。

    Returns:
        如果成功，则为本地存储库的路径；如果失败，则为 None。 在 git 错误上返回 None
        （而不是引发）以允许正常降级。
    """
    git = git_helper if git_helper is not None else GitHelper()

    # 确保存储库和锁文件的父目录都存在
    repo_path.parent.mkdir(parents=True, exist_ok=True)

    # 使用与 repo 目录相邻的锁文件
    lock_path = repo_path.with_suffix(".lock")
    lock = FileLock(lock_path)

    try:
        with lock.acquire(timeout=lock_timeout):
            return _do_clone_or_update(
                url,
                repo_path,
                ref,
                update,
                git,
                strict=strict,
            )
    except Timeout:
        logger.warning(
            f"Timed out waiting for lock on {repo_path} after {lock_timeout}s"
        )
        return None
    except GitCommandError as e:
        logger.warning(f"Git operation failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error managing repository: {str(e)}")
        return None


def _do_clone_or_update(
    url: str,
    repo_path: Path,
    ref: str | None,
    update: bool,
    git: GitHelper,
    strict: bool = False,
) -> Path:
    """执行实际的克隆或更新操作（在按住锁时调用）。

    Args:
        url: 使用 Git URL 来克隆。
        repo_path: 应缓存存储库的路径。
        ref: 分支、标记或提交结帐。
        update: 是否更新现有的存储库。
        git: GitHelper 实例。
        strict: 是否引发失败的请求引用刷新或无引用获取。

    Returns:
        存储库的路径。

    Raises:
        GitCommandError: 如果 git 操作失败。
    """
    if repo_path.exists() and (repo_path / ".git").exists():
        if ref:
            _resolve_and_checkout_requested_ref(
                repo_path,
                ref,
                git,
                update=update,
                strict=strict,
            )
        elif update:
            logger.debug(f"Updating repository at {repo_path}")
            _update_repository(repo_path, git, strict=strict)
        else:
            logger.debug(f"Using cached repository at {repo_path}")
    else:
        logger.info(f"Cloning repository from {redact_url_credentials(url)}")
        _clone_repository(url, repo_path, git)
        if ref:
            _resolve_and_checkout_requested_ref(
                repo_path,
                ref,
                git,
                update=True,
                strict=strict,
            )

    return repo_path


def _clone_repository(
    url: str,
    dest: Path,
    git: GitHelper,
) -> None:
    """克隆 git 存储库。

    Args:
        url: 使用 Git URL 来克隆。
        dest: 目的地路径。
        git: GitHelper 实例。
    """
    # 删除现有目录（如果存在但不是有效的 git 存储库）
    if dest.exists():
        shutil.rmtree(dest)

    git.clone(url, dest, depth=1, branch=None)
    logger.debug(f"Repository cloned to {dest}")


def _update_repository(
    repo_path: Path,
    git: GitHelper,
    strict: bool = False,
) -> None:
    """更新缓存的存储库，而无需新请求的引用。

    按场景划分的行为：
        1. 由较早的显式请求选择的分支保持选中状态。
        2. 在本地分支上：获取配置的引用，如果需要补充当前分支，然后重置为其原始引用。
        3. 在其他分离的 HEAD 状态：获取，然后签出并重置默认分支。

    Args:
        repo_path: 存储库的路径。
        git: GitHelper 实例。
        strict: 如果为 True，则失败的提取将引发 ``GitCommandError`` 而不是
            保持缓存。
    """
    requested_branch = git.get_requested_branch(repo_path)
    if requested_branch is not None:
        try:
            _resolve_and_checkout_requested_ref(
                repo_path,
                requested_branch,
                git,
                update=True,
                strict=strict,
                follow_tags=True,
            )
        except GitCommandError as error:
            if strict:
                raise
            if error.exit_code != 2:
                logger.warning(
                    f"Failed to update requested branch: {error}. "
                    "Using the cached version."
                )
                return
            git.clear_requested_branch(repo_path)
        else:
            return

    if strict:
        git.fetch(repo_path)
    elif not _try_fetch(repo_path, git):
        return
    current_branch = git.get_current_branch(repo_path)

    if current_branch:
        branch_ref = f"{_HEAD_REF_PREFIX}{current_branch}"
        if git.needs_explicit_branch_fetch(repo_path, current_branch):
            if strict:
                git.fetch_requested_ref(repo_path, branch_ref, follow_tags=True)
            elif not _try_fetch_requested_ref(
                repo_path,
                branch_ref,
                git,
                follow_tags=True,
            ):
                return
        _try_reset_to_origin(repo_path, current_branch, git)
        return

    # 分离HEAD：通过检查默认分支来恢复
    _recover_from_detached_head(repo_path, git)


def _try_fetch(repo_path: Path, git: GitHelper) -> bool:
    """尝试从原点获取。 成功时返回 True，失败时返回 False。"""
    try:
        git.fetch(repo_path)
        return True
    except GitCommandError as e:
        logger.warning(f"Failed to fetch updates: {e}. Using cached version.")
        return False


def _try_fetch_requested_ref(
    repo_path: Path,
    ref: str,
    git: GitHelper,
    *,
    follow_tags: bool = False,
) -> bool:
    """获取一个请求的引用，并返回获取是否成功。"""
    try:
        git.fetch_requested_ref(repo_path, ref, follow_tags=follow_tags)
        return True
    except GitCommandError as e:
        safe_ref = redact_url_credentials_in_text(ref)
        logger.warning(
            f"Failed to fetch requested ref {safe_ref}: {e}. Using cached version."
        )
        return False


def _resolve_and_checkout_requested_ref(
    repo_path: Path,
    ref: str,
    git: GitHelper,
    *,
    update: bool,
    strict: bool,
    follow_tags: bool = False,
) -> None:
    """解析一个请求的引用，然后检查其确切的提交。"""
    safe_ref = redact_url_credentials_in_text(ref)
    if not update:
        cached_commit = git.resolve_local_requested_ref(repo_path, ref)
        if cached_commit is None:
            raise GitCommandError(
                "Requested ref is not available in the cache",
                command=["git", "rev-parse", safe_ref],
                exit_code=1,
            )
        git.checkout_detached(repo_path, cached_commit)
        git.remember_requested_ref(repo_path, ref, cached_commit)
        return

    if _FULL_SHA_RE.fullmatch(ref):
        cached_commit = git.resolve_local_requested_ref(repo_path, ref)
        if cached_commit is not None:
            git.checkout_detached(repo_path, cached_commit)
            git.remember_requested_ref(repo_path, ref, cached_commit)
            return

    commit = git.fetch_requested_ref(
        repo_path,
        ref,
        follow_tags=follow_tags,
        allow_cached=not strict,
    )

    git.checkout_detached(repo_path, commit)
    git.remember_requested_ref(repo_path, ref, commit)


def _try_reset_to_origin(repo_path: Path, branch: str, git: GitHelper) -> None:
    """尝试重置到 origin/{branch}。 记录失败警告。"""
    try:
        git.reset_hard(repo_path, f"origin/{branch}")
        logger.debug("Repository updated successfully")
    except GitCommandError as e:
        logger.warning(
            f"Failed to reset to origin/{branch}: {e}. Using cached version."
        )


def _recover_from_detached_head(repo_path: Path, git: GitHelper) -> None:
    """从默认分支提交处的分离 HEAD 状态恢复。

    这处理以下情况：
    1. 用户之前获取了显式非分支引用 -> 分离 HEAD
    2. 用户现在使用 update=True 获取，但没有引用 -> 期望“最新”

    如果没有这种恢复，回购协议将停留在旧的参考上。 解析远程跟踪引用可以避免将远程控制
    名称传递给结账。
    """
    default_branch = git.get_default_branch(repo_path)

    if not default_branch:
        logger.warning(
            "Repository is in detached HEAD state and default branch could not be "
            "determined. Specify a ref explicitly to update, or the cached version "
            "will be used as-is."
        )
        return

    default_ref = f"{_REMOTE_REF_PREFIX}{default_branch}"
    commit = git.resolve_local_requested_ref(repo_path, default_ref)
    if commit is None:
        logger.warning(
            "Repository is in detached HEAD state and the default branch commit "
            "could not be resolved. The cached version will be used as-is."
        )
        return

    try:
        git.checkout_detached(repo_path, commit)
        logger.debug("Repository updated to the default branch commit")
    except GitCommandError as e:
        logger.warning(
            f"Failed to checkout the default branch commit: {e}. Using cached version."
        )
