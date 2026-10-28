"""测试来自 PR 审核的跟踪数据可以是已序列化到 JSON。"""

import json
import uuid

import pytest
from lmnr.sdk.types import LaminarSpanContext


def test_span_context_requires_json_mode_for_serialization():
    """验证 JSON 序列化需要 model_dump(mode='JSON')。

    model_dump() 返回 uuid.UUID 不可序列化的对象 JSON。 model_dump(mode='JSON') 将它
    们转换为字符串。
    """
    ctx = LaminarSpanContext(
        trace_id=uuid.uuid4(),
        span_id=uuid.uuid4(),
        is_remote=False,
        span_path=["conversation"],
        span_ids_path=["span_123"],
    )

    # UUIDs 无法序列化，缺少模式 'JSON'
    with pytest.raises(TypeError, match="not JSON serializable"):
        json.dumps({"span_context": ctx.model_dump()})

    # 在模式为'JSON'时：UUIDs变为字符串，序列化工作
    result = json.dumps({"span_context": ctx.model_dump(mode="json")})
    assert isinstance(json.loads(result)["span_context"]["trace_id"], str)
