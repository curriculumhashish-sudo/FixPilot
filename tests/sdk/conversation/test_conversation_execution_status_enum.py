"""测试 ConversationExecutionStatus 枚举功能。"""

from pydantic import SecretStr

from openhands.sdk import Agent, Conversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.llm import LLM


def test_agent_execution_state_enum_basic():
    """测试基本 ConversationExecutionStatus 枚举功能。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    conversation = Conversation(agent=agent)

    # 测试初始状态
    assert conversation._state.execution_status == ConversationExecutionStatus.IDLE

    # 直接测试设置枚举
    conversation._state.execution_status = ConversationExecutionStatus.RUNNING
    assert conversation._state.execution_status == ConversationExecutionStatus.RUNNING

    # 测试设置为 FINISHED
    conversation._state.execution_status = ConversationExecutionStatus.FINISHED
    assert conversation._state.execution_status == ConversationExecutionStatus.FINISHED

    # 测试设置为 PAUSED
    conversation._state.execution_status = ConversationExecutionStatus.PAUSED
    assert conversation._state.execution_status == ConversationExecutionStatus.PAUSED

    # 测试设置为 WAITING_FOR_CONFIRMATION
    conversation._state.execution_status = (
        ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
    )
    assert (
        conversation._state.execution_status
        == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
    )

    # 测试设置为 ERROR
    conversation._state.execution_status = ConversationExecutionStatus.ERROR
    assert conversation._state.execution_status == ConversationExecutionStatus.ERROR


def test_enum_values():
    """测试所有枚举值是否正确。"""
    assert ConversationExecutionStatus.IDLE == "idle"
    assert ConversationExecutionStatus.RUNNING == "running"
    assert ConversationExecutionStatus.PAUSED == "paused"
    assert (
        ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
        == "waiting_for_confirmation"
    )
    assert ConversationExecutionStatus.FINISHED == "finished"
    assert ConversationExecutionStatus.ERROR == "error"


def test_enum_serialization():
    """测试枚举序列化和反序列化是否正确。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    conversation = Conversation(agent=agent)

    # 设置不同的状态并测试序列化
    conversation._state.execution_status = ConversationExecutionStatus.FINISHED
    serialized = conversation._state.model_dump_json()
    assert '"execution_status":"finished"' in serialized

    conversation._state.execution_status = ConversationExecutionStatus.PAUSED
    serialized = conversation._state.model_dump_json()
    assert '"execution_status":"paused"' in serialized

    conversation._state.execution_status = (
        ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
    )
    serialized = conversation._state.model_dump_json()
    assert '"execution_status":"waiting_for_confirmation"' in serialized

    conversation._state.execution_status = ConversationExecutionStatus.ERROR
    serialized = conversation._state.model_dump_json()
    assert '"execution_status":"error"' in serialized
