from __future__ import annotations

from collections.abc import Callable, Generator
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from litellm.exceptions import (
    APIConnectionError,
    BadGatewayError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout as LiteLLMTimeout,
)
from pydantic import BaseModel, Field, PrivateAttr

from openhands.sdk.llm.exceptions import LLMNoResponseError
from openhands.sdk.llm.exceptions.classifier import (
    is_budget_exceeded_error,
    is_transient_http_error,
)
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.logger import get_logger


if TYPE_CHECKING:
    from openhands.sdk.llm.llm_response import LLMResponse
    from openhands.sdk.llm.utils.metrics import Metrics

logger = get_logger(__name__)

# 触发异常回退方案 to alternate LLMs (after) 重试 exhausted).
_LLM_FALLBACK_EXCEPTIONS: Final[tuple[type[Exception], ...]] = (
    APIConnectionError,
    BadGatewayError,
    RateLimitError,
    ServiceUnavailableError,
    LiteLLMTimeout,
    InternalServerError,
    LLMNoResponseError,
)


class FallbackStrategy(BaseModel):
    """封装 LLM 调用的回退方案行为。

    当主 LLM 失效并出现临时错误（在重试后）时，该策略会尝试从 LLMProfileStore 的备用
    LLMs 加载。 回退方案是每次调用：每个新请求都从主模型开
    始。
    """

    fallback_llms: list[str] = Field(
        description="Ordered list of LLM profile names to try on transient failure."
    )
    profile_store_dir: str | Path | None = Field(
        default=None,
        description="Path to directory containing profiles. "
        "If not specified, defaults to `.openhands/profiles`.",
    )

    # 私有：延迟解析 LLM 个实例
    _resolved: list[Any] | None = PrivateAttr(default=None)

    def should_fallback(self, error: Exception) -> bool:
        """该错误类型是否符合回退方案。"""
        return (
            isinstance(error, _LLM_FALLBACK_EXCEPTIONS)
            or is_transient_http_error(error)
        ) and not is_budget_exceeded_error(error)

    def try_fallback(
        self,
        primary_model: str,
        primary_error: Exception,
        primary_metrics: Metrics,
        call_fn: Callable[[Any], LLMResponse],
    ) -> LLMResponse | None:
        """按照回退方案 LLMs 的顺序尝试。 将指标合并到主要的成功指标中。

        Args:
            primary_model: 主要模型名称（用于日志记录）。
            primary_error: 主要模型的误差。
            primary_metrics: 将回退方案成本合并到的主要 LLM 的指标。
            call_fn: 一个接受LLM实例并返回LLMResponse的可调用函数。

        Returns:
            LLMResponse 从第一个成功的回退方案，或 None 如果所有都失败了。
        """
        total = len(self.fallback_llms)
        tried = 0
        for i, fb in enumerate(self._iter_fallbacks()):
            tried += 1
            remaining = total - i - 1
            logger.warning(
                f"[Fallback Strategy]Primary LLM ({primary_model}) failed with "
                f"{type(primary_error).__name__}, "
                f"trying fallback {i + 1}/{total} ({fb.model}); "
                f"{remaining} fallback(s) remaining"
            )
            try:
                # 禁用嵌套回退方案以防止递归链
                saved_strategy = fb.fallback_strategy
                fb.fallback_strategy = None
                metrics_before = fb.metrics.deep_copy()
                try:
                    result = call_fn(fb)
                finally:
                    fb.fallback_strategy = saved_strategy
                # 将回退方案指标（成本 + token）合并到主要指标中
                metrics_diff = fb.metrics.diff(metrics_before)
                primary_metrics.merge(metrics_diff)
                logger.info(f"[Fallback Strategy] Fallback LLM ({fb.model}) succeeded")
                return result
            except Exception as fb_error:
                # 预算适用于各种型号； 另一个回退方案无法绕过它。
                if is_budget_exceeded_error(fb_error):
                    raise
                logger.warning(
                    "[Fallback Strategy]"
                    f"Fallback {i + 1} ({fb.model}) failed: "
                    f"{type(fb_error).__name__}: {fb_error}"
                )
                continue

        if tried > 0:
            logger.error(
                "[Fallback Strategy] All fallback LLMs failed; re-raising primary error"
            )
        return None

    @cached_property
    def _profile_store(self) -> LLMProfileStore:
        return LLMProfileStore(self.profile_store_dir)

    def _iter_fallbacks(self) -> Generator[Any]:
        """产生回退方案 LLM 个实例，从配置文件中延迟解析。

        配置文件一次加载一个并逐渐附加到 ``_resolved``。 在后续调用中，首先生成已缓存
        的实例，然后继续解析尚未加载的任何剩余配置文件。
        """
        if self._resolved is None:
            self._resolved = []

        # 生成已缓存的实例
        yield from self._resolved

        # 继续解析尚未加载的配置文件
        remaining_names = self.fallback_llms[len(self._resolved) :]
        for name in remaining_names:
            try:
                fb = self._profile_store.load(name)
                self._resolved.append(fb)
                yield fb
            except (FileNotFoundError, ValueError) as exc:
                logger.error(
                    "[Fallback Strategy] Failed to load "
                    f"fallback profile '{name}': {exc}"
                )
