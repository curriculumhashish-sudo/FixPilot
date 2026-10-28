"""
单元测试用于智能体状态转换。

测试智能体是否在执行状态之间正确转换，特别关注调用 run() 时到 RUNNING 状态的转换。

这解决了问题 #865 的问题：当从 IDLE 状态调用 run() 时，智能体状态未转换为 RUNNING。

测试的状态转移矩阵：
- IDLE -> RUNNING（当调用run()时）
- PAUSED -> RUNNING（暂停后调用run()时）
- WAITING_FOR_CONFIRMATION -> RUNNING（调用run()确认时）
- FINISHED -> IDLE -> RUNNING（完成后发送新消息时）
- STUCK -> IDLE（发送新消息时） -> RUNNING（调用run()时）
- STUCK -> RUNNING（直接调用run()时）
- FINISHED -> 保持不变（run() 立即退出，没有新消息）
"""

import threading
from collections.abc import Sequence
from typing import ClassVar

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event import MessageEvent
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.llm import ImageContent, Message, MessageToolCall, TextContent
from openhands.sdk.testing import TestLLM
from openhands.sdk.tool import (
    Action,
    Observation,
    Tool,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)


class StatusTransitionMockAction(Action):
    """模拟对象操作模式用于测试。"""

    command: str


class StatusTransitionMockObservation(Observation):
    """模拟对象观测结果模式用于测试。"""

    result: str

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text=self.result)]


class StatusCheckingExecutor(
    ToolExecutor[StatusTransitionMockAction, StatusTransitionMockObservation]
):
    """执行时捕获智能体状态的执行器。"""

    def __init__(self, status_during_execution: list[ConversationExecutionStatus]):
        self.status_during_execution: list[ConversationExecutionStatus] = (
            status_during_execution
        )

    def __call__(
        self, action: StatusTransitionMockAction, conversation=None
    ) -> StatusTransitionMockObservation:
        # 捕获执行过程中的智能体状态
        if conversation:
            self.status_during_execution.append(conversation.state.execution_status)
        return StatusTransitionMockObservation(result=f"Executed: {action.command}")


class StatusTransitionTestTool(
    ToolDefinition[StatusTransitionMockAction, StatusTransitionMockObservation]
):
    """用于状态转换测试的具体工具。"""

    name: ClassVar[str] = "test_tool"

    @classmethod
    def create(
        cls, conv_state=None, *, executor: ToolExecutor, **params
    ) -> Sequence["StatusTransitionTestTool"]:
        return [
            cls(
                description="A test tool",
                action_type=StatusTransitionMockAction,
                observation_type=StatusTransitionMockObservation,
                executor=executor,
            )
        ]


def test_execution_status_transitions_to_running_from_idle():
    """测试当从 IDLE 调用 run() 时，智能体状态是否转换为 RUNNING。"""
    status_during_execution: list[ConversationExecutionStatus] = []

    test_tool = StatusTransitionTestTool.create(
        executor=StatusCheckingExecutor(status_during_execution)
    )[0]
    register_tool("test_tool", test_tool)

    # 将 TestLLM 与脚本化响应一起使用
    llm = TestLLM.from_messages(
        [
            Message(role="assistant", content=[TextContent(text="Task completed")]),
        ]
    )
    agent = Agent(llm=llm, tools=[])
    conversation = Conversation(agent=agent)

    # 验证初始状态为 IDLE
    assert conversation.state.execution_status == ConversationExecutionStatus.IDLE

    # 发送消息并运行
    conversation.send_message(Message(role="user", content=[TextContent(text="Hello")]))
    conversation.run()

    # 运行完成后，状态应为 FINISHED
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED

    # 验证我们有智能体回复
    agent_messages = [
        event
        for event in conversation.state.events
        if isinstance(event, MessageEvent) and event.source == "agent"
    ]
    assert len(agent_messages) == 1


def test_execution_status_is_running_during_execution_from_idle():
    """当从 IDLE 启动时，测试执行期间智能体状态是否为 RUNNING。"""
    status_during_execution: list[ConversationExecutionStatus] = []
    execution_started = threading.Event()
    # Barrier 让 main 线程在执行器返回之前观察 RUNNING，从而防止在我们检查之前运行循环继
    # 续进行的竞争。
    #
    main_thread_observed = threading.Event()

    class SignalingExecutor(
        ToolExecutor[StatusTransitionMockAction, StatusTransitionMockObservation]
    ):
        """执行器在执行开始时发出信号并捕获状态。"""

        def __call__(
            self, action: StatusTransitionMockAction, conversation=None
        ) -> StatusTransitionMockObservation:
            # 发出执行已开始的信号，然后等待 main 线程在返回之前观察状态，这样就不会出现
            # 竞争。
            #
            execution_started.set()
            main_thread_observed.wait(timeout=2.0)
            # 执行期间捕获智能体状态（返回之前）
            if conversation:
                status_during_execution.append(conversation.state.execution_status)
            return StatusTransitionMockObservation(result=f"Executed: {action.command}")

    test_tool = StatusTransitionTestTool.create(executor=SignalingExecutor())[0]
    register_tool("test_tool", test_tool)

    # 将 TestLLM 与脚本化响应一起使用：首先是工具调用，然后是完成
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[
                    MessageToolCall(
                        id="call_1",
                        name="test_tool",
                        arguments='{"command": "test_command"}',
                        origin="completion",
                    )
                ],
            ),
            Message(role="assistant", content=[TextContent(text="Task completed")]),
        ]
    )
    agent = Agent(
        llm=llm,
        tools=[Tool(name="test_tool")],
    )
    conversation = Conversation(agent=agent)

    # 验证初始状态为 IDLE
    assert conversation.state.execution_status == ConversationExecutionStatus.IDLE

    # 发送消息
    conversation.send_message(
        Message(role="user", content=[TextContent(text="Execute command")])
    )

    # 在单独的线程中运行，以便我们可以在执行期间检查状态
    run_complete = threading.Event()
    status_during_run: list[ConversationExecutionStatus | None] = [None]

    def run_agent():
        conversation.run()
        run_complete.set()

    t = threading.Thread(target=run_agent, daemon=True)
    t.start()

    # 等待执行开始
    assert execution_started.wait(timeout=2.0), "Execution never started"

    # 在执行器仍持有时检查状态（无竞赛）
    status_during_run[0] = conversation.state.execution_status

    # 释放执行者
    main_thread_observed.set()

    # 等待运行完成
    assert run_complete.wait(timeout=2.0), "Run did not complete"
    t.join(timeout=0.1)

    # 执行期间验证状态为 RUNNING
    assert status_during_run[0] == ConversationExecutionStatus.RUNNING, (
        f"Expected RUNNING status during execution, got {status_during_run[0]}"
    )

    # 运行完成后，状态应为 FINISHED
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED


def test_execution_status_transitions_to_running_from_paused():
    """测试当 run() 被调用时智能体状态是否转换为 RUNNING
    PAUSED."""
    # 将 TestLLM 与脚本化响应一起使用
    llm = TestLLM.from_messages(
        [
            Message(role="assistant", content=[TextContent(text="Task completed")]),
        ]
    )
    agent = Agent(llm=llm, tools=[])
    conversation = Conversation(agent=agent)

    # 暂停谈话
    conversation.pause()
    assert conversation.state.execution_status == ConversationExecutionStatus.PAUSED

    # 发送消息并运行
    conversation.send_message(Message(role="user", content=[TextContent(text="Hello")]))
    conversation.run()

    # 运行完成后，状态应为 FINISHED
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED

    # 验证我们有智能体回复
    agent_messages = [
        event
        for event in conversation.state.events
        if isinstance(event, MessageEvent) and event.source == "agent"
    ]
    assert len(agent_messages) == 1


def test_execution_status_transitions_from_waiting_for_confirmation():
    """调用 run() 时测试 WAITING_FOR_CONFIRMATION -> RUNNING 转换。"""
    from openhands.sdk.security.confirmation_policy import AlwaysConfirm

    test_tool = StatusTransitionTestTool.create(executor=StatusCheckingExecutor([]))[0]
    register_tool("test_tool", test_tool)

    # 将 TestLLM 与脚本化响应一起使用：首先是工具调用，然后是完成
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[
                    MessageToolCall(
                        id="call_1",
                        name="test_tool",
                        arguments='{"command": "test_command"}',
                        origin="completion",
                    )
                ],
            ),
            Message(role="assistant", content=[TextContent(text="Task completed")]),
        ]
    )

    agent = Agent(llm=llm, tools=[Tool(name="test_tool")])
    conversation = Conversation(agent=agent)
    conversation.set_confirmation_policy(AlwaysConfirm())

    # 发送消息并运行 - 应停在 WAITING_FOR_CONFIRMATION
    conversation.send_message(
        Message(role="user", content=[TextContent(text="Execute command")])
    )
    conversation.run()

    # 应该等待确认
    assert (
        conversation.state.execution_status
        == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
    )

    # 再次调用 run - 这会确认并应转换为 RUNNING，然后转换为 FINISHED
    conversation.run()

    # 确认执行后，应为FINISHED
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED


def test_execution_status_finished_to_idle_to_running():
    """发送新消息时测试 FINISHED -> IDLE -> RUNNING 转换。"""
    # 使用 TestLLM 和两个脚本化响应（每次运行一个）
    llm = TestLLM.from_messages(
        [
            Message(role="assistant", content=[TextContent(text="Task completed")]),
            Message(role="assistant", content=[TextContent(text="Task completed")]),
        ]
    )
    agent = Agent(llm=llm, tools=[])
    conversation = Conversation(agent=agent)

    # 第一次对话 - 应以 FINISHED 结束
    conversation.send_message(
        Message(role="user", content=[TextContent(text="First task")])
    )
    conversation.run()
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED

    # 发送新消息 - 应转换为 IDLE
    conversation.send_message(
        Message(role="user", content=[TextContent(text="Second task")])
    )
    assert conversation.state.execution_status == ConversationExecutionStatus.IDLE

    # 再次运行 - 应先转换为 RUNNING，然后转换为 FINISHED
    conversation.run()
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED


def test_run_exits_immediately_when_already_finished():
    """测试当状态已为 FINISHED 时 run() 是否立即退出。"""
    # 将 TestLLM 与单个脚本响应一起使用
    llm = TestLLM.from_messages(
        [
            Message(role="assistant", content=[TextContent(text="Task completed")]),
        ]
    )
    agent = Agent(llm=llm, tools=[])
    conversation = Conversation(agent=agent)

    # 完成任务
    conversation.send_message(Message(role="user", content=[TextContent(text="Task")]))
    conversation.run()
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED

    # 再次调用运行而不发送新消息应立即退出而不再次调用 LLM
    #
    initial_call_count = llm.call_count
    conversation.run()

    # 状态仍应为 FINISHED
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED
    # LLM 不应再次调用
    assert llm.call_count == initial_call_count


def test_run_recovers_from_stuck():
    """测试 run() 是否重置 STUCK 状态并让智能体继续。

    当对话为 STUCK (e.g. 卡住检测器已触发或之前会话的已持久化 STUCK 状态），调用
    run() 应将状态重置为 RUNNING，以便智能体可以重试。
    如果没有此重置，已持久化 STUCK 状态将永久终止会话。
    """
    # 提供一个完成响应，以便智能体在解粘后完成。
    llm = TestLLM.from_messages(
        [Message(role="assistant", content=[TextContent(text="Recovered")])]
    )
    agent = Agent(llm=llm, tools=[])
    conversation = Conversation(agent=agent)

    # 播种用户消息，以便智能体可以使用上下文
    conversation.send_message(
        Message(role="user", content=[TextContent(text="Please continue")])
    )

    # 模拟上一个会话的卡住检测已持久化
    conversation._state.execution_status = ConversationExecutionStatus.STUCK

    conversation.run()

    # 智能体应该已经恢复并正常完成
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED
    assert llm.call_count == 1


def test_send_message_resets_stuck_to_idle():
    """当新用户消息到达时测试 STUCK → IDLE 转换。

    新的用户消息是取消对话的隐式信号，类似于 FINISHED → IDLE 的工作原理。
    """
    llm = TestLLM.from_messages(
        [Message(role="assistant", content=[TextContent(text="Done")])]
    )
    agent = Agent(llm=llm, tools=[])
    conversation = Conversation(agent=agent)

    # 模拟卡住状态
    conversation._state.execution_status = ConversationExecutionStatus.STUCK

    # 发送新消息应重置 STUCK → IDLE
    conversation.send_message(
        Message(role="user", content=[TextContent(text="Try again")])
    )
    assert conversation.state.execution_status == ConversationExecutionStatus.IDLE

    # 运行应正常进行：IDLE → RUNNING → FINISHED
    conversation.run()
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED


def test_execution_status_error_on_max_iterations():
    """当达到最大迭代次数时，测试状态是否设置为 ERROR，并显示清晰的消息。"""

    status_during_execution: list[ConversationExecutionStatus] = []
    events_received: list = []

    test_tool = StatusTransitionTestTool.create(
        executor=StatusCheckingExecutor(status_during_execution)
    )[0]
    register_tool("test_tool", test_tool)

    # 创建一条将重复返回的工具调用消息
    tool_call_message = Message(
        role="assistant",
        content=[TextContent(text="")],
        tool_calls=[
            MessageToolCall(
                id="call_1",
                name="test_tool",
                arguments='{"command": "test_command"}',
                origin="completion",
            )
        ],
    )

    # 使用具有足够响应的 TestLLM 来达到最大迭代次数
    # max_iteration_per_run=2 means we need at least 2 tool call responses
    llm = TestLLM.from_messages(
        [
            tool_call_message,
            tool_call_message,
            tool_call_message,  # 额外以备不时之需
        ]
    )
    agent = Agent(llm=llm, tools=[Tool(name="test_tool")])
    # 将max_iteration_per_run设置为2可以快速达到极限
    conversation = Conversation(
        agent=agent,
        max_iteration_per_run=2,
        callbacks=[lambda e: events_received.append(e)],
    )

    # 发送消息并运行
    conversation.send_message(
        Message(role="user", content=[TextContent(text="Execute command")])
    )
    conversation.run()

    # 状态应为 ERROR
    assert conversation.state.execution_status == ConversationExecutionStatus.ERROR

    # 应该发出带有明确消息的 ConversationErrorEvent
    error_events = [e for e in events_received if isinstance(e, ConversationErrorEvent)]
    assert len(error_events) == 1
    assert error_events[0].code == "MaxIterationsReached"
    assert "maximum iterations limit" in error_events[0].detail
    assert "(2)" in error_events[0].detail  # max_iteration_per_run 值


def test_execution_status_finished_on_final_iteration():
    """当智能体完成其最终迭代时，FINISHED 被保留。

    回归测试：当任务恰好在 max_iteration_per_run 边界上完成时，智能体的 FINISHED 状态
    被 ERROR 覆盖。
    """

    events_received: list = []

    test_tool = StatusTransitionTestTool.create(executor=StatusCheckingExecutor([]))[0]
    register_tool("test_tool", test_tool)

    # 两次工具调用迭代，然后是第三次（最终）迭代的文本响应。 纯文本助理消息会导致智能体
    # 将状态设置为 FINISHED。
    #
    tool_call_message = Message(
        role="assistant",
        content=[TextContent(text="")],
        tool_calls=[
            MessageToolCall(
                id="call_1",
                name="test_tool",
                arguments='{"command": "test_command"}',
                origin="completion",
            )
        ],
    )
    finish_message = Message(
        role="assistant", content=[TextContent(text="Task completed successfully")]
    )

    llm = TestLLM.from_messages(
        [
            tool_call_message,  # 迭代1
            tool_call_message,  # 迭代2
            finish_message,  # 迭代 3（最终）- 智能体在此完成
        ]
    )
    agent = Agent(llm=llm, tools=[Tool(name="test_tool")])
    conversation = Conversation(
        agent=agent,
        max_iteration_per_run=3,
        callbacks=[lambda e: events_received.append(e)],
    )

    conversation.send_message(
        Message(role="user", content=[TextContent(text="Execute command")])
    )
    conversation.run()

    # 状态必须为 FINISHED，而不是 ERROR
    assert (
        conversation.state.execution_status == ConversationExecutionStatus.FINISHED
    ), (
        f"Expected FINISHED but got {conversation.state.execution_status}. "
        "Agent completing on the final iteration should not be treated as an error."
    )

    # 不应发出 MaxIterationsReached 错误事件
    error_events = [e for e in events_received if isinstance(e, ConversationErrorEvent)]
    max_iter_errors = [e for e in error_events if e.code == "MaxIterationsReached"]
    assert len(max_iter_errors) == 0, (
        "Expected no MaxIterationsReached error when agent finishes on final iteration"
    )


def test_execution_status_error_on_max_budget(tmp_path):
    """当超出成本预算时，以 ERROR + MaxBudgetReached 停止运行，
    甚至在达到迭代上限之前。"""
    from openhands.sdk.conversation.impl.local_conversation import LocalConversation
    from openhands.sdk.llm.utils.metrics import Metrics

    events_received: list = []
    test_tool = StatusTransitionTestTool.create(executor=StatusCheckingExecutor([]))[0]
    register_tool("test_tool", test_tool)

    tool_call_message = Message(
        role="assistant",
        content=[TextContent(text="")],
        tool_calls=[
            MessageToolCall(
                id="call_1",
                name="test_tool",
                arguments='{"command": "test_command"}',
                origin="completion",
            )
        ],
    )
    llm = TestLLM.from_messages([tool_call_message] * 5)
    agent = Agent(llm=llm, tools=[Tool(name="test_tool")])
    # 高迭代上限，因此 BUDGET 是停止运行的原因。
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        visualizer=None,
        delete_on_close=False,
        max_iteration_per_run=10,
        max_budget_per_run=1.0,
        callbacks=[lambda e: events_received.append(e)],
    )
    conversation.send_message(
        Message(role="user", content=[TextContent(text="Execute command")])
    )
    # 种子前支出超出预算（TestLLM 不产生实际成本）。
    conversation.conversation_stats.usage_to_metrics["spend"] = Metrics(
        accumulated_cost=5.0
    )
    conversation.run()

    assert conversation.state.execution_status == ConversationExecutionStatus.ERROR
    error_events = [e for e in events_received if isinstance(e, ConversationErrorEvent)]
    budget_errors = [e for e in error_events if e.code == "MaxBudgetReached"]
    assert len(budget_errors) == 1
    assert "maximum budget limit" in budget_errors[0].detail
    # 预算阻止了它，而不是迭代上限。
    assert not any(e.code == "MaxIterationsReached" for e in error_events)


def test_finished_preserved_even_when_over_budget(tmp_path):
    """即使超出预算，完成的运行也会保留 FINISHED。"""
    from openhands.sdk.conversation.impl.local_conversation import LocalConversation
    from openhands.sdk.llm.utils.metrics import Metrics

    events_received: list = []
    # 纯文本响应 -> 智能体在第一次迭代时完成。
    finish_message = Message(
        role="assistant", content=[TextContent(text="Task completed")]
    )
    llm = TestLLM.from_messages([finish_message])
    agent = Agent(llm=llm, tools=[])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        visualizer=None,
        delete_on_close=False,
        max_iteration_per_run=10,
        max_budget_per_run=1.0,
        callbacks=[lambda e: events_received.append(e)],
    )
    conversation.send_message(Message(role="user", content=[TextContent(text="Do it")]))
    conversation.conversation_stats.usage_to_metrics["spend"] = Metrics(
        accumulated_cost=5.0
    )
    conversation.run()

    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED
    error_events = [e for e in events_received if isinstance(e, ConversationErrorEvent)]
    assert not any(e.code == "MaxBudgetReached" for e in error_events)


def test_agent_mark_conversation_finished(tmp_path):
    """Agent._mark_conversation_finished直接设置FINISHED状态。"""
    from openhands.sdk.conversation.impl.local_conversation import LocalConversation

    llm = TestLLM.from_messages([])
    agent = Agent(llm=llm, tools=[])
    conversation = LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        visualizer=None,
    )
    conversation.state.execution_status = ConversationExecutionStatus.RUNNING

    Agent._mark_conversation_finished(conversation.state)
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED
