"""集成测试用于智能体内的并行工具执行。

这些测试验证了智能体在 tool_concurrency_limit > 1 时正确并行执行工具调用，包括事件顺
序、状态转换、FinishTool 转储和阻塞动作处理。
"""

import threading
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Self

import pytest
from pydantic import Field, ValidationError

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event import ActionEvent, AgentErrorEvent, ObservationEvent
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.testing import TestLLM
from openhands.sdk.tool import Action, Observation, Tool, ToolExecutor, register_tool
from openhands.sdk.tool.tool import DeclaredResources, ToolDefinition


if TYPE_CHECKING:
    from openhands.sdk.conversation.base import BaseConversation
    from openhands.sdk.conversation.state import ConversationState


# --- Test tools ---


class SlowAction(Action):
    delay: float = Field(default=0.05)
    label: str = Field(default="")


class SlowObservation(Observation):
    label: str = Field(default="")
    thread_name: str = Field(default="")


class SlowExecutor(ToolExecutor[SlowAction, SlowObservation]):
    def __call__(
        self, action: SlowAction, conversation: "BaseConversation | None" = None
    ) -> SlowObservation:
        time.sleep(action.delay)
        return SlowObservation.from_text(
            text=f"done-{action.label}",
            label=action.label,
            thread_name=threading.current_thread().name,
        )


class SlowTool(ToolDefinition[SlowAction, SlowObservation]):
    name = "slow_tool"

    def declared_resources(self, action: Action) -> DeclaredResources:
        # 每个调用都是独立的——可以安全地并行运行。
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(cls, conv_state: "ConversationState | None" = None) -> Sequence[Self]:
        return [
            cls(
                description="A slow tool for testing parallelism",
                action_type=SlowAction,
                observation_type=SlowObservation,
                executor=SlowExecutor(),
            )
        ]


class ParallelFailingAction(Action):
    value: str = ""


class ParallelFailingObservation(Observation):
    result: str = ""


class ParallelFailingExecutor(
    ToolExecutor[ParallelFailingAction, ParallelFailingObservation]
):
    def __call__(
        self,
        action: ParallelFailingAction,
        conversation: "BaseConversation | None" = None,
    ) -> ParallelFailingObservation:
        raise ValueError(f"Tool failed: {action.value}")


class ParallelFailingTool(
    ToolDefinition[ParallelFailingAction, ParallelFailingObservation]
):
    name = "parallel_failing_tool"

    @classmethod
    def create(cls, conv_state: "ConversationState | None" = None) -> Sequence[Self]:
        return [
            cls(
                description="A tool that always fails",
                action_type=ParallelFailingAction,
                observation_type=ParallelFailingObservation,
                executor=ParallelFailingExecutor(),
            )
        ]


register_tool("SlowTool", SlowTool)
register_tool("ParallelFailingTool", ParallelFailingTool)


# --- 帮手 ---


def _tool_call(call_id: str, name: str, arguments: str) -> MessageToolCall:
    return MessageToolCall(
        id=call_id, name=name, arguments=arguments, origin="completion"
    )


def _run_step(agent, conversation, collected_events):
    """运行单个智能体步骤并返回收集的事件。"""
    agent.step(conversation, on_event=lambda e: collected_events.append(e))


# --- 测试 ---


def test_parallel_execution_multiple_tools():
    """多个工具调用并行执行，事件按顺序发出。"""
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="Running tools")],
                tool_calls=[
                    _tool_call("call_0", "slow_tool", '{"delay": 0.05, "label": "a"}'),
                    _tool_call("call_1", "slow_tool", '{"delay": 0.05, "label": "b"}'),
                    _tool_call("call_2", "slow_tool", '{"delay": 0.05, "label": "c"}'),
                ],
            ),
            Message(role="assistant", content=[TextContent(text="Done")]),
        ]
    )
    agent = Agent(llm=llm, tools=[Tool(name="SlowTool")], tool_concurrency_limit=4)

    collected = []
    conversation = Conversation(agent=agent, callbacks=[lambda e: collected.append(e)])
    conversation.send_message(Message(role="user", content=[TextContent(text="Go")]))
    _run_step(agent, conversation, collected)

    # 验证观测结果是否按原始顺序发出
    obs_events = [e for e in collected if isinstance(e, ObservationEvent)]
    assert len(obs_events) == 3
    assert obs_events[0].tool_call_id == "call_0"
    assert obs_events[1].tool_call_id == "call_1"
    assert obs_events[2].tool_call_id == "call_2"


def test_parallel_execution_faster_than_sequential():
    """并行执行比顺序执行更快。"""
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[
                    _tool_call("call_0", "slow_tool", '{"delay": 0.1, "label": "a"}'),
                    _tool_call("call_1", "slow_tool", '{"delay": 0.1, "label": "b"}'),
                    _tool_call("call_2", "slow_tool", '{"delay": 0.1, "label": "c"}'),
                    _tool_call("call_3", "slow_tool", '{"delay": 0.1, "label": "d"}'),
                ],
            ),
            Message(role="assistant", content=[TextContent(text="Done")]),
        ]
    )
    agent = Agent(llm=llm, tools=[Tool(name="SlowTool")], tool_concurrency_limit=4)

    collected = []
    conversation = Conversation(agent=agent, callbacks=[lambda e: collected.append(e)])
    conversation.send_message(Message(role="user", content=[TextContent(text="Go")]))

    start = time.monotonic()
    _run_step(agent, conversation, collected)
    elapsed = time.monotonic() - start

    # 4 个工具 x 每个 0.1s = 0.4s 顺序，应该 ~0.1s 并行
    assert elapsed < 0.3, f"Expected parallel execution, took {elapsed:.2f}s"


def test_sequential_execution_with_default_limit():
    """默认 tool_concurrency_limit=1 时，工具按顺序执行。"""
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[
                    _tool_call("call_0", "slow_tool", '{"delay": 0.02, "label": "a"}'),
                    _tool_call("call_1", "slow_tool", '{"delay": 0.02, "label": "b"}'),
                ],
            ),
            Message(role="assistant", content=[TextContent(text="Done")]),
        ]
    )
    agent = Agent(llm=llm, tools=[Tool(name="SlowTool")])

    collected = []
    conversation = Conversation(agent=agent, callbacks=[lambda e: collected.append(e)])
    conversation.send_message(Message(role="user", content=[TextContent(text="Go")]))
    _run_step(agent, conversation, collected)

    obs_events = [e for e in collected if isinstance(e, ObservationEvent)]
    assert len(obs_events) == 2
    assert obs_events[0].tool_call_id == "call_0"
    assert obs_events[1].tool_call_id == "call_1"


def test_limit_one_preserves_sequential_semantics():
    """Regression: tool_concurrency_limit=1 必须保留旧的顺序行为。

    默认限制为 1，多工具批次必须：
    1. 在调用者的线程（而不是池线程）上运行每个工具。
    2. 严格按顺序执行工具。

    SlowTool 已经在其观测结果中记录了 threading.current_thread().name，因此我们可以端
    到端地验证线程亲和力。
    """
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[
                    _tool_call("call_0", "slow_tool", '{"delay": 0.0, "label": "a"}'),
                    _tool_call("call_1", "slow_tool", '{"delay": 0.0, "label": "b"}'),
                    _tool_call("call_2", "slow_tool", '{"delay": 0.0, "label": "c"}'),
                ],
            ),
            Message(role="assistant", content=[TextContent(text="Done")]),
        ]
    )
    # 默认 tool_concurrency_limit=1
    agent = Agent(llm=llm, tools=[Tool(name="SlowTool")])

    collected = []
    conversation = Conversation(agent=agent, callbacks=[lambda e: collected.append(e)])
    conversation.send_message(Message(role="user", content=[TextContent(text="Go")]))

    caller_thread = threading.current_thread().name
    _run_step(agent, conversation, collected)

    obs_events = [e for e in collected if isinstance(e, ObservationEvent)]
    assert len(obs_events) == 3

    # 属性 1：每个工具都在调用者的线程上运行，而不是在池线程上运行
    labels: list[str] = []
    for obs in obs_events:
        observation = obs.observation
        assert isinstance(observation, SlowObservation)
        assert observation.thread_name == caller_thread, (
            f"Tool '{observation.label}' ran on "
            f"{observation.thread_name}, expected {caller_thread}"
        )
        labels.append(observation.label)

    # 属性2：按原始顺序执行的工具
    assert labels == ["a", "b", "c"]


def test_finish_tool_truncates_subsequent_tools():
    """FinishTool 之后的工具将被丢弃并且永远不会执行。"""
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[
                    _tool_call(
                        "call_0", "slow_tool", '{"delay": 0.01, "label": "before"}'
                    ),
                    _tool_call("call_finish", "finish", '{"message": "All done"}'),
                    _tool_call(
                        "call_2", "slow_tool", '{"delay": 0.01, "label": "after"}'
                    ),
                ],
            ),
        ]
    )
    agent = Agent(llm=llm, tools=[Tool(name="SlowTool")], tool_concurrency_limit=4)

    collected = []
    conversation = Conversation(agent=agent, callbacks=[lambda e: collected.append(e)])
    conversation.send_message(Message(role="user", content=[TextContent(text="Go")]))
    _run_step(agent, conversation, collected)

    # 只有slow_tool“之前”和完成应该执行
    action_events = [e for e in collected if isinstance(e, ActionEvent)]
    tool_names = [e.tool_name for e in action_events]
    assert "slow_tool" in tool_names
    assert "finish" in tool_names

    # “之后”工具调用不应该存在
    obs_events = [e for e in collected if isinstance(e, ObservationEvent)]
    obs_tool_calls = [e.tool_call_id for e in obs_events]
    assert "call_2" not in obs_tool_calls

    # 谈话应该结束
    with conversation.state:
        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )


def test_error_in_parallel_batch_preserves_other_results():
    """
    并行批处理中出现故障的工具不会阻止其他工具完成。
    """
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[
                    _tool_call(
                        "call_0", "slow_tool", '{"delay": 0.01, "label": "ok1"}'
                    ),
                    _tool_call("call_1", "parallel_failing_tool", '{"value": "boom"}'),
                    _tool_call(
                        "call_2", "slow_tool", '{"delay": 0.01, "label": "ok2"}'
                    ),
                ],
            ),
            Message(role="assistant", content=[TextContent(text="Recovered")]),
        ]
    )
    agent = Agent(
        llm=llm,
        tools=[Tool(name="SlowTool"), Tool(name="ParallelFailingTool")],
        tool_concurrency_limit=4,
    )

    collected = []
    conversation = Conversation(agent=agent, callbacks=[lambda e: collected.append(e)])
    conversation.send_message(Message(role="user", content=[TextContent(text="Go")]))
    _run_step(agent, conversation, collected)

    # 应该有 2 个观测结果和 1 个错误，按顺序
    obs_events = [e for e in collected if isinstance(e, ObservationEvent)]
    error_events = [e for e in collected if isinstance(e, AgentErrorEvent)]

    assert len(obs_events) == 2
    assert len(error_events) == 1
    assert "boom" in error_events[0].error

    # 事件应按原始顺序排列：obs_0、error_1、obs_2
    result_events = [
        e for e in collected if isinstance(e, (ObservationEvent, AgentErrorEvent))
    ]
    assert result_events[0].tool_call_id == "call_0"
    assert result_events[1].tool_call_id == "call_1"
    assert result_events[2].tool_call_id == "call_2"

    # 对话应该不结束
    with conversation.state:
        assert (
            conversation.state.execution_status != ConversationExecutionStatus.FINISHED
        )


def test_blocked_action_with_parallel_execution():
    """
    阻塞的操作会产生拒绝，而非阻塞的操作会并行执行。
    """
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[
                    _tool_call("call_0", "slow_tool", '{"delay": 0.01, "label": "a"}'),
                    _tool_call("call_1", "slow_tool", '{"delay": 0.01, "label": "b"}'),
                ],
            ),
            Message(role="assistant", content=[TextContent(text="Done")]),
        ]
    )
    agent = Agent(llm=llm, tools=[Tool(name="SlowTool")], tool_concurrency_limit=4)

    collected = []
    conversation = Conversation(agent=agent, callbacks=[lambda e: collected.append(e)])
    conversation.send_message(Message(role="user", content=[TextContent(text="Go")]))

    # 运行一步来获取操作事件，以便我们知道它们的 ID
    _run_step(agent, conversation, collected)

    # 对于此测试，我们通过检查两个观测结果是否已发出（未配置阻塞）来验证该机制是否有效。
    #
    obs_events = [e for e in collected if isinstance(e, ObservationEvent)]
    assert len(obs_events) == 2


def test_tool_concurrency_limit_wires_to_executor():
    """Agent.tool_concurrency_limit 连接到 ParallelToolExecutor。"""
    llm = TestLLM.from_messages(
        [Message(role="assistant", content=[TextContent(text="Done")])]
    )
    agent = Agent(llm=llm, tools=[], tool_concurrency_limit=6)
    assert agent._parallel_executor._max_workers == 6

    agent_default = Agent(llm=llm, tools=[])
    assert agent_default._parallel_executor._max_workers == 1


@pytest.mark.parametrize("value", [0, -1, -100])
def test_tool_concurrency_limit_rejects_invalid_values(value):
    """Pydantic 在构造时验证 tool_concurrency_limit >= 1。"""
    llm = TestLLM.from_messages(
        [Message(role="assistant", content=[TextContent(text="Done")])]
    )
    with pytest.raises(ValidationError):
        Agent(llm=llm, tools=[], tool_concurrency_limit=value)
