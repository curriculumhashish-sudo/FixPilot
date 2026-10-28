"""测试 SystemPromptEvent.visualize 方法。"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Self

from pydantic import Field

from openhands.sdk.event.llm_convertible import SystemPromptEvent
from openhands.sdk.llm import TextContent
from openhands.sdk.tool import Action, Observation, ToolDefinition, ToolExecutor


if TYPE_CHECKING:
    from openhands.sdk.conversation.impl.local_conversation import LocalConversation


class SimpleAction(Action):
    """简单的测试动作。"""

    pass


class SimpleObservation(Observation):
    """简单测试观测结果。"""

    pass


class SimpleExecutor(ToolExecutor):
    """简单的测试执行器。"""

    def __call__(
        self, action: SimpleAction, conversation: "LocalConversation | None" = None
    ) -> SimpleObservation:
        return SimpleObservation.from_text("test")


class SimpleTool(ToolDefinition[SimpleAction, SimpleObservation]):
    """简单的测试工具。"""

    @classmethod
    def create(cls, *args, **kwargs) -> Sequence[Self]:
        return [
            cls(
                description="Test tool",
                action_type=SimpleAction,
                observation_type=SimpleObservation,
                executor=SimpleExecutor(),
            )
        ]


def test_visualize_no_data_mutation():
    """测试可视化不会改变原始事件数据。"""
    # 创建测试工具实例
    tool = SimpleTool.create()[0]

    event = SystemPromptEvent(
        system_prompt=TextContent(text="Test system prompt"),
        tools=[tool],
    )

    # 存储初始属性
    initial_name = event.tools[0].name
    initial_description = event.tools[0].description

    # 多次调用可视化
    for _ in range(3):
        _ = event.visualize

    # 验证没有发生突变（检查关键属性）
    assert event.tools[0].name == initial_name
    assert event.tools[0].description == initial_description


class LongParametersAction(Action):
    """具有许多参数的操作来测试截断。"""

    param_0: str = Field(description="Parameter 0 with very long description")
    param_1: str = Field(description="Parameter 1 with very long description")
    param_2: str = Field(description="Parameter 2 with very long description")
    param_3: str = Field(description="Parameter 3 with very long description")
    param_4: str = Field(description="Parameter 4 with very long description")
    param_5: str = Field(description="Parameter 5 with very long description")
    param_6: str = Field(description="Parameter 6 with very long description")
    param_7: str = Field(description="Parameter 7 with very long description")
    param_8: str = Field(description="Parameter 8 with very long description")
    param_9: str = Field(description="Parameter 9 with very long description")


class LongParametersExecutor(ToolExecutor):
    """长参数操作的执行器。"""

    def __call__(
        self,
        action: LongParametersAction,
        conversation: "LocalConversation | None" = None,
    ) -> SimpleObservation:
        return SimpleObservation.from_text("test")


class LongParametersTool(ToolDefinition[LongParametersAction, SimpleObservation]):
    """具有许多参数来测试截断的工具。"""

    @classmethod
    def create(cls, *args, **kwargs) -> Sequence[Self]:
        return [
            cls(
                description="Test tool",
                action_type=LongParametersAction,
                observation_type=SimpleObservation,
                executor=LongParametersExecutor(),
            )
        ]


def test_visualize_parameter_truncation():
    """测试长参数 JSON 字符串在显示中是否被截断。"""
    # 创建具有多个参数的工具
    tool = LongParametersTool.create()[0]

    event = SystemPromptEvent(
        system_prompt=TextContent(text="Test system prompt"),
        tools=[tool],
    )

    # 获得可视化效果
    visualization = event.visualize
    visualization_text = visualization.plain

    # 查找参数行
    params_lines = [
        line for line in visualization_text.split("\n") if "Parameters:" in line
    ]
    assert len(params_lines) == 1

    params_text = params_lines[0].split("Parameters: ")[1]

    # 验证截断
    assert len(params_text) <= 200
    assert params_text.endswith("...")


def test_visualize_string_truncation_logic():
    """测试工具字段的字符串截断逻辑。"""
    # 创建具有长描述的工具
    long_description = (
        "This is a very long description that should be truncated when displayed "
        "in the visualization because it exceeds the 100 character limit that is "
        "applied to the first line of the description in the visualize method"
    )

    # 创建具有详细描述的自定义工具
    tool = SimpleTool(
        description=long_description,
        action_type=SimpleAction,
        observation_type=SimpleObservation,
        executor=SimpleExecutor(),
    )

    event = SystemPromptEvent(
        system_prompt=TextContent(text="Test system prompt"),
        tools=[tool],
    )

    # 存储原始长度
    original_name_len = len(tool.name)
    original_desc_len = len(tool.description)

    # 调用可视化
    visualization = event.visualize
    visualization_text = visualization.plain

    # 验证原始数据不变
    assert len(event.tools[0].name) == original_name_len
    assert len(event.tools[0].description) == original_desc_len

    # 验证可视化包含截断的显示
    assert "..." in visualization_text  # 显示中发生一些截断
