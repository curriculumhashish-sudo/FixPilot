"""测试 MCP 工具的安全风险预测。"""

import mcp.types

from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.definition import MCPToolAction, MCPToolObservation
from openhands.sdk.mcp.tool import MCPToolDefinition


class MockMCPClient(MCPClient):
    """用于测试的模拟对象 MCPClient，可绕过复杂的构造函数。"""

    def __init__(self):
        # 跳过父构造函数以避免需要传输层
        pass

    def is_connected(self):
        return True

    async def call_tool_mcp(  # type: ignore[override]
        self, name: str, arguments: dict
    ):
        """模拟对象返回成功结果的实现。"""
        return mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text="Mock result")],
            isError=False,
        )

    def call_async_from_sync(self, coro_func, timeout=None, **kwargs):
        """模拟对象实现同步调用。"""
        import asyncio

        async def wrapper():
            async with self:
                return await coro_func(**kwargs)

        return asyncio.run(wrapper())

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def test_mcp_tool_to_openai_with_security_risk():
    """测试 MCP 工具模式是否正确包含 security_risk 字段。

    该测试重现了 MCP 启用 security_risk 的工具中错误地将 'data' 和 'security_risk' 字
    段包括在模式中，而不是实际的工具参数
    + security_risk。
    """
    # 创建一个类似 fetch 的 MCP 工具
    mcp_tool_def = mcp.types.Tool(
        name="fetch_fetch",
        description="Fetch a URL",
        inputSchema={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to fetch"}},
            "required": ["url"],
        },
    )

    mock_client = MockMCPClient()
    tools = MCPToolDefinition.create(mcp_tool=mcp_tool_def, mcp_client=mock_client)
    tool = tools[0]

    # 生成OpenAI工具模式WITH安全风险预测
    openai_tool = tool.to_openai_tool(add_security_risk_prediction=True)

    function_params = openai_tool["function"]["parameters"]  # type: ignore[typeddict-item]
    properties = function_params["properties"]
    required = function_params.get("required", [])

    # 模式应该有 'url' 和 'security_risk' 字段不 'data' 和 'security_risk'
    #
    props_list = list(properties.keys())
    assert "url" in properties, (
        f"Expected 'url' field in properties, but got: {props_list}"
    )
    assert "security_risk" in properties, (
        f"Expected 'security_risk' field in properties, but got: {props_list}"
    )

    # 模式应该不有一个“数据”字段
    assert "data" not in properties, (
        f"Unexpected 'data' field in properties. Properties: {props_list}"
    )

    # 工具本身的参数仍然是必需的； security_risk 是可选的，当 LLM 未提供时默认为 UNKNOWN
    # 。
    #
    assert "url" in required, f"Expected 'url' in required, but got: {required}"
    assert "security_risk" not in required, (
        f"Expected 'security_risk' NOT in required, but got: {required}"
    )


def test_mcp_tool_to_responses_with_security_risk():
    """测试 MCP 响应模式是否正确包含 security_risk。"""
    mcp_tool_def = mcp.types.Tool(
        name="fetch_fetch",
        description="Fetch a URL",
        inputSchema={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to fetch"}},
            "required": ["url"],
        },
    )

    mock_client = MockMCPClient()
    tools = MCPToolDefinition.create(mcp_tool=mcp_tool_def, mcp_client=mock_client)
    tool = tools[0]

    responses_tool = tool.to_responses_tool(add_security_risk_prediction=True)

    params = responses_tool["parameters"]
    assert isinstance(params, dict)
    properties = params["properties"]
    assert isinstance(properties, dict)
    required = params.get("required", [])
    assert isinstance(required, list)

    assert "url" in properties
    assert "security_risk" in properties
    assert "data" not in properties
    assert "url" in required
    assert "security_risk" not in required


def test_mcp_tool_action_from_arguments_with_security_risk():
    """测试 action_from_arguments 在 security_risk 弹出的情况下是否正常工作。

    此测试模拟 Agent._get_action_event 中发生的情况，其中在调用 action_from_arguments
     之前从参数中弹出
    security_risk。
    """
    # 创建一个类似 fetch 的 MCP 工具
    mcp_tool_def = mcp.types.Tool(
        name="fetch_fetch",
        description="Fetch a URL",
        inputSchema={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to fetch"}},
            "required": ["url"],
        },
    )

    mock_client = MockMCPClient()
    tools = MCPToolDefinition.create(mcp_tool=mcp_tool_def, mcp_client=mock_client)
    tool = tools[0]

    # 模拟 LLM 为 security_risk 提供参数（security_risk 将在调用 action_from_arguments
    # 之前被智能体弹出）
    #
    arguments = {
        "url": "https://google.com",
        # security_risk 已被智能体弹出
    }

    # 这应该正常工作，并创建一个包含数据字段的 MCPToolAction
    action = tool.action_from_arguments(arguments)

    assert isinstance(action, MCPToolAction)
    # 注意：DiscriminatedUnionMixin 中的“kind”字段应该在 action.data 中不
    # 因为它不是 MCP 工具模式的一部分，并且在发送到 MCP 服务器时会导致验证错误
    #
    assert action.data == {"url": "https://google.com"}


def test_mcp_tool_validates_correctly_after_security_risk_pop():
    """测试 MCP 工具验证在 security_risk 弹出后是否有效。

    这是重现错误场景的完整集成测试：
    1. LLM 基于模式和 security_risk 生成参数
    2. 智能体从参数中弹出 security_risk
    3. 智能体使用剩余参数调用 tool.action_from_arguments
    4. 工具应成功验证（THIS IS WHERE THE BUG OCCURS）
    """
    # 创建一个类似 fetch 的 MCP 工具
    mcp_tool_def = mcp.types.Tool(
        name="fetch_fetch",
        description="Fetch a URL",
        inputSchema={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to fetch"}},
            "required": ["url"],
        },
    )

    mock_client = MockMCPClient()
    tools = MCPToolDefinition.create(mcp_tool=mcp_tool_def, mcp_client=mock_client)
    tool = tools[0]

    # 模拟智能体的作用：
    # 1. 解析来自 LLM 的参数
    llm_generated_arguments = {
        "url": "https://google.com",
        "security_risk": "LOW",
    }

    # 2. Pop security_risk（这就是智能体在 _get_action_event 中所做的事情）
    llm_generated_arguments.pop("security_risk")

    # 3. 从剩余参数创建操作
    # 这应该不失败，并出现有关“数据”字段的验证错误
    action = tool.action_from_arguments(llm_generated_arguments)

    # 验证操作是否正确创建
    assert isinstance(action, MCPToolAction)
    # 注意：DiscriminatedUnionMixin 中的“kind”字段应该在 action.data 中不
    # 因为它不是 MCP 工具模式的一部分，并且在发送到 MCP 服务器时会导致验证错误
    #
    assert action.data == {"url": "https://google.com"}

    # 4. 执行操作（这也应该有效）
    observation = tool(action)
    assert isinstance(observation, MCPToolObservation)
    assert not observation.is_error
