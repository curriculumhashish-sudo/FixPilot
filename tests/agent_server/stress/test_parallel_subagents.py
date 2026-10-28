"""压力测试：单个对话中的许多并行子智能体。

捕获的错误类：
    - 事件归因竞赛（任务获得混合子智能体个结果）。
    - 当 N 子智能体并发发布时，发布-订阅损坏。
    - 子智能体注册表泄漏（工厂从未发布）。
    - 工具并发回归，默默地序列化并行工具调用。

为什么需要 SlowTestLLM：
    Stock TestLLM 在微秒内响应。 八子智能体串行完成的速度如此之快，以至于墙上的时间无
    法告诉我们它们是否实际上是并行运行的。 每次 LLM 调用添加约 2
    00 毫秒，使得串行（约 8 × 200 毫秒）和并行（约 200 毫秒）之间的差距足够大，足以进
    行断言。

微妙的陷阱 (manager.py:314):
    运行之前的 TaskManager model_copies 子智能体的 LLM。
    ``_call_count``（int）独立于副本； ``_scripted_responses``（双端队列）是引用共享
    的。 因此，我们通过
    ``remaining_responses`` 而不是 ``call_count`` 对原始子智能体 LLM 进行断言。
"""

import json
import time

import pytest

from openhands.agent_server.conversation_service import ConversationService
from openhands.sdk import Agent, Tool
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.subagent.registry import _reset_registry_for_tests, register_agent
from openhands.tools.task import TaskToolSet
from tests.agent_server.stress.budgets import PARALLEL_SUBAGENTS
from tests.agent_server.stress.probe import ResourceProbe
from tests.agent_server.stress.scripts import (
    SlowTestLLM,
    start_conversation_with_test_llm,
    text_message,
    wait_for_terminal,
)


pytestmark = pytest.mark.stress


@pytest.fixture(autouse=True)
def _reset_registry():
    """子智能体注册表是模块全局的； 每次测试隔离。"""
    _reset_registry_for_tests()
    yield
    _reset_registry_for_tests()


def _task_tool_call(call_id: str, subagent_type: str, prompt: str) -> MessageToolCall:
    return MessageToolCall(
        id=call_id,
        name="task",
        arguments=json.dumps({"prompt": prompt, "subagent_type": subagent_type}),
        origin="completion",
    )


def _register_subagents(n: int, latency_s: float) -> list[SlowTestLLM]:
    sub_llms: list[SlowTestLLM] = []
    for i in range(n):
        sub_llm = SlowTestLLM.from_messages(
            [text_message(f"sub-agent {i} done")],
            latency_s=latency_s,
        )
        # from_messages 被输入为返回父级 TestLLM； 狭窄。
        assert isinstance(sub_llm, SlowTestLLM)
        sub_llms.append(sub_llm)
        register_agent(
            name=f"stress_subagent_{i}",
            # `_bound=sub_llm` 在定义时捕获当前的 sub_llm； 如果没有它，所有工厂都会关闭
            # 循环变量并最终仅返回最后一个 `sub_llm`。
            #
            factory_func=lambda llm, _bound=sub_llm: Agent(llm=_bound, tools=[]),
            description=f"stress test sub-agent {i}",
        )
    return sub_llms


def _build_parent_llm(n: int, latency_s: float) -> SlowTestLLM:
    """Parent 发出一条包含 n 个并行任务工具调用的消息，然后
    观测结果回来后终端短信。"""
    delegations = Message(
        role="assistant",
        content=[TextContent(text="delegating")],
        tool_calls=[
            _task_tool_call(
                call_id=f"call_{i}",
                subagent_type=f"stress_subagent_{i}",
                prompt=f"task {i}",
            )
            for i in range(n)
        ],
    )
    llm = SlowTestLLM.from_messages(
        [delegations, text_message("all done")], latency_s=latency_s
    )
    # from_messages 被输入为返回父级 TestLLM； 狭窄。
    assert isinstance(llm, SlowTestLLM)
    return llm


async def _run_once(
    conversation_service: ConversationService,
    client,
    workspace: str,
    *,
    n_subagents: int,
    tool_concurrency_limit: int,
    latency_s: float,
    usage_id: str,
) -> tuple[float, list[SlowTestLLM], ConversationExecutionStatus]:
    sub_llms = _register_subagents(n_subagents, latency_s)
    parent_llm = _build_parent_llm(n_subagents, latency_s)
    info = await start_conversation_with_test_llm(
        conversation_service,
        parent_llm=parent_llm,
        workspace_dir=workspace,
        usage_id=usage_id,
        tools=[Tool(name=TaskToolSet.name)],
        tool_concurrency_limit=tool_concurrency_limit,
        initial_text=f"run {n_subagents} task(s)",
    )

    t0 = time.monotonic()
    run_resp = await client.post(f"/api/conversations/{info.id.hex}/run")
    assert run_resp.status_code == 200, run_resp.text
    status = await wait_for_terminal(client, info.id, timeout_s=30.0)
    return time.monotonic() - t0, sub_llms, status


async def test_parallel_subagents_all_complete(
    conversation_service: ConversationService,
    client,
    tmp_path,
    probe: ResourceProbe,
):
    """N=8 sub-agents in parallel: all complete, parallelism observed, no leak."""
    n = PARALLEL_SUBAGENTS.n_subagents
    latency_s = PARALLEL_SUBAGENTS.per_call_latency_s
    workspace = str(tmp_path / "ws")
    (tmp_path / "ws").mkdir()

    # 单智能体参考，然后注册表复位。
    single_wall, single_subs, single_status = await _run_once(
        conversation_service,
        client,
        workspace,
        n_subagents=1,
        tool_concurrency_limit=1,
        latency_s=latency_s,
        usage_id="stress-parent-single",
    )
    assert single_status == ConversationExecutionStatus.FINISHED
    assert single_subs[0].remaining_responses == 0
    _reset_registry_for_tests()

    # 快照探测参考运行和并行运行之间的状态，因此下面的资源断言仅测量**并行运行。 如果没
    # 有这个，峰值/基线包括由单次智能体运行引起的任何 RSS 尖峰，这与我们正在检查的泄漏无
    # 关。
    #
    pre_parallel_idx = len(probe.samples)
    pre_parallel_rss_mb = probe.samples[-1].rss_mb

    # 现在实际运行 n-子智能体。
    parallel_wall, sub_llms, status = await _run_once(
        conversation_service,
        client,
        workspace,
        n_subagents=n,
        tool_concurrency_limit=n,
        latency_s=latency_s,
        usage_id="stress-parent-parallel",
    )

    # 1. 每个子智能体只运行一次。 我们主张 remaining_responses（已耗尽的队列）而不是
    # call_count：TaskManager model_copies 子智能体 LLM（manager.py:314），以及复制有自
    # 己的整数 _call_count，而脚本响应的队列是引用共享的。 remaining_responses反映了原始
    # LLM的队列是否实际上被排空； 原件上的call_count始终显示为0。
    #
    assert status == ConversationExecutionStatus.FINISHED
    for i, sub in enumerate(sub_llms):
        assert sub.remaining_responses == 0, (
            f"sub-agent {i} still has {sub.remaining_responses} unconsumed "
            f"responses (expected 0). Likely cause: another sub-agent ran "
            f"twice while this one was skipped."
        )

    # 2. 并行性真的发生了。 如果没有这个，序列化工具执行的回归会默默地通过。
    #
    budget = single_wall * PARALLEL_SUBAGENTS.wall_time_factor
    assert parallel_wall < budget, (
        f"parallel wall ({parallel_wall:.2f}s) exceeded budget "
        f"({budget:.2f}s = {single_wall:.2f}s × "
        f"{PARALLEL_SUBAGENTS.wall_time_factor}). Sub-agents likely serialized."
    )

    # 3. 资源预算。 与单智能体参考运行和并行运行之间拍摄的快照相比，因此尖峰
    #
    #    from the reference run isn't attributed here.
    parallel_peak_rss_mb = max(
        (s.rss_mb for s in probe.samples[pre_parallel_idx:]),
        default=pre_parallel_rss_mb,
    )
    rss_growth = (parallel_peak_rss_mb - pre_parallel_rss_mb) / max(
        pre_parallel_rss_mb, 1.0
    )
    assert rss_growth < PARALLEL_SUBAGENTS.rss_growth_factor, (
        f"RSS grew {rss_growth:.2f}× during the parallel run "
        f"({pre_parallel_rss_mb:.1f} MB → peak {parallel_peak_rss_mb:.1f} MB). "
        f"Budget: < {PARALLEL_SUBAGENTS.rss_growth_factor}×."
    )
    assert probe.fd_delta() < PARALLEL_SUBAGENTS.max_fd_growth, (
        f"FDs grew by {probe.fd_delta()} (budget < "
        f"{PARALLEL_SUBAGENTS.max_fd_growth}). Possible FD leak in sub-agent "
        f"teardown."
    )
