"""Conversation类的核心高级测试，关注关键功能。"""

import os
import tempfile
import uuid
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.credential import CredentialSyncError
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.llm.utils.metrics import Metrics
from tests.platform_utils import maybe_mark_forked


def create_test_agent() -> Agent:
    """创建测试智能体。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    return Agent(llm=llm, tools=[])


def create_test_event(event_id: str, content: str = "Test content") -> MessageEvent:
    """创建具有特定 ID 的测试 MessageEvent。"""
    event = MessageEvent(
        id=event_id,
        llm_message=Message(role="user", content=[TextContent(text=content)]),
        source="user",
    )
    return event


def test_conversation_basic_creation():
    """测试基本对话创建和属性。"""
    agent = create_test_agent()

    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(agent=agent, persistence_dir=tmpdir, workspace=tmpdir)

        # 应设置基本属性
        assert conv.id is not None
        assert isinstance(conv.id, uuid.UUID)  # UUID 类型
        assert conv.state is not None
        assert conv._state.agent == agent


def test_conversation_event_log_functionality():
    """测试 EventLog 与 Conversation 的集成。"""
    agent = create_test_agent()

    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(agent=agent, persistence_dir=tmpdir, workspace=tmpdir)

        # 直接添加事件以测试 EventLog 功能
        events = [
            create_test_event("event-1", "First message"),
            create_test_event("event-2", "Second message"),
            create_test_event("event-3", "Third message"),
        ]

        for event in events:
            conv.state.events.append(event)

        # 测试基本 EventLog 功能
        total_events = len(conv.state.events)
        assert total_events >= 3  # 可能还有来自 Agent.init_state 的其他活动

        # 查找我们的测试活动
        our_events = [e for e in conv.state.events if e.id.startswith("event-")]
        assert len(our_events) == 3
        assert our_events[0].id == "event-1"
        assert our_events[1].id == "event-2"
        assert our_events[2].id == "event-3"

        # 测试迭代
        event_ids = [e.id for e in our_events]
        assert event_ids == ["event-1", "event-2", "event-3"]


def test_conversation_state_persistence():
    """测试会话状态持久化到文件存储。"""
    agent = create_test_agent()

    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(agent=agent, persistence_dir=tmpdir, workspace=tmpdir)

        # 添加事件
        event = create_test_event("persist-test", "Persistence test")
        conv.state.events.append(event)

        # 添加事件时状态应自动保存检查文件是否已创建
        #
        import os

        # 持久化目录实际上是一个子目录
        persistence_files = os.listdir(conv.state.persistence_dir)
        assert len(persistence_files) > 0

        # 应该有基本状态文件
        base_state_exists = any("base_state.json" in f for f in persistence_files)
        assert base_state_exists

        # 应该有事件目录
        if conv.state.persistence_dir:
            events_dir = os.path.join(conv.state.persistence_dir, "events")
            if os.path.exists(events_dir):
                events_files = os.listdir(events_dir)
                assert len(events_files) > 0


def test_conversation_with_custom_id():
    """使用自定义 ID 测试对话创建。"""
    agent = create_test_agent()

    with tempfile.TemporaryDirectory() as tmpdir:
        custom_id = uuid.uuid4()
        conv = Conversation(
            agent=agent,
            persistence_dir=tmpdir,
            workspace=tmpdir,
            conversation_id=custom_id,
        )

        assert conv.id == custom_id
        assert conv.state.id == custom_id


def test_conversation_event_id_validation():
    """测试 EventLog 是否可以防止重复的事件 ID。"""

    agent = create_test_agent()

    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(agent=agent, persistence_dir=tmpdir, workspace=tmpdir)

        # 添加第一个事件
        event1 = create_test_event("unique-id-1", "First event")
        conv.state.events.append(event1)

        # 添加具有重复 ID 的事件 - 应引发 ValueError
        event2 = create_test_event("unique-id-1", "Second event")
        with pytest.raises(
            ValueError, match=r"Event with ID 'unique-id-1' already exists at index \d+"
        ):
            conv.state.events.append(event2)

        # 只有第一个事件应该记录在日志中
        our_events = [e for e in conv.state.events if e.id == "unique-id-1"]
        assert len(our_events) == 1


@maybe_mark_forked
def test_conversation_large_event_handling():
    """通过内存使用情况监控来测试许多事件的对话处理。"""
    import gc

    import psutil

    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB

    agent = create_test_agent()

    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(agent=agent, persistence_dir=tmpdir, workspace=tmpdir)

        # 添加许多事件来测试内存限制
        num_events = 5000  # 大量测试内存使用情况
        for i in range(num_events):
            event = create_test_event(f"bulk-event-{i:04d}", f"Message {i}")
            conv.state.events.append(event)

            # 定期检查内存使用情况
            if i % 1000 == 0 and i > 0:
                gc.collect()  # 强制垃圾回收

                assert process is not None
                current_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_growth = current_memory - initial_memory
                # 内存不应过度增长（允许合理增长）
                assert memory_growth < 500, (
                    f"Memory usage grew too much: {memory_growth:.2f}MB "
                    f"after {i} events"
                )

        # 测试所有事件是否均可访问
        total_events = len(conv.state.events)
        assert total_events >= num_events

        # 查找我们的测试活动
        our_events = [e for e in conv.state.events if e.id.startswith("bulk-event-")]
        assert len(our_events) == num_events

        # 测试随机访问
        assert our_events[2500].id == "bulk-event-2500"
        assert our_events[4999].id == "bulk-event-4999"

        # 测试迭代性能
        event_count = sum(
            1 for e in conv.state.events if e.id.startswith("bulk-event-")
        )
        assert event_count == num_events

        # 最终内存检查
        gc.collect()
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        total_memory_growth = final_memory - initial_memory

        # 确保内存使用量保持有限（允许合理增长）
        assert total_memory_growth < 1000, (
            f"Total memory growth too high: {total_memory_growth:.2f}MB "
            f"for {num_events} events"
        )
        print(
            f"Memory usage: initial {initial_memory:.2f}MB, "
            f"final {final_memory:.2f}MB, "
            f"growth {total_memory_growth:.2f}MB"
        )


def test_conversation_error_handling():
    """测试对话可以优雅地处理错误。"""
    agent = create_test_agent()

    with tempfile.TemporaryDirectory() as tmpdir:
        # 应该与有效目录创建对话
        conv = Conversation(agent=agent, persistence_dir=tmpdir, workspace=tmpdir)

        # 应具备基本属性
        assert conv.id is not None
        assert conv.state is not None


def test_close_propagates_agent_failure_and_allows_retry(tmp_path):
    agent = create_test_agent()
    conv = Conversation(agent=agent, persistence_dir=tmp_path, workspace=tmp_path)

    with patch.object(
        Agent,
        "close",
        side_effect=[CredentialSyncError("writeback failed"), None],
    ) as close:
        with pytest.raises(CredentialSyncError, match="writeback failed"):
            conv.close()
        conv.close()
        conv.close()

    assert close.call_count == 2


def test_close_reports_accumulated_cost_to_workspace(tmp_path):
    """close() 将运行的累积 LLM 成本交给工作区，即
    是什么让它进入自动化完成回调。"""
    agent = create_test_agent()
    conv = Conversation(agent=agent, persistence_dir=tmp_path, workspace=tmp_path)
    metrics = Metrics()
    metrics.add_cost(0.75)
    conv.conversation_stats.usage_to_metrics["test-llm"] = metrics

    conv.close()

    assert conv.workspace.accumulated_cost == 0.75


def test_close_reports_zero_cost_when_no_llm_calls(tmp_path):
    """在任何 LLM 调用 - e.g 之前结束的运行。 它在设置过程中出错 -
    报告真实的 0.0，而不是遗漏的成本。 当地政府是正在进行中且具有权威性的，因此零支出
    是这里的事实； 这故意与 RemoteConversation.close()
     不同，其中缺少缓存的统计信息意味着成本未知，因此未报告。
    """
    agent = create_test_agent()
    conv = Conversation(agent=agent, persistence_dir=tmp_path, workspace=tmp_path)

    conv.close()

    assert conv.workspace.accumulated_cost == 0.0


def test_close_logs_noncredential_agent_failure_without_retry(tmp_path):
    agent = create_test_agent()
    conv = Conversation(agent=agent, persistence_dir=tmp_path, workspace=tmp_path)

    with patch.object(
        Agent,
        "close",
        side_effect=RuntimeError("custom agent close failed"),
    ) as close:
        conv.close()
        conv.close()

    assert close.call_count == 1


def test_conversation_memory_vs_local_filestore():
    """测试对话适用于不同的持久化配置。"""
    agent = create_test_agent()

    # 使用临时目录（LocalFileStore）进行测试
    with tempfile.TemporaryDirectory() as temp_dir:
        conv = Conversation(agent=agent, persistence_dir=temp_dir, workspace=temp_dir)

        event = create_test_event("local-test", "Local test")
        conv.state.events.append(event)
        # 添加事件时状态自动保存

        # 验证文件已创建
        import os

        persistence_files = os.listdir(conv.state.persistence_dir)
        assert len(persistence_files) > 0
        assert any("base_state.json" in f for f in persistence_files)


def test_conversation_lifecycle_flags_and_secret_propagation(tmp_path):
    """测试对话清理生命周期标志和机密传播。"""
    from openhands.sdk.context import AgentContext
    from openhands.sdk.conversation.base import BaseConversation

    ctx = AgentContext(secrets={"MY_KEY": "my_val"})
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"))
    agent = Agent(llm=llm, agent_context=ctx, tools=[])
    conv = Conversation(agent=agent, persistence_dir=tmp_path, workspace=tmp_path)
    try:
        assert isinstance(conv, BaseConversation)
        assert conv.cleanup_initiated is False
        assert conv.cleanup_complete is False
        assert "MY_KEY" in conv.state.secret_registry.secret_sources
        assert conv.state.secret_registry.get_secret_value("MY_KEY") == "my_val"

        conv.close()
        assert conv.cleanup_initiated is True
        assert conv.cleanup_complete is True

        # 幂等关闭
        conv.close()
        assert conv.cleanup_complete is True
    finally:
        conv.close()
