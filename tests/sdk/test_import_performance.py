"""测试导入 openhands.sdk 是否在合理时间内完成。

这是一个性能回归防护：它生成一个新的 Python 进程，以便测量不会受到已导入模块的影响
pytest session.
"""

import subprocess
import sys


# 冷过程中 `import openhands.sdk` 的上限（秒）。 保持慷慨，这样 CI 机器就不会剥落，同时
# 仍然捕获意外的大量急切导入 (e.g. 在导入时加载层流）。
#
IMPORT_TIME_LIMIT_SECONDS = 10.0

# 平均运行次数子进程次。
_ITERATIONS = 5


def _measure_import_time_seconds() -> float:
    """将子进程中的挂钟秒返回到 `import openhands.sdk`。"""
    code = (
        "import time; "
        "start = time.perf_counter(); "
        "import openhands.sdk; "
        "elapsed = time.perf_counter() - start; "
        "print(elapsed)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        env=None,  # 继承当前环境
    )
    assert result.returncode == 0, (
        f"Import subprocess failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return float(result.stdout.strip())


def test_import_openhands_sdk_time():
    """openhands.sdk 的导入必须在时限内完成。"""
    times = [_measure_import_time_seconds() for _ in range(_ITERATIONS)]
    avg = sum(times) / len(times)
    print(
        f"\n[import-perf] openhands.sdk import times (s): {[f'{t:.3f}' for t in times]}"
    )
    print(f"[import-perf] average: {avg:.3f}s (limit: {IMPORT_TIME_LIMIT_SECONDS}s)")
    assert avg < IMPORT_TIME_LIMIT_SECONDS, (
        f"Average import time {avg:.3f}s exceeded {IMPORT_TIME_LIMIT_SECONDS}s limit. "
        f"Individual runs: {times}"
    )
