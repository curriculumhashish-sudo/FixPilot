"""通过 ``PATCH /api/settings`` 书面同意。

没有专门的遥测同意端点。 画布书写
``misc_settings.telemetry.consent`` 与任何其他前端首选项一样，设置更新路径在返回之前
重新解析遥测决策。
"""

import pytest
from fastapi.testclient import TestClient

from openhands.agent_server.api import create_app
from openhands.agent_server.persistence.store import get_settings_store
from openhands.agent_server.telemetry.policy import TelemetryDecision, resolve


SETTINGS_URL = "/api/settings"


def diff(consent: str) -> dict:
    return {"misc_settings_diff": {"telemetry": {"consent": consent}}}


@pytest.fixture
def client(config_factory):
    return TestClient(create_app(config_factory()))


class RecordingSink:
    """代表实时接收器来观察传播情况。"""

    def __init__(self, enabled: bool = True):
        self._enabled = enabled
        self.events: list = []
        self.decisions: list[TelemetryDecision] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def emit(self, event):
        self.events.append(event)

    def on_decision_changed(self, decision: TelemetryDecision) -> None:
        self.decisions.append(decision)
        self._enabled = decision.enabled
        if not decision.enabled:
            self.events.clear()

    async def aclose(self):
        pass


# ── 持久化 ───────────────────────────────────────────────────────────


def test_consent_is_written_and_read_through_misc_settings(client, config_factory):
    with client as c:
        assert c.patch(SETTINGS_URL, json=diff("granted")).status_code == 200
        body = c.get(SETTINGS_URL).json()

    assert body["misc_settings"]["telemetry"]["consent"] == "granted"

    settings = get_settings_store(config_factory()).load()
    assert settings is not None
    assert resolve(settings.misc_settings, env={}).enabled is True


def test_consent_survives_a_store_reset(client, config_factory, temp_persistence_dir):
    from openhands.agent_server.persistence.store import reset_stores

    with client as c:
        c.patch(SETTINGS_URL, json=diff("granted"))

    reset_stores()
    settings = get_settings_store(config_factory()).load()
    assert settings is not None
    assert resolve(settings.misc_settings, env={}).enabled is True


def test_unrelated_misc_settings_are_preserved(client):
    with client as c:
        c.patch(SETTINGS_URL, json={"misc_settings_diff": {"theme": "dark"}})
        c.patch(SETTINGS_URL, json=diff("granted"))
        body = c.get(SETTINGS_URL).json()

    assert body["misc_settings"]["theme"] == "dark"
    assert body["misc_settings"]["telemetry"]["consent"] == "granted"


def test_consent_does_not_appear_as_a_typed_settings_field(client):
    with client as c:
        body = c.patch(SETTINGS_URL, json=diff("granted")).json()
    assert "telemetry_consent" not in body


# ── 传播至活水槽──────────────────────────────────────────


def test_granting_consent_notifies_the_sink(client, monkeypatch):
    import openhands.agent_server.telemetry.service as service_mod

    sink = RecordingSink(enabled=False)
    with client as c:
        # 启动后：生命周期会建立自己的水槽并会破坏它。
        monkeypatch.setattr(service_mod, "_telemetry_sink", sink)
        assert c.patch(SETTINGS_URL, json=diff("granted")).status_code == 200

    assert sink.decisions, "settings write did not re-resolve the decision"
    assert sink.decisions[-1].enabled is True
    assert sink.enabled is True


def test_revoking_consent_discards_queued_events(client, monkeypatch):
    """不变的接受标准，现在通过设置路径。"""
    import openhands.agent_server.telemetry.service as service_mod

    sink = RecordingSink(enabled=True)
    sink.events.extend(["queued-1", "queued-2", "queued-3"])
    with client as c:
        monkeypatch.setattr(service_mod, "_telemetry_sink", sink)
        assert c.patch(SETTINGS_URL, json=diff("denied")).status_code == 200

    assert sink.decisions[-1].enabled is False
    assert sink.enabled is False
    assert sink.events == [], "revocation did not discard the queue"


def test_an_unrelated_settings_write_still_re_resolves(client, monkeypatch):
    """不涉及遥测的杂项写入是无害的，但可以重新解决。"""
    import openhands.agent_server.telemetry.service as service_mod

    sink = RecordingSink(enabled=False)
    with client as c:
        monkeypatch.setattr(service_mod, "_telemetry_sink", sink)
        c.patch(SETTINGS_URL, json={"misc_settings_diff": {"theme": "dark"}})

    assert sink.decisions[-1].enabled is False


def test_a_non_misc_settings_write_does_not_touch_telemetry(client, monkeypatch):
    import openhands.agent_server.telemetry.service as service_mod

    sink = RecordingSink(enabled=True)
    with client as c:
        monkeypatch.setattr(service_mod, "_telemetry_sink", sink)
        c.patch(
            SETTINGS_URL,
            json={"conversation_settings_diff": {"max_iterations": 42}},
        )

    assert sink.decisions == []
    assert sink.enabled is True


def test_there_is_no_dedicated_consent_endpoint(client):
    with client as c:
        assert c.get("/api/telemetry/consent").status_code == 404


# ── 通过 header 进行请求范围归因 ──────────────────────────────────


def test_request_failed_uses_the_distinct_id_header(client, monkeypatch):
    """提供时，500 归因于前端的 PostHog 身份。"""
    import openhands.agent_server.telemetry.service as service_mod
    from openhands.agent_server.api import create_app
    from openhands.agent_server.telemetry.factory import (
        DISTINCT_ID_HEADER,
        DiagnosticEventFactory,
        build_runtime_properties,
    )

    captured: list = []

    class _Sink:
        enabled = True

        def emit(self, event):
            captured.append(event)

        def on_decision_changed(self, decision):
            pass

        async def aclose(self):
            pass

    app = create_app()

    @app.get("/api/_boom_header")
    async def _boom():
        raise ValueError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as c:
        monkeypatch.setattr(service_mod, "_telemetry_sink", _Sink())
        monkeypatch.setattr(
            service_mod,
            "_event_factory",
            DiagnosticEventFactory(
                runtime=build_runtime_properties(deferred_init=False)
            ),
        )
        r = c.get(
            "/api/_boom_header",
            headers={DISTINCT_ID_HEADER: "phc_frontend_user"},
        )
        assert r.status_code == 500

    assert captured, "request_failed was not emitted"
    assert captured[-1].distinct_id == "phc_frontend_user"


def test_request_failed_without_the_header_is_anonymous(client, monkeypatch):
    import openhands.agent_server.telemetry.service as service_mod
    from openhands.agent_server.api import create_app
    from openhands.agent_server.telemetry.factory import (
        ANONYMOUS_PREFIX,
        DiagnosticEventFactory,
        build_runtime_properties,
    )

    captured: list = []

    class _Sink:
        enabled = True

        def emit(self, event):
            captured.append(event)

        def on_decision_changed(self, decision):
            pass

        async def aclose(self):
            pass

    app = create_app()

    @app.get("/api/_boom_noheader")
    async def _boom():
        raise ValueError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as c:
        monkeypatch.setattr(service_mod, "_telemetry_sink", _Sink())
        monkeypatch.setattr(
            service_mod,
            "_event_factory",
            DiagnosticEventFactory(
                runtime=build_runtime_properties(deferred_init=False)
            ),
        )
        assert c.get("/api/_boom_noheader").status_code == 500

    assert captured
    assert captured[-1].distinct_id.startswith(ANONYMOUS_PREFIX)


def test_request_failed_is_emitted_for_an_exception_group(client, monkeypatch):
    """Regression: a BaseExceptionGroup 没有 HTTPException 返回了 500
    跳过 request_failed 遥测。"""
    import openhands.agent_server.telemetry.service as service_mod
    from openhands.agent_server.api import create_app
    from openhands.agent_server.telemetry import models as m
    from openhands.agent_server.telemetry.factory import (
        DiagnosticEventFactory,
        build_runtime_properties,
    )

    captured: list = []

    class _Sink:
        enabled = True

        def emit(self, event):
            captured.append(event)

        def on_decision_changed(self, decision):
            pass

        async def aclose(self):
            pass

    app = create_app()

    @app.get("/api/_boom_group")
    async def _boom():
        raise BaseExceptionGroup("grouped", [ValueError("x"), RuntimeError("y")])

    with TestClient(app, raise_server_exceptions=False) as c:
        monkeypatch.setattr(service_mod, "_telemetry_sink", _Sink())
        monkeypatch.setattr(
            service_mod,
            "_event_factory",
            DiagnosticEventFactory(
                runtime=build_runtime_properties(deferred_init=False)
            ),
        )
        assert c.get("/api/_boom_group").status_code == 500

    assert captured, "request_failed not emitted for an exception group"
    assert captured[-1].event_name == m.EventName.REQUEST_FAILED
