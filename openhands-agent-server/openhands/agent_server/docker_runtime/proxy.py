"""HTTP 和 WebSocket 转发到经过身份验证的会话容器。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import websockets
from fastapi import HTTPException, status
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

from openhands.sdk.logger import get_logger


class ProxyTarget(Protocol):
    @property
    def host(self) -> str: ...

    @property
    def api_key(self) -> str | None: ...


logger = get_logger(__name__)

# 逐跳标头 (RFC 7230) — 不得由代理转发。
_HOP_BY_HOP_HEADERS = frozenset(
    {
        "authorization",
        "x-session-api-key",
        "cookie",
        "set-cookie",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        # ``host``和``content-length``由httpx重新计算； 当主体被重新分块时，转发原始值会
        # 导致虚假的 400 秒。
        # ``proxy_http`` 当客户端的正文未更改时重新添加客户端的 ``content-length``。
        #
        "host",
        "content-length",
    }
)

# 服务 uvicorn 将自己的 ``date`` 和 ``server`` 添加到每个响应中，而不进行重复数据删除，
# 因此复制上游的将发送每个响应中的两个。
#
_RESPONSE_DROP_HEADERS = frozenset({"date", "server"})

# 请求/响应主体的流块大小。 显式设置它，以便代理行为不依赖于 httpx 实现默认值。
#
_CHUNK_SIZE = 64 * 1024


def _filter_headers(headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP_HEADERS}


def strip_auth_query(path: str) -> str:
    parsed = urlsplit(path)
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower()
            not in {"session_api_key", "x-session-api-key", "authorization"}
        ]
    )
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)
    )


async def proxy_http(
    request: Request,
    workspace: ProxyTarget,
    *,
    upstream_path: str,
    timeout: float | None = None,
    body: bytes | None = None,
    on_close: Callable[[], Awaitable[None]] | None = None,
    reject_redirects: bool = False,
) -> StreamingResponse:
    """将 ``request`` 转发到每个对话容器。

    Args:
        request: 外部智能体服务器上传入的 Starlette 请求。
        workspace: 目标容器的代理目标。
        upstream_path: 内部的路径（包括任何查询字符串）
            智能体-要转发到的服务器。 通常与外部服务器接收的路径相同，因为内部智能体-
            服务器公开相同的 API 表面。
        timeout: 每个请求超时以秒为单位。 ``None``（默认）表示
            no read 超时 — 对话事件流可以长期存在。
        body: 更换请求正文。 默认情况下，传入的正文是流式传输的。
        on_close: 一旦流式响应被完全消耗或
            客户端断开连接。 调用者使用它来释放会话附件，该附件必须比路由处理程序的寿
            命更长（请参阅
            ``DockerConversationRegistry.attach_session``).
        reject_redirects: 拒绝上游重定向而不是转发
            可以逃避固定目标代理的位置。

    Notes:
        每个请求都会创建一个新的：class:`httpx.AsyncClient`。 我们避免使用长连接池，
        因为外层服务器可以处理许多并发会话，每个会话都连接到不
        同的上游端口，而且因为客户端每请求一次就保持一个，这样生命周期和 teardown故事
        变得非常简单。
    """
    if request.headers.get("x-expose-secrets"):
        raise HTTPException(422, "Runtime secret exposure is unsupported")
    url = workspace.host + strip_auth_query(upstream_path)
    headers = _filter_headers(request.headers)
    # 如果客户端通过工作区-session cookie（由无法附加自定义标头的 iframe / img 嵌入使用
    # ）进行身份验证，则不会
    # 入站请求上的 ``X-Session-API-Key`` — 但内部智能体服务器只知道标头。 从工作区的存储
    # 密钥合成一个，以便内部接受代理请求。
    #
    if workspace.api_key:
        headers["X-Session-API-Key"] = workspace.api_key

    async def _request_body() -> AsyncIterator[bytes]:
        async for chunk in request.stream():
            if chunk:
                yield chunk

    # 保持客户端的主体框架：固定长度的主体保持固定长度（httpx 设置 Content-Length 时跳过
    #  chunking），没有主体的请求不发送主体，而是发送一个空的 chunked 主体。
    #
    content: bytes | AsyncIterator[bytes] | None = body
    if body is None and "transfer-encoding" in request.headers:
        content = _request_body()
    elif body is None and "content-length" in request.headers:
        headers["Content-Length"] = request.headers["content-length"]
        content = _request_body()

    # 保持 HTTPX 的上下文打开，直到 StreamingResponse 消耗掉主体。
    stack = AsyncExitStack()
    try:
        client = await stack.enter_async_context(
            httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=timeout, write=30.0, pool=10.0)
            )
        )
        upstream = await stack.enter_async_context(
            client.stream(request.method, url, headers=headers, content=content)
        )
    except BaseException as exc:
        await stack.aclose()
        if not isinstance(exc, httpx.HTTPError):
            raise
        logger.warning("Conversation upstream connection failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Conversation container unreachable",
        ) from exc

    if reject_redirects and upstream.is_redirect:
        await stack.aclose()
        if on_close is not None:
            await on_close()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream redirect is not allowed",
        )

    async def _response_body() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await stack.aclose()
            if on_close is not None:
                await on_close()

    return StreamingResponse(
        _response_body(),
        status_code=upstream.status_code,
        headers={
            k: v
            for k, v in _filter_headers(upstream.headers).items()
            if k.lower() not in _RESPONSE_DROP_HEADERS
        },
        media_type=upstream.headers.get("content-type"),
    )


async def bridge_websocket(
    client_ws: WebSocket,
    workspace: ProxyTarget,
    *,
    upstream_path: str,
) -> None:
    """在浏览器和内部容器之间桥接 WebSocket 会话。

    Precondition: ``client_ws`` 必须已被呼叫者接受。 的
    桥接器不会调用 ``accept()`` 本身，因为外部服务器的 WebSocket-auth 帮助程序在成功
    时接受，并且第二次调用 ``accept()`` 会引
    发。

    关闭语义：当任一端关闭（或错误）时，我们关闭另一端并返回。 无需重新连接。
    """
    upstream_url = workspace.host.replace("http://", "ws://").replace(
        "https://", "wss://"
    ) + strip_auth_query(upstream_path)

    # 本地套接字路由器通过标头/查询参数/第一条消息接受身份验证。 当我们到达这里时，外部
    # 已经接受了套接字 - 但内部是一个单独的服务器，需要自己的身份验证。 从工作区的共享密
    # 钥中生成 ``X-Session-API-Key`` 的内侧部分。（如果内外都无需密钥，则
    # workspace.api_key 是 None，我们不发送头部——这没问题。）
    #
    upstream_headers: dict[str, str] = {}
    if workspace.api_key:
        upstream_headers["X-Session-API-Key"] = workspace.api_key

    try:
        async with websockets.connect(
            upstream_url,
            additional_headers=upstream_headers or None,
        ) as upstream_ws:
            await _bridge_websocket_loop(client_ws, upstream_ws)
    except websockets.exceptions.InvalidStatus as exc:
        logger.warning("Upstream WebSocket rejected (%s) to %s", exc, workspace.host)
        # 第1011章上游 HTTP 故障的最接近匹配，因为浏览器无法看到升级失败的 HTTP 状态代码
        # 。
        #
        await client_ws.close(code=1011)
    except (OSError, websockets.exceptions.WebSocketException) as exc:
        logger.warning(
            "Upstream WebSocket connect failed to %s: %s", workspace.host, exc
        )
        await client_ws.close(code=1011)


async def _bridge_websocket_loop(client_ws: WebSocket, upstream_ws) -> None:
    async def _client_to_upstream() -> None:
        try:
            while True:
                message = await client_ws.receive()
                if message.get("type") == "websocket.disconnect":
                    return
                if "bytes" in message and message["bytes"] is not None:
                    await upstream_ws.send(message["bytes"])
                elif "text" in message and message["text"] is not None:
                    await upstream_ws.send(message["text"])
        except WebSocketDisconnect:
            return

    async def _upstream_to_client() -> None:
        try:
            async for message in upstream_ws:
                if isinstance(message, (bytes, bytearray)):
                    await client_ws.send_bytes(bytes(message))
                else:
                    await client_ws.send_text(message)
        except websockets.exceptions.ConnectionClosed:
            return

    tasks = {
        asyncio.create_task(_client_to_upstream()),
        asyncio.create_task(_upstream_to_client()),
    }
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await upstream_ws.close()
        except Exception as exc:
            logger.debug("Upstream WebSocket close failed (%s)", type(exc).__name__)
        try:
            await client_ws.close()
        except Exception as exc:
            logger.debug("Client WebSocket close failed (%s)", type(exc).__name__)
