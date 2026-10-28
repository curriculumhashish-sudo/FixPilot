import re
import uuid
from collections.abc import Callable
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field

from openhands.sdk.event.base import Event
from openhands.sdk.llm.streaming import TokenCallbackType


ConversationCallbackType = Callable[[Event], None]
"""事件回调函数的类型别名。"""

ConversationTokenCallbackType = TokenCallbackType
"""为流式传输 LLM 增量调用回调类型。"""

ConversationID = uuid.UUID
"""键入对话 ID 的别名。"""

TAG_KEY_PATTERN = re.compile(r"^[a-z0-9]+$")
TAG_VALUE_MAX_LENGTH = 256


def _validate_tags(v: dict[str, str] | None) -> dict[str, str]:
    if v is None:
        return {}
    for key, value in v.items():
        if not TAG_KEY_PATTERN.match(key):
            raise ValueError(
                f"Tag key '{key}' is invalid: keys must be lowercase alphanumeric only"
            )
        if len(value) > TAG_VALUE_MAX_LENGTH:
            raise ValueError(
                f"Tag value for '{key}' exceeds maximum length of "
                f"{TAG_VALUE_MAX_LENGTH} characters"
            )
    return v


ConversationTags = Annotated[dict[str, str], BeforeValidator(_validate_tags)]
"""经过验证的对话标签字典。

键必须是小写字母数字。 值是最多 256 个字符的任意字符串。
"""

type TraceMetadataValue = (
    str | bool | int | float | list[str] | list[bool] | list[int] | list[float]
)


def _validate_observability_metadata(
    v: Any,
) -> dict[str, TraceMetadataValue]:
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise ValueError("Observability metadata must be a dictionary")
    for key, value in v.items():
        if not isinstance(key, str) or not key:
            raise ValueError("Observability metadata keys must be non-empty strings")
        if isinstance(value, str | bool | int | float):
            continue
        if isinstance(value, list):
            if all(isinstance(item, str) for item in value):
                continue
            if all(isinstance(item, bool) for item in value):
                continue
            if all(
                isinstance(item, int) and not isinstance(item, bool) for item in value
            ):
                continue
            if all(isinstance(item, float) for item in value):
                continue
        raise ValueError(
            f"Observability metadata value for '{key}' must be a scalar "
            "or a homogeneous sequence of strings, booleans, integers, or floats "
            "(mixed numeric types such as [1, 1.5] are not supported by OpenTelemetry)"
        )
    return v


ConversationObservabilityMetadata = Annotated[
    dict[str, TraceMetadataValue],
    BeforeValidator(_validate_observability_metadata),
]
"""对话的 Laminar/OTel 跟踪元数据的经过验证的字典。"""


def _validate_observability_tags(v: Any) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list):
        raise ValueError("Observability tags must be a list")
    if not all(isinstance(tag, str) and tag for tag in v):
        raise ValueError("Observability tags must be non-empty strings")
    return v


ConversationObservabilityTags = Annotated[
    list[str],
    BeforeValidator(_validate_observability_tags),
]
"""对话的层流/OTel 跨度标签的验证列表。"""


OBSERVABILITY_SPAN_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._:/-]+$")
OBSERVABILITY_SPAN_NAME_MAX_LENGTH = 128


def _validate_observability_span_name(v: Any) -> str:
    if v is None:
        return "conversation"
    if not isinstance(v, str) or not v:
        raise ValueError("Observability span name must be a non-empty string")
    if len(v) > OBSERVABILITY_SPAN_NAME_MAX_LENGTH:
        raise ValueError(
            "Observability span name exceeds maximum length of "
            f"{OBSERVABILITY_SPAN_NAME_MAX_LENGTH} characters"
        )
    if not OBSERVABILITY_SPAN_NAME_PATTERN.match(v):
        raise ValueError(
            "Observability span name may only contain letters, numbers, dots, "
            "underscores, colons, slashes, and hyphens"
        )
    return v


ConversationObservabilitySpanName = Annotated[
    str,
    BeforeValidator(_validate_observability_span_name),
]
"""经过验证的 Laminar/OTel 跨度名称以实现对话可观察性。"""


class StuckDetectionThresholds(BaseModel):
    """卡住检测阈值的配置。

    Attributes:
        action_observation: 触发前的重复次数
            动作-观测结果循环检测
        action_error: 触发前的重复次数
            动作错误循环检测
        monologue: 触发前连续智能体条消息的数量
            独白检测
        alternating_pattern: 触发前的重复次数
            交替模式检测
    """

    action_observation: int = Field(
        default=4, ge=1, description="Threshold for action-observation loop detection"
    )
    action_error: int = Field(
        default=3, ge=1, description="Threshold for action-error loop detection"
    )
    monologue: int = Field(
        default=3, ge=1, description="Threshold for agent monologue detection"
    )
    alternating_pattern: int = Field(
        default=6, ge=1, description="Threshold for alternating pattern detection"
    )
