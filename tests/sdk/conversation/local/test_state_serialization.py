"""测试 ConversationState 序列化和持久化逻辑。"""

import json
import tempfile
import uuid
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from openhands.sdk import Agent, Conversation
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.conversation.types import (
    ConversationCallbackType,
    ConversationTokenCallbackType,
)
from openhands.sdk.event.llm_convertible import MessageEvent, SystemPromptEvent
from openhands.sdk.io import InMemoryFileStore
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.llm.llm_registry import RegistryEvent
from openhands.sdk.security.confirmation_policy import AlwaysConfirm
from openhands.sdk.workspace import LocalWorkspace


class _DifferentAgentForVerifyTest(AgentBase):
    """用于测试 Agent.verify() 的不同智能体类拒绝类不匹配。

    此类在模块级别定义（而不是在测试函数内部），以确保它在序列化/反序列化期间可由
    Pydantic 导入。 当与 pytest-xdist 并行运行测试时，在测试函数
    中定义它会导致测试污染。
    """

    def __init__(self):
        llm = LLM(
            model="gpt-4o-mini",
            api_key=SecretStr("test-key"),
            usage_id="test-llm",
        )
        super().__init__(llm=llm, tools=[])

    def init_state(self, state, on_event):
        pass

    def step(
        self,
        conversation,
        on_event: ConversationCallbackType,
        on_token: ConversationTokenCallbackType | None = None,
    ):
        pass


def test_conversation_state_basic_serialization():
    """测试基本 ConversationState 序列化和反序列化。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    state = ConversationState.create(
        agent=agent,
        id=uuid.UUID("12345678-1234-5678-9abc-123456789001"),
        workspace=LocalWorkspace(working_dir="/tmp"),
    )

    # 添加一些事件
    event1 = SystemPromptEvent(
        source="agent", system_prompt=TextContent(text="system"), tools=[]
    )
    event2 = MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="hello")]),
    )
    state.events.append(event1)
    state.events.append(event2)

    # 测试序列化 - 请注意，事件不包含在基本状态中
    serialized = state.model_dump_json(exclude_none=True)
    assert isinstance(serialized, str)

    # 测试反序列化 - 事件不会包含在基本状态中
    deserialized = ConversationState.model_validate_json(serialized)
    assert deserialized.id == state.id

    # 事件是单独存储的，所以我们需要通过EventLog来查看实际的事件，而不是通过序列化
    #
    assert len(state.events) >= 2  # 可能还有来自 Agent.init_state 的其他活动

    # 查找我们的测试活动
    our_events = [
        e
        for e in state.events
        if isinstance(e, (SystemPromptEvent, MessageEvent))
        and e.source in ["agent", "user"]
    ]
    assert len(our_events) >= 2
    assert deserialized.agent.llm.model == state.agent.llm.model
    assert deserialized.agent.__class__ == state.agent.__class__

    # 验证智能体个属性
    assert deserialized.agent.llm.model == agent.llm.model
    assert deserialized.agent.__class__ == agent.__class__


def test_conversation_state_persistence_save_load():
    """使用 FileStore 测试 ConversationState 持久化。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])

        conv_id = uuid.UUID("12345678-1234-5678-9abc-123456789002")
        persist_path_for_state = LocalConversation.get_persistence_dir(
            temp_dir, conv_id
        )
        state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path_for_state,
            agent=agent,
            id=conv_id,
        )

        # 添加事件
        event1 = SystemPromptEvent(
            source="agent", system_prompt=TextContent(text="system"), tools=[]
        )
        event2 = MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="hello")]),
        )
        state.events.append(event1)
        state.events.append(event2)
        # 注意：在此处不注册 LLM 统计数据 - 此测试验证纯事件
        # 持久化。 LLM 统计信息注册发生在智能体初始化期间，现在是惰性的。
        #

        # 添加事件时状态自动保存验证文件已创建
        #
        assert Path(persist_path_for_state, "base_state.json").exists()

        # 事件以新的命名模式存储
        event_files = list(Path(persist_path_for_state, "events").glob("*.json"))
        assert len(event_files) == 2

        # 使用 Conversation 加载状态（处理加载）
        conversation = Conversation(
            agent=agent,
            persistence_dir=temp_dir,
            workspace=LocalWorkspace(working_dir="/tmp"),
            conversation_id=conv_id,
        )
        assert isinstance(conversation, LocalConversation)
        loaded_state = conversation._state
        assert conversation.state.persistence_dir == persist_path_for_state

        # 验证加载状态是否与原始状态相符
        assert loaded_state.id == state.id
        assert len(loaded_state.events) == 2
        assert isinstance(loaded_state.events[0], SystemPromptEvent)
        assert isinstance(loaded_state.events[1], MessageEvent)
        assert loaded_state.agent.llm.model == agent.llm.model
        assert loaded_state.agent.__class__ == agent.__class__
        # 测试 model_dump 相等性
        assert loaded_state.model_dump(mode="json") == state.model_dump(mode="json")

        # 还要验证关键字段是否已保留
        assert loaded_state.id == state.id
        assert len(loaded_state.events) == len(state.events)


def test_conversation_state_incremental_save():
    """测试 ConversationState 是否增量保存事件。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])

        conv_id = uuid.UUID("12345678-1234-5678-9abc-123456789003")
        persist_path_for_state = LocalConversation.get_persistence_dir(
            temp_dir, conv_id
        )
        state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path_for_state,
            agent=agent,
            id=uuid.UUID("12345678-1234-5678-9abc-123456789003"),
        )

        # 添加第一个事件 - 自动保存
        event1 = SystemPromptEvent(
            source="agent", system_prompt=TextContent(text="system"), tools=[]
        )
        state.events.append(event1)
        # 注意：不在此注册 LLM 统计数据 - LLM 注册发生在
        # 智能体现在是懒加载的初始化。

        # 验证事件文件是否存在（可能有来自 Agent.init_state 的其他事件）
        event_files = list(Path(persist_path_for_state, "events").glob("*.json"))
        assert len(event_files) == 1

        # 添加第二个事件 - 自动保存
        event2 = MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="hello")]),
        )
        state.events.append(event2)

        # 验证是否已创建附加事件文件
        event_files = list(Path(persist_path_for_state, "events").glob("*.json"))
        assert len(event_files) == 2

        # 使用对话加载并验证事件是否存在
        conversation = Conversation(
            agent=agent,
            persistence_dir=temp_dir,
            workspace=LocalWorkspace(working_dir="/tmp"),
            conversation_id=conv_id,
        )
        assert isinstance(conversation, LocalConversation)
        assert conversation.state.persistence_dir == persist_path_for_state
        loaded_state = conversation._state
        assert len(loaded_state.events) == 2
        # 测试 model_dump 相等性
        assert loaded_state.model_dump(mode="json") == state.model_dump(mode="json")


def test_conversation_state_event_file_scanning():
    """通过EventLog测试事件文件扫描和排序逻辑。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])

        conv_id = uuid.UUID("12345678-1234-5678-9abc-123456789004")
        persist_path_for_state = LocalConversation.get_persistence_dir(
            temp_dir, conv_id
        )

        # 创建具有有效格式的事件文件（新模式）
        events_dir = Path(persist_path_for_state, "events")
        events_dir.mkdir(parents=True, exist_ok=True)

        # 使用有效的事件格式创建具有不同索引的文件
        event1 = SystemPromptEvent(
            id="abcdef01",
            source="agent",
            system_prompt=TextContent(text="system1"),
            tools=[],
        )
        (events_dir / "event-00000-abcdef01.json").write_text(
            event1.model_dump_json(exclude_none=True)
        )

        event2 = SystemPromptEvent(
            id="abcdef02",
            source="agent",
            system_prompt=TextContent(text="system2"),
            tools=[],
        )
        (events_dir / "event-00001-abcdef02.json").write_text(
            event2.model_dump_json(exclude_none=True)
        )

        # 无效文件应被忽略
        (events_dir / "invalid-file.json").write_text('{"type": "test"}')

        # 加载状态 - EventLog 应该处理扫描
        conversation = Conversation(
            agent=agent,
            persistence_dir=temp_dir,
            workspace=LocalWorkspace(working_dir="/tmp"),
            conversation_id=conv_id,
        )

        # 应按顺序加载有效事件
        assert (
            len(conversation._state.events) == 2
        )  # 可能还有来自 Agent.init_state 的其他活动

        # 查找我们的测试活动
        our_events = [
            e
            for e in conversation._state.events
            if isinstance(e, SystemPromptEvent) and e.id in ["abcdef01", "abcdef02"]
        ]
        assert len(our_events) == 2


def test_conversation_state_corrupted_event_handling():
    """测试重播期间损坏的事件文件的处理。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])

        # 创建一些损坏的事件文件
        conv_id = uuid.uuid4()
        persist_path_for_state = LocalConversation.get_persistence_dir(
            temp_dir, conv_id
        )
        events_dir = Path(persist_path_for_state, "events")
        events_dir.mkdir(parents=True, exist_ok=True)

        # 具有正确格式的有效事件
        valid_event = SystemPromptEvent(
            id="abcdef01",
            source="agent",
            system_prompt=TextContent(text="system"),
            tools=[],
        )
        (events_dir / "event-00000-abcdef01.json").write_text(
            valid_event.model_dump_json(exclude_none=True)
        )

        # 损坏的 JSON - 访问时将导致验证错误
        (events_dir / "event-00001-abcdef02.json").write_text('{"invalid": json}')

        # 空文件 - 将被 EventLog 忽略
        (events_dir / "event-00002-abcdef03.json").write_text("")

        # 具有正确格式的有效事件
        valid_event2 = MessageEvent(
            id="abcdef04",
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="hello")]),
        )
        (events_dir / "event-00003-abcdef04.json").write_text(
            valid_event2.model_dump_json(exclude_none=True)
        )

        # 加载对话 - EventLog 在初始化期间索引文件，但在访问事件之前不验证内容
        #
        conversation = Conversation(
            agent=agent,
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=temp_dir,
            conversation_id=conv_id,
        )

        # 访问事件触发器验证 - 损坏的 JSON 将失败
        with pytest.raises((ValidationError, json.JSONDecodeError)):
            # 遍历所有事件来触发加载
            list(conversation._state.events)


def test_conversation_state_empty_filestore():
    """使用空的持久化目录测试 ConversationState 行为。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])

        # 创建与空持久化目录的对话
        conversation = Conversation(
            agent=agent,
            persistence_dir=temp_dir,
            workspace=LocalWorkspace(working_dir="/tmp"),
            visualizer=None,
        )

        # 应该创建新状态
        assert conversation._state.id is not None

        # 智能体初始化是惰性的 - 触发它发出 SystemPromptEvent
        conversation._ensure_agent_ready()

        assert len(conversation._state.events) == 1  # 系统提示词事件
        assert isinstance(conversation._state.events[0], SystemPromptEvent)


def test_conversation_state_missing_base_state():
    """测试缺少 base_state.json 但事件存在时的错误处理。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])

        # 创建包含文件但不包含 base_state.json 的事件目录
        events_dir = Path(temp_dir, "events")
        events_dir.mkdir()
        event = SystemPromptEvent(
            id="abcdef01",
            source="agent",
            system_prompt=TextContent(text="system"),
            tools=[],
        )
        (events_dir / "event-00000-abcdef01.json").write_text(
            event.model_dump_json(exclude_none=True)
        )

        # 当前的实现创建新的对话并忽略孤立的事件文件
        #
        conversation = Conversation(
            agent=agent,
            persistence_dir=temp_dir,
            workspace=LocalWorkspace(working_dir="/tmp"),
        )

        # 应该创建新状态，而不是加载孤立事件文件
        assert conversation._state.id is not None
        # 注意：使用延迟初始化，系统提示词直到第一次使用时才添加


def test_conversation_state_exclude_from_base_state():
    """测试事件是否从基础状态中排除序列化。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])
        state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=temp_dir,
            agent=agent,
            id=uuid.UUID("12345678-1234-5678-9abc-123456789004"),
        )

        # 添加事件
        event = SystemPromptEvent(
            source="agent", system_prompt=TextContent(text="system"), tools=[]
        )
        state.events.append(event)

        # 状态自动保存，直接读取基础状态文件
        base_state_path = Path(temp_dir) / "base_state.json"
        base_state_content = base_state_path.read_text()
        base_state_data = json.loads(base_state_content)

        # 事件不应处于基本状态
        assert "events" not in base_state_data
        assert "agent" in base_state_data
        assert "id" in base_state_data


def test_conversation_state_thread_safety():
    """使用锁定/解锁测试 ConversationState 线程安全。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    state = ConversationState.create(
        workspace=LocalWorkspace(working_dir="/tmp"),
        agent=agent,
        id=uuid.UUID("12345678-1234-5678-9abc-123456789005"),
    )

    # 测试上下文管理器
    with state:
        assert state.owned()
        # 锁定时应由当前线程拥有

    # 测试手册获取/释放
    state.acquire()
    try:
        assert state.owned()
    finally:
        state.release()

    # 测试未锁定时状态不被拥有
    assert not state.owned()


def test_agent_pydantic_validation_on_creation():
    """测试创建智能体时是否发生 Pydantic 验证。"""
    # 有效智能体创建 - Pydantic 验证
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    assert agent.llm.model == "gpt-4o-mini"

    # 无效 LLM 创建应该失败 Pydantic 验证
    with pytest.raises(ValueError, match="model must be specified"):
        LLM(model="", api_key=SecretStr("test-key"), usage_id="test-llm")


def test_agent_verify_validates_tools_match():
    """测试 agent.verify() 验证运行时和已持久化之间的工具匹配。"""
    from openhands.sdk.agent import AgentBase
    from openhands.sdk.tool import Tool

    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")

    # 使用两个工具创建原创智能体
    original_agent = Agent(
        llm=llm, tools=[Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
    )

    # 序列化和反序列化模拟持久化
    serialized = original_agent.model_dump_json()
    persisted_agent = AgentBase.model_validate_json(serialized)

    # 使用相同工具的运行时智能体应该会成功
    same_tools_agent = Agent(
        llm=llm, tools=[Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
    )
    result = same_tools_agent.verify(persisted_agent)
    assert result is same_tools_agent

    # 使用不同工具的运行时智能体应该会失败
    different_tools_agent = Agent(llm=llm, tools=[Tool(name="TerminalTool")])
    with pytest.raises(ValueError, match="tools were removed mid-conversation"):
        different_tools_agent.verify(persisted_agent)


def test_agent_verify_allows_different_llm():
    """测试 agent.verify() 是否允许不同的 LLM 配置。"""
    from openhands.sdk.agent import AgentBase
    from openhands.sdk.tool import Tool

    tools = [Tool(name="TerminalTool")]

    # 创作原创智能体
    llm1 = LLM(model="gpt-4o-mini", api_key=SecretStr("key1"), usage_id="llm1")
    original_agent = Agent(llm=llm1, tools=tools)

    # 序列化和反序列化
    serialized = original_agent.model_dump_json()
    persisted_agent = AgentBase.model_validate_json(serialized)

    # 具有不同 LLM 的运行时智能体应该成功（LLM 可以自由更改）
    llm2 = LLM(model="gpt-4o", api_key=SecretStr("key2"), usage_id="llm2")
    different_llm_agent = Agent(llm=llm2, tools=tools)
    result = different_llm_agent.verify(persisted_agent)
    assert result is different_llm_agent
    assert result.llm.model == "gpt-4o"


def test_agent_verify_different_class_raises_error():
    """测试 agent.verify() 是否会针对不同的智能体类引发错误。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    original_agent = Agent(llm=llm, tools=[])
    different_agent = _DifferentAgentForVerifyTest()

    with pytest.raises(ValueError, match="Cannot load from persisted"):
        original_agent.verify(different_agent)


def test_conversation_state_flags_persistence():
    """测试对话状态标志是否正确已持久化。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])
        conv_id = uuid.UUID("12345678-1234-5678-9abc-123456789006")
        persist_path_for_state = LocalConversation.get_persistence_dir(
            temp_dir, conv_id
        )
        state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path_for_state,
            agent=agent,
            id=conv_id,
        )

        state.stats.register_llm(RegistryEvent(llm=llm))

        # 设置各种标志
        state.execution_status = ConversationExecutionStatus.FINISHED
        state.confirmation_policy = AlwaysConfirm()
        state.activated_knowledge_skills = ["agent1", "agent2"]

        # 创建一个从同一持久化目录加载的新 ConversationState
        loaded_state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path_for_state,
            agent=agent,
            id=conv_id,
        )

        # 验证关键字段是否已保留
        assert loaded_state.id == state.id
        assert loaded_state.agent.llm.model == state.agent.llm.model
        # 验证标志是否保留
        assert loaded_state.execution_status == ConversationExecutionStatus.FINISHED
        assert loaded_state.confirmation_policy == AlwaysConfirm()
        assert loaded_state.activated_knowledge_skills == ["agent1", "agent2"]
        # 测试 model_dump 平等 - 统计数据应保留在简历中
        assert loaded_state.model_dump(mode="json") == state.model_dump(mode="json")


def test_conversation_with_agent_different_llm_config():
    """测试与具有不同 LLM 配置的智能体的对话。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 使用原始 LLM 配置创建对话
        original_llm = LLM(
            model="gpt-4o-mini",
            api_key=SecretStr("original-key"),
            usage_id="test-llm",
        )
        original_agent = Agent(llm=original_llm, tools=[])
        conversation = Conversation(
            agent=original_agent,
            persistence_dir=temp_dir,
            workspace=LocalWorkspace(working_dir="/tmp"),
            visualizer=None,
        )

        # 发送消息（这会触发惰性智能体初始化）
        conversation.send_message(
            Message(role="user", content=[TextContent(text="test")])
        )

        # 在 LLM 注册期间，智能体初始化时，原始状态快照和ID应先保存
        #
        original_state_dump = conversation._state.model_dump(
            mode="json", exclude={"agent", "stats"}
        )
        conversation_id = conversation._state.id

        del conversation

        # 尝试使用不同的 LLM 配置（应该解析不同的 API 键）
        new_llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("new-key"), usage_id="test-llm"
        )
        new_agent = Agent(llm=new_llm, tools=[])

        # 这应该会成功，因为 API 关键差异已解决
        new_conversation = Conversation(
            agent=new_agent,
            persistence_dir=temp_dir,
            workspace=LocalWorkspace(working_dir="/tmp"),
            conversation_id=conversation_id,  # 使用相同的ID
            visualizer=None,
        )

        assert new_conversation._state.agent.llm.api_key is not None
        assert isinstance(new_conversation._state.agent.llm.api_key, SecretStr)
        assert new_conversation._state.agent.llm.api_key.get_secret_value() == "new-key"
        # 测试核心状态结构是否保留（不包括智能体和 stats）
        new_dump = new_conversation._state.model_dump(
            mode="json", exclude={"agent", "stats"}
        )

        assert new_dump == original_state_dump


def test_resume_uses_runtime_workspace_and_max_iterations():
    """测试恢复是否使用运行时提供的工作区和 max_iterations。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])
        conv_id = uuid.UUID("12345678-1234-5678-9abc-123456789007")
        persist_path = LocalConversation.get_persistence_dir(temp_dir, conv_id)

        original_workspace = LocalWorkspace(working_dir="/original/path")
        state = ConversationState.create(
            workspace=original_workspace,
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
            max_iterations=100,
        )
        assert state.max_iterations == 100

        new_workspace = LocalWorkspace(working_dir="/new/path")
        resumed_state = ConversationState.create(
            workspace=new_workspace,
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
            max_iterations=200,
        )

        assert resumed_state.workspace.working_dir == "/new/path"
        assert resumed_state.max_iterations == 200


def test_resume_preserves_persisted_execution_status_and_stuck_detection():
    """测试简历是否保留 execution_status 和 stuck_detection。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])
        conv_id = uuid.UUID("12345678-1234-5678-9abc-123456789008")
        persist_path = LocalConversation.get_persistence_dir(temp_dir, conv_id)

        state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
            stuck_detection=False,
        )
        state.execution_status = ConversationExecutionStatus.PAUSED

        resumed_state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
            stuck_detection=True,
        )

        assert resumed_state.execution_status == ConversationExecutionStatus.PAUSED
        assert resumed_state.stuck_detection is False


def test_resume_preserves_blocked_actions_and_messages():
    """测试简历是否保留 blocked_actions 和 blocked_messages。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])
        conv_id = uuid.UUID("12345678-1234-5678-9abc-123456789009")
        persist_path = LocalConversation.get_persistence_dir(temp_dir, conv_id)

        state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
        )
        state.block_action("action-1", "dangerous action")
        state.block_message("msg-1", "inappropriate content")

        resumed_state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
        )

        assert resumed_state.blocked_actions["action-1"] == "dangerous action"
        assert resumed_state.blocked_messages["msg-1"] == "inappropriate content"


def test_conversation_state_stats_preserved_on_resume():
    """Regression: 恢复对话时不应重置统计数据。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])

        conv_id = uuid.UUID("12345678-1234-5678-9abc-123456789010")
        persist_path_for_state = LocalConversation.get_persistence_dir(
            temp_dir, conv_id
        )
        state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path_for_state,
            agent=agent,
            id=conv_id,
        )

        state.stats.register_llm(RegistryEvent(llm=llm))

        # 将词元用量添加到 context_window
        assert llm.metrics is not None
        llm.metrics.add_cost(0.05)
        llm.metrics.add_token_usage(
            prompt_tokens=100,
            completion_tokens=50,
            cache_read_tokens=10,
            cache_write_tokens=5,
            context_window=128000,
            response_id="test-response-1",
        )

        # 保存前验证统计数据设置正确
        combined_metrics = state.stats.get_combined_metrics()
        assert combined_metrics.accumulated_cost == 0.05
        assert combined_metrics.accumulated_token_usage is not None
        assert combined_metrics.accumulated_token_usage.prompt_tokens == 100
        assert combined_metrics.accumulated_token_usage.context_window == 128000

        # 强制保存状态
        state._save_base_state(state._fs)

        # 验证 base_state.json 包含统计信息
        base_state_path = Path(persist_path_for_state) / "base_state.json"
        base_state_content = json.loads(base_state_path.read_text())
        assert "stats" in base_state_content
        assert "usage_to_metrics" in base_state_content["stats"]
        assert "test-llm" in base_state_content["stats"]["usage_to_metrics"]

        # 现在与新的智能体恢复对话
        new_llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        new_agent = Agent(llm=new_llm, tools=[])

        resumed_state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path_for_state,
            agent=new_agent,
            id=conv_id,
        )

        # 验证恢复后统计数据是否保留
        resumed_combined_metrics = resumed_state.stats.get_combined_metrics()
        assert resumed_combined_metrics.accumulated_cost == 0.05, (
            "Cost should be preserved after resume"
        )
        assert resumed_combined_metrics.accumulated_token_usage is not None
        assert resumed_combined_metrics.accumulated_token_usage.prompt_tokens == 100, (
            "Prompt tokens should be preserved after resume"
        )
        assert (
            resumed_combined_metrics.accumulated_token_usage.context_window == 128000
        ), "Context window should be preserved after resume"


def test_resume_with_conversation_id_mismatch_raises_error():
    """测试使用不匹配的对话 ID 进行恢复是否会引发错误。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])
        original_id = uuid.UUID("12345678-1234-5678-9abc-12345678900b")
        different_id = uuid.UUID("12345678-1234-5678-9abc-12345678900c")
        persist_path = LocalConversation.get_persistence_dir(temp_dir, original_id)

        ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=original_id,
        )

        with pytest.raises(ValueError, match="Conversation ID mismatch"):
            ConversationState.create(
                workspace=LocalWorkspace(working_dir="/tmp"),
                persistence_dir=persist_path,
                agent=agent,
                id=different_id,
            )


def test_conversation_state_secrets_serialization_deserialization():
    """测试机密是否正确为已序列化和已反序列化。

    这是一个回归测试 issue 1505 中的对话机密会导致恢复失败机密 are 已序列化 as '****
    ******' (已脱敏但
    StaticSecret.value 这是一个必填字段，不能接受 None 之后验证转换完毕**********' to
     None.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])
        conv_id = uuid.UUID("12345678-1234-5678-9abc-123456789099")
        persist_path = LocalConversation.get_persistence_dir(temp_dir, conv_id)

        # 创建与机密的对话状态
        state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
        )

        # 将机密添加到机密注册表
        state.secret_registry.update_secrets(
            {
                "API_KEY": "test-api-key",
                "DATABASE_URL": "postgresql://localhost/test",
            }
        )

        # 保存前验证机密已设置
        env_vars = state.secret_registry.get_secrets_as_env_vars("echo $API_KEY")
        assert env_vars == {"API_KEY": "test-api-key"}

        # 强制保存状态（触发序列化）
        state._save_base_state(state._fs)

        # 验证已序列化状态有已脱敏机密
        base_state_path = Path(persist_path) / "base_state.json"
        base_state_content = json.loads(base_state_path.read_text())
        assert "secret_registry" in base_state_content
        api_key_source = base_state_content["secret_registry"]["secret_sources"][
            "API_KEY"
        ]
        # 值应为序列化中的已脱敏到“**********”
        assert api_key_source["value"] == "**********"

        # 现在模拟从已持久化数据恢复对话状态在修复之前失败：“
        # pydantic_core._pydantic_core.ValidationError：需要字段
        #
        # [type=missing, ... for StaticSecret.value"
        resumed_state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
        )

        # 状态应该成功加载 - 这是错误修复
        assert resumed_state.id == conv_id

        # 恢复后机密应该是 None（因为它们是已脱敏），但 StaticSecret 对象应该存在
        #
        assert "API_KEY" in resumed_state.secret_registry.secret_sources
        assert "DATABASE_URL" in resumed_state.secret_registry.secret_sources

        # 这些值应为已脱敏机密的反序列化之后的 None
        api_key_source_restored = resumed_state.secret_registry.secret_sources[
            "API_KEY"
        ]
        assert api_key_source_restored.get_value() is None

        # 获取环境变量应该返回空，因为值为 None
        env_vars = resumed_state.secret_registry.get_secrets_as_env_vars(
            "echo $API_KEY"
        )
        assert env_vars == {}  # 没有值可用


def test_conversation_state_secrets_with_cipher():
    """测试使用密码时是否保留机密。

    当将密钥提供给 ConversationState.create() 时，机密应在序列化中加密，在反序列化中
    解密，以确保在保存/恢复周期中保留实际机密值。
    """
    from openhands.sdk.utils.cipher import Cipher

    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])
        conv_id = uuid.UUID("12345678-1234-5678-9abc-1234567890aa")
        persist_path = LocalConversation.get_persistence_dir(temp_dir, conv_id)

        # 创建用于加密的密码
        cipher = Cipher(secret_key="my-secret-encryption-key")

        # 使用机密 AND 密码创建对话状态
        state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
            cipher=cipher,
        )

        # 将机密添加到机密注册表
        state.secret_registry.update_secrets(
            {
                "API_KEY": "test-api-key",
                "DATABASE_URL": "postgresql://localhost/test",
            }
        )

        # 保存前验证机密已设置
        env_vars = state.secret_registry.get_secrets_as_env_vars("echo $API_KEY")
        assert env_vars == {"API_KEY": "test-api-key"}

        # 强制保存状态（触发序列化加密）
        state._save_base_state(state._fs)

        # 验证已序列化状态已加密（不是已脱敏）机密
        base_state_path = Path(persist_path) / "base_state.json"
        base_state_content = json.loads(base_state_path.read_text())
        assert "secret_registry" in base_state_content
        api_key_source = base_state_content["secret_registry"]["secret_sources"][
            "API_KEY"
        ]
        # 值应该加密（不是“**********”）
        assert api_key_source["value"] != "**********"
        assert api_key_source["value"] != "test-api-key"  # 不是明文
        assert len(api_key_source["value"]) > 20  # 加密值更长

        # 现在用相同的密码恢复对话状态
        resumed_state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
            cipher=cipher,
        )

        # 状态应该加载成功
        assert resumed_state.id == conv_id

        # 恢复后机密应为PRESERVED
        assert "API_KEY" in resumed_state.secret_registry.secret_sources
        assert "DATABASE_URL" in resumed_state.secret_registry.secret_sources

        # 这些值应该被解密并可访问
        api_key_source_restored = resumed_state.secret_registry.secret_sources[
            "API_KEY"
        ]
        assert api_key_source_restored.get_value() == "test-api-key"

        # 获取环境变量应该返回实际值
        env_vars = resumed_state.secret_registry.get_secrets_as_env_vars(
            "echo $API_KEY"
        )
        assert env_vars == {"API_KEY": "test-api-key"}

        db_env_vars = resumed_state.secret_registry.get_secrets_as_env_vars(
            "echo $DATABASE_URL"
        )
        assert db_env_vars == {"DATABASE_URL": "postgresql://localhost/test"}


def test_agent_context_seed_preserves_persisted_registry_secret_on_resume():
    """LocalConversation 简历不得降级现有注册表机密。

    ``agent_context.secrets`` 是不构建 ``request.secrets`` 的调用者的较低优先级引导源
    。 如果先前的请求机密已在注册表中为
    已持久化，则在没有新请求机密的情况下重新打开对话应保留注册表值。
    """
    from openhands.sdk.context.agent_context import AgentContext
    from openhands.sdk.secret import StaticSecret
    from openhands.sdk.utils.cipher import Cipher

    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(
            llm=llm,
            tools=[],
            agent_context=AgentContext(
                secrets={
                    "ANTHROPIC_API_KEY": StaticSecret(value=SecretStr("sk-from-ctx"))
                }
            ),
        )
        conv_id = uuid.UUID("12345678-1234-5678-9abc-1234567890ab")
        cipher = Cipher(secret_key="test-secret-key")
        conversation_kwargs = {
            "workspace": str(Path(temp_dir) / "workspace"),
            "persistence_dir": temp_dir,
            "conversation_id": conv_id,
            "cipher": cipher,
        }

        conv = LocalConversation(
            agent,
            **conversation_kwargs,
            secrets={
                "ANTHROPIC_API_KEY": StaticSecret(value=SecretStr("sk-from-request"))
            },
        )
        try:
            assert (
                conv.state.secret_registry.get_secret_value("ANTHROPIC_API_KEY")
                == "sk-from-request"
            )
            conv.state._save_base_state(conv.state._fs)
        finally:
            conv.close()

        resumed = LocalConversation(agent, **conversation_kwargs)
        try:
            assert (
                resumed.state.secret_registry.get_secret_value("ANTHROPIC_API_KEY")
                == "sk-from-request"
            )
        finally:
            resumed.close()


def test_conversation_state_save_with_cipher_load_without():
    """测试使用密码保存但不提供密码的加载状态。

    当使用密码（机密加密）保存状态，但加载时不使用密码时，应保持加密值不变（不可用）
    ，但对话应仍然成功加载。
    """
    from openhands.sdk.utils.cipher import Cipher

    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])
        conv_id = uuid.UUID("12345678-1234-5678-9abc-1234567890bb")
        persist_path = LocalConversation.get_persistence_dir(temp_dir, conv_id)

        # 创建用于加密的密码
        cipher = Cipher(secret_key="my-secret-encryption-key")

        # 使用机密 AND 密码创建对话状态
        state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
            cipher=cipher,
        )

        # 将机密添加到机密注册表
        state.secret_registry.update_secrets({"API_KEY": "test-api-key"})

        # 强制保存状态（触发序列化加密）
        state._save_base_state(state._fs)

        # 现在恢复 WITHOUT 密码 - 应该加载，但机密不可用
        resumed_state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
            cipher=None,  # 没有提供密码
        )

        # 状态应该加载成功
        assert resumed_state.id == conv_id

        # 机密源应该存在，但值是加密字符串（未解密，因此不能用作原始值）
        #
        assert "API_KEY" in resumed_state.secret_registry.secret_sources
        api_key_value = resumed_state.secret_registry.secret_sources[
            "API_KEY"
        ].get_value()
        # 值应该是加密的字符串，而不是原始字符串
        assert api_key_value != "test-api-key"
        assert api_key_value is not None  # 这是加密后的值


def test_conversation_state_save_without_cipher_load_with():
    """测试加载状态在没有密码的情况下保存，但提供了密码。

    当状态保存时不带密码 (机密已脱敏) 但加载密码时，已脱敏机密应为反序列化至 None 值
    。
    """
    from openhands.sdk.utils.cipher import Cipher

    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])
        conv_id = uuid.UUID("12345678-1234-5678-9abc-1234567890cc")
        persist_path = LocalConversation.get_persistence_dir(temp_dir, conv_id)

        # 使用机密创建对话状态，但没有密码
        state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
            cipher=None,  # 无密码 - 机密将变为已脱敏
        )

        # 将机密添加到机密注册表
        state.secret_registry.update_secrets({"API_KEY": "test-api-key"})

        # 强制保存状态（用脱敏触发序列化）
        state._save_base_state(state._fs)

        # 现在恢复 WITH 密码 - 应该加载，但机密已经丢失
        cipher = Cipher(secret_key="my-secret-encryption-key")
        resumed_state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
            cipher=cipher,
        )

        # 状态应该加载成功
        assert resumed_state.id == conv_id

        # 机密源应该存在，但值为 None（原为已脱敏）
        assert "API_KEY" in resumed_state.secret_registry.secret_sources
        api_key_value = resumed_state.secret_registry.secret_sources[
            "API_KEY"
        ].get_value()
        assert api_key_value is None


def test_conversation_state_cipher_mismatch():
    """使用与保存时使用的密码不同的密码来测试加载状态。

    当使用加密A保存状态，但使用加密B加载时，解密会优雅失败 - 对话加载，机密会被设置为
    None（并记录警告）。
    """
    from openhands.sdk.utils.cipher import Cipher

    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])
        conv_id = uuid.UUID("12345678-1234-5678-9abc-1234567890dd")
        persist_path = LocalConversation.get_persistence_dir(temp_dir, conv_id)

        # 创建密码 A 进行加密
        cipher_a = Cipher(secret_key="cipher-key-a")

        # 使用机密 AND 密码 A 创建对话状态
        state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
            cipher=cipher_a,
        )

        # 将机密添加到机密注册表
        state.secret_registry.update_secrets({"API_KEY": "test-api-key"})

        # 强制保存状态（使用密码 A 进行加密触发序列化）
        state._save_base_state(state._fs)

        # 现在尝试使用密码 B 恢复 - 解密正常失败
        cipher_b = Cipher(secret_key="cipher-key-b")

        # 对话加载，但机密丢失（设置为 None 并发出警告）
        resumed_state = ConversationState.create(
            workspace=LocalWorkspace(working_dir="/tmp"),
            persistence_dir=persist_path,
            agent=agent,
            id=conv_id,
            cipher=cipher_b,
        )

        # 状态应该加载成功
        assert resumed_state.id == conv_id

        # 机密源应该存在，但值为 None（解密失败）
        assert "API_KEY" in resumed_state.secret_registry.secret_sources
        api_key_value = resumed_state.secret_registry.secret_sources[
            "API_KEY"
        ].get_value()
        assert api_key_value is None


def test_agent_verify_fails_when_explicit_tools_differ():
    """当显式工具不同时，测试 verify() 是否失败。

    无法在对话中更改工具。 此测试验证更改显式工具未通过验证。
    """
    from openhands.sdk.agent import AgentBase
    from openhands.sdk.tool import Tool

    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")

    # 使用 TerminalTool 创建已持久化智能体
    persisted_agent_obj = Agent(
        llm=llm,
        tools=[Tool(name="TerminalTool")],
        include_default_tools=["FinishTool"],
    )

    # 序列化和反序列化模拟从持久化加载
    serialized = persisted_agent_obj.model_dump_json()
    persisted_agent = AgentBase.model_validate_json(serialized)

    # 使用 DIFFERENT 显式工具创建运行时智能体（FileEditorTool 而不是 TerminalTool） - 这
    # 应该是 FAIL，因为工具必须完全匹配
    #
    runtime_agent = Agent(
        llm=llm,
        tools=[Tool(name="FileEditorTool")],  # 与已持久化不同！
        include_default_tools=["FinishTool"],
    )

    # 应该会失败，因为 TerminalTool 被删除（FileEditorTool 与 TerminalTool）
    with pytest.raises(ValueError, match="tools were removed mid-conversation"):
        runtime_agent.verify(persisted_agent)


def test_agent_verify_fails_when_builtin_tools_differ():
    """当内置工具不同时，测试 verify() 是否失败。

    无法在对话中更改工具。 此测试验证更改内置工具 (include_default_tools) 是否会失败
    ，即使显式工具匹配也是如此。
    """
    from openhands.sdk.agent import AgentBase
    from openhands.sdk.tool import Tool

    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")

    # 已持久化智能体内置 FinishTool
    persisted_agent_obj = Agent(
        llm=llm,
        tools=[Tool(name="TerminalTool")],
        include_default_tools=["FinishTool"],
    )

    serialized = persisted_agent_obj.model_dump_json()
    persisted_agent = AgentBase.model_validate_json(serialized)

    # 运行时智能体有 ThinkTool 而不是 FinishTool（相同的显式工具）
    runtime_agent = Agent(
        llm=llm,
        tools=[Tool(name="TerminalTool")],  # 相同的显式工具
        include_default_tools=["ThinkTool"],  # 不同的内置！
    )

    # 应该会失败，因为 FinishTool 已被删除（ThinkTool 取代了它）
    with pytest.raises(ValueError, match="tools were removed mid-conversation"):
        runtime_agent.verify(persisted_agent)


def test_agent_verify_fails_when_builtin_tool_removed():
    """删除内置工具时验证失败的测试。"""
    from openhands.sdk.agent import AgentBase
    from openhands.sdk.tool import Tool

    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")

    persisted_agent_obj = Agent(
        llm=llm,
        tools=[Tool(name="TerminalTool")],
        include_default_tools=["FinishTool", "ThinkTool"],  # 两者都有
    )

    serialized = persisted_agent_obj.model_dump_json()
    persisted_agent = AgentBase.model_validate_json(serialized)

    # 运行时智能体删除 ThinkTool
    runtime_agent = Agent(
        llm=llm,
        tools=[Tool(name="TerminalTool")],
        include_default_tools=["FinishTool"],  # 缺少ThinkTool！
    )

    # 应该会失败，因为 ThinkTool 已被删除
    with pytest.raises(ValueError, match="tools were removed mid-conversation"):
        runtime_agent.verify(persisted_agent)


def test_v1_11_5_cli_default_conversation_resumes_when_runtime_adds_delegate(
    tmp_path: Path,
):
    """添加委托后，恢复 v1.11.5 CLI 对话的测试成功。

    允许添加新工具——只拒绝删除工具。
    """
    from openhands.sdk.agent import Agent
    from openhands.sdk.tool import Tool

    fixture_path = (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "conversations"
        / "v1_11_5_cli_default"
        / "base_state.json"
    )
    conversation_id = uuid.UUID("11111111-2222-3333-4444-555555555555")
    persistence_root = tmp_path / "persist"
    persistence_dir = Path(
        LocalConversation.get_persistence_dir(persistence_root, conversation_id)
    )
    persistence_dir.mkdir(parents=True)
    (persistence_dir / "base_state.json").write_text(fixture_path.read_text())
    (persistence_dir / "events").mkdir()

    llm = LLM(
        model="gpt-4o-mini",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )
    # 测试夹具有工具：终端、file_editor、task_tracker 运行时添加委托 — 这应该会成功（允
    # 许添加工具）
    #
    runtime_agent = Agent(
        llm=llm,
        tools=[
            Tool(name="terminal"),
            Tool(name="file_editor"),
            Tool(name="task_tracker"),
            Tool(name="delegate"),
        ],
        include_default_tools=["FinishTool", "ThinkTool"],
    )

    _ = Conversation(
        agent=runtime_agent,
        workspace=tmp_path,
        persistence_dir=persistence_root,
        conversation_id=conversation_id,
    )


def test_context_manager_batches_saves() -> None:
    """`with state:` 内的多个字段突变会产生一次保存。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("k"), usage_id="test-llm")
    agent = Agent(llm=llm)
    workspace = LocalWorkspace(working_dir="/tmp/test")

    state = ConversationState(
        id=uuid.uuid4(),
        workspace=workspace,
        persistence_dir="/tmp/test/.state",
        agent=agent,
    )

    fs = InMemoryFileStore()
    state._fs = fs
    state._autosave_enabled = True

    save_count = 0
    _original = state._save_base_state

    def _counting_save(f):
        nonlocal save_count
        save_count += 1
        _original(f)

    state._save_base_state = _counting_save  # type: ignore[method-assign]

    # 一个上下文-管理器块内的三个突变 → 恰好 1 次保存
    with state:
        state.execution_status = ConversationExecutionStatus.RUNNING
        state.max_iterations = 999
        state.stuck_detection = False

    assert save_count == 1

    # 上下文-管理器块外的突变 → 立即保存
    state.max_iterations = 42
    assert save_count == 2


@pytest.mark.parametrize("enabled", [False, True])
def test_saved_conversation_with_retired_browser_kwarg_resumes(tmp_path, enabled):
    conversation_id = uuid.uuid4()
    agent = Agent(llm=LLM(model="test-model"), tools=[])
    workspace = LocalWorkspace(working_dir=str(tmp_path))
    persistence_dir = LocalConversation.get_persistence_dir(tmp_path, conversation_id)
    state = ConversationState.create(
        workspace=workspace,
        persistence_dir=persistence_dir,
        agent=agent,
        id=conversation_id,
    )
    state.events.append(
        MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="old")]),
        )
    )
    path = Path(persistence_dir) / "base_state.json"
    saved = json.loads(path.read_text())
    saved["agent"]["system_prompt_kwargs"]["enable_browser"] = enabled
    path.write_text(json.dumps(saved))

    conversation = Conversation(
        agent=agent,
        workspace=workspace,
        persistence_dir=str(tmp_path),
        conversation_id=conversation_id,
    )
    try:
        assert "enable_browser" not in conversation.state.agent.system_prompt_kwargs
        assert any(
            isinstance(event, MessageEvent) for event in conversation.state.events
        )
    finally:
        conversation.close()
