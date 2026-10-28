# state.py
import operator
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, nullcontext
from typing import Final, SupportsIndex, overload

from openhands.sdk.conversation.events_list_base import EventsListBase
from openhands.sdk.conversation.persistence_const import (
    EVENT_FILE_PATTERN,
    EVENT_NAME_RE,
    EVENTS_DIR,
)
from openhands.sdk.event import Event, EventID
from openhands.sdk.event.types import ROOT_PARENT_ID
from openhands.sdk.io import FileStore
from openhands.sdk.logger import get_logger
from openhands.sdk.utils.path import posix_path_name


logger = get_logger(__name__)

LOCK_FILE_NAME = ".eventlog.lock"
LOCK_TIMEOUT_SECONDS = 30

# Sidecar 标记命名日志的事件计数，以便编写者可以用一个来检查它
# ``exists()``. 计数器的名字里就有 ``FileStore.read`` 已被缓存。
LENGTH_MARKER_PATTERN: Final[str] = ".eventlog-len-{length}.marker"

# ROOT_PARENT_ID 现在位于 event.types（单一事实来源）； 它在下面的_effective_parent_id中
# 使用并在这里重新导出，因此存在
# ``from event_store import ROOT_PARENT_ID`` 进口商继续工作。


class EventLog(EventsListBase):
    """具有锁定并发写入的持久事件日志。

    此类使用 FileStore 的锁定机制提供线程安全和进程安全的事件存储。 事件已持久化存储
    到磁盘，可以通过索引或事件 ID 进行访问。

    Note:
        对于 LocalFileStore，通过 flock() 进行文件锁定确实不在 NFS 安装或网络文件系统
        上可靠地工作。 使用共享存储部署的用户应使用替代协
        调机制。
    """

    _fs: FileStore
    _dir: str
    _length: int
    _lock_path: str
    _write_guard: Callable[[], AbstractContextManager[None]] | None

    def __init__(self, fs: FileStore, dir_path: str = EVENTS_DIR) -> None:
        self._fs = fs
        self._dir = dir_path
        self._id_to_idx: dict[EventID, int] = {}
        self._idx_to_id: dict[int, EventID] = {}
        self._event_cache: dict[int, Event] = {}
        self._lock_path = f"{dir_path}/{LOCK_FILE_NAME}"
        self._write_guard = None
        self._length = self._scan_and_build_index()

    def set_write_guard(
        self,
        write_guard: Callable[[], AbstractContextManager[None]] | None,
    ) -> None:
        self._write_guard = write_guard

    def get_index(self, event_id: EventID) -> int:
        """返回给定 event_id 的整数索引。"""
        try:
            return self._id_to_idx[event_id]
        except KeyError:
            raise KeyError(f"Unknown event_id: {event_id}")

    def get_id(self, idx: int) -> EventID:
        """返回给定索引的 event_id。"""
        if idx < 0:
            idx += self._length
        if idx < 0 or idx >= self._length:
            raise IndexError("Event index out of range")
        return self._idx_to_id[idx]

    def __contains__(self, item: object) -> bool:
        """日志是否包含给定事件 id 或 ``Event``（按 id）。

        通过 id 检查（不是值相等的默认值 ``Sequence``）
        ``event in events`` True 事件在追加时被标记为 ``parent_id``，并避免散列不可散
        列的事件载荷。
        """
        if isinstance(item, Event):
            return item.id in self._id_to_idx
        return item in self._id_to_idx

    def _effective_parent_id(self, idx: int, event: Event) -> EventID | None:
        """解析 ``event`` 的父级（在 ``idx`` 处）以进行树遍历。

        该树之前的遗留事件没有 ``parent_id``； 它们回退到线性链（事件 ``idx - 1``），
        因此旧对话会无分支加载，无需磁盘重写。
        """
        if event.parent_id == ROOT_PARENT_ID:
            return None  # 显式根（在 idx > 0 处创建的特征根）
        if event.parent_id is not None:
            return event.parent_id  # 明确的（新事件）
        if idx == 0:
            return None  # 正版root
        return self.get_id(idx - 1)  # 传统线性链（向后兼容）

    def path_to_root(
        self, leaf_id: EventID | None, limit: int | None = None
    ) -> list[Event]:
        """活动分支 ``leaf -> ... -> root``，首先返回根。

        ``leaf_id=None`` 产生 ``[]``。 ``limit`` 仅保留最后的 ``limit`` 事件（从叶子
        返回），因此想要最近窗口的调用者停
        留在 O(limit) 而不是 O(branch)。 在循环中引发 ValueError，如果 ``leaf_id`` 或
        祖先缺失则引发 KeyError。
        """
        chain: list[Event] = []
        seen: set[EventID] = set()
        cur_id: EventID | None = leaf_id
        while cur_id is not None and (limit is None or len(chain) < limit):
            if cur_id in seen:
                raise ValueError(f"Cycle in event tree at {cur_id}")
            seen.add(cur_id)
            idx = self.get_index(cur_id)
            chain.append(evt := self[idx])
            cur_id = self._effective_parent_id(idx, evt)
        return chain[::-1]

    @overload
    def __getitem__(self, idx: int) -> Event: ...

    @overload
    def __getitem__(self, idx: slice) -> list[Event]: ...

    def __getitem__(self, idx: SupportsIndex | slice) -> Event | list[Event]:
        if isinstance(idx, slice):
            start, stop, step = idx.indices(self._length)
            return [self._get_single_item(i) for i in range(start, stop, step)]
        return self._get_single_item(idx)

    def _get_single_item(self, idx: SupportsIndex) -> Event:
        i = operator.index(idx)
        if i < 0:
            i += self._length
        if i < 0 or i >= self._length:
            raise IndexError("Event index out of range")

        if (cached := self._event_cache.get(i)) is not None:
            return cached

        try:
            path = self._path(i)
        except KeyError:
            # 内存中索引已过时（e.g.、外部文件修改或并发写入）。 从磁盘重建并重试一次。
            #
            logger.warning("Stale EventLog index at %d; rebuilding from disk.", i)
            self._length = self._scan_and_build_index()
            if i >= self._length:
                raise IndexError("Event index out of range")
            path = self._path(i)
        txt = self._fs.read(path)
        if not txt:
            raise FileNotFoundError(f"Missing event file: {path}")
        evt = Event.model_validate_json(txt)
        self._event_cache[i] = evt
        return evt

    def __iter__(self) -> Iterator[Event]:
        for i in range(self._length):
            cached = self._event_cache.get(i)
            if cached is not None:
                yield cached
                continue
            txt = self._fs.read(self._path(i))
            if not txt:
                continue
            evt = Event.model_validate_json(txt)
            evt_id = evt.id
            if i not in self._idx_to_id:
                self._idx_to_id[i] = evt_id
                self._id_to_idx.setdefault(evt_id, i)
            self._event_cache[i] = evt
            yield evt

    def append(self, event: Event) -> int:
        """附加带有锁定的事件以确保线程/进程安全。

        Returns:
            日志分配给 ``event`` 的序列号（索引）。

        Raises:
            TimeoutError: 如果在LOCK_TIMEOUT_SECONDS内无法获取锁。
            ValueError: 如果具有相同 ID 的事件已存在或其显式
                父级不存在。
        """
        evt_id = event.id

        try:
            with self._fs.lock(self._lock_path, timeout=LOCK_TIMEOUT_SECONDS):
                # 同步仅当标记不能排除另一个写入器时才使用磁盘
                if not self._marker_matches_length():
                    disk_length = self._count_events_on_disk()
                    if disk_length > self._length:
                        self._sync_from_disk(disk_length)

                if evt_id in self._id_to_idx:
                    existing_idx = self._id_to_idx[evt_id]
                    raise ValueError(
                        f"Event with ID '{evt_id}' already exists at index "
                        f"{existing_idx}"
                    )

                if (
                    event.parent_id not in (None, ROOT_PARENT_ID)
                    and event.parent_id not in self._id_to_idx
                ):
                    raise ValueError(
                        f"Parent event '{event.parent_id}' does not exist "
                        f"for event '{evt_id}'"
                    )

                payload = event.model_dump_json(exclude_none=True)
                write_guard = (
                    nullcontext() if self._write_guard is None else self._write_guard()
                )
                idx = self._length
                with write_guard:
                    target_path = self._path(idx, event_id=evt_id)
                    self._fs.write(target_path, payload)
                self._idx_to_id[idx] = evt_id
                self._id_to_idx[evt_id] = idx
                self._event_cache[idx] = event
                self._length += 1
                self._advance_length_marker(idx)
                return idx
        except TimeoutError:
            logger.error(
                f"Failed to acquire EventLog lock within {LOCK_TIMEOUT_SECONDS}s "
                f"for event {evt_id}"
            )
            raise

    def _marker_path(self, length: int) -> str:
        return f"{self._dir}/{LENGTH_MARKER_PATTERN.format(length=length)}"

    def _marker_matches_length(self) -> bool:
        """标记是否证明自我们上次添加以来没有人添加过。

        ``False`` 不是分歧的证明，因此调用者必须回退到确切的计数。
        """
        try:
            return bool(self._fs.exists(self._marker_path(self._length)))
        except Exception as e:
            logger.warning("Error reading event count marker in %s: %s", self._dir, e)
            return False

    def _advance_length_marker(self, previous_length: int) -> None:
        """将标记从 ``previous_length`` 移动到当前长度。

        首先删除是经过深思熟虑的：中断的更新不会留下任何标记，而不是一个声称是最新的
        陈旧标记。
        """
        try:
            self._fs.delete(self._marker_path(previous_length))
            self._fs.write(self._marker_path(self._length), "")
        except Exception as e:
            logger.warning("Error updating event count marker in %s: %s", self._dir, e)

    def _count_events_on_disk(self) -> int:
        """计算磁盘上的事件文件数。"""
        try:
            paths = self._fs.list(self._dir)
        except FileNotFoundError:
            # 目录尚不存在 - 预计有新事件日志
            return 0
        except Exception as e:
            logger.warning("Error listing event directory %s: %s", self._dir, e)
            return 0
        return sum(
            1
            for p in paths
            if posix_path_name(p).startswith("event-") and p.endswith(".json")
        )

    def _sync_from_disk(self, disk_length: int) -> None:
        """同步其他进程写入的事件的状态。

        保留现有索引映射并仅扫描新事件。
        """
        # 保留现有映射
        existing_idx_to_id = dict(self._idx_to_id)

        # 重新扫描以获取新事件
        scanned_length = self._scan_and_build_index()

        # 恢复丢失的所有映射（e.g.，对于非 UUID 事件 ID）
        for idx, evt_id in existing_idx_to_id.items():
            if idx not in self._idx_to_id:
                self._idx_to_id[idx] = evt_id
            if evt_id not in self._id_to_idx:
                self._id_to_idx[evt_id] = idx

        # 使用扫描长度或 disk_length 中的较大者
        self._length = max(scanned_length, disk_length)

    def __len__(self) -> int:
        return self._length

    def _path(self, idx: int, *, event_id: EventID | None = None) -> str:
        return f"{self._dir}/{
            EVENT_FILE_PATTERN.format(
                idx=idx, event_id=event_id or self._idx_to_id[idx]
            )
        }"

    def _scan_and_build_index(self) -> int:
        try:
            paths = self._fs.list(self._dir)
        except Exception:
            self._id_to_idx.clear()
            self._idx_to_id.clear()
            self._event_cache.clear()
            return 0

        by_idx: dict[int, EventID] = {}
        for p in paths:
            name = posix_path_name(p)
            m = EVENT_NAME_RE.match(name)
            if m:
                idx = int(m.group("idx"))
                evt_id = m.group("event_id")
                by_idx[idx] = evt_id
            elif name.startswith("."):
                # 我们自己的 sidecar（锁文件，计数标记），而不是事件文件。
                continue
            else:
                logger.warning(f"Unrecognized event file name: {name}")

        if not by_idx:
            self._id_to_idx.clear()
            self._idx_to_id.clear()
            self._event_cache.clear()
            return 0

        n = 0
        while True:
            if n not in by_idx:
                if any(i > n for i in by_idx.keys()):
                    logger.warning(
                        "Event index gap detected: "
                        f"expect next index {n} but got {sorted(by_idx.keys())}"
                    )
                break
            n += 1

        self._id_to_idx.clear()
        self._idx_to_id.clear()
        self._event_cache.clear()
        for i in range(n):
            evt_id = by_idx[i]
            self._idx_to_id[i] = evt_id
            if evt_id in self._id_to_idx:
                logger.warning(
                    f"Duplicate event ID '{evt_id}' found during scan. "
                    f"Keeping first occurrence at index {self._id_to_idx[evt_id]}, "
                    f"ignoring duplicate at index {i}"
                )
            else:
                self._id_to_idx[evt_id] = i
        return n
