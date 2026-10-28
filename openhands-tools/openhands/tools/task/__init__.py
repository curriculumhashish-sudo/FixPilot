"""用于子智能体委派的任务工具包。

该软件包提供了一个 TaskToolSet 工具来将任务委托给子智能体。

工具：
    - task: 启动并运行（阻塞）子智能体任务。

用途：
    from openhands.tools.task import TaskToolSet

    agent = Agent(
        llm=llm,
        tools=[
            Tool(name=TerminalTool.name),
            Tool(name=TaskToolSet.name),
        ],
    )
"""

from openhands.tools.task.definition import (
    TaskAction,
    TaskObservation,
    TaskTool,
    TaskToolSet,
)
from openhands.tools.task.impl import TaskExecutor


__all__ = [
    "TaskAction",
    "TaskExecutor",
    "TaskObservation",
    "TaskTool",
    "TaskToolSet",
]
