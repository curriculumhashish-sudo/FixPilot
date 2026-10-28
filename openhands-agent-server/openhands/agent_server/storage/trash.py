import asyncio
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from openhands.agent_server.utils import safe_rmtree
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


class Trash:
    """唯一存储文件的地方被删除。

    ``discard`` 是一个重命名，因此它可以在锁下运行并且不会发生任何竞争：读者可以看到
    整个路径或根本看不到路径。 删除发生在后台，无论中断的运行留下什么，都会
    在下次启动时清空。 ``root`` 必须与丢弃的所有内容位于同一文件系统上。
    """

    def __init__(self, root: Path) -> None:
        self.dir = root / ".trash"
        self._emptying: asyncio.Task[None] | None = None

    def discard(self, path: Path) -> bool:
        try:
            self.dir.mkdir(mode=0o700, exist_ok=True)
            path.rename(self.dir / uuid4().hex)
        except FileNotFoundError:
            return False
        except OSError:
            logger.warning("Failed to discard %s", path, exc_info=True)
            return False
        return True

    def empty_soon(self) -> None:
        if self._emptying is None or self._emptying.done():
            self._emptying = asyncio.create_task(self._empty())

    async def drain(self) -> None:
        """等到迄今为止丢弃的所有内容都被删除。"""
        while self._emptying is not None and not self._emptying.done():
            await asyncio.shield(self._emptying)

    async def close(self) -> None:
        """放弃删除； 下一次开始会拾取剩下的东西。

        已在工作线程线程中运行的删除无法中断：它在返回后完成。 只有尚未开始的条目等待
        。
        """
        if self._emptying is not None:
            self._emptying.cancel()
            await asyncio.gather(self._emptying, return_exceptions=True)
            self._emptying = None

    async def _empty(self) -> None:
        # 重新列出同时丢弃的条目，但每次运行时都尝试一次：无法删除的条目不得旋转； 接下
        # 来就开始重试吧。
        #
        tried: set[Path] = set()
        while entries := [
            entry
            for entry in await asyncio.to_thread(self._entries)
            if entry not in tried
        ]:
            for entry in entries:
                tried.add(entry)
                try:
                    await asyncio.to_thread(_remove, entry)
                except Exception:
                    logger.warning("Failed to delete %s", entry, exc_info=True)

    def _entries(self) -> list[Path]:
        with suppress(FileNotFoundError):
            return list(self.dir.iterdir())
        return []


def _remove(path: Path) -> None:
    if path.is_symlink():
        path.unlink(missing_ok=True)
    # safe_rmtree 报告失败而不是引发。
    elif not safe_rmtree(path, "discarded conversation storage"):
        raise OSError(f"Could not delete {path}")
