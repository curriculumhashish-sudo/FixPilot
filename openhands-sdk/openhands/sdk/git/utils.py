import logging
import re
import shlex
import subprocess
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from openhands.sdk.git.exceptions import GitCommandError, GitRepositoryError
from openhands.sdk.utils.redact import (
    redact_url_credentials as redact_url_credentials,
    redact_url_credentials_in_text,
    redact_url_params,
)


logger = logging.getLogger(__name__)

# Git 空树哈希 - 这是 git 中众所周知的常量，表示空树对象的哈希
#
GIT_EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _run_git_subprocess(
    args: list[str],
    cwd: str | Path | None,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    """使用所有 git 调用者所需的捕获/解码设置运行子进程。"""
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
        timeout=timeout,
    )


def _run_git_probe(args: list[str], cwd: str | Path) -> str:
    try:
        result = _run_git_subprocess(["git", "--no-pager", *args], cwd, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def get_git_repository_metadata(repo_dir: str | Path) -> dict[str, str]:
    """返回尽力而为的存储库身份元数据。"""
    metadata: dict[str, str] = {}
    remote = _run_git_probe(["remote", "get-url", "origin"], repo_dir)
    if remote:
        metadata["repo_remote"] = redact_url_params(
            redact_url_credentials_in_text(remote)
        )

    head_and_branch = _run_git_probe(
        ["rev-parse", "HEAD", "--abbrev-ref", "HEAD"], repo_dir
    )
    lines = head_and_branch.splitlines()
    if len(lines) == 2:
        head, branch = lines
        metadata["head_commit"] = head
        metadata["branch"] = "DETACHED" if branch == "HEAD" else branch
    return metadata


def run_git_command(
    args: list[str],
    cwd: str | Path | None = None,
    timeout: int = 30,
    *,
    expected_failure: bool = False,
    strip: bool = True,
) -> str:
    """安全地运行 git 命令，没有 shell 注入漏洞。

    Args:
        args: 命令参数列表 (e.g., ['git', 'status', '--porcelain'])
        cwd: 工作目录运行命令（对于克隆等命令是可选的）
        timeout: 超时以秒为单位（默认值：30）
        expected_failure: 当调用者在调试级别记录非零退出
            有意探测回退方案条件。
        strip: 从输出中去除前导和尾随空格。 通行证
            ``False`` 读取文件内容 (e.g. ``git show rev:path``）逐字记录。

    Returns:
        命令输出为字符串

    Raises:
        GitCommandError: 如果 git 命令失败
    """
    redacted_args = [redact_url_credentials_in_text(a) for a in args]
    cmd_str = shlex.join(redacted_args)

    try:
        result = _run_git_subprocess(args, cwd, timeout)

        if result.returncode != 0:
            error_msg = f"Git command failed: {cmd_str}"
            # stderr 可以回显远程 URL（在某些设备上嵌入凭据
            # git versions / error paths), so redact before logging and storing.
            redacted_stderr = redact_url_credentials_in_text(result.stderr)
            log = logger.debug if expected_failure else logger.error
            log(
                f"{error_msg}. Exit code: {result.returncode}. "
                f"Stderr: {redacted_stderr}"
            )
            raise GitCommandError(
                message=error_msg,
                command=redacted_args,
                exit_code=result.returncode,
                stderr=redacted_stderr.strip(),
            )

        logger.debug(f"Git command succeeded: {cmd_str}")
        return result.stdout.strip() if strip else result.stdout

    except subprocess.TimeoutExpired as e:
        error_msg = f"Git command timed out: {cmd_str}"
        logger.error(error_msg)
        raise GitCommandError(
            message=error_msg,
            command=redacted_args,
            exit_code=-1,
            stderr="Command timed out",
        ) from e
    except FileNotFoundError as e:
        error_msg = "Git command not found. Is git installed?"
        logger.error(error_msg)
        raise GitCommandError(
            message=error_msg,
            command=redacted_args,
            exit_code=-1,
            stderr="Git executable not found",
        ) from e


def _repo_has_commits(repo_dir: str | Path) -> bool:
    """检查 git 存储库是否有任何提交。

    使用“git rev-list --count --all”，它会为空存储库返回“0”而不会失败，从而避免出现预
    期条件的 ERROR 日志。

    Args:
        repo_dir: git 存储库的路径

    Returns:
        True 如果存储库至少有一次提交，False 否则
    """
    try:
        count = run_git_command(
            ["git", "--no-pager", "rev-list", "--count", "--all"], repo_dir
        )
        return count.strip() != "0"
    except GitCommandError:
        logger.debug("Could not check commit count")
        return False


def _rev_parse(repo_dir: str | Path, ref: str) -> str | None:
    """将 ``ref`` 解析为提交 SHA，如果未解析，则解析为 None。"""
    try:
        result = run_git_command(
            ["git", "--no-pager", "rev-parse", "--verify", ref],
            repo_dir,
            expected_failure=True,
        )
        return result or None
    except GitCommandError:
        return None


def _merge_base(repo_dir: str | Path, ref_a: str, ref_b: str) -> str | None:
    """返回两个引用的合并基数，如果无法计算则返回 None
    (e.g. 不相关的历史，浅克隆）。"""
    try:
        result = run_git_command(
            ["git", "--no-pager", "merge-base", ref_a, ref_b],
            repo_dir,
            expected_failure=True,
        )
        return result or None
    except GitCommandError:
        return None


def _get_current_branch(repo_dir: str | Path) -> str | None:
    """返回当前分支名称，或在分离/未诞生时返回 None。"""
    try:
        branch = run_git_command(
            ["git", "--no-pager", "rev-parse", "--abbrev-ref", "HEAD"],
            repo_dir,
            expected_failure=True,
        )
        if branch and branch != "HEAD":
            return branch
    except GitCommandError:
        logger.debug("Could not get current branch name")
    return None


def _get_remote_default_branch(repo_dir: str | Path) -> str | None:
    """查找 origin 的默认分支名称 (e.g. ``main``).

    更喜欢本地 ``origin/HEAD`` symref（在克隆上记录 - 无网络）； 对于未记录
    ``origin/HEAD`` 的情况下添加的遥控器，回退到
    ``git remote show origin``（网络调用）。
    """
    try:
        symref = run_git_command(
            ["git", "--no-pager", "rev-parse", "--abbrev-ref", "origin/HEAD"],
            repo_dir,
            expected_failure=True,
        )
        prefix = "origin/"
        if symref.startswith(prefix) and len(symref) > len(prefix):
            return symref[len(prefix) :]
    except GitCommandError:
        logger.debug("origin/HEAD not set; falling back to `git remote show`")

    try:
        remote_info = run_git_command(
            ["git", "--no-pager", "remote", "show", "origin"], repo_dir
        )
        for line in remote_info.splitlines():
            if "HEAD branch:" in line:
                default_branch = line.split(":")[-1].strip()
                if default_branch and default_branch != "(unknown)":
                    return default_branch
                break
    except GitCommandError:
        logger.debug("Could not get remote information")
    return None


def _has_tracked_changes(repo_dir: str | Path) -> bool:
    """True 当工作树或索引不同于 HEAD 时。

    未跟踪的文件被故意排除：它们永远不会出现在
    ``git diff <ref>`` 输出（它们通过
    ``ls-files --others``），因此它们不得影响基本选择 - 杂散的临时文件不得重新隐藏完
    全推送的分支的差异。
    """
    try:
        status = run_git_command(
            ["git", "--no-pager", "status", "--porcelain", "--untracked-files=no"],
            repo_dir,
        )
        return bool(status.strip())
    except GitCommandError:
        # 故障安全：视为脏，因此分支不断与其自己的上游进行比较，而不是显示不相关的历史记
        # 录。
        #
        return True


def _get_display_base_ref(repo_dir: str | Path) -> str:
    """自动检测*显示*对话更改内容的基本引用。

    与导出算法（必须只选择可以从新鲜克隆中重建的基因为基础的）不同， 工作区- 脚本的输
    出会被重播到其他地方），这会选择最佳答案“这里发生了什么”——包括已经提交和甚至
    推送的工作。 候选人按顺序：

    1. ``origin/<current-branch>`` — 但当 * 指向 HEAD 时跳过 *
       while the tracked working tree is clean: comparing a fully-pushed
       针对其自己的上游的分支会呈现一个空的差异，并会隐藏该分支的（PR's）工作。 脏树
       保留了这个候选，因此预先存在的附加分支仅显示新的编辑而不是整个分支历史记录。
    2. ``merge-base(HEAD, origin/<default>)`` — 分叉点。 优先于默认提示，因此分叉后落
    在默认分支上的提交不会呈现为反向噪声。
    3. ``origin/<default>`` — 当合并基础不可用时 (e.g. 浅克隆）。
    4. 没有可用的起源： ``merge-base(HEAD, local main|master)``只有当分支不是当前分支
    ，并且是其祖先时， HEAD — 没有远
    程的工作树 shape (``openhands/<uuid>`` forked off local ``main``), 保持已提交的工
    作可见。
    5. ``HEAD`` — git 状态样式。 特别是，这可以防止非远程存储库落入空树，空树会将每个
    跟踪的文件作为添加项列出。

    调用者已经处理过没有提交的仓库，所以这只会回退到空树，对于一个未出生或孤儿的HEAD
    （与显式-``HEAD``-override行为一致：未跟踪的文件显示为添加）。
    """
    head_sha = _rev_parse(repo_dir, "HEAD")
    current_branch = _get_current_branch(repo_dir)

    if current_branch is not None:
        upstream_ref = f"origin/{current_branch}"
        upstream_sha = _rev_parse(repo_dir, upstream_ref)
        if upstream_sha is not None:
            if upstream_sha == head_sha and not _has_tracked_changes(repo_dir):
                logger.debug(
                    f"{upstream_ref} points at HEAD with a clean tree; "
                    "skipping it so committed work stays visible"
                )
            else:
                logger.debug(f"Using upstream of current branch: {upstream_ref}")
                return upstream_sha

    default_branch = _get_remote_default_branch(repo_dir)
    if default_branch is not None:
        merge_base = _merge_base(repo_dir, "HEAD", f"origin/{default_branch}")
        if merge_base is not None:
            logger.debug(f"Using merge base with origin/{default_branch}")
            return merge_base
        default_sha = _rev_parse(repo_dir, f"origin/{default_branch}")
        if default_sha is not None:
            logger.debug(f"Using default branch tip: origin/{default_branch}")
            return default_sha
    else:
        for local_default in ("main", "master"):
            local_default_sha = _rev_parse(repo_dir, local_default)
            if local_default_sha is not None:
                if local_default != current_branch:
                    merge_base = _merge_base(repo_dir, "HEAD", local_default)
                    if merge_base is not None and merge_base == local_default_sha:
                        logger.debug(f"Using local default branch: {local_default}")
                        return merge_base
                break

    if head_sha is not None:
        logger.debug("Using HEAD as display base (git status-style diff)")
        return head_sha
    logger.debug(f"Using empty tree reference: {GIT_EMPTY_TREE_HASH}")
    return GIT_EMPTY_TREE_HASH


def get_valid_ref(
    repo_dir: str | Path,
    override: str | None = None,
    *,
    purpose: Literal["export", "display"] = "export",
) -> str | None:
    """获取有效的 git 参考来进行比较。

    如果提供了``override``，则通过``git rev-parse --verify``解析并返回。 这允许调用者
    请求，例如 ``HEAD`` 以获取
    ``git status`` 风格的差异针对最新的提交，而不是针对远程分支。

    的 ``"HEAD"`` 重写时会特别处理：如果它没有解决（当前分支上没有提交记录） e.g. 新
    鲜的 ``git init``'d 工作区，或者一个不在仓库中的孤
    本分支（它在其他地方有提交记录），我们回退到空树哈希，让调用者看到未跟踪的文件作
    为添加，而不是一个不可见的哈希 ``rev-parse --verify`` 失败。
     其他未解决的重写仍然引发 ``GitCommandError`` 所以是一个错拼的分支SHA 没有被默默
     吞没。

    否则，根据 ``purpose`` 自动检测参考。 对于
    ``purpose="export"``（默认），尝试多种策略：
    1. 当前分支的起源 (e.g., origin/main)
    2. 默认分支（e.g.、origin/main、origin/master）
    3. 将基础分支与默认分支合并
    4. 空树（用于新存储库）

    Args:
        repo_dir: git 存储库的路径
        override: 可选的显式引用 (e.g. ``"HEAD"`` 或提交哈希）到
            使用而不是自动检测的比较参考。
        purpose: ref 的用途是什么。 ``"export"``（默认）仅选择
            可从新克隆重建的碱基 - 工作区导出/恢复所需，其补丁在其他地方重播。
            ``"display"`` 优化显示对话的工作（参见
            :func:`_get_display_base_ref`): 它跳过完全推送的分支
            自身上游，偏好分支点而非默认分支的顶端，并且在没有可用的上游时，降级为
            ``HEAD``（git status风格），而不是空树。

    Returns:
        有效的 git 引用哈希，如果没有找到有效的引用则为 None

    Raises:
        GitCommandError: 如果提供了非 ``"HEAD"`` ``override`` 且
            没有解决。
    """
    if override is not None:
        try:
            # 解决调用者的显式覆盖和表面故障，以便“未找到引用”和“无更改”之间的差异保持可
            # 见。
            #
            return run_git_command(
                [
                    "git",
                    "--no-pager",
                    "rev-parse",
                    "--verify",
                    f"{override}^{{commit}}",
                ],
                repo_dir,
                expected_failure=override == "HEAD",
            )
        except GitCommandError:
            # ``HEAD`` 当前分支的主干分支指针。 如果没有解决，则当前分支还没有提交。 这
            # 发生在新鲜的 ``git init``'d 工作区  *和* 对于拥有其他分支提交记录的仓库中
            # 的孤儿分支（所以 ``_repo_has_commits`` 单独无法捕获后者）。 将两者视为空树
            # 比较，以便更改标签显示工作树添加而不是向上冒泡的透明内容
            # ``rev-parse --verify`` 失败的 GUI.
            #
            # 对于非``HEAD``的覆盖（显式分支/SHAs调用者要求的），保持严格的模式，以免拼
            # 写错误悄无声息地变成“没有变化”。
            #
            if override == "HEAD":
                logger.debug(
                    "Override 'HEAD' did not resolve in %s; using empty tree",
                    repo_dir,
                )
                return GIT_EMPTY_TREE_HASH
            raise

    # 首先检查 repo 是否有任何提交。 空存储库（使用 git init 创建）不会有提交或远程，因
    # 此我们可以直接跳到空树回退方案。
    #
    if not _repo_has_commits(repo_dir):
        logger.debug("Repository has no commits yet, using empty tree reference")
        return GIT_EMPTY_TREE_HASH

    if purpose == "display":
        return _get_display_base_ref(repo_dir)

    refs_to_try = []

    # 尝试当前分支的起源
    try:
        current_branch = run_git_command(
            ["git", "--no-pager", "rev-parse", "--abbrev-ref", "HEAD"],
            repo_dir,
            expected_failure=True,
        )
        if current_branch and current_branch != "HEAD":  # 不处于分离HEAD状态
            refs_to_try.append(f"origin/{current_branch}")
            logger.debug(f"Added current branch reference: origin/{current_branch}")
    except GitCommandError:
        logger.debug("Could not get current branch name")

    # 尝试从远程获取默认分支
    try:
        remote_info = run_git_command(
            ["git", "--no-pager", "remote", "show", "origin"], repo_dir
        )
        for line in remote_info.splitlines():
            if "HEAD branch:" in line:
                default_branch = line.split(":")[-1].strip()
                if default_branch:
                    refs_to_try.append(f"origin/{default_branch}")
                    logger.debug(
                        f"Added default branch reference: origin/{default_branch}"
                    )

                    # 还可以尝试将基础分支与默认分支合并
                    try:
                        merge_base = run_git_command(
                            [
                                "git",
                                "--no-pager",
                                "merge-base",
                                "HEAD",
                                f"origin/{default_branch}",
                            ],
                            repo_dir,
                            expected_failure=True,
                        )
                        if merge_base:
                            refs_to_try.append(merge_base)
                            logger.debug(f"Added merge base reference: {merge_base}")
                    except GitCommandError:
                        logger.debug("Could not get merge base")
                break
    except GitCommandError:
        logger.debug("Could not get remote information")

    # 找到第一个有效的参考
    for ref in refs_to_try:
        try:
            result = run_git_command(
                ["git", "--no-pager", "rev-parse", "--verify", ref],
                repo_dir,
                expected_failure=True,
            )
            if result:
                logger.debug(f"Using valid reference: {ref} -> {result}")
                return result
        except GitCommandError:
            logger.debug(f"Reference not valid: {ref}")
            continue

    # 回退方案为空树哈希（始终有效，无需验证）
    logger.debug(f"Using empty tree reference: {GIT_EMPTY_TREE_HASH}")
    return GIT_EMPTY_TREE_HASH


def validate_git_repository(repo_dir: str | Path) -> Path:
    """验证给定目录是 git 存储库。

    Args:
        repo_dir: 检查路径

    Returns:
        验证路径对象

    Raises:
        GitRepositoryError: 如果不是有效的 git 存储库
    """
    repo_path = Path(repo_dir).resolve()

    if not repo_path.exists():
        raise GitRepositoryError(f"Directory does not exist: {repo_path}")

    if not repo_path.is_dir():
        raise GitRepositoryError(f"Path is not a directory: {repo_path}")

    try:
        run_git_command(["git", "rev-parse", "--git-dir"], repo_path)
    except GitCommandError as e:
        raise GitRepositoryError(f"Not a git repository: {repo_path}") from e

    return repo_path


# ============================================================================
# Git URL 实用程序
# ============================================================================


def is_git_url(source: str) -> bool:
    """检查源字符串是否类似于 git URL。

    检测 Git URLs 通过协议/方案，而不是列举提供者。 这处理任何 Git 仓储服务GitHub,
    GitLab, Codeberg, self-hosted,
     etc.)

    Args:
        source: 要检查的字符串。

    Returns:
        如果字符串看起来是 git URL，则为 True，否则为 False。

    Examples:
        >>> is_git_url("https://github.com/owner/repo.git")
        True
        >>> is_git_url("git@github.com:owner/repo.git")
        True
        >>> is_git_url("/local/path")
        False
    """
    # HTTPS/HTTP URLs 到 Git 仓库
    if source.startswith(("https://", "http://")):
        return True

    # SSH 格式：git@host:path 或 user@host:path
    if re.match(r"^[\w.-]+@[\w.-]+:", source):
        return True

    # Git协议
    if source.startswith("git://"):
        return True

    # 文件协议（用于测试）
    if source.startswith("file://"):
        return True

    return False


def normalize_git_url(url: str) -> str:
    """规范化 git URL 确保具有 .git 后缀的 HTTPS  URLs.

    Azure DevOps克隆 URLs（包含 ``/_git/`` 的路径）没有后缀，因为 Azure DevOps 解析
    ``<repo>.git`` 为不同的仓
    库。

    Args:
        url: Git URL 进行标准化。

    Returns:
        URL 以 .git 后缀命名，HTTPS/HTTP 除外，Azure URLs DevOps ``/_git/`` URLs 只去
        掉尾部斜杠。

    Examples:
        >>> normalize_git_url("https://github.com/owner/repo")
        " https://github.com/owner/repo.git"
        >>> normalize_git_url("https://github.com/owner/repo.git")
        " https://github.com/owner/repo.git"
        >>> normalize_git_url("git@github.com:owner/repo.git")
        “git@github.com：所有者/repo.git”
        >>> normalize_git_url("https://dev.azure.com/org/project/_git/repo")
        " https://dev.azure.com/org/project/_git/repo"
    """
    if url.startswith(("https://", "http://")) and not url.endswith(".git"):
        url = url.rstrip("/")
        # Azure DevOps 将 ``<repo>.git`` 解析为不同的、缺失的存储库。
        if "/_git/" in urlparse(url).path:
            return url
        url = f"{url}.git"
    return url


def extract_repo_name(source: str) -> str:
    """从 git URL 或路径中提取人类可读的存储库名称。

    提取最后一个路径组件（存储库名称）并对其进行清理以用于目录名称或显示目的。

    Args:
        source: Git URL 或本地路径字符串。

    Returns:
        适合在目录名称中使用的经过清理的名称（最多 32 个字符）。

    Examples:
        >>> extract_repo_name("https://github.com/owner/my-repo.git")
        “我的仓库”
        >>> extract_repo_name("git@github.com:owner/my-repo.git")
        “我的仓库”
        >>> extract_repo_name("/path/to/local-repo")
        “本地仓库”
    """
    # 去掉公共前缀以到达路径部分
    name = source
    for prefix in ("github:", "https://", "http://", "git://", "file://"):
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break

    # 句柄SSH格式：user@host:path -> path
    if "@" in name and ":" in name and "/" not in name.split(":")[0]:
        name = name.split(":", 1)[1]

    # 删除.git后缀并获取最后一个路径组件
    name = name.rstrip("/").removesuffix(".git")
    name = name.rsplit("/", 1)[-1]

    # 清理：仅保留字母数字、破折号、下划线
    name = re.sub(r"[^a-zA-Z0-9_-]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")

    return name[:32] if name else "repo"
