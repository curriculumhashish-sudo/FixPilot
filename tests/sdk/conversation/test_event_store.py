"""EventLog 类的综合边缘情况测试。"""

import json
from unittest.mock import Mock

import pytest

from openhands.sdk.conversation.event_store import LOCK_FILE_NAME, EventLog
from openhands.sdk.conversation.persistence_const import (
    EVENT_FILE_PATTERN,
    EVENT_NAME_RE,
    EVENTS_DIR,
)
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.io.memory import InMemoryFileStore
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.utils.path import posix_path_name


def create_test_event(event_id: str, content: str = "Test content") -> MessageEvent:
    """创建具有特定 ID 的测试 MessageEvent。"""
    event = MessageEvent(
        id=event_id,
        llm_message=Message(role="user", content=[TextContent(text=content)]),
        source="user",
    )
    return event


def test_event_log_empty_initialization():
    """使用空文件存储测试 EventLog。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    assert len(log) == 0
    assert list(log) == []

    # 测试访问空日志
    with pytest.raises(IndexError):
        log[0]

    with pytest.raises(IndexError):
        log[-1]


def test_event_log_append_returns_assigned_index():
    """``append`` 返回它分配的序列号，因此调用者不会
    附加后需要立即进行单独的 ``get_index`` 查找。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    assert log.append(create_test_event("event-1")) == 0
    assert log.append(create_test_event("event-2")) == 1
    assert log.append(create_test_event("event-3")) == 2


def test_event_log_id_validation_duplicate_id():
    """测试是否可以防止重复的事件 ID。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    event1 = create_test_event("test-id-1", "First event")
    event2 = create_test_event("test-id-1", "Second event with same ID")

    log.append(event1)

    # 重复的 ID 应引发 ValueError
    with pytest.raises(
        ValueError, match="Event with ID 'test-id-1' already exists at index 0"
    ):
        log.append(event2)

    assert len(log) == 1


def test_event_log_id_validation_existing_id_different_index():
    """测试手动修改内部状态时的行为。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    # 添加第一个事件
    event1 = create_test_event("event-1", "First")
    log.append(event1)

    # 手动破坏内部状态以模拟边缘情况
    log._id_to_idx["event-2"] = 0  # event-2 的索引错误

    # 通过重复预防，event-2 将被拒绝，因为“event-2”已在 _id_to_idx 中
    #
    event2 = create_test_event("event-2", "Second")
    with pytest.raises(
        ValueError, match="Event with ID 'event-2' already exists at index 0"
    ):
        log.append(event2)

    # 只有第一个事件应该记录在日志中
    assert len(log) == 1


def test_event_log_negative_indexing():
    """测试负索引是否正常工作。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    events = [
        create_test_event("event-1", "First"),
        create_test_event("event-2", "Second"),
        create_test_event("event-3", "Third"),
    ]

    for event in events:
        log.append(event)

    # 测试负面索引
    assert log[-1].id == "event-3"
    assert log[-2].id == "event-2"
    assert log[-3].id == "event-1"

    # 测试越界负索引
    with pytest.raises(IndexError):
        log[-4]


def test_event_log_get_index_and_get_id():
    """测试get_index和get_id方法。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    events = [
        create_test_event("alpha", "First"),
        create_test_event("beta", "Second"),
        create_test_event("gamma", "Third"),
    ]

    for event in events:
        log.append(event)

    # 测试 get_index
    assert log.get_index("alpha") == 0
    assert log.get_index("beta") == 1
    assert log.get_index("gamma") == 2

    # 测试 get_id
    assert log.get_id(0) == "alpha"
    assert log.get_id(1) == "beta"
    assert log.get_id(2) == "gamma"

    # 在 get_id 中测试负索引
    assert log.get_id(-1) == "gamma"
    assert log.get_id(-2) == "beta"
    assert log.get_id(-3) == "alpha"

    # 测试错误
    with pytest.raises(KeyError, match="Unknown event_id: nonexistent"):
        log.get_index("nonexistent")

    with pytest.raises(IndexError, match="Event index out of range"):
        log.get_id(3)

    with pytest.raises(IndexError, match="Event index out of range"):
        log.get_id(-4)


def test_event_log_missing_event_file():
    """测试事件文件丢失时的行为。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    event = create_test_event("test-event", "Content")
    log.append(event)

    # 手动删除文件以模拟损坏
    path = log._path(0, event_id="test-event")
    fs.delete(path)

    # 缓存访问仍然有效 - 事件在追加时缓存
    assert log[0].id == "test-event"

    # 清除缓存以测试磁盘访问路径
    log._event_cache.clear()
    with pytest.raises(FileNotFoundError):
        log[0]


def test_event_log_corrupted_json_in_file():
    """测试事件文件中损坏的 JSON 的行为。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    # 手动创建损坏的事件文件
    fs.write("events/event-00000-test-id.json", "invalid json content")

    # 强制重新扫描
    log._length = log._scan_and_build_index()

    # 损坏的文件不应被索引，因此长度应为 0
    assert len(log) == 0

    # 由于不存在有效事件，访问应引发 IndexError
    with pytest.raises(IndexError):
        log[0]


def test_event_log_clear_functionality():
    """测试EventLog在当前实现中没有明确的方法。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    events = [
        create_test_event("event-1", "First"),
        create_test_event("event-2", "Second"),
        create_test_event("event-3", "Third"),
    ]

    for event in events:
        log.append(event)

    assert len(log) == 3

    # 目前的实现没有明确的方法
    assert not hasattr(log, "clear")

    # 事件应该仍然可以访问
    assert len(log) == 3
    assert log._id_to_idx != {}
    assert log._idx_to_id != {}


def test_event_log_index_gaps_detection():
    """测试索引差距的检测和处理。"""
    fs = InMemoryFileStore()

    # 创建有间隙的文件（缺少 event-00001）
    event0 = {
        "id": "event-0",
        "llm_message": {
            "role": "user",
            "content": [{"type": "text", "text": "Event 0"}],
        },
        "source": "user",
        "kind": "openhands.sdk.event.llm_convertible.MessageEvent",
    }
    fs.write("events/event-00000-event-0.json", json.dumps(event0))

    event2 = {
        "id": "event-2",
        "llm_message": {
            "role": "user",
            "content": [{"type": "text", "text": "Event 2"}],
        },
        "source": "user",
        "kind": "openhands.sdk.event.llm_convertible.MessageEvent",
    }
    fs.write("events/event-00002-event-2.json", json.dumps(event2))

    # 应该只加载到间隙
    log = EventLog(fs)

    # 当前扫描逻辑对空隙非常严格。如果在任何索引处有空隙，就会完全停止加载事件。这是当前
    # 的行为，但可以改进
    #
    assert len(log) == 0  # 由于间隙检测，未加载任何事件


def test_event_log_file_store_exceptions():
    """测试文件存储异常的处理。"""
    import tempfile

    mock_fs = Mock()
    mock_fs.list.side_effect = Exception("File system error")
    with tempfile.TemporaryDirectory() as temp_dir:
        mock_fs.get_absolute_path.return_value = f"{temp_dir}/.eventlog.lock"
        log = EventLog(mock_fs)
        assert len(log) == 0


def test_event_log_iteration_with_missing_files():
    """测试某些文件丢失时的迭代行为。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    # 添加事件
    events = [
        create_test_event("event-1", "First"),
        create_test_event("event-2", "Second"),
        create_test_event("event-3", "Third"),
    ]

    for event in events:
        log.append(event)

    # 删除中间文件
    path = log._path(1, event_id="event-2")
    fs.delete(path)

    # 缓存的迭代仍然有效——所有 3 个事件都缓存在附加上
    assert [e.id for e in log] == ["event-1", "event-2", "event-3"]

    # 清除缓存以测试磁盘访问路径
    log._event_cache.clear()
    with pytest.raises(FileNotFoundError):
        list(log)


def test_event_log_iteration_backfills_missing_mappings():
    """测试当映射丢失且缓存变冷时迭代是否失败。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    # 通过普通append添加事件
    event = create_test_event("manual-event", "Manual event")
    log.append(event)

    # 验证事件已添加
    assert len(log) == 1
    assert log[0].id == "manual-event"

    # 清除映射和缓存以模拟丢失的数据
    log._idx_to_id.clear()
    log._id_to_idx.clear()
    log._event_cache.clear()

    # 但保持长度以便迭代可以工作
    log._length = 1

    # 如果没有缓存或映射，迭代在 _path 查找时失败
    with pytest.raises(KeyError):
        list(log)

    # 映射仍为空
    assert 0 not in log._idx_to_id
    assert "manual-event" not in log._id_to_idx


def test_event_log_custom_directory():
    """使用自定义目录测试 EventLog。"""
    fs = InMemoryFileStore()
    custom_dir = "custom_events"
    log = EventLog(fs, custom_dir)

    event = create_test_event("custom-event", "Custom content")
    log.append(event)

    # 应在自定义目录中创建文件 - 通过列出文件进行检查
    files = fs.list(custom_dir)
    assert len(files) > 0
    assert any("custom-event" in f for f in files)

    # 应该可以回读
    assert len(log) == 1
    assert log[0].id == "custom-event"


def test_event_log_large_index_formatting():
    """测试大型索引的正确格式。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    # 通过手动设置长度来模拟大索引
    log._length = 99999

    event = create_test_event("large-index-event", "Content")
    log.append(event)

    # 应使用适当的零填充进行格式化 - 通过列出文件进行检查
    files = fs.list("events")
    assert len(files) > 0
    assert any("event-99999-large-index-event" in f for f in files)

    assert log.get_index("large-index-event") == 99999
    assert log.get_id(99999) == "large-index-event"


def test_event_log_concurrent_append_thread_safety():
    """测试并发从多个线程追加。"""
    import tempfile
    import threading

    from openhands.sdk.io.local import LocalFileStore

    with tempfile.TemporaryDirectory() as temp_dir:
        fs = LocalFileStore(temp_dir)
        log = EventLog(fs)
        errors: list[Exception] = []
        lock = threading.Lock()

        def append_events(thread_id: int, num_events: int):
            for i in range(num_events):
                try:
                    event = create_test_event(
                        f"t{thread_id}-e{i}", f"Thread {thread_id}"
                    )
                    log.append(event)
                except Exception as e:
                    with lock:
                        errors.append(e)

        threads = []
        for t_id in range(5):
            t = threading.Thread(target=append_events, args=(t_id, 10))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(log) == 50


def test_event_log_concurrent_writes_serialized():
    """测试两个EventLog实例序列化写入正确。"""
    import tempfile

    from openhands.sdk.io.local import LocalFileStore

    with tempfile.TemporaryDirectory() as temp_dir:
        fs = LocalFileStore(temp_dir)
        log1 = EventLog(fs)
        log2 = EventLog(fs)

        log1.append(create_test_event("event-1", "First"))
        log2.append(create_test_event("event-2", "Second"))

        assert log1._length == 1
        assert log2._length == 2

        # Sidecar（锁文件，事件计数标记）是点文件，而不是事件。
        files = [f for f in fs.list("events") if not posix_path_name(f).startswith(".")]
        assert len(files) == 2


def test_get_single_item_recovers_from_stale_index():
    """当 _idx_to_id 过时时，_get_single_item 重建索引。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    # 使用UUID格式的ID来匹配EVENT_NAME_RE模式
    evt_id = "00000000-0000-0000-0000-000000000001"
    event = create_test_event(evt_id, "Should recover")
    log.append(event)
    assert log[0].id == evt_id

    # 模拟陈旧的内存索引（e.g.，外部文件修改）
    log._idx_to_id.clear()
    log._id_to_idx.clear()

    # Access 应该透明地重建索引并成功
    recovered = log[0]
    assert recovered.id == evt_id


def test_get_single_item_stale_index_out_of_range():
    """重建索引后，如果索引不再存在，则引发 IndexError。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    evt_id = "00000000-0000-0000-0000-000000000002"
    event = create_test_event(evt_id, "Only one")
    log.append(event)

    # 清除索引 AND 人为地增加长度以模拟陈旧状态
    log._idx_to_id.clear()
    log._id_to_idx.clear()
    log._length = 5  # 假设有 5 个事件

    # 索引3在磁盘上不存在； 重建后应提高 IndexError
    with pytest.raises(IndexError, match="Event index out of range"):
        log[3]


def test_event_cache_eliminates_repeated_deserialization():
    """重复访问同一事件将返回缓存的对象。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    event = create_test_event("cached-event", "Hello")
    log.append(event)

    first = log[0]
    second = log[0]
    # 相同的对象标识 — 无需重新反序列化
    assert first is second


def test_event_cache_populated_by_iteration():
    """迭代日志会填充缓存以供后续索引访问。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    for i in range(3):
        log.append(create_test_event(f"evt-{i}", f"Content {i}"))

    # 清除缓存以强制冷迭代
    log._event_cache.clear()
    events_from_iter = list(log)

    # 缓存现在应该保存所有 3 个事件
    assert len(log._event_cache) == 3

    # 索引访问返回相同的缓存对象
    for i, evt in enumerate(events_from_iter):
        assert log[i] is evt


def test_event_cache_survives_across_multiple_iterations():
    """多次迭代返回相同的缓存对象。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)

    log.append(create_test_event("a", "A"))
    log.append(create_test_event("b", "B"))

    first_pass = list(log)
    second_pass = list(log)
    assert all(a is b for a, b in zip(first_pass, second_pass, strict=True))


@pytest.mark.parametrize("idx", [0, 1, 99999, 100000, 100001, 999999, 1_000_000])
def test_event_filename_writer_reader_agree(idx):
    """读取器正则表达式必须与写入器发出的确切文件名匹配。"""
    event_id = f"{idx:08x}-0000-0000-0000-000000000000"
    name = EVENT_FILE_PATTERN.format(idx=idx, event_id=event_id)

    m = EVENT_NAME_RE.match(name)
    assert m is not None, f"reader regex failed to match writer output: {name!r}"
    assert int(m.group("idx")) == idx


def test_event_log_cold_reload_past_100k_events():
    """包含 >100000 个事件的日志会重新加载，而不会丢失尾部。

    在修复之前，冷扫描将索引截断为 100000（静默数据丢失），并且计数/扫描路径出现分歧
    ，从而破坏了长度统计。
    """
    # 提高 test-double LRU 上限，以便内存存储保留每个文件； 这仅配置存储替代，而不配置被
    # 测试的代码。
    #
    fs = InMemoryFileStore(max_size=500_000, max_memory=2 * 1024 * 1024 * 1024)
    payload = create_test_event("seed", "seed").model_dump_json(exclude_none=True)

    n = 100_002  # 跨越 5-/6-digit 边界
    for i in range(n):
        event_id = f"{i:08x}-0000-0000-0000-000000000000"
        path = f"{EVENTS_DIR}/" + EVENT_FILE_PATTERN.format(idx=i, event_id=event_id)
        fs.write(path, payload)

    log = EventLog(fs)

    # 没有静默截断：每个事件都能在冷扫描中幸存下来。
    assert len(log) == n

    # 跨越边界的事件是可读的，而不是不可到达的洞。
    assert log[99999] is not None
    assert log[100000] is not None
    assert log[100001] is not None

    # 重新加载后追加可以保持长度统计的一致性。
    log.append(create_test_event("after-reload", "after"))
    assert len(log) == n + 1


def test_append_does_not_scan_the_directory_as_the_log_grows():
    """附加成本不得随对话长度而增加（问题#4676）。

    同步多写入端点用于在每次追加时计数事件目录中的每个文件，因此追加事件N需要O(N)目录
    工作，同时持有锁。 挂牌电话是该成本的代理。
    """
    fs = InMemoryFileStore()
    log = EventLog(fs)

    listings: list[str] = []
    original_list = fs.list

    def counting_list(path: str) -> list[str]:
        listings.append(path)
        return original_list(path)

    fs.list = counting_list  # type: ignore[method-assign]

    for i in range(50):
        log.append(create_test_event(f"{i:08x}-0000-0000-0000-000000000000"))

    # 第一个追加没有可继续的标记，并支付一个列表的费用； 每个后面的附加都由标记单独回答
    # 。
    #
    assert len(listings) <= 1, f"append listed the events dir {len(listings)} times"
    assert len(log) == 50


def test_append_still_syncs_when_another_writer_appended():
    """第二个作家的事件仍然会被拾取，无论是否有标记。"""
    fs = InMemoryFileStore()
    log1 = EventLog(fs)
    log2 = EventLog(fs)

    log1.append(create_test_event("00000000-0000-0000-0000-000000000001"))
    log1.append(create_test_event("00000000-0000-0000-0000-000000000002"))

    # log2 以长度 0 打开并且从未看到那些附加； 标记不再命名其长度，因此它会退回到计数并
    # 落在它们后面。
    #
    log2.append(create_test_event("00000000-0000-0000-0000-000000000003"))

    assert log2._length == 3
    assert log2.get_index("00000000-0000-0000-0000-000000000003") == 2


def test_append_syncs_when_marker_is_missing():
    """在标记存在之前写入的日志保留精确计数路径。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)
    log.append(create_test_event("00000000-0000-0000-0000-000000000001"))

    # 模拟旧的磁盘日志：存在事件，无标记。
    for path in list(fs.files.keys()):
        if posix_path_name(path).startswith("."):
            del fs.files[path]

    reopened = EventLog(fs)
    reopened.append(create_test_event("00000000-0000-0000-0000-000000000002"))
    assert len(reopened) == 2

    # 并为随后的附加内容重新建立标记。
    assert fs.exists(reopened._marker_path(2))


def test_scan_does_not_warn_about_sidecar_files(caplog):
    """锁文件和计数标记是我们的； 它们不是畸形事件。"""
    fs = InMemoryFileStore()
    log = EventLog(fs)
    log.append(create_test_event("00000000-0000-0000-0000-000000000001"))
    fs.write(f"{EVENTS_DIR}/{LOCK_FILE_NAME}", "")

    with caplog.at_level("WARNING"):
        EventLog(fs)

    assert "Unrecognized event file name" not in caplog.text
