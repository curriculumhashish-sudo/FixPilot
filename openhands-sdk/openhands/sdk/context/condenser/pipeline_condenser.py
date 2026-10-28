from openhands.sdk.context.condenser.base import CondenserBase
from openhands.sdk.context.view import View
from openhands.sdk.event.condenser import Condensation
from openhands.sdk.llm import LLM


class PipelineCondenser(CondenserBase):
    """按顺序应用上下文压缩器序列的上下文压缩器。

    所有上下文压缩器主要由它们的 `condense` 方法定义，该方法采用
    `View` 和一个可选的 `agent_llm` 参数，返回一个新的 `View` 或一个
    `Condensation` 事件。 这意味着我们可以通过传递 `View` 并在任何上下文压缩器返回
    `Condensation` 时提前退出来将多个上下文压缩器
    链接在一起。

    例如：

        # 使用管道上下文压缩器将多个其他上下文压缩器链接在一起
        condenser = PipelineCondenser(condensers=[
            CondenserA(...),
            CondenserB(...),
            CondenserC(...),
        ])

        result = condenser.condense(view, agent_llm=agent_llm)

        # 在没有管道上下文压缩器的情况下做同样的事情需要更多样板
        # 对于单子链
        other_result = view

        if isinstance(other_result, View):
            other_result = CondenserA(...).condense(other_result, agent_llm=agent_llm)

        if isinstance(other_result, View):
            other_result = CondenserB(...).condense(other_result, agent_llm=agent_llm)

        if isinstance(other_result, View):
            other_result = CondenserC(...).condense(other_result, agent_llm=agent_llm)

        断言结果 == other_result
    """

    condensers: list[CondenserBase]
    """按顺序申请的上下文压缩器列表。"""

    def condense(self, view: View, agent_llm: LLM | None = None) -> View | Condensation:
        result: View | Condensation = view
        for condenser in self.condensers:
            if isinstance(result, Condensation):
                break
            result = condenser.condense(result, agent_llm=agent_llm)
        return result

    async def acondense(
        self, view: View, agent_llm: LLM | None = None
    ) -> View | Condensation:
        """异步：meth:`condense` 的变体。"""
        result: View | Condensation = view
        for condenser in self.condensers:
            if isinstance(result, Condensation):
                break
            result = await condenser.acondense(result, agent_llm=agent_llm)
        return result

    def handles_condensation_requests(self) -> bool:
        return any(
            condenser.handles_condensation_requests() for condenser in self.condensers
        )
