from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import (
    Field,
    field_validator,
    model_validator,
)

from openhands.sdk.llm.llm import LLM
from openhands.sdk.llm.llm_response import LLMResponse
from openhands.sdk.llm.message import Message
from openhands.sdk.llm.streaming import TokenCallbackType
from openhands.sdk.logger import get_logger
from openhands.sdk.tool.tool import ToolDefinition


if TYPE_CHECKING:
    from openhands.sdk.llm.llm import LLMCallContext


logger = get_logger(__name__)


class RouterLLM(LLM):
    """
    多个LLM的基类充当统一的LLM。 该类为实现模型路由提供了基础，继承自LLM，允许路由器
    与多个底层LLM模型交互，同时向消费者提供统一的LLM接口。 主要特点：
    - 通过llms_for_routing配置了多个LLMs
    - 将所有其他操作/属性委托给选定的 LLM
    - 通过select_llm()方法提供路由接口
    """

    router_name: str = Field(default="base_router", description="Name of the router")
    llms_for_routing: dict[str, LLM] = Field(
        default_factory=dict
    )  # 将 LLM 名称映射到 LLM 实例以进行路由
    active_llm: LLM | None = Field(
        default=None, description="Currently selected LLM instance"
    )

    @field_validator("llms_for_routing")
    @classmethod
    def validate_llms_not_empty(cls, v):
        if not v:
            raise ValueError(
                "llms_for_routing cannot be empty - at least one LLM must be provided"
            )
        return v

    def completion(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        add_security_risk_prediction: bool = False,
        on_token: TokenCallbackType | None = None,
        call_context: LLMCallContext | None = None,
        **kwargs,
    ) -> LLMResponse:
        """
        此方法拦截完成调用，并根据 select_llm() 中实现的路由逻辑将它们路由到适当的底
        层 LLM。

        Args:
            messages: 对话消息列表
            tools: 模型可用的可选工具列表
            add_security_risk_prediction: 将 security_risk 字段添加到工具模式
            on_token: 流式传输 token 的可选回调
            **kwargs: 传递给 LLM API 的附加参数

        Note:
            摘要字段始终添加到工具模式中，以提高智能体操作的透明度和可解释性。
        """
        # 选择合适的LLM
        selected_model = self.select_llm(messages)
        self.active_llm = self.llms_for_routing[selected_model]

        logger.info(f"RouterLLM routing to {selected_model}...")

        # 委托给选定的 LLM。
        return self.active_llm.completion(
            messages=messages,
            tools=tools,
            add_security_risk_prediction=add_security_risk_prediction,
            on_token=on_token,
            call_context=call_context,
            **kwargs,
        )

    @abstractmethod
    def select_llm(self, messages: list[Message]) -> str:
        """根据消息和事件选择要使用的 LLM。

        该方法实现了RouterLLM的核心路由逻辑。 子类应该分析所提供的消息，以确定
        llms_for_routing 中的哪个 LLM 最适合处理请求。

        Args:
            messages: 对话中可以使用的消息列表
                     通知路由决策。

        Returns:
            要使用 llms_for_routing 字典中的 LLM 的键/名称。
        """

    def __getattr__(self, name):
        """将其他属性/方法委托给活动的 LLM。"""
        fallback_llm = next(iter(self.llms_for_routing.values()))
        logger.info(f"RouterLLM: No active LLM, using first LLM for attribute '{name}'")
        return getattr(fallback_llm, name)

    def __str__(self) -> str:
        """路由器的字符串表示形式。"""
        return f"{self.__class__.__name__}(llms={list(self.llms_for_routing.keys())})"

    @model_validator(mode="before")
    @classmethod
    def set_placeholder_model(cls, data):
        """保证 `model` 在 LLM 基验证运行之前存在。"""
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # 在路由器中，我们不需要指定型号名称
        if "model" not in d or not d["model"]:
            d["model"] = d.get("router_name", "router")

        return d
