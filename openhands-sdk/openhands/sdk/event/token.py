from pydantic import Field

from openhands.sdk.event.base import Event
from openhands.sdk.event.types import SourceType


class TokenEvent(Event):
    """来自 VLLM 的事件代表 LLM 交互中使用的 token 个 ID。"""

    source: SourceType
    prompt_token_ids: list[int] = Field(
        ..., description="The exact prompt token IDs for this message event"
    )
    response_token_ids: list[int] = Field(
        ..., description="The exact response token IDs for this message event"
    )
