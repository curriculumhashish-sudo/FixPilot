"""OpenAI 基于订阅身份验证通过 OAuth。

该模块实现了 PKCE 流程，用于与 OpenAI's ChatGPT 服务进行身份验证，允许 ChatGPT Plus/
Pro 订阅的用户使用 Codex 模型而无需消耗
 API 信用。

使用 joserfc 进行 JWT 处理，使用 authlib 进行 OAuth 实用程序，使用 aiohttp 进行回调服
务器。
"""

from __future__ import annotations

import asyncio
import platform
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlencode

from aiohttp import web
from authlib.common.security import generate_token
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from httpx import AsyncClient, Client
from joserfc import jwk, jwt
from joserfc.errors import JoseError

from openhands.sdk.llm.auth.credentials import (
    CredentialStore,
    OAuthCredentials,
    get_credentials_dir,
)
from openhands.sdk.logger import get_logger


if TYPE_CHECKING:
    from openhands.sdk.llm.llm import LLM

# 支持基于订阅的供应商身份验证。 当新供应商获得支持时，在此处添加它们。
#
SupportedVendor = Literal["openai"]
OpenAIAuthMethod = Literal["browser", "device_code"]

logger = get_logger(__name__)

# =========================================================================
# 同意横幅常量
# =========================================================================

CONSENT_BANNER = """\
Signing in with ChatGPT uses your ChatGPT account. By continuing, you confirm \
you are a ChatGPT End User and are subject to OpenAI's Terms of Use.
https://openai.com/policies/terms-of-use/
"""

CONSENT_MARKER_FILENAME = ".chatgpt_consent_acknowledged"


def _get_consent_marker_path() -> Path:
    """获取同意确认标记文件的路径。"""
    return get_credentials_dir() / CONSENT_MARKER_FILENAME


def _has_acknowledged_consent() -> bool:
    """检查用户之前是否已确认同意免责声明。"""
    return _get_consent_marker_path().exists()


def _mark_consent_acknowledged() -> None:
    """标记用户已承认同意免责声明。"""
    marker_path = _get_consent_marker_path()
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.touch()


def _display_consent_and_confirm() -> bool:
    """显示同意横幅并获得用户确认。

    Returns:
        True 如果用户确认，False 否则。

    Raises:
        RuntimeError: 如果未经事先同意以非交互模式运行。
    """
    is_first_time = not _has_acknowledged_consent()

    # 始终显示同意横幅
    print("\n" + "=" * 70)
    print(CONSENT_BANNER)
    print("=" * 70 + "\n")

    # 检查我们是否处于交互式终端中
    if not sys.stdin.isatty():
        if is_first_time:
            raise RuntimeError(
                "Cannot proceed with ChatGPT sign-in: running in non-interactive mode "
                "and consent has not been previously acknowledged. Please run "
                "interactively first to acknowledge the terms."
            )
        # 非交互式但已事先同意 - 继续
        logger.info("Non-interactive mode: using previously acknowledged consent")
        return True

    # 交互模式：提示词确认
    try:
        response = input("Do you want to continue? [y/N]: ").strip().lower()
        if response in ("y", "yes"):
            if is_first_time:
                _mark_consent_acknowledged()
            return True
        return False
    except (EOFError, KeyboardInterrupt):
        print()  # ^C 后换行
        return False


# OpenAI Codex OAuth 配置。这是 OpenAI 的 OAuth 流程的公共客户端 ID（安全提交）
#
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
ISSUER = "https://auth.openai.com"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"
CODEX_API_ENDPOINT = "https://chatgpt.com/backend-api/codex/responses"
DEFAULT_OAUTH_PORT = 1455
OAUTH_TIMEOUT_SECONDS = 300  # 5分钟
DEVICE_CODE_TIMEOUT_SECONDS = 900  # 15分钟
JWKS_CACHE_TTL_SECONDS = 3600  # 1小时


# 可通过 ChatGPT 订阅（而非 API）获得模型。
OPENAI_CODEX_MODELS = frozenset(
    {
        "gpt-6.1-sol",
        "gpt-6-sol",
        "gpt-6-luna",
        "gpt-6-astra",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.5",
    }
)


# 线程安全JWKS缓存
class _JWKSCache:
    """线程安全缓存 OpenAI 的 JWKS（JSON Web 键集）。"""

    def __init__(self) -> None:
        self._keys: jwk.KeySetSerialization = {"keys": []}
        self._fetched_at: float = 0
        self._lock = threading.Lock()

    def get_key_set(self) -> jwk.KeySet:
        """获取 JWKS，如果缓存已过时或为空，则从 OpenAI 获取。

        Returns:
            KeySet 用于验证 JWT 签名。

        Raises:
            RuntimeError: 如果无法获取JWKS。
        """
        with self._lock:
            now = time.time()
            if (
                not self._keys["keys"]
                or (now - self._fetched_at) > JWKS_CACHE_TTL_SECONDS
            ):
                self._fetch_jwks()
            return jwk.KeySet.import_key_set(self._keys)

    def _fetch_jwks(self) -> None:
        """从 OpenAI 的众所周知的端点中获取 JWKS。"""
        try:
            with Client(timeout=10) as client:
                response = client.get(JWKS_URL)
                response.raise_for_status()
                self._keys = response.json()
                self._fetched_at = time.time()
                logger.debug(
                    f"Fetched JWKS from OpenAI: {len(self._keys.get('keys', []))} keys"
                )
        except Exception as e:
            raise RuntimeError(f"Failed to fetch OpenAI JWKS: {e}") from e

    def clear(self) -> None:
        """清除缓存（对于测试有用）。"""
        with self._lock:
            self._keys = {"keys": []}
            self._fetched_at = 0


_jwks_cache = _JWKSCache()


def _generate_pkce() -> tuple[str, str]:
    """使用 authlib 生成 PKCE 验证程序和质询。"""
    verifier = generate_token(43)
    challenge = create_s256_code_challenge(verifier)
    return verifier, challenge


def _extract_chatgpt_account_id(access_token: str) -> str | None:
    """通过签名验证从 JWT 访问令牌中提取 chatgpt_account_id。

    在提取声明之前，使用 OpenAI 发布的 JWKS 验证 JWT 签名。 这可以防止通过 OAuth 回调
    拦截注入被操纵的 token 的攻击。

    Args:
        access_token: OAuth 流程中的 JWT 访问令牌

    Returns:
        如果找到且签名有效则为 chatgpt_account_id，否则为 None
    """
    try:
        # 获取 JWKS 并验证 JWT 签名
        key_set = _jwks_cache.get_key_set()
        token = jwt.decode(access_token, key_set)

        # 验证标准声明（发行者）
        claims_registry = jwt.JWTClaimsRegistry()
        claims_registry.validate(token.claims)

        # 从嵌套结构中提取帐户 ID
        auth_info = token.claims.get("https://api.openai.com/auth", {})
        account_id = auth_info.get("chatgpt_account_id")

        if account_id:
            logger.debug(f"Extracted chatgpt_account_id: {account_id}")
            return account_id
        else:
            logger.warning("chatgpt_account_id not found in JWT payload")
            return None

    except JoseError as e:
        logger.warning(f"JWT signature verification failed: {e}")
        return None
    except RuntimeError as e:
        # JWKS 获取失败 - 记录但不崩溃
        logger.warning(f"Could not verify JWT: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to decode JWT: {e}")
        return None


def _build_authorize_url(redirect_uri: str, code_challenge: str, state: str) -> str:
    """构建 OAuth 授权 URL。"""
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email offline_access",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "state": state,
        "originator": "openhands",
    }
    return f"{ISSUER}/oauth/authorize?{urlencode(params)}"


async def _exchange_code_for_tokens(
    code: str, redirect_uri: str, code_verifier: str
) -> dict[str, Any]:
    """将授权代码交换为 token。"""
    async with AsyncClient() as client:
        response = await client.post(
            f"{ISSUER}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": CLIENT_ID,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not response.is_success:
            raise RuntimeError(f"Token exchange failed: {response.status_code}")
        return response.json()


@dataclass(frozen=True)
class DeviceCode:
    """OpenAI 设备授权详细信息。"""

    verification_url: str
    user_code: str
    device_auth_id: str
    interval: int


async def _request_device_code() -> DeviceCode:
    """请求用于无头 ChatGPT 登录的设备代码。"""
    async with AsyncClient() as client:
        response = await client.post(
            f"{ISSUER}/api/accounts/deviceauth/usercode",
            json={"client_id": CLIENT_ID},
            headers={"Content-Type": "application/json"},
        )
        if not response.is_success:
            if response.status_code == 404:
                raise RuntimeError(
                    "Device code login is not enabled for this OpenAI server. "
                    "Use browser login instead."
                )
            raise RuntimeError(
                f"Device code request failed with status {response.status_code}"
            )

        data = response.json()

    try:
        interval = int(str(data.get("interval", 5)).strip())
        user_code = data.get("user_code") or data.get("usercode")
        device_auth_id = data["device_auth_id"]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Invalid device code response from OpenAI") from exc

    if not user_code or not isinstance(user_code, str):
        raise RuntimeError("Invalid device code response from OpenAI")

    return DeviceCode(
        verification_url=f"{ISSUER}/codex/device",
        user_code=user_code,
        device_auth_id=device_auth_id,
        interval=max(interval, 1),
    )


async def _poll_device_code_once(device_code: DeviceCode) -> dict[str, Any] | None:
    """轮询一次以获取 OpenAI 设备登录结果。

    当授权仍待处理时返回 ``None``。
    """
    async with AsyncClient() as client:
        response = await client.post(
            f"{ISSUER}/api/accounts/deviceauth/token",
            json={
                "device_auth_id": device_code.device_auth_id,
                "user_code": device_code.user_code,
            },
            headers={"Content-Type": "application/json"},
        )

    if response.is_success:
        return response.json()

    if response.status_code in (403, 404):
        return None

    raise RuntimeError(f"Device auth failed with status {response.status_code}")


async def _poll_device_code(device_code: DeviceCode) -> dict[str, Any]:
    """轮询直到 OpenAI 发出用于设备登录的授权代码。"""
    deadline = time.monotonic() + DEVICE_CODE_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        token_response = await _poll_device_code_once(device_code)
        if token_response is not None:
            return token_response

        await asyncio.sleep(
            min(device_code.interval, max(0, deadline - time.monotonic()))
        )

    raise RuntimeError("Device auth timed out after 15 minutes")


async def _refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """使用刷新令牌刷新访问令牌。"""
    async with AsyncClient() as client:
        response = await client.post(
            f"{ISSUER}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not response.is_success:
            raise RuntimeError(f"Token refresh failed: {response.status_code}")
        return response.json()


def _refresh_access_token_sync(refresh_token: str) -> dict[str, Any]:
    """使用刷新令牌同步刷新访问令牌。"""
    with Client() as client:
        response = client.post(
            f"{ISSUER}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not response.is_success:
            raise RuntimeError(f"Token refresh failed: {response.status_code}")
        return response.json()


# HTML OAuth 模板回调
_HTML_SUCCESS = """<!DOCTYPE html>
<html>
<head>
  <title>OpenHands - Authorization Successful</title>
  <style>
    body { font-family: system-ui, sans-serif; display: flex;
           justify-content: center; align-items: center; height: 100vh;
           margin: 0; background: #1a1a2e; color: #eee; }
    .container { text-align: center; padding: 2rem; }
    h1 { color: #4ade80; }
    p { color: #aaa; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Authorization Successful</h1>
    <p>You can close this window and return to OpenHands.</p>
  </div>
  <script>setTimeout(() => window.close(), 2000);</script>
</body>
</html>"""

_HTML_ERROR = """<!DOCTYPE html>
<html>
<head>
  <title>OpenHands - Authorization Failed</title>
  <style>
    body { font-family: system-ui, sans-serif; display: flex;
           justify-content: center; align-items: center; height: 100vh;
           margin: 0; background: #1a1a2e; color: #eee; }
    .container { text-align: center; padding: 2rem; }
    h1 { color: #f87171; }
    p { color: #aaa; }
    .error { color: #fca5a5; font-family: monospace; margin-top: 1rem;
             padding: 1rem; background: rgba(248,113,113,0.1);
             border-radius: 0.5rem; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Authorization Failed</h1>
    <p>An error occurred during authorization.</p>
    <div class="error">{error}</div>
  </div>
</body>
</html>"""


class OpenAISubscriptionAuth:
    """处理 OpenAI ChatGPT 订阅访问的 OAuth 身份验证。"""

    def __init__(
        self,
        credential_store: CredentialStore | None = None,
        oauth_port: int = DEFAULT_OAUTH_PORT,
    ):
        """初始化 OpenAI 订阅身份验证处理程序。

        Args:
            credential_store: 可选自定义凭据商店。
            oauth_port: 本地 OAuth 回调服务器的端口。
        """
        self._credential_store = credential_store or CredentialStore()
        self._oauth_port = oauth_port

    @property
    def vendor(self) -> str:
        """获取供应商名称。"""
        return "openai"

    def get_credentials(self) -> OAuthCredentials | None:
        """如果存在，则存储凭据。"""
        return self._credential_store.get(self.vendor)

    def has_valid_credentials(self) -> bool:
        """检查是否存在有效（未过期）凭据。"""
        creds = self.get_credentials()
        return creds is not None and not creds.is_expired()

    async def refresh_if_needed(self) -> OAuthCredentials | None:
        """如果过期，请刷新凭据。

        Returns:
            更新凭据，如果不存在凭据，则更新 None。

        Raises:
            RuntimeError: 如果token刷新失败。
        """
        creds = self.get_credentials()
        if creds is None:
            return None

        if not creds.is_expired():
            return creds

        logger.info("Refreshing OpenAI access token")
        tokens = await _refresh_access_token(creds.refresh_token)
        updated = self._credential_store.update_tokens(
            vendor=self.vendor,
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            expires_in=tokens.get("expires_in", 3600),
        )
        return updated

    def refresh_if_needed_sync(self) -> OAuthCredentials | None:
        """如果过期则同步刷新凭据。"""
        creds = self.get_credentials()
        if creds is None:
            return None

        if not creds.is_expired():
            return creds

        logger.info("Refreshing OpenAI access token")
        tokens = _refresh_access_token_sync(creds.refresh_token)
        return self._credential_store.update_tokens(
            vendor=self.vendor,
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            expires_in=tokens.get("expires_in", 3600),
        )

    async def login(
        self,
        open_browser: bool = True,
        auth_method: OpenAIAuthMethod = "browser",
    ) -> OAuthCredentials:
        """执行 OAuth 登录流程。

        browser 方法启动本地 HTTP 服务器来处理 OAuth 回调，为用户身份验证打开浏览器，
        并等待回调和授权代码。 设备代码方法打印 URL 和一次性
        代码，然后轮询直到浏览器端授权完成。

        Args:
            open_browser: 是否自动打开浏览器。
            auth_method: 使用的登录方法：“浏览器”或“device_code”。

        Returns:
            获得的OAuth凭据。

        Raises:
            RuntimeError: 如果 OAuth 流程失败或超时。
        """
        if auth_method == "device_code":
            return await self._login_with_device_code()
        if auth_method != "browser":
            raise ValueError(f"Unsupported OpenAI auth method: {auth_method}")

        code_verifier, code_challenge = _generate_pkce()
        state = generate_token(32)
        redirect_uri = f"http://localhost:{self._oauth_port}/auth/callback"
        auth_url = _build_authorize_url(redirect_uri, code_challenge, state)

        # 未来将收到回调结果
        callback_future: asyncio.Future[dict[str, Any]] = asyncio.Future()

        # 为回调创建 aiohttp 应用程序
        app = web.Application()

        async def handle_callback(request: web.Request) -> web.Response:
            params = request.query

            if "error" in params:
                error_msg = params.get("error_description", params["error"])
                if not callback_future.done():
                    callback_future.set_exception(RuntimeError(error_msg))
                return web.Response(
                    text=_HTML_ERROR.format(error=error_msg),
                    content_type="text/html",
                )

            code = params.get("code")
            if not code:
                error_msg = "Missing authorization code"
                if not callback_future.done():
                    callback_future.set_exception(RuntimeError(error_msg))
                return web.Response(
                    text=_HTML_ERROR.format(error=error_msg),
                    content_type="text/html",
                    status=400,
                )

            if params.get("state") != state:
                error_msg = "Invalid state - potential CSRF attack"
                if not callback_future.done():
                    callback_future.set_exception(RuntimeError(error_msg))
                return web.Response(
                    text=_HTML_ERROR.format(error=error_msg),
                    content_type="text/html",
                    status=400,
                )

            try:
                tokens = await _exchange_code_for_tokens(
                    code, redirect_uri, code_verifier
                )
                if not callback_future.done():
                    callback_future.set_result(tokens)
                return web.Response(text=_HTML_SUCCESS, content_type="text/html")
            except Exception as e:
                if not callback_future.done():
                    callback_future.set_exception(e)
                return web.Response(
                    text=_HTML_ERROR.format(error=str(e)),
                    content_type="text/html",
                    status=500,
                )

        app.router.add_get("/auth/callback", handle_callback)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", self._oauth_port)

        try:
            try:
                await site.start()
            except OSError as exc:
                if "address already in use" in str(exc).lower():
                    raise RuntimeError(
                        "OAuth callback server port "
                        f"{self._oauth_port} is already in use. "
                        "Please free the port or set a different one via "
                        "OPENHANDS_OAUTH_PORT."
                    ) from exc
                raise

            logger.debug(f"OAuth callback server started on port {self._oauth_port}")

            if open_browser:
                logger.info("Opening browser for OpenAI authentication...")
                webbrowser.open(auth_url)
            else:
                logger.info(
                    f"Please open the following URL in your browser:\n{auth_url}"
                )

            try:
                tokens = await asyncio.wait_for(
                    callback_future, timeout=OAUTH_TIMEOUT_SECONDS
                )
            except TimeoutError:
                raise RuntimeError(
                    "OAuth callback timeout - authorization took too long"
                )

            expires_at = int(time.time() * 1000) + (
                tokens.get("expires_in", 3600) * 1000
            )
            credentials = OAuthCredentials(
                vendor=self.vendor,
                access_token=tokens["access_token"],
                refresh_token=tokens["refresh_token"],
                expires_at=expires_at,
            )
            self._credential_store.save(credentials)
            logger.info("OpenAI OAuth login successful")
            return credentials

        finally:
            await runner.cleanup()

    async def start_device_login(self) -> DeviceCode:
        """启动设备代码 OAuth 登录流程而不进行轮询。"""
        return await _request_device_code()

    async def poll_device_login(
        self, device_code: DeviceCode, *, persist: bool = True
    ) -> OAuthCredentials | None:
        """轮询一次设备代码 OAuth 登录结果。

        当授权仍待处理时返回 ``None``。
        """
        code_response = await _poll_device_code_once(device_code)
        if code_response is None:
            return None
        return await self._complete_device_login(code_response, persist=persist)

    async def _login_with_device_code(self) -> OAuthCredentials:
        """执行设备代码 OAuth 登录流程。"""
        device_code = await _request_device_code()
        logger.info(
            "Open this URL in your browser and enter the one-time code:\n"
            f"{device_code.verification_url}\n\n"
            f"Code: {device_code.user_code}\n\n"
            "Device codes are a common phishing target. Never share this code."
        )
        print(
            "\nOpen this URL in your browser and sign in to ChatGPT:\n"
            f"{device_code.verification_url}\n\n"
            f"Enter code: {device_code.user_code}\n\n"
            "Device codes are a common phishing target. Never share this code.\n"
        )

        code_response = await _poll_device_code(device_code)
        return await self._complete_device_login(code_response)

    async def _complete_device_login(
        self, code_response: dict[str, Any], *, persist: bool = True
    ) -> OAuthCredentials:
        """交换已完成的设备身份验证响应。

        交换成功后可选择保留凭据。
        """
        try:
            authorization_code = code_response["authorization_code"]
            code_verifier = code_response["code_verifier"]
        except KeyError as exc:
            raise RuntimeError("Invalid device token response from OpenAI") from exc

        tokens = await _exchange_code_for_tokens(
            authorization_code,
            f"{ISSUER}/deviceauth/callback",
            code_verifier,
        )

        expires_at = int(time.time() * 1000) + (tokens.get("expires_in", 3600) * 1000)
        credentials = OAuthCredentials(
            vendor=self.vendor,
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            expires_at=expires_at,
        )
        if persist:
            self.save_credentials(credentials)
        logger.info("OpenAI device-code login successful")
        return credentials

    def save_credentials(self, credentials: OAuthCredentials) -> None:
        """持久化OpenAI订阅凭据。"""
        self._credential_store.save(credentials)

    def extract_chatgpt_account_id(self, credentials: OAuthCredentials) -> str | None:
        """返回请求标头的 ChatGPT 帐户 ID（如果存在）。"""
        return _extract_chatgpt_account_id(credentials.access_token)

    def logout(self) -> bool:
        """删除存储的凭据。

        Returns:
            如果凭据被删除，则为 True；如果 None 存在，则为 False。
        """
        return self._credential_store.delete(self.vendor)

    def create_llm(
        self,
        model: str = "gpt-5.5",
        credentials: OAuthCredentials | None = None,
        instructions: str | None = None,
        **llm_kwargs: Any,
    ) -> LLM:
        """创建一个配置用于 Codex 订阅访问的 LLM 实例。

        Args:
            model: 要使用的模型（必须位于 OPENAI_CODEX_MODELS 中）。
            credentials: OAuth 凭据使用。 如果 None, 使用存储的凭据。
            instructions: Codex 模型的可选说明。
            **llm_kwargs: 要传递给 LLM 构造函数的其他参数。

        Returns:
            配置用于 Codex 访问的 LLM 实例。

        Raises:
            ValueError: 如果该型号不受支持或没有可用的凭据。
        """
        from openhands.sdk.llm.llm import LLM

        if model not in OPENAI_CODEX_MODELS:
            raise ValueError(
                f"Model '{model}' is not supported for subscription access. "
                f"Supported models: {', '.join(sorted(OPENAI_CODEX_MODELS))}"
            )

        creds = credentials or self.get_credentials()
        if creds is None:
            raise ValueError(
                "No credentials available. Call login() first or provide credentials."
            )

        account_id = _extract_chatgpt_account_id(creds.access_token)
        if not account_id:
            logger.warning(
                "Could not extract chatgpt_account_id from access token. "
                "API requests may fail."
            )

        # 使用 Codex 特定参数构建 extra_body
        extra_body: dict[str, Any] = {"store": False}
        if instructions:
            extra_body["instructions"] = instructions
        if "litellm_extra_body" in llm_kwargs:
            extra_body.update(llm_kwargs.pop("litellm_extra_body"))

        # 构建与 OpenAI 的官方 Codex CLI 匹配的标头
        extra_headers: dict[str, str] = {
            "originator": "codex_cli_rs",
            "OpenAI-Beta": "responses=experimental",
            "User-Agent": f"openhands-sdk ({platform.system()}; {platform.machine()})",
        }
        if account_id:
            extra_headers["chatgpt-account-id"] = account_id

        # Codex API 需要流式传输，但不支持温度/max_output_tokens
        llm = LLM(
            model=f"openai/{model}",
            base_url=CODEX_API_ENDPOINT.rsplit("/", 1)[0],
            api_key=None,
            extra_headers=extra_headers,
            litellm_extra_body=extra_body,
            temperature=None,
            max_output_tokens=None,
            stream=True,
            auth_type="subscription",
            subscription_vendor="openai",
            **llm_kwargs,
        )
        llm.is_subscription = True
        # 确保这些保持 None，即使模型信息尝试设置它们
        llm.max_output_tokens = None
        llm._effective_max_output_tokens = None
        llm.temperature = None
        llm.auth_type = "subscription"
        llm.subscription_vendor = "openai"
        llm._subscription_credential_store = self._credential_store
        llm._subscription_credentials = creds
        return llm


async def subscription_login_async(
    vendor: SupportedVendor = "openai",
    model: str = "gpt-5.5",
    force_login: bool = False,
    open_browser: bool = True,
    auth_method: OpenAIAuthMethod = "browser",
    skip_consent: bool = False,
    **llm_kwargs: Any,
) -> LLM:
    """使用订阅进行身份验证并返回 LLM 实例。

    这是基于订阅的 LLM 访问的主要入口。 它处理凭据缓存、token 刷新和登录流程。

    Args:
        vendor: 供应商/提供商（当前仅支持“OpenAI”）。
        model: 要使用的模型。
        force_login: 如果 True，则始终执行全新登录。
        open_browser: 是否自动打开浏览器登录。
        auth_method: 使用的登录方法：“浏览器”或“device_code”。
        skip_consent: 如果 True，则跳过同意提示词（用于编程使用
            已通过其他方式取得同意的情况）。
        **llm_kwargs: 要传递给 LLM 构造函数的其他参数。

    Returns:
        配置用于订阅访问的 LLM 实例。

    Raises:
        ValueError: 如果供应商不受支持。
        RuntimeError: 如果身份验证失败或用户拒绝同意。

    Example:
        >>> import asyncio
        >>> from openhands.sdk.llm.auth import subscription_login_async
        >>> llm = asyncio.run(subscription_login_async(model="gpt-5.6"))
    """
    if vendor != "openai":
        raise ValueError(
            f"Vendor '{vendor}' is not supported. Only 'openai' is supported."
        )

    auth = OpenAISubscriptionAuth()

    # 检查现有的有效凭据
    if not force_login:
        creds = await auth.refresh_if_needed()
        if creds is not None:
            logger.info("Using existing OpenAI credentials")
            return auth.create_llm(model=model, credentials=creds, **llm_kwargs)

    # 显示同意横幅并在登录前获得确认
    if not skip_consent:
        if not _display_consent_and_confirm():
            raise RuntimeError("User declined to continue with ChatGPT sign-in")

    # 执行登录
    creds = await auth.login(open_browser=open_browser, auth_method=auth_method)
    return auth.create_llm(model=model, credentials=creds, **llm_kwargs)


def create_subscription_llm_from_config(llm: LLM) -> LLM:
    """从已序列化 LLM 配置创建运行时订阅 LLM。"""
    if llm.auth_type != "subscription":
        return llm
    # 已序列化配置恢复标志，但不恢复运行时凭据。
    if llm.is_subscription and llm._subscription_credentials is not None:
        return llm

    vendor = llm.subscription_vendor or "openai"
    if vendor != "openai":
        raise ValueError(f"Unsupported subscription vendor: {vendor}")

    model = llm.model
    if model.startswith("openai/"):
        model = model.removeprefix("openai/")

    auth = OpenAISubscriptionAuth()
    credentials = auth.refresh_if_needed_sync()
    if credentials is None:
        raise ValueError("OpenAI subscription login is required")

    llm_kwargs = llm.model_dump(
        exclude_none=True,
        exclude_defaults=True,
        exclude={
            "model",
            "api_key",
            "base_url",
            "auth_type",
            "subscription_vendor",
            "extra_headers",
            "max_output_tokens",
            "stream",
            "temperature",
            "is_subscription",
        },
    )
    llm_kwargs["usage_id"] = llm.usage_id

    return auth.create_llm(
        model=model,
        credentials=credentials,
        **llm_kwargs,
    )


def subscription_login(
    vendor: SupportedVendor = "openai",
    model: str = "gpt-5.5",
    force_login: bool = False,
    open_browser: bool = True,
    auth_method: OpenAIAuthMethod = "browser",
    skip_consent: bool = False,
    **llm_kwargs: Any,
) -> LLM:
    """同步 subscription_login_async 的包装。

    请参阅 subscription_login_async 获取完整文档。
    """
    return asyncio.run(
        subscription_login_async(
            vendor=vendor,
            model=model,
            force_login=force_login,
            open_browser=open_browser,
            auth_method=auth_method,
            skip_consent=skip_consent,
            **llm_kwargs,
        )
    )


# =========================================================================
# 订阅模式的消息转换实用程序
# =========================================================================

DEFAULT_SYSTEM_MESSAGE = (
    "You are OpenHands agent, a helpful AI assistant that can interact "
    "with a computer to solve tasks."
)


def inject_system_prefix(
    input_items: list[dict[str, Any]], prefix_content: dict[str, Any]
) -> None:
    """将系统前缀插入到第一条用户消息中，或创建一个。

    这会就地修改 input_items。

    Args:
        input_items: 要修改的输入项（消息）列表。
        prefix_content: 要添加的内容字典
            （e.g.，{“类型”：“input_text”，“文本”：“...”}）。
    """
    for item in input_items:
        if item.get("type") == "message" and item.get("role") == "user":
            content = item.get("content")
            if not isinstance(content, list):
                content = [content] if content else []
            item["content"] = [prefix_content] + content
            return

    # 未找到用户消息，请创建一条合成消息
    input_items.insert(0, {"role": "user", "content": [prefix_content]})


def transform_for_subscription(
    system_chunks: list[str], input_items: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    """转换 Codex 订阅的消息传输层。

    Codex 订阅端点拒绝复杂/长的 `instructions`，所以我们：
    1. 使用最小的默认指令字符串
    2. 将系统提示词添加到第一条用户消息之前
    3. 标准化消息格式以匹配 OpenCode 的 Codex 客户端

    Args:
        system_chunks: 要合并的系统提示词字符串列表。
        input_items: 要转换的输入项（消息）列表。

    Returns:
        (指令，normalized_input_items) 的元组。
    """
    # 将系统提示词添加到第一条用户消息之前
    if system_chunks:
        merged = "\n\n---\n\n".join(system_chunks)
        prefix_content = {
            "type": "input_text",
            "text": f"Context (system prompt):\n{merged}\n\n",
        }
        inject_system_prefix(input_items, prefix_content)

    # 规范化： {"type": "message", ...} -> {"role": ..., "content": ...}
    normalized = [
        {"role": item.get("role"), "content": item.get("content") or []}
        if item.get("type") == "message"
        else item
        for item in input_items
    ]
    return DEFAULT_SYSTEM_MESSAGE, normalized
