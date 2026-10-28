"""
单元测试用于确认模式功能。

测试核心行为：暂停操作执行以供用户确认。
"""

from collections.abc import Sequence
from typing import ClassVar
from unittest.mock import MagicMock, Mock, patch

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
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.event import ActionEvent, MessageEvent, ObservationEvent
from openhands.sdk.event.base import Event
from openhands.sdk.event.llm_convertible import UserRejectObservation
from openhands.sdk.llm import (
    LLM,
    ImageContent,
    Message,
    MessageToolCall,
    MetricsSnapshot,
    TextContent,
)
from openhands.sdk.llm.utils.metrics import TokenUsage
from openhands.sdk.security.confirmation_policy import AlwaysConfirm, NeverConfirm
from openhands.sdk.tool import (
    Tool,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)
from openhands.sdk.tool.schema import Action, Observation


class MockConfirmationModeAction(Action):
    """模拟对象操作模式用于测试。"""

    command: str


class MockConfirmationModeObservation(Observation):
    """模拟对象观测结果模式用于测试。"""

    result: str

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text=self.result)]


class TestExecutor(
    ToolExecutor[MockConfirmationModeAction, MockConfirmationModeObservation]
):
    """用于确认模式测试的测试执行器。"""

    def __call__(
        self,
        action: MockConfirmationModeAction,
        conversation=None,  # noqa: ARG002
    ) -> MockConfirmationModeObservation:
        return MockConfirmationModeObservation(result=f"Executed: {action.command}")


class ConfirmationTestTool(
    ToolDefinition[MockConfirmationModeAction, MockConfirmationModeObservation]
):
    """用于确认模式测试的具体工具。"""

    name: ClassVar[str] = "test_tool"

    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["ConfirmationTestTool"]:
        return [
            cls(
                description="A test tool",
                action_type=MockConfirmationModeAction,
                observation_type=MockConfirmationModeObservation,
                executor=TestExecutor(),
            )
        ]


class TestConfirmationMode:
    """测试套件用于确认模式功能。"""

    def setup_method(self):
        """设置测试测试夹具。"""

        # 为智能体验证创建一个真实的 LLM 实例
        self.llm: LLM = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )

        # 创建一个MagicMock来覆盖完成方法
        self.mock_llm: Mock = MagicMock()

        # 为 LLM 创建适当的 MetricsSnapshot 模拟对象
        mock_token_usage = TokenUsage(
            model="test-model",
            prompt_tokens=100,
            completion_tokens=50,
            cache_read_tokens=0,
            cache_write_tokens=0,
            context_window=4096,
            per_turn_token=150,
            response_id="test-response-id",
        )
        mock_metrics_snapshot = MetricsSnapshot(
            model_name="test-model",
            accumulated_cost=0.00075,
            max_budget_per_task=None,
            accumulated_token_usage=mock_token_usage,
        )
        self.mock_llm.metrics.get_snapshot.return_value = mock_metrics_snapshot

        register_tool("test_tool", ConfirmationTestTool)

        self.agent: Agent = Agent(
            llm=self.llm,
            tools=[Tool(name="test_tool")],
        )
        self.conversation: LocalConversation = Conversation(agent=self.agent)

    def _mock_message_only(self, text: str = "Hello, how can I help you?") -> MagicMock:
        """配置 LLM 以返回普通助理消息（无工具调用）。"""
        return MagicMock(
            return_value=ModelResponse(
                id="response_msg",
                choices=[
                    Choices(message=LiteLLMMessage(role="assistant", content=text))
                ],
                created=0,
                model="test-model",
                object="chat.completion",
            )
        )

    def _make_pending_action(self) -> None:
        """启用确认模式并生成单个待处理操作。"""
        self.conversation.set_confirmation_policy(AlwaysConfirm())
        mock_completion = self._mock_action_once()
        with patch(
            "openhands.sdk.llm.llm.litellm_completion",
            return_value=mock_completion.return_value,
        ):
            self.conversation.send_message(
                Message(role="user", content=[TextContent(text="execute a command")])
            )
            self.conversation.run()
        assert self.conversation.state.confirmation_policy == AlwaysConfirm()
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
        )

    def _mock_action_once(
        self, call_id: str = "call_1", command: str = "test_command"
    ) -> MagicMock:
        """配置 LLM 返回一工具调用（操作）。"""
        litellm_tool_call = ChatCompletionMessageToolCall(
            id=call_id,
            type="function",
            function=Function(
                name="test_tool",
                arguments=f'{{"command": "{command}"}}',
            ),
        )
        return MagicMock(
            return_value=ModelResponse(
                id="response_action",
                choices=[
                    Choices(
                        message=LiteLLMMessage(
                            role="assistant",
                            content=f"I'll execute {command}",
                            tool_calls=[litellm_tool_call],
                        )
                    )
                ],
                created=0,
                model="test-model",
                object="chat.completion",
            )
        )

    def _mock_finish_action(self, message: str = "Task completed") -> MagicMock:
        """配置 LLM 返回 FinishAction 工具调用。"""
        tool_call = ChatCompletionMessageToolCall(
            id="finish_call_1",
            type="function",
            function=Function(
                name="finish",
                arguments=f'{{"message": "{message}"}}',
            ),
        )

        return MagicMock(
            return_value=ModelResponse(
                id="response_finish",
                choices=[
                    Choices(
                        message=LiteLLMMessage(
                            role="assistant",
                            content=f"I'll finish with: {message}",
                            tool_calls=[tool_call],
                        )
                    )
                ],
                created=0,
                model="test-model",
                object="chat.completion",
            )
        )

    def _mock_think_action(self, thought: str = "Let me think about this") -> MagicMock:
        """配置 LLM 返回 ThinkAction 工具调用。"""
        tool_call = ChatCompletionMessageToolCall(
            id="think_call_1",
            type="function",
            function=Function(
                name="think",
                arguments=f'{{"thought": "{thought}"}}',
            ),
        )

        return MagicMock(
            return_value=ModelResponse(
                id="response_think",
                choices=[
                    Choices(
                        message=LiteLLMMessage(
                            role="assistant",
                            content=f"I'll think: {thought}",
                            tool_calls=[tool_call],
                        )
                    )
                ],
                created=0,
                model="test-model",
                object="chat.completion",
            )
        )

    def _mock_multiple_actions_with_finish(self) -> MagicMock:
        """配置 LLM 以返回常规操作和 FinishAction。"""
        regular_tool_call = ChatCompletionMessageToolCall(
            id="call_1",
            type="function",
            function=Function(
                name="test_tool",
                arguments='{"command": "test_command"}',
            ),
        )

        finish_tool_call = ChatCompletionMessageToolCall(
            id="finish_call_1",
            type="function",
            function=Function(
                name="finish",
                arguments='{"message": "Task completed!"}',
            ),
        )

        return MagicMock(
            return_value=ModelResponse(
                id="response_multiple",
                choices=[
                    Choices(
                        message=LiteLLMMessage(
                            role="assistant",
                            content="I'll execute the command and then finish",
                            tool_calls=[
                                regular_tool_call,
                                finish_tool_call,
                            ],
                        )
                    )
                ],
                created=0,
                model="test-model",
                object="chat.completion",
            )
        )

    def _create_test_action(self, call_id="call_1", command="test_command"):
        """创建测试操作事件的帮助程序。"""
        action = MockConfirmationModeAction(command=command)

        litellm_tool_call = ChatCompletionMessageToolCall(
            id=call_id,
            type="function",
            function=Function(
                name="test_tool",
                arguments=f'{{"command": "{command}"}}',
            ),
        )

        # 将 ActionEvent 转换为 MessageToolCall
        tool_call = MessageToolCall.from_chat_tool_call(litellm_tool_call)

        action_event = ActionEvent(
            source="agent",
            thought=[TextContent(text="Test thought")],
            action=action,
            tool_name="test_tool",
            tool_call_id=call_id,
            tool_call=tool_call,
            llm_response_id="response_1",
        )

        return action_event

    def test_mock_observation(self):
        # 首先测试观测结果的上下文中的往返
        obs = MockConfirmationModeObservation(result="executed")

        # 现在测试将其嵌入到 ObservationEvent 中
        event = ObservationEvent(
            observation=obs,
            action_id="action_id",
            tool_name="hammer",
            tool_call_id="tool_call_id",
        )
        dumped_event = event.model_dump()
        assert dumped_event["observation"]["kind"] == "MockConfirmationModeObservation"
        assert dumped_event["observation"]["result"] == "executed"
        loaded_event = event.model_validate(dumped_event)
        loaded_obs = loaded_event.observation
        assert isinstance(loaded_obs, MockConfirmationModeObservation)
        assert loaded_obs.result == "executed"

    def test_confirmation_mode_basic_functionality(self):
        """测试基本确认模式操作。"""
        # 测试初始状态
        assert self.conversation.state.confirmation_policy == NeverConfirm()
        assert (
            self.conversation.state.execution_status == ConversationExecutionStatus.IDLE
        )
        assert (
            ConversationState.get_unmatched_actions(self.conversation.state.events)
            == []
        )

        # 启用确认模式
        self.conversation.set_confirmation_policy(AlwaysConfirm())
        assert self.conversation.state.confirmation_policy == AlwaysConfirm()

        # 禁用确认模式
        self.conversation.set_confirmation_policy(NeverConfirm())
        assert self.conversation.state.confirmation_policy == NeverConfirm()

        # 当不存在任何操作时测试拒绝不会引发错误
        self.conversation.reject_pending_actions("Nothing to reject")
        rejection_events = [
            event
            for event in self.conversation.state.events
            if isinstance(event, UserRejectObservation)
        ]
        assert len(rejection_events) == 0

    def test_getting_unmatched_events(self):
        """测试获取不匹配的事件（不带观测结果的操作）。"""
        # 创建测试动作
        action_event = self._create_test_action()
        events: list[Event] = [action_event]

        # 测试：不带观测结果的操作应待处理
        unmatched = ConversationState.get_unmatched_actions(events)
        assert len(unmatched) == 1
        assert unmatched[0].id == action_event.id

        # 为操作添加观测结果
        obs = MockConfirmationModeObservation(result="test result")

        obs_event = ObservationEvent(
            source="environment",
            observation=obs,
            action_id=action_event.id,
            tool_name="test_tool",
            tool_call_id="call_1",
        )
        events.append(obs_event)

        # 测试： 观测结果的操作不应处于待处理状态
        unmatched = ConversationState.get_unmatched_actions(events)
        assert len(unmatched) == 0

        # 测试拒绝功能
        action_event2 = self._create_test_action("call_2", "test_command_2")
        events.append(action_event2)

        # 添加第二个操作的拒绝
        rejection = UserRejectObservation(
            action_id=action_event2.id,
            tool_name="test_tool",
            tool_call_id="call_2",
            rejection_reason="Test rejection",
        )
        events.append(rejection)

        # 测试：被拒绝的操作不应处于待处理状态
        unmatched = ConversationState.get_unmatched_actions(events)
        assert len(unmatched) == 0

        # 测试 UserRejectObservation 功能
        llm_message = rejection.to_llm_message()
        assert llm_message.role == "tool"
        assert llm_message.name == "test_tool"
        assert llm_message.tool_call_id == "call_2"
        assert isinstance(llm_message.content[0], TextContent)
        assert "Action rejected: Test rejection" in llm_message.content[0].text

    def test_message_only_in_confirmation_mode_does_not_wait(self):
        """不确认智能体消息。"""
        self.conversation.set_confirmation_policy(AlwaysConfirm())
        mock_completion = self._mock_message_only("Hello, how can I help you?")
        with patch(
            "openhands.sdk.llm.llm.litellm_completion",
            return_value=mock_completion.return_value,
        ):
            self.conversation.send_message(
                Message(role="user", content=[TextContent(text="some prompt")])
            )
            self.conversation.run()

        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.FINISHED
        )

        msg_events = [
            e
            for e in self.conversation.state.events
            if isinstance(e, MessageEvent) and e.source == "agent"
        ]
        assert len(msg_events) == 1
        assert isinstance(msg_events[0].llm_message.content[0], TextContent)
        assert msg_events[0].llm_message.content[0].text == "Hello, how can I help you?"

    @pytest.mark.parametrize("should_reject", [True, False])
    def test_action_then_confirm_or_reject(self, should_reject: bool):
        """
        以确认模式启动，获取待处理操作，然后：
        - 如果 should_reject 是 False：通过调用 conversation.run() 确认
        - 如果 should_reject 是 True：通过 conversation.reject_pending_action 拒绝
        """
        # 创建单个待处理操作
        self._make_pending_action()

        if not should_reject:
            # 根据您的指令确认路径：调用 run() 执行待处理的操作
            mock_completion = self._mock_message_only("Task completed successfully!")
            with patch(
                "openhands.sdk.llm.llm.litellm_completion",
                return_value=mock_completion.return_value,
            ):
                self.conversation.run()

            # 预计出现观测结果（工具已执行）并且不会被拒绝
            obs_events = [
                e
                for e in self.conversation.state.events
                if isinstance(e, ObservationEvent)
            ]
            assert len(obs_events) == 1
            assert obs_events[0].observation.result == "Executed: test_command"  # type: ignore[attr-defined]
            rejection_events = [
                e
                for e in self.conversation.state.events
                if isinstance(e, UserRejectObservation)
            ]
            assert len(rejection_events) == 0
            assert (
                self.conversation.state.execution_status
                == ConversationExecutionStatus.FINISHED
            )
        else:
            self.conversation.reject_pending_actions("Not safe to run")

            # 预计会发生拒绝事件，但不会观测结果
            rejection_events = [
                e
                for e in self.conversation.state.events
                if isinstance(e, UserRejectObservation)
            ]
            assert len(rejection_events) == 1
            obs_events = [
                e
                for e in self.conversation.state.events
                if isinstance(e, ObservationEvent)
            ]
            assert len(obs_events) == 0

    def test_single_finish_action_skips_confirmation_entirely(self):
        """测试单个 FinishAction 完全跳过确认。"""
        # 启用确认模式
        self.conversation.set_confirmation_policy(AlwaysConfirm())

        # 模拟对象 LLM 返回单个 FinishAction
        mock_completion = self._mock_finish_action("Task completed successfully!")

        # 发送一条应触发完成操作的消息
        with patch(
            "openhands.sdk.llm.llm.litellm_completion",
            return_value=mock_completion.return_value,
        ):
            self.conversation.send_message(
                Message(
                    role="user", content=[TextContent(text="Please finish the task")]
                )
            )

            # 运行对话
            self.conversation.run()

        # 单个 FinishAction 应完全跳过确认
        assert (
            self.conversation.state.confirmation_policy == AlwaysConfirm()
        )  # 仍处于确认模式
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.FINISHED
        )  # 智能体应该完成

        # 不应有待处理的操作（FinishAction 已立即执行）
        pending_actions = ConversationState.get_unmatched_actions(
            self.conversation.state.events
        )
        assert len(pending_actions) == 0

        # 应该有一个观测结果事件（操作已执行）
        obs_events = [
            e for e in self.conversation.state.events if isinstance(e, ObservationEvent)
        ]
        assert len(obs_events) == 1
        # FinishObservation 内容中应包含结束消息
        assert obs_events[0].observation.text == "Task completed successfully!"

    def test_think_and_finish_action_skips_confirmation_entirely(self):
        """第一步：ThinkAction（跳过确认）。 第二步：FinishAction。"""
        # 启用确认模式
        self.conversation.set_confirmation_policy(AlwaysConfirm())

        # 第一个模型调用 -> ThinkAction;第二次模型调用 -> FinishAction
        mock_think = self._mock_think_action("Let me analyze this problem")
        mock_finish = self._mock_finish_action("Analysis complete")

        with patch(
            "openhands.sdk.llm.llm.litellm_completion",
            side_effect=[mock_think.return_value, mock_finish.return_value],
        ):
            # 开始吧（LLM 返回 ThinkAction； 应立即执行）
            self.conversation.send_message(
                Message(
                    role="user", content=[TextContent(text="Please think about this")]
                )
            )
            self.conversation.run()

        # 总体仍处于确认模式，但两个操作都应该已执行
        assert self.conversation.state.confirmation_policy == AlwaysConfirm()
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.FINISHED
        )

        # 没有在进行中的操作
        pending_actions = ConversationState.get_unmatched_actions(
            self.conversation.state.events
        )
        assert len(pending_actions) == 0

        # 我们应该有两个观测结果：一个用于 ThinkAction，一个用于 FinishAction
        obs_events = [
            e for e in self.conversation.state.events if isinstance(e, ObservationEvent)
        ]
        assert len(obs_events) == 2

        # 1) ThinkAction 观测结果 - 应包含标准消息
        assert hasattr(obs_events[0].observation, "content")
        assert obs_events[0].observation.text == "Your thought has been logged."

        # 2) FinishAction 观测结果 - 应包含完成消息
        assert hasattr(obs_events[1].observation, "content")
        assert obs_events[1].observation.text == "Analysis complete"

    def test_pause_during_confirmation_preserves_waiting_status(self):
        """测试 WAITING_FOR_CONFIRMATION 期间暂停是否保留状态。

        此测试重现了竞态条件问题，其中智能体可以等待确认，并且状态改为已暂停。 等待确
        认只是一种特殊类型的暂停，不应被覆盖。
        """
        # 创建一个待处理操作，将智能体置于 WAITING_FOR_CONFIRMATION 状态
        self._make_pending_action()

        # 验证我们处于预期状态
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
        )
        assert self.conversation.state.confirmation_policy == AlwaysConfirm()

        # 处于 WAITING_FOR_CONFIRMATION 状态时调用 pause()
        self.conversation.pause()

        # 状态应保持 WAITING_FOR_CONFIRMATION，而不是更改为 PAUSED 这是关键修复：等待确
        # 认是一种特殊类型的暂停
        #
        assert (
            self.conversation.state.execution_status
            == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
        )

        # 测试暂停对于其他状态是否正常工作重置为 IDLE 状态
        #
        with self.conversation._state:
            self.conversation._state.execution_status = ConversationExecutionStatus.IDLE

        # 从 IDLE 暂停应将状态更改为 PAUSED
        self.conversation.pause()
        assert (
            self.conversation._state.execution_status
            == ConversationExecutionStatus.PAUSED
        )

        # 重置为RUNNING状态
        with self.conversation._state:
            self.conversation._state.execution_status = (
                ConversationExecutionStatus.RUNNING
            )

        # 从 RUNNING 暂停应将状态更改为 PAUSED
        self.conversation.pause()
        assert (
            self.conversation._state.execution_status
            == ConversationExecutionStatus.PAUSED
        )

    def test_is_confirmation_mode_active_property(self):
        """测试 is_confirmation_mode_active 属性行为。"""
        # 最初，没有安全分析器和 NeverConfirm 策略
        assert self.conversation.state.security_analyzer is None
        assert self.conversation.state.confirmation_policy == NeverConfirm()
        assert not self.conversation.confirmation_policy_active
        assert not self.conversation.is_confirmation_mode_active

        # 将确认策略设置为AlwaysConfirm，但仍然没有安全分析器
        self.conversation.set_confirmation_policy(AlwaysConfirm())
        assert self.conversation.state.security_analyzer is None
        assert self.conversation.state.confirmation_policy == AlwaysConfirm()
        assert self.conversation.confirmation_policy_active
        # 仍然是 False，因为没有安全分析器
        assert not self.conversation.is_confirmation_mode_active

        # 创建智能体并在对话状态上设置安全分析器
        from openhands.sdk.security.llm_analyzer import LLMSecurityAnalyzer

        agent = Agent(
            llm=self.llm,
            tools=[Tool(name="test_tool")],
        )
        conversation_with_analyzer = Conversation(agent=agent)
        conversation_with_analyzer.set_security_analyzer(LLMSecurityAnalyzer())

        # 最初使用安全分析器，但 NeverConfirm 策略
        assert conversation_with_analyzer.state.security_analyzer is not None
        assert conversation_with_analyzer.state.confirmation_policy == NeverConfirm()
        assert not conversation_with_analyzer.confirmation_policy_active
        # False 因为政策是 NeverConfirm
        assert not conversation_with_analyzer.is_confirmation_mode_active

        # 使用安全分析器将确认策略设置为 AlwaysConfirm
        conversation_with_analyzer.set_confirmation_policy(AlwaysConfirm())
        assert conversation_with_analyzer.state.security_analyzer is not None
        assert conversation_with_analyzer.state.confirmation_policy == AlwaysConfirm()
        assert conversation_with_analyzer.confirmation_policy_active
        # True 因为两个条件都满足
        assert conversation_with_analyzer.is_confirmation_mode_active
