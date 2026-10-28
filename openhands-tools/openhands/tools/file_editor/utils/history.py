"""具有基于磁盘的存储和内存限制的文件编辑历史记录管理。"""

import logging
import tempfile
from pathlib import Path

from openhands.tools.file_editor.utils.file_cache import FileCache


class FileHistoryManager:
    """通过基于磁盘的存储和内存限制来管理文件编辑历史记录。"""

    max_history_per_file: int
    cache: FileCache
    logger: logging.Logger

    def __init__(self, max_history_per_file: int = 5, history_dir: Path | None = None):
        """初始化历史管理器。

        Args:
            max_history_per_file: 每个保留的历史记录条目的最大数量
                文件（默认：5）
            history_dir: 存储历史文件的目录。 如果 None，则使用温度
                目录

        Notes:
            - 每个文件的历史记录仅限于最后 N 个条目以节省内存
            - 文件缓存受到限制，以防止过多的磁盘使用
            - 当超出限制时，较旧的条目将被自动删除
        """
        self.max_history_per_file = max_history_per_file
        if history_dir is None:
            history_dir = Path(tempfile.mkdtemp(prefix="oh_editor_history_"))
        self.cache = FileCache(str(history_dir))
        self.logger = logging.getLogger(__name__)

    def _get_metadata_key(self, file_path: Path) -> str:
        return f"{file_path}.metadata"

    def _get_history_key(self, file_path: Path, counter: int) -> str:
        return f"{file_path}.{counter}"

    def add_history(self, file_path: Path, content: str):
        """为文件添加新的历史记录条目。"""
        metadata_key = self._get_metadata_key(file_path)
        metadata = self.cache.get(metadata_key, {"entries": [], "counter": 0})
        counter = metadata["counter"]

        # 添加新条目
        history_key = self._get_history_key(file_path, counter)
        self.cache.set(history_key, content)

        metadata["entries"].append(counter)
        metadata["counter"] += 1

        # 仅保留最后 N 个条目
        while len(metadata["entries"]) > self.max_history_per_file:
            old_counter = metadata["entries"].pop(0)
            old_history_key = self._get_history_key(file_path, old_counter)
            self.cache.delete(old_history_key)

        self.cache.set(metadata_key, metadata)

    def pop_last_history(self, file_path: Path) -> str | None:
        """弹出并返回文件的最新历史记录条目。"""
        metadata_key = self._get_metadata_key(file_path)
        metadata = self.cache.get(metadata_key, {"entries": [], "counter": 0})
        entries = metadata["entries"]

        if not entries:
            return None

        # 弹出并删除最后一个条目
        last_counter = entries.pop()
        history_key = self._get_history_key(file_path, last_counter)
        content = self.cache.get(history_key)

        if content is None:
            self.logger.warning(f"History entry not found for {file_path}")
        else:
            # 从缓存中删除该条目
            self.cache.delete(history_key)

        # 更新元数据
        metadata["entries"] = entries
        self.cache.set(metadata_key, metadata)

        return content

    def get_metadata(self, file_path: Path):
        """获取文件的元数据（用于测试目的）。"""
        metadata_key = self._get_metadata_key(file_path)
        metadata = self.cache.get(metadata_key, {"entries": [], "counter": 0})
        return metadata  # 返回实际的元数据，而不是副本

    def clear_history(self, file_path: Path):
        """清除给定文件的历史记录。"""
        metadata_key = self._get_metadata_key(file_path)
        metadata = self.cache.get(metadata_key, {"entries": [], "counter": 0})

        # 删除所有历史记录
        for counter in metadata["entries"]:
            history_key = self._get_history_key(file_path, counter)
            self.cache.delete(history_key)

        # 清除元数据
        self.cache.set(metadata_key, {"entries": [], "counter": 0})

    def get_all_history(self, file_path: Path) -> list[str]:
        """获取文件的所有历史条目。"""
        metadata_key = self._get_metadata_key(file_path)
        metadata = self.cache.get(metadata_key, {"entries": [], "counter": 0})
        entries = metadata["entries"]

        history = []
        for counter in entries:
            history_key = self._get_history_key(file_path, counter)
            content = self.cache.get(history_key)
            if content is not None:
                history.append(content)

        return history
