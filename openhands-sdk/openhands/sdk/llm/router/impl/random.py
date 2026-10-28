import random

from openhands.sdk.llm.message import Message
from openhands.sdk.llm.router.base import RouterLLM
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


class RandomRouter(RouterLLM):
    """
    RouterLLM 的简单实现，为每个完成请求从 llms_for_routing 中随机选择一个 LLM。
    """

    router_name: str = "random_router"

    def select_llm(self, messages: list[Message]) -> str:  # noqa: ARG002
        selected_llm_name = random.choice(list(self.llms_for_routing.keys()))
        logger.info(f"Randomly selected LLM: {selected_llm_name}")
        return selected_llm_name
