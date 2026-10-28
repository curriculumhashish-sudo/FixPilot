"""智能体插件 ``mcp.json`` 加载器（规范§7.2，§9）。

读取根级 ``mcp.json``（无点）并将每个条目映射到
：类：`~openhands.sdk.mcp.config.MCPServer`。 映射不是重命名：
portable format 携带了我们模型中没有的语义，因此这里的工作是扩展占位符（§9.2），路径
包含（§4.1，§7.2.1）以及远程 URL / 头部验证 — 每
个条目都按需应用，因此一个坏服务器不会打垮其兄弟服务器或另一个组件类型（§7.2.2）。

``agent_plugins.py`` 而不是在其中：manifest和 MCP 配置文件是分开的文档，各自独立模式
并保持失败边界分离。
"""

import ipaddress
import json
import re
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from pydantic import SecretStr, ValidationError

from openhands.sdk.extensions.fetch import get_cache_path
from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.config import MCPServer
from openhands.sdk.plugin.format.base import _load_schema
from openhands.sdk.utils.path import get_user_persistence_dir, resolves_within


logger = get_logger(__name__)

# ：位于插件根目录，没有前导点（与 Claude 代码 ``.mcp.json`` 不同）。
MCP_FILE: Final[str] = "mcp.json"

MCP_SCHEMA_URL: Final[str] = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
_MCP_SCHEMA_FILE: Final[str] = "mcp-1.0.0.schema.json"

# ：传输层我们联系。 规范中 ``sse`` 为 OPTIONAL，且 MCP 自身也将其已弃用，因此 ``sse``
# 条目会根据 §7.2.2 规则 4 作为不支持的传输层被跳过，而不会悄然经由其他传输层提供服务。
#
SUPPORTED_TRANSPORTS: Final[frozenset[str]] = frozenset({"stdio", "streamable-http"})

_PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"\$\{(PLUGIN_ROOT|PLUGIN_DATA)\}")

# : 客户端生成的头信息，用于实现 HTTP 或 MCP。 §7.2.1 指出，这些头信息优先于同名配置头，
# 因此配置的头会被丢弃：保留，HTTPx 会发送它们原样 -- 伪造 ``Host``，或一个
# ``Content-Length`` 与正文冲突。
#
_CLIENT_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "accept",
        "connection",
        "content-length",
        "content-type",
        "host",
        "keep-alive",
        "last-event-id",
        "mcp-protocol-version",
        "mcp-session-id",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)

#: RFC 9110 token 个字符，标题字段名称的合法字母。
_TOKEN_CHARS: Final[frozenset[str]] = frozenset(
    "!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


# ：``PLUGIN_DATA`` 目录的父目录（第 9.1 节）。 在 ``plugins/`` 之外，其：每个子项都作为
# 插件加载。 在导入时绑定，与其他默认值一样：此处，因此稍后的持久化-dir 更改需要
# ``plugin_data_root``。
#
DEFAULT_PLUGIN_DATA_DIR = get_user_persistence_dir() / "plugin-data"


class MCPConfigError(ValueError):
    """``mcp.json`` 文档或其中的一个服务器条目无效。

    对于插件来说永远不会致命：调用者将其变成禁用的 MCP 组件或跳过的服务器条目，根据 §
    7.2.2。
    """


def get_plugin_data_dir(plugin_root: Path, *, data_root: Path | None = None) -> Path:
    """返回插件的 ``PLUGIN_DATA`` 目录，而不创建它。

    由解析的根（而不是名称）键入：根在更新中保持稳定，并且其他地方的同名插件不得共享
    数据。
    """
    return get_cache_path(
        plugin_root.resolve().as_posix(), data_root or DEFAULT_PLUGIN_DATA_DIR
    )


def load_mcp_servers(
    plugin_dir: Path,
    *,
    plugin_root: Path,
    plugin_data: Path,
) -> dict[str, MCPServer]:
    """从 ``plugin_dir`` 加载 ``mcp.json``。

    Args:
        plugin_dir: 给定的插件目录（在消息中使用）。
        plugin_root: 文件系统解析的插件根目录 - ``${PLUGIN_ROOT}``,
            以及包路径的包含边界。
        plugin_data: 插件的持久数据目录 - ``${PLUGIN_DATA}``。

    Returns:
        加载的服务器。 当 ``mcp.json`` 不存在时为空（§6.2）或整个文档无效（§7.2.2 规
        则 2）。
    """
    mcp_path = plugin_dir / MCP_FILE
    if not mcp_path.is_file() or not resolves_within(mcp_path, plugin_root):
        return {}

    try:
        entries = _read_document(mcp_path)
    except MCPConfigError as e:
        logger.warning("Disabling MCP for %s: %s", plugin_dir, e)
        return {}

    servers: dict[str, MCPServer] = {}
    for name, entry in entries.items():
        try:
            servers[name] = _load_server(entry, plugin_root, plugin_data)
        except MCPConfigError as e:
            logger.warning("Skipping MCP server %r in %s: %s", name, mcp_path, e)

    if servers:
        logger.info("Loaded %d MCP server(s) from %s", len(servers), mcp_path)
    return servers


def _read_document(mcp_path: Path) -> dict[str, Any]:
    """验证顶级文档并返回其 ``mcpServers`` 映射。

    这里只检查顶层。 条目一次验证一个
    :func:`_load_server`，因此单个格式错误的条目无法禁用 MCP
    整个插件。
    """
    try:
        # utf-8-sig：容忍前导 BOM，RFC 8259 让我们忽略。
        document = json.loads(mcp_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise MCPConfigError(f"invalid JSON in {mcp_path}: {e}") from e
    except (OSError, UnicodeDecodeError) as e:
        raise MCPConfigError(f"failed to read {mcp_path}: {e}") from e

    try:
        Draft202012Validator(_top_level_schema()).validate(document)
    except JSONSchemaValidationError as e:
        raise MCPConfigError(f"invalid {MCP_FILE}: {e.message}") from e

    # 该声明的版本被粘贴模式's ``$schema`` const，且manifest被固定为同一1.0.0版本，因此§
    # 7.2.2的“目标版本不同于” plugin.json在我们支持一个版本的情况下，这种情况不会出现。
    #
    return document["mcpServers"]


def _load_server(entry: Any, plugin_root: Path, plugin_data: Path) -> MCPServer:
    """验证一个服务器条目并将其映射到 ``MCPServer``。"""
    try:
        _server_validator().validate(entry)
    except JSONSchemaValidationError as e:
        raise MCPConfigError(e.message) from e

    transport = entry["type"]
    if transport not in SUPPORTED_TRANSPORTS:
        raise MCPConfigError(f"unsupported transport {transport!r}")

    fields = (
        _stdio_fields(entry, plugin_root, plugin_data)
        if transport == "stdio"
        else _remote_fields(entry)
    )
    try:
        server = MCPServer.model_validate(fields)
    except ValidationError as e:  # pragma: no cover - the schema constrains this
        raise MCPConfigError(str(e)) from e

    if transport == "stdio":
        # §9.1：它必须在子进程启动之前存在并且可写。 仅当已知该条目是可用的 stdio 服务器
        # 时才创建，因此仅远程、无效或拒绝的条目不会在磁盘上留下任何痕迹。
        #
        try:
            plugin_data.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise MCPConfigError(f"cannot create PLUGIN_DATA {plugin_data}: {e}") from e

    # 已经全面扩展； §9.2 禁止扩展任何其他内容。
    return server.as_literal()


def _stdio_fields(
    entry: dict[str, Any], plugin_root: Path, plugin_data: Path
) -> dict[str, Any]:
    """映射 stdio 条目：解析命令、展开、包含 cwd。"""
    expand = _expander(plugin_root, plugin_data)

    env = {key: expand(value) for key, value in entry.get("env", {}).items()}
    # §9.1：我们的设置是最后设置的，插件无法覆盖它们。 模式已拒绝声明任一名称本身的条目
    # 。
    #
    env |= {"PLUGIN_ROOT": str(plugin_root), "PLUGIN_DATA": str(plugin_data)}

    cwd = entry.get("cwd")
    fields = {
        "transport": "stdio",
        # 从未扩展（第 9.2 节），并且一个 token，绝不是 shell 字符串。
        "command": _resolve_command(entry["command"], plugin_root),
        "args": [expand(arg) for arg in entry.get("args", [])],
        "env": {key: SecretStr(value) for key, value in env.items()},
        # §7.2.1：插件根目录是默认的工作目录。
        "cwd": str(
            _resolve_cwd(cwd, expand, plugin_root, plugin_data)
            if cwd is not None
            else plugin_root
        ),
    }
    return fields


def _remote_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """映射 ``streamable-http`` 条目：验证 URL 和文字标头。"""
    return {
        "transport": entry["type"],
        "url": _validate_url(entry["url"]),
        "headers": {
            name: SecretStr(value)
            for name, value in _validate_headers(
                entry.get("headers", {}), entry["url"]
            ).items()
        },
    }


def _expander(plugin_root: Path, plugin_data: Path) -> Callable[[str], str]:
    """返回 §9.2 扩展器：单遍、非递归、两个占位符。

    ``re.sub``次通过，所以文本替换引入的文本永远不会重新扫描 -- 不管路径本身是否包含
    ``${PLUGIN_DATA}`` -- 任何其他占位符式的文本都会
    被构造保留。
    """
    values = {"PLUGIN_ROOT": str(plugin_root), "PLUGIN_DATA": str(plugin_data)}

    def expand(value: str) -> str:
        return _PLACEHOLDER.sub(lambda match: values[match.group(1)], value)

    return expand


def _resolve_command(command: str, plugin_root: Path) -> str:
    """解析 ``command``：一个裸可执行文件名称，或一个 ``./`` 包路径。"""
    if not command.startswith("./"):
        # 平台的可执行搜索只需一个简单的名称。 除了绝对路径、``../`` 或者是裸露的相对路
        # 径之外，任何其他形式都不合法。
        #
        if "/" in command or "\\" in command:
            raise MCPConfigError(
                f"command {command!r} must be a bare executable name or a "
                "plugin-relative path beginning with './'"
            )
        return command
    return str(_contained(plugin_root / command[2:], plugin_root, "command"))


def _resolve_cwd(
    cwd: str,
    expand: Callable[[str], str],
    plugin_root: Path,
    plugin_data: Path,
) -> Path:
    """解析显式 ``cwd``，将其保留在为其写入的根中。

    模式约束三个合法前缀； 它无法检查的是一旦扩展和解决，它们会落在哪里，这就是它所强
    制执行的。
    """
    if cwd.startswith("./"):
        return _contained(plugin_root / expand(cwd[2:]), plugin_root, "cwd")
    root = plugin_data if cwd.startswith("${PLUGIN_DATA}") else plugin_root
    return _contained(Path(expand(cwd)), root, "cwd")


def _contained(path: Path, root: Path, field: str) -> Path:
    """解决 ``path`` 并要求其保持在 ``root`` (§4.1) 范围内。"""
    if not resolves_within(path, root):
        raise MCPConfigError(f"{field} {str(path)!r} escapes {root}")
    return path.resolve()


def _validate_url(url: str) -> str:
    """执行 §7.2.1 的远程端点规则。"""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise MCPConfigError(f"url {url!r} must be an absolute http(s) URL")
    # 检查原始文本： urlsplit 报告空用户 (" https://@host" ) 或片段 (" https://host/#" )
    #  为假，但两者都存在。
    #
    if "@" in parts.netloc:
        raise MCPConfigError(f"url {url!r} must not contain user information")
    if "#" in url:
        raise MCPConfigError(f"url {url!r} must not contain a fragment")
    if parts.scheme == "http" and not _is_loopback(parts.hostname):
        raise MCPConfigError(f"url {url!r} must use https: {parts.hostname} is remote")
    return url


def _is_loopback(host: str) -> bool:
    # 正好是 ``localhost`` 或环回范围内的 IP 文字。 一个仅解析为 1 的名称，或者仅以“127”
    # 开头的名称。 ——不符合条件。
    #
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _validate_headers(headers: dict[str, str], url: str) -> dict[str, str]:
    """强制执行 §7.2.1 的标头规则并删除客户端生成的标头。"""
    seen: set[str] = set()
    for name, value in headers.items():
        if not name or not set(name) <= _TOKEN_CHARS:
            raise MCPConfigError(f"header name {name!r} is not a valid HTTP token")
        if name.lower() in seen:
            raise MCPConfigError(f"header {name!r} is declared more than once")
        if not all(char in " \t" or 0x21 <= ord(char) <= 0x7E for char in value):
            raise MCPConfigError(
                f"header {name!r} has a value that is not a field value"
            )
        seen.add(name.lower())

    dropped = sorted(name for name in headers if name.lower() in _CLIENT_HEADERS)
    if dropped:
        logger.warning(
            "Ignoring client-generated header(s) %s configured for %s",
            ", ".join(dropped),
            url,
        )
    return {k: v for k, v in headers.items() if k.lower() not in _CLIENT_HEADERS}


@cache
def _top_level_schema() -> dict[str, Any]:
    """已删除每台服务器验证的供应商模式。

    源自供应商文档而不是重述，因此顶级字段的封闭集和 ``$schema`` const 保持单一来源。
    """
    schema = _load_schema(_MCP_SCHEMA_FILE)
    top_level = {key: value for key, value in schema.items() if key != "$defs"}
    top_level["properties"] = dict(
        top_level["properties"], mcpServers={"type": "object"}
    )
    return top_level


@cache
def _server_validator() -> Draft202012Validator:
    """根据规范公开的 ``#/$defs/server`` 验证一项。"""
    return Draft202012Validator(
        {"$ref": "#/$defs/server", "$defs": _load_schema(_MCP_SCHEMA_FILE)["$defs"]}
    )
