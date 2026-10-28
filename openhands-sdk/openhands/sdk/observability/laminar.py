from __future__ import annotations

import contextlib
import functools
import inspect
import json
import sys
from collections.abc import Callable, Iterator, Mapping
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from openhands.sdk.logger import get_logger
from openhands.sdk.observability.utils import get_env


if TYPE_CHECKING:
    from openhands.sdk.conversation.types import TraceMetadataValue


logger = get_logger(__name__)


# 缓存 should_enable_observability 的阳性结果。 一旦启用可观察性（通过环境变量或用户端
# Laminar.initialize() 调用），它就会在进程的生命周期内保持启用状态。
#
_observability_enabled: bool = False


_OBSERVABILITY_ENV_KEYS: Final[tuple[str, ...]] = (
    "LMNR_PROJECT_API_KEY",
    "OTEL_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
)


OPERATION_METADATA_KEY: Final[str] = "openhands.operation"
"""命名跨度子树所属的辅助实用操作的元数据键。"""

_OBSERVABILITY_METADATA_ENV: Final[str] = "OPENHANDS_OBSERVABILITY_METADATA"
_OBSERVABILITY_TAGS_ENV: Final[str] = "OPENHANDS_OBSERVABILITY_TAGS"
_OBSERVABILITY_SPAN_NAME_ENV: Final[str] = "OPENHANDS_OBSERVABILITY_SPAN_NAME"
_OBSERVABILITY_PARENT_CONTEXT_ENV: Final[str] = (
    "OPENHANDS_OBSERVABILITY_PARENT_SPAN_CONTEXT"
)
_LAMINAR_PARENT_CONTEXT_ENV: Final[str] = "LMNR_SPAN_CONTEXT"


def _is_trace_metadata_value(value: Any) -> bool:
    if isinstance(value, str | bool | int | float):
        return True
    if isinstance(value, list):
        return (
            all(isinstance(item, str) for item in value)
            or all(isinstance(item, bool) for item in value)
            or all(
                isinstance(item, int) and not isinstance(item, bool) for item in value
            )
            or all(isinstance(item, float) for item in value)
        )
    return False


def _clean_trace_metadata(value: Any) -> dict[str, TraceMetadataValue]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, TraceMetadataValue] = {}
    for key, item in value.items():
        if isinstance(key, str) and key and _is_trace_metadata_value(item):
            cleaned[key] = item
    return cleaned


def observability_metadata_from_env() -> dict[str, TraceMetadataValue]:
    """返回流程环境提供的通用可观察性元数据。"""
    raw_metadata = get_env(_OBSERVABILITY_METADATA_ENV)
    if not raw_metadata:
        return {}
    try:
        return _clean_trace_metadata(json.loads(raw_metadata))
    except json.JSONDecodeError:
        logger.debug("Ignoring invalid %s", _OBSERVABILITY_METADATA_ENV)
        return {}


def merge_observability_metadata(
    metadata: Mapping[str, TraceMetadataValue] | None,
) -> dict[str, TraceMetadataValue]:
    """将通用环境默认值与调用者提供的元数据合并。"""
    merged = observability_metadata_from_env()
    if metadata:
        merged.update(metadata)
    return merged


def observability_parent_span_context_from_env() -> str | None:
    """返回由主机进程传播的已序列化父范围上下文。"""
    return get_env(_OBSERVABILITY_PARENT_CONTEXT_ENV) or get_env(
        _LAMINAR_PARENT_CONTEXT_ENV
    )


def default_observability_span_name_from_env() -> str | None:
    """从通用环境返回默认对话子范围名称。"""
    return get_env(_OBSERVABILITY_SPAN_NAME_ENV)


def observability_tags_from_env() -> list[str]:
    """返回由通用环境提供的逗号分隔的可观察性标签。"""
    raw_tags = get_env(_OBSERVABILITY_TAGS_ENV)
    if not raw_tags:
        return []
    return [tag.strip() for tag in raw_tags.split(",") if tag.strip()]


def observability_headers_from_env() -> dict[str, str]:
    """为智能体-服务器 API 调用构建通用可观察性标头。"""
    headers: dict[str, str] = {}
    metadata = observability_metadata_from_env()
    if metadata:
        headers["X-OpenHands-Observability-Metadata"] = json.dumps(
            metadata, separators=(",", ":")
        )
    tags = observability_tags_from_env()
    if tags:
        headers["X-OpenHands-Observability-Tags"] = ",".join(tags)
    span_name = default_observability_span_name_from_env()
    if span_name:
        headers["X-OpenHands-Observability-Span-Name"] = span_name
    parent_context = observability_parent_span_context_from_env()
    if parent_context:
        headers["X-OpenHands-Observability-Parent-Span-Context"] = parent_context
    try:
        from opentelemetry.propagate import inject

        inject(headers)
    except Exception:
        logger.debug(
            "Failed to inject OpenTelemetry propagation headers", exc_info=True
        )
    return headers


def _get_int_env(key: str) -> int | None:
    """将环境变量读取为可选 int。"""
    val = get_env(key)
    if val is not None and val != "":
        try:
            return int(val)
        except ValueError:
            logger.warning("%s must be an integer, got %r", key, val)
            return None
    return None


def maybe_init_laminar():
    """如果设置了环境变量，则初始化层流。

    配置示例：

    ```bash
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://otel-collector:4317/v1/traces

    # 逗号分隔，key=value url 编码对
    OTEL_EXPORTER_OTLP_TRACES_HEADERS="Authorization=Bearer%20<KEY>,X-Key=<CUSTOM_VALUE>"

    # 如果未指定，则假定为 grpc
    OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf # 或 grpc/protobuf
    # 或
    OTEL_EXPORTER=otlp_http # 或 otlp_grpc
    ```

    对于自托管 Laminar，通过环境变量设置基础 URL 和端口：
    LMNR_BASE_URL=https://api.lmnr.ai  # 可选，默认值为  https://api.lmnr.ai
    LMNR_HTTP_PORT=8000
    LMNR_GRPC_PORT=8001

    强制 HTTP 而不是 gRPC 进行层流通信：
    LMNR_FORCE_HTTP=true  # 或者 1，是的，是的

    仅初始化选定的层流集成：
    LMNR_INSTRUMENTS=litellm,mcp
    """  # noqa: E501
    if not should_enable_observability():
        logger.debug(
            "Observability/OTEL environment variables are not set. "
            "Skipping Laminar initialization."
        )
        return

    from lmnr import Instruments, Laminar

    if Laminar.is_initialized():
        return

    base_url = get_env("LMNR_BASE_URL") or None
    force_http = (get_env("LMNR_FORCE_HTTP") or "").lower() in (
        "true",
        "1",
        "yes",
        "on",
    )
    instruments_env = get_env("LMNR_INSTRUMENTS")
    instruments = None
    if instruments_env is not None:
        instruments = set()
        for value in map(str.strip, instruments_env.split(",")):
            if not value:
                continue
            try:
                instruments.add(Instruments(value))
            except ValueError:
                logger.warning("Ignoring invalid LMNR_INSTRUMENTS value %r", value)

    if _is_otel_backend_laminar():
        Laminar.initialize(
            base_url=base_url,
            http_port=_get_int_env("LMNR_HTTP_PORT"),
            grpc_port=_get_int_env("LMNR_GRPC_PORT"),
            instruments=instruments,
            force_http=force_http,
        )
    else:
        # 不要为非分层后端启用浏览器会话重放
        Laminar.initialize(
            instruments=instruments,
            disabled_instruments=[
                Instruments.BROWSER_USE_SESSION,
                Instruments.PATCHRIGHT,
                Instruments.PLAYWRIGHT,
            ],
            force_http=force_http,
        )


def observe[**P, R](
    *,
    name: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    ignore_input: bool = False,
    ignore_output: bool = False,
    span_type: Literal["DEFAULT", "LLM", "TOOL"] = "DEFAULT",
    ignore_inputs: list[str] | None = None,
    input_formatter: Callable[P, str] | None = None,
    output_formatter: Callable[[R], str] | None = None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    preserve_global_context: bool = False,
    **kwargs: dict[str, Any],
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """延迟解析观察装饰器。

    当未启用可观察性时，修饰函数将作为传递运行，无需 `lmnr` 导入。 可观察性启用后的第
    一次调用导入 `lmnr` 并缓存包装的函数。
    """

    def _build_wrapped(func: Any) -> Any:
        from lmnr import observe as laminar_observe

        return laminar_observe(
            name=name,
            session_id=session_id,
            user_id=user_id,
            ignore_input=ignore_input,
            ignore_output=ignore_output,
            span_type=span_type,
            ignore_inputs=ignore_inputs,
            input_formatter=input_formatter,
            output_formatter=output_formatter,
            metadata=metadata,
            tags=tags,
            preserve_global_context=preserve_global_context,
            **kwargs,
        )(func)

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        wrapped: Any = None

        # 在装饰时在异步-ness 上进行分支，以便 inspect.iscoroutinefunction(decorated) 与
        # 原始内容匹配。 围绕异步函数的同步包装器将对像 run_async 这样内省该函数的调用者
        # 隐藏其异步性。
        #
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **fkwargs: P.kwargs) -> Any:
                nonlocal wrapped
                if wrapped is not None:
                    with _maybe_use_root_span(args):
                        return await wrapped(*args, **fkwargs)
                if not should_enable_observability():
                    return await func(*args, **fkwargs)
                wrapped = _build_wrapped(func)
                with _maybe_use_root_span(args):
                    return await wrapped(*args, **fkwargs)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **fkwargs: P.kwargs) -> R:
            nonlocal wrapped
            if wrapped is not None:
                with _maybe_use_root_span(args):
                    return wrapped(*args, **fkwargs)
            if not should_enable_observability():
                return func(*args, **fkwargs)
            wrapped = _build_wrapped(func)
            with _maybe_use_root_span(args):
                return wrapped(*args, **fkwargs)

        return sync_wrapper

    return decorator


# 首先保留所有者，以便观察可以恢复其会话根跨度。
def _return_tool_result(owner: object, tool_input: Any, tool_output: Any) -> Any:
    _ = owner, tool_input
    return tool_output


def record_tool_result(
    owner: object,
    *,
    name: str,
    tool_call_id: str,
    tool_input: Any,
    tool_output: Any,
) -> None:
    if not should_enable_observability():
        return
    observe(
        name=name,
        span_type="TOOL",
        ignore_inputs=["owner", "tool_output"],
        metadata={"tool_call_id": tool_call_id},
    )(_return_tool_result)(owner, tool_input, tool_output)


def should_enable_observability() -> bool:
    global _observability_enabled
    if _observability_enabled:
        return True
    if any(get_env(key) for key in _OBSERVABILITY_ENV_KEYS):
        _observability_enabled = True
        return True
    # 如果用户已经自己导入了 lmnr，则仅探测 Laminar.is_initialized() - 否则在这里导入它
    # 会破坏延迟加载的目的。
    #
    if "lmnr" in sys.modules:
        from lmnr import Laminar

        if Laminar.is_initialized():
            _observability_enabled = True
            return True
    return False


def _is_otel_backend_laminar():
    """简单的启发式检查 OTEL 后端是否为层流。
    Caveat: 如果另一个后端使用相同的值，这仍然是 True
    身份验证方案，用户使用LMNR_PROJECT_API_KEY而不是OTEL_HEADERS进行身份验证。
    """
    key = get_env("LMNR_PROJECT_API_KEY")
    return key is not None and key != ""


_ROOT_SPAN_ATTR: Final[str] = "_observability_root_span"


class RootSpan:
    """由单个对象 (e.g. 对话）。

    跨度是通过 ``Laminar.start_span`` 创建的（不将跨度附加到当前的 OpenTelemetry 上下
    文）。 为了使 Span 成为嵌套
    ``@observe`` 修饰调用的父级，此模块中的 ``observe`` 包装器在每个入口处通过
    ``Laminar.use_span`` 重新附加 Span。
     这允许根跨度跨越 asyncio 任务、线程和原生 ``contextvars`` 传播失败的进程。

    ``Laminar.start_active_span`` API 以前用于此目的，但其文档字符串明确警告：

        “以不同的异步上下文结束开始的跨度会产生
         意想不到的结果。 …尽可能使用 Laminar.start_span + Laminar.use_span。”

    empirically，``start_active_span`` 产生了上下文的[60%] 的对话（或无``session_id``
     的
    ``conversation.send_message`` / ``conversation.run`` 跟踪），因此我们切换到推荐的
    模式。
    """

    def __init__(
        self,
        name: str,
        session_id: str | None = None,
        user_id: str | None = None,
        attributes: Mapping[str, TraceMetadataValue] | None = None,
        metadata: dict[str, TraceMetadataValue] | None = None,
        tags: list[str] | None = None,
        parent_span_context: str | None = None,
    ) -> None:
        from lmnr import Laminar

        parent = None
        if parent_span_context:
            with contextlib.suppress(Exception):
                parent = Laminar.deserialize_span_context(parent_span_context)

        # ``start_span`` 返回一个跨度，但不将其附加为当前 OTel 上下文； 我们将通过
        # ``use_span`` 在每个入口上恢复它。
        #
        if parent is not None:
            self.span = Laminar.start_span(name, parent_span_context=parent)
        else:
            self.span = Laminar.start_span(name)
        if attributes:
            with contextlib.suppress(Exception):
                for key, value in attributes.items():
                    self.span.set_attribute(key, value)
        if session_id or user_id or metadata or tags:
            # 这些跟踪/跨度助手需要一个活动跨度； 简单输入范围上下文以应用会话级可观测性
            # 数据。
            #
            with contextlib.suppress(Exception):
                with Laminar.use_span(
                    self.span,
                    # 如果辅助者加注，请勿将跨度标记为 ERROR。
                    record_exception=False,
                    set_status_on_exception=False,
                ):
                    if session_id:
                        Laminar.set_trace_session_id(session_id)
                    if user_id:
                        Laminar.set_trace_user_id(user_id)
                    if metadata:
                        # dict 是不变量： dict[str, TraceMetadataValue] 不能在没有强制转
                        # 换的情况下分配给 dict[str, Any] 。
                        #
                        Laminar.set_trace_metadata(cast(dict[str, Any], metadata))
                    if tags:
                        Laminar.set_span_tags(tags)
        self._ended = False

    def end(self) -> None:
        if self._ended:
            return
        self._ended = True
        try:
            if self.span and self.span.is_recording():
                self.span.end()
        except Exception:
            logger.debug("Error ending observability root span", exc_info=True)


def start_root_span(
    name: str,
    session_id: str | None = None,
    user_id: str | None = None,
    attributes: Mapping[str, TraceMetadataValue] | None = None,
    metadata: dict[str, TraceMetadataValue] | None = None,
    tags: list[str] | None = None,
    parent_span_context: str | None = None,
) -> RootSpan | None:
    """为所属对象创建长期存在的根跨度。

    如果未启用可观察性，则返回 ``None``。
    """
    if not should_enable_observability():
        return None
    try:
        return RootSpan(
            name,
            session_id=session_id,
            user_id=user_id,
            attributes=attributes,
            metadata=metadata,
            tags=tags,
            parent_span_context=parent_span_context,
        )
    except Exception:
        logger.debug("Failed to create observability root span", exc_info=True)
        return None


def end_root_span(root: RootSpan | None) -> None:
    """结束先前启动的根跨度。 使用 ``None`` 可以安全通话。"""
    if root is None:
        return
    root.end()


def start_child_span(
    root: RootSpan | None,
    name: str,
    tags: list[str] | None = None,
) -> None:
    """在对话根跨度下创建并立即结束子跨度。"""
    if root is None or root.span is None:
        return
    try:
        from lmnr import Laminar

        with Laminar.use_span(
            root.span,
            record_exception=False,
            set_status_on_exception=False,
        ):
            with Laminar.start_as_current_span(name=name):
                if tags:
                    Laminar.set_span_tags(tags)
    except Exception:
        logger.debug("Failed to create observability child span", exc_info=True)


@contextlib.contextmanager
def llm_call_span(name: str) -> Iterator[Any]:
    """打开一个在一次 LLM 调用期间保持当前状态的跨度。

    lmnr 的 LiteLLM 检测用 ``Laminar.start_span``（与 OTel 上下文分离）构建其跨度，并
    在之前以 ``finally`` 结束
    ``litellm.completion`` 返回，因此之后无法将属性附加到它 - OTel 会默默地删除对结束
    跨度的写入。 这个跨度是
    *current* 当调用运行时，所以 lmnr 的跨度嵌套在它下面，并且它
    保持开放足够长的时间，以便 Telemetry 附加权威成本。

    当可观察性被禁用时，产量 ``None``，因此调用者保持无分支。
    """
    if not should_enable_observability():
        yield None
        return
    try:
        from lmnr import Laminar

        cm = Laminar.start_as_current_span(name=name, span_type="LLM")
    except Exception:
        logger.debug("Failed to open LLM observability span", exc_info=True)
        yield None
        return
    with cm as span:
        yield span


# 由软件-智能体-SDK#4010 在父级 `task` TOOL 跨度上设置的跟踪元数据键； 当存在时复制到分
# 离的委托跟踪上，因此原始工具调用仅从委托的跟踪中可见。
#
_TOOL_CALL_ID_META_KEY: Final[str] = "tool_call_id"


@contextlib.contextmanager
def detached_delegate_context() -> Iterator[dict[str, TraceMetadataValue]]:
    """清除环境范围，以便在该块内构建对话
    启动一个真正新的层流跟踪，而不是 ``RootSpan`` 默默地加入当前活动的任何跨度。

    ``Laminar.start_span`` 没有明确的 ``context=`` 父级到环境跨度 - 它的“隔离上下文”
    帮助器只返回当前的任何内容。 层流通过其
    OWN 隔离跟踪“电流”跨度
    ``ContextVar`` (``lmnr...tracing.context._ISOLATED_RUNTIME_CONTEXT``, 与标准分开
    ``opentelemetry.context`` 1. 所以，添加一个空的/没有父节点上下文通过标准 API (as
    ``RootSpan`` does for
    cross-线程重连操作在这里没有效果 ``Laminar.use_span`` 这是唯一一个更新两个的调用
    。 Pushing ``INVALID_SPAN`` 通
    过它实际上切断了链接，所以是它子智能体在它的父级中同步构建的对话 ``task``  TOOL
    span (see TaskManager它会自己启动跟踪，而不是继
    承父级的（软件）智能体-SDK#4365).

    生成回溯到断开父级 span 的 delegate 的跟踪元数据``delegate.parent_trace_id``
    /``delegate.parent_span_id``加上尽力而为 ``tool_call_id`` 从父元素中复制的 TOOL
    为调用者合并到委托的
    ``observability_metadata``. 如果没有活动范围，或者可观察性被禁用，则生成一个空字
    典。
    """
    if not should_enable_observability():
        yield {}
        return
    try:
        from lmnr import Laminar
        from opentelemetry import trace as otel_trace

        parent = Laminar.get_laminar_span_context()
    except Exception:
        logger.debug("Failed to capture parent span for delegate", exc_info=True)
        yield {}
        return

    link: dict[str, TraceMetadataValue] = {}
    if parent is not None:
        link["delegate.parent_trace_id"] = str(parent.trace_id)
        link["delegate.parent_span_id"] = str(parent.span_id)
        tool_call_id = (parent.metadata or {}).get(_TOOL_CALL_ID_META_KEY)
        if tool_call_id:
            link[_TOOL_CALL_ID_META_KEY] = tool_call_id

    # 仅保护 *entering* Laminar.use_span（下面的 ``with`` 块内引发的调用者异常必须正常传
    # 播，而不是在这里被吞噬）。
    #
    with contextlib.ExitStack() as stack:
        try:
            stack.enter_context(
                Laminar.use_span(
                    otel_trace.INVALID_SPAN,
                    record_exception=False,
                    set_status_on_exception=False,
                )
            )
        except Exception:
            logger.debug("Failed to detach ambient span for delegate", exc_info=True)
        yield link


@contextlib.contextmanager
def _maybe_use_root_span(args: tuple[Any, ...]) -> Iterator[None]:
    """如果第一个位置参数拥有 ``RootSpan``，则重新附加它。

    这就是将 ``@observe`` 修饰的方法（从任意异步任务或线程调用）与会话的长期根跨度联
    系起来的原因。
    """
    root = _root_span_from_args(args)
    if root is None or root.span is None:
        yield
        return
    try:
        from lmnr import Laminar
    except Exception:
        yield
        return
    try:
        span_context = Laminar.use_span(root.span)
        span_context.__enter__()
    except Exception:
        # 永远不要让可观察性错误破坏包装的函数。
        logger.debug("use_span failed; calling without parent", exc_info=True)
        yield
        return

    exc_info = (None, None, None)
    try:
        yield
    except BaseException:
        exc_info = sys.exc_info()
        raise
    finally:
        with contextlib.suppress(Exception):
            span_context.__exit__(*exc_info)


def _root_span_from_args(args: tuple[Any, ...]) -> RootSpan | None:
    if not args:
        return None
    candidate = getattr(args[0], _ROOT_SPAN_ATTR, None)
    if isinstance(candidate, RootSpan):
        return candidate
    return None


def init_laminar_for_external():
    """为外部调用者初始化 Laminar 并返回父跨度上下文。

    这是一个方便的集成函数（e.g.、GitHub、Slack Webhook），需要：
    1. 如果设置了环境变量，则初始化 Laminar（通过 maybe_init_laminar）
    2. 从外部触发器捕获父范围上下文

    Returns:
        如果启用了可观察性，则父范围为上下文，否则为 None。

    Example:
        ```python
        from openhands.sdk.observability import init_laminar_for_external
        from lmnr import Laminar

        # 开始处理外部事件时（Webhook等）
        laminar_span_context = init_laminar_for_external()

        if laminar_span_context:
            with Laminar.start_as_current_span(
                name='my-integration',
                parent_span_context=laminar_span_context,
            ):
                # 工作 - 痕迹将是外部触发器的子项
                await do_something()
        else:
            await do_something()
        ```
    """
    maybe_init_laminar()
    if should_enable_observability():
        from lmnr import Laminar

        return Laminar.get_laminar_span_context()
    return None
