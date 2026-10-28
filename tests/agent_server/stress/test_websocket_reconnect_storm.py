"""压力测试：快速订阅/取消订阅周期不得泄漏状态。

捕获的错误类：
    - PubSub 订阅者泄漏：订阅/取消订阅会计在多次循环后发生漂移，在字典中留下过时的条
    目。
    - FD 泄漏（过程中不太可能发生； 包括作为廉价的健全性检查）。

白盒，不是真正的 WS：
    Real WebSocket 通过重连 ASGITransport 都是笨拙的，失败模式在  *服务器端* 注册会计
    ，我们直接通过它到达
    ``event_service._pub_sub``.
"""

import os
from dataclasses import dataclass

import psutil
import pytest

from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.event_service import EventService
from openhands.agent_server.pub_sub import Subscriber
from openhands.sdk.event import Event
from tests.agent_server.stress.budgets import WEBSOCKET_RECONNECT_STORM
from tests.agent_server.stress.scripts import (
    SlowTestLLM,
    start_conversation_with_test_llm,
    text_message,
)


pytestmark = [pytest.mark.stress, pytest.mark.timeout(30)]


@dataclass(frozen=True, slots=True)
class _NoopSubscriber(Subscriber[Event]):
    async def __call__(self, event: Event) -> None:
        pass


async def _idle_event_service(
    conversation_service: ConversationService, *, workspace_dir: str
) -> EventService:
    """创建一个空闲会话并返回其事件服务。"""
    parent_llm = SlowTestLLM.from_messages([text_message("ok")], latency_s=0.0)
    info = await start_conversation_with_test_llm(
        conversation_service,
        parent_llm=parent_llm,
        workspace_dir=workspace_dir,
        usage_id="reconn-storm",
        initial_text=None,
    )
    es = await conversation_service.get_event_service(info.id)
    assert es is not None
    return es


async def test_reconnect_storm_subscriber_accounting_balanced(
    conversation_service: ConversationService,
    tmp_path,
):
    """N 个订阅/取消订阅周期。 订户数量和 FD 返回
    基线。"""
    workspace = str(tmp_path / "ws")
    (tmp_path / "ws").mkdir()
    es = await _idle_event_service(conversation_service, workspace_dir=workspace)

    proc = psutil.Process(os.getpid())
    pre_subscribers = len(es._pub_sub._subscribers)
    try:
        pre_fds = proc.num_fds()
    except (AttributeError, psutil.AccessDenied):
        pre_fds = -1

    # 使用 pub_sub.subscribe取消订阅直接。 subscribe_to_events 初始状态同步调用订阅者的
    # 方法是 FIFOLock  — 对一个订阅者收费，但在一个 100 的环中，它可以与续租循环竞争，并
    # 将测试变成一个延迟基准测试而不是泄漏检查。
    #
    for _ in range(WEBSOCKET_RECONNECT_STORM.cycles):
        sub = _NoopSubscriber()
        sid = es._pub_sub.subscribe(sub)
        ok = es._pub_sub.unsubscribe(sid)
        assert ok, "unsubscribe returned False — subscriber id mismatch"

    post_subscribers = len(es._pub_sub._subscribers)
    delta_subscribers = post_subscribers - pre_subscribers
    assert delta_subscribers <= WEBSOCKET_RECONNECT_STORM.max_subscriber_delta, (
        f"after {WEBSOCKET_RECONNECT_STORM.cycles} subscribe/unsubscribe "
        f"cycles, subscriber count grew by {delta_subscribers} (budget "
        f"{WEBSOCKET_RECONNECT_STORM.max_subscriber_delta}). Possible leak."
    )

    if pre_fds >= 0:
        post_fds = proc.num_fds()
        delta_fds = post_fds - pre_fds
        assert delta_fds <= WEBSOCKET_RECONNECT_STORM.max_fd_growth, (
            f"FDs grew by {delta_fds} across "
            f"{WEBSOCKET_RECONNECT_STORM.cycles} cycles (budget "
            f"{WEBSOCKET_RECONNECT_STORM.max_fd_growth})."
        )
