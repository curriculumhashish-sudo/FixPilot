from collections.abc import Callable, Iterable
from typing import Any, cast

from tenacity import (
    RetryCallState,
    retry,
    retry_base,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from openhands.sdk.llm.exceptions import LLMNoResponseError
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

# 侦听器签名的有用别名：(attempt_number, max_retries) -> None
RetryListener = Callable[[int, int, BaseException | None], None]


class RetryMixin:
    """重试逻辑的 Mixin 类。"""

    def _build_before_sleep(
        self,
        num_retries: int,
        retry_listener: RetryListener | None,
    ) -> Callable[[RetryCallState], None]:
        """构建一个由同步和异步装饰器共享的 ``before_sleep`` 回调。"""

        def before_sleep(retry_state: RetryCallState) -> None:
            self.log_retry_attempt(retry_state)

            if retry_listener is not None:
                exc = (
                    retry_state.outcome.exception()
                    if retry_state.outcome is not None
                    else None
                )
                retry_listener(retry_state.attempt_number, num_retries, exc)

            if retry_state.outcome is None:
                return
            exc = retry_state.outcome.exception()
            if exc is None:
                return

            # 仅调整温度 LLMNoResponseError
            if isinstance(exc, LLMNoResponseError):
                kwargs = getattr(retry_state, "kwargs", None)
                if isinstance(kwargs, dict):
                    current_temp = kwargs.get(
                        "temperature", getattr(self, "temperature", None)
                    )
                    if current_temp is None:
                        logger.warning(
                            "LLMNoResponseError with no configured temperature, "
                            "leaving temperature unset for next attempt."
                        )
                        return
                    if current_temp == 0:
                        kwargs["temperature"] = 1.0
                        logger.warning(
                            "LLMNoResponseError with temperature=0, "
                            "setting temperature to 1.0 for next attempt."
                        )
                    else:
                        logger.warning(
                            f"LLMNoResponseError with temperature={current_temp}, "
                            "keeping original temperature"
                        )

        return before_sleep

    def retry_decorator(
        self,
        num_retries: int = 5,
        retry_exceptions: tuple[type[BaseException], ...] | retry_base = (
            LLMNoResponseError,
        ),
        retry_min_wait: int = 8,
        retry_max_wait: int = 64,
        retry_multiplier: float = 2.0,
        retry_listener: RetryListener | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """
        创建一个具有可自定义参数的 LLM 重试装饰器。 这用于 429 错误以及 LLM 类中的一
        些其他异常。

        ``retry_exceptions`` 可以是异常类型的元组（按原样重试）或 tenacity 重试谓词 (
        e.g. 一个组合的
        ``retry_if_exception_type(...) & retry_if_not_exception(...)``) 用于更细粒度
        地控制重试哪些异
        常。
        """
        before_sleep = self._build_before_sleep(num_retries, retry_listener)

        retry_condition = (
            retry_if_exception_type(retry_exceptions)
            if isinstance(retry_exceptions, tuple)
            else retry_exceptions
        )

        retry_decorator: Callable[[Callable[..., Any]], Callable[..., Any]] = retry(
            before_sleep=before_sleep,
            stop=stop_after_attempt(num_retries),
            reraise=True,
            retry=retry_condition,
            wait=wait_exponential(
                multiplier=retry_multiplier,
                min=retry_min_wait,
                max=retry_max_wait,
            ),
        )
        return retry_decorator

    def log_retry_attempt(self, retry_state: RetryCallState) -> None:
        """Log 重试 attempts."""

        if retry_state.outcome is None:
            logger.error(
                "retry_state.outcome is None. "
                "This should not happen, please check the retry logic."
            )
            return

        exc = retry_state.outcome.exception()
        if exc is None:
            logger.error("retry_state.outcome.exception() returned None.")
            return

        # 尝试从停止条件（如果存在）获得最大尝试次数
        max_attempts: int | None = None
        retry_obj = getattr(retry_state, "retry_object", None)
        stop_condition = getattr(retry_obj, "stop", None)
        if stop_condition is not None:
            # stop_any 有 .stops，单站没有
            stops: Iterable[Any]
            if hasattr(stop_condition, "stops"):
                stops = stop_condition.stops  # type: ignore[attr-defined]
            else:
                stops = [stop_condition]
            for stop_func in stops:
                if hasattr(stop_func, "max_attempts"):
                    max_attempts = getattr(stop_func, "max_attempts")
                    break

        # 为下游消费者附加动态字段（保留现有行为）
        setattr(cast(Any, exc), "retry_attempt", retry_state.attempt_number)
        if max_attempts is not None:
            setattr(cast(Any, exc), "max_retries", max_attempts)

        logger.error(
            "%s. Attempt #%d | You can customize retry values in the configuration.",
            exc,
            retry_state.attempt_number,
        )
