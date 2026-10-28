import json
import os
import time
import traceback
import uuid
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from litellm.cost_calculator import completion_cost as litellm_completion_cost
from litellm.types.llms.openai import ResponseAPIUsage, ResponsesAPIResponse
from litellm.types.utils import CostPerToken, ModelResponse, Usage
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SecretStr

from openhands.sdk.llm.utils.litellm_provider import LLMProvider
from openhands.sdk.llm.utils.metrics import Metrics
from openhands.sdk.llm.utils.openhands_provider import litellm_call_kwargs
from openhands.sdk.logger import get_logger
from openhands.sdk.utils.redact import is_secret_key, redact_text_secrets, sanitize_dict


logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    """一个响应的 token 会计的独立于提供者的视图。

    LiteLLM 报告名称相同数量的两个不相交形状的使用情况
    differently: ``Usage``（聊天完成）使用 ``prompt_tokens`` /
    ``completion_tokens``，而 ``ResponseAPIUsage``（响应 API）使用
    ``input_tokens`` / ``output_tokens``. 一次标准化，边界处进行，而不是每次调用时重
    新发现别名，确保每个消费者（指标、跨度属性和完
    成日志）都使用同一个词汇表。
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def has_tokens(self) -> bool:
        """提供者是否报告了任何提示词或完成情况 token。"""
        return self.prompt_tokens > 0 or self.completion_tokens > 0


def normalize_usage(usage: Usage | ResponseAPIUsage | None) -> UsageSnapshot | None:
    """返回任一提供程序使用形状的：class:`UsageSnapshot`。

    ``None`` 表示“无 token 核算”：提供者报告没有使用，或报告了该模块无法识别的形状。
    未识别的形状被忽略，而不是猜测，因此添加提供者不会无意识地将虚构
    的 token 计数喂入成本和缓存计数。
    """
    if isinstance(usage, Usage):
        prompt_details = usage.prompt_tokens_details
        completion_details = usage.completion_tokens_details
        # ``cache_creation_tokens`` 默认为 ``None``，因此存在于
        # ``model_fields_set`` 是“提供商报告缓存写入”与“提供商对缓存写入未提及”的区别。
        # 然而，LiteLLM 当值为
        # ``None`` (e.g. minimax-m3 报告 ``cache_creation_tokens: null``），因此仅
        # ``model_fields_set`` 是不够的； 守卫``hasattr``。
        #
        cache_write = 0
        if (
            prompt_details is not None
            and "cache_creation_tokens" in prompt_details.model_fields_set
            and hasattr(prompt_details, "cache_creation_tokens")
        ):
            cache_write = int(prompt_details.cache_creation_tokens or 0)
        return UsageSnapshot(
            prompt_tokens=int(usage.prompt_tokens or 0),
            completion_tokens=int(usage.completion_tokens or 0),
            reasoning_tokens=(
                int(completion_details.reasoning_tokens or 0)
                if completion_details is not None
                else 0
            ),
            cache_read_tokens=(
                int(prompt_details.cached_tokens or 0)
                if prompt_details is not None
                else 0
            ),
            cache_write_tokens=cache_write,
        )

    if isinstance(usage, ResponseAPIUsage):
        input_details = usage.input_tokens_details
        output_details = usage.output_tokens_details
        return UsageSnapshot(
            prompt_tokens=int(usage.input_tokens or 0),
            completion_tokens=int(usage.output_tokens or 0),
            reasoning_tokens=(
                int(output_details.reasoning_tokens or 0)
                if output_details is not None
                else 0
            ),
            cache_read_tokens=(
                int(input_details.cached_tokens or 0)
                if input_details is not None
                else 0
            ),
        )

    return None


def _response_usage(
    resp: ModelResponse | ResponsesAPIResponse,
) -> Usage | ResponseAPIUsage | None:
    """返回响应携带的使用对象（如果有）。

    ``ResponsesAPIResponse`` 将 ``usage`` 声明为字段。 ``ModelResponse`` 仅接受它作为
    构造函数参数，因此 Pyda
    ntic 将其保留在模型的额外映射中，而不是其字段中； 读取该映射相当于探测可能不存在
    的属性的类型。
    """
    if isinstance(resp, ResponsesAPIResponse):
        return resp.usage
    if isinstance(resp, ModelResponse):
        extra = resp.model_extra
        if not extra:
            return None
        usage = extra.get("usage")
        if isinstance(usage, (Usage, ResponseAPIUsage)):
            return usage
    return None


class Telemetry(BaseModel):
    """
    处理延迟、令牌/成本核算和可选日志记录。 所有运行时状态（如开始时间）都存在于私有
    属性中。
    """

    # --- 配置字段 ---
    model_name: str = Field(default="unknown", description="Name of the LLM model")
    log_enabled: bool = Field(default=False, description="Whether to log completions")
    log_dir: str | None = Field(
        default=None, description="Directory to write logs if enabled"
    )
    input_cost_per_token: float | None = Field(
        default=None, ge=0, description="Custom Input cost per token (USD)"
    )
    output_cost_per_token: float | None = Field(
        default=None, ge=0, description="Custom Output cost per token (USD)"
    )

    metrics: Metrics = Field(..., description="Metrics collector instance")

    # --- 运行时字段（不是已序列化）---
    _req_start: float = PrivateAttr(default=0.0)
    _req_ctx: dict[str, Any] = PrivateAttr(default_factory=dict)
    _last_latency: float = PrivateAttr(default=0.0)
    _log_completions_callback: Callable[[str, str], None] | None = PrivateAttr(
        default=None
    )
    _stats_update_callback: Callable[[], None] | None = PrivateAttr(default=None)
    _span_cm: Any = PrivateAttr(default=None)
    _span: Any = PrivateAttr(default=None)

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", arbitrary_types_allowed=True
    )

    # ---------- 生命周期 ----------
    def set_log_completions_callback(
        self, callback: Callable[[str, str], None] | None
    ) -> None:
        """设置回调函数用于记录而不是写入文件。

        Args:
            callback: 一个接受 (filename, log_data) 并处理日志的函数。
                     用于远程执行上下文中的流式传输日志。
        """
        self._log_completions_callback = callback

    def set_stats_update_callback(self, callback: Callable[[], None] | None) -> None:
        """设置回调函数以在统计数据更新时收到通知。

        Args:
            callback: 每当指标更新时调用的函数。
                     用于远程执行上下文中的流式传输统计信息更新。
        """
        self._stats_update_callback = callback

    def on_request(self, telemetry_ctx: dict | None) -> None:
        self._req_start = time.time()
        self._req_ctx = _redact_request_credentials(telemetry_ctx or {})
        self._open_span()

    def on_response(
        self,
        resp: ModelResponse | ResponsesAPIResponse,
        raw_resp: ModelResponse | None = None,
        provider_info: LLMProvider | None = None,
    ) -> Metrics:
        """
        副作用：
          - 将延迟、token、成本记录到指标中
          - 可选择写入 JSON 日志文件
        """
        # 1) 延迟
        self._last_latency = time.time() - (self._req_start or time.time())
        response_id = resp.id
        self.metrics.add_response_latency(self._last_latency, response_id)

        # 2) 成本
        cost = self._compute_cost(resp, provider_info=provider_info)
        # 故意跳过记录零成本 (0.0) 响应； 仅记录正成本
        #
        if cost:
            self.metrics.add_cost(cost)

        # 3) token - 将提供者的使用形状标准化一次
        usage = normalize_usage(_response_usage(resp))

        if usage is not None and usage.has_tokens:
            self._record_usage(
                usage, response_id, self._req_ctx.get("context_window", 0)
            )

        # 4) 可选日志记录
        if self.log_enabled:
            self.log_llm_call(resp, cost, raw_resp=raw_resp)

        # 5) 权威成本+在关闭之前将桶缓存到跨度上
        self._annotate_span(cost, usage)
        self._close_span()

        # 6) 通知统计数据更新
        if self._stats_update_callback is not None:
            try:
                self._stats_update_callback()
            except Exception:
                logger.exception("Stats update callback failed", exc_info=True)

        return self.metrics.deep_copy()

    def on_error(self, _err: BaseException) -> None:
        # 尽力记录失败的请求（因此我们可以调试格式错误的请求载荷、e.g。 孤立的响应推理项
        # 目）。
        #
        self._last_latency = time.time() - (self._req_start or time.time())
        self._close_span(_err)

        if not self.log_enabled:
            return
        if not self.log_dir and not self._log_completions_callback:
            return

        try:
            filename = (
                f"{self.model_name.replace('/', '__')}-"
                f"{time.time():.3f}-"
                f"{uuid.uuid4().hex[:4]}-error.json"
            )

            data = self._req_ctx.copy()
            data["error"] = {
                "type": type(_err).__name__,
                "message": redact_text_secrets(str(_err)),
                "repr": redact_text_secrets(repr(_err)),
                "traceback": redact_text_secrets(
                    "".join(
                        traceback.format_exception(type(_err), _err, _err.__traceback__)
                    )
                ),
            }
            data["timestamp"] = time.time()
            data["latency_sec"] = self._last_latency
            data["cost"] = 0.0

            log_data = json.dumps(data, default=_safe_json, ensure_ascii=False)

            if self._log_completions_callback:
                self._log_completions_callback(filename, log_data)
            elif self.log_dir:
                os.makedirs(self.log_dir, exist_ok=True)
                fname = os.path.join(self.log_dir, filename)
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(log_data)
        except Exception as e:
            warnings.warn(f"Telemetry error logging failed: {e}")
        return

    # ---------- 帮手 ----------
    def _record_usage(
        self, usage: UsageSnapshot, response_id: str, context_window: int
    ) -> None:
        """将已经标准化的使用情况快照记录到 ``metrics`` 中。"""
        self.metrics.add_token_usage(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            context_window=context_window,
            response_id=response_id,
        )

    # ---------- 可观测范围 ----------
    # 这些括号包含一个 LLM 调用： ``on_request`` -> 传输层 -> ``on_response`` 都在一个重
    # 试次尝试中运行，因此跨度在 LiteLLM 执行时是当前的，当成本确定时仍然打开。
    #
    def _open_span(self) -> None:
        self._close_span()  # a 重试重新进入 on_request； 永远不要泄露旧的
        try:
            # 延迟导入：openhands.sdk.observability 拉入 openhands.sdk.event，从而导入该
            # 模块。
            #
            from openhands.sdk.observability.laminar import llm_call_span

            cm = llm_call_span(f"llm.{self.model_name}")
            self._span = cm.__enter__()
            self._span_cm = cm
        except Exception:
            logger.debug("Failed to open LLM span", exc_info=True)
            self._span = self._span_cm = None

    def _annotate_span(self, cost: float | None, usage: UsageSnapshot | None) -> None:
        span = self._span
        if span is None:
            return
        try:
            if cost:
                # 权威：_compute_cost更喜欢代理的
                # x-LiteLLM-response-cost 标头，它已经具有缓存感知能力，并由真实后端而不
                # 是名称查找定价。
                #
                span.set_attribute("gen_ai.usage.cost", float(cost))
            if usage is not None:
                # 无条件发出：lmnr 仅在填充 prompt_tokens_details 时报告这些内容，并非每
                # 个提供程序形状都会这样做。
                #
                span.set_attribute(
                    "gen_ai.usage.cache_read_input_tokens", usage.cache_read_tokens
                )
                span.set_attribute(
                    "gen_ai.usage.cache_creation_input_tokens",
                    usage.cache_write_tokens,
                )
        except Exception:
            logger.debug("Failed to annotate LLM span", exc_info=True)

    def _close_span(self, err: BaseException | None = None) -> None:
        cm, self._span_cm, self._span = self._span_cm, None, None
        if cm is None:
            return
        try:
            if err is not None:
                cm.__exit__(type(err), err, err.__traceback__)
            else:
                cm.__exit__(None, None, None)
        except Exception:
            logger.debug("Failed to close LLM span", exc_info=True)

    def _compute_cost(
        self,
        resp: ModelResponse | ResponsesAPIResponse,
        provider_info: LLMProvider | None = None,
    ) -> float | None:
        """尝试直接提供程序标头 → LiteLLM。 失败时返回None。"""
        extra_kwargs = {}
        if (
            self.input_cost_per_token is not None
            and self.output_cost_per_token is not None
        ):
            cost_per_token = CostPerToken(
                input_cost_per_token=self.input_cost_per_token,
                output_cost_per_token=self.output_cost_per_token,
            )
            logger.debug(f"Using custom cost per token: {cost_per_token}")
            extra_kwargs["custom_cost_per_token"] = cost_per_token

        try:
            hidden = resp._hidden_params or {}
            cost = hidden.get("additional_headers", {}).get(
                "llm_provider-x-litellm-response-cost"
            )
            if cost is not None:
                return float(cost)
        except Exception as e:
            logger.debug(f"Failed to get cost from LiteLLM headers: {e}")

        if provider_info is None:
            call_kwargs = litellm_call_kwargs(self.model_name, None)
            provider_info = LLMProvider.from_model(
                model=call_kwargs["model"],
                api_base=call_kwargs["api_base"],
            )
        extra_kwargs.update(provider_info.as_litellm_call_kwargs())
        try:
            return float(
                litellm_completion_cost(completion_response=resp, **extra_kwargs)
            )
        except Exception as e:
            warnings.warn(f"Cost calculation failed: {e}")
            return None

    def log_llm_call(
        self,
        resp: ModelResponse | ResponsesAPIResponse,
        cost: float | None,
        raw_resp: ModelResponse | ResponsesAPIResponse | None = None,
    ) -> None:
        # 如果文件日志记录和回调均未配置，则跳过
        if not self.log_dir and not self._log_completions_callback:
            return
        try:
            # 准备文件名和日志数据
            filename = (
                f"{self.model_name.replace('/', '__')}-"
                f"{time.time():.3f}-"
                f"{uuid.uuid4().hex[:4]}.json"
            )

            data = self._req_ctx.copy()
            data["response"] = (
                resp  # ModelResponse | ResponsesAPIResponse;
                # 已序列化通过 _safe_json
            )
            data["cost"] = float(cost or 0.0)
            data["timestamp"] = time.time()
            data["latency_sec"] = self._last_latency

            # 用法总结（提示词、完成、推理token）以供快速检查
            try:
                usage = normalize_usage(_response_usage(resp))
                if usage is not None:
                    data["usage_summary"] = {
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                        "reasoning_tokens": usage.reasoning_tokens,
                        "cache_read_tokens": usage.cache_read_tokens,
                    }
            except Exception:
                # 仅尽力而为； 不要记录失败
                pass

            # 原始响应 *before* nonfncall -> 调用转换
            if raw_resp:
                data["raw_response"] = (
                    raw_resp  # ModelResponse | ResponsesAPIResponse;
                    # 已序列化通过 _safe_json
                )
            # 弹出重复的工具以避免记录两次
            if (
                "tools" in data
                and isinstance(data.get("kwargs"), dict)
                and "tools" in data["kwargs"]
            ):
                data["kwargs"].pop("tools")

            log_data = json.dumps(data, default=_safe_json, ensure_ascii=False)

            # 如果设置则使用回调（用于远程执行），否则写入文件
            if self._log_completions_callback:
                self._log_completions_callback(filename, log_data)
            elif self.log_dir:
                # 如果日志目录不存在则创建
                os.makedirs(self.log_dir, exist_ok=True)
                if not os.access(self.log_dir, os.W_OK):
                    raise PermissionError(f"log_dir is not writable: {self.log_dir}")
                fname = os.path.join(self.log_dir, filename)
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(log_data)
        except Exception as e:
            warnings.warn(f"Telemetry logging failed: {e}")


def _redact_request_credentials(ctx: dict[str, Any]) -> dict[str, Any]:
    """返回 ``ctx``，并复制其记录的请求凭据和已脱敏。

    记录的 ``kwargs`` 与实时调用共享其标头字典，并且一些 LiteLLM 提供者将
    ``Authorization`` 写入其中。 在调用之前在此处进行复制
    ，可以将此类突变以及调用者提供的凭据选项和标头保留在完成日志之外。
    """
    kwargs = ctx.get("kwargs")
    if not isinstance(kwargs, dict):
        return ctx
    logged_kwargs = {}
    for key, value in kwargs.items():
        if isinstance(value, (str, SecretStr)) and is_secret_key(key):
            logged_kwargs[key] = sanitize_dict({key: value})[key]
        else:
            logged_kwargs[key] = sanitize_dict(value)
    return {**ctx, "kwargs": logged_kwargs}


def _safe_json(obj: Any) -> Any:
    # 遥测日志的集中序列化器。 首先对 Pydantic 模型选择稳健的序列化以避免循环。
    #
    if isinstance(obj, SecretStr):
        return str(obj)

    # 输入 LiteLLM 条回复
    if isinstance(obj, ModelResponse) or isinstance(obj, ResponsesAPIResponse):
        return obj.model_dump(mode="json", exclude_none=True)

    # 任意 Pydantic BaseModel（e.g.、ToolDefinition、ChatCompletionToolParam 等）
    if isinstance(obj, BaseModel):
        # 使用 Pydantic 的序列化器尊重字段排除（e.g.，执行者）
        return obj.model_dump(mode="json", exclude_none=True)

    # 回退方案用于日志中其他地方使用的其他不可序列化对象载荷
    try:
        return obj.__dict__
    except Exception:
        return str(obj)
