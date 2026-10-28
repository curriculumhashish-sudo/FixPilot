"""测试工具验证错误消息是否简洁且不包含值。"""

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Self
from unittest.mock import patch

from litellm import ChatCompletionMessageToolCall
from litellm.types.utils import (
    Choices,
    Function,
    Message as LiteLLMMessage,
    ModelResponse,
)
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event import ActionEvent, AgentErrorEvent, ObservationEvent
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.security.confirmation_policy import ConfirmRisky
from openhands.sdk.security.llm_analyzer import LLMSecurityAnalyzer
from openhands.sdk.security.risk import SecurityRisk
from openhands.sdk.tool import Action, Observation, Tool, ToolExecutor, register_tool
from openhands.sdk.tool.tool import ToolDefinition


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState


class ValidationTestAction(Action):
    """验证测试的操作。"""

    command: str = ""
    path: str = ""
    old_str: str = ""


class ValidationTestObservation(Observation):
    """观测结果用于验证测试。"""

    result: str = ""


class ValidationTestExecutor(
    ToolExecutor[ValidationTestAction, ValidationTestObservation]
):
    """仅返回观测结果的执行器。"""

    def __call__(
        self, action: ValidationTestAction, conversation=None
    ) -> ValidationTestObservation:
        return ValidationTestObservation(result="ok")


class ValidationTestTool(
    ToolDefinition[ValidationTestAction, ValidationTestObservation]
):
    """用于测试验证错误消息的工具。"""

    name = "validation_test_tool"

    @classmethod
    def create(cls, conv_state: "ConversationState | None" = None) -> Sequence[Self]:
        return [
            cls(
                description="A tool for testing validation errors",
                action_type=ValidationTestAction,
                observation_type=ValidationTestObservation,
                executor=ValidationTestExecutor(),
            )
        ]


register_tool("ValidationTestTool", ValidationTestTool)


def test_validation_error_shows_keys_not_values():
    """错误消息应显示参数键，而不是大参数值。"""
    llm = LLM(
        usage_id="test-llm",
        model="test-model",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )
    agent = Agent(llm=llm, tools=[Tool(name="ValidationTestTool")])

    # 创建具有大参数的工具调用和无效的 security_risk，以在同一代码路径中触发验证错误。
    #
    large_value = "x" * 1000
    tool_args = (
        f'{{"command": "view", "path": "/test", "old_str": "{large_value}", '
        f'"security_risk": "INVALID"}}'
    )

    def mock_llm_response(messages, **kwargs):
        return ModelResponse(
            id="mock-1",
            choices=[
                Choices(
                    index=0,
                    message=LiteLLMMessage(
                        role="assistant",
                        content="I'll use the tool.",
                        tool_calls=[
                            ChatCompletionMessageToolCall(
                                id="call_1",
                                type="function",
                                function=Function(
                                    name="validation_test_tool", arguments=tool_args
                                ),
                            )
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
            created=0,
            model="test-model",
            object="chat.completion",
        )

    collected_events = []
    conversation = Conversation(agent=agent, callbacks=[collected_events.append])
    conversation.set_security_analyzer(LLMSecurityAnalyzer())

    with patch(
        "openhands.sdk.llm.llm.litellm_completion", side_effect=mock_llm_response
    ):
        conversation.send_message(
            Message(role="user", content=[TextContent(text="Do something")])
        )
        agent.step(conversation, on_event=collected_events.append)

    error_events = [e for e in collected_events if isinstance(e, AgentErrorEvent)]
    assert len(error_events) == 1

    error_msg = error_events[0].error
    # 错误应包括工具名称和参数键
    assert "validation_test_tool" in error_msg
    assert "Parameters provided:" in error_msg
    assert "command" in error_msg
    assert "path" in error_msg
    assert "old_str" in error_msg
    # 错误应不包含大值 (1000 x's)
    assert large_value not in error_msg


def test_unparseable_json_error_message():
    """解析失败时，错误消息应指示无法解析 JSON。"""
    llm = LLM(
        usage_id="test-llm",
        model="test-model",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )
    agent = Agent(llm=llm, tools=[Tool(name="ValidationTestTool")])

    # 无效 JSON 无法解析
    invalid_json = "{invalid json syntax"

    def mock_llm_response(messages, **kwargs):
        return ModelResponse(
            id="mock-1",
            choices=[
                Choices(
                    index=0,
                    message=LiteLLMMessage(
                        role="assistant",
                        content="I'll use the tool.",
                        tool_calls=[
                            ChatCompletionMessageToolCall(
                                id="call_1",
                                type="function",
                                function=Function(
                                    name="validation_test_tool", arguments=invalid_json
                                ),
                            )
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
            created=0,
            model="test-model",
            object="chat.completion",
        )

    collected_events = []
    conversation = Conversation(agent=agent, callbacks=[collected_events.append])

    with patch(
        "openhands.sdk.llm.llm.litellm_completion", side_effect=mock_llm_response
    ):
        conversation.send_message(
            Message(role="user", content=[TextContent(text="Do something")])
        )
        agent.step(conversation, on_event=collected_events.append)

    error_events = [e for e in collected_events if isinstance(e, AgentErrorEvent)]
    assert len(error_events) == 1

    error_msg = error_events[0].error
    assert "validation_test_tool" in error_msg
    assert "unparseable JSON" in error_msg

    action_events = [e for e in collected_events if isinstance(e, ActionEvent)]
    assert len(action_events) == 1
    sanitized_args = json.loads(action_events[0].tool_call.arguments)
    assert sanitized_args == {
        "_openhands_malformed_tool_call": True,
        "error": error_msg,
    }


def _mock_llm_response_factory(tool_args: str):
    """返回一个模拟对象 LLM 可调用对象，它使用给定的参数发出一个工具调用 。"""

    def mock_llm_response(messages, **kwargs):
        return ModelResponse(
            id="mock-1",
            choices=[
                Choices(
                    index=0,
                    message=LiteLLMMessage(
                        role="assistant",
                        content="I'll use the tool.",
                        tool_calls=[
                            ChatCompletionMessageToolCall(
                                id="call_1",
                                type="function",
                                function=Function(
                                    name="validation_test_tool",
                                    arguments=tool_args,
                                ),
                            )
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
            created=0,
            model="test-model",
            object="chat.completion",
        )

    return mock_llm_response


def test_tool_call_without_security_risk_succeeds():
    """省略 security_risk 不应引发； 该操作会产生 UNKNOWN 风险。"""
    llm = LLM(
        usage_id="test-llm",
        model="test-model",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )
    agent = Agent(llm=llm, tools=[Tool(name="ValidationTestTool")])

    # 两个有效参数，NO security_risk 字段
    tool_args = '{"command": "view", "path": "/test"}'

    collected_events = []
    conversation = Conversation(agent=agent, callbacks=[collected_events.append])
    conversation.set_security_analyzer(LLMSecurityAnalyzer())

    with patch(
        "openhands.sdk.llm.llm.litellm_completion",
        side_effect=_mock_llm_response_factory(tool_args),
    ):
        conversation.send_message(
            Message(role="user", content=[TextContent(text="Do something")])
        )
        agent.step(conversation, on_event=collected_events.append)

    # 不应发出任何错误事件
    error_events = [e for e in collected_events if isinstance(e, AgentErrorEvent)]
    assert error_events == [], (
        f"Expected no errors when security_risk is omitted, got: {error_events}"
    )

    # 应该发出具有 UNKNOWN 风险的 ActionEvent
    action_events = [e for e in collected_events if isinstance(e, ActionEvent)]
    assert len(action_events) == 1
    assert action_events[0].security_risk == SecurityRisk.UNKNOWN


def test_omitted_security_risk_still_requires_confirmation():
    """与 LLMSecurityAnalyzer + ConfirmRisky, UNKNOWN 风险不能自动推进。"""
    llm = LLM(
        usage_id="test-llm",
        model="test-model",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )
    agent = Agent(llm=llm, tools=[Tool(name="ValidationTestTool")])

    # 两个有效参数，NO security_risk 字段
    tool_args = '{"command": "view", "path": "/test"}'

    collected_events = []
    conversation = Conversation(agent=agent, callbacks=[collected_events.append])
    conversation.set_security_analyzer(LLMSecurityAnalyzer())
    # confirm_unknown 默认为 True，因此默认的 ConfirmRisky 策略将要求确认 UNKNOWN 风险操
    # 作。
    #
    conversation.set_confirmation_policy(ConfirmRisky())

    with patch(
        "openhands.sdk.llm.llm.litellm_completion",
        side_effect=_mock_llm_response_factory(tool_args),
    ):
        conversation.send_message(
            Message(role="user", content=[TextContent(text="Do something")])
        )
        agent.step(conversation, on_event=collected_events.append)

    # 该操作应该等待确认，而不是自动执行
    assert (
        conversation.state.execution_status
        == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
    )

    # ActionEvent 应该存在且具有 UNKNOWN 风险
    action_events = [e for e in collected_events if isinstance(e, ActionEvent)]
    assert len(action_events) == 1
    assert action_events[0].security_risk == SecurityRisk.UNKNOWN

    # 不应生成观测结果（操作未执行）
    observation_events = [
        e for e in collected_events if isinstance(e, ObservationEvent)
    ]
    assert observation_events == [], (
        "Action should not have been executed while waiting for confirmation"
    )
