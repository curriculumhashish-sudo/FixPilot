"""server_started/stopped 跨 deferred-init 路径的生命周期。

回归两项审查结果的覆盖范围：

* 构建遥测接收器后失败的 ``/api/init`` 不得发出
  ``server_started``，并且重试必须恰好发出 1； 和
* ``emit_server_started`` 是幂等的，因此任何调用路径都不能产生不配对的第二个启动。
"""

from types import SimpleNamespace

import pytest

import openhands.agent_server.telemetry.service as service_mod
from openhands.agent_server.config import Config
from openhands.agent_server.init_router import InitRequest, InitService
from openhands.agent_server.telemetry import models as m
from openhands.agent_server.telemetry.factory import (
    DiagnosticEventFactory,
    build_runtime_properties,
)


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


@pytest.fixture
def recording(monkeypatch):
    """安装记录接收器和真实工厂，并重置生命周期状态。"""
    service_mod.reset_telemetry_sink()
    sink = _RecordingSink()
    monkeypatch.setattr(service_mod, "_telemetry_sink", sink)
    monkeypatch.setattr(
        service_mod,
        "_event_factory",
        DiagnosticEventFactory(runtime=build_runtime_properties(deferred_init=True)),
    )
    yield sink
    service_mod.reset_telemetry_sink()


def _reset_singletons():
    from openhands.agent_server import bash_service, conversation_service

    conversation_service._conversation_service = None
    bash_service._bash_event_service = None


async def test_emit_server_started_is_idempotent(recording):
    service_mod.emit_server_started()
    service_mod.emit_server_started()
    service_mod.emit_server_started()
    assert recording.events == [m.EventName.SERVER_STARTED]


async def test_started_then_stopped_pairs(recording):
    service_mod.emit_server_started()
    service_mod.emit_server_stopped()
    service_mod.emit_server_stopped()  # 没有双停
    assert recording.events == [m.EventName.SERVER_STARTED, m.EventName.SERVER_STOPPED]


async def test_failed_init_emits_no_start_and_retry_emits_exactly_one(
    recording, tmp_path, monkeypatch
):
    """核心回归：不能为失败的 init 发出启动。

    接收器是在会话服务之前构建的，因此 get_instance() 中的故障在遥测设置之后发生。 旧
    代码在那里发出 server_started，留下一个未配对的开始
    ，并让重试发出第二个开始。
    """
    _reset_singletons()
    base = Config(
        deferred_init=True,
        conversations_path=tmp_path / "convs",
        bash_events_dir=tmp_path / "bash",
    )
    app = SimpleNamespace(state=SimpleNamespace(config=base))
    svc = InitService(app, base_config=base)  # type: ignore[arg-type]

    # 水槽在initialize()内（重新）建造； 将我们的记录接收器保持在适当的位置，以便无论如
    # 何都能观察到发射路径。
    #
    monkeypatch.setattr(service_mod, "build_telemetry_sink", _keep_sink(recording))
    monkeypatch.setattr(service_mod, "shutdown_telemetry_sink", _noop_async)
    import openhands.agent_server.init_router as init_mod

    monkeypatch.setattr(init_mod, "build_telemetry_sink", _keep_sink(recording))
    monkeypatch.setattr(init_mod, "shutdown_telemetry_sink", _noop_async)

    # 第一次尝试：在水槽建成后强制失败。
    boom = {"raise": True}
    real_get_instance = init_mod.ConversationService.get_instance

    def _maybe_boom(config):
        if boom["raise"]:
            raise RuntimeError("get_instance failed")
        return real_get_instance(config)

    monkeypatch.setattr(init_mod.ConversationService, "get_instance", _maybe_boom)

    from fastapi import HTTPException

    try:
        with pytest.raises(HTTPException):
            await svc.initialize(InitRequest())
        assert svc.state == "dormant", "failed init should roll back to dormant"
        assert recording.events == [], "a failed init must not emit server_started"

        # 重试成功。
        boom["raise"] = False
        result = await svc.initialize(InitRequest())
        assert result.state == "ready"
        assert recording.events == [m.EventName.SERVER_STARTED], (
            "retry must emit exactly one server_started"
        )
    finally:
        await svc.teardown()
        _reset_singletons()


def _keep_sink(sink):
    async def _build(_config):
        service_mod._telemetry_sink = sink
        return sink

    return _build


async def _noop_async(*_args, **_kwargs):
    return None
