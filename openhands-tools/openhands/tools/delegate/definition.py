"""为 OpenHands 智能体委托操作和观测结果模型。"""

from typing import Literal

from pydantic import Field

from openhands.sdk.tool.tool import (
    Action,
    Observation,
)


CommandLiteral = Literal["spawn", "delegate"]


class DelegateAction(Action):
    """模式用于委托操作。"""

    command: CommandLiteral = Field(
        description="The commands to run. Allowed options are: `spawn`, `delegate`."
    )
    ids: list[str] | None = Field(
        default=None,
        description="Required parameter of `spawn` command. "
        "List of identifiers to initialize sub-agents with.",
    )
    agent_types: list[str] | None = Field(
        default=None,
        description=(
            "Optional parameter of `spawn` command. "
            "List of agent types for each ID (e.g., ['researcher', 'programmer']). "
            "If omitted or blank for an ID, the default general-purpose agent is used."
        ),
    )
    tasks: dict[str, str] | None = Field(
        default=None,
        description=(
            "Required parameter of `delegate` command. "
            "Dictionary mapping sub-agent identifiers to task descriptions."
        ),
    )


class DelegateObservation(Observation):
    """观测结果来自授权操作。"""

    command: CommandLiteral = Field(description="The command that was executed")
