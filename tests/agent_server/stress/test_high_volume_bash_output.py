"""压力测试：大量 bash 输出必须合并，而不是每字节 1 个事件。

捕获的错误类：
    - O(N²) 下的每字节/每行 BashOutput 事件创建
      `yes`式快速输出。
    - bash 淹没执行器时服务器无响应。
    - Bash 事件存储无限增长。

“合并”在此代码库中的含义：
    bash_service.MAX_CONTENT_CHAR_LENGTH 为 1 MiB (1024*1024)。 当缓冲区超过该阈值或
    在命令结束时发出
    BashOutput。 因此，5 MiB `yes` 次洪水会产生约 5-6 个事件，而不是数千个事件。
"""

import asyncio
import os
import statistics
import time
from uuid import UUID

import pytest

from openhands.agent_server.bash_service import BashEventService
from tests.agent_server.stress.budgets import HIGH_VOLUME_BASH_OUTPUT
from tests.agent_server.stress.scripts import descendants_of


pytestmark = [pytest.mark.stress, pytest.mark.timeout(60)]


async def test_high_volume_bash_output_is_bounded(
    client,
    bash_service: BashEventService,
):
    """运行快速发出的命令； 断言事件计数有界并且
    /health 始终保持响应。"""
    duration = HIGH_VOLUME_BASH_OUTPUT.duration_s

    # `yes | head -c <bytes>` 快速发射已知大小的洪水； 与确定性字节计数的耦合使得事件计
    # 数断言在机器上稳定（受挂钟限制的`yes`产生可变输出）。
    #
    flood_bytes = 5 * 1024 * 1024  # 5MB
    pre_children = set(p.pid for p in descendants_of(os.getpid()))
    resp = await client.post(
        "/api/bash/start_bash_command",
        json={
            "command": f"yes | head -c {flood_bytes}",
            "timeout": int(duration + 5),
        },
    )
    assert resp.status_code == 200, resp.text
    cmd_id = UUID(resp.json()["id"])

    # 当洪水运行时，采样 /health 延迟。
    health_lats: list[float] = []
    flood_deadline = time.monotonic() + duration + 5
    while time.monotonic() < flood_deadline:
        # `limit=1, sort_order=TIMESTAMP_DESC` 只获取最新事件。 默认页数上限为100； 这个
        # 测试故意生成输出 *could* 超出每字/行的限制回归所以，第一次页面加载会错过最后的
        #  BashOutput 循环会因为错误的原因超时。 下面的专用事件计数断言明确地分页以捕获
        # 底层回归。
        #
        events_resp = await client.get(
            "/api/bash/bash_events/search",
            params={
                "command_id__eq": str(cmd_id),
                "limit": 1,
                "sort_order": "TIMESTAMP_DESC",
            },
        )
        items = events_resp.json()["items"]
        final = next(
            (
                e
                for e in items
                if e["kind"] == "BashOutput" and e.get("exit_code") is not None
            ),
            None,
        )

        # 每次循环迭代都会锤击健康几次。
        for _ in range(5):
            t0 = time.monotonic()
            h_resp = await client.get("/health")
            health_lats.append(time.monotonic() - t0)
            assert h_resp.status_code == 200

        if final is not None:
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("yes flood did not terminate within budget")

    # 计算该命令的所有事件。 端点搜索每一页都限制在100个结果，所以单次请求无法告诉我们超
    # 过100个的结果——我们只能分页，否则我们可能会无意识地将“超过100个事件”视为“恰好100个
    # ”。
    #
    total_events = 0
    page_id: str | None = None
    while True:
        params: dict[str, object] = {
            "command_id__eq": str(cmd_id),
            "limit": 100,
        }
        if page_id is not None:
            params["page_id"] = page_id
        page = (await client.get("/api/bash/bash_events/search", params=params)).json()
        total_events += len(page["items"])
        page_id = page.get("next_page_id")
        if not page_id:
            break

    # 1. 事件计数有限。 通过 1 MiB 个基于缓冲区的合并，5 MiB 个洪水会产生 ~5–6
    # BashOutput 个事件加上 1 BashCommand 个事件。 每条线的排放量将激增至数百万。
    #
    assert total_events < HIGH_VOLUME_BASH_OUTPUT.max_events, (
        f"bash flood produced {total_events} events for "
        f"{flood_bytes} bytes (budget < {HIGH_VOLUME_BASH_OUTPUT.max_events}). "
        f"Output is being emitted per-line/per-byte instead of coalesced."
    )

    # 2. /health 始终保持响应。 需要 ≥ 10 个样本，因此
    # n=20 quantile actually represents a p95 — with fewer samples it
    # 向最大值崩溃并且断言不再有意义。
    assert len(health_lats) >= 10, (
        f"only {len(health_lats)} /health samples collected during the "
        f"flood; not enough for a representative p95. Either the flood "
        f"finished before sampling could land or the polling loop is "
        f"misconfigured."
    )
    p95 = statistics.quantiles(health_lats, n=20)[-1]
    assert p95 < HIGH_VOLUME_BASH_OUTPUT.health_p95_s, (
        f"/health p95 {p95 * 1000:.1f} ms during bash flood (budget "
        f"{HIGH_VOLUME_BASH_OUTPUT.health_p95_s * 1000:.0f} ms). The "
        f"flood is starving the event loop."
    )

    # 3. 管道清理：`yes | head -c N`是两个进程（shell
    # 是的，产生了头和作家）。 完成命令后，所有后代都必须被收割 bash_service 在管道中处
    # 理过程组时出现错误会导致泄漏子进程 test_long_running_command 它不显现（只锻炼非管
    # 道壳）。
    #
    cleanup_deadline = time.monotonic() + 3.0
    leaked: set[int] = set()
    while time.monotonic() < cleanup_deadline:
        leaked = set(p.pid for p in descendants_of(os.getpid())) - pre_children
        if not leaked:
            break
        await asyncio.sleep(0.1)
    assert not leaked, (
        f"after the flood ended, descendants of the test process still "
        f"include {leaked}. bash_service is leaking pipeline children."
    )
