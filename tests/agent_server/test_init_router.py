"""测试延迟初始化/休眠模式流程。

Background: https://github.com/OpenHands/software-agent-sdk/issues/2523
"""

from __future__ import annotations

import io
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import Request, Response, status
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect
from pydantic import SecretStr

from openhands.agent_server.api import api_lifespan, create_app
from openhands.agent_server.config import CONFIG_PATH_ENV, Config, load_config
from openhands.agent_server.init_router import (
    InitRequest,
    InitService,
    InitState,
    _build_initialized_config,
    require_initialized,
)
from openhands.agent_server.vscode_service import VSCodeService


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """智能体-服务器在导入时从环境获取配置。
    null 这些都出来了，所以每个测试都从头开始。"""
    for key in (
        "OH_DEFERRED_INIT",
        "OH_WEB_URL",
        "RUNTIME_URL",
        "TMUX_TMPDIR",
        "SESSION_API_KEY",
        "OH_SESSION_API_KEYS_0",
        "OH_SECRET_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _fresh_vscode_service(monkeypatch):
    """/api/init 更新了 VSCode 单例服务。 给每个测试自己的。

    该服务从默认配置中获取其 token，该配置加载于
    import time, before ``_clean_env`` runs, so reset that too.
    """
    monkeypatch.setattr("openhands.agent_server.vscode_service._vscode_service", None)
    monkeypatch.setattr("openhands.agent_server.config._default_config", None)


def _reset_conversation_singleton():
    """一些测试构建自己的ConversationService； 重置模块级别
    缓存，因此不相关的测试看不到剩余状态。"""
    from openhands.agent_server import conversation_service as cs_mod

    cs_mod._conversation_service = None


def _reset_bash_singleton():
    """重置模块级 BashEventService 缓存，以便每个测试重新开始。"""
    from openhands.agent_server import bash_service as bash_mod

    bash_mod._bash_event_service = None


def _vscode_url_after_init(tmp_path: Path) -> str | None:
    """启动休眠应用程序，通过 /api/init 传递会话密钥，然后读取
    /api/vscode/url 用那个键。"""
    _reset_conversation_singleton()
    cfg = Config(
        deferred_init=True,
        conversations_path=tmp_path / "convs",
        bash_events_dir=tmp_path / "bash",
    )
    with TestClient(create_app(cfg)) as client:
        try:
            resp = client.post(
                "/api/init",
                json={
                    "session_api_keys": ["user-session-key"],
                    "conversations_path": str(tmp_path / "u" / "convs"),
                    "bash_events_dir": str(tmp_path / "u" / "bash"),
                },
            )
            assert resp.status_code == 200

            resp = client.get(
                "/api/vscode/url", headers={"X-Session-API-Key": "user-session-key"}
            )
            assert resp.status_code == 200
            return resp.json()["url"]
        finally:
            _reset_conversation_singleton()


class TestConfigDefaults:
    def test_deferred_init_defaults_false(self):
        assert Config().deferred_init is False


class TestBuildInitializedConfig:
    def test_clears_deferred_init_flag(self):
        base = Config(deferred_init=True)
        merged = _build_initialized_config(base, InitRequest())
        assert merged.deferred_init is False

    def test_overrides_only_provided_fields(self, tmp_path):
        base = Config(
            deferred_init=True,
            conversations_path=Path("base/convs"),
            bash_events_dir=Path("base/bash"),
            max_concurrent_runs=5,
        )
        req = InitRequest(
            session_api_keys=["k1"],
            conversations_path=tmp_path / "user-workspace" / "conversations",
        )
        merged = _build_initialized_config(base, req)
        assert merged.session_api_keys == ["k1"]
        assert (
            merged.conversations_path == tmp_path / "user-workspace" / "conversations"
        )
        # 未触及的字段保留基值。
        assert merged.bash_events_dir == Path("base/bash")
        assert merged.max_concurrent_runs == 5

    def test_secret_key_falls_back_to_session_key(self):
        base = Config(deferred_init=True)
        # base.secret_key 默认为 None（无环境），因此我们应该回退到 /api/init. 之后的第
        # 一个会话密钥
        #
        assert base.secret_key is None
        merged = _build_initialized_config(
            base, InitRequest(session_api_keys=["s1", "s2"])
        )
        assert merged.secret_key is not None
        assert merged.secret_key.get_secret_value() == "s1"

    def test_previous_secret_keys_reach_the_cipher(self):
        base = Config(deferred_init=True)
        merged = _build_initialized_config(
            base,
            InitRequest(
                session_api_keys=["new-session-key"],
                previous_secret_keys=[SecretStr("old-session-key")],
            ),
        )
        assert merged.cipher is not None
        assert merged.cipher.secret_key == "new-session-key"
        assert merged.cipher.previous_keys == ("old-session-key",)

    def test_explicit_secret_key_wins(self):
        base = Config(deferred_init=True)
        merged = _build_initialized_config(
            base,
            InitRequest(
                session_api_keys=["sk"], secret_key=SecretStr("explicit-secret")
            ),
        )
        assert merged.secret_key is not None
        assert merged.secret_key.get_secret_value() == "explicit-secret"

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_empty_secret_key_is_treated_as_unset(self, blank):
        base = Config(deferred_init=True)
        merged = _build_initialized_config(
            base, InitRequest(session_api_keys=["s1"], secret_key=SecretStr(blank))
        )
        assert merged.secret_key is not None
        assert merged.secret_key.get_secret_value() == "s1"


class TestRouterMounting:
    """/api/init 端点寿命之外的行为。"""

    def test_init_get_404_without_deferred_mode(self):
        # 当 deferred_init=False 时，InitService 永远不会附加到 app.state，因此端点的行
        # 为就像未配置一样。
        #
        app = create_app(Config(deferred_init=False))
        client = TestClient(app)
        resp = client.get("/api/init")
        assert resp.status_code == 404


class TestInitServiceTransitions:
    @pytest.mark.asyncio
    async def test_init_transitions_dormant_to_ready(self, tmp_path):
        _reset_conversation_singleton()
        _reset_bash_singleton()
        from openhands.agent_server.bash_service import BashEventService

        base = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = SimpleNamespace(state=SimpleNamespace(config=base))
        svc = InitService(app, base_config=base)  # type: ignore[arg-type]
        assert svc.state == "dormant"

        result = await svc.initialize(
            InitRequest(
                session_api_keys=["user-key"],
                conversations_path=tmp_path / "user" / "convs",
                bash_events_dir=tmp_path / "user" / "bash",
            )
        )
        try:
            assert result.state == "ready"
            assert svc.state == "ready"
            # 新配置已到达 app.state，deferred_init 已清除。
            assert app.state.config.deferred_init is False
            assert app.state.config.session_api_keys == ["user-key"]
            assert app.state.conversation_service is not None
            # BashEventService 已在 app.state 上注册，因此 bash WebSocket 处理程序会选择
            # 每个用户的 bash_events_dir，而不是导入时默认值。
            #
            assert isinstance(
                getattr(app.state, "bash_event_service", None), BashEventService
            )
            assert (
                app.state.bash_event_service.bash_events_dir
                == tmp_path / "user" / "bash"
            )
        finally:
            await svc.teardown()
            _reset_conversation_singleton()
            _reset_bash_singleton()

    @pytest.mark.asyncio
    async def test_second_init_rejected_with_400(self, tmp_path):
        _reset_conversation_singleton()
        from fastapi import HTTPException

        base = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = SimpleNamespace(state=SimpleNamespace(config=base))
        svc = InitService(app, base_config=base)  # type: ignore[arg-type]

        await svc.initialize(
            InitRequest(
                conversations_path=tmp_path / "u1" / "convs",
                bash_events_dir=tmp_path / "u1" / "bash",
            )
        )
        try:
            with pytest.raises(HTTPException) as excinfo:
                await svc.initialize(InitRequest())
            assert excinfo.value.status_code == 400
            assert "already in state" in str(excinfo.value.detail)
        finally:
            await svc.teardown()
            _reset_conversation_singleton()

    @pytest.mark.asyncio
    async def test_init_applies_env_vars(self, tmp_path, monkeypatch):
        _reset_conversation_singleton()
        # 预清理，使环境变量真正来自 /api/init.
        monkeypatch.delenv("DEFERRED_INIT_TEST_VAR", raising=False)
        observed_env = None

        def capture_observability_env():
            nonlocal observed_env
            observed_env = os.environ.get("DEFERRED_INIT_TEST_VAR")

        monkeypatch.setattr(
            "openhands.agent_server.init_router.maybe_init_laminar",
            capture_observability_env,
        )
        base = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = SimpleNamespace(state=SimpleNamespace(config=base))
        svc = InitService(app, base_config=base)  # type: ignore[arg-type]

        await svc.initialize(
            InitRequest(
                env={"DEFERRED_INIT_TEST_VAR": "hello"},
                conversations_path=tmp_path / "u" / "convs",
                bash_events_dir=tmp_path / "u" / "bash",
            )
        )
        try:
            assert os.environ.get("DEFERRED_INIT_TEST_VAR") == "hello"
            assert observed_env == "hello"
        finally:
            await svc.teardown()
            monkeypatch.delenv("DEFERRED_INIT_TEST_VAR", raising=False)
            _reset_conversation_singleton()

    @pytest.mark.asyncio
    async def test_init_bash_service_uses_user_supplied_dir(self, tmp_path):
        """/api/init 之后，app.state.bash_event_service 使用
        bash_events_dir 供应给 InitRequest。"""
        _reset_conversation_singleton()
        _reset_bash_singleton()
        from openhands.agent_server.bash_service import BashEventService

        base = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "boot" / "bash",
        )
        app = SimpleNamespace(state=SimpleNamespace(config=base))
        svc = InitService(app, base_config=base)  # type: ignore[arg-type]

        user_dir = tmp_path / "user" / "bash"
        await svc.initialize(
            InitRequest(
                conversations_path=tmp_path / "user" / "convs",
                bash_events_dir=user_dir,
            )
        )
        try:
            bash_svc = app.state.bash_event_service
            assert isinstance(bash_svc, BashEventService)
            assert bash_svc.bash_events_dir == user_dir
        finally:
            await svc.teardown()
            _reset_conversation_singleton()
            _reset_bash_singleton()

    @pytest.mark.asyncio
    async def test_init_teardown_releases_bash_service(self, tmp_path):
        """当/api/init后面跟着teardown时，bash服务也必须
        退出，以便释放其后台任务。"""
        _reset_conversation_singleton()
        _reset_bash_singleton()
        base = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = SimpleNamespace(state=SimpleNamespace(config=base))
        svc = InitService(app, base_config=base)  # type: ignore[arg-type]

        await svc.initialize(
            InitRequest(
                conversations_path=tmp_path / "u" / "convs",
                bash_events_dir=tmp_path / "u" / "bash",
            )
        )
        assert svc._entered_bash_service is not None
        await svc.teardown()
        assert svc._entered_bash_service is None
        _reset_conversation_singleton()
        _reset_bash_singleton()

    @pytest.mark.asyncio
    async def test_init_switches_vscode_to_first_session_key(
        self, tmp_path, monkeypatch
    ):
        """VSCode 以随机 token 启动的。 init 将其切换到第一个
        会话密钥，使用该密钥启动的服务器将使用该密钥。"""
        _reset_conversation_singleton()
        vscode = SimpleNamespace(set_connection_token=AsyncMock())
        monkeypatch.setattr(
            "openhands.agent_server.init_router.get_vscode_service", lambda: vscode
        )
        base = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = SimpleNamespace(state=SimpleNamespace(config=base))
        svc = InitService(app, base_config=base)  # type: ignore[arg-type]

        await svc.initialize(
            InitRequest(
                session_api_keys=["user-key", "second-key"],
                conversations_path=tmp_path / "u" / "convs",
                bash_events_dir=tmp_path / "u" / "bash",
            )
        )
        try:
            vscode.set_connection_token.assert_awaited_once_with("user-key")
        finally:
            await svc.teardown()
            _reset_conversation_singleton()

    @pytest.mark.asyncio
    async def test_init_without_session_keys_keeps_vscode_token(
        self, tmp_path, monkeypatch
    ):
        """由于没有切换到会话密钥，VSCode 保持其启动 token。"""
        _reset_conversation_singleton()
        vscode = SimpleNamespace(set_connection_token=AsyncMock())
        monkeypatch.setattr(
            "openhands.agent_server.init_router.get_vscode_service", lambda: vscode
        )
        base = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = SimpleNamespace(state=SimpleNamespace(config=base))
        svc = InitService(app, base_config=base)  # type: ignore[arg-type]

        await svc.initialize(
            InitRequest(
                conversations_path=tmp_path / "u" / "convs",
                bash_events_dir=tmp_path / "u" / "bash",
            )
        )
        try:
            vscode.set_connection_token.assert_not_awaited()
        finally:
            await svc.teardown()
            _reset_conversation_singleton()


class TestEndToEndOverLifespan:
    """在 FastAPI 生命周期 + TestClient 内驱动整个流程。"""

    def test_blank_init_secret_falls_back_to_session_key(self, tmp_path):
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = create_app(cfg)
        with TestClient(app) as client:
            try:
                response = client.post(
                    "/api/init",
                    json={
                        "secret_key": "",
                        "session_api_keys": ["user-session-key"],
                    },
                )
                assert response.status_code == 200
                assert app.state.config.cipher.secret_key == "user-session-key"
            finally:
                _reset_conversation_singleton()

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_secret_key_env_keeps_init_closed(self, tmp_path, monkeypatch, blank):
        _reset_conversation_singleton()
        monkeypatch.setenv(CONFIG_PATH_ENV, str(tmp_path / "missing.json"))
        monkeypatch.setenv("OH_SECRET_KEY", blank)
        monkeypatch.setenv("OH_DEFERRED_INIT", "true")
        monkeypatch.setenv("OH_CONVERSATIONS_PATH", str(tmp_path / "convs"))
        monkeypatch.setenv("OH_BASH_EVENTS_DIR", str(tmp_path / "bash"))
        cfg = load_config()
        assert cfg.deferred_init and cfg.secret_key is None
        with TestClient(create_app(cfg)) as client:
            try:
                assert client.post("/api/init", json={}).status_code == 401
                assert client.get("/api/init").json()["state"] == "dormant"
            finally:
                _reset_conversation_singleton()

    @pytest.mark.parametrize("session_api_keys", [[""], ["", "user-session-key"]])
    def test_init_rejects_empty_session_keys(self, tmp_path, session_api_keys):
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        with TestClient(create_app(cfg)) as client:
            try:
                response = client.post(
                    "/api/init", json={"session_api_keys": session_api_keys}
                )
                assert response.status_code == 422
                assert "user-session-key" not in response.text
                assert client.get("/api/init").json()["state"] == "dormant"

                response = client.post(
                    "/api/init", json={"session_api_keys": ["user-session-key"]}
                )
                assert response.status_code == 200
                response = client.get(
                    "/api/conversations/count",
                    headers={"X-Session-API-Key": "user-session-key"},
                )
                assert response.status_code == 200
            finally:
                _reset_conversation_singleton()

    @pytest.mark.parametrize(
        ("method", "path"),
        (
            ("GET", "/api/conversations/count"),
            ("GET", "/v1/models"),
            (
                "GET",
                "/api/conversations/00000000-0000-0000-0000-000000000000/"
                "workspace/index.html",
            ),
            ("POST", "/app-backends/test-extension/session"),
        ),
    )
    def test_dormant_readiness_precedes_authentication(
        self, tmp_path: Path, method: str, path: str
    ) -> None:
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=True,
            session_api_keys=["dormant-key"],
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        with TestClient(create_app(cfg)) as client:
            try:
                assert client.request(method, path).status_code == 503
            finally:
                _reset_conversation_singleton()

    @pytest.mark.parametrize("init_state", ("dormant", "initializing"))
    def test_app_backend_http_requires_ready_state(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        init_state: InitState,
    ) -> None:
        async def accept_app_backend_http(
            _request: Request, _extension_name: str, _path: str
        ) -> Response:
            return Response(status_code=200)

        monkeypatch.setattr(
            "openhands.agent_server.canvas_extensions_bridge_router."
            "proxy_app_backend_http",
            accept_app_backend_http,
        )
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = create_app(cfg)
        with TestClient(app) as client:
            try:
                init_service: InitService = app.state.init_service
                init_service._state = init_state
                assert client.get("/api/init").json()["state"] == init_state
                assert client.get("/app-backends/test-extension").status_code == 503
            finally:
                _reset_conversation_singleton()

    @pytest.mark.parametrize(
        (
            "path",
            "dormant_keys",
            "request_headers",
            "expected_status",
            "ready_headers",
        ),
        (
            (
                "/api/conversations/count",
                [],
                {},
                401,
                {"X-Session-API-Key": "ready-key"},
            ),
            (
                "/api/conversations/count",
                ["dormant-key"],
                {"X-Session-API-Key": "dormant-key"},
                401,
                {"X-Session-API-Key": "ready-key"},
            ),
            (
                "/api/conversations/count",
                [],
                {"X-Session-API-Key": "ready-key"},
                200,
                {"X-Session-API-Key": "ready-key"},
            ),
            (
                "/v1/models",
                [],
                {},
                401,
                {"Authorization": "Bearer ready-key"},
            ),
            (
                "/v1/models",
                ["dormant-key"],
                {"Authorization": "Bearer dormant-key"},
                401,
                {"Authorization": "Bearer ready-key"},
            ),
            (
                "/v1/models",
                [],
                {"Authorization": "Bearer ready-key"},
                200,
                {"Authorization": "Bearer ready-key"},
            ),
        ),
    )
    def test_request_crossing_init_uses_ready_credentials(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        path: str,
        dormant_keys: list[str],
        request_headers: dict[str, str],
        expected_status: int,
        ready_headers: dict[str, str],
    ) -> None:
        class EmptyProfileStore:
            def list_summaries(self) -> list[dict[str, object]]:
                return []

        monkeypatch.setattr(
            "openhands.agent_server.openai.service.get_llm_profile_store",
            EmptyProfileStore,
        )
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=True,
            session_api_keys=dormant_keys,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = create_app(cfg)
        readiness_reached = Event()
        continue_request = Event()

        def pause_at_readiness(request: Request) -> None:
            readiness_reached.set()
            assert continue_request.wait(timeout=5)
            require_initialized(request)

        app.dependency_overrides[require_initialized] = pause_at_readiness
        with TestClient(app) as client:
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    pending = executor.submit(
                        client.get,
                        path,
                        headers=request_headers,
                    )
                    try:
                        assert readiness_reached.wait(timeout=5)
                        initialized = client.post(
                            "/api/init",
                            json={
                                "session_api_keys": ["ready-key"],
                                "conversations_path": str(tmp_path / "u" / "convs"),
                                "bash_events_dir": str(tmp_path / "u" / "bash"),
                            },
                        )
                        assert initialized.status_code == 200
                    finally:
                        continue_request.set()
                    crossed = pending.result(timeout=5)

                assert crossed.status_code == expected_status
                assert client.get(path, headers=ready_headers).status_code == 200
            finally:
                _reset_conversation_singleton()

    def test_dormant_503s_api_routes_until_init(self, tmp_path):
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = create_app(cfg)
        with TestClient(app) as client:
            try:
                # Health/ready/server_info 未门控。
                assert client.get("/alive").status_code == 200
                assert client.get("/ready").status_code == 200

                # 示例 /api/* 路线 — 应为 503。 智能体服务器的5xx异常处理器会将
                # ``detail``替换为一个通用的“内部服务器错误”消息，所以我们只在这里断言状
                # 态码——这是暖池调度器实际检查的。
                #
                resp = client.get("/api/conversations/count")
                assert resp.status_code == 503

                # 初始化状态报告处于休眠状态。
                resp = client.get("/api/init")
                assert resp.status_code == 200
                assert resp.json()["state"] == "dormant"

                # 运行/api/init.
                resp = client.post(
                    "/api/init",
                    json={
                        "conversations_path": str(tmp_path / "u" / "convs"),
                        "bash_events_dir": str(tmp_path / "u" / "bash"),
                    },
                )
                assert resp.status_code == 200
                assert resp.json()["state"] == "ready"

                # /api/* 现在可以使用（200，而不是 503）。
                resp = client.get("/api/conversations/count")
                assert resp.status_code == 200
            finally:
                _reset_conversation_singleton()

    def test_dormant_refuses_bash_socket_until_init(self, tmp_path):
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        marker = tmp_path / "marker"
        with TestClient(create_app(cfg)) as client:
            try:
                with pytest.raises(WebSocketDisconnect) as excinfo:
                    with client.websocket_connect("/sockets/bash-events") as ws:
                        ws.send_json({"command": f"touch {marker}"})
                assert excinfo.value.code == status.WS_1013_TRY_AGAIN_LATER
                assert not marker.exists()

                resp = client.post(
                    "/api/init",
                    json={
                        "conversations_path": str(tmp_path / "u" / "convs"),
                        "bash_events_dir": str(tmp_path / "u" / "bash"),
                    },
                )
                assert resp.status_code == 200

                with client.websocket_connect("/sockets/bash-events"):
                    pass
            finally:
                _reset_conversation_singleton()

    def test_dormant_503s_openai_routes_until_init(self, tmp_path, monkeypatch):
        class EmptyProfileStore:
            def list_summaries(self) -> list[dict[str, object]]:
                return []

        monkeypatch.setattr(
            "openhands.agent_server.openai.service.get_llm_profile_store",
            EmptyProfileStore,
        )
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        with TestClient(create_app(cfg)) as client:
            try:
                assert client.get("/v1/models").status_code == 503

                resp = client.post(
                    "/api/init",
                    json={
                        "conversations_path": str(tmp_path / "u" / "convs"),
                        "bash_events_dir": str(tmp_path / "u" / "bash"),
                    },
                )
                assert resp.status_code == 200

                assert client.get("/v1/models").status_code == 200
            finally:
                _reset_conversation_singleton()

    def test_root_path_updates_from_init_web_url(self, tmp_path):
        """当/api/init传送``web_url``时，FastAPI``root_path``
        必须重新从它中推导出来 OpenAPI/Swagger/ReDoc URLs 反映外部挂载路径 (e.g。 在
        反向代理后面）。
        """
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = create_app(cfg)
        with TestClient(app) as client:
            try:
                # 休眠服务器没有web_url → 空root_path。
                assert app.root_path == ""

                resp = client.post(
                    "/api/init",
                    json={
                        "web_url": "https://example.com/agent-server-123/agent-server/",
                        "conversations_path": str(tmp_path / "u" / "convs"),
                        "bash_events_dir": str(tmp_path / "u" / "bash"),
                    },
                )
                assert resp.status_code == 200

                # 的 FastAPI app的 root_path 现在必须与每个用户的前缀匹配 web_url so
                # OpenAPI doc URLs Swagger 资产链接在反向代理挂载路径下是正确的。
                #
                assert app.root_path == "/agent-server-123/agent-server", (
                    f"root_path was not updated after /api/init: {app.root_path!r}"
                )
            finally:
                _reset_conversation_singleton()

    def test_init_api_key_required_when_configured(self, tmp_path):
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=True,
            secret_key=SecretStr("pool-key"),
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = create_app(cfg)
        with TestClient(app) as client:
            try:
                # 钥匙错误 → 401。
                resp = client.post(
                    "/api/init",
                    headers={"X-Init-API-Key": "wrong"},
                    json={
                        "conversations_path": str(tmp_path / "u" / "convs"),
                        "bash_events_dir": str(tmp_path / "u" / "bash"),
                    },
                )
                assert resp.status_code == 401

                # 没有钥匙 → 401。
                resp = client.post("/api/init", json={})
                assert resp.status_code == 401

                # 右键 → 200。
                resp = client.post(
                    "/api/init",
                    headers={"X-Init-API-Key": "pool-key"},
                    json={
                        "conversations_path": str(tmp_path / "u" / "convs"),
                        "bash_events_dir": str(tmp_path / "u" / "bash"),
                    },
                )
                assert resp.status_code == 200

                # GET /api/init 不是否需要密钥（状态轮询）。
                resp = client.get("/api/init")
                assert resp.status_code == 200
            finally:
                _reset_conversation_singleton()

    def test_session_api_key_set_at_init_protects_api(self, tmp_path):
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = create_app(cfg)
        with TestClient(app) as client:
            try:
                # 在 /api/init 之前，启动配置级别不需要会话密钥 — 但无论如何都需要休眠门
                #  503。
                #
                assert client.get("/api/conversations/count").status_code == 503

                # Init 传递会话密钥。
                resp = client.post(
                    "/api/init",
                    json={
                        "session_api_keys": ["user-session-key"],
                        "conversations_path": str(tmp_path / "u" / "convs"),
                        "bash_events_dir": str(tmp_path / "u" / "bash"),
                    },
                )
                assert resp.status_code == 200

                assert app.state.config.session_api_keys == ["user-session-key"]
                assert client.get("/api/conversations/count").status_code == 401
                assert (
                    client.get(
                        "/api/conversations/count",
                        headers={"X-Session-API-Key": "wrong-key"},
                    ).status_code
                    == 401
                )
                assert (
                    client.get(
                        "/api/conversations/count",
                        headers={"X-Session-API-Key": "user-session-key"},
                    ).status_code
                    == 200
                )
            finally:
                _reset_conversation_singleton()

    def test_download_trajectory_uses_init_conversations_path(self, tmp_path):
        """两条轨迹路线均服务于存储在
        ``conversations_path`` 由 /api/init 交付，而不是启动路径。"""
        _reset_conversation_singleton()
        init_convs = tmp_path / "u" / "convs"
        workspace = tmp_path / "ws"
        workspace.mkdir()
        cfg = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        with TestClient(create_app(cfg)) as client:
            try:
                resp = client.post(
                    "/api/init",
                    json={
                        "conversations_path": str(init_convs),
                        "bash_events_dir": str(tmp_path / "u" / "bash"),
                    },
                )
                assert resp.status_code == 200

                resp = client.post(
                    "/api/conversations",
                    json={
                        "agent": {
                            "kind": "Agent",
                            "llm": {"model": "test", "api_key": "sk-init-path"},
                            "tools": [],
                        },
                        "workspace": {"working_dir": str(workspace)},
                    },
                )
                assert resp.status_code in (200, 201), resp.text
                conversation_id = UUID(resp.json()["id"])
                assert (init_convs / conversation_id.hex / "base_state.json").exists()

                for route in (
                    f"/api/file/download-trajectory/{conversation_id}",
                    f"/api/conversations/{conversation_id}"
                    f"/file/download-trajectory/{conversation_id}",
                ):
                    resp = client.get(route)
                    assert resp.status_code == 200, (route, resp.text)
                    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
                        names = archive.namelist()
                        blob = b"".join(archive.read(n) for n in names)
                    assert f"{conversation_id.hex}/base_state.json" in names
                    assert b"sk-init-path" not in blob
                    assert not list(init_convs.glob("*.zip"))

                missing = uuid4()
                resp = client.get(f"/api/file/download-trajectory/{missing}")
                assert resp.status_code == 404
                assert resp.json()["detail"] == "Conversation not found"
            finally:
                _reset_conversation_singleton()

    def test_vscode_url_uses_session_key_after_init(self, tmp_path, monkeypatch):
        """在 /api/init 之后，VSCode URL's token 是第一个会话密钥，所以
        掌握关键的编排器可以构建 URL 本身。"""

        async def fake_start(service):
            # 像start()：没有会话密钥启动的服务器组成随机token。
            #
            service.connection_token = service.connection_token or "boot-token"
            return True

        monkeypatch.setattr(VSCodeService, "start", fake_start)
        monkeypatch.setattr(VSCodeService, "stop", AsyncMock())
        monkeypatch.setattr(VSCodeService, "is_running", lambda service: True)

        url = _vscode_url_after_init(tmp_path)

        assert url is not None
        assert "?tkn=user-session-key&" in url

    def test_vscode_url_stays_empty_without_vscode(self, tmp_path, monkeypatch):
        """Where VSCode 从未启动，如不包含的图像
        /api/vscode/url 在 /api/init. 之后仍然报告没有 URL"""
        monkeypatch.setattr(
            VSCodeService, "_check_vscode_available", lambda service: False
        )

        assert _vscode_url_after_init(tmp_path) is None


class TestNonDeferredPathUnchanged:
    """Regression: deferred_init=False 的行为必须与之前完全相同。"""

    def test_non_deferred_does_not_create_init_service(self, tmp_path):
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=False,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = create_app(cfg)
        with TestClient(app) as client:
            try:
                # 非延迟模式下没有 init_service。
                assert getattr(app.state, "init_service", None) is None
                # /api/* 应该处于活动状态 (200) — 休眠门是无操作的。
                assert client.get("/api/conversations/count").status_code == 200
                # /api/init 返回 404，因为没有附加 InitService。
                assert client.get("/api/init").status_code == 404
            finally:
                _reset_conversation_singleton()


@pytest.mark.asyncio
async def test_lifespan_teardown_releases_conversation_service_after_init(
    tmp_path,
):
    """如果/api/init成功，则生命周期finally子句必须释放
    会话服务。 如果 /api/init 从未运行，则拆卸是无操作。"""
    _reset_conversation_singleton()
    _reset_bash_singleton()
    cfg = Config(
        deferred_init=True,
        conversations_path=tmp_path / "convs",
        bash_events_dir=tmp_path / "bash",
    )
    # 构建一个假的 FastAPI 应用程序 - api_lifespan 只涉及 `.state`。
    fake_app = SimpleNamespace(state=SimpleNamespace(config=cfg))
    async with api_lifespan(fake_app):  # type: ignore[arg-type]
        init_svc = fake_app.state.init_service
        assert init_svc.state == "dormant"
        await init_svc.initialize(
            InitRequest(
                conversations_path=tmp_path / "u" / "convs",
                bash_events_dir=tmp_path / "u" / "bash",
            )
        )
        assert init_svc.state == "ready"
    # 生命周期退出后，对话服务应该被拆除 - i.e。 _entered_service 已清除。
    #
    assert init_svc._entered_service is None
    # bash 服务也是如此：它必须在生命周期退出时被拆除。
    assert init_svc._entered_bash_service is None
    _reset_conversation_singleton()
    _reset_bash_singleton()


class TestSessionKeyExport:
    """服务器验证所用的密钥到达进程内调用者
    从环境中读取它（start_child_conversation，托管LLM密钥刷新），无论它是通过/api/
    init还是配置文件到达。
    """

    def test_init_exports_delivered_key_over_boot_key(self, tmp_path, monkeypatch):
        """休眠的 Pod 启动时持有共享密钥； /api/init 取代它。"""
        monkeypatch.setenv("OH_SESSION_API_KEYS_0", "boot-key")
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=True,
            session_api_keys=["boot-key"],
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        with TestClient(create_app(cfg)) as client:
            try:
                resp = client.post(
                    "/api/init",
                    json={
                        "session_api_keys": ["user-session-key"],
                        "conversations_path": str(tmp_path / "u" / "convs"),
                        "bash_events_dir": str(tmp_path / "u" / "bash"),
                    },
                    # 引导程序凭据是休眠机密密钥，默认为第一个会话密钥。
                    #
                    headers={"X-Init-API-Key": "boot-key"},
                )
                assert resp.status_code == 200
                assert os.environ["OH_SESSION_API_KEYS_0"] == "user-session-key"
            finally:
                _reset_conversation_singleton()

    @pytest.mark.asyncio
    async def test_teardown_restores_the_env_after_a_direct_init(self, tmp_path):
        """在没有寿命的情况下驾驶 InitService（与其他测试一样）必须
        不将交付的密钥泄漏到进程环境中。"""
        _reset_conversation_singleton()
        _reset_bash_singleton()
        base = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        app = SimpleNamespace(state=SimpleNamespace(config=base))
        svc = InitService(app, base_config=base)  # type: ignore[arg-type]
        try:
            await svc.initialize(
                InitRequest(
                    session_api_keys=["user-key"],
                    conversations_path=tmp_path / "user" / "convs",
                    bash_events_dir=tmp_path / "user" / "bash",
                )
            )
            assert os.environ["OH_SESSION_API_KEYS_0"] == "user-key"
        finally:
            await svc.teardown()
            _reset_conversation_singleton()
            _reset_bash_singleton()
        assert "OH_SESSION_API_KEYS_0" not in os.environ

    def test_init_without_keys_leaves_env_untouched(self, tmp_path):
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=True,
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        with TestClient(create_app(cfg)) as client:
            try:
                resp = client.post(
                    "/api/init",
                    json={
                        "conversations_path": str(tmp_path / "u" / "convs"),
                        "bash_events_dir": str(tmp_path / "u" / "bash"),
                    },
                )
                assert resp.status_code == 200
                assert "OH_SESSION_API_KEYS_0" not in os.environ
            finally:
                _reset_conversation_singleton()

    def test_startup_exports_config_key_and_restores_env_on_shutdown(self, tmp_path):
        """从配置文件中读取的密钥将导出到服务器的
        仅限一生。"""
        _reset_conversation_singleton()
        cfg = Config(
            deferred_init=False,
            session_api_keys=["file-key"],
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        try:
            with TestClient(create_app(cfg)):
                assert os.environ["OH_SESSION_API_KEYS_0"] == "file-key"
            assert "OH_SESSION_API_KEYS_0" not in os.environ
        finally:
            _reset_conversation_singleton()
