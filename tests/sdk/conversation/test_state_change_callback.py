"""测试 ConversationState 回调机制。"""

import uuid

import pytest
from pydantic import SecretStr

from openhands.sdk import LLM, Agent
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from openhands.sdk.io import InMemoryFileStore
from openhands.sdk.workspace import LocalWorkspace


@pytest.fixture
def state():
    """创建一个 ConversationState 进行测试。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm)
    workspace = LocalWorkspace(working_dir="/tmp/test")

    state = ConversationState(
        id=uuid.uuid4(),
        workspace=workspace,
        persistence_dir="/tmp/test/.state",
        agent=agent,
    )

    # 设置文件存储并启用自动保存，以便触发回调
    state._fs = InMemoryFileStore()
    state._autosave_enabled = True

    return state


def test_set_on_state_change_callback(state):
    """测试回调是否可以设置并在状态改变时被调用。"""
    callback_calls = []

    def callback(event: ConversationStateUpdateEvent):
        callback_calls.append(event)

    # 设置回调
    state.set_on_state_change(callback)

    # 更改状态 - 应触发回调
    with state:
        state.execution_status = ConversationExecutionStatus.RUNNING

    # 验证回调被调用
    assert len(callback_calls) == 1
    event = callback_calls[0]
    assert isinstance(event, ConversationStateUpdateEvent)
    assert event.key == "execution_status"
    assert event.value == ConversationExecutionStatus.RUNNING


def test_callback_called_multiple_times(state):
    """测试是否调用回调来进行多个状态更改。"""
    callback_calls = []

    def callback(event: ConversationStateUpdateEvent):
        callback_calls.append(event)

    state.set_on_state_change(callback)

    # 进行多个状态更改
    with state:
        state.execution_status = ConversationExecutionStatus.RUNNING
        state.execution_status = ConversationExecutionStatus.PAUSED
        state.execution_status = ConversationExecutionStatus.FINISHED

    # 验证每次更改都调用了回调
    assert len(callback_calls) == 3
    assert callback_calls[0].value == ConversationExecutionStatus.RUNNING
    assert callback_calls[1].value == ConversationExecutionStatus.PAUSED
    assert callback_calls[2].value == ConversationExecutionStatus.FINISHED


def test_callback_can_be_cleared(state):
    """测试是否可以通过设置为None来清除回调。"""
    callback_calls = []

    def callback(event: ConversationStateUpdateEvent):
        callback_calls.append(event)

    # 设置然后清除回调
    state.set_on_state_change(callback)
    state.set_on_state_change(None)

    # 更改状态 - 不应调用回调
    with state:
        state.execution_status = ConversationExecutionStatus.RUNNING

    # 验证回调未被调用
    assert len(callback_calls) == 0


def test_callback_exception_does_not_break_state_change(state):
    """测试回调中的异常不会阻止状态更改。"""

    def bad_callback(event: ConversationStateUpdateEvent):
        raise ValueError("Callback error")

    state.set_on_state_change(bad_callback)

    # 更改状态 - 尽管出现回调错误，但不应引发
    with state:
        state.execution_status = ConversationExecutionStatus.RUNNING

    # 验证状态仍然改变
    assert state.execution_status == ConversationExecutionStatus.RUNNING


def test_callback_not_called_without_lock(state):
    """测试仅当状态在锁内修改时才调用回调。"""
    callback_calls = []

    def callback(event: ConversationStateUpdateEvent):
        callback_calls.append(event)

    state.set_on_state_change(callback)

    # 这应该仍然会触发回调，因为 __setattr__ 被调用
    with state:
        state.execution_status = ConversationExecutionStatus.RUNNING

    # 验证回调被调用
    assert len(callback_calls) == 1


def test_callback_with_different_field_types(state):
    """测试回调适用于不同类型的字段。"""
    callback_calls = []

    def callback(event: ConversationStateUpdateEvent):
        callback_calls.append(event)

    state.set_on_state_change(callback)

    # 更改不同类型的字段
    with state:
        state.execution_status = ConversationExecutionStatus.RUNNING
        state.max_iterations = 100
        state.stuck_detection = False

    # 验证每次更改都调用了回调
    assert len(callback_calls) == 3
    assert callback_calls[0].key == "execution_status"
    assert callback_calls[1].key == "max_iterations"
    assert callback_calls[2].key == "stuck_detection"


def test_callback_receives_correct_new_value(state):
    """测试回调是否收到正确的新值。"""
    callback_calls = []

    def callback(event: ConversationStateUpdateEvent):
        callback_calls.append(event)

    # 设置初始值
    with state:
        state.max_iterations = 50

    # 现在设置回调并再次更改值
    state.set_on_state_change(callback)

    with state:
        state.max_iterations = 100

    # 验证新值是否正确
    assert len(callback_calls) == 1
    assert callback_calls[0].key == "max_iterations"
    assert callback_calls[0].value == 100


def test_leaf_event_id_persists_but_does_not_broadcast(state):
    """leaf_event_id 自动保存，但不作为状态更新事件广播。

    它会随着每个附加事件而变化； 广播它将使 Agent Server 的已持久化事件日志加倍。 该
    值仍然通过 base_state.json 往返。
    """
    callback_calls = []
    state.set_on_state_change(lambda event: callback_calls.append(event))

    with state:
        state.leaf_event_id = "evt-123"  # 高频场：不广播
        state.execution_status = ConversationExecutionStatus.RUNNING  # 广播

    keys = [c.key for c in callback_calls]
    assert "leaf_event_id" not in keys
    assert keys == ["execution_status"]
    # 该值仍然适用（并且将持久化更改为 base_state.json）。
    assert state.leaf_event_id == "evt-123"
