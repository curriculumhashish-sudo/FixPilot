"""GraySwanAnalyzer 类的测试。"""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from openhands.sdk.event import ActionEvent, MessageEvent, SystemPromptEvent
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.security.grayswan import GraySwanAnalyzer
from openhands.sdk.security.risk import SecurityRisk
from openhands.sdk.tool import Action


class GraySwanTestAction(Action):
    """模拟对象用于 GraySwan 分析仪测试的操作。"""

    command: str = "test_command"


def create_mock_action_event(
    tool_name: str = "test_tool",
    command: str = "test",
    security_risk: SecurityRisk = SecurityRisk.UNKNOWN,
) -> ActionEvent:
    """帮助程序创建 ActionEvent 用于测试。"""
    return ActionEvent(
        thought=[TextContent(text="test thought")],
        action=GraySwanTestAction(command=command),
        tool_name=tool_name,
        tool_call_id="test_call_id",
        tool_call=MessageToolCall(
            id="test_call_id",
            name=tool_name,
            arguments=json.dumps({"command": command}),
            origin="completion",
        ),
        llm_response_id="test_response_id",
        security_risk=security_risk,
    )


def create_mock_message_event(
    content: str = "test message",
    source: str = "user",
) -> MessageEvent:
    """帮助程序创建 MessageEvent 用于测试。"""
    return MessageEvent(
        source=source,  # type: ignore
        llm_message=Message(
            role="user" if source == "user" else "assistant",
            content=[TextContent(text=content)],
        ),
    )


def create_mock_system_prompt_event(
    prompt: str = "You are a helpful assistant.",
) -> SystemPromptEvent:
    """帮助程序创建 SystemPromptEvent 用于测试。"""
    return SystemPromptEvent(
        system_prompt=TextContent(text=prompt),
        tools=[],
    )


class TestGraySwanAnalyzerInit:
    """测试 GraySwanAnalyzer 初始化。"""

    def test_init_without_api_key_logs_warning(self, caplog: pytest.LogCaptureFixture):
        """测试没有 API 键的初始化是否会记录警告。"""
        with patch.dict("os.environ", {}, clear=True):
            analyzer = GraySwanAnalyzer()
            assert analyzer.api_key is None
            assert "GRAYSWAN_API_KEY not set" in caplog.text

    def test_init_with_api_key_from_env(self):
        """测试是否从环境中读取 API 键。"""
        with patch.dict("os.environ", {"GRAYSWAN_API_KEY": "test_key"}):
            analyzer = GraySwanAnalyzer()
            assert analyzer.api_key is not None
            assert analyzer.api_key.get_secret_value() == "test_key"

    def test_init_with_api_key_param(self):
        """测试 API 键是否可以作为参数传递。"""
        analyzer = GraySwanAnalyzer(api_key=SecretStr("param_key"))
        assert analyzer.api_key is not None
        assert analyzer.api_key.get_secret_value() == "param_key"

    def test_init_with_default_policy_id(self, caplog: pytest.LogCaptureFixture):
        """测试在未提供时是否使用默认策略 ID。"""
        with patch.dict("os.environ", {"GRAYSWAN_API_KEY": "test_key"}, clear=True):
            analyzer = GraySwanAnalyzer()
            assert analyzer.policy_id == "689ca4885af3538a39b2ba04"
            assert "Using default GraySwan policy ID" in caplog.text

    def test_init_with_policy_id_from_env(self, caplog: pytest.LogCaptureFixture):
        """测试是否从环境中读取策略 ID。"""
        with patch.dict(
            "os.environ",
            {"GRAYSWAN_API_KEY": "test_key", "GRAYSWAN_POLICY_ID": "custom_policy"},
        ):
            analyzer = GraySwanAnalyzer()
            assert analyzer.policy_id == "custom_policy"
            assert "Using GraySwan policy ID from environment" in caplog.text

    def test_init_with_custom_thresholds(self):
        """测试是否可以设置自定义阈值。"""
        analyzer = GraySwanAnalyzer(
            api_key=SecretStr("test_key"),
            low_threshold=0.2,
            medium_threshold=0.5,
        )
        assert analyzer.low_threshold == 0.2
        assert analyzer.medium_threshold == 0.5

    def test_init_with_invalid_threshold_order_raises_error(self):
        """测试无效阈值排序是否会升高 ValueError。"""
        with pytest.raises(
            ValueError, match="low_threshold.*must be less than.*medium_threshold"
        ):
            GraySwanAnalyzer(
                api_key=SecretStr("test_key"),
                low_threshold=0.7,
                medium_threshold=0.3,
            )

    def test_init_with_equal_thresholds_raises_error(self):
        """测试是否提高相同的阈值 ValueError。"""
        with pytest.raises(
            ValueError, match="low_threshold.*must be less than.*medium_threshold"
        ):
            GraySwanAnalyzer(
                api_key=SecretStr("test_key"),
                low_threshold=0.5,
                medium_threshold=0.5,
            )


class TestGraySwanAnalyzerViolationMapping:
    """测试违规分数到风险映射。"""

    @pytest.fixture
    def analyzer(self) -> GraySwanAnalyzer:
        """使用 test API 键创建分析器。"""
        return GraySwanAnalyzer(api_key=SecretStr("test_key"))

    def test_map_low_violation(self, analyzer: GraySwanAnalyzer):
        """测试低违规分数是否映射到 LOW 风险。"""
        assert analyzer._map_violation_to_risk(0.0) == SecurityRisk.LOW
        assert analyzer._map_violation_to_risk(0.1) == SecurityRisk.LOW
        assert analyzer._map_violation_to_risk(0.3) == SecurityRisk.LOW

    def test_map_medium_violation(self, analyzer: GraySwanAnalyzer):
        """测试中等违规分数是否映射到 MEDIUM 风险。"""
        assert analyzer._map_violation_to_risk(0.31) == SecurityRisk.MEDIUM
        assert analyzer._map_violation_to_risk(0.5) == SecurityRisk.MEDIUM
        assert analyzer._map_violation_to_risk(0.7) == SecurityRisk.MEDIUM

    def test_map_high_violation(self, analyzer: GraySwanAnalyzer):
        """测试高违规分数是否映射到 HIGH 风险。"""
        assert analyzer._map_violation_to_risk(0.71) == SecurityRisk.HIGH
        assert analyzer._map_violation_to_risk(0.9) == SecurityRisk.HIGH
        assert analyzer._map_violation_to_risk(1.0) == SecurityRisk.HIGH

    def test_map_boundary_low_threshold(self, analyzer: GraySwanAnalyzer):
        """在低阈值下测试精确边界。"""
        assert analyzer._map_violation_to_risk(0.3) == SecurityRisk.LOW
        assert analyzer._map_violation_to_risk(0.30001) == SecurityRisk.MEDIUM

    def test_map_boundary_medium_threshold(self, analyzer: GraySwanAnalyzer):
        """在中等阈值处测试精确边界。"""
        assert analyzer._map_violation_to_risk(0.7) == SecurityRisk.MEDIUM
        assert analyzer._map_violation_to_risk(0.70001) == SecurityRisk.HIGH


class TestGraySwanAnalyzerAPICall:
    """测试 GraySwan API 调用。"""

    @pytest.fixture
    def analyzer(self) -> GraySwanAnalyzer:
        """使用 test API 键创建分析器。"""
        return GraySwanAnalyzer(api_key=SecretStr("test_key"))

    def test_api_call_success_low_risk(self, analyzer: GraySwanAnalyzer):
        """测试成功 API 调用，违规分数较低。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"violation": 0.1}

        with patch.object(analyzer, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = analyzer._call_grayswan_api([{"role": "user", "content": "test"}])

            assert result == SecurityRisk.LOW
            mock_client.post.assert_called_once()

    def test_api_call_success_high_risk(self, analyzer: GraySwanAnalyzer):
        """测试成功 API 调用，违规分数较高。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"violation": 0.9}

        with patch.object(analyzer, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = analyzer._call_grayswan_api([{"role": "user", "content": "test"}])

            assert result == SecurityRisk.HIGH

    def test_api_call_ipi_detection_escalates_to_high(self, analyzer: GraySwanAnalyzer):
        """测试间接提示词注入检测是否升级至 HIGH 风险。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"violation": 0.1, "ipi": True}

        with patch.object(analyzer, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = analyzer._call_grayswan_api([{"role": "user", "content": "test"}])

            assert result == SecurityRisk.HIGH

    def test_api_call_error_returns_unknown(self, analyzer: GraySwanAnalyzer):
        """测试 API 个错误返回 UNKNOWN 个风险。"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch.object(analyzer, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = analyzer._call_grayswan_api([{"role": "user", "content": "test"}])

            assert result == SecurityRisk.UNKNOWN

    def test_api_call_timeout_returns_unknown(self, analyzer: GraySwanAnalyzer):
        """测试 API 超时返回 UNKNOWN 风险。"""
        with patch.object(analyzer, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.TimeoutException("Timeout")
            mock_get_client.return_value = mock_client

            result = analyzer._call_grayswan_api([{"role": "user", "content": "test"}])

            assert result == SecurityRisk.UNKNOWN

    def test_api_call_without_api_key_returns_unknown(self):
        """测试没有 API 键的 API 调用会返回 UNKNOWN 风险。"""
        analyzer = GraySwanAnalyzer(api_key=None)
        result = analyzer._call_grayswan_api([{"role": "user", "content": "test"}])
        assert result == SecurityRisk.UNKNOWN

    def test_api_call_missing_violation_field_returns_unknown(
        self, analyzer: GraySwanAnalyzer
    ):
        """测试响应中缺少违规字段会返回 UNKNOWN 风险。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"some_other_field": "value"}

        with patch.object(analyzer, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = analyzer._call_grayswan_api([{"role": "user", "content": "test"}])

            assert result == SecurityRisk.UNKNOWN


class TestGraySwanAnalyzerSecurityRisk:
    """测试 security_risk 方法。"""

    @pytest.fixture
    def analyzer(self) -> GraySwanAnalyzer:
        """使用 test API 键创建分析器。"""
        return GraySwanAnalyzer(api_key=SecretStr("test_key"))

    def test_security_risk_without_api_key(self):
        """测试 security_risk 在没有 API 键的情况下返回 UNKNOWN。"""
        analyzer = GraySwanAnalyzer(api_key=None)
        action = create_mock_action_event()
        result = analyzer.security_risk(action)
        assert result == SecurityRisk.UNKNOWN

    def test_security_risk_with_events(self, analyzer: GraySwanAnalyzer):
        """使用对话历史记录测试 security_risk。"""
        # 设置事件
        events = [
            create_mock_system_prompt_event(),
            create_mock_message_event("Hello", "user"),
        ]
        analyzer.set_events(events)

        action = create_mock_action_event()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"violation": 0.5}

        with patch.object(analyzer, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = analyzer.security_risk(action)

            assert result == SecurityRisk.MEDIUM
            # 验证 API 是通过消息调用的
            call_args = mock_client.post.call_args
            assert call_args is not None
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert "messages" in payload
            assert len(payload["messages"]) > 0

    def test_security_risk_respects_history_limit(self, analyzer: GraySwanAnalyzer):
        """测试 security_risk 是否尊重 history_limit。"""
        analyzer.history_limit = 2

        # 创建超过限制的事件
        events = [create_mock_message_event(f"Message {i}", "user") for i in range(5)]
        analyzer.set_events(events)

        action = create_mock_action_event()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"violation": 0.1}

        with patch.object(analyzer, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            analyzer.security_risk(action)

            # 验证 API 被调用
            call_args = mock_client.post.call_args
            assert call_args is not None
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            # 2次历史事件 + 1次操作 = 3，再加上一个前置合成系统消息，以确保请求以系统角
            # 色开始（窗口没有SystemPromptEvent重新包含）。
            #
            assert len(payload["messages"]) == 4
            assert payload["messages"][0]["role"] == "system"

    def test_security_risk_preserves_leading_system_prompt_when_window_drops_it(
        self, analyzer: GraySwanAnalyzer
    ):
        """当有界窗口时，前导 SystemPromptEvent 被重新包含
        否则将把它切掉，保持请求系统优先。"""
        analyzer.history_limit = 2

        events = [
            create_mock_system_prompt_event("You are a safe assistant."),
            *[create_mock_message_event(f"Message {i}", "user") for i in range(5)],
        ]
        analyzer.set_events(events)

        action = create_mock_action_event()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"violation": 0.1}

        with patch.object(analyzer, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            analyzer.security_risk(action)

            call_args = mock_client.post.call_args
            assert call_args is not None
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            messages = payload["messages"]
            # 第一条消息必须是真实系统提示词，而不是占位符。
            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == "You are a safe assistant."
            # 引导系统提示词+2个事件窗口+1个动作=4条消息。
            assert len(messages) == 4


class TestGraySwanAnalyzerSetEvents:
    """测试 set_events 方法。"""

    def test_set_events(self):
        """测试 set_events 是否存储事件。"""
        analyzer = GraySwanAnalyzer(api_key=SecretStr("test_key"))
        events = [
            create_mock_message_event("Hello", "user"),
            create_mock_message_event("Hi there", "agent"),
        ]
        analyzer.set_events(events)
        assert analyzer._events == events


class TestGraySwanAnalyzerClose:
    """测试 close 方法。"""

    def test_close_cleans_up_client(self):
        """测试关闭是否清理 HTTP 客户端。"""
        analyzer = GraySwanAnalyzer(api_key=SecretStr("test_key"))

        # 创建模拟对象客户端
        mock_client = MagicMock()
        mock_client.is_closed = False
        analyzer._client = mock_client

        analyzer.close()

        mock_client.close.assert_called_once()
        assert analyzer._client is None

    def test_close_handles_no_client(self):
        """测试当不存在客户端时 close 是否处理情况。"""
        analyzer = GraySwanAnalyzer(api_key=SecretStr("test_key"))
        # 不应该提高
        analyzer.close()


class TestGraySwanAnalyzerHTTPClientLifecycle:
    """集成测试用于使用 MockTransport 的 HTTP 客户端生命周期。"""

    def test_client_creation_and_reuse(self):
        """测试 HTTP 客户端是否已正确创建和重用。"""

        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"violation": 0.1})

        transport = httpx.MockTransport(mock_handler)
        analyzer = GraySwanAnalyzer(api_key=SecretStr("test_key"))

        # 使用模拟对象传输层手动设置客户端
        analyzer._client = httpx.Client(transport=transport)

        action = create_mock_action_event()

        try:
            # 第一次通话应该有效
            result = analyzer.security_risk(action)
            assert result == SecurityRisk.LOW

            # 第二次调用应重用同一客户端
            result = analyzer.security_risk(action)
            assert result == SecurityRisk.LOW
        finally:
            analyzer.close()

    def test_client_recreated_after_close(self):
        """测试调用 close() 后是否重新创建客户端。"""
        call_count = 0

        def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={"violation": 0.1})

        analyzer = GraySwanAnalyzer(api_key=SecretStr("test_key"))

        # 使用模拟对象传输层创建初始客户端
        transport = httpx.MockTransport(mock_handler)
        analyzer._client = httpx.Client(transport=transport)

        action = create_mock_action_event()

        try:
            # 第一次通话
            result = analyzer.security_risk(action)
            assert result == SecurityRisk.LOW
            assert call_count == 1

            # 关闭客户端
            analyzer.close()
            assert analyzer._client is None

            # 下一次调用应该创建一个新客户端（但我们需要再次模拟对象）由于 _get_client
            # 创建了一个真实的客户端，我们为此测试修补它
            #
            with patch.object(analyzer, "_create_client") as mock_create:
                new_transport = httpx.MockTransport(mock_handler)
                mock_create.return_value = httpx.Client(transport=new_transport)

                result = analyzer.security_risk(action)
                assert result == SecurityRisk.LOW
                mock_create.assert_called_once()
        finally:
            analyzer.close()

    def test_client_handles_json_decode_error(self):
        """测试无效的 JSON 响应是否得到妥善处理。"""

        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not valid json")

        transport = httpx.MockTransport(mock_handler)
        analyzer = GraySwanAnalyzer(api_key=SecretStr("test_key"))
        analyzer._client = httpx.Client(transport=transport)

        action = create_mock_action_event()
        try:
            result = analyzer.security_risk(action)
            assert result == SecurityRisk.UNKNOWN
        finally:
            analyzer.close()
