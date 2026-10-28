"""
独立单元测试用于 WebhookSubscriber 类功能。

此测试文件重新创建 WebhookSubscriber 类逻辑来测试它，而不依赖于 openhands.sdk 模块。
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from pydantic import BaseModel, SecretStr, ValidationError

from openhands.agent_server.config import WebhookSpec
from openhands.agent_server.conversation_service import (
    ConversationService,
    WebhookSubscriber,
)
from openhands.agent_server.event_service import EventService
from openhands.agent_server.models import StoredConversation
from openhands.agent_server.pub_sub import PubSub
from openhands.agent_server.utils import utc_now
from openhands.sdk import LLM, Agent, Event
from openhands.sdk.event import StreamingDeltaEvent
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.llm.message import Message, TextContent
from openhands.sdk.workspace import LocalWorkspace
from tests.agent_server.stress.scripts import (
    SlowTestLLM,
    start_conversation_with_test_llm,
    text_message,
)


@pytest.fixture
def mock_event_service():
    """创建模拟对象 EventService 进行测试。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        # 模拟对象 httpx.get 防止在 LLM init 期间 HTTP 调用登台服务器
        with patch("openhands.sdk.llm.utils.model_info.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(json=lambda: {"data": []})
            service = EventService(
                stored=StoredConversation(
                    id=uuid4(),
                    workspace=LocalWorkspace(working_dir="workspace/project"),
                ),
                agent=Agent(
                    llm=LLM(
                        usage_id="test-llm",
                        model="test-model",
                        api_key=SecretStr("test-key"),
                    ),
                    tools=[],
                ),
                conversations_dir=temp_path / "conversations_dir",
            )
            yield service


@pytest.fixture
def webhook_spec():
    """创建一个 WebhookSpec 进行测试。"""
    return WebhookSpec(
        base_url="https://example.com",
        event_buffer_size=3,
        headers={"Content-Type": "application/json", "Authorization": "Bearer token"},
        num_retries=2,
        retry_delay=1,
        flush_delay=0.1,  # 测试延迟短
    )


@pytest.fixture
def minimal_webhook_spec():
    """创建一个最小的 WebhookSpec 进行测试。"""
    return WebhookSpec(base_url="https://example.com")


@pytest.fixture
def sample_event():
    """创建一个示例事件以进行测试。"""
    text_content = TextContent(text="Hello, world!")
    message = Message(role="user", content=[text_content])
    message_event = MessageEvent(source="user", llm_message=message)
    return message_event


@pytest.fixture
def sample_events():
    """创建多个示例事件以进行测试。"""
    events = []
    for i in range(5):
        text_content = TextContent(text="Hello, world!")
        message = Message(role="user", content=[text_content])
        message_event = MessageEvent(source="user", llm_message=message)
        events.append(message_event)
    return events


@pytest.fixture
def sample_conversation_id():
    """创建示例对话 ID 进行测试。"""
    return uuid4()


class TestWebhookSpecValidation:
    """测试用例为 WebhookSpec 验证。"""

    def test_webhook_spec_default_flush_delay(self):
        """测试 WebhookSpec 是否具有默认值 flush_delay。"""
        spec = WebhookSpec(base_url="https://example.com")
        assert spec.flush_delay == 30.0

    def test_webhook_spec_custom_flush_delay(self):
        """测试 WebhookSpec 是否接受自定义 flush_delay 值。"""
        spec = WebhookSpec(base_url="https://example.com", flush_delay=60.0)
        assert spec.flush_delay == 60.0

    def test_webhook_spec_flush_delay_validation_positive(self):
        """测试 flush_delay 必须为正。"""
        with pytest.raises(ValidationError) as exc_info:
            WebhookSpec(base_url="https://example.com", flush_delay=0.0)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "greater_than"
        assert "flush_delay" in errors[0]["loc"]

    def test_webhook_spec_flush_delay_validation_negative(self):
        """测试 flush_delay 不能为负数。"""
        with pytest.raises(ValidationError) as exc_info:
            WebhookSpec(base_url="https://example.com", flush_delay=-1.0)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "greater_than"
        assert "flush_delay" in errors[0]["loc"]

    def test_webhook_spec_flush_delay_validation_small_positive(self):
        """测试是否接受小的正 flush_delay 值。"""
        spec = WebhookSpec(base_url="https://example.com", flush_delay=0.1)
        assert spec.flush_delay == 0.1


class TestWebhookSubscriberInitialization:
    """测试用例用于 WebhookSubscriber 初始化。"""

    def test_init_with_all_parameters(
        self, mock_event_service, webhook_spec, sample_conversation_id
    ):
        """使用所有参数测试初始化​​。"""
        session_api_key = "test_api_key"
        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
            session_api_key=session_api_key,
        )

        assert subscriber.conversation_id == sample_conversation_id
        assert subscriber.service == mock_event_service
        assert subscriber.spec == webhook_spec
        assert subscriber.session_api_key == session_api_key
        assert subscriber.queue == []

    def test_init_without_session_api_key(
        self, mock_event_service, webhook_spec, sample_conversation_id
    ):
        """测试没有会话 API 键的初始化。"""
        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        assert subscriber.conversation_id == sample_conversation_id
        assert subscriber.service == mock_event_service
        assert subscriber.spec == webhook_spec
        assert subscriber.session_api_key is None
        assert subscriber.queue == []

    def test_init_with_minimal_spec(
        self, mock_event_service, minimal_webhook_spec, sample_conversation_id
    ):
        """使用最小 Webhook 规格测试初始化。"""
        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=minimal_webhook_spec,
        )

        assert subscriber.conversation_id == sample_conversation_id
        assert subscriber.service == mock_event_service
        assert subscriber.spec == minimal_webhook_spec
        assert subscriber.session_api_key is None
        assert subscriber.queue == []


class TestWebhookSubscriberCallMethod:
    """测试用例代表 WebhookSubscriber.__call__ 方法。"""

    @pytest.mark.asyncio
    async def test_call_adds_event_to_queue(
        self, mock_event_service, webhook_spec, sample_event, sample_conversation_id
    ):
        """测试调用订阅者是否将事件添加到队列中。"""
        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        await subscriber(sample_event)

        assert len(subscriber.queue) == 1
        assert subscriber.queue[0] == sample_event

    @pytest.mark.asyncio
    async def test_call_multiple_events_below_buffer_size(
        self, mock_event_service, webhook_spec, sample_events, sample_conversation_id
    ):
        """测试添加低于缓冲区大小的多个事件。"""
        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 添加2个事件（缓冲区大小为3）
        for event in sample_events[:2]:
            await subscriber(event)

        assert len(subscriber.queue) == 2
        assert subscriber.queue == sample_events[:2]

    @pytest.mark.asyncio
    @patch.object(WebhookSubscriber, "_post_events")
    async def test_call_triggers_post_when_buffer_full(
        self,
        mock_post_events,
        mock_event_service,
        webhook_spec,
        sample_events,
        sample_conversation_id,
    ):
        """测试达到缓冲区大小是否会触发 _post_events。"""
        mock_post_events.return_value = None
        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 添加事件直至达到缓冲区大小 (3)
        for event in sample_events[:3]:
            await subscriber(event)

        # _post_events 缓冲区已满时应调用一次
        mock_post_events.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_triggers_post_multiple_times(
        self,
        mock_event_service,
        webhook_spec,
        sample_events,
        sample_event,
        sample_conversation_id,
    ):
        """测试当缓冲区填充时 _post_events 是否被多次调用。"""
        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 模拟对象 _post_events 方法用于跟踪呼叫但不实际发布
        post_events_calls = []

        async def mock_post_events():
            post_events_calls.append(len(subscriber.queue))
            subscriber.queue.clear()  # 模拟清队列

        subscriber._post_events = mock_post_events

        # 添加 6 个事件（缓冲区大小为 3，因此应触发两次：在 3 个事件时和在 6 个事件时）
        #
        for event in sample_events:  # 5 项活动
            await subscriber(event)

        # 添加一个事件以触发第二篇帖子
        await subscriber(sample_event)

        # _post_events 应该被调用两次（在 3 个事件和 6 个事件）
        assert len(post_events_calls) == 2
        assert post_events_calls[0] == 3  # 第一次调用包含 3 个事件
        assert post_events_calls[1] == 3  # 第二次调用包含 3 个事件


class TestWebhookSubscriberPostEvents:
    """测试用例代表 WebhookSubscriber._post_events 方法。"""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_post_events_success(
        self,
        mock_client_class,
        mock_event_service,
        webhook_spec,
        sample_events,
        sample_conversation_id,
    ):
        """测试事件的成功发布。"""
        # 设置模拟对象客户端
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 将事件添加到队列
        subscriber.queue = sample_events[:3]

        await subscriber._post_events()

        # 验证 HTTP 请求是否正确发出
        expected_url = f"https://example.com/events/{sample_conversation_id.hex}"
        mock_client.request.assert_called_once_with(
            method="POST",
            url=expected_url,
            json=[event.model_dump(mode="json") for event in sample_events[:3]],
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer token",
            },
            timeout=30.0,
        )

        # 验证队列已清除
        assert subscriber.queue == []

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_post_events_with_session_api_key(
        self,
        mock_client_class,
        mock_event_service,
        webhook_spec,
        sample_events,
        sample_conversation_id,
    ):
        """使用会话 API 键测试发布事件。"""
        # 设置模拟对象客户端
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
            session_api_key="test_session_key",
        )

        # 将事件添加到队列
        subscriber.queue = sample_events[:2]

        await subscriber._post_events()

        # 验证会话 API 密钥已添加到标头中
        expected_headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer token",
            "X-Session-API-Key": "test_session_key",
        }
        expected_url = f"https://example.com/events/{sample_conversation_id.hex}"
        mock_client.request.assert_called_once_with(
            method="POST",
            url=expected_url,
            json=[event.model_dump(mode="json") for event in sample_events[:2]],
            headers=expected_headers,
            timeout=30.0,
        )

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_post_events_serializes_set_and_secretstr(
        self,
        mock_client_class,
        mock_event_service,
        webhook_spec,
        sample_conversation_id,
    ):
        """Regression: 包含 set / SecretStr 的事件必须为序列化。

        Plain model_dump() 离开集合 SecretStr as Python httpx的 JSON 编码器无法序列化
         (集合对象)
        SecretStr 不是 JSON serializable"), failing every  重试并删除事件。
        model_dump(mode="
        JSON）使他们 JSON-safe.
        """
        import json as _json

        # 测试事件的类型 model_dump() 留下不可序列化的 JSON。
        # 注意：故意不是ConversationEvent； 我们只关心序列化
        # Webhook POST 载荷具有棘手字段类型的 Pydantic 模型。
        class _EventWithTrickyTypes(BaseModel):
            tags: set[str]
            secret: SecretStr

        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )
        # 故意为回归测试指定非 ConversationEvent。
        subscriber.queue = [
            _EventWithTrickyTypes(tags={"a", "b"}, secret=SecretStr("shh"))  # type: ignore[assignment]
        ]

        await subscriber._post_events()

        posted_json = mock_client.request.call_args.kwargs["json"]
        # httpx 在内部序列化它； 它不能提高 TypeError。
        _json.dumps(posted_json)
        assert isinstance(posted_json[0]["tags"], list)
        # 在 JSON 模式下，SecretStr 被屏蔽，而不是泄漏。
        assert posted_json[0]["secret"] != "shh"

    @pytest.mark.asyncio
    async def test_post_events_empty_queue(
        self, mock_event_service, webhook_spec, sample_conversation_id
    ):
        """使用空队列测试发布事件。"""
        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 应提前返回而不提出 HTTP 请求
        with patch("httpx.AsyncClient") as mock_client_class:
            await subscriber._post_events()
            mock_client_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_events_http_error_with_retries(
        self, mock_event_service, webhook_spec, sample_events, sample_conversation_id
    ):
        """使用重试逻辑测试 HTTP 错误处理。"""
        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 将事件添加到队列
        subscriber.queue = sample_events[:2]

        # 追踪重试次尝试
        retry_attempts = []
        sleep_calls = []

        # 模拟对象HTTP客户端和睡眠
        async def mock_request(*args, **kwargs):
            retry_attempts.append(len(retry_attempts) + 1)
            if len(retry_attempts) <= 2:  # 前两次尝试失败
                raise httpx.HTTPStatusError(
                    "Server Error", request=MagicMock(), response=MagicMock()
                )
            # 第三次尝试成功 - 返回模拟对象响应
            response = AsyncMock()
            response.raise_for_status.return_value = None
            return response

        async def mock_sleep(delay):
            sleep_calls.append(delay)

        subscriber._sleep = mock_sleep
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = mock_request
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await subscriber._post_events()

        # 验证已尝试重试
        assert len(retry_attempts) == 3
        # 仅记录此实例的延迟——没有全局睡眠污染。
        assert sleep_calls == [webhook_spec.retry_delay] * 2

        # 验证成功后队列是否被清除
        assert subscriber.queue == []

    @pytest.mark.asyncio
    async def test_post_events_max_retries_exceeded(
        self, mock_event_service, webhook_spec, sample_events, sample_conversation_id
    ):
        """测试超出 max 重试时的行为。"""
        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 将事件添加到队列
        original_events = sample_events[:2]
        subscriber.queue = original_events.copy()

        # 追踪重试次尝试
        retry_attempts = []
        sleep_calls = []

        # 模拟对象 HTTP 客户端总是失败
        async def mock_request(*args, **kwargs):
            retry_attempts.append(len(retry_attempts) + 1)
            raise httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=MagicMock()
            )

        async def mock_sleep(delay):
            sleep_calls.append(delay)

        subscriber._sleep = mock_sleep
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = mock_request
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await subscriber._post_events()

        # 验证所有重试均已尝试（num_retries + 1 = 3 次总尝试）
        assert len(retry_attempts) == 3
        # 仅记录此实例的延迟——没有全局睡眠污染。
        assert sleep_calls == [webhook_spec.retry_delay] * 2

        # 验证事件在失败后重新排队
        assert len(subscriber.queue) == 2
        assert subscriber.queue == original_events

    @pytest.mark.asyncio
    async def test_post_events_drops_oldest_when_requeue_exceeds_max_queue_size(
        self, mock_event_service, sample_conversation_id
    ):
        """重新排队失败会修剪过去 max_queue_size 的最旧事件。"""
        # 紧密绑定，因此我们可以轻松构造溢出。
        spec = WebhookSpec(
            base_url="https://example.com",
            event_buffer_size=1,
            flush_delay=0.1,
            num_retries=0,
            retry_delay=0,
            max_queue_size=3,
        )
        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=spec,
        )

        # 构建 5 个不同的、可识别的事件。
        events = []
        for i in range(5):
            ev = MessageEvent(
                source="user",
                llm_message=Message(role="user", content=[TextContent(text=f"e{i}")]),
            )
            events.append(ev)

        # 预加载队列超出界限，因此在失败后重新扩展必须修剪。
        subscriber.queue = events.copy()

        async def mock_request(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=MagicMock()
            )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = mock_request
            mock_client_class.return_value.__aenter__.return_value = mock_client
            await subscriber._post_events()

        # Bound 受到尊重，*oldest* 事件被丢弃。
        assert len(subscriber.queue) == spec.max_queue_size
        assert subscriber.queue == events[-spec.max_queue_size :]

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_post_events_handles_events_without_model_dump(
        self,
        mock_client_class,
        mock_event_service,
        webhook_spec,
        sample_conversation_id,
    ):
        """测试没有 model_dump 方法的发布事件。"""
        # 设置模拟对象客户端
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 创建不带 model_dump 方法的事件
        event_without_model_dump = MagicMock()
        del event_without_model_dump.model_dump  # 删除model_dump方法
        event_without_model_dump.__dict__ = {"type": "test", "data": "value"}

        subscriber.queue = [event_without_model_dump]

        await subscriber._post_events()

        # 验证当 model_dump 不可用时使用 __dict__
        expected_url = f"https://example.com/events/{sample_conversation_id.hex}"
        mock_client.request.assert_called_once_with(
            method="POST",
            url=expected_url,
            json=[{"type": "test", "data": "value"}],
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer token",
            },
            timeout=30.0,
        )


class TestWebhookSubscriberCloseMethod:
    """测试用例代表 WebhookSubscriber.close 方法。"""

    @pytest.mark.asyncio
    @patch.object(WebhookSubscriber, "_post_events")
    async def test_close_posts_remaining_events(
        self,
        mock_post_events,
        mock_event_service,
        webhook_spec,
        sample_events,
        sample_conversation_id,
    ):
        """测试 close 方法是否将剩余事件发布到队列中。"""
        mock_post_events.return_value = None
        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 将事件添加到队列
        subscriber.queue = sample_events[:2]

        await subscriber.close()

        # 验证 _post_events 被调用
        mock_post_events.assert_called_once()

    @pytest.mark.asyncio
    @patch.object(WebhookSubscriber, "_post_events")
    async def test_close_with_empty_queue(
        self, mock_post_events, mock_event_service, webhook_spec, sample_conversation_id
    ):
        """使用空队列测试 close 方法。"""
        mock_post_events.return_value = None
        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        await subscriber.close()

        # _post_events 当队列为空时不应调用
        mock_post_events.assert_not_called()


class TestWebhookSubscriberIntegration:
    """WebhookSubscriber 的集成测试个案例。"""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_full_workflow(
        self,
        mock_client_class,
        mock_event_service,
        webhook_spec,
        sample_events,
        sample_conversation_id,
    ):
        """测试从事件添加到发布的完整工作流程。"""
        # 设置模拟对象客户端
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
            session_api_key="integration_test_key",
        )

        # 逐一添加事件（缓冲区大小为3）
        await subscriber(sample_events[0])
        assert len(subscriber.queue) == 1

        await subscriber(sample_events[1])
        assert len(subscriber.queue) == 2

        # 这应该会触发 _post_events
        await subscriber(sample_events[2])
        assert len(subscriber.queue) == 0  # 队列应该被清除

        # 验证已发出 HTTP 请求
        mock_client.request.assert_called_once()

        # 添加更多事件并关闭
        await subscriber(sample_events[3])
        await subscriber(sample_events[4])
        assert len(subscriber.queue) == 2

        await subscriber.close()
        assert len(subscriber.queue) == 0  # 关闭后应清除队列

        # 验证关闭期间再次发出 HTTP 请求
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_concurrent_event_processing(
        self,
        mock_client_class,
        mock_event_service,
        webhook_spec,
        sample_events,
        sample_conversation_id,
    ):
        """测试处理并发事件添加。"""
        # 设置模拟对象客户端
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 同时处理事件
        tasks = [subscriber(event) for event in sample_events]
        await asyncio.gather(*tasks)

        # 缓冲区大小为 3 时，我们应该发布一次并剩余 2 个事件
        assert len(subscriber.queue) == 2
        mock_client.request.assert_called_once()

        # 接近发布剩余事件
        await subscriber.close()
        assert len(subscriber.queue) == 0
        assert mock_client.request.call_count == 2


@pytest.mark.asyncio
async def test_concurrent_event_delivery_has_one_request_in_flight(
    mock_event_service, sample_event, sample_conversation_id
):
    spec = WebhookSpec(
        base_url="https://example.com",
        event_buffer_size=5,
        flush_delay=3600,
        num_retries=0,
    )
    subscriber = WebhookSubscriber(
        conversation_id=sample_conversation_id,
        service=mock_event_service,
        spec=spec,
    )

    request_started = asyncio.Event()
    release_requests = asyncio.Event()
    active_requests = 0
    peak_active_requests = 0
    batches: list[list[dict]] = []

    async def blocked_request(*args, **kwargs):
        nonlocal active_requests, peak_active_requests
        active_requests += 1
        peak_active_requests = max(peak_active_requests, active_requests)
        batches.append(kwargs["json"])
        request_started.set()
        await release_requests.wait()
        active_requests -= 1
        response = MagicMock()
        response.raise_for_status.return_value = None
        return response

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = blocked_request
        mock_client_class.return_value.__aenter__.return_value = mock_client
        tasks = [asyncio.create_task(subscriber(sample_event)) for _ in range(40)]
        await asyncio.wait_for(request_started.wait(), timeout=1)
        await asyncio.sleep(0.05)
        try:
            assert peak_active_requests == 1
        finally:
            release_requests.set()
            await asyncio.gather(*tasks)

        await subscriber.close()

    assert peak_active_requests == 1
    assert sum(len(batch) for batch in batches) == 40
    assert all(len(batch) <= spec.event_buffer_size for batch in batches)


@pytest.mark.asyncio
async def test_events_published_during_post_are_sent_once_buffer_is_full(
    mock_event_service, sample_event, sample_conversation_id
):
    """在飞行中 POST 期间再次填充的缓冲区会立即发布。"""
    spec = WebhookSpec(
        base_url="https://example.com",
        event_buffer_size=2,
        flush_delay=3600,
        num_retries=0,
    )
    subscriber = WebhookSubscriber(
        conversation_id=sample_conversation_id,
        service=mock_event_service,
        spec=spec,
    )

    first_request_started = asyncio.Event()
    release_first_request = asyncio.Event()
    batches: list[list[dict]] = []

    async def request(*args, **kwargs):
        batches.append(kwargs["json"])
        if len(batches) == 1:
            first_request_started.set()
            await release_first_request.wait()
        response = MagicMock()
        response.raise_for_status.return_value = None
        return response

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = request
        mock_client_class.return_value.__aenter__.return_value = mock_client

        await subscriber(sample_event)
        first_post = asyncio.create_task(subscriber(sample_event))
        await asyncio.wait_for(first_request_started.wait(), timeout=1)

        # 当第一批事件正在进行时，另外两个事件填充了缓冲区。
        await subscriber(sample_event)
        await subscriber(sample_event)
        release_first_request.set()
        await asyncio.wait_for(first_post, timeout=1)

        # 无需等待 flush_delay（1 小时）或 close()。
        assert [len(batch) for batch in batches] == [2, 2]
        assert subscriber.queue == []
        # 在第一个 POST 期间启动的计时器不会继续运行。
        assert subscriber._flush_timer is None


@pytest.mark.asyncio
async def test_failed_follow_up_batch_keeps_a_flush_timer(
    mock_event_service, sample_event, sample_conversation_id
):
    """刷新计时器触发后失败的后续批次将重试。"""
    spec = WebhookSpec(
        base_url="https://example.com",
        event_buffer_size=2,
        flush_delay=3600,
        num_retries=0,
    )
    subscriber = WebhookSubscriber(
        conversation_id=sample_conversation_id,
        service=mock_event_service,
        spec=spec,
    )
    fire_timer = asyncio.Event()
    timer_sleeps = 0

    async def controlled_sleep(delay):
        nonlocal timer_sleeps
        timer_sleeps += 1
        if timer_sleeps == 1:
            await fire_timer.wait()
        else:
            await asyncio.Event().wait()

    subscriber._sleep = controlled_sleep

    first_request_started = asyncio.Event()
    release_first_request = asyncio.Event()
    second_request_started = asyncio.Event()
    release_second_request = asyncio.Event()
    batches: list[list[dict]] = []

    async def request(*args, **kwargs):
        batches.append(kwargs["json"])
        response = MagicMock()
        if len(batches) == 1:
            first_request_started.set()
            await release_first_request.wait()
            response.raise_for_status.return_value = None
        else:
            second_request_started.set()
            await release_second_request.wait()
            response.raise_for_status.side_effect = RuntimeError("503")
        return response

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = request
        mock_client_class.return_value.__aenter__.return_value = mock_client

        await subscriber(sample_event)
        first_post = asyncio.create_task(subscriber(sample_event))
        await asyncio.wait_for(first_request_started.wait(), timeout=1)

        # 在第一个 POST 期间，两个事件重新填充缓冲区：计时器启动。
        await subscriber(sample_event)
        await subscriber(sample_event)
        timer = subscriber._flush_timer
        assert timer is not None
        release_first_request.set()
        await asyncio.wait_for(second_request_started.wait(), timeout=1)

        # 计时器在后续 POST 期间触发并发现一个空队列。
        fire_timer.set()
        await asyncio.wait_for(timer, timeout=1)
        assert subscriber._flush_timer is None

        # 后续 POST 失败：不得在没有计时器的情况下留下其事件。
        release_second_request.set()
        await asyncio.wait_for(first_post, timeout=1)

        assert len(subscriber.queue) == 2
        assert subscriber._flush_timer is not None
        assert not subscriber._flush_timer.done()
        await subscriber.close()


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_post_events_splits_batches_by_serialized_bytes(
    mock_client_class, mock_event_service, sample_conversation_id
):
    spec = WebhookSpec(
        base_url="https://example.com",
        event_buffer_size=100,
        flush_delay=3600,
        num_retries=0,
        max_batch_bytes=4096,
    )
    subscriber = WebhookSubscriber(
        conversation_id=sample_conversation_id,
        service=mock_event_service,
        spec=spec,
    )
    subscriber.queue = [
        MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="x" * 3000)]),
        )
        for _ in range(3)
    ]

    mock_client = AsyncMock()
    response = MagicMock()
    response.raise_for_status.return_value = None
    mock_client.request.return_value = response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    await subscriber._post_events()

    batches = [call.kwargs["json"] for call in mock_client.request.call_args_list]
    assert len(batches) == 3
    for batch in batches:
        payload_bytes = len(
            json.dumps(batch, ensure_ascii=False, separators=(",", ":")).encode()
        )
        assert payload_bytes <= spec.max_batch_bytes or len(batch) == 1


@pytest.mark.asyncio
async def test_queue_drops_oldest_events_past_serialized_byte_limit(
    mock_event_service, sample_conversation_id
):
    events = [
        MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text=f"{i}" * 1000)]),
        )
        for i in range(2)
    ]
    event_size = len(
        json.dumps(
            events[0].model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    )
    spec = WebhookSpec(
        base_url="https://example.com",
        event_buffer_size=100,
        flush_delay=3600,
        max_batch_bytes=1024 * 1024,
        max_queue_bytes=event_size + 1,
    )
    subscriber = WebhookSubscriber(
        conversation_id=sample_conversation_id,
        service=mock_event_service,
        spec=spec,
    )

    try:
        await subscriber(events[0])
        await subscriber(events[1])

        assert subscriber.queue == [events[1]]
        assert subscriber._queue_bytes <= spec.max_queue_bytes
        assert subscriber._dropped_events == 1
    finally:
        subscriber._cancel_flush_timer()


class TestWebhookSubscriberErrorHandling:
    """测试用例用于 WebhookSubscriber 中的错误处理。"""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_network_error_handling(
        self,
        mock_client_class,
        mock_event_service,
        webhook_spec,
        sample_events,
        sample_conversation_id,
    ):
        """测试网络错误的处理。"""
        # 设置模拟对象客户端以引发网络错误
        mock_client = AsyncMock()
        mock_client.request.side_effect = httpx.NetworkError("Connection failed")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        subscriber.queue = sample_events[:2]

        # 记录在实例自己的接缝上，而不是全局 asyncio.sleep。
        sleep_calls: list[float] = []

        async def record_sleep(delay):
            sleep_calls.append(delay)

        subscriber._sleep = record_sleep
        await subscriber._post_events()

        # 验证已尝试重试
        assert mock_client.request.call_count == 3  # num_retries + 1
        assert sleep_calls == [webhook_spec.retry_delay] * 2

        # 事件失败后应重新排队
        assert len(subscriber.queue) == 2

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_timeout_error_handling(
        self,
        mock_client_class,
        mock_event_service,
        webhook_spec,
        sample_events,
        sample_conversation_id,
    ):
        """测试超时错误的处理。"""
        # 设置模拟对象客户端以引发超时错误
        mock_client = AsyncMock()
        mock_client.request.side_effect = httpx.TimeoutException("Request timed out")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        subscriber.queue = sample_events[:1]

        # 记录在实例自己的接缝上，而不是全局 asyncio.sleep。
        sleep_calls: list[float] = []

        async def record_sleep(delay):
            sleep_calls.append(delay)

        subscriber._sleep = record_sleep
        await subscriber._post_events()

        # 验证已尝试重试
        assert mock_client.request.call_count == 3
        assert sleep_calls == [webhook_spec.retry_delay] * 2

        # 事件失败后应重新排队
        assert len(subscriber.queue) == 1


class TestWebhookSubscriberFlushDelay:
    """测试用例用于 WebhookSubscriber 中的 flush_delay 功能。"""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_flush_delay_triggers_post(
        self,
        mock_client_class,
        mock_event_service,
        webhook_spec,
        sample_event,
        sample_conversation_id,
    ):
        """测试 flush_delay 是否在指定的延迟后触发发布。"""
        # 设置模拟对象客户端
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 添加一个事件（低于缓冲区大小）
        await subscriber(sample_event)
        assert len(subscriber.queue) == 1

        # 等待flush_delay触发
        await asyncio.sleep(webhook_spec.flush_delay + 0.05)

        # 验证已发出 HTTP 请求并且队列已清除
        mock_client.request.assert_called_once()
        assert len(subscriber.queue) == 0

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_flush_delay_not_reset_on_new_event(
        self,
        mock_client_class,
        mock_event_service,
        webhook_spec,
        sample_events,
        sample_conversation_id,
    ):
        """测试添加新事件时 flush_delay 计时器是否重置不。"""
        # 设置模拟对象客户端
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 添加第一个事件
        await subscriber(sample_events[0])
        assert len(subscriber.queue) == 1

        # 等待一半的刷新延迟
        await asyncio.sleep(webhook_spec.flush_delay / 2)

        # 添加第二个事件（应该不重置计时器）
        await subscriber(sample_events[1])
        assert len(subscriber.queue) == 2

        # 再等待一半延迟（从第一个事件开始总时间 = flush_delay）
        await asyncio.sleep(webhook_spec.flush_delay / 2 + 0.05)

        # 由于计时器未重置，应该已发布
        mock_client.request.assert_called_once()
        assert len(subscriber.queue) == 0

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_flush_delay_cancelled_on_buffer_full(
        self,
        mock_client_class,
        mock_event_service,
        webhook_spec,
        sample_events,
        sample_conversation_id,
    ):
        """测试当缓冲区已满时 flush_delay 计时器是否被取消。"""
        # 设置模拟对象客户端
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 添加事件直至缓冲区大小 - 1
        for event in sample_events[:2]:
            await subscriber(event)
        assert len(subscriber.queue) == 2

        # 添加一个事件以填充缓冲区（应触发立即发布）
        await subscriber(sample_events[2])

        # 验证立即发生的事件
        mock_client.request.assert_called_once()
        assert len(subscriber.queue) == 0

        # 等待 flush_delay 以确保计时器已取消
        await asyncio.sleep(webhook_spec.flush_delay + 0.05)

        # 不应该提出额外的要求
        assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_flush_delay_cancelled_on_close(
        self,
        mock_client_class,
        mock_event_service,
        webhook_spec,
        sample_event,
        sample_conversation_id,
    ):
        """测试订阅者关闭时 flush_delay 计时器是否被取消。"""
        # 设置模拟对象客户端
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 添加 1 个事件
        await subscriber(sample_event)
        assert len(subscriber.queue) == 1

        # 在 flush_delay 过去之前关闭订阅者
        await subscriber.close()

        # 验证关闭触发的帖子
        mock_client.request.assert_called_once()
        assert len(subscriber.queue) == 0

        # 等待 flush_delay 以确保计时器已取消
        await asyncio.sleep(webhook_spec.flush_delay + 0.05)

        # 不应该提出额外的要求
        assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_flush_delay_no_post_when_queue_empty(
        self, mock_event_service, webhook_spec, sample_conversation_id
    ):
        """测试当队列为空时 flush_delay 不会触发 post。"""
        WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 等待flush_delay
        await asyncio.sleep(webhook_spec.flush_delay + 0.05)

        # 不应提出任何 HTTP 请求
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.assert_not_called()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_flush_delay_triggers_on_timer(
        self,
        mock_client_class,
        mock_event_service,
        webhook_spec,
        sample_event,
        sample_conversation_id,
    ):
        """测试 flush_delay 计时器是否触发 HTTP 请求。"""
        # 设置模拟对象客户端成功
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 添加 1 个事件
        await subscriber(sample_event)
        assert len(subscriber.queue) == 1

        # 等待flush_delay触发
        await asyncio.sleep(webhook_spec.flush_delay + 0.05)

        # 验证请求已发出并且队列已清除
        mock_client.request.assert_called_once()
        assert len(subscriber.queue) == 0


class TestConversationWebhookSubscriber:
    """测试用例对应 ConversationWebhookSubscriber 类。"""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_post_conversation_info_success(
        self, mock_client_class, webhook_spec, mock_event_service
    ):
        """测试对话信息是否成功发布。"""
        from openhands.agent_server.conversation_service import (
            ConversationWebhookSubscriber,
        )
        from openhands.agent_server.models import ConversationInfo
        from openhands.sdk.conversation.state import ConversationExecutionStatus

        # 设置模拟对象客户端
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = ConversationWebhookSubscriber(
            spec=webhook_spec,
        )

        # 创建示例对话信息
        conversation_info = ConversationInfo(
            id=uuid4(),
            agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
            workspace=mock_event_service.stored.workspace,
            created_at=utc_now(),
            updated_at=utc_now(),
            execution_status=ConversationExecutionStatus.RUNNING,
        )

        await subscriber.post_conversation_info(conversation_info)

        # 验证 HTTP 请求是否正确发出
        mock_client.request.assert_called_once_with(
            method="POST",
            url="https://example.com/conversations",
            json=conversation_info.model_dump(mode="json"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer token",
            },
            timeout=30.0,
        )

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_post_conversation_info_with_session_api_key(
        self, mock_client_class, webhook_spec, mock_event_service
    ):
        """测试使用会话 API 键发布对话信息。"""
        from openhands.agent_server.conversation_service import (
            ConversationWebhookSubscriber,
        )
        from openhands.agent_server.models import ConversationInfo
        from openhands.sdk.conversation.state import ConversationExecutionStatus

        # 设置模拟对象客户端
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        subscriber = ConversationWebhookSubscriber(
            spec=webhook_spec,
            session_api_key="test_session_key",
        )

        # 创建示例对话信息
        conversation_info = ConversationInfo(
            id=uuid4(),
            agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
            workspace=mock_event_service.stored.workspace,
            created_at=utc_now(),
            updated_at=utc_now(),
            execution_status=ConversationExecutionStatus.PAUSED,
        )

        await subscriber.post_conversation_info(conversation_info)

        # 验证会话 API 密钥已添加到标头中
        expected_headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer token",
            "X-Session-API-Key": "test_session_key",
        }
        mock_client.request.assert_called_once_with(
            method="POST",
            url="https://example.com/conversations",
            json=conversation_info.model_dump(mode="json"),
            headers=expected_headers,
            timeout=30.0,
        )

    @pytest.mark.asyncio
    async def test_post_conversation_info_http_error_with_retries(
        self, webhook_spec, mock_event_service
    ):
        """使用对话 Webhook 的重试逻辑测试 HTTP 错误处理。"""
        from openhands.agent_server.conversation_service import (
            ConversationWebhookSubscriber,
        )
        from openhands.agent_server.models import ConversationInfo
        from openhands.sdk.conversation.state import ConversationExecutionStatus

        subscriber = ConversationWebhookSubscriber(
            spec=webhook_spec,
        )

        # 创建示例对话信息
        conversation_info = ConversationInfo(
            id=uuid4(),
            agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
            workspace=mock_event_service.stored.workspace,
            created_at=utc_now(),
            updated_at=utc_now(),
            execution_status=ConversationExecutionStatus.FINISHED,
        )

        # 追踪重试次尝试
        retry_attempts = []
        sleep_calls = []

        # 模拟对象HTTP客户端和睡眠
        async def mock_request(*args, **kwargs):
            retry_attempts.append(len(retry_attempts) + 1)
            if len(retry_attempts) <= 2:  # 前两次尝试失败
                raise httpx.HTTPStatusError(
                    "Server Error", request=MagicMock(), response=MagicMock()
                )
            # 第三次尝试成功 - 返回模拟对象响应
            response = AsyncMock()
            response.raise_for_status.return_value = None
            return response

        async def mock_sleep(delay):
            sleep_calls.append(delay)

        subscriber._sleep = mock_sleep
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = mock_request
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await subscriber.post_conversation_info(conversation_info)

        # 验证已尝试重试
        assert len(retry_attempts) == 3
        # 仅记录此实例的延迟——没有全局睡眠污染。
        assert sleep_calls == [webhook_spec.retry_delay] * 2


class TestWebhookSubscriberTimerBehavior:
    """测试用例用于 WebhookSubscriber 计时器行为。"""

    @pytest.mark.asyncio
    async def test_timer_not_reset_on_subsequent_events(
        self, mock_event_service, webhook_spec, sample_events, sample_conversation_id
    ):
        """测试收到新事件时计时器是否不会重置。"""
        # 对此测试使用更长的刷新延迟
        webhook_spec.flush_delay = 0.2

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 模拟对象 _post_events 跟踪何时被调用
        post_events_calls = []
        original_post_events = subscriber._post_events

        async def mock_post_events():
            post_events_calls.append(len(subscriber.queue))
            await original_post_events()

        subscriber._post_events = mock_post_events

        # 添加第一个事件 - 这应该启动计时器
        await subscriber(sample_events[0])
        assert subscriber._flush_timer is not None
        first_timer = subscriber._flush_timer

        # 不久后添加第二个事件 - 计时器应重置不
        await asyncio.sleep(0.05)  # 延迟小
        await subscriber(sample_events[1])

        # 计时器应该是同一个实例（不重置）
        assert subscriber._flush_timer is first_timer
        assert len(subscriber.queue) == 2

        # 等待计时器触发
        await asyncio.sleep(0.2)

        # 事件应该通过计时器发布
        assert len(post_events_calls) == 1
        assert post_events_calls[0] == 2  # 两项活动均已发布

    @pytest.mark.asyncio
    async def test_timer_only_started_once_until_flush(
        self, mock_event_service, webhook_spec, sample_events, sample_conversation_id
    ):
        """测试计时器仅启动一次，直到事件被刷新。"""
        webhook_spec.flush_delay = 0.2

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 模拟对象 _post_events 阻止实际的 HTTP 呼叫但清除队列
        async def mock_post_events():
            subscriber.queue.clear()

        subscriber._post_events = mock_post_events

        # 添加第一个事件 - 应该启动计时器
        await subscriber(sample_events[0])
        assert subscriber._flush_timer is not None
        first_timer = subscriber._flush_timer

        # 添加更多事件 - 计时器应保持不变
        await subscriber(sample_events[1])
        assert subscriber._flush_timer is first_timer

        # 等待计时器完成并进行清理
        await asyncio.sleep(0.3)

        # 冲洗后应清除计时器
        assert subscriber._flush_timer is None

        # 添加另一个事件 - 应该启动一个新的计时器
        await subscriber(sample_events[2])
        assert subscriber._flush_timer is not None
        assert subscriber._flush_timer is not first_timer  # 新的计时器实例

    @pytest.mark.asyncio
    async def test_timer_cancelled_when_buffer_full(
        self, mock_event_service, webhook_spec, sample_events, sample_conversation_id
    ):
        """测试当缓冲区已满时计时器是否被取消。"""
        webhook_spec.flush_delay = 1.0  # 长时间延迟
        webhook_spec.event_buffer_size = 2  # 缓冲区小

        subscriber = WebhookSubscriber(
            conversation_id=sample_conversation_id,
            service=mock_event_service,
            spec=webhook_spec,
        )

        # 模拟对象 _post_events 阻止实际的 HTTP 调用
        subscriber._post_events = AsyncMock()

        # 添加第一个事件 - 应该启动计时器
        await subscriber(sample_events[0])
        assert subscriber._flush_timer is not None
        timer = subscriber._flush_timer

        # 添加第二个事件以填充缓冲区 - 应取消计时器并立即发布
        await subscriber(sample_events[1])

        # 稍微延迟一下取消完成
        await asyncio.sleep(0.01)

        # 计时器应该被取消
        assert subscriber._flush_timer is None
        assert timer.cancelled()

        # _post_events 应该立即被调用
        subscriber._post_events.assert_called_once()


@pytest.mark.timeout(30)
async def test_webhook_subscribe_errors_surface(tmp_path, monkeypatch):
    persist = tmp_path / "persist"
    persist.mkdir()
    workspace = str(tmp_path / "ws")
    (tmp_path / "ws").mkdir()

    # 强制 WebhookSubscriber 的第一个 __call__ 加注一次。 后续调用成功，因此测试模型为“
    # 初始化错误”而不是“引发每个事件”。 event_service.py:412 在注册期间调用 __call__ 作
    # 为初始状态同步 — 这就是加注的地方。
    #
    original_init = WebhookSubscriber.__init__

    def _broken_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._broken = True

    async def _broken_call(self, event):
        if getattr(self, "_broken", False):
            self._broken = False
            raise RuntimeError("webhook subscriber init failed")

    monkeypatch.setattr(WebhookSubscriber, "__init__", _broken_init)
    monkeypatch.setattr(WebhookSubscriber, "__call__", _broken_call)

    service = ConversationService(
        conversations_dir=persist,
        webhook_specs=[
            WebhookSpec(
                base_url="http://unused.test",
                event_buffer_size=1,
                num_retries=0,
            )
        ],
    )
    async with service:
        # 合约：订阅者的初始化错误到达调用者。 今天两个
        # 存在吞咽位点，因此此 `pytest.raises` 将看不到任何内容，并且测试失败 (→ XFAIL)
        # 。 当 * 和 * 都固定时，start_conversation 传播 RuntimeError，pytest.raises 捕
        # 获它，测试通过（→ XPASS，strict=True 标记它进行清理）。
        #
        with pytest.raises(RuntimeError, match="webhook subscriber init failed"):
            await start_conversation_with_test_llm(
                service,
                parent_llm=SlowTestLLM.from_messages(
                    [text_message("done")], latency_s=0.0
                ),
                workspace_dir=workspace,
                usage_id="webhook-error",
                initial_text=None,
            )


@pytest.mark.asyncio
async def test_streaming_deltas_never_reach_webhook(
    mock_event_service, webhook_spec, sample_conversation_id
):
    """StreamingDeltaEvent 未排队，POSTed 未排队（回归对于 #4672）。"""
    subscriber = WebhookSubscriber(
        conversation_id=sample_conversation_id,
        service=mock_event_service,
        spec=webhook_spec,
    )
    pub_sub: PubSub[Event] = PubSub()
    pub_sub.subscribe(subscriber)

    with patch.object(subscriber, "_post_events", new_callable=AsyncMock) as post:
        # Past event_buffer_size：未过滤的队列将刷新到此处。
        for _ in range(webhook_spec.event_buffer_size + 2):
            await pub_sub(StreamingDeltaEvent(content="tok"))

        assert subscriber.queue == []
        post.assert_not_called()

    subscriber._cancel_flush_timer()
