import uuid

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.conversation.stuck_detector import (
    MAX_EVENTS_TO_SCAN_FOR_STUCK_DETECTION,
    StuckDetector,
)
from openhands.sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    MessageEvent,
    ObservationEvent,
)
from openhands.sdk.llm import (
    LLM,
    Message,
    MessageToolCall,
    TextContent,
)
from openhands.sdk.workspace import LocalWorkspace
from openhands.tools.terminal.definition import (
    TerminalAction,
    TerminalObservation,
)


def test_history_too_short():
    """测试当事件太少时卡住的检测器返回 False。"""
    # 创建最小智能体进行测试
    llm = LLM(model="gpt-4o-mini", usage_id="test-llm")
    agent = Agent(llm=llm)
    state = ConversationState.create(
        id=uuid.uuid4(), agent=agent, workspace=LocalWorkspace(working_dir="/tmp")
    )
    stuck_detector = StuckDetector(state)

    # 添加用户留言
    user_message = MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="Hello")]),
    )
    state.events.append(user_message)

    # 添加单个操作-观测结果对
    action = ActionEvent(
        source="agent",
        thought=[TextContent(text="I need to run ls command")],
        action=TerminalAction(command="ls"),
        tool_name="terminal",
        tool_call_id="call_1",
        tool_call=MessageToolCall(
            id="call_1",
            name="terminal",
            arguments='{"command": "ls"}',
            origin="completion",
        ),
        llm_response_id="response_1",
    )
    state.events.append(action)

    observation = ObservationEvent(
        source="environment",
        observation=TerminalObservation.from_text(
            text="file1.txt\nfile2.txt",
            command="ls",
            exit_code=0,
        ),
        action_id=action.id,
        tool_name="terminal",
        tool_call_id="call_1",
    )
    state.events.append(observation)

    # 用户消息后不应仅停留在一对操作观测结果上
    assert stuck_detector.is_stuck() is False


class _SpySequence:
    def __init__(self, items):
        self._items = list(items)
        self.slice_requests = []

    def __len__(self):
        return len(self._items)

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            self.slice_requests.append(idx)
            return self._items[idx]
        return self._items[idx]


class _SpyState:
    def __init__(self, events):
        self.events = events

    def active_branch(self, limit=None):
        # 线性对话的活动分支是整个日志； ``limit`` 取尾部。 通过间谍切片进行镜像，因此“
        # 仅触及最后 N 个事件”的断言仍然成立。
        #
        return list(self.events[-limit:] if limit is not None else self.events)


def test_is_stuck_uses_only_recent_event_window():
    llm = LLM(model="gpt-4o-mini", usage_id="test-llm")
    Agent(llm=llm)

    # 创建 50 个旧事件（不应扫描）。
    old_events = [
        MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text=f"old-{i}")]),
        )
        for i in range(50)
    ]

    # 确保最后 20 个事件包含用户消息和重复循环。
    last_user = MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="start")]),
    )

    loop_events = []
    for i in range(4):
        action = ActionEvent(
            source="agent",
            thought=[TextContent(text="I need to run ls command")],
            action=TerminalAction(command="ls"),
            tool_name="terminal",
            tool_call_id=f"call_{i}",
            tool_call=MessageToolCall(
                id=f"call_{i}",
                name="terminal",
                arguments='{"command": "ls"}',
                origin="completion",
            ),
            llm_response_id=f"response_{i}",
        )
        loop_events.append(action)
        loop_events.append(
            ObservationEvent(
                source="environment",
                observation=TerminalObservation.from_text(
                    text="file1.txt\nfile2.txt",
                    command="ls",
                    exit_code=0,
                ),
                action_id=action.id,
                tool_name="terminal",
                tool_call_id=f"call_{i}",
            )
        )

    # 添加一些填充事件，使总长度 > 20。
    filler = [
        MessageEvent(
            source="agent",
            llm_message=Message(role="assistant", content=[TextContent(text="ok")]),
        )
        for _ in range(3)
    ]

    all_events = old_events + [last_user] + filler + loop_events
    spy_events = _SpySequence(all_events)

    stuck_detector = StuckDetector(_SpyState(spy_events))  # pyright: ignore[reportArgumentType]
    assert stuck_detector.is_stuck() is True

    # 必须请求仅覆盖最后 20 个项目的单个切片。
    assert spy_events.slice_requests
    sl = spy_events.slice_requests[0]
    assert sl.step is None
    assert sl.stop is None
    assert sl.start == -MAX_EVENTS_TO_SCAN_FOR_STUCK_DETECTION


def test_is_stuck_without_recent_user_message_still_detects_loop():
    llm = LLM(model="gpt-4o-mini", usage_id="test-llm")
    Agent(llm=llm)

    # 最近 20 个窗口中根本没有用户消息。
    filler = [
        MessageEvent(
            source="agent",
            llm_message=Message(role="assistant", content=[TextContent(text="ok")]),
        )
        for _ in range(12)
    ]

    loop_events = []
    for i in range(4):
        action = ActionEvent(
            source="agent",
            thought=[TextContent(text="I need to run ls command")],
            action=TerminalAction(command="ls"),
            tool_name="terminal",
            tool_call_id=f"call_{i}",
            tool_call=MessageToolCall(
                id=f"call_{i}",
                name="terminal",
                arguments='{"command": "ls"}',
                origin="completion",
            ),
            llm_response_id=f"response_{i}",
        )
        loop_events.append(action)
        loop_events.append(
            ObservationEvent(
                source="environment",
                observation=TerminalObservation.from_text(
                    text="file1.txt\nfile2.txt",
                    command="ls",
                    exit_code=0,
                ),
                action_id=action.id,
                tool_name="terminal",
                tool_call_id=f"call_{i}",
            )
        )

    all_events = filler + loop_events  # 12 + 8 == 20
    spy_events = _SpySequence(all_events)

    stuck_detector = StuckDetector(_SpyState(spy_events))  # pyright: ignore[reportArgumentType]
    assert stuck_detector.is_stuck() is True


def test_is_stuck_with_fewer_than_20_events_still_detects_loop():
    llm = LLM(model="gpt-4o-mini", usage_id="test-llm")
    Agent(llm=llm)

    # 事件总数 < 20（8 个事件 == 4 个操作-观测结果对）
    loop_events = []
    for i in range(4):
        action = ActionEvent(
            source="agent",
            thought=[TextContent(text="I need to run ls command")],
            action=TerminalAction(command="ls"),
            tool_name="terminal",
            tool_call_id=f"call_{i}",
            tool_call=MessageToolCall(
                id=f"call_{i}",
                name="terminal",
                arguments='{"command": "ls"}',
                origin="completion",
            ),
            llm_response_id=f"response_{i}",
        )
        loop_events.append(action)
        loop_events.append(
            ObservationEvent(
                source="environment",
                observation=TerminalObservation.from_text(
                    text="file1.txt\nfile2.txt",
                    command="ls",
                    exit_code=0,
                ),
                action_id=action.id,
                tool_name="terminal",
                tool_call_id=f"call_{i}",
            )
        )

    spy_events = _SpySequence(loop_events)

    stuck_detector = StuckDetector(_SpyState(spy_events))  # pyright: ignore[reportArgumentType]
    assert stuck_detector.is_stuck() is True

    # 仍然使用单个负片作为扫描窗口。
    assert spy_events.slice_requests
    sl = spy_events.slice_requests[0]
    assert sl.start == -MAX_EVENTS_TO_SCAN_FOR_STUCK_DETECTION


def test_repeating_action_observation_not_stuck_less_than_4_repeats():
    """测试重复动作-观测结果循环的检测。"""
    llm = LLM(model="gpt-4o-mini", usage_id="test-llm")
    agent = Agent(llm=llm)
    state = ConversationState.create(
        id=uuid.uuid4(), agent=agent, workspace=LocalWorkspace(working_dir="/tmp")
    )
    stuck_detector = StuckDetector(state)

    # 先添加用户留言
    user_message = MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="Please run ls")]),
    )
    state.events.append(user_message)

    # 添加 3 个相同的 action-观测结果对以触发卡住检测
    for i in range(3):
        action = ActionEvent(
            source="agent",
            thought=[TextContent(text="I need to run ls command")],
            action=TerminalAction(command="ls"),
            tool_name="terminal",
            tool_call_id=f"call_{i}",
            tool_call=MessageToolCall(
                id=f"call_{i}",
                name="terminal",
                arguments='{"command": "ls"}',
                origin="completion",
            ),
            llm_response_id=f"response_{i}",
        )
        state.events.append(action)

        observation = ObservationEvent(
            source="environment",
            observation=TerminalObservation.from_text(
                text="file1.txt\nfile2.txt",
                command="ls",
                exit_code=0,
            ),
            action_id=action.id,
            tool_name="terminal",
            tool_call_id=f"call_{i}",
        )
        state.events.append(observation)

    # 应该被 4 个相同的 action-观测结果对卡住
    assert stuck_detector.is_stuck() is False


def test_repeating_action_observation_stuck():
    """测试重复动作-观测结果循环的检测。"""
    llm = LLM(model="gpt-4o-mini", usage_id="test-llm")
    agent = Agent(llm=llm)
    state = ConversationState.create(
        id=uuid.uuid4(), agent=agent, workspace=LocalWorkspace(working_dir="/tmp")
    )
    stuck_detector = StuckDetector(state)

    # 先添加用户留言
    user_message = MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="Please run ls")]),
    )
    state.events.append(user_message)

    # 添加 4 个相同的 action-观测结果对以触发卡住检测
    for i in range(4):
        action = ActionEvent(
            source="agent",
            thought=[TextContent(text="I need to run ls command")],
            action=TerminalAction(command="ls"),
            tool_name="terminal",
            tool_call_id=f"call_{i}",
            tool_call=MessageToolCall(
                id=f"call_{i}",
                name="terminal",
                arguments='{"command": "ls"}',
                origin="completion",
            ),
            llm_response_id=f"response_{i}",
        )
        state.events.append(action)

        observation = ObservationEvent(
            source="environment",
            observation=TerminalObservation.from_text(
                text="file1.txt\nfile2.txt",
                command="ls",
                exit_code=0,
            ),
            action_id=action.id,
            tool_name="terminal",
            tool_call_id=f"call_{i}",
        )
        state.events.append(observation)

    # 应该被 4 个相同的 action-观测结果对卡住
    assert stuck_detector.is_stuck() is True


def test_repeating_action_error_nudges_before_stuck():
    """达到门槛时会轻推一次； 再重复一次就很难了。"""
    llm = LLM(model="gpt-4o-mini", usage_id="test-llm")
    agent = Agent(llm=llm)
    state = ConversationState.create(
        id=uuid.uuid4(), agent=agent, workspace=LocalWorkspace(working_dir="/tmp")
    )
    stuck_detector = StuckDetector(state)

    # 先添加用户留言
    user_message = MessageEvent(
        source="user",
        llm_message=Message(
            role="user", content=[TextContent(text="Please run the invalid command")]
        ),
    )
    state.events.append(user_message)

    def create_action_and_error(i):
        action = ActionEvent(
            source="agent",
            thought=[TextContent(text="I need to run invalid_command")],
            action=TerminalAction(command="invalid_command"),
            tool_name="terminal",
            tool_call_id=f"call_{i}",
            tool_call=MessageToolCall(
                id=f"call_{i}",
                name="terminal",
                arguments='{"command": "invalid_command"}',
                origin="completion",
            ),
            llm_response_id=f"response_{i}",
        )
        error = AgentErrorEvent(
            source="agent",
            error="Command 'invalid_command' not found",
            tool_call_id=action.tool_call_id,
            tool_name=action.tool_name,
        )
        return action, error

    # 添加 2 个导致错误的相同操作
    for i in range(2):
        action, error = create_action_and_error(i)
        state.events.append(action)
        state.events.append(error)

    # 2对：没有卡住，还没有轻推
    assert stuck_detector.is_stuck() is False
    assert stuck_detector.get_action_error_nudge() is None

    # 第三对达到阈值：轻推，尚未卡住
    action, error = create_action_and_error(2)
    state.events.append(action)
    state.events.append(error)

    assert stuck_detector.is_stuck() is False
    nudge = stuck_detector.get_action_error_nudge()
    assert nudge is not None
    assert "terminal" in nudge
    assert "Command 'invalid_command' not found" in nudge

    # 尽管有轻推，第四对：卡住了
    action, error = create_action_and_error(3)
    state.events.append(action)
    state.events.append(error)

    assert stuck_detector.is_stuck() is True
    assert stuck_detector.get_action_error_nudge() is None


def test_agent_monologue_stuck():
    """测试检测智能体独白（无需用户输入的重复消息）。"""
    llm = LLM(model="gpt-4o-mini", usage_id="test-llm")
    agent = Agent(llm=llm)
    state = ConversationState.create(
        id=uuid.uuid4(), agent=agent, workspace=LocalWorkspace(working_dir="/tmp")
    )
    stuck_detector = StuckDetector(state)

    # 先添加用户留言
    user_message = MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="Hello")]),
    )
    state.events.append(user_message)

    # 添加 3 条连续的智能体消息（独白）
    for i in range(3):
        agent_message = MessageEvent(
            source="agent",
            llm_message=Message(
                role="assistant", content=[TextContent(text=f"I'm thinking... {i}")]
            ),
        )
        state.events.append(agent_message)

    # 应该因智能体独白而卡住
    assert stuck_detector.is_stuck() is True


def test_not_stuck_with_different_actions():
    """测试不同的操作不会触发卡住检测。"""
    llm = LLM(model="gpt-4o-mini", usage_id="test-llm")
    agent = Agent(llm=llm)
    state = ConversationState.create(
        id=uuid.uuid4(), agent=agent, workspace=LocalWorkspace(working_dir="/tmp")
    )
    stuck_detector = StuckDetector(state)

    # 先添加用户留言
    user_message = MessageEvent(
        source="user",
        llm_message=Message(
            role="user", content=[TextContent(text="Please run different commands")]
        ),
    )
    state.events.append(user_message)

    # 添加不同的动作
    commands = ["ls", "pwd", "whoami", "date"]
    for i, cmd in enumerate(commands):
        action = ActionEvent(
            source="agent",
            thought=[TextContent(text=f"I need to run {cmd} command")],
            action=TerminalAction(command=cmd),
            tool_name="terminal",
            tool_call_id=f"call_{i}",
            tool_call=MessageToolCall(
                id=f"call_{i}",
                name="terminal",
                arguments=f'{{"command": "{cmd}"}}',
                origin="completion",
            ),
            llm_response_id=f"response_{i}",
        )
        state.events.append(action)

        observation = ObservationEvent(
            source="environment",
            observation=TerminalObservation.from_text(
                text=f"output from {cmd}",
                command=cmd,
                exit_code=0,
            ),
            action_id=action.id,
            tool_name="terminal",
            tool_call_id=f"call_{i}",
        )
        state.events.append(observation)

    # 不应该被不同的行动所困扰
    assert stuck_detector.is_stuck() is False


def test_reset_after_user_message():
    """测试卡住检测是否在收到新用户消息后重置。"""
    llm = LLM(model="gpt-4o-mini", usage_id="test-llm")
    agent = Agent(llm=llm)
    state = ConversationState.create(
        id=uuid.uuid4(), agent=agent, workspace=LocalWorkspace(working_dir="/tmp")
    )
    stuck_detector = StuckDetector(state)

    # 添加初始用户消息
    user_message = MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="Please run ls")]),
    )
    state.events.append(user_message)

    # 添加 4 个相同的 action-观测结果对以触发卡住检测
    for i in range(4):
        action = ActionEvent(
            source="agent",
            thought=[TextContent(text="I need to run ls command")],
            action=TerminalAction(command="ls"),
            tool_name="terminal",
            tool_call_id=f"call_{i}",
            tool_call=MessageToolCall(
                id=f"call_{i}",
                name="terminal",
                arguments='{"command": "ls"}',
                origin="completion",
            ),
            llm_response_id=f"response_{i}",
        )
        state.events.append(action)

        observation = ObservationEvent(
            source="environment",
            observation=TerminalObservation.from_text(
                text="file1.txt\nfile2.txt",
                command="ls",
                exit_code=0,
            ),
            action_id=action.id,
            tool_name="terminal",
            tool_call_id=f"call_{i}",
        )
        state.events.append(observation)

    # 应该被卡住
    assert stuck_detector.is_stuck() is True

    # 添加新用户消息
    new_user_message = MessageEvent(
        source="user",
        llm_message=Message(
            role="user", content=[TextContent(text="Try something else")]
        ),
    )
    state.events.append(new_user_message)

    # 新用户消息后不应卡住（历史记录被重置）
    assert stuck_detector.is_stuck() is False

    # 在用户消息后添加一项操作 - 仍然没有卡住
    action = ActionEvent(
        source="agent",
        thought=[TextContent(text="I'll try pwd command")],
        action=TerminalAction(command="pwd"),
        tool_name="terminal",
        tool_call_id="call_new",
        tool_call=MessageToolCall(
            id="call_new",
            name="terminal",
            arguments='{"command": "pwd"}',
            origin="completion",
        ),
        llm_response_id="response_new",
    )
    state.events.append(action)

    observation = ObservationEvent(
        source="environment",
        observation=TerminalObservation.from_text(
            text="/home/user", command="pwd", exit_code=0
        ),
        action_id=action.id,
        tool_name="terminal",
        tool_call_id="call_new",
    )
    state.events.append(observation)

    # 在用户发送消息后仍然没有只进行一项操作
    assert stuck_detector.is_stuck() is False
