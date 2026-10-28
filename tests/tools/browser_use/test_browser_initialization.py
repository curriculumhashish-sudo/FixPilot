"""测试浏览器工具执行器初始化和超时处理。"""

from unittest.mock import MagicMock, patch

import pytest

from openhands.tools.browser_use.impl import BrowserToolExecutor
from openhands.tools.utils.timeout import TimeoutError


class TestBrowserInitialization:
    """测试浏览器工具执行器初始化。"""

    def test_initialization_timeout_handling(self):
        """测试初始化​​ 超时是否正确处理。"""
        with (
            patch.object(
                BrowserToolExecutor,
                "_ensure_chromium_available",
                return_value="/usr/bin/chromium",
            ),
            patch(
                "openhands.tools.browser_use.impl.run_with_timeout",
                side_effect=TimeoutError("Timeout occurred"),
            ),
        ):
            with pytest.raises(Exception) as exc_info:
                BrowserToolExecutor(init_timeout_seconds=5)

            assert "Browser tool initialization timed out after 5s" in str(
                exc_info.value
            )

    def test_initialization_custom_timeout(self):
        """使用自定义超时测试初始化​​。"""
        mock_server = MagicMock()

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
            patch("openhands.tools.browser_use.impl.run_with_timeout") as mock_timeout,
        ):
            BrowserToolExecutor(init_timeout_seconds=60)
            mock_timeout.assert_called_once()
            # 检查超时是否正确传递
            args, kwargs = mock_timeout.call_args
            assert args[1] == 60  # timeout_seconds参数

    def test_initialization_default_timeout(self):
        """使用默认值超时测试初始化。"""
        mock_server = MagicMock()

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
            patch("openhands.tools.browser_use.impl.run_with_timeout") as mock_timeout,
        ):
            BrowserToolExecutor()
            mock_timeout.assert_called_once()
            # 检查是否使用了默认值超时
            args, kwargs = mock_timeout.call_args
            assert args[1] == 30  # 默认 init_timeout_seconds

    def test_initialization_config_passed_to_server(self):
        """测试配置是否正确传递到服务器。"""
        mock_server = MagicMock()

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
                "openhands.tools.browser_use.impl.os.getuid",
                return_value=1000,
                create=True,
            ),  # 非root用户
        ):
            executor = BrowserToolExecutor(
                headless=False,
                allowed_domains=["example.com"],
                session_timeout_minutes=60,
                custom_param="test",
            )

            expected_config = {
                "headless": False,
                "allowed_domains": ["example.com"],
                "executable_path": "/usr/bin/chromium",
                "chromium_sandbox": True,  # 非 root 启用
                "custom_param": "test",
                "user_data_dir": executor._config["user_data_dir"],
            }

            assert executor._config == expected_config

    def test_initialization_server_creation_with_timeout(self):
        """测试服务器是否已使用正确的会话超时创建。"""
        mock_server = MagicMock()

        with (
            patch.object(
                BrowserToolExecutor,
                "_ensure_chromium_available",
                return_value="/usr/bin/chromium",
            ),
            patch(
                "openhands.tools.browser_use.impl.CustomBrowserUseServer",
                return_value=mock_server,
            ) as mock_server_class,
        ):
            BrowserToolExecutor(session_timeout_minutes=45)

            mock_server_class.assert_called_once_with(session_timeout_minutes=45)

    def test_initialization_async_executor_created(self):
        """测试异步执行程序是否已正确创建。"""
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

            assert executor._async_executor is mock_async_executor
            assert executor._initialized is False

    def test_initialization_chromium_not_available(self):
        """当 Chromium 不可用时测试初始化。"""
        with patch.object(
            BrowserToolExecutor,
            "_ensure_chromium_available",
            side_effect=Exception("Chromium not found"),
        ):
            with pytest.raises(Exception) as exc_info:
                BrowserToolExecutor()

            # 异常应该包含在超时错误消息中
            assert "Browser tool initialization timed out" in str(
                exc_info.value
            ) or "Chromium not found" in str(exc_info.value)

    def test_call_method_delegates_to_async_executor(self):
        """测试 __call__ 方法是否正确委托给异步执行器。"""
        from openhands.tools.browser_use.definition import BrowserObservation

        mock_server = MagicMock()
        mock_async_executor = MagicMock()
        mock_action = MagicMock()
        expected_result = BrowserObservation.from_text(text="OK")

        mock_async_executor.run_async.return_value = expected_result

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
            result = executor(mock_action)

            assert result is expected_result
            mock_async_executor.run_async.assert_called_once_with(
                executor._execute_action, mock_action, timeout=300.0
            )

    def test_call_method_timeout_configuration(self):
        """测试 __call__ 方法是否使用正确的超时。"""
        from openhands.tools.browser_use.definition import BrowserObservation

        mock_server = MagicMock()
        mock_async_executor = MagicMock()
        mock_async_executor.run_async.return_value = BrowserObservation.from_text(
            text="OK"
        )
        mock_action = MagicMock()

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
            executor(mock_action)

            # 验证超时设置为 300.0 秒（5 分钟）
            mock_async_executor.run_async.assert_called_once()
            args, kwargs = mock_async_executor.run_async.call_args
            assert kwargs["timeout"] == 300.0


class TestUniqueUserDataDir:
    """测试每个执行程序实例的唯一 user_data_dir。"""

    def test_two_executors_get_distinct_profile_dirs(self):
        """两个 BrowserToolExecutor 实例必须获得不同的 user_data_dir
        值，以便崩溃会话的 SingletonLock 无法阻止另一个会话。"""
        mock_server = MagicMock()

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
                "openhands.tools.browser_use.impl.os.getuid",
                return_value=1000,
                create=True,
            ),
        ):
            executor_a = BrowserToolExecutor()
            executor_b = BrowserToolExecutor()

            dir_a = executor_a._config["user_data_dir"]
            dir_b = executor_b._config["user_data_dir"]

            assert dir_a != dir_b, (
                "Two executor instances must have distinct user_data_dir values"
            )
            assert "browseruse" in dir_a and "profiles" in dir_a
            assert "browseruse" in dir_b and "profiles" in dir_b

    def test_explicit_user_data_dir_overrides_default(self):
        """通过 **config 传递的显式 user_data_dir 必须覆盖
        唯一的默认值。"""
        mock_server = MagicMock()

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
                "openhands.tools.browser_use.impl.os.getuid",
                return_value=1000,
                create=True,
            ),
        ):
            custom_dir = "/tmp/my-custom-browser-profile"
            executor = BrowserToolExecutor(user_data_dir=custom_dir)

            assert executor._config["user_data_dir"] == custom_dir
