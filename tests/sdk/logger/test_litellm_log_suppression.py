"""测试默认情况下是否抑制 LiteLLM INFO 日志。"""

import logging


def test_litellm_loggers_suppressed():
    """测试 LiteLLM、LiteLLM 和 OpenAI 记录器是否设置为 ERROR 级别。"""
    # 导入日志模块以触发初始化

    # 检查 LiteLLM 记录器是否设置为 ERROR 级别
    for logger_name in ["litellm", "LiteLLM", "openai"]:
        llm_logger = logging.getLogger(logger_name)
        assert llm_logger.level == logging.ERROR, (
            f"Logger {logger_name} should be set to ERROR level, got {llm_logger.level}"
        )
        assert llm_logger.propagate is False, (
            f"Logger {logger_name} should not propagate"
        )


def test_litellm_info_logs_not_shown(caplog):
    """测试是否不显示 LiteLLM 中的 INFO 级别日志。"""
    # 导入日志模块以触发初始化

    # 将捕获级别设置为 INFO 以确保我们在发出日志时捕获 INFO 个日志
    #
    caplog.set_level(logging.INFO)

    # 创建记录器并发出 INFO 日志
    for logger_name in ["litellm", "LiteLLM", "openai"]:
        test_logger = logging.getLogger(logger_name)
        test_logger.info("This INFO log should not appear")
        test_logger.warning("This WARNING log should not appear")

    # 检查是否未捕获 INFO 或警告日志
    for record in caplog.records:
        assert record.name not in [
            "litellm",
            "LiteLLM",
            "openai",
        ], f"Log from {record.name} should not be captured: {record.message}"


def test_litellm_logger_level_blocks_info():
    """测试 INFO/警告日志是否被 ERROR 级别阻止。"""
    # 导入日志模块以触发初始化

    # 验证 INFO 和警告日志将被阻止
    for logger_name in ["litellm", "LiteLLM", "openai"]:
        test_logger = logging.getLogger(logger_name)
        # 如果记录器级别为 ERROR，则 INFO 和警告不应通过
        assert not test_logger.isEnabledFor(logging.INFO), (
            f"Logger {logger_name} should not be enabled for INFO"
        )
        assert not test_logger.isEnabledFor(logging.WARNING), (
            f"Logger {logger_name} should not be enabled for WARNING"
        )
        # 但 ERROR 应该通过
        assert test_logger.isEnabledFor(logging.ERROR), (
            f"Logger {logger_name} should be enabled for ERROR"
        )
