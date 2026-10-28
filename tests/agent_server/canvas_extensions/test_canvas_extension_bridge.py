"""对经过身份验证的 Canvas 应用程序后端桥进行实时网络测试。"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import uvicorn
import websockets
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from openhands.agent_server.canvas_extensions.bridge import (
    APP_BACKEND_SESSION_COOKIE_NAME,
    APP_BACKEND_SESSION_TTL_SECONDS,
    AppBackendSessionStore,
)
from openhands.agent_server.canvas_extensions_bridge_router import (
    app_backend_bridge_router,
)
from openhands.agent_server.config import Config


CONTROL_KEY = "control-key"
CANVAS_ORIGIN = "https://canvas.example.test"
APP_NAME = "demo-app"


class _ReadyBackendManager:
    def __init__(self, endpoint: tuple[str, int]) -> None:
        self.endpoint: tuple[str, int] | None = endpoint

    def ready_endpoint(self, name: str) -> tuple[str, int] | None:
        return self.endpoint if name == APP_NAME else None


class _LiveServer:
    def __init__(
        self,
        app: FastAPI,
        *,
        port: int | None = None,
        ssl_certfile: Path | None = None,
        ssl_keyfile: Path | None = None,
        proxy_headers: bool = True,
    ) -> None:
        self.port = port or _free_port()
        self.server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=self.port,
                log_level="warning",
                ssl_certfile=str(ssl_certfile) if ssl_certfile else None,
                ssl_keyfile=str(ssl_keyfile) if ssl_keyfile else None,
                proxy_headers=proxy_headers,
            )
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> _LiveServer:
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert self.server.started
        return self

    def __exit__(self, *args: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)
        assert not self.thread.is_alive()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_tls_certificate(tmp_path: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    certfile = tmp_path / "cert.pem"
    keyfile = tmp_path / "key.pem"
    certfile.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return certfile, keyfile


@pytest.fixture
async def live_bridge(tmp_path: Path) -> AsyncIterator[SimpleNamespace]:
    async with _live_bridge(tmp_path) as bridge:
        yield bridge


@asynccontextmanager
async def _live_bridge(
    tmp_path: Path,
    *,
    ttl_seconds: int = APP_BACKEND_SESSION_TTL_SECONDS,
    trust_forwarded_headers: bool = False,
) -> AsyncIterator[SimpleNamespace]:
    stream_closed = threading.Event()
    backend_observation: dict[str, str | None] = {}
    backend = FastAPI()

    @backend.get("/prefix/static/app.js")
    async def static_asset(request: Request) -> JSONResponse:
        backend_observation.update(
            authorization=request.headers.get("authorization"),
            control_key=request.headers.get("x-session-api-key"),
            cookie=request.headers.get("cookie"),
            query=request.url.query,
        )
        return JSONResponse({"asset": "ok"})

    @backend.get("/range")
    async def range_response(request: Request):
        content = b"0123456789"
        if request.headers.get("range") == "bytes=2-5":
            return StreamingResponse(
                iter([content[2:6]]),
                status_code=206,
                headers={"Content-Range": "bytes 2-5/10"},
            )
        return StreamingResponse(iter([content]))

    @backend.get("/stream")
    async def stream_response() -> StreamingResponse:
        async def body() -> AsyncIterator[bytes]:
            try:
                yield b"first\n"
                await asyncio.sleep(30)
            finally:
                stream_closed.set()

        return StreamingResponse(body())

    @backend.get("/redirect")
    async def redirect_response() -> RedirectResponse:
        return RedirectResponse("https://attacker.example.test/escape")

    @backend.websocket("/socket")
    async def socket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                message = await websocket.receive_text()
                await websocket.send_text(f"echo:{message}")
        except Exception:
            pass

    with _LiveServer(backend) as backend_server:
        certfile, keyfile = _write_tls_certificate(tmp_path)
        bridge_port = _free_port()
        public_url = f"https://127.0.0.1:{bridge_port}"
        app = FastAPI()
        app.state.config = Config(
            session_api_keys=[CONTROL_KEY],
            allow_cors_origins=[CANVAS_ORIGIN],
            app_backend_public_url=public_url,
            trust_forwarded_headers=trust_forwarded_headers,
        )
        app.state.app_backend_session_store = AppBackendSessionStore(
            ttl_seconds=ttl_seconds
        )
        manager = _ReadyBackendManager(("127.0.0.1", backend_server.port))
        app.state.canvas_extension_backend_manager = manager
        app.include_router(app_backend_bridge_router)
        bridge_server = _LiveServer(
            app,
            port=bridge_port,
            ssl_certfile=certfile,
            ssl_keyfile=keyfile,
        )
        with bridge_server:
            async with httpx.AsyncClient(verify=False) as client:
                yield SimpleNamespace(
                    client=client,
                    public_url=public_url,
                    app=app,
                    manager=manager,
                    store=app.state.app_backend_session_store,
                    backend_observation=backend_observation,
                    stream_closed=stream_closed,
                )


def _bootstrap_headers(origin: str = CANVAS_ORIGIN) -> dict[str, str]:
    return {"X-Session-API-Key": CONTROL_KEY, "Origin": origin}


@pytest.mark.asyncio
async def test_live_http_bootstrap_cookie_scope_and_proxy_security(live_bridge) -> None:
    client: httpx.AsyncClient = live_bridge.client
    public_url: str = live_bridge.public_url
    root = f"{public_url}/app-backends/{APP_NAME}"

    unauthenticated = await client.post(
        f"{root}/session", headers={"Origin": CANVAS_ORIGIN}
    )
    assert unauthenticated.status_code == 401

    bad_origin = await client.post(
        f"{root}/session", headers=_bootstrap_headers("https://attacker.test")
    )
    assert bad_origin.status_code == 403

    bootstrap = await client.post(f"{root}/session", headers=_bootstrap_headers())
    assert bootstrap.status_code == 200
    assert bootstrap.json()["ingress_url"] == f"{root}/"
    assert "session" not in bootstrap.json()["ingress_url"]
    assert "allow-same-origin" in bootstrap.json()["iframe_sandbox"]
    set_cookie = bootstrap.headers["set-cookie"]
    assert set_cookie.startswith(f"{APP_BACKEND_SESSION_COOKIE_NAME}=")
    assert f"Path=/app-backends/{APP_NAME}" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=none" in set_cookie
    assert "Partitioned" in set_cookie
    cookie = client.cookies.get(APP_BACKEND_SESSION_COOKIE_NAME)
    assert cookie

    asset = await client.get(
        f"{root}/prefix/static/app.js?view=main&session_api_key=leak",
        headers={
            "Authorization": "Bearer control-secret",
            "X-Session-API-Key": "control-secret",
            "Cookie": f"{APP_BACKEND_SESSION_COOKIE_NAME}={cookie}; child=secret",
        },
    )
    assert asset.status_code == 200
    assert asset.json() == {"asset": "ok"}
    assert live_bridge.backend_observation == {
        "authorization": None,
        "control_key": None,
        "cookie": None,
        "query": "view=main",
    }

    ranged = await client.get(f"{root}/range", headers={"Range": "bytes=2-5"})
    assert ranged.status_code == 206
    assert ranged.content == b"2345"
    assert ranged.headers["content-range"] == "bytes 2-5/10"

    redirect = await client.get(f"{root}/redirect", follow_redirects=False)
    assert redirect.status_code == 502
    assert "location" not in redirect.headers

    traversal = await client.get(f"{root}/%252e%252e/secret")
    assert traversal.status_code == 400


@pytest.mark.asyncio
async def test_live_stream_disconnect_releases_upstream(live_bridge) -> None:
    client: httpx.AsyncClient = live_bridge.client
    root = f"{live_bridge.public_url}/app-backends/{APP_NAME}"
    assert (
        await client.post(f"{root}/session", headers=_bootstrap_headers())
    ).status_code == 200

    async with client.stream("GET", f"{root}/stream") as response:
        assert response.status_code == 200
        chunks = response.aiter_bytes()
        assert await anext(chunks) == b"first\n"

    assert await asyncio.to_thread(live_bridge.stream_closed.wait, 3)


@pytest.mark.asyncio
async def test_live_websocket_is_bidirectional_and_revoked(live_bridge) -> None:
    client: httpx.AsyncClient = live_bridge.client
    root = f"{live_bridge.public_url}/app-backends/{APP_NAME}"
    assert (
        await client.post(f"{root}/session", headers=_bootstrap_headers())
    ).status_code == 200
    cookie = client.cookies.get(APP_BACKEND_SESSION_COOKIE_NAME)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    websocket_url = root.replace("https://", "wss://") + "/socket"

    async with websockets.connect(
        websocket_url,
        origin=live_bridge.public_url,
        additional_headers={"Cookie": f"{APP_BACKEND_SESSION_COOKIE_NAME}={cookie}"},
        ssl=ssl_context,
    ) as websocket:
        await websocket.send("hello")
        assert await websocket.recv() == "echo:hello"
        revoked = await client.delete(f"{root}/session", headers=_bootstrap_headers())
        assert revoked.status_code == 204
        with pytest.raises(websockets.exceptions.ConnectionClosed):
            await websocket.recv()

    with pytest.raises(websockets.exceptions.InvalidStatus):
        async with websockets.connect(
            websocket_url,
            origin=live_bridge.public_url,
            additional_headers={
                "Cookie": f"{APP_BACKEND_SESSION_COOKIE_NAME}={cookie}"
            },
            ssl=ssl_context,
        ):
            pass


@pytest.mark.asyncio
async def test_live_websocket_is_revoked_at_session_expiry_without_traffic(
    tmp_path: Path,
) -> None:
    """空闲的桥接套接字必须在其 TTL 处终止，而不是在下一个请求时终止。

    回归测试：只运行于 `create()`/`authorize()` 的剪枝，因此一个 WebSocket-只应用（没
    有后续会话流量）一直转发到后端，直到
    `expires_at`。
    """
    async with _live_bridge(tmp_path, ttl_seconds=1) as bridge:
        client: httpx.AsyncClient = bridge.client
        root = f"{bridge.public_url}/app-backends/{APP_NAME}"
        assert (
            await client.post(f"{root}/session", headers=_bootstrap_headers())
        ).status_code == 200
        cookie = client.cookies.get(APP_BACKEND_SESSION_COOKIE_NAME)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        websocket_url = root.replace("https://", "wss://") + "/socket"

        async with websockets.connect(
            websocket_url,
            origin=bridge.public_url,
            additional_headers={
                "Cookie": f"{APP_BACKEND_SESSION_COOKIE_NAME}={cookie}"
            },
            ssl=ssl_context,
        ) as websocket:
            await websocket.send("hello")
            assert await websocket.recv() == "echo:hello"
            # 在此窗口期间没有会话流量：只有收割者可以采取行动。
            with pytest.raises(websockets.exceptions.ConnectionClosed):
                await asyncio.wait_for(websocket.recv(), timeout=10)

        assert (
            await bridge.store.authorize(cookie, APP_NAME, ("127.0.0.1", 0)) is None
            or not bridge.store._sessions
        )


@pytest.mark.asyncio
async def test_nested_percent_encoding_traversal_is_rejected_everywhere(
    live_bridge,
) -> None:
    """任何百分比编码 ``..`` 的嵌套深度都必须被拒绝。

    回归测试：验证器的解码上限为 3 轮，因此 ``..`` 周围的第 4 层编码通过了验证并被转
    发到上游。
    """
    client: httpx.AsyncClient = live_bridge.client
    root = f"{live_bridge.public_url}/app-backends/{APP_NAME}"
    assert (
        await client.post(f"{root}/session", headers=_bootstrap_headers())
    ).status_code == 200

    # 每个回合都会重新编码上一个值，因此`segment`只有经过那么多回合后才能解码为`..`，并
    # 且在路由器验证时仍然保持一个编码的`..`。
    #
    segment = "%2e%2e"
    for _ in range(2, 8):
        segment = segment.replace("%", "%25")
        traversal = await client.get(f"{root}/{segment}/secret")
        assert traversal.status_code == 400, (
            f"{segment!r} was accepted: {traversal.status_code}"
        )

    for encoded in ("%25255c", "%2525255c"):
        assert (await client.get(f"{root}/{encoded}{encoded}secret")).status_code == 400

    # 普通文件名中仍必须允许使用文字百分号。
    assert (await client.get(f"{root}/prefix/static/app%2Ejs")).status_code == 200


@pytest.mark.asyncio
async def test_spoofed_forwarded_headers_do_not_pass_ingress_check(
    live_bridge,
) -> None:
    """`X-Forwarded-*` 不得代表请求自己的主机。

    回归测试：`_request_origin` 首选客户提供
    `X-Forwarded-Host`/`X-Forwarded-Proto`，因此发送到不相关主机的请求可以满足配置的
    入口检查并创建会话。 可信转发可通过
    `trust_forwarded_headers` 选择加入。
    """
    client: httpx.AsyncClient = live_bridge.client
    ingress = live_bridge.public_url.removeprefix("https://")
    spoofed = await client.post(
        f"{live_bridge.public_url}/app-backends/{APP_NAME}/session",
        headers={
            **_bootstrap_headers(),
            "Host": "evil.test",
            "X-Forwarded-Host": ingress,
            "X-Forwarded-Proto": "https",
        },
    )
    assert spoofed.status_code == 421


@pytest.mark.asyncio
async def test_spoofed_forwarded_headers_are_honored_only_when_trusted(
    tmp_path: Path,
) -> None:
    """选择加入的可信代理模型恢复转发标头行为。"""

    async def run(*, trust_forwarded: bool) -> int:
        async with _live_bridge(
            tmp_path, trust_forwarded_headers=trust_forwarded
        ) as bridge:
            ingress = bridge.public_url.removeprefix("https://")
            response = await bridge.client.post(
                f"{bridge.public_url}/app-backends/{APP_NAME}/session",
                headers={
                    **_bootstrap_headers(),
                    "Host": "evil.test",
                    "X-Forwarded-Host": ingress,
                    "X-Forwarded-Proto": "https",
                },
            )
            return response.status_code

    assert await run(trust_forwarded=False) == 421
    assert await run(trust_forwarded=True) == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("public_scheme", "expected_status"),
    [
        # Plain-HTTP ingress：标头不得将原点变为 HTTPS。
        ("http", 200),
        # HTTPS 通过普通 HTTP 到达入口：标头不得声明它。
        ("https", 421),
    ],
)
async def test_untrusted_forwarded_proto_does_not_change_origin_on_launch_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    public_scheme: str,
    expected_status: int,
) -> None:
    """`trust_forwarded_headers` 关闭，`X-Forwarded-Proto` 来自环回
    客户端将请求源单独保留在服务器的真实 uvicorn 启动选项下。

    回归测试：`__main__`将uvicorn的`proxy_headers`打开，因此uvicorn重写了之前
    `X-Forwarded-Proto`中环回对等点的
    方案
    `_request_origin` 阅读它。
    """
    from openhands.agent_server.__main__ import _trust_forwarded_headers

    config_file = tmp_path / "config.json"
    config_file.write_text('{"trust_forwarded_headers": false}')
    monkeypatch.setenv("OPENHANDS_AGENT_SERVER_CONFIG_PATH", str(config_file))

    backend = FastAPI()

    @backend.get("/echo")
    async def echo() -> JSONResponse:
        return JSONResponse({"app": APP_NAME})

    with _LiveServer(backend) as backend_server:
        bridge_port = _free_port()
        public_url = f"{public_scheme}://127.0.0.1:{bridge_port}"
        app = FastAPI()
        app.state.config = Config(
            session_api_keys=[CONTROL_KEY],
            allow_cors_origins=[CANVAS_ORIGIN],
            app_backend_public_url=public_url,
        )
        app.state.app_backend_session_store = AppBackendSessionStore()
        app.state.canvas_extension_backend_manager = _ReadyBackendManager(
            ("127.0.0.1", backend_server.port)
        )
        app.include_router(app_backend_bridge_router)
        with _LiveServer(
            app, port=bridge_port, proxy_headers=_trust_forwarded_headers()
        ):
            root = f"http://127.0.0.1:{bridge_port}/app-backends/{APP_NAME}"
            async with httpx.AsyncClient() as client:
                bootstrap = await client.post(
                    f"{root}/session",
                    headers={**_bootstrap_headers(), "X-Forwarded-Proto": "https"},
                )
                assert bootstrap.status_code == expected_status
                if expected_status != 200:
                    return
                cookie = bootstrap.cookies.get(APP_BACKEND_SESSION_COOKIE_NAME)
                assert cookie
                proxied = await client.get(
                    f"{root}/echo",
                    headers={
                        "Cookie": f"{APP_BACKEND_SESSION_COOKIE_NAME}={cookie}",
                        "X-Forwarded-Proto": "https",
                    },
                )
                assert proxied.status_code == 200
                assert proxied.json() == {"app": APP_NAME}


@pytest.mark.asyncio
async def test_backend_switch_invalidates_existing_session(live_bridge) -> None:
    client: httpx.AsyncClient = live_bridge.client
    root = f"{live_bridge.public_url}/app-backends/{APP_NAME}"
    assert (
        await client.post(f"{root}/session", headers=_bootstrap_headers())
    ).status_code == 200

    live_bridge.manager.endpoint = ("127.0.0.1", _free_port())
    switched = await client.get(f"{root}/prefix/static/app.js")
    assert switched.status_code == 401


@pytest.mark.asyncio
async def test_unreachable_backend_error_names_the_canvas_backend(
    live_bridge,
) -> None:
    client: httpx.AsyncClient = live_bridge.client
    root = f"{live_bridge.public_url}/app-backends/{APP_NAME}"
    # 该端口上没有任何内容侦听，因此代理的连接失败。
    live_bridge.manager.endpoint = ("127.0.0.1", _free_port())
    assert (
        await client.post(f"{root}/session", headers=_bootstrap_headers())
    ).status_code == 200

    unreachable = await client.get(f"{root}/prefix/static/app.js")
    assert unreachable.status_code == 502
    assert unreachable.json() == {"detail": "Canvas App backend unreachable"}
