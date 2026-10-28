from openhands.sdk.event.base import Event
from openhands.sdk.event.types import SourceType


class StreamingDeltaEvent(Event):
    """实时 WebSocket 传送的瞬态 LLM token 增量。

    不已持久化到对话事件日志：这些事件直接发布到 PubSub，绕过写入
    ConversationState.events 的回调链。 在流中重新连接的客户端将收到历史
    中的最后 MessageEvent，但 None 生成它的差异 — 差异是用户体验的增强，而不是持久对
    话记录的一部分。
    """

    source: SourceType = "agent"
    content: str | None = None
    reasoning_content: str | None = None
