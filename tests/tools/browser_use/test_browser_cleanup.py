"""测试浏览器工具执行器清理和资源管理。"""

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openhands.tools.browser_use import BrowserToolSet
from openhands.tools.browser_use.impl import BrowserToolExecutor


class TestBrowserCleanup:
    """测试浏览器工具执行器清理功能。"""

    @pytest.fixture
    def mock_executor(self):
        """创建一个模拟对象浏览器执行器用于测试。"""
        mock_server = MagicMock()
        mock_async_executor = MagicMock()

        with (
            patch.object(
                BrowserToolExecutor,
                "_ensure_chromium_available",
                return_value="/usr/bin/chromium",
            ),
            patch(
                "openhands.tools.browser_use.impl.CustomBrowserUseServer",
                return_value=mock_server,
            ),
            patch(
                "openhands.tools.browser_use.impl.AsyncExecutor",
                return_value=mock_async_executor,
            ),
        ):
            executor = BrowserToolExecutor()
            executor._server = mock_server
            executor._async_executor = mock_async_executor
            return executor

    async def test_close_browser_when_initialized(self, mock_executor):
        """测试初始化时关闭浏览器。"""
        mock_executor._initialized = True
        mock_executor._server._close_browser = AsyncMock(return_value="Browser closed")

        result = await mock_executor.close_browser()

        assert result == "Browser closed"
        assert mock_executor._initialized is False
        mock_executor._server._close_browser.assert_called_once()

    async def test_close_browser_when_not_initialized(self, mock_executor):
        """测试未初始化时关闭浏览器。"""
        mock_executor._initialized = False

        result = await mock_executor.close_browser()

        assert result == "No browser session to close"
        assert (
            not hasattr(mock_executor._server, "_close_browser")
            or not mock_executor._server._close_browser.called
        )

    async def test_cleanup_calls_close_all_sessions(self, mock_executor):
        """测试清理调用 _close_all_sessions 以正确终止浏览器。"""
        mock_executor._server._close_all_sessions = AsyncMock()

        await mock_executor.cleanup()

        mock_executor._server._close_all_sessions.assert_called_once()

    async def test_cleanup_falls_back_to_close_browser(self, mock_executor):
        """
        当 _close_all_sessions 缺失时，测试清理会回退到 close_browser。
        """
        mock_executor._initialized = True
        mock_executor._server._close_browser = AsyncMock(return_value="Browser closed")
        # 删除 _close_all_sessions，hasattr 返回 False
        del mock_executor._server._close_all_sessions

        await mock_executor.cleanup()

        mock_executor._server._close_browser.assert_called_once()

    async def test_cleanup_with_close_all_sessions_exception(self, mock_executor):
        """测试清理可以优雅地处理 _close_all_sessions 异常。"""
        mock_executor._server._close_all_sessions = AsyncMock(
            side_effect=Exception("Close sessions failed")
        )

        # 不应引发异常，仅记录警告
        await mock_executor.cleanup()

        mock_executor._server._close_all_sessions.assert_called_once()

    def test_close_method_calls_cleanup(self, mock_executor):
        """测试 close 方法通过异步执行器调用清理。"""
        mock_executor._async_executor.run_async = MagicMock()

        mock_executor.close()

        mock_executor._async_executor.run_async.assert_called_once_with(
            mock_executor.cleanup, timeout=30.0
        )
        mock_executor._async_executor.close.assert_called_once()

    def test_close_method_handles_cleanup_exception(self, mock_executor):
        """测试 close 方法是否正常处理清理异常。"""
        mock_executor._async_executor.run_async = MagicMock(
            side_effect=Exception("Cleanup failed")
        )

        # 不应引发异常
        mock_executor.close()

        mock_executor._async_executor.close.assert_called_once()

    def test_close_method_always_closes_async_executor(self, mock_executor):
        """测试 close 方法是否始终关闭异步执行程序，即使出现异常也是如此。"""
        mock_executor._async_executor.run_async = MagicMock(
            side_effect=Exception("Cleanup failed")
        )
        mock_executor._async_executor.close = MagicMock()

        mock_executor.close()

        mock_executor._async_executor.close.assert_called_once()

    def test_close_method_releases_shared_executor(self, mock_executor):
        """测试关闭共享执行器是否会清除单例引用。"""
        BrowserToolSet._shared_executor = mock_executor

        try:
            mock_executor.close()
            assert BrowserToolSet._shared_executor is None
        finally:
            BrowserToolSet._shared_executor = None

    def test_concurrent_close_serializes_shared_cleanup(self, mock_executor):
        """在清理结束之前，并发关闭不得释放创建锁。"""
        first_detached = threading.Event()
        first_can_continue = threading.Event()
        cleanup_started = threading.Event()
        cleanup_can_finish = threading.Event()
        second_detach_entered = threading.Event()
        detach_call_count = 0

        def controlled_detach():
            nonlocal detach_call_count
            detach_call_count += 1
            if detach_call_count == 1:
                BrowserToolSet._shared_executor_creation_lock.acquire()
                BrowserToolSet._shared_executor = None
                first_detached.set()
                assert first_can_continue.wait(timeout=2)
                return True

            second_detach_entered.set()
            return False

        def blocked_cleanup(*args, **kwargs):
            cleanup_started.set()
            assert cleanup_can_finish.wait(timeout=2)

        mock_executor._detach_shared_executor_for_close = MagicMock(
            side_effect=controlled_detach
        )
        mock_executor._async_executor.run_async = MagicMock(side_effect=blocked_cleanup)
        BrowserToolSet._shared_executor = mock_executor

        first_close = threading.Thread(target=mock_executor.close)
        first_close.start()
        assert first_detached.wait(timeout=2)

        second_close = threading.Thread(target=mock_executor.close)
        second_close.start()
        assert not second_detach_entered.wait(timeout=0.1)
        assert mock_executor._async_executor.run_async.call_count == 0

        first_can_continue.set()
        assert cleanup_started.wait(timeout=2)
        assert BrowserToolSet._shared_executor_creation_lock.locked()

        cleanup_can_finish.set()
        first_close.join(timeout=2)
        second_close.join(timeout=2)

        assert not first_close.is_alive()
        assert not second_close.is_alive()
        assert mock_executor._async_executor.run_async.call_count == 1
        assert mock_executor._async_executor.close.call_count == 1
        assert BrowserToolSet._shared_executor is None

    def test_close_method_stale_executor_does_not_acquire_shared_lock(
        self,
        mock_executor,
        monkeypatch,
    ):
        """过时的执行器终结器不应该与 create() 的锁竞争。"""

        class FailOnEnterLock:
            def __enter__(self):
                raise AssertionError("stale executor tried to acquire shared lock")

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        BrowserToolSet._shared_executor = None
        monkeypatch.setattr(
            BrowserToolSet,
            "_shared_executor_lock",
            FailOnEnterLock(),
        )

        mock_executor.close()
        assert BrowserToolSet._shared_executor is None

        mock_executor._async_executor.close.assert_called_once()

    def test_del_method_calls_close(self, mock_executor):
        """测试 __del__ 方法调用 close。"""
        with patch.object(mock_executor, "close") as mock_close:
            mock_executor.__del__()
            mock_close.assert_called_once()

    def test_del_method_handles_close_exception(self, mock_executor):
        """测试 __del__ 方法是否正常处理关闭异常。"""
        with patch.object(
            mock_executor, "close", side_effect=Exception("Close failed")
        ):
            # 不应引发异常
            mock_executor.__del__()

    def test_close_method_timeout_configuration(self, mock_executor):
        """测试 close 方法是否使用正确的超时进行清理。"""
        mock_executor._async_executor.run_async = MagicMock()

        mock_executor.close()

        # 验证超时设置为 30.0 秒
        mock_executor._async_executor.run_async.assert_called_once()
        args, kwargs = mock_executor._async_executor.run_async.call_args
        assert kwargs["timeout"] == 30.0

    async def test_cleanup_not_initialized_browser(self, mock_executor):
        """测试浏览器未初始化时的清理。"""
        mock_executor._initialized = False
        mock_executor._server._close_all_sessions = AsyncMock()

        await mock_executor.cleanup()

        # _close_all_sessions 仍然被调用（如果不存在会话则无操作）
        mock_executor._server._close_all_sessions.assert_called_once()
