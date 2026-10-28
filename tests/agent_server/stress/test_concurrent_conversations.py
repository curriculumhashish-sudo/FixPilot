"""压力测试：许多单独的对话同时运行。

捕获的错误类：
    - 共享持久化层的会话之间存在租约争用。
    - 持久化写入争用（一个对话的追加阻塞了另一个对话）。
    - 交叉对话事件泄漏（事件最终出现在错误的日志中）。
    - 连接池/线程池耗尽，静默序列化运行。

与test_parallel_subagents.py不同：
    parallel_subagents 在 * 一个 * 对话中测试 N 子智能体。 这测试了N
    *分开的*个对话，所以热路径是conversation_lease，
    持久化/存储，以及 pub_sub 广播 — 而不是 TaskManager。
"""

import asyncio
import time
from uuid import UUID

import pytest

from openhands.agent_server.conversation_service import ConversationService
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.llm import Message, TextContent
from tests.agent_server.stress.budgets import CONCURRENT_CONVERSATIONS
from tests.agent_server.stress.probe import ResourceProbe
from tests.agent_server.stress.scripts import (
    SlowTestLLM,
    start_conversation_with_test_llm,
    wait_for_terminal,
)


pytestmark = pytest.mark.stress


def _build_simple_llm(latency_s: float) -> SlowTestLLM:
    """LLM 用一个文本响应编写脚本（无工具调用）。

    的智能体在收到第一个响应后，终止工具调用因此，一个对话中的一个脚本消息就足够了——
    额外的脚本消息永远不会被消费。
    """
    llm = SlowTestLLM.from_messages(
        [Message(role="assistant", content=[TextContent(text="done")])],
        latency_s=latency_s,
    )
    # from_messages 被输入为返回父级 TestLLM； 狭窄。
    assert isinstance(llm, SlowTestLLM)
    return llm


async def _start_one(
    conversation_service: ConversationService,
    *,
    workspace: str,
    latency_s: float,
    usage_id: str,
) -> tuple[UUID, SlowTestLLM]:
    parent_llm = _build_simple_llm(latency_s)
    info = await start_conversation_with_test_llm(
        conversation_service,
        parent_llm=parent_llm,
        workspace_dir=workspace,
        usage_id=usage_id,
        initial_text="hello",
    )
    return info.id, parent_llm


async def _run_and_wait(
    client, conversation_id: UUID
) -> tuple[float, ConversationExecutionStatus]:
    t0 = time.monotonic()
    run_resp = await client.post(f"/api/conversations/{conversation_id.hex}/run")
    assert run_resp.status_code == 200, run_resp.text
    status = await wait_for_terminal(client, conversation_id, timeout_s=60.0)
    return time.monotonic() - t0, status


async def test_concurrent_conversations_isolated_and_fast(
    conversation_service: ConversationService,
    client,
    tmp_path,
    probe: ResourceProbe,
):
    """N并发个对话：全部完整，无交叉泄漏，并行性。"""
    n = CONCURRENT_CONVERSATIONS.n_conversations
    latency_s = CONCURRENT_CONVERSATIONS.per_call_latency_s
    workspace = str(tmp_path / "ws")
    (tmp_path / "ws").mkdir()

    # 1. 单对话参考时序 — 相同的循环，相同的测试夹具。
    ref_id, ref_llm = await _start_one(
        conversation_service,
        workspace=workspace,
        latency_s=latency_s,
        usage_id="conc-ref",
    )
    ref_wall, ref_status = await _run_and_wait(client, ref_id)
    assert ref_status == ConversationExecutionStatus.FINISHED
    assert ref_llm.remaining_responses == 0

    # 快照探测状态介于参考和并发运行之间，因此下面的 RSS 预算仅测量并发运行 — 请参阅
    # test_parallel_subagents.py 了解相同的模式。
    #
    pre_concurrent_idx = len(probe.samples)
    assert pre_concurrent_idx > 0, "ResourceProbe yielded no samples?"
    pre_concurrent_rss_mb = probe.samples[-1].rss_mb

    # 2. 现在有 N并发个对话。
    started = await asyncio.gather(
        *[
            _start_one(
                conversation_service,
                workspace=workspace,
                latency_s=latency_s,
                usage_id=f"conc-{i}",
            )
            for i in range(n)
        ]
    )

    t0 = time.monotonic()
    results = await asyncio.gather(
        *[_run_and_wait(client, conv_id) for conv_id, _llm in started]
    )
    concurrent_wall = time.monotonic() - t0

    # 3. 每一次谈话都干净利落地结束。
    for i, (_wall, status) in enumerate(results):
        assert status == ConversationExecutionStatus.FINISHED, (
            f"conversation {i} ended in {status}, expected FINISHED. "
            f"Possible lease contention or persistence error."
        )

    # 4. 每个 LLM 实际上都被耗尽了——捕捉到“所有共享一个 LLM 的对话”或“错误的 LLM 拾取”回
    # 归。
    #
    for i, (_, llm) in enumerate(started):
        assert llm.remaining_responses == 0, (
            f"conversation {i} LLM not drained "
            f"({llm.remaining_responses} responses left). Cross-conversation "
            f"event leak or LLM mix-up?"
        )

    # 5. 并行性。 并发墙必须远小于n×ref_wall。
    serial_estimate = ref_wall * n
    budget = ref_wall * CONCURRENT_CONVERSATIONS.wall_time_factor
    assert concurrent_wall < budget, (
        f"concurrent wall ({concurrent_wall:.2f}s) > budget ({budget:.2f}s "
        f"= ref {ref_wall:.2f}s × {CONCURRENT_CONVERSATIONS.wall_time_factor}). "
        f"Serial estimate would be {serial_estimate:.2f}s. Conversations "
        f"are running effectively in series — likely a global lock somewhere."
    )

    # 6. 持久化理智：磁盘上的目录集必须与我们启动的对话 ID 集完全匹配。 在验证ID集（而不
    # 是数量）时，可以捕捉“正确数量，错误ID” — e.g。 对话无法启动，但留下了一个目录，重
    # 试成功但使用了不同的 ID。
    #
    expected_ids = {ref_id, *(conv_id for conv_id, _llm in started)}
    on_disk_ids = {UUID(d.name) for d in (tmp_path / "persist").iterdir() if d.is_dir()}
    assert on_disk_ids == expected_ids, (
        f"persisted dirs don't match started conversations. "
        f"missing={expected_ids - on_disk_ids}, "
        f"extra={on_disk_ids - expected_ids}."
    )

    # 7. 资源预算。 与参考运行和并发运行之间拍摄的快照相比，因此此处不归因于参考运行的尖
    # 峰。
    #
    concurrent_peak_rss_mb = max(
        (s.rss_mb for s in probe.samples[pre_concurrent_idx:]),
        default=pre_concurrent_rss_mb,
    )
    rss_growth = (concurrent_peak_rss_mb - pre_concurrent_rss_mb) / max(
        pre_concurrent_rss_mb, 1.0
    )
    assert rss_growth < CONCURRENT_CONVERSATIONS.rss_growth_factor, (
        f"RSS grew {rss_growth:.2f}× during concurrent run (budget < "
        f"{CONCURRENT_CONVERSATIONS.rss_growth_factor}×). Conversation "
        f"teardown may not be releasing memory."
    )
