"""工作区操作结果和构建类型的 Pydantic 模型。"""

from typing import Literal

from pydantic import BaseModel, Field


TargetType = Literal[
    "binary",
    "binary-minimal",
    "source",
    "source-minimal",
    "base-image-minimal",
    "base-image",
    "builder",
]
PlatformType = Literal["linux/amd64", "linux/arm64"]


class CommandResult(BaseModel):
    """执行工作区中命令的结果。"""

    command: str = Field(description="The command that was executed")
    exit_code: int = Field(description="Exit code of the command")
    stdout: str = Field(description="Standard output from the command")
    stderr: str = Field(description="Standard error from the command")
    timeout_occurred: bool = Field(
        description="Whether the command timed out during execution"
    )


class FileOperationResult(BaseModel):
    """文件上传或下载操作的结果。"""

    success: bool = Field(description="Whether the operation was successful")
    source_path: str = Field(description="Path to the source file")
    destination_path: str = Field(description="Path to the destination file")
    file_size: int | None = Field(
        default=None, description="Size of the file in bytes (if successful)"
    )
    error: str | None = Field(
        default=None, description="Error message (if operation failed)"
    )
