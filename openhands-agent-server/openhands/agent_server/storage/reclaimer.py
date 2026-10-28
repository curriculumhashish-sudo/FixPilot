import asyncio
import itertools
import shutil
import time
from contextlib import AbstractAsyncContextManager, suppress
from pathlib import Path
from typing import Final, Protocol
from uuid import UUID

from openhands.agent_server.storage.model import StoredRuntime, Tier
from openhands.agent_server.storage.selectors import caches, ignored_dirs
from openhands.agent_server.storage.trash import Trash
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

# 应用磁盘预算和保留的传递之间的秒数。
MAINTENANCE_INTERVAL: Final[float] = 300.0


class ReclaimableStorage(Protocol):
    """一个``Config.conversation_runtime``（本地，Docker）如何存储
    该主机上的对话。"""

    @property
    def root(self) -> Path:
        """运行时所在的地方； 垃圾放在这里，在同一个文件系统上。"""
        ...

    def runtime(self, conversation_id: UUID) -> StoredRuntime | None:
        """对话的存储运行时间，如果此处有 None，则为 None。"""
        ...

    def runtimes(self) -> list[StoredRuntime]:
        """每个存储的运行时间，最近最少活动的在前。"""
        ...

    def idle(self, conversation_id: UUID) -> AbstractAsyncContextManager[bool]:
        """保持运行时间静止； True 如果其中没有任何运行或启动。"""
        ...

    def archive(self, conversation_id: UUID) -> list[Path]:
        """将运行时间记录为存档； 返回要丢弃的内容。 谓之闲。"""
        ...

    async def on_archived(self, conversation_id: UUID) -> None: ...


class Reclaimer:
    """按层释放运行时模式为每个对话存储的内容。

    仅当存储保持运行时空闲时，文件才会移至垃圾箱； 垃圾箱会在后台删除它们。
    """

    def __init__(
        self,
        storage: ReclaimableStorage,
        *,
        disk_budget: float | None = None,
        retention_days: float | None = None,
    ) -> None:
        self.storage = storage
        self.disk_budget = disk_budget
        self.retention_days = retention_days
        self.trash = Trash(storage.root)
        self._maintenance: asyncio.Task[None] | None = None
        self._over_budget_warned = False

    async def start(self) -> None:
        """仅在任何运行时开始之前才是安全的：每个都被回收。"""
        for runtime in await asyncio.to_thread(self.storage.runtimes):
            await self.reclaim(runtime, Tier.CACHES)
        self.trash.empty_soon()
        if self.disk_budget or self.retention_days:
            self._maintenance = asyncio.create_task(self._maintenance_loop())

    async def shutdown(self) -> None:
        if self._maintenance is not None:
            self._maintenance.cancel()
            with suppress(asyncio.CancelledError):
                await self._maintenance
            self._maintenance = None
        await self.trash.close()

    async def run_pass(self) -> None:
        """应用一次配置的策略； 仅在释放某些内容时才记录。"""
        free_before = _free_bytes(self.storage.root)
        # 保留第一：归档的内容不再计入预算。
        archived = await self._enforce_retention()
        shed = await self._enforce_disk_budget()
        if not (archived or shed):
            return
        await self.trash.drain()
        logger.info(
            "Conversation storage: freed %.1f GB (archived %d runtimes, shed "
            "dependencies of %d), %s at %.0f%%",
            # 文件系统上的其他写入可能比少量回收更重要。
            max(0, _free_bytes(self.storage.root) - free_before) / 1e9,
            archived,
            shed,
            self.storage.root,
            disk_usage(self.storage.root) * 100,
        )

    async def on_stop(self, conversation_id: UUID) -> None:
        runtime = await asyncio.to_thread(self.storage.runtime, conversation_id)
        if runtime is not None and await self.reclaim(runtime, Tier.CACHES):
            self.trash.empty_soon()

    async def _maintenance_loop(self) -> None:
        while True:
            await asyncio.sleep(MAINTENANCE_INTERVAL)
            try:
                await self.run_pass()
            except Exception:
                logger.exception("error_reclaiming_conversation_storage")

    async def _enforce_retention(self) -> int:
        """存档运行时间处于非活动状态的时间超过保留期。"""
        if not self.retention_days:
            return 0
        cutoff = time.time() - self.retention_days * 86400
        runtimes = await asyncio.to_thread(self.storage.runtimes)
        # 最近最不活跃的优先，所以过时的是前缀。
        stale = itertools.takewhile(lambda r: r.last_active <= cutoff, runtimes)
        archived = sum([await self.reclaim(r, Tier.RUNTIME) for r in stale])
        if archived:
            self.trash.empty_soon()
        return archived

    async def _enforce_disk_budget(self) -> int:
        """摆脱对已停止运行时的依赖，最旧的首先，直到低于预算。"""
        budget = self.disk_budget
        root = self.storage.root
        if not budget or disk_usage(root) <= budget:
            self._over_budget_warned = False
            return 0
        shed = 0
        for runtime in await asyncio.to_thread(self.storage.runtimes):
            if not await self.reclaim(runtime, Tier.DEPENDENCIES):
                continue
            shed += 1
            # 只有当垃圾真正清空后，使用量才会下降。
            self.trash.empty_soon()
            await self.trash.drain()
            if disk_usage(root) <= budget:
                break
        if not shed and not self._over_budget_warned:
            self._over_budget_warned = True
            logger.warning(
                "Conversation storage at %s is above its %.0f%% budget with "
                "nothing left to shed from stopped runtimes",
                root,
                budget * 100,
            )
        return shed

    async def reclaim(self, runtime: StoredRuntime, tier: Tier) -> bool:
        """放弃 ``tier`` 允许的内容，除非正在使用运行时。"""
        archiving = tier >= Tier.RUNTIME
        # 归档需要整个运行时间，所以没有什么可以选择的。
        paths = [] if archiving else await asyncio.to_thread(_select, runtime, tier)
        if not (paths or archiving):
            return False
        async with self.storage.idle(runtime.id) as idle:
            if not idle:
                return False
            if archiving:
                paths = self.storage.archive(runtime.id)
            # 仅在此处重命名：锁保留微秒。
            moved = [path for path in paths if self.trash.discard(path)]
        if archiving and moved:
            await self.storage.on_archived(runtime.id)
        return bool(moved)


def _select(runtime: StoredRuntime, tier: Tier) -> list[Path]:
    paths: list[Path] = []
    if tier >= Tier.CACHES and runtime.home is not None:
        paths += caches(runtime.home)
    if tier >= Tier.DEPENDENCIES:
        for workspace in runtime.workspaces:
            paths += ignored_dirs(workspace)
    return paths


def disk_usage(path: Path) -> float:
    usage = shutil.disk_usage(path)
    return usage.used / (usage.used + usage.free)


def _free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free
