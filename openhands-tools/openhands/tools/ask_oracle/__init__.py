"""Ask-Oracle工具包。

提供只读 ``ask_oracle`` 工具：一种一次性的、无需工具的子智能体，可以咨询更强大/更有能
力的 LLM 以获得第二意见。 Oracle 模型是一个已保存的
LLM 配置文件，按照约定以名称 ``oracle`` 解析（请参阅
``ORACLE_PROFILE_NAME``).

用途：
    from openhands.tools.ask_oracle import AskOracleTool

    agent = Agent(
        llm=llm,
        tools=[Tool(name=AskOracleTool.name)],
    )

智能体的活动对话 LLM 永远不会切换。 Oracle 调用仅发送 Oracle 系统提示词加上智能体的问
题和可选上下文，而不转发对话历史记录或工具。
"""

from openhands.tools.ask_oracle.definition import (
    ORACLE_PROFILE_NAME,
    AskOracleAction,
    AskOracleObservation,
    AskOracleTool,
)
from openhands.tools.ask_oracle.impl import AskOracleExecutor


__all__ = [
    "ORACLE_PROFILE_NAME",
    "AskOracleAction",
    "AskOracleObservation",
    "AskOracleExecutor",
    "AskOracleTool",
]
