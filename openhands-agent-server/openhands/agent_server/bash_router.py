"""OpenHands SDK 的 Bash 路由器。"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from openhands.agent_server.bash_service import BashEventService
from openhands.agent_server.dependencies import get_bash_event_service
from openhands.agent_server.models import (
    BashCommand,
    BashEventBase,
    BashEventPage,
    BashEventSortOrder,
    BashOutput,
    ExecuteBashRequest,
    Success,
)
from openhands.agent_server.server_details_router import update_last_execution_time


bash_router = APIRouter(prefix="/bash", tags=["Bash"])
logger = logging.getLogger(__name__)


# bash活动路线
@bash_router.get("/bash_events/search")
async def search_bash_events(
    kind__eq: Literal["BashCommand", "BashOutput"] | None = None,
    command_id__eq: UUID | None = None,
    timestamp__gte: datetime | None = None,
    timestamp__lt: datetime | None = None,
    order__gt: Annotated[
        int | None,
        Query(
            title="Filter to events with order greater than this value",
            description="Only returns BashOutput events with order > this value. "
            "Useful for polling to fetch only new events since the last poll.",
        ),
    ] = None,
    sort_order: BashEventSortOrder = BashEventSortOrder.TIMESTAMP,
    page_id: Annotated[
        str | None,
        Query(title="Optional next_page_id from the previously returned page"),
    ] = None,
    limit: Annotated[
        int,
        Query(title="The max number of results in the page", gt=0, le=100),
    ] = 100,
    bash_event_service: BashEventService = Depends(get_bash_event_service),
) -> BashEventPage:
    """搜索/列出 bash 事件"""

    return await bash_event_service.search_bash_events(
        kind__eq=kind__eq,
        command_id__eq=command_id__eq,
        timestamp__gte=timestamp__gte,
        timestamp__lt=timestamp__lt,
        order__gt=order__gt,
        sort_order=sort_order,
        page_id=page_id,
        limit=limit,
    )


@bash_router.get(
    "/bash_events/{event_id}", responses={404: {"description": "Item not found"}}
)
async def get_bash_event(
    event_id: str,
    bash_event_service: BashEventService = Depends(get_bash_event_service),
) -> BashEventBase:
    """获取给定 id 的 bash event 事件"""
    event = await bash_event_service.get_bash_event(event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return event


@bash_router.get("/bash_events/")
async def batch_get_bash_events(
    event_ids: list[str],
    bash_event_service: BashEventService = Depends(get_bash_event_service),
) -> list[BashEventBase | None]:
    """获取一批给定 id 的 bash 事件，对于任何事件都返回 null
    缺少物品。"""
    events = await bash_event_service.batch_get_bash_events(event_ids)
    return events


@bash_router.post("/start_bash_command")
async def start_bash_command(
    request: ExecuteBashRequest,
    bash_event_service: BashEventService = Depends(get_bash_event_service),
) -> BashCommand:
    """在后台执行bash命令"""
    update_last_execution_time()
    _validate_cwd(request, bash_event_service)
    command, _ = await bash_event_service.start_bash_command(request)
    return command


@bash_router.post("/execute_bash_command")
async def execute_bash_command(
    request: ExecuteBashRequest,
    bash_event_service: BashEventService = Depends(get_bash_event_service),
) -> BashOutput:
    """执行bash命令并等待结果"""
    update_last_execution_time()
    _validate_cwd(request, bash_event_service)
    command, task = await bash_event_service.start_bash_command(request)
    await task
    return await _collect_bash_output(bash_event_service, command.id)


async def _collect_bash_output(
    bash_event_service: BashEventService, command_id: UUID
) -> BashOutput:
    """将已完成命令的每个存储的输出块连接到一个结果中。

    ``MAX_CONTENT_CHAR_LENGTH`` 的输出被存储为多个``BashOutput`` 事件，只有最后的一个
    携带退出代码，所以应该读取所有页面，而不
    是返回第一个页面的最后一条事件。
    """
    outputs: list[BashOutput] = []
    page_id: str | None = None
    while True:
        page = await bash_event_service.search_bash_events(
            kind__eq="BashOutput", command_id__eq=command_id, page_id=page_id
        )
        outputs.extend(item for item in page.items if isinstance(item, BashOutput))
        page_id = page.next_page_id
        if not page_id:
            break
    if not outputs:
        return BashOutput(command_id=command_id, exit_code=-1)
    # 搜索返回时间戳顺序； 稳定排序可以使其保持相同的顺序。
    outputs.sort(key=lambda output: output.order)
    final = outputs[-1]
    stdout = "".join(output.stdout for output in outputs if output.stdout)
    stderr = "".join(output.stderr for output in outputs if output.stderr)
    return final.model_copy(
        update={
            "exit_code": -1 if final.exit_code is None else final.exit_code,
            "stdout": stdout or None,
            "stderr": stderr or None,
        }
    )


@bash_router.delete("/bash_events")
async def clear_all_bash_events(
    bash_event_service: BashEventService = Depends(get_bash_event_service),
) -> dict[str, int]:
    """从存储中清除所有 bash 事件"""
    count = await bash_event_service.clear_all_events()
    return {"cleared_count": count}


@bash_router.post(
    "/bash_commands/{command_id}/stop",
    responses={404: {"description": "Item not found"}},
)
async def stop_bash_command(
    command_id: UUID,
    bash_event_service: BashEventService = Depends(get_bash_event_service),
) -> Success:
    """通过 id 停止正在运行的 bash 命令，而不影响其他命令。

    Idempotent: 成功停止已完成的命令，而
    未知命令 ID 报告未找到，因此调用者可以将其视为已取消的停止。
    """
    update_last_execution_time()
    if await bash_event_service.stop_bash_command(command_id):
        return Success()
    if await bash_event_service.get_bash_event(command_id.hex) is not None:
        return Success()
    raise HTTPException(status.HTTP_404_NOT_FOUND)


def _validate_cwd(request: ExecuteBashRequest, service: BashEventService) -> None:
    if service.default_cwd is not None and request.cwd is not None:
        if (
            not Path(request.cwd)
            .resolve()
            .is_relative_to(Path(service.default_cwd).resolve())
        ):
            raise HTTPException(422, "cwd must be inside the conversation workspace")
