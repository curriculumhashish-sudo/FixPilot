import json
from datetime import datetime
from typing import Any

from litellm.types.utils import ModelResponse

from openhands.sdk.llm.exceptions import LLMResponseError
from openhands.sdk.llm.utils.metrics import Metrics


class OpenHandsJSONEncoder(json.JSONEncoder):
    """处理日期时间和其他 OH 对象的自定义 JSON 编码器"""

    def default(self, o: object) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Metrics):
            return o.get()
        if isinstance(o, ModelResponse):
            return o.model_dump()
        return super().default(o)


# 创建单个可重用编码器实例
_json_encoder = OpenHandsJSONEncoder()


def dumps(obj, **kwargs):
    """序列化 str 格式的对象"""
    if not kwargs:
        return _json_encoder.encode(obj)

    # 创建 kwargs 的副本以避免修改原始文件
    encoder_kwargs = kwargs.copy()

    # 如果指定了 cls，则使用它； 否则使用我们的自定义编码器
    if "cls" not in encoder_kwargs:
        encoder_kwargs["cls"] = OpenHandsJSONEncoder

    return json.dumps(obj, **encoder_kwargs)


def loads(json_str, **kwargs):
    """从 str 创建一个 JSON 对象"""
    try:
        return json.loads(json_str, **kwargs)
    except json.JSONDecodeError:
        raise LLMResponseError("No valid JSON object found in response.")
