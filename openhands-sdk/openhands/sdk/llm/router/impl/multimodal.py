from typing import ClassVar

from pydantic import model_validator

from openhands.sdk.llm.message import Message
from openhands.sdk.llm.router.base import RouterLLM
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


class MultimodalRouter(RouterLLM):
    """
    根据多模式内容（e.g.、图像）和 token 限制路由请求的 RouterLLM 实现。 如果任何消息
    包含多模式内容，或者超出辅助模型的 token 限制，则会路
    由到主模型。 否则，它会路由到辅助模型。

    Note: 主要模型预计将支持多模式内容，而
    辅助模型通常是具有较低上下文窗口的纯文本模型。
    """

    router_name: str = "multimodal_router"

    PRIMARY_MODEL_KEY: ClassVar[str] = "primary"
    SECONDARY_MODEL_KEY: ClassVar[str] = "secondary"

    def select_llm(self, messages: list[Message]) -> str:
        """根据多模式内容和 token 限制选择 LLM。"""
        route_to_primary = False

        # 检查消息中的多模式内容
        for message in messages:
            if message.contains_image:
                logger.info(
                    "Multimodal content detected in messages. "
                    "Routing to the primary model."
                )
                route_to_primary = True

        # 检查辅助模型的 `messages` 是否超过上下文窗口假设辅助模型与主模型相比具有较低的
        # 上下文窗口限制
        #
        secondary_llm = self.llms_for_routing.get(self.SECONDARY_MODEL_KEY)
        if secondary_llm and (
            secondary_llm.effective_max_input_tokens
            and secondary_llm.get_token_count(messages)
            > secondary_llm.effective_max_input_tokens
        ):
            logger.warning(
                f"Messages having {secondary_llm.get_token_count(messages)} tokens, exceeded secondary model's max input tokens ({secondary_llm.effective_max_input_tokens} tokens). "  # noqa: E501
                "Routing to the primary model."
            )
            route_to_primary = True

        if route_to_primary:
            logger.info("Routing to the primary model...")
            return self.PRIMARY_MODEL_KEY
        else:
            logger.info("Routing to the secondary model...")
            return self.SECONDARY_MODEL_KEY

    @model_validator(mode="after")
    def _validate_llms_for_routing(self) -> "MultimodalRouter":
        """确保所需的模型存在于 llms_for_routing 中。"""
        if self.PRIMARY_MODEL_KEY not in self.llms_for_routing:
            raise ValueError(
                f"Primary LLM key '{self.PRIMARY_MODEL_KEY}' not found"
                " in llms_for_routing."
            )
        if self.SECONDARY_MODEL_KEY not in self.llms_for_routing:
            raise ValueError(
                f"Secondary LLM key '{self.SECONDARY_MODEL_KEY}' not found"
                " in llms_for_routing."
            )
        return self
