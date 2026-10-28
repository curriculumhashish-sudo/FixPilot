"""用于快速文件模式匹配的 Glob 工具实现。"""

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


class GlobAction(Action):
    """模式用于全局模式匹配操作。"""

    pattern: str = Field(
        description='The glob pattern to match files (e.g., "**/*.js", "src/**/*.ts")'
    )
    path: str | None = Field(
        default=None,
        description=(
            "The directory (absolute path) to search in. "
            "Defaults to the current working directory."
        ),
    )


class GlobObservation(Observation):
    """观测结果来自全局模式匹配操作。"""

    files: list[str] = Field(
        description="List of matching file paths sorted by modification time"
    )
    pattern: str = Field(description="The glob pattern that was used")
    search_path: str = Field(description="The directory that was searched")
    truncated: bool = Field(
        default=False, description="Whether results were truncated to 100 files"
    )


TOOL_DESCRIPTION = """Fast file pattern matching tool.
* Supports glob patterns like "**/*.js" or "src/**/*.ts"
* Use this tool when you need to find files by name patterns
* Returns matching file paths sorted by modification time
* Only the first 100 results are returned. Consider narrowing your search with stricter glob patterns or provide path parameter if you need more results.

Examples:
- Find all JavaScript files: "**/*.js"
- Find TypeScript files in src: "src/**/*.ts"
- Find Python test files: "**/test_*.py"
- Find configuration files: "**/*.{json,yaml,yml,toml}"
"""  # noqa


class GlobTool(ToolDefinition[GlobAction, GlobObservation]):
    """自动初始化 GlobExecutor 的 ToolDefinition 子类。"""

    catalog_description: ClassVar[str] = "Find files by name pattern, such as **/*.ts."

    def declared_resources(self, action: Action) -> DeclaredResources:
        """根据活动后端声明资源使用情况。

        使用 ripgrep，每个调用都会生成一个独立的子进程 — 对于无锁的并行执行来说是安全
        的。 Python 回退方案使用进程全局
        os.chdir(), so concurrent calls must be serialized via the tool-wide mutex.
        """
        if not isinstance(action, GlobAction):
            raise TypeError(f"Expected GlobAction, got {type(action).__name__}")
        # 在此导入以避免循环导入（定义↔ impl）
        from openhands.tools.glob.impl import GlobExecutor

        if isinstance(self.executor, GlobExecutor) and self.executor.is_parallel_safe():
            return DeclaredResources(keys=(), declared=True)
        return DeclaredResources(keys=(), declared=False)

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState",
    ) -> Sequence["GlobTool"]:
        """用 GlobExecutor 初始化 GlobTool。

        Args:
            conv_state: 要从中获取工作目录的对话状态。
                         如果提供，working_dir 将从 conv_state.workspace 中获取
        """
        # 在这里导入以避免循环导入
        from openhands.tools.glob.impl import GlobExecutor

        working_dir = conv_state.workspace.working_dir
        if not os.path.isdir(working_dir):
            raise ValueError(f"working_dir '{working_dir}' is not a valid directory")

        # 初始化执行器
        executor = GlobExecutor(working_dir=working_dir)

        # 在工具描述中添加工作目录信息
        enhanced_description = (
            f"{TOOL_DESCRIPTION}\n\n"
            f"Your current working directory is: {working_dir}\n"
            f"When searching for files, patterns are relative to this directory."
        )

        # 使用执行器初始化父级ToolDefinition
        return [
            cls(
                description=enhanced_description,
                action_type=GlobAction,
                observation_type=GlobObservation,
                annotations=ToolAnnotations(
                    title="glob",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


# 导入此模块时自动注册该工具
register_tool(GlobTool.name, GlobTool)
