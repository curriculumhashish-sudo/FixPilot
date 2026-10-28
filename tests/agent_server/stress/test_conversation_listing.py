"""压力测试：列出许多对话。

捕获的错误类：
    - O(N) 列出分页应为 O(page_size) 的位置。
    - 分页相差一位或重复。
    - 列表期间意外保留全局锁（将序列化并发列出调用并导致 p95 膨胀）。
    - 每次调用泄漏：列出 N 次不应按比例增长 RSS。

为什么 N=2000 而不是 10k：
    遍历 start_conversation 10k 次需要几分钟； 之后通过
    ``ConversationService.__aenter__`` 加载它们又需要几
    分钟。 N=2000 仍然表面 O(N) 回归强烈，同时将测试保持在一分钟以内。
"""

import asyncio
import os
import statistics
import time
from uuid import UUID

import pytest

from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.models import StartConversationRequest
from openhands.sdk import Agent
from openhands.sdk.workspace import LocalWorkspace
from tests.agent_server.stress.budgets import CONVERSATION_LISTING
from tests.agent_server.stress.probe import ResourceProbe
from tests.agent_server.stress.scripts import placeholder_llm


pytestmark = pytest.mark.stress


async def _seed_conversations(
    conversation_service: ConversationService,
    *,
    n: int,
    workspace_dir: str,
) -> set[UUID]:
    """通过公共服务路径进行n次对话。

    Concurrency=8 is enough to amortize the per-conversation fixed cost
    不会压垮租赁层。 我们使用占位符 LLM 和
    autotitle=False so seeding never hits the network.
    """
    semaphore = asyncio.Semaphore(8)

    async def _one(i: int) -> UUID:
        async with semaphore:
            # 否则，No initial_message: start_conversation 会调用
            # event_service.send_message(..., run_after_send=True)，这会调用占位符 LLM
            # 并因真正的身份验证错误而失败。 我们只需要持久化行存在即可列出。
            #
            request = StartConversationRequest(
                agent=Agent(llm=placeholder_llm(f"seed-{i}"), tools=[]),
                workspace=LocalWorkspace(working_dir=workspace_dir),
                autotitle=False,
            )
            info, _ = await conversation_service.start_conversation(request)
            return info.id

    ids = await asyncio.gather(*[_one(i) for i in range(n)])
    return set(ids)


_MAX_PAGINATION_ITERATIONS = 10_000


async def _walk_pages(
    client, *, page_size: int, sort_order: str
) -> list[tuple[UUID, str]]:
    """遍历 /api/conversations/search. 的每一页

    按 API 返回顺序返回 ``(id, created_at)`` 对。 ``created_at`` 是响应中的原始 ISO
    字符串； 调用者将其两两进行比较，以
    验证 ``sort_order`` 确实得到了尊重。 UTC-only 时间戳使字典比较相当于按时间顺序比
    较。
    """
    seen: list[tuple[UUID, str]] = []
    page_id: str | None = None
    # 此文件上没有 `pytest.mark.timeout`，因此循环 `next_page_id` 将无限期挂起。 在 N=
    # 2000 / limit=50 时，我们预计
    # ~40 次迭代； 10k 是 250 倍的安全裕度。
    for _ in range(_MAX_PAGINATION_ITERATIONS):
        params: dict[str, object] = {
            "limit": page_size,
            "sort_order": sort_order,
        }
        if page_id is not None:
            params["page_id"] = page_id
        resp = await client.get("/api/conversations/search", params=params)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for item in body["items"]:
            seen.append((UUID(item["id"]), item["created_at"]))
        page_id = body.get("next_page_id")
        if not page_id:
            return seen
    raise AssertionError(
        f"pagination did not terminate in {_MAX_PAGINATION_ITERATIONS} "
        f"iterations — possible circular next_page_id."
    )


async def _find_last_page_id(client, *, page_size: int, sort_order: str) -> str | None:
    """返回最后一页的 page_id 光标，如果分页则返回 None
    适合单页。"""
    page_id: str | None = None
    for _ in range(_MAX_PAGINATION_ITERATIONS):
        params: dict[str, object] = {"limit": page_size, "sort_order": sort_order}
        if page_id is not None:
            params["page_id"] = page_id
        resp = await client.get("/api/conversations/search", params=params)
        assert resp.status_code == 200, resp.text
        next_id = resp.json().get("next_page_id")
        if not next_id:
            return page_id
        page_id = next_id
    raise AssertionError(
        f"pagination did not terminate in {_MAX_PAGINATION_ITERATIONS} "
        f"iterations — possible circular next_page_id."
    )


async def _time_first_page(client, *, page_size: int) -> float:
    t0 = time.monotonic()
    resp = await client.get(
        "/api/conversations/search",
        params={"limit": page_size, "sort_order": "CREATED_AT_DESC"},
    )
    assert resp.status_code == 200
    return time.monotonic() - t0


async def _time_deep_page(client, *, page_size: int, page_id: str) -> float:
    t0 = time.monotonic()
    resp = await client.get(
        "/api/conversations/search",
        params={
            "limit": page_size,
            "sort_order": "CREATED_AT_DESC",
            "page_id": page_id,
        },
    )
    assert resp.status_code == 200
    return time.monotonic() - t0


async def test_pagination_is_correct_and_bounded(
    conversation_service: ConversationService,
    client,
    tmp_path,
    probe: ResourceProbe,
):
    """种子 N，遍历页面，断言正确性 + 延迟 + 内存边界。"""
    n = CONVERSATION_LISTING.n_conversations
    page_size = CONVERSATION_LISTING.page_size
    workspace = str(tmp_path / "ws")
    (tmp_path / "ws").mkdir()

    seeded = await _seed_conversations(
        conversation_service, n=n, workspace_dir=workspace
    )
    assert len(seeded) == n, "seeding hit a UUID collision (cosmically unlikely)"

    # 1. 正确性：分页集 == 种子集，无重复。
    paged = await _walk_pages(client, page_size=page_size, sort_order="CREATED_AT_DESC")
    paged_ids = [u for u, _ in paged]
    assert len(paged_ids) == n, (
        f"pagination returned {len(paged_ids)} items, seeded {n}. "
        f"Duplicates or missing pages?"
    )
    assert set(paged_ids) == seeded, (
        "pagination returned a different set than was seeded. "
        f"Diff: missing={seeded - set(paged_ids)}, "
        f"extra={set(paged_ids) - seeded}."
    )

    # 1b. 排序顺序：CREATED_AT_DESC 实际上必须是降序。 如果没有这个，忽略 sort_order 的
    # 回归仍然会通过集合/计数检查。 created_at 字符串是 UTC ISO，所以字典顺序 == 按时间
    # 顺序排列。
    #
    timestamps = [t for _, t in paged]
    first_break = next(
        (i for i in range(len(timestamps) - 1) if timestamps[i] < timestamps[i + 1]),
        -1,
    )
    assert first_break == -1, (
        f"CREATED_AT_DESC did not return items in descending order. "
        f"First disagreement at index {first_break}: "
        f"{timestamps[first_break]} < {timestamps[first_break + 1]}."
    )

    # 1c. 排序顺序：CREATED_AT (ASC) 实际上必须是升序。 与上面的 1b 一起，这捕获了一个忽
    # 略 sort_order 的回归，并且始终返回一个固定方向（单独的 1b 不会注意到）。
    #
    paged_asc = await _walk_pages(client, page_size=page_size, sort_order="CREATED_AT")
    timestamps_asc = [t for _, t in paged_asc]
    first_break_asc = next(
        (
            i
            for i in range(len(timestamps_asc) - 1)
            if timestamps_asc[i] > timestamps_asc[i + 1]
        ),
        -1,
    )
    assert first_break_asc == -1, (
        f"CREATED_AT did not return items in ascending order. "
        f"First disagreement at index {first_break_asc}: "
        f"{timestamps_asc[first_break_asc]} > {timestamps_asc[first_break_asc + 1]}."
    )

    # 2. 计数端点个匹配项。
    count_resp = await client.get("/api/conversations/count")
    assert count_resp.status_code == 200
    assert count_resp.json() == n

    # 3. 首页延迟预算。 在共享 CI 运行器 (2-vCPU) 上
    # 每个项目的恒定时间工作比开发人员笔记本电脑慢得多，因此放宽 CI=True 下的绝对上限。
    # N=2000 时的真实 O(N) 回归会产生 10-100 倍的减速，因此 4 倍的余量仍然可以大声捕捉到
    # 它。 下面的深度页面检查已经是一个比率（相对于基线）并且保持可移植性。
    #
    p95_budget = CONVERSATION_LISTING.p95_first_page_s * (
        4.0 if os.getenv("CI") else 1.0
    )
    first_page_samples = [
        await _time_first_page(client, page_size=page_size) for _ in range(10)
    ]
    p95_first = statistics.quantiles(first_page_samples, n=20)[-1]
    assert p95_first < p95_budget, (
        f"first-page p95 {p95_first:.3f}s > budget {p95_budget}s "
        f"(CI={'on' if os.getenv('CI') else 'off'}). Listing has likely gone "
        f"O(N)."
    )

    # 4. 深页延迟降低：应该是平稳的，而不是悬崖。
    # 当 N=2000 且 page_size=50 时，我们预计约为 40 页，因此 _find_last_page_id 必须返回
    # 非 None 游标。 None 这里意味着 API 返回一页中的所有内容（分页损坏） - 大声断言，以
    # 便深页块不会默默无操作。
    #
    deep_page_id = await _find_last_page_id(
        client, page_size=page_size, sort_order="CREATED_AT_DESC"
    )
    assert deep_page_id is not None, (
        f"expected multi-page pagination for N={n} with page_size={page_size}, "
        f"but the API returned everything in one page. Pagination is broken."
    )
    deep_samples = [
        await _time_deep_page(client, page_size=page_size, page_id=deep_page_id)
        for _ in range(10)
    ]
    p95_deep = statistics.quantiles(deep_samples, n=20)[-1]
    ratio = p95_deep / max(p95_first, 1e-6)
    assert ratio < CONVERSATION_LISTING.deep_page_factor, (
        f"deep-page p95 ({p95_deep:.3f}s) is {ratio:.1f}× first-page "
        f"({p95_first:.3f}s). Pagination likely re-scans from the start each "
        f"call."
    )

    # 5. RSS 在紧密的列表循环期间。 每次调用斜率在进程中噪音太大（分配器行为、碎片），因
    # 此我们测量列表开始与列表期间峰值。 “每次调用时将所有内容都列出到内存中”回归会超出
    # 此范围； 分配器噪音则不然。
    #
    # 仅使用在循环中捕获的样本 — `probe.peak_rss_mb()` 返回所有时间的峰值，这将包括测试
    # 早期的种子峰并人为夸大了差异。
    #
    pre_loop_idx = len(probe.samples)
    assert pre_loop_idx > 0, "ResourceProbe yielded no samples — fixture not entered?"
    pre_loop_rss = probe.samples[-1].rss_mb
    for _k in range(50):
        await _time_first_page(client, page_size=page_size)
    peak_during_loop = max(
        (s.rss_mb for s in probe.samples[pre_loop_idx:]),
        default=pre_loop_rss,
    )
    delta = peak_during_loop - pre_loop_rss
    assert delta < CONVERSATION_LISTING.listing_rss_delta_mb, (
        f"RSS grew {delta:.1f} MB during 50 list calls "
        f"({pre_loop_rss:.1f} → peak {peak_during_loop:.1f} MB; budget "
        f"{CONVERSATION_LISTING.listing_rss_delta_mb} MB). The listing path "
        f"may be materializing the full store into memory per call."
    )
