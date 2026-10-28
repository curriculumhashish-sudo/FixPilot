"""对 openhands.sdk.runtime.tool 中的 Tool 类进行测试。"""

from collections.abc import Sequence
from typing import Any

import pytest
from pydantic import Field

from openhands.sdk.llm.message import ImageContent, TextContent
from openhands.sdk.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)


class ToolMockAction(Action):
    """模拟对象用于测试的动作类。"""

    command: str = Field(description="Command to execute")
    optional_field: str | None = Field(default=None, description="Optional field")
    nested: dict[str, Any] = Field(default_factory=dict, description="Nested object")
    array_field: list[int] = Field(default_factory=list, description="Array field")


# 模块级 Action 类，以避免序列化测试期间出现“不支持本地类”错误。 局部类（在函数内部定义
# ）不能是已反序列化，因为它们在反序列化时可能不存在。
#
class ComplexSchemaAction(Action):
    """针对模式代测试的复杂字段类型的操作。"""

    simple_field: str = Field(description="Simple string field")
    optional_int: int | None = Field(default=None, description="Optional integer")
    string_list: list[str] = Field(default_factory=list, description="List of strings")


class RequiredFieldAction(Action):
    """具有用于测试的必填和可选字段的操作。"""

    required_field: str = Field(description="This field is required")
    optional_field: str | None = Field(
        default=None, description="This field is optional"
    )


class ComplexNestedAction(Action):
    """用于测试的复杂嵌套类型的操作。"""

    simple_string: str = Field(description="Simple string field")
    optional_int: int | None = Field(default=None, description="Optional integer")
    string_array: list[str] = Field(
        default_factory=list, description="Array of strings"
    )
    int_array: list[int] = Field(default_factory=list, description="Array of integers")
    nested_dict: dict[str, Any] = Field(
        default_factory=dict, description="Nested dictionary"
    )
    optional_array: list[str | None] | None = Field(
        default=None, description="Optional array"
    )


class ToolMockObservation(Observation):
    """模拟对象观测结果测试类。"""

    result: str = Field(description="Result of the action")
    extra_field: str | None = Field(default=None, description="Extra field")

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text=self.result)]


class ComplexObservation(Observation):
    """观测结果用复杂的数据进行测试。"""

    data: dict[str, Any] = Field(default_factory=dict, description="Complex data")
    count: int = Field(default=0, description="Count field")

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text=f"Data: {self.data}, Count: {self.count}")]


class RequiredFieldsObservation(Observation):
    """观测结果具有验证测试所需的字段。

    Note: 在模块级别定义以确保稳定的限定名称
    JSON 序列化/反序列化。
    """

    message: str = Field(description="Required message field")
    value: int = Field(description="Required value field")

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text=f"{self.message}: {self.value}")]


class MockTestTool(ToolDefinition[ToolMockAction, ToolMockObservation]):
    """具体的模拟对象测试工具。"""

    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["MockTestTool"]:
        return [cls(**params)]


class TestTool:
    """测试用例为工具类。"""

    def test_tool_creation_basic(self):
        """测试基本工具创建。"""
        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
        )

        assert tool.name == "mock_test"
        assert tool.description == "A test tool"
        assert tool.action_type == ToolMockAction
        assert tool.observation_type == ToolMockObservation
        assert tool.executor is None

    def test_tool_creation_with_executor(self):
        """使用执行器功能测试工具创建。"""

        class MockExecutor(ToolExecutor):
            def __call__(self, action, conversation=None) -> ToolMockObservation:
                return ToolMockObservation(result=f"Executed: {action.command}")

        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
            executor=MockExecutor(),
        )

        # 测试该工具可以用作可执行文件
        executable_tool = tool.as_executable()
        action = ToolMockAction(command="test")
        result = executable_tool(action)
        assert isinstance(result, ToolMockObservation)
        assert result.result == "Executed: test"

    def test_tool_creation_with_annotations(self):
        """使用注释测试工具创建。"""
        annotations = ToolAnnotations(
            title="Annotated Tool",
            readOnlyHint=True,
            destructiveHint=False,
        )

        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
            annotations=annotations,
        )

        assert tool.annotations is not None
        assert tool.annotations == annotations
        assert tool.annotations.title == "Annotated Tool"
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False

    def test_to_mcp_tool_basic(self):
        """测试转换为 MCP 工具格式。"""
        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
        )

        mcp_tool = tool.to_mcp_tool()

        assert mcp_tool["name"] == "mock_test"
        assert mcp_tool["description"] == "A test tool"
        assert "inputSchema" in mcp_tool
        assert mcp_tool["inputSchema"]["type"] == "object"
        assert "properties" in mcp_tool["inputSchema"]

        # 检查操作字段是否在模式中
        properties = mcp_tool["inputSchema"]["properties"]
        assert "command" in properties
        assert "optional_field" in properties
        assert "nested" in properties
        assert "array_field" in properties

    def test_to_mcp_tool_with_annotations(self):
        """带注释的测试MCP工具转换。"""
        annotations = ToolAnnotations(
            title="Custom Tool",
            readOnlyHint=True,
        )

        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
            annotations=annotations,
        )

        mcp_tool = tool.to_mcp_tool()

        # 工具应包含注释
        assert mcp_tool["name"] == "mock_test"
        assert mcp_tool["description"] == "A test tool"
        assert "annotations" in mcp_tool
        assert mcp_tool["annotations"] == annotations

    def test_call_without_executor(self):
        """没有执行器的测试调用工具会引发错误。"""
        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
        )

        action = ToolMockAction(command="test")
        with pytest.raises(
            NotImplementedError, match="Tool 'mock_test' has no executor"
        ):
            tool(action)

    def test_call_with_executor(self):
        """使用执行器测试调用工具。"""

        class MockExecutor(ToolExecutor):
            def __call__(self, action, conversation=None) -> ToolMockObservation:
                return ToolMockObservation(result=f"Processed: {action.command}")

        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
            executor=MockExecutor(),
        )

        action = ToolMockAction(command="test_command")
        result = tool(action)

        assert isinstance(result, ToolMockObservation)
        assert result.result == "Processed: test_command"

    def test_schema_generation_complex_types(self):
        """使用复杂字段类型测试模式生成。"""
        tool = MockTestTool(
            description="Tool with complex types",
            action_type=ComplexSchemaAction,
            observation_type=ToolMockObservation,
        )

        mcp_tool = tool.to_mcp_tool()
        properties = mcp_tool["inputSchema"]["properties"]
        assert "simple_field" in properties
        assert properties["simple_field"]["type"] == "string"
        assert "optional_int" in properties
        assert properties["optional_int"]["type"] == "integer"
        assert "string_list" in properties
        assert properties["string_list"]["type"] == "array"
        assert properties["string_list"]["items"]["type"] == "string"

    def test_observation_type_validation(self):
        """测试观测结果类型是否已正确验证。"""

        class MockExecutor(ToolExecutor):
            def __call__(self, action, conversation=None) -> ToolMockObservation:
                return ToolMockObservation(result="success")

        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
            executor=MockExecutor(),
        )

        action = ToolMockAction(command="test")
        result = tool(action)

        # 应该返回正确的观测结果类型
        assert isinstance(result, ToolMockObservation)
        assert result.result == "success"

    def test_observation_with_extra_fields(self):
        """使用附加字段测试观测结果。"""

        class MockExecutor(ToolExecutor):
            def __call__(self, action, conversation=None) -> ToolMockObservation:
                return ToolMockObservation(result="test", extra_field="extra_data")

        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
            executor=MockExecutor(),
        )

        action = ToolMockAction(command="test")
        result = tool(action)

        assert isinstance(result, ToolMockObservation)
        assert result.result == "test"
        assert result.extra_field == "extra_data"

    def test_action_validation_with_nested_data(self):
        """使用嵌套数据结构测试操作验证。"""
        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
        )

        # 创建包含嵌套数据的动作
        action_data = {
            "command": "test",
            "nested": {"value": "test"},
            "array_field": [1, 2, 3],
        }
        action = tool.action_type.model_validate(action_data)

        assert isinstance(action, ToolMockAction)
        assert action.nested == {"value": "test"}
        assert action.array_field == [1, 2, 3]
        assert hasattr(action, "optional_field")

    def test_schema_roundtrip_conversion(self):
        """测试模式转换是否一致。"""
        # 从一堂课开始
        original_schema = ToolMockAction.to_mcp_schema()

        # 创建工具并获取其模式
        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
        )
        tool_schema = tool.to_mcp_tool()["inputSchema"]

        # 模式应该是等价的（忽略顺序）
        assert original_schema["type"] == tool_schema["type"]
        assert set(original_schema["properties"].keys()) == set(
            tool_schema["properties"].keys()
        )

    def test_tool_with_no_observation_type(self):
        """创建None 观测结果类型的测试工具。"""
        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=None,
        )

        assert tool.observation_type is None

        # 应该仍然能够创建 MCP 工具
        mcp_tool = tool.to_mcp_tool()
        assert mcp_tool["name"] == "mock_test"

    def test_executor_function_attachment(self):
        """使用执行器测试创建工具。"""

        # 首先创建执行器
        class MockExecutor(ToolExecutor):
            def __call__(self, action, conversation=None) -> ToolMockObservation:
                return ToolMockObservation(result=f"Attached: {action.command}")

        executor = MockExecutor()

        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
            executor=executor,
        )

        # 应该作为可执行工具
        executable_tool = tool.as_executable()
        action = ToolMockAction(command="test")
        result = executable_tool(action)
        assert isinstance(result, ToolMockObservation)
        assert result.result == "Attached: test"

    def test_tool_name_validation(self):
        """测试工具名称验证。"""
        # 名称现在根据类名自动生成
        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
        )
        assert tool.name == "mock_test"

    def test_complex_executor_return_types(self):
        """测试具有复杂返回类型的执行器。"""

        class MockComplexExecutor(ToolExecutor):
            def __call__(self, action, conversation=None) -> ComplexObservation:
                return ComplexObservation(
                    data={"processed": action.command, "timestamp": 12345},
                    count=len(action.command) if hasattr(action, "command") else 0,
                )

        tool = MockTestTool(
            description="Tool with complex observation",
            action_type=ToolMockAction,
            observation_type=ComplexObservation,
            executor=MockComplexExecutor(),
        )

        action = ToolMockAction(command="test_command")
        result = tool(action)

        assert isinstance(result, ComplexObservation)
        assert result.data["processed"] == "test_command"
        assert result.count == len("test_command")

    def test_error_handling_in_executor(self):
        """测试执行器引发异常时的错误处理。"""

        class FailingExecutor(ToolExecutor):
            def __call__(self, action, conversation=None) -> ToolMockObservation:
                raise RuntimeError("Executor failed")

        tool = MockTestTool(
            description="Tool that fails",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
            executor=FailingExecutor(),
        )

        action = ToolMockAction(command="test")
        with pytest.raises(RuntimeError, match="Executor failed"):
            tool(action)

    def test_executor_with_observation_validation(self):
        """测试执行器返回值是否经过验证。"""

        class ValidExecutor(ToolExecutor):
            def __call__(self, action, conversation=None) -> RequiredFieldsObservation:
                return RequiredFieldsObservation(message="success", value=42)

        tool = MockTestTool(
            description="Tool with required fields observation",
            action_type=ToolMockAction,
            observation_type=RequiredFieldsObservation,
            executor=ValidExecutor(),
        )

        action = ToolMockAction(command="test")
        result = tool(action)
        assert isinstance(result, RequiredFieldsObservation)
        assert result.message == "success"
        assert result.value == 42

    def test_tool_equality_and_hashing(self):
        """测试工具相等性和哈希行为。"""
        tool1 = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
        )

        tool2 = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
        )

        # 具有相同参数的工具应该是相等的
        assert tool1.name == tool2.name
        assert tool1.description == tool2.description
        assert tool1.action_type == tool2.action_type

    def test_mcp_tool_schema_required_fields(self):
        """测试 MCP 工具模式是否包含必填字段。"""
        tool = MockTestTool(
            description="Tool with required fields",
            action_type=RequiredFieldAction,
            observation_type=ToolMockObservation,
        )

        mcp_tool = tool.to_mcp_tool()
        schema = mcp_tool["inputSchema"]

        # 检查必填字段是否已标记为必填
        assert "required" in schema
        assert "required_field" in schema["required"]
        assert "optional_field" not in schema["required"]

    def test_tool_with_meta_data(self):
        """使用元数据测试工具创建。"""
        meta_data = {"version": "1.0", "author": "test"}

        tool = MockTestTool(
            description="Tool with metadata",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
            meta=meta_data,
        )

        assert tool.meta == meta_data

        mcp_tool = tool.to_mcp_tool()
        assert "_meta" in mcp_tool
        assert mcp_tool["_meta"] == meta_data

    def test_to_mcp_tool_complex_nested_types(self):
        """使用复杂嵌套类型测试 MCP 工具模式生成。"""
        tool = MockTestTool(
            description="Tool with complex nested types",
            action_type=ComplexNestedAction,
            observation_type=ToolMockObservation,
        )

        mcp_tool = tool.to_mcp_tool()
        schema = mcp_tool["inputSchema"]
        props = schema["properties"]

        # 测试简单字符串
        assert props["simple_string"]["type"] == "string"
        assert "simple_string" in schema["required"]

        # 测试可选 int
        optional_int_schema = props["optional_int"]
        assert "anyOf" not in optional_int_schema
        assert optional_int_schema["type"] == "integer"
        assert "optional_int" not in schema["required"]

        # 测试字符串数组
        string_array_schema = props["string_array"]
        assert string_array_schema["type"] == "array"
        assert string_array_schema["items"]["type"] == "string"

        # 测试 int 数组
        int_array_schema = props["int_array"]
        assert int_array_schema["type"] == "array"
        assert int_array_schema["items"]["type"] == "integer"

        # 测试嵌套字典
        nested_dict_schema = props["nested_dict"]
        assert nested_dict_schema["type"] == "object"

        # 测试可选数组
        optional_array_schema = props["optional_array"]
        assert "anyOf" not in optional_array_schema
        assert optional_array_schema["type"] == "array"
        assert optional_array_schema["items"]["type"] == "string"

    def test_security_risk_only_added_for_non_readonly_tools(self):
        """测试仅当工具不是只读时才添加 security_risk。"""
        # 使用只读工具测试
        readonly_annotations = ToolAnnotations(
            title="Read-only Tool",
            readOnlyHint=True,
        )

        readonly_tool = MockTestTool(
            description="A read-only tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
            annotations=readonly_annotations,
        )

        # 使用非只读工具进行测试
        writable_annotations = ToolAnnotations(
            title="Writable Tool",
            readOnlyHint=False,
        )

        writable_tool = MockTestTool(
            description="A writable tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
            annotations=writable_annotations,
        )

        # 使用没有注释的工具进行测试（应视为可写）
        no_annotations_tool = MockTestTool(
            description="A tool with no annotations",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
            annotations=None,
        )

        # 测试只读工具 - 应添加 security_risk 不
        readonly_openai_tool = readonly_tool.to_openai_tool(
            add_security_risk_prediction=True
        )
        readonly_function = readonly_openai_tool["function"]
        assert "parameters" in readonly_function
        readonly_params = readonly_function["parameters"]
        assert "security_risk" not in readonly_params["properties"]

        # 测试可写工具 - 添加security_riskSHOULD
        writable_openai_tool = writable_tool.to_openai_tool(
            add_security_risk_prediction=True
        )
        writable_function = writable_openai_tool["function"]
        assert "parameters" in writable_function
        writable_params = writable_function["parameters"]
        assert "security_risk" in writable_params["properties"]

        # 添加无注释的测试工具 - security_risk SHOULD
        no_annotations_openai_tool = no_annotations_tool.to_openai_tool(
            add_security_risk_prediction=True
        )
        no_annotations_function = no_annotations_openai_tool["function"]
        assert "parameters" in no_annotations_function
        no_annotations_params = no_annotations_function["parameters"]
        assert "security_risk" in no_annotations_params["properties"]

        # 测试当 add_security_risk_prediction 等于 False 时，不应添加 security_risk
        readonly_no_risk = readonly_tool.to_openai_tool(
            add_security_risk_prediction=False
        )
        readonly_no_risk_function = readonly_no_risk["function"]
        assert "parameters" in readonly_no_risk_function
        readonly_no_risk_params = readonly_no_risk_function["parameters"]
        assert "security_risk" not in readonly_no_risk_params["properties"]

        writable_no_risk = writable_tool.to_openai_tool(
            add_security_risk_prediction=False
        )
        writable_no_risk_function = writable_no_risk["function"]
        assert "parameters" in writable_no_risk_function
        writable_no_risk_params = writable_no_risk_function["parameters"]
        assert "security_risk" not in writable_no_risk_params["properties"]

    def test_security_risk_is_optional_field_in_schema(self):
        """测试 _create_action_type_with_risk 是否使 security_risk 成为默认为 UNKNOWN
        的可选字段。"""  # noqa: E501
        from openhands.sdk.tool.tool import create_action_type_with_risk

        # 使用简单的动作类型进行测试
        action_type_with_risk = create_action_type_with_risk(ToolMockAction)

        # security_risk 应该出现在属性中，但不出现在必需的中
        schema = action_type_with_risk.to_mcp_schema()
        assert "security_risk" in schema["properties"]
        assert "security_risk" not in schema.get("required", [])

        # 通过to_openai_tool方法测试
        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
        )

        openai_tool = tool.to_openai_tool(add_security_risk_prediction=True)
        function_chunk = openai_tool["function"]
        assert "parameters" in function_chunk
        function_params = function_chunk["parameters"]

        assert "security_risk" in function_params["properties"]
        assert "security_risk" not in function_params.get("required", [])

        # 使用带有注释但不包含只读的工具进行测试
        writable_annotations = ToolAnnotations(
            title="Writable Tool",
            readOnlyHint=False,
        )

        writable_tool = MockTestTool(
            description="A writable tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
            annotations=writable_annotations,
        )

        writable_openai_tool = writable_tool.to_openai_tool(
            add_security_risk_prediction=True
        )
        writable_function_chunk = writable_openai_tool["function"]
        assert "parameters" in writable_function_chunk
        writable_function_params = writable_function_chunk["parameters"]

        assert "security_risk" in writable_function_params["properties"]
        assert "security_risk" not in writable_function_params.get("required", [])

    def test_security_risk_precedes_content_params_in_schema(self):
        """测试 security_risk 是否出现在模式中的内容参数之前。

        当 LLM 耗尽其输出词元预算时，截断应该剪切内容参数而不是所需的 security_risk
        字段。 参见
        https://github.com/OpenHands/software-agent-sdk/issues/1911
        """
        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
        )

        schema = tool._get_tool_schema(add_security_risk_prediction=True)
        keys = list(schema["properties"].keys())

        assert keys[0] == "security_risk"
        assert keys[1] == "summary"
        # 原始操作字段必须位于之后
        assert keys.index("command") > keys.index("security_risk")

        # 验证所有原始字段仍然存在（不包括被 to_mcp_schema 删除的“kind”等鉴别器字段）
        #
        original_schema = ToolMockAction.to_mcp_schema()
        original_keys = set(original_schema["properties"].keys())
        schema_keys = set(keys)
        assert original_keys.issubset(schema_keys)

    def test_as_executable_with_executor(self):
        """使用具有执行器的工具测试 as_executable() 方法。"""

        class MockExecutor(ToolExecutor):
            def __call__(self, action, conversation=None) -> ToolMockObservation:
                return ToolMockObservation(result=f"Executed: {action.command}")

        executor = MockExecutor()
        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
            executor=executor,
        )

        # 应该返回 ExecutableTool，没有错误
        executable_tool = tool.as_executable()
        assert executable_tool.name == "mock_test"
        assert executable_tool.executor is executor

        # 应该可以调用
        action = ToolMockAction(command="test")
        result = executable_tool(action)
        assert isinstance(result, ToolMockObservation)
        assert result.result == "Executed: test"

    def test_as_executable_without_executor(self):
        """使用没有执行器的工具测试 as_executable() 方法。"""
        tool = MockTestTool(
            description="A test tool",
            action_type=ToolMockAction,
            observation_type=ToolMockObservation,
        )

        # 应提高 NotImplementedError
        with pytest.raises(
            NotImplementedError, match="Tool 'mock_test' has no executor"
        ):
            tool.as_executable()
