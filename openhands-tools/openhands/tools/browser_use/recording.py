"""使用 rrweb 进行浏览器会话记录的记录会话管理。

错误处理策略
=====================
录制是次要功能，不应阻止主要浏览器操作。 该模块根据操作类型遵循一致的错误处理策略：

1. **面向用户的操作**（启动、停止）：
   - 返回描述性错误字符串给用户（前缀为“Error:”）
   - 在警告级别记录意外错误
   - 在 INFO 级别记录预期失败（e.g.，rrweb 加载失败）

2. **内部/后台操作**（flush_events，定期刷新，重新启动）：
   - 以 DEBUG 级别登录并继续静默
   - 切勿引发会中断浏览器操作的异常
   - 失败时返回中性值 (0, None)

3. **AttributeError 表示“未初始化”**：
   - 无声通过 - 当尚未设置录音时，这是预期的
   - 用于impl.py中的recording_aware装饰器

此策略确保可以通过日志观察记录失败，但不会中断用户的主浏览器工作流程。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from openhands.sdk import get_logger
from openhands.tools.browser_use.event_storage import EventStorage


if TYPE_CHECKING:
    from browser_use.browser.session import BrowserSession


logger = get_logger(__name__)

# 包含 JavaScript 个文件的目录
_JS_DIR = Path(__file__).parent / "js"


# =============================================================================
# 配置
# =============================================================================


@dataclass
class RecordingConfig:
    """记录会话的配置。

    CDN 依赖说明：
        cdn_url 指向 unpkg.com，它提供 npm 包。 如果此 CDN 不可用（关闭、被防火墙阻止
        或速度缓慢），录制将无法开始。 对于受限环境中的生
        产部署，请考虑：
        - 自托管 rrweb 库
        - 使用不同的 CDN（jsdelivr、cdnjs）
        - 将 rrweb 与您的应用程序捆绑在一起
    """

    flush_interval_seconds: float = 5.0
    rrweb_load_timeout_ms: int = 10000  # 超时供 rrweb 从 CDN 加载
    cdn_url: str = "https://unpkg.com/rrweb@2.0.0-alpha.17/dist/rrweb.umd.cjs"


# 默认配置
DEFAULT_CONFIG = RecordingConfig()


# =============================================================================
# JavaScript 代码加载
# =============================================================================


@lru_cache(maxsize=16)
def _load_js_file(filename: str) -> str:
    """从 js/ 目录加载 JavaScript 文件并进行缓存。"""
    filepath = _JS_DIR / filename
    return filepath.read_text()


def get_rrweb_loader_js(cdn_url: str) -> str:
    """使用指定的 CDN URL 生成 rrweb 加载器 JavaScript。"""
    template = _load_js_file("rrweb-loader.js")
    return template.replace("{{CDN_URL}}", cdn_url)


def _get_flush_events_js() -> str:
    """获取 JavaScript 将记录事件从浏览器刷新到 Python。"""
    return _load_js_file("flush-events.js")


def _get_start_recording_simple_js() -> str:
    """获取JavaScript开始在页面上录制（简单版本）。"""
    return _load_js_file("start-recording-simple.js")


def _get_start_recording_js() -> str:
    """获取JavaScript开始录制（完整版带加载失败检查）。"""
    return _load_js_file("start-recording.js")


def _get_stop_recording_js() -> str:
    """获取 JavaScript 以停止记录并收集剩余事件。"""
    return _load_js_file("stop-recording.js")


def _get_wait_for_rrweb_js() -> str:
    """使用 Promise 获取 JavaScript 等待 rrweb 加载。"""
    return _load_js_file("wait-for-rrweb.js")


# =============================================================================
# RecordingSession 班级
# =============================================================================


@dataclass
class RecordingSession:
    """使用 rrweb 管理浏览器会话记录。

    Concurrency: 使用 asyncio.Lock 保护 _events 缓冲区免受并发的影响
    通过定期刷新循环和导航刷新进行访问。
    """

    output_dir: str | None = None
    config: RecordingConfig = field(default_factory=lambda: DEFAULT_CONFIG)

    _storage: EventStorage = field(default_factory=EventStorage, repr=False)
    _is_recording: bool = False
    _events: list[dict] = field(default_factory=list)
    _flush_task: asyncio.Task | None = field(default=None, repr=False)
    _scripts_injected: bool = False
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _consecutive_flush_failures: int = 0

    def __post_init__(self) -> None:
        # 同步output_dir到存储
        self._storage.output_dir = self.output_dir

    @property
    def session_dir(self) -> str | None:
        return self._storage.session_dir

    @property
    def is_active(self) -> bool:
        return self._is_recording

    @property
    def total_events(self) -> int:
        return self._storage.total_events

    @property
    def file_count(self) -> int:
        return self._storage.file_count

    @property
    def events(self) -> list[dict]:
        return self._events

    def _save_and_clear_events(self) -> str | None:
        """将当前事件保存到存储器并清除缓冲区。"""
        if not self._events:
            return None
        filepath = self._storage.save_events(self._events)
        if filepath:
            self._events = []
        return filepath

    async def _set_recording_flag(
        self, browser_session: BrowserSession, should_record: bool
    ) -> None:
        """在浏览器中设置录制标志以在新页面上自动启动。"""
        try:
            cdp_session = await browser_session.get_or_create_cdp_session()
            flag_value = str(should_record).lower()
            await cdp_session.cdp_client.send.Runtime.evaluate(
                params={
                    "expression": f"window.__rrweb_should_record = {flag_value};",
                    "returnByValue": True,
                },
                session_id=cdp_session.session_id,
            )
        except Exception as e:
            # 内部操作：记录在DEBUG，不要中断（参见错误处理策略）
            logger.debug(f"Failed to set recording flag: {e}")

    async def inject_scripts(self, browser_session: BrowserSession) -> list[str]:
        """将 rrweb 加载器脚本注入浏览器会话中。

        使用 Page.addScriptToEvaluateOnNewDocument 注入将在页面脚本执行之前在每个新文
        档上运行的脚本。

        Returns:
            CDP 返回的脚本标识符列表。
        """
        if self._scripts_injected:
            return []

        script_ids = []
        try:
            cdp_session = await browser_session.get_or_create_cdp_session()
            cdp_client = cdp_session.cdp_client

            rrweb_loader = get_rrweb_loader_js(self.config.cdn_url)
            result = await cdp_client.send.Page.addScriptToEvaluateOnNewDocument(
                params={"source": rrweb_loader, "runImmediately": True},
                session_id=cdp_session.session_id,
            )
            script_id = result.get("identifier")
            if script_id:
                script_ids.append(script_id)
                logger.debug(f"Injected rrweb script with identifier: {script_id}")

            self._scripts_injected = True
            logger.debug("Injected rrweb loader script")
        except Exception as e:
            # 内部操作：记录在DEBUG，不要中断（参见错误处理策略）
            logger.debug(f"Script injection skipped: {e}")

        return script_ids

    async def flush_events(self, browser_session: BrowserSession) -> int:
        """将记录事件从浏览器刷新到 Python 存储。"""
        if not self._is_recording:
            return 0

        try:
            cdp_session = await browser_session.get_or_create_cdp_session()
            result = await cdp_session.cdp_client.send.Runtime.evaluate(
                params={"expression": _get_flush_events_js(), "returnByValue": True},
                session_id=cdp_session.session_id,
            )

            data = json.loads(result.get("result", {}).get("value", "{}"))
            events = data.get("events", [])
            if events:
                async with self._lock:
                    self._events.extend(events)
                    logger.debug(f"Flushed {len(events)} events from browser")

            return len(events)
        except Exception as e:
            # 内部操作：在 DEBUG 处登录，返回 0（请参阅错误处理策略）
            logger.debug(f"Event flush skipped: {e}")
            return 0

    async def _periodic_flush_loop(self, browser_session: BrowserSession) -> None:
        """定期刷新记录事件的后台任务。"""
        while self._is_recording:
            await asyncio.sleep(self.config.flush_interval_seconds)
            if not self._is_recording:
                break

            try:
                await self.flush_events(browser_session)
                async with self._lock:
                    if self._events:
                        filepath = self._save_and_clear_events()
                        if filepath:
                            self._consecutive_flush_failures = 0
                        else:
                            self._consecutive_flush_failures += 1
            except Exception as e:
                # 内部操作：记录在DEBUG，不要中断（参见错误处理策略）
                self._consecutive_flush_failures += 1
                logger.debug(f"Periodic flush skipped: {e}")

            # 连续 3 次失败后发出警告，以便了解持续存在的问题
            if self._consecutive_flush_failures >= 3:
                logger.warning(
                    f"Recording flush has failed {self._consecutive_flush_failures} "
                    f"times. Events may be accumulating in memory. "
                    f"Check disk space and permissions."
                )

    async def _wait_for_rrweb_load(self, browser_session: BrowserSession) -> dict:
        """使用事件驱动的基于 Promise 的等待等待 rrweb 加载。

        使用 CDP 的 awaitPromise 等待 rrweb 加载器 Promise 解析，避免轮询反模式。 这
        会根据需要等待足够长的时间，如果加载失败，则
        会立即失败。

        Returns:
            带有“成功”(bool) 和可选的“错误”(str) 键的字典。
        """
        cdp_session = await browser_session.get_or_create_cdp_session()

        try:
            result = await asyncio.wait_for(
                cdp_session.cdp_client.send.Runtime.evaluate(
                    params={
                        "expression": _get_wait_for_rrweb_js(),
                        "awaitPromise": True,
                        "returnByValue": True,
                    },
                    session_id=cdp_session.session_id,
                ),
                timeout=self.config.rrweb_load_timeout_ms / 1000,
            )

            value = result.get("result", {}).get("value", {})
            if isinstance(value, dict):
                return value
            return {"success": False, "error": "unexpected_response"}

        except TimeoutError:
            logger.debug(f"rrweb load timeout ({self.config.rrweb_load_timeout_ms}ms)")
            return {"success": False, "error": "timeout"}

    def _initialize_session_state(self) -> None:
        """重置状态并为新的录制会话创建会话子文件夹。"""
        self._events = []
        self._is_recording = True
        self._consecutive_flush_failures = 0
        self._storage.reset()
        self._storage.output_dir = self.output_dir
        self._storage.create_session_subfolder()

    async def _handle_rrweb_load_failure(
        self, browser_session: BrowserSession, error: str
    ) -> str:
        """处理 rrweb 加载失败并返回相应的错误消息。

        预期失败：在 INFO 处登录，返回错误字符串（请参阅错误处理策略）
        """
        self._is_recording = False
        await self._set_recording_flag(browser_session, False)

        error_messages = {
            "load_failed": (
                "Error: Unable to start recording. The rrweb library "
                "failed to load from CDN. Please check network "
                "connectivity and try again."
            ),
            "timeout": (
                "Error: Unable to start recording. rrweb did not load in time. "
                "Please navigate to a page first and try again."
            ),
            "not_injected": (
                "Error: Unable to start recording. Scripts not injected. "
                "Please navigate to a page first and try again."
            ),
        }

        if error in error_messages:
            if error == "timeout":
                logger.info(
                    f"Recording start failed: rrweb load timeout "
                    f"({self.config.rrweb_load_timeout_ms}ms)"
                )
            else:
                logger.info(f"Recording start failed: rrweb {error}")
            return error_messages[error]

        logger.info(f"Recording start failed: {error}")
        return f"Error: Unable to start recording: {error}"

    async def _ensure_rrweb_loaded(self, browser_session: BrowserSession) -> str | None:
        """等待 rrweb 加载。 如果失败则返回错误消息，如果成功则返回 None。"""
        load_result = await self._wait_for_rrweb_load(browser_session)

        if not load_result.get("success"):
            error = load_result.get("error", "unknown")
            return await self._handle_rrweb_load_failure(browser_session, error)

        return None

    async def _start_flush_task(self, browser_session: BrowserSession) -> None:
        """如果尚未运行，则启动定期刷新任务。"""
        if not self._flush_task:
            self._flush_task = asyncio.create_task(
                self._periodic_flush_loop(browser_session)
            )

    async def _execute_start_recording(self, browser_session: BrowserSession) -> str:
        """执行开始录制JS并处理结果状态。"""
        cdp_session = await browser_session.get_or_create_cdp_session()

        result = await cdp_session.cdp_client.send.Runtime.evaluate(
            params={"expression": _get_start_recording_js(), "returnByValue": True},
            session_id=cdp_session.session_id,
        )

        value = result.get("result", {}).get("value", {})
        status = value.get("status") if isinstance(value, dict) else value

        if status == "started":
            await self._set_recording_flag(browser_session, True)
            await self._start_flush_task(browser_session)
            logger.info("Recording started")
            return "Recording started"

        if status == "already_recording":
            await self._set_recording_flag(browser_session, True)
            await self._start_flush_task(browser_session)
            logger.debug("Recording already active")
            return "Already recording"

        if status == "load_failed":
            return await self._handle_rrweb_load_failure(browser_session, "load_failed")

        self._is_recording = False
        logger.info(f"Recording start failed: unknown status '{status}'")
        return f"Unknown status: {status}"

    async def start(self, browser_session: BrowserSession) -> str:
        """开始 rrweb 会话记录。

        使用基于事件驱动的 Promise 等待 rrweb 加载，避免轮询反模式。 这会根据需要等待
        足够长的时间，如果加载失败，则会立即失败。

        每个记录会话都会在 output_dir 下创建一个新的带有时间戳的子文件夹，以确保多个
        启动/停止周期不会混合事件。

        Returns:
            指示成功或失败的状态消息。

        Note:
            面向用户的操作：返回错误字符串，在警告处记录意外错误（请参阅模块文档字符
            串中的错误处理策略）。
        """
        if not self._scripts_injected:
            await self.inject_scripts(browser_session)

        self._initialize_session_state()

        try:
            error_msg = await self._ensure_rrweb_loaded(browser_session)
            if error_msg:
                return error_msg

            return await self._execute_start_recording(browser_session)

        except Exception as e:
            # 面向用户的操作：在警告处登录，返回错误字符串
            self._is_recording = False
            logger.warning(f"Recording start failed: {e}")
            return f"Error starting recording: {str(e)}"

    async def stop(self, browser_session: BrowserSession) -> str:
        """停止 rrweb 记录并保存剩余事件。

        停止定期刷新任务，从浏览器收集所有剩余事件，并将它们保存到最终编号为 JSON 的
        文件中。

        Returns:
            包含保存目录和文件计数的摘要消息。

        Note:
            面向用户的操作：返回错误字符串，在警告处记录意外错误（请参阅模块文档字符
            串中的错误处理策略）。
        """
        if not self._is_recording:
            return "Error: Not recording. Call browser_start_recording first."

        try:
            # 首先停止定期刷新任务
            self._is_recording = False
            if self._flush_task:
                self._flush_task.cancel()
                try:
                    await self._flush_task
                except (asyncio.CancelledError, Exception):
                    pass
                self._flush_task = None

            cdp_session = await browser_session.get_or_create_cdp_session()

            # 停止当前页面录制并获取剩余事件
            result = await cdp_session.cdp_client.send.Runtime.evaluate(
                params={"expression": _get_stop_recording_js(), "returnByValue": True},
                session_id=cdp_session.session_id,
            )

            current_page_data = json.loads(result.get("result", {}).get("value", "{}"))
            current_page_events = current_page_data.get("events", [])

            async with self._lock:
                if current_page_events:
                    self._events.extend(current_page_events)
                if self._events:
                    self._save_and_clear_events()
                total_events = self._storage.total_events
                total_files = self._storage.file_count

            await self._set_recording_flag(browser_session, False)
            session_dir_used = self._storage.session_dir

            logger.info(
                f"Recording stopped: {total_events} events saved to "
                f"{total_files} file(s) in {session_dir_used}"
            )

            summary = (
                f"Recording stopped. Captured {total_events} events "
                f"in {total_files} file(s)."
            )
            if session_dir_used:
                summary += f" Saved to: {session_dir_used}"

            return summary

        except Exception as e:
            # 面向用户的操作：在警告处登录，返回错误字符串
            self._is_recording = False
            if self._flush_task:
                self._flush_task.cancel()
                self._flush_task = None
            logger.warning(f"Recording stop failed: {e}")
            return f"Error stopping recording: {str(e)}"

    async def restart_on_new_page(self, browser_session: BrowserSession) -> None:
        """导航后在新页面上重新开始录制。

        使用基于事件驱动的 Promise 等待 rrweb 准备好，然后启动新的记录会话。 当录音处
        于活动状态时，导航后自动调用。

        Note:
            内部操作：记录在 DEBUG，从不引发（请参阅模块文档字符串中的错误处理策略）
            。
        """
        if not self._is_recording:
            return

        try:
            load_result = await self._wait_for_rrweb_load(browser_session)

            if not load_result.get("success"):
                error = load_result.get("error", "unknown")
                logger.debug(f"Recording restart skipped: rrweb {error}")
                return

            cdp_session = await browser_session.get_or_create_cdp_session()
            result = await cdp_session.cdp_client.send.Runtime.evaluate(
                params={
                    "expression": _get_start_recording_simple_js(),
                    "returnByValue": True,
                },
                session_id=cdp_session.session_id,
            )

            value = result.get("result", {}).get("value", {})
            status = value.get("status") if isinstance(value, dict) else value

            if status == "started":
                logger.debug("Recording restarted on new page")
            elif status == "already_recording":
                logger.debug("Recording already active on new page")
            else:
                logger.debug(f"Recording restart: unexpected status '{status}'")

        except Exception as e:
            # 内部操作：记录在DEBUG，不要中断（参见错误处理策略）
            logger.debug(f"Recording restart skipped: {e}")

    def reset(self) -> None:
        """重置录制会话状态以供重复使用。"""
        self._events = []
        self._is_recording = False
        self._storage.reset()
        self._flush_task = None
