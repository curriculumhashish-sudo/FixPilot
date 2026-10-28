"""对 openhands.sdk.runtime.tool 中的 Tool 类进行测试。"""

from collections.abc import Sequence
from typing import Any

import pytest
from pydantic import Field, ValidationError

from openhands.sdk.llm.message import ImageContent, TextContent
from openhands.sdk.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)


class ToolImmutabilityMockAction(Action):
    """模拟对象用于测试的动作类。"""

    command: str = Field(description="Command to execute")
    optional_field: str | None = Field(default=None, description="Optional field")
    nested: dict[str, Any] = Field(default_factory=dict, description="Nested object")
    array_field: list[int] = Field(default_factory=list, description="Array field")


class ToolImmutabilityMockObservation(Observation):
    """模拟对象观测结果测试类。"""

    result: str = Field(description="Result of the action")
    extra_field: str | None = Field(default=None, description="Extra field")

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text=self.result)]


class MockImmutableTool(
    ToolDefinition[ToolImmutabilityMockAction, ToolImmutabilityMockObservation]
):
    """用于不变性测试的具体模拟对象工具。"""

    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["MockImmutableTool"]:
        return [cls(**params)]


class TestToolImmutability:
    """测试套件用于工具不变性功能。"""

    def test_tool_is_frozen(self):
        """测试 Tool 实例是否已冻结且无法修改。"""
        tool = MockImmutableTool(
            description="Test tool",
            action_type=ToolImmutabilityMockAction,
            observation_type=ToolImmutabilityMockObservation,
        )

        # 测试我们不能修改任何字段
        # 注意：名称现在是 ClassVar，不能通过实例分配
        with pytest.raises(Exception):
            tool.description = "modified_description"

        with pytest.raises(Exception):
            tool.executor = None

    def test_tool_set_executor_returns_new_instance(self):
        """测试 set_executor 返回一个新的 Tool 实例。"""
        tool = MockImmutableTool(
            description="Test tool",
            action_type=ToolImmutabilityMockAction,
            observation_type=ToolImmutabilityMockObservation,
        )

        class NewExecutor(
            ToolExecutor[ToolImmutabilityMockAction, ToolImmutabilityMockObservation]
        ):
            def __call__(
                self, action: ToolImmutabilityMockAction, conversation=None
            ) -> ToolImmutabilityMockObservation:
                return ToolImmutabilityMockObservation(result="new_result")

        new_executor = NewExecutor()
        new_tool = tool.set_executor(new_executor)

        # 验证是否创建了新实例
        assert new_tool is not tool
        assert tool.executor is None
        assert new_tool.executor is new_executor
        assert new_tool.name == tool.name
        assert new_tool.description == tool.description

    def test_tool_model_copy_creates_modified_instance(self):
        """测试 model_copy 是否可以创建 Tool 实例的修改版本。"""
        tool = MockImmutableTool(
            description="Test tool",
            action_type=ToolImmutabilityMockAction,
            observation_type=ToolImmutabilityMockObservation,
        )

        # 创建包含修改字段的副本
        modified_tool = tool.model_copy(
            update={"name": "modified_tool", "description": "Modified description"}
        )

        # 验证是否创建了经过修改的新实例
        assert modified_tool is not tool
        assert tool.name == "mock_immutable"
        assert tool.description == "Test tool"
        assert modified_tool.name == "modified_tool"
        assert modified_tool.description == "Modified description"

    def test_tool_meta_field_immutability(self):
        """测试元字段是否正常工作并且不可变。"""
        meta_data = {"version": "1.0", "author": "test"}
        tool = MockImmutableTool(
            description="Test tool",
            action_type=ToolImmutabilityMockAction,
            observation_type=ToolImmutabilityMockObservation,
            meta=meta_data,
        )

        # 验证元字段可访问
        assert tool.meta == meta_data

        # 测试meta字段不能直接修改
        with pytest.raises(Exception):
            tool.meta = {"version": "2.0"}

        # 测试元字段是否可以通过 model_copy 修改
        new_meta = {"version": "2.0", "author": "new_author"}
        modified_tool = tool.model_copy(update={"meta": new_meta})
        assert modified_tool.meta == new_meta
        assert tool.meta == meta_data  # Original unchanged

    def test_tool_constructor_parameter_validation(self):
        """测试工具构造函数是否正确验证参数。"""
        # 测试新参数名称是否有效
        tool = MockImmutableTool(
            description="Test tool",
            action_type=ToolImmutabilityMockAction,
            observation_type=ToolImmutabilityMockObservation,
        )
        assert tool.action_type == ToolImmutabilityMockAction
        assert tool.observation_type == ToolImmutabilityMockObservation

        # 测试无效字段类型是否被拒绝
        with pytest.raises(ValidationError):
            MockImmutableTool(
                description="Test tool",
                action_type="invalid_type",  # type: ignore[arg-type] # Should be a class, not string
                observation_type=ToolImmutabilityMockObservation,
            )

    def test_tool_annotations_immutability(self):
        """测试 ToolAnnotations 作为 Tool 的一部分也是不可变的。"""
        annotations = ToolAnnotations(
            title="Test Tool",
            readOnlyHint=True,
            destructiveHint=False,
        )

        tool = MockImmutableTool(
            description="Test tool",
            action_type=ToolImmutabilityMockAction,
            observation_type=ToolImmutabilityMockObservation,
            annotations=annotations,
        )

        # 测试注释字段无法重新分配（冻结行为）
        with pytest.raises(Exception):
            tool.annotations = ToolAnnotations(title="New Annotations")

        # 测试注释是否可以通过 model_copy 修改
        new_annotations = ToolAnnotations(
            title="Modified Tool",
            readOnlyHint=False,
            destructiveHint=True,
        )
        modified_tool = tool.model_copy(update={"annotations": new_annotations})
        assert (
            modified_tool.annotations
            and modified_tool.annotations.title == "Modified Tool"
        )
        assert (
            tool.annotations and tool.annotations.title == "Test Tool"
        )  # Original unchanged
