"""测试智能体加载（对话重新启动）行为。"""

import sys
import tempfile
import uuid
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from openhands.sdk import Agent
from openhands.sdk.context import AgentContext, Skill
from openhands.sdk.context.condenser.llm_summarizing_condenser import (
    LLMSummarizingCondenser,
)
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.tool import Tool, register_tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.preset.default import get_default_agent
from openhands.tools.terminal import TerminalTool


pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="TerminalTool restore tests require the Unix terminal backend.",
)


register_tool("TerminalTool", TerminalTool)
register_tool("FileEditorTool", FileEditorTool)


class ModuleScopeOtherAgent(Agent):
    pass


# 测试来自 test_llm_reconciliation.py
def test_conversation_restart_with_nested_llms(tmp_path):
    """智能体包含嵌套的LLMs 的测试对话重置。"""
    # 使用虚拟 LLM + 模型 + 键创建默认智能体

    working_dir = str(tmp_path)

    llm = LLM(
        model="gpt-4o-mini", api_key=SecretStr("llm-api-key"), usage_id="main-llm"
    )

    # 使用标准智能体类来避免多态反序列化问题
    agent = get_default_agent(llm)

    conversation_id = uuid.uuid4()

    # 创建对话，默认智能体 + 持久化
    conversation1 = Conversation(
        agent=agent,
        persistence_dir=working_dir,
        conversation_id=conversation_id,
    )

    # 验证对话已成功创建
    assert conversation1.id == conversation_id
    assert conversation1.agent.llm.api_key is not None
    assert isinstance(conversation1.agent.llm.api_key, SecretStr)
    assert conversation1.agent.llm.api_key.get_secret_value() == "llm-api-key"
    assert isinstance(conversation1.agent.condenser, LLMSummarizingCondenser)
    assert conversation1.agent.condenser.llm.api_key is not None
    assert isinstance(conversation1.agent.condenser.llm.api_key, SecretStr)
    assert conversation1.agent.condenser.llm.api_key.get_secret_value() == "llm-api-key"

    # 尝试重新启动对话 - 这应该不会出现错误
    conversation2 = Conversation(
        agent=agent,
        persistence_dir=working_dir,
        conversation_id=conversation_id,  # 相同 conversation_id
    )

    # 确保对话正确初始化，没有错误
    assert conversation2.id == conversation_id
    assert conversation2.agent.llm.api_key is not None
    assert isinstance(conversation2.agent.llm.api_key, SecretStr)
    assert conversation2.agent.llm.api_key.get_secret_value() == "llm-api-key"
    assert isinstance(conversation2.agent.condenser, LLMSummarizingCondenser)
    assert conversation2.agent.condenser.llm.api_key is not None
    assert isinstance(conversation2.agent.condenser.llm.api_key, SecretStr)
    assert conversation2.agent.condenser.llm.api_key.get_secret_value() == "llm-api-key"

    # 验证智能体配置是否正确协调
    assert conversation2.agent.llm.model == "gpt-4o-mini"
    assert conversation2.agent.condenser.llm.model == "gpt-4o-mini"
    assert conversation2.agent.condenser.max_size == 80
    assert conversation2.agent.condenser.keep_first == 4


def test_conversation_restarted_with_changed_working_directory(tmp_path_factory):
    working_dir = str(tmp_path_factory.mktemp("persist"))

    llm = LLM(
        model="gpt-4o-mini", api_key=SecretStr("llm-api-key"), usage_id="main-llm"
    )

    agent1 = get_default_agent(llm)
    conversation_id = uuid.uuid4()

    # first conversation
    _ = Conversation(
        agent=agent1, persistence_dir=working_dir, conversation_id=conversation_id
    )

    # 智能体内置于 * 不同的 * 临时目录中
    agent2 = get_default_agent(llm)

    # 使用新的智能体工作目录重新启动，但对话 ID 相同
    _ = Conversation(
        agent=agent2, persistence_dir=working_dir, conversation_id=conversation_id
    )


# 测试智能体工具限制和 LLM 灵活性
def test_conversation_fails_when_removing_tools():
    """测试即使未使用工具，删除工具也会失败。

    工具是系统提示词的一部分，无法在对话中更改。 要使用不同的工具，请开始新对话或使用
    对话分叉。
    See: https://github.com/OpenHands/OpenHands/issues/8560
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 使用 2 个工具与原始智能体创建对话
        original_tools = [
            Tool(name="TerminalTool"),
            Tool(name="FileEditorTool"),
        ]
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        original_agent = Agent(llm=llm, tools=original_tools)
        conversation = LocalConversation(
            agent=original_agent,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            visualizer=None,
        )

        # 发送消息但未使用任何工具（历史上没有ActionEvent）
        conversation.send_message(
            Message(role="user", content=[TextContent(text="test message")])
        )

        conversation_id = conversation.state.id
        del conversation

        # 仅使用一种工具继续 - 应该 FAIL（工具必须完全匹配）
        reduced_tools = [Tool(name="TerminalTool")]  # 已删除 FileEditorTool
        llm2 = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        reduced_agent = Agent(llm=llm2, tools=reduced_tools)

        with pytest.raises(ValueError) as exc_info:
            LocalConversation(
                agent=reduced_agent,
                workspace=temp_dir,
                persistence_dir=temp_dir,
                conversation_id=conversation_id,
                visualizer=None,
            )

        assert "tools were removed mid-conversation" in str(exc_info.value)
        assert "removed:" in str(exc_info.value)
        assert "FileEditorTool" in str(exc_info.value)


def test_conversation_succeeds_when_adding_tools():
    """测试恢复时添加新工具是否成功。

    允许添加工具——只拒绝删除工具。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 仅使用一种工具即可创建对话
        original_tools = [Tool(name="TerminalTool")]
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        original_agent = Agent(llm=llm, tools=original_tools)
        conversation = LocalConversation(
            agent=original_agent,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            visualizer=None,
        )

        # 发送消息（不使用任何工具）
        conversation.send_message(
            Message(role="user", content=[TextContent(text="test message")])
        )

        conversation_id = conversation.state.id
        del conversation

        # 使用附加工具继续 - 应该 SUCCEED（允许添加工具）
        expanded_tools = [
            Tool(name="TerminalTool"),
            Tool(name="FileEditorTool"),  # 添加了新工具
        ]
        llm2 = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        expanded_agent = Agent(llm=llm2, tools=expanded_tools)

        conversation = LocalConversation(
            agent=expanded_agent,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            conversation_id=conversation_id,
            visualizer=None,
        )
        assert conversation is not None


def test_conversation_fails_when_used_tool_is_missing():
    """测试删除历史记录中使用过的 WAS 工具是否失败。

    无论是否使用工具，都不能在对话中更改。 此测试验证移除使用过的工具时的行为。
    """
    from openhands.sdk.event import ActionEvent

    with tempfile.TemporaryDirectory() as temp_dir:
        # 使用两个工具创建对话
        original_tools = [
            Tool(name="TerminalTool"),
            Tool(name="FileEditorTool"),
        ]
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        original_agent = Agent(llm=llm, tools=original_tools)
        conversation = LocalConversation(
            agent=original_agent,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            visualizer=None,
        )

        # 初始化智能体以获取实际的工具定义
        conversation.agent.init_state(conversation.state, lambda e: None)

        # 通过添加 ActionEvent 来模拟使用 TerminalTool
        from openhands.sdk.llm import MessageToolCall, TextContent

        action_event = ActionEvent(
            tool_name="TerminalTool",
            tool_call_id="test-call-1",
            thought=[TextContent(text="Running a command")],
            tool_call=MessageToolCall(
                id="test-call-1",
                name="TerminalTool",
                arguments="{}",
                origin="completion",
            ),
            llm_response_id="test-response-1",
        )
        conversation.state.events.append(action_event)

        conversation_id = conversation.state.id
        del conversation

        # 尝试恢复 WITHOUT TerminalTool - 应该会失败
        reduced_tools = [Tool(name="FileEditorTool")]  # 失踪TerminalTool
        llm2 = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        reduced_agent = Agent(llm=llm2, tools=reduced_tools)

        # 这应该会引发 - 工具在对话中被删除
        with pytest.raises(ValueError, match="tools were removed mid-conversation"):
            LocalConversation(
                agent=reduced_agent,
                workspace=temp_dir,
                persistence_dir=temp_dir,
                conversation_id=conversation_id,
                visualizer=None,
            )


def test_conversation_with_same_agent_succeeds():
    """测试使用相同的智能体配置是否成功。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建并保存对话
        tools = [
            Tool(name="TerminalTool"),
            Tool(name="FileEditorTool"),
        ]
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        original_agent = Agent(llm=llm, tools=tools)
        conversation = LocalConversation(
            agent=original_agent,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            visualizer=None,
        )

        # 发送消息
        conversation.send_message(
            Message(role="user", content=[TextContent(text="test message")])
        )

        # 获取对话 ID 以供重复使用
        conversation_id = conversation.state.id

        # 删除对话
        del conversation

        # 使用相同的智能体配置创建新对话
        same_tools = [
            Tool(name="TerminalTool"),
            Tool(name="FileEditorTool"),
        ]
        llm2 = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        same_agent = Agent(llm=llm2, tools=same_tools)

        # 这应该会成功
        new_conversation = LocalConversation(
            agent=same_agent,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            conversation_id=conversation_id,  # 使用相同的ID
            visualizer=None,
        )

        # 验证状态已加载
        assert len(new_conversation.state.events) > 0


def test_conversation_with_different_llm_succeeds():
    """测试使用具有不同 LLM 的智能体是否成功（LLM 可以更改）。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建并保存与原始对话智能体
        tools = [Tool(name="TerminalTool")]
        llm1 = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        original_agent = Agent(llm=llm1, tools=tools)
        conversation = LocalConversation(
            agent=original_agent,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            visualizer=None,
        )

        # 发送消息以创建某种状态
        conversation.send_message(
            Message(role="user", content=[TextContent(text="test message")])
        )

        conversation_id = conversation.state.id
        del conversation

        # 使用不同的 LLM 创建新对话 - 这应该会成功
        llm2 = LLM(
            model="gpt-4o",  # 型号不同
            api_key=SecretStr("different-key"),  # 不同的钥匙
            usage_id="different-llm",
        )
        different_agent = Agent(llm=llm2, tools=tools)

        # 这应该会成功 - LLM 可以在会话之间自由更改
        new_conversation = LocalConversation(
            agent=different_agent,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            conversation_id=conversation_id,
            visualizer=None,
        )

        # 验证状态已加载并且使用了新的智能体和新的 LLM
        assert len(new_conversation.state.events) > 0
        assert new_conversation.agent.llm.model == "gpt-4o"
        assert new_conversation.agent.llm.usage_id == "different-llm"


def test_conversation_fails_when_agent_type_changes():
    """测试使用不同的智能体类恢复是否失败。

    这是一个硬兼容性要求：只有当运行时智能体与已持久化智能体是同一类时，我们才能恢复
    。

    Note: 我们在模块范围定义替代方案智能体以确保已持久化
    快照可以是已反序列化； 否则，Pydantic 会拒绝本地类。
    """

    tools = [Tool(name="TerminalTool")]

    llm1 = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="llm")
    llm2 = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="llm")

    with tempfile.TemporaryDirectory() as temp_dir:
        conversation = LocalConversation(
            agent=Agent(llm=llm1, tools=tools),
            workspace=temp_dir,
            persistence_dir=temp_dir,
            visualizer=None,
        )
        conversation_id = conversation.state.id
        del conversation

        with pytest.raises(ValueError, match=r"persisted agent is of type"):
            LocalConversation(
                agent=ModuleScopeOtherAgent(llm=llm2, tools=tools),
                workspace=temp_dir,
                persistence_dir=temp_dir,
                conversation_id=conversation_id,
                visualizer=None,
            )


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_conversation_persistence_lifecycle(mock_completion):
    """测试完整的对话生命周期持久化类似于 examples/10_persistence.py."""  # noqa: E501
    from tests.conftest import create_mock_litellm_response

    # 模拟对象 LLM 完成调用
    mock_response = create_mock_litellm_response(
        content="I'll help you with that task.", finish_reason="stop"
    )
    mock_completion.return_value = mock_response

    with tempfile.TemporaryDirectory() as temp_dir:
        tools = [
            Tool(name="TerminalTool"),
            Tool(name="FileEditorTool"),
        ]
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=tools)

        # 创建对话并发送消息
        conversation = LocalConversation(
            agent=agent, workspace=temp_dir, persistence_dir=temp_dir, visualize=False
        )

        # 发送第一条消息
        conversation.send_message(
            Message(role="user", content=[TextContent(text="First message")])
        )
        conversation.run()

        # 发送第二条消息
        conversation.send_message(
            Message(role="user", content=[TextContent(text="Second message")])
        )
        conversation.run()

        # 存储对话 ID 和事件计数
        original_id = conversation.id
        original_event_count = len(conversation.state.events)
        original_state_dump = conversation._state.model_dump(
            mode="json", exclude={"events"}
        )

        # 删除对话以模拟重启
        del conversation

        # 创建新对话（应从持久化加载）
        new_conversation = LocalConversation(
            agent=agent,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            conversation_id=original_id,  # 使用相同的 ID 加载现有状态
            visualizer=None,
        )

        # 验证状态已恢复
        assert new_conversation.id == original_id
        # 从持久化加载时，状态应该完全相同
        assert len(new_conversation.state.events) == original_event_count
        # Test model_dump equality (excluding events which may have different timestamps)  # noqa: E501
        new_dump = new_conversation._state.model_dump(mode="json", exclude={"events"})
        assert new_dump == original_state_dump

        # 发送另一条消息以验证对话是否继续
        new_conversation.send_message(
            Message(role="user", content=[TextContent(text="Third message")])
        )
        new_conversation.run()

        # 验证新事件已添加我们期望：original_event_count + 1（来自 init 的系统提示词）+
        # 2（用户消息 + 智能体响应）
        #
        assert len(new_conversation.state.events) >= original_event_count + 2


def test_conversation_resume_overrides_agent_llm_but_preserves_state_settings():
    """测试更改运行时 Agent/LLM 设置时的恢复行为。

    期望：
    - 某些对话 *state* 设置为已持久化，不应在恢复时覆盖（e.g.、confirmation_policy、
    execution_status）。
    - Agent/LLM 设置应来自恢复时运行时提供的智能体

    此测试涵盖常见工作流程：启动已持久化对话，调整几个状态设置，然后使用不同的 LLM 配
    置恢复。
    """

    from openhands.sdk.security.confirmation_policy import AlwaysConfirm

    with tempfile.TemporaryDirectory() as temp_dir:
        tools = [Tool(name="TerminalTool")]

        # 初始智能体（已持久化快照包含此智能体配置，但在恢复时我们应该使用运行时提供的智
        # 能体）。
        #
        llm1 = LLM(
            model="gpt-5.1-codex-max",
            api_key=SecretStr("test-key-1"),
            usage_id="llm-1",
            max_input_tokens=100_000,
        )
        agent1 = Agent(llm=llm1, tools=tools)

        conversation = LocalConversation(
            agent=agent1,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            visualizer=None,
        )

        # 已持久化状态设置（这些应该从持久化恢复）。
        conversation.state.confirmation_policy = AlwaysConfirm()
        conversation.state.execution_status = ConversationExecutionStatus.STUCK

        conversation_id = conversation.state.id
        del conversation

        # 使用不同的运行时间智能体 + LLM 设置继续。
        llm2 = LLM(
            model="gpt-5.2",
            api_key=SecretStr("test-key-2"),
            usage_id="llm-2",
            max_input_tokens=50_000,
        )
        agent2 = Agent(llm=llm2, tools=tools)

        resumed = LocalConversation(
            agent=agent2,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            conversation_id=conversation_id,
            visualizer=None,
        )

        # 应保留已持久化设置。
        assert resumed.state.execution_status == ConversationExecutionStatus.STUCK
        assert resumed.state.confirmation_policy.should_confirm()

        # 运行时代理/LLM 设置应覆盖已持久化智能体快照。
        assert resumed.agent.llm.model == "gpt-5.2"
        assert resumed.agent.llm.max_input_tokens == 50_000
        assert resumed.agent.llm.usage_id == "llm-2"


def test_conversation_restart_with_different_agent_context():
    """
    当 agent_context 不同时测试对话重新启动。

    这模拟在常规 CLI 模式下恢复 ACP 对话。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 模拟ACP模式：用user_provided_resources技能创造智能体
        acp_skill = Skill(
            name="user_provided_resources",
            content=(
                "You may encounter sections labeled as user-provided additional "
                "context or resources."
            ),
            trigger=None,
        )
        acp_context = AgentContext(
            skills=[acp_skill],
            system_message_suffix=(
                "You current working directory is: /Users/jpshack/code/all-hands"
            ),
        )

        tools = [
            Tool(name="TerminalTool"),
            Tool(name="FileEditorTool"),
        ]
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        acp_agent = Agent(llm=llm, tools=tools, agent_context=acp_context)

        # 与 ACP 智能体创建对话
        conversation = LocalConversation(
            agent=acp_agent,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            visualizer=None,
        )

        # 发送消息以创建状态
        conversation.send_message(
            Message(role="user", content=[TextContent(text="test message")])
        )

        conversation_id = conversation.state.id
        del conversation

        # 模拟常规 CLI 模式：在没有 user_provided_resources 技能和不同工作目录的情况下创
        # 建智能体
        #
        cli_skill = Skill(
            name="project_info",
            content="Information about the current project",
            trigger=None,
        )
        cli_context = AgentContext(
            skills=[cli_skill],
            system_message_suffix="You current working directory is: /Users/jpshack",
        )

        cli_agent = Agent(llm=llm, tools=tools, agent_context=cli_context)

        # 这应该会成功 - agent_context 分歧应该得到协调
        new_conversation = LocalConversation(
            agent=cli_agent,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            conversation_id=conversation_id,
            visualizer=None,
        )

        # 验证状态已加载并且 agent_context 已更新
        assert new_conversation.id == conversation_id
        assert len(new_conversation.state.events) > 0
        # 新对话应使用 CLI 智能体的上下文
        assert new_conversation.agent.agent_context is not None
        assert len(new_conversation.agent.agent_context.skills) == 1
        assert new_conversation.agent.agent_context.skills[0].name == "project_info"
        assert new_conversation.agent.agent_context.system_message_suffix is not None
        assert (
            "You current working directory is: /Users/jpshack"
            in new_conversation.agent.agent_context.system_message_suffix
        )
