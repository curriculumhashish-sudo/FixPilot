"""uvicorn 的自定义日志记录配置以重用 SDK 的根记录器。"""

import logging
from typing import Any

from pythonjsonlogger.json import JsonFormatter

from openhands.sdk.logger import ENV_JSON, ENV_LOG_LEVEL, IN_CI


class UvicornAccessJsonFormatter(JsonFormatter):
    """用于提取 HTTP 字段的 uvicorn 访问日志的 JSON 格式化程序。

    Uvicorn 访问日志将 record.args 中的结构化数据作为元组传递：(client_addr, method,
    full_path,
    http_version, status_code)

    该格式化程序将它们提取到单独的 JSON 字段中，以便在 Datadog 等日志聚合系统中更好地
    查询和分析。
    """

    def add_fields(
        self,
        log_data: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_data, record, message_dict)

        # 从 uvicorn 访问日志中提取 HTTP 字段 args record.args 是 uvicorn 访问日志的元组
        # ：(client_addr, method, full_path, http_version, status_code)
        #
        args = record.args
        if isinstance(args, tuple) and len(args) >= 5:
            client_addr, method, full_path, http_version, status_code = args[:5]
            log_data["http.client_ip"] = client_addr
            log_data["http.method"] = method
            log_data["http.url"] = full_path
            log_data["http.version"] = http_version
            # uvicorn 中的 status_code 通常是一个 int，但处理边缘情况
            if isinstance(status_code, int):
                log_data["http.status_code"] = status_code
            elif isinstance(status_code, str) and status_code.isdigit():
                log_data["http.status_code"] = int(status_code)
            else:
                log_data["http.status_code"] = status_code


def get_uvicorn_logging_config() -> dict[str, Any]:
    """
    生成与 SDK 的根记录器集成的 uvicorn 日志记录配置。

    此函数创建一个日志记录配置：
    1. 保留 SDK 的根记录器配置
    2. 通过相同的处理程序路由 uvicorn 日志
    3. 当 LOG_JSON=True 或在 CI 中时，对访问日志使用 JSON 格式化程序
    4. 将 HTTP 字段提取为结构化 JSON 属性
    """
    use_json = ENV_JSON or IN_CI
    log_level = logging.getLevelName(ENV_LOG_LEVEL)

    # Base configuration
    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "incremental": False,
        "formatters": {},
        "handlers": {},
        "loggers": {
            # 常见记录器配置 - 传播到根
            "uvicorn": {
                "handlers": [],
                "level": log_level,
                "propagate": True,
            },
            "uvicorn.error": {
                "handlers": [],
                "level": log_level,
                "propagate": True,
            },
        },
    }

    if use_json:
        # 使用 HTTP 字段提取为访问日志定义 JSON 格式化程序
        config["formatters"]["access_json"] = {
            "()": UvicornAccessJsonFormatter,
            "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }

        # 定义访问日志的处理程序
        config["handlers"]["access_json"] = {
            "class": "logging.StreamHandler",
            "formatter": "access_json",
            "stream": "ext://sys.stderr",
        }

        # 访问记录器使用专用的 JSON 处理程序和 HTTP 字段提取
        config["loggers"]["uvicorn.access"] = {
            "handlers": ["access_json"],
            "level": log_level,
            "propagate": False,  # 不要双重登录
        }
    else:
        # 非JSON模式：将访问日志传播到根（使用丰富的处理程序）
        config["loggers"]["uvicorn.access"] = {
            "handlers": [],
            "level": log_level,
            "propagate": True,
        }

    return config


LOGGING_CONFIG = get_uvicorn_logging_config()
