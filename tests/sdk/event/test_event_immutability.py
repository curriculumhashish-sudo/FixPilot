"""测试事件不变性。"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Self

import pytest

from openhands.sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    Condensation,
    CondensationRequest,
    Event,
    MessageEvent,
    ObservationEvent,
    PauseEvent,
    SystemPromptEvent,
    UserRejectObservation,
)
from openhands.sdk.llm import (
    ImageContent,
    Message,
    MessageToolCall,
    TextContent,
)
from openhands.sdk.tool import ToolDefinition, ToolExecutor
from openhands.sdk.tool.schema import Action, Observation


if TYPE_CHECKING:
    from openhands.sdk.conversation.impl.local_conversation import LocalConversation


class EventsImmutabilityMockAction(Action):
    """模拟对象测试操作。"""

    command: str = "test_command"


class EventsImmutabilityMockObservation(Observation):
    """模拟对象观测结果用于测试。"""

    result: str = "test_result"

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text=self.result)]


class EventsImmutabilityMockExecutor(ToolExecutor):
    """模拟对象用于测试的执行器。"""

    def __call__(
        self,
        action: EventsImmutabilityMockAction,
        conversation: "LocalConversation | None" = None,
    ) -> EventsImmutabilityMockObservation:
        return EventsImmutabilityMockObservation.from_text("test")


class EventsImmutabilityMockTool(
    ToolDefinition[EventsImmutabilityMockAction, EventsImmutabilityMockObservation]
):
    """模拟对象测试工具。"""

    @classmethod
    def create(cls, *args, **kwargs) -> Sequence[Self]:
        return [
            cls(
                description="Test tool",
                action_type=EventsImmutabilityMockAction,
                observation_type=EventsImmutabilityMockObservation,
                executor=EventsImmutabilityMockExecutor(),
            )
        ]


class _TestEventForImmutability(Event):
    """用于不变性测试的测试事件类。

    此类在模块级别定义（而不是在测试函数内部），以确保它在序列化/反序列化期间可由
    Pydantic 导入。 当与 pytest-xdist 并行运行测试时，在测试函数
    中定义它会导致测试污染。
    """

    test_field: str = "test_value"


def test_event_base_is_frozen():
    """测试事件实例是否已冻结且无法修改。"""
    event = _TestEventForImmutability(source="agent", test_field="initial_value")

    # 测试我们不能修改任何字段
    with pytest.raises(Exception):  # Pydantic 为冻结模型加薪 ValidationError
        event.id = "modified_id"

    with pytest.raises(Exception):
        event.timestamp = "modified_timestamp"

    with pytest.raises(Exception):
        event.source = "user"

    with pytest.raises(Exception):
        event.test_field = "modified_value"


def test_system_prompt_event_is_frozen():
    """测试 SystemPromptEvent 个实例是否被冻结。"""
    tool = EventsImmutabilityMockTool.create()[0]

    event = SystemPromptEvent(
        system_prompt=TextContent(text="Test system prompt"),
        tools=[tool],
    )

    # 测试我们不能修改任何字段
    with pytest.raises(Exception):
        event.system_prompt = TextContent(text="Modified prompt")

    with pytest.raises(Exception):
        event.tools = []

    with pytest.raises(Exception):
        event.id = "modified_id"


def test_action_event_is_frozen():
    """测试 ActionEvent 个实例是否被冻结。"""
    action = EventsImmutabilityMockAction()
    tool_call = MessageToolCall(
        id="test_call_id", name="test_tool", arguments="{}", origin="completion"
    )

    event = ActionEvent(
        thought=[TextContent(text="Test thought")],
        action=action,
        tool_name="test_tool",
        tool_call_id="test_call_id",
        tool_call=tool_call,
        llm_response_id="test_response_id",
    )

    # 测试我们不能修改任何字段
    with pytest.raises(Exception):
        event.thought = [TextContent(text="Modified thought")]

    with pytest.raises(Exception):
        event.action = EventsImmutabilityMockAction(command="modified_command")

    with pytest.raises(Exception):
        event.tool_name = "modified_tool"

    with pytest.raises(Exception):
        event.reasoning_content = "modified_reasoning"


def test_observation_event_is_frozen():
    """测试 ObservationEvent 个实例是否被冻结。"""
    observation = EventsImmutabilityMockObservation()

    event = ObservationEvent(
        observation=observation,
        action_id="test_action_id",
        tool_name="test_tool",
        tool_call_id="test_call_id",
    )

    # 测试我们不能修改任何字段
    with pytest.raises(Exception):
        event.observation = EventsImmutabilityMockObservation(result="modified_result")

    with pytest.raises(Exception):
        event.action_id = "modified_action_id"

    with pytest.raises(Exception):
        event.tool_name = "modified_tool"

    with pytest.raises(Exception):
        event.tool_call_id = "modified_call_id"


def test_message_event_is_frozen():
    """测试 MessageEvent 个实例是否被冻结。"""
    message = Message(role="user", content=[TextContent(text="Test message")])

    event = MessageEvent(source="user", llm_message=message)

    # 测试我们不能修改任何字段
    with pytest.raises(Exception):
        event.source = "agent"

    with pytest.raises(Exception):
        event.llm_message = Message(
            role="assistant", content=[TextContent(text="Modified message")]
        )

    with pytest.raises(Exception):
        event.activated_skills = ["test_skill"]

    with pytest.raises(Exception):
        event.extended_content = [TextContent(text="Extended content")]


def test_user_reject_observation_is_frozen():
    """测试 UserRejectObservation 个实例是否被冻结。"""
    event = UserRejectObservation(
        action_id="test_action_id",
        tool_name="test_tool",
        tool_call_id="test_call_id",
        rejection_reason="Test rejection",
    )

    # 测试我们不能修改任何字段
    with pytest.raises(Exception):
        event.action_id = "modified_action_id"

    with pytest.raises(Exception):
        event.tool_name = "modified_tool"

    with pytest.raises(Exception):
        event.tool_call_id = "modified_call_id"

    with pytest.raises(Exception):
        event.rejection_reason = "Modified rejection"

    with pytest.raises(Exception):
        event.rejection_source = "hook"


def test_user_reject_observation_rejection_source():
    """测试 UserRejectObservation rejection_source 字段是否正常工作。"""
    # 默认应该是“用户”
    user_event = UserRejectObservation(
        action_id="test_action_id",
        tool_name="test_tool",
        tool_call_id="test_call_id",
        rejection_reason="User rejected",
    )
    assert user_event.rejection_source == "user"

    # 钩子拒绝应该有“钩子”来源
    hook_event = UserRejectObservation(
        action_id="test_action_id",
        tool_name="test_tool",
        tool_call_id="test_call_id",
        rejection_reason="Blocked by hook",
        rejection_source="hook",
    )
    assert hook_event.rejection_source == "hook"


def test_agent_error_event_is_frozen():
    """测试 AgentErrorEvent 个实例是否被冻结。"""
    event = AgentErrorEvent(
        error="Test error message", tool_call_id="test_call_id", tool_name="test_tool"
    )

    # 测试我们不能修改任何字段
    with pytest.raises(Exception):
        event.error = "Modified error message"

    with pytest.raises(Exception):
        event.source = "user"


def test_pause_event_is_frozen():
    """测试 PauseEvent 个实例是否被冻结。"""
    event = PauseEvent()

    # 测试我们不能修改任何字段
    with pytest.raises(Exception):
        event.source = "agent"

    with pytest.raises(Exception):
        event.id = "modified_id"


def test_condensation_is_frozen():
    """测试上下文压缩个实例是否被冻结。"""
    event = Condensation(
        forgotten_event_ids={"event1", "event2"},
        summary="Test summary",
        llm_response_id="condensation_response_1",
    )

    # 测试我们不能修改任何字段
    with pytest.raises(Exception):
        event.forgotten_event_ids = {"modified_event"}

    with pytest.raises(Exception):
        event.summary = "Modified summary"

    with pytest.raises(Exception):
        event.summary_offset = 10


def test_condensation_request_is_frozen():
    """测试 CondensationRequest 个实例是否被冻结。"""
    event = CondensationRequest()

    # 测试我们不能修改任何字段
    with pytest.raises(Exception):
        event.source = "agent"

    with pytest.raises(Exception):
        event.id = "modified_id"


def test_event_model_copy_creates_new_instance():
    """测试 model_copy 是否可以创建冻结事件的修改版本。"""
    event = PauseEvent()
    original_id = event.id

    # 创建包含修改字段的副本
    modified_event = event.model_copy(update={"id": "new_id"})

    # 验证是否创建了经过修改的新实例
    assert modified_event is not event
    assert event.id == original_id
    assert modified_event.id == "new_id"
    assert modified_event.source == event.source


def test_event_immutability_prevents_mutation_bugs():
    """测试冻结事件是否可以防止 PR #226 中修复的突变错误类型。"""
    tool = EventsImmutabilityMockTool.create()[0]

    event = SystemPromptEvent(
        system_prompt=TextContent(text="Test system prompt"),
        tools=[tool],
    )

    # 存储原始刀具数据
    original_tool_name = event.tools[0].name
    original_tool_description = event.tools[0].description

    # 多次调用可视化（这通常会导致突变）
    for _ in range(3):
        _ = event.visualize

    # 验证没有发生突变 - 事件数据应该保持不变
    assert event.tools[0].name == original_tool_name
    assert event.tools[0].description == original_tool_description

    # 验证尝试直接修改事件字段是否失败
    with pytest.raises(Exception):
        event.tools = []  # 这应该会失败，因为事件被冻结
