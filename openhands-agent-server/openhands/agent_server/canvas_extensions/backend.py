"""可选 Canvas 应用程序后端的拥有生命周期子进程。"""

import asyncio
import gzip
import hashlib
import os
import platform
import shutil
import signal
import socket
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zlib
from collections import deque
from pathlib import Path, PurePosixPath
from typing import Final, Literal
from urllib.parse import urljoin, urlsplit

from pydantic import BaseModel, Field

from openhands.agent_server.canvas_extensions.installed import (
    get_installed_canvas_extension,
    get_installed_canvas_extension_manifest,
    get_installed_canvas_extensions_dir,
)
from openhands.agent_server.canvas_extensions.manifest import (
    BackendPlatform,
    CanvasExtensionBackend,
    CanvasExtensionBackendArtifact,
    CanvasExtensionManifest,
)
from openhands.sdk.utils.path import get_user_persistence_dir


BackendState = Literal[
    "missing", "stopped", "starting", "ready", "unhealthy", "unsupported"
]
_SAFE_INHERITED_ENV: Final[frozenset[str]] = frozenset(
    {"LANG", "LC_ALL", "LC_CTYPE", "PATH", "TMPDIR", "TZ"}
)
_MAX_LOG_BYTES: Final[int] = 256 * 1024
_STOP_TIMEOUT_SECONDS: Final[float] = 5
_ARTIFACT_DOWNLOAD_TIMEOUT_SECONDS: Final[float] = 120
_MAX_ARTIFACT_BYTES: Final[int] = 1024 * 1024 * 1024
_MAX_ARTIFACT_REDIRECTS: Final[int] = 5
_PROBE_FAILED_DETAIL: Final[str] = "Backend health probe failed"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


class BackendRevisionRequest(BaseModel):
    """明确批准一项确切安装的修订版。"""

    revision: str = Field(min_length=1)


class BackendStatus(BaseModel):
    """已安装 Canvas 应用程序后端的当前状态。"""

    name: str
    state: BackendState
    revision: str | None = None
    prepared_revision: str | None = None
    pid: int | None = None
    port: int | None = None
    detail: str | None = None


class BackendLogs(BaseModel):
    """有界的组合 stdout 和 stderr 输出。"""

    name: str
    logs: str
    truncated: bool


class _PreparedState(BaseModel):
    revision: str
    platform: BackendPlatform
    artifact_sha256: str
    artifact_dir: str


class _RunRecord(BaseModel):
    """标识后端进程组和启动它的服务器。"""

    name: str
    pgid: int
    start_time: int
    server_pid: int
    server_start_time: int


def _process_start_time(pid: int) -> int | None:
    """返回自启动以来进程的启动时间（以时钟周期为单位）（Linux）。"""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    # 场22； 命令名称（字段 2）可以包含空格和括号。
    return int(stat.rsplit(")", 1)[1].split()[19])


class _Runtime:
    def __init__(self) -> None:
        self.process: asyncio.subprocess.Process | None = None
        self.port: int | None = None
        self.revision: str | None = None
        self.state: BackendState = "stopped"
        self.detail: str | None = None
        self.logs: deque[bytes] = deque()
        self.log_bytes = 0
        self.logs_truncated = False
        self.drain_tasks: list[asyncio.Task[None]] = []
        # 运行状况等待在其自己的任务中运行，因此当后端启动时，名称锁在 status()
        # /stop()/logs() 内保持空闲状态。
        #
        self.start_task: asyncio.Task[None] | None = None
        self.stop_requested = asyncio.Event()


class CanvasExtensionBackendManager:
    """每个已安装的 Canvas 应用程序拥有一个可选的后端进程。"""

    def __init__(
        self,
        installed_dir: Path | None = None,
        state_dir: Path | None = None,
        *,
        allow_insecure_artifact_urls: bool = False,
        max_artifact_bytes: int = _MAX_ARTIFACT_BYTES,
    ) -> None:
        self.installed_dir = installed_dir or get_installed_canvas_extensions_dir()
        root = (
            state_dir or get_user_persistence_dir() / "canvas-extensions" / "backends"
        )
        self.state_dir = root
        self.artifacts_dir = root / "artifacts"
        self.downloads_dir = root / "downloads"
        self.data_dir = root / "data"
        self.approvals_dir = root / "approvals"
        self.run_dir = root / "run"
        self.allow_insecure_artifact_urls = allow_insecure_artifact_urls
        self.max_artifact_bytes = max_artifact_bytes
        self._runtimes: dict[str, _Runtime] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, name: str) -> asyncio.Lock:
        return self._locks.setdefault(name, asyncio.Lock())

    def _runtime(self, name: str) -> _Runtime:
        return self._runtimes.setdefault(name, _Runtime())

    def _manifest(self, name: str) -> CanvasExtensionManifest | None:
        return get_installed_canvas_extension_manifest(name, self.installed_dir)

    def revision(self, name: str) -> str | None:
        info = get_installed_canvas_extension(name, self.installed_dir)
        manifest = self._manifest(name)
        if info is None or manifest is None:
            return None
        if info.resolved_ref:
            return info.resolved_ref
        payload = manifest.model_dump_json(exclude_none=True).encode()
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"

    @staticmethod
    def current_platform() -> BackendPlatform | None:
        if platform.system() != "Linux":
            return None
        machine = platform.machine().lower()
        if machine in {"x86_64", "amd64"}:
            return "linux-amd64"
        if machine in {"aarch64", "arm64"}:
            return "linux-arm64"
        return None

    def _backend_parts(
        self, name: str
    ) -> (
        tuple[
            CanvasExtensionBackend,
            CanvasExtensionBackendArtifact,
            BackendPlatform,
        ]
        | None
    ):
        manifest = self._manifest(name)
        current_platform = self.current_platform()
        if manifest is None or manifest.backend is None or current_platform is None:
            return None
        artifact = manifest.backend.artifacts.get(current_platform)
        if artifact is None:
            return None
        return manifest.backend, artifact, current_platform

    def _approval_path(self, name: str) -> Path:
        return self.approvals_dir / f"{name}.json"

    def _read_prepared(self, name: str) -> _PreparedState | None:
        try:
            return _PreparedState.model_validate_json(
                self._approval_path(name).read_text()
            )
        except (OSError, ValueError):
            return None

    def _write_prepared(self, name: str, state: _PreparedState) -> None:
        self.approvals_dir.mkdir(parents=True, exist_ok=True)
        destination = self._approval_path(name)
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(state.model_dump_json())
        os.replace(temporary, destination)

    def invalidate_approval(self, name: str) -> None:
        self._approval_path(name).unlink(missing_ok=True)

    @staticmethod
    def _resolve_contained(root: Path, relative: str) -> Path:
        resolved_root = root.resolve()
        candidate = (resolved_root / relative).resolve()
        if not candidate.is_relative_to(resolved_root) or not candidate.is_file():
            raise ValueError("backend artifact is not a contained regular file")
        return candidate

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _validate_download_url(url: str, allow_http: bool) -> None:
        parsed = urlsplit(url)
        schemes = {"https", "http"} if allow_http else {"https"}
        if (
            parsed.scheme not in schemes
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("backend artifact URL is not allowed")

    def _download_archive(self, url: str, expected_sha256: str) -> Path:
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        destination = self.downloads_dir / f"{expected_sha256}.tar.gz"
        if destination.is_file() and self._sha256(destination) == expected_sha256:
            return destination
        destination.unlink(missing_ok=True)
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
        opener = urllib.request.build_opener(_NoRedirect)
        current_url = url
        try:
            for redirect_count in range(_MAX_ARTIFACT_REDIRECTS + 1):
                self._validate_download_url(
                    current_url, self.allow_insecure_artifact_urls
                )
                request = urllib.request.Request(
                    current_url,
                    headers={
                        "Accept": "application/octet-stream",
                        "Accept-Encoding": "identity",
                        "User-Agent": "OpenHands-Agent-Server",
                    },
                )
                try:
                    response = opener.open(
                        request, timeout=_ARTIFACT_DOWNLOAD_TIMEOUT_SECONDS
                    )
                except urllib.error.HTTPError as exc:
                    if exc.code not in {301, 302, 303, 307, 308}:
                        raise ValueError(
                            f"backend artifact download failed with HTTP {exc.code}"
                        ) from exc
                    location = exc.headers.get("Location")
                    if not location or redirect_count == _MAX_ARTIFACT_REDIRECTS:
                        raise ValueError(
                            "backend artifact redirect limit exceeded"
                        ) from exc
                    current_url = urljoin(current_url, location)
                    continue
                with response:
                    length = response.headers.get("Content-Length")
                    if length is not None and int(length) > self.max_artifact_bytes:
                        raise ValueError("backend artifact exceeds maximum size")
                    digest = hashlib.sha256()
                    received = 0
                    with temporary.open("wb") as stream:
                        while chunk := response.read(1024 * 1024):
                            received += len(chunk)
                            if received > self.max_artifact_bytes:
                                raise ValueError(
                                    "backend artifact exceeds maximum size"
                                )
                            digest.update(chunk)
                            stream.write(chunk)
                    if digest.hexdigest() != expected_sha256:
                        raise ValueError(
                            "backend artifact checksum does not match manifest"
                        )
                    os.replace(temporary, destination)
                    return destination
            raise ValueError("backend artifact redirect limit exceeded")
        except (OSError, urllib.error.URLError) as exc:
            raise ValueError("backend artifact download failed") from exc
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _extract_archive(
        archive: Path, destination: Path, strip_components: int = 0
    ) -> None:
        root = destination.resolve()
        seen: set[PurePosixPath] = set()
        extracted = 0
        with tarfile.open(archive, mode="r:gz") as tar:
            for member in tar:
                original = PurePosixPath(member.name)
                if original.is_absolute() or ".." in original.parts:
                    raise ValueError(
                        "backend artifact contains an unsafe archive entry"
                    )
                parts = original.parts[strip_components:]
                if not parts:
                    continue
                relative = PurePosixPath(*parts)
                if relative in seen or not (member.isfile() or member.isdir()):
                    raise ValueError(
                        "backend artifact contains an unsafe archive entry"
                    )
                seen.add(relative)
                target = (root / Path(*relative.parts)).resolve()
                if not target.is_relative_to(root):
                    raise ValueError(
                        "backend artifact contains an unsafe archive entry"
                    )
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    source = tar.extractfile(member)
                    if source is None:
                        raise ValueError(
                            "backend artifact contains an unsafe archive entry"
                        )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    target.chmod(member.mode & 0o555)
                extracted += 1
        if not extracted:
            raise ValueError("backend artifact contains no files after stripping")
        for path in sorted(destination.rglob("*"), reverse=True):
            if path.is_dir():
                path.chmod(0o555)
        destination.chmod(0o555)

    async def prepare(self, name: str, revision: str) -> BackendStatus:
        async with self._lock(name):
            status = self._status_unlocked(name)
            if status.state in {"missing", "unsupported"}:
                return status
            current_revision = self.revision(name)
            if revision != current_revision:
                raise ValueError("approval revision does not match installed revision")
            prepared = self._read_prepared(name)
            if (
                prepared is not None
                and prepared.revision == revision
                and Path(prepared.artifact_dir).is_dir()
            ):
                return self._status_unlocked(name)

            parts = self._backend_parts(name)
            assert parts is not None
            _, artifact, current_platform = parts
            package_root = self.installed_dir / name
            if artifact.path:
                archive = self._resolve_contained(package_root, artifact.path)
                actual_sha256 = await asyncio.to_thread(self._sha256, archive)
                if actual_sha256 != artifact.sha256:
                    raise ValueError(
                        "backend artifact checksum does not match manifest"
                    )
            else:
                assert artifact.url is not None
                archive = await asyncio.to_thread(
                    self._download_archive, artifact.url, artifact.sha256
                )
                actual_sha256 = artifact.sha256

            artifact_dir = self.artifacts_dir / name / actual_sha256
            if not artifact_dir.exists():
                artifact_dir.parent.mkdir(parents=True, exist_ok=True)
                temporary = Path(
                    tempfile.mkdtemp(
                        prefix=f".{actual_sha256}.", dir=artifact_dir.parent
                    )
                )
                try:
                    try:
                        await asyncio.to_thread(
                            self._extract_archive,
                            archive,
                            temporary,
                            artifact.strip_components,
                        )
                    except (
                        tarfile.TarError,
                        gzip.BadGzipFile,
                        EOFError,
                        zlib.error,
                    ) as exc:
                        raise ValueError(
                            "backend artifact is not a valid gzip tar archive"
                        ) from exc
                    try:
                        os.replace(temporary, artifact_dir)
                    except OSError:
                        if not artifact_dir.is_dir():
                            raise
                finally:
                    shutil.rmtree(temporary, ignore_errors=True)
            self._write_prepared(
                name,
                _PreparedState(
                    revision=revision,
                    platform=current_platform,
                    artifact_sha256=actual_sha256,
                    artifact_dir=str(artifact_dir),
                ),
            )
            return self._status_unlocked(name)

    def _status_unlocked(self, name: str) -> BackendStatus:
        revision = self.revision(name)
        manifest = self._manifest(name)
        runtime = self._runtimes.get(name)
        prepared = self._read_prepared(name)
        prepared_revision = prepared.revision if prepared else None
        if manifest is None:
            state: BackendState = "missing"
            detail = "Canvas App is not installed or its manifest is invalid"
        elif manifest.backend is None:
            state = "unsupported"
            detail = "Canvas App does not declare a backend"
        elif self._backend_parts(name) is None:
            state = "unsupported"
            detail = "Canvas App backend does not support this platform"
        elif runtime is not None and runtime.state in {
            "starting",
            "ready",
            "unhealthy",
        }:
            state = runtime.state
            detail = runtime.detail
        else:
            state = "stopped"
            detail = None
        return BackendStatus(
            name=name,
            state=state,
            revision=revision,
            prepared_revision=prepared_revision,
            pid=(
                runtime.process.pid
                if runtime and runtime.process and runtime.process.returncode is None
                else None
            ),
            port=(
                runtime.port
                if runtime and runtime.process and runtime.process.returncode is None
                else None
            ),
            detail=detail,
        )

    async def status(self, name: str) -> BackendStatus:
        async with self._lock(name):
            return await self._refresh_unlocked(name)

    async def _refresh_unlocked(self, name: str) -> BackendStatus:
        runtime = self._runtimes.get(name)
        if runtime and runtime.process and runtime.process.returncode is not None:
            returncode = runtime.process.returncode
            runtime.port = None
            runtime.state = "unhealthy"
            runtime.detail = f"Backend exited with code {returncode}"
            await self._terminate_runtime(runtime)
        elif (
            runtime
            and runtime.port is not None
            and (
                runtime.state == "ready"
                # 只错过一次探测的实时进程会被再次探测，因此一个缓慢的答案不会锁定它
                # `unhealthy`。
                #
                or (
                    runtime.state == "unhealthy"
                    and runtime.detail == _PROBE_FAILED_DETAIL
                )
            )
        ):
            manifest = self._manifest(name)
            if manifest is None or manifest.backend is None:
                # 磁盘清单不再验证（或停止声明后端）； 报告一旦 `_probe` 取消引用它，而
                # 不是回溯 AssertionError。
                #
                return self._status_unlocked(name)
            probe_url = f"http://127.0.0.1:{runtime.port}{manifest.backend.health.path}"
            if await asyncio.to_thread(self._probe, probe_url):
                runtime.state = "ready"
                runtime.detail = None
            else:
                runtime.state = "unhealthy"
                runtime.detail = _PROBE_FAILED_DETAIL
        return self._status_unlocked(name)

    @staticmethod
    def _allocate_port() -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _environment(
        self, backend: CanvasExtensionBackend, data_dir: Path
    ) -> dict[str, str]:
        disallowed = set(backend.inherit_environment) - _SAFE_INHERITED_ENV
        if disallowed:
            names = ", ".join(sorted(disallowed))
            raise ValueError(
                f"backend requests disallowed environment variables: {names}"
            )
        home = data_dir / "home"
        home.mkdir(parents=True, exist_ok=True)
        environment = {
            name: os.environ[name]
            for name in backend.inherit_environment
            if name in os.environ
        }
        environment["HOME"] = str(home)
        return environment

    @staticmethod
    def _expand_argv(
        backend: CanvasExtensionBackend,
        port: int,
        data_dir: Path,
        artifact_dir: Path,
    ) -> list[str]:
        replacements = {
            "{port}": str(port),
            "{data_dir}": str(data_dir),
            "{artifact_dir}": str(artifact_dir),
        }
        argv: list[str] = []
        for argument in backend.argv:
            for placeholder, value in replacements.items():
                argument = argument.replace(placeholder, value)
            argv.append(argument)

        artifact_root = artifact_dir.resolve()
        executable = Path(argv[0]).resolve()
        if (
            not executable.is_relative_to(artifact_root)
            or not executable.is_file()
            or not os.access(executable, os.X_OK)
        ):
            raise ValueError(
                "backend executable must be an executable regular file inside "
                "the prepared artifact"
            )
        argv[0] = str(executable)
        return argv

    async def _drain(
        self, runtime: _Runtime, stream: asyncio.StreamReader | None, label: bytes
    ) -> None:
        if stream is None:
            return
        while chunk := await stream.read(8192):
            entry = label + chunk
            runtime.logs.append(entry)
            runtime.log_bytes += len(entry)
            while runtime.log_bytes > _MAX_LOG_BYTES and runtime.logs:
                runtime.log_bytes -= len(runtime.logs.popleft())
                runtime.logs_truncated = True

    @staticmethod
    def _probe(url: str) -> bool:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return 200 <= response.status < 400
        except (OSError, urllib.error.URLError):
            return False

    async def _await_healthy(
        self,
        runtime: _Runtime,
        backend: CanvasExtensionBackend,
        port: int,
    ) -> None:
        """轮询后端的运行状况端点直到其准备就绪。

        作为 ``runtime.start_task`` 而不是内联运行，因此名称锁是
        free: ``status()`` 可以举报 ``starting``，``stop()`` 可以放弃
        永远不会出现的后端。
        """
        try:
            deadline = time.monotonic() + backend.health.timeout_seconds
            probe_url = f"http://127.0.0.1:{port}{backend.health.path}"
            while time.monotonic() < deadline:
                if runtime.stop_requested.is_set():
                    return
                process = runtime.process
                if process is None or process.returncode is not None:
                    code = process.returncode if process is not None else None
                    raise RuntimeError(f"backend exited with code {code}")
                if await asyncio.to_thread(self._probe, probe_url):
                    runtime.state = "ready"
                    runtime.detail = None
                    return
                await asyncio.sleep(backend.health.interval_seconds)
            raise TimeoutError("backend health check timed out")
        except asyncio.CancelledError:
            runtime.state = "stopped"
            runtime.detail = None
            raise
        except Exception as exc:
            if runtime.stop_requested.is_set():
                # `stop()` 拥有最终状态； 不要纯粹因为我们破坏了流程而引发错误来破坏它。
                #
                runtime.state = "stopped"
                runtime.detail = None
            else:
                runtime.state = "unhealthy"
                runtime.detail = str(exc)

    async def start(self, name: str, revision: str) -> BackendStatus:
        async with self._lock(name):
            current = self._status_unlocked(name)
            if current.state in {"missing", "unsupported"}:
                return current
            runtime = self._runtime(name)
            task = runtime.start_task
            if runtime.process and runtime.process.returncode is None:
                if runtime.revision != revision:
                    raise RuntimeError(
                        "a different backend revision is already running"
                    )
                if task is None:
                    return await self._refresh_unlocked(name)
            else:
                if revision != self.revision(name):
                    raise ValueError(
                        "approval revision does not match installed revision"
                    )
                prepared = self._read_prepared(name)
                if prepared is None or prepared.revision != revision:
                    raise RuntimeError("backend revision must be prepared before start")
                artifact_dir = Path(prepared.artifact_dir)
                if not artifact_dir.is_dir():
                    raise RuntimeError("prepared backend artifact is missing")

                parts = self._backend_parts(name)
                assert parts is not None
                backend, artifact, current_platform = parts
                expected_artifact_dir = (
                    self.artifacts_dir / name / prepared.artifact_sha256
                ).resolve()
                if (
                    prepared.platform != current_platform
                    or prepared.artifact_sha256 != artifact.sha256
                    or artifact_dir.resolve() != expected_artifact_dir
                ):
                    raise RuntimeError(
                        "prepared backend metadata does not match manifest"
                    )
                if runtime.process is not None:
                    await self._terminate_runtime(runtime)
                package_root = (self.installed_dir / name).resolve()
                data_dir = self.data_dir / name
                data_dir.mkdir(parents=True, exist_ok=True)
                port = self._allocate_port()
                runtime.state = "starting"
                runtime.detail = None
                runtime.port = port
                runtime.revision = revision
                runtime.logs.clear()
                runtime.log_bytes = 0
                runtime.logs_truncated = False
                runtime.stop_requested = asyncio.Event()
                try:
                    runtime.process = await asyncio.create_subprocess_exec(
                        *self._expand_argv(backend, port, data_dir, artifact_dir),
                        cwd=package_root,
                        env=self._environment(backend, data_dir),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        start_new_session=True,
                    )
                except Exception as exc:
                    runtime.state = "unhealthy"
                    runtime.detail = str(exc)
                    await self._terminate_runtime(runtime)
                    return self._status_unlocked(name)
                self._write_run_record(name, runtime.process.pid)
                runtime.drain_tasks = [
                    asyncio.create_task(
                        self._drain(runtime, runtime.process.stdout, b"[stdout] ")
                    ),
                    asyncio.create_task(
                        self._drain(runtime, runtime.process.stderr, b"[stderr] ")
                    ),
                ]
                task = asyncio.create_task(self._await_healthy(runtime, backend, port))
                runtime.start_task = task
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        async with self._lock(name):
            # 在这里清除句柄并回收失败启动的进程组，其中运行时已知仍然是我们的。
            #
            if runtime.start_task is task:
                runtime.start_task = None
            if runtime.state == "unhealthy":
                await self._terminate_runtime(runtime)
            return self._status_unlocked(name)

    async def _finish_runtime(self, runtime: _Runtime) -> None:
        if runtime.process is not None:
            await runtime.process.wait()
        if runtime.drain_tasks:
            await asyncio.gather(*runtime.drain_tasks, return_exceptions=True)
        runtime.drain_tasks = []

    @staticmethod
    def _signal_group(pgid: int, sig: int) -> None:
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass

    @staticmethod
    def _group_alive(pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False

    def _runtime_group_alive(self, runtime: _Runtime) -> bool:
        process = runtime.process
        return process is not None and (
            process.returncode is None or self._group_alive(process.pid)
        )

    async def _wait_for_group_exit(self, pgid: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            if not self._group_alive(pgid):
                return True
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(0.05)

    async def _terminate_runtime(self, runtime: _Runtime) -> None:
        process = runtime.process
        if process is None:
            return
        pgid = process.pid
        # 向整个组发送信号，并等待 *集团* 去排水，而不仅仅是
        # 领导者：一个后端可能会分叉后代，并且一个比它寿命更长（或者是
        # 之后分叉）领导者使团队保持活力。 仅在领导者的退出代码上升级会泄漏这些后代。
        #
        if process.returncode is None:
            self._signal_group(pgid, signal.SIGTERM)
            if not await self._wait_for_group_exit(pgid, _STOP_TIMEOUT_SECONDS):
                self._signal_group(pgid, signal.SIGKILL)
                await self._wait_for_group_exit(pgid, _STOP_TIMEOUT_SECONDS)
        elif self._group_alive(pgid):
            # 由于没有领导者可以彻底关闭，它的后代成为孤儿； 不要让某人在宽限期内保持状
            # 态或重新启动。
            #
            self._signal_group(pgid, signal.SIGKILL)
            await self._wait_for_group_exit(pgid, _STOP_TIMEOUT_SECONDS)
        if process.returncode is None:
            await process.wait()
        await self._finish_runtime(runtime)
        self._run_record_path(pgid).unlink(missing_ok=True)
        runtime.process = None
        runtime.port = None

    def _run_record_path(self, pgid: int) -> Path:
        return self.run_dir / f"{pgid}.json"

    def _write_run_record(self, name: str, pgid: int) -> None:
        start_time = _process_start_time(pgid)
        server_start_time = _process_start_time(os.getpid())
        if start_time is None or server_start_time is None:
            return
        self.run_dir.mkdir(parents=True, exist_ok=True)
        record = _RunRecord(
            name=name,
            pgid=pgid,
            start_time=start_time,
            server_pid=os.getpid(),
            server_start_time=server_start_time,
        )
        destination = self._run_record_path(pgid)
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(record.model_dump_json())
        os.replace(temporary, destination)

    def _is_recorded_backend(self, record: _RunRecord) -> bool:
        if _process_start_time(record.pgid) != record.start_time:
            return False
        try:
            cmdline = Path(f"/proc/{record.pgid}/cmdline").read_bytes()
        except OSError:
            return False
        prefix = f"{(self.artifacts_dir / record.name).resolve()}/"
        return any(
            argument.decode(errors="replace").startswith(prefix)
            for argument in cmdline.split(b"\0")
        )

    async def reap_orphans(self) -> None:
        """停止因未拆除而死亡的服务器留下的运行后端。

        在服务请求之前调用：内存中的运行时是唯一的视图
        `status`、`start` 和 `delete_data` 有一个正在运行的后端。
        """
        for path in sorted(self.run_dir.glob("*.json")):
            try:
                record = _RunRecord.model_validate_json(path.read_text())
            except (OSError, ValueError):
                path.unlink(missing_ok=True)
                continue
            if _process_start_time(record.server_pid) == record.server_start_time:
                continue  # 它的服务器仍在运行并拥有它。
            if self._is_recorded_backend(record):
                self._signal_group(record.pgid, signal.SIGTERM)
                if not await self._wait_for_group_exit(
                    record.pgid, _STOP_TIMEOUT_SECONDS
                ):
                    self._signal_group(record.pgid, signal.SIGKILL)
                    await self._wait_for_group_exit(record.pgid, _STOP_TIMEOUT_SECONDS)
            path.unlink(missing_ok=True)

    def has_running_backends(self) -> bool:
        return any(
            runtime.start_task is not None or self._runtime_group_alive(runtime)
            for runtime in self._runtimes.values()
        )

    async def stop(self, name: str) -> BackendStatus:
        task: asyncio.Task[None] | None = None
        async with self._lock(name):
            runtime = self._runtimes.get(name)
            if runtime is not None:
                # 在取消前询问空中健康等待，以便在`starting`中停滞的后端可以停止，而不是
                # 对锁（以及REST处理器）进行全超时。
                #
                runtime.stop_requested.set()
                task = runtime.start_task
                runtime.start_task = None
                if task is not None:
                    task.cancel()
                await self._terminate_runtime(runtime)
                runtime.state = "stopped"
                runtime.detail = None
            status = self._status_unlocked(name)
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        return status

    async def logs(self, name: str, limit_bytes: int) -> BackendLogs:
        async with self._lock(name):
            runtime = self._runtimes.get(name)
            if runtime is None:
                return BackendLogs(name=name, logs="", truncated=False)
            content = b"".join(runtime.logs)
            truncated = runtime.logs_truncated or len(content) > limit_bytes
            return BackendLogs(
                name=name,
                logs=content[-limit_bytes:].decode(errors="replace"),
                truncated=truncated,
            )

    async def delete_data(self, name: str) -> BackendStatus:
        async with self._lock(name):
            runtime = self._runtimes.get(name)
            if runtime and (
                runtime.start_task is not None or self._runtime_group_alive(runtime)
            ):
                raise RuntimeError("stop the backend before deleting its data")
            shutil.rmtree(self.data_dir / name, ignore_errors=True)
            return self._status_unlocked(name)

    def ready_endpoint(self, name: str) -> tuple[str, int] | None:
        """未来经过身份验证的路由器的内部注册表边界。"""
        runtime = self._runtimes.get(name)
        if runtime is None or runtime.state != "ready" or runtime.port is None:
            return None
        # `state`仅由status()/start()/stop()协调； 从那时起崩溃的后端不得被拨打（下一个
        # 状态轮询报告它`unhealthy`并获取其进程组）。
        #
        if runtime.process is None or runtime.process.returncode is not None:
            return None
        return "127.0.0.1", runtime.port

    async def shutdown(self) -> None:
        await asyncio.gather(
            *(self.stop(name) for name in list(self._runtimes)),
            return_exceptions=True,
        )
