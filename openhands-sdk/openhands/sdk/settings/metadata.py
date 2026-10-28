from __future__ import annotations

from enum import Enum

from pydantic import BaseModel
from pydantic.config import JsonDict


SETTINGS_METADATA_KEY = "openhands_settings"
SETTINGS_SECTION_METADATA_KEY = "openhands_settings_section"


class SettingProminence(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class SettingsSectionMetadata(BaseModel):
    key: str
    label: str | None = None
    variant: str | None = None


class SettingsFieldMetadata(BaseModel):
    label: str | None = None
    prominence: SettingProminence = SettingProminence.MINOR
    depends_on: tuple[str, ...] = ()
    """必须打开此字段才能显示的字段。 ``"field=value"`` 代替
    要求该字段保存该值（对于选择字段）。"""
    variant: str | None = None
    """设置后，该字段仅适用于命名的 ``AgentSettings``
    变体（``"openhands"`` 或 ``"acp"``）。 无论 ``agent_kind`` 是否处于活动状态，都会
    显示带 ``variant=None``
     的字段。
"""


def field_meta(
    prominence: SettingProminence = SettingProminence.MINOR,
    *,
    label: str | None = None,
    depends_on: tuple[str, ...] = (),
) -> JsonDict:
    """为 Pydantic ``Field`` 构建一个 ``json_schema_extra`` 字典。

    示例：:

        model: 字符串 = 字段（
            ..., json_schema_extra=field_meta(SettingProminence.CRITICAL)
        )
    """
    metadata: JsonDict = SettingsFieldMetadata(
        label=label,
        prominence=prominence,
        depends_on=depends_on,
    ).model_dump(mode="json")
    return {SETTINGS_METADATA_KEY: metadata}
