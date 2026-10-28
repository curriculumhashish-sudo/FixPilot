from typing import Any

from pydantic import (
    BaseModel,
    Field,
    SerializationInfo,
    field_serializer,
    field_validator,
)


class Tool(BaseModel):
    """定义要为智能体初始化的工具。

    这仅在智能体-SDK 中用于服务器使用的类型模式。
    """

    name: str = Field(
        ...,
        description=(
            "Name of the tool class, e.g., 'TerminalTool'. "
            "Import it from an `openhands.tools.<module>` subpackage."
        ),
        examples=["TerminalTool", "FileEditorTool", "TaskTrackerTool"],
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the tool's .create() method,"
        " e.g., {'working_dir': '/app'}",
        examples=[{"working_dir": "/workspace"}],
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """验证该名称不为空。"""
        if not v or not v.strip():
            raise ValueError("Tool name cannot be empty")
        return v

    @field_validator("params", mode="before")
    @classmethod
    def validate_params(cls, v: dict[str, Any] | None) -> dict[str, Any]:
        """将 None 参数转换为空字典。"""
        return v if v is not None else {}

    @field_serializer("params")
    def _serialize_params(
        self, params: dict[str, Any], info: SerializationInfo
    ) -> dict[str, Any]:
        """序列化 Pydantic 响应模式为 JSON 模式。"""
        response_schema = params.get("response_schema")
        if info.mode != "json" or not (
            isinstance(response_schema, type) and issubclass(response_schema, BaseModel)
        ):
            return params
        return {
            **params,
            "response_schema": response_schema.model_json_schema(),
        }
