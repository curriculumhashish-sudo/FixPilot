from openhands.sdk.conversation.types import ConversationID
from openhands.sdk.event.conversation_error import ConversationErrorEvent


ISSUE_URL = "https://github.com/OpenHands/software-agent-sdk/issues/new"


class WebSocketConnectionError(RuntimeError):
    """当 WebSocket 连接无法在超时内建立时引发。"""

    def __init__(
        self,
        conversation_id: ConversationID,
        timeout: float,
        message: str | None = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.timeout = timeout
        default_msg = (
            f"WebSocket subscription did not complete within {timeout} seconds "
            f"for conversation {conversation_id}. Events may be missed."
        )
        super().__init__(message or default_msg)


class ConversationRunError(RuntimeError):
    """当对话运行失败时引发。

    携带 conversation_id 和 persistence_dir 以使恢复/调试更容易，同时通过异常链接保留
    原始异常。
    """

    conversation_id: ConversationID
    persistence_dir: str | None
    original_exception: BaseException
    conversation_error: ConversationErrorEvent | None

    def __init__(
        self,
        conversation_id: ConversationID,
        original_exception: BaseException,
        persistence_dir: str | None = None,
        message: str | None = None,
        conversation_error: ConversationErrorEvent | None = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.persistence_dir = persistence_dir
        self.original_exception = original_exception
        self.conversation_error = conversation_error
        default_msg = self._build_error_message(
            conversation_id, original_exception, persistence_dir
        )
        super().__init__(message or default_msg)

    @staticmethod
    def _build_error_message(
        conversation_id: ConversationID,
        original_exception: BaseException,
        persistence_dir: str | None,
    ) -> str:
        """使用调试信息构建详细的错误消息。"""
        lines = [
            f"Conversation run failed for id={conversation_id}: {original_exception}",
        ]

        if persistence_dir:
            lines.append(f"\nConversation logs are stored at: {persistence_dir}")
            lines.append("\nTo help debug this issue, please file a bug report at:")
            lines.append(f"  {ISSUE_URL}")
            lines.append("and attach the conversation logs from the directory above.")

        return "\n".join(lines)
