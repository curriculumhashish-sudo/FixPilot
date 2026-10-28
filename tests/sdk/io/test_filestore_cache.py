"""测试 LocalFileStore 缓存功能。

这个模块测试：
1. 缓存正确性和一致性
2. 缓存性能改进
3. 内存限制强制执行
4. 处理大量没有 OOM 的事件
"""

import logging
import os
import tempfile
import time

import pytest

from openhands.sdk.io.cache import MemoryLRUCache
from openhands.sdk.io.local import LocalFileStore


def test_cache_basic_functionality():
    """测试缓存是否正确存储和检索值。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        store = LocalFileStore(temp_dir, cache_limit_size=10)

        # 写和读
        store.write("test.txt", "Hello, World!")
        content = store.read("test.txt")
        assert content == "Hello, World!"

        # 验证它在缓存中
        full_path = store.get_full_path("test.txt")
        assert full_path in store.cache


def test_cache_hit_performance():
    """测试缓存命中是否明显快于磁盘读取。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        store = LocalFileStore(temp_dir, cache_limit_size=100)

        # 创建更大的测试文件以使计时更可测量
        test_content = "x" * 100000  # 100KB
        store.write("large_file.txt", test_content)

        # 热身并进行多次读取以获得更稳定的计时
        num_reads = 10

        # 第一遍 - 从磁盘（缓存未命中 + 后续缓存命中）首先清除缓存
        #
        store.cache.clear()
        content1 = ""
        start = time.perf_counter()
        for _ in range(num_reads):
            content1 = store.read("large_file.txt")
        first_pass_time = time.perf_counter() - start

        # 第二遍 - 全部来自缓存（所有缓存命中）
        content2 = ""
        start = time.perf_counter()
        for _ in range(num_reads):
            content2 = store.read("large_file.txt")
        second_pass_time = time.perf_counter() - start

        # Verify correctness
        assert content1 == test_content
        assert content2 == test_content

        # 第一次通过包括一次磁盘读取，因此应该明显变慢这是一个更宽松的检查，因为不同系统
        # 上的时间可能会有所不同
        #
        print(
            f"First pass: {first_pass_time:.6f}s, Second pass: {second_pass_time:.6f}s"
        )
        # 只需验证缓存是否正常工作 - 第二遍应该不会慢很多
        assert second_pass_time < first_pass_time * 2


def test_cache_lru_eviction():
    """测试 LRU 驱逐是否正常工作。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 较小的缓存大小可强制驱逐
        store = LocalFileStore(temp_dir, cache_limit_size=3)

        # 写入5个文件，缓存只能容纳3个
        for i in range(5):
            store.write(f"file_{i}.txt", f"content_{i}")

        # 缓存最多应有 3 个条目
        assert len(store.cache) <= 3

        # 最近写入的文件应位于缓存中（文件 2、3、4）
        #
        full_path_4 = store.get_full_path("file_4.txt")
        assert full_path_4 in store.cache


def test_cache_memory_limit():
    """测试是否强制执行内存限制。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 设置非常小的内存限制（10KB）
        store = LocalFileStore(
            temp_dir, cache_limit_size=100, cache_memory_size=10 * 1024
        )

        # 写入文件，直到超出内存限制每个文件约为 2KB
        #
        for i in range(20):
            content = "x" * 2000
            store.write(f"file_{i}.txt", content)

        # 缓存不应超过内存限制允许 Python 对象产生一些开销
        #
        assert store.cache.current_memory <= 12 * 1024  # 10KB + 20% 开销


def test_cache_invalidation_on_write():
    """测试文件被覆盖时缓存是否更新。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        store = LocalFileStore(temp_dir, cache_limit_size=10)

        # 写入初始内容
        store.write("test.txt", "original")
        assert store.read("test.txt") == "original"

        # 用新内容覆盖
        store.write("test.txt", "updated")
        cached_content = store.read("test.txt")

        # 缓存应该有更新的内容
        assert cached_content == "updated"


def test_cache_invalidation_on_delete():
    """测试删除文件时缓存是否被清除。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        store = LocalFileStore(temp_dir, cache_limit_size=10)

        # 写入和读取以填充缓存
        store.write("test.txt", "content")
        store.read("test.txt")

        full_path = store.get_full_path("test.txt")
        assert full_path in store.cache

        # 删除文件
        store.delete("test.txt")

        # 应该清除缓存
        assert full_path not in store.cache


def test_delete_uncached_file_succeeds_quietly(caplog):
    """删除此存储从未缓存的文件不是错误。

    由另一个进程写入的文件不存在于该存储的缓存中； 驱逐它们不得引发（并被吞入 ERROR
    日志）。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        store = LocalFileStore(temp_dir, cache_limit_size=10)

        # 就像另一个过程一样，是在商店背后写的。
        outside = os.path.join(temp_dir, "outside.txt")
        with open(outside, "w") as f:
            f.write("content")

        full_path = store.get_full_path("outside.txt")
        assert full_path not in store.cache

        with caplog.at_level(logging.ERROR):
            store.delete("outside.txt")

        assert not os.path.exists(outside)
        assert "Error clearing local file store" not in caplog.text


def test_cache_directory_deletion():
    """测试删除目录时缓存是否被清除。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        store = LocalFileStore(temp_dir, cache_limit_size=10)

        # 在子目录中创建文件
        store.write("subdir/file1.txt", "content1")
        store.write("subdir/file2.txt", "content2")

        # 读取以填充缓存
        store.read("subdir/file1.txt")
        store.read("subdir/file2.txt")

        # 在缓存中验证
        full_path1 = store.get_full_path("subdir/file1.txt")
        full_path2 = store.get_full_path("subdir/file2.txt")
        assert full_path1 in store.cache
        assert full_path2 in store.cache

        # 删除目录
        store.delete("subdir")

        # 这两个文件都应该从缓存中删除
        assert full_path1 not in store.cache
        assert full_path2 not in store.cache


def test_large_number_of_events_no_oom():
    """测试存储是否可以在没有 OOM 的情况下处理许多事件。

    这模拟了一个有数千个事件被重复写入和读取的场景，这就是缓存的最初动机。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 防止的保守限制 OOM 默认 5MB 内存，500 个条目
        #
        store = LocalFileStore(temp_dir)

        num_events = 2000  # 模拟 2000 个事件

        # 编写许多事件（模拟对话历史）
        for i in range(num_events):
            event_content = f"Event {i}: " + "x" * 200  # 每个事件 ~200 字节
            store.write(f"events/event_{i}.json", event_content)

        # 多次读取所有事件（模拟迭代）
        for iteration in range(3):
            for i in range(0, num_events, 10):  # 每 10 个事件采样一次
                content = store.read(f"events/event_{i}.json")
                assert f"Event {i}:" in content

        # 验证缓存没有无限增长
        assert len(store.cache) <= 500  # 应遵守限制
        # 允许开销但应低于内存限制
        assert store.cache.current_memory <= 6 * 1024 * 1024  # 6MB（含开销）


def test_cache_correctness_under_concurrent_operations():
    """测试缓存与各种操作保持一致。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        store = LocalFileStore(temp_dir, cache_limit_size=50)

        # 交错写入、读取和删除
        for i in range(10):
            # 写
            store.write(f"file_{i}.txt", f"content_{i}")

            # 阅读
            content = store.read(f"file_{i}.txt")
            assert content == f"content_{i}"

            # 更新
            store.write(f"file_{i}.txt", f"updated_{i}")

            # 再读一遍
            content = store.read(f"file_{i}.txt")
            assert content == f"updated_{i}"

            # 删除奇数文件
            if i % 2 == 1:
                store.delete(f"file_{i}.txt")

                # 验证已删除的文件不在缓存中
                full_path = store.get_full_path(f"file_{i}.txt")
                assert full_path not in store.cache

                # 验证读取已删除的文件会引发错误
                with pytest.raises(FileNotFoundError):
                    store.read(f"file_{i}.txt")


def test_cache_performance_repeated_reads():
    """测试重复读取是否显示性能改进。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        store = LocalFileStore(temp_dir, cache_limit_size=100)

        # 创建包含更多内容的测试文件以使磁盘 I/O 更加明显
        num_files = 50
        for i in range(num_files):
            content = f"Test content {i}\n" * 500  # 每个文件 ~10KB
            store.write(f"file_{i}.txt", content)

        # 清除缓存以确保重新启动
        store.cache.clear()

        # 第一遍 - 缓存未命中
        start = time.perf_counter()
        for i in range(num_files):
            store.read(f"file_{i}.txt")
        first_pass_time = time.perf_counter() - start

        # 第二遍 - 缓存命中
        start = time.perf_counter()
        for i in range(num_files):
            store.read(f"file_{i}.txt")
        second_pass_time = time.perf_counter() - start

        # 第二次传递应该更快或至少不会明显变慢
        speedup = first_pass_time / second_pass_time
        print(f"Cache speedup: {speedup:.2f}x")
        # 使用更宽松的检查 - 缓存应该有所帮助或至少不会造成伤害
        assert speedup > 0.8  # 缓存不会显着减慢速度


def test_cache_zero_size():
    """测试 cache_limit_size=0 有效禁用缓存。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        store = LocalFileStore(temp_dir, cache_limit_size=0)

        store.write("test.txt", "content")
        store.read("test.txt")

        # 缓存应保持为空或非常小
        assert len(store.cache) <= 1  # 可能有短暂进入


def test_very_large_file_cache():
    """测试相对于高速缓存内存限制的非常大文件的处理。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 小内存限制
        store = LocalFileStore(
            temp_dir, cache_limit_size=10, cache_memory_size=10 * 1024
        )

        # 写入大于缓存内存限制的文件
        large_content = "x" * 50000  # 50KB 文件，但 10KB 缓存限制
        store.write("large.txt", large_content)

        # 应该还是可以读的
        content = store.read("large.txt")
        assert content == large_content

        # 缓存应逐出条目以保持在内存限制以下
        assert store.cache.current_memory <= 12 * 1024  # 允许开销


def test_cache_with_evict_correct():
    cache = MemoryLRUCache(1000, 2)
    cache["key1"] = "a" * 500
    cache["key2"] = "b" * 500
    cache["key3"] = "c" * 100
    # key1 此时应被逐出（超出内存/条目限制）
    assert "key2" in cache and "key3" in cache and "key1" not in cache
    total_len = len(cache["key2"]) + len(cache["key3"])
    # 验证内存统计信息与 key2 和 key3 的总大小匹配
    assert total_len == cache.current_memory
