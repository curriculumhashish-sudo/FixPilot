"""降低智能体终端的 CPU 优先级，这样它们就不会导致服务器饥饿。"""

import os
import platform
import shutil
from collections.abc import Mapping
from typing import Final


TERMINAL_PROCESS_PRIORITY_ENV: Final[str] = "OH_TERMINAL_PROCESS_PRIORITY"

# macOS很大程度上忽略了nice； 实用程序 QoS 夹钳是保持服务器响应的工具。 避免背景限制：它
# 还会严重限制 I/O。
#
_TASKPOLICY_PATH: Final[str] = "/usr/sbin/taskpolicy"
_LINUX_NICE_INCREMENT: Final[str] = "10"


def should_lower_process_priority(env: Mapping[str, str]) -> bool:
    """当终端环境选择退出 ``none`` 时，返回 False。"""
    value = env.get(TERMINAL_PROCESS_PRIORITY_ENV, "")
    return value.strip().lower() != "none"


def process_priority_prefix(env: Mapping[str, str]) -> list[str]:
    """返回以较低 CPU 优先级运行 shell 的 argv 前缀。

    这必须是 argv 前缀而不是 ``preexec_fn``：调用线程上设置的 macOS QoS 类无法保留
    ``exec``。 ``taskpolicy`` 和
     ``nice`` 都被 shell 启动的每个进程继承。
    """
    if not should_lower_process_priority(env):
        return []

    system = platform.system()
    if system == "Darwin" and os.path.exists(_TASKPOLICY_PATH):
        return [_TASKPOLICY_PATH, "-c", "utility"]
    if system == "Linux" and (nice_path := shutil.which("nice")) is not None:
        return [nice_path, "-n", _LINUX_NICE_INCREMENT]
    return []
