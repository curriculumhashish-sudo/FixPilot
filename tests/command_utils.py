"""用于通过 shell 执行的测试的可移植命令生成器。"""

from __future__ import annotations

import math
import os
import shlex
import subprocess
import sys
from pathlib import Path


def shell_join(args: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(args)
    return shlex.join(args)


def python_command(script: str) -> str:
    return shell_join([sys.executable, "-c", script])


def touch_command(path: str | Path) -> str:
    return python_command(f"from pathlib import Path; Path({str(path)!r}).touch()")


def sleep_command(seconds: float) -> str:
    if not math.isfinite(seconds):
        raise ValueError("seconds must be finite")
    return python_command(f"import time; time.sleep({seconds!r})")
