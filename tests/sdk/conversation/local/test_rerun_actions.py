"""测试 conversation.rerun_actions() 功能。"""

from pathlib import Path

import pytest
from pydantic import SecretStr

from openhands.sdk.agent.base import AgentBase
from openhands.sdk.conversation import Conversation, LocalConversation
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.conversation.types import (
    ConversationCallbackType,
    ConversationTokenCallbackType,
)
from openhands.sdk.event import ActionEvent
from openhands.sdk.event.llm_convertible import MessageEvent, SystemPromptEvent
from openhands.sdk.llm import LLM, Message, MessageToolCall, TextContent
from openhands.sdk.tool import (
    Action,
    Observation,
    Tool,
    ToolDefinition,
    ToolExecutor,
    register_tool as register_tool_public,
    registry as tool_registry,
)


def _make_action_event(
    tool_name: str,
    action: Action,
    tool_call_id: str = "tc1",
) -> ActionEvent:
    """帮助程序创建包含所有必填字段的 ActionEvent。"""
    return ActionEvent(
        source="agent",
        thought=[TextContent(text="test thought")],
        action=action,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_call=MessageToolCall(
            id=tool_call_id,
            name=tool_name,
            arguments="{}",
            origin="completion",
        ),
        llm_response_id="response_1",
    )


# 跟踪测试的执行计数
execution_counts: dict[str, int] = {}


class RerunTestAction(Action):
    """重新运行测试的测试操作。"""

    value: str = "test"


class RerunTestObservation(Observation):
    """测试观测结果以重新运行测试。"""

    result: str = ""
    execution_count: int = 0


class RerunTestExecutor(ToolExecutor[RerunTestAction, RerunTestObservation]):
    """跟踪执行计数的测试执行器。"""

    def __call__(
        self,
        action: RerunTestAction,
        conversation: "LocalConversation | None" = None,
    ) -> RerunTestObservation:
        # 跟踪每个操作值执行的次数
        key = action.value
        execution_counts[key] = execution_counts.get(key, 0) + 1
        return RerunTestObservation.from_text(
            f"executed: {action.value} (count: {execution_counts[key]})",
            result=f"result_{action.value}",
            execution_count=execution_counts[key],
        )


class RerunTestTool(ToolDefinition[RerunTestAction, RerunTestObservation]):
    """用于重新运行测试的测试工具。"""

    @classmethod
    def create(cls, conv_state=None, **params):
        return [
            cls(
                description="A test tool for testing rerun_actions",
                action_type=RerunTestAction,
                observation_type=RerunTestObservation,
                executor=RerunTestExecutor(),
            )
        ]


@pytest.fixture(autouse=True)
def _reset_execution_counts():
    """每次测试前重置执行计数。"""
    execution_counts.clear()
    yield
    execution_counts.clear()


@pytest.fixture(autouse=True)
def _tool_registry_isolation(monkeypatch: pytest.MonkeyPatch):
    """使用monkeypatch 隔离每个测试的工具注册表。

    这确保了测试工具注册时不影响全局注册表并且在每次测试后自动清理。
    """
    # 创建注册表字典的独立副本
    isolated_reg = dict(tool_registry._REG)
    isolated_tool_classes = dict(tool_registry._TOOL_CLASSES)

    # 修补注册表以使用隔离副本
    monkeypatch.setattr(tool_registry, "_REG", isolated_reg)
    monkeypatch.setattr(tool_registry, "_TOOL_CLASSES", isolated_tool_classes)

    # 在隔离的注册表中注册我们的测试工具
    register_tool_public(RerunTestTool.name, RerunTestTool)


class RerunDummyAgent(AgentBase):
    """用于测试 rerun_actions 的虚拟智能体。"""

    def __init__(self, tools=None):
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        super().__init__(llm=llm, tools=tools or [])

    def init_state(
        self, state: ConversationState, on_event: ConversationCallbackType
    ) -> None:
        super().init_state(state, on_event)
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


def test_rerun_actions_empty_conversation():
    """在没有任何操作的对话中测试 rerun_actions。"""
    agent = RerunDummyAgent(tools=[Tool(name="rerun_test", params={})])
    conversation = Conversation(agent=agent)

    # 重新运行空对话应返回 True（无事可做 = 成功）
    result = conversation.rerun_actions()
    assert result is True


def test_rerun_actions_basic():
    """测试基本 rerun_actions 功能。"""
    agent = RerunDummyAgent(tools=[Tool(name="rerun_test", params={})])
    conversation = Conversation(agent=agent)

    # 执行一些工具来创建动作事件
    action1 = RerunTestAction(value="first")
    action2 = RerunTestAction(value="second")

    # 手动添加动作事件来模拟对话历史记录
    conversation._ensure_agent_ready()
    action_event = _make_action_event("rerun_test", action1, "tc1")
    conversation._state.events.append(action_event)

    action_event2 = _make_action_event("rerun_test", action2, "tc2")
    conversation._state.events.append(action_event2)

    # 现在重新运行所有操作
    result = conversation.rerun_actions()

    # 应该已成功执行这两个操作
    assert result is True
    assert execution_counts["first"] == 1
    assert execution_counts["second"] == 1


def test_rerun_actions_preserves_original_observations():
    """测试 rerun_actions 不会修改原始事件日志。"""
    agent = RerunDummyAgent(tools=[Tool(name="rerun_test", params={})])
    conversation = Conversation(agent=agent)

    # 添加动作事件
    conversation._ensure_agent_ready()
    action = RerunTestAction(value="preserve_test")
    action_event = _make_action_event("rerun_test", action, "tc1")
    conversation._state.events.append(action_event)

    # 重新运行之前对事件进行计数
    events_before = len(list(conversation._state.events))

    # 重新运行操作
    result = conversation.rerun_actions()

    # 重新运行后计数事件 - 应该相同
    events_after = len(list(conversation._state.events))

    assert events_before == events_after
    assert result is True


def test_rerun_actions_skips_none_actions():
    """使用 action=None 测试 rerun_actions 是否跳过 ActionEvents。"""
    agent = RerunDummyAgent(tools=[Tool(name="rerun_test", params={})])
    conversation = Conversation(agent=agent)

    conversation._ensure_agent_ready()

    # 添加action=None的动作事件（失败验证）
    action_event_none = ActionEvent(
        source="agent",
        thought=[TextContent(text="test")],
        tool_name="rerun_test",
        tool_call_id="tc1",
        tool_call=MessageToolCall(
            id="tc1", name="rerun_test", arguments="{}", origin="completion"
        ),
        llm_response_id="resp1",
        action=None,  # 失败验证
    )
    conversation._state.events.append(action_event_none)

    # 添加有效的操作事件
    action = RerunTestAction(value="valid")
    action_event_valid = _make_action_event("rerun_test", action, "tc2")
    conversation._state.events.append(action_event_valid)

    # 重新运行应该只执行有效的操作并成功
    result = conversation.rerun_actions()

    assert result is True
    assert execution_counts["valid"] == 1


def test_rerun_actions_missing_tool_raises():
    """测试 rerun_actions 是否会因缺少工具而引发 KeyError。"""
    agent = RerunDummyAgent(tools=[])  # 没有注册工具
    conversation = Conversation(agent=agent)

    conversation._ensure_agent_ready()

    # 为不存在的工具添加操作事件
    action = RerunTestAction(value="test")
    action_event = _make_action_event("rerun_test", action, "tc1")
    conversation._state.events.append(action_event)

    with pytest.raises(KeyError) as exc_info:
        conversation.rerun_actions()

    assert "rerun_test" in str(exc_info.value)
    assert "not found during rerun" in str(exc_info.value)


def test_rerun_can_be_called_manually():
    """测试初始化​​后是否可以手动调用rerun_actions。"""
    agent = RerunDummyAgent(tools=[Tool(name="rerun_test", params={})])
    conversation = Conversation(agent=agent)

    conversation._ensure_agent_ready()
    action = RerunTestAction(value="manual")
    action_event = _make_action_event("rerun_test", action, "tc1")
    conversation._state.events.append(action_event)

    # 手动调用重新运行（不在初始化期间）
    result = conversation.rerun_actions()

    assert result is True
    assert execution_counts["manual"] == 1

    # 可以再打电话
    result2 = conversation.rerun_actions()

    assert result2 is True
    assert execution_counts["manual"] == 2  # 现已执行两次


# =============================================================================
# 使用真实文件操作进行测试
# =============================================================================
# 这些测试验证 rerun_actions 实际上使用真实文件系统操作重现环境状态。
#


class FileWriteAction(Action):
    """将内容写入文件的操作。"""

    filepath: str
    content: str


class FileWriteObservation(Observation):
    """观测结果从文件写入操作返回。"""

    filepath: str = ""
    written: bool = False


class FileWriteExecutor(ToolExecutor[FileWriteAction, FileWriteObservation]):
    """将内容写入真实文件的执行器。"""

    def __call__(
        self,
        action: FileWriteAction,
        conversation: "LocalConversation | None" = None,
    ) -> FileWriteObservation:
        path = Path(action.filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(action.content)
        return FileWriteObservation.from_text(
            f"Written to {action.filepath}",
            filepath=action.filepath,
            written=True,
        )


class FileWriteTool(ToolDefinition[FileWriteAction, FileWriteObservation]):
    """将内容写入文件的工具。"""

    @classmethod
    def create(cls, conv_state=None, **params):
        return [
            cls(
                description="Write content to a file",
                action_type=FileWriteAction,
                observation_type=FileWriteObservation,
                executor=FileWriteExecutor(),
            )
        ]


class FileCreateAction(Action):
    """创建新文件的操作（如果文件存在则失败）。"""

    filepath: str
    content: str


class FileCreateObservation(Observation):
    """观测结果从文件创建操作返回。"""

    filepath: str = ""
    created: bool = False


class FileCreateExecutor(ToolExecutor[FileCreateAction, FileCreateObservation]):
    """创建新文件的执行器（如果存在则失败）。"""

    def __call__(
        self,
        action: FileCreateAction,
        conversation: "LocalConversation | None" = None,
    ) -> FileCreateObservation:
        path = Path(action.filepath)
        if path.exists():
            return FileCreateObservation.from_text(
                f"Error: File {action.filepath} already exists",
                filepath=action.filepath,
                created=False,
                is_error=True,
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(action.content)
        return FileCreateObservation.from_text(
            f"Created {action.filepath}",
            filepath=action.filepath,
            created=True,
        )


class FileCreateTool(ToolDefinition[FileCreateAction, FileCreateObservation]):
    """创建新文件的工具（非幂等）。"""

    @classmethod
    def create(cls, conv_state=None, **params):
        return [
            cls(
                description="Create a new file (fails if exists)",
                action_type=FileCreateAction,
                observation_type=FileCreateObservation,
                executor=FileCreateExecutor(),
            )
        ]


class FailingAction(Action):
    """行动总是失败。"""

    message: str = "fail"


class FailingObservation(Observation):
    """观测结果来自失败的工具。"""

    pass


class FailingExecutor(ToolExecutor[FailingAction, FailingObservation]):
    """总是引发异常的执行器。"""

    def __call__(
        self,
        action: FailingAction,
        conversation: "LocalConversation | None" = None,
    ) -> FailingObservation:
        raise RuntimeError(f"Intentional failure: {action.message}")


class FailingTool(ToolDefinition[FailingAction, FailingObservation]):
    """总是失败的工具。"""

    @classmethod
    def create(cls, conv_state=None, **params):
        return [
            cls(
                description="A tool that always fails",
                action_type=FailingAction,
                observation_type=FailingObservation,
                executor=FailingExecutor(),
            )
        ]


def test_rerun_reproduces_file_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """测试 rerun_actions 是否再现文件系统状态。

    此测试验证主要用例：创建文件、清除工作区、重新运行操作并验证文件是否已重新创建。
    """
    # 注册文件写入工具
    register_tool_public(FileWriteTool.name, FileWriteTool)

    agent = RerunDummyAgent(tools=[Tool(name="file_write", params={})])
    conversation = Conversation(agent=agent)
    conversation._ensure_agent_ready()

    # 创建写入文件的操作
    test_file = tmp_path / "test_file.txt"
    action = FileWriteAction(filepath=str(test_file), content="hello world")
    action_event = _make_action_event("file_write", action, "tc1")
    conversation._state.events.append(action_event)

    # 第一次重新运行创建文件
    result = conversation.rerun_actions()
    assert result is True
    assert test_file.exists()
    assert test_file.read_text() == "hello world"

    # 清除文件
    test_file.unlink()
    assert not test_file.exists()

    # 再次重新运行 - 应重新创建文件
    result2 = conversation.rerun_actions()
    assert result2 is True
    assert test_file.exists()
    assert test_file.read_text() == "hello world"


def test_rerun_non_idempotent_with_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """测试重新运行日志中是否跟踪非幂等操作。

    这验证了记录的非幂等性警告：如果文件已存在，文件创建将失败。 重新运行仍然“成功”（
    工具正确执行），但观测结果显示 is_error=True。
    """
    from openhands.sdk.conversation.event_store import EventLog
    from openhands.sdk.event import ObservationEvent
    from openhands.sdk.io import LocalFileStore

    # 注册文件创建工具（非幂等）
    register_tool_public(FileCreateTool.name, FileCreateTool)

    agent = RerunDummyAgent(tools=[Tool(name="file_create", params={})])
    conversation = Conversation(agent=agent)
    conversation._ensure_agent_ready()

    test_file = tmp_path / "new_file.txt"
    action = FileCreateAction(filepath=str(test_file), content="content")
    action_event = _make_action_event("file_create", action, "tc1")
    conversation._state.events.append(action_event)

    log_dir = tmp_path / "rerun_log"

    # 第一次重新运行成功创建文件
    result = conversation.rerun_actions(rerun_log_path=log_dir)
    assert result is True
    assert test_file.exists()

    # 使用EventLog检查日志
    file_store = LocalFileStore(str(log_dir))
    event_log = EventLog(file_store, dir_path="events")
    assert len(event_log) == 2  # ActionEvent + ObservationEvent
    obs_event = event_log[1]
    assert isinstance(obs_event, ObservationEvent)
    assert isinstance(obs_event.observation, FileCreateObservation)
    assert obs_event.observation.created is True

    # 第二次重新运行 - 文件已存在，返回错误观测结果但仍然成功
    log_dir2 = tmp_path / "rerun_log2"
    result2 = conversation.rerun_actions(rerun_log_path=log_dir2)
    assert result2 is True  # 工具执行正确，只是返回错误

    # 检查第二条日志显示错误观测结果
    file_store2 = LocalFileStore(str(log_dir2))
    event_log2 = EventLog(file_store2, dir_path="events")
    assert len(event_log2) == 2
    obs_event2 = event_log2[1]
    assert isinstance(obs_event2, ObservationEvent)
    assert isinstance(obs_event2.observation, FileCreateObservation)
    assert obs_event2.observation.created is False
    assert obs_event2.observation.is_error is True


def test_rerun_early_exit_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """测试当工具引发异常时重新运行立即退出。

    这将验证重新运行在第一次失败时停止并将部分进度保存到日志中。
    """
    from openhands.sdk.conversation.event_store import EventLog
    from openhands.sdk.event import ObservationEvent
    from openhands.sdk.io import LocalFileStore

    # 注册这两个工具
    register_tool_public(FileWriteTool.name, FileWriteTool)
    register_tool_public(FailingTool.name, FailingTool)

    agent = RerunDummyAgent(
        tools=[
            Tool(name="file_write", params={}),
            Tool(name="failing", params={}),
        ]
    )
    conversation = Conversation(agent=agent)
    conversation._ensure_agent_ready()

    # 添加成功的操作
    test_file1 = tmp_path / "file1.txt"
    action1 = FileWriteAction(filepath=str(test_file1), content="first")
    conversation._state.events.append(_make_action_event("file_write", action1, "tc1"))

    # 添加失败的操作（引发异常）
    action2 = FailingAction(message="intentional")
    conversation._state.events.append(_make_action_event("failing", action2, "tc2"))

    # 添加另一个成功的操作（由于提前退出，应该执行不）
    test_file2 = tmp_path / "file2.txt"
    action3 = FileWriteAction(filepath=str(test_file2), content="second")
    conversation._state.events.append(_make_action_event("file_write", action3, "tc3"))

    log_dir = tmp_path / "rerun_log"

    # 重新运行 - 应在第二个操作中失败并提前退出
    result = conversation.rerun_actions(rerun_log_path=log_dir)

    # 由于失败应返回 False
    assert result is False

    # 应创建第一个文件（失败之前）
    assert test_file1.exists()
    assert test_file1.read_text() == "first"

    # 第二个文件应该不存在（由于提前退出而未执行操作）
    assert not test_file2.exists()

    # 日志应仅包含失败之前的成功操作（第一个操作的 ActionEvent + ObservationEvent = 2 个
    # 事件）
    #
    file_store = LocalFileStore(str(log_dir))
    event_log = EventLog(file_store, dir_path="events")
    assert len(event_log) == 2  # ActionEvent + ObservationEvent 表示第一个动作
    obs_event = event_log[1]
    assert isinstance(obs_event, ObservationEvent)
    assert obs_event.tool_name == "file_write"


def test_rerun_multiple_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """按顺序测试多个文件操作重新运行。"""
    register_tool_public(FileWriteTool.name, FileWriteTool)

    agent = RerunDummyAgent(tools=[Tool(name="file_write", params={})])
    conversation = Conversation(agent=agent)
    conversation._ensure_agent_ready()

    # 创建多个文件写入操作
    files_content = [
        ("file_a.txt", "content A"),
        ("file_b.txt", "content B"),
        ("subdir/file_c.txt", "content C"),
    ]

    for i, (filename, content) in enumerate(files_content):
        action = FileWriteAction(
            filepath=str(tmp_path / filename),
            content=content,
        )
        conversation._state.events.append(
            _make_action_event("file_write", action, f"tc{i}")
        )

    # 重新运行所有操作
    result = conversation.rerun_actions()

    # 所有行动都应该成功
    assert result is True

    # 应创建所有文件
    for filename, expected_content in files_content:
        file_path = tmp_path / filename
        assert file_path.exists(), f"File {filename} should exist"
        assert file_path.read_text() == expected_content
