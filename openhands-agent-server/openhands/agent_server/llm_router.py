"""LLM 模型、提供商和订阅信息端点的路由器。"""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from openhands.sdk.llm.auth.openai import (
    DEVICE_CODE_TIMEOUT_SECONDS,
    OPENAI_CODEX_MODELS,
    DeviceCode,
    OpenAISubscriptionAuth,
)
from openhands.sdk.llm.utils.unverified_models import (
    _extract_model_and_provider,
    _get_litellm_provider_names,
    get_supported_llm_models,
)
from openhands.sdk.llm.utils.verified_models import VERIFIED_MODELS


llm_router = APIRouter(prefix="/llm", tags=["LLM"])


@dataclass(frozen=True)
class PendingDeviceLogin:
    """正在进行的设备代码登录的服务器端状态。"""

    device_code: DeviceCode
    expires_at: int
    epoch: int


_PENDING_OPENAI_DEVICE_LOGINS: dict[str, PendingDeviceLogin] = {}
_IN_FLIGHT_OPENAI_DEVICE_LOGINS: set[str] = set()
_OPENAI_DEVICE_LOGIN_LOCK = asyncio.Lock()
_OPENAI_DEVICE_LOGIN_EPOCH = 0


class ProvidersResponse(BaseModel):
    """包含可用 LLM 提供商列表的响应。"""

    providers: list[str]


class ModelsResponse(BaseModel):
    """包含可用 LLM 模型列表的响应。"""

    models: list[str]


class VerifiedModelsResponse(BaseModel):
    """响应包含由提供商组织的经过验证的 LLM 模型。"""

    models: dict[str, list[str]]


class SubscriptionStatusResponse(BaseModel):
    """安全订阅身份验证状态。"""

    vendor: str = "openai"
    connected: bool
    account_email: str | None = None
    expires_at: int | None = None


class SubscriptionDeviceStartResponse(BaseModel):
    """浏览器登录的设备代码质询详细信息。"""

    device_code: str = Field(description="Opaque server-side polling token.")
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None = None
    expires_at: int
    interval_seconds: int


class SubscriptionDevicePollRequest(BaseModel):
    """对先前启动的订阅设备登录的轮询请求。"""

    device_code: str


class SubscriptionModelsResponse(BaseModel):
    """通过订阅提供商提供的模型。"""

    vendor: str = "openai"
    models: list[str]


def _get_openai_subscription_auth() -> OpenAISubscriptionAuth:
    return OpenAISubscriptionAuth()


def _status_from_auth(auth: OpenAISubscriptionAuth) -> SubscriptionStatusResponse:
    creds = auth.get_credentials()
    if creds is None or creds.is_expired():
        return SubscriptionStatusResponse(connected=False)
    return SubscriptionStatusResponse(connected=True, expires_at=creds.expires_at)


def _drop_expired_device_logins() -> None:
    now = int(time.time() * 1000)
    for key, pending in list(_PENDING_OPENAI_DEVICE_LOGINS.items()):
        if pending.expires_at <= now:
            _PENDING_OPENAI_DEVICE_LOGINS.pop(key, None)


@llm_router.get("/providers", response_model=ProvidersResponse)
async def list_providers() -> ProvidersResponse:
    """列出 LiteLLM 支持的所有可用 LLM 提供程序。"""
    providers = sorted(_get_litellm_provider_names())
    return ProvidersResponse(providers=providers)


@llm_router.get("/models", response_model=ModelsResponse)
async def list_models(
    provider: str | None = Query(
        default=None,
        description="Filter models by provider (e.g., 'openai', 'anthropic')",
    ),
) -> ModelsResponse:
    """列出 LiteLLM 支持的所有可用 LLM 模型。

    Args:
        provider: 用于过滤模型的可选提供商名称。

    Note: 除非配置 AWS 凭据，否则基岩模型将被排除。
    """
    all_models = get_supported_llm_models()

    if provider is None:
        models = sorted(set(all_models))
    else:
        filtered_models = []
        verified_provider_models = set(VERIFIED_MODELS.get(provider, ()))
        for model in all_models:
            model_provider, _, _ = _extract_model_and_provider(model)
            if model_provider == provider or (
                model in verified_provider_models
                # 命名空间验证条目（OpenRouter id 带有
                # ``openrouter/`` 前缀被去除，e.g。 ``deepseek/deepseek-chat``) 可能会与
                # 其他提供商的同名真实目录模型发生冲突。 当它发生时，模型会提取到那个其
                # 他提供商那里，因此只有在模型不解析到不同提供商时才验证列表匹配。
                #
                and not ("/" in model and model_provider and model_provider != provider)
            ):
                filtered_models.append(model)
        models = sorted(set(filtered_models))

    return ModelsResponse(models=models)


@llm_router.get("/models/verified", response_model=VerifiedModelsResponse)
async def list_verified_models() -> VerifiedModelsResponse:
    """列出由提供商组织的所有经过验证的 LLM 模型。

    验证模型是那些经过测试并确认运行良好的模型
    with OpenHands.
    """
    return VerifiedModelsResponse(models=VERIFIED_MODELS)


@llm_router.get(
    "/subscription/openai/models", response_model=SubscriptionModelsResponse
)
async def list_openai_subscription_models() -> SubscriptionModelsResponse:
    """列出可通过 ChatGPT 订阅身份验证获得的型号。"""
    return SubscriptionModelsResponse(models=sorted(OPENAI_CODEX_MODELS))


@llm_router.get(
    "/subscription/openai/status", response_model=SubscriptionStatusResponse
)
async def get_openai_subscription_status() -> SubscriptionStatusResponse:
    """返回不带 token 的安全 ChatGPT 订阅连接状态。"""
    auth = _get_openai_subscription_auth()
    try:
        await auth.refresh_if_needed()
    except (RuntimeError, httpx.HTTPError):
        # 拒绝刷新 (RuntimeError) 或无法访问 auth.openai.com（httpx 传输层错误）现在都不
        # 会留下任何可用的登录信息。
        #
        return SubscriptionStatusResponse(connected=False)
    return _status_from_auth(auth)


@llm_router.post(
    "/subscription/openai/device/start",
    response_model=SubscriptionDeviceStartResponse,
)
async def start_openai_subscription_device_login() -> SubscriptionDeviceStartResponse:
    """开始 ChatGPT 设备代码登录而不返回 token。"""
    auth = _get_openai_subscription_auth()
    challenge = await auth.start_device_login()
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time() * 1000) + (DEVICE_CODE_TIMEOUT_SECONDS * 1000)
    async with _OPENAI_DEVICE_LOGIN_LOCK:
        _drop_expired_device_logins()
        _PENDING_OPENAI_DEVICE_LOGINS[token] = PendingDeviceLogin(
            device_code=challenge,
            expires_at=expires_at,
            epoch=_OPENAI_DEVICE_LOGIN_EPOCH,
        )
    return SubscriptionDeviceStartResponse(
        device_code=token,
        user_code=challenge.user_code,
        verification_uri=challenge.verification_url,
        expires_at=expires_at,
        interval_seconds=challenge.interval,
    )


@llm_router.post(
    "/subscription/openai/device/poll", response_model=SubscriptionStatusResponse
)
async def poll_openai_subscription_device_login(
    request: SubscriptionDevicePollRequest,
) -> SubscriptionStatusResponse:
    """轮询 ChatGPT 设备代码登录而不返回 token。"""
    async with _OPENAI_DEVICE_LOGIN_LOCK:
        _drop_expired_device_logins()
        pending = _PENDING_OPENAI_DEVICE_LOGINS.pop(request.device_code, None)
        if pending is None:
            if request.device_code in _IN_FLIGHT_OPENAI_DEVICE_LOGINS:
                return SubscriptionStatusResponse(connected=False)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription device login not found or expired",
            )
        _IN_FLIGHT_OPENAI_DEVICE_LOGINS.add(request.device_code)

    auth = _get_openai_subscription_auth()
    credentials = None
    try:
        credentials = await auth.poll_device_login(pending.device_code, persist=False)
    finally:
        async with _OPENAI_DEVICE_LOGIN_LOCK:
            _IN_FLIGHT_OPENAI_DEVICE_LOGINS.discard(request.device_code)
            # 如果提供者仍待处理或者轮询请求在获取凭据之前失败，请保持不透明轮询 token
            # 可用。
            #
            if credentials is None and pending.epoch == _OPENAI_DEVICE_LOGIN_EPOCH:
                _PENDING_OPENAI_DEVICE_LOGINS[request.device_code] = pending

    async with _OPENAI_DEVICE_LOGIN_LOCK:
        current_epoch = _OPENAI_DEVICE_LOGIN_EPOCH
        if credentials is None:
            return SubscriptionStatusResponse(connected=False)
        if pending.epoch != current_epoch:
            return SubscriptionStatusResponse(connected=False)
        auth.save_credentials(credentials)
        return SubscriptionStatusResponse(
            connected=True, expires_at=credentials.expires_at
        )


@llm_router.post(
    "/subscription/openai/logout", response_model=SubscriptionStatusResponse
)
async def logout_openai_subscription() -> SubscriptionStatusResponse:
    """删除存储的 ChatGPT 订阅凭据。"""
    global _OPENAI_DEVICE_LOGIN_EPOCH

    auth = _get_openai_subscription_auth()
    async with _OPENAI_DEVICE_LOGIN_LOCK:
        _OPENAI_DEVICE_LOGIN_EPOCH += 1
        _PENDING_OPENAI_DEVICE_LOGINS.clear()
        auth.logout()
    return SubscriptionStatusResponse(connected=False)
