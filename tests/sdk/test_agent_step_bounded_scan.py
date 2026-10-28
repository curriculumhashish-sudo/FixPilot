from __future__ import annotations

from collections.abc import Iterator

import pytest

from openhands.sdk.agent.agent import Agent
from openhands.sdk.conversation import LocalConversation
from openhands.sdk.conversation.event_store import EventLog
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event import MessageEvent
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.workspace.local import LocalWorkspace


class _LimitedIterEvents(EventLog):
    def __init__(self, events, max_iter: int):
        self._events = list(events)
        # 镜像 EventLog 的 id/index 映射，因此基于 id 的查找（get_index、path_to_root、
        # active_branch）无需触及 __iter__ 即可工作。
        #
        self._id_to_idx = {e.id: i for i, e in enumerate(self._events)}
        self._idx_to_id = {i: e.id for i, e in enumerate(self._events)}
        self._max_iter = max_iter
        self._iter_count = 0

    def __len__(self) -> int:  # type: ignore[override]
        return len(self._events)

    def __getitem__(self, idx):  # type: ignore[override]
        return self._events[idx]

    def __iter__(self) -> Iterator:  # type: ignore[override]
        self._iter_count += 1
        if self._iter_count > self._max_iter:
            raise AssertionError("events iterated too many times")
        return iter(self._events)

    def append(self, event) -> int:  # type: ignore[override]
        self._events.append(event)
        return len(self._events) - 1


class _FailingIterEvents(EventLog):
    def __init__(self, events):
        self._events = list(events)
        # 镜像 EventLog 的 id/index 映射，因此基于 id 的查找（get_index、path_to_root、
        # active_branch）无需触及 __iter__ 即可工作。
        #
        self._id_to_idx = {e.id: i for i, e in enumerate(self._events)}
        self._idx_to_id = {i: e.id for i, e in enumerate(self._events)}

    def __len__(self) -> int:  # type: ignore[override]
        return len(self._events)

    def __getitem__(self, idx):  # type: ignore[override]
        return self._events[idx]

    def __iter__(self) -> Iterator:  # type: ignore[override]
        raise AssertionError("events iterated unexpectedly")

    def append(self, event) -> int:  # type: ignore[override]
        self._events.append(event)
        return len(self._events) - 1


def test_agent_step_latest_user_message_scan_is_bounded(tmp_path):
    agent = Agent(llm=LLM(model="gpt-4o-mini", api_key="x"), tools=[])
    workspace = LocalWorkspace(working_dir=tmp_path)
    conv = LocalConversation(agent=agent, workspace=workspace)

    # 创建一个较长的历史记录，并在末尾添加用户消息。
    for i in range(1000):
        conv._on_event(
            MessageEvent(
                source="agent",
                llm_message=Message(
                    role="assistant", content=[TextContent(text=str(i))]
                ),
            )
        )

    conv.send_message("hi")
    blocked_user_msg = conv.state.events[-1]

    conv.state.block_message(blocked_user_msg.id, "blocked")

    # 将事件列表替换为包装器，如果代码通过 list(state.events) 迭代完整历史记录，该包装器
    # 将会爆炸。
    #
    conv.state._events = _LimitedIterEvents(conv.state.events, max_iter=0)

    agent.step(conv, on_event=conv._on_event)

    assert conv.state.execution_status == ConversationExecutionStatus.FINISHED


def test_agent_step_uses_last_user_message_id(tmp_path):
    agent = Agent(llm=LLM(model="gpt-4o-mini", api_key="x"), tools=[])
    workspace = LocalWorkspace(working_dir=tmp_path)
    conv = LocalConversation(agent=agent, workspace=workspace)

    conv.send_message("hi")
    message = conv.state.events[-1]

    conv.state.block_message(message.id, "blocked")

    conv.state._events = _FailingIterEvents(conv.state.events)

    agent.step(conv, on_event=conv._on_event)

    assert conv.state.execution_status == ConversationExecutionStatus.FINISHED


def test_agent_step_legacy_state_no_last_user_id(tmp_path, caplog):
    """验证在不last_user_message_id的情况下优雅处理旧状态的能力。

    当 last_user_message_id 为 None 但 blocked_messages 存在（旧状态）时，代码应记录
    调试消息并继续处理，而不是检查阻止的消
    息。
    """
    import logging

    agent = Agent(llm=LLM(model="gpt-4o-mini", api_key="x"), tools=[])
    workspace = LocalWorkspace(working_dir=tmp_path)
    conv = LocalConversation(agent=agent, workspace=workspace)

    conv.send_message("hi")
    message = conv.state.events[-1]

    # 模拟遗留状态：blocked_messages存在，但last_user_message_id是None
    conv.state.block_message(message.id, "blocked by hook")
    conv.state.last_user_message_id = None

    # 捕获调试日志
    with caplog.at_level(logging.DEBUG, logger="openhands.sdk.agent.agent"):
        # 步骤不应该提前完成，因为如果没有 last_user_message_id，我们就无法检查被阻止的
        # 消息。 它将继续进行 LLM 调用，该调用将因 API 键无效而失败，但这是预期的。
        #
        try:
            agent.step(conv, on_event=conv._on_event)
        except Exception:
            # 预期：LLM 调用因 API 密钥无效而失败
            pass

    # 验证已记录旧版回退方案调试消息
    assert any(
        "Blocked messages exist but last_user_message_id is None" in record.message
        for record in caplog.records
    )

    # 验证 blocked_messages 已消耗不（因为我们跳过了检查）
    assert message.id in conv.state.blocked_messages


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
