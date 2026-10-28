"""全流程遥测接收器的构造和生命周期。

镜像 ``persistence/store.py`` 使用的单例模式，因此测试可以在案例之间重置进程状态。

这里的一切都退化而不是失败：缺少的可选依赖、未配置的导出器、或者设置存储读取错误都会
导致无操作的汇流点。 分析绝不能阻止服务器启动。
"""

import asyncio
from functools import partial
from typing import Any

from openhands.agent_server.config import Config
from openhands.agent_server.telemetry.factory import (
    DiagnosticEventFactory,
    build_runtime_properties,
)
from openhands.agent_server.telemetry.models import (
    EventName,
    ServerLifecycleProperties,
)
from openhands.agent_server.telemetry.policy import TelemetryDecision, resolve
from openhands.agent_server.telemetry.sink import (
    BufferedTelemetrySink,
    NoOpTelemetrySink,
    TelemetryExporter,
    TelemetrySink,
)
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

_telemetry_sink: TelemetrySink | None = None
_event_factory: DiagnosticEventFactory | None = None
_server_started_emitted = False


def _read_misc_settings_sync(config: Config) -> dict[str, Any]:
    from openhands.agent_server.persistence.store import get_settings_store

    # 必须通过配置：存储单例由第一次调用修复，并且此处的无参数调用将禁用整个密码进程。
    #
    settings = get_settings_store(config).load()
    return dict(settings.misc_settings) if settings is not None else {}


async def _read_decision(config: Config) -> TelemetryDecision:
    """从已持久化设置中解决同意问题，关闭事件循环。"""
    misc = await asyncio.to_thread(_read_misc_settings_sync, config)
    return resolve(misc)


def _build_exporter(config: Config) -> TelemetryExporter | None:
    """按类型选择导出器，如果无法构建，则选择 ``None``。"""
    spec = config.telemetry

    if spec.exporter == "posthog":
        api_key = (
            spec.posthog_api_key.get_secret_value()
            if spec.posthog_api_key is not None
            else None
        )
        if not api_key:
            logger.info("Telemetry exporter is 'posthog' but no API key is configured.")
            return None
        try:
            # 惰性：唯一引入可选供应商依赖项的行。
            from openhands.agent_server.telemetry.posthog_exporter import (
                PostHogExporter,
            )

            return PostHogExporter(api_key, host=spec.posthog_host)
        except ImportError:
            logger.warning(
                "Telemetry exporter is 'posthog' but the extra is not installed; "
                "telemetry is inactive. Install openhands-agent-server[posthog]."
            )
            return None

    if spec.exporter == "http":
        if not spec.http_endpoint:
            logger.info("Telemetry exporter is 'http' but no endpoint is configured.")
            return None
        from openhands.agent_server.telemetry.http_exporter import HttpExporter

        return HttpExporter(
            spec.http_endpoint,
            token=(
                spec.http_token.get_secret_value()
                if spec.http_token is not None
                else None
            ),
        )

    return None


async def build_telemetry_sink(config: Config) -> TelemetrySink:
    """为 ``config`` 构建接收器，如果遥测无法运行，则构建无操作。"""
    global _telemetry_sink, _event_factory

    spec = config.telemetry
    _event_factory = DiagnosticEventFactory(
        runtime=build_runtime_properties(
            deferred_init=config.deferred_init,
            deployment_kind=spec.deployment_kind,
        ),
        salt=(
            spec.salt.get_secret_value()
            if spec.salt is not None
            else (
                config.secret_key.get_secret_value()
                if config.secret_key is not None
                else None
            )
        ),
    )

    try:
        exporter = _build_exporter(config)
    except Exception as exc:
        logger.warning(
            "Telemetry exporter could not be constructed (%s); telemetry is inactive.",
            type(exc).__name__,
        )
        exporter = None

    if exporter is None:
        _telemetry_sink = NoOpTelemetrySink()
        return _telemetry_sink

    try:
        decision = await _read_decision(config)
    except Exception as exc:
        # 无法读取的设置无法关闭。
        logger.debug("Could not read telemetry consent: %s", type(exc).__name__)
        decision = resolve(None)

    sink = BufferedTelemetrySink(
        exporter,
        decision=decision,
        decision_reader=partial(_read_decision, config),
        max_queue_size=spec.max_queue_size,
        event_buffer_size=spec.event_buffer_size,
        flush_delay=spec.flush_delay,
        num_retries=spec.num_retries,
        retry_delay=spec.retry_delay,
    )
    sink.start()

    logger.info(
        "Telemetry initialised: exporter=%s enabled=%s (%s)",
        spec.exporter,
        decision.enabled,
        decision.reason,
    )
    _telemetry_sink = sink
    return sink


def get_telemetry_sink() -> TelemetrySink:
    """返回进程接收器，如果从未构建过则返回无操作。"""
    if _telemetry_sink is None:
        return NoOpTelemetrySink()
    return _telemetry_sink


def get_event_factory() -> DiagnosticEventFactory | None:
    return _event_factory


async def shutdown_telemetry_sink() -> None:
    """关闭水槽，排出仍允许发送的内容。"""
    global _telemetry_sink
    sink = _telemetry_sink
    _telemetry_sink = None
    if sink is not None:
        try:
            await sink.aclose()
        except Exception as exc:
            logger.debug("Telemetry shutdown failed: %s", type(exc).__name__)


def reset_telemetry_sink() -> None:
    """无需等待即可删除进程状态。 用于测试。"""
    global _telemetry_sink, _event_factory, _server_started_emitted
    _telemetry_sink = None
    _event_factory = None
    _server_started_emitted = False


def emit_server_started() -> None:
    """如果遥测处于活动状态，则发出 ``server_started`` 一次。

    Idempotent: 当启动已经完成时第二次调用是无操作，
    因此，在重试路径上运行的调用者无法产生不配对的第二个开始。
    """
    global _server_started_emitted
    if _server_started_emitted:
        return
    if _emit_lifecycle(EventName.SERVER_STARTED):
        _server_started_emitted = True


def emit_server_stopped() -> None:
    """发出 ``server_stopped``，但前提是实际发出了开始。"""
    global _server_started_emitted
    if not _server_started_emitted:
        return
    _server_started_emitted = False
    _emit_lifecycle(EventName.SERVER_STOPPED)


def _emit_lifecycle(event_name: EventName) -> bool:
    """发出服务器生命周期事件。 返回是否实际发送。"""
    try:
        sink = get_telemetry_sink()
        if not sink.enabled:
            return False
        factory = get_event_factory()
        if factory is None:
            return False
        sink.emit(factory.build(event_name, ServerLifecycleProperties()))
        return True
    except Exception:
        logger.debug("Could not emit server lifecycle telemetry", exc_info=True)
        return False


def notify_misc_settings_changed(misc_settings: dict[str, Any] | None) -> None:
    """设置写入后重新解决同意。

    设置更新路径现在是同意更改的唯一方式。 撤销必须在请求返回之前生效，并且必须丢弃队
    列。
    """
    sink = _telemetry_sink
    if sink is None:
        return
    try:
        sink.on_decision_changed(resolve(misc_settings))
    except Exception as exc:
        logger.debug("Consent propagation failed: %s", type(exc).__name__)
