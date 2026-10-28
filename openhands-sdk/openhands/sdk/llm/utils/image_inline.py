"""Inline ``http(s)://`` image URLs 作为 base64 ``data:``  URLs.

一些模型 APIs （特别是 Moonshot 的公共 Kimi） 端点) reject http(s) image URLs 仅接受
base64 编码的图像内容。 当此
轮次生效时，每  ``ImageContent`` 其条目还不是 ``data:``  URL 被获取并重写为
``data:{mime};base64,{...}`` 在
请求离开之前 SDK.

失败是非致命的：原始的 URL 被保留，并且允许上游产生其本机错误。 我们还保留了一个小的
内存缓存，因此每次对话时都不会重新下载相同的图像。

Security: 请求根据环回的 SSRF 块列表进行验证，
手动遵循私有、链路本地、多播和其他保留的 IP 范围以及重定向，以便重新验证每个跃点。 套
装
``OH_INLINE_IMAGE_ALLOW_PRIVATE_HOSTS=1`` 只有在 tests/dev 才能绕过。
"""

from __future__ import annotations

import asyncio
import base64
import copy
import ipaddress
import os
import socket
from collections import OrderedDict
from threading import Lock
from urllib.parse import urljoin, urlparse

import httpx

from openhands.sdk.llm.message import ImageContent, Message
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

# 我们愿意下载的最大单个图像大小（以兆字节为单位）。 镜像 LiteLLM 的
# MAX_IMAGE_URL_DOWNLOAD_SIZE_MB 默认值。
#
DEFAULT_MAX_IMAGE_DOWNLOAD_MB = 20
MAX_IMAGE_DOWNLOAD_MB: int = int(
    os.environ.get("OH_INLINE_IMAGE_MAX_MB", DEFAULT_MAX_IMAGE_DOWNLOAD_MB)
)

# 限制进程内缓存在所有内联图像中可以容纳的内存量。
DEFAULT_CACHE_MAX_BYTES = 64 * 1024 * 1024  # 64MB
CACHE_MAX_BYTES: int = int(
    os.environ.get("OH_INLINE_IMAGE_CACHE_BYTES", DEFAULT_CACHE_MAX_BYTES)
)

# 每个图像获取超时（秒）。 通过 env 覆盖慢速网络。
DEFAULT_FETCH_TIMEOUT_S = 30.0
FETCH_TIMEOUT_S: float = float(
    os.environ.get("OH_INLINE_IMAGE_FETCH_TIMEOUT_S", DEFAULT_FETCH_TIMEOUT_S)
)

# 我们将手动遵循的最大数量 HTTP 重定向。
MAX_REDIRECTS = 5

# SSRF 检查的选择退出开关； 仅限 tests/dev。
_ALLOW_PRIVATE_HOSTS = os.environ.get(
    "OH_INLINE_IMAGE_ALLOW_PRIVATE_HOSTS", ""
).lower() in {"1", "true", "yes"}

_EXT_TO_MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "tif": "image/tiff",
}

# 只有内联内容上游模型才能真正解码为图像。 如果服务器返回 ``200 OK`` 和 ``text/html``（
# soft-404、auth wall、CDN 错误页面），则内联字节将生成 ``data:text/html;...``，模型会默
# 默地拒绝该值。 相反，我们回到原来的URL。
#
_ALLOWED_IMAGE_MIMES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/bmp",
        "image/tiff",
    }
)


class _DataUrlCache:
    """有界 LRU 缓存映射 URL → ``data:`` URL。

    大小受缓存条目的总编码大小限制，因此一些非常大的图像无法将其他所有图像推出。
    """

    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes
        self._entries: OrderedDict[str, str] = OrderedDict()
        self._size_bytes = 0
        self._lock = Lock()

    def get(self, url: str) -> str | None:
        with self._lock:
            value = self._entries.get(url)
            if value is not None:
                self._entries.move_to_end(url)
            return value

    def put(self, url: str, data_url: str) -> None:
        encoded_size = len(data_url)
        if encoded_size > self._max_bytes:
            # 单个图像大于缓存预算：跳过缓存。
            logger.debug(
                "Image too large to cache (%d bytes > %d byte budget); "
                "will re-fetch. url=%s",
                encoded_size,
                self._max_bytes,
                url,
            )
            return
        with self._lock:
            existing = self._entries.pop(url, None)
            if existing is not None:
                self._size_bytes -= len(existing)
            self._entries[url] = data_url
            self._size_bytes += encoded_size
            while self._size_bytes > self._max_bytes and self._entries:
                _, evicted = self._entries.popitem(last=False)
                self._size_bytes -= len(evicted)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._size_bytes = 0


_CACHE = _DataUrlCache(max_bytes=CACHE_MAX_BYTES)


def maybe_inline_image_urls(
    messages: list[Message],
    *,
    inline_required: bool,
    vision_enabled: bool,
) -> list[Message]:
    """返回带有http(s)图片URLs的分离消息列表，作为Base64编码。

    当 ``inline_required`` 或 ``vision_enabled`` 为 False 时，这是一个无操作快速路径
    ，返回输入列表不变。 否则，使用单个
    共享 ``httpx.Client`` 获取和内联 URL 格式的图像，因此多图像可以从连接池中受益。
    """
    if not vision_enabled or not inline_required:
        return messages

    out: list[Message] | None = None
    client: httpx.Client | None = None
    try:
        for msg_index, message in enumerate(messages):
            new_content_items: list | None = None
            for item_index, item in enumerate(message.content):
                if not isinstance(item, ImageContent):
                    continue
                new_urls: list[str] = []
                changed = False
                for url in item.image_urls:
                    # 仅当我们知道需要进行真正的网络调用时才构建客户端。 URLs 已经从缓存
                    # 中服务过e.g. 在第二轮）不得触发客户端设置。
                    #
                    if _needs_fetch(url) and _CACHE.get(url) is None and client is None:
                        client = httpx.Client(
                            timeout=FETCH_TIMEOUT_S,
                            follow_redirects=False,
                        )
                    inlined = _inline_url(url, client)
                    new_urls.append(inlined)
                    if inlined != url:
                        changed = True
                if not changed:
                    continue
                if new_content_items is None:
                    new_content_items = list(message.content)
                new_content_items[item_index] = item.model_copy(
                    update={"image_urls": new_urls}
                )
            if new_content_items is None:
                continue
            if out is None:
                out = copy.copy(messages)
            out[msg_index] = message.model_copy(update={"content": new_content_items})
    finally:
        if client is not None:
            client.close()

    return out if out is not None else messages


async def amaybe_inline_image_urls(
    messages: list[Message],
    *,
    inline_required: bool,
    vision_enabled: bool,
) -> list[Message]:
    """异步变体：将阻塞的 fetch+encode 工作卸载给工作人员线程。

    由 ``acompletion`` / ``aresponses`` 使用，因此事件循环不会被阻塞
    while images download.
    """
    if not vision_enabled or not inline_required:
        return messages
    return await asyncio.to_thread(
        maybe_inline_image_urls,
        messages,
        inline_required=inline_required,
        vision_enabled=vision_enabled,
    )


def _needs_fetch(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def _inline_url(url: str, client: httpx.Client | None) -> str:
    """返回不变的 URL 或具有 base64 图像字节的 ``data:`` URL。"""
    if url.startswith("data:"):
        return url
    if not _needs_fetch(url):
        # 未知方案（e.g. ``ms://<file_id>``): 留给上游。
        return url

    cached = _CACHE.get(url)
    if cached is not None:
        return cached

    # ``assert`` 将被剥离到 ``python -O`` 下； 使用显式加薪，以便无论优化级别如何，合约
    # 都会得到执行。 不变量由``maybe_inline_image_urls``维护，因此该路径在实践中不可达。
    #
    if client is None:
        raise RuntimeError(
            "internal error: httpx.Client must be provided for http(s) URLs"
        )

    try:
        data_url = _fetch_and_encode(url, client)
    except Exception as e:
        logger.warning(
            "Failed to inline image URL as base64; sending original URL. "
            "url=%s error=%s: %s",
            url,
            type(e).__name__,
            e,
        )
        return url

    _CACHE.put(url, data_url)
    return data_url


def _fetch_and_encode(url: str, client: httpx.Client) -> str:
    """获取 ``url``（手动，SSRF-验证重定向跟随）和
    返回结果 ``data:`` URL。"""
    max_bytes = MAX_IMAGE_DOWNLOAD_MB * 1024 * 1024
    current_url = url
    # +1：初始获取不计入 MAX_REDIRECTS，所以这
    # 循环执行 1 个原始请求 + 最多 MAX_REDIRECTS 个重定向跃点。
    for _ in range(MAX_REDIRECTS + 1):
        _validate_url_target(current_url)
        with client.stream("GET", current_url) as response:
            if response.is_redirect:
                location = response.headers.get("Location") or response.headers.get(
                    "location"
                )
                if not location:
                    # ``raise_for_status()`` 在 3xx 上是无操作，因此直接引发以显示明确的
                    # 已记录错误。
                    #
                    raise ValueError(f"Redirect without Location header: {current_url}")
                current_url = urljoin(current_url, location)
                continue
            response.raise_for_status()
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > max_bytes:
                size_mb = int(content_length) / (1024 * 1024)
                raise ValueError(
                    f"Image exceeds {MAX_IMAGE_DOWNLOAD_MB}MB cap "
                    f"({size_mb:.2f}MB). url={url}"
                )
            mime_type = _derive_mime_type(response.headers.get("Content-Type"), url)
            buffer = bytearray()
            for chunk in response.iter_bytes(chunk_size=64 * 1024):
                buffer.extend(chunk)
                if len(buffer) > max_bytes:
                    size_mb = len(buffer) / (1024 * 1024)
                    raise ValueError(
                        f"Image exceeds {MAX_IMAGE_DOWNLOAD_MB}MB cap "
                        f"({size_mb:.2f}MB). url={url}"
                    )

        encoded = base64.b64encode(bytes(buffer)).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    raise ValueError(f"Exceeded max {MAX_REDIRECTS} redirects for url={url}")


def _validate_url_target(url: str) -> None:
    """如果 ``url`` 解析为非公共地址，则引发 ``ValueError``。

    跳过回环、私有、链路本地、组播和广播范围（IPv4和IPv6），以及像``localhost``和
    ``*.local``这样的DNS主机名的语法捷径。 在初始
    URL 和每个重定向目标上调用。

    Note (TOCTOU): httpx 在连接时执行第二个 DNS 解析，
    所以，一个叛逆的短-TTL  DNS 服务器在检查期间可以提供公共IP，在真实连接上提供私有
    IP。 这是验证-连接模式的已知限制，并且在这一威胁模型中被认为是可接受
    的——嵌入是受大小限制的 MIME 类型和超时，失败时会回退到原始状态 URL.
    """
    if _ALLOW_PRIVATE_HOSTS:
        return

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Refusing non-http(s) scheme {scheme!r}: {url}")
    host = parsed.hostname
    if not host:
        raise ValueError(f"URL has no host: {url}")

    host_lower = host.lower().rstrip(".")
    if host_lower in {"localhost", "ip6-localhost", "ip6-loopback"} or (
        host_lower.endswith(".localhost") or host_lower.endswith(".local")
    ):
        raise ValueError(f"Refusing to fetch local/mDNS host: {host}")

    # IP 字面意思？ 不带DNS直接验证。
    try:
        ip = ipaddress.ip_address(host_lower.strip("[]"))
    except ValueError:
        ip = None
    if ip is not None:
        if _is_disallowed_ip(ip):
            raise ValueError(f"Refusing to fetch disallowed IP {ip}: {url}")
        return

    # 主机名：解析并检查每个返回的地址。
    port = parsed.port or (443 if scheme == "https" else 80)
    addrs = _resolve_host_ips(host, port)
    if not addrs:
        raise ValueError(f"DNS returned no addresses for host {host}: {url}")
    for ip_str in addrs:
        try:
            resolved = ipaddress.ip_address(ip_str)
        except ValueError:
            # 跳过任何我们无法解释为 IP 文字的内容。
            continue
        if _is_disallowed_ip(resolved):
            raise ValueError(
                f"Refusing to fetch host {host} resolving to disallowed "
                f"address {resolved}: {url}"
            )


def _resolve_host_ips(host: str, port: int) -> list[str]:
    """返回 ``host`` 解析为的唯一 IP 文字。

    提取为模块级函数，以便测试可以对其进行修补，而不会毒害进程内 DNS 缓存或需要真正的
    网络访问。
    """
    try:
        addrinfo = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed for host {host}: {e}") from e
    seen: list[str] = []
    for entry in addrinfo:
        sockaddr = entry[4]
        # sockaddr 对于 IPv4 是（主机、端口），对于 IPv6 是（主机、端口、flowinfo、
        # scopeid）； 主机元素始终是字符串形式的 IP 文字。
        #
        ip_str = sockaddr[0]
        if isinstance(ip_str, str) and ip_str not in seen:
            seen.append(ip_str)
    return seen


def _is_disallowed_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
        or (
            isinstance(ip, ipaddress.IPv4Address)
            and ip == ipaddress.IPv4Address("255.255.255.255")
        )
    )


def _derive_mime_type(content_type_header: str | None, url: str) -> str:
    """返回响应正文的经过验证的图像 MIME 类型。

    如果服务器报告非图像 ``Content-Type`` (e.g. ``text/html``
    from a soft-404 or auth wall), raise ``ValueError`` so the caller can
    回退到原始的 URL 而不是内联不可用的字节。
    """
    mime = ""
    if content_type_header:
        mime = content_type_header.split(";", 1)[0].strip()
    if not mime:
        mime = _mime_from_url(url)
    if mime not in _ALLOWED_IMAGE_MIMES:
        raise ValueError(f"Unexpected Content-Type {mime!r} for image URL: {url}")
    return mime


def _mime_from_url(url: str) -> str:
    """根据 URL 路径扩展进行尽力 MIME 推断。

    当扩展名未知或不存在时返回 ``""``，以便
    ``_derive_mime_type`` 上升，调用者回落到原来的 URL。 我们故意不在这里猜测
    ``image/png``：省略
    ``Content-Type`` 的 soft-404 或 auth-wall 会偷偷溜过
    ``_ALLOWED_IMAGE_MIMES`` 守卫。
    """
    path = url.split("?", 1)[0].split("#", 1)[0]
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _EXT_TO_MIME.get(ext, "")
