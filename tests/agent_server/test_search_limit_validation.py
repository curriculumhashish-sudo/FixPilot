"""每个分页搜索端点上的 ``limit`` 绑定都必须强制执行。

这些端点用来声明``Query(gt=0, lte=100)``。 ``lte`` 不是 FastAPI/Pydantic 约束关键字（
``le`` 是），因此绑定是静默的
dropped: 它从未达到 OpenAPI 模式并且从未被验证。 安
过大的 ``limit`` 然后在处理程序中遇到了裸露的 ``assert``，并显示为未处理的
``AssertionError`` — HTTP 500，这是什么客户端
错误。
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openhands.agent_server.bash_router import bash_router
from openhands.agent_server.conversation_router import conversation_router
from openhands.agent_server.dependencies import get_event_service
from openhands.agent_server.event_router import event_router
from openhands.agent_server.event_service import EventService
from openhands.agent_server.file_router import file_discovery_router


SEARCH_ROUTES = [
    (conversation_router, "/api/conversations/search"),
    (event_router, "/api/conversations/{conversation_id}/events/search"),
    (bash_router, "/api/bash/bash_events/search"),
    (file_discovery_router, "/api/file/search_subdirs"),
]


def _limit_schema(router, path: str) -> dict:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    parameters = app.openapi()["paths"][path]["get"]["parameters"]
    limit = next(p for p in parameters if p["name"] == "limit")
    return limit["schema"]


@pytest.mark.parametrize(
    "router, path", SEARCH_ROUTES, ids=[path for _, path in SEARCH_ROUTES]
)
def test_search_limit_bounds_are_published_in_the_schema(router, path):
    """绑定必须在模式中，否则生成的客户端无法看到它。"""
    schema = _limit_schema(router, path)

    assert schema["maximum"] == 100
    assert schema["exclusiveMinimum"] == 0
    # 拼写错误的约束会进入模式而不是提升。
    assert "lte" not in schema


@pytest.mark.parametrize("limit", [0, 101])
def test_search_events_rejects_out_of_range_limit(limit):
    """超出范围 ``limit`` 是客户端错误，而不是服务器故障。"""
    app = FastAPI()
    app.include_router(event_router, prefix="/api")
    service = AsyncMock(spec=EventService)
    service.search_events = AsyncMock(return_value={"items": [], "next_page_id": None})
    app.dependency_overrides[get_event_service] = lambda: service

    with TestClient(app) as client:
        response = client.get(
            f"/api/conversations/{uuid4()}/events/search", params={"limit": limit}
        )

    assert response.status_code == 422
    service.search_events.assert_not_called()


def test_search_events_accepts_the_maximum_limit():
    app = FastAPI()
    app.include_router(event_router, prefix="/api")
    service = AsyncMock(spec=EventService)
    service.search_events = AsyncMock(return_value={"items": [], "next_page_id": None})
    app.dependency_overrides[get_event_service] = lambda: service

    with TestClient(app) as client:
        response = client.get(
            f"/api/conversations/{uuid4()}/events/search", params={"limit": 100}
        )

    assert response.status_code == 200
    service.search_events.assert_called_once()
