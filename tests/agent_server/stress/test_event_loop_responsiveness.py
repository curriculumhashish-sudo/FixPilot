"""横切金丝雀：/health 在每个后台负载下保持响应。

为什么存在：
    大多数导致用户可见的“服务器挂起”症状的智能体服务器错误都归结为 asyncio 上的同步 I
    /O 线程。 每个单独的套件都会在其特定场景中检查这一点。 这个金丝雀
    在一个地方的代表性负载组合下检查它——添加成本低，捕获我们忘记专门测试的回归类。

行使负荷：
    - 长 bash 命令（睡眠 + 最终标记）——练习 bash_service。
    - 种子商店上的繁忙对话列表 - 练习持久化。

此处执行的负载不（由其自己的套件覆盖）：
    - 慢 Webhook (test_slow_webhook.py)。
    - 懒猴 WebSocket (test_slow_websocket_consumer.py)。
    - 高容量 bash 输出 (test_high_volume_bash_output.py)。
"""

import asyncio
import statistics
import time
from uuid import UUID

import pytest

from openhands.agent_server.bash_service import BashEventService
from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.models import StartConversationRequest
from openhands.sdk import Agent
from openhands.sdk.workspace import LocalWorkspace
from tests.agent_server.stress.budgets import EVENT_LOOP_RESPONSIVENESS
from tests.agent_server.stress.scripts import placeholder_llm


pytestmark = pytest.mark.stress


async def _measure_health_p95_p99(client, *, samples: int) -> tuple[float, float]:
    latencies: list[float] = []
    for _ in range(samples):
        t0 = time.monotonic()
        resp = await client.get("/health")
        latencies.append(time.monotonic() - t0)
        assert resp.status_code == 200
    quantiles = statistics.quantiles(latencies, n=100)
    # 分位数返回 99 个分割点； 索引 94 ≈ p95，98 ≈ p99。
    return quantiles[94], quantiles[98]


def _assert_within_budget(name: str, p95: float, p99: float) -> None:
    assert p95 < EVENT_LOOP_RESPONSIVENESS.health_p95_s, (
        f"under load '{name}', /health p95 = {p95 * 1000:.1f} ms exceeded "
        f"{EVENT_LOOP_RESPONSIVENESS.health_p95_s * 1000:.0f} ms. The event "
        f"loop is being blocked by this load."
    )
    assert p99 < EVENT_LOOP_RESPONSIVENESS.health_p99_s, (
        f"under load '{name}', /health p99 = {p99 * 1000:.1f} ms exceeded "
        f"{EVENT_LOOP_RESPONSIVENESS.health_p99_s * 1000:.0f} ms."
    )


async def test_health_responsive_under_long_bash(
    client,
    bash_service: BashEventService,
):
    """长 bash 命令一定不能让事件循环挨饿。"""
    samples = EVENT_LOOP_RESPONSIVENESS.health_samples

    # 基线：无负载。
    p95_baseline, p99_baseline = await _measure_health_p95_p99(client, samples=samples)
    _assert_within_budget("baseline", p95_baseline, p99_baseline)

    bash_duration_s = 4
    resp = await client.post(
        "/api/bash/start_bash_command",
        json={"command": f"sleep {bash_duration_s}; echo done", "timeout": 10},
    )
    assert resp.status_code == 200, resp.text
    cmd_id = UUID(resp.json()["id"])

    # 与 bash-completion 轮询交错 /health 采样，因此：
    #   (a) 样本在整个 bash 生命周期中着陆（进程内 ASGI 使
    #       单个 /health 调用亚毫秒，因此紧密突发只会覆盖第一帧并错过运行的 REST）；
    #   (b) 我们验证 bash 命令实际上运行到干净退出，否则
    #       无声的崩溃/提前退出会因错误的原因而通过预算（“/health在空载下速度很快”）。
    #
    latencies: list[float] = []
    deadline = time.monotonic() + bash_duration_s + 10
    final = None
    while time.monotonic() < deadline:
        for _ in range(5):
            t0 = time.monotonic()
            h_resp = await client.get("/health")
            latencies.append(time.monotonic() - t0)
            assert h_resp.status_code == 200

        # `limit=1, sort_order=TIMESTAMP_DESC` 所以我们只读取最新的事件，不管bash命令输
        # 出多少条 — 默认页面最多显示100条，我们不想有分页输出回归默默错过结局
        # BashOutput 这里。
        #
        events_resp = await client.get(
            "/api/bash/bash_events/search",
            params={
                "command_id__eq": str(cmd_id),
                "limit": 1,
                "sort_order": "TIMESTAMP_DESC",
            },
        )
        assert events_resp.status_code == 200, events_resp.text
        final = next(
            (
                e
                for e in events_resp.json()["items"]
                if e["kind"] == "BashOutput" and e.get("exit_code") is not None
            ),
            None,
        )
        if final is not None:
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail(f"bash command {cmd_id} never produced a final event")

    assert final["exit_code"] == 0, (
        f"background bash exited with {final['exit_code']}, expected 0; the "
        f"health-budget assertion below would have measured under no real load."
    )

    quantiles = statistics.quantiles(latencies, n=100)
    _assert_within_budget("long_bash", quantiles[94], quantiles[98])


async def test_health_responsive_under_busy_listing(
    conversation_service: ConversationService,
    client,
    tmp_path,
):
    """并行的大容量对话列表绝不能匮乏 /health."""
    samples = EVENT_LOOP_RESPONSIVENESS.health_samples
    workspace = str(tmp_path / "ws")
    (tmp_path / "ws").mkdir()

    # 开一家不起眼的商店。
    seed_n = 100
    seed_sem = asyncio.Semaphore(8)

    async def _seed(i: int):
        async with seed_sem:
            request = StartConversationRequest(
                agent=Agent(llm=placeholder_llm(f"resp-canary-{i}"), tools=[]),
                workspace=LocalWorkspace(working_dir=workspace),
                autotitle=False,
            )
            await conversation_service.start_conversation(request)

    await asyncio.gather(*[_seed(i) for i in range(seed_n)])

    # 在后台驱动器列表。
    stop = asyncio.Event()

    async def _listing_loop():
        while not stop.is_set():
            resp = await client.get(
                "/api/conversations/search",
                params={"limit": 50, "sort_order": "CREATED_AT_DESC"},
            )
            # 如果没有这个保护，列表中的 500 会默默地将测试变成“无负载下的/health”——由于
            # 错误的原因而通过。
            #
            assert resp.status_code == 200, resp.text

    bg_task = asyncio.create_task(_listing_loop())
    try:
        # 短暂的预热，以便在我们测量之前列表循环是热的。
        await asyncio.sleep(0.1)
        p95, p99 = await _measure_health_p95_p99(client, samples=samples)
        _assert_within_budget("busy_listing", p95, p99)
    finally:
        stop.set()
        await bg_task
