"""
OpenHands SDK 的本地事件路由器。
"""

import logging
from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from starlette.responses import JSONResponse

from openhands.agent_server.dependencies import get_event_service
from openhands.agent_server.event_service import EventService
from openhands.agent_server.models import (
    ConfirmationResponseRequest,
    EventSortOrder,
    SendMessageRequest,
    Success,
)
from openhands.sdk import Message
from openhands.sdk.event import Event


event_read_router = APIRouter(
    prefix="/conversations/{conversation_id}/events", tags=["Events"]
)
event_write_router = APIRouter(
    prefix="/conversations/{conversation_id}/events", tags=["Events"]
)
logger = logging.getLogger(__name__)


# 读取方法


def normalize_datetime_to_server_timezone(dt: datetime) -> datetime:
    """
    将日期时间标准化为服务器时区，以便与事件进行一致的比较。

    事件时间戳存储为服务器本地时间中的原始日期时间。 此函数确保过滤器日期时间在服务器
    本地时间中也是简单的，因此可以正确比较它们。

    如果日期时间有时区信息，请转换为服务器本机时区并删除 tzinfo 以使其变得简单。 如果
    它很天真（没有时区），则假设它已经在服务器时区中。

    Args:
        dt: 输入日期时间（可能是时区感知的或天真的）

    Returns:
        服务器本地时间中的原始日期时间
    """
    if dt.tzinfo is not None:
        # 时区感知：转换为服务器本机时区，然后进行天真
        return dt.astimezone(None).replace(tzinfo=None)
    else:
        # 天真的日期时间：假设它已经在服务器时区中
        return dt


@event_read_router.get(
    "/search", responses={404: {"description": "Conversation not found"}}
)
async def search_conversation_events(
    page_id: Annotated[
        str | None,
        Query(title="Optional next_page_id from the previously returned page"),
    ] = None,
    limit: Annotated[
        int,
        Query(title="The max number of results in the page", gt=0, le=100),
    ] = 100,
    kind: Annotated[
        str | None,
        Query(
            title="Optional filter by event kind/type (e.g., ActionEvent, MessageEvent)"
        ),
    ] = None,
    source: Annotated[
        str | None,
        Query(title="Optional filter by event source (e.g., agent, user, environment)"),
    ] = None,
    body: Annotated[
        str | None,
        Query(title="Optional filter by message content (case-insensitive)"),
    ] = None,
    sort_order: Annotated[
        EventSortOrder,
        Query(title="Sort order for events"),
    ] = EventSortOrder.TIMESTAMP,
    timestamp__gte: Annotated[
        datetime | None,
        Query(title="Filter: event timestamp >= this datetime"),
    ] = None,
    timestamp__lt: Annotated[
        datetime | None,
        Query(title="Filter: event timestamp < this datetime"),
    ] = None,
    event_service: EventService = Depends(get_event_service),
) -> JSONResponse:
    """搜索/列出当地活动"""

    # 将时区感知的日期时间标准化为服务器时区
    normalized_gte = (
        normalize_datetime_to_server_timezone(timestamp__gte)
        if timestamp__gte
        else None
    )
    normalized_lt = (
        normalize_datetime_to_server_timezone(timestamp__lt) if timestamp__lt else None
    )

    page = await event_service.search_events(
        page_id, limit, kind, source, body, sort_order, normalized_gte, normalized_lt
    )
    if isinstance(page, dict):
        items = cast(list[Any], page.get("items", []))
        next_page_id = cast(str | None, page.get("next_page_id"))
    else:
        items = page.items
        next_page_id = page.next_page_id
    return JSONResponse(
        {
            "items": [
                dict(event)
                if isinstance(event, dict)
                else event.model_dump(mode="json", exclude_none=True)
                for event in items
            ],
            "next_page_id": next_page_id,
        }
    )


@event_read_router.get(
    "/count", responses={404: {"description": "Conversation not found"}}
)
async def count_conversation_events(
    kind: Annotated[
        str | None,
        Query(
            title="Optional filter by event kind/type (e.g., ActionEvent, MessageEvent)"
        ),
    ] = None,
    source: Annotated[
        str | None,
        Query(title="Optional filter by event source (e.g., agent, user, environment)"),
    ] = None,
    body: Annotated[
        str | None,
        Query(title="Optional filter by message content (case-insensitive)"),
    ] = None,
    timestamp__gte: Annotated[
        datetime | None,
        Query(title="Filter: event timestamp >= this datetime"),
    ] = None,
    timestamp__lt: Annotated[
        datetime | None,
        Query(title="Filter: event timestamp < this datetime"),
    ] = None,
    event_service: EventService = Depends(get_event_service),
) -> int:
    """计算与给定过滤器匹配的本地事件数"""
    # 将时区感知的日期时间标准化为服务器时区
    normalized_gte = (
        normalize_datetime_to_server_timezone(timestamp__gte)
        if timestamp__gte
        else None
    )
    normalized_lt = (
        normalize_datetime_to_server_timezone(timestamp__lt) if timestamp__lt else None
    )

    count = await event_service.count_events(
        kind, source, body, normalized_gte, normalized_lt
    )

    return count


@event_read_router.get(
    "/{event_id}", responses={404: {"description": "Item not found"}}
)
async def get_conversation_event(
    event_id: str,
    event_service: EventService = Depends(get_event_service),
) -> Event:
    """获取给定 id 的本地事件"""
    event = await event_service.get_event(event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return event


@event_read_router.get("")
async def batch_get_conversation_events(
    event_ids: list[str],
    event_service: EventService = Depends(get_event_service),
) -> list[Event | None]:
    """根据给定的 id 获取一批本地事件，对于任何事件都返回 null
    缺少物品。"""
    events = await event_service.batch_get_events(event_ids)
    return events


@event_write_router.post(
    "",
    responses={429: {"description": "Message saved but server run capacity is full"}},
)
async def send_message(
    request: SendMessageRequest,
    event_service: EventService = Depends(get_event_service),
) -> Success:
    """向对话发送消息。

    如果开始运行返回 429，则消息已保存。 重试对话的 /run 端点，而不是重新发送消息。
    """
    message = Message(role=request.role, content=request.content)
    await event_service.send_message(message, request.run)
    return Success()


@event_write_router.post(
    "/respond_to_confirmation",
    responses={
        404: {"description": "Item not found"},
        429: {"description": "Server conversation run capacity is full"},
    },
)
async def respond_to_confirmation(
    request: ConfirmationResponseRequest,
    event_service: EventService = Depends(get_event_service),
) -> Success:
    """在确认模式下接受或拒绝待处理的操作。"""
    await event_service.respond_to_confirmation(request)
    return Success()


event_router = APIRouter()
event_router.include_router(event_read_router)
event_router.include_router(event_write_router)
