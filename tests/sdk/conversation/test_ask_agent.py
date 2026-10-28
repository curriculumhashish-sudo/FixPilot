"""测试对话类中的 ask_agent 功能。"""

import json
from collections.abc import Sequence
from unittest.mock import Mock, patch

import pytest
from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse, Usage
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.impl.remote_conversation import RemoteConversation
from openhands.sdk.event.llm_convertible import (
    ActionEvent,
    MessageEvent,
    ObservationEvent,
    SystemPromptEvent,
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


class MockAction(Action):
    command: str


class MockObservation(Observation):
    result: str

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text=self.result)]


def create_test_agent() -> Agent:
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    return Agent(llm=llm, tools=[])


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


def find_msg(messages: list[Message], role: str, text_substring: str | None = None):
    """查找具有给定角色且（可选）包含子字符串的第一条消息。"""
    for m in messages:
        if m.role != role:
            continue
        if text_substring is None:
            return m
        if any(getattr(c, "text", "").find(text_substring) != -1 for c in m.content):
            return m
    return None


# ---------------------------------------------------------------------------
# 测试夹具
# ---------------------------------------------------------------------------


@pytest.fixture
def agent() -> Agent:
    return create_test_agent()


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_local_conversation_ask_agent(mock_completion, tmp_path, agent):
    """ask_agent返回LLM响应并配置专用ask-智能体-llm。"""
    mock_completion.return_value = create_mock_llm_response(
        "This is the agent's response"
    )

    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    result = conv.ask_agent("What is 2+2?")

    assert result == "This is the agent's response"

    # LLM 被调用，并附加了一个问题作为最后一条用户消息
    mock_completion.assert_called_once()
    messages = mock_completion.call_args.kwargs["messages"]
    assert len(messages) >= 2

    user_msg = messages[-1]
    assert user_msg.role == "user"
    expected_text = (
        "<QUESTION>\n"
        "Based on the activity so far answer the following question\n\n"
        "## Question\n"
        "What is 2+2?\n\n\n"
        "<IMPORTANT>\n"
        "This is a question, do not make any tool call and just answer my question.\n"
        "</IMPORTANT>\n"
        "</QUESTION>"
    )
    assert user_msg.content[0].text == expected_text

    # 专用ask-智能体LLM配置正确
    ask_agent_llm = conv.llm_registry.get("ask-agent-llm")
    # 验证参数是否是从原始智能体的LLM复制而来
    assert ask_agent_llm.native_tool_calling == agent.llm.native_tool_calling
    assert ask_agent_llm.caching_prompt == agent.llm.caching_prompt
    assert ask_agent_llm.usage_id == "ask-agent-llm"
    # 由于我们使用默认的 LLM 值，因此这些值应该是 True
    assert ask_agent_llm.native_tool_calling is True
    assert ask_agent_llm.caching_prompt is True


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_ask_agent_llm_refreshes_after_switch_llm(mock_completion, tmp_path, agent):
    """switch_llm() 使缓存的ask-智能体-llm 无效，因此/btw 跟随开关。

    回归测试 #3943：切换用户后，会出现第二个 ask_agent() 必须克隆一个新鲜的 ask-智能
    体-来自新的llm 智能体  LLM 而不是从之前的配置中重
    用一个缓存。
    """
    mock_completion.return_value = create_mock_llm_response("answer")

    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    # 第一个 /btw 缓存从配置文件 A 克隆的ask-智能体-llm。
    conv.ask_agent("profile A?")
    assert conv.llm_registry.get("ask-agent-llm").model == agent.llm.model

    # 将对话切换到可区分的配置文件 B.
    profile_b = LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="profile-b",
    )
    conv.switch_llm(profile_b)

    # 过时的ask-智能体-llm 必须消失，而不是默默地重用。
    with pytest.raises(KeyError):
        conv.llm_registry.get("ask-agent-llm")

    # 第二个 /btw 从配置文件 B 重新克隆。
    conv.ask_agent("profile B?")
    assert conv.llm_registry.get("ask-agent-llm").model == "gpt-4o"


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_local_conversation_ask_agent_copies_llm_config(mock_completion, tmp_path):
    """ask_agent 使用从原始智能体的 LLM 复制的参数创建 LLM。"""
    mock_completion.return_value = create_mock_llm_response("Test response")

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

    result = conv.ask_agent("Test question")
    assert result == "Test response"

    # 验证ask-智能体-llm 是否复制了自定义配置
    ask_agent_llm = conv.llm_registry.get("ask-agent-llm")
    assert ask_agent_llm.native_tool_calling == agent.llm.native_tool_calling
    assert ask_agent_llm.caching_prompt == agent.llm.caching_prompt
    assert ask_agent_llm.usage_id == "ask-agent-llm"
    # 验证特定自定义值是否已复制
    assert ask_agent_llm.native_tool_calling is False
    assert ask_agent_llm.caching_prompt is False


def create_mock_model_response(content: str) -> ModelResponse:
    """原始 LiteLLM ModelResponse，由 ``LLM._transport_call`` 返回。"""
    return ModelResponse(
        id="test-id",
        choices=[
            Choices(
                finish_reason="stop",
                index=0,
                message=LiteLLMMessage(content=content, role="assistant"),
            )
        ],
        created=1234567890,
        model="gpt-4o-mini",
        object="chat.completion",
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


@patch("openhands.sdk.llm.llm.LLM._transport_call", autospec=True)
def test_ask_agent_disables_streaming_when_llm_streams(mock_transport, tmp_path):
    """回归测试（PR #3901 的同级）：``stream=True`` 智能体 LLM 必须
    即使路径没有经过 ``on_token`` 回调，仍然回答 ask_agent。 修补 ``_transport_call``
     保留真正的流式传输守卫
    ``completion()`` 已上线，因此错误会在未修复的情况下重现。
    """
    mock_transport.return_value = create_mock_model_response("4")

    streaming_llm = LLM(
        model="gpt-4o-mini",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
        stream=True,
    )
    agent = Agent(llm=streaming_llm, tools=[])
    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    result = conv.ask_agent("What is 2+2?")

    assert result == "4"
    mock_transport.assert_called_once()
    # 流式传输在专用询问-智能体 LLM 上被禁用； 智能体 LLM 未受影响。
    assert mock_transport.call_args.kwargs["enable_streaming"] is False
    assert mock_transport.call_args.kwargs["on_token"] is None
    assert streaming_llm.stream is True
    assert conv.llm_registry.get("ask-agent-llm").stream is False


@patch("openhands.sdk.llm.llm.LLM._transport_call", autospec=True)
def test_ask_agent_during_in_flight_llm_call(mock_transport, tmp_path, agent):
    """回归测试 #5082：在智能体 LLM 有调用的情况下，它的
    遥测保留开放跨度，无法对其进行深度复制。
    """
    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )
    answers = []

    def transport(llm, *args, **kwargs):
        if llm.usage_id != "ask-agent-llm":
            answers.append(conv.ask_agent("How's the progress?"))
        return create_mock_model_response("answer")

    mock_transport.side_effect = transport
    agent.llm.completion(
        messages=[Message(role="user", content=[TextContent(text="hi")])]
    )

    assert answers == ["answer"]
    assert conv.llm_registry.get("ask-agent-llm").telemetry is not agent.llm.telemetry


@patch("openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient")
def test_remote_conversation_ask_agent(mock_ws_client, agent):
    mock_ws_client.return_value.wait_until_ready.return_value = True

    workspace = RemoteWorkspace(host="http://test-server", working_dir="/tmp")
    mock_client = create_mock_http_client("12345678-1234-5678-9abc-123456789abc")

    # 对 /ask_agent 的回复
    mock_ask_response = Mock()
    mock_ask_response.raise_for_status.return_value = None
    mock_ask_response.json.return_value = {"response": "Remote agent response"}

    def mock_request(method, url, **kwargs):
        if method == "POST" and "ask_agent" in url:
            return mock_ask_response

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

        result = conv.ask_agent("What is the weather?")
        assert result == "Remote agent response"

        # 确保我们与预期的载荷进行了一次 ask_agent 调用
        ask_calls = [
            c
            for c in mock_client.request.call_args_list
            if len(c[0]) >= 2 and "ask_agent" in c[0][1]
        ]
        assert len(ask_calls) == 1

        (method, url), kwargs = ask_calls[0]
        assert method == "POST"
        assert "ask_agent" in url
        assert kwargs["json"] == {"question": "What is the weather?"}


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_ask_agent_with_existing_events_and_tool_calls(
    mock_completion, tmp_path, agent
):
    """ask_agent 包括上下文中的先前事件（用户、工具调用、观测结果）。"""
    mock_completion.return_value = create_mock_llm_response(
        "Based on the tool calls, I can see you ran 'ls' command."
    )

    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    # 0. SystemPromptEvent（正确对话状态所需）
    # 在真实的对话中，它总是在用户消息之前添加 init_state
    conv.state.events.append(
        SystemPromptEvent(
            source="agent",
            system_prompt=TextContent(text="You are a helpful assistant."),
            tools=[],  # 用于测试目的的工具列表
        )
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
            action=MockAction(command="ls -la"),
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
            observation=MockObservation(result=observation_result),
            action_id="action_123",
            tool_name="terminal",
            tool_call_id="call_123",
        )
    )

    # ask_agent应该包含整个历史
    result = conv.ask_agent("What did you find?")
    assert result == "Based on the tool calls, I can see you ran 'ls' command."

    mock_completion.assert_called_once()
    messages = mock_completion.call_args.kwargs["messages"]

    # 预期：用户 + assistant(tool_call) + 工具 + 问题
    # 注意：使用延迟初始化，如果事件发生，系统消息可能不会出现
    # 在智能体初始化之前添加
    assert len(messages) >= 4

    user_msg = find_msg(messages, "user", "List the files")
    assistant_msg = next(
        (m for m in messages if m.role == "assistant" and m.tool_calls), None
    )
    tool_msg = next((m for m in messages if m.role == "tool"), None)
    question_msg = find_msg(messages, "user", "What did you find?")

    assert user_msg is not None, "User message should be present"
    assert assistant_msg is not None, "Assistant tool-call message should be present"
    assert tool_msg is not None, "Tool response message should be present"
    assert question_msg is not None, "ask_agent question message should be present"

    # 工具调用接线
    assert len(assistant_msg.tool_calls) == 1
    assert assistant_msg.tool_calls[0].id == "call_123"
    assert assistant_msg.tool_calls[0].name == "terminal"

    assert tool_msg.tool_call_id == "call_123"
    assert tool_msg.name == "terminal"


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_ask_agent_drops_in_flight_action_without_observation(
    mock_completion, tmp_path, agent
):
    """ask_agent 必须删除尚无观测结果的正在运行的 ActionEvent。"""
    mock_completion.return_value = create_mock_llm_response("answer")

    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    conv.state.events.append(
        SystemPromptEvent(
            source="agent",
            system_prompt=TextContent(text="You are a helpful assistant."),
            tools=[],
        )
    )
    conv.state.events.append(
        MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="List the files")],
            ),
        )
    )

    # 没有匹配的飞行中操作观测结果。
    tool_call = MessageToolCall(
        id="call_inflight",
        name="terminal",
        arguments=json.dumps({"command": "ls -la"}),
        origin="completion",
    )
    conv.state.events.append(
        ActionEvent(
            source="agent",
            thought=[TextContent(text="Listing files")],
            action=MockAction(command="ls -la"),
            tool_name="terminal",
            tool_call_id="call_inflight",
            tool_call=tool_call,
            llm_response_id="response_1",
        )
    )

    conv.ask_agent("What did you find?")

    messages = mock_completion.call_args.kwargs["messages"]
    assistant_tool_calls = [
        m for m in messages if m.role == "assistant" and m.tool_calls
    ]
    assert assistant_tool_calls == [], (
        "Orphaned tool_use must be dropped from the ask_agent context"
    )


# ---------------------------------------------------------------------------
# 异常处理测试
# ---------------------------------------------------------------------------


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_ask_agent_filters_incomplete_parallel_tool_calls(
    mock_completion, tmp_path, agent
):
    mock_completion.return_value = create_mock_llm_response("One tool completed.")
    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )
    conv.state.events.append(
        SystemPromptEvent(
            source="agent",
            system_prompt=TextContent(text="You are a helpful assistant."),
            tools=[],
        )
    )

    conv.state.events.append(
        MessageEvent(
            source="user",
            llm_message=Message(
                role="user", content=[TextContent(text="Inspect two files")]
            ),
        )
    )
    for call_id in ("call_complete", "call_pending"):
        conv.state.events.append(
            ActionEvent(
                source="agent",
                thought=[],
                action=MockAction(command=f"cat {call_id}"),
                tool_name="terminal",
                tool_call_id=call_id,
                tool_call=MessageToolCall(
                    id=call_id,
                    name="terminal",
                    arguments=json.dumps({"command": f"cat {call_id}"}),
                    origin="completion",
                ),
                llm_response_id="parallel_response",
            )
        )
    conv.state.events.append(
        ObservationEvent(
            source="environment",
            observation=MockObservation(result="done"),
            action_id="action_complete",
            tool_name="terminal",
            tool_call_id="call_complete",
        )
    )

    assert conv.ask_agent("What completed?") == "One tool completed."

    messages = mock_completion.call_args.kwargs["messages"]
    tool_calls = [call for message in messages for call in (message.tool_calls or [])]
    assert tool_calls == []
    assert [message for message in messages if message.role == "tool"] == []


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_local_conversation_ask_agent_raises_context_window_error(
    mock_completion, tmp_path, agent
):
    """ask_agent 应该正确地传播 LLMContextWindowExceedError 从 LLM 完成。"""
    from openhands.sdk.llm.exceptions import LLMContextWindowExceedError

    # 模拟对象 LLM 完成以引发上下文窗口错误
    mock_completion.side_effect = LLMContextWindowExceedError(
        "Context window exceeded: conversation too long"
    )

    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    # ask_agent 应该传播异常
    with pytest.raises(LLMContextWindowExceedError) as exc_info:
        conv.ask_agent("What is the current status?")

    assert "Context window exceeded" in str(exc_info.value)
    mock_completion.assert_called_once()


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_local_conversation_ask_agent_raises_failed_to_generate_summary(
    mock_completion, tmp_path, agent
):
    """当 LLM 没有返回文本时，ask_agent 引发“无法生成摘要”。"""
    # 模拟对象 LLM 响应无文本内容
    mock_response = create_mock_llm_response("")
    mock_response.message.content = []  # 内容列表为空
    mock_completion.return_value = mock_response

    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    # ask_agent 应该引发通用异常
    with pytest.raises(Exception) as exc_info:
        conv.ask_agent("What is the current status?")

    assert str(exc_info.value) == "Failed to generate summary"
    mock_completion.assert_called_once()


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_local_conversation_ask_agent_raises_failed_to_generate_summary_non_text(
    mock_completion, tmp_path, agent
):
    """当 LLM 仅返回非文本时，ask_agent 引发“无法生成摘要”。"""
    # 模拟对象 LLM 仅包含图像内容的响应（无文本内容）
    mock_response = create_mock_llm_response("")
    mock_response.message.content = [
        ImageContent(image_urls=["http://example.com/image.jpg"])
    ]
    mock_completion.return_value = mock_response

    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    # ask_agent 应该引发通用异常
    with pytest.raises(Exception) as exc_info:
        conv.ask_agent("What is the current status?")

    assert str(exc_info.value) == "Failed to generate summary"
    mock_completion.assert_called_once()


@patch("openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient")
def test_remote_conversation_ask_agent_raises_http_status_error(mock_ws_client, agent):
    """RemoteConversation ask_agent 应该正确地传播 HTTPStatusError。"""
    mock_ws_client.return_value.wait_until_ready.return_value = True

    import httpx

    workspace = RemoteWorkspace(host="http://test-server", working_dir="/tmp")
    mock_client = create_mock_http_client("12345678-1234-5678-9abc-123456789abc")

    # 模拟对象 HTTP ask_agent 端点的错误响应
    mock_error_response = Mock()
    mock_error_response.status_code = 500
    mock_error_response.reason_phrase = "Internal Server Error"
    mock_error_response.json.return_value = {"error": "LLM context window exceeded"}
    mock_error_response.text = "Internal Server Error"

    def mock_request(method, url, **kwargs):
        if method == "POST" and "ask_agent" in url:
            # HTTPStatusError请求ask_agent
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

        # ask_agent 应该传播 HTTPStatusError
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            conv.ask_agent("What is the current status?")

        assert "500 Internal Server Error" in str(exc_info.value)


@patch("openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient")
def test_remote_conversation_ask_agent_raises_request_error(mock_ws_client, agent):
    """RemoteConversation ask_agent 从网络正确传播 RequestError。"""
    mock_ws_client.return_value.wait_until_ready.return_value = True

    import httpx

    workspace = RemoteWorkspace(host="http://test-server", working_dir="/tmp")
    mock_client = create_mock_http_client("12345678-1234-5678-9abc-123456789abc")

    def mock_request(method, url, **kwargs):
        if method == "POST" and "ask_agent" in url:
            # 针对 ask_agent 个请求引发 RequestError（网络错误）
            raise httpx.RequestError("Connection failed", request=Mock())

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

        # ask_agent 应该传播 RequestError
        with pytest.raises(httpx.RequestError) as exc_info:
            conv.ask_agent("What is the current status?")

        assert "Connection failed" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 模板目录和渲染测试
# ---------------------------------------------------------------------------


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_ask_agent_template_dir_path_construction(mock_completion, tmp_path, agent):
    """测试 ask_agent 是否正确构造 template_dir 路径并找到模板。"""
    mock_completion.return_value = create_mock_llm_response(
        "Template rendered successfully"
    )

    conv = Conversation(
        agent=agent,
        persistence_dir=str(tmp_path),
        workspace=str(tmp_path),
    )

    # 调用ask_agent触发template_dir构建
    result = conv.ask_agent("Test question")
    assert result == "Template rendered successfully"

    # 验证使用格式正确的问题调用 LLM
    mock_completion.assert_called_once()
    messages = mock_completion.call_args.kwargs["messages"]

    # 查找包含问题的用户消息
    question_msg = None
    for msg in messages:
        if msg.role == "user" and msg.content:
            for content in msg.content:
                if isinstance(content, TextContent) and "Test question" in content.text:
                    question_msg = msg
                    break

    assert question_msg is not None, "Question message should be found"

    # 验证模板是否正确呈现（包含预期的模板结构）
    question_text = question_msg.content[0].text
    assert "<QUESTION>" in question_text
    assert "Test question" in question_text
    assert "<IMPORTANT>" in question_text
    assert "do not make any tool call" in question_text
