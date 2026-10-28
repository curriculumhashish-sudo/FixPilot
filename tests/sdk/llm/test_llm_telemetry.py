import json
import os
import tempfile
import time
import warnings
from unittest.mock import MagicMock, patch

import pytest
from litellm.types.llms.openai import (
    InputTokensDetails,
    OutputTokensDetails,
    ResponseAPIUsage,
    ResponsesAPIResponse,
)
from litellm.types.utils import ModelResponse, Usage
from pydantic import BaseModel, Field, ValidationError

from openhands.sdk.llm.utils.metrics import Metrics
from openhands.sdk.llm.utils.telemetry import (
    Telemetry,
    UsageSnapshot,
    _safe_json,
    normalize_usage,
)


def _snapshot(usage: Usage) -> UsageSnapshot:
    """在记录之前按照遥测的方式规范提供程序的使用情况。"""
    snapshot = normalize_usage(usage)
    assert snapshot is not None
    return snapshot


@pytest.fixture
def mock_metrics():
    """创建一个模拟对象 Metrics 实例。"""
    return Metrics()


@pytest.fixture
def basic_telemetry(mock_metrics):
    """创建一个基本的遥测实例以进行测试。"""
    return Telemetry(model_name="gpt-4o", log_enabled=False, metrics=mock_metrics)


@pytest.fixture
def mock_response():
    """创建模拟对象 ModelResponse 进行测试。"""
    return ModelResponse(
        id="test-response-id",
        choices=[],
        created=1234567890,
        model="gpt-4o",
        object="chat.completion",
        usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
    )


class TestTelemetryInitialization:
    """测试遥测类的初始化和配置。"""

    def test_telemetry_default_initialization(self, mock_metrics):
        """测试测迹初始化，使用默认值。"""
        telemetry = Telemetry(metrics=mock_metrics)

        assert telemetry.model_name == "unknown"
        assert telemetry.log_enabled is False
        assert telemetry.log_dir is None
        assert telemetry.input_cost_per_token is None
        assert telemetry.output_cost_per_token is None
        assert telemetry.metrics == mock_metrics

    def test_telemetry_custom_initialization(self, mock_metrics):
        """使用自定义值测试遥测初始化。"""
        telemetry = Telemetry(
            model_name="custom-model",
            log_enabled=True,
            log_dir="/tmp/logs",
            input_cost_per_token=0.001,
            output_cost_per_token=0.002,
            metrics=mock_metrics,
        )

        assert telemetry.model_name == "custom-model"
        assert telemetry.log_enabled is True
        assert telemetry.log_dir == "/tmp/logs"
        assert telemetry.input_cost_per_token == 0.001
        assert telemetry.output_cost_per_token == 0.002
        assert telemetry.metrics == mock_metrics

    def test_telemetry_validation_error(self):
        """测试当指标缺失时遥测是否会引发 ValidationError。"""
        with pytest.raises(ValidationError):
            Telemetry()  # type: ignore

    def test_telemetry_private_attributes(self, basic_telemetry):
        """测试私有属性是否正确初始化。"""
        # 私有属性应该可以访问，但不能访问已序列化
        assert hasattr(basic_telemetry, "_req_start")
        assert hasattr(basic_telemetry, "_req_ctx")
        assert hasattr(basic_telemetry, "_last_latency")

        # 检查默认值
        assert basic_telemetry._req_start == 0.0
        assert basic_telemetry._req_ctx == {}
        assert basic_telemetry._last_latency == 0.0


class TestTelemetryLifecycle:
    """测试遥测生命周期方法。"""

    def test_on_request_basic(self, basic_telemetry):
        """测试on_request方法的基本功能。"""
        start_time = time.time()
        basic_telemetry.on_request(None)

        # 应设置请求开始时间
        assert basic_telemetry._req_start >= start_time
        assert basic_telemetry._req_ctx == {}

    def test_on_request_with_context(self, basic_telemetry):
        """使用遥测上下文测试 on_request 方法。"""
        telemetry_ctx = {"context_window": 4096, "user_id": "test-user"}
        basic_telemetry.on_request(telemetry_ctx)

        assert basic_telemetry._req_ctx == telemetry_ctx

    def test_on_error_noop_when_logging_disabled(self, basic_telemetry):
        """禁用日志记录时测试 on_error 方法。"""
        # 不应引发任何异常
        basic_telemetry.on_request({"context_window": 4096})
        basic_telemetry.on_error(Exception("test error"))

    @patch("time.time")
    def test_on_response_latency_tracking(
        self, mock_time, basic_telemetry, mock_response
    ):
        """测试 on_response 是否正确跟踪延迟。"""
        # 设置时间顺序
        mock_time.side_effect = [1000.0, 1002.5]  # 2.5 秒延迟

        basic_telemetry.on_request(None)
        metrics = basic_telemetry.on_response(mock_response)

        assert basic_telemetry._last_latency == 2.5
        assert isinstance(metrics.accumulated_cost, float)

    def test_on_response_with_usage(self, basic_telemetry):
        """使用使用信息测试 on_response。"""
        basic_telemetry.on_request({"context_window": 4096})

        # 使用使用数据创建 ModelResponse
        response = ModelResponse(
            id="test-response-id",
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )

        basic_telemetry.on_response(response)

        # 应记录词元用量
        assert len(basic_telemetry.metrics.token_usages) == 1
        token_usage = basic_telemetry.metrics.token_usages[0]
        assert token_usage.prompt_tokens == 100
        assert token_usage.completion_tokens == 50


class TestTelemetryTokenUsage:
    """测试词元用量录音功能。"""

    def test_record_usage_basic(self, basic_telemetry):
        """测试基本词元用量录音。"""
        usage = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        basic_telemetry._record_usage(_snapshot(usage), "test-id", 4096)

        assert len(basic_telemetry.metrics.token_usages) == 1
        token_usage = basic_telemetry.metrics.token_usages[0]
        assert token_usage.prompt_tokens == 100
        assert token_usage.completion_tokens == 50
        assert token_usage.cache_read_tokens == 0
        assert token_usage.cache_write_tokens == 0
        assert token_usage.context_window == 4096
        assert token_usage.response_id == "test-id"

    def test_record_usage_with_cache_read(self, basic_telemetry):
        """使用缓存读取 token 测试词元用量记录。"""
        # 使用 prompt_tokens_details 创建模拟对象用法
        usage = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        # 模拟对象 prompt_tokens_details 属性
        mock_details = MagicMock()
        mock_details.cached_tokens = 25
        usage.prompt_tokens_details = mock_details

        basic_telemetry._record_usage(_snapshot(usage), "test-id", 4096)

        token_usage = basic_telemetry.metrics.token_usages[0]
        assert token_usage.cache_read_tokens == 25

    def test_record_usage_with_cache_write(self, basic_telemetry):
        """使用缓存写入 token 测试词元用量记录。"""
        from litellm import Usage

        usage = Usage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            cache_creation_input_tokens=30,
        )

        basic_telemetry._record_usage(_snapshot(usage), "test-id", 4096)

        token_usage = basic_telemetry.metrics.token_usages[0]
        assert token_usage.cache_write_tokens == 30

    def test_record_usage_missing_tokens(self, basic_telemetry):
        """测试词元用量记录，但缺少 token 计数。"""
        usage = Usage()  # 空用

        basic_telemetry._record_usage(_snapshot(usage), "test-id", 4096)

        token_usage = basic_telemetry.metrics.token_usages[0]
        assert token_usage.prompt_tokens == 0
        assert token_usage.completion_tokens == 0

    def test_record_usage_with_none_context_window(self, basic_telemetry):
        """使用 None context_window 测试词元用量录音。

        此测试问题 #905，其中未映射的模型有
        max_input_tokens=None. The fix ensures that None values
        通过在到达遥测之前将它们转换为 0 来处理。
        """
        usage = Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30)

        # 模拟 context_window 为 None（未映射的模型）的情况。这应在验证级别引发错误。修
        # 复措施在调用 _record_usage 之前应用在 LLM 级别
        #
        with pytest.raises(ValidationError, match="Input should be a valid integer"):
            basic_telemetry._record_usage(  # type: ignore[arg-type]
                _snapshot(usage), "test-id", None
            )


class TestUsageNormalization:
    """两个提供者使用塑造的类型化边界都通过。"""

    def test_chat_completions_shape_is_normalized(self):
        snapshot = normalize_usage(
            Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        )

        assert snapshot == UsageSnapshot(prompt_tokens=100, completion_tokens=50)

    def test_responses_api_shape_is_normalized(self):
        snapshot = normalize_usage(
            ResponseAPIUsage(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                input_tokens_details=InputTokensDetails(cached_tokens=25),
                output_tokens_details=OutputTokensDetails(reasoning_tokens=7),
            )
        )

        assert snapshot == UsageSnapshot(
            prompt_tokens=100,
            completion_tokens=50,
            reasoning_tokens=7,
            cache_read_tokens=25,
            cache_write_tokens=0,
        )

    def test_absent_usage_normalizes_to_none(self):
        assert normalize_usage(None) is None

    def test_on_response_records_responses_api_usage(self, basic_telemetry):
        """响应 API 响应通过相同的边界达到指标。"""
        response = ResponsesAPIResponse(
            id="responses-id",
            status="completed",
            created_at=1234567890,
            output=[],
            usage=ResponseAPIUsage(
                input_tokens=30,
                output_tokens=9,
                total_tokens=39,
                input_tokens_details=InputTokensDetails(cached_tokens=4),
                output_tokens_details=OutputTokensDetails(reasoning_tokens=3),
            ),
        )
        basic_telemetry.on_request({"context_window": 8192})

        basic_telemetry.on_response(response)

        assert len(basic_telemetry.metrics.token_usages) == 1
        token_usage = basic_telemetry.metrics.token_usages[0]
        assert token_usage.prompt_tokens == 30
        assert token_usage.completion_tokens == 9
        assert token_usage.reasoning_tokens == 3
        assert token_usage.cache_read_tokens == 4
        assert token_usage.cache_write_tokens == 0

    def test_log_usage_summary_comes_from_the_same_snapshot(self, mock_metrics):
        """记录的使用情况摘要和指标不能不一致。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            telemetry = Telemetry(
                model_name="gpt-4o",
                log_enabled=True,
                log_dir=temp_dir,
                metrics=mock_metrics,
            )
            response = ModelResponse(
                id="log-id",
                usage=Usage(
                    prompt_tokens=11,
                    completion_tokens=5,
                    total_tokens=16,
                    completion_tokens_details={"reasoning_tokens": 2},
                ),
            )
            telemetry.on_request({"context_window": 4096})

            telemetry.on_response(response)

            [filename] = os.listdir(temp_dir)
            with open(os.path.join(temp_dir, filename)) as f:
                data = json.loads(f.read())

        assert data["usage_summary"] == {
            "prompt_tokens": 11,
            "completion_tokens": 5,
            "reasoning_tokens": 2,
            "cache_read_tokens": 0,
        }


class TestTelemetryCostCalculation:
    """测试成本计算功能。"""

    def test_compute_cost_with_custom_rates(self, mock_metrics):
        """使用自定义输入/输出率测试成本计算。"""
        telemetry = Telemetry(
            model_name="gpt-4o",
            input_cost_per_token=0.001,
            output_cost_per_token=0.002,
            metrics=mock_metrics,
        )

        mock_response = ModelResponse(
            id="test-id",
            choices=[],
            created=1234567890,
            model="gpt-4o",
            object="chat.completion",
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )

        with patch(
            "openhands.sdk.llm.utils.telemetry.litellm_completion_cost"
        ) as mock_cost:
            mock_cost.return_value = 0.25
            telemetry._compute_cost(mock_response)

            # 应按 token 的自定义成本调用 LiteLLM
            mock_cost.assert_called_once()
            call_kwargs = mock_cost.call_args[1]
            assert "custom_cost_per_token" in call_kwargs
            # CostPerToken 是 TypedDict，因此检查它是否具有预期的键
            cost_per_token = call_kwargs["custom_cost_per_token"]
            assert "input_cost_per_token" in cost_per_token
            assert "output_cost_per_token" in cost_per_token

    def test_compute_cost_from_headers(self, basic_telemetry):
        """测试从响应标头中提取成本。"""
        mock_response = MagicMock()
        mock_response._hidden_params = {
            "additional_headers": {"llm_provider-x-litellm-response-cost": "0.15"}
        }

        cost = basic_telemetry._compute_cost(mock_response)
        assert cost == 0.15

    def test_compute_cost_litellm_fallback(self, basic_telemetry):
        """测试回退方案到 LiteLLM 成本计算器。"""
        mock_response = ModelResponse(
            id="test-id",
            choices=[],
            created=1234567890,
            model="gpt-4o",
            object="chat.completion",
        )

        with patch(
            "openhands.sdk.llm.utils.telemetry.litellm_completion_cost"
        ) as mock_cost:
            mock_cost.return_value = 0.30
            cost = basic_telemetry._compute_cost(mock_response)

            assert cost == 0.30
            mock_cost.assert_called_once()

    def test_compute_cost_failure_handling(self, basic_telemetry):
        """测试成本计算失败处理。"""
        mock_response = ModelResponse(
            id="test-id",
            choices=[],
            created=1234567890,
            model="gpt-4o",
            object="chat.completion",
        )

        with patch(
            "openhands.sdk.llm.utils.telemetry.litellm_completion_cost"
        ) as mock_cost:
            mock_cost.side_effect = Exception("Cost calculation failed")

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                cost = basic_telemetry._compute_cost(mock_response)

                assert cost is None
                assert len(w) == 1
                assert "Cost calculation failed" in str(w[0].message)

    def test_compute_cost_model_name_processing(self, mock_metrics):
        """测试解析的提供商/模型信息是否发送到 LiteLLM 成本计算。"""
        telemetry = Telemetry(model_name="gpt-4o-mini", metrics=mock_metrics)

        mock_response = ModelResponse(
            id="test-id",
            choices=[],
            created=1234567890,
            model="gpt-4o-mini",
            object="chat.completion",
        )

        with patch(
            "openhands.sdk.llm.utils.telemetry.litellm_completion_cost"
        ) as mock_cost:
            mock_cost.return_value = 0.10
            telemetry._compute_cost(mock_response)

            # 应该发送 LiteLLM 的解析提供者/模型对
            call_kwargs = mock_cost.call_args[1]
            assert call_kwargs["model"] == "gpt-4o-mini"
            assert call_kwargs["custom_llm_provider"] == "openai"

    def test_compute_cost_passes_provider_to_litellm_cost_calculator(
        self, mock_metrics
    ):
        telemetry = Telemetry(
            model_name="vertex_ai/claude-sonnet-4-5@20250929",
            metrics=mock_metrics,
        )

        resp = ModelResponse(
            id="test-id",
            choices=[],
            created=1234567890,
            model="claude-sonnet-4-5@20250929",
            object="chat.completion",
        )

        with patch(
            "openhands.sdk.llm.utils.telemetry.litellm_completion_cost"
        ) as mock_cost:
            mock_cost.return_value = 0.10
            telemetry._compute_cost(resp)

            mock_cost.assert_called_once()
            kwargs = mock_cost.call_args.kwargs
            assert kwargs["model"] == "claude-sonnet-4-5@20250929"
            assert kwargs["custom_llm_provider"] == "vertex_ai"

    def test_compute_cost_passes_provider_to_litellm_cost_calculator_azure(
        self, mock_metrics
    ):
        telemetry = Telemetry(
            model_name="azure/responses/gpt-5.2-chat",
            metrics=mock_metrics,
        )

        resp = ModelResponse(
            id="test-id",
            choices=[],
            created=1234567890,
            model="gpt-5.2-chat",
            object="chat.completion",
        )

        with patch(
            "openhands.sdk.llm.utils.telemetry.litellm_completion_cost"
        ) as mock_cost:
            mock_cost.return_value = 0.05
            telemetry._compute_cost(resp)

            mock_cost.assert_called_once()
            kwargs = mock_cost.call_args.kwargs
            assert kwargs["model"] == "responses/gpt-5.2-chat"
            assert kwargs["custom_llm_provider"] == "azure"


class TestTelemetryLogging:
    """测试遥测记录功能。"""

    def test_log_completion_disabled(self, basic_telemetry, mock_response):
        """测试禁用时是否会跳过日志记录。"""
        basic_telemetry.on_request({"test": "context"})

        # 当 log_enabled 为 False 时不应创建任何文件
        with tempfile.TemporaryDirectory() as temp_dir:
            basic_telemetry.log_dir = temp_dir
            # 直接使用on_response代替_log_completion测试全流程
            basic_telemetry.on_response(mock_response)

            # 由于禁用日志记录，不应创建任何文件
            assert len(os.listdir(temp_dir)) == 0

    def test_log_completion_no_directory(self, mock_metrics, mock_response):
        """未设置日志目录时测试日志记录。"""
        telemetry = Telemetry(
            model_name="gpt-4o", log_enabled=True, log_dir=None, metrics=mock_metrics
        )

        # 应该尽早返回而不会出现错误
        telemetry.log_llm_call(mock_response, 0.25)

    def test_log_completion_success(self, mock_metrics, mock_response):
        """测试成功完成日志记录。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            telemetry = Telemetry(
                model_name="gpt-4o",
                log_enabled=True,
                log_dir=temp_dir,
                metrics=mock_metrics,
            )

            # 设置上下文和延迟
            telemetry.on_request({"user_id": "test-user", "context_window": 4096})
            telemetry._last_latency = 1.5

            telemetry.log_llm_call(mock_response, 0.25)

            # 应该创建一个日志文件
            files = os.listdir(temp_dir)
            assert len(files) == 1

            # 检查文件内容
            with open(os.path.join(temp_dir, files[0])) as f:
                data = json.loads(f.read())

            assert data["user_id"] == "test-user"
            assert data["context_window"] == 4096
            assert data["cost"] == 0.25
            assert data["latency_sec"] == 1.5
            assert "response" in data
            assert "timestamp" in data

    def test_log_error_success(self, mock_metrics):
        """测试启用日志记录时是否记录失败的请求。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            telemetry = Telemetry(
                model_name="gpt-4o",
                log_enabled=True,
                log_dir=temp_dir,
                metrics=mock_metrics,
            )

            telemetry.on_request(
                {
                    "llm_path": "responses",
                    "context_window": 4096,
                    "instructions": "test instructions",
                    "input": [
                        {"type": "reasoning", "id": "rs_test", "summary": []},
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "hi"}],
                        },
                    ],
                    "kwargs": {"foo": "bar"},
                }
            )

            telemetry.on_error(ValueError("boom"))

            files = os.listdir(temp_dir)
            assert len(files) == 1
            assert files[0].endswith("-error.json")

            with open(os.path.join(temp_dir, files[0])) as f:
                data = json.loads(f.read())

            assert data["llm_path"] == "responses"
            assert data["context_window"] == 4096
            assert data["instructions"] == "test instructions"
            assert data["input"][0]["type"] == "reasoning"
            assert "error" in data
            assert data["error"]["type"] == "ValueError"
            assert data["error"]["message"] == "boom"
            assert "traceback" in data["error"]
            assert data["cost"] == 0.0
            assert "timestamp" in data
            assert "latency_sec" in data

    def test_log_completion_with_raw_response(self, mock_metrics, mock_response):
        """包含原始响应的测试日志记录。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            telemetry = Telemetry(
                model_name="gpt-4o",
                log_enabled=True,
                log_dir=temp_dir,
                metrics=mock_metrics,
            )

            raw_response = ModelResponse(
                id="raw-id",
                choices=[],
                created=1234567890,
                model="gpt-4o",
                object="chat.completion",
            )

            telemetry.on_request({})
            telemetry.log_llm_call(mock_response, 0.25, raw_resp=raw_response)

            files = os.listdir(temp_dir)
            with open(os.path.join(temp_dir, files[0])) as f:
                data = json.loads(f.read())

            assert "raw_response" in data

    def test_log_completion_with_pydantic_objects_in_context(
        self, mock_metrics, mock_response
    ):
        """
        确保当 log_ctx 包含 Pydantic 个具有排除字段的模型时日志记录有效。 这模拟了远
        程运行情况，其中工具（Pydantic 具有排除的仅运行时字
        段（如执行器）的模型）包含在日志上下文中。 使用Pydantic的model_dump应该避免循
        环引用。
        """

        class SelfReferencingModel(BaseModel):
            name: str
            # 模拟不应该是已序列化的类执行器字段
            executor: object | None = Field(default=None, exclude=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            telemetry = Telemetry(
                model_name="gpt-4o",
                log_enabled=True,
                log_dir=temp_dir,
                metrics=mock_metrics,
            )

            # 通过排除字段创建自引用实例
            m = SelfReferencingModel(name="tool-like")
            m.executor = m  # 将创建一个循环 if 已序列化 via __dict__

            telemetry.on_request({"tools": [m]})

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                telemetry.log_llm_call(mock_response, 0.25)

            # 不应引发循环引用警告
            msgs = [str(x.message) for x in w]
            assert not any("Circular reference detected" in s for s in msgs)

            # 应创建且可读的日志文件 JSON
            files = os.listdir(temp_dir)
            assert len(files) == 1
            with open(os.path.join(temp_dir, files[0])) as f:
                data = json.loads(f.read())
            assert "response" in data

        """测试文件名中带有斜杠的模型名称是否已被清理。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            telemetry = Telemetry(
                model_name="provider/gpt-4o",
                log_enabled=True,
                log_dir=temp_dir,
                metrics=mock_metrics,
            )

            telemetry.on_request({})
            telemetry.log_llm_call(mock_response, 0.25)

            files = os.listdir(temp_dir)
            assert len(files) == 1
            # 应将“/'”替换为“__”
            assert "provider__gpt-4o" in files[0]

    def test_log_completion_error_handling(self, mock_metrics, mock_response):
        """测试日志记录错误处理。"""
        # 通过指向常规文件路径而不是目录来使用保证无效的 log_dir。 这避免了对可能意外存
        # 在或在 CI 中可写的环境特定目录的依赖。
        #
        tmp = tempfile.NamedTemporaryFile(delete=False)
        try:
            bogus_path = tmp.name
            telemetry = Telemetry(
                model_name="gpt-4o",
                log_enabled=True,
                log_dir=bogus_path,
                metrics=mock_metrics,
            )

            telemetry.on_request({})

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                telemetry.log_llm_call(mock_response, 0.25)

                # 应该发出警告但不崩溃
                assert len(w) == 1
                assert "Telemetry logging failed" in str(w[0].message)
        finally:
            try:
                tmp.close()
            except Exception:
                pass
            try:
                os.unlink(tmp.name)
            except Exception:
                pass


class TestTelemetryIntegration:
    """测试完整的遥测集成场景。"""

    def test_full_request_response_cycle(self, mock_metrics):
        """使用所有功能测试完整的请求-响应周期。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            telemetry = Telemetry(
                model_name="gpt-4o",
                log_enabled=True,
                log_dir=temp_dir,
                input_cost_per_token=0.001,
                output_cost_per_token=0.002,
                metrics=mock_metrics,
            )

            # 开始请求
            telemetry_ctx = {"user_id": "test-user", "context_window": 4096}
            telemetry.on_request(telemetry_ctx)

            # 创建使用情况的响应（ModelResponse 格式）
            response = ModelResponse(
                id="test-response-id",
                usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            )

            with patch(
                "openhands.sdk.llm.utils.telemetry.litellm_completion_cost"
            ) as mock_cost:
                mock_cost.return_value = 0.25
                metrics = telemetry.on_response(response)  # type: ignore

            # 验证各方面
            assert metrics.accumulated_cost == 0.25
            assert len(telemetry.metrics.token_usages) == 1
            assert len(telemetry.metrics.costs) == 1
            assert len(telemetry.metrics.response_latencies) == 1

            # 验证日志文件已创建
            files = os.listdir(temp_dir)
            assert len(files) == 1

    def test_multiple_requests(self, basic_telemetry):
        """测试处理多个连续请求。"""
        responses = []

        for i in range(3):
            basic_telemetry.on_request({"request_id": i})

            response = ModelResponse(
                id=f"response-{i}",
                usage=Usage(
                    prompt_tokens=100 + i * 10,
                    completion_tokens=50 + i * 5,
                    total_tokens=150 + i * 15,
                ),
            )

            with patch(
                "openhands.sdk.llm.utils.telemetry.litellm_completion_cost"
            ) as mock_cost:
                mock_cost.return_value = 0.1 + i * 0.05
                cost = basic_telemetry.on_response(response)
                responses.append((response, cost))

        # 应该记录所有请求
        assert len(basic_telemetry.metrics.token_usages) == 3
        assert len(basic_telemetry.metrics.costs) == 3
        assert len(basic_telemetry.metrics.response_latencies) == 3

        # 验证累积指标
        total_cost = sum(cost.cost for cost in basic_telemetry.metrics.costs)
        assert abs(total_cost - 0.45) < 1e-10  # 处理浮点精度


class TestSafeJsonFunction:
    """测试 _safe_json 效用函数。"""

    def test_safe_json_with_dict_object(self):
        """使用具有 __dict__ 的对象测试 _safe_json。"""

        class TestObj:
            def __init__(self):
                self.attr1: str = "value1"
                self.attr2: int = 42

        obj = TestObj()
        result = _safe_json(obj)

        assert result == {"attr1": "value1", "attr2": 42}

    def test_safe_json_without_dict(self):
        """使用不具有 __dict__ 的对象测试 _safe_json。"""
        obj = 42
        result = _safe_json(obj)

        assert result == "42"

    def test_safe_json_with_exception(self):
        """当 __dict__ 访问引发异常时测试 _safe_json。"""

        class BadObj:
            def __getattribute__(self, name):  # type: ignore
                if name == "__dict__":
                    raise Exception("Cannot access __dict__")
                return super().__getattribute__(name)

        obj = BadObj()
        result = _safe_json(obj)

        # 应该回落到 str()
        assert isinstance(result, str)


class TestTelemetryEdgeCases:
    """测试边缘情况和错误条件。"""

    def test_log_completions_no_serialization_warnings(self, mock_metrics):
        """测试日志记录完成情况，没有 Pydantic 序列化警告。

        这会重现使用嵌套 Message 和 Choices 对象记录完成情况导致
        PydanticSerializationUnexpectedValue 警告的
        问题。
        """
        from litellm.types.utils import (
            Choices,
            Message as LiteLLMMessage,
            ModelResponse,
            Usage,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            telemetry = Telemetry(
                model_name="gpt-4o",
                log_enabled=True,
                log_dir=temp_dir,
                metrics=mock_metrics,
            )

            # 使用嵌套消息和选择创建现实的 ModelResponse
            message = LiteLLMMessage(
                content="Test response content",
                role="assistant",
                tool_calls=None,
                function_call=None,
            )
            choice = Choices(
                finish_reason="stop",
                index=0,
                message=message,
                logprobs=None,
            )
            usage = Usage(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            )
            response = ModelResponse(
                id="test-response-id",
                choices=[choice],
                created=1234567890,
                model="gpt-4o",
                object="chat.completion",
                usage=usage,
            )

            telemetry.on_request({"user_id": "test-user", "context_window": 4096})
            telemetry._last_latency = 1.5

            # 这不应产生任何 Pydantic 序列化警告
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                telemetry.log_llm_call(response, 0.25)

                # 检查是否未发出 Pydantic 序列化警告
                pydantic_warnings = [
                    warning
                    for warning in w
                    if "PydanticSerializationUnexpectedValue" in str(warning.message)
                    or "Circular reference detected" in str(warning.message)
                ]
                if pydantic_warnings:
                    for pw in pydantic_warnings:
                        print(f"Warning: {pw.message}")
                assert len(pydantic_warnings) == 0, (
                    f"Got unexpected serialization warnings: {pydantic_warnings}"
                )

            # 验证日志文件是否已成功创建
            files = os.listdir(temp_dir)
            assert len(files) == 1

            # 验证内容是否可以读回
            with open(os.path.join(temp_dir, files[0])) as f:
                data = json.loads(f.read())
                assert "response" in data
                assert data["cost"] == 0.25

    def test_on_response_without_on_request(self, basic_telemetry, mock_response):
        """测试 on_response 在没有事先 on_request 的情况下调用。"""
        # 不应崩溃，应使用当前时间进行延迟计算
        metrics = basic_telemetry.on_response(mock_response)

        assert isinstance(metrics.accumulated_cost, float)
        # 由于计时精度，延迟可能非常小甚至为负值，重要的是它不会崩溃
        #
        assert isinstance(basic_telemetry._last_latency, float)

    def test_response_id_extraction_edge_cases(self, basic_telemetry):
        """测试从各种响应格式中提取响应 ID。"""
        # 使用 ModelResponse 和 ID 进行测试
        response_with_id = ModelResponse(id="model-response-id", usage=None)
        basic_telemetry.on_request({})
        basic_telemetry.on_response(response_with_id)

        # 测试 ModelResponse 缺少 ID
        response_no_id = ModelResponse(usage=None)
        basic_telemetry.on_request({})
        basic_telemetry.on_response(response_no_id)

        # 使用非ModelResponse对象进行测试
        with pytest.raises(ValidationError):
            mock_response = MagicMock()
            basic_telemetry.on_request({})
            basic_telemetry.on_response(mock_response)

        # 应该记录所有情况的延迟
        assert len(basic_telemetry.metrics.response_latencies) == 2

    def test_usage_extraction_edge_cases(self, basic_telemetry):
        """测试从各种响应格式中提取用法。"""
        # 使用包含用法的字典响应进行测试
        response = ModelResponse(
            id="test-id",
            usage={
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        )

        basic_telemetry.on_request({"context_window": 4096})
        basic_telemetry.on_response(response)
        assert len(basic_telemetry.metrics.token_usages) == 1

        # 在不使用的情况下使用 dict 响应进行测试
        response_no_usage = ModelResponse(id="no-usage-id", usage=None)
        basic_telemetry.on_request({})
        basic_telemetry.on_response(response_no_usage)

        # 应该仍然只有一条词元用量记录
        assert len(basic_telemetry.metrics.token_usages) == 1

    def test_cost_calculation_with_zero_cost(self, basic_telemetry, mock_response):
        """测试成本为零或 None 时的成本计算。"""
        with patch.object(basic_telemetry, "_compute_cost", return_value=None):
            metrics = basic_telemetry.on_response(mock_response)

            assert metrics.accumulated_cost == 0.0
            # 当成本为 None 时不应添加到成本列表
            assert len(basic_telemetry.metrics.costs) == 0

        with patch.object(basic_telemetry, "_compute_cost", return_value=0.0):
            metrics = basic_telemetry.on_response(mock_response)

            assert metrics.accumulated_cost == 0.0
            # 应该不将零成本添加到成本列表中（0.0 是错误的）
            assert len(basic_telemetry.metrics.costs) == 0


class TestTelemetryCallbacks:
    """测试日志流式传输和统计更新的回调功能。"""

    def test_set_log_callback(self, basic_telemetry):
        """测试设置日志回调。"""
        callback_called = []

        def log_callback(filename: str, log_data: str):
            callback_called.append((filename, log_data))

        basic_telemetry.set_log_completions_callback(log_callback)
        assert basic_telemetry._log_completions_callback == log_callback

        # 清除回调
        basic_telemetry.set_log_completions_callback(None)
        assert basic_telemetry._log_completions_callback is None

    def test_set_stats_update_callback(self, basic_telemetry):
        """测试设置统计数据更新回调。"""
        callback_called = []

        def stats_callback():
            callback_called.append(True)

        basic_telemetry.set_stats_update_callback(stats_callback)
        assert basic_telemetry._stats_update_callback == stats_callback

        # 清除回调
        basic_telemetry.set_stats_update_callback(None)
        assert basic_telemetry._stats_update_callback is None

    def test_stats_update_callback_triggered_on_response(
        self, basic_telemetry, mock_response
    ):
        """测试响应时是否触发统计更新回调。"""
        callback_called = []

        def stats_callback():
            callback_called.append(True)

        basic_telemetry.set_stats_update_callback(stats_callback)
        basic_telemetry.on_request(None)
        basic_telemetry.on_response(mock_response)

        # 回调响应后应触发一次
        assert len(callback_called) == 1

    def test_stats_update_callback_exception_handling(
        self, basic_telemetry, mock_response
    ):
        """测试 stats 回调中的异常不会破坏 on_response。"""

        def failing_callback():
            raise Exception("Callback failed")

        basic_telemetry.set_stats_update_callback(failing_callback)
        basic_telemetry.on_request(None)

        # 即使回调失败也不应引发异常
        metrics = basic_telemetry.on_response(mock_response)
        assert isinstance(metrics, Metrics)
