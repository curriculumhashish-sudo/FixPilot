"""browser_use 服务器在导入时重新配置全部记录器的日志记录，覆盖我们可能已应用的任何自
定义配置。

我们已经提交了一个补丁，应该可以让我们绕过这个问题
behavior: https://github.com/browser-use/browser-use/pull/3717

同时，使用此脚本而不是直接导入意味着日志记录仍将在 Agent Server 中工作。
"""

import logging
from dataclasses import dataclass, field

from openhands.sdk.utils.deprecation import warn_cleanup


warn_cleanup(
    "Monkey patching to prevent browser_use logging interference",
    cleanup_by="2.0.0",
    details=(
        "This workaround should be removed once browser_use fixes the "
        "problematic logging configuration code. The upstream PR #3717 "
        "(https://github.com/browser-use/browser-use/pull/3717) was closed "
        "without merge. As of browser_use 0.13.3, the server still calls "
        "logging.basicConfig(), logging.disable() and "
        "_ensure_all_loggers_use_stderr() during import and initialization, "
        "and provides no opt-out env var. Re-evaluate when browser_use "
        "changes that behavior."
    ),
)


def _noop(*args, **kwargs):
    """函数的无操作替换"""


@dataclass
class _MockManager:
    loggerDict: dict[str, logging.Logger] = field(default_factory=dict)


@dataclass
class _MockRoot:
    handlers: list[logging.Handler] = field(default_factory=list)
    manager: _MockManager = field(default_factory=_MockManager)

    def __getattr__(self, name: str):
        return _noop


# 导入前的猴子补丁
_orig_disable = logging.disable
_orig_basic_config = logging.basicConfig
_orig_root = logging.root
logging.disable = _noop
logging.basicConfig = _noop
logging.root = _MockRoot()
try:
    from browser_use.mcp import server  # noqa: E402
finally:
    # 导入后恢复日志记录
    logging.disable = _orig_disable
    logging.basicConfig = _orig_basic_config
    logging.root = _orig_root


# 这会在每次初始化时被调用 - 所以确保它是一个 noop
server._ensure_all_loggers_use_stderr = _noop

LogSafeBrowserUseServer = server.BrowserUseServer
