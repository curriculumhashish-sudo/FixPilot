"""测试浏览器会话记录刷新行为。

这些测试验证：
1. 记录事件定期刷新到新文件块
"""

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from openhands.tools.browser_use.event_storage import EventStorage
from openhands.tools.browser_use.recording import (
    DEFAULT_CONFIG,
    RecordingSession,
)
from openhands.tools.browser_use.server import CustomBrowserUseServer


# 获取测试的默认配置值
RECORDING_FLUSH_INTERVAL_SECONDS = DEFAULT_CONFIG.flush_interval_seconds


@pytest.fixture
def mock_cdp_session():
    """创建模拟对象 CDP 会话。"""
    cdp_session = MagicMock()
    cdp_session.session_id = "test-session-id"
    cdp_session.cdp_client = MagicMock()
    cdp_session.cdp_client.send = MagicMock()
    cdp_session.cdp_client.send.Runtime = MagicMock()
    cdp_session.cdp_client.send.Runtime.evaluate = AsyncMock()
    return cdp_session


@pytest.fixture
def mock_browser_session(mock_cdp_session):
    """创建模拟对象浏览器会话。"""
    browser_session = MagicMock()
    browser_session.get_or_create_cdp_session = AsyncMock(return_value=mock_cdp_session)
    return browser_session


@pytest.fixture
def server_with_mock_browser(mock_browser_session):
    """创建 CustomBrowserUseServer 和模拟的浏览器会话。"""
    server = CustomBrowserUseServer()
    server.browser_session = mock_browser_session
    return server


@pytest.fixture
def recording_session_with_mock_browser(mock_browser_session):
    """创建 RecordingSession 和模拟的浏览器会话。"""
    return mock_browser_session, RecordingSession()


def create_mock_events(count: int, size_per_event: int = 100) -> list[dict]:
    """创建具有指定计数和大致大小的模拟对象个 rrweb 事件。"""
    events = []
    for i in range(count):
        # 使用填充创建事件以达到近似大小
        padding = "x" * max(0, size_per_event - 50)
        events.append(
            {
                "type": 3,
                "timestamp": 1000 + i,
                "data": {"source": 1, "text": padding},
            }
        )
    return events


class TestEventStorage:
    """测试 EventStorage - 无需浏览器模拟对象。"""

    def test_save_events_creates_file(self):
        """测试 save_events 创建一个包含事件的 JSON 文件。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = EventStorage(output_dir=temp_dir)
            storage.create_session_subfolder()

            events = create_mock_events(10)
            filepath = storage.save_events(events)

            assert filepath is not None
            assert os.path.exists(filepath)
            with open(filepath) as f:
                saved = json.load(f)
            assert len(saved) == 10

    def test_save_events_updates_counters(self):
        """测试 save_events 是否更新 file_count 和 total_events。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = EventStorage(output_dir=temp_dir)
            storage.create_session_subfolder()

            storage.save_events(create_mock_events(5))
            assert storage.file_count == 1
            assert storage.total_events == 5

            storage.save_events(create_mock_events(10))
            assert storage.file_count == 2
            assert storage.total_events == 15

    def test_save_events_returns_none_without_session_dir(self):
        """测试如果未设置 session_dir，save_events 是否返回 None。"""
        storage = EventStorage()
        result = storage.save_events(create_mock_events(5))
        assert result is None

    def test_save_events_returns_none_for_empty_events(self):
        """测试 save_events 对于空事件列表是否返回 None。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = EventStorage(output_dir=temp_dir)
            storage.create_session_subfolder()
            result = storage.save_events([])
            assert result is None

    def test_reset_clears_state(self):
        """测试重置会清除所有存储状态。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = EventStorage(output_dir=temp_dir)
            storage.create_session_subfolder()
            storage.save_events(create_mock_events(5))

            assert storage.session_dir is not None
            assert storage.file_count == 1

            storage.reset()

            assert storage.session_dir is None
            assert storage.file_count == 0
            assert storage.total_events == 0


class TestPeriodicFlush:
    """测试定期刷新行为（每隔几秒）。"""

    @pytest.mark.asyncio
    async def test_periodic_flush_creates_new_file_chunks(
        self, mock_browser_session, mock_cdp_session
    ):
        """测试周期性刷新创建新文件块的频率。"""
        from openhands.tools.browser_use.recording import RecordingConfig

        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建具有快速刷新间隔的记录会话
            config = RecordingConfig(flush_interval_seconds=0.1)  # 100毫秒
            session = RecordingSession(config=config)
            session._storage._session_dir = temp_dir
            session._is_recording = True

            # 模拟对象 CDP 评估以在每次刷新时返回事件
            flush_call_count = 0

            async def mock_evaluate(*args, **kwargs):
                nonlocal flush_call_count
                expression = kwargs.get("params", {}).get("expression", "")

                # 返回刷新调用的事件
                if (
                    "window.__rrweb_events" in expression
                    and "JSON.stringify" in expression
                ):
                    flush_call_count += 1
                    events = create_mock_events(10)  # 每次刷新 10 个事件
                    return {"result": {"value": json.dumps({"events": events})}}
                return {"result": {"value": None}}

            mock_cdp_session.cdp_client.send.Runtime.evaluate = AsyncMock(
                side_effect=mock_evaluate
            )

            # 启动周期性刷新任务
            flush_task = asyncio.create_task(
                session._periodic_flush_loop(mock_browser_session)
            )

            # 让它运行足够的时间以创建多次刷新
            await asyncio.sleep(0.35)  # 应允许 ~3 次冲洗周期

            # 停止录制以结束任务
            session._is_recording = False
            await asyncio.sleep(0.15)  # 允许任务退出

            # 如果仍在运行则取消
            if not flush_task.done():
                flush_task.cancel()
                try:
                    await flush_task
                except asyncio.CancelledError:
                    pass

            # 验证：应该已创建多个文件
            files = sorted(os.listdir(temp_dir))
            json_files = [f for f in files if f.endswith(".json")]

            assert len(json_files) >= 2, (
                f"Expected at least 2 file chunks from periodic flush, "
                f"got {len(json_files)}: {json_files}"
            )

            # 验证每个文件包含有效事件
            for json_file in json_files:
                filepath = os.path.join(temp_dir, json_file)
                with open(filepath) as f:
                    events = json.load(f)
                assert isinstance(events, list)
                assert len(events) > 0

    @pytest.mark.asyncio
    async def test_periodic_flush_interval_is_configurable(self):
        """测试冲洗间隔常数设置是否正确。"""
        # 验证默认间隔是否为 5 秒
        assert RECORDING_FLUSH_INTERVAL_SECONDS == 5


class TestConcurrentFlushSafety:
    """测试并发冲水安全性（锁保护）。"""

    @pytest.mark.asyncio
    async def test_concurrent_flushes_do_not_corrupt_event_buffer(
        self, mock_browser_session, mock_cdp_session
    ):
        """测试并发刷新不会损坏事件缓冲区。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = RecordingSession()
            session._storage._session_dir = temp_dir
            session._is_recording = True

            async def mock_evaluate(*args, **kwargs):
                expression = kwargs.get("params", {}).get("expression", "")
                if (
                    "window.__rrweb_events" in expression
                    and "JSON.stringify" in expression
                ):
                    events = create_mock_events(20, size_per_event=100)
                    return {"result": {"value": json.dumps({"events": events})}}
                return {"result": {"value": None}}

            mock_cdp_session.cdp_client.send.Runtime.evaluate = AsyncMock(
                side_effect=mock_evaluate
            )

            # 触发多次并发刷新
            tasks = [
                asyncio.create_task(session.flush_events(mock_browser_session))
                for _ in range(5)
            ]
            await asyncio.gather(*tasks)

            # 验证：事件应累积在缓冲区中（5 次刷新 * 20 个事件）
            assert len(session.events) == 100

    @pytest.mark.asyncio
    async def test_periodic_flush_creates_timestamped_files(
        self, mock_browser_session, mock_cdp_session
    ):
        """测试定期刷新是否创建可排序的带有时间戳的文件。"""
        from openhands.tools.browser_use.recording import RecordingConfig

        with tempfile.TemporaryDirectory() as temp_dir:
            config = RecordingConfig(flush_interval_seconds=0.05)
            session = RecordingSession(config=config)
            session._storage._session_dir = temp_dir
            session._is_recording = True

            async def mock_evaluate(*args, **kwargs):
                expression = kwargs.get("params", {}).get("expression", "")
                if (
                    "window.__rrweb_events" in expression
                    and "JSON.stringify" in expression
                ):
                    events = create_mock_events(20, size_per_event=100)
                    return {"result": {"value": json.dumps({"events": events})}}
                return {"result": {"value": None}}

            mock_cdp_session.cdp_client.send.Runtime.evaluate = AsyncMock(
                side_effect=mock_evaluate
            )

            flush_task = asyncio.create_task(
                session._periodic_flush_loop(mock_browser_session)
            )
            await asyncio.sleep(0.2)

            session._is_recording = False
            await asyncio.sleep(0.1)
            if not flush_task.done():
                flush_task.cancel()
                try:
                    await flush_task
                except asyncio.CancelledError:
                    pass

            files = sorted(os.listdir(temp_dir))
            json_files = [f for f in files if f.endswith(".json")]

            # 文件应该是唯一的并且可以按时间戳排序
            assert len(json_files) >= 2, f"Expected at least 2 files, got {json_files}"
            assert len(json_files) == len(set(json_files)), "Files should be unique"

            # 验证文件完整性
            for json_file in json_files:
                filepath = os.path.join(temp_dir, json_file)
                with open(filepath) as f:
                    events = json.load(f)
                assert isinstance(events, list)


class TestRecordingIsolation:
    """测试记录会话隔离（单独的子文件夹）。"""

    @pytest.mark.asyncio
    async def test_multiple_recordings_create_separate_subfolders(
        self, mock_browser_session, mock_cdp_session
    ):
        """测试多个启动/停止循环是否创建单独的子文件夹。"""
        import time

        with tempfile.TemporaryDirectory() as temp_dir:
            # 设置模拟对象 CDP 会话以成功录制
            # 注意：stop_recording 需要一个 JSON 字符串，而不是字典
            mock_cdp_session.cdp_client.send.Runtime.evaluate = AsyncMock(
                side_effect=[
                    # 第一次录制：等待rrweb加载
                    {"result": {"value": {"success": True}}},
                    # 第一次录音：开始录音
                    {"result": {"value": {"status": "started"}}},
                    # 首次录音：设置录音标志（停止时）
                    {"result": {"value": None}},
                    # 第一次录音：停止录音（返回JSON字符串）
                    {"result": {"value": json.dumps({"events": [{"type": 3}] * 5})}},
                    # 第一次录音：设置录音标志为False
                    {"result": {"value": None}},
                    # 第二次录音：等待rrweb加载
                    {"result": {"value": {"success": True}}},
                    # 第二次录音：开始录音
                    {"result": {"value": {"status": "started"}}},
                    # 第二次录音：设置录音标志（停止时）
                    {"result": {"value": None}},
                    # 第二次录音：停止录音（返回JSON字符串）
                    {"result": {"value": json.dumps({"events": [{"type": 3}] * 10})}},
                    # 第二次录音：将录音标志设置为False
                    {"result": {"value": None}},
                ]
            )
            mock_cdp_session.cdp_client.send.Page.addScriptToEvaluateOnNewDocument = (
                AsyncMock(return_value={"identifier": "script-1"})
            )

            # 第一次录音
            session1 = RecordingSession(output_dir=temp_dir)
            await session1.start(mock_browser_session)
            session_dir_1 = session1.session_dir
            await session1.stop(mock_browser_session)

            # 小延迟保证不同的时间戳
            time.sleep(0.01)

            # 第二次录音
            session2 = RecordingSession(output_dir=temp_dir)
            await session2.start(mock_browser_session)
            session_dir_2 = session2.session_dir
            await session2.stop(mock_browser_session)

            # 验证：创建了两个单独的子文件夹
            subdirs = [
                d
                for d in os.listdir(temp_dir)
                if os.path.isdir(os.path.join(temp_dir, d))
            ]
            assert len(subdirs) == 2, (
                f"Expected 2 recording subfolders, got {len(subdirs)}: {subdirs}"
            )

            # 验证两者都以“recording-”开头
            for subdir in subdirs:
                assert subdir.startswith("recording-"), (
                    f"Expected subfolder to start with 'recording-', got {subdir}"
                )

            # 验证 session_dirs 不同
            assert session_dir_1 != session_dir_2, (
                "Expected different session directories for each recording"
            )

            # 验证每个子文件夹都有自己的文件
            for subdir in subdirs:
                subdir_path = os.path.join(temp_dir, subdir)
                files = os.listdir(subdir_path)
                json_files = [f for f in files if f.endswith(".json")]
                assert len(json_files) > 0, (
                    f"Expected at least one JSON file in {subdir}"
                )


class TestFileCountAccuracy:
    """测试准确的文件计数报告。"""

    @pytest.mark.asyncio
    async def test_file_count_accurate_with_existing_files(self):
        """当 session_dir 具有现有文件时，测试文件计数是否准确。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 预先创建一些文件来模拟现有录音
            for i in range(1, 4):  # 创建1.json、2.json、3.json
                with open(os.path.join(temp_dir, f"{i}.json"), "w") as f:
                    json.dump([{"type": "existing"}], f)

            session = RecordingSession()
            session._storage._session_dir = temp_dir
            session._is_recording = True

            # 将事件添加到缓冲区并保存两次
            for _ in range(2):
                session._events.extend(create_mock_events(20))
                session._save_and_clear_events()

            # 验证：file_count 应为 2（本次会话写入的文件）
            assert session.file_count == 2, (
                f"Expected file_count=2 (files written), got {session.file_count}"
            )

            # 验证新文件是否已创建（时间戳，未编号）
            files = sorted(os.listdir(temp_dir))
            json_files = [f for f in files if f.endswith(".json")]
            assert len(json_files) == 5  # 3 existing + 2 new

    @pytest.mark.asyncio
    async def test_file_count_zero_when_no_events(self):
        """测试没有记录事件时文件计数是否为 0。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = RecordingSession()
            session._storage._session_dir = temp_dir
            session._is_recording = True

            # 没有刷新调用，没有事件
            assert session.file_count == 0

    @pytest.mark.asyncio
    async def test_file_count_matches_actual_files_written(self):
        """测试 file_count 是否与写入的文件数完全匹配。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = RecordingSession()
            session._storage._session_dir = temp_dir
            session._is_recording = True

            # 将事件添加到缓冲区并保存5次
            for _ in range(5):
                session._events.extend(create_mock_events(20))
                session._save_and_clear_events()

            # 验证 file_count 与实际文件匹配
            files = os.listdir(temp_dir)
            json_files = [f for f in files if f.endswith(".json")]
            assert session.file_count == len(json_files) == 5
