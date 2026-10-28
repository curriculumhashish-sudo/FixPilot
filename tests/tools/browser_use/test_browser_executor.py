"""测试 BrowserToolExecutor 集成逻辑。"""

import asyncio
import builtins
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch
from urllib.request import urlopen

import pytest

from openhands.sdk.utils.async_executor import AsyncExecutor
from openhands.tools.browser_use.definition import (
    BrowserClickAction,
    BrowserGetStateAction,
    BrowserNavigateAction,
    BrowserObservation,
)
from openhands.tools.browser_use.impl import (
    DEFAULT_BROWSER_ACTION_TIMEOUT_SECONDS,
    BrowserToolExecutor,
)

from .conftest import (
    assert_browser_observation_error,
    assert_browser_observation_success,
)


class _ThreadedSlowServer(ThreadingHTTPServer):
    daemon_threads = True


class SlowServiceBrowserExecutor(BrowserToolExecutor):
    """阻止实时 HTTP 请求的最小浏览器执行器。"""

    def __init__(self, action_timeout_seconds: float):
        self._server = cast(Any, SimpleNamespace(_is_recording=False))
        self._config = {}
        self._initialized = True
        self._async_executor = AsyncExecutor()
        self._cleanup_initiated = False
        self._action_timeout_seconds = action_timeout_seconds
        self.full_output_save_dir = None
        self._consecutive_failures = 0

    async def navigate(self, url: str, new_tab: bool = False) -> str:
        del new_tab
        return await asyncio.to_thread(self._fetch_url, url)

    def close(self) -> None:
        return

    @staticmethod
    def _fetch_url(url: str) -> str:
        with urlopen(url, timeout=30) as response:
            return response.read().decode()


@pytest.fixture
def slow_service():
    """提供一个端点那要足够长的时间才能触发一个超时。"""
    request_started = threading.Event()

    class SlowHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            request_started.set()
            time.sleep(5)
            body = b"slow response"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A003
            _ = (format, args)
            return

    server = _ThreadedSlowServer(("127.0.0.1", 0), SlowHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host = server.server_address[0]
        port = server.server_address[1]
        yield f"http://{host}:{port}", request_started
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_browser_executor_initialization():
    """测试 BrowserToolExecutor 初始化是否正确。"""
    with patch.object(
        BrowserToolExecutor,
        "_ensure_chromium_available",
        return_value="/usr/bin/chromium",
    ):
        executor = BrowserToolExecutor()

    assert executor._config["headless"] is True
    assert executor._config["allowed_domains"] == []
    assert executor._initialized is False
    assert executor._server is not None
    assert executor._async_executor is not None
    assert executor._action_timeout_seconds == DEFAULT_BROWSER_ACTION_TIMEOUT_SECONDS


def test_browser_executor_config_passing():
    """测试配置是否正确通过。"""
    with patch.object(
        BrowserToolExecutor,
        "_ensure_chromium_available",
        return_value="/usr/bin/chromium",
    ):
        executor = BrowserToolExecutor(
            session_timeout_minutes=60,
            headless=False,
            allowed_domains=["example.com", "test.com"],
            action_timeout_seconds=12.5,
            custom_param="value",
        )

    assert executor._config["headless"] is False
    assert executor._config["allowed_domains"] == ["example.com", "test.com"]
    assert executor._config["custom_param"] == "value"
    assert executor._action_timeout_seconds == 12.5


def test_browser_executor_rejects_non_positive_action_timeout():
    """测试 BrowserToolExecutor 是否验证操作超时。"""
    with patch("openhands.tools.browser_use.impl.run_with_timeout"):
        with patch.object(BrowserToolExecutor, "_ensure_chromium_available"):
            with patch("openhands.tools.browser_use.impl.CustomBrowserUseServer"):
                with patch("openhands.tools.browser_use.impl.AsyncExecutor"):
                    with pytest.raises(
                        ValueError,
                        match="action_timeout_seconds must be greater than 0",
                    ):
                        BrowserToolExecutor(action_timeout_seconds=0)


@patch("openhands.tools.browser_use.impl.BrowserToolExecutor.navigate")
async def test_browser_executor_action_routing_navigate(
    mock_navigate, mock_browser_executor
):
    """测试导航操作是否正确路由。"""
    mock_navigate.return_value = "Navigation successful"

    action = BrowserNavigateAction(url="https://example.com", new_tab=False)
    result = await mock_browser_executor._execute_action(action)

    mock_navigate.assert_called_once_with("https://example.com", False)
    assert_browser_observation_success(result, "Navigation successful")


@patch("openhands.tools.browser_use.impl.BrowserToolExecutor.click")
async def test_browser_executor_action_routing_click(mock_click, mock_browser_executor):
    """测试单击操作是否正确路由。"""
    mock_click.return_value = "Click successful"

    action = BrowserClickAction(index=5, new_tab=True)
    result = await mock_browser_executor._execute_action(action)

    mock_click.assert_called_once_with(5, True)
    assert_browser_observation_success(result, "Click successful")


@patch("openhands.tools.browser_use.impl.BrowserToolExecutor.get_state")
async def test_browser_executor_action_routing_get_state(
    mock_get_state, mock_browser_executor
):
    """测试 get_state 操作是否正确路由并直接返回。"""
    expected_observation = BrowserObservation.from_text(
        text="State retrieved", screenshot_data="base64data"
    )
    mock_get_state.return_value = expected_observation

    action = BrowserGetStateAction(include_screenshot=True)
    result = await mock_browser_executor._execute_action(action)

    mock_get_state.assert_called_once_with(True)
    assert result is expected_observation


async def test_browser_executor_unsupported_action_handling(mock_browser_executor):
    """测试不支持的操作类型的处理。"""

    class UnsupportedAction:
        pass

    action = UnsupportedAction()
    result = await mock_browser_executor._execute_action(action)

    assert_browser_observation_error(result, "Unsupported action type")


@patch("openhands.tools.browser_use.impl.BrowserToolExecutor.navigate")
async def test_browser_executor_error_wrapping(mock_navigate, mock_browser_executor):
    """测试异常是否正确包装在 BrowserObservation 中。"""
    mock_navigate.side_effect = Exception("Browser error occurred")

    action = BrowserNavigateAction(url="https://example.com")
    result = await mock_browser_executor._execute_action(action)

    assert_browser_observation_error(result, "Browser operation failed")
    assert "Browser error occurred" in result.text


def test_browser_executor_async_execution(mock_browser_executor):
    """通过 call 方法测试异步执行是否有效。"""
    with patch.object(
        mock_browser_executor, "_execute_action", new_callable=AsyncMock
    ) as mock_execute:
        expected_result = BrowserObservation.from_text(text="Test result")
        mock_execute.return_value = expected_result

        action = BrowserNavigateAction(url="https://example.com")
        result = mock_browser_executor(action)

        assert result is expected_result
        mock_execute.assert_called_once_with(action)


def test_browser_executor_timeout_wrapping_live_service(slow_service):
    """测试实时慢速服务超时变为 BrowserObservation。"""
    slow_url, request_started = slow_service
    executor = SlowServiceBrowserExecutor(action_timeout_seconds=1)

    try:
        result = executor(BrowserNavigateAction(url=slow_url))
    finally:
        executor.close()

    assert request_started.wait(timeout=1), "The slow service was never queried"
    assert_browser_observation_error(result, "Browser operation failed")
    assert "timed out after 1 seconds" in result.text


def test_browser_executor_timeout_wrapping(mock_browser_executor):
    """测试浏览器操作超时返回 BrowserObservation 错误。"""
    mock_browser_executor._action_timeout_seconds = 7

    with patch.object(
        mock_browser_executor._async_executor,
        "run_async",
        side_effect=builtins.TimeoutError(),
    ):
        action = BrowserNavigateAction(url="https://example.com")
        result = mock_browser_executor(action)

    assert_browser_observation_error(result, "Browser operation failed")
    assert "timed out after 7 seconds" in result.text


def test_issue_2412_consecutive_failures_reset_session(mock_browser_executor):
    """MAX_CONSECUTIVE_FAILURES 超时之后，应重置会话。

    当浏览器崩溃时，每个后续操作都会针对死会话超时。 在连续失败足够多次后，执行器应该
    设置 _initialized=False，以便下次调用重新创建浏览器会话，而不是
    继续循环死掉的会话。

    See: https://github.com/OpenHands/software-agent-sdk/issues/2412
    """
    from openhands.tools.browser_use.impl import MAX_CONSECUTIVE_FAILURES

    mock_browser_executor._initialized = True

    with patch.object(
        mock_browser_executor._async_executor,
        "run_async",
        side_effect=builtins.TimeoutError(),
    ):
        action = BrowserNavigateAction(url="https://example.com")

        # 第一个 (MAX_CONSECUTIVE_FAILURES - 1) 次失败应重置不
        for i in range(MAX_CONSECUTIVE_FAILURES - 1):
            result = mock_browser_executor(action)
            assert result.is_error is True
            assert mock_browser_executor._initialized is True, (
                f"Session reset too early on failure {i + 1}"
            )
            assert "reset" not in result.text.lower()

        # 下一次失败会触发重置
        result = mock_browser_executor(action)
        assert result.is_error is True
        assert mock_browser_executor._initialized is False
        assert "reset" in result.text.lower()
        assert mock_browser_executor._consecutive_failures == 0


def test_issue_2412_success_resets_failure_counter(mock_browser_executor):
    """成功的操作应该重置连续失败计数器。

    See: https://github.com/OpenHands/software-agent-sdk/issues/2412
    """
    mock_browser_executor._initialized = True

    # 模拟2次失败
    with patch.object(
        mock_browser_executor._async_executor,
        "run_async",
        side_effect=builtins.TimeoutError(),
    ):
        action = BrowserNavigateAction(url="https://example.com")
        mock_browser_executor(action)
        mock_browser_executor(action)

    assert mock_browser_executor._consecutive_failures == 2

    # 现在成功了
    success_result = BrowserObservation.from_text(text="OK")
    with patch.object(
        mock_browser_executor._async_executor,
        "run_async",
        return_value=success_result,
    ):
        result = mock_browser_executor(action)

    assert result.is_error is False
    assert mock_browser_executor._consecutive_failures == 0


def test_issue_2412_action_errors_do_not_trigger_reset(mock_browser_executor):
    """常规操作错误应不计入崩溃检测。

    只有超时表示浏览器可能已失效。 诸如无效选择器或缺少元素之类的错误是正常的智能体错
    误。

    See: https://github.com/OpenHands/software-agent-sdk/issues/2412
    """
    from openhands.tools.browser_use.impl import MAX_CONSECUTIVE_FAILURES

    mock_browser_executor._initialized = True

    error_result = BrowserObservation.from_text(text="Element not found", is_error=True)
    with patch.object(
        mock_browser_executor._async_executor,
        "run_async",
        return_value=error_result,
    ):
        action = BrowserNavigateAction(url="https://example.com")
        for _ in range(MAX_CONSECUTIVE_FAILURES + 1):
            mock_browser_executor(action)

    # 尽管存在许多操作错误，但仍应重置会话不
    assert mock_browser_executor._initialized is True
    assert mock_browser_executor._consecutive_failures == 0


def test_issue_2412_degraded_timeout_after_failures(mock_browser_executor):
    """连续 2 次以上超时失败后，降级超时开始生效。

    See: https://github.com/OpenHands/software-agent-sdk/issues/2412
    """
    from openhands.tools.browser_use.impl import DEGRADED_TIMEOUT_SECONDS

    mock_browser_executor._initialized = True
    mock_browser_executor._action_timeout_seconds = 300.0

    action = BrowserNavigateAction(url="https://example.com")

    # 第一次调用失败 — 使用正常超时
    with patch.object(
        mock_browser_executor._async_executor,
        "run_async",
        side_effect=builtins.TimeoutError(),
    ) as mock_run:
        mock_browser_executor(action)
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 300.0

    # 第二次调用仍然使用正常的超时（降级在 2+ 时开始）
    with patch.object(
        mock_browser_executor._async_executor,
        "run_async",
        side_effect=builtins.TimeoutError(),
    ) as mock_run:
        mock_browser_executor(action)
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 300.0

    # 第三次调用应使用降级的超时进行操作。
    # 注意：重置还会调用 run_async 进行清理，因此我们检查
    # 第一次调用（操作），而不是最后一次调用（清理）。
    with patch.object(
        mock_browser_executor._async_executor,
        "run_async",
        side_effect=builtins.TimeoutError(),
    ) as mock_run:
        mock_browser_executor(action)
        # 第一个调用是操作（降级超时），如果重置触发，第二个调用可能是清理（5 秒）。
        #
        _, kwargs = mock_run.call_args_list[0]
        assert kwargs["timeout"] == DEGRADED_TIMEOUT_SECONDS


async def test_browser_executor_initialization_lazy(mock_browser_executor):
    """测试浏览器会话初始化是否是惰性的。"""
    assert mock_browser_executor._initialized is False

    await mock_browser_executor._ensure_initialized()

    assert mock_browser_executor._initialized is True
    mock_browser_executor._server._init_browser_session.assert_called_once()


async def test_browser_executor_initialization_idempotent(mock_browser_executor):
    """测试初始化是否幂等。"""
    await mock_browser_executor._ensure_initialized()
    await mock_browser_executor._ensure_initialized()

    # 应该只被调用一次
    assert mock_browser_executor._server._init_browser_session.call_count == 1


async def test_start_recording_initializes_session(mock_browser_executor):
    """测试 start_recording 是否以正确的状态初始化记录会话。"""
    import tempfile
    from unittest.mock import AsyncMock

    from openhands.tools.browser_use.recording import RecordingSession

    # 设置模拟对象 CDP 会话来模拟成功的 rrweb 加载
    mock_cdp_session = AsyncMock()
    mock_cdp_session.session_id = "test-session"
    mock_cdp_session.cdp_client.send.Runtime.evaluate = AsyncMock(
        side_effect=[
            # 第一次调用：等待rrweb加载（返回成功）
            {"result": {"value": {"success": True}}},
            # 第二次调用：开始录音（返回开始）
            {"result": {"value": {"status": "started"}}},
        ]
    )
    mock_cdp_session.cdp_client.send.Page.addScriptToEvaluateOnNewDocument = AsyncMock(
        return_value={"identifier": "script-1"}
    )

    mock_browser_session = AsyncMock()
    mock_browser_session.get_or_create_cdp_session = AsyncMock(
        return_value=mock_cdp_session
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建一个真实的 RecordingSession 并测试其行为使用 output_dir - start() 将创建一
        # 个带时间戳的子文件夹
        #
        session = RecordingSession(output_dir=temp_dir)
        result = await session.start(mock_browser_session)

        # 验证会话状态是否已正确初始化
        assert session.is_active is True
        assert result == "Recording started"
        assert session._scripts_injected is True
        # 验证是否已创建带时间戳的子文件夹
        assert session.session_dir is not None
        assert session.session_dir.startswith(temp_dir)
        assert "recording-" in session.session_dir


async def test_stop_recording_returns_summary_with_event_counts():
    """测试 stop_recording 返回包含事件计数的准确摘要。"""
    import json
    import os
    import tempfile
    from unittest.mock import AsyncMock

    from openhands.tools.browser_use.recording import RecordingSession

    with tempfile.TemporaryDirectory() as temp_dir:
        # 使用一些事件创建处于 RECORDING 状态的记录会话
        session = RecordingSession()
        session._storage._session_dir = temp_dir
        session._is_recording = True
        session._scripts_injected = True

        # 用一些事件预先填充事件缓冲区
        test_events = [{"type": 3, "timestamp": i, "data": {}} for i in range(25)]
        session._events.extend(test_events)

        # 设置模拟对象 CDP 会话以停止
        mock_cdp_session = AsyncMock()
        mock_cdp_session.session_id = "test-session"
        # 停止时从浏览器返回其他事件
        mock_cdp_session.cdp_client.send.Runtime.evaluate = AsyncMock(
            return_value={
                "result": {
                    "value": json.dumps(
                        {"events": [{"type": 3, "timestamp": 100, "data": {}}] * 17}
                    )
                }
            }
        )

        mock_browser_session = AsyncMock()
        mock_browser_session.get_or_create_cdp_session = AsyncMock(
            return_value=mock_cdp_session
        )

        # 停止录音
        result = await session.stop(mock_browser_session)

        # 验证摘要包含准确的计数
        assert "Recording stopped" in result
        assert "42 events" in result  # 25 个缓冲 + 17 个来自浏览器
        assert "1 file(s)" in result
        assert temp_dir in result

        # 验证状态转换
        assert session.is_active is False

        # 验证文件实际上是使用正确的内容创建的
        files = os.listdir(temp_dir)
        assert len(files) == 1
        with open(os.path.join(temp_dir, files[0])) as f:
            saved_events = json.load(f)
        assert len(saved_events) == 42


async def test_stop_recording_without_active_session_returns_error():
    """测试stop_recording在不记录时返回错误。"""
    from unittest.mock import AsyncMock

    from openhands.tools.browser_use.recording import RecordingSession

    # 创建一个不录制的会话
    session = RecordingSession()
    assert session.is_active is False

    mock_browser_session = AsyncMock()

    result = await session.stop(mock_browser_session)

    assert "Error" in result
    assert "Not recording" in result
