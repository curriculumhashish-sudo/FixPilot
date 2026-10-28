import argparse
import atexit
import faulthandler
import importlib
import os
import signal
import sys
from types import FrameType

import uvicorn
from uvicorn import Config

from openhands.agent_server.logging_config import LOGGING_CONFIG
from openhands.sdk.logger import DEBUG, get_logger


logger = get_logger(__name__)


_INTERNAL_SERVER_URL_ENV = "OH_INTERNAL_SERVER_URL"
_EXTRA_PYTHON_PATH_ENV = "OH_EXTRA_PYTHON_PATH"

# 绑定到每个网络接口的主机。 绑定到其中之一而不使用身份验证会将（否则未经身份验证的）
# Agent Server 暴露给网络 - 请参阅下面的 session-API-key 绑定防护。
#
_WILDCARD_HOSTS = frozenset({"0.0.0.0", "::", "[::]"})
_LOOPBACK_HOST = "127.0.0.1"


def _load_server_config():
    """解析有效的智能体-服务器配置，如果失败则解析 ``None``。

    设置可能来自环境变量或智能体服务器配置文件，因此我们解析有效配置而不是检查单个源
    。
    """
    from openhands.agent_server.config import load_config

    try:
        return load_config()
    except Exception:
        logger.warning(
            "Failed to load agent-server config while resolving server "
            "startup options; using safe defaults.",
            exc_info=True,
        )
        return None


def _auth_enabled() -> bool:
    """当至少配置了一个会话 API 密钥时返回 True。

    密钥可能来自 ``SESSION_API_KEY`` / ``OH_SESSION_API_KEYS_0`` 环境变量或智能体-服
    务器配置文件。
    """
    config = _load_server_config()
    return bool(config and config.session_api_keys)


def _trust_forwarded_headers() -> bool:
    """当操作员选择信任转发标头时返回 True。

    uvicorn的``proxy_headers``重写了请求方案和客户端地址
    from ``X-Forwarded-Proto``/``X-Forwarded-For`` sent by any peer in
    ``FORWARDED_ALLOW_IPS``（默认环回）。 将其绑定到
    ``trust_forwarded_headers`` 在该设置关闭时阻止客户端更改服务器派生的源。
    """
    config = _load_server_config()
    return bool(config and config.trust_forwarded_headers)


def _get_internal_server_url(host: str, port: int) -> str:
    """构建当前的智能体-服务器 URL 以进行本地机密查找。

    通配符绑定被重写为回环，这样在途的调用者可以连接回当前服务器实例，而IPv6常量被括
    起来以生成有效的URL。

    Examples:
        >>> _get_internal_server_url("0.0.0.0", 8000)
        ' http://127.0.0.1:8000'
        >>> _get_internal_server_url("::", 8000)
        ' http://127.0.0.1:8000'
        >>> _get_internal_server_url("fe80::1", 8000)
        ' http://[fe80::1 ]:8000'
    """
    resolved_host = host
    if host in _WILDCARD_HOSTS:
        resolved_host = "127.0.0.1"
    elif ":" in host and not host.startswith("["):
        resolved_host = f"[{host}]"
    return f"http://{resolved_host}:{port}"


def extend_python_path(extra_paths: str | None) -> None:
    """将目录添加到 ``sys.path``，以便 ``importlib.import_module`` 可以找到
    外部自定义工具模块 - 即使从 PyInstaller 二进制文件运行时也是如此。

    路径从 *extra_paths* (``--extra-python-path`` CLI arg) ** 和 **
    ``OH_EXTRA_PYTHON_PATH`` 环境变量读取。 两者都使用平台路径分隔符（POSIX 上的
    ``':'``，Windows 上的 ``';'``）
    。

    不存在的目录会被跳过并带有警告； ``sys.path`` 上已有的重复项和路径将被默默忽略。
    """
    raw_parts: list[str] = []
    for source in (extra_paths, os.environ.get(_EXTRA_PYTHON_PATH_ENV)):
        if source:
            raw_parts.extend(source.split(os.pathsep))

    added = 0
    for part in raw_parts:
        part = part.strip()
        if not part:
            continue
        resolved = os.path.abspath(part)
        if not os.path.isdir(resolved):
            logger.warning(
                "Ignoring non-existent --extra-python-path entry: %s", resolved
            )
            continue
        if resolved not in sys.path:
            sys.path.insert(0, resolved)
            logger.info("Added to sys.path: %s", resolved)
            added += 1

    if added:
        logger.info(
            "Extended sys.path with %d director%s for custom tool imports",
            added,
            "y" if added == 1 else "ies",
        )


def preload_modules(modules_arg: str | None) -> None:
    """导入用户指定的模块，以便其顶级副作用运行。

    用于在创建任何对话之前注册自定义工具，避免与 conversation_service 中的动态
    `tool_module_qualnames` 导入发生竞争。
    """
    if not modules_arg:
        return
    for module_name in modules_arg.split(","):
        module_name = module_name.strip()
        if not module_name:
            continue
        try:
            importlib.import_module(module_name)
            logger.info("Imported module: %s", module_name)
        except ImportError as e:
            logger.error(
                "Failed to import module '%s' specified in --import-modules: %s",
                module_name,
                e,
            )
            raise


def check_browser():
    """检查浏览器功能是否可以呈现 about:blank。"""
    executor = None
    try:
        # 注册工具以确保浏览器工具可用
        from openhands.tools.preset.default import register_default_tools

        register_default_tools(enable_browser=True)

        # 导入浏览器组件
        from openhands.tools.browser_use.definition import BrowserNavigateAction
        from openhands.tools.browser_use.impl import BrowserToolExecutor

        # 创建执行者
        executor = BrowserToolExecutor(headless=True, session_timeout_minutes=2)

        # 尝试导航至 about:blank
        action = BrowserNavigateAction(url="about:blank")
        result = executor(action)

        # 检查操作是否成功
        if result.is_error:
            print(f"Browser check failed: {str(result.content)}")
            return False

        print("Browser check passed: Successfully rendered about:blank")
        return True

    except Exception as e:
        print(f"Browser check failed: {e}")
        return False
    finally:
        # 即使发生错误也确保进行清理
        if executor is not None:
            executor.close()


class LoggingServer(uvicorn.Server):
    """记录信号处理事件的自定义 uvicorn 服务器。

    该子类重写 handle_exit 以在接收终止信号时添加结构化日志记录，确保能够查看服务器为
    何关闭。
    """

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        """在委托给父级之前通过日志记录处理退出信号。"""
        sig_name = signal.Signals(sig).name
        logger.info(
            "Received signal %s (%d), shutting down...",
            sig_name,
            sig,
        )
        super().handle_exit(sig, frame)


def _setup_crash_diagnostics() -> None:
    """启用崩溃诊断以调试意外终止。

    Note: 故障处理程序以纯文本格式将回溯输出到 stderr，
    不通过结构化的 JSON 记录器。 这是不可避免的，因为在段错误期间，Python 的正常日志
    记录基础设施不可用。 纯文本回溯对于调试仍然很有价值。
    """
    faulthandler.enable()

    # 注册 atexit 处理程序以记录正常退出
    @atexit.register
    def _log_exit() -> None:
        logger.info("Process exiting via atexit handler")


def main() -> None:
    # 在任何其他初始化之前尽早设置崩溃诊断
    _setup_crash_diagnostics()

    parser = argparse.ArgumentParser(description="OpenHands Agent Server App")
    parser.add_argument(
        "--host",
        default=None,
        help=(
            "Host to bind to. Defaults to 127.0.0.1 (loopback) when no session "
            "API key is configured, or 0.0.0.0 when authentication is enabled via "
            "SESSION_API_KEY / OH_SESSION_API_KEYS_0."
        ),
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port to bind to (default: 8000)"
    )
    parser.add_argument(
        "--reload",
        dest="reload",
        default=False,
        action="store_true",
        help="Enable auto-reload (disabled by default)",
    )
    parser.add_argument(
        "--check-browser",
        action="store_true",
        help="Check if browser functionality works and exit",
    )
    parser.add_argument(
        "--import-modules",
        type=str,
        default=None,
        help=(
            "Comma-separated list of modules to import at startup "
            "(e.g. 'myapp.tools,myapp.plugins')"
        ),
    )
    parser.add_argument(
        "--extra-python-path",
        type=str,
        default=None,
        help=(
            "Additional directories to add to sys.path for custom tool imports "
            f"('{os.pathsep}'-separated).  Also reads from the "
            f"{_EXTRA_PYTHON_PATH_ENV} environment variable."
        ),
    )

    args = parser.parse_args()

    # 处理浏览器检查（应该在不导入用户模块的情况下运行）
    if args.check_browser:
        if check_browser():
            sys.exit(0)
        else:
            sys.exit(1)

    # 在导入用户模块之前扩展 sys.path，以便可以访问外部 .py 文件 - 对于 PyInstaller 二进
    # 制构建至关重要。
    #
    extend_python_path(args.extra_python_path)

    # 提前退出检查后导入用户模块
    preload_modules(args.import_modules)

    # 解析绑定主机。 当操作员不传递 --host 时，我们选择一个安全默认值：回环接口，除非配
    # 置了会话 API 键，否则绑定所有接口是故意的。 允许使用没有会话 API 密钥的显式通配符
    # 主机（操作员选择了它 - e.g。 一个映射到主机回环的容器化沙盒，但它会发出警告，以防
    # 止意外地暴露未认证的服务器给网络。
    #
    host = args.host
    auth_enabled = _auth_enabled()
    if host is None:
        host = "0.0.0.0" if auth_enabled else _LOOPBACK_HOST
    elif host in _WILDCARD_HOSTS and not auth_enabled:
        logger.warning(
            "Binding to all interfaces (%s) without a session API key: the "
            "agent server will be unauthenticated and reachable from the "
            "network. Set SESSION_API_KEY (or OH_SESSION_API_KEYS_0) to "
            "require authentication, or bind to a loopback address with "
            "--host.",
            host,
        )

    os.environ[_INTERNAL_SERVER_URL_ENV] = _get_internal_server_url(host, args.port)

    print(f"Starting OpenHands Agent Server on {host}:{args.port}")
    print(f"API docs will be available at http://{host}:{args.port}/docs")
    print(f"Auto-reload: {'enabled' if args.reload else 'disabled'}")

    # 显示调试模式状态
    if DEBUG:
        print("DEBUG mode: ENABLED (stack traces will be shown)")
    else:
        print("DEBUG mode: DISABLED")
    print()

    # 根据DEBUG环境变量配置uvicorn日志记录
    log_level = "debug" if DEBUG else "info"

    # 创建 uvicorn 配置
    config = Config(
        "openhands.agent_server.api:api",
        host=host,
        port=args.port,
        reload=args.reload,
        reload_includes=[
            "openhands-agent-server",
            "openhands-sdk",
            "openhands-tools",
        ],
        log_level=log_level,
        log_config=LOGGING_CONFIG,
        ws="wsproto",  # 使用 wsproto 代替已弃用 WebSocket 实现
        proxy_headers=_trust_forwarded_headers(),
    )

    # 使用自定义LoggingServer捕获信号处理事件
    server = LoggingServer(config)

    try:
        server.run()
    except Exception:
        logger.error("Server crashed with unexpected exception", exc_info=True)
        raise
    except BaseException as e:
        # Catch SystemExit、KeyboardInterrupt 等 - 这些是正常的终止路径
        logger.info("Server terminated: %s: %s", type(e).__name__, e)
        raise


if __name__ == "__main__":
    main()
