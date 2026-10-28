"""与对话状态更新相关的事件。"""

import uuid
from typing import TYPE_CHECKING, Any

from pydantic import Field, field_validator

from openhands.sdk.event.base import Event
from openhands.sdk.event.types import SourceType


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState

FULL_STATE_KEY = "full_state"


class ConversationStateUpdateEvent(Event):
    """包含对话状态更新的事件。

    每当对话状态发生变化时，都会通过 WebSocket 发送此事件，从而允许远程客户端保持在同
    步状态，而不进行 REST API 调用。

    所有字段都是相应ConversationState字段的已序列化版本，以确保与WebSocket传输的兼容
    性。
    """

    source: SourceType = "environment"
    key: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique key for this state update event",
    )
    value: Any = Field(
        default_factory=dict,
        description="Serialized conversation state updates",
    )

    @field_validator("key")
    def validate_key(cls, key):
        if not isinstance(key, str):
            raise ValueError("Key must be a string")
        # 允许使用特殊键“full_state”进行完整状态快照
        if key == FULL_STATE_KEY:
            return key
        # 允许任何字符串键以实现灵活性（测试、未来的可扩展性）实际上，键应该匹配
        # ConversationState 字段，但我们不强制这样做
        #
        return key

    @field_validator("value")
    def validate_value(cls, value, info):
        # 防止循环导入
        from openhands.sdk.conversation.conversation_stats import ConversationStats

        # 对于 ConversationStats，使用快照序列化以避免发送超过 WebSocket 的冗长列表
        #
        if isinstance(value, ConversationStats):
            return value.model_dump(mode="json", context={"use_snapshot": True})

        key = info.data.get("key")
        if key is None:
            # 允许没有键的值以实现灵活性
            return value

        # 跳过验证获取特殊的“full_state”键
        if key == FULL_STATE_KEY:
            return value

        # 防止循环导入
        from openhands.sdk.conversation.state import ConversationState

        field_info = ConversationState.model_fields.get(key)
        if field_info is None:
            # 允许使用任意键进行测试/未来的可扩展性
            return value

        # 跳过类型验证 - 只接受任何值实际的类型转换将在状态更新时发生
        #
        return value

    @classmethod
    def from_conversation_state(
        cls, state: "ConversationState"
    ) -> "ConversationStateUpdateEvent":
        """从 ConversationState 对象创建状态更新事件。

        这将创建一个包含重要状态字段快照的事件。

        Args:
            state: ConversationState 至序列化
            conversation_id: 事件的对话 ID

        Returns:
            具有已序列化状态数据的 ConversationStateUpdateEvent
        """
        # 创建包含所有重要状态字段的快照使用 mode='JSON' 确保正确的序列化包括 SecretStr
        #
        state_snapshot = state.model_dump(mode="json", exclude_none=True)

        # 使用特殊键“full_state”表示这是完整快照
        return cls(key=FULL_STATE_KEY, value=state_snapshot)

    def __str__(self) -> str:
        return f"ConversationStateUpdate(key={self.key}, value={self.value})"
