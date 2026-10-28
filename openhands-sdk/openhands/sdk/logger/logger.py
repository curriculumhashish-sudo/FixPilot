# simple_logger.py
"""
鼓励每个模块记录器的最小记录器设置，Rich 适合人类，JSON 适合机器。

用途：
    from openhands.sdk.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Hello from this module!")
"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler

import litellm
from pythonjsonlogger.json import JsonFormatter
from rich.console import Console

from openhands.sdk.logger._rich_handler import BoundedRichHandler


# ========= ENV（导入时加载）=========
LEVEL_MAP = (
    logging.getLevelNamesMapping()
    if hasattr(logging, "getLevelNamesMapping")
    else logging._nameToLevel
)

DEBUG = os.environ.get("DEBUG", "false").lower() in {"1", "true", "yes"}
ENV_LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
ENV_LOG_LEVEL = LEVEL_MAP.get(ENV_LOG_LEVEL_STR, logging.INFO)
if DEBUG:
    ENV_LOG_LEVEL = logging.DEBUG

ENV_LOG_TO_FILE = os.getenv("LOG_TO_FILE", "false").lower() in {"1", "true", "yes"}
ENV_LOG_DIR = os.getenv("LOG_DIR", "logs")
ENV_ROTATE_WHEN = os.getenv("LOG_ROTATE_WHEN", "midnight")
ENV_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "7"))

# 丰富 vs JSON
ENV_JSON = os.getenv("LOG_JSON", "false").lower() in {"1", "true", "yes"}
IN_CI = os.getenv("CI", "false").lower() in {"1", "true", "yes"} or bool(
    os.environ.get("GITHUB_ACTIONS")
)
ENV_RICH_TRACEBACKS = os.getenv("LOG_RICH_TRACEBACKS", "true").lower() in {
    "1",
    "true",
    "yes",
}


ENV_AUTO_CONFIG = os.getenv("LOG_AUTO_CONFIG", "true").lower() in {"1", "true", "yes"}
ENV_DEBUG_LLM = os.getenv("DEBUG_LLM", "false").lower() in {"1", "true", "yes"}


# ========= LiteLLM 控件 =========
_ENABLE_LITELLM_DEBUG = False
if ENV_DEBUG_LLM:
    confirmation = input(
        "\n⚠️ WARNING: You are enabling DEBUG_LLM which may expose sensitive "
        "information like API keys.\nThis should NEVER be enabled in production.\n"
        "Type 'y' to confirm you understand the risks: "
    )
    if confirmation.lower() == "y":
        _ENABLE_LITELLM_DEBUG = True
        litellm.suppress_debug_info = False
        litellm.set_verbose = True  # type: ignore
    else:
        print("DEBUG_LLM disabled due to lack of confirmation")
        litellm.suppress_debug_info = True
        litellm.set_verbose = False  # type: ignore
else:
    litellm.suppress_debug_info = True
    litellm.set_verbose = False  # type: ignore


def disable_logger(name: str, level: int = logging.CRITICAL) -> None:
    """按名称禁用或安静特定记录器。"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False


# 安静闲聊的第三方记录器
for name in ["litellm", "LiteLLM", "openai"]:
    disable_logger(name, logging.DEBUG if _ENABLE_LITELLM_DEBUG else logging.ERROR)
for name in ["httpcore", "httpx", "libtmux"]:
    disable_logger(name, logging.WARNING)


# ========= SETUP =========
def setup_logging(
    level: int | None = None,
    log_to_file: bool | None = None,
    log_dir: str | None = None,
    fmt: str | None = None,
    when: str | None = None,
    backup_count: int | None = None,
) -> None:
    """配置根记录器。 所有子记录器都会继承此设置。"""
    lvl = ENV_LOG_LEVEL if level is None else level
    to_file = ENV_LOG_TO_FILE if log_to_file is None else log_to_file
    directory = ENV_LOG_DIR if log_dir is None else log_dir
    rotate_when = ENV_ROTATE_WHEN if when is None else when
    keep = ENV_BACKUP_COUNT if backup_count is None else backup_count

    root = logging.getLogger()
    old_level = root.level
    root.setLevel(lvl)

    # 为具有相同初始级别的任何现有记录器设置级别
    for logger in logging.root.manager.loggerDict.values():
        if isinstance(logger, logging.Logger) and logger.level == old_level:
            logger.setLevel(lvl)

    # 执行不清除现有处理程序； Uvicorn 在导入应用程序之前安装这些。 仅当还没有类似的流处
    # 理程序时才添加我们的流处理程序。
    #
    has_stream = any(isinstance(h, logging.StreamHandler) for h in root.handlers)

    if not has_stream:
        if ENV_JSON or IN_CI:
            # JSON 控制台处理程序
            ch = logging.StreamHandler()
            ch.setLevel(lvl)
            ch.setFormatter(
                JsonFormatter(
                    fmt="%(asctime)s %(levelname)s %(name)s "
                    "%(filename)s %(lineno)d %(message)s"
                )
            )
            root.addHandler(ch)
        else:
            # 丰富的控制台处理器
            rich_handler = BoundedRichHandler(
                console=Console(stderr=True),
                omit_repeated_times=False,
                rich_tracebacks=ENV_RICH_TRACEBACKS,
            )
            rich_handler.setFormatter(logging.Formatter("%(message)s"))
            rich_handler.setLevel(lvl)
            root.addHandler(rich_handler)

    if to_file:
        os.makedirs(directory, exist_ok=True)
        fh = TimedRotatingFileHandler(
            os.path.join(directory, "app.log"),
            when=rotate_when,
            backupCount=keep,
            encoding="utf-8",
        )
        fh.setLevel(lvl)
        if ENV_JSON:
            fh.setFormatter(
                JsonFormatter(
                    fmt="%(asctime)s %(levelname)s %(name)s "
                    "%(filename)s %(lineno)d %(message)s"
                )
            )
        else:
            log_fmt = (
                fmt
                or "%(asctime)s - %(levelname)s - %(name)s "
                "- %(filename)s:%(lineno)d - %(message)s"
            )
            fh.setFormatter(logging.Formatter(log_fmt))
        root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    """获取指定模块的记录器实例。

    此函数返回一个继承自根记录器设置的已配置记录器。 logger 支持两种格式化方式：JSON
    用于机器处理的人可读输出，以及 Rich 格式化用于人类可读输出。

    Args:
        name: 模块的名称，通常为 __name__。

    Returns:
        配置好的 Logger 实例。

    Example:
        >>> from openhands.sdk.logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("This is an info message")
        >>> logger.error("This is an error message")
    """
    logger = logging.getLogger(name)
    logger.propagate = True
    return logger


# 如果需要自动配置
if ENV_AUTO_CONFIG:
    setup_logging()
