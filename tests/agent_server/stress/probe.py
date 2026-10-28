"""压力测试基于 psutil 的资源采样器。

后台 asyncio 任务中以固定节奏采样 RSS、num_fds、num_threads、cpu。 与测试夹具条目中采
取的基线不同，因此预算与热身相关，而不是绝对的 CI
 跑步者常数。
"""

import asyncio
import contextlib
import os
import time
from dataclasses import dataclass, field
from typing import Self

import psutil


@dataclass(frozen=True, slots=True)
class Sample:
    t: float
    rss_mb: float
    num_fds: int
    num_threads: int
    cpu_percent: float


@dataclass(slots=True)
class ResourceProbe:
    interval_s: float = 0.25
    _proc: psutil.Process = field(default_factory=lambda: psutil.Process(os.getpid()))
    _samples: list[Sample] = field(default_factory=list)
    _task: asyncio.Task | None = None
    _baseline: Sample | None = None
    _start_t: float = 0.0

    async def __aenter__(self) -> Self:
        # Prime cpu_percent — 第一次调用返回 0.0。
        self._proc.cpu_percent(interval=None)
        self._start_t = time.monotonic()
        self._baseline = self._take()
        self._samples.append(self._baseline)
        self._task = asyncio.create_task(self._loop())
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        # 最终的运行后示例 - 抑制，以便拆卸时的 psutil 打嗝无法掩盖已经从外部传播的异常
        # `async with` 身体。
        with contextlib.suppress(Exception):
            self._samples.append(self._take())

    async def _loop(self) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            while True:
                await asyncio.sleep(self.interval_s)
                self._samples.append(self._take())

    def _take(self) -> Sample:
        try:
            num_fds = self._proc.num_fds()
        except (AttributeError, psutil.AccessDenied):
            # psutil 仅在 POSIX 上公开 num_fds()； AttributeError 覆盖 Windows，
            # AccessDenied 覆盖沙箱内或不拥有该进程的情况。-1 是表示“不可用”的哨兵值；
            # peak_fds()/fd_delta() 会显式检查该值，使 FD 断言在这些环境中成为空操作。
            #
            num_fds = -1
        return Sample(
            t=time.monotonic() - self._start_t,
            rss_mb=self._proc.memory_info().rss / (1024 * 1024),
            num_fds=num_fds,
            num_threads=self._proc.num_threads(),
            cpu_percent=self._proc.cpu_percent(interval=None),
        )

    @property
    def baseline(self) -> Sample:
        assert self._baseline is not None, "ResourceProbe used outside async-with"
        return self._baseline

    @property
    def samples(self) -> list[Sample]:
        return list(self._samples)

    def peak_rss_mb(self) -> float:
        return max(s.rss_mb for s in self._samples)

    def peak_fds(self) -> int:
        """样品间的峰值 FD 计数。 在平台上返回 -1
        psutil 无法读取 FD（Windows； 沙盒进程）； 与
        ``fd_delta`` 而不是直接断言这一点。"""
        return max(s.num_fds for s in self._samples)

    def peak_threads(self) -> int:
        return max(s.num_threads for s in self._samples)

    def rss_delta_mb(self) -> float:
        return self.peak_rss_mb() - self.baseline.rss_mb

    def fd_delta(self) -> int:
        """FD 增长峰值减去基线。 在平台上返回 0
        基线读取失败（-1 哨兵值 from ``_take``），因此
        ``fd_delta() < budget`` 断言会默默地传递到那里，而不是触发丢失的测量。
        """
        if self.baseline.num_fds < 0:
            return 0
        return self.peak_fds() - self.baseline.num_fds
