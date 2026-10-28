"""
单元测试用于 ConversationState 中的 get_unmatched_actions 方法。

测试与各种观测结果类型匹配的操作行为，包括：
- ObservationEvent
- UserRejectObservation
- AgentErrorEvent（崩溃恢复场景）

相关问题： https://github.com/OpenHands/agent-sdk/issues/2298
"""

from litellm import ChatCompletionMessageToolCall
from litellm.types.utils import Function

from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    ObservationEvent,
    UserRejectObservation,
)
from openhands.sdk.event.base import Event
from openhands.sdk.llm import MessageToolCall, TextContent
from openhands.sdk.tool.schema import Action, Observation


class MockTestAction(Action):
    """模拟对象操作模式用于测试。"""

    command: str


class MockTestObservation(Observation):
    """模拟对象观测结果模式用于测试。"""

    result: str

    @property
    def visualize(self):
        from rich.text import Text

        return Text(self.result)


def _create_action_event(
    call_id: str = "call_1",
    command: str = "test_command",
) -> ActionEvent:
    """创建测试的帮助程序 ActionEvent。"""
    action = MockTestAction(command=command)

    litellm_tool_call = ChatCompletionMessageToolCall(
        id=call_id,
        type="function",
        function=Function(
            name="test_tool",
            arguments=f'{{"command": "{command}"}}',
        ),
    )

    tool_call = MessageToolCall.from_chat_tool_call(litellm_tool_call)

    return ActionEvent(
        source="agent",
        thought=[TextContent(text="Test thought")],
        action=action,
        tool_name="test_tool",
        tool_call_id=call_id,
        tool_call=tool_call,
        llm_response_id="response_1",
    )


def test_action_without_observation_is_unmatched():
    """测试没有任何观测结果的操作是否被视为不匹配。"""
    action = _create_action_event(call_id="call_1")
    events: list[Event] = [action]

    unmatched = ConversationState.get_unmatched_actions(events)

    assert len(unmatched) == 1
    assert unmatched[0].id == action.id


def test_action_with_observation_event_is_matched():
    """测试带有 ObservationEvent 的操作是否匹配。"""
    action = _create_action_event(call_id="call_1")
    observation = ObservationEvent(
        source="environment",
        observation=MockTestObservation(result="test result"),
        action_id=action.id,
        tool_name="test_tool",
        tool_call_id="call_1",
    )
    events: list[Event] = [action, observation]

    unmatched = ConversationState.get_unmatched_actions(events)

    assert len(unmatched) == 0


def test_action_with_user_reject_observation_is_matched():
    """测试带有 UserRejectObservation 的操作是否匹配。"""
    action = _create_action_event(call_id="call_1")
    rejection = UserRejectObservation(
        action_id=action.id,
        tool_name="test_tool",
        tool_call_id="call_1",
        rejection_reason="User rejected the action",
    )
    events: list[Event] = [action, rejection]

    unmatched = ConversationState.get_unmatched_actions(events)

    assert len(unmatched) == 0


def test_action_with_agent_error_event_is_matched():
    """测试带有 AgentErrorEvent 的操作是否匹配。

    这是崩溃恢复场景，其中：
    1. 创建 ActionEvent (tool_call_id=X)
    2. 服务器在执行过程中崩溃
    3. 重新启动时，崩溃恢复会发出 AgentErrorEvent (tool_call_id=X)
    4. 该操作现在应被视为“匹配”并重新执行不

    相关问题： https://github.com/OpenHands/agent-sdk/issues/2298
    """
    action = _create_action_event(call_id="call_crash")
    error_event = AgentErrorEvent(
        tool_name="test_tool",
        tool_call_id="call_crash",
        error=(
            "A restart occurred while this tool was in progress. "
            "This may indicate a fatal memory error or system crash."
        ),
    )
    events: list[Event] = [action, error_event]

    unmatched = ConversationState.get_unmatched_actions(events)

    # 该操作应该不不匹配，因为 AgentErrorEvent 已发出
    assert len(unmatched) == 0


def test_multiple_actions_with_mixed_responses():
    """测试多个操作和混合观测结果类型的匹配。"""
    action1 = _create_action_event(call_id="call_1", command="cmd1")
    action2 = _create_action_event(call_id="call_2", command="cmd2")
    action3 = _create_action_event(call_id="call_3", command="cmd3")
    action4 = _create_action_event(call_id="call_4", command="cmd4")

    # 动作 1 获取 ObservationEvent
    obs1 = ObservationEvent(
        source="environment",
        observation=MockTestObservation(result="result1"),
        action_id=action1.id,
        tool_name="test_tool",
        tool_call_id="call_1",
    )

    # 动作2得到UserRejectObservation
    reject2 = UserRejectObservation(
        action_id=action2.id,
        tool_name="test_tool",
        tool_call_id="call_2",
        rejection_reason="Rejected",
    )

    # action3 获取 AgentErrorEvent（崩溃恢复）
    error3 = AgentErrorEvent(
        tool_name="test_tool",
        tool_call_id="call_3",
        error="Crash recovery error",
    )

    # action4 没有响应 - 应该是不匹配的
    events: list[Event] = [action1, action2, action3, action4, obs1, reject2, error3]

    unmatched = ConversationState.get_unmatched_actions(events)

    # 只有action4应该是不匹配的
    assert len(unmatched) == 1
    assert unmatched[0].tool_call_id == "call_4"


def test_agent_error_event_matching_by_tool_call_id():
    """测试 AgentErrorEvent 是否与 tool_call_id 匹配，而不是 action_id。

    AgentErrorEvent 没有 action_id 字段（与 ObservationEvent 不同），因此匹配必须使用
     tool_call_id。
    """
    action = _create_action_event(call_id="specific_call_id")

    # AgentErrorEvent 与 tool_call_id 相同
    matching_error = AgentErrorEvent(
        tool_name="test_tool",
        tool_call_id="specific_call_id",
        error="Error message",
    )

    events: list[Event] = [action, matching_error]
    unmatched = ConversationState.get_unmatched_actions(events)

    assert len(unmatched) == 0


def test_agent_error_event_different_tool_call_id_does_not_match():
    """测试AgentErrorEvent与不同的tool_call_id不匹配。"""
    action = _create_action_event(call_id="call_A")

    # AgentErrorEvent 与 tool_call_id 不同
    non_matching_error = AgentErrorEvent(
        tool_name="test_tool",
        tool_call_id="call_B",  # 与操作的 tool_call_id 不同
        error="Error message",
    )

    events: list[Event] = [action, non_matching_error]
    unmatched = ConversationState.get_unmatched_actions(events)

    # 操作仍应不匹配，因为错误针对不同的 tool_call_id
    assert len(unmatched) == 1
    assert unmatched[0].tool_call_id == "call_A"


def test_crash_recovery_scenario_prevents_duplicate_execution():
    """测试问题 #2298 中描述的完整崩溃恢复场景。

    场景：
    1. ActionEvent 已创建 (tool_call_id=X)
    2. 工具执行期间服务器崩溃
    3. 重新启动时，崩溃恢复会发出 AgentErrorEvent (tool_call_id=X)
    4. 用户再次呼叫run()
    5. get_unmatched_actions() 应该不返回操作
    6. 因此，该操作被重新执行不（不重复观测结果）
    """
    # 第 1 步：已创建 ActionEvent
    action = _create_action_event(call_id="crash_action_id")

    # 第 3 步：崩溃恢复发出 AgentErrorEvent
    crash_error = AgentErrorEvent(
        tool_name="test_tool",
        tool_call_id="crash_action_id",
        error=(
            "A restart occurred while this tool was in progress. "
            "This may indicate a fatal memory error or system crash. "
            "The tool execution was interrupted and did not complete."
        ),
    )

    events: list[Event] = [action, crash_error]

    # 第 5 步：get_unmatched_actions() 应该不返回操作
    unmatched = ConversationState.get_unmatched_actions(events)

    assert len(unmatched) == 0, (
        "Action with AgentErrorEvent should not be returned as unmatched, "
        "otherwise it will be re-executed causing duplicate observations"
    )


def test_non_executable_action_is_not_considered_unmatched():
    """测试 action=None（不可执行）的操作是否不匹配。"""
    litellm_tool_call = ChatCompletionMessageToolCall(
        id="call_nonexec",
        type="function",
        function=Function(
            name="test_tool",
            arguments='{"command": "test"}',
        ),
    )
    tool_call = MessageToolCall.from_chat_tool_call(litellm_tool_call)

    # ActionEvent 且操作=None（不可执行）
    non_executable_action = ActionEvent(
        source="agent",
        thought=[TextContent(text="Test thought")],
        action=None,  # 不可执行
        tool_name="test_tool",
        tool_call_id="call_nonexec",
        tool_call=tool_call,
        llm_response_id="response_1",
    )

    events: list[Event] = [non_executable_action]
    unmatched = ConversationState.get_unmatched_actions(events)

    # 不可执行的操作不应出现在不匹配的位置
    assert len(unmatched) == 0
