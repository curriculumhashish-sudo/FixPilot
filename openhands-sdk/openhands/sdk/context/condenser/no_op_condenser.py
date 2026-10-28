from openhands.sdk.context.condenser.base import CondenserBase
from openhands.sdk.context.view import View
from openhands.sdk.event.condenser import Condensation
from openhands.sdk.llm import LLM


class NoOpCondenser(CondenserBase):
    """简单上下文压缩器返回未操作的视图。

    主要用于测试目的。
    """

    def condense(self, view: View, agent_llm: LLM | None = None) -> View | Condensation:  # noqa: ARG002
        return view
