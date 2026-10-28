import asyncio
import contextlib
import fnmatch
import io
import json
import os
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import IO, Annotated, Any, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from openhands.agent_server._secret_redaction import (
    redacted_json_bytes,
    should_redact,
)
from openhands.agent_server.config import Config
from openhands.agent_server.models import FileUploadResult, Success
from openhands.agent_server.server_details_router import update_last_execution_time
from openhands.sdk.git.exceptions import GitCommandError, GitRepositoryError
from openhands.sdk.git.utils import (
    GIT_EMPTY_TREE_HASH,
    get_git_repository_metadata,
    get_valid_ref,
    run_git_command,
    validate_git_repository,
)
from openhands.sdk.logger import get_logger
from openhands.sdk.utils.files import is_temp_file


class SubdirectoryEntry(BaseModel):
    name: str
    path: str


class SubdirectoryPage(BaseModel):
    items: list[SubdirectoryEntry]
    next_page_id: str | None = None


class FileBrowserEntry(BaseModel):
    label: str
    path: str


class HomeResponse(BaseModel):
    home: str
    favorites: list[FileBrowserEntry] = []
    locations: list[FileBrowserEntry] = []


logger = get_logger(__name__)
file_router = APIRouter(prefix="/file", tags=["Files"])
file_discovery_router = APIRouter(prefix="/file", tags=["Files"])
_FILE_DOWNLOAD_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {
            # 现有路由通告此媒体类型。 运行时别名丢弃它。
            "application/json": {"schema": {}},
            "application/octet-stream": {
                "schema": {"type": "string", "format": "binary"}
            },
        }
    }
}


async def _upload_file(path: str, file: UploadFile) -> FileUploadResult:
    """用于将文件上传到工作区的内部助手。"""
    update_last_execution_time()
    logger.info(f"Uploading file: {path}")
    try:
        target_path = Path(path)
        if not target_path.is_absolute():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path must be absolute",
            )

        # 确保目标目录存在
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # 将文件流式传输到磁盘以避免大文件的内存问题。 卸载写入工作进程线程，因此缓慢的
        # 存储（NFS、FUSE、加密的 FS）无法在上传期间使事件循环饥饿。
        #
        file_size = 0
        with open(target_path, "wb") as f:
            while chunk := await file.read(8192):  # 读取 8KB 块
                await asyncio.to_thread(f.write, chunk)
                file_size += len(chunk)

        logger.info(f"Uploaded file to {target_path}")
        return FileUploadResult(file_size=file_size)

    except HTTPException:
        raise
    except IsADirectoryError:
        # 目标本身是一个现有目录：调用者的路径错误，而不是服务器故障（create_directory
        # 同样回答 400）。
        #
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is a directory",
        )
    except (FileExistsError, NotADirectoryError):
        # 当直接父级是文件时，mkdir(parents=True) 引发 FileExistsError；当更上一层的组件
        # 是文件时，NotADirectoryError 引发。
        #
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A parent of the path is not a directory",
        )
    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}",
        )


async def _download_file(path: str) -> FileResponse:
    """从工作区下载文件的内部助手。"""
    update_last_execution_time()
    logger.info(f"Downloading file: {path}")
    try:
        target_path = Path(path)
        if not target_path.is_absolute():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path must be absolute",
            )

        if not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
            )

        if not target_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Path is not a file"
            )

        return FileResponse(
            path=target_path,
            filename=target_path.name,
            media_type="application/octet-stream",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download file: {str(e)}",
        )


_TRAJECTORY_EXCLUDED_TOP_DIRS = frozenset({"acp"})


def _create_zip_from_directory(source_dir: Path, output_path: Path) -> None:
    """使用 Python 标准库 APIs 创建 source_dir 的 zip 压缩文件。

    已持久化 JSON 载荷中携带机密的字段（LLM/AWS 凭据）会在写入归档时进行已脱敏，确保
    下载的轨迹不会泄漏 API 密钥；参见
    ``redacted_json_bytes``。 顶级目录位于
    ``_TRAJECTORY_EXCLUDED_TOP_DIRS`` 保留运行时间凭据，并且被省略。

    这段对话可能仍在运行并保存状态，因此正在写入的文件（``*.tmp``）会被跳过，以及在列
    出和读取之间消失的条目。 每个 JSON 文件都会读取一次，因此检查机密的
    字节是存档的字节。
    """
    try:
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(source_dir, source_dir.name)
            for path in sorted(source_dir.rglob("*")):
                if path.relative_to(source_dir).parts[0] in (
                    _TRAJECTORY_EXCLUDED_TOP_DIRS
                ):
                    continue
                if is_temp_file(path):
                    # 正在进行的保存（或因崩溃而留下），来自 atomic_write_text 或租约的
                    # owner_lease.tmp； 它所替换的文件已存档。
                    #
                    continue
                arcname = str(path.relative_to(source_dir.parent))
                # rglob 列出后，跳过条目被删除或重命名。
                with contextlib.suppress(FileNotFoundError):
                    if should_redact(path) and path.is_file():
                        zinfo = zipfile.ZipInfo.from_file(path, arcname)
                        data = path.read_bytes()
                        redacted = redacted_json_bytes(data, path)
                        archive.writestr(
                            zinfo,
                            data if redacted is None else redacted,
                            compress_type=zipfile.ZIP_DEFLATED,
                        )
                    else:
                        archive.write(path, arcname)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise


ArchiveFormat = Literal["git-delta", "tar.gz"]

_ARCHIVE_SUFFIX: dict[str, str] = {
    "git-delta": ".patch",
    "tar.gz": ".tar.gz",
}

_ARCHIVE_MEDIA_TYPE: dict[str, str] = {
    "git-delta": "text/x-patch",
    "tar.gz": "application/gzip",
}

ARCHIVE_MANIFEST_NAME = "archive_manifest.json"


# 繁重/生成的目录通常会使存档膨胀，而不会帮助评估重放。 这些是默认排除，而不是最小排除集
# ：当调用者需要完整的工作区捕获时，可以使用 ``use_default_excludes=false`` 禁用它们。
# 两种格式都应用相同的集合：git-delta as
# ``:(exclude)`` 路径规格（删除已跟踪的 * 和 * 未跟踪的副本，再加上仓库本身的 .gitignore
# ）以及 tar.gz 通过修剪走道来实现——因此这两个归档捕获了相同的文件。
#
_DEFAULT_ARCHIVE_EXCLUDES = (
    ".git/",
    "node_modules/",
    ".venv/",
    "venv/",
    "__pycache__/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    "dist/",
    "build/",
    ".next/",
    "target/",
    "*.pyc",
)

# 凭据-轴承 git 内部结构必须绝不是已持久化到共享存档存储桶，即使是完整捕获 (
# ``use_default_excludes=false``)。 标记化克隆 (
# ``https://x-access-token:TOKEN@github.com/...``) 将 token 保留在 ``.git/config`` 和
# ``.git/FETCH_HEAD`` 中； 引用日志和保存的凭据同样敏感。 这些位于 ``.git`` AND
# ``.git/modules/<name>`` 下的子模块中，因此匹配是在任何 ``.git`` 目录中，而不是固定在顶
# 级路径。 (git-delta 是工作目录的差异，从不包括 ``.git``，所以这只对 tar.gz 有影响。)
#
_SENSITIVE_GIT_INTERNALS = frozenset(
    {"config", "config.worktree", "credentials", ".git-credentials", "FETCH_HEAD"}
)


def _is_sensitive_git_internal(rel: PurePosixPath) -> bool:
    """True 如果 ``rel`` 是任何 ``.git`` 目录中包含凭据的文件。

    涵盖任意深度的超级项目 (``.git/...``) 和子模块 (``.git/modules/<name>/...``)：敏
    感的配置/凭证文件以及
    ``logs/`` 子树下的每个引用日志。
    """
    parts = rel.parts
    for i, part in enumerate(parts):
        if part == ".git":
            internal = parts[i + 1 :]
            if not internal:
                return False
            if "logs" in internal:
                return True
            return internal[-1] in _SENSITIVE_GIT_INTERNALS
    return False


# 在工作区路径下的仓库根目录下的目录名从不值得向下递归：它们可能合法地包含 vendored/
# nested git 仓库，这些仓库必须不能被误认为是工作区的仓库。
#
_ARCHIVE_DESCENT_SKIP = frozenset({"node_modules", "venv", "site-packages", "vendor"})


def _resolve_git_repo_root(target: Path, max_depth: int = 3) -> Path:
    """将 git 工作树解析为存档在 ``target`` 下。

    调用者传递工作区基数 (e.g. ``/workspace/project``），但基于仓库的对话会克隆到子目
    录（
    ``{base}/[{group}/]{repo_name}``），因此基目录本身通常*不是* Git 仓库。
    ``git rev-parse`` 只向上搜索，因此
    即使仓库位于其下方一层或两层，也400 —— 完全无声地捕获了不存在于档案中用于支持档案
    的仓库对话。

    如果 ``target`` 已经是 git 工作树，则将其原样返回。 否则，对它的后代进行有界深度
    优先搜索（跳过隐藏和 vendored 目录，并在找到后不进入仓库
    ），以查找 git 工作树根。 如果恰好有一个，则返回唯一匹配； 如果找到零个或多个，则
    返回 ``target`` 不变，以便应用现有的 not-a-git-rep
    o 处理 (HTTP 400) 而不是猜测。
    """
    if (target / ".git").exists():
        return target
    found: list[Path] = []
    frontier: list[tuple[Path, int]] = [(target, 0)]
    while frontier:
        current, depth = frontier.pop()
        if depth >= max_depth:
            continue
        try:
            children = sorted(current.iterdir())
        except OSError:
            continue
        for child in children:
            if child.name.startswith(".") or child.name in _ARCHIVE_DESCENT_SKIP:
                continue
            try:
                if child.is_symlink() or not child.is_dir():
                    continue
            except OSError:
                continue
            if (child / ".git").exists():
                found.append(child)
                if len(found) > 1:
                    # 不明确——不要猜测要存档哪个存储库。
                    logger.warning(
                        f"Multiple git repos under {target}; cannot pick one to "
                        "archive — using the path as given. Caller should pass "
                        "the repo path explicitly."
                    )
                    return target
            else:
                frontier.append((child, depth + 1))
    return found[0] if len(found) == 1 else target


def _excludes_to_git_pathspecs(excludes: list[str]) -> list[str]:
    """将存档排除项翻译为 git ``:(exclude)`` 路径规范。

    使用 pathspecs 而不是 ``core.excludesFile`` 会删除排除的路径，无论它们是跟踪还是
    未跟踪，因此 git-delta 和 tar.gz
     捕获相同的文件集。 ``glob`` 魔法阻止 ``*`` 通过 ``/``，同时 ``**`` 跨越目录，镜
     像 tar.gz 匹配器的 gitignore 语义
    ：裸名在任何深度都匹配。 多段模式锚定在存储库根上。

    ``/`` 通常表示一个只包含目录的模式：我们只输出(``.../**``)的内容，不输出(不)的裸
    文件名，因此，如果一个文件的名称(e.g)与它共享，那么它将不会
    被处理。 一个字面上命名的创作文件
    ``build``) 被保留 — 匹配 ``_path_is_excluded`` 的仅目录剥离。 发出裸条目也会从
    git-delta 中默默地删除这些文件，而
    tar.gz 会保留它们。
    """
    specs: list[str] = []
    for raw in excludes:
        dir_only = raw.endswith("/")
        pat = raw.rstrip("/")
        if not pat:
            continue
        if "/" in pat:
            if not dir_only:
                specs.append(f":(glob,exclude){pat}")
            specs.append(f":(glob,exclude){pat}/**")
        else:
            if not dir_only:
                specs.append(f":(glob,exclude)**/{pat}")
            specs.append(f":(glob,exclude)**/{pat}/**")
    return specs


def _head_is_detached(root: Path) -> bool:
    """True 如果 ``root`` 处的存储库具有分离的 HEAD（没有当前分支）。"""
    try:
        branch = run_git_command(
            ["git", "--no-pager", "rev-parse", "--abbrev-ref", "HEAD"], root
        )
    except GitCommandError:
        return False
    return branch.strip() == "HEAD"


def _header_safe(value: str) -> str:
    """对标头值进行百分比编码。"""
    return quote(value, safe="")


def _create_git_delta(
    root: Path, base_ref: str | None, output_path: Path, excludes: list[str]
) -> str:
    """编写一个 git 补丁，捕获针对基础的工作树增量。

    Delta 包含了相对于 ``base_ref``（默认为自动检测的比较分支 —— 源分支、合并基、或空
    树，对于一个新仓库）的跟踪修改、新（未跟踪）文件，以及删除。
     使用一次性索引（``GIT_INDEX_FILE``），因此存储库的真实索引永远不会被触及。
     ``excludes`` 应用在 ``:(exclude)`` 路径
    规格上，``.gitignore`` 仓库自己的，所以排除的路径无论是否被跟踪，都会被丢弃，符合
     tar.gz 格式。 当调用者有意想要更全面的捕获时，可以禁用默认
    排除。

    返回补丁所应用的完整基础提交 SHA，或者当基础是空树（新存储库）或无法解析为提交时
    返回“”。
    """
    validate_git_repository(root)
    effective_base = base_ref
    if effective_base is None and _head_is_detached(root):
        # 固定的基础提交签出 (e.g. SWE-bench-style eval 设置）使 HEAD 分离；
        # get_valid_ref 然后跳过分支策略并与远程默认分支 TIP 进行比较，用 base..tip 污染
        # 补丁。 固定的 HEAD 提交是正确的基础，因此请求它。
        #
        effective_base = "HEAD"
    try:
        ref = get_valid_ref(root, effective_base) or GIT_EMPTY_TREE_HASH
    except GitCommandError as e:
        # 无法解析的显式 base_ref 是客户端错误，而不是服务器故障； 将其显示出来，以便调
        # 用者得到 4xx。
        #
        raise ValueError(f"base_ref {base_ref!r} could not be resolved") from e
    index_path = output_path.with_name(output_path.name + ".index")
    pathspecs = _excludes_to_git_pathspecs(excludes)
    env = {**os.environ, "GIT_INDEX_FILE": str(index_path)}
    try:
        # 从基本引用中播种临时索引，将工作树放置在其顶部（跳过请求的排除），然后进行比较
        # 。 ``-- .`` 路径规范范围暂存和差异到请求的目录，所以
        # ``path`` 是较大存储库的子目录，仅生成该子树的增量，而不是整个存储库的增量。
        #
        subprocess.run(
            ["git", "read-tree", ref],
            cwd=root,
            env=env,
            capture_output=True,
            check=True,
            timeout=60,
        )
        subprocess.run(
            ["git", "add", "-A", "--", ".", *pathspecs],
            cwd=root,
            env=env,
            capture_output=True,
            check=True,
            timeout=300,
        )
        # 将 diff 直接流式传输到磁盘，因此大型二进制补丁永远不会在内存中缓冲（OOM 在胖工
        # 作区上暂停/停止的风险）。
        #
        with open(output_path, "wb") as out:
            subprocess.run(
                ["git", "diff", "--binary", "--cached", ref, "--", ".", *pathspecs],
                cwd=root,
                env=env,
                stdout=out,
                stderr=subprocess.PIPE,
                check=True,
                timeout=300,
            )
    except subprocess.CalledProcessError as e:
        output_path.unlink(missing_ok=True)
        stderr = e.stderr.decode("utf-8", "replace") if e.stderr else ""
        raise GitCommandError(
            message="Failed to generate git delta",
            command=e.cmd if isinstance(e.cmd, list) else [str(e.cmd)],
            exit_code=e.returncode,
            stderr=stderr.strip(),
        ) from e
    except subprocess.TimeoutExpired as e:
        output_path.unlink(missing_ok=True)
        raise GitCommandError(
            message="Timed out generating git delta",
            command=e.cmd if isinstance(e.cmd, list) else [str(e.cmd)],
            exit_code=-1,
            stderr=f"timed out after {e.timeout}s",
        ) from e
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    finally:
        index_path.unlink(missing_ok=True)

    if ref == GIT_EMPTY_TREE_HASH:
        return ""
    # 将基础解析为完整提交 SHA，以便工件是自描述的。
    try:
        return run_git_command(
            ["git", "--no-pager", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            root,
        )
    except GitCommandError:
        return ""


def _path_is_excluded(rel: PurePosixPath, patterns: list[str], is_dir: bool) -> bool:
    """True 如果 ``rel`` 被 ``patterns`` 中的任何 glob 排除。

    镜像 git-delta 路径的 gitignore 语义，因此两种格式一致：

    - 逗号 ``/`` 标示了一个只匹配目录的模式：它匹配目录，但永远不会匹配文件的名称，所
    以  ``build/`` 模式修剪一个 ``build`` 目录，同时保
    留一个文件的名称 ``build``.
    - 多段模式（其中包含 ``/``、e.g。 ``secrets/prod``) 匹配完整的相对路径或其任何前
    缀，因此它会删除两者
      ``secrets/prod`` 及其下面的所有内容。
    - 裸名模式（无 ``/``、e.g。 ``node_modules`` 或 ``*.pyc``) 匹配任何深度的任何单个
    路径组件。

    无依赖关系，因此不会引入新的包。
    """
    parts = rel.parts
    for raw in patterns:
        pattern = raw.rstrip("/")
        dir_only = raw.endswith("/")
        if "/" in pattern:
            # 多段：锚点与相对路径根匹配，按段匹配，``*`` 会不跨越 ``/``（gitignore语义
            # ，与 git-delta 路径匹配）。 该模式匹配路径本身或嵌套在其下的任何内容：
            # ``secrets/prod`` 删除 ``secrets/prod`` 和 ``secrets/prod/key``；
            # ``*/test`` 掉落 ``a/test`` 但不
            # ``a/b/test``; ``a/*/c`` 下降 ``a/x/c``。
            pattern_parts = pattern.split("/")
            if len(parts) >= len(pattern_parts) and all(
                fnmatch.fnmatch(part, pat) for part, pat in zip(parts, pattern_parts)
            ):
                # 一个只匹配目录的模式匹配目录及其子目录，但不匹配路径等于模式的文件。
                #
                if dir_only and not is_dir and len(parts) == len(pattern_parts):
                    continue
                return True
        else:
            # 裸名：匹配任何单个组件。 对于文件上的仅目录模式，请跳过基本名称，以便共享
            # 目录排除名称的文件不会被删除。
            #
            candidates = parts if (is_dir or not dir_only) else parts[:-1]
            for part in candidates:
                if fnmatch.fnmatch(part, pattern):
                    return True
    return False


def _build_archive_manifest(
    source: str, file_count: int, total_bytes: int, excludes: list[str]
) -> bytes:
    """确定性（无时间戳）JSON 清单嵌入在 tar.gz 中。"""
    manifest = {
        "format": "tar.gz",
        "source": source,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "excludes": excludes,
    }
    return json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")


class _ExactSizeReader:
    """始终精确生成 ``size`` 字节的文件包装器。

    ``tar.addfile``写入成员头（声明``size``），然后从文件中复制字节； 如果并发作家在
    中间截断文件，那么一个短读会引发 * 中成员 *，在头和已经
    存在于 gzip 流中的部分前缀之后。这样，每跟随的成员（包括尾随的元数据）都会被无声
    地错位。 通过在NUL（文件变小）和在``size``（文件变大）处填充短读，
    ``addfile``总是收到声明大小的字节，因此，无论工作区在捕获过程中如何变异，流都不会
    解同步。
    """

    def __init__(self, fileobj: IO[bytes], size: int) -> None:
        self._fileobj = fileobj
        self._remaining = size

    def read(self, n: int = -1) -> bytes:
        if self._remaining <= 0:
            return b""
        if n is None or n < 0 or n > self._remaining:
            n = self._remaining
        data = self._fileobj.read(n)
        if len(data) < n:
            data = data + b"\x00" * (n - len(data))
        self._remaining -= len(data)
        return data


def _add_file_member(tar: tarfile.TarFile, file_path: Path, arcname: str) -> int | None:
    """将常规文件添加到 ``tar``，而不会有 tar 流损坏的风险。

    ``tar.add`` 统计文件，写入该大小的标头，然后复制正文 - 两者之间的并发截断会使流不
    同步（请参阅
    ``_ExactSizeReader``). 相反，调整 OPEN fd 中的标头大小，并通过
    ``_ExactSizeReader`` 复制那么多字节。 返回字节
    数，或者
    ``None`` 如果文件无法读取/不是常规文件（已跳过，尽力而为 - 工作区可能仍在变异）。
    """
    try:
        f = open(file_path, "rb")
    except OSError as e:
        logger.warning(f"Skipping unreadable file {file_path}: {e}")
        return None
    try:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode):
            # 进入非常规路径（dir/fifo/socket）； 跳过它。
            return None
        info = tar.gettarinfo(arcname=arcname, fileobj=f)
        tar.addfile(info, _ExactSizeReader(f, info.size))
        return info.size
    except OSError as e:
        logger.warning(f"Skipping unreadable file {file_path}: {e}")
        return None
    finally:
        f.close()


def _create_tar_gz_archive(root: Path, output_path: Path, excludes: list[str]) -> None:
    """将 ``root`` 的 gzip tarball 流式传输到 ``output_path``。

    ``root`` 步行时不跟随符号链接，修剪排除的目录，以确保它们从不被访问，只添加常规文
    件（符号链接被跳过——与REST的端点相同的安全姿态）。 文件一次添加一个
    ，因此存档永远不会保存在内存中。 确定性清单成员 (``ARCHIVE_MANIFEST_NAME``) 记录
    捕获的内容。
    """
    file_count = 0
    total_bytes = 0
    manifest_arcname = f"{root.name}/{ARCHIVE_MANIFEST_NAME}"
    manifest_collision = False
    try:
        with tarfile.open(output_path, "w:gz") as tar:
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                base = PurePosixPath(Path(dirpath).relative_to(root).as_posix())
                # 修剪已排除的目录，这样我们就不会降级它们。
                dirnames[:] = [
                    d
                    for d in dirnames
                    if not _path_is_excluded(base / d, excludes, is_dir=True)
                    and not _is_sensitive_git_internal(base / d)
                ]
                # 为每个幸存目录发出一个目录成员，以便清空创作目录往返（逐字节完整捕获合
                # 同）。 否则 tar 只会重新创建文件成员隐含的父目录，完全删除无子目录。
                #
                dir_arcname = (
                    root.name if base == PurePosixPath(".") else f"{root.name}/{base}"
                )
                if not Path(dirpath).is_symlink():
                    # 像下面每个文件添加的防护一样：在捕获中消失的目录（并发突变）必须跳
                    # 过其自己的成员，而不是中止整个存档。
                    #
                    try:
                        tar.add(dirpath, arcname=dir_arcname, recursive=False)
                    except OSError as e:
                        logger.warning(f"Skipping unreadable directory {dirpath}: {e}")
                for name in filenames:
                    rel = base / name
                    if _path_is_excluded(
                        rel, excludes, is_dir=False
                    ) or _is_sensitive_git_internal(rel):
                        continue
                    file_path = Path(dirpath) / name
                    if file_path.is_symlink() or not file_path.is_file():
                        continue
                    arcname = f"{root.name}/{rel}"
                    # 尽力而为且防腐败：工作区仍然可能变异，因此在添加文件时文件消失或被
                    # 截断的文件会被跳过，而不进行 tar 流的同步。
                    #
                    size = _add_file_member(tar, file_path, arcname)
                    if size is None:
                        continue
                    if arcname == manifest_arcname:
                        manifest_collision = True
                    file_count += 1
                    total_bytes += size

            # 当工作区在该路径上已经有一个真实文件时，跳过我们的合成捕获清单：用户的数据
            # 必须胜过我们的元数据。
            #
            if manifest_collision:
                logger.warning(
                    f"Workspace already contains {ARCHIVE_MANIFEST_NAME!r}; "
                    "preserving the user's file and skipping the synthetic "
                    "archive manifest."
                )
            else:
                manifest = _build_archive_manifest(
                    root.name, file_count, total_bytes, excludes
                )
                info = tarfile.TarInfo(manifest_arcname)
                info.size = len(manifest)
                tar.addfile(info, io.BytesIO(manifest))
    except Exception:
        output_path.unlink(missing_ok=True)
        raise


@file_router.post("/upload")
async def upload_file_query(
    path: Annotated[str, Query(description="Absolute file path")],
    file: Annotated[UploadFile, File()],
) -> FileUploadResult:
    """使用查询参数将文件上传到工作区（首选方法）。"""
    return await _upload_file(path, file)


@file_router.get(
    "/download", responses=_FILE_DOWNLOAD_RESPONSES, response_class=FileResponse
)
async def download_file_query(
    path: Annotated[str, Query(description="Absolute file path")],
) -> FileResponse:
    """使用查询参数从工作区下载文件（首选方法）。"""
    return await _download_file(path)


@file_router.post("/create_directory")
async def create_directory(
    path: Annotated[str, Query(description="Absolute directory path to create")],
) -> Success:
    """在工作区中创建一个目录，包括所有缺失的父目录。

    Idempotent: 现有目录成功并保留其内容
    未受影响。 在现有文件上或在父文件为文件的路径下创建是客户端错误 (400)，而不是服务
    器故障。
    """
    update_last_execution_time()
    logger.info(f"Creating directory: {path}")

    target_path = Path(path)
    if not target_path.is_absolute():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path must be absolute",
        )

    try:
        await asyncio.to_thread(lambda: target_path.mkdir(parents=True, exist_ok=True))
    except (FileExistsError, NotADirectoryError):
        # 当最终组件作为非目录存在时，mkdir(exist_ok=True) 仍然会引发；
        # NotADirectoryError 涵盖了作为文件的父组件。 两者都是调用者的路径错误，而不是服
        # 务器故障。
        #
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path exists and is not a directory",
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {e}",
        )
    except Exception as e:
        logger.error(f"Failed to create directory {path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create directory: {str(e)}",
        )

    logger.info(f"Created directory {target_path}")
    return Success()


def _list_home_favorites(
    home: Path, limit: int = 50, include_hidden: bool = False
) -> list[FileBrowserEntry]:
    """用户家中的顶级目录，按字母顺序排列。

    符号链接被跳过。 除非 ``include_hidden`` 为 True，否则将跳过隐藏条目（以“.”开头的
    名称），因此列表与
    ``search_subdirs`` 返回相同的路径和相同的标志。
    """
    entries: list[FileBrowserEntry] = []
    try:
        with os.scandir(home) as scanner:
            for entry in scanner:
                if not include_hidden and entry.name.startswith("."):
                    continue
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                entries.append(
                    FileBrowserEntry(label=entry.name, path=str(home / entry.name))
                )
    except (PermissionError, FileNotFoundError):
        return []
    entries.sort(key=lambda e: e.label.lower())
    return entries[:limit]


def _list_root_locations() -> list[FileBrowserEntry]:
    """文件系统根：Windows 上的当前驱动器，“/' 位于 POSIX”。"""
    if os.name == "nt":
        from string import ascii_uppercase

        roots: list[FileBrowserEntry] = []
        for letter in ascii_uppercase:
            candidate = Path(f"{letter}:\\")
            try:
                if candidate.exists():
                    roots.append(
                        FileBrowserEntry(label=f"{letter}:", path=str(candidate))
                    )
            except OSError:
                continue
        return roots
    return [FileBrowserEntry(label="/", path="/")]


@file_discovery_router.get("/home")
async def get_home_directory(
    include_hidden: Annotated[
        bool,
        Query(description="Include hidden top-level directories in `favorites`"),
    ] = False,
) -> HomeResponse:
    """返回智能体-服务器用户的主目录和动态侧边栏列表。

    ``favorites`` 是用户家目录中实际存在的顶级目录集合，因此反映了真实的环境，而不是
    硬编码的名称列表，这些名称可能不存在。 仅当
    ``include_hidden`` 为 True 时才包含隐藏目录。 ``locations`` 是文件系统根的集合 -
    POSIX 上的“/'”或 Window
    s 上的可用驱动器号。
    """
    home = Path.home()
    return HomeResponse(
        home=str(home),
        favorites=_list_home_favorites(home, include_hidden=include_hidden),
        locations=_list_root_locations(),
    )


@file_discovery_router.get("/search_subdirs")
async def search_subdirs(
    path: Annotated[
        str,
        Query(description="Absolute directory path to list subdirectories of"),
    ],
    page_id: Annotated[
        str | None,
        Query(title="Optional next_page_id from the previously returned page"),
    ] = None,
    limit: Annotated[
        int,
        Query(title="The max number of results in the page", gt=0, le=100),
    ] = 100,
    include_hidden: Annotated[
        bool,
        Query(title="Include hidden subdirectories (names starting with '.')"),
    ] = False,
) -> SubdirectoryPage:
    """搜索/列出 `path` 的直接子目录。

    由 GUI 的工作区选择器使用。 符号链接和文件被跳过。 除非 ``include_hidden`` 为
    True，否则将跳过隐藏条目（以“.”开头的名称）。 返回
    绝对路径，以便 GUI 可以直接使用结果
    ``workspace.working_dir``.

    结果按名称（按确切名称断开关系）排序（不区分大小写）并分页。 ``page_id`` 是上一页
    返回的 ``next_page_id``（下一页中包含的第一个项目的名
    称）。
    """

    target = Path(path)
    if not target.is_absolute():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path must be absolute",
        )
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Directory not found",
        )
    if not target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a directory",
        )

    entries: list[SubdirectoryEntry] = []
    try:
        with os.scandir(target) as scanner:
            for entry in scanner:
                if not include_hidden and entry.name.startswith("."):
                    continue
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                entries.append(
                    SubdirectoryEntry(name=entry.name, path=str(target / entry.name))
                )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {e}",
        )

    # 通过确切的名称打破不区分大小写的关系，以便仅大小写不同的名称（“Foo”、“foo”）具有稳
    # 定的顺序和不同的游标。
    #
    entries.sort(key=lambda e: (e.name.lower(), e.name))

    start_index = 0
    if page_id:
        names = [entry.name for entry in entries]
        if page_id in names:
            start_index = names.index(page_id)
        else:
            # 旧服务器发出的小写游标。
            for i, name in enumerate(names):
                if name.lower() == page_id:
                    start_index = i
                    break

    page_items = entries[start_index : start_index + limit]
    next_page_id: str | None = None
    if start_index + limit < len(entries):
        next_page_id = entries[start_index + limit].name

    return SubdirectoryPage(items=page_items, next_page_id=next_page_id)


@file_router.get(
    "/download-trajectory/{conversation_id}",
    responses=_FILE_DOWNLOAD_RESPONSES,
    response_class=FileResponse,
)
async def download_trajectory(
    conversation_id: UUID,
    request: Request,
) -> FileResponse:
    """下载对话轨迹的 zip 存档。"""
    config: Config = request.app.state.config
    temp_file = config.conversations_path / f"{conversation_id.hex}.zip"
    conversation_dir = config.conversations_path / conversation_id.hex

    if not conversation_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    await asyncio.to_thread(_create_zip_from_directory, conversation_dir, temp_file)
    return FileResponse(
        path=temp_file,
        filename=temp_file.name,
        media_type="application/octet-stream",
        background=BackgroundTask(temp_file.unlink),
    )


@file_router.get(
    "/archive", responses=_FILE_DOWNLOAD_RESPONSES, response_class=FileResponse
)
async def archive_directory(
    path: Annotated[
        str,
        Query(
            description=(
                "Absolute path of the directory to archive. If it is not a git "
                "repository but holds exactly one git repository (up to three "
                "levels down), that repository is archived instead, for both "
                "formats; pass the repository itself, or a directory holding "
                "zero or several repositories, to control what is archived."
            )
        ),
    ],
    archive_format: Annotated[
        ArchiveFormat,
        Query(
            alias="format",
            description=(
                "Archive format: 'git-delta' for a git patch of the working-tree "
                "changes against a base ref (requires a git repository); 'tar.gz' "
                "for a gzip tarball of the files (works on non-git directories "
                "too). Both formats archive the directory at path, except that "
                "a non-repository path holding exactly one git repository (up "
                "to three levels down, skipping hidden and vendored "
                "directories) is archived as that repository, so files beside "
                "it are not included; with zero or several repositories the "
                "directory is archived as given."
            ),
        ),
    ] = "git-delta",
    base_ref: Annotated[
        str | None,
        Query(
            description=(
                "Only for format='git-delta': base ref to diff against. "
                "Defaults to the auto-detected comparison ref (origin branch, "
                "merge-base, or the empty tree for a fresh repo). Ignored for "
                "format='tar.gz'."
            )
        ),
    ] = None,
    use_default_excludes: Annotated[
        bool,
        Query(
            description=(
                "Whether to apply the built-in default exclude patterns "
                "(node_modules/, .venv/, caches, build outputs, etc.). Defaults "
                "to true for compact archives; set false to allow a full "
                "workspace capture, including fat directories."
            )
        ),
    ] = True,
    exclude: Annotated[
        list[str] | None,
        Query(
            description=(
                "Additional glob patterns to exclude (repeatable, e.g. "
                "?exclude=foo&exclude=*.bin). Combined with the built-in "
                "default excludes when use_default_excludes=true; used by "
                "itself when use_default_excludes=false."
            )
        ),
    ] = None,
) -> FileResponse:
    """在运行时删除之前，将持久化的工作区目录存档。

    生成一个可下载的归档文件 ``path``。 符号链接永远不会离开请求的目录，因此存档不能
    包含来自外部的文件。 临时存档在 ``path`` 外部创建，并在发送响应
    后删除。
    """
    update_last_execution_time()

    target = Path(path)
    if not target.is_absolute():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path must be absolute",
        )
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Directory not found",
        )
    if not target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a directory",
        )
    if base_ref is not None and base_ref.startswith("-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="base_ref must not start with '-'",
        )

    target = target.resolve()
    effective_excludes = (
        list(_DEFAULT_ARCHIVE_EXCLUDES) if use_default_excludes else []
    ) + (exclude or [])
    # 将档案建在工作区的同一卷上（其父目录，因此它永远不会包含在自己之中），而不是系统临
    # 时目录：在 tmpfs /tmp 上的大型 tar.gz 会击败流到磁盘 OOM 的修复，而在小容器根目录
    # 上可能会触发 pod 的 ephemeral-storage 限制。 如果父级不可用，则回退到默认临时位置
    # 。
    #
    scratch_dir: str | None = None
    parent = target.parent
    if parent != target and os.access(parent, os.W_OK):
        scratch_dir = str(parent)
    fd, tmp_name = tempfile.mkstemp(
        suffix=_ARCHIVE_SUFFIX[archive_format], dir=scratch_dir
    )
    os.close(fd)
    output_path = Path(tmp_name)

    # 调用者传递工作区基址，但存储库支持的对话克隆到子目录中； 将实际仓库解决，这样两个
    # 格式都会在仓库中根化（在 git-delta、tar.gz 和初始快照中的一致路径），git-delta 不
    # 会在非仓库父节点上返回 400。
    #
    repo_root = await asyncio.to_thread(_resolve_git_repo_root, target)
    base_commit = ""
    try:
        if archive_format == "git-delta":
            base_commit = await asyncio.to_thread(
                _create_git_delta,
                repo_root,
                base_ref,
                output_path,
                effective_excludes,
            )
        else:
            await asyncio.to_thread(
                _create_tar_gz_archive, repo_root, output_path, effective_excludes
            )
    except GitRepositoryError as e:
        output_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Not a git repository: {e}",
        )
    except ValueError as e:
        output_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except GitCommandError as e:
        output_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate git delta: {e}",
        )
    except Exception as e:
        output_path.unlink(missing_ok=True)
        logger.error(f"Failed to archive {target}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to archive directory: {str(e)}",
        )

    # 存储库身份（远程/分支/HEAD）适用于两种格式，因此 tar.gz 快照也是自描述的；
    # base_commit/base_ref 仅限 git-delta（它们描述了补丁的重放基础）。
    #
    headers: dict[str, str] = {}
    if (repo_root / ".git").exists():
        repo_metadata = await asyncio.to_thread(get_git_repository_metadata, repo_root)
        for key, header in (
            ("repo_remote", "X-Archive-Repo-Remote"),
            ("branch", "X-Archive-Branch"),
            ("head_commit", "X-Archive-Head-Commit"),
        ):
            if value := repo_metadata.get(key):
                headers[header] = _header_safe(value)
        headers["X-Archive-Repo-Root"] = _header_safe(str(repo_root))
    if base_commit:
        # 使 git-delta 自描述，以便消费者可以重播补丁。
        headers["X-Archive-Base-Commit"] = base_commit
        headers["X-Archive-Base-Ref"] = base_ref or "auto"

    return FileResponse(
        path=output_path,
        filename=f"{repo_root.name}{_ARCHIVE_SUFFIX[archive_format]}",
        media_type=_ARCHIVE_MEDIA_TYPE[archive_format],
        headers=headers,
        background=BackgroundTask(output_path.unlink, missing_ok=True),
    )
