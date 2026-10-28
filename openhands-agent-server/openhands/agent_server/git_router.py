"""OpenHands SDK 的 Git 路由器。"""

import asyncio
import functools
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path as PathParam, Query, Request

from openhands.agent_server._secrets_exposure import get_config
from openhands.agent_server.git_provider_service import (
    GitProviderAPIError,
    UnsupportedGitProviderError,
    search_provider_repositories,
)
from openhands.agent_server.server_details_router import update_last_execution_time
from openhands.sdk.git.exceptions import GitError, GitRepositoryError
from openhands.sdk.git.git_changes import get_git_changes
from openhands.sdk.git.git_commits import (
    get_commit_changes,
    get_commit_file_diff,
    get_git_commits,
)
from openhands.sdk.git.git_diff import get_git_diff
from openhands.sdk.git.models import (
    GitChange,
    GitCommitsPage,
    GitDiff,
    GitProviderRepositoryPage,
)
from openhands.sdk.workspace.repo import GitProvider


git_router = APIRouter(prefix="/git", tags=["Git"])
runtime_git_router = APIRouter(prefix="/git", tags=["Git"])
logger = logging.getLogger(__name__)


_REF_QUERY_DESCRIPTION = (
    "Optional git ref to diff against (e.g. 'HEAD' for git status-style "
    "changes, or a commit hash). When omitted, the upstream/default branch "
    "is auto-detected."
)

_COMMIT_QUERY_DESCRIPTION = (
    "Optional commit SHA. When set, the diff is the change that commit "
    "introduced (vs its first parent), read entirely from git objects so "
    "deleted files still render. Mutually exclusive with 'ref'."
)

# 仅十六进制，因此路径/查询值永远无法作为选项到达 git argv （list-args 防止 shell 注入，
# 而不是选项注入）。
#
_SHA_PATTERN = r"^[0-9a-fA-F]{4,64}$"


async def _get_git_changes(path: str, ref: str | None) -> list[GitChange]:
    """用于获取给定路径的 git 更改的内部助手。"""
    update_last_execution_time()
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            None, functools.partial(get_git_changes, Path(path), ref=ref)
        )
    except GitRepositoryError:
        # 非存储库工作区没有要报告的 git 更改； 使用空列表进行响应，以便“更改”选项卡可以
        # 正常呈现而不是 500ing。
        #
        logger.debug("Path %s is not a git repository; returning no changes", path)
        return []


async def _get_git_diff(path: str, ref: str | None) -> GitDiff:
    """用于获取给定路径的 git diff 的内部助手。"""
    update_last_execution_time()
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            None, functools.partial(get_git_diff, Path(path), ref=ref)
        )
    except GitRepositoryError:
        # 仅将非回购案例折叠为空差异； 文件级别 GitPathError（缺失/超大/外部存储库）保持
        #  500，以便调用者可以将其与“无更改”区分开来。
        #
        logger.debug("Path %s is not in a git repository; returning empty diff", path)
        return GitDiff(modified=None, original=None)


async def _get_git_commits(path: str, limit: int) -> GitCommitsPage:
    """用于列出给定存储库路径的提交的内部帮助程序。"""
    update_last_execution_time()
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            None, functools.partial(get_git_commits, Path(path), limit=limit)
        )
    except GitRepositoryError:
        # 非回购工作区没有要报告的提交； 使用空页面进行响应，以便提交部分可以呈现其空状
        # 态。
        #
        logger.debug("Path %s is not a git repository; returning no commits", path)
        return GitCommitsPage(commits=[], has_more=False)


async def _get_commit_changes(path: str, sha: str) -> list[GitChange]:
    """用于通过一次提交更改文件的内部帮助程序。"""
    update_last_execution_time()
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            None, functools.partial(get_commit_changes, Path(path), sha)
        )
    except GitRepositoryError:
        logger.debug("Path %s is not a git repository; returning no changes", path)
        return []


async def _get_commit_file_diff(path: str, commit: str) -> GitDiff:
    """用于获取由一次提交更改的一个文件的差异的内部帮助程序。"""
    update_last_execution_time()
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            None, functools.partial(get_commit_file_diff, Path(path), commit)
        )
    except GitRepositoryError:
        logger.debug("Path %s is not in a git repository; returning empty diff", path)
        return GitDiff(modified=None, original=None)


@git_router.get("/repositories/search", response_model=GitProviderRepositoryPage)
async def git_repositories_search(
    request: Request,
    provider: Annotated[GitProvider, Query(description="Git provider to search")],
    query: Annotated[
        str | None, Query(description="Optional repository name filter")
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=100, description="Maximum repositories to return")
    ] = 100,
    page_id: Annotated[
        str | None, Query(description="Provider-specific page cursor")
    ] = None,
) -> GitProviderRepositoryPage:
    """列出已配置的 git 提供程序可访问的存储库 token。"""
    try:
        return await search_provider_repositories(
            get_config(request),
            provider,
            query=query,
            limit=limit,
            page_id=page_id,
        )
    except UnsupportedGitProviderError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except GitProviderAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e


@git_router.get("/changes")
@runtime_git_router.get("/changes")
async def git_changes_query(
    path: str = Query(..., description="The git repository path"),
    ref: str | None = Query(None, description=_REF_QUERY_DESCRIPTION),
) -> list[GitChange]:
    """使用查询参数获取 git 更改（首选方法）。"""
    try:
        return await _get_git_changes(path, ref)
    except GitError as e:
        # GitRepositoryError 已在助手中处理（返回 []）。 任何剩余的 GitError 子类 (e.g.
        # GitCommandError）显示为 400，以便客户端可以显示可操作的错误，而不是不透明的
        # 500。
        #
        raise HTTPException(status_code=400, detail=str(e))


@git_router.get("/diff")
@runtime_git_router.get("/diff")
async def git_diff_query(
    path: str = Query(..., description="The file path to get diff for"),
    ref: str | None = Query(None, description=_REF_QUERY_DESCRIPTION),
    commit: str | None = Query(
        None, pattern=_SHA_PATTERN, description=_COMMIT_QUERY_DESCRIPTION
    ),
) -> GitDiff:
    """使用查询参数获取 git diff（首选方法）。"""
    if ref is not None and commit is not None:
        raise HTTPException(
            status_code=400, detail="'ref' and 'commit' are mutually exclusive"
        )
    try:
        if commit is not None:
            return await _get_commit_file_diff(path, commit)
        return await _get_git_diff(path, ref)
    except GitError as e:
        # GitRepositoryError 已在辅助函数中处理（返回一个空的差异）。 任何剩余的
        # GitError 子类 (e.g. GitCommandError、GitPathError）显示为 400，以便客户端可以
        # 显示可操作的错误，而不是不透明的 500。
        #
        raise HTTPException(status_code=400, detail=str(e))


@git_router.get("/commits")
@runtime_git_router.get("/commits")
async def git_commits_query(
    path: str = Query(..., description="The git repository path"),
    limit: int = Query(50, ge=1, le=200, description="Maximum commits to return"),
) -> GitCommitsPage:
    """列出存储库的最新提交，最新的在前。"""
    try:
        return await _get_git_commits(path, limit)
    except GitError as e:
        # GitRepositoryError 已在助手中处理（返回空页面）。 任何剩余的 GitError 子类表面
        # 为 400。
        #
        raise HTTPException(status_code=400, detail=str(e))


@git_router.get("/commits/{sha}/changes")
@runtime_git_router.get("/commits/{sha}/changes")
async def git_commit_changes_query(
    sha: str = PathParam(..., pattern=_SHA_PATTERN, description="Commit SHA"),
    path: str = Query(..., description="The git repository path"),
) -> list[GitChange]:
    """获取通过单个提交（相对于其第一个父级）更改的文件。"""
    try:
        return await _get_commit_changes(path, sha)
    except GitError as e:
        # GitRepositoryError 已在助手中处理（返回 []）。 未知/无法解析的煞能提高
        # GitCommandError -> 400。
        #
        raise HTTPException(status_code=400, detail=str(e))
