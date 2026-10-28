"""测试 AsyncExecutor 关闭行为。"""

import threading
import time

import anyio
from anyio.to_thread import run_sync

from openhands.sdk.utils.async_executor import AsyncExecutor


def _close_in_background(executor: AsyncExecutor, **kwargs) -> threading.Event:
    """调用 close() off-线程，以便挂起使测试失败而不是冻结它。"""
    done = threading.Event()

    def run() -> None:
        executor.close(**kwargs)
        done.set()

    threading.Thread(target=run, daemon=True).start()
    return done


def test_close_returns_with_task_still_running():
    """close() 不得等待正在进行的任务自行完成。"""
    executor = AsyncExecutor()
    executor.portal.start_task_soon(anyio.sleep_forever)
    time.sleep(0.1)

    done = _close_in_background(executor)

    assert done.wait(timeout=10), "close() blocked on a task that never finishes"


def test_close_gives_up_on_uncancellable_task():
    """忽略取消的任务不得阻止 close() 超过超时。"""

    async def blocked_in_worker_thread() -> None:
        # 在工作人员线程返回之前，anyio 无法交付取消。
        await run_sync(lambda: time.sleep(30))

    executor = AsyncExecutor()
    executor.portal.start_task_soon(blocked_in_worker_thread)
    time.sleep(0.1)

    done = _close_in_background(executor, timeout=1.0)

    assert done.wait(timeout=15), "close() blocked on an uncancellable task"


def test_close_is_idempotent():
    executor = AsyncExecutor()
    _ = executor.portal

    executor.close()
    executor.close()


def test_close_without_started_portal():
    """close() 在一个从未启动门户的延迟创建的执行器上。"""
    AsyncExecutor().close()


def test_run_async_still_works_before_close():
    executor = AsyncExecutor()

    async def add(a: int, b: int) -> int:
        return a + b

    assert executor.run_async(add, 1, 2) == 3
    executor.close()
