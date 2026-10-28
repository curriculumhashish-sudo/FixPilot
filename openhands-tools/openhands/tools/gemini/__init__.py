"""Gemini 风格的文件编辑工具。

该模块提供 Gemini 风格的文件编辑工具作为 claude 风格 file_editor 工具的替代工具。 这
些工具旨在匹配 Gemini-CLI 使用的工具界面。

工具：
    - read_file: 通过分页支持读取文件内容
    - write_file: 全文件覆盖操作
    - edit: 查找并替换为验证
    - list_directory: 包含元数据的目录列表

用途：
    要使用 Gemini 风格的工具而不是标准 FileEditorTool，请将 FileEditorTool 替换为四个
     Gemini 工具：

    ```python
    from openhands.tools.gemini import GEMINI_FILE_TOOLS

    agent = Agent(
        llm=llm,
        tools=[
            Tool(name=TerminalTool.name),
            *GEMINI_FILE_TOOLS,  # 而不是 Tool(name=FileEditorTool.name)
        ],
    )
    ```

    或者单独：

    ```python
    from openhands.tools.gemini import (
        ReadFileTool, WriteFileTool, EditTool, ListDirectoryTool
    )

    agent = Agent(
        llm=llm,
        tools=[
            Tool(name=TerminalTool.name),
            Tool(name=ReadFileTool.name),
            Tool(name=WriteFileTool.name),
            Tool(name=EditTool.name),
            Tool(name=ListDirectoryTool.name),
        ],
    )
    ```
"""

from openhands.sdk import Tool
from openhands.tools.gemini.edit import EditAction, EditObservation, EditTool
from openhands.tools.gemini.list_directory import (
    ListDirectoryAction,
    ListDirectoryObservation,
    ListDirectoryTool,
)
from openhands.tools.gemini.read_file import (
    ReadFileAction,
    ReadFileObservation,
    ReadFileTool,
)
from openhands.tools.gemini.write_file import (
    WriteFileAction,
    WriteFileObservation,
    WriteFileTool,
)


# 方便更换 FileEditorTool 的便利清单
GEMINI_FILE_TOOLS: list[Tool] = [
    Tool(name=ReadFileTool.name),
    Tool(name=WriteFileTool.name),
    Tool(name=EditTool.name),
    Tool(name=ListDirectoryTool.name),
]

__all__ = [
    # 便利清单
    "GEMINI_FILE_TOOLS",
    # 个人工具
    "ReadFileTool",
    "ReadFileAction",
    "ReadFileObservation",
    "WriteFileTool",
    "WriteFileAction",
    "WriteFileObservation",
    "EditTool",
    "EditAction",
    "EditObservation",
    "ListDirectoryTool",
    "ListDirectoryAction",
    "ListDirectoryObservation",
]
