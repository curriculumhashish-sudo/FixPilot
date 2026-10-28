"""压力测试：慢 Webhook 不得拖延对话。

捕获的错误类：
    - 当事件订阅者（Webhook）发布到慢速下游时，队头阻塞。 PubSub.__call__ 按顺序等待
    订阅者 (pub_sub.py:70-74)，因此缓慢的
    Webhook 会阻止其后面的每个事件发布。
    - Webhook 在持续的压力下，订户缓冲无限增长。

该测试揭示了什么与断言：
    今天，发布路径是连续的。 使用 ``event_buffer_size=1``（在每个事件上刷新）和 2 秒
    慢 Webhook，对话将明显地在等待每个帖子时停止。
    下面的预算表示“我们希望捕获回归行为”——如果智能体-服务器后来转向异步背后 Webhook
    发布，预算应该收紧。

真正的HTTP服务器（不是monkeypatch）因为：
    Monkeypatching ``httpx.AsyncClient`` 也会影响此测试自己的 ASGI 客户端（使用 httpx
    ）。 小型 stdlib HTTP
     服务器更简单。
"""

import asyncio
import http.server
import threading
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from openhands.agent_server import bash_router as bash_router_module
from openhands.agent_server.bash_service import BashEventService
from openhands.agent_server.config import Config, WebhookSpec
from openhands.agent_server.conversation_router import conversation_router
from openhands.agent_server.conversation_service import (
    ConversationService,
    WebhookSubscriber,
)
from openhands.agent_server.dependencies import get_conversation_service
from openhands.agent_server.event_router import event_router
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from tests.agent_server.stress.budgets import SLOW_WEBHOOK
from tests.agent_server.stress.probe import ResourceProbe
from tests.agent_server.stress.scripts import (
    SlowTestLLM,
    start_conversation_with_test_llm,
    text_message,
    wait_for_terminal,
)


pytestmark = pytest.mark.stress


class _SlowReceiver(http.server.BaseHTTPRequestHandler):
    """HTTP 在响应 200 之前休眠的处理程序。

    类属性按测试夹具设置，因此我们可以改变延迟而无需重建处理程序类。
    """

    delay_s: float = SLOW_WEBHOOK.webhook_delay_s

    def do_POST(self) -> None:  # noqa: N802 — stdlib API
        # 清空请求正文，以便干净地关闭连接。
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        time.sleep(self.delay_s)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # 禁止默认的 stderr 访问日志 — 它们会污染 pytest 输出。
        pass


@pytest.fixture
def slow_webhook_url() -> Iterator[str]:
    """在随机端口上启动慢速 stdlib HTTP 服务器以进行此测试。"""
    _SlowReceiver.delay_s = SLOW_WEBHOOK.webhook_delay_s
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SlowReceiver)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        t.join(timeout=2)


# 这些测试夹具覆盖了该模块的 conftest 默认值，因此我们可以连接启用 Webhook 的
# ConversationService。 pytest 按地点解决它们。
#


@pytest_asyncio.fixture
async def conversation_service(
    tmp_path: Path, slow_webhook_url: str
) -> AsyncIterator[ConversationService]:
    persist = tmp_path / "persist"
    persist.mkdir()
    spec = WebhookSpec(
        base_url=slow_webhook_url,
        event_buffer_size=1,
        flush_delay=1.0,
        num_retries=0,
    )
    service = ConversationService(
        conversations_dir=persist,
        webhook_specs=[spec],
    )
    async with service:
        yield service


@pytest.fixture
def app(
    conversation_service: ConversationService, bash_service: BashEventService
) -> FastAPI:
    fastapi_app = FastAPI()
    fastapi_app.state.config = Config()
    fastapi_app.include_router(conversation_router, prefix="/api")
    fastapi_app.include_router(event_router, prefix="/api")
    fastapi_app.include_router(bash_router_module.bash_router, prefix="/api")
    fastapi_app.dependency_overrides[get_conversation_service] = (
        lambda: conversation_service
    )
    return fastapi_app


@pytest_asyncio.fixture
async def baseline_service(tmp_path: Path) -> AsyncIterator[ConversationService]:
    """Webhook免费的计时基线服务。 不同的持久化目录
    因此它不与 Webhook 服务共享状态。"""
    persist = tmp_path / "persist_baseline"
    persist.mkdir()
    service = ConversationService(conversations_dir=persist)
    async with service:
        yield service


async def _run_conversation_and_time(
    service: ConversationService,
    client: httpx.AsyncClient,
    workspace_dir: str,
    *,
    usage_id: str,
) -> tuple[float, ConversationExecutionStatus]:
    parent_llm = SlowTestLLM.from_messages([text_message("done")], latency_s=0.0)
    info = await start_conversation_with_test_llm(
        service,
        parent_llm=parent_llm,
        workspace_dir=workspace_dir,
        usage_id=usage_id,
        initial_text="hi",
    )

    t0 = time.monotonic()
    run_resp = await client.post(f"/api/conversations/{info.id.hex}/run")
    assert run_resp.status_code == 200, run_resp.text
    status = await wait_for_terminal(client, info.id, timeout_s=60.0)
    return time.monotonic() - t0, status


async def test_slow_webhook_does_not_unbound_growth(
    conversation_service: ConversationService,
    baseline_service: ConversationService,
    client: httpx.AsyncClient,
    tmp_path: Path,
    probe: ResourceProbe,
):
    """对话完成，RSS 有界，即使有 2 s Webhook。

    Webhook * 阻止 * 会话是否由实现定义； 不可协商的是：
      (a) 对话最终 FINISHED，并且 (b) Webhook 订户缓冲区不会累积无限事件。
    """
    # 每次运行都有不同的工作区，因此来自基线的任何工作区端状态（来自
    # `_ensure_workspace_is_git_repo` 的 e.g..git，临时文件）不会渗入 Webhook 计时。
    #
    workspace_baseline = str(tmp_path / "ws_baseline")
    workspace_webhook = str(tmp_path / "ws_webhook")
    (tmp_path / "ws_baseline").mkdir()
    (tmp_path / "ws_webhook").mkdir()

    # 基线：相同的流程，无 Webhook。 重用 bash_service 支持的应用程序
    # 但有 Webhook-free ConversationService。 我们需要一个单独的 ASGI 客户端。
    #
    baseline_app = FastAPI()
    baseline_app.state.config = Config()
    baseline_app.include_router(conversation_router, prefix="/api")
    baseline_app.include_router(event_router, prefix="/api")
    baseline_app.dependency_overrides[get_conversation_service] = (
        lambda: baseline_service
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(baseline_app),
        base_url="http://stress.test",
    ) as baseline_client:
        baseline_wall, baseline_status = await _run_conversation_and_time(
            baseline_service,
            baseline_client,
            workspace_baseline,
            usage_id="webhook-baseline",
        )
    assert baseline_status == ConversationExecutionStatus.FINISHED

    # Webhook 运行。
    webhook_wall, webhook_status = await _run_conversation_and_time(
        conversation_service, client, workspace_webhook, usage_id="webhook-slow"
    )

    # 1. 谈话结束。 捕获“永远缓慢Webhook死锁对话”回归。
    #
    assert webhook_status == ConversationExecutionStatus.FINISHED, (
        f"conversation ended in {webhook_status} with a slow webhook in the "
        f"subscriber chain. Possible deadlock or unhandled exception."
    )

    # 2. 墙时间是有限的。 今天，随着顺序 pub_sub, 缓慢的 Webhook 这会增加延迟。 预算允许
    # 这样做——如果智能体-server later moves Webhook to 异步后台任务，这将有更多的余地通
    # 过，预算可以精简。
    #
    # `× 4` 松弛：典型的 TestLLM 会话通过 pub_sub 发布 ~4 个事件（状态→运行、消息、状态→
    # 完成、+1 备用），并且每个事件同步等待缓慢的 Webhook，因此每个事件花费 ~
    # webhook_delay_s。 允许其中 4 个与基线相关因素并列。
    #
    budget = baseline_wall * SLOW_WEBHOOK.wall_time_factor + (
        SLOW_WEBHOOK.webhook_delay_s * 4
    )
    assert webhook_wall < budget, (
        f"with a {SLOW_WEBHOOK.webhook_delay_s} s webhook, conversation "
        f"took {webhook_wall:.2f} s vs budget {budget:.2f} s "
        f"(baseline {baseline_wall:.2f} s × "
        f"{SLOW_WEBHOOK.wall_time_factor} + slack). The webhook may be "
        f"head-of-line blocking conversation completion more than expected."
    )

    # 3. RSS 绝对增量。 慢速Webhook的故障模式是*无界*缓冲区增长，因此相对预算会掩盖它。
    #
    assert probe.rss_delta_mb() < SLOW_WEBHOOK.max_rss_delta_mb, (
        f"RSS grew by {probe.rss_delta_mb():.1f} MB during the slow-webhook "
        f"run (budget {SLOW_WEBHOOK.max_rss_delta_mb}). The webhook "
        f"subscriber may be buffering events without bound."
    )


class _AlwaysFailReceiver(http.server.BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        self.send_response(503)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@pytest.fixture
def always_fail_webhook_url():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _AlwaysFailReceiver)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        t.join(timeout=2)


@pytest_asyncio.fixture
async def failing_webhook_service(tmp_path: Path, always_fail_webhook_url: str):
    persist = tmp_path / "persist_fail"
    persist.mkdir()
    service = ConversationService(
        conversations_dir=persist,
        webhook_specs=[
            WebhookSpec(
                base_url=always_fail_webhook_url,
                event_buffer_size=1,
                flush_delay=0.5,
                num_retries=0,
                retry_delay=0,
                max_queue_size=100,
            )
        ],
    )
    async with service:
        yield service


async def test_webhook_queue_bounded_under_sustained_downstream_failure(
    failing_webhook_service, tmp_path
):
    (tmp_path / "ws").mkdir()
    info = await start_conversation_with_test_llm(
        failing_webhook_service,
        parent_llm=SlowTestLLM.from_messages([text_message("done")], latency_s=0.0),
        workspace_dir=str(tmp_path / "ws"),
        usage_id="webhook-fail",
        initial_text=None,
    )
    es = await failing_webhook_service.get_event_service(info.id)
    assert es is not None
    # 白盒访问：该错误是在持续的下游故障下 WebhookSubscriber.queue 无限增长（
    # conversation_service.py:1059 将失败的批次无限制地向后延伸）。 没有公开 API 公开单
    # 个订阅者的队列，并且仅为回归测试添加一个队列会将测试问题带入生产中。 直接在此处访
    # 问_pub_sub。
    #
    webhook_sub = next(
        (
            s
            for s in es._pub_sub._subscribers.values()
            if isinstance(s, WebhookSubscriber)
        ),
        None,
    )
    assert webhook_sub is not None, (
        f"no WebhookSubscriber registered on the event service. Found: "
        f"{[type(s).__name__ for s in es._pub_sub._subscribers.values()]}"
    )

    n_events = 500
    for i in range(n_events):
        await es._pub_sub(
            ConversationStateUpdateEvent(
                key="execution_status", value=f"idle-{i}", source="environment"
            )
        )

    # 轮询直到队列稳定（两个连续的相同读数），而不是休眠固定的挂壁时间。 Webhook 规范使
    # 用
    # `flush_delay=0.5`，因此单个 0.5 秒的睡眠可以与刷新周期竞争并读取飞行中的值； 轮询
    # 可以让测试稳定下来，无论它落在刷新周期的哪个位置。
    #
    stable_deadline = time.monotonic() + 5.0
    last_size = -1
    stable_count = 0
    stabilised = False
    while time.monotonic() < stable_deadline:
        size = len(webhook_sub.queue)
        if size == last_size:
            stable_count += 1
            if stable_count >= 2:
                stabilised = True
                break
        else:
            stable_count = 0
        last_size = size
        await asyncio.sleep(0.1)
    assert stabilised, (
        f"webhook queue did not stabilise within 5 s "
        f"(last_size={last_size}); the assertion below would otherwise "
        f"fire on a mid-flight reading."
    )

    assert len(webhook_sub.queue) < n_events // 2, (
        f"queue grew to {len(webhook_sub.queue)} after {n_events} events; "
        f"failed batches are re-extended without bound."
    )
