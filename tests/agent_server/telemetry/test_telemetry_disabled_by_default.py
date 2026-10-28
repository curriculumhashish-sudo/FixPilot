"""默认关闭行为，包括从不导入供应商 SDK。"""

import subprocess
import sys
from uuid import uuid4

from fastapi.testclient import TestClient

from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config, TelemetrySpec
from openhands.agent_server.telemetry import (
    NoOpTelemetrySink,
    build_telemetry_sink,
    get_event_factory,
    get_telemetry_sink,
)
from openhands.agent_server.telemetry.sanitizer import pseudonymize


def test_default_config_yields_a_noop_sink(temp_persistence_dir):
    assert isinstance(get_telemetry_sink(), NoOpTelemetrySink)
    assert get_telemetry_sink().enabled is False


async def test_building_from_a_default_config_stays_a_noop(temp_persistence_dir):
    sink = await build_telemetry_sink(Config(static_files_path=None))
    assert isinstance(sink, NoOpTelemetrySink)
    assert sink.enabled is False


async def test_building_sink_carries_configured_deployment_kind(
    temp_persistence_dir,
):
    sink = await build_telemetry_sink(
        Config(
            static_files_path=None, telemetry=TelemetrySpec(deployment_kind="remote")
        )
    )
    try:
        factory = get_event_factory()
        assert factory is not None
        assert factory.runtime.deployment_kind == "remote"
    finally:
        await sink.aclose()


async def test_salt_falls_back_to_the_secret_key_as_documented(
    config_factory, secret_key
):
    """如果没有盐，参考文献将由机密键作为键，如 `salt` 文档。"""
    description = TelemetrySpec.model_fields["salt"].description or ""
    assert "OH_SECRET_KEY" in description
    assert "linkable across restarts" in description

    conversation_id = uuid4()
    sink = await build_telemetry_sink(config_factory())
    try:
        factory = get_event_factory()
        assert factory is not None
        assert factory.conversation_ref(conversation_id) == pseudonymize(
            conversation_id.bytes, secret_key
        )
    finally:
        await sink.aclose()


async def test_opt_in_without_an_api_key_stays_inactive(config_factory):
    """没有钥匙就意味着没有出口商。"""
    sink = await build_telemetry_sink(config_factory("posthog"))
    assert isinstance(sink, NoOpTelemetrySink)


async def test_kill_switch_short_circuits_delivery(config_factory, monkeypatch):
    monkeypatch.setenv("DO_NOT_TRACK", "1")
    sink = await build_telemetry_sink(
        config_factory("posthog", posthog_api_key="phc_test")
    )
    assert sink.enabled is False


def test_importing_the_telemetry_package_does_not_import_posthog():
    """默认情况下，可选依赖项必须远离导入路径。

    关于范围的注意事项：这断言 * 这个包 * 不导入 posthog，而不是在完整服务器启动后
    ``sys.modules`` 中不存在 ``posthog``。 它
    不能断言后者，因为不相关的预先存在的
    ``browser-use`` 工具预加载服务启动时，依赖项会传递导入 posthog。 测试用例——即，一
    个没有启用遥测功能的服务器 SDK 从未在 * 上代表
    * 追踪遥测 —— 精确地通过检查我们的自定义导出器模块是否保持未导入。

    在子进程中运行，因此测试会话中其他位置的导入无法屏蔽回归。
    """
    script = """
import sys

import openhands.agent_server.telemetry as t
from openhands.agent_server.config import Config, TelemetrySpec
from openhands.agent_server.api import create_app

assert "posthog" not in sys.modules, "importing telemetry pulled in posthog"

create_app(Config(static_files_path=None, session_api_keys=[]))
assert "openhands.agent_server.telemetry.posthog_exporter" not in sys.modules, (
    "the exporter module was imported with telemetry disabled"
)
print("OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert "OK" in result.stdout, (
        f"subprocess failed\nstdout:{result.stdout}\nstderr:{result.stderr}"
    )


async def test_disabled_server_never_constructs_the_exporter(temp_persistence_dir):
    """补充导入测试：也没有构建导出器对象。"""
    import openhands.agent_server.telemetry.service as service_mod

    built: list[object] = []

    class _Tripwire:
        def __init__(self, *a, **k):
            built.append(self)

    monkeypatched = getattr(service_mod, "PostHogExporter", None)
    assert monkeypatched is None, "exporter must not be a module-level attribute"

    await build_telemetry_sink(Config(static_files_path=None))
    assert built == []


async def test_conversation_service_reads_the_live_sink_not_a_captured_one(
    tmp_path, monkeypatch
):
    """Regression: 对话遥测必须控制 *live* 进程接收器。

    ``ConversationService`` 在导入时（``sockets.py`` 模块范围）实例化，在生命周期构建
    遥测接收器之前。 如果门读取在构造时捕获的接
    收器，则每次对话都会看到预初始化 NoOp，并且无论是否同意，都不会发出任何内容。 在
    sink 仍然是 NoOp 时构建服务，之后启用 telemetry，并断言
    一个新对话仍然附带订阅者并发出 ``conversation_created``。
    """
    from uuid import uuid4

    import openhands.agent_server.telemetry.service as service_mod
    from openhands.agent_server.conversation_service import ConversationService
    from openhands.agent_server.models import StoredConversation
    from openhands.agent_server.telemetry import models as m
    from openhands.agent_server.telemetry.factory import (
        DiagnosticEventFactory,
        build_runtime_properties,
    )
    from openhands.sdk.security.confirmation_policy import NeverConfirm
    from openhands.sdk.workspace import LocalWorkspace

    # 1. 在遥测仍然是预初始化 NoOp 时构建服务 — 通过在导入时构建服务来强制执行精确的顺序
    #  sockets.py。
    #
    service_mod.reset_telemetry_sink()
    assert isinstance(get_telemetry_sink(), NoOpTelemetrySink)
    service = ConversationService(conversations_dir=tmp_path)

    # 2. 稍后启用遥测（生命周期构建/同意授予）。
    class _RecordingSink:
        enabled = True

        def __init__(self):
            self.events: list[str] = []

        def emit(self, event):
            self.events.append(str(event.event_name))

        def on_decision_changed(self, decision):
            pass

        async def aclose(self):
            pass

    sink = _RecordingSink()
    monkeypatch.setattr(service_mod, "_telemetry_sink", sink)
    monkeypatch.setattr(
        service_mod,
        "_event_factory",
        DiagnosticEventFactory(runtime=build_runtime_properties(deferred_init=False)),
    )

    # 3. 一个全新的对话必须附加订阅者并开始发出，读取现在启用的接收器而不是步骤 1 中存在
    # 的 NoOp。
    #
    class _FakeEventService:
        def __init__(self):
            self.subscribers: list[object] = []
            self._conversation = None

        async def subscribe_to_events(self, subscriber):
            self.subscribers.append(subscriber)

    event_service = _FakeEventService()
    stored = StoredConversation(
        id=uuid4(),
        workspace=LocalWorkspace(working_dir=str(tmp_path)),
        confirmation_policy=NeverConfirm(),
        initial_message=None,
        metrics=None,
    )

    await service._maybe_subscribe_telemetry(
        event_service,  # type: ignore[arg-type]
        stored,
        is_new_conversation=True,
    )

    assert len(event_service.subscribers) == 1
    assert m.EventName.CONVERSATION_CREATED in sink.events


def test_app_exposes_a_sink_on_state_after_startup(temp_persistence_dir):
    with TestClient(create_app(Config(static_files_path=None))) as client:
        sink = client.app.state.telemetry_sink  # type: ignore[attr-defined]
        assert isinstance(sink, NoOpTelemetrySink)


def test_server_lifecycle_events_are_emitted_when_enabled(
    temp_persistence_dir, monkeypatch
):
    """server_started/stopped 表示遥测处于活动状态时的寿命。"""
    import openhands.agent_server.telemetry.service as service_mod
    from openhands.agent_server.telemetry import models as m

    emitted: list[str] = []

    class _Sink:
        enabled = True

        def emit(self, event):
            emitted.append(event.event_name)

        def on_consent_changed(self, consent):
            pass

        async def aclose(self):
            pass

    monkeypatch.setattr(service_mod, "get_telemetry_sink", lambda: _Sink())
    monkeypatch.setattr(
        service_mod,
        "_event_factory",
        service_mod.DiagnosticEventFactory(
            runtime=service_mod.build_runtime_properties(deferred_init=False)
        ),
    )

    with TestClient(create_app(Config(static_files_path=None))):
        pass

    assert emitted == [m.EventName.SERVER_STARTED, m.EventName.SERVER_STOPPED]


def test_deferred_pod_does_not_emit_an_unpaired_server_stopped(
    temp_persistence_dir, monkeypatch
):
    """Regression: 禁用遥测功能的暖池吊舱靴子。

    ``server_started`` 是在 POST /api/init 重建接收器之后由 InitService 发出的，而不
    是在启动时发出的。 因此，必须始终不
    初始化的pod也不发出任何事件——此前它发出一个``server_stopped``，这破坏了可用性和会
    话指标。
    """
    import openhands.agent_server.telemetry.service as service_mod

    emitted: list[str] = []

    class _Sink:
        enabled = True

        def emit(self, event):
            emitted.append(event.event_name)

        def on_consent_changed(self, consent):
            pass

        async def aclose(self):
            pass

    monkeypatch.setattr(service_mod, "get_telemetry_sink", lambda: _Sink())
    monkeypatch.setattr(
        service_mod,
        "_event_factory",
        service_mod.DiagnosticEventFactory(
            runtime=service_mod.build_runtime_properties(deferred_init=True)
        ),
    )

    with TestClient(create_app(Config(static_files_path=None, deferred_init=True))):
        pass

    assert emitted == [], f"deferred pod emitted unpaired lifecycle events: {emitted}"


async def test_telemetry_init_does_not_hijack_the_settings_store_singleton(
    temp_persistence_dir, monkeypatch
):
    """Regression: 遥测必须准备设置存储 WITH 配置。

    ``get_settings_store`` 是一个单例，其密码由第一次调用固定。 遥测在生命周期启动期
    间初始化，因此这里的无参数调用将使整个进程写入机密并禁用加密
    。
    """
    from base64 import urlsafe_b64encode

    from pydantic import SecretStr

    import openhands.agent_server.telemetry.posthog_exporter as pe
    from openhands.agent_server.config import Config, TelemetrySpec
    from openhands.agent_server.persistence.store import get_settings_store

    class _FakeExporter:
        async def send(self, events):
            pass

        async def aclose(self):
            pass

    monkeypatch.setattr(pe, "PostHogExporter", lambda *a, **k: _FakeExporter())
    config = Config(
        static_files_path=None,
        conversations_path=temp_persistence_dir / "workspace/conversations",
        secret_key=SecretStr(urlsafe_b64encode(b"a" * 32).decode("ascii")),
        telemetry=TelemetrySpec(
            exporter="posthog", posthog_api_key=SecretStr("phc_test")
        ),
    )

    sink = await build_telemetry_sink(config)
    try:
        store = get_settings_store(config)
        assert store.cipher is not None, (
            "telemetry primed the settings store without a cipher; secrets "
            "would be persisted unencrypted process-wide"
        )
        assert store.persistence_dir == temp_persistence_dir
    finally:
        await sink.aclose()
