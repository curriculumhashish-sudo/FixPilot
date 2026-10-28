"""测试 Conversation.fork() 原语。"""

import tempfile
import threading
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Self

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation, LocalConversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event.llm_convertible import MessageEvent, SystemPromptEvent
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.tool import Action, Observation, ToolDefinition, ToolExecutor


def _agent() -> Agent:
    return Agent(
        llm=LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test"),
        tools=[],
    )


def _msg(event_id: str, text: str = "hi") -> MessageEvent:
    return MessageEvent(
        id=event_id,
        llm_message=Message(role="user", content=[TextContent(text=text)]),
        source="user",
    )


class ForkCopyMockAction(Action):
    command: str = "test"


class ForkCopyMockObservation(Observation):
    pass


class ForkCopyNonPicklableExecutor(
    ToolExecutor[ForkCopyMockAction, ForkCopyMockObservation]
):
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def __call__(
        self,
        action: ForkCopyMockAction,
        conversation: LocalConversation | None = None,
    ) -> ForkCopyMockObservation:
        return ForkCopyMockObservation.from_text(action.command)


class ForkCopyNonPicklableTool(
    ToolDefinition[ForkCopyMockAction, ForkCopyMockObservation]
):
    @classmethod
    def create(cls, *args, **kwargs) -> Sequence[Self]:
        return [
            cls(
                description="test tool with a non-picklable executor",
                action_type=ForkCopyMockAction,
                observation_type=ForkCopyMockObservation,
                executor=ForkCopyNonPicklableExecutor(),
            )
        ]


def test_fork_creates_new_id():
    """分叉对话必须有一个独特的 ID。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        fork = src.fork()

        assert fork.id != src.id
        assert isinstance(fork.id, uuid.UUID)


def test_fork_with_explicit_id():
    """显式 conversation_id 受到尊重。"""
    custom_id = uuid.uuid4()
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        fork = src.fork(conversation_id=custom_id)

        assert fork.id == custom_id


def test_fork_copies_events():
    """来自源的事件必须出现在分叉中。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        src.state.events.append(_msg("evt-1", "hello"))
        src.state.events.append(_msg("evt-2", "world"))

        fork = src.fork()

        # 分叉应该至少有我们添加的事件
        fork_ids = [e.id for e in fork.state.events]
        assert "evt-1" in fork_ids
        assert "evt-2" in fork_ids


def test_fork_copies_system_prompt_event_with_non_picklable_executor():
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        source_tool = ForkCopyNonPicklableTool.create()[0]
        src.state.events.append(
            SystemPromptEvent(
                system_prompt=TextContent(text="test system prompt"),
                tools=[source_tool],
            )
        )

        fork = src.fork()

        source_event = src.state.events[0]
        fork_event = fork.state.events[0]
        assert isinstance(source_event, SystemPromptEvent)
        assert isinstance(fork_event, SystemPromptEvent)
        assert fork_event is not source_event
        assert source_event.tools[0].executor is not None
        assert fork_event.tools[0].executor is None
        assert fork_event.tools[0].action_type is ForkCopyMockAction


def test_fork_source_unmodified():
    """附加到 fork 不得影响源。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        src.state.events.append(_msg("src-evt"))
        src_event_count = len(src.state.events)

        fork = src.fork()
        fork.state.events.append(_msg("fork-only"))

        # 来源不应增长
        assert len(src.state.events) == src_event_count


def test_fork_execution_status_is_idle():
    """分叉对话在空闲状态下开始。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        fork = src.fork()

        assert fork.state.execution_status == ConversationExecutionStatus.IDLE


def test_fork_resets_metrics_by_default():
    """默认情况下，分叉上的指标应该是新鲜的（空）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        fork = src.fork()

        combined = fork.state.stats.get_combined_metrics()
        assert combined.accumulated_cost == 0


def test_fork_preserves_metrics_when_requested():
    """当 reset_metrics=False 时，分叉应该保留统计数据。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        # 注入非零指标
        from openhands.sdk.llm.utils.metrics import Metrics

        m = Metrics()
        m.accumulated_cost = 1.5
        src._state.stats.usage_to_metrics["test"] = m

        fork = src.fork(reset_metrics=False)

        combined = fork.state.stats.get_combined_metrics()
        assert combined.accumulated_cost == pytest.approx(1.5)


def test_fork_copies_agent_state():
    """agent_state dict 应该被转移到 fork。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        src._state.agent_state = {"key": "value"}

        fork = src.fork()

        assert fork.state.agent_state == {"key": "value"}
        # 分叉上的突变不应影响源
        fork._state.agent_state = {**fork._state.agent_state, "new": True}
        assert "new" not in src._state.agent_state


def test_fork_accepts_replacement_agent():
    """提供智能体 kwarg 会替换 fork 中的源智能体。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        alt_agent = Agent(
            llm=LLM(
                model="gpt-4o",
                api_key=SecretStr("other-key"),
                usage_id="alt",
            ),
            tools=[],
        )

        fork = src.fork(agent=alt_agent)

        assert fork.agent.llm.model == "gpt-4o"
        # 来源应保留其原始内容智能体
        assert src.agent.llm.model == "gpt-4o-mini"


def test_fork_with_tags():
    """标签应该传递到 fork。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        fork = src.fork(tags={"env": "test"})

        assert fork.state.tags.get("env") == "test"


@pytest.mark.parametrize("tags", [{}, {"purpose": "debugging"}, {"title": "user tag"}])
def test_fork_with_title_is_deprecated(tags: dict[str, str]):
    """compat 接受传递标题，但会发出警告并且不会污染标签。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        with pytest.warns(DeprecationWarning, match="title parameter is deprecated"):
            fork = src.fork(title="My Fork", tags=tags)

        assert dict(fork.state.tags) == tags


def test_fork_shares_workspace():
    """Fork 应该重用与源相同的工作区。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        fork = src.fork()

        assert fork.workspace.working_dir == src.workspace.working_dir


def test_fork_event_deep_copy_isolation():
    """改变分叉中的事件对象不得影响源。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        src.state.events.append(_msg("deep-evt", "original"))

        fork = src.fork()

        # fork事件是一个不同的对象
        src_evt = src.state.events[0]
        fork_evt = fork.state.events[0]
        assert src_evt is not fork_evt

        # 改变 fork 事件不应改变源
        assert fork_evt.llm_message.content[0].text == "original"  # type: ignore[union-attr]
        fork_evt.llm_message.content[0].text = "mutated"  # type: ignore[union-attr]
        assert src_evt.llm_message.content[0].text == "original"  # type: ignore[union-attr]


def test_fork_persistence_path_no_doubling():
    """Fork 持久化 dir 必须是 source 的同级，而不是嵌套在其中。

    回归测试：fork() 之前计算了附加了对话十六进制的持久化路径，但 __init__ 也通过
    get_persistence_dir() 附加了它，导致
    /base/FORK_HEX/FORK_HEX.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        fork = src.fork()

        assert src._state.persistence_dir is not None
        assert fork._state.persistence_dir is not None
        src_path = Path(src._state.persistence_dir)
        fork_path = Path(fork._state.persistence_dir)

        # 两者都应该直接位于同一基本目录下
        assert src_path.parent == fork_path.parent
        # fork dir 应该是 <base>/<fork_id_hex>，而不是双倍
        assert fork_path.name == fork.id.hex


def test_fork_persisted_events_survive_reload():
    """事件已持久化 by fork() 应该可以从 fork 目录加载。

    它验证了路径双倍修正的端到端：如果分支写入了错误的目录，从正确的路径恢复将看到零
    事件。
    """
    # 事件 ID 必须是十六进制 + 破折号，≥8 个字符才能匹配 EVENT_NAME_RE。
    evt_id_1 = uuid.uuid4().hex
    evt_id_2 = uuid.uuid4().hex

    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        src.state.events.append(_msg(evt_id_1, "hello"))
        src.state.events.append(_msg(evt_id_2, "world"))

        fork = src.fork()
        fork_id = fork.id

        # 分叉应该将事件保存在内存中
        assert len(fork.state.events) == 2

        # 关闭 fork 以刷新持久化，然后从磁盘重新打开
        fork.close()

        resumed = Conversation(
            agent=_agent(),
            persistence_dir=tmpdir,
            workspace=tmpdir,
            conversation_id=fork_id,
        )
        resumed_ids = [e.id for e in resumed.state.events]
        assert evt_id_1 in resumed_ids
        assert evt_id_2 in resumed_ids


def test_fork_default_does_not_clobber_source_cache_key():
    """默认 fork() 必须保持源的 prompt_cache_key 不变 (#2917)。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        src_key_before = src.get_llm_call_context().prompt_cache_key

        fork = src.fork()

        assert (
            src.get_llm_call_context().prompt_cache_key == src_key_before == str(src.id)
        )
        assert fork.get_llm_call_context().prompt_cache_key == str(fork.id)
        assert (
            fork.get_llm_call_context().prompt_cache_key
            != src.get_llm_call_context().prompt_cache_key
        )


def test_fork_with_aliased_agent_does_not_clobber_source_cache_key():
    """fork(agent=source.agent) 必须保留源缓存标识 (#2917)。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Conversation(agent=_agent(), persistence_dir=tmpdir, workspace=tmpdir)
        src_key_before = src.get_llm_call_context().prompt_cache_key

        fork = src.fork(agent=src.agent)

        assert (
            src.get_llm_call_context().prompt_cache_key == src_key_before == str(src.id)
        )
        assert fork.get_llm_call_context().prompt_cache_key == str(fork.id)
        assert fork.agent.llm is not src.agent.llm
