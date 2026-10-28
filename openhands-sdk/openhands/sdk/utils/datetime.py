"""日期/时间和 UUID 助手。"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from pydantic import PlainSerializer


def utc_now() -> datetime:
    """返回 UTC 中的当前时间（``datetime.utcnow`` 为已弃用）。"""
    return datetime.now(UTC)


def _uuid_to_hex(uuid_obj: UUID) -> str:
    return uuid_obj.hex


OpenHandsUUID = Annotated[UUID, PlainSerializer(_uuid_to_hex, when_used="json")]
"""UUID 序列化为 JSON 中的十六进制字符串（无连字符）的类型。"""
