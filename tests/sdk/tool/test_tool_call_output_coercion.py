from collections.abc import Sequence

import pytest
from pydantic import Field

from openhands.sdk.tool import Observation, ToolDefinition, ToolExecutor
from openhands.sdk.tool.schema import Action


class OCAAction(Action):
    y: int = Field(description="y")


class OCAObs(Observation):
    value: int

    @property
    def to_llm_content(self):  # type: ignore[override]
        from openhands.sdk.llm import TextContent

        return [TextContent(text=str(self.value))]


# 模块级观测结果类，以避免序列化测试期间出现“不支持本地类”错误。 局部类（在函数内部定义
# ）不能是已反序列化，因为它们在反序列化时可能不存在。
#
class CoercionTestObs(Observation):
    """观测结果用于测试输出强制。"""

    value: int

    @property
    def to_llm_content(self):  # type: ignore[override]
        from openhands.sdk.llm import TextContent

        return [TextContent(text=str(self.value))]


class MockCoercionTool(ToolDefinition[OCAAction, OCAObs]):
    """用于输出强制测试的具体模拟对象工具。"""

    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["MockCoercionTool"]:
        return [cls(**params)]


def test_tool_call_with_observation_none_result_shapes():
    # 当 observation_type 为 None 时，结果被包装/强制为观测结果
    # 1) 字典 -> 观测结果
    class E1(ToolExecutor[OCAAction, dict[str, object]]):
        def __call__(self, action: OCAAction, conversation=None) -> dict[str, object]:
            return {"kind": "OCAObs", "value": 1}

    t = MockCoercionTool(
        description="d",
        action_type=OCAAction,
        observation_type=None,
        executor=E1(),
    )
    obs = t(OCAAction(y=1))
    assert isinstance(obs, Observation)

    # 2) 观测结果子类 -> 观测结果直通
    class E2(ToolExecutor[OCAAction, CoercionTestObs]):
        def __call__(self, action: OCAAction, conversation=None) -> CoercionTestObs:
            return CoercionTestObs(value=2)

    t2 = MockCoercionTool(
        description="d",
        action_type=OCAAction,
        observation_type=None,
        executor=E2(),
    )
    obs2 = t2(OCAAction(y=2))
    assert isinstance(obs2, Observation)
    assert isinstance(obs2, CoercionTestObs)

    # 3) 无效类型 -> 引发 TypeError
    class E3(ToolExecutor[OCAAction, list[int]]):
        def __call__(self, action: OCAAction, conversation=None) -> list[int]:
            return [1, 2, 3]

    t3 = MockCoercionTool(
        description="d",
        action_type=OCAAction,
        observation_type=None,
        executor=E3(),
    )
    with pytest.raises(TypeError, match="Output must be dict or BaseModel"):
        t3(OCAAction(y=3))
