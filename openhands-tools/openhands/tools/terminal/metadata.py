"""bash 命令执行的元数据。"""

import json
import re
import traceback

from pydantic import BaseModel, Field

from openhands.sdk.logger import get_logger
from openhands.tools.terminal.constants import (
    CMD_OUTPUT_METADATA_PS1_REGEX,
    CMD_OUTPUT_PS1_BEGIN,
    CMD_OUTPUT_PS1_END,
)


logger = get_logger(__name__)


class CmdOutputMetadata(BaseModel):
    """从 PS1 捕获的其他元数据"""

    exit_code: int = Field(
        default=-1, description="The exit code of the last executed command."
    )
    pid: int = Field(
        default=-1, description="The process ID of the last executed command."
    )
    username: str | None = Field(
        default=None, description="The username of the current user."
    )
    hostname: str | None = Field(
        default=None, description="The hostname of the machine."
    )
    working_dir: str | None = Field(
        default=None, description="The current working directory."
    )
    py_interpreter_path: str | None = Field(
        default=None, description="The path to the current Python interpreter, if any."
    )
    prefix: str = Field(default="", description="Prefix to add to command output")
    suffix: str = Field(default="", description="Suffix to add to command output")

    @classmethod
    def to_ps1_prompt(cls) -> str:
        """将所需的元数据转换为 PS1 提示词。"""
        prompt = CMD_OUTPUT_PS1_BEGIN
        json_str = json.dumps(
            {
                "pid": "$!",
                "exit_code": "$?",
                "username": r"\u",
                "hostname": r"\h",
                "working_dir": r"$(pwd)",
                "py_interpreter_path": r'$(command -v python || echo "")',
            },
            indent=2,
        )
        # 确保我们在 JSON 字符串中转义双引号，以便 PS1 将它们保留为输出的一部分
        #
        prompt += json_str.replace('"', r"\"")
        prompt += CMD_OUTPUT_PS1_END + "\n"  # 确保末尾有换行符
        return prompt

    @classmethod
    def matches_ps1_metadata(cls, string: str) -> list[re.Match[str]]:
        """查找字符串中所有有效的 PS1 元数据块。"""
        matches: list[re.Match[str]] = []
        for match in CMD_OUTPUT_METADATA_PS1_REGEX.finditer(string):
            content = match.group(1).strip()
            try:
                json.loads(content)
                matches.append(match)
            except json.JSONDecodeError:
                logger.debug(
                    f"Failed to parse PS1 metadata - Skipping: [{content[:200]}"
                    f"{'...' if len(content) > 200 else ''}]" + traceback.format_exc()
                )
        return matches

    @classmethod
    def from_ps1_match(cls, match: re.Match[str]) -> "CmdOutputMetadata":
        """从 PS1 提示词中提取所需的元数据。"""
        metadata = json.loads(match.group(1))
        # 创建元数据的副本以避免修改原始数据
        processed = metadata.copy()
        # 转换数字字段
        if "pid" in metadata:
            try:
                processed["pid"] = int(float(str(metadata["pid"])))
            except (ValueError, TypeError):
                processed["pid"] = -1
        if "exit_code" in metadata:
            try:
                processed["exit_code"] = int(float(str(metadata["exit_code"])))
            except (ValueError, TypeError):
                logger.debug(
                    f"Failed to parse exit code: {metadata['exit_code']}. "
                    f"Setting to -1."
                )
                processed["exit_code"] = -1
        return cls(**processed)
