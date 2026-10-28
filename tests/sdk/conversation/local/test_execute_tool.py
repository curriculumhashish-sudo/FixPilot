"""测试 conversation.execute_tool() 功能。"""

import pytest
from pydantic import SecretStr

from openhands.sdk.agent.base import AgentBase
from openhands.sdk.conversation import Conversation, LocalConversation
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.conversation.types import (
    ConversationCallbackType,
    ConversationTokenCallbackType,
)
from openhands.sdk.event.llm_convertible import MessageEvent, SystemPromptEvent
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.tool import (
    Action,
    Observation,
    Tool,
    ToolDefinition,
    ToolExecutor,
    register_tool as register_tool_public,
    registry as tool_registry,
)


# 定义一个简单的测试操作和观测结果
class ExecuteToolTestAction(Action):
    """execute_tool 测试的测试操作。"""

    value: str = "test"


class ExecuteToolTestObservation(Observation):
    """测试观测结果进行 execute_tool 次测试。"""

    result: str = ""


# 定义一个简单的测试工具执行器
class ExecuteToolTestExecutor(
    ToolExecutor[ExecuteToolTestAction, ExecuteToolTestObservation]
):
    """返回简单观测结果的测试执行器。"""

    def __init__(self, prefix: str = "executed"):
        self.prefix = prefix
        self.call_count = 0

    def __call__(
        self,
        action: ExecuteToolTestAction,
        conversation: "LocalConversation | None" = None,
    ) -> ExecuteToolTestObservation:
        self.call_count += 1
        return ExecuteToolTestObservation.from_text(
            f"{self.prefix}: {action.value}", result=f"{self.prefix}_{action.value}"
        )


# 定义一个简单的测试工具
class ExecuteToolTestTool(
    ToolDefinition[ExecuteToolTestAction, ExecuteToolTestObservation]
):
    """用于 execute_tool 测试的测试工具。"""

    @classmethod
    def create(cls, conv_state=None, **params):
        executor = ExecuteToolTestExecutor(prefix=params.get("prefix", "executed"))
        return [
            cls(
                description="A test tool for testing execute_tool",
                action_type=ExecuteToolTestAction,
                observation_type=ExecuteToolTestObservation,
                executor=executor,
            )
        ]


@pytest.fixture(autouse=True)
def _tool_registry_snapshot():
    registry_snapshot = dict(tool_registry._REG)
    tool_class_snapshot = dict(tool_registry._TOOL_CLASSES)
    register_tool_public(ExecuteToolTestTool.name, ExecuteToolTestTool)
    try:
        yield
    finally:
        tool_registry._REG.clear()
        tool_registry._REG.update(registry_snapshot)
        tool_registry._TOOL_CLASSES.clear()
        tool_registry._TOOL_CLASSES.update(tool_class_snapshot)


class ExecuteToolDummyAgent(AgentBase):
    """用于测试 execute_tool 的虚拟智能体。"""

    def __init__(self, tools=None):
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        super().__init__(llm=llm, tools=tools or [])

    def init_state(
        self, state: ConversationState, on_event: ConversationCallbackType
    ) -> None:
        # 调用父级 init_state 来正确初始化工具
        super().init_state(state, on_event)
        # 然后发出系统提示词事件
        event = SystemPromptEvent(
            source="agent", system_prompt=TextContent(text="dummy"), tools=[]
        )
        on_event(event)

    def step(
        self,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
        on_token: ConversationTokenCallbackType | None = None,
    ) -> None:
        on_event(
            MessageEvent(
                source="agent",
                llm_message=Message(role="assistant", content=[TextContent(text="ok")]),
            )
        )


def test_execute_tool_basic():
    """测试基本 execute_tool 功能。"""
    agent = ExecuteToolDummyAgent(
        tools=[Tool(name="execute_tool_test", params={"prefix": "hello"})]
    )
    conversation = Conversation(agent=agent)

    # 在 run() 之前执行该工具
    action = ExecuteToolTestAction(value="world")
    result = conversation.execute_tool("execute_tool_test", action)

    # 验证结果
    assert isinstance(result, ExecuteToolTestObservation)
    assert result.result == "hello_world"
    assert "hello: world" in result.text


def test_execute_tool_initializes_agent():
    """如果尚未初始化，则测试 execute_tool 是否初始化智能体。"""
    agent = ExecuteToolDummyAgent(tools=[Tool(name="execute_tool_test", params={})])
    conversation = Conversation(agent=agent)

    # 智能体尚未初始化
    assert not conversation._agent_ready

    # 执行工具
    action = ExecuteToolTestAction(value="test")
    conversation.execute_tool("execute_tool_test", action)

    # 智能体现在应该被初始化
    assert conversation._agent_ready


def test_execute_tool_before_send_message():
    """在调用 send_message 之前测试 execute_tool 是否有效。"""
    agent = ExecuteToolDummyAgent(tools=[Tool(name="execute_tool_test", params={})])
    conversation = Conversation(agent=agent)

    # 在任何消息之前执行工具
    action = ExecuteToolTestAction(value="pre-message")
    result = conversation.execute_tool("execute_tool_test", action)

    assert isinstance(result, ExecuteToolTestObservation)
    assert result.result == "executed_pre-message"

    # 现在发送消息 - 应该仍然有效
    conversation.send_message("Hello")
    assert len(conversation.state.events) >= 2  # 系统提示词+用户消息


def test_execute_tool_after_send_message():
    """测试 execute_tool 是否在调用 send_message 后起作用。"""
    agent = ExecuteToolDummyAgent(tools=[Tool(name="execute_tool_test", params={})])
    conversation = Conversation(agent=agent)

    # 先发消息
    conversation.send_message("Hello")

    # 消息后执行工具
    action = ExecuteToolTestAction(value="post-message")
    result = conversation.execute_tool("execute_tool_test", action)

    assert isinstance(result, ExecuteToolTestObservation)
    assert result.result == "executed_post-message"


def test_execute_tool_not_found():
    """测试 execute_tool 是否会因不存在的工具而引发 KeyError。"""
    agent = ExecuteToolDummyAgent(tools=[Tool(name="execute_tool_test", params={})])
    conversation = Conversation(agent=agent)

    action = ExecuteToolTestAction(value="test")

    with pytest.raises(KeyError) as exc_info:
        conversation.execute_tool("nonexistent_tool", action)

    assert "nonexistent_tool" in str(exc_info.value)
    assert "not found" in str(exc_info.value)


def test_execute_tool_multiple_calls():
    """测试execute_tool可以被多次调用。"""
    agent = ExecuteToolDummyAgent(tools=[Tool(name="execute_tool_test", params={})])
    conversation = Conversation(agent=agent)

    # 执行多次
    for i in range(3):
        action = ExecuteToolTestAction(value=f"call_{i}")
        result = conversation.execute_tool("execute_tool_test", action)
        assert isinstance(result, ExecuteToolTestObservation)
        assert result.result == f"executed_call_{i}"


def test_execute_tool_with_conversation_context():
    """测试 execute_tool 将对话上下文传递给执行者。"""

    class ContextAwareExecutor(
        ToolExecutor[ExecuteToolTestAction, ExecuteToolTestObservation]
    ):
        """使用对话上下文的执行器。"""

        def __call__(
            self,
            action: ExecuteToolTestAction,
            conversation: "LocalConversation | None" = None,
        ) -> ExecuteToolTestObservation:
            # 验证对话是否通过
            conv_id = str(conversation.id) if conversation else "no_conversation"
            return ExecuteToolTestObservation.from_text(
                f"conv_id: {conv_id}", result=f"context_{action.value}"
            )

    class ContextAwareTool(
        ToolDefinition[ExecuteToolTestAction, ExecuteToolTestObservation]
    ):
        @classmethod
        def create(cls, conv_state=None, **params):
            return [
                cls(
                    description="Context-aware test tool",
                    action_type=ExecuteToolTestAction,
                    observation_type=ExecuteToolTestObservation,
                    executor=ContextAwareExecutor(),
                )
            ]

    register_tool_public("context_aware", ContextAwareTool)

    agent = ExecuteToolDummyAgent(tools=[Tool(name="context_aware", params={})])
    conversation = Conversation(agent=agent)

    action = ExecuteToolTestAction(value="test")
    result = conversation.execute_tool("context_aware", action)

    # 验证对话已通过（结果应包含对话 ID）
    assert "conv_id:" in result.text
    assert isinstance(result, ExecuteToolTestObservation)
    assert result.result == "context_test"
