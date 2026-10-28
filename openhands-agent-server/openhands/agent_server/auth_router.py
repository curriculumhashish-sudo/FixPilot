"""工作区静态服务器 cookie 身份验证端点。

浏览器无法附加自定义头 ``<iframe src>``, ``<img src>`` 或顶级导航请求，因此工作区静态
文件服务器无法被认证
``X-Session-API-Key`` 只有头部时，当 canvas 前端想要嵌入时工作区 artifacts (HTML 报告
，图表 PDFs).

这些端点让一个已经拥有有效会话 API 的客户端，将其会话密钥交换成一个短生命周期的
cookie，浏览器会自动将其附加到每个工作区请求 — 包括跨站 iframe，多亏了
 ``SameSite=None; Secure; Partitioned``。

该 cookie 受到 ``workspace_router`` 仅的尊重。 所有其他 API 路由仍然需要
``X-Session-API-Key`` 标头。 这是故意的
：将 cookie 保留在 API 的 REST 之外会删除 cookie 身份验证本来会添加的 CSRF 表面。
"""

from fastapi import APIRouter, Request, Response, status

from openhands.agent_server.dependencies import WORKSPACE_SESSION_COOKIE_NAME


auth_router = APIRouter(prefix="/auth", tags=["Auth"])

# Cookie 的生命周期以秒为单位。 设置为有效“永不过期”——浏览器（根据 RFC 6265bis，e.g.
# Chrome）将 Max-Age 限制为约 400 天，无论发送的值如何，因此这是规范允许的最长期限持久化
# 。
#
_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365 * 10  # 10年

# 路径范围：仅在工作区-路由器URLs上发送。 其他 /api/* 端点从未见过这个 cookie。
#
_COOKIE_PATH = "/api/conversations"

# 浏览器将某些主机名视为“安全上下文”，即使在 HTTP 中，因此我们可以在本地开发环境中向这些
# 主机名发送 ``Secure`` 会话 cookie，而无需 TLS。 与 WHATWG 安全上下文规范中的平台安全上
# 下文列表匹配。
#
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _request_is_secure_context(request: Request) -> bool:
    """请求是否源自上下文所在浏览器
    将接受 ``Secure`` cookie。

    True 表示：
      - HTTPS（尊重由在我们面前终止 TLS 的可信代理设置的 ``X-Forwarded-Proto``），以
      及
      - 针对环回主机名的普通 HTTP，浏览器（根据安全上下文规范）将其视为安全。
    """
    forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
    scheme = forwarded_proto.split(",")[0].strip() or request.url.scheme
    if scheme == "https":
        return True

    forwarded_host = request.headers.get("x-forwarded-host", "")
    host = forwarded_host.split(",")[0].strip() or request.url.hostname or ""
    # 去掉可选的 ``:port`` 后缀。 IPv6 主机被括在
    # ``X-Forwarded-Host``; ``request.url.hostname`` 返回它们裸露 (``::1``)，因此仅在单
    # 个冒号上分割。
    #
    if host.startswith("["):
        host = host.partition("]")[0].lstrip("[")
    elif host.count(":") == 1:
        host = host.split(":")[0]
    return host.lower() in _LOOPBACK_HOSTS


def _set_workspace_cookie(
    response: Response, *, value: str, secure: bool, max_age: int
) -> None:
    """发出工作区会话 cookie。

    跨站点 iframe 支持需要 ``SameSite=None; Secure``。 现代 Chrome 还需要
    ``Partitioned`` (CHIPS) 在
    第三方上下文中设置 cookie； 如果没有它，cookie 可能会在第三方 cookie 逐步淘汰的情
    况下被悄悄删除。

    我们总是设置 ``SameSite=None``，以便同一个 cookie 适用于同站点和跨站点 iframe，并
    且始终设置 ``HttpOnly``，以便工作区
    HTML 中的 JS 无法读回它。 当请求来自一个安全的上下文（HTTPS 或回环）时，
    ``Secure`` 会被设置。——只有在这种情况下，浏览器才会存储
    ``SameSite=None`` 会话 cookie。
    """
    response.set_cookie(
        key=WORKSPACE_SESSION_COOKIE_NAME,
        value=value,
        max_age=max_age,
        path=_COOKIE_PATH,
        secure=secure,
        httponly=True,
        samesite="none",
    )
    # Starlette 探索 ``partitioned`` 到 ``http.cookies.Morsel``，它只识别从 Python 3.14
    # 开始的属性。 我们也需要 3.12/3.13 上的标志，因此请修补 ``Set-Cookie`` 标头。 仅当
    # 设置“安全”时才有意义 — 浏览器会忽略非安全 cookie 上的“分区”。
    #
    if secure:
        _append_partitioned_to_last_set_cookie(response)


def _append_partitioned_to_last_set_cookie(
    response: Response, cookie_name: str = WORKSPACE_SESSION_COOKIE_NAME
) -> None:
    """将 ``; Partitioned`` 附加到指定的 Set-Cookie 标头。

    ``MutableHeaders`` 不提供“按名称编辑”辅助功能，因为我们需要小心不要覆盖任何其他父
    级中间件已排队的 Set-Cookie 头。
    """
    raw = response.raw_headers
    for idx in range(len(raw) - 1, -1, -1):
        name, value = raw[idx]
        if name.lower() == b"set-cookie" and value.startswith(
            cookie_name.encode("latin-1") + b"="
        ):
            if b"partitioned" not in value.lower():
                raw[idx] = (name, value + b"; Partitioned")
            return


@auth_router.post(
    "/workspace-session",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Cookie set"},
        401: {"description": "Missing or invalid X-Session-API-Key header"},
    },
)
async def create_workspace_session(request: Request, response: Response) -> Response:
    """创建一个工作区范围的会话 cookie。

    调用者必须已经通过 ``X-Session-API-Key`` 标头进行身份验证（由父路由器的依赖项强制
    执行）。 cookie 值是经过验证的会话 API 密钥本身
    ； 它是HttpOnly，所以工作区HTML中的JS无法读回它。
    """
    session_api_key = request.headers.get("x-session-api-key", "")
    _set_workspace_cookie(
        response,
        value=session_api_key,
        secure=_request_is_secure_context(request),
        max_age=_COOKIE_MAX_AGE_SECONDS,
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@auth_router.delete(
    "/workspace-session",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={204: {"description": "Cookie cleared"}},
)
async def delete_workspace_session(request: Request, response: Response) -> Response:
    """清除工作区会话 cookie。

    浏览器通过``(name, domain, path)``来识别cookies； 因此，删除 cookie 必须共享原始
    cookie 的属性。 我们用空值和
    ``max_age=0`` 覆盖，以便浏览器立即删除它。
    """
    _set_workspace_cookie(
        response,
        value="",
        secure=_request_is_secure_context(request),
        max_age=0,
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
