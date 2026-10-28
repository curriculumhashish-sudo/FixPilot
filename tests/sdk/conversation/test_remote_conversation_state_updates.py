"""测试 RemoteConversation 状态更新处理。"""

from unittest.mock import patch

from pydantic import SecretStr

from openhands.sdk import RemoteWorkspace
from openhands.sdk.agent import Agent
from openhands.sdk.conversation.impl.remote_conversation import RemoteConversation
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from openhands.sdk.llm import LLM

from .conftest import create_mock_http_client


def create_test_agent() -> Agent:
    """创建一个测试智能体进行测试。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    return Agent(llm=llm, tools=[])


def test_update_state_from_event_with_full_state():
    """测试从完整状态快照更新缓存状态。"""
    agent = create_test_agent()

    # 模拟对象 httpx 客户端
    mock_client_instance = create_mock_http_client()

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        # 创造真实RemoteConversation
        conv = RemoteConversation(
            agent=agent,
            workspace=RemoteWorkspace(working_dir="/tmp", host="http://localhost:3000"),
        )

        # 创建完整状态事件
        full_state = {
            "execution_status": "running",
            "confirmation_policy": {"kind": "NeverConfirm"},
            "max_iterations": 100,
        }
        event = ConversationStateUpdateEvent(key="full_state", value=full_state)

        # 使用真实的 RemoteState 更新状态
        conv.state.update_state_from_event(event)

        # 验证所有字段均已更新
        assert conv.state._cached_state is not None
        assert conv.state._cached_state == full_state
        assert conv.state._cached_state["execution_status"] == "running"
        assert conv.state._cached_state["max_iterations"] == 100


def test_update_state_from_event_with_individual_field():
    """测试从单个字段更新更新缓存状态。"""
    agent = create_test_agent()

    # 模拟对象 httpx 客户端及其响应
    mock_client_instance = create_mock_http_client()

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        # 创造真实RemoteConversation
        conv = RemoteConversation(
            agent=agent,
            workspace=RemoteWorkspace(working_dir="/tmp", host="http://localhost:3000"),
        )

        # 设置初始缓存状态
        conv.state._cached_state = {
            "execution_status": "idle",
            "max_iterations": 50,
        }

        # 创建单独的字段更新事件
        event = ConversationStateUpdateEvent(key="execution_status", value="running")

        # 使用真实的 RemoteState 更新状态
        conv.state.update_state_from_event(event)

        # 仅验证该字段已更新
        assert conv.state._cached_state is not None
        assert conv.state._cached_state["execution_status"] == "running"
        assert conv.state._cached_state["max_iterations"] == 50  # 不变


def test_update_state_initializes_cache_if_none():
    """测试更新是否初始化缓存（如果不存在）。"""
    agent = create_test_agent()

    # 模拟对象 httpx 客户端及其响应
    mock_client_instance = create_mock_http_client()

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        # 创造真实RemoteConversation
        conv = RemoteConversation(
            agent=agent,
            workspace=RemoteWorkspace(working_dir="/tmp", host="http://localhost:3000"),
        )

        # 确保缓存以 None 开头
        conv.state._cached_state = None

        # 当缓存为 None 时更新单个字段
        event = ConversationStateUpdateEvent(key="execution_status", value="running")
        conv.state.update_state_from_event(event)

        # 验证缓存是否已初始化
        assert conv.state._cached_state is not None
        assert conv.state._cached_state["execution_status"] == "running"


def test_update_state_from_multiple_events():
    """测试多个事件的更新状态。"""
    agent = create_test_agent()

    # 模拟对象 httpx 客户端及其响应
    mock_client_instance = create_mock_http_client()

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        # 创造真实RemoteConversation
        conv = RemoteConversation(
            agent=agent,
            workspace=RemoteWorkspace(working_dir="/tmp", host="http://localhost:3000"),
        )

        # 一、全状态
        full_state = {
            "execution_status": "idle",
            "max_iterations": 50,
            "stuck_detection": True,
        }
        event1 = ConversationStateUpdateEvent(key="full_state", value=full_state)
        conv.state.update_state_from_event(event1)

        # 然后，个别更新
        event2 = ConversationStateUpdateEvent(key="execution_status", value="running")
        conv.state.update_state_from_event(event2)

        event3 = ConversationStateUpdateEvent(key="max_iterations", value=100)
        conv.state.update_state_from_event(event3)

        # 验证最终状态
        assert conv.state._cached_state is not None
        assert conv.state._cached_state["execution_status"] == "running"
        assert conv.state._cached_state["max_iterations"] == 100
        assert conv.state._cached_state["stuck_detection"] is True


def test_update_state_full_state_overwrites_fields():
    """测试 full_state 更新是否正确覆盖现有字段。"""
    agent = create_test_agent()

    # 模拟对象 httpx 客户端及其响应
    mock_client_instance = create_mock_http_client()

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        # 创造真实RemoteConversation
        conv = RemoteConversation(
            agent=agent,
            workspace=RemoteWorkspace(working_dir="/tmp", host="http://localhost:3000"),
        )

        # 设置初始缓存状态
        conv.state._cached_state = {
            "execution_status": "running",
            "max_iterations": 100,
            "old_field": "old_value",
        }

        # 更新完整状态（不带 old_field）
        full_state = {
            "execution_status": "idle",
            "max_iterations": 50,
        }
        event = ConversationStateUpdateEvent(key="full_state", value=full_state)
        conv.state.update_state_from_event(event)

        # 验证新字段已设置并且旧字段仍然存在（更新，而不是替换）
        assert conv.state._cached_state is not None
        assert conv.state._cached_state["execution_status"] == "idle"
        assert conv.state._cached_state["max_iterations"] == 50
        assert "old_field" in conv.state._cached_state  # 仍然存在。update()


def test_update_state_thread_safe():
    """测试状态更新是否为线程安全。"""
    import threading
    import time

    agent = create_test_agent()

    # 模拟对象 httpx 客户端及其响应
    mock_client_instance = create_mock_http_client()

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        # 创造真实RemoteConversation
        conv = RemoteConversation(
            agent=agent,
            workspace=RemoteWorkspace(working_dir="/tmp", host="http://localhost:3000"),
        )

        # 设置初始缓存状态
        conv.state._cached_state = {"counter": 0}

        def update_worker(i):
            event = ConversationStateUpdateEvent(key="counter", value=i)
            conv.state.update_state_from_event(event)
            time.sleep(0.001)  # 小延迟鼓励竞态条件

        # 创建多个线程并发更新
        threads = [threading.Thread(target=update_worker, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证状态仍然有效（应该具有以下值之一）
        assert conv.state._cached_state is not None
        assert "counter" in conv.state._cached_state
        assert 0 <= conv.state._cached_state["counter"] < 10


def test_update_state_preserves_data_types():
    """测试状态更新是否正确保留数据类型。"""
    agent = create_test_agent()

    # 模拟对象 httpx 客户端及其响应
    mock_client_instance = create_mock_http_client()

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        # 创造真实RemoteConversation
        conv = RemoteConversation(
            agent=agent,
            workspace=RemoteWorkspace(working_dir="/tmp", host="http://localhost:3000"),
        )

        # 使用各种数据类型进行更新
        full_state = {
            "string_field": "test",
            "int_field": 42,
            "bool_field": True,
            "list_field": [1, 2, 3],
            "dict_field": {"nested": "value"},
        }
        event = ConversationStateUpdateEvent(key="full_state", value=full_state)
        conv.state.update_state_from_event(event)

        # 验证类型是否已保留
        assert conv.state._cached_state is not None
        assert isinstance(conv.state._cached_state["string_field"], str)
        assert isinstance(conv.state._cached_state["int_field"], int)
        assert isinstance(conv.state._cached_state["bool_field"], bool)
        assert isinstance(conv.state._cached_state["list_field"], list)
        assert isinstance(conv.state._cached_state["dict_field"], dict)


def test_state_update_callback_integration():
    """测试状态更新回调是否正确集成。"""
    agent = create_test_agent()

    # 模拟对象 httpx 客户端及其响应
    mock_client_instance = create_mock_http_client()

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        # 创造真实RemoteConversation
        conv = RemoteConversation(
            agent=agent,
            workspace=RemoteWorkspace(working_dir="/tmp", host="http://localhost:3000"),
        )

        # 验证状态更新回调已添加到回调
        state_update_callback = conv.state.create_state_update_callback()

        # 测试回调是否正确处理 ConversationStateUpdateEvent
        event = ConversationStateUpdateEvent(key="execution_status", value="running")

        # 直接调用回调（模拟WebSocket事件）
        state_update_callback(event)

        # 验证状态已更新
        assert conv.state._cached_state is not None
        assert conv.state._cached_state["execution_status"] == "running"


def test_conversation_stats_reads_from_stats_field():
    """测试 conversation_stats 属性是否从“stats”字段读取。"""
    agent = create_test_agent()

    # 模拟对象带有统计数据的 httpx 客户端
    mock_client_instance = create_mock_http_client()

    # 模拟对象带有统计字段的对话信息响应
    mock_info_response = {
        "conversation_id": "test-id",
        "execution_status": "idle",
        "stats": {
            "usage_to_metrics": {
                "test-llm": {
                    "model_name": "gpt-4o-mini",
                    "accumulated_cost": 1.23,
                    "accumulated_token_usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 50,
                    },
                }
            }
        },
    }

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        # 创建RemoteConversation
        conv = RemoteConversation(
            agent=agent,
            workspace=RemoteWorkspace(working_dir="/tmp", host="http://localhost:3000"),
        )

        # 手动设置缓存状态以模拟 REST API 响应
        conv.state._cached_state = mock_info_response

        # 访问 conversation_stats 属性
        stats = conv.conversation_stats

        # 验证从“统计”字段正确读取统计信息
        assert stats is not None
        assert "test-llm" in stats.usage_to_metrics
        assert stats.usage_to_metrics["test-llm"].accumulated_cost == 1.23


def test_stats_update_via_state_event():
    """测试是否通过 ConversationStateUpdateEvent 接收统计更新。"""
    agent = create_test_agent()

    # 模拟对象 httpx 客户端
    mock_client_instance = create_mock_http_client()

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        # 创建RemoteConversation
        conv = RemoteConversation(
            agent=agent,
            workspace=RemoteWorkspace(working_dir="/tmp", host="http://localhost:3000"),
        )

        # 使用空统计数据设置初始状态
        initial_state = {
            "execution_status": "running",
            "stats": {"usage_to_metrics": {}},
        }
        event1 = ConversationStateUpdateEvent(key="full_state", value=initial_state)
        conv.state.update_state_from_event(event1)

        # 验证初始统计数据为空
        stats = conv.conversation_stats
        assert stats is not None
        assert stats.usage_to_metrics == {}

        # 使用新统计数据模拟状态更新
        updated_stats = {
            "usage_to_metrics": {
                "test-llm": {
                    "model_name": "gpt-4o-mini",
                    "accumulated_cost": 2.45,
                }
            }
        }
        event2 = ConversationStateUpdateEvent(key="stats", value=updated_stats)
        conv.state.update_state_from_event(event2)

        # 验证统计数据已更新
        stats = conv.conversation_stats
        assert stats is not None
        assert "test-llm" in stats.usage_to_metrics
        assert stats.usage_to_metrics["test-llm"].accumulated_cost == 2.45
