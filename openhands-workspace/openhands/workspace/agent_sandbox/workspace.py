"""智能体-基于沙箱 (Kubernetes) 的远程工作区实现。

在由 pod 管理的 pod 内运行 OpenHands Agent Server
`kubernetes-sigs/agent-sandbox <https://github.com/kubernetes-sigs/agent-sandbox>`_控
制器
。 该 Pod 从 ``SandboxWarmPool``（预热池时为秒级）获取，这消除了 Docker 和托管运行时
后端因每会话支付而产生的容器冷启动延迟。

与其他远程后端相比，该后端增加了：

* **温池**：``SandboxWarmPool``根据要求分发一个已经运行的 Pod。
* **本机暂停/恢复**：``pause()``和``resume()``翻转沙箱
  ``spec.operatingMode`` 位于 ``Suspended`` 和 ``Running`` 之间。 对于持久卷，工作区
  状态在挂起后仍然存在。
* **强隔离**：Pod 可以通过 ``SandboxTemplate`` 上的 ``runtimeClass`` 设置在 gVisor 或
 Kata 下运行，这是一种基
础设施选择，而不是 Python 基础设施选择。

需要可选的依赖项：:

    pip install openhands-workspace[agent-sandbox]
"""

import os
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Literal
from urllib.request import urlopen

from pydantic import Field, PrivateAttr

from openhands.sdk.logger import get_logger
from openhands.sdk.workspace import RemoteWorkspace
from openhands.workspace.docker.workspace import (
    check_port_available,
    find_available_tcp_port,
)


logger = get_logger(__name__)


class AgentSandboxWorkspace(RemoteWorkspace):
    """远程工作区由 Kubernetes-sigs/agent-sandbox Sandbox pod 支持。

    声称运行中的 pod 是  OpenHands  Agent Server 从一个 ``SandboxWarmPool``连接到它
    HTTP它还管理其生命周期（暂停
    /恢复/删除） 智能体-sandbox自定义资源。

    支持两种连接方式：

    * ``port_forward`` (默认) 启动了 ``kubectl port-forward`` 到 pod，因此它可以在笔
    记本电脑上与本地的 kind 或
     minikube 集群进行交互，也可以与你的 kubeconfig 可以访问的任何集群进行交互。
    * ``direct`` 表示您自己提供 ``host``，例如 ``sandbox-router`` 或网关 URL，或者当
    OpenHands 在集群中运行时提
    供集群内 DNS 名称。 没有启动端口转发。

    Example:
        with AgentSandboxWorkspace(warmpool="openhands-pool") as workspace:
            result = workspace.execute_command("ls -la")
    """

    # 使用默认值覆盖父字段
    working_dir: str = Field(
        default="/workspace",
        description="Working directory inside the sandbox pod.",
    )
    host: str = Field(
        default="",
        description=(
            "Agent server URL. Set automatically in 'port_forward' mode; must be "
            "provided by the caller in 'direct' mode."
        ),
    )

    # 智能体-沙箱配置
    warmpool: str = Field(
        description="Name of the SandboxWarmPool to claim the pod from.",
    )
    namespace: str = Field(
        default="default",
        description="Kubernetes namespace holding the warm pool and the sandbox pod.",
    )
    server_port: int = Field(
        default=8000,
        description="Port the agent server listens on inside the pod.",
    )
    connection: Literal["port_forward", "direct"] = Field(
        default="port_forward",
        description="How to reach the agent server: local kubectl port-forward, or a "
        "caller-provided 'host' URL.",
    )
    host_port: int | None = Field(
        default=None,
        description="Local port for port-forward. If None, an available port is used.",
    )
    kube_context: str | None = Field(
        default=None,
        description="kubectl context to use for port-forward (defaults to current).",
    )
    sandbox_ready_timeout: int = Field(
        default=180,
        description="Seconds to wait for the Sandbox to reach the Ready condition.",
    )
    health_check_timeout: float = Field(
        default=120.0,
        gt=0.0,
        description="Seconds to wait for the agent server /health endpoint to pass.",
    )
    shutdown_after_seconds: int | None = Field(
        default=None,
        description="Optional TTL; the controller auto-deletes the claim after this "
        "many seconds (a safety net against leaked sandboxes).",
    )
    labels: dict[str, str] | None = Field(
        default=None,
        description="Kubernetes labels to attach to the SandboxClaim object.",
    )
    pod_labels: dict[str, str] | None = Field(
        default=None,
        description="Labels stamped onto the running pod (readable via the Downward "
        "API from inside the sandbox).",
    )
    pod_annotations: dict[str, str] | None = Field(
        default=None,
        description="Annotations stamped onto the running pod.",
    )
    detach_logs: bool = Field(
        default=True,
        description="Whether to stream port-forward output in the background.",
    )

    _sandbox: Any = PrivateAttr(default=None)  # k8s_agent_sandbox.Sandbox 手柄
    _sb_client: Any = PrivateAttr(default=None)  # k8s_agent_sandbox.SandboxClient
    _pf_process: subprocess.Popen[str] | None = PrivateAttr(default=None)
    _logs_thread: threading.Thread | None = PrivateAttr(default=None)
    _stop_logs: threading.Event = PrivateAttr(default_factory=threading.Event)
    # 调用者的显式 host_port（如果有）。 `host_port` 本身跟踪当前正在使用的端口，因此它
    # 不能兼作重新连接时的首选项。
    #
    _preferred_host_port: int | None = PrivateAttr(default=None)

    def model_post_init(self, context: Any) -> None:
        """声明一个沙盒 Pod，连接到 Agent Server，然后初始化。"""
        # 在此处验证连接配置（不在 model_validator 中）以匹配同级后端并避免 Pydantic 验
        # 证器/初始化后排序意外。
        #
        if self.connection == "direct" and not self.host:
            raise ValueError(
                "connection='direct' requires 'host' to be set to the agent-server URL."
            )

        self._preferred_host_port = self.host_port

        try:
            import k8s_agent_sandbox  # type: ignore[import-not-found]
        except ImportError as e:
            raise ImportError(
                "AgentSandboxWorkspace requires the 'agent-sandbox' extra. Install "
                "with: pip install openhands-workspace[agent-sandbox]"
            ) from e

        # 1) 从温水池中领取一个豆荚（在沙箱准备好之前会阻塞）。
        self._sb_client = k8s_agent_sandbox.SandboxClient()
        logger.info(
            "Claiming a sandbox from warm pool %r in namespace %r...",
            self.warmpool,
            self.namespace,
        )
        self._sandbox = self._sb_client.create_sandbox(
            warmpool=self.warmpool,
            namespace=self.namespace,
            sandbox_ready_timeout=self.sandbox_ready_timeout,
            labels=self.labels,
            shutdown_after_seconds=self.shutdown_after_seconds,
            pod_labels=self.pod_labels,
            pod_annotations=self.pod_annotations,
        )
        logger.info(
            "Sandbox %r is ready (claim %r).",
            self._sandbox.sandbox_id,
            self._sandbox.claim_name,
        )

        # 从这里开始，所有的事情都必须清理失败的声明：构造函数抛出意味着调用者永远得不到
        # 一个对象来关闭，因此声明及其容器将泄漏直到垃圾回收，或者永远，
        # shutdown_after_seconds 时默认为 None。
        #
        try:
            # 2) 建立与 Agent Server 的连接并等待健康。
            if self.connection == "port_forward":
                self._connect_port_forward_with_retry(
                    preferred_port=self._preferred_host_port
                )
            else:
                # 'direct': self.host 由调用者提供。
                self._wait_for_health(timeout=self.health_check_timeout)
            logger.info("agent-sandbox workspace is ready at %s", self.host)

            # 3) 针对 Agent Server URL 初始化父级 RemoteWorkspace。
            super().model_post_init(context)
        except Exception:
            self.cleanup()
            raise

    def _connect_port_forward_with_retry(
        self, attempts: int = 8, *, preferred_port: int | None = None
    ) -> None:
        """启动端口转发并等待运行状况，重试暂时性故障。

        恢复后，Pod 的网络命名空间仍可能处于搅动状态，因此 kubectl port-forward 可能
        会因“network 命名空间 ... 已关闭”。 一
        个倒地的前锋立即退出，所以重试后退逐步进行——否则预算很快就会耗尽，甚至在新启
        动的pod之前就已经耗尽。

        ``preferred_port`` 仅在第一次尝试时获得荣誉； pass None（默认值，在恢复时使用
        ）始终采用新分配的端口，因为前一个会话的端口可能仍
        在 TIME_WAIT 中。
        """
        last_error: Exception | None = None
        for i in range(attempts):
            # 第一次尝试时尊重调用者提供的端口； 自动选取重试。
            self.host_port = preferred_port if i == 0 else None
            try:
                self._start_port_forward()
                self._wait_for_health(timeout=self.health_check_timeout)
                return
            except Exception as e:
                last_error = e
                logger.warning(
                    "Agent server not reachable (attempt %d/%d): %s",
                    i + 1,
                    attempts,
                    e,
                )
                self._stop_port_forward()
                time.sleep(min(2 * (i + 1), 10))
        raise RuntimeError(
            f"Could not reach agent server after {attempts} attempts: {last_error}"
        )

    def _resolve_pod_name(self) -> str:
        """从实时 Sandbox 对象中读取当前的 Pod 名称。

        pod 名称在暂停/恢复周期内可能会改变，因此总是重新读取它，而不是使用
        ``Sandbox.get_pod_name()``，后者在 handle 的生命
        周期内缓存第一次值。 仅使用公共客户端API； 如果 ``k8s_agent_sandbox`` 增加公
        共刷新 (e.g.
        ``get_pod_name(refresh=True)``），这个可以按照它。
        """
        from k8s_agent_sandbox.constants import (  # type: ignore[import-not-found]
            POD_NAME_ANNOTATION,
        )

        sandbox_object = (
            self._sb_client.k8s_helper.get_sandbox(
                self._sandbox.sandbox_id, self.namespace
            )
            or {}
        )
        annotations = (sandbox_object.get("metadata") or {}).get("annotations") or {}
        return annotations.get(POD_NAME_ANNOTATION) or self._sandbox.sandbox_id

    def _start_port_forward(self) -> None:
        """启动（或重新启动）kubectl 端口转发到沙箱 pod。"""
        if self.host_port is None:
            self.host_port = find_available_tcp_port()
        elif not check_port_available(self.host_port):
            raise RuntimeError(f"Port {self.host_port} is not available")

        pod = self._resolve_pod_name()

        cmd = ["kubectl", "port-forward"]
        if self.kube_context:
            cmd += ["--context", self.kube_context]
        cmd += [
            "-n",
            self.namespace,
            f"pod/{pod}",
            f"{self.host_port}:{self.server_port}",
        ]
        logger.info("Starting port-forward: %s", " ".join(cmd))
        self._stop_logs = threading.Event()
        self._pf_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        object.__setattr__(self, "host", f"http://127.0.0.1:{self.host_port}")

        if self.detach_logs:
            self._logs_thread = threading.Thread(target=self._stream_logs, daemon=True)
            self._logs_thread.start()

    def _stream_logs(self) -> None:
        """在后台将端口转发输出流式传输到标准输出。"""
        if not self._pf_process or not self._pf_process.stdout:
            return
        try:
            for line in iter(self._pf_process.stdout.readline, ""):
                if self._stop_logs.is_set():
                    break
                if line:
                    sys.stdout.write(f"[PORT-FORWARD] {line}")
                    sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"Error streaming port-forward logs: {e}\n")
        finally:
            self._stop_logs.set()

    def _wait_for_health(self, *, timeout: float) -> None:
        """等待Agent Server/health端点返回成功。"""
        start = time.time()
        health_url = f"{self.host.rstrip('/')}/health"
        while time.time() - start < timeout:
            try:
                with urlopen(health_url, timeout=1.0) as resp:
                    if 200 <= getattr(resp, "status", 200) < 300:
                        return
            except Exception:
                pass
            if self._pf_process and self._pf_process.poll() is not None:
                raise RuntimeError(
                    "kubectl port-forward exited unexpectedly with code "
                    f"{self._pf_process.returncode}"
                )
            time.sleep(1)
        raise RuntimeError("agent server failed to become healthy in time")

    def _patch_operating_mode(self, mode: str) -> None:
        """修补沙箱 spec.operatingMode（“正在运行”或“已暂停”）。

        TODO: 智能体-sandbox #1160（声明级空闲生命周期）和#1296
        （流量触发的简历）将使这成为索赔级别的问题； 一旦他们着陆，暂停/恢复应该移至
        声明 API，而不是直接修补沙箱。
        """
        from k8s_agent_sandbox.constants import (  # type: ignore[import-not-found]
            SANDBOX_API_GROUP,
            SANDBOX_API_VERSION,
            SANDBOX_PLURAL_NAME,
        )

        self._sb_client.k8s_helper.custom_objects_api.patch_namespaced_custom_object(
            group=SANDBOX_API_GROUP,
            version=SANDBOX_API_VERSION,
            namespace=self.namespace,
            plural=SANDBOX_PLURAL_NAME,
            name=self._sandbox.sandbox_id,
            body={"spec": {"operatingMode": mode}},
        )

    def pause(self) -> None:
        """暂停沙箱以节省资源。

        将沙箱``operatingMode``设置为``Suspended``； 控制器终止 pod，同时保留任何持久
        卷。 继续使用
        ``resume()``.
        """
        if self._sandbox is None:
            raise RuntimeError("Cannot pause: no active sandbox")
        logger.info("Suspending sandbox %r...", self._sandbox.sandbox_id)
        self._stop_port_forward()
        self._patch_operating_mode("Suspended")

    def resume(self) -> None:
        """恢复暂停的沙箱并重新连接到Agent Server。"""
        if self._sandbox is None:
            raise RuntimeError("Cannot resume: no active sandbox")
        logger.info("Resuming sandbox %r...", self._sandbox.sandbox_id)
        self._patch_operating_mode("Running")
        self._sb_client.k8s_helper.wait_for_sandbox_ready(
            self._sandbox.sandbox_id, self.namespace, self.sandbox_ready_timeout
        )
        if self.connection == "port_forward":
            # 在新的本地端口上重新连接（旧端口可能位于 TIME_WAIT 中）并重建 HTTP 客户端
            # ，使其以新主机 URL 为目标。
            #
            self._connect_port_forward_with_retry(preferred_port=None)
            self.reset_client()
        else:
            self._wait_for_health(timeout=self.health_check_timeout)
        logger.info("Sandbox %r resumed at %s", self._sandbox.sandbox_id, self.host)

    def _stop_port_forward(self) -> None:
        """如果正在运行，请停止 kubectl port-forward 子进程。"""
        if self._pf_process is None:
            return
        self._stop_logs.set()
        if self._logs_thread and self._logs_thread.is_alive():
            self._logs_thread.join(timeout=2)
        try:
            os.killpg(os.getpgid(self._pf_process.pid), signal.SIGTERM)
            self._pf_process.wait(timeout=5)
        except Exception:
            try:
                os.killpg(os.getpgid(self._pf_process.pid), signal.SIGKILL)
                self._pf_process.wait(timeout=2)
            except Exception:
                pass
        self._pf_process = None

    def __enter__(self) -> "AgentSandboxWorkspace":
        """上下文管理器条目 - 返回工作区本身。"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """发送完成回调并拆除沙箱。"""
        try:
            super().__exit__(exc_type, exc_val, exc_tb)
        finally:
            self.cleanup()

    def __del__(self) -> None:
        """当工作区被垃圾回收时尽最大努力进行清理。"""
        try:
            if getattr(self, "__pydantic_private__", None) is not None:
                self.cleanup()
        except Exception:
            # 切勿从 __del__ (e.g. 口译员关闭期间）。
            pass

    def cleanup(self) -> None:
        """停止端口转发并删除 SandboxClaim（幂等）。"""
        self._stop_port_forward()
        sandbox = getattr(self, "_sandbox", None)
        if sandbox is not None:
            try:
                logger.info("Terminating sandbox %r...", sandbox.sandbox_id)
                sandbox.terminate()
            except Exception as e:
                logger.warning("Error terminating sandbox: %s", e)
            self._sandbox = None
