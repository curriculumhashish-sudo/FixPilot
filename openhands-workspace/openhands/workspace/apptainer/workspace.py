"""Apptainer基于远程工作区实现。"""

import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from pydantic import Field, PrivateAttr

from openhands.sdk.logger import get_logger
from openhands.sdk.utils.command import execute_command
from openhands.sdk.workspace import PlatformType, RemoteWorkspace
from openhands.workspace.docker.workspace import (
    check_port_available,
    find_available_tcp_port,
)


logger = get_logger(__name__)


class ApptainerWorkspace(RemoteWorkspace):
    """设置和管理 Apptainer 容器的远程工作区。

    This 工作区创建了一个 Apptainer 运行预构建的容器 OpenHands  Agent Server 图像，等
    待它变得健康，然后提供远程工作区通过容器的
    操作 HTTP  API.

    Apptainer（以前称为 Singularity）是一个不需要 root 访问权限的容器运行时，非常适合
     HPC 和共享计算环境。

    Note: 此类仅适用于预先构建的图像。 它不支持
    从基本图像即时构建图像。

    Example:
        with ApptainerWorkspace(
            server_image="ghcr.io/openhands/agent-server:latest-python"
        ) 作为工作区：
            result = workspace.execute_command("ls -la")
    """

    # 使用默认值覆盖父字段
    working_dir: str = Field(
        default="/workspace",
        description="Working directory inside the container.",
    )
    host: str = Field(
        default="",
        description=("Remote host URL (set automatically during container startup)."),
    )

    # Apptainer-具体配置
    server_image: str | None = Field(
        default=None,
        description="Pre-built agent server image to use.",
    )
    sif_file: str | None = Field(
        default=None,
        description=(
            "Path to existing Apptainer SIF file. If provided, skips image pull. "
            "Mutually exclusive with server_image."
        ),
    )
    host_port: int | None = Field(
        default=None,
        description="Port to bind the container to. If None, finds available port.",
    )
    forward_env: list[str] = Field(
        default_factory=lambda: ["DEBUG", "SESSION_API_KEY", "OH_SESSION_API_KEYS_0"],
        description=(
            "Environment variables to forward to the container. The session "
            "API key variables are forwarded so the sandboxed agent server can "
            "authenticate network-bound requests when it binds 0.0.0.0."
        ),
    )
    mount_dir: str | None = Field(
        default=None,
        description="Optional host directory to mount into the container.",
    )
    extra_bind_mounts: list[str] = Field(
        default_factory=list,
        description=(
            "Additional Apptainer bind mount specs to pass as --bind values. "
            "Use src[:dest[:opts]] syntax. OPENHANDS_APPTAINER_EXTRA_BINDS can "
            "also provide comma-separated bind specs."
        ),
    )
    detach_logs: bool = Field(
        default=True, description="Whether to stream container logs in background."
    )
    platform: PlatformType = Field(
        default="linux/amd64", description="Platform for the Docker image."
    )
    extra_ports: bool = Field(
        default=False,
        description="Whether to expose the additional VSCode port.",
    )
    enable_gpu: bool = Field(
        default=False,
        description="Whether to enable GPU support with --nv.",
    )
    cache_dir: str | None = Field(
        default=None,
        description=(
            "Directory for Apptainer cache and SIF files. "
            "Defaults to ~/.apptainer_cache"
        ),
    )
    use_fakeroot: bool = Field(
        default=True,
        description=(
            "Whether to use --fakeroot for consistent file ownership. "
            "Set to False if fakeroot is not supported in your environment."
        ),
    )

    enable_docker_compat: bool = Field(
        default=True,
        description=(
            "Whether to use --compat for maximum Docker compatibility. "
            "Check this URL for documentation: "
            "https://apptainer.org/docs/user/main/docker_and_oci.html#docker-like-compat-flag"
            " Set to False if you want custom Apptainer behavior."
        ),
    )

    disable_mount_locations: list[str] = Field(
        default=["hostfs", "bind-paths"],
        description=(
            "List of locations to disable mounting for. "
            "Helpful for disabling system-level mounts/binds from apptainer.conf. "
            "Check this URL for documentation: "
            "https://apptainer.org/docs/user/main/bind_paths_and_mounts.html. "
            "Specify locations to disable mounts for custom Apptainer behavior."
        ),
    )
    health_check_timeout: float = Field(
        default=120.0,
        gt=0.0,
        description="Timeout in seconds to wait for container health check to pass.",
    )

    _instance_name: str | None = PrivateAttr(default=None)
    _logs_thread: threading.Thread | None = PrivateAttr(default=None)
    _stop_logs: threading.Event = PrivateAttr(default_factory=threading.Event)
    _sif_path: str = PrivateAttr()
    _process: subprocess.Popen[str] | None = PrivateAttr(default=None)

    def model_post_init(self, context: Any) -> None:
        """设置 Apptainer 容器并初始化远程工作区。"""
        # 验证是否提供了 server_image 或 sif_file 之一这必须在此处完成（而不是在
        # model_validator 中），因为 model_post_init 在 Pydantic 中在 model_validator 之
        # 前运行
        #
        sources = [self.server_image, self.sif_file]
        if sum(x is not None for x in sources) != 1:
            raise ValueError("Exactly one of 'server_image' or 'sif_file' must be set.")

        # 确定端口
        if self.host_port is None:
            self.host_port = find_available_tcp_port()
        else:
            self.host_port = int(self.host_port)

        if not check_port_available(self.host_port):
            raise RuntimeError(f"Port {self.host_port} is not available")

        if self.extra_ports:
            if not check_port_available(self.host_port + 1):
                raise RuntimeError(
                    f"Port {self.host_port + 1} is not available for VSCode"
                )

        # 确保 Apptainer 可用
        apptainer_ver = execute_command(["apptainer", "version"]).returncode
        if apptainer_ver != 0:
            raise RuntimeError(
                "Apptainer is not available. Please install Apptainer from "
                "https://apptainer.org/docs/user/main/quick_start.html"
            )

        # 设置缓存目录
        if self.cache_dir is None:
            self.cache_dir = str(Path.home() / ".apptainer_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

        # 构建或使用现有的 SIF 文件
        if self.sif_file:
            if not Path(self.sif_file).exists():
                raise RuntimeError(f"SIF file not found: {self.sif_file}")
            self._sif_path = self.sif_file
            logger.info("Using existing SIF file: %s", self._sif_path)
        else:
            self._sif_path = self._prepare_sif_image()

        # 运行容器
        self._instance_name = f"agent-server-{uuid.uuid4()}"
        self._start_container()

        # 设置 RemoteWorkspace 使用的主机
        object.__setattr__(self, "host", f"http://localhost:{self.host_port}")
        # Apptainer 默认从环境继承 SESSION_API_KEY 我们需要匹配它（如果存在）
        #
        session_api_key = os.environ.get("SESSION_API_KEY")
        object.__setattr__(self, "api_key", session_api_key)

        # 等待容器健康
        self._wait_for_health(timeout=self.health_check_timeout)
        logger.info("Apptainer workspace is ready at %s", self.host)

        # 现在用容器 URL 初始化父级 RemoteWorkspace
        super().model_post_init(context)

    def _prepare_sif_image(self) -> str:
        """准备 server_image 中的 SIF 图像文件。"""
        if self.server_image is None:
            raise RuntimeError("server_image must be set")

        docker_image = self.server_image

        # 将 Docker 图像转换为 SIF
        assert self.cache_dir is not None, "cache_dir must be set in model_post_init"
        sif_name = docker_image.replace(":", "_").replace("/", "_") + ".sif"
        sif_path = os.path.join(self.cache_dir, sif_name)

        if Path(sif_path).exists():
            logger.info("Using cached SIF file: %s", sif_path)
            return sif_path

        logger.info("Pulling and converting Docker image to SIF: %s", docker_image)
        # 使用 Apptainer pull 直接从 Docker 转换注册表这不需要 Docker 守护进程
        #
        pull_cmd = [
            "apptainer",
            "pull",
            sif_path,
            f"docker://{docker_image}",
        ]
        proc = execute_command(pull_cmd)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Failed to pull and convert Docker image: {proc.stderr}"
            )

        logger.info("SIF file created: %s", sif_path)
        return sif_path

    def _start_container(self) -> None:
        """启动 Apptainer 容器实例。"""
        # 准备环境变量
        env_args: list[str] = []
        for key in self.forward_env:
            if key in os.environ:
                env_args += ["--env", f"{key}={os.environ[key]}"]

        # 准备绑定安装
        bind_args: list[str] = []
        if self.mount_dir:
            mount_path = "/workspace"
            bind_args += ["--bind", f"{self.mount_dir}:{mount_path}"]
            logger.info(
                "Mounting host dir %s to container path %s",
                self.mount_dir,
                mount_path,
            )
        env_extra_binds = [
            item.strip()
            for item in os.getenv("OPENHANDS_APPTAINER_EXTRA_BINDS", "").split(",")
            if item.strip()
        ]
        for bind_spec in [*self.extra_bind_mounts, *env_extra_binds]:
            bind_args += ["--bind", bind_spec]
            logger.info("Adding Apptainer bind mount: %s", bind_spec)

        # 构建容器选项
        container_opts: list[str] = []

        # 添加 fakeroot 以获得一致的文件所有权（用户显示为 root）
        if self.use_fakeroot:
            container_opts.append("--fakeroot")
        if self.enable_docker_compat:
            container_opts.append("--compat")
        if self.enable_gpu:
            container_opts.append("--nv")
        if self.disable_mount_locations:
            for loc in self.disable_mount_locations:
                container_opts += [
                    "--no-mount",
                    loc,
                ]  # 禁用指定的安装位置

        # 运行 Agent Server 使用 Apptainer run 来尊重图像的入口这适用于源和二进制构建目
        # 标使用入口从智能体-server Dockerfile 预配置的
        #
        server_cmd = [
            "apptainer",
            "run",
            *container_opts,
            *env_args,
            *bind_args,
            self._sif_path,
            "--host",
            "0.0.0.0",
            "--port",
            str(self.host_port),
        ]

        # 在单独的进程组中在后台启动服务器进程
        self._process = subprocess.Popen(
            server_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )

        # 可选择在后台流式传输日志
        if self.detach_logs:
            self._logs_thread = threading.Thread(target=self._stream_logs, daemon=True)
            self._logs_thread.start()

    def _stream_logs(self) -> None:
        """在后台将容器日志流式传输到标准输出。"""
        if not self._process or not self._process.stdout:
            return
        try:
            for line in iter(self._process.stdout.readline, ""):
                if self._stop_logs.is_set():
                    break
                if line:
                    sys.stdout.write(f"[APPTAINER] {line}")
                    sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"Error streaming apptainer logs: {e}\n")
        finally:
            try:
                self._stop_logs.set()
            except Exception:
                pass

    def _wait_for_health(self, *, timeout: float) -> None:
        """等待容器变得健康。"""
        start = time.time()
        health_url = f"http://127.0.0.1:{self.host_port}/health"

        while time.time() - start < timeout:
            try:
                with urlopen(health_url, timeout=1.0) as resp:
                    if 200 <= getattr(resp, "status", 200) < 300:
                        return
            except Exception:
                pass

            # 检查进程是否仍在运行
            if self._process and self._process.poll() is not None:
                # 进程已终止
                raise RuntimeError(
                    f"Container process stopped unexpectedly with "
                    f"exit code {self._process.returncode}"
                )

            time.sleep(1)
        raise RuntimeError("Container failed to become healthy in time")

    def __enter__(self) -> "ApptainerWorkspace":
        """上下文管理器条目 - 返回工作区本身。"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """上下文管理器 exit - 清理 Apptainer 容器。"""
        self.cleanup()

    def __del__(self) -> None:
        """当工作区被破坏时清理Apptainer容器。"""
        # 防止在解释器关闭期间访问私有属性
        if getattr(self, "__pydantic_private__", None) is not None:
            self.cleanup()

    def cleanup(self) -> None:
        """停止并移除 Apptainer 容器。"""
        if getattr(self, "_instance_name", None):
            # 停止日志流式传输
            self._stop_logs.set()
            if self._logs_thread and self._logs_thread.is_alive():
                self._logs_thread.join(timeout=2)

            # 如果正在运行，则终止服务器进程
            if self._process:
                try:
                    logger.info("Terminating Apptainer process...")
                    pgid = os.getpgid(self._process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                    self._process.wait(timeout=5)
                except Exception as e:
                    logger.warning("Error terminating process: %s", e)
                    try:
                        pgid = os.getpgid(self._process.pid)
                        os.killpg(pgid, signal.SIGKILL)
                        self._process.wait(timeout=2)
                    except Exception:
                        pass

            self._process = None
            self._instance_name = None
