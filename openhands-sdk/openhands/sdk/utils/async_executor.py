import atexit
import inspect
import threading
import weakref
from collections.abc import Callable
from typing import Any

import anyio
from anyio.from_thread import BlockingPortal, start_blocking_portal

from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

# close() 等待传送门线程关闭的时间上限。 门户线程是一个守护进程线程，因此放弃它是安全的
# ； 永远阻止呼叫者并非如此。
#
# 默认值是特意简短的，用于生命周期 teardown：一旦剩余任务被取消，成功的门户停止和加入通
# 常会在毫秒内完成，因此10秒已经是一个健康的关闭的宽裕时间。 故意的 *不* 30年代继承自
# BrowserToolExecutor 清理 —— 那个值早于生命周期锁路径过长，可能包含对话的 teardown 锁等
# 待中。 参见 PR #4548 和 #4598 的讨论在描述中。
#
DEFAULT_CLOSE_TIMEOUT = 10.0


class AsyncExecutor:
    """
    围绕AnyIO的BlockingPortal执行异步代码的薄壳
    from synchronous contexts with proper resource and timeout handling.
    """

    def __init__(self):
        self._portal = None
        self._portal_cm = None
        self._lock = threading.Lock()
        self._atexit_registered = False

    @property
    def portal(self) -> BlockingPortal:
        """延迟启动的 ``BlockingPortal`` — 公共访问器。

        需要直接在门户循环上安排工作的调用者 (e.g. ``ACPAgent.astep`` 桥 ACP 通过循环
        等待
        ``portal.start_task_soon`` + ``asyncio.wrap_future``) 使用这个而不是
        ``run_async`` 因为
        他们需要未来，而不是结果。
        """
        return self._ensure_portal()

    def _ensure_portal(self) -> BlockingPortal:
        with self._lock:
            if self._portal is None:
                self._portal_cm = start_blocking_portal()
                self._portal = self._portal_cm.__enter__()
                # 注册 atexit 处理程序以确保解释器关闭时的清理
                if not self._atexit_registered:
                    # 使用weakref来避免让执行者保持活动状态
                    weak_self = weakref.ref(self)

                    def cleanup():
                        executor = weak_self()
                        if executor is not None:
                            try:
                                executor.close()
                            except Exception:
                                pass

                    atexit.register(cleanup)
                    self._atexit_registered = True
            return self._portal

    def run_async(
        self,
        awaitable_or_fn: Callable[..., Any] | Any,
        *args,
        timeout: float | None = None,
        **kwargs,
    ) -> Any:
        """
        从同步代码运行协程或异步函数。

        Args:
            awaitable_or_fn: 协程或异步功能
            *args: 位置参数（仅当 awaitable_or_fn 是函数时使用）
            timeout: 可选超时以秒为单位
            **kwargs: 关键字参数（仅当 awaitable_or_fn 是函数时使用）
        """
        portal = self._ensure_portal()

        # 构建协程
        if inspect.iscoroutine(awaitable_or_fn):
            coro = awaitable_or_fn
        elif inspect.iscoroutinefunction(awaitable_or_fn):
            coro = awaitable_or_fn(*args, **kwargs)
        else:
            raise TypeError("run_async expects a coroutine or async function")

        # 通过将异步函数包裹在 fail_after 中来应用超时
        if timeout is not None:

            async def _with_timeout():
                with anyio.fail_after(timeout):
                    return await coro

            return portal.call(_with_timeout)
        else:

            async def _execute():
                return await coro

            return portal.call(_execute)

    def close(self, timeout: float | None = DEFAULT_CLOSE_TIMEOUT):
        """关闭门户，而不会永远阻止调用者。

        语义学
        ---------
        这是**有限制的、尽力关闭，不保证清理。**

        - 它首先取消任何剩余的门户任务 (``portal.stop(True)``)，然后等待 ``timeout``
        秒以让门户线程退出。
        - 如果门户线程正在工作于  *不* 荣誉取消例如一个任务在工作者内部等待线程，任何
        io都无法中断直到线程返回（参见#4598）——等待超时，助手停止线程是
         **废弃的**. 门户线程这是一个守护进程，因此进程仍然可以退出。 但线程以及它持
         有的任何资源子进程这些处理程序、套接字、文件描述符等可能会一直存活到进程
        退出。 这是一个故意的权衡：永远阻止调用者会更糟糕。
        - 关闭路径是非上升的。 门户拆卸内的故障会被记录（带有回溯）并被吞掉，以便
          从析构函数调用 ``close()`` 始终是安全的，或者
          ``__exit__``.
        - **幂等。**在已经关闭的执行器上调用 ``close()`` 是一个空操作。

        Args:
            timeout: 等待门户线程退出的秒数。 ``None``
                无限期等待（之前的，预#4548行为）并且仅保留兼容性 — ** 不在任何生产路
                径上使用它**，因为这修复引入了这个补丁存在的无界挂起。 请
                参阅 PR #4548/问题 #4598。
        """
        with self._lock:
            portal_cm = self._portal_cm
            portal = self._portal
            self._portal_cm = None
            self._portal = None

        if portal_cm is None:
            return

        # 将所有者刻入线程名称中，以便在 py-spy / py-dump 跟踪中识别遗弃的线程（门户线程
        # 自身并不携带执行者身份）。
        #
        owner = type(self).__qualname__
        thread_name = f"{owner}-close"

        def _shutdown() -> None:
            try:
                # 取消仍在运行的任何内容。 如果没有这个，anyio 的优雅路径 (portal.stop(
                # cancel_remaining=False)) 会等待可能永远不会自行完成的正在进行的任务。
                #
                if portal is not None:
                    portal.call(portal.stop, True)
            except RuntimeError:
                pass  # 门户已经停止
            except Exception:
                # 拆卸必须保持非引发状态：从 __del__/__exit__/atexit 调用 close()。 使用
                # 回溯记录日志，以便故障保持可诊断状态，而不是减少到 str(exc)。
                #
                logger.warning(
                    "Error stopping BlockingPortal during AsyncExecutor.close "
                    "(owner=%s); teardown continues.",
                    owner,
                    exc_info=True,
                )
            try:
                portal_cm.__exit__(None, None, None)
            except Exception:
                logger.warning(
                    "Error closing BlockingPortal context manager during "
                    "AsyncExecutor.close (owner=%s); teardown continues.",
                    owner,
                    exc_info=True,
                )

        # 运行一个辅助端点线程，以便我们可以限制等待：门户线程可能会停留在不尊重取消的工
        # 作上（例如一个 await 被阻塞在 worker 线程中），并且任何io 会将其与超时的任何io
        #  一起。
        #
        try:
            waiter = threading.Thread(target=_shutdown, name=thread_name, daemon=True)
            waiter.start()
        except RuntimeError:
            # 解释器正在关闭并且不会启动新的线程。 门户线程是一个守护进程； 让过程收获它
            # 。
            #
            return

        waiter.join(timeout)
        if waiter.is_alive():
            # 抛弃是可观察的：指出所有者、超时和取消已经尝试过，因此操作员可以与 py-spy
            # / 裂缝资源进行关联。 根据 #4598，线程可能确实是 Python 不可中断的。
            #
            logger.warning(
                "AsyncExecutor (owner=%s): BlockingPortal did not shut down "
                "within %.1fs; abandoning its helper thread. Cancellation was "
                "attempted but the portal thread appears to be stuck on work "
                "that does not honour cancellation. Its resources (subprocess "
                "handles, sockets, fds) may remain alive until process exit. "
                "See issue #4598.",
                owner,
                float(timeout) if timeout is not None else -1.0,
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
