"""由压力套件共享的助手。

Centralises: scripted-LLM 构造，“通过
然后服务交换 LLM" 舞蹈和一个小的轮询助手。 存在于此（不在 conftest 中），因为它很简单
 Python — 更容易从测试文件导入，无需测试夹具间接。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import httpx
import psutil
from pydantic import PrivateAttr, SecretStr

from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.models import ConversationInfo, StartConversationRequest
from openhands.sdk import LLM, Agent, Tool
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.llm.llm_response import LLMResponse
from openhands.sdk.llm.streaming import TokenCallbackType
from openhands.sdk.testing import TestLLM
from openhands.sdk.tool.tool import ToolDefinition
from openhands.sdk.workspace import LocalWorkspace


if TYPE_CHECKING:
    from openhands.sdk.llm.llm import LLMCallContext


class SlowTestLLM(TestLLM):
    """TestLLM 具有合成的每次调用延迟。

    通过 ``time.sleep`` 应用延迟，因此它会阻止 LLM 运行的工作线程线程。 这使得并行性
    变得可见：当 8 子智能体（或 16 个对话）同时执行时，每个
    对话都有自己的线程并且睡眠重叠； 如果执行序列化，则不会。
    """

    _latency_s: float = PrivateAttr(default=0.0)

    def __init__(self, *, latency_s: float = 0.0, **data: Any) -> None:
        super().__init__(**data)
        self._latency_s = latency_s

    def completion(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        add_security_risk_prediction: bool = False,
        on_token: TokenCallbackType | None = None,
        call_context: LLMCallContext | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        if self._latency_s > 0:
            time.sleep(self._latency_s)
        return super().completion(
            messages,
            tools,
            add_security_risk_prediction,
            on_token,
            call_context=call_context,
            **kwargs,
        )


def placeholder_llm(usage_id: str) -> LLM:
    """StartConversationRequest 载荷的看起来有效的 LLM。

    的智能体服务器的 ``_start_conversation`` does ``model_dump(mode='json')`` 然后重
    新验证从  JSON, w
    hich strips TestLLM私有脚本回复。 我们通过这个循环往返并替换为真实的 TestLLM via
    ``conversation.switch_llm``  *之后* 对话已创建 switch_llm uses
    ``model_copy(update={'llm': ...})`` 它保留了  TestLLM 实例及其脚本状态。
    """
    return LLM(usage_id=usage_id, model="openai/gpt-4o", api_key=SecretStr("unused"))


def text_message(text: str) -> Message:
    return Message(role="assistant", content=[TextContent(text=text)])


def descendants_of(pid: int) -> list[psutil.Process]:
    """``pid`` 的所有递归后代。 如果进程消失则为空
    或 psutil 无法读取它（Windows / 沙盒运行程序）。"""
    try:
        return psutil.Process(pid).children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return []


async def start_conversation_with_test_llm(
    conversation_service: ConversationService,
    *,
    parent_llm: TestLLM,
    workspace_dir: str,
    usage_id: str,
    tools: list[Tool] | None = None,
    tool_concurrency_limit: int = 1,
    initial_text: str | None = "stress test",
) -> ConversationInfo:
    """创建对话，安装 ``parent_llm``，然后选择队列
    初始用户消息（不自动运行）。

    返回 ``ConversationInfo``。 调用者负责显式触发运行（POST
    ``/api/conversations/<id>/run`` 或
    ``event_service.run()``).

    为什么我们*不*使用StartConversationRequest.initial_message：
        ``_start_conversation`` 调用 ``send_message(..., run_after_send=True)`` 获取
        初始消息 -
         安排一次即发即忘运行之前该助手有机会通过以下方式安装 TestLLM
        ``switch_llm``. 然后占位符 LLM 进行真正的网络调用，触发重试，显式 /run 随后与
        之对抗（409、races、flake）。 使用 r
        un=False 在 switch_llm 之后对消息进行排队可以保持运行路径的单次性和确定性。
    """
    request = StartConversationRequest(
        agent=Agent(
            llm=placeholder_llm(usage_id),
            tools=tools or [],
            tool_concurrency_limit=tool_concurrency_limit,
        ),
        workspace=LocalWorkspace(working_dir=workspace_dir),
        # initial_message 故意省略 - 参见文档字符串。
        autotitle=False,
    )
    info, _is_new = await conversation_service.start_conversation(request)
    assert isinstance(info, ConversationInfo)
    event_service = await conversation_service.get_event_service(info.id)
    assert event_service is not None, (
        f"start_conversation returned info.id={info.id} but "
        f"get_event_service returned None — ConversationService invariant "
        f"violation."
    )
    conv = event_service.get_conversation()
    conv.switch_llm(parent_llm)

    if initial_text is not None:
        await event_service.send_message(
            Message(role="user", content=[TextContent(text=initial_text)]),
            run=False,
        )
    return info


_TERMINAL_STATES: Final[frozenset[ConversationExecutionStatus]] = frozenset(
    {
        ConversationExecutionStatus.FINISHED,
        ConversationExecutionStatus.ERROR,
        ConversationExecutionStatus.STUCK,
    }
)


async def wait_for_terminal(
    client: httpx.AsyncClient,
    conversation_id: UUID,
    *,
    timeout_s: float = 30.0,
    poll_s: float = 0.05,
) -> ConversationExecutionStatus:
    """轮询对话直至其达到最终状态。

    轮询而不是订阅，因为 WebSocket 覆盖范围是由单独的套件执行的； 我们希望这个助手能
    够在没有 WS 基础设施的情况下工作。
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        # 将每个请求限制在剩余的墙上时间（下限为 0.1 秒），以便挂起的 GET 无法绕过总体轮
        # 询截止时间。
        #
        remaining = max(0.1, deadline - time.monotonic())
        resp = await client.get(
            f"/api/conversations/{conversation_id.hex}", timeout=remaining
        )
        assert resp.status_code == 200, resp.text
        st = ConversationExecutionStatus(resp.json()["execution_status"])
        if st in _TERMINAL_STATES:
            return st
        await asyncio.sleep(poll_s)
    raise TimeoutError(
        f"Conversation {conversation_id} did not reach terminal state in {timeout_s}s"
    )
