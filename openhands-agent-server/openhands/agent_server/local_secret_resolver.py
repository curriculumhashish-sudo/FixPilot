"""不使用回环请求，为本服务器提供自身的 ``LookupSecret`` URLs。

``LookupSecret`` 比 HTTP 延迟解析，因此原始值永远不会传输 SDK 客户端。 当客户端和服务
器都在同一个进程中时，这个往返是没有价值且会带来正确性的损
失：在事件循环处的解决会阻塞循环，从而导致客户端超时。 将那些URLs与本地存储进行匹配，
保留懒惰性，丢弃往返。
"""

import os
from urllib.parse import urlsplit

from openhands.agent_server.config import Config
from openhands.agent_server.persistence import get_secrets_store
from openhands.sdk.logger import get_logger
from openhands.sdk.secret import (
    register_local_secret_resolver,
    unregister_local_secret_resolver,
)


logger = get_logger(__name__)

_INTERNAL_SERVER_URL_ENV = "OH_INTERNAL_SERVER_URL"
_DEFAULT_INTERNAL_SERVER_URL = "http://127.0.0.1:8000"
_SECRET_PATH_PREFIX = "/api/settings/secrets/"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _effective_port(scheme: str, port: int | None) -> int | None:
    return port if port is not None else _DEFAULT_PORTS.get(scheme)


def _secret_name_if_local(url: str) -> str | None:
    """当 ``url`` 是该进程自行服务的名称时，返回机密名称。"""
    parsed = urlsplit(url)
    server = urlsplit(os.getenv(_INTERNAL_SERVER_URL_ENV, _DEFAULT_INTERNAL_SERVER_URL))
    if parsed.scheme != server.scheme:
        return None
    if _effective_port(parsed.scheme, parsed.port) != _effective_port(
        server.scheme, server.port
    ):
        return None
    if parsed.hostname != server.hostname and not {
        parsed.hostname,
        server.hostname,
    }.issubset(_LOOPBACK_HOSTS):
        return None
    if not parsed.path.startswith(_SECRET_PATH_PREFIX):
        return None
    name = parsed.path[len(_SECRET_PATH_PREFIX) :]
    # 只有一个光秃秃的名字； 任何更深的东西都是不同的路线。
    if not name or "/" in name:
        return None
    return name


def build_local_secret_resolver(config: Config):
    """构建一个解析器，回答这个服务器的机密 URLs。"""

    def resolve(url: str) -> str | None:
        name = _secret_name_if_local(url)
        if name is None:
            return None
        value = get_secrets_store(config).get_secret(name)
        if value is None:
            # 跳转到 HTTP，因此调用者仍然会看到服务器的 404。
            return None
        logger.debug("Resolved secret '%s' in-process", name)
        return value

    return resolve


class local_secret_resolution:
    """上下文管理器为服务器注册进程内解析器。"""

    def __init__(self, config: Config) -> None:
        self._resolver = build_local_secret_resolver(config)

    def __enter__(self) -> None:
        register_local_secret_resolver(self._resolver)

    def __exit__(self, *exc_info) -> None:
        unregister_local_secret_resolver(self._resolver)
