"""压力测试：租约争用——只有一位作家获胜。

捕获的错误类：
    - 两个竞相启动同一个对话的服务都成功了，产生了裂脑所有者和无声的事件日志损坏。
    - 租约释放发生两次或在合法所有者完成之前发生，从而导致虚假收购。

租赁如何运作 (ConversationLease)：
    每个ConversationService都有一个``owner_instance_id``。 启动 EventService 通过文件
    锁 + 每个会话租约文件声明
    租约。 如果租约由另一位业主持有且未到期，
    ``claim()`` 提高 ConversationLeaseHeldError。
"""

import asyncio
import contextlib
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from openhands.agent_server.conversation_lease import ConversationLeaseHeldError
from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.models import StartConversationRequest
from openhands.sdk import Agent
from openhands.sdk.workspace import LocalWorkspace
from tests.agent_server.stress.budgets import LEASE_CONTENTION
from tests.agent_server.stress.scripts import placeholder_llm


pytestmark = [pytest.mark.stress, pytest.mark.timeout(30)]


async def _try_start(
    service: ConversationService,
    conv_id: UUID,
    *,
    workspace_dir: str,
    usage_id: str,
) -> tuple[bool, Exception | None]:
    """尝试开始对话。 返回（成功，异常）。"""
    request = StartConversationRequest(
        conversation_id=conv_id,
        agent=Agent(llm=placeholder_llm(usage_id), tools=[]),
        workspace=LocalWorkspace(working_dir=workspace_dir),
        autotitle=False,
    )
    try:
        await service.start_conversation(request)
        return True, None
    except Exception as e:
        return False, e


async def test_concurrent_start_of_same_conversation_yields_one_winner(
    tmp_path: Path,
):
    """N 个服务尝试同时启动 * 相同的 * conversation_id。 正是如此
    一胜一负； REST 因 ConversationLeaseHeldError 失败（或类似的争用错误）。
    """
    persist = tmp_path / "persist"
    persist.mkdir()
    workspace = str(tmp_path / "ws")
    (tmp_path / "ws").mkdir()

    n = LEASE_CONTENTION.n_concurrent
    services = [ConversationService(conversations_dir=persist) for _ in range(n)]
    # 确保不同的所有者，以便我们运用跨所有者竞争路径。
    owner_ids = [uuid4().hex for _ in range(n)]
    for s, o in zip(services, owner_ids):
        s.owner_instance_id = o

    # 启动每项服务。 __aenter__扫描持久化目录； 由于没有预先存在的对话，这只是初始化。
    #
    started: list[ConversationService] = []
    try:
        for s in services:
            await s.__aenter__()
            started.append(s)
    except Exception:
        # 如果后面的服务无法进入，则将已经启动的服务拆掉。
        for s in reversed(started):
            with contextlib.suppress(Exception):
                await s.__aexit__(None, None, None)
        raise
    try:
        target = uuid4()
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *[
                        _try_start(
                            s, target, workspace_dir=workspace, usage_id=f"lc-{i}"
                        )
                        for i, s in enumerate(services)
                    ],
                    return_exceptions=False,
                ),
                timeout=LEASE_CONTENTION.settle_timeout_s,
            )
        except TimeoutError:
            pytest.fail(
                f"contention did not settle within "
                f"{LEASE_CONTENTION.settle_timeout_s}s; one of the {n} "
                f"services is wedged on lease acquisition."
            )

        winners = [(i, exc) for i, (ok, exc) in enumerate(results) if ok]
        losers = [(i, exc) for i, (ok, exc) in enumerate(results) if not ok]

        # 1. 恰好一位获胜者。 捕获“脑裂——两个服务都认为自己拥有对话”回归。
        #
        assert len(winners) == 1, (
            f"expected exactly 1 winner, got {len(winners)}: "
            f"{[i for i, _ in winners]}. Lease contention is broken."
        )
        assert len(losers) == n - 1, f"expected {n - 1} losers, got {len(losers)}"

        # 2. 每个失败者都会提出一个可识别的租约争用错误。 我们直接接受
        # ConversationLeaseHeldError，或包含它的任何子类链（某些路径包装它）。
        #
        for i, exc in losers:
            assert exc is not None
            chain: list[BaseException | None] = [exc]
            while chain[-1] is not None and chain[-1].__cause__ is not None:
                chain.append(chain[-1].__cause__)
            kinds = {type(e) for e in chain if e is not None}
            assert any(issubclass(k, ConversationLeaseHeldError) for k in kinds), (
                f"loser service {i} raised {type(exc).__name__}: {exc}. "
                f"Expected ConversationLeaseHeldError somewhere in the "
                f"cause chain."
            )

        # 3. 持久化 dir 恰好包含目标的一个对话目录。 如果失败者部分写入了状态，我们会看
        # 到两个状态，或者更糟糕的是，一个损坏的状态。
        #
        target_dirs = list(persist.glob(f"{target.hex}*"))
        assert len(target_dirs) == 1, (
            f"expected 1 conversation directory for {target.hex}, found "
            f"{len(target_dirs)}: {[d.name for d in target_dirs]}. A loser "
            f"partially wrote state to disk."
        )
    finally:
        # 拆除所有服务。 顺序并不重要——失败者没有附加event_services。 抑制每个服务的异常
        # ，这样糟糕的拆卸就不会掩盖测试的主要故障或跳过清理的 REST。
        #
        for s in services:
            with contextlib.suppress(Exception):
                await s.__aexit__(None, None, None)
