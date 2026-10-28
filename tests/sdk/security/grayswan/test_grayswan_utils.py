"""测试 GraySwan utils 模块。"""

import json

from openhands.sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    MessageEvent,
    ObservationEvent,
    SystemPromptEvent,
    UserRejectObservation,
)
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.security.grayswan.utils import convert_events_to_openai_messages
from openhands.sdk.tool import Action, Observation


class GraySwanUtilsTestAction(Action):
    """模拟对象 GraySwan utils 测试的操作。"""

    command: str = "test_command"


class GraySwanUtilsTestObservation(Observation):
    """模拟对象观测结果用于 GraySwan 实用程序测试。"""

    output: str = "test_output"

    @property
    def to_llm_content(self) -> list[TextContent]:
        return [TextContent(text=self.output)]


def create_system_prompt_event(prompt: str = "You are a helpful assistant."):
    """创建一个 SystemPromptEvent 进行测试。"""
    return SystemPromptEvent(
        system_prompt=TextContent(text=prompt),
        tools=[],
    )


def create_message_event(content: str, source: str = "user"):
    """创建一个 MessageEvent 进行测试。"""
    return MessageEvent(
        source=source,  # type: ignore
        llm_message=Message(
            role="user" if source == "user" else "assistant",
            content=[TextContent(text=content)],
        ),
    )


def create_action_event(
    tool_name: str = "test_tool",
    command: str = "test",
    thought: str = "thinking about this",
    tool_call_id: str = "call_123",
):
    """创建一个 ActionEvent 进行测试。"""
    return ActionEvent(
        thought=[TextContent(text=thought)],
        action=GraySwanUtilsTestAction(command=command),
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_call=MessageToolCall(
            id=tool_call_id,
            name=tool_name,
            arguments=json.dumps({"command": command}),
            origin="completion",
        ),
        llm_response_id="response_123",
    )


def create_observation_event(
    tool_name: str = "test_tool",
    output: str = "test output",
    tool_call_id: str = "call_123",
    action_id: str = "action_123",
):
    """创建一个 ObservationEvent 进行测试。"""
    return ObservationEvent(
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        observation=GraySwanUtilsTestObservation(output=output),
        action_id=action_id,
    )


def create_agent_error_event(
    tool_name: str = "test_tool",
    error: str = "Something went wrong",
    tool_call_id: str = "call_123",
):
    """创建一个 AgentErrorEvent 进行测试。"""
    return AgentErrorEvent(
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        error=error,
    )


def create_user_reject_observation(
    tool_name: str = "test_tool",
    reason: str = "User rejected the action",
    tool_call_id: str = "call_123",
    action_id: str = "action_123",
):
    """创建一个 UserRejectObservation 进行测试。"""
    return UserRejectObservation(
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        rejection_reason=reason,
        action_id=action_id,
    )


class TestConvertEventsToOpenAIMessages:
    """测试 convert_events_to_openai_messages 功能。"""

    def test_empty_events(self):
        """测试空事件列表的转换。"""
        result = convert_events_to_openai_messages([])
        assert result == []

    def test_system_prompt_event(self):
        """测试 SystemPromptEvent 的转换。"""
        events = [create_system_prompt_event("You are a helpful assistant.")]
        result = convert_events_to_openai_messages(events)

        assert len(result) == 1
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are a helpful assistant."

    def test_user_message_event(self):
        """测试用户MessageEvent的转化。"""
        events = [create_message_event("Hello, how are you?", "user")]
        result = convert_events_to_openai_messages(events)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hello, how are you?"

    def test_agent_message_event(self):
        """测试智能体 MessageEvent 的转换。"""
        events = [create_message_event("I'm doing well, thanks!", "agent")]
        result = convert_events_to_openai_messages(events)

        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "I'm doing well, thanks!"

    def test_action_event(self):
        """测试 ActionEvent 的转换。"""
        events = [
            create_action_event(
                tool_name="execute_bash",
                command="ls -la",
                thought="Let me list the files",
                tool_call_id="call_abc",
            )
        ]
        result = convert_events_to_openai_messages(events)

        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Let me list the files"
        assert "tool_calls" in result[0]
        assert len(result[0]["tool_calls"]) == 1
        assert result[0]["tool_calls"][0]["id"] == "call_abc"
        assert result[0]["tool_calls"][0]["function"]["name"] == "execute_bash"

    def test_action_event_removes_security_risk_from_arguments(self):
        """测试 security_risk 是否已从工具调用参数中删除。"""
        action = ActionEvent(
            thought=[TextContent(text="thinking")],
            action=GraySwanUtilsTestAction(command="test"),
            tool_name="test_tool",
            tool_call_id="call_123",
            tool_call=MessageToolCall(
                id="call_123",
                name="test_tool",
                arguments=json.dumps({"command": "test", "security_risk": "LOW"}),
                origin="completion",
            ),
            llm_response_id="response_123",
        )
        result = convert_events_to_openai_messages([action])

        assert len(result) == 1
        args = json.loads(result[0]["tool_calls"][0]["function"]["arguments"])
        assert "security_risk" not in args
        assert args["command"] == "test"

    def test_observation_event(self):
        """测试 ObservationEvent 的转换。"""
        events = [
            create_observation_event(
                tool_name="execute_bash",
                output="file1.txt\nfile2.txt",
                tool_call_id="call_abc",
            )
        ]
        result = convert_events_to_openai_messages(events)

        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["content"] == "file1.txt\nfile2.txt"
        assert result[0]["tool_call_id"] == "call_abc"

    def test_agent_error_event(self):
        """测试 AgentErrorEvent 的转换。"""
        events = [
            create_agent_error_event(
                tool_name="execute_bash",
                error="Command not found",
                tool_call_id="call_abc",
            )
        ]
        result = convert_events_to_openai_messages(events)

        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["content"] == "Command not found"
        assert result[0]["tool_call_id"] == "call_abc"

    def test_user_reject_observation(self):
        """测试 UserRejectObservation 的转换。"""
        events = [
            create_user_reject_observation(
                tool_name="execute_bash",
                reason="Too dangerous",
                tool_call_id="call_abc",
            )
        ]
        result = convert_events_to_openai_messages(events)

        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert "Too dangerous" in result[0]["content"]
        assert result[0]["tool_call_id"] == "call_abc"

    def test_full_conversation(self):
        """测试具有多种事件类型的完整对话的转换。"""
        events = [
            create_system_prompt_event("You are a helpful assistant."),
            create_message_event("List the files in the current directory", "user"),
            create_action_event(
                tool_name="execute_bash",
                command="ls -la",
                thought="I'll list the files",
                tool_call_id="call_1",
            ),
            create_observation_event(
                tool_name="execute_bash",
                output="file1.txt\nfile2.txt",
                tool_call_id="call_1",
            ),
            create_message_event("Here are the files in the directory.", "agent"),
        ]
        result = convert_events_to_openai_messages(events)

        assert len(result) == 5
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert result[2]["role"] == "assistant"
        assert "tool_calls" in result[2]
        assert result[3]["role"] == "tool"
        assert result[4]["role"] == "assistant"

    def test_multiple_tool_calls_in_sequence(self):
        """依次测试多个工具调用的转换。"""
        events = [
            create_action_event(
                tool_name="tool1",
                command="cmd1",
                thought="First action",
                tool_call_id="call_1",
            ),
            create_observation_event(
                tool_name="tool1",
                output="output1",
                tool_call_id="call_1",
            ),
            create_action_event(
                tool_name="tool2",
                command="cmd2",
                thought="Second action",
                tool_call_id="call_2",
            ),
            create_observation_event(
                tool_name="tool2",
                output="output2",
                tool_call_id="call_2",
            ),
        ]
        result = convert_events_to_openai_messages(events)

        assert len(result) == 4
        assert result[0]["tool_calls"][0]["id"] == "call_1"
        assert result[1]["tool_call_id"] == "call_1"
        assert result[2]["tool_calls"][0]["id"] == "call_2"
        assert result[3]["tool_call_id"] == "call_2"
