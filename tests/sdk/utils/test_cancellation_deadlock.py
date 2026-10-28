"""证明取消的失败测试不会阻止同步代码。

两个表现相同问题的不同方面——一个任务被阻塞在某个地方同步调用 futex / 均衡 I/O / C 级
别锁) 不能通过 asyncio 来取消
``CancelledError`` 只能通过交付 ``await`` 点。 清理代码知道这一点 *tries* 可以取消，
但中途放弃超时，留下僵尸线程直到进程被杀死，这些
累积。

测试 1 — ``AsyncExecutor.close()`` 永远挂在工作线程中阻塞的任务上
         线程（PR#4548 解决的错误）。

测试 2 — ``bubus`` EventBus 处理程序超时在超时之后记录错误
         但处理程序的工作人员线程永远活着，因为
         ``asyncio.wait_for``取消协程但不能中断下面阻塞的同步调用。 ``finally``块只等
         待0.1秒取消生效，然后放弃任务。

两个测试都在 ``main`` 上失败，并且在修复基础取消问题后应该会通过。
"""

import asyncio
import threading
import time

import pytest

from openhands.sdk.utils.async_executor import AsyncExecutor


# ── 测试1：AsyncExecutor.close()永远挂起────────────────────────────


@pytest.mark.xfail(
    strict=False,
    reason="AsyncExecutor cannot cancel synchronous work blocked in a worker thread",
)
def test_async_executor_close_hangs_on_blocking_task():
    """当任务在工作线程中被阻塞时，AsyncExecutor.close() 不得挂起
    线程忽略取消。

    如果没有修复 (PR #4548): ``close()`` 调用
    ``portal_cm.__exit__(None, None, None)`` 采用 anyio 的优雅路径 (
    ``cancel_remaining=False``) 并永远等待任务自行完成。

    修复后：``close()`` 取消剩余任务并将线程连接与超时绑定，因此即使任务忽略取消，它
    也会返回。
    """
    from anyio.to_thread import run_sync

    thread_alive = threading.Event()

    async def blocked_in_worker_thread():
        thread_alive.set()
        # 在工作人员线程返回之前，anyio 无法交付取消。
        await run_sync(lambda: time.sleep(300))

    executor = AsyncExecutor()
    executor.portal.start_task_soon(blocked_in_worker_thread)
    time.sleep(0.2)  # let the task start

    done = threading.Event()

    def _close():
        try:
            # 尝试使用超时（如果应用 PR #4548 则可用）； 回退到未修补的 close() 签名。
            #
            executor.close()
        finally:
            done.set()

    threading.Thread(target=_close, daemon=True).start()

    # 如果不修复，close() 将永远挂起 — 5 秒后失败而不是挂起。
    assert done.wait(timeout=5), (
        "AsyncExecutor.close() hung >5s on a task blocked in a worker thread. "
        "The task ignores cancellation (blocked in sync code), and close() "
        "does not bound the wait."
    )
    assert thread_alive.is_set(), "Task thread should have started"


# ── 测试2：布布斯EventBus超时离开僵尸线程──────────────────


@pytest.mark.xfail(
    strict=False,
    reason="bubus cannot cancel synchronous work blocked in a worker thread",
)
def test_bubus_timeout_does_not_free_blocked_handler_thread():
    """bubus EventBus 处理程序超时实际上必须释放线程，而不仅仅是
    记录警告并放弃它。

    当处理程序在同步代码 (e.g. 在 C 级锁) 上挂起的浏览器启动，``asyncio.wait_for`` 会
    取消 asyncio 任务，但无法中断底层的阻塞调
    用。 ``finally`` 块只等待 0.1 秒让取消生效，然后继续移动 — 让线程永远卡住。

    在生产环境中，这个累积了僵尸线程（一个浏览器启动失败后一个），直到线程队列耗尽，
    新对话创建卡住了。

    这个测试注册了一个在工作线程中阻塞的处理器线程，发送一个短事件超时，并断言在超时
    触发并清理运行后没有僵尸线程。
    """
    pytest.importorskip("bubus")
    from bubus import BaseEvent, EventBus

    thread_started = threading.Event()
    thread_should_stop = threading.Event()

    class TestEvent(BaseEvent):
        pass

    def _block_sync():
        # 模拟同步 C 级代码 (e.g. 浏览器启动卡在 C 级锁/剧作家内部的 futex）。 与
        # anyio.to_thread.run_sync 不同，原始 ThreadPoolExecutor 线程无法通过 asyncio 取
        # 消 - CancelledError 只能在等待点传递，并且 run_in_executor 不会取消底层线程。
        #
        thread_started.set()
        thread_should_stop.wait(timeout=30)
        return "done"

    async def blocking_handler(event):
        # run_in_executor 返回一个 Future； 取消 asyncio 任务会取消 Future 的等待，但不
        # 底层线程。
        #
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _block_sync)

    bus = EventBus(name="test_bus")
    bus.on(TestEvent, blocking_handler)
    bus._start()

    async def _run():
        # 分派事件 — 处理程序将阻塞 30 秒
        bus.dispatch(TestEvent(event_timeout=1.0))
        # step() will time out after the event's timeout (1s)
        await bus.step(timeout=1.0)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(asyncio.wait_for(_run(), timeout=5))
    except (TimeoutError, Exception):
        pass  # 预期 — 处理程序超时

    time.sleep(1)  # 给清理代码运行时间

    # 向线程发出停止信号，以便它在还活着的情况下可以退出
    thread_should_stop.set()
    time.sleep(0.5)

    loop.run_until_complete(bus.stop(timeout=1))
    loop.close()

    # 计数活动非守护进程线程 — 如果 bubus 正确取消了处理程序，则阻塞处理程序中不应有剩余
    # 线程。
    #
    active_worker_threads = [
        t
        for t in threading.enumerate()
        if t is not threading.main_thread() and t.is_alive() and not t.daemon
    ]

    # 这个断言FAILS是因为bubus的超时无法取消阻塞同步代码：
    assert len(active_worker_threads) == 0, (
        f"bubus timeout fired but {len(active_worker_threads)} thread(s) are still "
        "alive. The handler was blocked in synchronous code and "
        "asyncio.wait_for could not deliver cancellation. The finally block "
        "waited only 0.1s then abandoned the task, leaving zombie threads "
        "that accumulate until the thread pool is exhausted."
    )
