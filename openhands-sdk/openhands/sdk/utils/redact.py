"""用于编辑日志和错误响应中的敏感数据的实用程序。

该模块提供了一套集中统一的模式和函数，用于检测和删除机密- 包含键的结构化数据（JSON 对
象，头部 URLs, etc.). 它是唯一的事实来源机密在
                                                                                                                   [
 SDK.

副本/消费者（更改时保留同步）：
  - OpenHands/runtime-API → utils/redact.py（部分复制）
  - All-Hands-AI/OpenHands → 直接导入
"""  # noqa: E501

import copy
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx


# 用于与键名称进行子字符串匹配的模式（不区分大小写）。 包含任何这些模式的键都将具有其值
# 已脱敏。
# 示例：api_key、X-Access-token、授权、密码、机密
# 注意：我们使用“AUTHORIZATION”而不是“AUTH”来避免False正数
# 比如“作者”标题。
SECRET_KEY_PATTERNS = frozenset(
    {
        "AUTHORIZATION",
        "COOKIE",
        "CREDENTIAL",
        "KEY",
        "PASSWORD",
        "SECRET",
        "SESSION",
        "TOKEN",
    }
)

# 应该具有全部嵌套值已脱敏的键（不仅仅是检测到的机密个键）。 这些通常包含环境变量或可能
# 包含机密的标头。
#
REDACT_ALL_VALUES_KEYS = frozenset({"environment", "env", "headers"})

# 除了通过 is_secret_key() 匹配 SECRET_KEY_PATTERNS 的任何参数之外，特定的 URL 查询参数
# 名称（小写）应始终为已脱敏。
#
SENSITIVE_URL_PARAMS = frozenset(
    {
        "tavilyapikey",
        "apikey",
        "api_key",
        "token",
        "access_token",
        "secret",
        "key",
    }
)


def is_secret_key(key: str) -> bool:
    """检查键名称是否可能包含机密数据。

    针对已知的机密键模式执行不区分大小写的子字符串匹配。

    Args:
        key: 要检查的键名称（e.g.、“api_key”、“授权”、“X-token”）

    Returns:
        如果键与任何机密模式匹配，则为 True，否则为 False

    Examples:
        >>> is_secret_key("api_key")
        True
        >>> is_secret_key("Authorization")
        True
        >>> is_secret_key("user_name")
        False
    """
    key_upper = key.upper()
    return any(pattern in key_upper for pattern in SECRET_KEY_PATTERNS)


def _redact_all_values(value: Any) -> Any:
    """递归地编辑所有值，同时保留结构（键名称）。"""
    if isinstance(value, Mapping):
        return {k: _redact_all_values(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_all_values(item) for item in value]
    return "<redacted>"


def sanitize_dict(content: Any) -> Any:
    """从结构化数据中递归地编辑可能的机密。

    该函数遍历嵌套的字典/列表结构，并且：
    - 编辑匹配 SECRET_KEY_PATTERNS 的键的值
    - 编辑 REDACT_ALL_VALUES_KEYS 中键的全部嵌套值
    - 保持其他值不变

    Args:
        content: 要清理的字典、列表或标量值

    Returns:
        已清理的副本，其中机密替换为“<redacted>”
    """
    if isinstance(content, Mapping):
        sanitized = {}
        for key, value in content.items():
            key_str = str(key)
            key_lower = key_str.lower()
            if key_lower in REDACT_ALL_VALUES_KEYS:
                sanitized[key] = _redact_all_values(value)
            elif is_secret_key(key_str):
                sanitized[key] = "<redacted>"
            else:
                sanitized[key] = sanitize_dict(value)
        return sanitized
    if isinstance(content, list):
        return [sanitize_dict(item) for item in content]
    return content


def http_error_log_content(response: httpx.Response) -> str | dict:
    """返回日志的 HTTP 错误正文的清理表示。

    对于 JSON 响应，返回带有机密已脱敏的清理字典。 对于非 JSON 响应，返回带有正文长度
    的占位符消息。

    Args:
        response: 从中提取错误内容的 httpx.Response

    Returns:
        可以安全记录的经过清理的字典或字符串
    """
    try:
        return sanitize_dict(response.json())
    except Exception:
        body_len = len(response.text or "")
        return f"<non-JSON response body omitted ({body_len} chars)>"


def redact_url_credentials(url: str, *, preserve_placeholders: bool = False) -> str:
    """编辑嵌入 URL 中的凭据 (e.g.  https://user:token@host ).

    将 ``@`` 之前的 ``user:password`` 或裸 token 部分替换为
    ``****`` 所以，URL 安全用于日志、错误消息和已持久化状态。 SSH URLs (``git@host``)
     和凭据-无 URLs 保持不变。

    ``preserve_placeholders``中，一个持有``${VAR}``引用的用户信息被保留：它在获取时从
    机密注册表中扩展，并不是本身就是一个机密，因此掩
    盖它会破坏克隆。 内联凭据仍然被屏蔽。

    Examples:
        >>> redact_url_credentials("https://oauth2:SECRET@gitlab.com/repo.git")
        ' https://****@gitlab.com/repo.git'
        >>> redact_url_credentials("https://github.com/owner/repo.git")
        ' https://github.com/owner/repo.git'
        >>> redact_url_credentials("git@github.com:owner/repo.git")
        'git@github.com:owner/repo.git'
        >>> redact_url_credentials(
        ...     "https://x-token-auth:${TOKEN}@host/r.git", preserve_placeholders=True
        ... )
        ' https://x-token-auth:${TOKEN}@host/r.git'
    """
    match = re.match(r"^(https?://)([^@/]+)@(.+)$", url)
    if not match:
        return url
    if preserve_placeholders and "${" in match.group(2):
        return url
    return f"{match.group(1)}****@{match.group(3)}"


# 匹配较大字符串中任意位置嵌入的 ``http(s)://user:token@`` 凭据。 userinfo 部分不包括
# ``/``、``@`` 和空格，因此匹配在第一个凭据边界处停止，并且永远不会跨越路径段或另一个
# token。
#
_EMBEDDED_URL_CREDENTIALS_RE = re.compile(r"(https?://)[^/@\s]+@", re.IGNORECASE)


def redact_url_credentials_in_text(text: str) -> str:
    """编辑 ``https?://user:token@host`` 凭据嵌入任意文本中。

    不同于：func：`redact_url_credentials`该端点是锚定的，只有在被点击时才会被删除 *
    entire* string 是凭据-bearing
    URL, 这扫描嵌入的 URLs 在更大的字符串中e.g. git ``stderr`` 例如
    ``fatal: unable to access 'https://oauth2:SECRET@github.com/o/r.git/': 403``) 并
    将每个
    凭据部分替换为 ``****``。

    Args:
        text: 任意文本，可能包含一个或多个凭据-bearing URLs.

    Returns:
        每个嵌入的 URL 凭据的文本被 ``****`` 替换。

    Examples:
        >>> redact_url_credentials_in_text(
        ...     "fatal: unable to access 'https://oauth2:SECRET@github.com/o/r.git/'"
        ... )
        “致命：无法访问 ' https://****@github.com/o/r.git/'"
        >>> redact_url_credentials_in_text("no credentials here")
        “这里没有凭据”
    """
    return _EMBEDDED_URL_CREDENTIALS_RE.sub(r"\g<1>****@", text)


def redact_url_params(url: str) -> str:
    """从 URL 字符串中编辑敏感查询参数值。

    解析 URL，检查每个查询参数名称
    ``SENSITIVE_URL_PARAMS``（精确，不区分大小写）和 ``is_secret_key()``（子字符串模
    式匹配），并将匹配值替换为
    ``<redacted>``.

    Args:
        url: 要清理的 URL 字符串。

    Returns:
        敏感查询参数值的 URL 被替换为“<redacted>”。 如果URL没有查询参数或者无法解析，
        则原样返回。

    Examples:
        >>> redact_url_params("https://example.com/search?q=hello&apikey=secret123")
        ' https://example.com/search?q=hello&apikey=%3Credacted%3E'
        >>> redact_url_params("https://example.com/path")
        ' https://example.com/path'
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return url

    if not parsed.query:
        return url

    # parse_qs 以列表形式返回值； keep_blank_values 保留具有空值的参数，因此重建的 URL
    # 与原始形状匹配。
    #
    params = parse_qs(parsed.query, keep_blank_values=True)

    redacted_params: dict[str, list[str]] = {}
    for param_name, values in params.items():
        if param_name.lower() in SENSITIVE_URL_PARAMS or is_secret_key(param_name):
            redacted_params[param_name] = ["<redacted>"] * len(values)
        else:
            redacted_params[param_name] = values

    # doseq=True tells urlencode to unpack the value lists correctly.
    redacted_query = urlencode(redacted_params, doseq=True)
    return urlunparse(parsed._replace(query=redacted_query))


def _walk_redact_urls(obj: Any) -> Any:
    """递归地遍历嵌套的字典/列表，将 URL 参数脱敏应用于字符串。"""
    if isinstance(obj, dict):
        return {k: _walk_redact_urls(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_redact_urls(item) for item in obj]
    if isinstance(obj, str) and "?" in obj:
        return redact_url_params(obj)
    return obj


def sanitize_config(config: dict[str, Any]) -> dict[str, Any]:
    """深度复制配置字典、redact 机密键和 redact URL 查询参数。

    将 ``sanitize_dict``（基于键的脱敏用于标头、env、api_key、token 等）与
    ``redact_url_params``（URL 查询参
    数脱敏用于字符串值，例如 ``https://api.example.com?apiKey=secret``）。

    Args:
        config: 配置字典 (e.g. MCP 服务器配置）。

    Returns:
        用于日志记录的经过清理的深层副本。
    """
    config = copy.deepcopy(config)
    config = sanitize_dict(config)
    config = _walk_redact_urls(config)
    return config


_SENSITIVE_ENTRY_RE = re.compile(
    r"(?P<head>(?P<kq>\\?[\"'])[\w-]*(?:key|secret|token|password|authorization)"
    r"[\w-]*(?P=kq)\s*:\s*)(?P<q>\\?[\"'])(?P<value>.*?)(?P=q)",
    re.IGNORECASE | re.DOTALL,
)


def redact_text_secrets(text: str) -> str:
    """从配置对象的字符串表示形式中编辑机密。

    当您有一个 Pydantic 模型或其他对象，其 ``str()`` 输出包含凭据但无法转换为字典时很
    有用
    ``sanitize_dict``.

    编辑：
    - ``api_key='...'`` 图案
    - 字典、JSON 以及键包含 KEY、SECRET、TOKEN、PASSWORD 或 AUTHORIZATION 的标头条目
    ，无论是引号样式还是任何大小写
    - URL 查询参数匹配常见的机密名称

    Args:
        text: 要编辑的字符串。

    Returns:
        将机密的字符串替换为 ``<redacted>``。
    """
    # api_key='...' patterns (single or double quotes)
    text = re.sub(r"api_key='[^']*'", "api_key='<redacted>'", text)
    text = re.sub(r'api_key="[^"]*"', 'api_key="<redacted>"', text)

    # JSON 和包含敏感键名的头字段：使用双引号（在消息中嵌入时需要转义，如 JSON），任何大
    # 小写，以及如 x-API-key 这样的带破折号的头字段。
    #
    text = _SENSITIVE_ENTRY_RE.sub(r"\g<head>\g<q><redacted>\g<q>", text)

    # URL 查询参数
    text = re.sub(
        r"((?:tavilyApiKey|apiKey|api_key|token|access_token|secret|key)=)"
        r"[^&\s'\")\]]+",
        r"\g<1><redacted>",
        text,
        flags=re.IGNORECASE,
    )

    # 裸 API 键文字（常见提供程序格式）
    text = redact_api_key_literals(text)

    return text


# 来自常见提供商的裸 API 键文字的编译模式。 每个分支都匹配一个已知的前缀，后跟密钥主体。
#  字边界 (\b) 阻止匹配部分 token。
#
_API_KEY_LITERAL_RE = re.compile(
    r"\b("
    # OpenRouter / OpenAI / Anthropic
    r"sk-(?:or-v1|proj|ant-(?:api|oat)\d{2})-[A-Za-z0-9_-]{20,}"
    r"|gsk_[A-Za-z0-9]{20,}"  # GROQ
    r"|hf_[A-Za-z0-9]{20,}"  # HuggingFace
    r"|tgp_v1_[A-Za-z0-9_-]{20,}"  # 一起人工智能
    r"|ghp_[A-Za-z0-9]{20,}"  # GitHubPAT（经典）
    r"|github_pat_[A-Za-z0-9_]{20,}"  # GitHub PAT（细粒度）
    r"|ghu_[A-Za-z0-9]{20,}"  # GitHub 用户到服务器 token
    r"|ghs_[A-Za-z0-9]{20,}"  # GitHub 服务器到服务器 token
    r"|gho_[A-Za-z0-9]{20,}"  # GitHub OAuth token
    r"|sk-oh-[A-Za-z0-9_-]{10,}"  # OpenHands API 键
    r"|ctx7sk-[A-Za-z0-9_-]{10,}"  # Context7 MCP 键
    r"|cla_[A-Za-z0-9_-]{20,}"  # Claude.ai MCP token
    r"|sntryu_[A-Za-z0-9]{10,}"  # 哨兵 token
    r"|lin_api_[A-Za-z0-9]{10,}"  # 线性 API token
    r"|tvly-[A-Za-z0-9_-]{10,}"  # 泰维利钥匙
    r"|ATATT3x[A-Za-z0-9_-]{10,}"  # 吉拉/Atlassian token
    r"|xoxb-[A-Za-z0-9_-]{20,}"  # Slack 机器人 token
    r"|xoxp-[A-Za-z0-9_-]{20,}"  # 松弛用户 token
    r"|Bearer\s+[A-Za-z0-9_.-]{20,}"  # 承载者 token
    r")"
)


def redact_api_key_literals(text: str) -> str:
    """将公共提供程序中的裸 API 键文字替换为 ``<redacted>``。

    在文本中任何地方匹配已知的键前缀（OpenAI，Anthropic，OpenRouter，GROQ，
    HuggingFace，Together AI，GitHub，S
    entry，Linear，Tavily，Slack，OpenHands session token 等）。

    Args:
        text: 要扫描的字符串。

    Returns:
        具有匹配键文字的字符串被替换。
    """
    return _API_KEY_LITERAL_RE.sub("<redacted>", text)
