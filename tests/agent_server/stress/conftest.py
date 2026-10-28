"""共享测试夹具用于压力/规模测试。

针对智能体-server FastAPI 应用程序运行 **in-process** 测试：
- 构造一个真正的 ConversationService 指向 tmp_path/persist。
- 使用这些套件所需的路由器构建了一个最小的 FastAPI 应用程序。
- `get_conversation_service` 依赖项被覆盖以返回我们的服务。
- `httpx.AsyncClient(transport=ASGITransport(app))` 分享测试事件循环。

我们在对话的 * 创建 * 中绕过 HTTP，因为 TestLLM 具有无法在 Pydantic JSON 往返中生存的
私有属性（`_scripted_responses`
、`_call_count`）。 测试直接使用真实的 Python 对象调用
`service.start_conversation(request)`，然后使用 API
进行其他操作。
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from openhands.agent_server import bash_router as bash_router_module
from openhands.agent_server.bash_service import BashEventService
from openhands.agent_server.config import Config
from openhands.agent_server.conversation_router import conversation_router
from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.dependencies import get_conversation_service
from openhands.agent_server.event_router import event_router
from openhands.agent_server.server_details_router import (
    mark_initialization_complete,
    server_details_router,
)
from tests.agent_server.stress.budgets import CONCURRENT_CONVERSATIONS
from tests.agent_server.stress.probe import ResourceProbe


@pytest_asyncio.fixture
async def conversation_service(tmp_path: Path) -> AsyncIterator[ConversationService]:
    """真实的 ConversationService 和持久化在 tmp_path/坚持下。

    使用服务自己的 __aenter__/__aexit__ 来设置和拆除 event_services dict 和 Webhook
    订阅者。 跨测试不会发生全局状态
    泄漏，因为每个测试的路径都是唯一的。
    """
    persist_dir = tmp_path / "persist"
    persist_dir.mkdir(parents=True, exist_ok=True)
    # 并行性基准测试运行一个参考对话，然后同时运行 n 个参考对话。 参考运行在其状态读取
    # FINISHED 后仍可暂时保留其许可，因此将容量大小调整为 n + 1 以为其留出空间； 否则，
    # 最后的并发启动会间歇性地被 ConversationRunLimitExceeded 拒绝。
    # test_run_admission.py 仍然涵盖超出容量的拒绝。
    #
    service = ConversationService(
        conversations_dir=persist_dir,
        max_concurrent_runs=CONCURRENT_CONVERSATIONS.n_conversations + 1,
    )
    async with service:
        yield service


@pytest_asyncio.fixture
async def bash_service(tmp_path: Path) -> AsyncIterator[BashEventService]:
    """每次测试 BashEventService 范围为 tmp_path/bash_events。"""
    bash_dir = tmp_path / "bash_events"
    bash_dir.mkdir(parents=True, exist_ok=True)
    service = BashEventService(bash_events_dir=bash_dir)
    async with service:
        yield service


@pytest.fixture
def app(
    conversation_service: ConversationService, bash_service: BashEventService
) -> FastAPI:
    """FastAPI 应用程序连接到测试 ConversationService 和 bash 服务。

    包括压力套件今天使用的路由器：对话 + 事件 + server_details（对于 /health) + bash
    。 这里跳过套接字； 需要WebSocket覆盖
    率的测试套件应针对pub_sub内部（白盒）进行测试，而不是通过ASGITransport进行真实的
    WS握手。

    设置 ``app.state.config`` 以便任何读取它的代码 (e.g. 中间件）发现了一些东西。
    ``mark_initialization_complete`` 被调用，因此 /ready 在响应性金丝雀中返回 200。
    """
    fastapi_app = FastAPI()
    fastapi_app.state.config = Config()
    fastapi_app.state.bash_event_service = bash_service
    fastapi_app.include_router(server_details_router)
    fastapi_app.include_router(conversation_router, prefix="/api")
    fastapi_app.include_router(event_router, prefix="/api")
    fastapi_app.include_router(bash_router_module.bash_router, prefix="/api")
    fastapi_app.dependency_overrides[get_conversation_service] = (
        lambda: conversation_service
    )
    mark_initialization_complete()
    return fastapi_app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://stress.test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def probe() -> AsyncIterator[ResourceProbe]:
    p = ResourceProbe()
    async with p:
        yield p
