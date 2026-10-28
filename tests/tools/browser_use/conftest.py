"""用于 browser_use 测试的共享测试实用程序。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openhands.sdk.tool.schema import TextContent
from openhands.tools.browser_use.definition import BrowserObservation
from openhands.tools.browser_use.impl import BrowserToolExecutor


@pytest.fixture
def mock_browser_server():
    """创建模拟对象 CustomBrowserUseServer。"""
    server = MagicMock()
    server._init_browser_session = AsyncMock()
    server._inject_scripts_to_session = AsyncMock()
    server._close_all_sessions = AsyncMock()
    return server


@pytest.fixture
def mock_browser_executor(mock_browser_server):
    """创建带有模拟的服务器的 BrowserToolExecutor。"""
    with patch.object(
        BrowserToolExecutor,
        "_ensure_chromium_available",
        return_value="/usr/bin/chromium",
    ):
        executor = BrowserToolExecutor()
    executor._server = mock_browser_server
    return executor


def create_mock_browser_response(
    output: str = "Success",
    error: str | None = None,
    screenshot_data: str | None = None,
):
    """创建模拟对象浏览器响应的帮助程序。"""
    if error:
        return BrowserObservation.from_text(
            text=error, is_error=True, screenshot_data=screenshot_data
        )
    return BrowserObservation.from_text(text=output, screenshot_data=screenshot_data)


def assert_browser_observation_success(
    observation: BrowserObservation, expected_output: str | None = None
):
    """断言浏览器观测结果表示成功。"""
    assert isinstance(observation, BrowserObservation)
    assert observation.is_error is False
    if expected_output:
        if isinstance(observation.content, str):
            output_text = observation.content
        else:
            output_text = "".join(
                [c.text for c in observation.content if isinstance(c, TextContent)]
            )
        assert expected_output in output_text


def assert_browser_observation_error(
    observation: BrowserObservation, expected_error: str | None = None
):
    """断言浏览器观测结果包含错误。"""
    assert isinstance(observation, BrowserObservation)
    assert observation.is_error is True
    if expected_error:
        assert expected_error in observation.text
