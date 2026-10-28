import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout

from openhands.sdk.io.cache import MemoryLRUCache
from openhands.sdk.logger import get_logger
from openhands.sdk.utils.files import atomic_write_text
from openhands.sdk.utils.path import to_posix_path

from .base import FileStore


logger = get_logger(__name__)


class LocalFileStore(FileStore):
    root: str
    cache: MemoryLRUCache

    def __init__(
        self,
        root: str,
        cache_limit_size: int = 500,
        cache_memory_size: int = 20 * 1024 * 1024,
    ) -> None:
        """使用缓存初始化 LocalFileStore。

        Args:
            root: 文件存储的根目录。
            cache_limit_size: 缓存条目的最大数量（默认值：500）。
            cache_memory_size: 最大缓存内存（以字节为单位）（默认值：20MB）。

        Note:
            缓存假定对文件的独占访问。 对文件的外部修改将不会被检测到，并且可能会导致
            缓存读取过时。
        """
        if root.startswith("~"):
            root = os.path.expanduser(root)
        root = os.path.abspath(os.path.normpath(root))
        self.root = root
        os.makedirs(self.root, exist_ok=True)
        self.cache = MemoryLRUCache(cache_memory_size, cache_limit_size)

    def get_full_path(self, path: str) -> str:
        # 去掉前导斜杠以将相对位置保留在根目录下
        if path.startswith("/"):
            path = path[1:]
        # 规范化路径分隔符以处理 Unix (/) 和 Windows (\) 样式
        normalized_path = to_posix_path(path)
        full = os.path.abspath(
            os.path.normpath(os.path.join(self.root, normalized_path))
        )
        # 确保沙箱
        if os.path.commonpath([self.root, full]) != self.root:
            raise ValueError(f"path escapes filestore root: {path}")

        return full

    def write(self, path: str, contents: str | bytes) -> None:
        full_path = self.get_full_path(path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        if isinstance(contents, str):
            atomic_write_text(Path(full_path), contents)
            self.cache[full_path] = contents
        else:
            with open(full_path, "wb") as f:
                f.write(contents)
            # 不缓存二进制内容 - LocalFileStore 代表 JSON 数据如果写入然后读取二进制数据
            # ，则读取时会出错
            #

    def read(self, path: str) -> str:
        full_path = self.get_full_path(path)

        if full_path in self.cache:
            return self.cache[full_path]

        if not os.path.exists(full_path):
            raise FileNotFoundError(path)

        with open(full_path, encoding="utf-8") as f:
            result = f.read()

        self.cache[full_path] = result
        return result

    def list(self, path: str) -> list[str]:
        full_path = self.get_full_path(path)
        if not os.path.exists(full_path):
            return []

        # 如果路径是文件，则返回文件本身（S3 一致的行为）
        if os.path.isfile(full_path):
            return [path]

        # 否则它是一个目录，返回其内容
        files = [os.path.join(path, f) for f in os.listdir(full_path)]
        files = [f + "/" if os.path.isdir(self.get_full_path(f)) else f for f in files]
        return files

    def delete(self, path: str) -> None:
        try:
            full_path = self.get_full_path(path)
            if not os.path.exists(full_path):
                logger.debug(f"Local path does not exist: {full_path}")
                return

            if os.path.isfile(full_path):
                os.remove(full_path)
                # 容忍缓存未命中：另一个进程写入的文件从未缓存在这里，删除它也不是错误。
                #
                self.cache.pop(full_path, None)
                logger.debug(f"Removed local file: {full_path}")
            elif os.path.isdir(full_path):
                shutil.rmtree(full_path)
                self.cache.clear()
                logger.debug(f"Removed local directory: {full_path}")

        except Exception as e:
            logger.error(f"Error clearing local file store: {str(e)}")

    def exists(self, path: str) -> bool:
        """检查文件或目录是否存在。"""
        return os.path.exists(self.get_full_path(path))

    def get_absolute_path(self, path: str) -> str:
        """获取绝对文件系统路径。"""
        return self.get_full_path(path)

    @contextmanager
    def lock(self, path: str, timeout: float = 30.0) -> Iterator[None]:
        """使用flock获取基于文件的锁。"""
        lock_path = self.get_full_path(path)
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        file_lock = FileLock(lock_path)
        try:
            with file_lock.acquire(timeout=timeout):
                yield
        except Timeout:
            logger.error(f"Failed to acquire lock within {timeout}s: {lock_path}")
            raise TimeoutError(f"Lock acquisition timed out: {path}")
