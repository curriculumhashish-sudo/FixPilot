"""由日志记录回归子进程显式加载，从不由生产加载。

在服务边界注入合成循环异常形状； HTTP、WebSocket、日志记录配置和信号处理使用库存服务
器入口。
"""

import logging
from unittest.mock import patch

from openhands.agent_server.event_service import EventService
from openhands.sdk import Message, TextContent


async def fail_message(
    self: EventService,
    message: Message,
    run: bool = False,
    _from_goal_loop: bool = False,
):
    error = RuntimeError("injected cyclic exception")
    error.__context__ = error
    if any(
        isinstance(part, TextContent) and part.text == "handler"
        for part in message.content
    ):
        logging.getLogger(__name__).error(
            "handler probe", exc_info=(type(error), error, None)
        )
    raise error


patch.object(EventService, "send_message", fail_message).start()
