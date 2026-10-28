"""使用新的简化实现来测试 MCP 工具功能。"""

from typing import Any
from unittest.mock import MagicMock, Mock

import mcp.types

from openhands.sdk.llm import ImageContent, TextContent
from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.definition import MCPToolObservation
from openhands.sdk.mcp.tool import MCPToolDefinition, MCPToolExecutor
from openhands.sdk.tool import ToolAnnotations
from openhands.sdk.utils.async_executor import AsyncExecutor


class MockMCPClient(MCPClient):
    """用于测试的模拟对象 MCPClient，可绕过复杂的构造函数。"""

    def __init__(self):
        # 仅初始化同步执行所需的字段（无传输层）
        self._executor = AsyncExecutor()
        self._closed = False
        self._tools = []


class TestMCPToolObservation:
    """测试 MCPToolObservation 功能。"""

    def test_from_call_tool_result_success(self):
        """测试从成功的 MCP 结果创建观测结果。"""
        # 创建模拟对象 MCP 个结果
        result = MagicMock(spec=mcp.types.CallToolResult)
        result.content = [
            mcp.types.TextContent(type="text", text="Operation completed successfully")
        ]
        result.isError = False

        observation = MCPToolObservation.from_call_tool_result(
            tool_name="test_tool", result=result
        )

        assert observation.tool_name == "test_tool"
        assert observation.content is not None
        assert len(observation.content) == 2
        assert isinstance(observation.content[0], TextContent)
        assert observation.content[0].text == "[Tool 'test_tool' executed.]"
        assert isinstance(observation.content[1], TextContent)
        assert observation.content[1].text == "Operation completed successfully"
        assert observation.is_error is False

    def test_from_call_tool_result_error(self):
        """测试从错误 MCP 结果创建观测结果。"""
        # 创建模拟对象 MCP 个结果
        result = MagicMock(spec=mcp.types.CallToolResult)
        result.content = [mcp.types.TextContent(type="text", text="Operation failed")]
        result.isError = True

        observation = MCPToolObservation.from_call_tool_result(
            tool_name="test_tool", result=result
        )

        assert observation.tool_name == "test_tool"
        assert observation.is_error is True
        assert len(observation.content) == 2
        assert isinstance(observation.content[0], TextContent)
        assert observation.content[0].text == "[Tool 'test_tool' executed.]"
        assert isinstance(observation.content[1], TextContent)
        assert observation.content[1].text == "Operation failed"

    def test_from_call_tool_result_with_image(self):
        """测试使用图像内容从 MCP 结果创建观测结果。"""
        # 使用图像创建模拟对象 MCP 结果
        result = MagicMock(spec=mcp.types.CallToolResult)
        result.content = [
            mcp.types.TextContent(type="text", text="Here's the image:"),
            mcp.types.ImageContent(
                type="image", data="base64data", mimeType="image/png"
            ),
        ]
        result.isError = False

        observation = MCPToolObservation.from_call_tool_result(
            tool_name="test_tool", result=result
        )

        assert observation.tool_name == "test_tool"
        assert observation.content is not None
        assert len(observation.content) == 3
        # 第一项是标题
        assert isinstance(observation.content[0], TextContent)
        assert observation.content[0].text == "[Tool 'test_tool' executed.]"
        # 第二项是文本
        assert isinstance(observation.content[1], TextContent)
        assert observation.content[1].text == "Here's the image:"
        # 第三项是图像
        assert isinstance(observation.content[2], ImageContent)
        assert hasattr(observation.content[2], "image_urls")
        assert observation.is_error is False

    def test_to_llm_content_success(self):
        """测试智能体观测结果格式化是否成功。"""
        observation = MCPToolObservation.from_text(
            text="[Tool 'test_tool' executed.]\nSuccess result",
            tool_name="test_tool",
        )

        agent_obs = observation.to_llm_content
        assert len(agent_obs) == 1
        assert isinstance(agent_obs[0], TextContent)
        assert "[Tool 'test_tool' executed.]" in agent_obs[0].text
        assert "Success result" in agent_obs[0].text
        assert MCPToolObservation.ERROR_MESSAGE_HEADER not in agent_obs[0].text

    def test_to_llm_content_error(self):
        """测试智能体观测结果格式是否有错误。"""
        observation = MCPToolObservation.from_text(
            text=(
                "[Tool 'test_tool' executed.]\n"
                "[An error occurred during execution.]\n"
                "Error occurred"
            ),
            tool_name="test_tool",
            is_error=True,
        )

        agent_obs = observation.to_llm_content
        assert len(agent_obs) == 2
        assert isinstance(agent_obs[0], TextContent)
        assert agent_obs[0].text == MCPToolObservation.ERROR_MESSAGE_HEADER
        assert isinstance(agent_obs[1], TextContent)
        assert "[Tool 'test_tool' executed.]" in agent_obs[1].text
        assert "[An error occurred during execution.]" in agent_obs[1].text
        assert "Error occurred" in agent_obs[1].text


class TestMCPToolExecutor:
    """测试 MCPToolExecutor 功能。"""

    def setup_method(self):
        """设置测试测试夹具。"""
        self.mock_client: Mock = MagicMock()
        self.executor: Any = MCPToolExecutor(
            tool_name="test_tool", client=self.mock_client
        )

    def test_call_tool_success(self):
        """测试成功的工具执行。"""
        # 模拟对象成功 MCP 通话
        mock_result = MagicMock(spec=mcp.types.CallToolResult)
        mock_result.content = [
            mcp.types.TextContent(type="text", text="Success result")
        ]
        mock_result.isError = False

        # 模拟对象行动
        mock_action = MagicMock()
        mock_action.model_dump.return_value = {"param": "value"}

        # 模拟对象call_async_from_sync返回预期的观测结果
        def mock_call_async_from_sync(coro_func, **kwargs):
            return MCPToolObservation.from_call_tool_result(
                tool_name="test_tool", result=mock_result
            )

        self.mock_client.call_async_from_sync = mock_call_async_from_sync

        observation = self.executor(mock_action)

        assert isinstance(observation, MCPToolObservation)
        assert observation.tool_name == "test_tool"
        assert observation.is_error is False

    def test_call_tool_error(self):
        """测试工具执行时出错。"""
        # 模拟对象错误 MCP 调用
        mock_result = MagicMock(spec=mcp.types.CallToolResult)
        mock_result.content = [
            mcp.types.TextContent(type="text", text="Error occurred")
        ]
        mock_result.isError = True

        # 模拟对象行动
        mock_action = MagicMock()
        mock_action.model_dump.return_value = {"param": "value"}

        # 模拟对象call_async_from_sync返回预期的观测结果
        def mock_call_async_from_sync(coro_func, **kwargs):
            return MCPToolObservation.from_call_tool_result(
                tool_name="test_tool", result=mock_result
            )

        self.mock_client.call_async_from_sync = mock_call_async_from_sync

        observation = self.executor(mock_action)

        assert isinstance(observation, MCPToolObservation)
        assert observation.tool_name == "test_tool"
        assert observation.is_error is True

    def test_call_tool_exception(self):
        """测试工具执行有异常。"""
        # 模拟对象行动
        mock_action = MagicMock()
        mock_action.model_dump.return_value = {"param": "value"}

        # 模拟对象 call_async_from_sync 返回错误观测结果
        def mock_call_async_from_sync(coro_func, **kwargs):
            return MCPToolObservation.from_text(
                text="Error calling MCP tool test_tool: Connection failed",
                tool_name="test_tool",
                is_error=True,
            )

        self.mock_client.call_async_from_sync = mock_call_async_from_sync

        observation = self.executor(mock_action)

        assert isinstance(observation, MCPToolObservation)
        assert observation.tool_name == "test_tool"
        assert observation.is_error is True
        assert observation.is_error is True
        assert "Connection failed" in observation.text

    def test_call_tool_timeout(self):
        """测试工具执行时出现超时错误，返回观测结果。"""
        # 模拟对象行动
        mock_action = MagicMock()
        mock_action.model_dump.return_value = {"param": "value"}

        # 模拟对象 call_async_from_sync 提高 TimeoutError
        def mock_call_async_from_sync(coro_func, **kwargs):
            raise TimeoutError("Operation timed out")

        self.mock_client.call_async_from_sync = mock_call_async_from_sync

        observation = self.executor(mock_action)

        assert isinstance(observation, MCPToolObservation)
        assert observation.tool_name == "test_tool"
        assert observation.is_error is True
        assert "timed out" in observation.text
        assert f"{self.executor.timeout} seconds" in observation.text

    def test_close_calls_client_sync_close(self):
        """close() 必须调用 MCPClient.sync_close() 来拆除
        标准输入输出子进程。 如果没有这个，MCP 客户端将在会话删除后幸存下来并在长期运
        行的服务器上累积。
        """
        self.executor.close()
        self.mock_client.sync_close.assert_called_once()

    def test_call_tool_reconnects_when_session_lost(self):
        """当is_connected()返回False但客户端未关闭时，
        call_tool 应在失败之前尝试重新连接。"""
        mock_result = MagicMock(spec=mcp.types.CallToolResult)
        mock_result.content = [
            mcp.types.TextContent(type="text", text="Success after reconnect")
        ]
        mock_result.isError = False

        mock_action = MagicMock()
        mock_action.model_dump.return_value = {"param": "value"}
        mock_action.to_mcp_arguments.return_value = {"param": "value"}

        # 使用 MockMCPClient （真实的 AsyncExecutor），因此 call_tool 实际上运行
        client = MockMCPClient()
        connect_calls: list[int] = []

        async def mock_connect():
            connect_calls.append(1)

        async def mock_is_connected():
            return False if not connect_calls else True

        async def mock_call_tool_mcp(**kwargs):
            return mock_result

        # 修补 fastmcp.Client.is_connected() 和 connect() 使用的方法
        client.is_connected = lambda: len(connect_calls) > 0  # type: ignore[method-assign]
        client._closed = False
        client.connect = mock_connect  # type: ignore[method-assign]
        client.call_tool_mcp = mock_call_tool_mcp  # type: ignore[method-assign]

        executor = MCPToolExecutor(tool_name="test_tool", client=client)
        observation = executor(mock_action)

        assert isinstance(observation, MCPToolObservation)
        assert observation.tool_name == "test_tool"
        assert observation.is_error is False
        assert len(connect_calls) == 1
        client.sync_close()

    def test_call_tool_fails_when_client_closed(self):
        """当客户端关闭（_close=True）时，call_tool应该
        不尝试重新连接，并且应该立即失败。"""
        mock_action = MagicMock()
        mock_action.model_dump.return_value = {"param": "value"}
        mock_action.to_mcp_arguments.return_value = {"param": "value"}

        client = MockMCPClient()
        client.is_connected = lambda: False  # type: ignore[method-assign]
        client._closed = True

        async def mock_connect():
            raise AssertionError("connect() should not be called on a closed client")

        client.connect = mock_connect  # type: ignore[method-assign]

        async def mock_call_tool_mcp(**kwargs):
            raise AssertionError(
                "call_tool_mcp should not be called when client is closed"
            )

        client.call_tool_mcp = mock_call_tool_mcp  # type: ignore[method-assign]

        executor = MCPToolExecutor(tool_name="test_tool", client=client)
        observation = executor(mock_action)

        assert isinstance(observation, MCPToolObservation)
        assert observation.is_error is True
        assert "has been closed" in observation.text
        client.sync_close()

    def test_call_tool_fails_when_reconnect_fails(self):
        """当重新连接尝试失败时，call_tool 应返回错误
        观测结果带有重新连接失败消息。"""
        mock_action = MagicMock()
        mock_action.model_dump.return_value = {"param": "value"}
        mock_action.to_mcp_arguments.return_value = {"param": "value"}

        client = MockMCPClient()
        client.is_connected = lambda: False  # type: ignore[method-assign]
        client._closed = False

        async def mock_connect():
            raise RuntimeError("Server unreachable")

        client.connect = mock_connect  # type: ignore[method-assign]

        async def mock_call_tool_mcp(**kwargs):
            raise AssertionError(
                "call_tool_mcp should not be called when reconnect fails"
            )

        client.call_tool_mcp = mock_call_tool_mcp  # type: ignore[method-assign]

        executor = MCPToolExecutor(tool_name="test_tool", client=client)
        observation = executor(mock_action)

        assert isinstance(observation, MCPToolObservation)
        assert observation.is_error is True
        assert "Reconnection attempt failed" in observation.text
        assert "Server unreachable" in observation.text
        client.sync_close()


class TestMCPTool:
    """测试 MCPTool 功能。"""

    def setup_method(self):
        """设置测试测试夹具。"""
        self.mock_client: MockMCPClient = MockMCPClient()

        # 创建模拟对象 MCP 工具
        self.mock_mcp_tool: Mock = MagicMock(spec=mcp.types.Tool)
        self.mock_mcp_tool.name = "test_tool"
        self.mock_mcp_tool.description = "A test tool"
        self.mock_mcp_tool.inputSchema = {
            "type": "object",
            "properties": {"param": {"type": "string"}},
        }
        self.mock_mcp_tool.annotations = None
        self.mock_mcp_tool.meta = None

        tools = MCPToolDefinition.create(
            mcp_tool=self.mock_mcp_tool, mcp_client=self.mock_client
        )
        self.tool: MCPToolDefinition = tools[0]  # 从序列中提取单个工具

    def test_mcp_tool_creation(self):
        """测试创建 MCP 工具。"""
        assert self.tool.name == "test_tool"
        assert self.tool.description == "A test tool"

        # 从OpenAI工具中获取模式，因为MCPToolAction现在使用动态模式
        #
        openai_tool = self.tool.to_openai_tool()
        function_def = openai_tool["function"]
        assert "parameters" in function_def
        input_schema = function_def["parameters"]

        # 由于 security_risk 已从操作中删除，因此不应在模式中始终添加摘要字段以实现 LLM
        # 透明度
        #
        assert len(input_schema["properties"]) == 2
        assert "security_risk" not in input_schema["properties"]
        assert "summary" in input_schema["properties"]

        # 检查实际工具参数是否存在
        assert "param" in input_schema["properties"]
        assert input_schema["properties"]["param"] == {"type": "string"}

    def test_mcp_tool_with_annotations(self):
        """测试创建带有注释的 MCP 工具。"""
        # 模拟对象带注释的工具
        mock_tool_with_annotations = MagicMock(spec=mcp.types.Tool)
        mock_tool_with_annotations.name = "annotated_tool"
        mock_tool_with_annotations.description = "Tool with annotations"
        mock_tool_with_annotations.inputSchema = {"type": "object"}
        mock_tool_with_annotations.annotations = ToolAnnotations(title="Annotated Tool")
        mock_tool_with_annotations.meta = {"version": "1.0"}

        tools = MCPToolDefinition.create(
            mcp_tool=mock_tool_with_annotations, mcp_client=self.mock_client
        )
        tool = tools[0]  # 从序列中提取单个工具

        assert tool.name == "annotated_tool"
        assert tool.description == "Tool with annotations"
        assert tool.annotations is not None

    def test_mcp_tool_no_description(self):
        """测试创建一个没有描述的 MCP 工具。"""
        # 模拟对象没有说明的工具
        mock_tool_no_desc = MagicMock(spec=mcp.types.Tool)
        mock_tool_no_desc.name = "no_desc_tool"
        mock_tool_no_desc.description = None
        mock_tool_no_desc.inputSchema = {"type": "object"}
        mock_tool_no_desc.annotations = None
        mock_tool_no_desc.meta = None

        tools = MCPToolDefinition.create(
            mcp_tool=mock_tool_no_desc, mcp_client=self.mock_client
        )
        tool = tools[0]  # 从序列中提取单个工具

        assert tool.name == "no_desc_tool"
        assert tool.description == "No description provided"

    def test_executor_assignment(self):
        """测试该工具是否具有正确的执行器。"""
        assert isinstance(self.tool.executor, MCPToolExecutor)
        assert self.tool.executor.tool_name == "test_tool"
        assert self.tool.executor.client == self.mock_client


def test_action_type_cache_is_bounded():
    """模式不断变化的工具一定不会永远增加缓存。"""
    from openhands.sdk.mcp.tool import (
        _MCP_ACTION_TYPE_CACHE_MAX,
        _create_mcp_action_type,
        _mcp_dynamic_action_type,
    )

    for i in range(_MCP_ACTION_TYPE_CACHE_MAX + 50):
        tool = mcp.types.Tool(
            name="churning_tool",
            description="d",
            inputSchema={
                "type": "object",
                "properties": {f"field_{i}": {"type": "string"}},
            },
        )
        _create_mcp_action_type(tool)

    assert len(_mcp_dynamic_action_type) <= _MCP_ACTION_TYPE_CACHE_MAX


def test_action_type_cache_serializes_get_and_evict(monkeypatch):
    """缓存命中不得观察到同一键的并发驱逐。

    强迫实现一个真实的竞态的精确重排：在缓存命中路径（在`.get()`和`.move_to_end()`之
    间）暂停，然后让第二个线程尝试删除这个相同的条目。 如果没有
    锁，则从 `move_to_end` 得出 KeyError； 有了它，第二个线程就会阻塞，直到第一个线程
    的关键部分完成。
    """
    import threading
    import time
    from collections import OrderedDict

    import openhands.sdk.mcp.tool as tool_module

    paused = threading.Event()

    class PausingDict(OrderedDict):
        def get(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            result = super().get(*args, **kwargs)
            if result is not None and not paused.is_set():
                paused.set()
                time.sleep(0.3)
            return result

    monkeypatch.setattr(tool_module, "_MCP_ACTION_TYPE_CACHE_MAX", 1)
    monkeypatch.setattr(tool_module, "_mcp_dynamic_action_type", PausingDict())

    shared_tool = mcp.types.Tool(
        name="shared", description="d", inputSchema={"type": "object"}
    )
    other_tool = mcp.types.Tool(
        name="other", description="d", inputSchema={"type": "object"}
    )
    tool_module._create_mcp_action_type(shared_tool)  # 缓存种子

    errors: list[Exception] = []

    def hit():
        try:
            tool_module._create_mcp_action_type(shared_tool)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    def evict():
        paused.wait(2.0)
        try:
            tool_module._create_mcp_action_type(other_tool)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=hit), threading.Thread(target=evict)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5.0)

    assert not errors
