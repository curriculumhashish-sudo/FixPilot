"""
单元测试用于暂停功能。

测试核心行为：在步骤之间暂停智能体执行。 关键要求：
1. 连续多次调用暂停方法只会创建一个PauseEvent
2. 当 conversation.run() 仍在单独的线程中运行时调用 conversation.pause() 将暂停智能体
3. 在已经暂停的智能体上调用 conversation.run() 将恢复它
"""

import threading
from collections.abc import Sequence
from typing import ClassVar
from unittest.mock import patch

import pytest
from litellm import ChatCompletionMessageToolCall
from litellm.types.utils import (
    Choices,
    Function,
    Message as LiteLLMMessage,
    ModelResponse,
)
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation, LocalConversation
from openhands.sdk.conversation.base import BaseConversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event import ActionEvent, MessageEvent, ObservationEvent, PauseEvent
from openhands.sdk.llm import (
    LLM,
    ImageContent,
    Message,
    TextContent,
)
from openhands.sdk.security.confirmation_policy import AlwaysConfirm
from openhands.sdk.tool import (
    Action,
    Observation,
    Tool,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)


class PauseFunctionalityMockAction(Action):
    """模拟对象操作模式用于测试。"""

    command: str


class PauseFunctionalityMockObservation(Observation):
    """模拟对象观测结果模式用于测试。"""

    result: str

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text=self.result)]


class BlockingExecutor(
    ToolExecutor[PauseFunctionalityMockAction, PauseFunctionalityMockObservation]
):
    def __init__(self, step_entered: threading.Event):
        self.step_entered: threading.Event = step_entered

    def __call__(
        self,
        action: PauseFunctionalityMockAction,
        conversation: BaseConversation | None = None,
    ) -> PauseFunctionalityMockObservation:
        # 表明我们已进入此步骤的工具执行
        self.step_entered.set()
        return PauseFunctionalityMockObservation(result=f"Executed: {action.command}")


class TestExecutor(
    ToolExecutor[PauseFunctionalityMockAction, PauseFunctionalityMockObservation]
):
    """用于暂停功能测试的测试执行器。"""

    def __call__(
        self,
        action: PauseFunctionalityMockAction,
        conversation: BaseConversation | None = None,
    ) -> PauseFunctionalityMockObservation:
        return PauseFunctionalityMockObservation(result=f"Executed: {action.command}")


class PauseFunctionalityTestTool(
    ToolDefinition[PauseFunctionalityMockAction, PauseFunctionalityMockObservation]
):
    """用于暂停功能测试的具体工具。"""

    name: ClassVar[str] = "test_tool"

    @classmethod
    def create(
        cls, conv_state=None, **params
    ) -> Sequence["PauseFunctionalityTestTool"]:
        return [
            cls(
                description="A test tool",
                action_type=PauseFunctionalityMockAction,
                observation_type=PauseFunctionalityMockObservation,
                executor=TestExecutor(),
            )
        ]


class BlockingTestTool(
    ToolDefinition[PauseFunctionalityMockAction, PauseFunctionalityMockObservation]
):
    """用于阻止暂停测试的具体工具。"""

    name: ClassVar[str] = "test_tool"

    @classmethod
    def create(
        cls, conv_state=None, step_entered=None, **params
    ) -> Sequence["BlockingTestTool"]:
        if step_entered is None:
            raise ValueError("step_entered is required for BlockingTestTool")
        return [
            cls(
                description="Blocking tool for pause test",
                action_type=PauseFunctionalityMockAction,
                observation_type=PauseFunctionalityMockObservation,
                executor=BlockingExecutor(step_entered),
            )
        ]


class TestPauseFunctionality:
    """测试套件用于暂停功能。"""

    def setup_method(self):
        """设置测试测试夹具。"""

        self.llm: LLM = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )

        register_tool("test_tool", PauseFunctionalityTestTool)

        self.agent: Agent = Agent(
            llm=self.llm,
            tools=[Tool(name="test_tool")],
        )
        self.conversation: LocalConversation = Conversation(agent=self.agent)

    def test_pause_basic_functionality(self):
        """测试基本的暂停操作。"""
        # 测试初始状态
        assert (
            self.conversation.state.execution_status == ConversationExecutionStatus.IDLE
        )
        # 注意：使用延迟初始化，系统提示词事件在第一次使用之前不会添加

        # 测试暂停方法
        self.conversation.pause()
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.PAUSED
        )

        pause_events = [
            event
            for event in self.conversation.state.events
            if isinstance(event, PauseEvent)
        ]
        assert len(pause_events) == 1
        assert pause_events[0].source == "user"

    @patch("openhands.sdk.llm.llm.litellm_completion")
    def test_pause_during_normal_execution(self, mock_completion):
        """run() 开始之前测试暂停 - 暂停已重置且智能体正常运行。"""
        # 模拟对象LLM返回执行完成的消息
        mock_completion.return_value = ModelResponse(
            id="response_msg",
            choices=[
                Choices(
                    message=LiteLLMMessage(role="assistant", content="Task completed")
                )
            ],
            created=0,
            model="test-model",
            object="chat.completion",
        )

        # 发送消息并开始执行
        self.conversation.send_message(
            Message(role="user", content=[TextContent(text="Hello")])
        )

        # 立即暂停（运行开始前）
        self.conversation.pause()

        # 验证已设置暂停
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.PAUSED
        )

        # 运行在开始时重置暂停标志并正常进行
        self.conversation.run()

        # 智能体应该完成（暂停在运行开始时重置）
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.FINISHED
        )

        # 应该有来自 pause() 调用的暂停事件
        pause_events = [
            event
            for event in self.conversation.state.events
            if isinstance(event, PauseEvent)
        ]
        assert len(pause_events) == 1

    @patch("openhands.sdk.llm.llm.litellm_completion")
    def test_resume_paused_agent(self, mock_completion):
        """在 run() 之前测试暂停 - 暂停被重置并且智能体正常运行。"""
        # 模拟对象LLM返回执行完成的消息
        mock_completion.return_value = ModelResponse(
            id="response_msg",
            choices=[
                Choices(
                    message=LiteLLMMessage(role="assistant", content="Task completed")
                )
            ],
            created=0,
            model="test-model",
            object="chat.completion",
        )

        # 发送消息
        self.conversation.send_message(
            Message(role="user", content=[TextContent(text="Hello")])
        )

        # 跑步前暂停
        self.conversation.pause()
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.PAUSED
        )

        # 第一个 run() 调用重置暂停并正常运行
        self.conversation.run()

        # 智能体应该完成（暂停在运行开始时重置）
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.FINISHED
        )

        # 由于运行正常完成，应该有智能体消息
        agent_messages = [
            event
            for event in self.conversation.state.events
            if isinstance(event, MessageEvent) and event.source == "agent"
        ]
        assert len(agent_messages) == 1  # 智能体运行并完成

    @patch("openhands.sdk.llm.llm.litellm_completion")
    def test_pause_with_confirmation_mode(self, mock_completion):
        """使用确认模式测试 run() 之前的暂停 - 暂停已重置并且智能体等待确认。"""  # noqa: E501
        # 启用确认模式
        self.conversation.set_confirmation_policy(AlwaysConfirm())
        self.conversation.pause()
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.PAUSED
        )

        # 模拟对象行动
        tool_call = ChatCompletionMessageToolCall(
            id="call_1",
            type="function",
            function=Function(
                name="test_tool",
                arguments='{"command": "test_command"}',
            ),
        )
        mock_completion.return_value = ModelResponse(
            id="response_action",
            choices=[
                Choices(
                    message=LiteLLMMessage(
                        role="assistant",
                        content="",
                        tool_calls=[tool_call],
                    )
                )
            ],
            created=0,
            model="test-model",
            object="chat.completion",
        )

        # 发送消息
        self.conversation.send_message(
            Message(role="user", content=[TextContent(text="Execute command")])
        )

        # 运行重置暂停并继续创建操作，然后等待确认
        self.conversation.run()

        # 应重置暂停，智能体应等待确认
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
        )

        # 操作未执行（不应记录 ObservationEvent）

        observations = [
            event
            for event in self.conversation.state.events
            if isinstance(event, ObservationEvent)
        ]
        assert len(observations) == 0

        # 但应该至少有一个 ActionEvent 待确认
        action_events = [
            event
            for event in self.conversation.state.events
            if isinstance(event, ActionEvent)
        ]
        assert len(action_events) >= 1

    def test_multiple_pause_calls_create_one_event(self):
        """测试多个连续的暂停调用仅创建一个 PauseEvent。"""
        # 连续多次调用暂停
        self.conversation.pause()
        self.conversation.pause()
        self.conversation.pause()

        # 应该只有一个个暂停事件（要求 #1）
        pause_events = [
            event
            for event in self.conversation.state.events
            if isinstance(event, PauseEvent)
        ]
        assert len(pause_events) == 1, (
            f"Expected 1 PauseEvent, got {len(pause_events)}. "
            "Multiple successive pause calls should only create one PauseEvent."
        )

        # 状态应该暂停
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.PAUSED
        )

    @pytest.mark.timeout(3)
    @patch("openhands.sdk.llm.llm.litellm_completion")
    def test_pause_while_running_continuous_actions(self, mock_completion):
        step_entered = threading.Event()

        blocking_tool = BlockingTestTool.create(step_entered=step_entered)[0]
        register_tool("test_tool", blocking_tool)
        agent = Agent(
            llm=self.llm,
            tools=[Tool(name="test_tool")],
        )
        conversation = Conversation(agent=agent, stuck_detection=False)

        # 仅在本次测试中更换它们
        self.agent = agent
        self.conversation = conversation

        # LLM 连续发出动作（没有完成）
        tool_call = ChatCompletionMessageToolCall(
            id="call_loop",
            type="function",
            function=Function(
                name="test_tool",
                arguments='{"command": "loop_forever"}',
            ),
        )
        import time

        def side_effect(*_args, **_kwargs):
            return ModelResponse(
                id="response_action_loop",
                choices=[
                    Choices(
                        message=LiteLLMMessage(
                            role="assistant",
                            content="I'll execute loop_forever",
                            tool_calls=[tool_call],
                        )
                    )
                ],
                created=int(time.time()),
                model="test-model",
                object="chat.completion",
            )

        mock_completion.side_effect = side_effect

        # 播种用户消息
        self.conversation.send_message(
            Message(
                role="user", content=[TextContent(text="Loop actions until paused")]
            )
        )

        run_exc: list[Exception | None] = [None]
        finished = threading.Event()

        def run_agent():
            try:
                self.conversation.run()
            except Exception as e:
                run_exc[0] = e
            finally:
                finished.set()

        t = threading.Thread(target=run_agent, daemon=True)
        t.start()

        # 等到我们在当前迭代的 *inside* 工具执行中
        assert step_entered.wait(timeout=3.0), "Agent never reached tool execution"
        self.conversation.pause()
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.PAUSED
        )

        assert finished.wait(timeout=3.0), "run() did not exit after pause"
        t.join(timeout=0.1)
        assert run_exc[0] is None, f"Run thread failed with: {run_exc[0]}"

        # 已暂停，未完成，正好一个 PauseEvent
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.PAUSED
        )
        pause_events = [
            e for e in self.conversation.state.events if isinstance(e, PauseEvent)
        ]
        assert len(pause_events) == 1, f"Expected 1 PauseEvent, got {len(pause_events)}"
