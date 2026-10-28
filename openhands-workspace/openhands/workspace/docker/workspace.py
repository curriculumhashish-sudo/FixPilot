"""Docker基于远程工作区实现。"""

import os
import subprocess
import sys
import threading
import time
import uuid
from typing import Any
from urllib.request import urlopen

from pydantic import Field, PrivateAttr, model_validator

from openhands.sdk.logger import get_logger
from openhands.sdk.utils.command import execute_command
from openhands.sdk.workspace import PlatformType, RemoteWorkspace


logger = get_logger(__name__)


def check_port_available(port: int) -> bool:
    """检查端口是否可用于绑定。"""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("0.0.0.0", port))
        return True
    except OSError:
        time.sleep(0.1)
        return False
    finally:
        sock.close()


def find_available_tcp_port(
    min_port: int = 30000, max_port: int = 39999, max_attempts: int = 50
) -> int:
    """查找指定范围内可用的TCP端口。"""
    import random

    rng = random.SystemRandom()
    ports = list(range(min_port, max_port + 1))
    rng.shuffle(ports)

    for port in ports[:max_attempts]:
        if check_port_available(port):
            return port
    return -1


class DockerWorkspace(RemoteWorkspace):
    """设置和管理 Docker 容器的远程工作区。

    工作区这个 Docker 创建了一个运行预构建的 OpenHands Agent Server 镜像的容器，等待
    它变得健康，然后通过容器的 HTTP API 提供远
    程工作区操作。

    Note: 此类仅适用于预先构建的图像。 即时构建图像
    from a base image, use DockerDevWorkspace instead.

    Example:
        with DockerWorkspace(
            server_image="ghcr.io/openhands/agent-server:latest"
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

    # Docker-具体配置
    server_image: str | None = Field(
        default="ghcr.io/openhands/agent-server:latest-python",
        description="Pre-built agent server image to use.",
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
    volumes: list[str] = Field(
        default_factory=list,
        description="Additional volume mounts for the Docker container.",
    )
    detach_logs: bool = Field(
        default=True, description="Whether to stream Docker logs in background."
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
        description="Whether to enable GPU support with --gpus all.",
    )
    cleanup_image: bool = Field(
        default=False,
        description="Whether to delete the Docker image when cleaning up workspace.",
    )
    network: str | None = Field(
        default=None,
        description="Connect a container to the specified Docker network.",
    )
    health_check_timeout: float = Field(
        default=120.0,
        gt=0.0,
        description="Timeout in seconds to wait for container health check to pass.",
    )

    _container_id: str | None = PrivateAttr(default=None)
    _image_name: str | None = PrivateAttr(default=None)
    _logs_thread: threading.Thread | None = PrivateAttr(default=None)
    _stop_logs: threading.Event = PrivateAttr(default_factory=threading.Event)

    @model_validator(mode="before")
    @classmethod
    def _reject_removed_mount_dir(cls, data: Any) -> Any:
        if isinstance(data, dict) and "mount_dir" in data:
            raise ValueError(
                "DockerWorkspace.mount_dir has been removed; use "
                "volumes=['/host/dir:/workspace'] instead."
            )
        return data

    @model_validator(mode="after")
    def _validate_server_image(self):
        """直接使用 DockerWorkspace 时请确保设置 server_image。"""
        if self.__class__ is DockerWorkspace and self.server_image is None:
            raise ValueError("server_image must be provided")
        return self

    def model_post_init(self, context: Any) -> None:
        """设置 Docker 容器并初始化远程工作区。"""
        # 子类应该调用 get_image() 来获取要使用的映像这允许它们在容器启动之前构建或准备
        # 映像
        #
        image = self.get_image()
        self._start_container(image, context)

    def get_image(self) -> str:
        """获取用于容器的 Docker 图像。

        子类可以重写它以提供自定义图像分辨率逻辑（e.g.，即时构建图像）。

        Returns:
            要使用的 Docker 图像标签。
        """
        if self.server_image is None:
            raise ValueError("server_image must be set")
        return self.server_image

    def _start_container(self, image: str, context: Any) -> None:
        """使用给定图像启动 Docker 容器。

        此方法处理所有容器生命周期：端口分配、Docker 验证、容器创建、运行状况检查和
        RemoteWorkspace 初始化。

        Args:
            image: 要使用的 Docker 图像标签。
            context: model_post_init 中的 Pydantic 上下文。
        """
        # 存储用于清理的图像名称
        self._image_name = image

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

        # 确保 Docker 可用
        docker_ver = execute_command(["docker", "version"]).returncode
        if docker_ver != 0:
            raise RuntimeError(
                "Docker is not available. Please install and start "
                "Docker Desktop/daemon."
            )

        # 准备 Docker 运行标志
        flags: list[str] = []
        for key in self.forward_env:
            if key in os.environ:
                flags += ["-e", f"{key}={os.environ[key]}"]

        for volume in self.volumes:
            flags += ["-v", volume]
            logger.info(f"Adding volume mount: {volume}")

        ports = ["-p", f"127.0.0.1:{self.host_port}:8000"]
        if self.extra_ports:
            ports += [
                "-p",
                f"127.0.0.1:{self.host_port + 1}:8001",  # VSCode
            ]
        flags += ports

        # 添加 GPU 支持（如果启用）
        if self.enable_gpu:
            flags += ["--gpus", "all"]

        # 将容器连接到指定的Docker网络
        if self.network:
            flags += ["--network", self.network]

        # 运行容器
        run_cmd = [
            "docker",
            "run",
            "-d",
            "--platform",
            self.platform,
            "--rm",
            "--ulimit",
            "nofile=65536:65536",  # 防止“打开文件过多”错误
            "--name",
            f"agent-server-{uuid.uuid4()}",
            *flags,
            image,
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ]
        proc = execute_command(run_cmd)
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to run docker container: {proc.stderr}")

        self._container_id = proc.stdout.strip()
        logger.info(f"Started container: {self._container_id}")

        # 可选择在后台流式传输日志
        if self.detach_logs:
            self._logs_thread = threading.Thread(
                target=self._stream_docker_logs, daemon=True
            )
            self._logs_thread.start()

        # 设置 RemoteWorkspace 使用的主机容器公开端口 8000，映射到 self.host_port 覆盖父
        # 主机的初始化
        #
        if not self.host:
            object.__setattr__(self, "host", f"http://127.0.0.1:{self.host_port}")
        # 按照 Agent Server 在这个容器中的顺序解决 (`config.py`: V1 的
        # `OH_SESSION_API_KEYS_0` 变量由 env 解析器读取，V0 `SESSION_API_KEY` 只是一个回
        # 退方案在 V1 不存在时使用)。 两者都由 `forward_env` 转发到容器中，因此这里首选
        # V0 将发送服务器拒绝的密钥。
        #
        session_api_key = os.environ.get(
            "OH_SESSION_API_KEYS_0", os.environ.get("SESSION_API_KEY")
        )
        object.__setattr__(self, "api_key", session_api_key)

        # 等待容器健康
        self._wait_for_health(timeout=self.health_check_timeout)
        logger.info(f"Docker workspace is ready at {self.host}")

        # 现在用容器 URL 初始化父级 RemoteWorkspace
        super().model_post_init(context)

    def _stream_docker_logs(self) -> None:
        """Stream Docker 在后台记录到标准输出。"""
        if not self._container_id:
            return
        try:
            p = subprocess.Popen(
                ["docker", "logs", "-f", self._container_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if p.stdout is None:
                return
            for line in iter(p.stdout.readline, ""):
                if self._stop_logs.is_set():
                    break
                if line:
                    sys.stdout.write(f"[DOCKER] {line}")
                    sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"Error streaming docker logs: {e}\n")
        finally:
            try:
                self._stop_logs.set()
            except Exception:
                pass

    def _wait_for_health(self, *, timeout: float) -> None:
        """等待 Docker 容器恢复正常。"""
        start = time.time()
        # 我们可以根据self.host（如果可用）构建健康状况URL，或者回退方案到本地主机
        #
        base_url = self.host.rstrip("/")
        health_url = f"{base_url}/health"

        while time.time() - start < timeout:
            try:
                with urlopen(health_url, timeout=1.0) as resp:
                    if 200 <= getattr(resp, "status", 200) < 300:
                        return
            except Exception:
                pass

            # 检查容器是否仍在运行
            if self._container_id:
                ps = execute_command(
                    [
                        "docker",
                        "inspect",
                        "-f",
                        "{{.State.Running}}",
                        self._container_id,
                    ]
                )
                if ps.stdout.strip() != "true":
                    logs = execute_command(["docker", "logs", self._container_id])
                    msg = (
                        "Container stopped unexpectedly. Logs:\n"
                        f"{logs.stdout}\n{logs.stderr}"
                    )
                    raise RuntimeError(msg)
            time.sleep(1)
        raise RuntimeError("Container failed to become healthy in time")

    def __enter__(self) -> "DockerWorkspace":
        """上下文管理器条目 - 返回工作区本身。"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """上下文管理器 exit - 清理 Docker 容器。"""
        self.cleanup()

    def __del__(self) -> None:
        """当工作区被破坏时清理Docker容器。"""
        try:
            object.__getattribute__(self, "__pydantic_private__")
        except AttributeError:
            return
        self.cleanup()

    def cleanup(self) -> None:
        """停止并移除 Docker 容器。"""
        if self._container_id:
            # 停止日志流式传输
            self._stop_logs.set()
            if self._logs_thread and self._logs_thread.is_alive():
                self._logs_thread.join(timeout=2)

            # 停止并移除容器
            logger.info(f"Stopping container: {self._container_id}")
            execute_command(["docker", "stop", self._container_id])
            self._container_id = None

        # （可选）删除 Docker 图像
        if self.cleanup_image and self._image_name:
            logger.info(f"Deleting Docker image: {self._image_name}")
            result = execute_command(["docker", "rmi", "-f", self._image_name])
            if result.returncode == 0:
                logger.info(f"Successfully deleted image: {self._image_name}")
            else:
                logger.warning(
                    f"Failed to delete image {self._image_name}: {result.stderr}"
                )
            self._image_name = None

    def pause(self) -> None:
        """暂停 Docker 容器以节省资源。

        使用 `docker pause` 冻结容器中的所有进程而不停止它。 稍后可以使用 `resume()`
        恢复容器。

        Raises:
            RuntimeError: 如果容器没有运行或者暂停失败。
        """
        if not self._container_id:
            raise RuntimeError("Cannot pause: container is not running")

        logger.info(f"Pausing container: {self._container_id}")
        result = execute_command(["docker", "pause", self._container_id])
        if result.returncode != 0:
            raise RuntimeError(f"Failed to pause container: {result.stderr}")
        logger.info(f"Container paused: {self._container_id}")

    def resume(self) -> None:
        """恢复暂停的 Docker 容器。

        使用 `docker unpause` 恢复容器中的所有进程。

        Raises:
            RuntimeError: 如果容器没有运行或者恢复失败。
        """
        if not self._container_id:
            raise RuntimeError("Cannot resume: container is not running")

        logger.info(f"Resuming container: {self._container_id}")
        result = execute_command(["docker", "unpause", self._container_id])
        if result.returncode != 0:
            raise RuntimeError(f"Failed to resume container: {result.stderr}")

        # 等待容器健康
        self._wait_for_health(timeout=self.health_check_timeout)
        logger.info(f"Container resumed: {self._container_id}")
