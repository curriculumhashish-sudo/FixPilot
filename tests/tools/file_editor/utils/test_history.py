"""文件历史管理测试。"""

import tempfile
from pathlib import Path

from openhands.tools.file_editor.utils.history import (
    FileHistoryManager,
)


def test_default_history_limit():
    """测试默认历史限制是否为 5 条。"""
    with tempfile.NamedTemporaryFile() as temp_file:
        path = Path(temp_file.name)
        manager = FileHistoryManager()

        # 添加 6 个条目 - 这应该会触发删除第一个条目
        for i in range(6):
            manager.add_history(path, f"content{i}")

        # 获取元数据
        metadata = manager.get_metadata(path)
        assert len(metadata["entries"]) == 5  # 应该只保留最后 5 个条目
        # 第一个条目应为 content1，最后一个条目应为 content5
        assert manager.get_all_history(path)[0].startswith("content1")
        assert manager.get_all_history(path)[-1].startswith("content5")


def test_history_keys_are_unique():
    """测试即使在删除旧条目后历史记录键仍保持唯一。"""
    with tempfile.NamedTemporaryFile() as temp_file:
        path = Path(temp_file.name)
        manager = FileHistoryManager(max_history_per_file=2)

        # 添加 3 个条目 - 这应该会触发删除第一个条目
        manager.add_history(path, "content1")
        manager.add_history(path, "content2")
        manager.add_history(path, "content3")

        # 获取元数据
        metadata = manager.get_metadata(path)
        assert len(metadata["entries"]) == 2  # 应该只保留最后 2 个条目

        # 键应该是唯一且连续的
        keys = metadata["entries"]
        assert len(set(keys)) == len(keys)  # 所有键都应该是唯一的
        assert sorted(keys) == keys  # 键应该是连续的

        # 添加另一个条目
        manager.add_history(path, "content4")
        new_metadata = manager.get_metadata(path)
        new_keys = new_metadata["entries"]

        # 新密钥应该大于所有以前的密钥
        assert min(new_keys) > min(keys)
        assert len(set(new_keys)) == len(new_keys)  # 所有键仍然应该是唯一的


def test_history_counter_persists():
    """测试历史计数器是否在管理器实例中持续存在。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "test.txt"
        path.write_text("initial")

        # 第一个管理器实例
        manager1 = FileHistoryManager(history_dir=Path(temp_dir))
        manager1.add_history(path, "content1")
        manager1.add_history(path, "content2")

        # 使用同一目录的第二个管理器实例
        manager2 = FileHistoryManager(history_dir=Path(temp_dir))
        manager2.add_history(path, "content3")

        # 获取元数据
        metadata = manager2.get_metadata(path)
        keys = metadata["entries"]

        # 即使跨实例，键也应该是连续的
        assert len(set(keys)) == len(keys)  # 所有键都应该是唯一的
        assert sorted(keys) == keys  # 键应该是连续的


def test_clear_history_resets_counter():
    """测试清除历史记录是否会重置计数器。"""
    with tempfile.NamedTemporaryFile() as temp_file:
        path = Path(temp_file.name)
        manager = FileHistoryManager()

        # 添加一些条目
        manager.add_history(path, "content1")
        manager.add_history(path, "content2")

        # 清除历史记录
        manager.clear_history(path)

        # 计数器应重置
        metadata = manager.get_metadata(path)
        assert metadata["counter"] == 0

        # 添加新条目应从 0 开始
        manager.add_history(path, "new_content")
        metadata = manager.get_metadata(path)
        assert len(metadata["entries"]) == 1
        assert metadata["entries"][0] == 0  # 第一个键应该是 0


def test_pop_last_history_removes_entry():
    """测试 pop_last_history 是否删除最新条目。"""
    with tempfile.NamedTemporaryFile() as temp_file:
        path = Path(temp_file.name)
        manager = FileHistoryManager()

        # 添加一些条目
        manager.add_history(path, "content1")
        manager.add_history(path, "content2")
        manager.add_history(path, "content3")

        # 弹出最后一条历史记录
        last_entry = manager.pop_last_history(path)
        assert last_entry == "content3"

        # 检查该条目是否已被删除
        metadata = manager.get_metadata(path)
        assert len(metadata["entries"]) == 2

        # 再次弹出最后一条历史记录
        last_entry = manager.pop_last_history(path)
        assert last_entry == "content2"

        # 检查该条目是否已被删除
        metadata = manager.get_metadata(path)
        assert len(metadata["entries"]) == 1

        # 再次弹出最后一个历史记录条目
        last_entry = manager.pop_last_history(path)
        assert last_entry == "content1"

        # 检查所有条目是否已被删除
        metadata = manager.get_metadata(path)
        assert len(metadata["entries"]) == 0

        # 当没有条目时尝试弹出最后的历史记录
        last_entry = manager.pop_last_history(path)
        assert last_entry is None
