"""运行时空闲感知终端超时策略。"""

import os
from collections.abc import Mapping


RUNTIME_IDLE_TIMEOUT_SECONDS_ENV = "OH_RUNTIME_IDLE_TIMEOUT_SECONDS"
MAX_FOREGROUND_TIMEOUT_RATIO = 0.9


def get_runtime_idle_timeout_seconds(
    env: Mapping[str, str] | None = None,
) -> float | None:
    """返回配置的运行时空闲超时（以秒为单位）（如果有）。

    runtime-API 将此值注入到托管运行时 pod 中。 没有空闲清理功能的本地和自托管部署可
    以将其保留为未设置，这会禁用前台终端超时上限。
    """
    raw = (env or os.environ).get(RUNTIME_IDLE_TIMEOUT_SECONDS_ENV)
    if raw is None or raw.strip() == "":
        return None

    try:
        value = float(raw)
    except ValueError:
        return None

    if value <= 0:
        return None
    return value


def get_max_foreground_timeout_seconds(
    runtime_idle_timeout_seconds: float | None = None,
) -> float | None:
    """返回最大安全前台终端超时，或未限制时返回 None。"""
    idle_timeout = (
        get_runtime_idle_timeout_seconds()
        if runtime_idle_timeout_seconds is None
        else runtime_idle_timeout_seconds
    )
    if idle_timeout is None:
        return None
    return idle_timeout * MAX_FOREGROUND_TIMEOUT_RATIO


def format_seconds(value: float) -> str:
    """紧凑地格式化第二个值以面向用户观测结果。"""
    return f"{value:g}"


def foreground_timeout_rejection_message(
    requested_timeout_seconds: float,
    runtime_idle_timeout_seconds: float,
) -> str:
    """为不安全的前景构建面向用户的拒绝超时。"""
    max_timeout = get_max_foreground_timeout_seconds(runtime_idle_timeout_seconds)
    assert max_timeout is not None
    ratio_percent = int(MAX_FOREGROUND_TIMEOUT_RATIO * 100)
    return (
        "Refusing to run foreground terminal command with "
        f"timeout={format_seconds(requested_timeout_seconds)}s.\n\n"
        "This runtime is subject to idle cleanup after "
        f"{format_seconds(runtime_idle_timeout_seconds)}s. Foreground terminal "
        f"commands are capped at {ratio_percent}% of that threshold, currently "
        f"{format_seconds(max_timeout)}s, so commands can return control before "
        "the runtime is considered idle.\n\n"
        "For long-running work, use a shorter timeout, omit the timeout to use "
        "the terminal soft-timeout/polling flow, or start the command in the "
        "background and poll its log file."
    )


def foreground_timeout_rejection_for(
    *,
    command: str,
    is_input: bool,
    timeout: float | None,
    runtime_idle_timeout_seconds: float | None = None,
) -> str | None:
    """如果终端操作运行不安全，则返回拒绝消息。"""
    if is_input or not command.strip() or timeout is None:
        return None

    idle_timeout = (
        get_runtime_idle_timeout_seconds()
        if runtime_idle_timeout_seconds is None
        else runtime_idle_timeout_seconds
    )
    max_timeout = get_max_foreground_timeout_seconds(idle_timeout)
    if idle_timeout is None or max_timeout is None or timeout <= max_timeout:
        return None

    return foreground_timeout_rejection_message(timeout, idle_timeout)
