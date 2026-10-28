"""用于快速内容搜索的 Grep 工具实现。"""

import os
from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

from pydantic import Field

from openhands.sdk.tool import (
    Action,
    DeclaredResources,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    register_tool,
)


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState


class GrepAction(Action):
    """模式用于 grep 内容搜索操作。"""

    pattern: str = Field(description="The regex pattern to search for in file contents")
    path: str | None = Field(
        default=None,
        description=(
            "The directory (absolute path) to search in. "
            "Defaults to the current working directory."
        ),
    )
    include: str | None = Field(
        default=None,
        description=(
            "Optional file pattern to filter which files to search "
            '(e.g., "*.js", "*.{ts,tsx}")'
        ),
    )


class GrepObservation(Observation):
    """观测结果来自 grep 内容搜索操作。"""

    matches: list[str] = Field(description="List of file paths containing the pattern")
    pattern: str = Field(description="The regex pattern that was used")
    search_path: str = Field(description="The directory that was searched")
    include_pattern: str | None = Field(
        default=None, description="The file pattern filter that was used"
    )
    truncated: bool = Field(
        default=False, description="Whether results were truncated to 100 files"
    )


TOOL_DESCRIPTION = """Fast content search tool.
* Searches file contents using regular expressions
* Supports full regex syntax (eg. "log.*Error", "function\\s+\\w+", etc.)
* Filter files by pattern with the include parameter (eg. "*.js", "*.{ts,tsx}")
* Returns matching file paths sorted by modification time.
* Only the first 100 results are returned. Consider narrowing your search with stricter regex patterns or provide path parameter if you need more results.
* Use this tool when you need to find files containing specific patterns.
"""  # noqa


class GrepTool(ToolDefinition[GrepAction, GrepObservation]):
    """自动初始化 GrepExecutor 的 ToolDefinition 子类。"""

    catalog_description: ClassVar[str] = (
        "Search file contents with regular expressions."
    )

    def declared_resources(self, action: Action) -> DeclaredResources:
        """声明并行执行的资源使用情况。

        所有grep后端都是无状态的，并且可以并行运行锁无子进程：ripgrep 和系统 grep 启
        动独立进程，而 Python 回退方案只进行本地文件读取。
        """
        if not isinstance(action, GrepAction):
            raise TypeError(f"Expected GrepAction, got {type(action).__name__}")
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState",
    ) -> Sequence["GrepTool"]:
        """用 GrepExecutor 初始化 GrepTool。

        Args:
            conv_state: 要从中获取工作目录的对话状态。
                         如果提供，working_dir 将从 conv_state.workspace 中获取
        """
        # 在这里导入以避免循环导入
        from openhands.tools.grep.impl import GrepExecutor

        working_dir = conv_state.workspace.working_dir
        if not os.path.isdir(working_dir):
            raise ValueError(f"working_dir '{working_dir}' is not a valid directory")

        # 初始化执行器
        executor = GrepExecutor(working_dir=working_dir)

        # 在工具描述中添加工作目录信息
        enhanced_description = (
            f"{TOOL_DESCRIPTION}\n\n"
            f"Your current working directory is: {working_dir}\n"
            f"When searching for content, searches are performed in this directory."
        )

        # 使用执行器初始化父级ToolDefinition
        return [
            cls(
                description=enhanced_description,
                action_type=GrepAction,
                observation_type=GrepObservation,
                annotations=ToolAnnotations(
                    title="grep",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


# 导入此模块时自动注册该工具
register_tool(GrepTool.name, GrepTool)
