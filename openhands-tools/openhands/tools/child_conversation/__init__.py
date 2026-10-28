"""儿童对话工具包。

提供 ``start_child_conversation`` 工具：一个服务器执行的工具，它在相同的后端启动一个
子对话，并将子对话的 id 和启动状态返回给父对话智能体。
 HTTP 启动本身由端点子启动器接管，该子启动器默认运行工具
 ``POST /api/conversations/{id}/children``的智能体服务器，可以通过
``launch_url``工具参数指向其他地方，以便托管后端运行自己的部署生命周期。

用途：
    from openhands.tools.child_conversation import StartChildConversationTool

    agent = Agent(
        llm=llm,
        tools=[Tool(name=StartChildConversationTool.name)],
    )

该工具由智能体-服务器注册； 它不是默认工具预设的一部分，因为它需要服务器来创建子工具
。
"""

from openhands.tools.child_conversation.definition import (
    StartChildConversationAction,
    StartChildConversationObservation,
    StartChildConversationTool,
)
from openhands.tools.child_conversation.impl import StartChildConversationExecutor


__all__ = [
    "StartChildConversationAction",
    "StartChildConversationExecutor",
    "StartChildConversationObservation",
    "StartChildConversationTool",
]
