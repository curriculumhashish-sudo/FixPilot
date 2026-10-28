"""压力测试：停止的订阅者不得 OOM 服务器。

捕获的错误类：
    - 当一个订阅者停止时，缓冲区无限增长。 在生产中，这是一个 WebSocket 客户端，其
    TCP 缓冲区已满； 进程内的类似物是订阅者，它在每个事件上无限期地阻
    塞。
    - 订阅者泄漏：从未取消订阅的订阅者会在许多事件中累积，即使单个事件很小。

为什么是白盒（pub_sub）而不是真实的WebSocket：
    实现实时通信（Real WS） httpx.ASGITransport 驾驶起来很 awkward。 故障模式 (TCP 只
    有真实套接字才会触发缓冲区填充。 我们使
    用了最接近的在途模拟——订阅链，并在此基础上声明了不变量 that *不要* 依赖于  TCP 层
    ：订阅注册是平衡的 RSS 订阅者速度慢并不会因为一个订阅者慢而产
    生无限延迟。

架构方面的观测结果可在此处进行测试：
    PubSub.__call__ 依次等待订阅者 (pub_sub.py:70-74)。 一个缓慢的订阅者会阻塞链条。
    我们断言 ON THE CURRENT
    BEHAVIOUR (慢订阅者会阻碍快订阅者) — 如果未来重构将任务细化到每个订阅者，测试将通
    过，有更大的缓冲空间，预算可以收紧。
"""

import asyncio
import os
import time
from dataclasses import dataclass, field

import psutil
import pytest

from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.event_service import EventService
from openhands.agent_server.pub_sub import Subscriber
from openhands.sdk.event import Event
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from tests.agent_server.stress.budgets import SLOW_WEBSOCKET_CONSUMER
from tests.agent_server.stress.scripts import (
    SlowTestLLM,
    start_conversation_with_test_llm,
    text_message,
)


pytestmark = [pytest.mark.stress, pytest.mark.timeout(30)]


@dataclass(frozen=True, slots=True)
class _RecordingSubscriber(Subscriber[Event]):
    """记录它看到的每个事件以及它看到的时间戳。"""

    events: list[tuple[float, type]] = field(default_factory=list)

    async def __call__(self, event: Event) -> None:
        self.events.append((time.monotonic(), type(event)))


@dataclass(slots=True)
class _StalledSubscriber(Subscriber[Event]):
    """在 __call__ 内永远等待 — 模拟楔形消费者。

    测试在拆卸时发布 ``unblock``，因此任何待处理的 pub_sub 发布协程都可以耗尽。
    """

    unblock: asyncio.Event = field(default_factory=asyncio.Event)
    seen_calls: int = 0

    async def __call__(self, event: Event) -> None:
        self.seen_calls += 1
        await self.unblock.wait()


async def _get_event_service(
    conversation_service: ConversationService, *, workspace_dir: str
) -> EventService:
    """进行空闲（未运行）对话并返回其 EventService。

    这个测试的重点是直接驱动``_pub_sub``。 如果我们让 start_conversation 自动运行（通
    过 initial_message），则占位符
    LLM 在我们的 switch_llm 落地之前触发真正的网络调用，这既增加了碎片，又阻止了拆卸
    。
    """
    parent_llm = SlowTestLLM.from_messages([text_message("done")], latency_s=0.0)
    info = await start_conversation_with_test_llm(
        conversation_service,
        parent_llm=parent_llm,
        workspace_dir=workspace_dir,
        usage_id="slow-ws",
        initial_text=None,
    )
    es = await conversation_service.get_event_service(info.id)
    assert es is not None
    return es


async def test_stalled_subscriber_does_not_grow_unbounded(
    conversation_service: ConversationService,
    tmp_path,
):
    """当一个订阅者停止时触发 N 个事件。 服务器RSS保持有界；
    pub_sub 注册之后就干净了。"""
    workspace = str(tmp_path / "ws")
    (tmp_path / "ws").mkdir()
    event_service = await _get_event_service(
        conversation_service, workspace_dir=workspace
    )

    baseline_subscribers = len(event_service._pub_sub._subscribers)

    proc = psutil.Process(os.getpid())
    # 采取 RSS  *之前* 订阅或发布——这是无上限增长预算的参考点。 重复采样并使用最大值可以
    # 减轻单个分配器的噪声观测结果。
    #
    rss_baseline_mb = max(proc.memory_info().rss / (1024 * 1024) for _ in range(3))

    # 直接通过底层 pub_sub 订阅，通过 event_service.subscribe_to_events * 而非 * 订阅。
    # 后者执行一个初始状态-同步（event_service.py:412），即同步调用新订阅者——对于停滞的
    # 订阅者来说，这意味着在注册时会阻塞，永远不会返回，测试死锁。
    #
    stalled = _StalledSubscriber()
    fast = _RecordingSubscriber()
    stalled_id = event_service._pub_sub.subscribe(stalled)
    fast_id = event_service._pub_sub.subscribe(fast)

    # 快照基线事件计数：对话的状态更改回调可能会在启动期间发布环境事件。 我们测量增量。
    #
    fast_baseline_events = len(fast.events)

    try:

        def _make_event(i: int) -> ConversationStateUpdateEvent:
            return ConversationStateUpdateEvent(
                key="execution_status",
                value=f"idle-{i}",
                source="environment",
            )

        async def _emit_one(i: int):
            await event_service._pub_sub(_make_event(i))

        # 每个发布都会等待停滞的订阅者（当前的顺序行为 pub_sub），因此我们分发到后台任务
        # ，并让它们排队等待停滞。
        #
        publish_tasks = [
            asyncio.create_task(_emit_one(i))
            for i in range(SLOW_WEBSOCKET_CONSUMER.n_events)
        ]
        await asyncio.sleep(0.1)  # let create_task scheduling settle

        # 预检查：停滞的订阅者必须实际上已经被调用，否则测试会因为错误的原因通过（一个）
        #  回归那如果悄悄忽略慢速订阅者，一切就会瞬间耗尽， RSS 非阻塞链中的快订阅者断言
        # 都会通过。
        #
        assert stalled.seen_calls > 0, (
            "stalled subscriber was never invoked; the publish chain isn't "
            "blocked on it. Did pub_sub start skipping subscribers?"
        )

        # 失败模式是无限增长，因此预算是绝对的。 将失速期间峰值与失速前基线进行比较。 与
        # 基线相同的 max-of-3 采样，因此分配器噪声不会缩小增量并掩盖实际增长。
        #
        rss_peak_mb = max(proc.memory_info().rss / (1024 * 1024) for _ in range(3))
        rss_delta = rss_peak_mb - rss_baseline_mb
        assert rss_delta < SLOW_WEBSOCKET_CONSUMER.max_rss_delta_mb, (
            f"RSS grew {rss_delta:.1f} MB with one stalled subscriber and "
            f"{SLOW_WEBSOCKET_CONSUMER.n_events} pending events "
            f"(baseline {rss_baseline_mb:.1f} → peak {rss_peak_mb:.1f}; "
            f"budget {SLOW_WEBSOCKET_CONSUMER.max_rss_delta_mb} MB). "
            f"Likely an unbounded per-subscriber buffer."
        )

        # 释放失速，以便 publish_tasks 可以排空。
        stalled.unblock.set()
        await asyncio.gather(*publish_tasks)

        # 快速订阅者至少应该看过我们发布的所有活动。 来自对话生命周期的环境事件（状态更
        # 新回调）也可能在停顿窗口期间流过——这些都很好； 我们捕获的是同级停止时的 *
        # dropped* 事件。
        #
        published = len(fast.events) - fast_baseline_events
        assert published >= SLOW_WEBSOCKET_CONSUMER.n_events, (
            f"fast subscriber received {published} of "
            f"{SLOW_WEBSOCKET_CONSUMER.n_events} published events. Events "
            f"were dropped while a sibling subscriber was stalled."
        )

    finally:
        # 即使断言失败，清理也必须成功。
        stalled.unblock.set()
        event_service._pub_sub.unsubscribe(stalled_id)
        event_service._pub_sub.unsubscribe(fast_id)

    # 取消订阅后，订户数量恢复到基线——注册核算达到平衡。
    #
    assert len(event_service._pub_sub._subscribers) == baseline_subscribers, (
        f"after unsubscribing, pub_sub still has "
        f"{len(event_service._pub_sub._subscribers)} subscribers "
        f"(expected {baseline_subscribers}). Subscriber leak."
    )
