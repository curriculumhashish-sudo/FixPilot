"""VSCode 用于管理 OpenVSCode 服务器的 Agent Server 服务。"""

import asyncio
import os
import signal
from pathlib import Path
from urllib.parse import quote, urlencode

from openhands.sdk.logger import get_logger
from openhands.sdk.utils import sanitized_env


logger = get_logger(__name__)


class VSCodeService:
    """管理VSCode服务器启动和token生成的服务。"""

    def __init__(
        self,
        port: int = 8001,
        connection_token: str | None = None,
        server_base_path: str | None = None,
    ):
        """初始化 VSCode 服务。

        Args:
            port: 运行 VSCode 服务器的端口（默认：8001）
            workspace_path: 工作区目录的路径
            create_workspace: 如果没有则是否创建工作区目录
                存在
            server_base_path: 服务器的基本路径（用于基于路径的路由）
        """
        self.port: int = port
        self.connection_token: str | None = connection_token
        self.server_base_path: str | None = server_base_path
        self.process: asyncio.subprocess.Process | None = None
        self.openvscode_server_root: Path = Path("/openhands/.openvscode-server")
        self.extensions_dir: Path = self.openvscode_server_root / "extensions"

    async def start(self) -> bool:
        """启动 VSCode 服务器。

        Returns:
            True 如果启动成功，False 否则
        """
        try:
            # 检查 VSCode 服务器二进制是否存在
            if not self._check_vscode_available():
                logger.warning(
                    "VSCode server binary not found, VSCode will be disabled"
                )
                return False

            # 如果尚未设置，则生成连接 token
            if self.connection_token is None:
                self.connection_token = os.urandom(32).hex()

            # 检查端口是否可用
            if not await self._is_port_available():
                logger.warning(
                    f"Port {self.port} is not available, VSCode will be disabled"
                )
                return False

            # 开始 VSCode 带有扩展的服务器
            await self._start_vscode_process()

            logger.info(f"VSCode server started successfully on port {self.port}")
            return True

        except Exception as e:
            logger.error(f"Failed to start VSCode server: {e}")
            return False

    async def stop(self) -> None:
        """停止 VSCode 服务器。"""
        if self.process:
            try:
                self._signal_process_group(signal.SIGTERM)
                await asyncio.wait_for(self._wait_for_exit(), timeout=5.0)
                logger.info("VSCode server stopped successfully")
            except TimeoutError:
                logger.warning("VSCode server did not stop gracefully, killing process")
                self._signal_process_group(signal.SIGKILL)
                await self.process.wait()
            except Exception as e:
                logger.error(f"Error stopping VSCode server: {e}")
            finally:
                self.process = None

    async def set_connection_token(self, connection_token: str) -> None:
        """使用新连接重新启动正在运行的服务器 token。

        openvscode-server 在启动时只读取 token，因此服务器会被重新停止和启动。 一个未
        运行的服务器会保留其 token，因此
        ``get_vscode_url`` 不会广播一个不存在的服务器（例如，在没有 VSCode 的图像中）
        。
        """
        if not self.is_running() or connection_token == self.connection_token:
            return
        self.connection_token = connection_token
        await self.stop()
        await self.start()

    def get_vscode_url(
        self,
        base_url: str | None = None,
        workspace_dir: str = "workspace",
    ) -> str | None:
        """获取 VSCode URL 身份验证 token。

        配置 ``server_base_path`` 时，服务器仅在该前缀下应答（它被传递到 openvscode-
        server 作为
        ``--server-base-path``)，因此返回的URL中包含前缀。 如果没有它，基于路径的路由
        部署将被通告到服务器不提供服务的根 URL。

        Args:
            base_url: URL 服务器的基础 VSCode
            workspace_dir: 工作区目录的路径

        Returns:
            VSCode URL 与 token 或 None（如果服务器未运行）
        """
        # 密钥服务器在 start() 运行之前播种 token，因此单独的 token 并不意味着服务器可以
        # 打开。
        #
        if self.connection_token is None or not self.is_running():
            return None

        if base_url is None:
            base_url = f"http://localhost:{self.port}"

        base = base_url.rstrip("/")
        if self.server_base_path:
            base = f"{base}/{self.server_base_path.strip('/')}"

        # 对值进行编码，使其成为包含“&”、“#”、“?”的路径或空格解码回同一文件夹； '/' 保持
        # 可读。
        #
        query = urlencode(
            {"tkn": self.connection_token, "folder": workspace_dir},
            quote_via=quote,
            safe="/",
        )
        return f"{base}/?{query}"

    def is_running(self) -> bool:
        """检查 VSCode 服务器是否运行。

        Returns:
            True 如果正在运行，False 否则
        """
        return self.process is not None and self.process.returncode is None

    def _check_vscode_available(self) -> bool:
        """检查 VSCode 服务器二进制是否可用。

        Returns:
            True 如果可用，False 否则
        """
        vscode_binary = self.openvscode_server_root / "bin" / "openvscode-server"
        return vscode_binary.exists() and vscode_binary.is_file()

    async def _is_port_available(self) -> bool:
        """检查指定端口是否可用。

        Returns:
            True 如果端口可用，False 否则
        """
        try:
            # 尝试绑定端口
            server = await asyncio.start_server(
                lambda _r, _w: None, "localhost", self.port
            )
            server.close()
            await server.wait_closed()
            return True
        except OSError:
            return False

    def _signal_process_group(self, sig: signal.Signals) -> None:
        """向启动器脚本及其运行的节点服务器发出信号。

        启动器将节点作为子节点运行，而不是执行它，因此仅向脚本发出信号会使节点运行并
        保留端口。 该脚本引导其自己的进程组（``start_new_session``
        ），因此即使脚本本身退出后，其 pid 仍然是组 id。
        """
        if self.process is None:
            return
        try:
            os.killpg(self.process.pid, sig)
        except ProcessLookupError:
            pass

    async def _wait_for_exit(self) -> None:
        """等待启动器退出并等待节点释放端口。"""
        if self.process is None:
            return
        await self.process.wait()
        while not await self._is_port_available():
            await asyncio.sleep(0.1)

    async def _start_vscode_process(self) -> None:
        """启动 VSCode 服务器进程。"""
        extensions_arg = (
            f"--extensions-dir {self.extensions_dir} "
            if self.extensions_dir.exists()
            else ""
        )
        base_path_arg = (
            f"--server-base-path {self.server_base_path} "
            if self.server_base_path
            else ""
        )
        cmd = (
            f"exec {self.openvscode_server_root}/bin/openvscode-server "
            f"--host 0.0.0.0 "
            f"--connection-token {self.connection_token} "
            f"--port {self.port} "
            f"{extensions_arg}"
            f"{base_path_arg}"
            f"--disable-workspace-trust\n"
        )

        # 在自己的进程组中启动进程，因此 stop() 可以与启动器脚本一起向节点发出信号。
        #
        self.process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=sanitized_env(),
            start_new_session=True,
        )

        # 等待服务器启动（查找启动消息）
        await self._wait_for_startup()

    async def _wait_for_startup(self) -> None:
        """等待VSCode服务器启动。"""
        if not self.process or not self.process.stdout:
            return

        try:
            # 读取输出，直到我们看到服务器准备就绪
            timeout = 30  # 30 秒超时
            start_time = asyncio.get_event_loop().time()

            while (
                self.process.returncode is None
                and (asyncio.get_event_loop().time() - start_time) < timeout
            ):
                try:
                    line_bytes = await asyncio.wait_for(
                        self.process.stdout.readline(), timeout=1.0
                    )
                    if not line_bytes:
                        break

                    line = line_bytes.decode("utf-8", errors="ignore").strip()
                    logger.debug(f"VSCode server output: {line}")

                    # 寻找启动指标
                    if "Web UI available at" in line or "Server bound to" in line:
                        logger.info("VSCode server startup detected")
                        break

                except TimeoutError:
                    continue

        except Exception as e:
            logger.warning(f"Error waiting for VSCode startup: {e}")


# 全局 VSCode 服务实例
_vscode_service: VSCodeService | None = None


def get_vscode_service() -> VSCodeService | None:
    """获取全局 VSCode 服务实例。

    Returns:
        VSCode 如果启用，None 如果禁用
    """
    global _vscode_service
    if _vscode_service is None:
        from openhands.agent_server.config import (
            get_default_config,
        )

        config = get_default_config()

        if not config.enable_vscode:
            logger.info("VSCode is disabled in configuration")
            return None
        else:
            connection_token = None
            if config.session_api_keys:
                connection_token = config.session_api_keys[0]
            _vscode_service = VSCodeService(
                port=config.vscode_port,
                connection_token=connection_token,
                server_base_path=config.vscode_base_path,
            )
    return _vscode_service
