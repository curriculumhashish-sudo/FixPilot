"""LLMResponse 类型为 LLM 完成响应。

该模块提供了一个 LLMResponse 类型，该类型将 LLM 完成响应包装成 OpenHands 标准类型，从
而消除了消费者直接操作的需求
with LiteLLM types.
"""

import warnings
from typing import ClassVar

from litellm import ResponsesAPIResponse
from litellm.types.utils import ModelResponse
from pydantic import BaseModel, ConfigDict

from openhands.sdk.llm.message import Message
from openhands.sdk.llm.utils.metrics import MetricsSnapshot


# 禁止 Pydantic 序列化器的警告 LiteLLM 这些警告在 Pydantic 时发生，当 LiteLLM 的
# ModelResponse 对象的字段计数不匹配时，这是预期的行为在 LiteLLM
#
warnings.filterwarnings("ignore", message="Pydantic serializer warnings")


__all__ = ["LLMResponse"]


class LLMResponse(BaseModel):
    """LLM 完成请求的结果。

    此类型为 LLM 完成结果提供了一个干净的接口，仅暴露 OpenHands 样本类型给消费者，同
    时保留对 LiteLLM 原始响应的访问以供内部使用。

    Attributes:
        message: 完成消息转换为 OpenHands 消息类型
        metrics: 完成请求中的指标快照
        raw_response: 原始 LiteLLM 响应（ModelResponse 或
            ResponsesAPIResponse) 供内部使用
    """

    message: Message
    metrics: MetricsSnapshot
    raw_response: ModelResponse | ResponsesAPIResponse

    model_config: ClassVar[ConfigDict] = ConfigDict(arbitrary_types_allowed=True)

    @property
    def id(self) -> str:
        """从底层 LLM 响应获取响应 ID。

        此属性提供了一个干净的接口来访问响应 ID，支持完成模式 (ModelResponse) 和响应
        API 模式 (ResponsesAPIResponse)
        。

        Returns:
            来自 LLM 响应的响应 ID
        """
        return self.raw_response.id
