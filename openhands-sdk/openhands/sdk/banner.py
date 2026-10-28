"""OpenHands SDK 的启动横幅。

首次导入 SDK 时打印一条带有有用链接的欢迎消息。 可以通过设置OPENHANDS_SUPPRESS_BANNER
环境变量来抑制。
"""

import os
import sys


# 不受锁保护； 比赛中最糟糕的情况是横幅打印两次。
_BANNER_PRINTED = False


def _print_banner(version: str) -> None:
    """将 OpenHands SDK 启动横幅打印到 stderr。"""
    global _BANNER_PRINTED

    # 检查是否应抑制横幅（在设置标志之前先检查此项）
    suppress = os.environ.get("OPENHANDS_SUPPRESS_BANNER", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if suppress:
        return

    if _BANNER_PRINTED:
        return
    _BANNER_PRINTED = True

    banner = f"""\
+----------------------------------------------------------------------+
|  OpenHands SDK v{version:<53}|
|                                                                      |
|  Report a bug: github.com/OpenHands/software-agent-sdk/issues        |
|  Get help: openhands.dev/joinslack                                   |
|  Scale up: openhands.dev/product/sdk                                 |
|                                                                      |
|  Set OPENHANDS_SUPPRESS_BANNER=1 to hide this message                |
+----------------------------------------------------------------------+
"""
    print(banner, file=sys.stderr)
