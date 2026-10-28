"""测试 Conversation 类中的 generate_title 方法。"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock, patch

import pytest

# 导入 LiteLLM 类型以获得正确的模拟
from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse, Usage
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.title_utils import generate_title_with_llm
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.llm import LLM, LLMResponse, Message, MetricsSnapshot, TextContent
from openhands.sdk.llm.auth.credentials import CredentialStore, OAuthCredentials
from openhands.sdk.llm.auth.openai import OpenAISubscriptionAuth
from openhands.sdk.settings import ACPAgentSettings


def create_test_agent() -> Agent:
    """创建测试智能体。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test")
    return Agent(llm=llm, tools=[])


def create_user_message_event(content: str) -> MessageEvent:
    """使用用户内容创建测试 MessageEvent。"""
    return MessageEvent(
        llm_message=Message(role="user", content=[TextContent(text=content)]),
        source="user",
    )


def create_mock_llm_response(content: str) -> LLMResponse:
    """创建结构正确的 LiteLLM 模拟对象响应。"""
    # 创建 LiteLLM 条消息
    message = LiteLLMMessage(content=content, role="assistant")

    # 创造选择
    choice = Choices(finish_reason="stop", index=0, message=message)

    # 创建用途
    usage = Usage(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )

    # 创建ModelResponse
    model_response = ModelResponse(
        id="test-id",
        choices=[choice],
        created=1234567890,
        model="gpt-4o-mini",
        object="chat.completion",
        usage=usage,
    )
    message = Message.from_llm_chat_message(choice["message"])
    metrics = MetricsSnapshot(
        model_name="gpt-4o-mini",
        accumulated_cost=0.0,
        max_budget_per_task=None,
        accumulated_token_usage=None,
    )
    return LLMResponse(
        message=message,
        metrics=metrics,
        raw_response=model_response,
    )


def get_completion_user_prompt(mock_completion: MagicMock) -> str:
    messages = mock_completion.call_args.kwargs["messages"]
    content = messages[1].content[0]
    assert isinstance(content, TextContent)
    return content.text


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_generate_title_without_llm_uses_agent_llm(mock_completion):
    """如果没有明确的 LLM，generate_title 就会退回到智能体的 LLM。

    这为未配置专用标题的调用者保留了向后兼容的行为 LLM。
    """
    agent = create_test_agent()
    conv = Conversation(agent=agent, visualizer=None)

    user_message = create_user_message_event("Help me create a Python script")
    conv.state.events.append(user_message)

    mock_completion.return_value = create_mock_llm_response("Create Python Script")

    title = conv.generate_title()

    assert title == "Create Python Script"
    mock_completion.assert_called_once()


def test_generate_title_skips_llm_for_settings_built_acp_agent(tmp_path):
    agent = ACPAgentSettings(
        acp_server="custom", acp_command=["true"], acp_model="claude-opus-4-7"
    ).create_agent()
    conv = Conversation(agent=agent, workspace=str(tmp_path), visualizer=None)
    conv.state.events.append(create_user_message_event("Fix the login bug"))

    with patch(
        "openhands.sdk.conversation.title_utils.generate_title_with_llm"
    ) as mock_llm_title:
        title = conv.generate_title()

    assert title == "Fix the login bug"
    mock_llm_title.assert_not_called()


def test_generate_title_no_user_messages():
    """当不存在用户消息时，测试 generate_title 引发 ValueError。"""
    agent = create_test_agent()
    conv = Conversation(agent=agent, visualizer=None)

    # 不要添加任何用户消息 - 对话可能包含系统消息

    # 应提高 ValueError
    with pytest.raises(
        ValueError, match="No user messages found in conversation events"
    ):
        conv.generate_title()


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_generate_title_llm_error_fallback(mock_completion):
    """当 LLM 失败时，测试 generate_title 会退回到简单截断。"""
    agent = create_test_agent()
    conv = Conversation(agent=agent, visualizer=None)

    # 添加用户留言
    user_message = create_user_message_event("Fix the bug in my application")
    conv.state.events.append(user_message)

    # 创建一个 LLM 来显式传递
    custom_llm = LLM(model="gpt-4o-mini", api_key=SecretStr("key"), usage_id="err")

    # 模拟对象 LLM 引发异常
    mock_completion.side_effect = Exception("LLM error")

    # 使用显式 LLM 生成标题（出现错误时应回退到截断）
    title = conv.generate_title(llm=custom_llm)

    # 验证已生成回退方案标题
    assert title == "Fix the bug in my application"


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_generate_title_with_llm_invokes_on_error(mock_completion):
    """generate_title_with_llm 通过 on_error 报告吞咽 LLM 错误
    （选择加入接缝过去常常将其呈现给客户端 - 问题#16686），同时仍然返回 None，因此调
    用者会退回到截断。
    """
    custom_llm = LLM(model="gpt-4o-mini", api_key=SecretStr("key"), usage_id="err")
    mock_completion.side_effect = Exception("model does not exist")

    seen: list[Exception] = []
    result = generate_title_with_llm("Fix the bug", custom_llm, on_error=seen.append)

    assert result is None
    assert len(seen) == 1
    assert str(seen[0]) == "model does not exist"


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_generate_title_with_llm_renders_custom_prompt_placeholders(mock_completion):
    custom_llm = LLM(model="gpt-4o-mini", api_key=SecretStr("key"), usage_id="test")
    mock_completion.return_value = create_mock_llm_response("Fix Login")

    result = generate_title_with_llm(
        "Fix the login bug",
        custom_llm,
        max_length=32,
        prompt=(
            "Return a title under {max_length} characters for: {conversation_content}"
        ),
    )

    assert result == "Fix Login"
    assert get_completion_user_prompt(mock_completion) == (
        "Return a title under 32 characters for: Fix the login bug"
    )


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_generate_title_with_llm_appends_content_to_custom_prompt(mock_completion):
    custom_llm = LLM(model="gpt-4o-mini", api_key=SecretStr("key"), usage_id="test")
    mock_completion.return_value = create_mock_llm_response("Fix Login")

    generate_title_with_llm(
        "Fix the login bug",
        custom_llm,
        prompt="Use sentence case without an emoji.",
    )

    assert get_completion_user_prompt(mock_completion) == (
        "Use sentence case without an emoji.\n\n"
        "Conversation content:\nFix the login bug"
    )


@pytest.mark.parametrize("prompt", [None, "", "   "])
@patch("openhands.sdk.llm.llm.LLM.completion")
def test_generate_title_with_llm_uses_default_for_blank_prompt(mock_completion, prompt):
    custom_llm = LLM(model="gpt-4o-mini", api_key=SecretStr("key"), usage_id="test")
    mock_completion.return_value = create_mock_llm_response("🐛 Fix Login")

    generate_title_with_llm("Fix the login bug", custom_llm, prompt=prompt)

    user_prompt = get_completion_user_prompt(mock_completion)
    assert user_prompt.startswith("Generate a title (maximum 50 characters)")
    assert "🐛 bugfix: Bug fixes" in user_prompt


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_generate_title_truncation_respects_max_length(mock_completion):
    """当 LLM 失败时，截断回退方案遵循 max_length。"""
    agent = create_test_agent()
    conv = Conversation(agent=agent, visualizer=None)

    # 添加长度超过 max_length 的用户消息
    long_message = "Create a web application with advanced features and database"
    user_message = create_user_message_event(long_message)
    conv.state.events.append(user_message)

    # 强制 LLM 无法执行截断回退方案路径
    mock_completion.side_effect = Exception("LLM error")

    title = conv.generate_title(max_length=20)

    assert len(title) <= 20
    assert title.endswith("...")


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_generate_title_with_llm_truncates_long_response(mock_completion):
    """测试 generate_title 截断对 max_length 的长 LLM 响应。"""
    agent = create_test_agent()
    conv = Conversation(agent=agent, visualizer=None)

    # 添加用户留言
    user_message = create_user_message_event("Create a web application")
    conv.state.events.append(user_message)

    # 创建一个 LLM 来显式传递
    custom_llm = LLM(model="gpt-4o-mini", api_key=SecretStr("key"), usage_id="test")

    # 模拟对象具有长标题的 LLM 响应
    mock_response = create_mock_llm_response(
        "Create a Complex Web Application with Database"
    )
    mock_completion.return_value = mock_response

    # 生成 max_length=20 且显式 LLM 的标题
    title = conv.generate_title(llm=custom_llm, max_length=20)

    # 验证标题是否被截断
    assert len(title) <= 20
    assert title.endswith("...")


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_generate_title_with_custom_llm(mock_completion):
    """使用提供的自定义 LLM 测试 generate_title。"""
    agent = create_test_agent()
    conv = Conversation(agent=agent, visualizer=None)

    # 添加用户留言
    user_message = create_user_message_event("Debug my code")
    conv.state.events.append(user_message)

    # 创建自定义 LLM
    custom_llm = LLM(
        model="gpt-3.5-turbo", api_key=SecretStr("custom-key"), usage_id="custom"
    )

    # 模拟对象自定义 LLM 响应
    mock_response = create_mock_llm_response("Debug Code Issue")
    mock_completion.return_value = mock_response

    # 使用自定义生成标题 LLM
    title = conv.generate_title(llm=custom_llm)

    # 验证标题是否已生成
    assert title == "Debug Code Issue"


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_generate_title_empty_llm_response_fallback(mock_completion):
    """当 LLM 返回空响应时，测试 generate_title 会回退。"""
    agent = create_test_agent()
    conv = Conversation(agent=agent, visualizer=None)

    # 添加用户留言
    user_message = create_user_message_event("Help with testing")
    conv.state.events.append(user_message)

    # 创建一个 LLM 来显式传递
    custom_llm = LLM(model="gpt-4o-mini", api_key=SecretStr("key"), usage_id="empty")

    # 模拟对象 LLM 响应内容为空
    mock_response = MagicMock()
    mock_response.choices = []
    mock_completion.return_value = mock_response

    # 使用显式 LLM 生成标题（在空响应时回退到截断）
    title = conv.generate_title(llm=custom_llm)

    # 验证已生成回退方案标题
    assert title == "Help with testing"


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
def test_generate_title_disables_streaming_when_llm_streams(mock_transport):
    """回归测试（PR #3901 的同级）：``stream=True`` 智能体 LLM 必须
    即使标题生成未通过 ``on_token`` 回调，仍然会生成标题。 修补 ``_transport_call``
    保留真正的流式传输守卫
    ``completion()`` 已上线，因此错误会在未修复的情况下重现。
    """
    streaming_llm = LLM(
        model="gpt-4o-mini",
        api_key=SecretStr("test-key"),
        usage_id="title-stream-test",
        stream=True,
    )
    agent = Agent(llm=streaming_llm, tools=[])
    conv = Conversation(agent=agent, visualizer=None)

    user_message = create_user_message_event("Help me create a Python script")
    conv.state.events.append(user_message)

    mock_transport.return_value = create_mock_model_response("Create Python Script")

    title = conv.generate_title()

    # 标题来自 LLM，而不是截断回退方案。
    assert title == "Create Python Script"
    mock_transport.assert_called_once()
    # 流式传输在副本上被禁用； 智能体自己的 LLM 未受影响。
    assert mock_transport.call_args.kwargs["enable_streaming"] is False
    assert mock_transport.call_args.kwargs["on_token"] is None
    assert streaming_llm.stream is True


@pytest.fixture
def title_http_server():
    requests = []
    title = "Fix title transport"

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body))
            if self.path == "/v1/responses":
                response = {
                    "id": "resp_title",
                    "object": "response",
                    "created_at": 1,
                    "status": "completed",
                    "model": "gpt-5.6-luna",
                    "output": [
                        {
                            "id": "msg_title",
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": title,
                                    "annotations": [],
                                }
                            ],
                        }
                    ],
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 4,
                        "total_tokens": 14,
                    },
                }
                if body.get("stream"):
                    payload = (
                        "event: response.completed\ndata: "
                        + json.dumps(
                            {
                                "type": "response.completed",
                                "sequence_number": 1,
                                "response": response,
                            }
                        )
                        + "\n\n"
                    ).encode()
                    content_type = "text/event-stream"
                else:
                    payload = json.dumps(response).encode()
                    content_type = "application/json"
            else:
                payload = json.dumps(
                    {
                        "id": "chat_title",
                        "object": "chat.completion",
                        "created": 1,
                        "model": "gpt-4o-mini",
                        "choices": [
                            {
                                "index": 0,
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": title},
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": 4,
                            "total_tokens": 14,
                        },
                    }
                ).encode()
                content_type = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("mode", ["chat", "responses", "subscription"])
def test_title_uses_real_http_transport(title_http_server, tmp_path, mode):
    base_url, requests = title_http_server
    if mode == "subscription":
        auth = OpenAISubscriptionAuth(
            credential_store=CredentialStore(tmp_path / "auth")
        )
        llm = auth.create_llm(
            model="gpt-5.6-luna",
            credentials=OAuthCredentials(
                vendor="openai",
                access_token="local-test-token",
                refresh_token="unused-test-token",
                expires_at=int(time.time() * 1000) + 3600000,
            ),
        )
        llm = llm.model_copy(update={"base_url": base_url, "num_retries": 0})
    else:
        llm = LLM(
            model="openai/gpt-4o-mini",
            api_key=SecretStr("local-test-key"),
            base_url=base_url,
            api_mode=mode,
            stream=True,
            num_retries=0,
        )
    errors = []
    assert (
        generate_title_with_llm("Fix the title", llm, on_error=errors.append)
        == "Fix title transport"
    )
    assert not errors
    assert len(requests) == 1
    path, body = requests[0]
    assert path == ("/v1/chat/completions" if mode == "chat" else "/v1/responses")
    assert bool(body.get("stream")) == (mode == "subscription")
    if mode != "chat":
        assert body["store"] is False


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_generate_title_strips_inline_reasoning(mock_completion):
    """守卫#4530。

    不将思想链拆分为 `reasoning_content` 的提供者将其内联返回为 `<think>...</think>`
    。 标题是逐字消耗的，因此在不进行剥离的情
    况下，截断为 `max_length` 会保留推理并丢弃标题。
    """
    llm = LLM(model="qwen3-32b", api_key=SecretStr("test-key"), usage_id="t")
    mock_completion.return_value = create_mock_llm_response(
        "<think>The user wants a CSV summary script. I will pick the features "
        "emoji and keep it short.</think>✨ Summarise a CSV in Python"
    )

    title = generate_title_with_llm("Help me summarise a CSV", llm)

    assert title == "✨ Summarise a CSV in Python"


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_generate_title_strips_unterminated_reasoning(mock_completion):
    """未终止的块意味着响应在思考过程中被切断，因此没有
    要挽救的标题，调用者会退回到被截断的消息标题。"""
    llm = LLM(model="qwen3-32b", api_key=SecretStr("test-key"), usage_id="t")
    mock_completion.return_value = create_mock_llm_response(
        "<think>Let me consider what this conversation is really about"
    )

    assert generate_title_with_llm("Help me summarise a CSV", llm) is None


@patch("openhands.sdk.llm.llm.LLM.completion")
def test_generate_title_keeps_text_without_reasoning(mock_completion):
    """正常反应不受影响。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="t")
    mock_completion.return_value = create_mock_llm_response("✨ Create Python Script")

    assert generate_title_with_llm("Help me write a script", llm) == (
        "✨ Create Python Script"
    )
