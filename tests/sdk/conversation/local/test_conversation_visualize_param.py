"""测试 Conversation 类可视化参数。"""

from unittest.mock import Mock, patch

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.visualizer import (
    DefaultConversationVisualizer,
)
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.llm import LLM, Message, TextContent


def create_test_event(content: str = "Test event content") -> MessageEvent:
    """创建一个测试 MessageEvent 进行测试。"""
    return MessageEvent(
        llm_message=Message(role="user", content=[TextContent(text=content)]),
        source="user",
    )


@pytest.fixture
def mock_agent():
    """创建一个真实的智能体进行测试。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    return agent


def test_conversation_with_default_visualizer(mock_agent):
    """使用默认可视化工具测试对话（省略参数）。"""
    with patch.object(Agent, "init_state") as mock_init_state:
        conversation = Conversation(agent=mock_agent)

        # 应该有一个可视化工具
        assert conversation._visualizer is not None
        assert isinstance(conversation._visualizer, DefaultConversationVisualizer)

        # 智能体初始化是惰性的； 显式触发它
        conversation._ensure_agent_ready()

        # 智能体应使用包含可视化工具的回调进行初始化
        mock_init_state.assert_called_once()
        args, kwargs = mock_init_state.call_args
        assert "on_event" in kwargs

        # on_event回调应该由多个回调组成
        on_event = kwargs["on_event"]
        assert callable(on_event)


def test_conversation_with_visualize_false(mock_agent):
    """使用可视化工具=None测试对话。"""
    with patch.object(Agent, "init_state") as mock_init_state:
        conversation = Conversation(agent=mock_agent, visualizer=None)

        # 不应该有可视化工具
        assert conversation._visualizer is None

        # 智能体初始化是惰性的； 显式触发它
        conversation._ensure_agent_ready()

        # 智能体仍应使用回调进行初始化（只是不是可视化工具）
        mock_init_state.assert_called_once()
        args, kwargs = mock_init_state.call_args
        assert "on_event" in kwargs

        # on_event 回调应该仍然存在（对于状态持久化）
        on_event = kwargs["on_event"]
        assert callable(on_event)


def test_conversation_default_visualize_is_true(mock_agent):
    """测试可视化工具是否默认为默认可视化工具。"""
    with patch.object(Agent, "init_state"):
        conversation = Conversation(agent=mock_agent)

        # 默认情况下应该有一个可视化工具
        assert conversation._visualizer is not None
        assert isinstance(conversation._visualizer, DefaultConversationVisualizer)


def test_conversation_with_custom_callbacks_and_default_visualizer(mock_agent):
    """使用自定义回调和默认可视化工具测试对话。"""
    custom_callback = Mock()
    callbacks = [custom_callback]

    with patch.object(Agent, "init_state") as mock_init_state:
        conversation = Conversation(agent=mock_agent, callbacks=callbacks)

        # 应该有一个可视化工具
        assert conversation._visualizer is not None

        # 智能体初始化是惰性的； 显式触发它
        conversation._ensure_agent_ready()

        # 通过触发事件来测试回调是否正确组成
        mock_init_state.assert_called_once()
        args, kwargs = mock_init_state.call_args
        on_event = kwargs["on_event"]

        # 创建测试事件
        test_event = create_test_event("Test event content")
        on_event(test_event)

        # 应该调用自定义回调
        custom_callback.assert_called_once_with(test_event)

        # 事件应处于对话状态
        assert test_event in conversation.state.events


def test_conversation_with_custom_callbacks_and_visualize_false(mock_agent):
    """使用自定义回调和 Visualize=False 测试对话。"""
    custom_callback = Mock()
    callbacks = [custom_callback]

    with patch.object(Agent, "init_state") as mock_init_state:
        conversation = Conversation(
            agent=mock_agent, callbacks=callbacks, visualizer=None
        )

        # 不应该有可视化工具
        assert conversation._visualizer is None

        # 智能体初始化是惰性的； 显式触发它
        conversation._ensure_agent_ready()

        # 测试回调的组成是否正确
        mock_init_state.assert_called_once()
        args, kwargs = mock_init_state.call_args
        on_event = kwargs["on_event"]

        # 创建测试事件并触发它
        test_event = create_test_event("Test event content")
        on_event(test_event)

        # 应该调用自定义回调
        custom_callback.assert_called_once_with(test_event)

        # 事件应处于对话状态
        assert test_event in conversation.state.events


def test_conversation_callback_order(mock_agent):
    """测试回调是否以正确的顺序执行。"""
    call_order = []

    def callback1(event):
        call_order.append("callback1")

    def callback2(event):
        call_order.append("callback2")

    # 创建一个自定义可视化工具来跟踪它的调用时间
    with patch.object(Agent, "init_state") as mock_init_state:
        # 创建模拟对象可视化工具实例
        mock_visualizer = Mock(spec=DefaultConversationVisualizer)
        mock_visualizer.on_event = Mock(
            side_effect=lambda e: call_order.append("visualizer")
        )

        conversation = Conversation(
            agent=mock_agent,
            callbacks=[callback1, callback2],
            visualizer=mock_visualizer,
        )

        # 智能体初始化是惰性的； 显式触发它
        conversation._ensure_agent_ready()

        # 获取组合回调
        mock_init_state.assert_called_once()
        args, kwargs = mock_init_state.call_args
        on_event = kwargs["on_event"]

        # 触发事件
        test_event = create_test_event("Test event content")
        on_event(test_event)

        # 检查顺序：可视化工具、回调 1、回调 2，然后状态持久化
        assert call_order == ["visualizer", "callback1", "callback2"]

        # 事件应处于状态（状态持久化最后发生）
        assert test_event in conversation.state.events


def test_conversation_no_callbacks_with_default_visualizer(mock_agent):
    """使用默认可视化工具而不是自定义回调来测试对话。"""
    with patch.object(Agent, "init_state") as mock_init_state:
        conversation = Conversation(agent=mock_agent, callbacks=None)

        # 应该有一个可视化工具
        assert conversation._visualizer is not None

        # 智能体初始化是惰性的； 显式触发它
        conversation._ensure_agent_ready()

        # 仍应仅使用可视化工具和状态持久化
        mock_init_state.assert_called_once()
        args, kwargs = mock_init_state.call_args
        on_event = kwargs["on_event"]

        # 应该能够处理事件
        test_event = create_test_event("Test event content")
        on_event(test_event)

        # 事件应该处于状态
        assert test_event in conversation.state.events


def test_conversation_no_callbacks_with_visualize_false(mock_agent):
    """测试没有自定义回调和 Visualize=False 的对话。"""
    with patch.object(Agent, "init_state") as mock_init_state:
        conversation = Conversation(agent=mock_agent, callbacks=None, visualizer=None)

        # 不应该有可视化工具
        assert conversation._visualizer is None

        # 智能体初始化是惰性的； 显式触发它
        conversation._ensure_agent_ready()

        # 仍应仅使用状态持久化
        mock_init_state.assert_called_once()
        args, kwargs = mock_init_state.call_args
        on_event = kwargs["on_event"]

        # 应该能够处理事件
        test_event = create_test_event("Test event content")
        on_event(test_event)

        # 事件应该处于状态
        assert test_event in conversation.state.events


def test_conversation_with_custom_visualizer_instance(mock_agent):
    """使用自定义 DefaultConversationVisualizer 实例测试对话。"""
    # 创建自定义可视化工具
    custom_visualizer = DefaultConversationVisualizer(
        highlight_regex={"Test:": "bold red"},
        skip_user_messages=True,
    )

    with patch.object(Agent, "init_state") as mock_init_state:
        conversation = Conversation(agent=mock_agent, visualizer=custom_visualizer)

        # 应该使用自定义可视化工具
        assert conversation._visualizer is custom_visualizer
        assert isinstance(conversation._visualizer, DefaultConversationVisualizer)

        # 智能体初始化是惰性的； 显式触发它
        conversation._ensure_agent_ready()

        # 智能体应使用包含自定义可视化工具的回调进行初始化
        mock_init_state.assert_called_once()
        args, kwargs = mock_init_state.call_args
        assert "on_event" in kwargs

        # on_event回调应该由多个回调组成
        on_event = kwargs["on_event"]
        assert callable(on_event)


def test_conversation_with_custom_visualizer_and_callbacks(mock_agent):
    """使用自定义可视化工具和自定义回调测试对话。"""
    custom_callback = Mock()
    callbacks = [custom_callback]

    # 使用模拟的 on_event 创建自定义可视化工具来跟踪呼叫
    custom_visualizer = Mock(spec=DefaultConversationVisualizer)
    custom_visualizer.on_event = Mock()

    with patch.object(Agent, "init_state") as mock_init_state:
        conversation = Conversation(
            agent=mock_agent, callbacks=callbacks, visualizer=custom_visualizer
        )

        # 应该使用自定义可视化工具
        assert conversation._visualizer is custom_visualizer

        # 智能体初始化是惰性的； 显式触发它
        conversation._ensure_agent_ready()

        # 测试回调的组成是否正确
        mock_init_state.assert_called_once()
        args, kwargs = mock_init_state.call_args
        on_event = kwargs["on_event"]

        # 创建测试事件并触发它
        test_event = create_test_event("Test event content")
        on_event(test_event)

        # 自定义可视化工具和自定义回调都应该被调用
        custom_visualizer.on_event.assert_called_once_with(test_event)
        custom_callback.assert_called_once_with(test_event)

        # 事件应处于对话状态
        assert test_event in conversation.state.events


def test_conversation_with_visualize_none(mock_agent):
    """使用 Visualize=None 测试对话（无可视化）。"""
    with patch.object(Agent, "init_state") as mock_init_state:
        conversation = Conversation(agent=mock_agent, visualizer=None)

        # 不应该有可视化工具
        assert conversation._visualizer is None

        # 智能体初始化是惰性的； 显式触发它
        conversation._ensure_agent_ready()

        # 智能体仍应使用回调进行初始化（只是不是可视化工具）
        mock_init_state.assert_called_once()
        args, kwargs = mock_init_state.call_args
        assert "on_event" in kwargs

        # on_event 回调应该仍然存在（对于状态持久化）
        on_event = kwargs["on_event"]
        assert callable(on_event)


def test_conversation_with_visualizer_class(mock_agent):
    """使用可视化工具类（不是实例）测试对话。"""
    with patch.object(Agent, "init_state") as mock_init_state:
        # 传递类本身，而不是实例
        conversation = Conversation(
            agent=mock_agent,
            visualizer=DefaultConversationVisualizer,
        )

        # 应该实例化可视化工具
        assert conversation._visualizer is not None
        assert isinstance(conversation._visualizer, DefaultConversationVisualizer)

        # 智能体初始化是惰性的； 显式触发它
        conversation._ensure_agent_ready()

        # 智能体应使用包含可视化工具的回调进行初始化
        mock_init_state.assert_called_once()
        args, kwargs = mock_init_state.call_args
        assert "on_event" in kwargs

        # on_event回调应该由多个回调组成
        on_event = kwargs["on_event"]
        assert callable(on_event)
