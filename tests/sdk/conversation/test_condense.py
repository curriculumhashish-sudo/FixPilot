"""测试对话类中的压缩功能。"""

import json
from collections.abc import Sequence
from unittest.mock import Mock, patch

import pytest
from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse, Usage
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.impl.remote_conversation import RemoteConversation
from openhands.sdk.event.llm_convertible import (
    ActionEvent,
    MessageEvent,
    ObservationEvent,
)
from openhands.sdk.llm import (
    LLM,
    ImageContent,
    LLMResponse,
    Message,
    MessageToolCall,
    MetricsSnapshot,
    TextContent,
)
from openhands.sdk.tool import Action, Observation
from openhands.sdk.workspace import RemoteWorkspace
from tests.sdk.conversation.conftest import create_mock_http_client


# ---------------------------------------------------------------------------
# 测试助手
# ---------------------------------------------------------------------------


class CondenseTestMockAction(Action):
    command: str


class CondenseTestMockObservation(Observation):
    result: str

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text=self.result)]


def create_test_agent() -> Agent:
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    return Agent(llm=llm, tools=[])


def create_test_agent_with_condenser() -> Agent:
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    condenser_llm = LLM(
        model="gpt-4o-mini",
        api_key=SecretStr("test-key"),
        usage_id="test-condenser-llm",
    )
    condenser = LLMSummarizingCondenser(llm=condenser_llm, max_size=100, keep_first=5)
    return Agent(llm=llm, condenser=condenser, tools=[])


def create_mock_llm_response(content: str) -> LLMResponse:
    """创建最小的、结构正确的 LLM 响应。"""
    message = LiteLLMMessage(content=content, role="assistant")
    choice = Choices(finish_reason="stop", index=0, message=message)
    usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    model_response = ModelResponse(
        id="test-id",
        choices=[choice],
        created=1234567890,
        model="gpt-4o-mini",
        object="chat.completion",
        usage=usage,
    )

    msg = Message.from_llm_chat_message(choice["message"])
    metrics = MetricsSnapshot(
        model_name="gpt-4o-mini",
        accumulated_cost=0.0,
        max_budget_per_task=None,
        accumulated_token_usage=None,
    )

    return LLMResponse(message=msg, metrics=metrics, raw_response=model_response)


# ---------------------------------------------------------------------------
# 测试夹具
# ---------------------------------------------------------------------------


@pytest.fixture
def agent() -> Agent:
    return create_test_agent()


@pytest.fixture
def agent_with_condenser() -> Agent:
    return create_test_agent_with_condenser()


# ---------------------------------------------------------------------------
# 测试 LocalConversation.condense()
# ---------------------------------------------------------------------------


def test_local_conversation_condense_without_condenser(tmp_path, agent):
    """当未配置上下文压缩器时，condense 会引发 ValueError。"""
    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    # 添加一些事件来创造历史
    conv.state.events.append(
        MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Hello, how are you?")],
            ),
        )
    )

    # 调用 condense 应该提高 ValueError
    with pytest.raises(
        ValueError, match="Cannot condense conversation: No condenser configured"
    ):
        conv.condense()


@patch(
    "openhands.sdk.context.condenser.llm_summarizing_condenser.LLMSummarizingCondenser.condense"
)
def test_local_conversation_condense_with_condenser(
    mock_condense, tmp_path, agent_with_condenser
):
    """配置上下文压缩器时，condense 添加 CondensationRequest 并调用 agent.step()。"""  # noqa: E501
    # 模拟对象上下文压缩器以避免实际的 LLM 调用
    from openhands.sdk.event.condenser import Condensation

    # 返回一个上下文压缩事件来模拟成功上下文压缩
    mock_condense.return_value = Condensation(
        summary="Test summary", llm_response_id="test-response-id"
    )

    conv = Conversation(
        agent=agent_with_condenser,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    # 添加一些事件来创造历史
    conv.state.events.append(
        MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Hello, how are you?")],
            ),
        )
    )

    # 调用压缩
    conv.condense()

    # 检查 CondensationRequest 是否已添加到事件中
    from openhands.sdk.event.condenser import CondensationRequest

    condensation_requests = [
        e for e in conv.state.events if isinstance(e, CondensationRequest)
    ]
    assert len(condensation_requests) == 1

    # 上下文压缩器应该被称为
    mock_condense.assert_called_once()


def test_local_conversation_condense_copies_llm_config(tmp_path):
    """当未配置上下文压缩器时，即使使用自定义 LLM 配置，condense 也会引发 ValueError
    。"""  # noqa: E501
    # 使用自定义 LLM 配置创建智能体
    llm = LLM(
        model="gpt-4o-mini",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
        native_tool_calling=False,  # 非默认值
        caching_prompt=False,  # 非默认值
    )
    agent = Agent(llm=llm, tools=[])

    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    # 添加一些事件来创造历史
    conv.state.events.append(
        MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Test message")],
            ),
        )
    )

    # 调用 condense 应该提高 ValueError
    with pytest.raises(
        ValueError, match="Cannot condense conversation: No condenser configured"
    ):
        conv.condense()


def test_local_conversation_condense_with_existing_events_and_tool_calls(
    tmp_path, agent
):
    """当没有配置上下文压缩器时，即使历史记录很复杂，condense 也会引发 ValueError。"""  # noqa: E501
    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    # 1. 之前的用户消息
    conv.state.events.append(
        MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="List the files in current directory")],
            ),
        )
    )

    # 2. 带有工具调用的动作事件
    tool_call = MessageToolCall(
        id="call_123",
        name="terminal",
        arguments=json.dumps({"command": "ls -la"}),
        origin="completion",
    )
    conv.state.events.append(
        ActionEvent(
            source="agent",
            thought=[TextContent(text="I'll list the files using the terminal")],
            action=CondenseTestMockAction(command="ls -la"),
            tool_name="terminal",
            tool_call_id="call_123",
            tool_call=tool_call,
            llm_response_id="response_1",
        )
    )

    # 3. 观测结果事件（工具结果）
    observation_result = (
        "total 8\n"
        "drwxr-xr-x 2 user user 4096 Nov 25 10:00 .\n"
        "drwxr-xr-x 3 user user 4096 Nov 25 09:59 ..\n"
        "-rw-r--r-- 1 user user   12 Nov 25 10:00 test.txt"
    )
    conv.state.events.append(
        ObservationEvent(
            source="environment",
            observation=CondenseTestMockObservation(result=observation_result),
            action_id="action_123",
            tool_name="terminal",
            tool_call_id="call_123",
        )
    )

    # 调用 condense 应该提高 ValueError
    with pytest.raises(
        ValueError, match="Cannot condense conversation: No condenser configured"
    ):
        conv.condense()


def test_local_conversation_condense_force_condenser_bypasses_window(tmp_path, agent):
    """当没有配置上下文压缩器时，即使历史记录最少，condense 也会引发 ValueError。"""  # noqa: E501
    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    # 添加最少的事件（通常不会触发上下文压缩）
    conv.state.events.append(
        MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Short message")],
            ),
        )
    )

    # 调用 condense 应该提高 ValueError
    with pytest.raises(
        ValueError, match="Cannot condense conversation: No condenser configured"
    ):
        conv.condense()


# ---------------------------------------------------------------------------
# 测试 RemoteConversation.condense()
# ---------------------------------------------------------------------------


@patch("openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient")
def test_remote_conversation_condense(mock_ws_client, agent):
    """RemoteConversation.condense() 调用服务器压缩端点。"""
    mock_ws_client.return_value.wait_until_ready.return_value = True

    workspace = RemoteWorkspace(host="http://test-server", working_dir="/tmp")
    mock_client = create_mock_http_client("12345678-1234-5678-9abc-123456789abc")

    # 对 /condense 的回复
    mock_condense_response = Mock()
    mock_condense_response.raise_for_status.return_value = None
    mock_condense_response.json.return_value = {"success": True}

    def mock_request(method, url, **kwargs):
        if method == "POST" and "condense" in url:
            return mock_condense_response

        response = Mock()
        response.raise_for_status.return_value = None
        # 对于会话创建，返回一个ID； 否则，返回空列表
        response.json.return_value = (
            {"id": "12345678-1234-5678-9abc-123456789abc"}
            if method == "POST"
            else {"items": []}
        )
        return response

    mock_client.request = Mock(side_effect=mock_request)

    with patch("httpx.Client", return_value=mock_client):
        conv = RemoteConversation(
            base_url="http://test-server",
            api_key="test-key",
            agent=agent,
            workspace=workspace,
        )

        # 调用 condense - 不应引发任何异常
        conv.condense()

        # 确保我们只进行了一次精简通话
        condense_calls = [
            c
            for c in mock_client.request.call_args_list
            if len(c[0]) >= 2 and "condense" in c[0][1]
        ]
        assert len(condense_calls) == 1

        (method, url), kwargs = condense_calls[0]
        assert method == "POST"
        assert "condense" in url
        # 压缩端点不需要 JSON 载荷
        assert "json" not in kwargs or kwargs["json"] is None


@patch("openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient")
def test_remote_conversation_condense_with_agent_with_condenser(
    mock_ws_client, agent_with_condenser
):
    """RemoteConversation.condense() 与具有上下文压缩器的智能体一起使用。"""
    mock_ws_client.return_value.wait_until_ready.return_value = True

    workspace = RemoteWorkspace(host="http://test-server", working_dir="/tmp")
    mock_client = create_mock_http_client("12345678-1234-5678-9abc-123456789abc")

    # 对 /condense 的回复
    mock_condense_response = Mock()
    mock_condense_response.raise_for_status.return_value = None
    mock_condense_response.json.return_value = {"success": True}

    def mock_request(method, url, **kwargs):
        if method == "POST" and "condense" in url:
            return mock_condense_response

        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = (
            {"id": "12345678-1234-5678-9abc-123456789abc"}
            if method == "POST"
            else {"items": []}
        )
        return response

    mock_client.request = Mock(side_effect=mock_request)

    with patch("httpx.Client", return_value=mock_client):
        conv = RemoteConversation(
            base_url="http://test-server",
            api_key="test-key",
            agent=agent_with_condenser,
            workspace=workspace,
        )

        # 调用压缩 - 应该与启用上下文压缩器的智能体一起使用
        conv.condense()

        # 确保我们只进行了一次精简通话
        condense_calls = [
            c
            for c in mock_client.request.call_args_list
            if len(c[0]) >= 2 and "condense" in c[0][1]
        ]
        assert len(condense_calls) == 1


# ---------------------------------------------------------------------------
# 异常处理测试
# ---------------------------------------------------------------------------


def test_local_conversation_condense_raises_context_window_error(tmp_path, agent):
    """当未配置上下文压缩器时，condense 会引发 ValueError。"""
    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    # 添加一些事件来创造历史
    conv.state.events.append(
        MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Test message")],
            ),
        )
    )

    # 调用 condense 应该提高 ValueError
    with pytest.raises(
        ValueError, match="Cannot condense conversation: No condenser configured"
    ):
        conv.condense()


def test_local_conversation_condense_handles_empty_response(tmp_path, agent):
    """当未配置上下文压缩器时，condense 会引发 ValueError。"""
    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    # 添加一些事件来创造历史
    conv.state.events.append(
        MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Test message")],
            ),
        )
    )

    # 调用 condense 应该提高 ValueError
    with pytest.raises(
        ValueError, match="Cannot condense conversation: No condenser configured"
    ):
        conv.condense()


@patch("openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient")
def test_remote_conversation_condense_raises_http_status_error(mock_ws_client, agent):
    """RemoteConversation 精简后的 HTTPStatusError 从服务器传播。"""
    mock_ws_client.return_value.wait_until_ready.return_value = True

    import httpx

    workspace = RemoteWorkspace(host="http://test-server", working_dir="/tmp")
    mock_client = create_mock_http_client("12345678-1234-5678-9abc-123456789abc")

    # 模拟对象 HTTP 压缩端点的错误响应
    mock_error_response = Mock()
    mock_error_response.status_code = 500
    mock_error_response.reason_phrase = "Internal Server Error"
    mock_error_response.json.return_value = {"error": "Condensation failed"}
    mock_error_response.text = "Internal Server Error"

    def mock_request(method, url, **kwargs):
        if method == "POST" and "condense" in url:
            # 针对压缩请求提出 HTTPStatusError
            raise httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=Mock(),
                response=mock_error_response,
            )

        # 其他请求的正常响应
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = (
            {"id": "12345678-1234-5678-9abc-123456789abc"}
            if method == "POST"
            else {"items": []}
        )
        return response

    mock_client.request = Mock(side_effect=mock_request)

    with patch("httpx.Client", return_value=mock_client):
        conv = RemoteConversation(
            base_url="http://test-server",
            api_key="test-key",
            agent=agent,
            workspace=workspace,
        )

        # 压缩应该传播 HTTPStatusError
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            conv.condense()

        assert "500 Internal Server Error" in str(exc_info.value)


@patch("openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient")
def test_remote_conversation_condense_raises_request_error(mock_ws_client, agent):
    """RemoteConversation 压缩从网络正确传播 RequestError。"""
    mock_ws_client.return_value.wait_until_ready.return_value = True

    import httpx

    workspace = RemoteWorkspace(host="http://test-server", working_dir="/tmp")
    mock_client = create_mock_http_client("12345678-1234-5678-9abc-123456789abc")

    def mock_request(method, url, **kwargs):
        if method == "POST" and "condense" in url:
            # 针对压缩请求提出 RequestError
            raise httpx.RequestError("Network connection failed")

        # 其他请求的正常响应
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = (
            {"id": "12345678-1234-5678-9abc-123456789abc"}
            if method == "POST"
            else {"items": []}
        )
        return response

    mock_client.request = Mock(side_effect=mock_request)

    with patch("httpx.Client", return_value=mock_client):
        conv = RemoteConversation(
            base_url="http://test-server",
            api_key="test-key",
            agent=agent,
            workspace=workspace,
        )

        # 压缩应该传播 RequestError
        with pytest.raises(httpx.RequestError) as exc_info:
            conv.condense()

        assert "Network connection failed" in str(exc_info.value)


# ---------------------------------------------------------------------------
# LLM 注册表测试
# ---------------------------------------------------------------------------


def test_local_conversation_condense_llm_registry_isolation(tmp_path, agent):
    """当未配置上下文压缩器时，condense 会引发 ValueError。"""
    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    # 添加一些事件来创造历史
    conv.state.events.append(
        MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Test message")],
            ),
        )
    )

    # 检查初始LLM注册表状态
    initial_llms = conv.llm_registry.list_usage_ids()
    assert "condense-llm" not in initial_llms

    # 调用 condense 应该提高 ValueError
    with pytest.raises(
        ValueError, match="Cannot condense conversation: No condenser configured"
    ):
        conv.condense()

    # LLM 注册表应保持不变
    final_llms = conv.llm_registry.list_usage_ids()
    assert "condense-llm" not in final_llms
