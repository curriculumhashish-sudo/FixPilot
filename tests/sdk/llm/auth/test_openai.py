"""测试 OpenAI 订阅身份验证。

Note: JWT 验证和 JWKS 缓存测试已被删除，因为它们
需要真正的 OAuth token 才有意义。 请参阅 GitHub 问题 #1806 了解跟踪集成测试要求。
"""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from joserfc import jwt as joserfc_jwt
from joserfc.jwk import KeySet, RSAKey

from openhands.sdk.llm import LLM
from openhands.sdk.llm.auth.credentials import CredentialStore, OAuthCredentials
from openhands.sdk.llm.auth.openai import (
    CLIENT_ID,
    CONSENT_BANNER,
    ISSUER,
    OPENAI_CODEX_MODELS,
    DeviceCode,
    OpenAISubscriptionAuth,
    _build_authorize_url,
    _display_consent_and_confirm,
    _extract_chatgpt_account_id,
    _generate_pkce,
    _get_consent_marker_path,
    _has_acknowledged_consent,
    _mark_consent_acknowledged,
    _poll_device_code,
    _request_device_code,
    create_subscription_llm_from_config,
)


def test_subscription_config_leaves_api_key_llm_unchanged():
    llm = LLM(model="gpt-4o", api_key="test-key")
    with patch.object(OpenAISubscriptionAuth, "refresh_if_needed_sync") as refresh:
        assert create_subscription_llm_from_config(llm) is llm
    refresh.assert_not_called()


def test_subscription_config_restores_credentials():
    llm = LLM(model="openai/gpt-5.6-sol", auth_type="subscription", usage_id="restored")
    credentials = OAuthCredentials(
        vendor="openai",
        access_token="test-access",
        refresh_token="test-refresh",
        expires_at=int(time.time() * 1000) + 3600_000,
    )
    with patch.object(
        OpenAISubscriptionAuth, "refresh_if_needed_sync", return_value=credentials
    ) as refresh:
        restored = create_subscription_llm_from_config(llm)
        assert create_subscription_llm_from_config(restored) is restored
    refresh.assert_called_once()
    assert restored.usage_id == "restored"
    assert restored.is_subscription
    assert restored.auth_type == "subscription"
    assert restored._get_litellm_api_key_value() == "test-access"


def test_generate_pkce():
    """测试 PKCE 代码生成。"""
    verifier, challenge = _generate_pkce()
    assert verifier is not None
    assert challenge is not None
    assert len(verifier) > 0
    assert len(challenge) > 0
    # 验证者和挑战者应该不同
    assert verifier != challenge


def test_pkce_codes_are_unique():
    """测试 PKCE 代码每次都是唯一的。"""
    verifier1, challenge1 = _generate_pkce()
    verifier2, challenge2 = _generate_pkce()
    assert verifier1 != verifier2
    assert challenge1 != challenge2


def test_build_authorize_url():
    """测试构建 OAuth 授权 URL。"""
    code_challenge = "test_challenge"
    state = "test_state"
    redirect_uri = "http://localhost:1455/auth/callback"

    url = _build_authorize_url(redirect_uri, code_challenge, state)

    assert url.startswith(f"{ISSUER}/oauth/authorize?")
    assert f"client_id={CLIENT_ID}" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback" in url
    assert "code_challenge=test_challenge" in url
    assert "code_challenge_method=S256" in url
    assert "state=test_state" in url
    assert "originator=openhands" in url
    assert "response_type=code" in url


def test_openai_subscription_auth_get_credentials(tmp_path):
    """测试从商店获取凭据。"""
    store = CredentialStore(credentials_dir=tmp_path)
    auth = OpenAISubscriptionAuth(credential_store=store)

    # 最初没有凭据
    assert auth.get_credentials() is None

    # 保存凭据
    creds = OAuthCredentials(
        vendor="openai",
        access_token="test_access",
        refresh_token="test_refresh",
        expires_at=int(time.time() * 1000) + 3600_000,
    )
    store.save(creds)

    # 现在应该返回凭据
    retrieved = auth.get_credentials()
    assert retrieved is not None
    assert retrieved.access_token == "test_access"


def test_openai_subscription_auth_has_valid_credentials(tmp_path):
    """测试检查是否有效凭据。"""
    store = CredentialStore(credentials_dir=tmp_path)
    auth = OpenAISubscriptionAuth(credential_store=store)

    # 没有凭据
    assert not auth.has_valid_credentials()

    # 有效凭据
    valid_creds = OAuthCredentials(
        vendor="openai",
        access_token="test",
        refresh_token="test",
        expires_at=int(time.time() * 1000) + 3600_000,
    )
    store.save(valid_creds)
    assert auth.has_valid_credentials()

    # 已过期凭据
    expired_creds = OAuthCredentials(
        vendor="openai",
        access_token="test",
        refresh_token="test",
        expires_at=int(time.time() * 1000) - 3600_000,
    )
    store.save(expired_creds)
    assert not auth.has_valid_credentials()


def test_openai_subscription_auth_logout(tmp_path):
    """测试注销删除凭据。"""
    store = CredentialStore(credentials_dir=tmp_path)
    auth = OpenAISubscriptionAuth(credential_store=store)

    # 保存凭据
    creds = OAuthCredentials(
        vendor="openai",
        access_token="test",
        refresh_token="test",
        expires_at=int(time.time() * 1000) + 3600_000,
    )
    store.save(creds)
    assert auth.has_valid_credentials()

    # 退出
    assert auth.logout() is True
    assert not auth.has_valid_credentials()

    # 再次注销应返回 False
    assert auth.logout() is False


def test_openai_subscription_auth_create_llm_invalid_model(tmp_path):
    """测试 create_llm 引发无效模型的错误。"""
    store = CredentialStore(credentials_dir=tmp_path)
    auth = OpenAISubscriptionAuth(credential_store=store)

    # 保存有效凭据
    creds = OAuthCredentials(
        vendor="openai",
        access_token="test",
        refresh_token="test",
        expires_at=int(time.time() * 1000) + 3600_000,
    )
    store.save(creds)

    with pytest.raises(ValueError, match="not supported for subscription access"):
        auth.create_llm(model="gpt-4o-mini")


def test_openai_subscription_auth_create_llm_no_credentials(tmp_path):
    """当没有凭据可用时，测试 create_llm 会引发错误。"""
    store = CredentialStore(credentials_dir=tmp_path)
    auth = OpenAISubscriptionAuth(credential_store=store)

    with pytest.raises(ValueError, match="No credentials available"):
        auth.create_llm(model="gpt-5.6-sol")


@pytest.mark.parametrize("model", sorted(OPENAI_CODEX_MODELS))
def test_openai_subscription_auth_create_llm_success(tmp_path, model):
    """测试 create_llm 创建具有正确配置的 LLM。"""
    store = CredentialStore(credentials_dir=tmp_path)
    auth = OpenAISubscriptionAuth(credential_store=store)

    # 保存有效凭据
    creds = OAuthCredentials(
        vendor="openai",
        access_token="test_access_token",
        refresh_token="test_refresh",
        expires_at=int(time.time() * 1000) + 3600_000,
    )
    store.save(creds)

    llm = auth.create_llm(model=model)

    assert llm.model == f"openai/{model}"
    assert llm.api_key is None
    assert llm._get_litellm_api_key_value() == "test_access_token"
    assert llm.auth_type == "subscription"
    assert llm.subscription_vendor == "openai"
    assert llm.extra_headers is not None
    # 使用 codex_cli_rs 来匹配官方 Codex CLI 以实现兼容性
    assert llm.extra_headers.get("originator") == "codex_cli_rs"


class _FakeAsyncClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.posts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _response(status_code=200, payload=None):
    return SimpleNamespace(
        status_code=status_code,
        is_success=200 <= status_code < 300,
        json=lambda: payload or {},
    )


@pytest.mark.asyncio
async def test_request_device_code_success():
    """测试请求 OpenAI 设备代码。"""
    fake_client = _FakeAsyncClient(
        [
            _response(
                payload={
                    "device_auth_id": "device-auth-123",
                    "user_code": "ABCD-1234",
                    "interval": "2",
                }
            )
        ]
    )

    with patch("openhands.sdk.llm.auth.openai.AsyncClient", return_value=fake_client):
        device_code = await _request_device_code()

    assert device_code == DeviceCode(
        verification_url=f"{ISSUER}/codex/device",
        user_code="ABCD-1234",
        device_auth_id="device-auth-123",
        interval=2,
    )
    assert fake_client.posts == [
        (
            f"{ISSUER}/api/accounts/deviceauth/usercode",
            {
                "json": {"client_id": CLIENT_ID},
                "headers": {"Content-Type": "application/json"},
            },
        )
    ]


@pytest.mark.asyncio
async def test_poll_device_code_retries_pending_then_succeeds():
    """测试轮询 OpenAI 设备身份验证令牌端点。"""
    fake_client = _FakeAsyncClient(
        [
            _response(status_code=403),
            _response(
                payload={
                    "authorization_code": "auth-code",
                    "code_verifier": "verifier",
                    "code_challenge": "challenge",
                }
            ),
        ]
    )
    device_code = DeviceCode(
        verification_url=f"{ISSUER}/codex/device",
        user_code="ABCD-1234",
        device_auth_id="device-auth-123",
        interval=1,
    )

    with (
        patch("openhands.sdk.llm.auth.openai.AsyncClient", return_value=fake_client),
        patch("openhands.sdk.llm.auth.openai.asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await _poll_device_code(device_code)

    assert result["authorization_code"] == "auth-code"
    assert fake_client.posts == [
        (
            f"{ISSUER}/api/accounts/deviceauth/token",
            {
                "json": {
                    "device_auth_id": "device-auth-123",
                    "user_code": "ABCD-1234",
                },
                "headers": {"Content-Type": "application/json"},
            },
        ),
        (
            f"{ISSUER}/api/accounts/deviceauth/token",
            {
                "json": {
                    "device_auth_id": "device-auth-123",
                    "user_code": "ABCD-1234",
                },
                "headers": {"Content-Type": "application/json"},
            },
        ),
    ]


@pytest.mark.asyncio
async def test_openai_subscription_auth_login_device_code(tmp_path):
    """测试设备代码登录存储 OAuth 凭据。"""
    store = CredentialStore(credentials_dir=tmp_path)
    auth = OpenAISubscriptionAuth(credential_store=store)
    device_code = DeviceCode(
        verification_url=f"{ISSUER}/codex/device",
        user_code="ABCD-1234",
        device_auth_id="device-auth-123",
        interval=1,
    )

    with (
        patch(
            "openhands.sdk.llm.auth.openai._request_device_code",
            new_callable=AsyncMock,
        ) as mock_request,
        patch(
            "openhands.sdk.llm.auth.openai._poll_device_code",
            new_callable=AsyncMock,
        ) as mock_poll,
        patch(
            "openhands.sdk.llm.auth.openai._exchange_code_for_tokens",
            new_callable=AsyncMock,
        ) as mock_exchange,
    ):
        mock_request.return_value = device_code
        mock_poll.return_value = {
            "authorization_code": "auth-code",
            "code_verifier": "verifier",
            "code_challenge": "challenge",
        }
        mock_exchange.return_value = {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
        }

        credentials = await auth.login(auth_method="device_code")

    assert credentials.access_token == "access"
    assert store.get("openai") is not None
    mock_exchange.assert_called_once_with(
        "auth-code",
        f"{ISSUER}/deviceauth/callback",
        "verifier",
    )


@pytest.mark.asyncio
async def test_openai_subscription_auth_refresh_if_needed_no_creds(tmp_path):
    """当没有凭据时，测试 refresh_if_needed 返回 None。"""
    store = CredentialStore(credentials_dir=tmp_path)
    auth = OpenAISubscriptionAuth(credential_store=store)

    result = await auth.refresh_if_needed()
    assert result is None


@pytest.mark.asyncio
async def test_openai_subscription_auth_refresh_if_needed_valid_creds(tmp_path):
    """测试 refresh_if_needed 返回未过期的现有信用。"""
    store = CredentialStore(credentials_dir=tmp_path)
    auth = OpenAISubscriptionAuth(credential_store=store)

    # 保存有效凭据
    creds = OAuthCredentials(
        vendor="openai",
        access_token="test_access",
        refresh_token="test_refresh",
        expires_at=int(time.time() * 1000) + 3600_000,
    )
    store.save(creds)

    result = await auth.refresh_if_needed()
    assert result is not None
    assert result.access_token == "test_access"


@pytest.mark.asyncio
async def test_openai_subscription_auth_refresh_if_needed_expired_creds(tmp_path):
    """测试 refresh_if_needed 刷新已过期凭据。"""
    store = CredentialStore(credentials_dir=tmp_path)
    auth = OpenAISubscriptionAuth(credential_store=store)

    # 保存已过期凭据
    creds = OAuthCredentials(
        vendor="openai",
        access_token="old_access",
        refresh_token="test_refresh",
        expires_at=int(time.time() * 1000) - 3600_000,
    )
    store.save(creds)

    # 模拟对象刷新功能
    with patch(
        "openhands.sdk.llm.auth.openai._refresh_access_token",
        new_callable=AsyncMock,
    ) as mock_refresh:
        mock_refresh.return_value = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_in": 3600,
        }

        result = await auth.refresh_if_needed()

        assert result is not None
        assert result.access_token == "new_access"
        mock_refresh.assert_called_once_with("test_refresh")


# =========================================================================
# 同意横幅系统测试
# =========================================================================


class TestConsentBannerSystem:
    """测试同意横幅和确认系统。"""

    def test_consent_banner_content(self):
        """测试同意横幅是否包含所需的文本。"""
        assert "ChatGPT" in CONSENT_BANNER
        assert "Terms of Use" in CONSENT_BANNER
        assert "openai.com/policies/terms-of-use" in CONSENT_BANNER

    def test_consent_marker_path(self, tmp_path):
        """测试同意标记路径是否位于凭据目录中。"""
        with patch(
            "openhands.sdk.llm.auth.openai.get_credentials_dir", return_value=tmp_path
        ):
            marker_path = _get_consent_marker_path()
            assert marker_path.parent == tmp_path
            assert ".chatgpt_consent_acknowledged" in str(marker_path)

    def test_has_acknowledged_consent_false_initially(self, tmp_path):
        """测试最初是否未确认同意。"""
        with patch(
            "openhands.sdk.llm.auth.openai.get_credentials_dir", return_value=tmp_path
        ):
            assert not _has_acknowledged_consent()

    def test_mark_consent_acknowledged(self, tmp_path):
        """测试标记同意是否已确认。"""
        with patch(
            "openhands.sdk.llm.auth.openai.get_credentials_dir", return_value=tmp_path
        ):
            assert not _has_acknowledged_consent()
            _mark_consent_acknowledged()
            assert _has_acknowledged_consent()

    def test_display_consent_user_accepts(self, tmp_path, capsys):
        """当用户接受时测试同意显示。"""
        with (
            patch(
                "openhands.sdk.llm.auth.openai.get_credentials_dir",
                return_value=tmp_path,
            ),
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", return_value="y"),
        ):
            result = _display_consent_and_confirm()
            assert result is True

            # 检查横幅已打印
            captured = capsys.readouterr()
            assert "ChatGPT" in captured.out
            assert "Terms of Use" in captured.out

    def test_display_consent_user_declines(self, tmp_path, capsys):
        """当用户拒绝时测试同意显示。"""
        with (
            patch(
                "openhands.sdk.llm.auth.openai.get_credentials_dir",
                return_value=tmp_path,
            ),
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", return_value="n"),
        ):
            result = _display_consent_and_confirm()
            assert result is False

    def test_display_consent_non_interactive_first_time_raises(self, tmp_path):
        """测试非交互模式第一次是否会引发错误。"""
        with (
            patch(
                "openhands.sdk.llm.auth.openai.get_credentials_dir",
                return_value=tmp_path,
            ),
            patch("sys.stdin.isatty", return_value=False),
        ):
            with pytest.raises(RuntimeError, match="non-interactive mode"):
                _display_consent_and_confirm()

    def test_display_consent_non_interactive_after_acknowledgment(self, tmp_path):
        """在事先确认后测试非交互模式是否有效。"""
        with patch(
            "openhands.sdk.llm.auth.openai.get_credentials_dir", return_value=tmp_path
        ):
            # 将同意标记为已确认
            _mark_consent_acknowledged()

            with patch("sys.stdin.isatty", return_value=False):
                result = _display_consent_and_confirm()
                assert result is True

    def test_display_consent_keyboard_interrupt(self, tmp_path):
        """测试同意期间键盘中断的处理。"""
        with (
            patch(
                "openhands.sdk.llm.auth.openai.get_credentials_dir",
                return_value=tmp_path,
            ),
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", side_effect=KeyboardInterrupt),
        ):
            result = _display_consent_and_confirm()
            assert result is False

    def test_display_consent_eof_error(self, tmp_path):
        """在同意期间测试 EOF 的处理。"""
        with (
            patch(
                "openhands.sdk.llm.auth.openai.get_credentials_dir",
                return_value=tmp_path,
            ),
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", side_effect=EOFError),
        ):
            result = _display_consent_and_confirm()
            assert result is False


# =========================================================================
# 使用 joserfc 对 _extract_chatgpt_account_id 进行端到端测试
# =========================================================================


@pytest.fixture
def rsa_signing_key():
    """生成用于 JWT 登录测试的 RSA 密钥对。"""
    return RSAKey.generate_key(2048, parameters={"kid": "test-key-1"})


@pytest.fixture
def mock_jwks_cache(rsa_signing_key):
    """模拟对象 _jwks_cache 返回带有测试公钥的 KeySet。"""
    pub_dict = rsa_signing_key.as_dict(private=False)
    key_set = KeySet.import_key_set({"keys": [pub_dict]})
    with patch(
        "openhands.sdk.llm.auth.openai._jwks_cache.get_key_set",
        return_value=key_set,
    ):
        yield


def _sign_jwt(key: RSAKey, claims: dict) -> str:
    """使用给定的 RSA 密钥和声明签署 JWT。"""
    header = {"alg": "RS256", "kid": key.kid}
    return joserfc_jwt.encode(header, claims, key)


def test_extract_chatgpt_account_id_success(rsa_signing_key, mock_jwks_cache):
    """端到端：用joserfc签署JWT，提取chatgpt_account_id。"""
    token = _sign_jwt(
        rsa_signing_key,
        {
            "sub": "user-123",
            "https://api.openai.com/auth": {
                "chatgpt_account_id": "acct-abc-456",
            },
        },
    )
    account_id = _extract_chatgpt_account_id(token)
    assert account_id == "acct-abc-456"


def test_extract_chatgpt_account_id_missing_claim(rsa_signing_key, mock_jwks_cache):
    """当 JWT 没有 chatgpt_account_id 声明时返回 None。"""
    token = _sign_jwt(rsa_signing_key, {"sub": "user-123"})
    assert _extract_chatgpt_account_id(token) is None


def test_extract_chatgpt_account_id_wrong_key(rsa_signing_key):
    """当 JWT 签名无法验证时（密钥错误），返回 None。"""
    # 使用测试密钥签名，但使用不同的密钥进行验证
    different_key = RSAKey.generate_key(2048, parameters={"kid": "other-key"})
    different_pub = different_key.as_dict(private=False)
    wrong_key_set = KeySet.import_key_set({"keys": [different_pub]})

    token = _sign_jwt(
        rsa_signing_key,
        {
            "sub": "user-123",
            "https://api.openai.com/auth": {
                "chatgpt_account_id": "acct-should-not-appear",
            },
        },
    )

    with patch(
        "openhands.sdk.llm.auth.openai._jwks_cache.get_key_set",
        return_value=wrong_key_set,
    ):
        assert _extract_chatgpt_account_id(token) is None


def test_extract_chatgpt_account_id_jwks_fetch_failure():
    """当 JWKS 缓存引发 RuntimeError 时，返回 None。"""
    with patch(
        "openhands.sdk.llm.auth.openai._jwks_cache.get_key_set",
        side_effect=RuntimeError("network error"),
    ):
        assert _extract_chatgpt_account_id("dummy.jwt.token") is None
