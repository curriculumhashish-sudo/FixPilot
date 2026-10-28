"""压力测试：长时间运行的 bash 命令不得阻塞事件循环。

捕获的错误类：
    - 在长 bash 命令期间阻塞异步路径中的 I/O（同步子进程调用而不是 asyncio.subprocess
    ）。
    - PTYs / 指令执行完毕或超时后泄露。
    - 当 bash 运行时，智能体-服务器在 /health 上失去响应能力。

API 差距（已记录）：
    bash 路由器公开 ``POST /api/bash/start_bash_command``（背景）和
    ``DELETE /api/bash/bash_events``（清除所有），但 ** 没有每个命令的终止/取消端点**
    。 该提案的“取消返回< 1s”断言目前无法
    通过公众测试API。 最接近的替代是 ExecuteBashRequest 上的 ``timeout`` 字段，它强制
    服务在截止日期后执行 SIGKILL 流程 (
    bash_service.py:274)。 我们在这里练习该代码路径。 真正的取消端点需要进行单独的测
    试。

CI模式：
    ``--stress-quick``（默认）：5 秒。 ``--stress-full`` 根据提案，将增加到 1800 秒。
     我们不在这里的漫长道路上设门； 这是
    一个单独的工作流程。
"""

import asyncio
import os
import statistics
import time
from uuid import UUID

import pytest

from openhands.agent_server.bash_service import BashEventService
from tests.agent_server.stress.budgets import LONG_RUNNING_COMMAND
from tests.agent_server.stress.scripts import descendants_of


pytestmark = pytest.mark.stress


async def test_long_running_bash_does_not_block_event_loop(
    client,
    bash_service: BashEventService,
):
    """当 bash 运行时，/health 必须保持响应并且进程树
    必须在命令结束或超时后清理。"""
    duration = LONG_RUNNING_COMMAND.duration_s

    # 启动一个命令，该命令保持活动状态 ``duration`` 秒并发出最终标记。 我们为服务提供稍
    # 大的超时，以便自然退出路径运行（我们在下面单独测试超时路径）。
    #
    pre_children = set(p.pid for p in descendants_of(os.getpid()))
    resp = await client.post(
        "/api/bash/start_bash_command",
        json={
            "command": f"sleep {duration}; echo done",
            "timeout": duration + 5,
        },
    )
    assert resp.status_code == 200, resp.text
    cmd_id = UUID(resp.json()["id"])

    # bash 命令运行时连续采样 /health。 N 个请求的预循环突发将在约 100 毫秒内完成（进程
    # 内 ASGI），因此稍后在 5 秒窗口中发生的阻塞将不会被观察到。 与完成轮询交错可将样本
    # 分布在整个 bash 生命周期中。
    #
    health_lats: list[float] = []
    deadline = time.monotonic() + duration + 10
    while time.monotonic() < deadline:
        for _ in range(5):
            t0 = time.monotonic()
            # 将每个请求限制在剩余的墙上时间，以便挂起的 /health 无法绕过 `deadline`（使
            # 用 0.1 秒的下限以避免在边界上传递零/负值）。
            #
            remaining = max(0.1, deadline - time.monotonic())
            h_resp = await client.get("/health", timeout=remaining)
            health_lats.append(time.monotonic() - t0)
            assert h_resp.status_code == 200

        # `limit=1, sort_order=TIMESTAMP_DESC` 仅获取最新事件。 默认页数上限为100； 如果
        # 回归时，bash 会发出每行/每字的输出（这是 test_high_volume_… 所测试的），那么第
        # 一次页面的加载可能会错过最后一个事件，从而无声地超时。
        #
        events = await client.get(
            "/api/bash/bash_events/search",
            params={
                "command_id__eq": str(cmd_id),
                "limit": 1,
                "sort_order": "TIMESTAMP_DESC",
            },
        )
        items = events.json()["items"]
        # 最后的 BashOutput 带有 exit_code != null。
        final = next(
            (
                e
                for e in items
                if e["kind"] == "BashOutput" and e.get("exit_code") is not None
            ),
            None,
        )
        if final is not None:
            assert final["exit_code"] == 0
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail(f"command {cmd_id} did not finish within {duration + 10}s")

    # 1. /health 始终保持响应。 p95 预算捕获事件循环饥饿； 这里的失败通常表示同步子进程.
    # *在异步路径中。 需要 ≥ 10 个样本，因此 n=20 分位数是真正的 p95，而不是向 max(...)
    # 折叠。
    #
    assert len(health_lats) >= 10, (
        f"only {len(health_lats)} /health samples collected during the "
        f"bash run; not enough for a representative p95."
    )
    p95 = statistics.quantiles(health_lats, n=20)[-1]
    assert p95 < LONG_RUNNING_COMMAND.health_p95_s, (
        f"/health p95 {p95 * 1000:.1f} ms during running bash exceeded "
        f"{LONG_RUNNING_COMMAND.health_p95_s * 1000:.0f} ms. The event loop "
        f"is probably being blocked by the bash command's I/O."
    )

    # 2. 没有后代进程泄漏。 bash 子进程及其任何子级必须在命令完成后 cleanup_timeout_s 内
    # 收获。
    #
    cleanup_deadline = time.monotonic() + LONG_RUNNING_COMMAND.cleanup_timeout_s
    leaked: set[int] = set()
    while time.monotonic() < cleanup_deadline:
        post_children = set(p.pid for p in descendants_of(os.getpid()))
        leaked = post_children - pre_children
        if not leaked:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail(
            f"after {LONG_RUNNING_COMMAND.cleanup_timeout_s}s, descendants of "
            f"the test process include unexpected pids: {leaked}. Bash "
            f"subprocess teardown is leaking children."
        )


async def test_bash_timeout_kills_process_cleanly(
    client,
    bash_service: BashEventService,
):
    """超出其范围的命令 ``timeout`` 是 SIGKILLed, exit_code reported,
    后代树中没有留下任何僵尸。

    这是最接近的显式取消可用替代方案； 有关 API 间隙，请参阅模块文档字符串。
    """
    pre_children = set(p.pid for p in descendants_of(os.getpid()))

    resp = await client.post(
        "/api/bash/start_bash_command",
        json={
            "command": "sleep 30",
            "timeout": 1,  # 强制超时-kill 路径
        },
    )
    assert resp.status_code == 200, resp.text
    cmd_id = UUID(resp.json()["id"])

    # 等待超时发射并传播杀戮。
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        # 请参阅兄弟测试以了解原因 `limit=1, sort_order=TIMESTAMP_DESC`。
        events = await client.get(
            "/api/bash/bash_events/search",
            params={
                "command_id__eq": str(cmd_id),
                "limit": 1,
                "sort_order": "TIMESTAMP_DESC",
            },
        )
        items = events.json()["items"]
        final = next(
            (
                e
                for e in items
                if e["kind"] == "BashOutput" and e.get("exit_code") is not None
            ),
            None,
        )
        if final is not None:
            # exit_code -1 是  bash_service 超时信号 SIGKILLed" (bash_service.py:289).
            #
            assert final["exit_code"] == -1, (
                f"expected exit_code -1 (timeout-kill), got {final['exit_code']}"
            )
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail("timeout-killed command never produced a final event")

    cleanup_deadline = time.monotonic() + LONG_RUNNING_COMMAND.cleanup_timeout_s
    leaked: set[int] = set()
    while time.monotonic() < cleanup_deadline:
        post_children = set(p.pid for p in descendants_of(os.getpid()))
        leaked = post_children - pre_children
        if not leaked:
            return
        await asyncio.sleep(0.1)
    pytest.fail(
        f"after timeout-kill, descendants still include {leaked}. "
        f"SIGKILL path is leaving zombies."
    )
