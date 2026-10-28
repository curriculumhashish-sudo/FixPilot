"""测试 check_browser 功能。"""

from unittest.mock import MagicMock, patch


class TestCheckBrowser:
    """使用模拟的浏览器组件测试 check_browser 功能。"""

    def test_check_browser_success(self, capsys):
        """当浏览器正常工作时，测试 check_browser 返回 True。"""
        mock_result = MagicMock()
        mock_result.is_error = False
        mock_result.content = "Success"

        mock_executor = MagicMock()
        mock_executor.return_value = mock_result

        with (
            patch(
                "openhands.tools.preset.default.register_default_tools"
            ) as mock_register,
            patch(
                "openhands.tools.browser_use.impl.BrowserToolExecutor",
                return_value=mock_executor,
            ) as mock_executor_class,
        ):
            from openhands.agent_server.__main__ import check_browser

            result = check_browser()

            assert result is True
            mock_register.assert_called_once_with(enable_browser=True)
            mock_executor_class.assert_called_once_with(
                headless=True, session_timeout_minutes=2
            )
            mock_executor.close.assert_called_once()

            captured = capsys.readouterr()
            assert "Browser check passed" in captured.out

    def test_check_browser_failure_is_error(self, capsys):
        """当 result.is_error 为 True 时，测试 check_browser 返回 False。"""
        mock_result = MagicMock()
        mock_result.is_error = True
        mock_result.content = "Navigation failed"

        mock_executor = MagicMock()
        mock_executor.return_value = mock_result

        with (
            patch("openhands.tools.preset.default.register_default_tools"),
            patch(
                "openhands.tools.browser_use.impl.BrowserToolExecutor",
                return_value=mock_executor,
            ),
        ):
            from openhands.agent_server.__main__ import check_browser

            result = check_browser()

            assert result is False
            mock_executor.close.assert_called_once()

            captured = capsys.readouterr()
            assert "Browser check failed" in captured.out
            assert "Navigation failed" in captured.out

    def test_check_browser_failure_exception(self, capsys):
        """当引发异常时，测试 check_browser 返回 False。"""
        mock_executor = MagicMock()
        mock_executor.side_effect = RuntimeError("Browser crashed")

        with (
            patch("openhands.tools.preset.default.register_default_tools"),
            patch(
                "openhands.tools.browser_use.impl.BrowserToolExecutor",
                return_value=mock_executor,
            ),
        ):
            from openhands.agent_server.__main__ import check_browser

            result = check_browser()

            assert result is False
            mock_executor.close.assert_called_once()

            captured = capsys.readouterr()
            assert "Browser check failed" in captured.out
            assert "Browser crashed" in captured.out

    def test_check_browser_cleanup_on_executor_creation_failure(self, capsys):
        """测试 check_browser 优雅地处理执行器创建失败。"""
        with (
            patch("openhands.tools.preset.default.register_default_tools"),
            patch(
                "openhands.tools.browser_use.impl.BrowserToolExecutor",
                side_effect=RuntimeError("Chromium not found"),
            ),
        ):
            from openhands.agent_server.__main__ import check_browser

            result = check_browser()

            assert result is False

            captured = capsys.readouterr()
            assert "Browser check failed" in captured.out
            assert "Chromium not found" in captured.out

    def test_check_browser_str_conversion_for_content(self, capsys):
        """测试 result.content 是否正确转换为字符串。"""
        mock_result = MagicMock()
        mock_result.is_error = True
        # 使用非字符串内容验证str()转换
        mock_result.content = {"error": "complex error object"}

        mock_executor = MagicMock()
        mock_executor.return_value = mock_result

        with (
            patch("openhands.tools.preset.default.register_default_tools"),
            patch(
                "openhands.tools.browser_use.impl.BrowserToolExecutor",
                return_value=mock_executor,
            ),
        ):
            from openhands.agent_server.__main__ import check_browser

            result = check_browser()

            assert result is False

            captured = capsys.readouterr()
            assert "Browser check failed" in captured.out
            # 字典应该转换为字符串表示形式
            assert "error" in captured.out
