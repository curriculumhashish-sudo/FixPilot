"""对话状态锁不得在 LLM 网络呼叫中保持。

Regression: ``arun()`` 保持整个智能体的对话状态锁
步骤。 在LLM次往返中，``send_message()``和状态快照被阻塞，导致全响应时间的智能体-服务
器似乎“停止响应”而等待模型。 ``Agent.astep``
现在释放锁仅用于网络调用
``LocalConversation._released_state_lock_during_io``.
"""

import asyncio
import threading

import pytest
from pydantic import PrivateAttr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.llm import LLM
from openhands.sdk.llm.exceptions import LLMContentPolicyViolationError


class _LockProbingLLM(LLM):
    """记录 ``acompletion`` 中间观察到的对话锁状态。

    引发 * 可恢复 * 内容策略错误，因此 ``astep`` 干净地返回，而无需我们合成完整的
    ``LLMResponse``。
    """

    _convo_box: list = PrivateAttr(default_factory=list)
    _probe: dict = PrivateAttr(default_factory=dict)

    def __init__(self):
        super().__init__(model="test-model", usage_id="test-llm")

    def uses_responses_api(self) -> bool:  # 超越门控
        return False

    async def acompletion(self, *, messages, tools=None, **kwargs):  # type: ignore[override]
        convo = self._convo_box[0]
        lock = convo._state._lock
        # 1) 在网络调用期间，线程不应拥有状态锁。
        self._probe["locked_during_call"] = lock.locked()
        # 2) 运行循环标志必须反映现实（锁现在是免费的）。
        self._probe["step_flag_during_call"] = convo._step_holds_state_lock

        # 3) 不同的线程（如 send_message 运行，通过 run_in_executor）必须能够在呼叫进行
        # 时实际抓取锁。
        #
        acquired: dict = {}

        def _try_acquire():
            got = lock.acquire(blocking=True, timeout=2.0)
            acquired["ok"] = got
            if got:
                lock.release()

        t = threading.Thread(target=_try_acquire)
        t.start()
        await asyncio.to_thread(t.join)
        self._probe["worker_acquired_during_call"] = acquired.get("ok", False)

        raise LLMContentPolicyViolationError()


@pytest.mark.asyncio
async def test_astep_releases_state_lock_during_llm_call():
    llm = _LockProbingLLM()
    agent = Agent(llm=llm, tools=[])
    convo = Conversation(agent=agent)
    assert isinstance(convo, LocalConversation)
    convo._ensure_agent_ready()
    llm._convo_box.append(convo)
    convo.send_message("hello")

    # 模仿 arun() 的每步关键部分：在调用 astep 之前保持跨步的状态锁并设置标志 arun set。
    #
    convo._step_holds_state_lock = True
    with convo._state:
        assert convo._state._lock.locked()
        await agent.astep(convo, on_event=[].append)
        # 上下文管理器恢复了锁（相同的线程）和标志。
        assert convo._state._lock.owned()
        assert convo._step_holds_state_lock is True

    # 锁是在提供商往返期间举行的不...
    assert llm._probe["locked_during_call"] is False
    # ...another thread could take it mid-call...
    assert llm._probe["worker_acquired_during_call"] is True
    # ...and the run-loop flag told the truth while it was released.
    assert llm._probe["step_flag_during_call"] is False


@pytest.mark.asyncio
async def test_direct_astep_without_lock_is_unaffected():
    """直接 astep()（无运行循环，锁未保持）必须仍然有效：
    当当前线程不拥有锁时，上下文管理器是无操作。"""
    llm = _LockProbingLLM()
    agent = Agent(llm=llm, tools=[])
    convo = Conversation(agent=agent)
    assert isinstance(convo, LocalConversation)
    convo._ensure_agent_ready()
    llm._convo_box.append(convo)
    convo.send_message("hello")

    # 这里没有 `with convo._state:` — 锁在进入时不保留。
    await agent.astep(convo, on_event=[].append)

    assert llm._probe["locked_during_call"] is False
    assert llm._probe["worker_acquired_during_call"] is True
