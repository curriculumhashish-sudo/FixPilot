"""使用浏览器使用MCP服务器包装器实现浏览器工具执行器。"""

from __future__ import annotations

import builtins
import functools
import json
import logging
import os
import shutil
import sys
import threading
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, TypeVar
from uuid import uuid4


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation

from openhands.sdk.logger import DEBUG, get_logger
from openhands.sdk.tool import ToolExecutor
from openhands.sdk.utils.async_executor import AsyncExecutor
from openhands.tools.browser_use.definition import (
    BROWSER_RECORDING_OUTPUT_DIR,
    BrowserAction,
    BrowserObservation,
)
from openhands.tools.browser_use.server import CustomBrowserUseServer
from openhands.tools.utils.timeout import (
    TimeoutError as ToolTimeoutError,
    run_with_timeout,
)


F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


def recording_aware(
    func: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """处理导航操作之前/之后的记录刷新的装饰器。

    这个装饰器：
    1. 在操作之前刷新记录事件（以保留它们）
    2. 执行操作
    3. 如果录制处于活动状态，则在新页面上重新开始录制

    错误处理策略（有关完整详细信息，请参阅 recording.py 模块文档字符串）：
    - 录制是次要功能，不应阻止浏览器操作
    - AttributeError: 无声通过（录音未初始化 - 预期）
    - 其他例外：登录DEBUG，不中断导航
    """

    @functools.wraps(func)
    async def wrapper(self: BrowserToolExecutor, *args: Any, **kwargs: Any) -> Any:
        is_recording = self._server._is_recording
        if is_recording:
            try:
                await self._server._flush_recording_events()
            except AttributeError:
                # 录音未初始化 - 预期，静默通过
                pass
            except Exception as e:
                # 内部操作：登录DEBUG，不中断导航
                logger.debug(f"Recording flush before {func.__name__} skipped: {e}")

        result = await func(self, *args, **kwargs)

        if is_recording:
            try:
                await self._server._restart_recording_on_new_page()
            except AttributeError:
                # 录音未初始化 - 预期，静默通过
                pass
            except Exception as e:
                # 内部操作：登录DEBUG，不中断导航
                logger.debug(f"Recording restart after {func.__name__} skipped: {e}")

        return result

    return wrapper


# 禁止浏览器使用日志记录以实现更清晰的集成
if DEBUG:
    logging.getLogger("browser_use").setLevel(logging.DEBUG)
else:
    logging.getLogger("browser_use").setLevel(logging.WARNING)

logger = get_logger(__name__)

DEFAULT_BROWSER_ACTION_TIMEOUT_SECONDS: Final[float] = 300.0
# 在连续多次失败后，重置浏览器会话（假设浏览器已崩溃或变得不可恢复）。
#
MAX_CONSECUTIVE_FAILURES: Final[int] = 3
# 在失败后使用较短的超时来避免针对死浏览器的长时间级联等待。
#
DEGRADED_TIMEOUT_SECONDS: Final[float] = 30.0


def _current_platform(platform: str | None = None) -> str:
    return sys.platform if platform is None else platform


def _windows_browser_install_paths() -> list[Path]:
    roots = [
        os.environ.get("PROGRAMFILES", "C:\\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    browsers = [
        ("Google", "Chrome", "Application", "chrome.exe"),
        ("Microsoft", "Edge", "Application", "msedge.exe"),
        ("Chromium", "Application", "chrome.exe"),
    ]

    paths: list[Path] = []
    for root in roots:
        if root is None:
            continue
        for parts in browsers:
            paths.append(Path(root).joinpath(*parts))
    return paths


def _standard_chromium_paths(platform: str | None = None) -> list[Path]:
    match _current_platform(platform):
        case "darwin":
            return [
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
                Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            ]
        case "win32":
            return _windows_browser_install_paths()
        case _:
            return [
                Path("/usr/bin/google-chrome"),
                Path("/usr/bin/google-chrome-stable"),
                Path("/usr/bin/chromium"),
                Path("/usr/bin/chromium-browser"),
                Path("/usr/bin/microsoft-edge"),
                Path("/usr/bin/microsoft-edge-stable"),
            ]


def _playwright_cache_dirs(platform: str | None = None) -> list[Path]:
    # 设置后，Playwright 将浏览器安装到 $PLAYWRIGHT_BROWSERS_PATH 中。 “0”是安装包内浏览
    # 器的特殊值，不是目录路径，所以这里忽略。
    #
    dirs: list[Path] = []
    if (browsers_path := os.environ.get("PLAYWRIGHT_BROWSERS_PATH")) and (
        browsers_path != "0"
    ):
        dirs.append(Path(browsers_path).expanduser())
    match _current_platform(platform):
        case "darwin":
            dirs.append(Path.home() / "Library" / "Caches" / "ms-playwright")
        case "win32":
            if local_app_data := os.environ.get("LOCALAPPDATA"):
                dirs.append(Path(local_app_data) / "ms-playwright")
            else:
                dirs.append(Path.home() / "AppData" / "Local" / "ms-playwright")
        case _:
            dirs.append(Path.home() / ".cache" / "ms-playwright")
    return dirs


def _playwright_chromium_paths(
    chromium_dir: Path,
    platform: str | None = None,
) -> list[Path]:
    match _current_platform(platform):
        case "darwin":
            return [
                chromium_dir
                / "chrome-mac-arm64"
                / "Google Chrome for Testing.app"
                / "Contents"
                / "MacOS"
                / "Google Chrome for Testing",
                chromium_dir
                / "chrome-mac"
                / "Google Chrome for Testing.app"
                / "Contents"
                / "MacOS"
                / "Google Chrome for Testing",
                chromium_dir
                / "chrome-mac"
                / "Chromium.app"
                / "Contents"
                / "MacOS"
                / "Chromium",
            ]
        case "win32":
            return [
                chromium_dir / "chrome-win64" / "chrome.exe",
                chromium_dir / "chrome-win" / "chrome.exe",
            ]
        case _:
            return [
                chromium_dir / "chrome-linux64" / "chrome",
                chromium_dir / "chrome-linux" / "chrome",
            ]


def _path_binary_candidates(platform: str | None = None) -> tuple[str, ...]:
    if _current_platform(platform) == "win32":
        return ("chrome", "msedge", "chromium")
    return (
        "google-chrome",
        "chrome",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
    )


def _format_browser_operation_error(
    error: BaseException, timeout_seconds: float | None = None
) -> str:
    if error_detail := str(error).strip():
        pass
    elif isinstance(error, builtins.TimeoutError):
        error_detail = (
            f"Operation timed out after {int(timeout_seconds)} seconds"
            if timeout_seconds is not None
            else "Operation timed out"
        )
    else:
        error_detail = error.__class__.__name__
    return f"Browser operation failed: {error_detail}"


def _get_chromium_error_message() -> str:
    """获取 Chromium 不可用时的错误消息。"""
    return (
        "Chromium is required for browser operations but is not installed.\n\n"
        "To install Chromium, run one of the following commands:\n"
        "  1. Using uvx (recommended): uvx playwright install chromium "
        "--with-deps --no-shell\n"
        "  2. Using pip: pip install playwright && playwright install chromium\n"
        "  3. Using system package manager:\n"
        "     - Ubuntu/Debian: sudo apt install chromium-browser\n"
        "     - macOS: brew install chromium\n"
        "     - Windows: winget install Chromium.Chromium\n\n"
        "After installation, restart your application to use the browser tool."
    )


class BrowserToolExecutor(ToolExecutor[BrowserAction, BrowserObservation]):
    """包装浏览器使用的 MCP 服务器以进行 OpenHands 集成的执行器。"""

    _server: CustomBrowserUseServer
    _config: dict[str, Any]
    _initialized: bool
    _async_executor: AsyncExecutor
    _cleanup_initiated: bool
    _close_lock: threading.Lock
    _action_timeout_seconds: float

    @staticmethod
    @functools.cache
    def check_chromium_available() -> str | None:
        """检查 Chromium/Chrome 二进制文件是否可用。

        Returns:
            如果找到 Chromium 二进制文件的路径，否则为 None
        """
        # 检查标准安装路径（最好安装完整的 Chrome）
        for path in _standard_chromium_paths():
            if path.exists():
                return str(path)

        # 检查 Playwright 安装的 Chromium（优于 PATH 查找，因为像自制 chromium 这样的
        # PATH 二进制文件可能缺乏 CDP 支持）
        #
        for playwright_cache in _playwright_cache_dirs():
            if playwright_cache.exists():
                chromium_dirs = list(playwright_cache.glob("chromium-*"))
                for chromium_dir in chromium_dirs:
                    for path in _playwright_chromium_paths(chromium_dir):
                        if path.exists():
                            return str(path)

        # 回退方案：检查 PATH 是否有任何基于 chromium 的二进制文件
        for binary in _path_binary_candidates():
            if path := shutil.which(binary):
                return path

        return None

    def _ensure_chromium_available(self) -> str:
        """确保 Chromium 可用于浏览器操作。

        Raises:
            Exception: 如果 Chromium 不可用
        """
        if path := self.check_chromium_available():
            logger.info(f"Chromium is available for browser operations at {path}")
            return path

        # Chromium 不可用 - 提供清晰的安装说明
        raise Exception(_get_chromium_error_message())

    def __init__(
        self,
        headless: bool = True,
        allowed_domains: list[str] | None = None,
        session_timeout_minutes: int = 30,
        init_timeout_seconds: int = 30,
        action_timeout_seconds: float = DEFAULT_BROWSER_ACTION_TIMEOUT_SECONDS,
        full_output_save_dir: str | None = None,
        inject_scripts: list[str] | None = None,
        **config,
    ):
        """使用超时保护初始化 BrowserToolExecutor。

        Args:
            headless: 是否以无头模式运行浏览器
            allowed_domains: 浏览器操作允许的域列表
            session_timeout_minutes: 浏览器会话超时（分钟）
            init_timeout_seconds: 超时浏览器初始化（以秒为单位）
            action_timeout_seconds: 超时每个浏览器操作（以秒为单位）
            full_output_save_dir: 用于保存完整输出的目录的绝对路径
                日志和文件，在需要截断时使用。
            inject_scripts: 要注入每个的 JavaScript 代码字符串列表
                新文件。 脚本通过 CDP 的 Page.addScriptToEvaluateOnNewDocument 注入并
                在页面脚本之前运行。 对于
                注入 rrweb 等记录工具很有用。
            **config: 附加配置选项
        """

        self._close_lock = threading.Lock()

        def init_logic():
            executable_path = self._ensure_chromium_available()
            self._server = CustomBrowserUseServer(
                session_timeout_minutes=session_timeout_minutes,
            )
            # 配置注入脚本
            if inject_scripts:
                self._server.set_inject_scripts(inject_scripts)

            # Chromium 拒绝在启用沙箱的情况下以 root 身份运行。 以 root 身份运行时禁用沙
            # 箱，因此应用 CHROME_DOCKER_ARGS（--no-sandbox、--disable-setuid-sandbox 等
            # ）。
            # SECURITY：在没有沙箱的情况下以 root 身份运行 Chrome 是有风险的
            # - 受感染的浏览器具有完全的 root 访问权限。 仅用于
            # 受控环境。
            getuid = getattr(os, "getuid", None)
            running_as_root = getuid is not None and getuid() == 0
            if running_as_root:
                logger.warning(
                    "Running as root - disabling Chromium sandbox "
                    "(required for root). This reduces security isolation."
                )

            self._config = {
                "headless": headless,
                "allowed_domains": allowed_domains or [],
                "executable_path": executable_path,
                "chromium_sandbox": not running_as_root,
                "user_data_dir": str(
                    Path.home() / ".config" / "browseruse" / "profiles" / uuid4().hex
                ),
                **config,
            }

        try:
            run_with_timeout(init_logic, init_timeout_seconds)
        except ToolTimeoutError:
            raise Exception(
                f"Browser tool initialization timed out after {init_timeout_seconds}s"
            )

        if action_timeout_seconds <= 0:
            raise ValueError("action_timeout_seconds must be greater than 0")

        self.full_output_save_dir: str | None = full_output_save_dir
        self._initialized = False
        self._async_executor = AsyncExecutor()
        self._cleanup_initiated = False
        self._action_timeout_seconds = action_timeout_seconds
        self._consecutive_failures = 0

    def __call__(
        self,
        action: BrowserAction,
        conversation: LocalConversation | None = None,  # noqa: ARG002
    ):
        """提交一个操作以在后台循环中运行并等待结果。"""
        # 在触发重置之前，在最后一个重试上使用较短的超时，以避免针对死浏览器的长时间级联
        # 等待。
        #
        effective_timeout = (
            DEGRADED_TIMEOUT_SECONDS
            if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES - 1
            else self._action_timeout_seconds
        )

        try:
            result = self._async_executor.run_async(
                self._execute_action,
                action,
                timeout=effective_timeout,
            )
        except builtins.TimeoutError as error:
            # 超时指示浏览器可能已死/挂起 - 跟踪它们以进行崩溃检测。 常规操作错误（无效
            # 选择器、缺少元素）被计入不，因为这些是正常的智能体错误，而不是浏览器崩溃。
            #
            return self._handle_timeout_failure(
                _format_browser_operation_error(
                    error, timeout_seconds=effective_timeout
                )
            )

        self._consecutive_failures = 0
        return result

    def _handle_timeout_failure(self, error_text: str) -> BrowserObservation:
        """跟踪连续的超时失败并根据需要重置会话。"""
        self._consecutive_failures += 1
        logger.debug(
            "Browser timeout failure %d/%d",
            self._consecutive_failures,
            MAX_CONSECUTIVE_FAILURES,
        )

        if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            logger.warning(
                "Browser appears crashed (%d consecutive failures). "
                "Resetting session for automatic recovery.",
                self._consecutive_failures,
            )
            # 尽最大努力清理旧浏览器进程/会话。 如果浏览器真的崩溃了，这将很快失败； 如
            # 果它是楔入的，则可以避免泄漏过程。
            #
            try:
                self._async_executor.run_async(self.cleanup, timeout=5.0)
            except Exception as e:
                logger.debug(
                    "Cleanup during session reset failed "
                    "(expected if browser crashed): %s",
                    e,
                )
            self._initialized = False
            self._consecutive_failures = 0
            error_text = (
                f"{error_text}\n\n"
                "The browser session has been reset after multiple consecutive "
                "failures (possible crash). The browser will be restarted on "
                "the next action. Please retry your action."
            )

        return BrowserObservation.from_text(
            text=error_text,
            is_error=True,
            full_output_save_dir=self.full_output_save_dir,
        )

    async def _execute_action(self, action):
        """异步执行浏览器操作。"""
        from openhands.tools.browser_use.definition import (
            BrowserClickAction,
            BrowserCloseTabAction,
            BrowserGetContentAction,
            BrowserGetStateAction,
            BrowserGetStorageAction,
            BrowserGoBackAction,
            BrowserListTabsAction,
            BrowserNavigateAction,
            BrowserObservation,
            BrowserScrollAction,
            BrowserSetStorageAction,
            BrowserStartRecordingAction,
            BrowserStopRecordingAction,
            BrowserSwitchTabAction,
            BrowserTypeAction,
        )

        try:
            result = ""
            # 根据操作类型路由到适当的方法
            if isinstance(action, BrowserNavigateAction):
                result = await self.navigate(action.url, action.new_tab)
            elif isinstance(action, BrowserClickAction):
                result = await self.click(action.index, action.new_tab)
            elif isinstance(action, BrowserTypeAction):
                result = await self.type_text(action.index, action.text)
            elif isinstance(action, BrowserGetStateAction):
                return await self.get_state(action.include_screenshot)
            elif isinstance(action, BrowserGetStorageAction):
                result = await self.get_storage()
            elif isinstance(action, BrowserSetStorageAction):
                result = await self.set_storage(action.storage_state)
            elif isinstance(action, BrowserGetContentAction):
                result = await self.get_content(
                    action.extract_links, action.start_from_char
                )
            elif isinstance(action, BrowserScrollAction):
                result = await self.scroll(action.direction)
            elif isinstance(action, BrowserGoBackAction):
                result = await self.go_back()
            elif isinstance(action, BrowserListTabsAction):
                result = await self.list_tabs()
            elif isinstance(action, BrowserSwitchTabAction):
                result = await self.switch_tab(action.tab_id)
            elif isinstance(action, BrowserCloseTabAction):
                result = await self.close_tab(action.tab_id)
            elif isinstance(action, BrowserStartRecordingAction):
                result = await self.start_recording()
            elif isinstance(action, BrowserStopRecordingAction):
                result = await self.stop_recording()
            else:
                error_msg = f"Unsupported action type: {type(action)}"
                return BrowserObservation.from_text(
                    text=error_msg,
                    is_error=True,
                    full_output_save_dir=self.full_output_save_dir,
                )

            return BrowserObservation.from_text(
                text=result,
                is_error=False,
                full_output_save_dir=self.full_output_save_dir,
            )
        except Exception as error:
            error_msg = _format_browser_operation_error(error)
            logging.error(error_msg, exc_info=True)
            return BrowserObservation.from_text(
                text=error_msg,
                is_error=True,
                full_output_save_dir=self.full_output_save_dir,
            )

    async def _ensure_initialized(self):
        """确保浏览器会话已初始化。"""
        if not self._initialized:
            # 使用我们的配置初始化浏览器会话
            await self._server._init_browser_session(**self._config)
            # 会话准备好后注入任何配置的用户脚本
            # 注意： rrweb 脚本在录制开始时延迟注入
            await self._server._inject_scripts_to_session()
            self._initialized = True

    # 导航和浏览器控制方法
    @recording_aware
    async def navigate(self, url: str, new_tab: bool = False) -> str:
        """导航至 URL。"""
        await self._ensure_initialized()
        return await self._server._navigate(url, new_tab)

    @recording_aware
    async def go_back(self) -> str:
        """返回浏览器历史记录。"""
        await self._ensure_initialized()
        return await self._server._go_back()

    # 页面交互
    @recording_aware
    async def click(self, index: int, new_tab: bool = False) -> str:
        """按索引单击元素。"""
        await self._ensure_initialized()
        return await self._server._click(index, new_tab)

    async def type_text(self, index: int, text: str) -> str:
        """在元素中键入文本。"""
        await self._ensure_initialized()
        return await self._server._type_text(index, text)

    async def scroll(self, direction: str = "down") -> str:
        """滚动页面。"""
        await self._ensure_initialized()
        return await self._server._scroll(direction)

    async def get_state(self, include_screenshot: bool = False):
        """通过交互元素获取当前浏览器状态。"""
        from openhands.tools.browser_use.definition import BrowserObservation

        await self._ensure_initialized()
        result_json = await self._server._get_browser_state(include_screenshot)

        if include_screenshot:
            try:
                result_data = json.loads(result_json)
                screenshot_data = result_data.pop("screenshot", None)

                # 返回干净的JSON+单独的屏幕截图数据
                clean_json = json.dumps(result_data, indent=2)
                return BrowserObservation.from_text(
                    text=clean_json,
                    is_error=False,
                    screenshot_data=screenshot_data,
                    full_output_save_dir=self.full_output_save_dir,
                )
            except json.JSONDecodeError:
                # 如果JSON解析失败，则按原样返回
                pass

        return BrowserObservation.from_text(
            text=result_json,
            is_error=False,
            full_output_save_dir=self.full_output_save_dir,
        )

    async def get_storage(self) -> str:
        """获取浏览器存储（cookie、本地存储、会话存储）。"""
        await self._ensure_initialized()
        return await self._server._get_storage()

    async def set_storage(self, storage_state: dict) -> str:
        """设置浏览器存储（cookie、本地存储、会话存储）。"""
        await self._ensure_initialized()
        return await self._server._set_storage(storage_state)

    # 标签管理
    async def list_tabs(self) -> str:
        """列出所有打开的选项卡。"""
        await self._ensure_initialized()
        return await self._server._list_tabs()

    async def switch_tab(self, tab_id: str) -> str:
        """切换到不同的选项卡。"""
        await self._ensure_initialized()
        return await self._server._switch_tab(tab_id)

    async def close_tab(self, tab_id: str) -> str:
        """关闭特定选项卡。"""
        await self._ensure_initialized()
        return await self._server._close_tab(tab_id)

    # Content Extraction
    async def get_content(self, extract_links: bool, start_from_char: int) -> str:
        """提取页面内容，可以选择包含链接。"""
        await self._ensure_initialized()
        return await self._server._get_content(
            extract_links=extract_links, start_from_char=start_from_char
        )

    # 会话录音
    async def start_recording(self) -> str:
        """使用 rrweb 开始记录浏览器会话。

        记录事件会定期刷新到 BROWSER_RECORDING_OUTPUT_DIR 下会话子文件夹中带时间戳的
        JSON 文件。 事件每 5 秒刷新一次。
        """
        await self._ensure_initialized()
        return await self._server._start_recording(
            output_dir=BROWSER_RECORDING_OUTPUT_DIR
        )

    async def stop_recording(self) -> str:
        """停止记录并将剩余事件保存到文件中。

        停止定期刷新，收集所有剩余事件，并将它们保存到最终编号为 JSON 的文件中。 返回
        包含事件总数和文件计数的摘要消息。
        """
        await self._ensure_initialized()
        return await self._server._stop_recording()

    async def close_browser(self) -> str:
        """关闭浏览器会话。"""
        if self._initialized:
            result = await self._server._close_browser()
            self._initialized = False
            return result
        return "No browser session to close"

    async def cleanup(self):
        """清理浏览器资源。"""
        try:
            # 使用 _close_all_sessions instead of close_browser 因为它调用了一个函数
            # session.kill() 正确地停止事件总线并清除所有待处理事件（包括
            # BrowserKillEvent 终止 Chromium 的那个子进程). close_browser() 单独执行
            # BrowserKillEvent fire-and-forget 和在未处理之前就返回，这可能会让浏览器进
            # 程保持运行。
            #
            if hasattr(self._server, "_close_all_sessions"):
                await self._server._close_all_sessions()
            else:
                await self.close_browser()
        except Exception as e:
            logger.warning(f"Error during browser cleanup: {e}")

    def close(self):
        """关闭浏览器执行器并清理资源。"""
        with self._close_lock:
            shared_close_lock_acquired = self._detach_shared_executor_for_close()
            if self._cleanup_initiated:
                if shared_close_lock_acquired:
                    self._release_shared_executor_creation_lock()
                return
            self._cleanup_initiated = True
            try:
                # 使用较短的超时在异步执行器中运行清理
                self._async_executor.run_async(self.cleanup, timeout=30.0)
            except Exception as e:
                logger.warning(f"Error during browser cleanup: {e}")
            finally:
                # 删除浏览器配置文件目录以避免磁盘堆积。 browser_use 不会在关闭时清除
                # user_data_dir。
                #
                user_data_dir = self._config.get("user_data_dir")
                if user_data_dir and "browseruse/profiles/" in user_data_dir:
                    try:
                        shutil.rmtree(user_data_dir, ignore_errors=True)
                    except Exception:
                        pass
                try:
                    # 始终关闭异步执行器
                    self._async_executor.close()
                finally:
                    if shared_close_lock_acquired:
                        self._release_shared_executor_creation_lock()
                    else:
                        self._release_shared_executor_reference()

    def _detach_shared_executor_for_close(self) -> bool:
        from openhands.tools.browser_use.definition import BrowserToolSet

        if BrowserToolSet._shared_executor is not self:
            return False

        BrowserToolSet._shared_executor_creation_lock.acquire()
        with BrowserToolSet._shared_executor_lock:
            if BrowserToolSet._shared_executor is self:
                BrowserToolSet._shared_executor = None
                return True

        BrowserToolSet._shared_executor_creation_lock.release()
        return False

    @staticmethod
    def _release_shared_executor_creation_lock() -> None:
        from openhands.tools.browser_use.definition import BrowserToolSet

        BrowserToolSet._shared_executor_creation_lock.release()

    def _release_shared_executor_reference(self):
        # 避免将共享执行器锁用作普通/陈旧的执行器。 __del__ 可以在 BrowserToolSet.create
        # () 创建新的共享执行器时运行； 过时的执行器终结器试图获取与创建路径相同的锁 can
        #  死锁，尤其是在 Windows 上。
        #
        from openhands.tools.browser_use.definition import BrowserToolSet

        if BrowserToolSet._shared_executor is not self:
            return
        with BrowserToolSet._shared_executor_lock:
            if BrowserToolSet._shared_executor is self:
                BrowserToolSet._shared_executor = None

    def __del__(self):
        """删除时清理。"""
        try:
            self.close()
        except Exception:
            pass  # 忽略删除期间的清理错误
